# backend/tests/test_data_quality.py
# Category 2: Normalization, Completeness Scoring, Deduplication & Lead Merge Logic

import pytest
from services.deduplication import compute_dedup_hash
from services.collection_pipeline import calculate_lead_completeness
from services.merge_service import LeadComparisonProfile
from database.models import Lead, Contact


def test_deduplication_hash_deterministic():
    """Verifies that dedup hash is invariant to case and whitespace differences."""
    hash1 = compute_dedup_hash(
        business_name="  Alpha Tech Solutions Pvt Ltd  ",
        source_site="GoogleMaps",
        address="Sector 18, Noida, Uttar Pradesh"
    )
    hash2 = compute_dedup_hash(
        business_name="alpha tech solutions pvt ltd",
        source_site="googlemaps",
        address="sector 18, noida, uttar pradesh"
    )
    assert hash1 == hash2, "Dedup hash must match across case and whitespace variations"


def test_deduplication_cross_platform_isolation():
    """Verifies that the same company found on different sources yields different hashes."""
    hash_gmaps = compute_dedup_hash("Zenith College", "googlemaps", "MG Road, Bangalore")
    hash_imart = compute_dedup_hash("Zenith College", "indiamart", "MG Road, Bangalore")
    hash_jdeal = compute_dedup_hash("Zenith College", "justdial", "MG Road, Bangalore")
    
    assert hash_gmaps != hash_imart
    assert hash_imart != hash_jdeal
    assert hash_gmaps != hash_jdeal


def test_completeness_scoring_calculation():
    """Verifies completeness scoring correctly awards 12.5% per valid field up to 100%."""
    # 1. Bare minimum lead (Name only) -> 12.5%
    lead_minimal = Lead(business_name="Acme Corp")
    score_min = calculate_lead_completeness(lead_minimal, [])
    assert score_min == 12.5

    # 2. Name + Location + Phone -> 37.5%
    lead_partial = Lead(
        business_name="Acme Corp",
        address="123 Main St, New Delhi",
        primary_phone="+91 99999 11111"
    )
    score_partial = calculate_lead_completeness(lead_partial, [])
    assert score_partial == 37.5

    # 3. Full lead -> 100.0%
    lead_full = Lead(
        business_name="Acme Corp",
        address="123 Main St, New Delhi",
        primary_phone="+91 99999 11111",
        primary_email="info@acme.com",
        website="https://acme.com",
        review_count=45,
        listing_url="https://maps.google.com/acme",
        rating=4.8
    )
    score_full = calculate_lead_completeness(lead_full, [])
    assert score_full == 100.0


def test_lead_comparison_profile_normalization():
    """Verifies LeadComparisonProfile removes common legal suffixes and cleans phone/website."""
    profile1 = LeadComparisonProfile(
        business_name="Apex Global Softwares Private Limited",
        phone="+91 (120) 456-7890",
        website="https://www.apex-global.com/contact.html"
    )
    profile2 = LeadComparisonProfile(
        business_name="Apex Global Softwares Pvt Ltd",
        phone="01204567890",
        website="http://apex-global.com"
    )

    # Normalized company names should match
    assert profile1.normalized_name == profile2.normalized_name
    assert "apexglobalsoftwares" in profile1.normalized_name

    # Normalized phone should strip formatting
    assert profile1.normalized_phone == "1204567890"
    assert profile2.normalized_phone == "1204567890"

    # Normalized website domains should match
    assert profile1.normalized_website == "apex-global.com"
    assert profile2.normalized_website == "apex-global.com"
