# backend/tests/test_database.py
# Category 1: Database Initialization, WAL Pragmas, Migrations, CRUD, Integrity & Backups

import os
import sqlite3
from datetime import datetime
from sqlmodel import Session, text, select
from database.models import (
    Lead, Contact, CollectionBatch, Job, CollectionJob, DeepQueueItem,
    SchemaVersion, WebsiteSource, DataCapsule
)
from database.backup import verify_sqlite_integrity, get_sqlite_lead_count


def test_database_initialization_and_pragmas(temp_test_env):
    """Verifies that all tables are created and SQLite performance pragmas are active."""
    engine = temp_test_env["engine"]
    with Session(engine) as session:
        # Check SQLite journal mode
        journal_res = session.execute(text("PRAGMA journal_mode;")).first()
        assert journal_res[0].lower() == "wal", f"Expected WAL mode, got {journal_res[0]}"

        # Check busy timeout
        timeout_res = session.execute(text("PRAGMA busy_timeout;")).first()
        assert timeout_res[0] >= 10000, f"Expected busy timeout >= 10000ms, got {timeout_res[0]}"

        # Check foreign keys
        fk_res = session.execute(text("PRAGMA foreign_keys;")).first()
        assert fk_res[0] == 1, "Foreign keys must be enabled"

        # Check table count (at least 20 tables)
        tables = session.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).all()
        table_names = [t[0] for t in tables]
        assert "leads" in table_names
        assert "contacts" in table_names
        assert "collection_batches" in table_names
        assert "collection_jobs" in table_names
        assert "deep_queue_items" in table_names
        assert "data_capsules" in table_names
        assert "schema_version" in table_names


def test_schema_version_and_composite_indexes(temp_test_env):
    """Verifies schema version is tracked and required composite indexes exist."""
    engine = temp_test_env["engine"]
    with Session(engine) as session:
        # Check schema version
        versions = session.exec(select(SchemaVersion)).all()
        assert len(versions) >= 2
        assert max(v.version_id for v in versions) >= 2

        # Check composite indexes in sqlite_master
        indices = session.execute(text("SELECT name FROM sqlite_master WHERE type='index';")).all()
        index_names = [i[0] for i in indices]
        assert "idx_leads_source_approved" in index_names
        assert "idx_leads_approved_collected" in index_names
        assert "idx_leads_dedup_hash" in index_names
        assert "idx_contacts_lead_id" in index_names
        assert "idx_deep_queue_job_status" in index_names


def test_lead_and_contacts_crud(temp_test_env):
    """Verifies basic CRUD operations on Lead and Contact relational tables."""
    engine = temp_test_env["engine"]
    with Session(engine) as session:
        # 1. Create parent batch
        batch = CollectionBatch(
            batch_id="CRUD-BATCH-01",
            source_site="googlemaps",
            collection_mode="quick"
        )
        session.add(batch)
        session.commit()

        # 2. Create Lead
        lead = Lead(
            batch_id="CRUD-BATCH-01",
            source_site="googlemaps",
            business_name="Matrix Technologies",
            city="Pune",
            category="IT Services",
            lead_status="new",
            is_approved=False
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        assert lead.lead_id is not None

        # 3. Create Contacts
        c1 = Contact(lead_id=lead.lead_id, contact_type="phone", contact_value="+91 91234 56789")
        c2 = Contact(lead_id=lead.lead_id, contact_type="email", contact_value="info@matrixtech.com")
        session.add_all([c1, c2])
        session.commit()

        # 4. Read
        fetched_lead = session.get(Lead, lead.lead_id)
        assert fetched_lead.business_name == "Matrix Technologies"
        
        contacts = session.exec(select(Contact).where(Contact.lead_id == lead.lead_id)).all()
        assert len(contacts) == 2

        # 5. Update
        fetched_lead.notes = "Client interested in ERP software."
        fetched_lead.is_approved = True
        session.add(fetched_lead)
        session.commit()

        updated_lead = session.get(Lead, lead.lead_id)
        assert updated_lead.notes == "Client interested in ERP software."
        assert updated_lead.is_approved is True

        # 6. Delete
        for c in contacts:
            session.delete(c)
        session.delete(fetched_lead)
        session.commit()

        assert session.get(Lead, lead.lead_id) is None


def test_database_integrity_check(temp_test_env):
    """Verifies that SQLite PRAGMA integrity_check returns ok."""
    engine = temp_test_env["engine"]
    with Session(engine) as session:
        res = session.execute(text("PRAGMA integrity_check;")).first()
        assert res[0] == "ok"


def test_online_backup_and_restore_operations(temp_test_env):
    """Verifies point-in-time online SQLite backup creation, integrity check, and restoration."""
    db_file = temp_test_env["db_file"]
    backup_file = temp_test_env["dir"] / "test_snapshot.db"

    # 1. Create a live backup using SQLite Backup API
    source_conn = sqlite3.connect(str(db_file), timeout=5.0)
    dest_conn = sqlite3.connect(str(backup_file))
    with dest_conn:
        source_conn.backup(dest_conn)
    dest_conn.close()
    source_conn.close()

    # 2. Verify snapshot integrity
    assert verify_sqlite_integrity(backup_file) is True

    # 3. Add canary lead to source DB
    engine = temp_test_env["engine"]
    with Session(engine) as session:
        batch = CollectionBatch(batch_id="CANARY-BATCH", source_site="indiamart")
        session.add(batch)
        session.commit()
        canary = Lead(
            batch_id="CANARY-BATCH",
            source_site="indiamart",
            business_name="Temporary Canary Lead",
            dedup_hash="canary-hash-xyz"
        )
        session.add(canary)
        session.commit()

    assert get_sqlite_lead_count(db_file) >= 1

    # 4. Restore from backup (should rollback canary lead)
    restore_source = sqlite3.connect(str(backup_file), timeout=5.0)
    restore_dest = sqlite3.connect(str(db_file), timeout=5.0)
    with restore_dest:
        restore_source.backup(restore_dest)
    restore_dest.close()
    restore_source.close()

    # 5. Verify restored database
    assert verify_sqlite_integrity(db_file) is True
    with Session(engine) as session:
        canary_found = session.exec(select(Lead).where(Lead.dedup_hash == "canary-hash-xyz")).first()
        assert canary_found is None
