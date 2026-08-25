# backend/tests/test_collection_jobs.py
# Category 4: Collection Jobs Lifecycle, Progress, Status & Queue Persistence

import pytest
import time


def test_collection_job_creation_and_lifecycle(client):
    """Verifies collection job initialization and status progression."""
    job_id = f"job-reg-{int(time.time())}"
    job_payload = {
        "job_id": job_id,
        "source": "googlemaps",
        "mode": "deep",
        "search_query": "Colleges in Delhi NCR",
        "status": "running"
    }

    # Create job
    create_res = client.post("/api/collection-jobs", json=job_payload)
    assert create_res.status_code == 200
    assert create_res.json()["job"]["job_id"] == job_id

    # Update progress
    prog_res = client.post(f"/api/collection-jobs/{job_id}/progress", json={
        "saved": 10,
        "duplicates": 1,
        "errors": 0,
        "progress_percentage": 50.0,
        "current_listing": "Delhi University"
    })
    assert prog_res.status_code == 200
    job_data = prog_res.json()["job"]
    assert job_data["saved"] == 10
    assert job_data["progress_percentage"] == 50.0

    # Verify active job endpoint
    active_res = client.get("/api/collection-jobs/active")
    assert active_res.status_code == 200
    assert active_res.json()["job"]["job_id"] == job_id

    # Complete job
    status_res = client.post(f"/api/collection-jobs/{job_id}/status", json={"status": "completed"})
    assert status_res.status_code == 200
    assert status_res.json()["job"]["status"] == "completed"


def test_deep_collect_queue_persistence_and_progression(client):
    """Verifies Deep Collect queue items order, state transitions, and retry counter."""
    job_id = f"job-queue-{int(time.time())}"
    client.post("/api/collection-jobs", json={
        "job_id": job_id,
        "source": "indiamart",
        "mode": "deep",
        "status": "running"
    })

    # Enqueue 3 items
    queue_payload = {
        "items": [
            {"lead_id": "lead-q-1", "business_name": "Supplier One", "listing_url": "https://imart/s1"},
            {"lead_id": "lead-q-2", "business_name": "Supplier Two", "listing_url": "https://imart/s2"},
            {"lead_id": "lead-q-3", "business_name": "Supplier Three", "listing_url": "https://imart/s3"}
        ]
    }
    client.post(f"/api/collection-jobs/{job_id}/queue", json=queue_payload)

    # Fetch queue
    q_res = client.get(f"/api/collection-jobs/{job_id}/queue")
    assert q_res.status_code == 200
    items = q_res.json()["items"]
    assert len(items) == 3
    assert items[0]["queue_position"] == 1
    assert items[0]["status"] == "pending"

    # Update item 1 to completed
    stat_res = client.post(f"/api/collection-jobs/{job_id}/queue/lead-q-1/status", json={
        "status": "completed"
    })
    assert stat_res.status_code == 200

    # Update item 2 to retrying with retry_count=1
    retry_res = client.post(f"/api/collection-jobs/{job_id}/queue/lead-q-2/status", json={
        "status": "retrying",
        "retry_count": 1
    })
    assert retry_res.status_code == 200

    # Verify updated statuses
    q_res2 = client.get(f"/api/collection-jobs/{job_id}/queue")
    items2 = q_res2.json()["items"]
    assert items2[0]["status"] == "completed"
    assert items2[1]["status"] == "retrying"
    assert items2[1]["retry_count"] == 1
