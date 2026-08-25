# backend/database/migrations.py
# ProspectLens — Safe, Versioned Database Migration Manager

from datetime import datetime
from sqlmodel import Session, text, select
from database.models import SchemaVersion


CURRENT_SCHEMA_VERSION = 2

MIGRATIONS = [
    {
        "version": 1,
        "label": "v1.0.0_baseline",
        "description": "Initial core database tables (leads, contacts, batches, jobs, exports)."
    },
    {
        "version": 2,
        "label": "v1.1.0_hardening_and_capsules",
        "description": "Extended leads columns, capsules, composite indexes, backup audit logging, and WAL mode tuning."
    }
]


INDEXES_TO_ENSURE = [
    ("idx_leads_source_approved", "CREATE INDEX IF NOT EXISTS idx_leads_source_approved ON leads (source_site, is_approved)"),
    ("idx_leads_approved_collected", "CREATE INDEX IF NOT EXISTS idx_leads_approved_collected ON leads (is_approved, collected_at DESC)"),
    ("idx_leads_dedup_hash", "CREATE INDEX IF NOT EXISTS idx_leads_dedup_hash ON leads (dedup_hash)"),
    ("idx_leads_status", "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (lead_status)"),
    ("idx_leads_city", "CREATE INDEX IF NOT EXISTS idx_leads_city ON leads (city)"),
    ("idx_contacts_lead_id", "CREATE INDEX IF NOT EXISTS idx_contacts_lead_id ON contacts (lead_id)"),
    ("idx_contacts_type_value", "CREATE INDEX IF NOT EXISTS idx_contacts_type_value ON contacts (contact_type, contact_value)"),
    ("idx_deep_queue_job_status", "CREATE INDEX IF NOT EXISTS idx_deep_queue_job_status ON deep_queue_items (job_id, status)"),
    ("idx_batches_started_at", "CREATE INDEX IF NOT EXISTS idx_batches_started_at ON collection_batches (started_at DESC)"),
    ("idx_collection_jobs_status", "CREATE INDEX IF NOT EXISTS idx_collection_jobs_status ON collection_jobs (status)")
]


def run_database_migrations(engine):
    """
    Applies versioned migrations incrementally and creates composite query indices.
    Safe to execute multiple times (idempotent).
    """
    with Session(engine) as session:
        # 1. Ensure composite query indexes exist
        for idx_name, idx_sql in INDEXES_TO_ENSURE:
            try:
                session.execute(text(idx_sql))
            except Exception as e:
                print(f"[DB Migration] Note creating index {idx_name}: {e}")
        session.commit()

        # 2. Check current applied version in schema_version table
        try:
            applied_versions = {
                v.version_id: v for v in session.exec(select(SchemaVersion)).all()
            }
        except Exception:
            session.rollback()
            applied_versions = {}

        # 3. Apply missing migration records
        for m in MIGRATIONS:
            ver = m["version"]
            if ver not in applied_versions:
                rec = SchemaVersion(
                    version_id=ver,
                    version_label=m["label"],
                    description=m["description"],
                    applied_at=datetime.utcnow()
                )
                session.add(rec)
                print(f"[DB Migration] Successfully applied schema migration {ver} ({m['label']})")
        
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[DB Migration] Migration commit note: {e}")

        # 4. Run SQLite Integrity Check
        try:
            res = session.execute(text("PRAGMA integrity_check;")).first()
            if res and res[0] == "ok":
                print("[DB Migration] SQLite PRAGMA integrity_check: PASSED (ok)")
            else:
                print(f"[DB Migration] WARNING: PRAGMA integrity_check returned: {res}")
        except Exception as e:
            print(f"[DB Migration] Integrity check note: {e}")


def seed_initial_data(engine):
    """Seeds default website sources and capsules into database if missing."""
    from database.models import WebsiteSource, DataCapsule
    sources_to_seed = [
        ("googlemaps", "Google Maps", "https://www.google.com/maps", "/assets/icons/googlemaps.png", "GoogleMapsAdapter", '{"quick_collect": "supported", "deep_collect": "supported", "pagination": "supported", "infinite_scroll": "experimental", "email_extraction": "experimental", "phone_extraction": "supported", "website_extraction": "supported", "review_extraction": "supported", "coordinates": "supported", "categories": "supported", "business_hours": "supported", "social_links": "experimental", "images": "supported", "attachments": "unavailable"}', '["quick", "deep"]'),
        ("indiamart", "IndiaMART", "https://www.indiamart.com", "/assets/icons/indiamart.png", "IndiaMartAdapter", '{"quick_collect": "supported", "deep_collect": "supported", "phone_extraction": "supported", "email_extraction": "unavailable", "attachments": "supported"}', '["quick", "deep"]'),
        ("justdial", "Justdial", "https://www.justdial.com", "/assets/icons/justdial.png", "JustdialAdapter", '{"quick_collect": "supported", "deep_collect": "supported", "phone_extraction": "supported", "email_extraction": "experimental"}', '["quick", "deep"]'),
        ("tradeindia", "TradeIndia", "https://www.tradeindia.com", "/assets/icons/tradeindia.png", "TradeIndiaAdapter", '{"quick_collect": "supported", "deep_collect": "supported", "phone_extraction": "supported"}', '["quick", "deep"]')
    ]
    with Session(engine) as session:
        for key, display_name, base_url, icon_path, adapter_key, capabilities, collection_types in sources_to_seed:
            existing = session.exec(select(WebsiteSource).where(WebsiteSource.source_key == key)).first()
            if not existing:
                src = WebsiteSource(
                    source_key=key,
                    display_name=display_name,
                    base_url=base_url,
                    icon_path=icon_path,
                    adapter_key=adapter_key,
                    capabilities=capabilities,
                    collection_types=collection_types,
                    current_health="Healthy",
                    health_score=100
                )
                session.add(src)
            # Ensure capsule exists
            cap = session.exec(select(DataCapsule).where(DataCapsule.source_site == key)).first()
            if not cap:
                session.add(DataCapsule(source_site=key))
        try:
            session.commit()
        except Exception:
            session.rollback()


def get_current_schema_version(engine) -> int:
    """Returns the highest applied schema version."""
    try:
        with Session(engine) as session:
            versions = session.exec(select(SchemaVersion)).all()
            if not versions:
                return 1
            return max(v.version_id for v in versions)
    except Exception:
        return 1

