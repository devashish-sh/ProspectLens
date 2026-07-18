# backend/services/discovery_engine.py
# ProspectLens — Listing Discovery Engine Service

from datetime import datetime
from typing import List, Dict
from sqlmodel import Session, select, func
from database.models import DiscoveredListing, CollectionBatch
from services.adapter_manager import AdapterManager
from services.sync_service import SyncBroadcaster

class ListingDiscoveryEngine:
    """
    Handles discovery, filtering, and state updates of tracking listings.
    Coordinates visibility metrics and updates session batch aggregates.
    """

    @staticmethod
    def register_discovery(
        session: Session,
        batch_id: str,
        website: str,
        incoming_listings: List[dict]
    ) -> dict:
        """
        Saves discovered listings, handles deduplication, filters out ads, and updates counters.
        """
        start_time = datetime.utcnow()
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return {"status": "error", "message": f"Session {batch_id} not found"}

        # Fetch adapter logic
        adapter = AdapterManager.ADAPTER_MAP.get(website)
        if not adapter:
            return {"status": "error", "message": f"Adapter for site '{website}' not loaded"}

        # Apply filtering rules: ignore ads, sponsored, skeletons
        filtered = adapter.discover_listings(incoming_listings)
        ignored_count = len(incoming_listings) - len(filtered)

        # Process each listing node
        for idx, item in enumerate(filtered):
            dom_ref = item.get("dom_reference")
            if not dom_ref:
                continue

            # Check if this node is already tracked in this session
            existing = session.exec(
                select(DiscoveredListing)
                .where(DiscoveredListing.batch_id == batch_id)
                .where(DiscoveredListing.dom_reference == dom_ref)
            ).first()

            if existing:
                existing.visible_state = item.get("visible_state", True)
                existing.listing_position = item.get("listing_position", idx)
                existing.page_position = item.get("page_position", 1)
                existing.collection_status = item.get("collection_status", "discovered")
                session.add(existing)
            else:
                new_listing = DiscoveredListing(
                    batch_id=batch_id,
                    listing_id=item.get("listing_id"),
                    website=website,
                    dom_reference=dom_ref,
                    listing_position=item.get("listing_position", idx),
                    page_position=item.get("page_position", 1),
                    visible_state=item.get("visible_state", True),
                    discovery_timestamp=datetime.utcnow(),
                    discovery_source="Quick Collect",
                    collection_status="discovered"
                )
                session.add(new_listing)

        session.commit()

        # Update stats on CollectionBatch
        discovered_total = session.exec(
            select(func.count(DiscoveredListing.discovered_id))
            .where(DiscoveredListing.batch_id == batch_id)
        ).first() or 0

        visible_total = session.exec(
            select(func.count(DiscoveredListing.discovered_id))
            .where(DiscoveredListing.batch_id == batch_id)
            .where(DiscoveredListing.visible_state == True)
        ).first() or 0

        # Update session batch counts
        batch.total_listings_found = discovered_total
        batch.total_records = discovered_total
        
        # Increment DOM Refresh Count (internal simulation or field increment)
        # We can store the current refresh count in memory/state or log it.
        # Let's save the stats update
        session.add(batch)
        session.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()

        # Broadcast progress updates
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "LISTINGS_DISCOVERED",
            "batch_id": batch_id,
            "total_discovered": discovered_total,
            "total_visible": visible_total,
            "ignored": ignored_count
        })

        return {
            "status": "success",
            "listings_discovered": discovered_total,
            "visible_listings": visible_total,
            "ignored_listings": ignored_count,
            "discovery_duration": round(duration, 3),
            "dom_refresh_count": 1
        }

    @staticmethod
    def get_session_discovery(session: Session, batch_id: str) -> dict:
        """
        Gathers list details and stats metrics for active discovery runs.
        """
        listings = session.exec(
            select(DiscoveredListing).where(DiscoveredListing.batch_id == batch_id)
        ).all()

        total = len(listings)
        visible = len([l for l in listings if l.visible_state])
        processed = len([l for l in listings if l.collection_status == "processed"])

        return {
            "batch_id": batch_id,
            "total_listings_discovered": total,
            "visible_listings": visible,
            "processed_listings": processed,
            "listings": [
                {
                    "temp_internal_id": l.temp_internal_id,
                    "dom_reference": l.dom_reference,
                    "listing_position": l.listing_position,
                    "page_position": l.page_position,
                    "visible_state": l.visible_state,
                    "collection_status": l.collection_status
                } for l in listings
            ]
        }
