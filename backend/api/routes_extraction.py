# backend/api/routes_extraction.py
# ProspectLens — Quick Collect Extraction Engine Endpoint

from typing import List, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.extraction_engine import QuickCollectExtractionEngine

router = APIRouter(tags=["Extraction"])

class ExtractBatchRequest(BaseModel):
    website:  str
    payloads: List[dict]

@router.post("/extraction/extract")
def extract_visible_fields(req: ExtractBatchRequest):
    """
    Accepts raw scraped cards, runs adapter normalization/validations in-memory,
    generates Lead profiles, and compiles stats without writing to database.
    """
    result = QuickCollectExtractionEngine.extract_batch_payloads(req.website, req.payloads)
    return result
