# backend/api/routes_adapters.py
# ProspectLens — Website Detection & Adapter Resolution Endpoint

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel

from database.db import get_session
from services.adapter_manager import AdapterManager

router = APIRouter(tags=["Adapters"])

class DetectAdapterRequest(BaseModel):
    url:             str
    collection_mode: Optional[str] = "quick"

@router.post("/adapter/detect")
def detect_and_resolve_adapter(req: DetectAdapterRequest, session: Session = Depends(get_session)):
    """
    Accepts a page URL, detects the website source, checks registry capabilities,
    audits health statuses, and resolves its configuration limits profile.
    """
    result = AdapterManager.resolve_adapter(req.url, session, req.collection_mode)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class CheckEligibilityRequest(BaseModel):
    url:             str
    collection_mode: Optional[str] = "quick"
    batch_id:        Optional[str] = None

@router.post("/adapter/eligibility")
def check_page_eligibility(req: CheckEligibilityRequest, session: Session = Depends(get_session)):
    """
    Accepts page details, maps adapters, identifies layout structures,
    and runs multi-level validation to verify if the URL is eligible for collection.
    """
    result = AdapterManager.check_eligibility(req.url, session, req.collection_mode, req.batch_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
