# backend/database/models.py
# ProspectLens — All 10 SQLModel Table Definitions
# Phase 1: Tables 1-7 fully active | Tables 8-10 skeleton only

import hashlib
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())


# ==============================================================================
# TABLE 1 — Leads (Master Record)
# Every collected business listing ends up here. Central table of the system.
# ==============================================================================

class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    lead_id:          str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:         str      = Field(foreign_key="collection_batches.batch_id", index=True)
    search_query:     str      = Field(default="")                  # e.g. "Interior Designers Noida"
    source_site:      str      = Field(default="", index=True)      # indiamart / googlemaps / justdial
    business_name:    str      = Field(default="")                  # Required — never null
    service_name:     Optional[str] = Field(default=None)           # Primarily from IndiaMART
    contact_person:   Optional[str] = Field(default=None)           # Owner/manager if available
    website:          Optional[str] = Field(default=None)           # Company website URL
    address:          Optional[str] = Field(default=None)           # Full raw address string
    city:             Optional[str] = Field(default=None)           # Parsed — normalized by Gemini
    state:            Optional[str] = Field(default=None)           # Parsed — normalized by Gemini
    country:          str      = Field(default="India")
    postal_code:      Optional[str] = Field(default=None)           # PIN code
    category:         Optional[str] = Field(default=None)           # Business category tag
    listing_url:      Optional[str] = Field(default=None)           # Directory listing URL
    collection_mode:  str      = Field(default="quick")             # quick / deep
    collection_status: str     = Field(default="success")           # success / partial / failed
    lead_status:      str      = Field(default="new", index=True)   # new / contacted / qualified / closed
    dedup_hash:       str      = Field(default="", index=True)      # SHA-256 fingerprint (unique key)
    collected_at:     datetime = Field(default_factory=datetime.utcnow)
    notes:            Optional[str] = Field(default=None)
    tags:             Optional[str] = Field(default=None)


# ==============================================================================
# TABLE 2 — Contacts
# Multiple contact entries per lead (phones, emails, whatsapp, social links)
# ==============================================================================

class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    contact_id:       str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:          str      = Field(foreign_key="leads.lead_id", index=True)
    contact_type:     str      = Field(default="phone")     # phone / email / whatsapp / linkedin / instagram / facebook
    contact_value:    str      = Field(default="")          # The actual number / email / URL
    sequence_number:  int      = Field(default=1)           # Order among contacts of same type
    source:           str      = Field(default="listing")   # listing / website / extractor


# ==============================================================================
# TABLE 3 — Collection Batches
# One batch = one collection session. Groups all leads from a single run.
# ==============================================================================

class CollectionBatch(SQLModel, table=True):
    __tablename__ = "collection_batches"

    batch_id:           str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_name:         str      = Field(default="")            # Human-readable name
    search_query:       str      = Field(default="")            # The search query used
    source_site:        str      = Field(default="")            # indiamart / googlemaps / justdial
    collection_mode:    str      = Field(default="quick")       # quick / deep
    total_records:      int      = Field(default=0)             # Total listings found on page
    successful_records: int      = Field(default=0)             # Listings successfully saved
    failed_records:     int      = Field(default=0)             # Listings that failed to extract
    created_at:         datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 4 — Jobs
# Tracks Deep Collect and Website Extractor long-running jobs.
# Supports pause/resume via saved progress state.
# ==============================================================================

class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    job_id:              str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:            Optional[str] = Field(default=None, foreign_key="collection_batches.batch_id")
    job_type:            str      = Field(default="deep_collect")   # deep_collect / website_extract
    status:              str      = Field(default="queued", index=True)  # queued / running / paused / completed / failed
    progress_percentage: float    = Field(default=0.0)              # 0.0 to 100.0
    records_done:        int      = Field(default=0)
    records_total:       int      = Field(default=0)
    gemini_profile_id:   Optional[str] = Field(default=None)        # ID of Gemini behavior profile used
    queue_state:         Optional[str] = Field(default=None)        # JSON string — saved queue for resume
    created_at:          datetime = Field(default_factory=datetime.utcnow)
    updated_at:          datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 5 — Export History  (Phase 1 Active)
# Every export generated is logged here — file path, format, record count.
# ==============================================================================

class ExportHistory(SQLModel, table=True):
    __tablename__ = "export_history"

    export_id:      str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:       Optional[str] = Field(default=None, foreign_key="collection_batches.batch_id")
    export_format:  str      = Field(default="xlsx")    # csv / xlsx
    file_path:      str      = Field(default="")        # Full path to the generated file
    record_count:   int      = Field(default=0)         # Number of leads in this export
    file_size_kb:   Optional[float] = Field(default=None)
    exported_at:    datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 6 — Visited URLs  (Phase 1 Active)
# SHA-256 hashes of every URL visited in Deep Collect.
# Prevents revisiting the same listing URL across sessions.
# ==============================================================================

class VisitedURL(SQLModel, table=True):
    __tablename__ = "visited_urls"

    url_id:       str      = Field(default_factory=generate_uuid, primary_key=True)
    url_hash:     str      = Field(default="", index=True)  # SHA-256 of the URL
    original_url: str      = Field(default="")              # Full URL (stored for debugging)
    source_site:  str      = Field(default="")              # Which platform
    visited_at:   datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 7 — Source Records  (Phase 1 Active)
# Cross-platform tracking — same business found on multiple platforms.
# Links IndiaMART + Google Maps + Justdial records of the same company.
# ==============================================================================

class SourceRecord(SQLModel, table=True):
    __tablename__ = "source_records"

    source_id:    str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:      str      = Field(foreign_key="leads.lead_id", index=True)
    source_site:  str      = Field(default="")          # Which platform this record came from
    listing_url:  Optional[str] = Field(default=None)   # Platform-specific listing URL
    raw_data:     Optional[str] = Field(default=None)   # JSON string of original scraped data
    created_at:   datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 8 — Notes  (Phase 1: Schema only | Phase 2: UI)
# Written notes attachable to any lead. Schema defined now to avoid migration later.
# ==============================================================================

class Note(SQLModel, table=True):
    __tablename__ = "notes"

    note_id:    str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:    str      = Field(foreign_key="leads.lead_id", index=True)
    note_text:  str      = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 9 — Users  (Phase 1: Skeleton | Phase 2: Active)
# Multi-user support. Defined now so UUID foreign keys work without migration.
# ==============================================================================

class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id:    str      = Field(default_factory=generate_uuid, primary_key=True)
    username:   str      = Field(default="", index=True)
    email:      Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 10a — Tags  (Phase 1: Skeleton | Phase 2: Active)
# Tag definitions. e.g. "Hot Lead", "Contacted", "LSFX", "Boostlane"
# ==============================================================================

class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    tag_id:   str = Field(default_factory=generate_uuid, primary_key=True)
    tag_name: str = Field(default="", index=True)
    color:    str = Field(default="#354024")    # Default to ProspectLens highlight color


# ==============================================================================
# TABLE 10b — Lead Tags  (Phase 1: Skeleton | Phase 2: Active)
# Join table — many leads can have many tags.
# ==============================================================================

class LeadTag(SQLModel, table=True):
    __tablename__ = "lead_tags"

    lead_tag_id: str = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:     str = Field(foreign_key="leads.lead_id", index=True)
    tag_id:      str = Field(foreign_key="tags.tag_id", index=True)