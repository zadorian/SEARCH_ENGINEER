#!/usr/bin/env python3
"""
UnifiedAleph - OCCRP Aleph API Integration
Returns ALL results from different datasets without deduplication
Each Aleph result can contain different information from different sources!
"""

import requests
import os
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class UnifiedAleph:
    """
    Unified Aleph API client that returns ALL results without deduplication
    Multiple results for the same entity contain different information from different datasets!
    """

    def __init__(self):
        self.api_key = os.getenv('ALEPH_API_KEY', '1c0971afa4804c2aafabb125c79b275e')
        self.base_url = "https://aleph.occrp.org/api/2"
        self.headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Accept": "application/json"
        }

    def search_entity(
        self,
        query: str,
        country: Optional[str] = None,
        schema: str = "Company",
        limit: int = 100  # Get MORE results by default
    ) -> Dict[str, Any]:
        """
        Search Aleph and return ALL results - NO DEDUPLICATION!

        Each result from different datasets contains unique information:
        - Sanctions lists
        - Leaks databases (Panama Papers, Paradise Papers, etc.)
        - PEP databases
        - Corporate registries
        - Court records
        - Investigative collections

        WE NEED ALL OF THEM!
        """
        try:
            # Build search parameters
            params = {
                "q": query,
                "limit": limit,  # Get many results
                "facet": "collection_id",  # Show which dataset each result comes from
                "facet": "countries",
                "facet": "schema"
            }

            # Add schema filter if specified
            if schema:
                params["filter:schema"] = schema

            # Add country filter if specified
            if country:
                # Map country codes
                country_upper = country.upper()
                if len(country) == 2:
                    params["filter:countries"] = country_upper
                elif country_upper in ['USA', 'UNITED STATES']:
                    params["filter:countries"] = "US"
                elif country_upper in ['GBR', 'UNITED KINGDOM', 'UK']:
                    params["filter:countries"] = "GB"

            # Execute search
            response = requests.get(
                f"{self.base_url}/entities",
                params=params,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                # DO NOT DEDUPLICATE! Each result is valuable!
                # Enrich each result with source information
                for result in results:
                    # Add dataset/collection info to each result
                    collection_id = result.get("collection_id")
                    if collection_id:
                        collection_info = self._get_collection_info(collection_id)
                        result["_source_dataset"] = collection_info

                    # Add highlights to show what matched
                    result["_match_highlights"] = result.get("highlight", {})

                    # Keep ALL properties - different datasets have different fields
                    props = result.get("properties", {})

                    # Extract key identifiers that might differ across datasets
                    result["_identifiers"] = {
                        "registration_number": props.get("registrationNumber", []),
                        "tax_number": props.get("taxNumber", []),
                        "lei": props.get("leiCode", []),
                        "opencorporates_url": props.get("opencorporatesUrl", []),
                        "wikipedia_url": props.get("wikipediaUrl", []),
                        "website": props.get("website", []),
                        "email": props.get("email", []),
                        "phone": props.get("phone", [])
                    }

                    # Keep sanctions and PEP status from each source
                    result["_risk_indicators"] = {
                        "sanctions": props.get("sanctions", []),
                        "pep_status": props.get("politicalExposure", []),
                        "notes": props.get("notes", []),
                        "program": props.get("program", []),
                        "reason": props.get("reason", [])
                    }

                return {
                    "ok": True,
                    "results": results,  # ALL results, no deduplication!
                    "total": data.get("total", len(results)),
                    "facets": data.get("facets", {}),
                    "query": query,
                    "source": "aleph"
                }

            elif response.status_code == 401:
                return {
                    "ok": False,
                    "error": "Authentication failed - check API key",
                    "source": "aleph"
                }
            else:
                return {
                    "ok": False,
                    "error": f"API error: {response.status_code}",
                    "source": "aleph"
                }

        except Exception as e:
            logger.error(f"Aleph search error: {str(e)}")
            return {
                "ok": False,
                "error": str(e),
                "source": "aleph"
            }

    def _get_collection_info(self, collection_id: str) -> Dict[str, str]:
        """Get information about which dataset/collection this result comes from"""
        # Common Aleph collections - helps identify the source
        collections = {
            "sanctions": "Sanctions Lists",
            "pep": "Politically Exposed Persons",
            "leak": "Leaked Documents",
            "panama": "Panama Papers",
            "paradise": "Paradise Papers",
            "pandora": "Pandora Papers",
            "bahamas": "Bahamas Leaks",
            "offshore": "Offshore Leaks",
            "icij": "ICIJ Database",
            "opensanctions": "OpenSanctions",
            "everypolitician": "EveryPolitician",
            "interpol": "INTERPOL Notices",
            "worldbank": "World Bank Debarred",
            "ukraine": "Ukraine Datasets",
            "russia": "Russia Datasets"
        }

        # Try to identify the collection
        collection_lower = str(collection_id).lower()
        for key, name in collections.items():
            if key in collection_lower:
                return {
                    "id": collection_id,
                    "name": name,
                    "type": key
                }

        return {
            "id": collection_id,
            "name": collection_id,
            "type": "unknown"
        }

    def get_entity_detail(self, entity_id: str) -> Dict[str, Any]:
        """Get full details for a specific entity"""
        try:
            response = requests.get(
                f"{self.base_url}/entities/{entity_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 200:
                return {
                    "ok": True,
                    "data": response.json()
                }
            else:
                return {
                    "ok": False,
                    "error": f"Failed to get entity: {response.status_code}"
                }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def get_entity_relationships(self, entity_id: str) -> Dict[str, Any]:
        """Get all relationships for an entity (directors, ownership, etc.)"""
        try:
            # Get relationships via the similar endpoint
            response = requests.get(
                f"{self.base_url}/entities/{entity_id}/similar",
                headers=self.headers,
                params={"limit": 200},  # Get many relationships
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "ok": True,
                    "relationships": data.get("results", []),
                    "total": data.get("total", 0)
                }
            else:
                return {
                    "ok": False,
                    "error": f"Failed to get relationships: {response.status_code}"
                }

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }


# For backwards compatibility
def search_aleph(query: str, **kwargs) -> Dict[str, Any]:
    """Legacy function for searching Aleph"""
    client = UnifiedAleph()
    return client.search_entity(query, **kwargs)