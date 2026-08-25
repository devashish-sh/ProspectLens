# backend/tests/test_data_quality.py
# Category 2: Normalization, Completeness Scoring, Deduplication & Lead Merge Logic

import pytest
from services.deduplication import compute_dedup_hash
from services.collection_pipeline import calculate_lead_completeness
from services.merge_service import LeadComparisonProfile
from services.data_cleaner import (
    clean_business_name, normalize_name_for_comparison, clean_phone_number,
    clean_website_url, clean_address_text, extract_pin_code, extract_city_and_state,
    is_valid_text
)
from database.models import Lead, Contact


def test_clean_business_name_and_unicode_normalizations():
    """Verifies business name cleaning handles unicode spaces, quotes, and dashes."""
    # Unicode non-breaking space & multiple whitespace
    raw_1 = "  Apex\u00a0\u00a0Technologies   Pvt   Ltd  "
    assert clean_business_name(raw_1) == "Apex Technologies Pvt Ltd"

    # Unicode smart quotes & dashes
    raw_2 = "“Om – Sai” — Enterprises."
    assert clean_business_name(raw_2) == '"Om - Sai" - Enterprises'

    # Empty/placeholder names
    assert clean_business_name("N/A") == ""
    assert clean_business_name("  -  ") == ""
    assert clean_business_name(None) == ""


def test_phone_number_cleaning_and_placeholder_rejection():
    """Verifies phone number standardization and placeholder rejection."""
    # Standard 10-digit mobile
    assert clean_phone_number("9876543210") == "+91-9876543210"

    # Leading zero format
    assert clean_phone_number("09876543210") == "+91-9876543210"

    # Country code prefix with formatting
    assert clean_phone_number("+91 (987) 654-3210") == "+91-9876543210"
    assert clean_phone_number("91-9876543210") == "+91-9876543210"
    assert clean_phone_number("+91-011-23456789") == "+91-1123456789"

    # Toll-free preservation
    assert clean_phone_number("1800-111-222") == "1800111222"
    assert clean_phone_number("1860 200 300") == "1860200300"

    # Rejection of invalid/placeholder phone strings
    assert clean_phone_number("N/A") is None
    assert clean_phone_number("0000000000") is None
    assert clean_phone_number("1234567890") is None
    assert clean_phone_number("Not available") is None
    assert clean_phone_number(None) is None


def test_website_normalization_and_tracking_stripping():
    """Verifies website URLs strip tracking params, normalizes protocol, and extracts root domain."""
    # Strips UTM params and trailing slashes
    url_1 = "https://www.apexglobal.in/about/?utm_source=google&utm_medium=maps&utm_campaign=brand"
    cleaned_1, domain_1 = clean_website_url(url_1)
    assert cleaned_1 == "https://www.apexglobal.in/about"
    assert domain_1 == "apexglobal.in"

    # Adds https to bare domain
    url_2 = "companyhub.org/contact"
    cleaned_2, domain_2 = clean_website_url(url_2)
    assert cleaned_2 == "https://companyhub.org/contact"
    assert domain_2 == "companyhub.org"

    # Strips fbclid & gclid
    url_3 = "http://matrix.co.in/?gclid=ABC12345&fbclid=XYZ987"
    cleaned_3, domain_3 = clean_website_url(url_3)
    assert cleaned_3 == "http://matrix.co.in"
    assert domain_3 == "matrix.co.in"

    # Rejection of placeholder URLs
    assert clean_website_url("N/A") == (None, None)
    assert clean_website_url("http://none") == (None, None)
    assert clean_website_url("https://") == (None, None)
    assert clean_website_url(None) == (None, None)


def test_address_cleaning_and_city_state_pin_extraction():
    """Verifies address punctuation cleanup and accurate City, State, and PIN extraction."""
    raw_addr = "Shop 12, , Sector 62, , Noida - 201309, Uttar Pradesh, India"
    cleaned_addr = clean_address_text(raw_addr)
    assert cleaned_addr == "Shop 12, Sector 62, Noida - 201309, Uttar Pradesh, India"

    # PIN extraction
    assert extract_pin_code(cleaned_addr) == "201309"

    # City & State extraction
    city, state = extract_city_and_state(cleaned_addr)
    assert city == "Noida"
    assert state == "Uttar Pradesh"

    # Extraction for other Indian hubs
    c2, s2 = extract_city_and_state("Plot 45, GIDC Industrial Estate, Surat, Gujarat")
    assert c2 == "Surat"
    assert s2 == "Gujarat"


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


def test_completeness_scoring_rejects_dummy_placeholders():
    """Verifies that invalid/placeholder strings do NOT get false completeness credit."""
    lead_dummy = Lead(
        business_name="N/A",               # Invalid placeholder -> 0%
        address="-",                        # Invalid placeholder -> 0%
        primary_phone="0000000000",         # Invalid dummy phone -> 0%
        primary_email="None",               # Invalid placeholder -> 0%
        website="http://none",              # Invalid placeholder -> 0%
        review_count=0,                     # Zero reviews -> 0%
        listing_url="na",                   # Invalid URL -> 0%
        rating=0.0                          # Zero rating -> 0%
    )
    dummy_contacts = [
        {"contact_type": "phone", "contact_value": "N/A"},
        {"contact_type": "email", "contact_value": "none"}
    ]
    score_dummy = calculate_lead_completeness(lead_dummy, dummy_contacts)
    assert score_dummy == 0.0, f"Expected 0.0% completeness for all-placeholder lead, got {score_dummy}%"


def test_lead_comparison_profile_normalization():
    """Verifies LeadComparisonProfile removes common legal suffixes and cleans phone/website."""
    profile1 = LeadComparisonProfile(
        business_name="Apex Global Softwares Private Limited",
        phone="+91 (120) 456-7890",
        website="https://www.apex-global.com/contact.html?utm_source=google"
    )
    profile2 = LeadComparisonProfile(
        business_name="Apex Global Softwares Pvt Ltd",
        phone="01204567890",
        website="http://apex-global.com/"
    )

    # Normalized company names should match
    assert profile1.normalized_name == profile2.normalized_name
    assert "apexglobalsoftwares" in profile1.normalized_name

    # Normalized phone should match canonical 10 digits
    assert profile1.normalized_phone == "1204567890"
    assert profile2.normalized_phone == "1204567890"

    # Normalized website root domains should match
    assert profile1.normalized_website == "apex-global.com"
    assert profile2.normalized_website == "apex-global.com"
