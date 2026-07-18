# backend/adapters/googlemaps.py
# ProspectLens — Google Maps Extraction Adapter

from adapters.base import BaseAdapter

class GoogleMapsAdapter(BaseAdapter):
    def validate_page(self, url: str) -> bool:
        url = url.lower()
        return "google.com/maps" in url or "google.co.in/maps" in url or "maps.google" in url

    def supports_quick_collect(self) -> bool:
        return True

    def supports_deep_collect(self) -> bool:
        return True

    def get_site_information(self) -> dict:
        return {
            "source_key": "googlemaps",
            "display_name": "Google Maps",
            "adapter_class": "GoogleMapsAdapter"
        }

    def get_collection_configuration(self) -> dict:
        return {
            "max_rpm": 60,
            "recommended_delay": 1.0,
            "retry_count": 3,
            "timeout": 30,
            "concurrent_limit": 5
        }

    def is_search_results_page(self, url: str) -> bool:
        url = url.lower()
        return "/maps/search/" in url

    def is_detail_page(self, url: str) -> bool:
        url = url.lower()
        return "/maps/place/" in url

    def is_supported_page(self, url: str) -> bool:
        return self.is_search_results_page(url) or self.is_detail_page(url)

    def get_page_type(self, url: str) -> str:
        url = url.lower()
        if self.is_search_results_page(url):
            return "Search Results"
        if self.is_detail_page(url):
            return "Business Detail"
        if "/accounts/" in url or "signin" in url:
            return "Login"
        if "/settings" in url:
            return "Settings"
        if url.endswith("/maps") or url.endswith("/maps/") or url.endswith("google.com/") or url.endswith("google.co.in/"):
            return "Home"
        return "Unknown"

    def validate_collection_page(self, url: str) -> dict:
        page_type = self.get_page_type(url)
        is_search = page_type == "Search Results"
        return {
            "is_valid": is_search,
            "page_type": page_type,
            "recognition_method": "URL Pattern Matching",
            "reason": None if is_search else f"Page type '{page_type}' is not a valid Quick Collect search results page."
        }

    def discover_listings(self, payloads: list) -> list:
        # Filter out sponsored, ads, skeletons, etc.
        discovered = []
        for p in payloads:
            if p.get("is_ad") or p.get("is_sponsored") or p.get("is_skeleton"):
                continue
            discovered.append(p)
        return discovered

    def get_listing_count(self, payloads: list) -> int:
        return len(self.discover_listings(payloads))

    def get_listing_by_index(self, payloads: list, index: int) -> Optional[dict]:
        filtered = self.discover_listings(payloads)
        if 0 <= index < len(filtered):
            return filtered[index]
        return None

    def is_listing_visible(self, payload: dict) -> bool:
        return payload.get("visible_state", True)

    def refresh_listing_collection(self, existing: list, incoming: list) -> list:
        # Deduplicate on dom_reference or listing_id
        existing_map = {e.get("dom_reference"): e for e in existing}
        for item in incoming:
            dom_ref = item.get("dom_reference")
            if dom_ref in existing_map:
                # Update visibility and positions
                existing_map[dom_ref]["visible_state"] = item.get("visible_state", True)
                existing_map[dom_ref]["listing_position"] = item.get("listing_position", 0)
                existing_map[dom_ref]["page_position"] = item.get("page_position", 0)
            else:
                existing.append(item)
        return existing

    def calculate_quality_score(self, extracted: dict) -> float:
        primary_fields = [
            "business_name", "primary_phone", "website", "address", 
            "rating", "review_count", "category", "listing_url", 
            "image_url", "description"
        ]
        filled = 0
        for f in primary_fields:
            if extracted.get(f) is not None and extracted.get(f) != "":
                filled += 1
        return round((filled / len(primary_fields)) * 100.0, 1)

    def extract_listing(self, raw_data: dict) -> dict:
        import re
        # Standard Normalizations
        biz_name = (raw_data.get("business_name") or raw_data.get("name") or "").strip()
        biz_name = re.sub(r'\s+', ' ', biz_name) if biz_name else ""
        
        phone = (raw_data.get("primary_phone") or raw_data.get("phone") or "").strip()
        phone = re.sub(r'[^0-9+]', '', phone) if phone else ""
        
        web = (raw_data.get("website") or "").strip().lower()
        if web and not web.startswith("http"):
            web = "http://" + web
            
        list_url = (raw_data.get("listing_url") or "").strip()
        addr = (raw_data.get("address") or "").strip()
        
        rating_raw = raw_data.get("rating")
        try:
            rating = round(float(rating_raw), 1) if rating_raw is not None else None
        except Exception:
            rating = None
            
        reviews_raw = raw_data.get("review_count") or raw_data.get("reviews")
        try:
            reviews = int(reviews_raw) if reviews_raw is not None else None
        except Exception:
            reviews = None

        is_verified = bool(raw_data.get("is_verified") or raw_data.get("verification_badge"))
        
        biz_status = (raw_data.get("business_status") or raw_data.get("status") or "").strip()
        if biz_status.lower() in ["open", "closed", "temporarily closed"]:
            biz_status = biz_status.title()
        else:
            biz_status = None
            
        desc = (raw_data.get("description") or raw_data.get("short_description") or "").strip()
        img = (raw_data.get("image_url") or "").strip()
        category = (raw_data.get("category") or raw_data.get("type") or "").strip()
        biz_type = (raw_data.get("business_type") or "").strip()

        extracted = {
            "business_name": biz_name if biz_name else None,
            "primary_phone": phone if phone else None,
            "website": web if web else None,
            "listing_url": list_url if list_url else None,
            "address": addr if addr else None,
            "rating": rating,
            "review_count": reviews,
            "verification_badge": is_verified,
            "business_status": biz_status,
            "description": desc if desc else None,
            "image_url": img if img else None,
            "category": category if category else None,
            "business_type": biz_type if biz_type else None,
            "source_website": self.get_site_information()["source_key"],
            "search_keyword": (raw_data.get("search_keyword") or "").strip()
        }

        extracted["quality_score"] = self.calculate_quality_score(extracted)
        missing = [k for k, v in extracted.items() if v is None]
        extracted["missing_fields"] = missing
        
        return extracted
