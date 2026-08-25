# backend/services/merge_service.py
# ProspectLens — Future Merge & Enrichment Architecture

import re
from typing import Optional, List
from sqlmodel import Session, select
from database.models import Lead, Contact

class LeadComparisonProfile:
    """
    Standardized lead profile designed specifically for comparison matching.
    Provides normalized keys for Company Name, Phone, Website, and Location.
    """
    def __init__(
        self,
        business_name: str,
        phone: Optional[str] = None,
        website: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None
    ):
        self.raw_name = business_name
        self.raw_phone = phone
        self.raw_website = website
        self.raw_address = address
        self.raw_city = city
        self.raw_state = state
        self.raw_postal_code = postal_code

        # Normalized values
        self.normalized_name = self.normalize_company_name(business_name)
        self.normalized_phone = self.normalize_phone(phone)
        self.normalized_website = self.normalize_website(website)
        self.normalized_location_hash = self.normalize_location(address, city, state, postal_code)

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        Normalize company name to ignore suffixes, punctuation, casing, and spacing.
        e.g., 'ABC Interiors Pvt. Ltd.' -> 'abcinteriors'
        """
        from services.data_cleaner import normalize_name_for_comparison, clean_business_name
        return normalize_name_for_comparison(name) or clean_business_name(name).lower()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normalize phone numbers by stripping non-numeric characters and country codes.
        e.g., '+91 98765-43210' -> '9876543210'
        """
        if not phone:
            return ""
        digits = re.sub(r"\D", "", str(phone))
        digits = digits.lstrip("0")
        if digits.startswith("91") and len(digits) > 10:
            digits = digits[2:].lstrip("0")
        return digits[-10:] if len(digits) >= 10 else digits

    @staticmethod
    def normalize_website(url: str) -> str:
        """
        Normalize website URLs to extract the canonical root domain.
        e.g., 'https://www.abcinteriors.com/contact?utm_source=google' -> 'abcinteriors.com'
        """
        from services.data_cleaner import clean_website_url
        _, clean_dom = clean_website_url(url)
        return clean_dom or ""

    @staticmethod
    def normalize_location(address: str, city: str, state: str, postal_code: str) -> str:
        """
        Normalize location properties focusing on postal codes and city keys.
        """
        from services.data_cleaner import extract_pin_code, extract_city_and_state, clean_address_text
        pin = postal_code or extract_pin_code(address) or ""
        c, s = extract_city_and_state(address, city_hint=city, state_hint=state)
        c_norm = re.sub(r"[^a-z0-9]", "", (c or "").lower())
        s_norm = re.sub(r"[^a-z0-9]", "", (s or "").lower())
        return f"{pin}|{c_norm}|{s_norm}"


class LeadMergeEngine:
    """
    Centralized architectural engine prepared to manage merge operations.
    Designed to compare incoming leads with existing database entries.
    """
    
    @staticmethod
    def find_matching_lead(session: Session, incoming_profile: LeadComparisonProfile) -> Optional[Lead]:
        """
        Architecture Prep: Scan the database for an existing lead matching the incoming profile.
        Matches can be evaluated across Company Name, Phone, Website, or Location.
        
        Note: Comparison logic is skeletonized for future implementation.
        """
        # Future Matching Strategy:
        # 1. Match by exact normalized website if available
        # 2. Match by exact normalized phone if available
        # 3. Fallback to matching by normalized business name + normalized location key
        
        return None  # Reserved for future comparison implementation

    @staticmethod
    def merge_and_enrich_lead(session: Session, existing_lead: Lead, new_lead_data: dict) -> Lead:
        """
        Architecture Prep: Merge and enrich an existing lead with new incoming properties.
        This allows a Deep Collect session to fill in missing fields for an existing Quick Collect lead.
        
        Note: Merge logic is skeletonized for future implementation.
        """
        # Future Enrichment Strategy:
        # 1. Update rating, review_count, and listing_url if incoming values are present
        # 2. Add any new contacts (phones/emails) that are not duplicates
        # 3. Recalculate completeness score
        
        return existing_lead  # Reserved for future merge implementation
