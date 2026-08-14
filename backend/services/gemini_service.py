# backend/services/gemini_service.py
# ProspectLens — Central Gemini API Client with Local Fallbacks
#
# This file handles all calls to the Gemini API (google-genai SDK).
# In case of API quota exhaustion (429), timeouts, or missing keys,
# it falls back to local heuristic/regex algorithms to ensure zero-crash operations.

import os
import re
import json
import random
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load GEMINI_API_KEY from backend/.env relative to this file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[GeminiService] WARNING: google-genai package not installed. Run: pip install google-genai")

MODEL = "gemini-2.0-flash"

def _get_client():
    """Returns initialized genai Client, or None if key is missing/invalid."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[GeminiService] Error initializing client: {e}")
        return None


# ==============================================================================
# PYDANTIC SCHEMAS FOR STRUCTURED JSON OUTPUT
# ==============================================================================

class BehaviorProfile(BaseModel):
    delays: List[float] = Field(description="Delay in seconds before loading each listing details page")
    heavy_pause_indices: List[int] = Field(description="Zero-indexed listing indices where the crawler should take a heavy break")
    heavy_pause_durations: List[float] = Field(description="Duration in seconds for each heavy break")
    scroll_hesitations: List[float] = Field(description="Extra delay in seconds during scroll simulation for each listing")

class NormalizedData(BaseModel):
    business_name: str
    phone: Optional[str] = Field(None, description="Standardized phone number in format '+91-XXXXXXXXXX'")
    city: Optional[str] = Field(None, description="Clean city name, e.g. 'Noida'")
    state: Optional[str] = Field(None, description="Clean Indian State, e.g. 'Uttar Pradesh'")
    postal_code: Optional[str] = Field(None, description="6-digit PIN code")
    contact_person: Optional[str] = Field(None, description="Clean contact person name")
    category: Optional[str] = Field(None, description="Clean business category/service segment")

class ExtractedContacts(BaseModel):
    emails: List[str] = Field(default_factory=list, description="All email addresses found")
    phones: List[str] = Field(default_factory=list, description="All phone numbers found, standardized to +91-XXXXXXXXXX if Indian")
    whatsapp: List[str] = Field(default_factory=list, description="WhatsApp numbers or chat link values")
    linkedin: Optional[str] = Field(None, description="Company LinkedIn page URL")
    instagram: Optional[str] = Field(None, description="Company Instagram handle or URL")


# ==============================================================================
# INTEGRATION 1 — Session Behavior Profile
# ==============================================================================

async def get_session_behavior_profile(listing_count: int, site: str) -> dict:
    """
    Returns a dict with delay arrays and pause indices.
    Tries Gemini with schema; falls back to random uniform ranges if Gemini fails.
    """
    client = _get_client()
    if client:
        try:
            prompt = (
                f"Create a human-like scraping delay profile for visiting {listing_count} listings on {site}. "
                "Delays should range between 3.0 and 8.0 seconds. Include a heavy pause (10.0 to 20.0s) every 7-12 pages. "
                "Scroll hesitations should be between 0.4 and 1.8 seconds."
            )
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BehaviorProfile,
                    temperature=0.7
                )
            )
            profile_data = json.loads(response.text)
            # Validate lengths
            if len(profile_data.get("delays", [])) >= listing_count:
                return profile_data
        except Exception as e:
            print(f"[GeminiService] get_session_behavior_profile failed: {e}. Using local fallback.")

    # Local Fallback
    delays = [round(random.uniform(4.0, 9.0), 1) for _ in range(listing_count)]
    scroll_hesitations = [round(random.uniform(0.5, 1.8), 1) for _ in range(listing_count)]
    heavy_pause_indices = []
    heavy_pause_durations = []
    
    current_index = random.randint(7, 12)
    while current_index < listing_count:
        heavy_pause_indices.append(current_index)
        heavy_pause_durations.append(round(random.uniform(12.0, 20.0), 1))
        current_index += random.randint(7, 12)

    return {
        "delays": delays,
        "heavy_pause_indices": heavy_pause_indices,
        "heavy_pause_durations": heavy_pause_durations,
        "scroll_hesitations": scroll_hesitations
    }


# ==============================================================================
# INTEGRATION 2 — Data Normalization (Gemini cleans address and standardizes phone)
# ==============================================================================

async def normalize_lead_data(raw_lead: dict) -> dict:
    """
    Cleans and normalizes raw lead data.
    Standardizes phone numbers to +91-XXXXXXXXXX.
    Parses city, state, postal code from raw address fields.
    """
    client = _get_client()
    if client:
        try:
            prompt = (
                "Normalize the following Indian B2B lead info. Extract city, state (full name, e.g. 'Uttar Pradesh'), "
                "and PIN code from the raw address. If the phone number is provided, convert it to standard format '+91-XXXXXXXXXX'. "
                f"Lead Details: {json.dumps(raw_lead)}"
            )
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=NormalizedData,
                    temperature=0.1
                )
            )
            normalized = json.loads(response.text)
            
            # Merge normalized fields back
            result = raw_lead.copy()
            for key in ["business_name", "phone", "city", "state", "postal_code", "contact_person", "category"]:
                val = normalized.get(key)
                if val:
                    result[key] = val
            return result
        except Exception as e:
            print(f"[GeminiService] normalize_lead_data failed: {e}. Using local heuristics.")

    # Local Heuristic Fallback
    return local_normalize_lead_data(raw_lead)


def local_normalize_lead_data(raw_lead: dict) -> dict:
    """Fallback parser for normalizing lead data without API access."""
    result = raw_lead.copy()
    
    # 1. Phone number standardization
    phone_val = raw_lead.get("phone")
    if phone_val:
        result["phone"] = clean_indian_phone(phone_val)

    # 2. Extract PIN code (6 digits)
    address = raw_lead.get("address", "") or ""
    pin_match = re.search(r"\b([1-9][0-9]{5})\b", address)
    if pin_match:
        result["postal_code"] = pin_match.group(1)

    # 3. Heuristic City and State extraction from address
    city_list = ["noida", "delhi", "gurgaon", "mumbai", "bangalore", "pune", "chennai", "kolkata", "hyderabad", "ahmedabad", "jaipur", "ghaziabad", "faridabad"]
    states_map = {
        "uttar pradesh": ["uttar pradesh", "up"],
        "haryana": ["haryana", "hr"],
        "delhi": ["delhi", "nct"],
        "maharashtra": ["maharashtra", "mh"],
        "karnataka": ["karnataka", "ka"],
        "tamil nadu": ["tamil nadu", "tn"],
        "west bengal": ["west bengal", "wb"],
        "gujarat": ["gujarat", "gj"]
    }
    
    addr_lower = address.lower()
    
    # Detect city
    if not raw_lead.get("city"):
        for city in city_list:
            if re.search(r"\b" + re.escape(city) + r"\b", addr_lower):
                result["city"] = city.capitalize()
                break

    # Detect state
    if not raw_lead.get("state"):
        for state_name, triggers in states_map.items():
            for trigger in triggers:
                if re.search(r"\b" + re.escape(trigger) + r"\b", addr_lower):
                    result["state"] = state_name.title()
                    break
            if result.get("state"):
                break

    return result


def clean_indian_phone(phone_str: str) -> str:
    """Standardizes an Indian phone string.
    Removes leading country code '91' and/or leading '0', allows up to 30 digits,
    and prepends '+91-' to the final number. Preserves toll-free numbers."""
    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone_str)
    
    if not digits:
        return phone_str
        
    # Check if it is a toll-free number
    if re.match(r"^(1800|1860|1600)", digits):
        return digits

    # Strip any leading zeros
    digits = digits.lstrip("0")
        
    # Remove '91' country code prefix if present
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[2:]
        # Strip leading zeros again (e.g. if original was 91-0888...)
        digits = digits.lstrip("0")
        
    if not digits:
        return phone_str
        
    # Limit maximum length of final digits to 30
    digits = digits[:30]
    
    return f"+91-{digits}"


# ==============================================================================
# INTEGRATION 3 — Contact Extraction Assist
# ==============================================================================

async def extract_contacts_from_html(html_snippet: str) -> dict:
    """
    Given raw HTML from a contact page, returns structured contacts.
    Falls back to regex-based parser if Gemini fails.
    """
    client = _get_client()
    if client:
        try:
            # Truncate input snippet to save tokens
            truncated_html = html_snippet[:15000]
            prompt = (
                "Extract email addresses, phone numbers, WhatsApp, and social media links "
                f"from this contact page HTML snippet:\n{truncated_html}"
            )
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedContacts,
                    temperature=0.1
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[GeminiService] extract_contacts_from_html failed: {e}. Using regex fallback.")

    # Regex Fallback
    emails = list(set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", html_snippet)))
    
    # Simple Indian mobile regex (looks for 10 consecutive digits or separators)
    raw_phones = re.findall(r"\b(?:(?:\+|0{0,2})91[\s\-]*)?[6-9]\d{9}\b", html_snippet)
    cleaned_phones = list(set([clean_indian_phone(p) for p in raw_phones]))
    
    # Find social links in href attributes
    linkedin_matches = re.findall(r"href=[\"'](https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-\_]+)[\"']", html_snippet)
    insta_matches = re.findall(r"href=[\"'](https?://(?:www\.)?instagram\.com/[A-Za-z0-9\-\_\.]+)[\"']", html_snippet)
    whatsapp_matches = re.findall(r"href=[\"'](https?://api\.whatsapp\.com/send\?phone=\d+|https?://wa\.me/\d+)[\"']", html_snippet)

    return {
        "emails": emails,
        "phones": cleaned_phones,
        "whatsapp": list(set(whatsapp_matches)),
        "linkedin": linkedin_matches[0] if linkedin_matches else None,
        "instagram": insta_matches[0] if insta_matches else None
    }


# ==============================================================================
# HEALTH CHECK
# ==============================================================================

def check_gemini_connection() -> dict:
    """Verifies that API connection works."""
    try:
        client = _get_client()
        if not client:
            return {"status": "error", "message": "No API key configured"}
        response = client.models.generate_content(
            model=MODEL,
            contents="Reply with: ok"
        )
        if "ok" in response.text.lower():
            return {"status": "ok", "model": MODEL}
        return {"status": "error", "message": "Unexpected response: " + response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}