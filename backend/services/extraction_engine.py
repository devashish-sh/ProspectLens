# backend/services/extraction_engine.py
# ProspectLens — Quick Collect Extraction Engine Service

import time
from datetime import datetime
from typing import List, Dict
from services.adapter_manager import AdapterManager

class QuickCollectExtractionEngine:
    """
    Standardizes, normalizes, and calculates metadata for in-memory extractions.
    Exposes batch statistical indicators.
    """

    @staticmethod
    def extract_listing_payload(website: str, payload: dict) -> dict:
        """
        Extracts, normalizes, and assigns missing fields/quality score to a single card payload.
        """
        adapter = AdapterManager.ADAPTER_MAP.get(website)
        if not adapter:
            return {
                "success": False,
                "error": f"Adapter for site '{website}' not loaded",
                "lead": None
            }

        start_time = time.perf_counter()
        
        try:
            extracted = adapter.extract_listing(payload)
            # Validation rule: business_name must not be empty
            if not extracted.get("business_name"):
                return {
                    "success": False,
                    "error": "Data Validation Error: Business Name is empty or missing",
                    "lead": extracted
                }

            duration = time.perf_counter() - start_time
            
            # Additional metadata tracing
            metadata = {
                "extraction_timestamp": datetime.utcnow().isoformat(),
                "extraction_duration_sec": round(duration, 4),
                "adapter_version": "1.0.0",
                "missing_fields": extracted.get("missing_fields", []),
                "quality_score": extracted.get("quality_score", 0.0)
            }
            
            return {
                "success": True,
                "lead": extracted,
                "metadata": metadata
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"System Extraction Error: {str(e)}",
                "lead": None
            }

    @staticmethod
    def extract_batch_payloads(website: str, payloads: List[dict]) -> dict:
        """
        Iterates over a list of raw DOM elements, converts them into Leads, and computes session stats.
        """
        results = []
        processed = 0
        success_count = 0
        partial_count = 0
        failed_count = 0
        total_quality_score = 0.0
        total_time = 0.0

        for p in payloads:
            processed += 1
            t_start = time.perf_counter()
            res = QuickCollectExtractionEngine.extract_listing_payload(website, p)
            t_duration = time.perf_counter() - t_start
            total_time += t_duration

            if res["success"]:
                success_count += 1
                lead_data = res["lead"]
                q_score = lead_data.get("quality_score", 0.0)
                total_quality_score += q_score
                
                # Check for partial (arbitrary threshold of quality score < 70)
                if q_score < 70.0:
                    partial_count += 1
                
                results.append({
                    "lead": lead_data,
                    "metadata": res["metadata"]
                })
            else:
                failed_count += 1
                results.append({
                    "lead": res.get("lead"),
                    "error": res["error"],
                    "metadata": {
                        "extraction_timestamp": datetime.utcnow().isoformat(),
                        "extraction_duration_sec": round(t_duration, 4),
                        "adapter_version": "1.0.0",
                        "quality_score": 0.0
                    }
                })

        avg_quality = round(total_quality_score / success_count, 1) if success_count > 0 else 0.0
        avg_time = round(total_time / processed, 4) if processed > 0 else 0.0

        return {
            "statistics": {
                "total_listings_processed": processed,
                "successful_extractions": success_count,
                "partial_extractions": partial_count,
                "failed_extractions": failed_count,
                "average_extraction_time_sec": avg_time,
                "average_quality_score": avg_quality
            },
            "results": results
        }
