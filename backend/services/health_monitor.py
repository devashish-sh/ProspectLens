# backend/services/health_monitor.py
# ProspectLens — Website Health & Capability Monitoring Service

import json
from datetime import datetime
from sqlmodel import Session, select
from database.models import WebsiteSource

class WebsiteHealthMonitor:
    """
    Monitors operational health states, tracks response metrics,
    and checks capability registry profiles for supported website sources.
    """

    @staticmethod
    def get_source_profile(session: Session, source_key: str) -> dict:
        """
        Retrieves the complete health, capabilities registry, and config limits of a website source.
        """
        source = session.exec(
            select(WebsiteSource).where(WebsiteSource.source_key == source_key)
        ).first()
        if not source:
            return {"status": "Unknown", "error": f"Source key '{source_key}' not found"}

        # Deserialize capabilities JSON
        caps = {}
        if source.capabilities:
            try:
                caps = json.loads(source.capabilities)
            except Exception:
                caps = {}

        col_types = []
        if source.collection_types:
            try:
                col_types = json.loads(source.collection_types)
            except Exception:
                col_types = []

        return {
            "source_key": source.source_key,
            "display_name": source.display_name,
            "is_active": source.is_active,
            "health": {
                "current_health": source.current_health,
                "health_score": source.health_score,
                "last_health_check_at": source.last_health_check_at,
                "last_success_at": source.last_success_at,
                "last_failure_at": source.last_failure_at,
                "success_count": source.success_count,
                "failure_count": source.failure_count,
                "consecutive_failures": source.consecutive_failures,
                "avg_response_time": round(source.avg_response_time, 2),
                "last_failure_reason": source.last_failure_reason
            },
            "capabilities": caps,
            "collection_types": col_types,
            "configuration": {
                "max_rpm": source.max_rpm,
                "recommended_delay": source.recommended_delay,
                "retry_count": source.retry_count,
                "timeout": source.timeout,
                "concurrent_limit": source.concurrent_limit
            }
        }

    @staticmethod
    def record_check(
        session: Session,
        source_key: str,
        success: bool,
        response_time: float = None,
        failure_reason: str = None
    ) -> dict:
        """
        Updates response speed averages, tracks error counts, and refines health scores.
        """
        source = session.exec(
            select(WebsiteSource).where(WebsiteSource.source_key == source_key)
        ).first()
        if not source:
            return {}

        now = datetime.utcnow()
        source.last_health_check_at = now

        if success:
            source.success_count += 1
            source.consecutive_failures = 0
            source.last_success_at = now
            # Slowly restore health score
            source.health_score = min(100, source.health_score + 5)
            
            # Recalculate rolling average response time
            if response_time is not None:
                if source.avg_response_time > 0.0:
                    source.avg_response_time = (source.avg_response_time * 0.8) + (response_time * 0.2)
                else:
                    source.avg_response_time = response_time
        else:
            source.failure_count += 1
            source.consecutive_failures += 1
            source.last_failure_at = now
            source.last_failure_reason = failure_reason or "Unknown Error"
            # Deduct health score
            source.health_score = max(0, source.health_score - 10)

        # Configurable health state updates based on failures
        if source.consecutive_failures >= 5:
            source.current_health = "Offline"
        elif source.consecutive_failures >= 3:
            reason = (source.last_failure_reason or "").lower()
            if "captcha" in reason:
                source.current_health = "Captcha Detected"
            elif "rate" in reason or "limit" in reason:
                source.current_health = "Rate Limited"
            else:
                source.current_health = "Limited"
        elif source.consecutive_failures > 0:
            source.current_health = "Limited"
        else:
            source.current_health = "Healthy"

        session.add(source)
        session.commit()
        session.refresh(source)

        return WebsiteHealthMonitor.get_source_profile(session, source_key)

    @staticmethod
    def is_capability_available(session: Session, source_key: str, capability: str) -> bool:
        """
        Query if a specific capability is active and available for use on a directory.
        Returns True if capability status is 'supported' or 'experimental'.
        """
        source = session.exec(
            select(WebsiteSource).where(WebsiteSource.source_key == source_key)
        ).first()
        if not source or not source.is_active:
            return False

        if source.current_health in ["Offline", "Disabled", "Blocked"]:
            return False

        if not source.capabilities:
            return False

        try:
            caps = json.loads(source.capabilities)
            status = caps.get(capability, "unavailable")
            return status in ["supported", "experimental"]
        except Exception:
            return False
