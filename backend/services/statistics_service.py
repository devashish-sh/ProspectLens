# backend/services/statistics_service.py
# ProspectLens — Centralized Statistics Service

from datetime import datetime, time
from sqlmodel import Session, select, func
from database.models import Lead, WebsiteSource

class StatisticsService:
    """
    Centralized stats calculator.
    Calculates lead counts, sources, and status breakdowns dynamically from SQLite.
    """
    
    @staticmethod
    def get_summary_stats(session: Session) -> dict:
        """
        Query and compute all dashboard statistics dynamically.
        """
        # 1. Total Leads
        total_leads = session.exec(select(func.count(Lead.lead_id))).first() or 0

        # 2. Today's Collection (leads gathered since midnight UTC)
        today_start = datetime.combine(datetime.utcnow().date(), time.min)
        todays_collection = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.collected_at >= today_start)
        ).first() or 0

        # 3. Active vs. Inactive website sources
        all_sources = session.exec(select(WebsiteSource)).all()
        active_source_keys = session.exec(
            select(Lead.source_site).distinct()
        ).all()

        active_sources = []
        inactive_sources = []

        for src in all_sources:
            src_info = {
                "source_key": src.source_key,
                "display_name": src.display_name,
                "base_url": src.base_url
            }
            if src.source_key in active_source_keys:
                active_sources.append(src_info)
            else:
                inactive_sources.append(src_info)

        # 4. Leads Waiting Approval (is_approved == False)
        waiting_approval = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.is_approved == False)
        ).first() or 0

        # 5. Approved Leads (is_approved == True)
        approved_leads = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.is_approved == True)
        ).first() or 0

        # 6. Status counters (Workflow-based)
        rejected_leads = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.status == "Rejected")
        ).first() or 0

        incomplete_leads = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.status == "Incomplete")
        ).first() or 0

        enriched_leads = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.status == "Enriched")
        ).first() or 0

        return {
            "total_leads": total_leads,
            "todays_collection": todays_collection,
            "active_sources": {
                "count": len(active_sources),
                "sources": active_sources
            },
            "inactive_sources": {
                "count": len(inactive_sources),
                "sources": inactive_sources
            },
            "leads_waiting_approval": waiting_approval,
            "approved_leads": approved_leads,
            "rejected_leads": rejected_leads,
            "incomplete_leads": incomplete_leads,
            "enriched_leads": enriched_leads
        }
