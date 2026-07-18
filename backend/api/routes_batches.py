# backend/api/routes_batches.py
# ProspectLens — Collection Batch Endpoints
#
# A "batch" is one collection session.
# Every time you run a search on IndiaMART/Google Maps/Justdial,
# a batch is created first, then all leads are saved under that batch_id.
#
# Endpoints:
#   POST   /api/batches          — Create a new batch before collection starts
#   GET    /api/batches          — List all past batches
#   GET    /api/batches/{id}     — Get one batch + its lead count
#   PUT    /api/batches/{id}     — Update batch counts after collection finishes

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from database.db import get_session
from database.models import CollectionBatch, Lead
from services import event_bus
from services.progress_engine import CollectionProgressEngine
from services.session_manager import CollectionSessionManager

router = APIRouter(tags=["Batches"])


# ==============================================================================
# REQUEST SCHEMAS
# ==============================================================================

class BatchIn(BaseModel):
    batch_name:      str = ""
    search_query:    str
    source_site:     str        # indiamart / googlemaps / justdial
    collection_mode: str = "quick"
    search_url:      Optional[str] = None
    total_listings_found: Optional[int] = 0

class BatchUpdate(BaseModel):
    total_records:      Optional[int] = None
    successful_records: Optional[int] = None
    failed_records:     Optional[int] = None
    status:             Optional[str] = None # running / completed / failed


# ==============================================================================
# POST /api/batches
# Called by the Chrome extension BEFORE collection starts.
# Returns a batch_id that gets attached to every lead in this session.
# ==============================================================================

@router.post("/batches")
def create_batch(batch_in: BatchIn, session: Session = Depends(get_session)):
    batch = CollectionSessionManager.create_session(
        session=session,
        source_site=batch_in.source_site,
        search_query=batch_in.search_query,
        collection_mode=batch_in.collection_mode,
        search_url=batch_in.search_url,
        batch_name=batch_in.batch_name
    )
    return {
        "status": "ok",
        "message": "Batch created",
        "batch_id": batch.batch_id,
        "batch": batch
    }


# ==============================================================================
# GET /api/batches
# List all collection batches, most recent first.
# ==============================================================================

@router.get("/batches")
def get_batches(active_only: bool = False, session: Session = Depends(get_session)):
    if active_only:
        # Get batch_ids that have retrieved leads
        active_batch_ids = session.exec(
            select(Lead.batch_id).where(Lead.lead_status == "retrieved").distinct()
        ).all()
        
        batches = session.exec(
            select(CollectionBatch)
            .where(CollectionBatch.batch_id.in_(active_batch_ids))
            .order_by(CollectionBatch.created_at.desc())
        ).all()
    else:
        batches = session.exec(
            select(CollectionBatch).order_by(CollectionBatch.created_at.desc())
        ).all()

    # Map batches to include live retrieved count
    batch_list = []
    for b in batches:
        b_dict = b.model_dump()
        retrieved_count = session.exec(
            select(Lead).where((Lead.batch_id == b.batch_id) & (Lead.lead_status == "retrieved"))
        ).all()
        b_dict["retrieved_count"] = len(retrieved_count)
        batch_list.append(b_dict)

    return {
        "status": "ok",
        "count": len(batch_list),
        "batches": batch_list
    }


# ==============================================================================
# GET /api/batches/{batch_id}
# Get a single batch with live lead count from the leads table.
# ==============================================================================

@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, session: Session = Depends(get_session)):
    batch = session.get(CollectionBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    # Count actual leads saved under this batch
    leads = session.exec(
        select(Lead).where(Lead.batch_id == batch_id)
    ).all()

    retrieved_count = len([l for l in leads if l.lead_status == "retrieved"])

    return {
        "status": "ok",
        "batch": batch,
        "actual_lead_count": len(leads),
        "retrieved_count": retrieved_count
    }


# ==============================================================================
# PUT /api/batches/{batch_id}
# Update batch counts after collection finishes.
# Called by the extension when scraping is complete.
# ==============================================================================

@router.put("/batches/{batch_id}")
def update_batch(
    batch_id: str,
    update: BatchUpdate,
    session: Session = Depends(get_session)
):
    batch = session.get(CollectionBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    if update.total_records is not None:
        batch.total_records = update.total_records
        batch.total_listings_found = update.total_records
    if update.successful_records is not None:
        batch.successful_records = update.successful_records
        batch.total_leads_stored = update.successful_records
    if update.failed_records is not None:
        batch.failed_records = update.failed_records
    if update.status is not None:
        batch.status = update.status
        if update.status in ["completed", "failed"]:
            batch.completed_at = datetime.utcnow()

    session.add(batch)
    session.commit()
    session.refresh(batch)

    # Publish internal event
    if batch.status in ["completed", "failed"]:
        event_bus.EventBus.publish(event_bus.COLLECTION_FINISHED, batch=batch)

    return {
        "status": "ok",
        "message": "Batch updated",
        "batch": batch
    }


class ProgressUpdateIn(BaseModel):
    listings_processed:   Optional[int] = None
    failed_listings:      Optional[int] = None
    skipped_listings:     Optional[int] = None
    enriched_leads:       Optional[int] = None
    duplicate_leads:      Optional[int] = None
    current_listing:      Optional[int] = None
    current_company_name: Optional[str] = None
    current_page:         Optional[int] = None
    current_stage:        Optional[str] = None
    status:               Optional[str] = None


@router.get("/batches/{batch_id}/progress")
def get_batch_progress(batch_id: str, session: Session = Depends(get_session)):
    """
    Exposes real-time collection metrics and current execution statistics for a session.
    """
    progress = CollectionProgressEngine.get_session_progress(session, batch_id)
    if not progress:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} progress not found")
    return {
        "status": "ok",
        "progress": progress
    }


@router.post("/batches/{batch_id}/progress")
def update_batch_progress(
    batch_id: str,
    update: ProgressUpdateIn,
    session: Session = Depends(get_session)
):
    """
    Pushes real-time scraper progress updates and triggers speed/ETA recalculations.
    """
    batch = CollectionProgressEngine.update_progress(
        session=session,
        batch_id=batch_id,
        listings_processed=update.listings_processed,
        failed_listings=update.failed_listings,
        skipped_listings=update.skipped_listings,
        enriched_leads=update.enriched_leads,
        duplicate_leads=update.duplicate_leads,
        current_listing=update.current_listing,
        current_company_name=update.current_company_name,
        current_page=update.current_page,
        current_stage=update.current_stage,
        status=update.status
    )
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {
        "status": "ok",
        "message": "Progress metrics updated successfully",
        "batch": batch
    }


class SessionCompleteIn(BaseModel):
    total_listings:   Optional[int] = None
    successful_leads: Optional[int] = None
    failed_listings:  Optional[int] = None
    skipped_listings: Optional[int] = None
    enriched_leads:   Optional[int] = None
    duplicate_leads:  Optional[int] = None


class SessionFailIn(BaseModel):
    error_category:    str
    error_message:     str
    severity:          Optional[str] = "Error"
    technical_details: Optional[str] = None
    stack_trace:       Optional[str] = None


class SessionStageIn(BaseModel):
    stage: str


@router.post("/batches/{batch_id}/start")
def start_batch(batch_id: str, session: Session = Depends(get_session)):
    """
    Transitions the collection session state to Running.
    """
    batch = CollectionSessionManager.start_session(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session started successfully", "batch": batch}


@router.post("/batches/{batch_id}/pause")
def pause_batch(batch_id: str, session: Session = Depends(get_session)):
    """
    Transitions the collection session status to Paused.
    """
    batch = CollectionSessionManager.pause_session(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session paused successfully", "batch": batch}


@router.post("/batches/{batch_id}/resume")
def resume_batch(batch_id: str, session: Session = Depends(get_session)):
    """
    Transitions the collection session status to Resumed and Running.
    """
    batch = CollectionSessionManager.resume_session(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session resumed successfully", "batch": batch}


@router.post("/batches/{batch_id}/cancel")
def cancel_batch(
    batch_id: str,
    reason: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """
    Transitions the collection session status to Cancelled.
    """
    batch = CollectionSessionManager.cancel_session(session, batch_id, reason=reason)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session cancelled successfully", "batch": batch}


@router.post("/batches/{batch_id}/complete")
def complete_batch(
    batch_id: str,
    payload: SessionCompleteIn,
    session: Session = Depends(get_session)
):
    """
    Transitions the session state to Completed, logs final metrics, and fires events.
    """
    batch = CollectionSessionManager.complete_session(
        session=session,
        batch_id=batch_id,
        total_listings=payload.total_listings,
        successful_leads=payload.successful_leads,
        failed_listings=payload.failed_listings,
        skipped_listings=payload.skipped_listings,
        enriched_leads=payload.enriched_leads,
        duplicate_leads=payload.duplicate_leads
    )
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session completed successfully", "batch": batch}


@router.post("/batches/{batch_id}/fail")
def fail_batch(
    batch_id: str,
    payload: SessionFailIn,
    session: Session = Depends(get_session)
):
    """
    Transitions the session state to Failed and logs the session execution error.
    """
    batch = CollectionSessionManager.fail_session(
        session=session,
        batch_id=batch_id,
        error_category=payload.error_category,
        error_message=payload.error_message,
        severity=payload.severity,
        technical_details=payload.technical_details,
        stack_trace=payload.stack_trace
    )
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Session marked as failed", "batch": batch}


@router.post("/batches/{batch_id}/stage")
def update_batch_stage(
    batch_id: str,
    payload: SessionStageIn,
    session: Session = Depends(get_session)
):
    """
    Updates the session stage context during execution.
    """
    batch = CollectionSessionManager.update_stage(session, batch_id, payload.stage)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Session {batch_id} not found")
    return {"status": "ok", "message": "Stage updated successfully", "batch": batch}