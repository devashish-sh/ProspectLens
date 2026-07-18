# backend/services/collection_pipeline.py
# Centralized Data Collection Pipeline for ProspectLens

from sqlmodel import Session, func
from database.models import Lead, Contact, SourceRecord, CollectionBatch, DataCapsule, SearchHistory, LeadHistory
from services.deduplication import compute_dedup_hash, is_duplicate_lead
from services.gemini_service import normalize_lead_data
import asyncio
from datetime import datetime

def calculate_lead_completeness(lead: Lead, contacts: list) -> float:
    score = 0.0
    
    # 1. Company Name
    if lead.business_name and lead.business_name.strip():
        score += 12.5
        
    # 2. Location
    if (lead.address and lead.address.strip()) or (lead.city and lead.city.strip()) or (lead.state and lead.state.strip()) or (lead.postal_code and lead.postal_code.strip()):
        score += 12.5
        
    # 3. Phone
    has_phone = False
    if lead.primary_phone and lead.primary_phone.strip():
        has_phone = True
    elif contacts:
        if any(c.contact_type == "phone" and c.contact_value.strip() for c in contacts):
            has_phone = True
    if has_phone:
        score += 12.5
        
    # 4. Email
    has_email = False
    if lead.primary_email and lead.primary_email.strip():
        has_email = True
    elif contacts:
        if any(c.contact_type == "email" and c.contact_value.strip() for c in contacts):
            has_email = True
    if has_email:
        score += 12.5
        
    # 5. Website
    if lead.website and lead.website.strip():
        score += 12.5
        
    # 6. Reviews
    if lead.review_count is not None and lead.review_count > 0:
        score += 12.5
        
    # 7. Listing URL
    if lead.listing_url and lead.listing_url.strip():
        score += 12.5
        
    # 8. Rating
    if lead.rating is not None and lead.rating > 0.0:
        score += 12.5
        
    return min(100.0, score)

class CollectionPipeline:
    
    @staticmethod
    async def ingest_lead(lead_data: dict, session: Session) -> dict:
        """
        Centralized pipeline to ingest any lead collected from any source (Quick / Deep).
        All ingested leads:
        1. Are normalized using the AI normalizing service.
        2. Are checked for duplication.
        3. Are saved with is_approved=False and lead_status="retrieved" (ensuring they only go to Data Capsules/User Review).
        """
        # Step 1: Normalize raw details using Gemini/local heuristics
        raw_lead_dict = {
            "business_name": lead_data.get("business_name", ""),
            "address": lead_data.get("address"),
            "phone": lead_data.get("contacts")[0]["contact_value"] if lead_data.get("contacts") else None,
            "city": lead_data.get("city"),
            "state": lead_data.get("state"),
            "postal_code": lead_data.get("postal_code"),
            "contact_person": lead_data.get("contact_person"),
            "category": lead_data.get("category")
        }
        normalized = await normalize_lead_data(raw_lead_dict)

        # Use normalized values
        biz_name = normalized.get("business_name") or lead_data.get("business_name", "")
        addr = normalized.get("address") or lead_data.get("address")
        city_val = normalized.get("city") or lead_data.get("city")
        state_val = normalized.get("state") or lead_data.get("state")
        pin_val = normalized.get("postal_code") or lead_data.get("postal_code")
        person_val = normalized.get("contact_person") or lead_data.get("contact_person")
        cat_val = normalized.get("category") or lead_data.get("category")

        # Step 2: Compute dedup hash
        dedup_hash = compute_dedup_hash(
            business_name=biz_name,
            source_site=lead_data.get("source_site", ""),
            address=addr or ""
        )

        # Step 3: Deduplicate
        if is_duplicate_lead(dedup_hash, session):
            return {
                "status": "duplicate",
                "message": f"Lead '{biz_name}' already exists — skipped",
                "lead_id": None
            }

        # Step 3.5: Validate that batch source_site matches lead source_site to keep capsules isolated
        batch_id = lead_data.get("batch_id")
        if batch_id:
            batch = session.get(CollectionBatch, batch_id)
            if batch and batch.source_site != lead_data.get("source_site"):
                return {
                    "status": "error",
                    "message": f"Source site mismatch: Lead from '{lead_data.get('source_site')}' cannot be mixed into batch/capsule '{batch.source_site}'",
                    "lead_id": None
                }

        # Calculate contact information
        normalized_phone = normalized.get("phone")
        normalized_email = normalized.get("email")
        if not normalized_email and lead_data.get("contacts"):
            emails = [c for c in lead_data["contacts"] if c.get("contact_type") == "email"]
            if emails:
                normalized_email = emails[0].get("contact_value")

        # Step 4: Create Lead record (forcing is_approved=False and lead_status="retrieved")
        lead = Lead(
            batch_id=lead_data.get("batch_id"),
            search_query=lead_data.get("search_query", ""),
            source_site=lead_data.get("source_site", ""),
            business_name=biz_name,
            service_name=lead_data.get("service_name"),
            contact_person=person_val,
            website=lead_data.get("website"),
            address=addr,
            city=city_val,
            state=state_val,
            country=lead_data.get("country", "India"),
            postal_code=pin_val,
            category=cat_val,
            listing_url=lead_data.get("listing_url"),
            collection_mode=lead_data.get("collection_mode", "quick"),
            collection_status="partial" if lead_data.get("collection_mode") == "deep" else "success",
            lead_status="retrieved", # Initial state for User Review
            is_approved=False,       # Centralized rule: never approved directly
            
            # Contact Information Cache
            primary_email=normalized_email,
            primary_phone=normalized_phone,

            # Business Information
            review_count=lead_data.get("review_count"),
            rating=lead_data.get("rating"),
            business_profile_url=lead_data.get("business_profile_url"),

            # Collection Information
            directory_search_url=lead_data.get("directory_search_url"),
            
            dedup_hash=dedup_hash
        )
        
        # Calculate final completeness score using the standard formula
        comp_score = calculate_lead_completeness(lead, lead_data.get("contacts", []))
        lead.completeness_score = comp_score
        lead.status = "Incomplete" if comp_score < 50.0 else "New"
        session.add(lead)
        session.flush()

        # Step 5: Save all contacts
        normalized_phone = normalized.get("phone")
        contacts_in = lead_data.get("contacts", [])
        for i, c in enumerate(contacts_in):
            c_val = c.get("contact_value")
            if c.get("contact_type") == "phone" and i == 0 and normalized_phone:
                c_val = normalized_phone
            contact = Contact(
                lead_id=lead.lead_id,
                contact_type=c.get("contact_type", "phone"),
                contact_value=c_val,
                sequence_number=c.get("sequence_number", 1),
                source=c.get("source", "listing")
            )
            session.add(contact)

        # Step 6: Save source record
        source_record = SourceRecord(
            lead_id=lead.lead_id,
            source_site=lead_data.get("source_site", ""),
            listing_url=lead_data.get("listing_url")
        )
        session.add(source_record)

        # Step 7: Update DataCapsule metrics and last sync timestamps
        capsule = session.exec(select(DataCapsule).where(DataCapsule.source_site == lead.source_site)).first()
        if not capsule:
            capsule = DataCapsule(source_site=lead.source_site, total_leads_count=1, last_sync_at=datetime.utcnow())
            session.add(capsule)
        else:
            total_count = session.exec(
                select(func.count(Lead.lead_id)).where(Lead.source_site == lead.source_site)
            ).first() or 0
            capsule.total_leads_count = total_count + 1
            capsule.last_sync_at = datetime.utcnow()
            session.add(capsule)

        # Step 8: Log SearchHistory if query is provided
        if lead.search_query:
            recent_search = session.exec(
                select(SearchHistory).where(
                    (SearchHistory.search_query == lead.search_query) &
                    (SearchHistory.source_site == lead.source_site)
                ).order_by(SearchHistory.searched_at.desc())
            ).first()
            if not recent_search or (datetime.utcnow() - recent_search.searched_at).total_seconds() > 60:
                search_history = SearchHistory(
                    search_query=lead.search_query,
                    source_site=lead.source_site,
                    total_results_found=1
                )
                session.add(search_history)
            else:
                recent_search.total_results_found += 1
                session.add(recent_search)

        # Step 9: Log LeadHistory (Audit log)
        lead_history = LeadHistory(
            lead_id=lead.lead_id,
            action_type="collected",
            new_value=lead.status,
            changed_by="pipeline"
        )
        session.add(lead_history)

        session.commit()
        session.refresh(lead)

        # Publish internal event
        from services import event_bus
        event_bus.EventBus.publish(event_bus.LEAD_ADDED, lead=lead)

        # Broadcast state synchronization event
        from services.sync_service import SyncBroadcaster
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "LEAD_COLLECTED",
            "lead_id": lead.lead_id,
            "source_site": lead.source_site,
            "status": lead.status
        })

        return {
            "status": "saved",
            "message": f"Lead '{lead.business_name}' saved via Pipeline successfully",
            "lead_id": lead.lead_id
        }
