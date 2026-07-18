# backend/services/search_context_engine.py
# ProspectLens — Search Metadata & Collection Context Engine

import json
from datetime import datetime, date
from typing import Optional, List, Dict
from sqlmodel import Session, select, func, desc
from database.models import SearchContext, CollectionBatch

class SearchContextEngine:
    """
    Manages and retrieves search configurations, runtime parameters,
    and performance snapshots for every collection session.
    """

    @staticmethod
    def create_search_context(
        session: Session,
        batch_id: str,
        website: str,
        search_keyword: str,
        search_category: Optional[str] = None,
        search_location: Optional[str] = None,
        original_search_url: Optional[str] = None,
        applied_filters: Optional[dict] = None,
        sorting_method: Optional[str] = None,
        collection_mode: str = "quick",
        max_listings: int = 1000,
        max_pages: int = 100,
        delay_between_reqs: float = 1.0,
        concurrency_limit: int = 5,
        retry_policy: Optional[str] = None,
        timeout: int = 30,
        duplicate_strategy: str = "merge",
        website_version: Optional[str] = None,
        layout_version: Optional[str] = None,
        extension_version: Optional[str] = None,
        started_by: str = "manual"
    ) -> SearchContext:
        """
        Creates a permanent search context record linked to a collection session.
        """
        # Ensure context doesn't already exist for this batch
        existing = session.exec(
            select(SearchContext).where(SearchContext.batch_id == batch_id)
        ).first()
        if existing:
            return existing

        filter_str = json.dumps(applied_filters) if applied_filters else None

        context = SearchContext(
            batch_id=batch_id,
            website=website,
            search_keyword=search_keyword,
            search_category=search_category,
            search_location=search_location,
            original_search_url=original_search_url,
            applied_filters=filter_str,
            sorting_method=sorting_method,
            search_timestamp=datetime.utcnow(),
            search_status="pending",
            
            # Configurations
            collection_mode=collection_mode,
            max_listings=max_listings,
            max_pages=max_pages,
            delay_between_reqs=delay_between_reqs,
            concurrency_limit=concurrency_limit,
            retry_policy=retry_policy,
            timeout=timeout,
            duplicate_strategy=duplicate_strategy,
            
            # Website/App context
            website_version=website_version,
            layout_version=layout_version,
            extension_version=extension_version,
            started_by=started_by,
            
            # Audit timestamps
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        session.add(context)
        session.commit()
        session.refresh(context)
        return context

    @staticmethod
    def update_search_context(
        session: Session,
        batch_id: str,
        search_status: Optional[str] = None,
        search_duration: Optional[float] = None,
        listings_found: Optional[int] = None,
        listings_processed: Optional[int] = None,
        successful_leads: Optional[int] = None,
        failed_leads: Optional[int] = None,
        skipped_leads: Optional[int] = None,
        duplicate_leads: Optional[int] = None,
        approved_leads: Optional[int] = None,
        rejected_leads: Optional[int] = None,
        avg_completeness: Optional[float] = None,
        avg_speed: Optional[float] = None,
        cancellation_reason: Optional[str] = None,
        completion_status: Optional[str] = None
    ) -> Optional[SearchContext]:
        """
        Updates the execution outcome and result snapshot metrics of a search context.
        """
        context = session.exec(
            select(SearchContext).where(SearchContext.batch_id == batch_id)
        ).first()
        if not context:
            return None

        context.updated_at = datetime.utcnow()

        if search_status is not None:
            context.search_status = search_status
            if search_status in ["success", "failed", "cancelled"]:
                context.completed_at = datetime.utcnow()
                context.completion_status = search_status
                if search_status == "cancelled":
                    context.cancelled_at = datetime.utcnow()
                    context.cancellation_reason = cancellation_reason

        if search_duration is not None:
            context.search_duration = search_duration
        if listings_found is not None:
            context.listings_found = listings_found
        if listings_processed is not None:
            context.listings_processed = listings_processed
        if successful_leads is not None:
            context.successful_leads = successful_leads
        if failed_leads is not None:
            context.failed_leads = failed_leads
        if skipped_leads is not None:
            context.skipped_leads = skipped_leads
        if duplicate_leads is not None:
            context.duplicate_leads = duplicate_leads
        if approved_leads is not None:
            context.approved_leads = approved_leads
        if rejected_leads is not None:
            context.rejected_leads = rejected_leads
        if avg_completeness is not None:
            context.avg_completeness = avg_completeness
        if avg_speed is not None:
            context.avg_speed = avg_speed

        session.add(context)
        session.commit()
        session.refresh(context)
        return context

    @staticmethod
    def get_search_statistics(session: Session) -> dict:
        """
        Computes aggregated search metrics for dashboards and historical reporting.
        """
        total = session.exec(select(func.count(SearchContext.search_id))).first() or 0
        
        # Site counts
        site_counts = session.exec(
            select(SearchContext.website, func.count(SearchContext.search_id))
            .group_by(SearchContext.website)
        ).all()
        by_website = {site: count for site, count in site_counts}

        # Average completeness
        avg_comp = session.exec(select(func.avg(SearchContext.avg_completeness))).first() or 0.0
        
        # Success Rate
        successes = session.exec(
            select(func.count(SearchContext.search_id))
            .where(SearchContext.search_status == "success")
        ).first() or 0
        success_rate = (successes / total * 100.0) if total > 0 else 0.0

        # Recent searches
        recent = session.exec(
            select(SearchContext)
            .order_by(desc(SearchContext.search_timestamp))
            .limit(10)
        ).all()

        return {
            "total_searches": total,
            "by_website": by_website,
            "avg_completeness": round(avg_comp, 1),
            "success_rate": round(success_rate, 1),
            "recent_searches": [
                {
                    "search_id": s.search_id,
                    "batch_id": s.batch_id,
                    "website": s.website,
                    "keyword": s.search_keyword,
                    "location": s.search_location,
                    "status": s.search_status,
                    "timestamp": s.search_timestamp,
                    "listings_found": s.listings_found
                } for s in recent
            ]
        }

    @staticmethod
    def query_searches(
        session: Session,
        website: Optional[str] = None,
        keyword: Optional[str] = None,
        location: Optional[str] = None,
        check_date: Optional[date] = None,
        collection_mode: Optional[str] = None,
        status: Optional[str] = None,
        batch_id: Optional[str] = None,
        search_id: Optional[str] = None
    ) -> List[SearchContext]:
        """
        Executes granular filtering of historical search logs.
        """
        statement = select(SearchContext)

        if website:
            statement = statement.where(SearchContext.website == website)
        if keyword:
            statement = statement.where(SearchContext.search_keyword.like(f"%{keyword}%"))
        if location:
            statement = statement.where(SearchContext.search_location.like(f"%{location}%"))
        if collection_mode:
            statement = statement.where(SearchContext.collection_mode == collection_mode)
        if status:
            statement = statement.where(SearchContext.search_status == status)
        if batch_id:
            statement = statement.where(SearchContext.batch_id == batch_id)
        if search_id:
            statement = statement.where(SearchContext.search_id == search_id)
        if check_date:
            start_dt = datetime.combine(check_date, datetime.min.time())
            end_dt = datetime.combine(check_date, datetime.max.time())
            statement = statement.where(SearchContext.search_timestamp >= start_dt).where(SearchContext.search_timestamp <= end_dt)

        statement = statement.order_by(desc(SearchContext.search_timestamp))
        return session.exec(statement).all()
