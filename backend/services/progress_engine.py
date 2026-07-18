# backend/services/progress_engine.py
# ProspectLens — Real-Time Collection Progress Engine

import json
from datetime import datetime
from sqlmodel import Session
from database.models import CollectionBatch
from services.sync_service import SyncBroadcaster

class CollectionProgressEngine:
    """
    Tracks and computes progress, ETA, and speed metrics for active collection sessions.
    Updates the database and broadcasts changes to clients in real-time.
    """

    @staticmethod
    def update_progress(
        session: Session,
        batch_id: str,
        listings_processed: int = None,
        failed_listings: int = None,
        skipped_listings: int = None,
        enriched_leads: int = None,
        duplicate_leads: int = None,
        successful_leads: int = None,
        current_listing: int = None,
        current_company_name: str = None,
        current_page: int = None,
        current_stage: str = None,
        status: str = None
    ) -> CollectionBatch:
        """
        Updates the session record and dynamically calculates progress percent, speed, and ETA.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            print(f"[ProgressEngine] Batch {batch_id} not found")
            return None

        # Update timestamps
        now = datetime.utcnow()
        batch.last_updated_at = now

        # Update status if requested
        if status is not None:
            batch.status = status
            if status in ["completed", "failed", "cancelled"]:
                batch.completed_at = now

        # Update increments
        if listings_processed is not None:
            batch.listings_processed = listings_processed
        if failed_listings is not None:
            batch.failed_listings = failed_listings
        if skipped_listings is not None:
            batch.skipped_listings = skipped_listings
        if enriched_leads is not None:
            batch.enriched_leads = enriched_leads
        if duplicate_leads is not None:
            batch.duplicate_leads = duplicate_leads
        
        if successful_leads is not None:
            batch.total_leads_stored = successful_leads
            batch.successful_records = successful_leads

        # Update current processing details
        if current_listing is not None:
            batch.current_listing = current_listing
        if current_company_name is not None:
            batch.current_company_name = current_company_name
        if current_page is not None:
            batch.current_page = current_page
        if current_stage is not None:
            batch.current_stage = current_stage

        # Calculate metrics if listings found is set
        total = batch.total_listings_found or batch.total_records or 0
        processed = batch.listings_processed

        if total > 0:
            batch.listings_remaining = max(0, total - processed)
            batch.progress_percentage = round(min(100.0, (processed / total) * 100.0), 1)
        else:
            batch.listings_remaining = 0
            batch.progress_percentage = 0.0

        # Speed and ETA calculations
        elapsed = (now - batch.started_at).total_seconds()
        if elapsed > 1.0 and processed > 0:
            batch.listings_per_second = round(processed / elapsed, 2)
            batch.avg_processing_time = round(elapsed / processed, 2)
            batch.avg_listing_time = batch.avg_processing_time
            # Continuously improve ETA
            batch.estimated_time_remaining = round(batch.listings_remaining * batch.avg_processing_time, 1)
        else:
            batch.listings_per_second = 0.0
            batch.avg_processing_time = 0.0
            batch.avg_listing_time = 0.0
            batch.estimated_time_remaining = 0.0

        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Broadcast update to frontend clients
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_PROGRESS_UPDATED",
            "batch_id": batch.batch_id,
            "status": batch.status,
            "progress_percentage": batch.progress_percentage,
            "listings_processed": batch.listings_processed,
            "listings_remaining": batch.listings_remaining,
            "estimated_time_remaining": batch.estimated_time_remaining,
            "listings_per_second": batch.listings_per_second,
            "current_company_name": batch.current_company_name,
            "current_stage": batch.current_stage
        })

        return batch

    @staticmethod
    def get_session_progress(session: Session, batch_id: str) -> dict:
        """
        Returns a serializable progress profile dictionary.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return {}

        return {
            "batch_id": batch.batch_id,
            "source_site": batch.source_site,
            "collection_mode": batch.collection_mode,
            "status": batch.status,
            "started_at": batch.started_at,
            "last_updated_at": batch.last_updated_at,
            "completed_at": batch.completed_at,
            "progress": {
                "total_listings_found": batch.total_listings_found,
                "listings_processed": batch.listings_processed,
                "listings_remaining": batch.listings_remaining,
                "successful_leads": batch.total_leads_stored,
                "failed_listings": batch.failed_listings,
                "skipped_listings": batch.skipped_listings,
                "enriched_leads": batch.enriched_leads,
                "duplicate_leads": batch.duplicate_leads,
                "progress_percentage": batch.progress_percentage
            },
            "current_processing": {
                "current_listing": batch.current_listing,
                "current_company_name": batch.current_company_name,
                "current_page": batch.current_page,
                "current_stage": batch.current_stage
            },
            "speed_metrics": {
                "listings_per_second": batch.listings_per_second,
                "avg_processing_time": batch.avg_processing_time,
                "avg_listing_time": batch.avg_listing_time,
                "estimated_time_remaining": batch.estimated_time_remaining
            }
        }
