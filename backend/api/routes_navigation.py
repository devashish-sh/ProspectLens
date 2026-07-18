# backend/api/routes_navigation.py
# ProspectLens — Navigation Routing Flow Endpoint

from fastapi import APIRouter
from config import NAVIGATION_FLOW

router = APIRouter(tags=["Navigation"])

@router.get("/navigation/mapping")
def get_navigation_mapping():
    """
    Exposes the hierarchical navigation routing structure for ProspectLens:
    Popup -> Data Capsule -> Dashboard -> Selected Website -> Listing View.
    """
    return NAVIGATION_FLOW
