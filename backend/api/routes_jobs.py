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
