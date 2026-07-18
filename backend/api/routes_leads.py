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
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from database.db import get_session
from database.models import Lead, Contact, SourceRecord
from services.deduplication import compute_dedup_hash, is_duplicate_lead, compute_url_hash
from services.gemini_service import normalize_lead_data
from services.collection_pipeline import CollectionPipeline, calculate_lead_completeness
from services.sync_service import SyncBroadcaster
from services import event_bus
from services.statistics_service import StatisticsService
from config import VALID_CAPSULE_STATUSES

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
async def create_lead(lead_in: LeadIn, session: Session = Depends(get_session)):
    lead_dict = lead_in.model_dump()
    result = await CollectionPipeline.ingest_lead(lead_dict, session)
    return result


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
    approved:     Optional[bool] = Query(None),
    limit:        int           = Query(50, le=500),
    offset:       int           = Query(0),
    session:      Session       = Depends(get_session)
):
    statement = select(Lead)

    # Apply filters if provided
    if source_site:
        statement = statement.where(Lead.source_site == source_site)
    if lead_status:
        if lead_status != "all":
            statement = statement.where(Lead.lead_status == lead_status)
    else:
        if not batch_id:
            statement = statement.where(Lead.lead_status != "retrieved")
        else:
            statement = statement.where(Lead.lead_status == "retrieved")
    if city:
        statement = statement.where(Lead.city == city)
    if batch_id:
        statement = statement.where(Lead.batch_id == batch_id)
    if search:
        statement = statement.where(Lead.business_name.contains(search))
        
    # Apply centralized approval filter
    if approved is not None:
        statement = statement.where(Lead.is_approved == approved)
    else:
        if batch_id:
            statement = statement.where(Lead.is_approved == False)
        else:
            statement = statement.where(Lead.is_approved == True)

    # Order by most recently collected first
    statement = statement.order_by(Lead.collected_at.desc())
    statement = statement.offset(offset).limit(limit)

    leads = session.exec(statement).all()

    # Map phone and email from contacts
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
        "status": "ok",
        "count": len(lead_list),
        "leads": lead_list
    }


# ==============================================================================
# GET /api/leads/stats
# Returns summary counts for the dashboard header cards.
# ==============================================================================

@router.get("/leads/stats")
def get_lead_stats(session: Session = Depends(get_session)):
    main_leads = session.exec(select(Lead).where(Lead.is_approved == True)).all()
    all_leads = session.exec(select(Lead)).all()

    total        = len(main_leads)
    by_status    = {}
    by_source    = {}
    by_city      = {}

    for lead in main_leads:
        by_status[lead.lead_status] = by_status.get(lead.lead_status, 0) + 1
        if lead.city:
            by_city[lead.city] = by_city.get(lead.city, 0) + 1

    for lead in all_leads:
        by_source[lead.source_site] = by_source.get(lead.source_site, 0) + 1

    return {
        "total_leads": total,
        "total_database_leads": len(all_leads),
        "by_status":   by_status,
        "by_source":   by_source,
        "top_cities":  dict(sorted(by_city.items(), key=lambda x: x[1], reverse=True)[:10])
    }


@router.get("/statistics")
def get_global_statistics(session: Session = Depends(get_session)):
    """
    Exposes the dynamically calculated summary metrics from the StatisticsService.
    """
    return StatisticsService.get_summary_stats(session)


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

    # Publish internal event
    event_bus.EventBus.publish(event_bus.LEAD_UPDATED, lead=lead)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "STATUS_UPDATED",
        "lead_id": lead_id,
        "lead_status": lead.lead_status
    })

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

    # Publish internal event
    event_bus.EventBus.publish(event_bus.LEAD_DELETED, lead_id=lead_id)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "LEAD_DELETED",
        "lead_id": lead_id
    })

    return {
        "status": "ok",
        "message": f"Lead {lead_id} deleted successfully"
    }


# ==============================================================================
# EDIT & PROMOTE ENDPOINTS
# ==============================================================================

class LeadUpdate(BaseModel):
    business_name:  Optional[str] = None
    category:       Optional[str] = None
    contact_person: Optional[str] = None
    website:        Optional[str] = None
    address:        Optional[str] = None
    city:           Optional[str] = None
    state:          Optional[str] = None
    postal_code:    Optional[str] = None
    phone:          Optional[str] = None
    email:          Optional[str] = None
    notes:          Optional[str] = None
    tags:           Optional[str] = None
    lead_status:    Optional[str] = None

class PromoteLeadsRequest(BaseModel):
    lead_ids: list[str]

@router.put("/leads/{lead_id}")
def update_lead(lead_id: str, update: LeadUpdate, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if update.business_name is not None: lead.business_name = update.business_name
    if update.category is not None: lead.category = update.category
    if update.contact_person is not None: lead.contact_person = update.contact_person
    if update.website is not None: lead.website = update.website
    if update.address is not None: lead.address = update.address
    if update.city is not None: lead.city = update.city
    if update.state is not None: lead.state = update.state
    if update.postal_code is not None: lead.postal_code = update.postal_code
    if update.notes is not None: lead.notes = update.notes
    if update.tags is not None: lead.tags = update.tags
    if update.lead_status is not None: lead.lead_status = update.lead_status
    
    # Update primary phone
    if update.phone is not None:
        phone_contact = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) & 
                (Contact.contact_type == "phone") & 
                (Contact.sequence_number == 1)
            )
        ).first()
        if phone_contact:
            if update.phone.strip():
                phone_contact.contact_value = update.phone
            else:
                session.delete(phone_contact)
        elif update.phone.strip():
            session.add(Contact(lead_id=lead_id, contact_type="phone", contact_value=update.phone, sequence_number=1, source="editor"))
            
    # Update primary email
    if update.email is not None:
        email_contact = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) & 
                (Contact.contact_type == "email") & 
                (Contact.sequence_number == 1)
            )
        ).first()
        if email_contact:
            if update.email.strip():
                email_contact.contact_value = update.email
            else:
                session.delete(email_contact)
        elif update.email.strip():
            session.add(Contact(lead_id=lead_id, contact_type="email", contact_value=update.email, sequence_number=1, source="editor"))
            
    # Synchronize primary contact cache fields
    if update.phone is not None:
        lead.primary_phone = update.phone.strip() if update.phone.strip() else None
    if update.email is not None:
        lead.primary_email = update.email.strip() if update.email.strip() else None

    # Recalculate completeness score and update workflow metadata
    contacts = session.exec(select(Contact).where(Contact.lead_id == lead_id)).all()
    lead.completeness_score = calculate_lead_completeness(lead, contacts)
    if lead.status == "Incomplete" and lead.completeness_score >= 50.0:
        lead.status = "New"
    lead.updated_at = datetime.utcnow()
            
    session.add(lead)
    session.commit()

    # Publish internal event
    event_bus.EventBus.publish(event_bus.LEAD_UPDATED, lead=lead)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "LEAD_UPDATED",
        "lead_id": lead_id,
        "completeness_score": lead.completeness_score,
        "status": lead.status
    })

    return {"status": "ok", "message": "Lead updated successfully"}

class ApproveLeadsRequest(BaseModel):
    lead_ids: Optional[list[str]] = None
    batch_id: Optional[str] = None

class WorkflowStatusUpdate(BaseModel):
    status: str

@router.post("/leads/approve")
def approve_leads(req: ApproveLeadsRequest, session: Session = Depends(get_session)):
    if req.lead_ids:
        # Approve specific leads
        statement = select(Lead).where(Lead.lead_id.in_(req.lead_ids))
        leads = session.exec(statement).all()
        for lead in leads:
            lead.is_approved = True
            lead.lead_status = "new"  # Set to main leads status
            lead.status = "Approved"
            session.add(lead)
        session.commit()
        
        # Publish internal events
        for lead in leads:
            event_bus.EventBus.publish(event_bus.LEAD_APPROVED, lead=lead)
        
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "LEADS_APPROVED",
            "lead_ids": req.lead_ids
        })
        
        return {"status": "ok", "message": f"Approved {len(leads)} leads"}
    elif req.batch_id:
        # Approve all leads in a batch
        statement = select(Lead).where(Lead.batch_id == req.batch_id)
        leads = session.exec(statement).all()
        for lead in leads:
            lead.is_approved = True
            lead.lead_status = "new"
            lead.status = "Approved"
            session.add(lead)
        session.commit()
        
        # Publish internal events
        for lead in leads:
            event_bus.EventBus.publish(event_bus.LEAD_APPROVED, lead=lead)
        
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "BATCH_APPROVED",
            "batch_id": req.batch_id
        })
        
        return {"status": "ok", "message": f"Approved all {len(leads)} leads in batch {req.batch_id}"}
    else:
        raise HTTPException(status_code=400, detail="Must provide either lead_ids or batch_id")

@router.post("/leads/{lead_id}/approve")
def approve_single_lead(lead_id: str, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.is_approved = True
    lead.lead_status = "new"
    lead.status = "Approved"
    session.add(lead)
    session.commit()

    # Publish internal event
    event_bus.EventBus.publish(event_bus.LEAD_APPROVED, lead=lead)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "LEAD_APPROVED",
        "lead_id": lead_id,
        "source_site": lead.source_site
    })

    return {"status": "ok", "message": "Lead approved", "lead_id": lead_id}

@router.put("/leads/{lead_id}/workflow-status")
def update_workflow_status(
    lead_id: str,
    update: WorkflowStatusUpdate,
    session: Session = Depends(get_session)
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    if update.status not in VALID_CAPSULE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_CAPSULE_STATUSES}")
        
    lead.status = update.status
    
    # Bridge with approval flags
    if update.status in ["Approved", "Moved to Main Leads"]:
        lead.is_approved = True
        lead.lead_status = "new"
    elif update.status == "Rejected":
        lead.is_approved = False
        
    session.add(lead)
    session.commit()
    session.refresh(lead)

    # Publish internal events depending on status changes
    if lead.status == "Enriched":
        event_bus.EventBus.publish(event_bus.LEAD_ENRICHED, lead=lead)
    elif lead.status == "Approved":
        event_bus.EventBus.publish(event_bus.LEAD_APPROVED, lead=lead)
    elif lead.status == "Moved to Main Leads":
        event_bus.EventBus.publish(event_bus.LEAD_MOVED, lead=lead)
    else:
        event_bus.EventBus.publish(event_bus.LEAD_UPDATED, lead=lead)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "WORKFLOW_STATUS_UPDATED",
        "lead_id": lead_id,
        "status": lead.status,
        "is_approved": lead.is_approved
    })

    return {"status": "ok", "message": f"Lead workflow status updated to '{update.status}'", "lead_id": lead_id}

@router.post("/leads/promote")
def promote_leads(req: PromoteLeadsRequest, session: Session = Depends(get_session)):
    promoted_count = 0
    for lead_id in req.lead_ids:
        lead = session.get(Lead, lead_id)
        if lead and lead.lead_status == "retrieved":
            # Check if there is already a lead with the same dedup_hash in the main collection
            existing_main = session.exec(
                select(Lead).where(
                    (Lead.dedup_hash == lead.dedup_hash) & 
                    (Lead.lead_status != "retrieved") &
                    (Lead.lead_id != lead_id)
                )
            ).first()
            
            if existing_main:
                # Delete duplicate temporary lead and its contacts
                contacts = session.exec(select(Contact).where(Contact.lead_id == lead_id)).all()
                for c in contacts:
                    session.delete(c)
                source_records = session.exec(select(SourceRecord).where(SourceRecord.lead_id == lead_id)).all()
                for sr in source_records:
                    session.delete(sr)
                session.delete(lead)
            else:
                lead.lead_status = "new"
                lead.is_approved = True
                lead.status = "Approved"
                session.add(lead)
                promoted_count += 1
                
    session.commit()

    # Publish internal events for promoted leads
    for lead_id in req.lead_ids:
        lead = session.get(Lead, lead_id)
        if lead and lead.is_approved:
            event_bus.EventBus.publish(event_bus.LEAD_APPROVED, lead=lead)

    SyncBroadcaster.broadcast("STATE_UPDATED", {
        "action": "LEADS_PROMOTED",
        "lead_ids": req.lead_ids,
        "count": promoted_count
    })

    return {"status": "ok", "message": f"{promoted_count} leads promoted to main collection"}