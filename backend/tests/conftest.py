# backend/tests/conftest.py
# Pytest Fixtures with Isolated Temporary SQLite Database

import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event

from main import app
from database.db import get_session
from database.migrations import run_database_migrations
from database.models import (
    Lead, Contact, CollectionBatch, Job, CollectionJob, DeepQueueItem,
    ExportHistory, VisitedURL, SourceRecord, Note, User, Tag, LeadTag,
    WebsiteSource, DataCapsule, SearchHistory, LeadHistory,
    LeadVersionHistory, CollectionError, SearchContext, DiscoveredListing,
    SchemaVersion, DatabaseBackupLog
)


@pytest.fixture(scope="session")
def temp_test_env():
    """Creates an isolated temporary test directory and database."""
    temp_dir = tempfile.TemporaryDirectory(prefix="prospectlens_test_")
    temp_path = Path(temp_dir.name)
    db_file = temp_path / "test_prospectlens.db"
    db_url = f"sqlite:///{db_file}"

    test_engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 15.0}
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA busy_timeout = 10000;")
        cursor.execute("PRAGMA cache_size = -64000;")
        cursor.execute("PRAGMA temp_store = MEMORY;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()

    # Create all tables & migrations on test engine
    SQLModel.metadata.create_all(test_engine)
    run_database_migrations(test_engine)
    from database.migrations import seed_initial_data
    seed_initial_data(test_engine)

    yield {
        "dir": temp_path,
        "db_file": db_file,
        "engine": test_engine
    }

    test_engine.dispose()
    temp_dir.cleanup()


@pytest.fixture
def db_session(temp_test_env):
    """Yields a database session bound to the temporary test database."""
    with Session(temp_test_env["engine"]) as session:
        yield session


@pytest.fixture
def client(temp_test_env):
    """FastAPI TestClient with overridden get_session dependency."""
    def get_test_session():
        with Session(temp_test_env["engine"]) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_lead_data():
    """Provides a realistic sample lead payload for testing."""
    return {
        "batch_id": "TEST-BATCH-001",
        "source_site": "googlemaps",
        "business_name": "Apex Global Solutions Pvt Ltd",
        "category": "Software & ERP Development",
        "address": "Tower B, Sector 62, Noida, Uttar Pradesh 201309",
        "city": "Noida",
        "state": "Uttar Pradesh",
        "country": "India",
        "postal_code": "201309",
        "website": "https://www.apexglobal.in",
        "listing_url": "https://maps.google.com/place/apex-global-noida",
        "collection_mode": "quick",
        "rating": 4.7,
        "review_count": 86,
        "contacts": [
            {"contact_type": "phone", "contact_value": "+91 98765 43210"},
            {"contact_type": "email", "contact_value": "contact@apexglobal.in"}
        ]
    }
