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
    batch = CollectionBatch(
        batch_name=batch_in.batch_name or f"{batch_in.source_site} — {batch_in.search_query}",
        search_query=batch_in.search_query,
        source_site=batch_in.source_site,
        collection_mode=batch_in.collection_mode,
        started_at=datetime.utcnow(),
        status="running",
        search_url=batch_in.search_url,
        total_listings_found=batch_in.total_listings_found or 0
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    # Publish internal event
    event_bus.EventBus.publish(event_bus.COLLECTION_STARTED, batch=batch)

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