# backend/services/deep_collect_service.py
# ProspectLens — Asynchronous Playwright Scrapers for Deep Collection
#
# Steps 7, 8, and 9: IndiaMART, Google Maps, and Justdial detail page adapters.
# Implements Playwright headless browser extraction, Gemini behavior delays,
# and pause/resume logic using serialized database queues.

import os
import asyncio
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright
from sqlmodel import Session, select

from database.db import get_session
from database.models import Job, Lead, Contact, VisitedURL, SourceRecord
from services.gemini_service import get_session_behavior_profile, normalize_lead_data
from services.deduplication import compute_url_hash

# Global registry of active background asyncio Tasks: job_id -> asyncio.Task
ACTIVE_TASKS: Dict[str, asyncio.Task] = {}


class JobWorker:
    """Worker class representing a single running Deep Collect / Extractor session."""
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.paused = False
        self.cancelled = False

    async def run(self):
        """Asynchronously executes the job work loop."""
        db_gen = get_session()
        session: Session = next(db_gen)

        job = session.get(Job, self.job_id)
        if not job:
            print(f"[JobWorker] Job {self.job_id} not found in database.")
            return

        job.status = "running"
        job.updated_at = datetime.utcnow()
        session.add(job)
        session.commit()

        try:
            if job.job_type == "deep_collect":
                await self.run_deep_collect(job, session)
            elif job.job_type == "website_extract":
                from services.website_extractor_service import run_website_extractor
                await run_website_extractor(self, job, session)
        except asyncio.CancelledError:
            print(f"[JobWorker] Job {self.job_id} cancelled.")
            job.status = "paused" if self.paused else "failed"
            session.add(job)
            session.commit()
        except Exception as e:
            print(f"[JobWorker] Job {self.job_id} failed with error: {e}")
            job.status = "failed"
            session.add(job)
            session.commit()
        finally:
            if self.job_id in ACTIVE_TASKS:
                del ACTIVE_TASKS[self.job_id]

    async def run_deep_collect(self, job: Job, session: Session):
        """Executes detail page scraping using Playwright."""
        # 1. Parse queue state
        queue = []
        if job.queue_state:
            queue = json.loads(job.queue_state)
        else:
            # First run: get all leads for this batch that are queued/partial in deep collection
            statement = select(Lead).where(
                (Lead.batch_id == job.batch_id) &
                (Lead.collection_mode == "deep") &
                (Lead.collection_status != "success")
            )
            leads = session.exec(statement).all()
            queue = [lead.lead_id for lead in leads]
            job.records_total = len(queue)
            job.queue_state = json.dumps(queue)
            session.add(job)
            session.commit()

        if not queue:
            job.status = "completed"
            job.progress_percentage = 100.0
            session.add(job)
            session.commit()
            print(f"[JobWorker] Deep collect batch {job.batch_id} has no leads to process.")
            return

        # 2. Get Gemini Behavior Profile for human-like delays
        first_lead = session.get(Lead, queue[0])
        site = first_lead.source_site if first_lead else "indiamart"
        profile = await get_session_behavior_profile(len(queue), site)
        
        delays = profile.get("delays", [5.0] * len(queue))
        heavy_pause_indices = profile.get("heavy_pause_indices", [])
        heavy_pause_durations = profile.get("heavy_pause_durations", [])
        scroll_hesitations = profile.get("scroll_hesitations", [1.0] * len(queue))

        # 3. Start Playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Standard desktop user agent to avoid bot detection
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            processed_count = job.records_done
            
            while queue and not self.paused and not self.cancelled:
                lead_id = queue[0]
                lead = session.get(Lead, lead_id)

                if lead and lead.listing_url:
                    print(f"[JobWorker] Deep collecting lead '{lead.business_name}': {lead.listing_url}")
                    
                    # Deduplicate by URL hash to avoid double scraping
                    url_hash = compute_url_hash(lead.listing_url)
                    existing_visited = session.exec(
                        select(VisitedURL).where(VisitedURL.url_hash == url_hash)
                    ).first()

                    if existing_visited:
                        print(f"[JobWorker] URL already visited. Skipping: {lead.listing_url}")
                        lead.collection_status = "success"
                        session.add(lead)
                    else:
                        try:
                            # Apply scroll hesitation delay
                            hesitation = scroll_hesitations[processed_count % len(scroll_hesitations)]
                            await asyncio.sleep(hesitation)

                            # Visit and scrape
                            scraped_data = await self.scrape_detail_page(page, lead.listing_url, lead.source_site)
                            
                            # Standardize raw address details
                            normalized = await normalize_lead_data({
                                "business_name": lead.business_name,
                                "address": scraped_data.get("address") or lead.address,
                                "phone": scraped_data.get("phone"),
                                "city": lead.city,
                                "state": lead.state,
                                "postal_code": scraped_data.get("postal_code") or lead.postal_code,
                                "contact_person": scraped_data.get("contact_person") or lead.contact_person,
                                "category": scraped_data.get("category") or lead.category
                            })

                            # Update Lead record fields
                            lead.address = normalized.get("address")
                            lead.city = normalized.get("city")
                            lead.state = normalized.get("state")
                            lead.postal_code = normalized.get("postal_code")
                            lead.contact_person = normalized.get("contact_person")
                            lead.category = normalized.get("category")
                            lead.website = scraped_data.get("website") or lead.website
                            lead.collection_status = "success"
                            session.add(lead)

                            # Save scraped phone/email contacts
                            sequence = 1
                            if normalized.get("phone"):
                                self.add_or_update_contact(session, lead.lead_id, "phone", normalized["phone"], sequence)
                                sequence += 1
                            
                            for alt_phone in scraped_data.get("alternate_phones", []):
                                self.add_or_update_contact(session, lead.lead_id, "phone", alt_phone, sequence)
                                sequence += 1
                                
                            if scraped_data.get("email"):
                                self.add_or_update_contact(session, lead.lead_id, "email", scraped_data["email"], 1)

                            # Save Visited URL record
                            visited = VisitedURL(
                                url_hash=url_hash,
                                original_url=lead.listing_url,
                                source_site=lead.source_site
                            )
                            session.add(visited)

                            # Save raw source data
                            source_record = session.exec(
                                select(SourceRecord).where(
                                    (SourceRecord.lead_id == lead.lead_id) &
                                    (SourceRecord.source_site == lead.source_site)
                                )
                            ).first()
                            if source_record:
                                source_record.raw_data = json.dumps(scraped_data)
                                session.add(source_record)

                        except Exception as scrape_err:
                            print(f"[JobWorker] Failed scraping {lead.listing_url}: {scrape_err}")
                            lead.collection_status = "failed"
                            session.add(lead)

                    # Commit current lead transaction
                    session.commit()

                # Pop lead from queue
                queue.pop(0)
                processed_count += 1

                # Update job progress
                job.records_done = processed_count
                job.queue_state = json.dumps(queue)
                job.progress_percentage = round((processed_count / job.records_total) * 100, 1)
                job.updated_at = datetime.utcnow()
                session.add(job)
                session.commit()

                # Check if session needs a heavy pause break
                if processed_count in heavy_pause_indices:
                    pause_idx = heavy_pause_indices.index(processed_count)
                    pause_duration = heavy_pause_durations[pause_idx] if pause_idx < len(heavy_pause_durations) else 15.0
                    print(f"[JobWorker] Taking heavy pause break for {pause_duration}s...")
                    await asyncio.sleep(pause_duration)
                elif queue:
                    # Normal random crawl delay
                    delay = delays[processed_count % len(delays)]
                    await asyncio.sleep(delay)

            # Close browser context
            await context.close()
            await browser.close()

        # Update final job completion status
        if not queue:
            job.status = "completed"
            job.progress_percentage = 100.0
        elif self.paused:
            job.status = "paused"
        elif self.cancelled:
            job.status = "failed"
            
        session.add(job)
        session.commit()
        print(f"[JobWorker] Job {self.job_id} finished. Status: {job.status}")

    def add_or_update_contact(self, session: Session, lead_id: str, c_type: str, c_val: str, seq: int):
        """Helper to save/update lead contact records in db."""
        existing = session.exec(
            select(Contact).where(
                (Contact.lead_id == lead_id) &
                (Contact.contact_type == c_type) &
                (Contact.contact_value == c_val)
            )
        ).first()
        if not existing:
            contact = Contact(
                lead_id=lead_id,
                contact_type=c_type,
                contact_value=c_val,
                sequence_number=seq,
                source="extractor"
            )
            session.add(contact)

    async def scrape_detail_page(self, page, url: str, source: str) -> Dict[str, Any]:
        """Loads url using Playwright and extracts text elements based on site patterns."""
        result = {
            "address": None,
            "phone": None,
            "alternate_phones": [],
            "email": None,
            "website": None,
            "contact_person": None,
            "category": None
        }

        try:
            # Visit listing page with 15s timeout to handle slow pages gracefully
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            
            body_text = await page.inner_text("body")
            
            # --- Platform-specific CSS parsing adapters ---
            if source == "indiamart":
                # Scrape IndiaMART detail page
                result["address"] = await self.safe_text(page, ".addDetail, [class*='address']")
                result["phone"] = await self.safe_text(page, ".call-supp-btn, [class*='phone'], [class*='mobile']")
                result["website"] = await self.safe_attr(page, "a[href*='http']:not([href*='indiamart'])", "href")
                result["contact_person"] = await self.safe_text(page, ".supplier-name, .contact-person")
                result["category"] = await self.safe_text(page, ".breadcrumb, .keyword")
                
            elif source == "googlemaps":
                # Scrape Google Maps place details
                result["address"] = await self.safe_text(page, "[data-item-id*='address'] .Io6YTe")
                result["phone"] = await self.safe_text(page, "[data-item-id*='phone'] .Io6YTe")
                result["website"] = await self.safe_text(page, "[data-item-id='authority'] .Io6YTe")
                
            elif source == "justdial":
                # Scrape Justdial details
                result["address"] = await self.safe_text(page, ".store-address, [class*='address']")
                result["phone"] = await self.safe_text(page, ".contact-info, [class*='phone']")
                result["website"] = await self.safe_attr(page, ".website a, [class*='website'] a", "href")
                result["category"] = await self.safe_text(page, ".category-name, [class*='category']")

            # --- Heuristic Fallback Extraction via Regex on body text ---
            # 1. Emails
            emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", body_text)
            if emails:
                result["email"] = emails[0]

            # 2. GSTIN matching
            gstin_match = re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b", body_text)
            if gstin_match:
                result["gstin"] = gstin_match.group(0)

            # 3. Alternate phone numbers
            phones = re.findall(r"\b(?:(?:\+|0{0,2})91[\s\-]*)?[6-9]\d{9}\b", body_text)
            unique_phones = list(set(phones))
            if unique_phones:
                if not result["phone"]:
                    result["phone"] = unique_phones[0]
                result["alternate_phones"] = unique_phones[1:5]

        except Exception as e:
            print(f"[JobWorker] Scrape failed for {url}: {e}")

        return result

    async def safe_text(self, page, selector: str) -> Optional[str]:
        """Tries to get inner text of selector, returns None on failure."""
        try:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                return text.strip()
        except:
            pass
        return None

    async def safe_attr(self, page, selector: str, attr: str) -> Optional[str]:
        """Tries to get attribute value of selector, returns None on failure."""
        try:
            el = await page.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return val.strip() if val else None
        except:
            pass
        return None


# ==============================================================================
# CONTROLLER ENDPOINTS HOOKS
# ==============================================================================

def start_background_job(job_id: str):
    """Creates asyncio task in event loop for job execution."""
    worker = JobWorker(job_id)
    task = asyncio.create_task(worker.run())
    ACTIVE_TASKS[job_id] = task
    return worker


def pause_background_job(job_id: str, session: Session) -> bool:
    """Cancels running job task, setting state to paused."""
    if job_id in ACTIVE_TASKS:
        task = ACTIVE_TASKS[job_id]
        task.cancel()
        
        job = session.get(Job, job_id)
        if job:
            job.status = "paused"
            session.add(job)
            session.commit()
        return True
    return False


def cancel_background_job(job_id: str, session: Session) -> bool:
    """Cancels running job task and sets status to failed."""
    if job_id in ACTIVE_TASKS:
        task = ACTIVE_TASKS[job_id]
        task.cancel()
        
        job = session.get(Job, job_id)
        if job:
            job.status = "failed"
            session.add(job)
            session.commit()
        return True
    return False
