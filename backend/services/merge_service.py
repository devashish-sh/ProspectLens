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
        if not name:
            return ""
        name_lower = name.lower().strip()
        # Remove common business suffixes to allow cleaner matching
        suffixes = [
            r"\bpvt\b", r"\bltd\b", r"\bprivate\b", r"\blimited\b",
            r"\binc\b", r"\bllc\b", r"\bco\b", r"\bcorp\b", r"\bcorporation\b"
        ]
        for suffix in suffixes:
            name_lower = re.sub(suffix, "", name_lower)
        # Strip non-alphanumeric characters
        return re.sub(r"[^a-z0-9]", "", name_lower)

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normalize phone numbers by stripping non-numeric characters and country codes.
        e.g., '+91 98765-43210' -> '9876543210'
        """
        if not phone:
            return ""
        # Keep only digits
        digits = re.sub(r"\D", "", phone)
        # Handle country code (e.g., strip leading 91 or 0 for standard Indian numbers)
        if len(digits) == 12 and digits.startswith("91"):
            return digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            return digits[1:]
        return digits

    @staticmethod
    def normalize_website(url: str) -> str:
        """
        Normalize website URLs to extract the domain/hostname exactly.
        e.g., 'https://www.abcinteriors.com/contact' -> 'abcinteriors.com'
        """
        if not url:
            return ""
        url_lower = url.lower().strip()
        # Remove protocol prefixes
        url_lower = re.sub(r"^https?://", "", url_lower)
        # Remove www prefix
        url_lower = re.sub(r"^www\.", "", url_lower)
        # Split path and keep host/domain only
        parts = url_lower.split("/")
        return parts[0] if parts else ""

    @staticmethod
    def normalize_location(address: str, city: str, state: str, postal_code: str) -> str:
        """
        Normalize location properties focusing on postal codes and city keys.
        """
        postal = re.sub(r"\D", "", postal_code) if postal_code else ""
        city_norm = re.sub(r"[^a-z0-9]", "", city.lower()) if city else ""
        state_norm = re.sub(r"[^a-z0-9]", "", state.lower()) if state else ""
        
        # Combine normalized components into a composite location key
        return f"{postal}|{city_norm}|{state_norm}"


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
