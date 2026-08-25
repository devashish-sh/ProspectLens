# backend/services/deduplication.py
# ProspectLens — SHA-256 Deduplication Logic
#
# HOW IT WORKS:
# Every incoming lead gets a dedup_hash computed from 3 fields:
#   business_name + source_site + address
#
# Before saving any lead, we check if this hash already exists in the DB.
# If it does — skip it. If not — save it.
#
# WHY SHA-256 over MD5:
# Significantly lower collision risk (two different businesses producing
# the same hash). Industry standard. No performance difference at our scale.
#
# CROSS-PLATFORM BEHAVIOUR:
# "ABC Interiors" on IndiaMART  → hash A  (saved as lead 1)
# "ABC Interiors" on Google Maps → hash B  (saved as lead 2)  ← different source_site
# Running same IndiaMART search again → hash A already exists → skipped ✓

import hashlib
from sqlmodel import Session, select
from database.models import Lead, VisitedURL


def compute_dedup_hash(business_name: str, source_site: str, address: str = "") -> str:
    """
    Compute a SHA-256 fingerprint for a lead.
    Normalizes business name, source site, and address to prevent duplicate creations
    caused by cosmetic formatting variations while strictly isolating source sites.
    """
    from services.data_cleaner import compute_clean_dedup_hash
    return compute_clean_dedup_hash(business_name=business_name, source_site=source_site, address=address)


def is_duplicate_lead(dedup_hash: str, session: Session) -> bool:
    """
    Returns True if a lead with this hash already exists in the database.
    Use this before saving any new lead.

    Example usage in LeadService:
        hash = compute_dedup_hash(name, site, address)
        if is_duplicate_lead(hash, session):
            return None  # skip
    """
    statement = select(Lead).where(Lead.dedup_hash == dedup_hash)
    existing  = session.exec(statement).first()
    return existing is not None


def compute_url_hash(url: str) -> str:
    """
    SHA-256 hash of a URL string.
    Used by VisitedURL table to track which listing URLs have been visited
    in Deep Collect — prevents revisiting the same listing across sessions.
    """
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def is_url_visited(url_hash: str, session: Session) -> bool:
    """
    Returns True if this URL has already been visited in a previous Deep Collect run.
    """
    statement = select(VisitedURL).where(VisitedURL.url_hash == url_hash)
    existing  = session.exec(statement).first()
    return existing is not None