# backend/api/routes_errors.py
# ProspectLens — Collection Error Logging & Diagnostics Endpoint

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from pydantic import BaseModel

from database.db import get_session
from database.models import CollectionError
from services.error_tracker import CollectionErrorTracker

router = APIRouter(tags=["Errors"])

class CollectionErrorIn(BaseModel):
    batch_id:             str
    website:              str
    error_category:       str
    error_message:        str
    collection_mode:      Optional[str] = "quick"
    collection_stage:     Optional[str] = "Unknown"
    severity:             Optional[str] = "Error"
    lead_id:              Optional[str] = None
    technical_details:    Optional[str] = None
    stack_trace:          Optional[str] = None
    current_url:          Optional[str] = None
    listing_url:          Optional[str] = None
    search_url:           Optional[str] = None
    page_number:          Optional[int] = 1
    listing_index:        Optional[int] = 0
    browser_info:         Optional[dict] = None
    extension_version:    Optional[str] = None
    backend_version:      Optional[str] = "1.0.0"
    retry_recommended:    Optional[bool] = False
    recovery_strategy:    Optional[str] = None

@router.post("/errors")
def log_collection_error(error_in: CollectionErrorIn, session: Session = Depends(get_session)):
    """
    Captures and categorizes a collection execution error.
    """
    error = CollectionErrorTracker.log_error(
        session=session,
        batch_id=error_in.batch_id,
        website=error_in.website,
        error_category=error_in.error_category,
        error_message=error_in.error_message,
        collection_mode=error_in.collection_mode,
        collection_stage=error_in.collection_stage,
        severity=error_in.severity,
        lead_id=error_in.lead_id,
        technical_details=error_in.technical_details,
        stack_trace=error_in.stack_trace,
        current_url=error_in.current_url,
        listing_url=error_in.listing_url,
        search_url=error_in.search_url,
        page_number=error_in.page_number,
        listing_index=error_in.listing_index,
        browser_info=error_in.browser_info,
        extension_version=error_in.extension_version,
        backend_version=error_in.backend_version,
        retry_recommended=error_in.retry_recommended,
        recovery_strategy=error_in.recovery_strategy
    )
    return {
        "status": "ok",
        "message": "Error logged successfully",
        "error_id": error.error_id
    }

@router.get("/errors/statistics")
def get_error_statistics(session: Session = Depends(get_session)):
    """
    Exposes rolling calculations of errors across websites, categories, and severities.
    """
    return {
        "status": "ok",
        "statistics": CollectionErrorTracker.get_error_statistics(session)
    }

@router.get("/errors/diagnostics")
def query_developer_diagnostics(
    website:          Optional[str] = Query(None),
    check_date:       Optional[date] = Query(None),
    batch_id:         Optional[str] = Query(None),
    severity:         Optional[str] = Query(None),
    category:         Optional[str] = Query(None),
    collection_mode:  Optional[str] = Query(None),
    lead_id:          Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    """
    Allows developers to filter error records by site, date, session, severity, and category.
    """
    errors = CollectionErrorTracker.query_diagnostics(
        session=session,
        website=website,
        date_check=check_date,
        batch_id=batch_id,
        severity=severity,
        category=category,
        collection_mode=collection_mode,
        lead_id=lead_id
    )
    return {
        "status": "ok",
        "count": len(errors),
        "errors": errors
    }
