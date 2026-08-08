# backend/services/collection_pipeline.py
# Centralized Data Collection Pipeline for ProspectLens

from sqlmodel import Session, func, select
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
        for c in contacts:
            c_type = c.contact_type if hasattr(c, "contact_type") else c.get("contact_type")
            c_val = c.contact_value if hasattr(c, "contact_value") else c.get("contact_value")
            if c_type == "phone" and c_val and str(c_val).strip():
                has_phone = True
                break
    if has_phone:
        score += 12.5
        
    # 4. Email
    has_email = False
    if lead.primary_email and lead.primary_email.strip():
        has_email = True
    elif contacts:
        for c in contacts:
            c_type = c.contact_type if hasattr(c, "contact_type") else c.get("contact_type")
            c_val = c.contact_value if hasattr(c, "contact_value") else c.get("contact_value")
            if c_type == "email" and c_val and str(c_val).strip():
                has_email = True
                break
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
        # Debug Log: Lead ID
        print(f"[DEBUG_AUDIT] Lead ID: '{lead_data.get('business_name')}' | Step 1: Validation & normalization started")
        
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

        # Step 2.5: Verify capability and health status of the website source
        source_site = lead_data.get("source_site", "")
        mode = lead_data.get("collection_mode", "quick")
        capability = "quick_collect" if mode == "quick" else "deep_collect"
        
        from services.health_monitor import WebsiteHealthMonitor
        if not WebsiteHealthMonitor.is_capability_available(session, source_site, capability):
            return {
                "status": "error",
                "message": f"Website source '{source_site}' is currently offline, disabled, or does not support collection mode '{mode}'",
                "lead_id": None
            }

        # Step 3: Deduplicate
        if is_duplicate_lead(dedup_hash, session):
            try:
                from database.models import CollectionJob
                job = session.get(CollectionJob, lead_data.get("batch_id"))
                if job:
                    job.total_seen += 1
                    job.duplicates += 1
                    job.updated_at = datetime.utcnow()
                    session.add(job)
                    session.commit()
            except Exception as e:
                print(f"[DB] Error incrementing job duplicate counter: {e}")

            # Retrieve existing lead_id
            existing_lead = session.exec(select(Lead).where(Lead.dedup_hash == dedup_hash)).first()
            existing_id = existing_lead.lead_id if existing_lead else None

            return {
                "status": "duplicate",
                "message": f"Lead '{biz_name}' already exists — skipped",
                "lead_id": existing_id
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
            
            # New fields for Sprint 4.3 Quick Collect Expansion
            search_keyword=lead_data.get("search_keyword"),
            search_location=lead_data.get("search_location"),
            collection_date=lead_data.get("collection_date"),
            collection_time=lead_data.get("collection_time"),
            website_domain=lead_data.get("website_domain"),
            open_status=lead_data.get("open_status"),
            displayed_price=lead_data.get("displayed_price"),
            price_currency=lead_data.get("price_currency"),
            price_type=lead_data.get("price_type"),
            price_level=lead_data.get("price_level"),
            flexible_metadata=__import__("json").dumps(lead_data.get("flexible_metadata")) if isinstance(lead_data.get("flexible_metadata"), dict) else lead_data.get("flexible_metadata"),

            # Sprint 4.4 Universal Schema additions
            sub_category=lead_data.get("sub_category"),
            source_business_id=lead_data.get("source_business_id"),
            collector_version=lead_data.get("collector_version", "1.0.0"),
            secondary_phones=lead_data.get("secondary_phones"),

            dedup_hash=dedup_hash
        )
        
        # Calculate final completeness score using the standard formula
        comp_score = calculate_lead_completeness(lead, lead_data.get("contacts", []))
        lead.completeness_score = comp_score
        lead.status = "Incomplete" if comp_score < 50.0 else "New"
        
        print(f"[DEBUG_AUDIT] Lead ID: '{lead.business_name}' | Step 2: Validation success (Completeness: {comp_score})")
        session.add(lead)

        # Increment active collection job counters (Sprint 4.5)
        try:
            from database.models import CollectionJob
            job = session.get(CollectionJob, lead.batch_id)
            if job:
                job.total_seen += 1
                job.saved += 1
                job.updated_at = datetime.utcnow()
                session.add(job)
        except Exception as e:
            print(f"[DB] Error incrementing collection job counter: {e}")

        session.flush()
        print(f"[DEBUG_AUDIT] Lead ID: '{lead.business_name}' | Step 3: Database Save (flushed)")

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

        # Call Lead Versioning Service to log the creation event
        from services.version_service import VersionService
        VersionService.record_creation(session, lead)

        session.commit()
        print(f"[DEBUG_AUDIT] Lead ID: '{lead.business_name}' | Step 4: Database transaction committed successfully")
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

        print(f"[DEBUG_AUDIT] Lead ID: '{lead.business_name}' | Step 5: Returned Status -> 'saved'")
        return {
            "status": "saved",
            "message": f"Lead '{lead.business_name}' saved via Pipeline successfully",
            "lead_id": lead.lead_id
        }

    @staticmethod
    async def ingest_batch(
        session: Session,
        batch_id: str,
        website: str,
        raw_leads: list
    ) -> dict:
        """
        Ingests a batch of leads sequentially through the centralized pipeline.
        Updates progress engine and statistics after each lead, and handles duplicate/failure cases gracefully.
        """
        # Fetch batch
        batch = session.get(CollectionBatch, batch_id)
        if not batch:
            return {"status": "error", "message": f"Session batch {batch_id} not found"}

        from services.progress_engine import CollectionProgressEngine
        from services.error_tracker import CollectionErrorTracker
        from services.sync_service import SyncBroadcaster
        from database.models import SearchContext

        # Fetch search context for search_location mapping
        search_ctx = session.exec(
            select(SearchContext).where(SearchContext.batch_id == batch_id)
        ).first()
        search_loc = search_ctx.search_location if search_ctx else None

        successful_count = 0
        failed_count = 0
        duplicate_count = 0
        total_leads = len(raw_leads)

        # Set total listings found if not already set or update it
        if not batch.total_listings_found or batch.total_listings_found < total_leads:
            batch.total_listings_found = total_leads
            session.add(batch)
            session.commit()

        results = []

        for idx, lead_item in enumerate(raw_leads):
            # Prepare standard lead structure for ingest_lead
            contacts = []
            if lead_item.get("primary_phone"):
                contacts.append({
                    "contact_type": "phone",
                    "contact_value": lead_item["primary_phone"],
                    "sequence_number": 1,
                    "source": "listing"
                })
            if lead_item.get("primary_email"):
                contacts.append({
                    "contact_type": "email",
                    "contact_value": lead_item["primary_email"],
                    "sequence_number": 1,
                    "source": "listing"
                })

            lead_payload = {
                "batch_id": batch_id,
                "source_site": website,
                "business_name": lead_item.get("business_name"),
                "search_query": batch.search_query or "",
                "service_name": lead_item.get("service_name") or lead_item.get("category"),
                "contact_person": lead_item.get("contact_person"),
                "website": lead_item.get("website"),
                "address": lead_item.get("address"),
                "city": lead_item.get("city") or search_loc,
                "state": lead_item.get("state"),
                "country": lead_item.get("country", "India"),
                "postal_code": lead_item.get("postal_code"),
                "category": lead_item.get("category"),
                "listing_url": lead_item.get("listing_url"),
                "collection_mode": batch.collection_mode or "quick",
                "contacts": contacts,
                "rating": lead_item.get("rating"),
                "review_count": lead_item.get("review_count"),
                "business_profile_url": lead_item.get("listing_url")
            }

            try:
                ingest_res = await CollectionPipeline.ingest_lead(lead_payload, session)
                status_val = ingest_res.get("status")
                
                print(f"[DEBUG_AUDIT] Lead ID: '{lead_item.get('business_name')}' | Step 6: Pipeline returned status -> '{status_val}'")

                if status_val == "saved":
                    successful_count += 1
                    print(f"[DEBUG_AUDIT] Lead ID: '{lead_item.get('business_name')}' | Step 7: Batch Counter Increment -> 'successful_count': {successful_count}")
                elif status_val == "duplicate":
                    duplicate_count += 1
                    print(f"[DEBUG_AUDIT] Lead ID: '{lead_item.get('business_name')}' | Step 7: Batch Counter Increment -> 'duplicate_count': {duplicate_count}")
                else:
                    failed_count += 1
                    print(f"[DEBUG_AUDIT] Lead ID: '{lead_item.get('business_name')}' | Step 7: Batch Counter Increment -> 'failed_count': {failed_count} (Reason: {ingest_res.get('message')})")
                    CollectionErrorTracker.log_error(
                        session=session,
                        batch_id=batch_id,
                        website=website,
                        error_category="Data Validation Error",
                        error_message=ingest_res.get("message", "Unknown pipeline error"),
                        current_url=lead_item.get("listing_url")
                    )

                results.append(ingest_res)

            except Exception as e:
                session.rollback() # Clear any failed SQL transaction states
                failed_count += 1
                print(f"[DEBUG_AUDIT] Lead ID: '{lead_item.get('business_name')}' | Step 7: Batch Counter Increment -> 'failed_count': {failed_count} (Pipeline Exception: {str(e)})")
                CollectionErrorTracker.log_error(
                    session=session,
                    batch_id=batch_id,
                    website=website,
                    error_category="System Ingestion Error",
                    error_message=f"Pipeline exception: {str(e)}",
                    current_url=lead_item.get("listing_url")
                )
                results.append({
                    "status": "error",
                    "message": str(e),
                    "lead_id": None
                })

            # Update progress engine after each processed lead
            CollectionProgressEngine.update_progress(
                session=session,
                batch_id=batch_id,
                listings_processed=idx + 1,
                failed_listings=failed_count,
                skipped_listings=duplicate_count,
                duplicate_leads=duplicate_count,
                successful_leads=successful_count,
                current_listing=idx + 1,
                current_company_name=lead_item.get("business_name"),
                current_stage="ingesting"
            )

        # Broadcast final capsule/statistics updates
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "CAPSULE_UPDATED",
            "website": website,
            "timestamp": datetime.utcnow().isoformat()
        })
        SyncBroadcaster.broadcast("STATE_UPDATED", {
            "action": "STATISTICS_UPDATED",
            "timestamp": datetime.utcnow().isoformat()
        })

        print(f"[DEBUG_AUDIT] Finished Ingestion Batch: '{batch_id}' | Step 8: Final Session Statistics -> Total: {total_leads}, Successful: {successful_count}, Failed: {failed_count}, Duplicates: {duplicate_count}")

        return {
            "status": "success",
            "total_processed": total_leads,
            "successful": successful_count,
            "failed": failed_count,
            "duplicates": duplicate_count,
            "results": results
        }
