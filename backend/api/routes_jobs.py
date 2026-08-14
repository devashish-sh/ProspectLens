# backend/api/routes_jobs.py
# ProspectLens — Scraper & Extractor Jobs Manager
#
# FastAPI router to manage long-running background collection tasks,
# supporting start, pause, resume, cancel, and live progress reporting.

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database.db import get_session
from database.models import Job, CollectionBatch
from services.deep_collect_service import (
    start_background_job,
    pause_background_job,
    cancel_background_job,
    ACTIVE_TASKS
)

router = APIRouter(tags=["Jobs"])


# ==============================================================================
# SCHEMAS
# ==============================================================================

class JobIn(BaseModel):
    batch_id: str
    job_type: str = "deep_collect"  # deep_collect / website_extract


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/jobs")
def create_job(job_in: JobIn, session: Session = Depends(get_session)):
    """Launches or creates a background scraping/extraction job."""
    # Verify batch exists
    batch = session.get(CollectionBatch, job_in.batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {job_in.batch_id} not found")

    # Check for active running job for this batch
    existing = session.exec(
        select(Job).where(
            (Job.batch_id == job_in.batch_id) &
            (Job.job_type == job_in.job_type) &
            (Job.status == "running")
        )
    ).first()
    
    if existing:
        # Check if actually in ACTIVE_TASKS registry
        if existing.job_id in ACTIVE_TASKS:
            return {
                "status": "already_running",
                "message": "Job is already running in the background",
                "job_id": existing.job_id,
                "job": existing
            }
        else:
            # Sync db state if process died unexpectedly
            existing.status = "failed"
            session.add(existing)
            session.commit()

    # Create new job record
    job = Job(
        batch_id=job_in.batch_id,
        job_type=job_in.job_type,
        status="queued",
        progress_percentage=0.0
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Start background asyncio worker
    start_background_job(job.job_id)

    return {
        "status": "started",
        "message": f"Job {job.job_id} successfully queued",
        "job_id": job.job_id,
        "job": job
    }


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session)):
    """Lists all background jobs, sorted by creation date."""
    jobs = session.exec(
        select(Job).order_by(Job.created_at.desc())
    ).all()
    return {
        "status": "ok",
        "count": len(jobs),
        "jobs": [
            {
                "job_id": j.job_id,
                "batch_id": j.batch_id,
                "job_type": j.job_type,
                "status": j.status,
                "progress_percentage": j.progress_percentage,
                "records_done": j.records_done,
                "records_total": j.records_total,
                "active_thread": j.job_id in ACTIVE_TASKS,
                "created_at": j.created_at,
                "updated_at": j.updated_at
            }
            for j in jobs
        ]
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    """Retrieves progress metrics, status, and active task state."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "status": "ok",
        "job_id": job.job_id,
        "job_status": job.status,
        "progress_percentage": job.progress_percentage,
        "records_done": job.records_done,
        "records_total": job.records_total,
        "active_thread": job_id in ACTIVE_TASKS,
        "job": job
    }


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str, session: Session = Depends(get_session)):
    """Instructs a running job to suspend work and serialize queue state."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != "running":
        raise HTTPException(status_code=400, detail=f"Only running jobs can be paused. Current status: {job.status}")

    # Set pause flag in registry
    paused = pause_background_job(job_id, session)
    
    if paused:
        job.status = "paused"
        job.updated_at = datetime.utcnow()
        session.add(job)
        session.commit()
        return {"status": "paused", "message": f"Job {job_id} has been paused"}
        
    return {"status": "error", "message": "Failed to pause background task"}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, session: Session = Depends(get_session)):
    """Resumes a paused job by loading its serialized queue state."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != "paused":
        raise HTTPException(status_code=400, detail=f"Only paused jobs can be resumed. Current status: {job.status}")

    job.status = "running"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()

    # Re-launch background thread worker task
    start_background_job(job_id)

    return {"status": "resumed", "message": f"Job {job_id} is running again"}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, session: Session = Depends(get_session)):
    """Stops the job immediately and flags it as failed/cancelled."""
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    cancelled = cancel_background_job(job_id, session)
    
    job.status = "failed"
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()

    return {"status": "cancelled", "message": f"Job {job_id} has been cancelled"}


# ==============================================================================
# COLLECTION JOBS ENDPOINTS (Sprint 4.5)
# ==============================================================================

from database.models import CollectionJob

class CollectionJobCreate(BaseModel):
    job_id: str
    source: str
    mode: str = "quick"
    search_keyword: Optional[str] = None
    search_query: Optional[str] = None
    search_location: Optional[str] = None
    search_url: Optional[str] = None
    metadata_json: Optional[dict] = None

class CollectionJobProgressUpdate(BaseModel):
    status: Optional[str] = None
    saved: Optional[int] = None
    duplicates: Optional[int] = None
    errors: Optional[int] = None
    skipped: Optional[int] = None
    total_seen: Optional[int] = None
    current_listing: Optional[str] = None
    progress_percentage: Optional[float] = None
    metadata_json: Optional[dict] = None

class CollectionJobStatusUpdate(BaseModel):
    status: str # completed / failed / cancelled
    metadata_json: Optional[dict] = None

@router.post("/collection-jobs")
def register_collection_job(job_in: CollectionJobCreate, session: Session = Depends(get_session)):
    """Registers a new collection job in the database."""
    # Check if job already exists
    existing = session.get(CollectionJob, job_in.job_id)
    if existing:
        return {"status": "exists", "job_id": existing.job_id, "job": existing}

    import json
    meta_str = json.dumps(job_in.metadata_json) if job_in.metadata_json else None
    
    job = CollectionJob(
        job_id=job_in.job_id,
        status="queued",
        source=job_in.source,
        mode=job_in.mode,
        search_keyword=job_in.search_keyword,
        search_query=job_in.search_query,
        search_location=job_in.search_location,
        search_url=job_in.search_url,
        start_time=datetime.utcnow(),
        metadata_json=meta_str
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return {"status": "created", "job_id": job.job_id, "job": job}

@router.post("/collection-jobs/{job_id}/progress")
def update_collection_job_progress(job_id: str, progress: CollectionJobProgressUpdate, session: Session = Depends(get_session)):
    """Updates live progress statistics of a collection job."""
    job = session.get(CollectionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Collection job {job_id} not found")

    if progress.status:
        job.status = progress.status
    if progress.saved is not None:
        job.saved = progress.saved
    if progress.duplicates is not None:
        job.duplicates = progress.duplicates
    if progress.errors is not None:
        job.errors = progress.errors
    if progress.skipped is not None:
        job.skipped = progress.skipped
    if progress.total_seen is not None:
        job.total_seen = progress.total_seen
    if progress.current_listing is not None:
        job.current_listing = progress.current_listing
    if progress.progress_percentage is not None:
        job.progress_percentage = progress.progress_percentage
    if progress.metadata_json is not None:
        import json
        job.metadata_json = json.dumps(progress.metadata_json)

    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return {"status": "ok", "job": job}

@router.post("/collection-jobs/{job_id}/status")
def update_collection_job_status(job_id: str, status_up: CollectionJobStatusUpdate, session: Session = Depends(get_session)):
    """Sets the final lifecycle state (completed, failed, cancelled) of a job."""
    job = session.get(CollectionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Collection job {job_id} not found")

    job.status = status_up.status
    job.end_time = datetime.utcnow()
    
    if job.start_time:
        delta = job.end_time - job.start_time
        job.duration = delta.total_seconds()
        
    if status_up.metadata_json:
        import json
        job.metadata_json = json.dumps(status_up.metadata_json)
        
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return {"status": "ok", "job": job}

@router.get("/collection-jobs/active")
def get_active_collection_job(session: Session = Depends(get_session)):
    """Gets the currently active/running collection job."""
    job = session.exec(
        select(CollectionJob).where(
            (CollectionJob.status == "running") | (CollectionJob.status == "paused") | (CollectionJob.status == "queued") | (CollectionJob.status == "starting")
        ).order_by(CollectionJob.updated_at.desc())
    ).first()
    
    if not job:
        return {"status": "no_active_job", "job": None}
    return {"status": "ok", "job": job}

@router.get("/collection-jobs/recent")
def get_recent_collection_jobs(session: Session = Depends(get_session)):
    """Gets recent collection jobs (history)."""
    jobs = session.exec(
        select(CollectionJob).order_by(CollectionJob.created_at.desc()).limit(15)
    ).all()
    return {"status": "ok", "jobs": jobs}


# ==============================================================================
# DEEP COLLECT QUEUE ENDPOINTS (Sprint 5)
# ==============================================================================

from database.models import DeepQueueItem, Lead, Contact
from typing import List

class QueueItemCreate(BaseModel):
    lead_id: str
    business_name: str
    listing_url: Optional[str] = ""

class QueueCreatePayload(BaseModel):
    items: List[QueueItemCreate]

@router.post("/collection-jobs/{job_id}/queue")
def create_collection_job_queue(job_id: str, payload: QueueCreatePayload, session: Session = Depends(get_session)):
    """Deletes existing queue and inserts new enrichment queue items for a job."""
    items = session.exec(
        select(DeepQueueItem).where(DeepQueueItem.job_id == job_id)
    ).all()
    for item in items:
        session.delete(item)
    session.commit()
    
    for idx, item_in in enumerate(payload.items):
        q_item = DeepQueueItem(
            lead_id=item_in.lead_id,
            job_id=job_id,
            business_name=item_in.business_name,
            listing_url=item_in.listing_url,
            queue_position=idx + 1,
            status="pending"
        )
        session.add(q_item)
    session.commit()
    return {"status": "ok", "queued_count": len(payload.items)}

@router.get("/collection-jobs/{job_id}/queue")
def get_collection_job_queue(job_id: str, session: Session = Depends(get_session)):
    """Retrieves all queue items for a job, sorted by position."""
    items = session.exec(
        select(DeepQueueItem).where(DeepQueueItem.job_id == job_id).order_by(DeepQueueItem.queue_position.asc())
    ).all()
    return {"status": "ok", "items": items}

class QueueStatusUpdate(BaseModel):
    status: str
    retry_count: Optional[int] = None

@router.post("/collection-jobs/{job_id}/queue/{lead_id}/status")
def update_queue_item_status(job_id: str, lead_id: str, status_up: QueueStatusUpdate, session: Session = Depends(get_session)):
    """Updates the status and retry counts of a queue item."""
    q_item = session.exec(
        select(DeepQueueItem).where(
            (DeepQueueItem.job_id == job_id) & (DeepQueueItem.lead_id == lead_id)
        )
    ).first()
    
    if not q_item:
        raise HTTPException(status_code=404, detail="Queue item not found")
        
    q_item.status = status_up.status
    if status_up.retry_count is not None:
        q_item.retry_count = status_up.retry_count
        
    if status_up.status == "running":
        q_item.started_at = datetime.utcnow()
    elif status_up.status in ["completed", "failed", "skipped"]:
        q_item.completed_at = datetime.utcnow()
        
    q_item.updated_at = datetime.utcnow()
    session.add(q_item)
    session.commit()
    session.refresh(q_item)
    return {"status": "ok", "item": q_item}

class LeadMergePayload(BaseModel):
    website: Optional[str] = None
    website_domain: Optional[str] = None
    primary_phone: Optional[str] = None
    secondary_phones: Optional[str] = None
    primary_email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    open_status: Optional[str] = None
    price_level: Optional[str] = None
    displayed_price: Optional[str] = None
    contacts: Optional[List[dict]] = None
    flexible_metadata: Optional[dict] = None

@router.post("/collection-jobs/{job_id}/queue/{lead_id}/merge")
def merge_queue_lead_data(job_id: str, lead_id: str, payload: LeadMergePayload, session: Session = Depends(get_session)):
    """Merges detailed enrichment data into the existing Snapshot Lead."""
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    import json
    
    print("BEFORE MERGE:")
    print(json.dumps({
        "address": lead.address or "—",
        "phone": lead.primary_phone or "—",
        "website": lead.website or "—"
    }, indent=2))
    
    # 1. Update standard fields
    for field in ["website", "website_domain", "primary_phone", "secondary_phones", 
                  "primary_email", "address", "city", "state", "postal_code",
                  "rating", "review_count", "open_status", "price_level", "displayed_price"]:
        deep_val = getattr(payload, field, None)
        if deep_val is None or deep_val == "":
            continue
            
        snap_val = getattr(lead, field, None)
        if not snap_val:
            setattr(lead, field, deep_val)
        else:
            if isinstance(deep_val, str) and isinstance(snap_val, str):
                if len(deep_val) >= len(snap_val):
                    setattr(lead, field, deep_val)
            else:
                setattr(lead, field, deep_val)
                
    # 2. Merge flexible_metadata JSON
    if payload.flexible_metadata:
        try:
            snap_meta = json.loads(lead.flexible_metadata) if lead.flexible_metadata else {}
        except:
            snap_meta = {}
        merged_meta = {**snap_meta, **payload.flexible_metadata}
        lead.flexible_metadata = json.dumps(merged_meta)
        
    # Calculate completeness
    from services.collection_pipeline import calculate_lead_completeness
    contacts_list = payload.contacts or []
    comp_score = calculate_lead_completeness(lead, contacts_list)
    lead.completeness_score = comp_score
    lead.status = "Incomplete" if comp_score < 50.0 else "New"
    lead.collection_status = "success"  # Explicitly mark collection as success
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    
    # 2.5 Auto-register primary phone & email in contacts table if they don't exist
    if lead.primary_phone:
        exists_phone = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) &
                (Contact.contact_type == "phone") &
                (Contact.contact_value == lead.primary_phone)
            )
        ).first()
        if not exists_phone:
            new_phone = Contact(
                lead_id=lead_id,
                contact_type="phone",
                contact_value=lead.primary_phone,
                sequence_number=1,
                source="deep_collect"
            )
            session.add(new_phone)

    if lead.primary_email:
        exists_email = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) &
                (Contact.contact_type == "email") &
                (Contact.contact_value == lead.primary_email)
            )
        ).first()
        if not exists_email:
            new_email = Contact(
                lead_id=lead_id,
                contact_type="email",
                contact_value=lead.primary_email,
                sequence_number=1,
                source="deep_collect"
            )
            session.add(new_email)
    
    # 3. Add any new contacts from payload
    for idx, c in enumerate(contacts_list):
        c_val = c.get("contact_value")
        c_type = c.get("contact_type", "phone")
        if not c_val:
            continue
            
        exists = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) & 
                (Contact.contact_type == c_type) & 
                (Contact.contact_value == c_val)
            )
        ).first()
        if not exists:
            new_c = Contact(
                lead_id=lead_id,
                contact_type=c_type,
                contact_value=c_val,
                sequence_number=idx + 2, # offset from primary contacts
                source="deep_collect"
            )
            session.add(new_c)
            
    # 4. Mark queue item as completed
    q_item = session.exec(
        select(DeepQueueItem).where(
            (DeepQueueItem.job_id == job_id) & (DeepQueueItem.lead_id == lead_id)
        )
    ).first()
    if q_item:
        q_item.status = "completed"
        q_item.completed_at = datetime.utcnow()
        q_item.updated_at = datetime.utcnow()
        session.add(q_item)
        
    session.commit()
    
    print("AFTER MERGE:")
    print(json.dumps({
        "address": lead.address or "—",
        "phone": lead.primary_phone or "—",
        "website": lead.website or "—"
    }, indent=2))
    
    return {"status": "ok", "lead": lead}

@router.get("/collection-jobs/{job_id}/validation")
def get_job_validation_metrics(job_id: str, session: Session = Depends(get_session)):
    """
    Returns diagnostic validation metrics, completeness matrices, missing fields reports,
    extraction timings, and error logs for a specific collection job.
    """
    from database.models import Lead, DeepQueueItem, CollectionError
    import json

    job = session.get(CollectionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # 1. Basic Stats
    leads = session.exec(select(Lead).where(Lead.batch_id == job_id)).all()
    queue_items = session.exec(select(DeepQueueItem).where(DeepQueueItem.job_id == job_id)).all()
    
    total_leads = len(leads)
    completed_q = sum(1 for q in queue_items if q.status == "completed")
    total_q = len(queue_items)
    queue_success_rate = (completed_q / total_q * 100) if total_q > 0 else 100.0
    
    avg_completeness = sum(l.completeness_score or 0.0 for l in leads) / total_leads if total_leads > 0 else 0.0

    # 2. Field Completeness Matrix
    fields_to_track = [
        "primary_phone", "secondary_phones", "website", "primary_email", "address", 
        "city", "state", "postal_code", "rating", "review_count", "price_level",
        "description", "business_hours", "reservation_link", "booking_link", 
        "order_link", "latitude", "longitude", "plus_code", "amenities", 
        "accessibility_features", "popular_times", "photo_urls", "owner_claimed", 
        "social_links", "hotel_prices", "business_status", "directions_url"
    ]
    
    field_counts = {f: 0 for f in fields_to_track}
    
    for lead in leads:
        # Standard fields
        for field in ["primary_phone", "secondary_phones", "website", "primary_email", "address", "city", "state", "postal_code", "rating", "review_count", "price_level"]:
            val = getattr(lead, field, None)
            if val is not None and val != "" and val != 0 and val != 0.0:
                field_counts[field] += 1
                
        # Flexible metadata fields
        meta = {}
        if lead.flexible_metadata:
            try:
                meta = json.loads(lead.flexible_metadata)
            except:
                pass
        for field in ["description", "business_hours", "reservation_link", "booking_link", "order_link", "latitude", "longitude", "plus_code", "amenities", "accessibility_features", "popular_times", "photo_urls", "owner_claimed", "social_links", "hotel_prices", "business_status", "directions_url"]:
            val = meta.get(field)
            if val is not None and val != "" and val != [] and val != {}:
                field_counts[field] += 1

    field_completeness = {}
    for f in fields_to_track:
        field_completeness[f] = round((field_counts[f] / total_leads * 100), 1) if total_leads > 0 else 0.0

    # 3. Missing Fields Report (sorted by percent missing, highest first)
    missing_report = []
    for f in fields_to_track:
        present_count = field_counts[f]
        missing_count = total_leads - present_count
        missing_pct = round((missing_count / total_leads * 100), 1) if total_leads > 0 else 0.0
        if missing_count > 0:
            missing_report.append({
                "field": f,
                "missing_count": missing_count,
                "missing_percentage": missing_pct
            })
    missing_report.sort(key=lambda x: x["missing_percentage"], reverse=True)

    # 4. Extraction Timing
    job_meta = {}
    if job.metadata_json:
        try:
            job_meta = json.loads(job.metadata_json)
        except:
            pass
            
    snapshot_time = job_meta.get("snapshot_time", 0.0)
    queue_time = job_meta.get("queue_time", 0.0)
    merge_time = job_meta.get("merge_time", 0.0)

    completed_durations = []
    total_retries = 0
    for q in queue_items:
        total_retries += q.retry_count
        if q.started_at and q.completed_at and q.status == "completed":
            dur = (q.completed_at - q.started_at).total_seconds()
            completed_durations.append(dur)
            
    total_deep_time = sum(completed_durations)
    avg_deep_time = sum(completed_durations) / len(completed_durations) if len(completed_durations) > 0 else 0.0

    # 5. Error Logs
    errors_list = session.exec(select(CollectionError).where(CollectionError.batch_id == job_id)).all()
    error_logs = []
    for err in errors_list:
        error_logs.append({
            "error_id": err.error_id,
            "error_category": err.error_category,
            "error_message": err.error_message,
            "collection_stage": err.collection_stage,
            "lead_id": err.lead_id,
            "listing_url": err.listing_url,
            "technical_details": err.technical_details,
            "created_at": err.created_at.isoformat() if err.created_at else None
        })

    # 6. Queue stats
    q_stats = {
        "pending": sum(1 for q in queue_items if q.status == "pending"),
        "running": sum(1 for q in queue_items if q.status == "running"),
        "completed": completed_q,
        "failed": sum(1 for q in queue_items if q.status == "failed"),
        "skipped": sum(1 for q in queue_items if q.status == "skipped"),
        "retrying": sum(1 for q in queue_items if q.status == "retrying"),
    }

    return {
        "status": "ok",
        "validation": {
            "job_id": job_id,
            "website": job.source,
            "mode": job.mode,
            "runtime": job.duration or 0.0,
            "total_seen": job.total_seen,
            "saved": job.saved,
            "duplicates": job.duplicates,
            "failed_extractions": job.errors,
            "queue_success_rate": queue_success_rate,
            "average_completeness_score": avg_completeness,
            "field_completeness_matrix": field_completeness,
            "missing_fields_report": missing_report,
            "timings": {
                "snapshot_time": snapshot_time,
                "queue_time": queue_time,
                "deep_extraction_time": total_deep_time,
                "merge_time": merge_time,
                "avg_extraction_time_per_lead": avg_deep_time
            },
            "performance": {
                "avg_extraction_time": avg_deep_time,
                "retry_count": total_retries,
                "queue_stats": q_stats
            },
            "error_logs": error_logs
        }
    }
