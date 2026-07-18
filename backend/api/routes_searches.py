# backend/api/routes_searches.py
# ProspectLens — Search Context & Metadata Registry Endpoint

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from pydantic import BaseModel

from database.db import get_session
from database.models import SearchContext
from services.search_context_engine import SearchContextEngine

router = APIRouter(tags=["Searches"])

class SearchContextCreateIn(BaseModel):
    batch_id:             str
    website:              str
    search_keyword:       str
    search_category:      Optional[str] = None
    search_location:      Optional[str] = None
    original_search_url:  Optional[str] = None
    applied_filters:      Optional[dict] = None
    sorting_method:       Optional[str] = None
    collection_mode:      Optional[str] = "quick"
    max_listings:         Optional[int] = 1000
    max_pages:            Optional[int] = 100
    delay_between_reqs:   Optional[float] = 1.0
    concurrency_limit:    Optional[int] = 5
    retry_policy:         Optional[str] = None
    timeout:              Optional[int] = 30
    duplicate_strategy:   Optional[str] = "merge"
    website_version:      Optional[str] = None
    layout_version:       Optional[str] = None
    extension_version:    Optional[str] = None
    started_by:           Optional[str] = "manual"

class SearchContextUpdateIn(BaseModel):
    search_status:        Optional[str] = None
    search_duration:      Optional[float] = None
    listings_found:       Optional[int] = None
    listings_processed:   Optional[int] = None
    successful_leads:     Optional[int] = None
    failed_leads:         Optional[int] = None
    skipped_leads:        Optional[int] = None
    duplicate_leads:      Optional[int] = None
    approved_leads:       Optional[int] = None
    rejected_leads:       Optional[int] = None
    avg_completeness:     Optional[float] = None
    avg_speed:            Optional[float] = None
    cancellation_reason:  Optional[str] = None
    completion_status:    Optional[str] = None

@router.post("/searches")
def create_search_context(search_in: SearchContextCreateIn, session: Session = Depends(get_session)):
    """
    Registers a permanent search context linked to a collection session.
    """
    context = SearchContextEngine.create_search_context(
        session=session,
        batch_id=search_in.batch_id,
        website=search_in.website,
        search_keyword=search_in.search_keyword,
        search_category=search_in.search_category,
        search_location=search_in.search_location,
        original_search_url=search_in.original_search_url,
        applied_filters=search_in.applied_filters,
        sorting_method=search_in.sorting_method,
        collection_mode=search_in.collection_mode,
        max_listings=search_in.max_listings,
        max_pages=search_in.max_pages,
        delay_between_reqs=search_in.delay_between_reqs,
        concurrency_limit=search_in.concurrency_limit,
        retry_policy=search_in.retry_policy,
        timeout=search_in.timeout,
        duplicate_strategy=search_in.duplicate_strategy,
        website_version=search_in.website_version,
        layout_version=search_in.layout_version,
        extension_version=search_in.extension_version,
        started_by=search_in.started_by
    )
    return {
        "status": "ok",
        "message": "Search context registered successfully",
        "search_id": context.search_id
    }

@router.put("/searches/{batch_id}")
def update_search_context(
    batch_id: str,
    update: SearchContextUpdateIn,
    session: Session = Depends(get_session)
):
    """
    Updates search context metrics, durations, status, and outcome fields.
    """
    context = SearchContextEngine.update_search_context(
        session=session,
        batch_id=batch_id,
        search_status=update.search_status,
        search_duration=update.search_duration,
        listings_found=update.listings_found,
        listings_processed=update.listings_processed,
        successful_leads=update.successful_leads,
        failed_leads=update.failed_leads,
        skipped_leads=update.skipped_leads,
        duplicate_leads=update.duplicate_leads,
        approved_leads=update.approved_leads,
        rejected_leads=update.rejected_leads,
        avg_completeness=update.avg_completeness,
        avg_speed=update.avg_speed,
        cancellation_reason=update.cancellation_reason,
        completion_status=update.completion_status
    )
    if not context:
        raise HTTPException(status_code=404, detail=f"Search context for session '{batch_id}' not found")
    return {
        "status": "ok",
        "message": "Search context metadata updated",
        "search": context
    }

@router.get("/searches/statistics")
def get_search_statistics(session: Session = Depends(get_session)):
    """
    Exposes aggregated statistics for searches, success rates, and counts.
    """
    return {
        "status": "ok",
        "statistics": SearchContextEngine.get_search_statistics(session)
    }

@router.get("/searches/history")
def query_search_history(
    website:          Optional[str] = Query(None),
    keyword:          Optional[str] = Query(None),
    location:         Optional[str] = Query(None),
    check_date:       Optional[date] = Query(None),
    collection_mode:  Optional[str] = Query(None),
    status:           Optional[str] = Query(None),
    batch_id:         Optional[str] = Query(None),
    search_id:        Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    """
    Exposes search history with extensive filters for audits and reproduction.
    """
    history = SearchContextEngine.query_searches(
        session=session,
        website=website,
        keyword=keyword,
        location=location,
        check_date=check_date,
        collection_mode=collection_mode,
        status=status,
        batch_id=batch_id,
        search_id=search_id
    )
    return {
        "status": "ok",
        "count": len(history),
        "history": history
    }
