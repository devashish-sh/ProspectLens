# backend/services/error_tracker.py
# ProspectLens — Collection Error Tracking & Recovery Engine

import json
from datetime import datetime, date
from typing import Optional, List, Dict
from sqlmodel import Session, select, func, desc
from database.models import CollectionError
from services.sync_service import SyncBroadcaster

class CollectionErrorTracker:
    """
    Captures, classifies, and stores all scraping/collection errors.
    Exposes statistics and diagnostic queries for debugging and recovery.
    """

    @staticmethod
    def log_error(
        session: Session,
        batch_id: str,
        website: str,
        error_category: str,
        error_message: str,
        collection_mode: str = "quick",
        collection_stage: str = "Unknown",
        severity: str = "Error", # Info, Warning, Error, Critical, Fatal
        lead_id: Optional[str] = None,
        technical_details: Optional[str] = None,
        stack_trace: Optional[str] = None,
        current_url: Optional[str] = None,
        listing_url: Optional[str] = None,
        search_url: Optional[str] = None,
        page_number: int = 1,
        listing_index: int = 0,
        browser_info: Optional[dict] = None,
        extension_version: Optional[str] = None,
        backend_version: Optional[str] = "1.0.0",
        retry_recommended: bool = False,
        recovery_strategy: Optional[str] = None
    ) -> CollectionError:
        """
        Records a collection error with full diagnostics and recovery parameters.
        """
        browser_str = json.dumps(browser_info) if browser_info else None
        
        error_record = CollectionError(
            batch_id=batch_id,
            lead_id=lead_id,
            website=website,
            collection_mode=collection_mode,
            collection_stage=collection_stage,
            timestamp=datetime.utcnow(),
            severity=severity,
            error_category=error_category,
            error_message=error_message,
            technical_details=technical_details,
            stack_trace=stack_trace,
            current_url=current_url,
            listing_url=listing_url,
            search_url=search_url,
            page_number=page_number,
            listing_index=listing_index,
            browser_info=browser_str,
            extension_version=extension_version,
            backend_version=backend_version,
            
            # Recovery info
            retry_recommended=retry_recommended,
            recovery_status="pending",
            max_retry_count=3,
            current_retry_count=0,
            recovery_strategy=recovery_strategy
        )
        
        session.add(error_record)
        session.commit()
        session.refresh(error_record)
        
        print(f"[ErrorTracker] Logged '{error_category}' ({severity}) for session {batch_id}: {error_message}")
        
        # Broadcast error state update to frontend clients
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "COLLECTION_ERROR_LOGGED",
            "error_id": error_record.error_id,
            "batch_id": error_record.batch_id,
            "website": error_record.website,
            "severity": error_record.severity,
            "error_category": error_record.error_category,
            "error_message": error_record.error_message
        })
        
        return error_record

    @staticmethod
    def get_error_statistics(session: Session) -> dict:
        """
        Returns dynamic calculations of error distributions by severity, site, session, and category.
        """
        total_errors = session.exec(select(func.count(CollectionError.error_id))).first() or 0
        
        # Errors by Website
        site_counts = session.exec(
            select(CollectionError.website, func.count(CollectionError.error_id))
            .group_by(CollectionError.website)
        ).all()
        by_website = {site: count for site, count in site_counts}

        # Errors by Session
        session_counts = session.exec(
            select(CollectionError.batch_id, func.count(CollectionError.error_id))
            .group_by(CollectionError.batch_id)
        ).all()
        by_session = {sid: count for sid, count in session_counts}

        # Errors by Category
        category_counts = session.exec(
            select(CollectionError.error_category, func.count(CollectionError.error_id))
            .group_by(CollectionError.error_category)
        ).all()
        by_category = {cat: count for cat, count in category_counts}

        # Errors by Severity
        severity_counts = session.exec(
            select(CollectionError.severity, func.count(CollectionError.error_id))
            .group_by(CollectionError.severity)
        ).all()
        by_severity = {sev: count for sev, count in severity_counts}

        # Most Common Errors (Top 5)
        common_errors = session.exec(
            select(CollectionError.error_message, func.count(CollectionError.error_id))
            .group_by(CollectionError.error_message)
            .order_by(desc(func.count(CollectionError.error_id)))
            .limit(5)
        ).all()
        most_common = [{"message": msg, "count": count} for msg, count in common_errors]

        # Recent Errors (Top 10)
        recent_errs = session.exec(
            select(CollectionError)
            .order_by(desc(CollectionError.timestamp))
            .limit(10)
        ).all()
        
        recent_list = []
        for e in recent_errs:
            recent_list.append({
                "error_id": e.error_id,
                "batch_id": e.batch_id,
                "website": e.website,
                "error_category": e.error_category,
                "error_message": e.error_message,
                "severity": e.severity,
                "timestamp": e.timestamp
            })

        return {
            "total_errors": total_errors,
            "by_website": by_website,
            "by_session": by_session,
            "by_category": by_category,
            "by_severity": by_severity,
            "most_common": most_common,
            "recent_errors": recent_list
        }

    @staticmethod
    def query_diagnostics(
        session: Session,
        website: Optional[str] = None,
        date_check: Optional[date] = None,
        batch_id: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        collection_mode: Optional[str] = None,
        lead_id: Optional[str] = None
    ) -> List[CollectionError]:
        """
        Provides comprehensive query filtering options for developers.
        """
        statement = select(CollectionError)
        
        if website:
            statement = statement.where(CollectionError.website == website)
        if batch_id:
            statement = statement.where(CollectionError.batch_id == batch_id)
        if severity:
            statement = statement.where(CollectionError.severity == severity)
        if category:
            statement = statement.where(CollectionError.error_category == category)
        if collection_mode:
            statement = statement.where(CollectionError.collection_mode == collection_mode)
        if lead_id:
            statement = statement.where(CollectionError.lead_id == lead_id)
        if date_check:
            start_dt = datetime.combine(date_check, datetime.min.time())
            end_dt = datetime.combine(date_check, datetime.max.time())
            statement = statement.where(CollectionError.timestamp >= start_dt).where(CollectionError.timestamp <= end_dt)

        statement = statement.order_by(desc(CollectionError.timestamp))
        return session.exec(statement).all()
