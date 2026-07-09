# backend/services/website_extractor_service.py
# ProspectLens — Website Extraction Service
#
# Step 10: Playwright visits company website URLs, crawls homepage + contact page,
# extracts phone numbers, emails, and social links (LinkedIn, Instagram, WhatsApp).
# Employs Gemini html snippet assist when standard parsing yields zero contacts.

import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from sqlmodel import Session, select

from database.models import Job, Lead, Contact
from services.gemini_service import extract_contacts_from_html


async def run_website_extractor(worker: Any, job: Job, session: Session):
    """Worker task loop for crawling websites of leads in a batch."""
    # 1. Parse queue state
    queue = []
    if job.queue_state:
        queue = json.loads(job.queue_state)
    else:
        # First run: get all leads in this batch that have a valid website URL
        statement = select(Lead).where(
            (Lead.batch_id == job.batch_id) &
            (Lead.website != None) &
            (Lead.website != "")
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
        print(f"[WebsiteExtractor] Batch {job.batch_id} has no lead websites to extract.")
        return

    # 2. Run Playwright crawler
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        processed_count = job.records_done

        while queue and not worker.paused and not worker.cancelled:
            lead_id = queue[0]
            lead = session.get(Lead, lead_id)

            if lead and lead.website:
                print(f"[WebsiteExtractor] Crawling website for '{lead.business_name}': {lead.website}")
                
                try:
                    # Parse contacts from website
                    contacts = await extract_website_contacts(page, lead.website)
                    
                    # Save results to db
                    sequence = 10  # start from sequence 10 to avoid conflicting with primary directory phones
                    
                    # Phones
                    for phone in contacts.get("phones", []):
                        add_extracted_contact(session, lead.lead_id, "phone", phone, sequence)
                        sequence += 1
                    
                    # Emails
                    for email in contacts.get("emails", []):
                        add_extracted_contact(session, lead.lead_id, "email", email, 1)
                        
                    # WhatsApp
                    for wa in contacts.get("whatsapp", []):
                        add_extracted_contact(session, lead.lead_id, "whatsapp", wa, 1)

                    # Social URLs
                    if contacts.get("linkedin"):
                        add_extracted_contact(session, lead.lead_id, "linkedin", contacts["linkedin"], 1)
                    if contacts.get("instagram"):
                        add_extracted_contact(session, lead.lead_id, "instagram", contacts["instagram"], 1)

                    session.commit()
                except Exception as crawl_err:
                    print(f"[WebsiteExtractor] Failed crawling {lead.website}: {crawl_err}")

            # Pop lead from queue
            queue.pop(0)
            processed_count += 1

            # Update job progress
            job.records_done = processed_count
            job.queue_state = json.dumps(queue)
            job.progress_percentage = round((processed_count / job.records_total) * 100, 1)
            session.add(job)
            session.commit()

            # Small sleep between site visits
            await asyncio.sleep(2.0)

        await context.close()
        await browser.close()


def add_extracted_contact(session: Session, lead_id: str, c_type: str, c_val: str, seq: int):
    """Saves contact record under the given lead."""
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
            source="website"
        )
        session.add(contact)


async def extract_website_contacts(page, start_url: str) -> Dict[str, Any]:
    """
    Crawls start_url (homepage) and contact page links to collect contacts.
    Returns: {"emails": [...], "phones": [...], "whatsapp": [...], "linkedin": ..., "instagram": ...}
    """
    result = {
        "emails": [],
        "phones": [],
        "whatsapp": [],
        "linkedin": None,
        "instagram": None
    }

    # Ensure URL has protocol
    if not start_url.startswith("http"):
        start_url = "http://" + start_url

    try:
        # Load Homepage
        await page.goto(start_url, wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(1500)
        
        home_html = await page.content()
        home_contacts = await parse_html_contacts(home_html)
        merge_contacts(result, home_contacts)

        # Detect contact page link
        contact_page_url = await find_contact_link(page, start_url)
        if contact_page_url and contact_page_url != start_url:
            print(f"[WebsiteExtractor] Loading contact page: {contact_page_url}")
            await page.goto(contact_page_url, wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(1500)
            
            contact_html = await page.content()
            contact_contacts = await parse_html_contacts(contact_html)
            
            # If standard regex finds nothing, ask Gemini for layout help
            if not contact_contacts.get("emails") and not contact_contacts.get("phones"):
                print("[WebsiteExtractor] Standard regex found zero contacts. Calling Gemini Layout Assist...")
                cleaned_text = await page.inner_text("body")
                gemini_contacts = await extract_contacts_from_html(cleaned_text[:12000])
                merge_contacts(result, gemini_contacts)
            else:
                merge_contacts(result, contact_contacts)

    except Exception as e:
        print(f"[WebsiteExtractor] Error loading pages for {start_url}: {e}")

    return result


async def find_contact_link(page, base_url: str) -> Optional[str]:
    """Finds links pointing to Contact, About, or Info pages."""
    try:
        links = await page.query_selector_all("a")
        for link in links:
            text = await link.inner_text()
            href = await link.get_attribute("href")
            
            if href and text:
                text_lower = text.lower()
                href_lower = href.lower()
                
                # Check for contact triggers
                if "contact" in text_lower or "contact" in href_lower or "about" in text_lower or "reach" in text_lower:
                    full_url = urljoin(base_url, href)
                    # Verify we stay on the same domain
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        return full_url
    except:
        pass
    return None


async def parse_html_contacts(html: str) -> Dict[str, Any]:
    """Simple local helper to extract basic contacts from page source using regex."""
    emails = list(set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", html)))
    
    # Raw Indian mobile number extraction
    raw_phones = re.findall(r"\b(?:(?:\+|0{0,2})91[\s\-]*)?[6-9]\d{9}\b", html)
    
    # Standarize numbers using clean helper from gemini_service
    from services.gemini_service import clean_indian_phone
    cleaned_phones = list(set([clean_indian_phone(p) for p in raw_phones]))
    
    linkedin = re.findall(r"href=[\"'](https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-\_]+)[\"']", html)
    instagram = re.findall(r"href=[\"'](https?://(?:www\.)?instagram\.com/[A-Za-z0-9\-\_\.]+)[\"']", html)
    whatsapp = re.findall(r"href=[\"'](https?://api\.whatsapp\.com/send\?phone=\d+|https?://wa\.me/\d+)[\"']", html)

    return {
        "emails": emails,
        "phones": cleaned_phones,
        "whatsapp": whatsapp,
        "linkedin": linkedin[0] if linkedin else None,
        "instagram": instagram[0] if instagram else None
    }


def merge_contacts(target: Dict[str, Any], source: Dict[str, Any]):
    """Merges source contacts lists/urls into target dictionary."""
    target["emails"] = list(set(target["emails"] + source.get("emails", [])))
    target["phones"] = list(set(target["phones"] + source.get("phones", [])))
    target["whatsapp"] = list(set(target["whatsapp"] + source.get("whatsapp", [])))
    
    if source.get("linkedin"):
        target["linkedin"] = source["linkedin"]
    if source.get("instagram"):
        target["instagram"] = source["instagram"]
