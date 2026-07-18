# backend/api/routes_ingestion.py
# ProspectLens — Ingestion Pipeline Endpoints

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel

from database.db import get_session
from services.collection_pipeline import CollectionPipeline

router = APIRouter(tags=["Ingestion"])

class BatchLeadIn(BaseModel):
    business_name:  str
    primary_phone:  Optional[str] = None
    primary_email:  Optional[str] = None
    website:        Optional[str] = None
    address:        Optional[str] = None
    city:           Optional[str] = None
    state:          Optional[str] = None
    postal_code:    Optional[str] = None
    category:       Optional[str] = None
    listing_url:    Optional[str] = None
    rating:         Optional[float] = None
    review_count:   Optional[int] = None
    contact_person: Optional[str] = None

class IngestionRequest(BaseModel):
    batch_id: str
    website:  str
    leads:    List[BatchLeadIn]

@router.post("/pipeline/ingest")
async def ingest_batch_leads(req: IngestionRequest, session: Session = Depends(get_session)):
    """
    Ingests multiple leads through the centralized Collection Pipeline.
    Runs deduplication, AI normalization, data capsule mapping, version logs,
    and updates the session progress engine sequentially.
    """
    leads_list = [lead.model_dump() for lead in req.leads]
    result = await CollectionPipeline.ingest_batch(session, req.batch_id, req.website, leads_list)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
