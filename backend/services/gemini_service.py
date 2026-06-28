# backend/services/gemini_service.py
# ProspectLens — Central Gemini API Client
#
# This is the SKELETON for Step 2.
# Full implementation happens in Step 3 (normalize_lead_data)
# and Steps 7-9 (get_session_behavior_profile for Deep Collect).
#
# NOTE: Uses the NEW google.genai SDK (not the deprecated google.generativeai)
# This eliminates the FutureWarning you saw during environment setup.

import os
import json
from dotenv import load_dotenv

# Load GEMINI_API_KEY from backend/.env
load_dotenv()

# ==============================================================================
# SDK IMPORT — new package
# If this throws ModuleNotFoundError, run:
#   pip install google-genai
# ==============================================================================

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[GeminiService] WARNING: google-genai package not installed. Run: pip install google-genai")


# ==============================================================================
# CLIENT INITIALIZATION
# ==============================================================================

def _get_client():
    """Returns an initialized Gemini client. Raises if API key is missing."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("[GeminiService] GEMINI_API_KEY not found in .env file")
    if not GEMINI_AVAILABLE:
        raise ImportError("[GeminiService] google-genai package not installed")
    return genai.Client(api_key=api_key)


MODEL = "gemini-2.0-flash"      # Free tier: 15 req/min, 1M tokens/day — sufficient for all Phase 1 use


# ==============================================================================
# INTEGRATION 1 — Session Behavior Profile
# Called ONCE when a Deep Collect job starts.
# Generates a full human-like delay sequence for the entire session.
# Implemented fully in Step 7 (IndiaMART adapter).
# ==============================================================================

async def get_session_behavior_profile(listing_count: int, site: str) -> dict:
    """
    Returns a dict with delay arrays and pause indices for a Deep Collect session.

    Example return value:
    {
        "delays": [4.2, 6.8, 5.1, 7.3, ...],        ← one per listing
        "heavy_pause_indices": [8, 17, 25],           ← extra long pauses here
        "heavy_pause_durations": [18.2, 14.7, 21.3], ← duration of each heavy pause
        "scroll_hesitations": [1.2, 0.8, 2.1, ...]   ← scroll pause per listing
    }
    """
    # TODO: Implement in Step 7
    # Placeholder returns a safe default profile so backend doesn't crash before Step 7
    import random
    delays = [round(random.uniform(3.0, 9.0), 1) for _ in range(listing_count)]
    return {
        "delays": delays,
        "heavy_pause_indices": list(range(8, listing_count, 10)),
        "heavy_pause_durations": [15.0] * len(range(8, listing_count, 10)),
        "scroll_hesitations": [round(random.uniform(0.5, 2.0), 1) for _ in range(listing_count)]
    }


# ==============================================================================
# INTEGRATION 2 — Data Normalization
# Called during /api/ingest to clean messy Indian directory data.
# Extracts city/state/PIN from raw address. Standardizes phone numbers.
# Implemented fully in Step 3 (LeadService).
# ==============================================================================

async def normalize_lead_data(raw_lead: dict) -> dict:
    """
    Cleans and normalizes a raw lead dict from the extension.
    Returns a dict with structured address fields and standardized phone.

    Input:  {"business_name": "ABC Interiors", "address": "Plot 5, Sec 18, Noida UP 201301", "phone": "9876543210"}
    Output: {"business_name": "ABC Interiors", "address": "...", "city": "Noida", "state": "Uttar Pradesh", "postal_code": "201301", "phone": "+91-9876543210"}
    """
    # TODO: Implement fully in Step 3
    # Placeholder passes through raw data unchanged
    return raw_lead


# ==============================================================================
# INTEGRATION 3 — Contact Extraction Assist
# Called by WebsiteExtractorService for ambiguous contact page layouts.
# Implemented fully in Step 10 (Website Extractor).
# ==============================================================================

async def extract_contacts_from_html(html_snippet: str) -> dict:
    """
    Given raw HTML from a company's contact page, returns structured contact info.

    Output: {"emails": [...], "phones": [...], "whatsapp": [...], "social": {...}}
    """
    # TODO: Implement in Step 10
    return {"emails": [], "phones": [], "whatsapp": [], "social": {}}


# ==============================================================================
# HEALTH CHECK
# Called by GET /health to verify Gemini API key is working.
# ==============================================================================

def check_gemini_connection() -> dict:
    """
    Returns {"status": "ok"} if Gemini API key is valid and reachable.
    Returns {"status": "error", "message": "..."} if not.
    """
    try:
        client = _get_client()
        # Minimal test call — just verifies the key works
        response = client.models.generate_content(
            model=MODEL,
            contents="Reply with the single word: ok"
        )
        return {"status": "ok", "model": MODEL}
    except Exception as e:
        return {"status": "error", "message": str(e)}