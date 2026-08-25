# backend/api/routes_backup.py
# ProspectLens — Database Backup, Restore, and Diagnostics API Routes

import os
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, text

from database.db import engine, DB_PATH
from database.backup import create_database_backup, restore_database_backup, list_database_backups
from database.migrations import get_current_schema_version

router = APIRouter(tags=["Database & Backups"])


class BackupRequest(BaseModel):
    tag: Optional[str] = "manual"


class RestoreRequest(BaseModel):
    backup_file: str


@router.post("/backup")
def trigger_backup(req: BackupRequest = BackupRequest()):
    """Creates a point-in-time SQLite online backup."""
    result = create_database_backup(tag=req.tag or "manual")
    if result.get("status") != "ok":
        raise HTTPException(status_code=500, detail=result.get("message", "Backup failed"))
    return result


@router.get("/backups")
def get_backups():
    """Lists all available backup files."""
    backups = list_database_backups()
    return {
        "status": "ok",
        "count": len(backups),
        "backups": backups
    }


@router.post("/backup/restore")
def restore_backup(req: RestoreRequest):
    """Restores database from a verified backup."""
    if not req.backup_file:
        raise HTTPException(status_code=400, detail="backup_file is required")
    
    result = restore_database_backup(req.backup_file)
    if result.get("status") != "ok":
        raise HTTPException(status_code=500, detail=result.get("message", "Restore failed"))
    return result


@router.get("/database/health")
def get_database_health():
    """Returns deep database diagnostics including WAL mode, integrity check, and schema version."""
    try:
        with Session(engine) as session:
            # 1. Check integrity
            integrity_res = session.execute(text("PRAGMA integrity_check;")).first()
            integrity = integrity_res[0] if integrity_res else "unknown"

            # 2. Check journal mode
            journal_res = session.execute(text("PRAGMA journal_mode;")).first()
            journal_mode = journal_res[0] if journal_res else "unknown"

            # 3. Check busy timeout
            timeout_res = session.execute(text("PRAGMA busy_timeout;")).first()
            busy_timeout = timeout_res[0] if timeout_res else 0

            # 4. Check schema version
            schema_ver = get_current_schema_version(engine)

            # 5. Check file size
            db_size_kb = round(os.path.getsize(DB_PATH) / 1024.0, 2) if DB_PATH.exists() else 0.0

            # 6. Count tables
            tables_res = session.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")).first()
            table_count = tables_res[0] if tables_res else 0

            return {
                "status": "ok" if integrity == "ok" else "degraded",
                "database_path": str(DB_PATH),
                "database_size_kb": db_size_kb,
                "integrity": integrity,
                "journal_mode": journal_mode,
                "busy_timeout_ms": busy_timeout,
                "schema_version": schema_ver,
                "table_count": table_count
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database health query failed: {str(e)}")
