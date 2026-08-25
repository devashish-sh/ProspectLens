# backend/tests/test_deep_collect_safety.py
# Category 5: Deep Collect Anti-Contamination, Error Tracking, and Safety Checks

import pytest
from database.models import CollectionBatch, Lead


def test_batch_source_site_mismatch_protection(client):
    """Verifies that leads cannot be contaminated into a batch belonging to a different source platform."""
    # 1. Create a Google Maps batch
    batch_res = client.post("/api/leads", json={
        "batch_id": "BATCH-GMAPS-STRICT",
        "source_site": "googlemaps",
        "business_name": "Google Maps Anchor Business"
    })
    assert batch_res.status_code == 200

    # 2. Attempt to ingest an IndiaMART lead into the Google Maps batch
    mismatch_res = client.post("/api/leads", json={
        "batch_id": "BATCH-GMAPS-STRICT",
        "source_site": "indiamart",
        "business_name": "IndiaMART Intruder Business"
    })
    assert mismatch_res.status_code == 200
    res_data = mismatch_res.json()
    assert res_data["status"] == "error"
    assert "cannot be mixed into batch/capsule" in res_data["message"]


def test_collection_error_tracking_and_retrieval(client):
    """Verifies that scraper/DOM errors during collection are tracked and auditable."""
    err_payload = {
        "batch_id": "BATCH-ERR-01",
        "website": "googlemaps",
        "collection_mode": "deep",
        "collection_stage": "Opening Listing",
        "severity": "Warning",
        "error_category": "DOM Timeout",
        "error_message": "Side panel failed to load within 5000ms",
        "retry_recommended": True
    }

    # Record error
    record_res = client.post("/api/errors", json=err_payload)
    assert record_res.status_code == 200
    err_data = record_res.json()
    assert err_data["status"] == "ok"
    error_id = err_data["error_id"]

    # Fetch errors
    get_res = client.get("/api/errors/diagnostics")
    assert get_res.status_code == 200
    all_errs = get_res.json().get("errors", [])
    assert any(e["error_id"] == error_id for e in all_errs)
