# backend/database/db.py
# ProspectLens — SQLite Connection + Session Management + DB Initialization

from sqlmodel import SQLModel, Session, create_engine
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
        Note, User, Tag, LeadTag
    )
    SQLModel.metadata.create_all(engine)
    print(f"[DB] Database ready at: {DB_PATH}")


# ==============================================================================
# SESSION DEPENDENCY
# Used in every FastAPI endpoint as: session = Depends(get_session)
# Automatically opens and closes the DB connection per request
# ==============================================================================

def get_session():
    with Session(engine) as session:
        yield session