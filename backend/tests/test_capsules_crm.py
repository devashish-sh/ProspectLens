# backend/tests/test_capsules_crm.py
# Category 3: Data Capsules & Main Leads CRM Workflow Verification

import pytest
from database.models import Lead, CollectionBatch


def test_lead_ingestion_enters_unapproved_capsule(client, sample_lead_data):
    """Verifies that freshly ingested leads enter unapproved (capsule) state by default."""
    res = client.post("/api/leads", json=sample_lead_data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "saved"
    lead_id = res_data["lead_id"]

    # Verify lead in DB
    lead_res = client.get(f"/api/leads/{lead_id}")
    assert lead_res.status_code == 200
    lead = lead_res.json()["lead"]
    assert lead["is_approved"] is False
    assert lead["lead_status"] == "retrieved"


def test_capsule_source_isolation(client):
    """Verifies that leads from one source are isolated into their specific capsule."""
    # Insert Google Maps lead
    client.post("/api/leads", json={
        "batch_id": "BATCH-GMAPS-1",
        "source_site": "googlemaps",
        "business_name": "Gmaps Exclusive Tech",
        "city": "Bengaluru"
    })
    # Insert IndiaMART lead
    client.post("/api/leads", json={
        "batch_id": "BATCH-IMART-1",
        "source_site": "indiamart",
        "business_name": "Indiamart Exclusive Suppliers",
        "city": "Mumbai"
    })

    # Query Google Maps capsule
    g_res = client.get("/api/capsules/googlemaps/leads")
    assert g_res.status_code == 200
    g_names = [l["business_name"] for l in g_res.json()["leads"]]
    assert "Gmaps Exclusive Tech" in g_names
    assert "Indiamart Exclusive Suppliers" not in g_names

    # Query IndiaMART capsule
    i_res = client.get("/api/capsules/indiamart/leads")
    assert i_res.status_code == 200
    i_names = [l["business_name"] for l in i_res.json()["leads"]]
    assert "Indiamart Exclusive Suppliers" in i_names
    assert "Gmaps Exclusive Tech" not in i_names


def test_lead_approval_to_main_leads(client):
    """Verifies approving a lead transitions it to Main Leads CRM database."""
    create_res = client.post("/api/leads", json={
        "batch_id": "BATCH-APPROVE-1",
        "source_site": "googlemaps",
        "business_name": "Approvable Solutions",
        "city": "Gurugram"
    })
    lead_id = create_res.json()["lead_id"]

    # Approve lead
    app_res = client.post(f"/api/leads/{lead_id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "ok"

    # Verify present in Main Leads (approved=true)
    main_res = client.get("/api/leads?approved=true")
    assert main_res.status_code == 200
    approved_ids = [l["lead_id"] for l in main_res.json().get("leads", [])]
    assert lead_id in approved_ids

    # Verify removed from pending Capsule
    cap_res = client.get("/api/capsules/googlemaps/leads")
    pending_ids = [l["lead_id"] for l in cap_res.json()["leads"]]
    assert lead_id not in pending_ids


def test_bulk_approval_workflow(client):
    """Verifies bulk approval of multiple selected leads."""
    l1 = client.post("/api/leads", json={
        "batch_id": "BULK-BATCH", "source_site": "justdial", "business_name": "Bulk Candidate One"
    }).json()["lead_id"]

    l2 = client.post("/api/leads", json={
        "batch_id": "BULK-BATCH", "source_site": "justdial", "business_name": "Bulk Candidate Two"
    }).json()["lead_id"]

    bulk_res = client.post("/api/leads/bulk-approve", json={"lead_ids": [l1, l2]})
    assert bulk_res.status_code == 200
    assert bulk_res.json()["count"] == 2

    # Verify both approved
    main_res = client.get("/api/leads?approved=true")
    main_ids = [l["lead_id"] for l in main_res.json().get("leads", [])]
    assert l1 in main_ids
    assert l2 in main_ids


def test_lead_notes_and_status_persistence(client):
    """Verifies custom research notes and CRM status lifecycle updates."""
    lead_id = client.post("/api/leads", json={
        "batch_id": "NOTES-BATCH", "source_site": "googlemaps", "business_name": "Notes Persistence Org"
    }).json()["lead_id"]

    # Update note and status
    update_res = client.put(f"/api/leads/{lead_id}", json={
        "notes": "Decision maker: Mr. Sharma. Interested in enterprise trial.",
        "lead_status": "qualified"
    })
    assert update_res.status_code == 200

    # Fetch back
    get_res = client.get(f"/api/leads/{lead_id}")
    lead = get_res.json()["lead"]
    assert lead["notes"] == "Decision maker: Mr. Sharma. Interested in enterprise trial."
    assert lead["lead_status"] == "qualified"
