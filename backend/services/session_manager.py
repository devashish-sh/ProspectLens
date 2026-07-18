# backend/services/session_manager.py
# ProspectLens — Collection Session Lifecycle Orchestrator

from datetime import datetime
from typing import Optional
from sqlmodel import Session
from database.models import CollectionBatch, SearchContext
from services import event_bus
from services.sync_service import SyncBroadcaster
from services.progress_engine import CollectionProgressEngine
from services.search_context_engine import SearchContextEngine
from services.error_tracker import CollectionErrorTracker

class CollectionSessionManager:
    """
    Central orchestrator coordinating the lifecycle of collection sessions.
    Transitions statuses, handles audits/errors, and triggers sync notifications.
    """

    @staticmethod
    def create_session(
        session: Session,
        source_site: str,
        search_query: str,
        collection_mode: str = "quick",
        search_url: Optional[str] = None,
        batch_name: Optional[str] = None
    ) -> CollectionBatch:
        """
        Creates a new collection batch (session) and seeds its search context.
        """
        name = batch_name or f"{source_site} — {search_query}"
        
        batch = CollectionBatch(
            batch_name=name,
            search_query=search_query,
            source_site=source_site,
            collection_mode=collection_mode,
            started_at=datetime.utcnow(),
            status="created",
            search_url=search_url,
            total_listings_found=0,
            last_updated_at=datetime.utcnow()
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Seed SearchContext
        SearchContextEngine.create_search_context(
            session=session,
            batch_id=batch.batch_id,
            website=source_site,
            search_keyword=search_query,
            original_search_url=search_url,
            collection_mode=collection_mode,
            started_by="manual"
        )

        # Publish starting events
        event_bus.EventBus.publish(event_bus.COLLECTION_STARTED, batch=batch)
        
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_CREATED",
            "batch_id": batch.batch_id,
            "status": batch.status
        })

        return batch

    @staticmethod
    def start_session(session: Session, batch_id: str) -> Optional[CollectionBatch]:
        """
        Transitions the collection session to the running state.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return None

        batch.status = "running"
        batch.last_updated_at = datetime.utcnow()
        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Update SearchContext status
        SearchContextEngine.update_search_context(
            session=session,
            batch_id=batch_id,
            search_status="pending"
        )

        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_STARTED",
            "batch_id": batch.batch_id,
            "status": batch.status
        })

        return batch

    @staticmethod
    def pause_session(session: Session, batch_id: str) -> Optional[CollectionBatch]:
        """
        Transitions the session status to paused.
        """
        batch = CollectionProgressEngine.update_progress(
            session=session,
            batch_id=batch_id,
            status="paused"
        )
        if batch:
            SyncBroadcaster.broadcast("STATE_UPDATED", {
                "action": "BATCH_PAUSED",
                "batch_id": batch_id,
                "status": "paused"
            })
        return batch

    @staticmethod
    def resume_session(session: Session, batch_id: str) -> Optional[CollectionBatch]:
        """
        Transitions the session through resuming and sets it back to running.
        """
        # Intermediate state transition
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return None
        
        batch.status = "resuming"
        batch.last_updated_at = datetime.utcnow()
        session.add(batch)
        session.commit()

        # Update to active running state
        batch = CollectionProgressEngine.update_progress(
            session=session,
            batch_id=batch_id,
            status="running"
        )
        if batch:
            SyncBroadcaster.broadcast("STATE_UPDATED", {
                "action": "BATCH_RESUMED",
                "batch_id": batch_id,
                "status": "running"
            })
        return batch

    @staticmethod
    def cancel_session(session: Session, batch_id: str, reason: Optional[str] = None) -> Optional[CollectionBatch]:
        """
        Cancels the session gracefully. Preserves stats and partially collected leads.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return None

        now = datetime.utcnow()
        batch.status = "cancelled"
        batch.completed_at = now
        batch.last_updated_at = now
        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Update search context
        duration = (now - batch.started_at).total_seconds()
        SearchContextEngine.update_search_context(
            session=session,
            batch_id=batch_id,
            search_status="cancelled",
            search_duration=duration,
            cancellation_reason=reason or "User Cancelled",
            listings_found=batch.total_listings_found,
            listings_processed=batch.listings_processed,
            successful_leads=batch.total_leads_stored,
            failed_leads=batch.failed_listings
        )

        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_CANCELLED",
            "batch_id": batch_id,
            "status": "cancelled",
            "reason": reason
        })

        return batch

    @staticmethod
    def complete_session(
        session: Session,
        batch_id: str,
        total_listings: Optional[int] = None,
        successful_leads: Optional[int] = None,
        failed_listings: Optional[int] = None,
        skipped_listings: Optional[int] = None,
        enriched_leads: Optional[int] = None,
        duplicate_leads: Optional[int] = None
    ) -> Optional[CollectionBatch]:
        """
        Completes the session, calculates duration, writes final stats, and publishes finished events.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return None

        now = datetime.utcnow()
        batch.status = "completed"
        batch.completed_at = now
        batch.last_updated_at = now

        if total_listings is not None:
            batch.total_listings_found = total_listings
            batch.total_records = total_listings
        if successful_leads is not None:
            batch.total_leads_stored = successful_leads
            batch.successful_records = successful_leads
        if failed_listings is not None:
            batch.failed_listings = failed_listings
            batch.failed_records = failed_listings
        if skipped_listings is not None:
            batch.skipped_listings = skipped_listings
        if enriched_leads is not None:
            batch.enriched_leads = enriched_leads
        if duplicate_leads is not None:
            batch.duplicate_leads = duplicate_leads

        # Calculations
        duration = (now - batch.started_at).total_seconds()
        processed = batch.listings_processed or successful_leads or 0
        batch.listings_processed = processed
        batch.listings_remaining = 0
        batch.progress_percentage = 100.0
        
        if duration > 1.0 and processed > 0:
            batch.listings_per_second = round(processed / duration, 2)
            batch.avg_processing_time = round(duration / processed, 2)
            batch.avg_listing_time = batch.avg_processing_time
        batch.estimated_time_remaining = 0.0

        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Update SearchContext with final results
        SearchContextEngine.update_search_context(
            session=session,
            batch_id=batch_id,
            search_status="success",
            search_duration=duration,
            listings_found=batch.total_listings_found,
            listings_processed=batch.listings_processed,
            successful_leads=batch.total_leads_stored,
            failed_leads=batch.failed_listings,
            skipped_leads=batch.skipped_listings,
            duplicate_leads=batch.duplicate_leads,
            avg_speed=batch.listings_per_second
        )

        # Publish finished events
        event_bus.EventBus.publish(event_bus.COLLECTION_FINISHED, batch=batch)

        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_COMPLETED",
            "batch_id": batch_id,
            "status": "completed"
        })

        return batch

    @staticmethod
    def fail_session(
        session: Session,
        batch_id: str,
        error_category: str,
        error_message: str,
        severity: str = "Error",
        technical_details: Optional[str] = None,
        stack_trace: Optional[str] = None
    ) -> Optional[CollectionBatch]:
        """
        Sets the session status to failed, logs detailed diagnostics to error tracker, and fires events.
        """
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return None

        now = datetime.utcnow()
        batch.status = "failed"
        batch.completed_at = now
        batch.last_updated_at = now
        session.add(batch)
        session.commit()
        session.refresh(batch)

        # Log details to Error Tracker
        CollectionErrorTracker.log_error(
            session=session,
            batch_id=batch_id,
            website=batch.source_site,
            error_category=error_category,
            error_message=error_message,
            collection_mode=batch.collection_mode,
            collection_stage="Session Manager",
            severity=severity,
            technical_details=technical_details,
            stack_trace=stack_trace
        )

        # Update search context
        duration = (now - batch.started_at).total_seconds()
        SearchContextEngine.update_search_context(
            session=session,
            batch_id=batch_id,
            search_status="failed",
            search_duration=duration,
            listings_found=batch.total_listings_found,
            listings_processed=batch.listings_processed,
            successful_leads=batch.total_leads_stored,
            failed_leads=batch.failed_listings
        )

        # Publish finished events
        event_bus.EventBus.publish(event_bus.COLLECTION_FINISHED, batch=batch)

        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_FAILED",
            "batch_id": batch_id,
            "status": "failed",
            "error_category": error_category,
            "error_message": error_message
        })

        return batch

    @staticmethod
    def update_stage(session: Session, batch_id: str, stage: str) -> Optional[CollectionBatch]:
        """
        Updates the execution stage string.
        """
        return CollectionProgressEngine.update_progress(
            session=session,
            batch_id=batch_id,
            current_stage=stage
        )
