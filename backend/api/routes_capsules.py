# backend/api/routes_capsules.py
# ProspectLens — Data Capsule Storage & Isolation Endpoints

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from typing import Optional, List
from database.db import get_session
from database.models import Lead, Contact, CollectionBatch, SourceRecord
from config import SUPPORTED_WEBSITES

router = APIRouter(tags=["Capsules"])

@router.get("/capsules")
def get_capsules_summary(session: Session = Depends(get_session)):
    """
    Retrieve all Data Capsules with their isolated storage metrics.
    Ensures that leads from different websites are grouped and calculated separately.
    """
    summaries = {}
    for site in SUPPORTED_WEBSITES:
        # Isolated total collected
        total_collected = session.exec(
            select(func.count(Lead.lead_id)).where(Lead.source_site == site)
        ).first() or 0

        # Isolated pending user review (in capsule)
        pending_review = session.exec(
            select(func.count(Lead.lead_id))
            .where((Lead.source_site == site) & (Lead.is_approved == False))
        ).first() or 0

        # Isolated approved leads (in main collection)
        approved_leads = session.exec(
            select(func.count(Lead.lead_id))
            .where((Lead.source_site == site) & (Lead.is_approved == True))
        ).first() or 0

        # Latest batch sync timestamp
        latest_batch = session.exec(
            select(CollectionBatch)
            .where(CollectionBatch.source_site == site)
            .order_by(CollectionBatch.created_at.desc())
        ).first()
        
        last_sync = latest_batch.created_at if latest_batch else None

        summaries[site] = {
            "source_site": site,
            "total_collected": total_collected,
            "pending_review": pending_review,
            "approved_leads": approved_leads,
            "last_sync": last_sync
        }
    return summaries

@router.get("/capsules/{source_site}/leads")
def get_capsule_leads(
    source_site: str,
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    session: Session = Depends(get_session)
):
    """
    Get unapproved leads strictly isolated for a single capsule/website.
    Prevents mixing data from different websites.
    """
    site_key = source_site.lower().replace(" ", "").strip()
    if site_key not in SUPPORTED_WEBSITES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported website capsule. Must be one of: {SUPPORTED_WEBSITES}"
        )

    statement = (
        select(Lead)
        .where((Lead.source_site == site_key) & (Lead.is_approved == False))
        .order_by(Lead.collected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    leads = session.exec(statement).all()

    # Map contacts
    lead_list = []
    for lead in leads:
        lead_dict = lead.model_dump()
        
        phone_contact = session.exec(
            select(Contact)
            .where((Contact.lead_id == lead.lead_id) & (Contact.contact_type == "phone"))
            .order_by(Contact.sequence_number.asc())
        ).first()
        lead_dict["phone"] = phone_contact.contact_value if phone_contact else None
        
        email_contact = session.exec(
            select(Contact)
            .where((Contact.lead_id == lead.lead_id) & (Contact.contact_type == "email"))
            .order_by(Contact.sequence_number.asc())
        ).first()
        lead_dict["email"] = email_contact.contact_value if email_contact else None
        
        lead_list.append(lead_dict)

    return {
        "source_site": site_key,
        "leads": lead_list,
        "count": len(lead_list)
    }

@router.delete("/capsules/{source_site}")
def clear_capsule_storage(source_site: str, session: Session = Depends(get_session)):
    """
    Clear all unapproved review data inside a specific capsule storage room.
    Does not delete approved leads.
    """
    site_key = source_site.lower().replace(" ", "").strip()
    if site_key not in SUPPORTED_WEBSITES:
        raise HTTPException(status_code=400, detail="Invalid capsule source")

    # Fetch all unapproved leads for this source
    unapproved_leads = session.exec(
        select(Lead).where((Lead.source_site == site_key) & (Lead.is_approved == False))
    ).all()

    deleted_count = 0
    for lead in unapproved_leads:
        # Delete contacts
        contacts = session.exec(select(Contact).where(Contact.lead_id == lead.lead_id)).all()
        for c in contacts:
            session.delete(c)
        # Delete source records
        source_records = session.exec(select(SourceRecord).where(SourceRecord.lead_id == lead.lead_id)).all()
        for sr in source_records:
            session.delete(sr)
        # Delete lead
        session.delete(lead)
        deleted_count += 1

    session.commit()
    return {
        "status": "ok",
        "message": f"Successfully cleared {deleted_count} unapproved leads from {source_site} capsule."
    }

@router.post("/capsules/{source_site}/approve")
def approve_entire_capsule(source_site: str, session: Session = Depends(get_session)):
    """
    Approve all unapproved leads isolated in this capsule.
    Promotes them to Main Leads.
    """
    site_key = source_site.lower().replace(" ", "").strip()
    if site_key not in SUPPORTED_WEBSITES:
        raise HTTPException(status_code=400, detail="Invalid capsule source")

    unapproved_leads = session.exec(
        select(Lead).where((Lead.source_site == site_key) & (Lead.is_approved == False))
    ).all()

    for lead in unapproved_leads:
        lead.is_approved = True
        lead.lead_status = "new"
        session.add(lead)

    session.commit()
    return {
        "status": "ok",
        "message": f"Approved all {len(unapproved_leads)} leads from {source_site} capsule."
    }

@router.get("/capsules/{source_site}")
def get_capsule_details(source_site: str, session: Session = Depends(get_session)):
    """
    Get detailed metrics, status, and logs for a website capsule.
    Ensures complete isolation.
    """
    site_key = source_site.lower().replace(" ", "").strip()
    if site_key not in SUPPORTED_WEBSITES:
        raise HTTPException(status_code=400, detail="Invalid capsule source")

    # 1. Fetch Capsule Meta
    capsule = session.exec(
        select(DataCapsule).where(DataCapsule.source_site == site_key)
    ).first()
    
    # 2. Leads statistics
    total_leads = session.exec(
        select(func.count(Lead.lead_id)).where((Lead.source_site == site_key) & (Lead.is_approved == False))
    ).first() or 0

    approved_leads = session.exec(
        select(func.count(Lead.lead_id)).where((Lead.source_site == site_key) & (Lead.is_approved == True))
    ).first() or 0

    # 3. Collection Sessions
    batches = session.exec(
        select(CollectionBatch)
        .where(CollectionBatch.source_site == site_key)
        .order_by(CollectionBatch.created_at.desc())
    ).all()

    # 4. Search history (Queries & search URLs if available)
    search_history = session.exec(
        select(SearchHistory)
        .where(SearchHistory.source_site == site_key)
        .order_by(SearchHistory.searched_at.desc())
    ).all()

    # 5. Last updated time
    last_updated = capsule.last_sync_at if capsule else None
    if not last_updated and batches:
        last_updated = batches[0].created_at

    return {
        "source_site": site_key,
        "is_locked": capsule.is_locked if capsule else False,
        "last_updated": last_updated,
        "statistics": {
            "pending_review": total_leads,
            "approved": approved_leads,
            "total_collected": total_leads + approved_leads
        },
        "collection_sessions": [b.model_dump() for b in batches],
        "search_history": [sh.model_dump() for sh in search_history]
    }
