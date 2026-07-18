# backend/api/routes_discovery.py
# ProspectLens — Listing Discovery Engine Endpoint

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel

from database.db import get_session
from services.discovery_engine import ListingDiscoveryEngine

router = APIRouter(tags=["Discovery"])

class ListingNode(BaseModel):
    dom_reference:      str
    listing_id:         Optional[str] = None
    listing_position:   Optional[int] = 0
    page_position:      Optional[int] = 1
    visible_state:      Optional[bool] = True
    is_ad:              Optional[bool] = False
    is_sponsored:       Optional[bool] = False
    is_skeleton:        Optional[bool] = False
    collection_status:  Optional[str] = "discovered"

class RegisterDiscoveryRequest(BaseModel):
    batch_id:   str
    website:    str
    listings:   List[ListingNode]

@router.post("/discovery/register")
def register_discovered_listings(req: RegisterDiscoveryRequest, session: Session = Depends(get_session)):
    """
    Registers a batch of discovered DOM nodes from the client extension,
    filters ads/sponsored nodes, deduplicates records, and updates stats.
    """
    listings_list = [l.model_dump() for l in req.listings]
    result = ListingDiscoveryEngine.register_discovery(session, req.batch_id, req.website, listings_list)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

@router.get("/discovery/{batch_id}/stats")
def get_session_discovery_stats(batch_id: str, session: Session = Depends(get_session)):
    """
    Returns counts and list parameters of all tracked listings in a collection batch session.
    """
    result = ListingDiscoveryEngine.get_session_discovery(session, batch_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"No discovery metrics found for session {batch_id}")
    return result
