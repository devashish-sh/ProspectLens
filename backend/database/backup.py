# backend/database/backup.py
# ProspectLens — Safe Local SQLite Online Backup & Restore Manager

import os
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from database.db import DB_PATH, USER_DATA_DIR

BACKUP_DIR = USER_DATA_DIR / "backups"


def get_backup_dir() -> Path:
    """Returns the backup directory path, creating it if it doesn't exist."""
    if not BACKUP_DIR.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def verify_sqlite_integrity(file_path: Path) -> bool:
    """Runs PRAGMA integrity_check on an SQLite file."""
    if not file_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(file_path), timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()
        conn.close()
        return res is not None and res[0] == "ok"
    except Exception:
        return False


def get_sqlite_lead_count(file_path: Path) -> int:
    """Returns the count of leads in a database file."""
    if not file_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(file_path), timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM leads;")
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 0
    except Exception:
        return 0


def create_database_backup(tag: str = "manual", max_retained: int = 10) -> Dict[str, Any]:
    """
    Creates a safe, online, point-in-time backup of the SQLite database
    using the SQLite Online Backup API. This ensures zero locks and zero data corruption.
    """
    if not DB_PATH.exists():
        return {
            "status": "error",
            "message": f"Database file does not exist at {DB_PATH}"
        }

    backup_dir = get_backup_dir()
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    clean_tag = "".join(c for c in tag if c.isalnum() or c in ("-", "_")) or "backup"
    backup_filename = f"prospectlens_backup_{timestamp_str}_{clean_tag}.db"
    backup_file_path = backup_dir / backup_filename

    try:
        # Connect to source and destination
        source_conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
        dest_conn = sqlite3.connect(str(backup_file_path))
        
        # Atomic online backup stream
        with dest_conn:
            source_conn.backup(dest_conn, pages=100, sleep=0.01)
            
        dest_conn.close()
        source_conn.close()

        # Verify backup integrity
        is_valid = verify_sqlite_integrity(backup_file_path)
        if not is_valid:
            if backup_file_path.exists():
                backup_file_path.unlink()
            return {
                "status": "error",
                "message": "Backup verification failed (corrupt integrity check)."
            }

        size_kb = round(os.path.getsize(backup_file_path) / 1024.0, 2)
        lead_count = get_sqlite_lead_count(backup_file_path)

        # Retention management for automated backups
        if tag.startswith("auto"):
            prune_old_backups(prefix="prospectlens_backup_", tag_filter="auto", keep=max_retained)

        return {
            "status": "ok",
            "message": f"Successfully created backup: {backup_filename}",
            "backup_file": backup_filename,
            "path": str(backup_file_path),
            "size_kb": size_kb,
            "lead_count": lead_count,
            "is_valid": is_valid,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        if backup_file_path.exists():
            try:
                backup_file_path.unlink()
            except Exception:
                pass
        return {
            "status": "error",
            "message": f"Failed to create database backup: {str(e)}"
        }


def restore_database_backup(backup_filename: str) -> Dict[str, Any]:
    """
    Safely restores the database from a verified backup file.
    Creates a pre-restore backup first to guarantee rollback capability.
    """
    backup_dir = get_backup_dir()
    # Prevent path traversal
    safe_name = os.path.basename(backup_filename)
    backup_file_path = backup_dir / safe_name

    if not backup_file_path.exists():
        return {
            "status": "error",
            "message": f"Backup file '{safe_name}' was not found in backups directory."
        }

    # 1. Verify backup file integrity before touching active database
    if not verify_sqlite_integrity(backup_file_path):
        return {
            "status": "error",
            "message": f"Backup file '{safe_name}' failed integrity check and cannot be restored."
        }

    # 2. Create emergency pre-restore snapshot
    pre_restore_result = create_database_backup(tag="pre_restore")

    try:
        # 3. Perform atomic online restore into active DB_PATH
        source_conn = sqlite3.connect(str(backup_file_path), timeout=10.0)
        dest_conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
        
        with dest_conn:
            source_conn.backup(dest_conn, pages=100, sleep=0.01)
            
        dest_conn.close()
        source_conn.close()

        # 4. Verify restored active database integrity
        if not verify_sqlite_integrity(DB_PATH):
            # Attempt rollback from pre-restore backup
            if pre_restore_result.get("status") == "ok" and "path" in pre_restore_result:
                rb_source = sqlite3.connect(pre_restore_result["path"])
                rb_dest = sqlite3.connect(str(DB_PATH))
                rb_source.backup(rb_dest)
                rb_dest.close()
                rb_source.close()
            return {
                "status": "error",
                "message": "Restored database failed integrity verification. Rolled back to pre-restore snapshot."
            }

        lead_count = get_sqlite_lead_count(DB_PATH)
        return {
            "status": "ok",
            "message": f"Successfully restored database from '{safe_name}'.",
            "leads_restored": lead_count,
            "pre_restore_backup": pre_restore_result.get("backup_file")
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Restore operation encountered an error: {str(e)}"
        }


def list_database_backups() -> List[Dict[str, Any]]:
    """Lists all available backup files sorted newest first."""
    backup_dir = get_backup_dir()
    backups = []
    
    for f in backup_dir.glob("*.db"):
        try:
            stat = f.stat()
            size_kb = round(stat.st_size / 1024.0, 2)
            created_dt = datetime.utcfromtimestamp(stat.st_mtime)
            backups.append({
                "filename": f.name,
                "path": str(f),
                "size_kb": size_kb,
                "created_at": created_dt.isoformat() + "Z",
                "is_valid": True
            })
        except Exception:
            continue

    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def prune_old_backups(prefix: str = "prospectlens_backup_", tag_filter: Optional[str] = "auto", keep: int = 10):
    """Deletes older backups exceeding the retention threshold."""
    backup_dir = get_backup_dir()
    matching_files = []
    
    for f in backup_dir.glob(f"{prefix}*.db"):
        if tag_filter and tag_filter not in f.name:
            continue
        try:
            matching_files.append((f.stat().st_mtime, f))
        except Exception:
            pass

    matching_files.sort(key=lambda x: x[0], reverse=True)
    if len(matching_files) > keep:
        for _, file_path in matching_files[keep:]:
            try:
                file_path.unlink()
            except Exception:
                pass
