# backend/services/merge_confidence_engine.py
# ProspectLens — Intelligent Merge Confidence Engine

import re
import difflib
from database.models import Lead
from config import MERGE_CONFIDENCE_WEIGHTS, MERGE_ACTION_THRESHOLDS

class MergeConfidenceEngine:
    """
    Intelligently compares two leads and returns a similarity score and recommendation.
    Enables future Deep Collect enrichment to align with existing Capsule/CRM leads.
    """

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        Cleans company name: lowercase, removes punctuation and common suffixes.
        """
        if not name:
            return ""
        name = name.lower()
        # Remove non-alphanumeric chars
        name = re.sub(r'[^a-z0-9\s]', '', name)
        # Strip common business suffixes
        suffixes = [
            r'\bpvt ltd\b', r'\bltd\b', r'\binc\b', r'\bco\b',
            r'\bservices\b', r'\bcorp\b', r'\bcorporation\b', r'\bindia\b'
        ]
        for suff in suffixes:
            name = re.sub(suff, '', name)
        return " ".join(name.split())

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Cleans phone: extracts only digits.
        """
        if not phone:
            return ""
        return re.sub(r'\D', '', phone)

    @staticmethod
    def normalize_website(url: str) -> str:
        """
        Cleans URL: strips protocols, subdomains (www), and trailing slashes.
        """
        if not url:
            return ""
        url = url.lower().strip()
        url = re.sub(r'^https?://', '', url)
        url = re.sub(r'^www\.', '', url)
        return url.rstrip('/')

    @staticmethod
    def compare_leads(lead_a: Lead, lead_b: Lead, weights: dict = None, thresholds: dict = None) -> dict:
        """
        Computes the matching profile and confidence score between two leads.
        """
        w = weights or MERGE_CONFIDENCE_WEIGHTS
        t = thresholds or MERGE_ACTION_THRESHOLDS

        matching_fields = []
        different_fields = []
        missing_fields = []
        score = 0.0

        # 1. Company Name Match (Weight: 40%)
        name_a = MergeConfidenceEngine.normalize_company_name(lead_a.business_name or "")
        name_b = MergeConfidenceEngine.normalize_company_name(lead_b.business_name or "")
        if not name_a or not name_b:
            missing_fields.append("company_name")
        else:
            similarity = difflib.SequenceMatcher(None, name_a, name_b).ratio()
            if similarity >= 0.85:
                matching_fields.append("company_name")
                score += w.get("company_name", 0.40) * similarity
            elif similarity >= 0.50:
                score += w.get("company_name", 0.40) * similarity * 0.50
                different_fields.append("company_name")
            else:
                different_fields.append("company_name")

        # 2. Phone Match (Weight: 30%)
        phone_a = MergeConfidenceEngine.normalize_phone(lead_a.primary_phone or "")
        phone_b = MergeConfidenceEngine.normalize_phone(lead_b.primary_phone or "")
        if not phone_a or not phone_b:
            missing_fields.append("phone")
        else:
            last_10_a = phone_a[-10:] if len(phone_a) >= 10 else phone_a
            last_10_b = phone_b[-10:] if len(phone_b) >= 10 else phone_b
            if last_10_a == last_10_b:
                matching_fields.append("phone")
                score += w.get("phone", 0.30)
            else:
                different_fields.append("phone")

        # 3. Website Match (Weight: 15%)
        web_a = MergeConfidenceEngine.normalize_website(lead_a.website or "")
        web_b = MergeConfidenceEngine.normalize_website(lead_b.website or "")
        if not web_a or not web_b:
            missing_fields.append("website")
        else:
            if web_a == web_b:
                matching_fields.append("website")
                score += w.get("website", 0.15)
            else:
                different_fields.append("website")

        # 4. Location Match (Weight: 10%)
        addr_a = (lead_a.address or "").lower().strip()
        addr_b = (lead_b.address or "").lower().strip()
        if not addr_a or not addr_b:
            missing_fields.append("location")
        else:
            addr_similarity = difflib.SequenceMatcher(None, addr_a, addr_b).ratio()
            city_match = lead_a.city and lead_b.city and lead_a.city.lower() == lead_b.city.lower()
            if addr_similarity >= 0.75 or city_match:
                matching_fields.append("location")
                score += w.get("location", 0.10) * max(addr_similarity, 0.8 if city_match else 0.0)
            else:
                different_fields.append("location")

        # 5. Email Match (Weight: 5%)
        email_a = (lead_a.primary_email or "").lower().strip()
        email_b = (lead_b.primary_email or "").lower().strip()
        if not email_a or not email_b:
            missing_fields.append("email")
        else:
            if email_a == email_b:
                matching_fields.append("email")
                score += w.get("email", 0.05)
            else:
                different_fields.append("email")

        # Convert score to percentage
        final_percentage = round(score * 100.0, 1)

        # Decide Action Recommendation
        if final_percentage >= t.get("merge", 75.0):
            recommended_action = "Merge"
        elif final_percentage >= t.get("review", 40.0):
            recommended_action = "Review"
        else:
            recommended_action = "Create New"

        return {
            "lead_a_id": lead_a.lead_id,
            "lead_b_id": lead_b.lead_id,
            "confidence_score": final_percentage,
            "matching_fields": matching_fields,
            "different_fields": different_fields,
            "missing_fields": missing_fields,
            "recommended_action": recommended_action
        }
