# backend/config.py
# ProspectLens — Centralized Backend Configurations & Constants

# Supported website directories/scrapers
SUPPORTED_WEBSITES = ["googlemaps", "indiamart", "justdial", "tradeindia"]

# Valid workflow statuses for leads in review capsules
VALID_CAPSULE_STATUSES = [
    "New",
    "Incomplete",
    "Enriched",
    "Reviewed",
    "Approved",
    "Moved to Main Leads",
    "Rejected",
    "Duplicate",
    "Needs Review"
]

# Hierarchical Navigation Routing Flow Structure
NAVIGATION_FLOW = {
    "flow": [
        {
            "step": 1,
            "name": "Popup",
            "description": "Chrome Extension Popup entry point containing active status toggles.",
            "route": "/popup"
        },
        {
            "step": 2,
            "name": "Data Capsule",
            "description": "Website-specific isolated review capsule holding unapproved leads.",
            "route": "/capsule/{source_site}"
        },
        {
            "step": 3,
            "name": "Dashboard",
            "description": "Main CRM layout showing stats and the master approved leads table.",
            "route": "/dashboard"
        },
        {
            "step": 4,
            "name": "Selected Website",
            "description": "Filtered workspace displaying leads gathered from a single website.",
            "route": "/dashboard?source={source_site}"
        },
        {
            "step": 5,
            "name": "Listing View",
            "description": "Detailed modal or page showing full contact and business information for a single lead.",
            "route": "/leads/{lead_id}"
        }
    ]
}
