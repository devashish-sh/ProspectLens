# backend/adapters/base.py
# ProspectLens — Reusable Adapter Interface

from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    """
    Abstract Base Class defining the interface for all website source adapters.
    """

    @abstractmethod
    def validate_page(self, url: str) -> bool:
        """
        Validates if the url matches the expected format for this adapter.
        """
        pass

    @abstractmethod
    def supports_quick_collect(self) -> bool:
        """
        Returns true if this website supports quick collect.
        """
        pass

    @abstractmethod
    def supports_deep_collect(self) -> bool:
        """
        Returns true if this website supports deep collect.
        """
        pass

    @abstractmethod
    def get_site_information(self) -> dict:
        """
        Returns basic identification metadata about the adapter.
        """
        pass

    @abstractmethod
    def get_collection_configuration(self) -> dict:
        """
        Returns collection constraints (concurrency limit, timeouts, delays).
        """
        pass

    @abstractmethod
    def is_search_results_page(self, url: str) -> bool:
        """
        Returns true if the URL points to a listing search results page.
        """
        pass

    @abstractmethod
    def is_detail_page(self, url: str) -> bool:
        """
        Returns true if the URL points to an individual profile page.
        """
        pass

    @abstractmethod
    def is_supported_page(self, url: str) -> bool:
        """
        Returns true if the URL is supported for any type of collection.
        """
        pass

    @abstractmethod
    def get_page_type(self, url: str) -> str:
        """
        Returns string classification of the URL (Search Results, Business Detail, etc.).
        """
        pass

    @abstractmethod
    def validate_collection_page(self, url: str) -> dict:
        """
        Validates page context and returns structured classification metadata.
        """
        pass

    @abstractmethod
    def discover_listings(self, payloads: list) -> list:
        """
        Filters out invalid listings (ads, sponsored, hidden elements) and returns discoverable records.
        """
        pass

    @abstractmethod
    def get_listing_count(self, payloads: list) -> int:
        """
        Returns count of discoverable listings.
        """
        pass

    @abstractmethod
    def get_listing_by_index(self, payloads: list, index: int) -> Optional[dict]:
        """
        Returns listing payload at given index.
        """
        pass

    @abstractmethod
    def is_listing_visible(self, payload: dict) -> bool:
        """
        Returns true if the listing element is currently visible in viewport.
        """
        pass

    @abstractmethod
    def refresh_listing_collection(self, existing: list, incoming: list) -> list:
        """
        Merges new listings, handles infinite scroll updates, and refines positions.
        """
        pass

    @abstractmethod
    def extract_listing(self, raw_data: dict) -> dict:
        """
        Extracts visible fields, normalizes them, validates data, and returns a standardized lead dictionary.
        """
        pass

    @abstractmethod
    def calculate_quality_score(self, extracted: dict) -> float:
        """
        Computes extraction completeness quality score (0 to 100).
        """
        pass
