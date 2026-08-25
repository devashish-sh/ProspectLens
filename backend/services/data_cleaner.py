# backend/services/data_cleaner.py
# ProspectLens — Deterministic Data Quality, Normalization & Cleansing Engine

import re
import urllib.parse
from typing import Optional, Tuple, Dict, Any, List

# Common sentinel/dummy placeholder strings produced by messy scrapers
INVALID_PLACEHOLDERS = {
    "", "n/a", "na", "none", "null", "undefined", "-", "--", "---", "nil",
    "not available", "unknown", "false", "true", "0", "0.0", "nan", "test",
    "no address", "no phone", "no email", "no website", "not provided"
}

# Standard Indian States & Union Territories
INDIAN_STATES_MAP = {
    "andaman and nicobar islands": ["andaman", "nicobar"],
    "andhra pradesh": ["andhra pradesh", "ap"],
    "arunachal pradesh": ["arunachal pradesh", "arunachal"],
    "assam": ["assam", "as"],
    "bihar": ["bihar", "br"],
    "chandigarh": ["chandigarh", "ch"],
    "chhattisgarh": ["chhattisgarh", "cg", "chhatisgarh"],
    "dadra and nagar haveli and daman and diu": ["daman", "diu", "dadra", "nagar haveli"],
    "delhi": ["delhi", "new delhi", "nct", "delhi ncr", "ncr"],
    "goa": ["goa"],
    "gujarat": ["gujarat", "gj"],
    "haryana": ["haryana", "hr"],
    "himachal pradesh": ["himachal pradesh", "himachal", "hp"],
    "jammu and kashmir": ["jammu", "kashmir", "j&k"],
    "jharkhand": ["jharkhand", "jh"],
    "karnataka": ["karnataka", "ka"],
    "kerala": ["kerala", "kl"],
    "ladakh": ["ladakh"],
    "lakshadweep": ["lakshadweep"],
    "madhya pradesh": ["madhya pradesh", "mp"],
    "maharashtra": ["maharashtra", "mh"],
    "manipur": ["manipur"],
    "meghalaya": ["meghalaya"],
    "mizoram": ["mizoram"],
    "nagaland": ["nagaland"],
    "odisha": ["odisha", "orissa", "or"],
    "puducherry": ["puducherry", "pondicherry"],
    "punjab": ["punjab", "pb"],
    "rajasthan": ["rajasthan", "rj"],
    "sikkim": ["sikkim"],
    "tamil nadu": ["tamil nadu", "tamilnadu", "tn"],
    "telangana": ["telangana", "ts", "tg"],
    "tripura": ["tripura"],
    "uttar pradesh": ["uttar pradesh", "up"],
    "uttarakhand": ["uttarakhand", "uttaranchal", "uk"],
    "west bengal": ["west bengal", "bengal", "wb"]
}

# Major commercial & industrial Indian cities
INDIAN_CITIES_LIST = [
    # Metros & Tier 1
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata", "pune", "ahmedabad",
    # Tier 2 Hubs & Industrial clusters
    "noida", "greater noida", "gurugram", "gurgaon", "faridabad", "ghaziabad", "surat", "jaipur", "lucknow",
    "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam", "patna", "vadodara", "ludhiana", "agra",
    "nashik", "meerut", "rajkot", "varanasi", "srinagar", "aurangabad", "dhanbad", "amritsar", "navi mumbai",
    "allahabad", "prayagraj", "ranchi", "howrah", "jabalpur", "gwalior", "vijayawada", "jodhpur", "raipur",
    "kota", "guwahati", "chandigarh", "solapur", "hubli", "dharwad", "bareilly", "moradabad", "mysuru", "mysore",
    "tiruppur", "gurugram", "aligarh", "jalandhar", "bhubaneswar", "salem", "warangal", "guntur", "bhiwandi",
    "saharanpur", "gorakhpur", "bikaner", "amravati", "noida", "jamshedpur", "bhilai", "cuttack", "firozabad",
    "kochi", "cochin", "nellore", "bhavnagar", "dehradun", "durgapur", "asansol", "rourkela", "nanded", "kolhapur",
    "ajmer", "akola", "gulbarga", "jamnagar", "ujjain", "loni", "siliguri", "jhansi", "ulhasnagar", "jammu",
    "sangli", "mangalore", "erode", "belgaum", "ambattur", "tirunelveli", "malegaon", "gaya", "tirupati", "udaipur",
    "kakinada", "davanagere", "kozhikode", "calicut", "panipat", "rohtak", "karnal", "sonipat", "haridwar", "rishikesh"
]


def is_valid_text(val: Optional[str]) -> bool:
    """Returns True if val is non-empty and not a known placeholder."""
    if val is None:
        return False
    cleaned = str(val).strip().lower()
    cleaned_no_punct = re.sub(r"[^\w\s]", "", cleaned)
    return bool(cleaned) and cleaned not in INVALID_PLACEHOLDERS and cleaned_no_punct not in INVALID_PLACEHOLDERS


def clean_business_name(name: Optional[str]) -> str:
    """
    Cleans raw business name:
    - Normalizes unicode whitespace and multiple spaces to a single space
    - Converts unicode dashes (–, —) to standard '-'
    - Converts smart quotes to standard quotes
    - Strips leading/trailing punctuation
    """
    if not is_valid_text(name):
        return ""
    
    n = str(name).strip()
    # Normalize unicode spaces (non-breaking space, etc.)
    n = re.sub(r"[\u00a0\u2000-\u200b\s]+", " ", n)
    # Normalize dashes and quotes
    n = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", n)
    n = re.sub(r"[\u2018\u2019]", "'", n)
    n = re.sub(r"[\u201c\u201d]", '"', n)
    # Strip leading/trailing separators
    n = n.strip(" \t\r\n,-–—|/\\.")
    return n


def normalize_name_for_comparison(name: Optional[str]) -> str:
    """
    Generates a canonical string representation for deduplication and comparison.
    Strips common legal entity suffixes and non-alphanumeric characters.
    """
    cleaned = clean_business_name(name).lower()
    if not cleaned:
        return ""

    # Remove legal entity designators
    suffixes = [
        r"\bprivate\s+limited\b", r"\bpvt\s*\.?\s*ltd\s*\.?\b", r"\bpvt\b", r"\bltd\s*\.?\b",
        r"\blimited\b", r"\bllc\b", r"\bllp\b", r"\binc\s*\.?\b", r"\bcorp\s*\.?\b",
        r"\bcorporation\b", r"\bco\s*\.?\b", r"\benterprises?\b", r"\bservices?\b",
        r"\bsolutions?\b", r"\btechnologies\b", r"\btech\b", r"\bindustries?\b"
    ]
    for s in suffixes:
        cleaned = re.sub(s, "", cleaned)

    # Keep only lowercase alphanumeric chars
    return re.sub(r"[^a-z0-9]", "", cleaned)


def clean_phone_number(phone_str: Optional[str]) -> Optional[str]:
    """
    Standardizes phone numbers into canonical formats (+91-XXXXXXXXXX or toll-free).
    Rejects dummy numbers, placeholder strings, and non-viable lengths.
    """
    if not is_valid_text(phone_str):
        return None

    # Extract all digits
    digits = re.sub(r"\D", "", str(phone_str))
    if not digits:
        return None

    # Rejection of common placeholder repeated sequences
    if re.match(r"^0{6,}$|^1{10,}$|^9{10,}$|^1234567890$", digits):
        return None

    # Toll-free numbers (1800, 1860, 1600)
    if re.match(r"^(1800|1860|1600)", digits):
        return digits[:11] if len(digits) >= 10 else digits

    # Remove leading zeros
    digits = digits.lstrip("0")
    if not digits:
        return None

    # Strip country code 91 if present and total length > 10
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[2:].lstrip("0")

    # Indian mobile / landline numbers are standard 10 digits (or 8-11 for STD)
    if len(digits) < 7:
        return None

    if len(digits) > 15:
        digits = digits[:10]

    return f"+91-{digits}"


def clean_website_url(url: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Cleans a website URL and extracts the canonical domain.
    Strips tracking params (utm_*, gclid, fbclid, ref), normalizes scheme and removes trailing slashes.
    Returns (cleaned_url, clean_domain).
    """
    if not is_valid_text(url):
        return None, None

    u = str(url).strip()
    # Reject explicit placeholder URLs
    if u.lower() in {"http://", "https://", "http://none", "https://none", "http://na", "https://na"}:
        return None, None

    # Prepend https:// if no scheme provided
    if not re.match(r"^https?://", u, re.IGNORECASE):
        u = f"https://{u}"

    try:
        parsed = urllib.parse.urlparse(u)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            scheme = "https"
            
        netloc = parsed.netloc.lower().strip()
        if not netloc:
            return None, None

        # Clean tracking query parameters
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid", "ref", "source", "trk"
        }
        query_dict = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
        filtered_query = {k: v for k, v in query_dict.items() if k.lower() not in tracking_params}
        new_query = urllib.parse.urlencode(filtered_query, doseq=True)

        # Normalize path
        path = parsed.path.rstrip("/") if parsed.path != "/" else ""

        # Construct clean URL
        reconstructed = urllib.parse.urlunparse((
            scheme,
            netloc,
            path,
            parsed.params,
            new_query,
            ""  # Strip fragment
        ))

        # Extract root/canonical domain (remove www.)
        clean_domain = re.sub(r"^www\.", "", netloc).split(":")[0]

        return reconstructed, clean_domain
    except Exception:
        return None, None


def clean_address_text(address: Optional[str]) -> Optional[str]:
    """
    Standardizes raw address strings:
    - Collapses multiple commas and extra whitespace
    - Normalizes separators and strips trailing/leading punctuation
    """
    if not is_valid_text(address):
        return None

    a = str(address).strip()
    # Normalize unicode whitespace
    a = re.sub(r"[\u00a0\u2000-\u200b\s]+", " ", a)
    # Collapse multiple commas and semicolons with surrounding spaces
    a = re.sub(r"(\s*[,;]\s*)+", ", ", a)
    # Collapse multiple spaces
    a = re.sub(r"\s+", " ", a)
    # Strip leading/trailing punctuation
    a = a.strip(" ,;.-–—")
    return a if a else None


def extract_pin_code(text_val: Optional[str]) -> Optional[str]:
    """Extracts a valid 6-digit Indian PIN code (100000 - 999999)."""
    if not is_valid_text(text_val):
        return None
    match = re.search(r"\b([1-9][0-9]{5})\b", str(text_val))
    return match.group(1) if match else None


def extract_city_and_state(address: Optional[str], city_hint: Optional[str] = None, state_hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Heuristically extracts standardized City and State from address and hints
    using the comprehensive Indian Cities and States dictionary.
    """
    found_city = None
    found_state = None

    if is_valid_text(city_hint):
        c_hint = str(city_hint).strip().lower()
        if c_hint in INDIAN_CITIES_LIST:
            found_city = c_hint.title()
        else:
            found_city = str(city_hint).strip().title()

    if is_valid_text(state_hint):
        s_hint = str(state_hint).strip().lower()
        for state_name, triggers in INDIAN_STATES_MAP.items():
            if s_hint == state_name or s_hint in triggers:
                found_state = state_name.title()
                break
        if not found_state:
            found_state = str(state_hint).strip().title()

    if (not found_city or not found_state) and is_valid_text(address):
        addr_lower = str(address).lower()

        # Search for city in address
        if not found_city:
            for city in INDIAN_CITIES_LIST:
                if re.search(r"\b" + re.escape(city) + r"\b", addr_lower):
                    found_city = city.title()
                    break

        # Search for state in address
        if not found_state:
            for state_name, triggers in INDIAN_STATES_MAP.items():
                for trigger in triggers:
                    if re.search(r"\b" + re.escape(trigger) + r"\b", addr_lower):
                        found_state = state_name.title()
                        break
                if found_state:
                    break

    return found_city, found_state


def compute_clean_dedup_hash(business_name: str, source_site: str, address: Optional[str] = None) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for duplicate detection.
    Normalizes business name, source site, and address to prevent false duplicate splits
    caused by cosmetic formatting variations.
    """
    import hashlib
    norm_name = normalize_name_for_comparison(business_name) or clean_business_name(business_name).lower()
    norm_site = str(source_site).strip().lower()
    
    # Normalize address components
    clean_addr = clean_address_text(address) or ""
    norm_addr = re.sub(r"[^a-z0-9]", "", clean_addr.lower())

    hash_input = f"{norm_name}|{norm_site}|{norm_addr}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
