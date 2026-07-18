# backend/database/db.py
# ProspectLens — SQLite Connection + Session Management + DB Initialization

from sqlmodel import SQLModel, Session, create_engine, text
from pathlib import Path

# ==============================================================================
# DATABASE FILE LOCATION
# Stored in the backend folder as prospectlens.db
# This single file IS the entire database — back it up to back up all your data
# ==============================================================================

DB_DIR  = Path(__file__).parent.parent          # points to backend/
DB_PATH = DB_DIR / "prospectlens.db"
DB_URL  = f"sqlite:///{DB_PATH}"

# ==============================================================================
# ENGINE
# connect_args check_same_thread=False is required for FastAPI
# because FastAPI handles requests across multiple threads
# ==============================================================================

engine = create_engine(
    DB_URL,
    echo=False,                                  # Set True temporarily if you want to see SQL queries
    connect_args={"check_same_thread": False}
)


# ==============================================================================
# CREATE ALL TABLES
# Call this once on backend startup — safe to call multiple times,
# it will NOT drop existing tables or delete any data
# ==============================================================================

def create_db_and_tables():
    # Import all models here so SQLModel knows about them before creating tables
    from database.models import (
        Lead, Contact, CollectionBatch, Job,
        ExportHistory, VisitedURL, SourceRecord,
        Note, User, Tag, LeadTag,
        WebsiteSource, DataCapsule, SearchHistory, LeadHistory
    )
    SQLModel.metadata.create_all(engine)

    # Run automatic SQLite migration to add new columns to website_sources if they don't exist
    sources_new_columns = [
        ("icon_path", "TEXT"),
        ("adapter_key", "TEXT"),
        ("capabilities", "TEXT"),
        ("collection_types", "TEXT")
    ]
    
    with Session(engine) as session:
        for col_name, col_type in sources_new_columns:
            try:
                session.execute(text(f"SELECT {col_name} FROM website_sources LIMIT 1"))
            except Exception:
                session.rollback()
                try:
                    session.execute(text(f"ALTER TABLE website_sources ADD COLUMN {col_name} {col_type}"))
                    session.commit()
                    print(f"[DB] Migrated: added '{col_name}' column to 'website_sources' table")
                except Exception as e:
                    session.rollback()
                    print(f"[DB] Migration failed for website_sources column {col_name}: {e}")

    # Seed supported website sources and capsules if they don't exist
    with Session(engine) as session:
        sources_to_seed = [
            ("googlemaps", "Google Maps", "https://www.google.com/maps", "/assets/icons/googlemaps.png", "GoogleMapsAdapter", '["leads", "ratings", "reviews"]', '["quick", "deep"]'),
            ("indiamart", "IndiaMART", "https://www.indiamart.com", "/assets/icons/indiamart.png", "IndiaMartAdapter", '["leads", "contacts"]', '["quick"]'),
            ("justdial", "Justdial", "https://www.justdial.com", "/assets/icons/justdial.png", "JustdialAdapter", '["leads", "ratings"]', '["quick", "deep"]'),
            ("tradeindia", "TradeIndia", "https://www.tradeindia.com", "/assets/icons/tradeindia.png", "TradeIndiaAdapter", '["leads"]', '["quick"]')
        ]
        for key, display_name, base_url, icon_path, adapter_key, capabilities, collection_types in sources_to_seed:
            try:
                existing = session.exec(select(WebsiteSource).where(WebsiteSource.source_key == key)).first()
                if not existing:
                    src = WebsiteSource(
                        source_key=key,
                        display_name=display_name,
                        base_url=base_url,
                        icon_path=icon_path,
                        adapter_key=adapter_key,
                        capabilities=capabilities,
                        collection_types=collection_types
                    )
                    session.add(src)
                else:
                    existing.icon_path = icon_path
                    existing.adapter_key = adapter_key
                    existing.capabilities = capabilities
                    existing.collection_types = collection_types
                    session.add(existing)
            except Exception as e:
                print(f"[DB] Seeding website source failed for {key}: {e}")

            try:
                existing_cap = session.exec(select(DataCapsule).where(DataCapsule.source_site == key)).first()
                if not existing_cap:
                    cap = DataCapsule(source_site=key, is_locked=False, total_leads_count=0)
                    session.add(cap)
            except Exception as e:
                print(f"[DB] Seeding capsule failed for {key}: {e}")
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[DB] Seeding transaction commit failed: {e}")
    
    # Run automatic SQLite migration to add new columns to leads if they don't exist
    new_columns = [
        ("is_approved", "BOOLEAN DEFAULT 0"),
        ("status", "TEXT DEFAULT 'New'"),
        ("primary_email", "TEXT"),
        ("primary_phone", "TEXT"),
        ("review_count", "INTEGER"),
        ("rating", "REAL"),
        ("business_profile_url", "TEXT"),
        ("directory_search_url", "TEXT"),
        ("completeness_score", "REAL DEFAULT 0.0"),
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
        ("reserved_field_1", "TEXT"),
        ("reserved_field_2", "TEXT"),
        ("reserved_field_3", "TEXT")
    ]
    
    with Session(engine) as session:
        for col_name, col_type in new_columns:
            try:
                session.execute(text(f"SELECT {col_name} FROM leads LIMIT 1"))
            except Exception:
                session.rollback()
                try:
                    session.execute(text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}"))
                    session.commit()
                    print(f"[DB] Migrated: added '{col_name}' column to 'leads' table")
                    # If migrating is_approved, set existing leads to approved
                    if col_name == "is_approved":
                        session.execute(text("UPDATE leads SET is_approved = 1 WHERE lead_status != 'retrieved'"))
                        session.commit()
                except Exception as e:
                    session.rollback()
                    print(f"[DB] Migration failed for column {col_name}: {e}")
                
    # Run automatic SQLite migration to add new columns to collection_batches if they don't exist
    batch_new_columns = [
        ("started_at", "DATETIME"),
        ("completed_at", "DATETIME"),
        ("total_listings_found", "INTEGER DEFAULT 0"),
        ("total_leads_stored", "INTEGER DEFAULT 0"),
        ("status", "TEXT DEFAULT 'running'"),
        ("search_url", "TEXT")
    ]
    
    with Session(engine) as session:
        for col_name, col_type in batch_new_columns:
            try:
                session.execute(text(f"SELECT {col_name} FROM collection_batches LIMIT 1"))
            except Exception:
                session.rollback()
                try:
                    session.execute(text(f"ALTER TABLE collection_batches ADD COLUMN {col_name} {col_type}"))
                    session.commit()
                    print(f"[DB] Migrated: added '{col_name}' column to 'collection_batches' table")
                except Exception as e:
                    session.rollback()
                    print(f"[DB] Migration failed for collection_batches column {col_name}: {e}")
                
    print(f"[DB] Database ready at: {DB_PATH}")


# ==============================================================================
# SESSION DEPENDENCY
# Used in every FastAPI endpoint as: session = Depends(get_session)
# Automatically opens and closes the DB connection per request
# ==============================================================================

def get_session():
    with Session(engine) as session:
        yield session