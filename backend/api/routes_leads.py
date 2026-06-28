# backend/api/routes_leads.py
# ProspectLens — Lead Management Endpoints
#
# This file handles everything related to leads:
# - Saving new leads from the Chrome extension  (POST /api/leads)
# - Fetching leads with filters               (GET  /api/leads)
# - Getting a single lead by ID               (GET  /api/leads/{lead_id})
# - Updating lead status                      (PUT  /api/leads/{lead_id}/status)
# - Deleting a lead                           (DELETE /api/leads/{lead_id})
# - Getting lead statistics                   (GET  /api/leads/stats)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from database.db import get_session
from database.models import Lead, Contact, SourceRecord
from services.deduplication import compute_dedup_hash, is_duplicate_lead, compute_url_hash

router = APIRouter(tags=["Leads"])


# ==============================================================================
# REQUEST BODY SCHEMAS
# These define what data the Chrome extension sends when saving a lead
# ==============================================================================

from pydantic import BaseModel

class ContactIn(BaseModel):
    contact_type:    str          # phone / email / whatsapp / linkedin
    contact_value:   str          # the actual number or email
    sequence_number: int = 1
    source:          str = "listing"

class LeadIn(BaseModel):
    # Required fields
    batch_id:        str
    source_site:     str          # indiamart / googlemaps / justdial
    business_name:   str
    search_query:    str = ""

    # Optional fields — filled in when available
    service_name:    Optional[str] = None
    contact_person:  Optional[str] = None
    website:         Optional[str] = None
    address:         Optional[str] = None
    city:            Optional[str] = None
    state:           Optional[str] = None
    country:         str = "India"
    postal_code:     Optional[str] = None
    category:        Optional[str] = None
    listing_url:     Optional[str] = None
    collection_mode: str = "quick"

    # Contacts list — phones, emails etc
    contacts:        list[ContactIn] = []


class LeadStatusUpdate(BaseModel):
    lead_status: str    # new / contacted / qualified / closed


# ==============================================================================
# POST /api/leads
# Called by Chrome extension to save a collected lead.
# Runs deduplication before saving — skips if lead already exists.
# ==============================================================================

@router.post("/leads")
def create_lead(lead_in: LeadIn, session: Session = Depends(get_session)):

    # Step 1 — Compute dedup hash
    dedup_hash = compute_dedup_hash(
        business_name=lead_in.business_name,
        source_site=lead_in.source_site,
        address=lead_in.address or ""
    )

    # Step 2 — Check for duplicate
    if is_duplicate_lead(dedup_hash, session):
        return {
            "status": "duplicate",
            "message": f"Lead '{lead_in.business_name}' already exists — skipped",
            "lead_id": None
        }

    # Step 3 — Create Lead record
    lead = Lead(
        batch_id=lead_in.batch_id,
        search_query=lead_in.search_query,
        source_site=lead_in.source_site,
        business_name=lead_in.business_name,
        service_name=lead_in.service_name,
        contact_person=lead_in.contact_person,
        website=lead_in.website,
        address=lead_in.address,
        city=lead_in.city,
        state=lead_in.state,
        country=lead_in.country,
        postal_code=lead_in.postal_code,
        category=lead_in.category,
        listing_url=lead_in.listing_url,
        collection_mode=lead_in.collection_mode,
        collection_status="success",
        dedup_hash=dedup_hash
    )
    session.add(lead)
    session.flush()     # Flush to get lead_id before saving contacts

    # Step 4 — Save all contacts
    for c in lead_in.contacts:
        contact = Contact(
            lead_id=lead.lead_id,
            contact_type=c.contact_type,
            contact_value=c.contact_value,
            sequence_number=c.sequence_number,
            source=c.source
        )
        session.add(contact)

    # Step 5 — Save source record (cross-platform tracking)
    source_record = SourceRecord(
        lead_id=lead.lead_id,
        source_site=lead_in.source_site,
        listing_url=lead_in.listing_url
    )
    session.add(source_record)

    session.commit()
    session.refresh(lead)

    return {
        "status": "saved",
        "message": f"Lead '{lead.business_name}' saved successfully",
        "lead_id": lead.lead_id
    }


# ==============================================================================
# GET /api/leads
# Fetch leads with optional filters.
# The Chrome extension dashboard uses this to display the leads table.
#
# Query parameters (all optional):
#   ?source_site=indiamart
#   ?lead_status=new
#   ?city=Noida
#   ?batch_id=abc-123
#   ?search=ABC Interiors     ← searches business_name
#   ?limit=50&offset=0        ← pagination
# ==============================================================================

@router.get("/leads")
def get_leads(
    source_site:  Optional[str] = Query(None),
    lead_status:  Optional[str] = Query(None),
    city:         Optional[str] = Query(None),
    batch_id:     Optional[str] = Query(None),
    search:       Optional[str] = Query(None),
    limit:        int           = Query(50, le=500),
    offset:       int           = Query(0),
    session:      Session       = Depends(get_session)
):
    statement = select(Lead)

    # Apply filters if provided
    if source_site:
        statement = statement.where(Lead.source_site == source_site)
    if lead_status:
        statement = statement.where(Lead.lead_status == lead_status)
    if city:
        statement = statement.where(Lead.city == city)
    if batch_id:
        statement = statement.where(Lead.batch_id == batch_id)
    if search:
        statement = statement.where(Lead.business_name.contains(search))

    # Order by most recently collected first
    statement = statement.order_by(Lead.collected_at.desc())
    statement = statement.offset(offset).limit(limit)

    leads = session.exec(statement).all()

    return {
        "status": "ok",
        "count": len(leads),
        "leads": leads
    }


# ==============================================================================
# GET /api/leads/stats
# Returns summary counts for the dashboard header cards.
# ==============================================================================

@router.get("/leads/stats")
def get_lead_stats(session: Session = Depends(get_session)):
    all_leads = session.exec(select(Lead)).all()

    total        = len(all_leads)
    by_status    = {}
    by_source    = {}
    by_city      = {}

    for lead in all_leads:
        # Count by status
        by_status[lead.lead_status] = by_status.get(lead.lead_status, 0) + 1
        # Count by source
        by_source[lead.source_site] = by_source.get(lead.source_site, 0) + 1
        # Count by city
        if lead.city:
            by_city[lead.city] = by_city.get(lead.city, 0) + 1

    return {
        "total_leads": total,
        "by_status":   by_status,
        "by_source":   by_source,
        "top_cities":  dict(sorted(by_city.items(), key=lambda x: x[1], reverse=True)[:10])
    }


# ==============================================================================
# GET /api/leads/{lead_id}
# Get a single lead with all its contacts.
# ==============================================================================

@router.get("/leads/{lead_id}")
def get_lead(lead_id: str, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    # Get all contacts for this lead
    contacts = session.exec(
        select(Contact).where(Contact.lead_id == lead_id)
    ).all()

    return {
        "status": "ok",
        "lead": lead,
        "contacts": contacts
    }


# ==============================================================================
# PUT /api/leads/{lead_id}/status
# Update a lead's status — called from the extension dashboard.
# ==============================================================================

@router.put("/leads/{lead_id}/status")
def update_lead_status(
    lead_id: str,
    update: LeadStatusUpdate,
    session: Session = Depends(get_session)
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    valid_statuses = ["new", "contacted", "qualified", "closed"]
    if update.lead_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    lead.lead_status = update.lead_status
    session.add(lead)
    session.commit()
    session.refresh(lead)

    return {
        "status": "ok",
        "message": f"Lead status updated to '{update.lead_status}'",
        "lead_id": lead_id
    }


# ==============================================================================
# DELETE /api/leads/{lead_id}
# Delete a lead and all its contacts.
# ==============================================================================

@router.delete("/leads/{lead_id}")
def delete_lead(lead_id: str, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    # Delete all contacts first (foreign key dependency)
    contacts = session.exec(
        select(Contact).where(Contact.lead_id == lead_id)
    ).all()
    for contact in contacts:
        session.delete(contact)

    # Delete source records
    source_records = session.exec(
        select(SourceRecord).where(SourceRecord.lead_id == lead_id)
    ).all()
    for sr in source_records:
        session.delete(sr)

    session.delete(lead)
    session.commit()

    return {
        "status": "ok",
        "message": f"Lead {lead_id} deleted successfully"
    }