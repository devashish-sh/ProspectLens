# backend/api/routes_health.py
# ProspectLens — Health Check Endpoints
#
# These endpoints let you verify the backend is running correctly.
# Visit http://localhost:8000/api/health in your browser anytime to check.

from fastapi import APIRouter
from database.db import engine
from sqlmodel import text, Session

router = APIRouter(tags=["Health"])


# ==============================================================================
# GET /api/health
# Main health check — confirms server + database are both working
# ==============================================================================

@router.get("/health")
def health_check():
    # Test database connection
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "server": "running",
        "database": db_status,
        "message": "ProspectLens backend is running"
    }


# ==============================================================================
# GET /api/health/db
# Detailed database check — shows all 10 tables and their row counts
# Useful for verifying database structure during development
# ==============================================================================

@router.get("/health/db")
def health_db():
    tables = [
        "leads", "contacts", "collection_batches", "jobs",
        "export_history", "visited_urls", "source_records",
        "notes", "users", "tags", "lead_tags"
    ]

    table_counts = {}
    try:
        with Session(engine) as session:
            for table in tables:
                result = session.exec(text(f"SELECT COUNT(*) FROM {table}")).first()
                table_counts[table] = result[0] if result else 0
        return {
            "status": "ok",
            "tables": table_counts,
            "total_tables": len(table_counts)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}