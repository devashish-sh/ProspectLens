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
    is_approved:      bool     = Field(default=False, index=True)   # review flow state
    status:           str      = Field(default="New", index=True)   # New / Incomplete / Enriched / Reviewed / Approved / Moved to Main Leads / Rejected / Duplicate / Needs Review
    
    # Contact Information Cache
    primary_email:    Optional[str] = Field(default=None)
    primary_phone:    Optional[str] = Field(default=None)

    # Business Information
    review_count:     Optional[int] = Field(default=None)
    rating:           Optional[float] = Field(default=None)
    business_profile_url: Optional[str] = Field(default=None)

    # Collection Information
    directory_search_url: Optional[str] = Field(default=None)

    # Workflow & Metadata
    completeness_score: float  = Field(default=0.0)
    created_at:       datetime = Field(default_factory=datetime.utcnow)
    updated_at:       datetime = Field(default_factory=datetime.utcnow)
    
    # New fields for Sprint 4.3 Quick Collect Expansion
    search_keyword:   Optional[str] = Field(default=None)
    search_location:  Optional[str] = Field(default=None)
    collection_date:  Optional[str] = Field(default=None)
    collection_time:  Optional[str] = Field(default=None)
    website_domain:   Optional[str] = Field(default=None)
    open_status:      Optional[str] = Field(default=None)
    displayed_price:  Optional[str] = Field(default=None)
    price_currency:   Optional[str] = Field(default=None)
    price_type:       Optional[str] = Field(default=None)
    price_level:      Optional[str] = Field(default=None)
    flexible_metadata: Optional[str] = Field(default=None)

    # Sprint 4.4 Universal Schema additions
    sub_category:     Optional[str] = Field(default=None)
    source_business_id: Optional[str] = Field(default=None)
    collector_version: Optional[str] = Field(default="1.0.0")
    secondary_phones:  Optional[str] = Field(default=None)

    # Reserved Fields
    reserved_field_1: Optional[str] = Field(default=None)
    reserved_field_2: Optional[str] = Field(default=None)
    reserved_field_3: Optional[str] = Field(default=None)

    dedup_hash:       str      = Field(default="", index=True)      # SHA-256 fingerprint (unique key)
    collected_at:     datetime = Field(default_factory=datetime.utcnow)
    notes:            Optional[str] = Field(default=None)
    tags:             Optional[str] = Field(default=None)
    version:          int      = Field(default=1)


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
    
    # Collection Session Fields
    started_at:         datetime = Field(default_factory=datetime.utcnow)
    completed_at:       Optional[datetime] = Field(default=None)
    total_listings_found: int      = Field(default=0)
    total_leads_stored: int      = Field(default=0)
    status:             str      = Field(default="running", index=True) # running / completed / failed / paused / resumed / cancelled
    search_url:         Optional[str] = Field(default=None)
    
    # Real-Time Progress Metrics
    last_updated_at:    datetime = Field(default_factory=datetime.utcnow)
    listings_processed: int      = Field(default=0)
    listings_remaining: int      = Field(default=0)
    failed_listings:     int      = Field(default=0)
    skipped_listings:    int      = Field(default=0)
    enriched_leads:      int      = Field(default=0)
    duplicate_leads:     int      = Field(default=0)
    
    # Processing state
    current_listing:     int      = Field(default=0)
    current_company_name: Optional[str] = Field(default=None)
    current_page:        int      = Field(default=1)
    current_stage:       Optional[str] = Field(default=None) # Scanning Listings, Opening Listing, Extracting Data, Saving Lead, Calculating Completeness, Updating Capsule
    
    # Calculations
    progress_percentage: float    = Field(default=0.0)
    estimated_time_remaining: float = Field(default=0.0) # In seconds
    listings_per_second: float    = Field(default=0.0)
    avg_processing_time: float    = Field(default=0.0) # In seconds per listing
    avg_listing_time:    float    = Field(default=0.0) # In seconds per listing
    
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
# TABLE 4.5 — Collection Jobs (Sprint 4.5)
# Tracks Quick Collect & Deep Collect managed scraper lifecycles.
# ==============================================================================

class CollectionJob(SQLModel, table=True):
    __tablename__ = "collection_jobs"

    job_id:              str      = Field(primary_key=True)
    status:              str      = Field(default="queued", index=True)  # queued / starting / running / paused / completed / failed / cancelled
    source:              str      = Field(default="")                   # googlemaps / indiamart / justdial
    mode:                str      = Field(default="quick")              # quick / deep
    search_keyword:      Optional[str] = Field(default=None)
    search_query:        Optional[str] = Field(default=None)
    search_location:     Optional[str] = Field(default=None)
    search_url:          Optional[str] = Field(default=None)
    start_time:          Optional[datetime] = Field(default=None)
    end_time:            Optional[datetime] = Field(default=None)
    duration:            Optional[float] = Field(default=None)         # duration in seconds
    saved:               int      = Field(default=0)
    duplicates:          int      = Field(default=0)
    errors:              int      = Field(default=0)
    skipped:             int      = Field(default=0)
    total_seen:          int      = Field(default=0)
    current_listing:     Optional[str] = Field(default=None)
    progress_percentage: float    = Field(default=0.0)
    metadata_json:       Optional[str] = Field(default=None)        # holds JSON options / retry state
    created_at:          datetime = Field(default_factory=datetime.utcnow)
    updated_at:          datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 4.6 — Deep Queue Items (Sprint 5)
# Tracks sequential listing enrichment queues in Deep Collect.
# ==============================================================================

class DeepQueueItem(SQLModel, table=True):
    __tablename__ = "deep_queue_items"

    queue_item_id:   str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:         str      = Field(index=True)
    job_id:          str      = Field(index=True)
    business_name:   str      = Field(default="")
    listing_url:     str      = Field(default="")
    queue_position:  int      = Field(default=0)
    status:          str      = Field(default="pending", index=True) # pending / running / completed / failed / skipped / retrying
    retry_count:     int      = Field(default=0)
    started_at:      Optional[datetime] = Field(default=None)
    completed_at:    Optional[datetime] = Field(default=None)
    created_at:      datetime = Field(default_factory=datetime.utcnow)
    updated_at:      datetime = Field(default_factory=datetime.utcnow)


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


# ==============================================================================
# TABLE 11 — Website Sources
# Explicit metadata and statuses of supported source directories.
# ==============================================================================

class WebsiteSource(SQLModel, table=True):
    __tablename__ = "website_sources"

    source_id:    str      = Field(default_factory=generate_uuid, primary_key=True)
    source_key:   str      = Field(default="", index=True, unique=True) # e.g. "googlemaps"
    display_name: str      = Field(default="")                          # e.g. "Google Maps"
    base_url:     Optional[str] = Field(default=None)
    is_active:    bool     = Field(default=True)
    icon_path:    Optional[str] = Field(default=None)
    adapter_key:  Optional[str] = Field(default=None)
    capabilities: Optional[str] = Field(default=None)                  # Stored as JSON string dictionary
    collection_types: Optional[str] = Field(default=None)              # Stored as JSON string list
    
    # Config limits per website source
    max_rpm:             int      = Field(default=60)
    recommended_delay:   float    = Field(default=1.0)
    retry_count:         int      = Field(default=3)
    timeout:             int      = Field(default=30)
    concurrent_limit:    int      = Field(default=5)
    
    # Health monitoring status fields
    current_health:       str      = Field(default="Healthy", index=True) # Healthy, Limited, Rate Limited, Captcha Detected, Blocked, Maintenance, Offline, Disabled, Unknown
    last_health_check_at: Optional[datetime] = Field(default=None)
    last_success_at:      Optional[datetime] = Field(default=None)
    last_failure_at:      Optional[datetime] = Field(default=None)
    failure_count:        int      = Field(default=0)
    success_count:        int      = Field(default=0)
    avg_response_time:    float    = Field(default=0.0)
    consecutive_failures: int      = Field(default=0)
    last_failure_reason:  Optional[str] = Field(default=None)
    health_score:         int      = Field(default=100)
    
    created_at:   datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 12 — Data Capsules
# Website-specific review capsules/storage rooms metadata.
# ==============================================================================

class DataCapsule(SQLModel, table=True):
    __tablename__ = "data_capsules"

    capsule_id:        str      = Field(default_factory=generate_uuid, primary_key=True)
    source_site:       str      = Field(default="", index=True, unique=True) # links to source_key
    is_locked:         bool     = Field(default=False)
    last_sync_at:      Optional[datetime] = Field(default=None)
    total_leads_count: int      = Field(default=0)


# ==============================================================================
# TABLE 13 — Search History
# Comprehensive log of all directory searches made by the user.
# ==============================================================================

class SearchHistory(SQLModel, table=True):
    __tablename__ = "search_history"

    search_id:           str      = Field(default_factory=generate_uuid, primary_key=True)
    search_query:        str      = Field(default="", index=True)
    source_site:         str      = Field(default="", index=True)
    total_results_found: int      = Field(default=0)
    searched_at:         datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 14 — Lead History (Workflow Audit Logs)
# Keeps track of all lead actions (collections, edits, status updates, approvals).
# ==============================================================================

class LeadHistory(SQLModel, table=True):
    __tablename__ = "lead_history"

    history_id:   str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:      str      = Field(foreign_key="leads.lead_id", index=True)
    action_type:  str      = Field(default="collected", index=True) # collected / edited / status_changed / approved / rejected
    old_value:    Optional[str] = Field(default=None)
    new_value:    Optional[str] = Field(default=None)
    changed_by:   Optional[str] = Field(default="system")
    created_at:   datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 15 — Lead Version History
# Tracks every version iteration of a lead with modified fields list.
# ==============================================================================

class LeadVersionHistory(SQLModel, table=True):
    __tablename__ = "lead_version_history"

    version_history_id: str      = Field(default_factory=generate_uuid, primary_key=True)
    lead_id:            str      = Field(foreign_key="leads.lead_id", index=True)
    previous_version:   int      = Field(default=1)
    new_version:        int      = Field(default=1)
    action_type:        str      = Field(default="edited") # created / edited / enriched / status_changed
    modified_fields:    Optional[str] = Field(default=None) # JSON string listing modified fields
    created_at:         datetime = Field(default_factory=datetime.utcnow)


# ==============================================================================
# TABLE 16 — Collection Errors
# Tracks all scraper, network, validation, and database errors during execution.
# ==============================================================================

class CollectionError(SQLModel, table=True):
    __tablename__ = "collection_errors"

    error_id:            str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:            str      = Field(foreign_key="collection_batches.batch_id", index=True) # Session ID
    lead_id:             Optional[str] = Field(default=None, foreign_key="leads.lead_id", index=True, nullable=True)
    website:             str      = Field(default="", index=True) # Website Source
    collection_mode:     str      = Field(default="quick", index=True) # Collection Type
    collection_stage:    str      = Field(default="") # Collection Stage
    timestamp:           datetime = Field(default_factory=datetime.utcnow, index=True)
    severity:            str      = Field(default="Error", index=True) # Info, Warning, Error, Critical, Fatal
    error_category:      str      = Field(default="Unknown Error", index=True)
    error_message:       str      = Field(default="")
    technical_details:   Optional[str] = Field(default=None)
    stack_trace:         Optional[str] = Field(default=None)
    current_url:         Optional[str] = Field(default=None)
    listing_url:         Optional[str] = Field(default=None)
    search_url:          Optional[str] = Field(default=None)
    page_number:         int      = Field(default=1)
    listing_index:       int      = Field(default=0)
    browser_info:        Optional[str] = Field(default=None) # JSON string
    extension_version:   Optional[str] = Field(default=None)
    backend_version:     Optional[str] = Field(default=None)
    
    # Recovery Fields
    retry_recommended:   bool     = Field(default=False)
    recovery_status:     str      = Field(default="pending") # pending / retried / resolved / failed
    recovery_notes:      Optional[str] = Field(default=None)
    max_retry_count:     int      = Field(default=3)
    current_retry_count: int      = Field(default=0)
    recovery_strategy:   Optional[str] = Field(default=None)


# ==============================================================================
# TABLE 17 — Search Context & Metadata
# Permanent search parameters, result telemetry, and system execution contexts.
# ==============================================================================

class SearchContext(SQLModel, table=True):
    __tablename__ = "search_contexts"

    search_id:           str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:            str      = Field(foreign_key="collection_batches.batch_id", index=True, unique=True)
    website:             str      = Field(default="", index=True)
    search_keyword:      str      = Field(default="", index=True)
    search_category:     Optional[str] = Field(default=None)
    search_location:     Optional[str] = Field(default=None, index=True)
    original_search_url: Optional[str] = Field(default=None)
    applied_filters:     Optional[str] = Field(default=None) # JSON string
    sorting_method:      Optional[str] = Field(default=None)
    search_timestamp:    datetime = Field(default_factory=datetime.utcnow, index=True)
    search_duration:     float    = Field(default=0.0) # in seconds
    search_status:       str      = Field(default="pending", index=True) # pending / success / failed / cancelled
    
    # Search Configurations
    collection_mode:     str      = Field(default="quick", index=True) # quick / deep
    max_listings:        int      = Field(default=1000)
    max_pages:           int      = Field(default=100)
    delay_between_reqs:  float    = Field(default=1.0)
    concurrency_limit:   int      = Field(default=5)
    retry_policy:        Optional[str] = Field(default=None)
    timeout:             int      = Field(default=30)
    duplicate_strategy:  str      = Field(default="merge")
    
    # Search Result Metadata (copies / snapshots for historic query performance)
    listings_found:      int      = Field(default=0)
    listings_processed:  int      = Field(default=0)
    successful_leads:    int      = Field(default=0)
    failed_leads:        int      = Field(default=0)
    skipped_leads:       int      = Field(default=0)
    duplicate_leads:     int      = Field(default=0)
    approved_leads:      int      = Field(default=0)
    rejected_leads:      int      = Field(default=0)
    avg_completeness:    float    = Field(default=0.0)
    avg_speed:           float    = Field(default=0.0)
    
    # Website Context versions
    website_version:     Optional[str] = Field(default=None)
    layout_version:      Optional[str] = Field(default=None)
    adapter_version:     Optional[str] = Field(default="1.0.0")
    rules_version:       Optional[str] = Field(default="1.0.0")
    extension_version:   Optional[str] = Field(default=None)
    backend_version:     Optional[str] = Field(default="1.0.0")
    
    # Execution Context
    started_by:          str      = Field(default="manual") # manual / scheduled / api / resume
    
    # Audit info
    created_at:          datetime = Field(default_factory=datetime.utcnow)
    updated_at:          datetime = Field(default_factory=datetime.utcnow)
    completed_at:        Optional[datetime] = Field(default=None)
    cancelled_at:        Optional[datetime] = Field(default=None)
    cancellation_reason: Optional[str] = Field(default=None)
    completion_status:   Optional[str] = Field(default=None)


# ==============================================================================
# TABLE 18 — Discovered Listings
# Tracks DOM node mappings, viewport locations, and statuses of discovered listings.
# ==============================================================================

class DiscoveredListing(SQLModel, table=True):
    __tablename__ = "discovered_listings"

    discovered_id:       str      = Field(default_factory=generate_uuid, primary_key=True)
    batch_id:            str      = Field(foreign_key="collection_batches.batch_id", index=True)
    listing_id:          Optional[str] = Field(default=None, index=True)
    temp_internal_id:    str      = Field(default_factory=generate_uuid, index=True)
    website:             str      = Field(default="", index=True)
    dom_reference:       str      = Field(default="", index=True)
    listing_position:    int      = Field(default=0)
    page_position:       int      = Field(default=0)
    visible_state:       bool     = Field(default=True)
    discovery_timestamp: datetime = Field(default_factory=datetime.utcnow)
    discovery_source:    str      = Field(default="Quick Collect")
    collection_status:   str      = Field(default="discovered") # discovered / processing / processed / failed / skipped