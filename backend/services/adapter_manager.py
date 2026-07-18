# backend/services/adapter_manager.py
# ProspectLens — Adapter Management & Validation Service

import urllib.parse
from datetime import datetime
from typing import Optional
from sqlmodel import Session, select
from database.models import WebsiteSource
from services.health_monitor import WebsiteHealthMonitor
from services.error_tracker import CollectionErrorTracker

# concrete adapter imports
from adapters.googlemaps import GoogleMapsAdapter
from adapters.indiamart import IndiaMartAdapter
from adapters.justdial import JustdialAdapter
from adapters.tradeindia import TradeIndiaAdapter

class AdapterManager:
    """
    Manages detection, capability validation, and adapter instantiation for website targets.
    """

    ADAPTER_MAP = {
        "googlemaps": GoogleMapsAdapter(),
        "indiamart": IndiaMartAdapter(),
        "justdial": JustdialAdapter(),
        "tradeindia": TradeIndiaAdapter()
    }

    @staticmethod
    def detect_website(url: str) -> Optional[str]:
        """
        Parses url and matches hostname to registry keys.
        """
        if not url:
            return None
        
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower() or parsed.path.lower() # Fallback for path if protocol missing
        
        for key, adapter in AdapterManager.ADAPTER_MAP.items():
            if adapter.validate_page(url):
                return key
        
        # fallback string netloc searches
        if "google.com/maps" in url or "google.co.in/maps" in url or "maps.google" in url:
            return "googlemaps"
        if "indiamart" in netloc:
            return "indiamart"
        if "justdial" in netloc:
            return "justdial"
        if "tradeindia" in netloc:
            return "tradeindia"
            
        return None

    @staticmethod
    def resolve_adapter(url: str, session: Session, collection_mode: str = "quick") -> dict:
        """
        Detects, validates health, checks capabilities, and loads adapter instances.
        """
        source_key = AdapterManager.detect_website(url)
        
        # 1. Validation: Website is supported
        if not source_key:
            err_msg = f"No adapter matched URL: {url}"
            # Log anonymous check fail to tracker
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website="unknown",
                error_category="Parsing Error",
                error_message=err_msg,
                current_url=url,
                severity="Error"
            )
            return {"status": "error", "message": err_msg}

        # Fetch Registry Source
        source = session.exec(
            select(WebsiteSource).where(WebsiteSource.source_key == source_key)
        ).first()

        # 2. Validation: Website is registered
        if not source:
            err_msg = f"Website key '{source_key}' not found in registry"
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website=source_key,
                error_category="Database Error",
                error_message=err_msg,
                current_url=url
            )
            return {"status": "error", "message": err_msg}

        # 3. Validation: Website is enabled
        if not source.is_active:
            err_msg = f"Website source '{source.display_name}' is currently disabled in registry"
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website=source_key,
                error_category="Authorization Error",
                error_message=err_msg,
                current_url=url
            )
            return {"status": "error", "message": err_msg}

        # 4. Validation: Health status permits collection
        if source.current_health in ["Offline", "Blocked", "Disabled"]:
            err_msg = f"Website source '{source.display_name}' health status is '{source.current_health}' — collection blocked"
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website=source_key,
                error_category="Network Error",
                error_message=err_msg,
                current_url=url
            )
            return {"status": "error", "message": err_msg}

        # 5. Validation: Capability is active/available
        capability = "quick_collect" if collection_mode == "quick" else "deep_collect"
        if not WebsiteHealthMonitor.is_capability_available(session, source_key, capability):
            err_msg = f"Website '{source.display_name}' does not support collection mode '{collection_mode}' (Status: {source.current_health})"
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website=source_key,
                error_category="Authorization Error",
                error_message=err_msg,
                current_url=url
            )
            return {"status": "error", "message": err_msg}

        # 6. Validation: Adapter loaded
        adapter = AdapterManager.ADAPTER_MAP.get(source_key)
        if not adapter:
            err_msg = f"Failed to load adapter instance for class: {source.adapter_key}"
            CollectionErrorTracker.log_error(
                session=session,
                batch_id="anonymous",
                website=source_key,
                error_category="Unknown Error",
                error_message=err_msg,
                current_url=url
            )
            return {"status": "error", "message": err_msg}

        # Assemble metadata profile
        return {
            "status": "success",
            "source_key": source_key,
            "display_name": source.display_name,
            "adapter_class": source.adapter_key,
            "configuration": adapter.get_collection_configuration(),
            "metadata": adapter.get_site_information(),
            "validation": {
                "detected_at": datetime.utcnow().isoformat(),
                "health_score": source.health_score,
                "current_health": source.current_health,
                "is_active": source.is_active
            }
        }

    @staticmethod
    def check_eligibility(
        url: str,
        session: Session,
        collection_mode: str = "quick",
        batch_id: Optional[str] = None
    ) -> dict:
        """
        Validates if a URL is eligible for collection by detecting the website,
        confirming health permits collection, checking active capabilities,
        and classifying page layouts.
        """
        # Resolve the adapter and its configuration/health constraints first
        res = AdapterManager.resolve_adapter(url, session, collection_mode)
        if res.get("status") == "error":
            # If a batch session was active, fail it
            if batch_id:
                from services.session_manager import CollectionSessionManager
                CollectionSessionManager.fail_session(
                    session=session,
                    batch_id=batch_id,
                    error_category="Data Validation Error",
                    error_message=res.get("message")
                )
            return {
                "status": "error",
                "message": res.get("message"),
                "eligibility": False,
                "reason": res.get("message")
            }

        source_key = res["source_key"]
        adapter = AdapterManager.ADAPTER_MAP[source_key]
        
        # Run adapter-specific page type classification
        page_val = adapter.validate_collection_page(url)
        
        if not page_val["is_valid"]:
            err_msg = page_val["reason"]
            CollectionErrorTracker.log_error(
                session=session,
                batch_id=batch_id or "anonymous",
                website=source_key,
                error_category="Data Validation Error",
                error_message=err_msg,
                current_url=url
            )
            if batch_id:
                from services.session_manager import CollectionSessionManager
                CollectionSessionManager.fail_session(
                    session=session,
                    batch_id=batch_id,
                    error_category="Data Validation Error",
                    error_message=err_msg
                )
            return {
                "status": "error",
                "message": err_msg,
                "page_type": page_val["page_type"],
                "source_key": source_key,
                "eligibility": False,
                "reason": err_msg
            }

        return {
            "status": "success",
            "message": "Page is eligible for collection",
            "page_type": page_val["page_type"],
            "source_key": source_key,
            "eligibility": True,
            "adapter_class": adapter.__class__.__name__,
            "metadata": {
                "url": url,
                "timestamp": datetime.utcnow().isoformat(),
                "recognition_method": page_val["recognition_method"],
                "adapter_version": "1.0.0"
            }
        }
