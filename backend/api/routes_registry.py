# backend/api/routes_registry.py
# ProspectLens — Website Sources Registry Endpoint

import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from database.db import get_session
from database.models import WebsiteSource, DataCapsule

router = APIRouter(tags=["Registry"])

class WebsiteSourceIn(BaseModel):
    source_key:       str
    display_name:     str
    base_url:         Optional[str] = None
    icon_path:        Optional[str] = None
    adapter_key:      Optional[str] = None
    capabilities:     List[str] = []
    collection_types: List[str] = ["quick"]

@router.get("/registry/websites")
def list_registered_websites(session: Session = Depends(get_session)):
    """
    Lists all website sources registered in the database, parsing JSON strings.
    """
    sources = session.exec(select(WebsiteSource)).all()
    result = []
    for s in sources:
        # Safely parse JSON strings to lists
        caps = []
        if s.capabilities:
            try:
                caps = json.loads(s.capabilities)
            except Exception:
                caps = [s.capabilities]
                
        types = []
        if s.collection_types:
            try:
                types = json.loads(s.collection_types)
            except Exception:
                types = [s.collection_types]

        result.append({
            "source_id": s.source_id,
            "source_key": s.source_key,
            "display_name": s.display_name,
            "base_url": s.base_url,
            "is_active": s.is_active,
            "icon_path": s.icon_path,
            "adapter_key": s.adapter_key,
            "capabilities": caps,
            "collection_types": types,
            "created_at": s.created_at
        })
    return {
        "status": "ok",
        "count": len(result),
        "websites": result
    }

@router.post("/registry/websites")
def register_website(source_in: WebsiteSourceIn, session: Session = Depends(get_session)):
    """
    Registers a new website source at runtime.
    Automatically creates a corresponding Data Capsule.
    """
    existing = session.exec(
        select(WebsiteSource).where(WebsiteSource.source_key == source_in.source_key)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Source with key '{source_in.source_key}' is already registered")

    new_source = WebsiteSource(
        source_key=source_in.source_key,
        display_name=source_in.display_name,
        base_url=source_in.base_url,
        icon_path=source_in.icon_path,
        adapter_key=source_in.adapter_key,
        capabilities=json.dumps(source_in.capabilities),
        collection_types=json.dumps(source_in.collection_types),
        is_active=True
    )
    session.add(new_source)

    # Automatically create isolated Data Capsule for the new source site
    capsule = DataCapsule(
        source_site=source_in.source_key,
        is_locked=False,
        total_leads_count=0
    )
    session.add(capsule)
    
    session.commit()
    session.refresh(new_source)

    return {
        "status": "ok",
        "message": f"Website source '{source_in.display_name}' registered successfully",
        "website": new_source
    }
