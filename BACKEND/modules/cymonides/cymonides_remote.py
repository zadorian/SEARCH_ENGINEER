"""
CYMONIDES Remote Client - Connect to sastre server's CYMONIDES API

Provides access to 59.9M+ records on sastre (176.9.2.153:8100):
- persons_unified (6.3M)
- linkedin_unified (2.8M)
- emails_unified (220K)
- phones_unified (49K)
- uk_ccod (4.29M UK companies with geocoding)
- wdc-person-entities (6.8M)
- wdc-organization-entities (9.6M)
- wdc-product-entities
- wdc-localbusiness-entities

Usage:
    from CYMONIDES.cymonides_remote import CymonidesRemote

    client = CymonidesRemote()
    results = client.search("John Smith", limit=50)
    results = client.geo_search(51.5074, -0.1278, radius_km=10)
    results = client.find_by_job("Software Engineer")
"""

import os
import logging
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# sastre server CYMONIDES API
CYMONIDES_API_URL = os.getenv('CYMONIDES_API_URL', 'http://176.9.2.153:8100')


@dataclass
class RemoteSearchResult:
    """Standard result format for remote CYMONIDES queries"""
    query: str
    total: int
    results: List[Dict[str, Any]]
    indices_searched: List[str]
    timing_ms: Optional[float] = None


class CymonidesRemote:
    """
    Remote client for CYMONIDES API on sastre server.

    Connects to the unified search API with 59.9M+ records across
    9 Elasticsearch indices.
    """

    def __init__(self, api_url: str = None, timeout: int = 30):
        """
        Initialize remote CYMONIDES client.

        Args:
            api_url: Base URL for CYMONIDES API (default: sastre:8100)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url or CYMONIDES_API_URL
        self.timeout = timeout
        self._healthy = None

    def _request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make HTTP request to CYMONIDES API."""
        url = f"{self.api_url}{endpoint}"
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            logger.error(f"CYMONIDES API connection error: {e}")
            raise ConnectionError(f"Cannot connect to CYMONIDES API at {self.api_url}")
        except requests.exceptions.Timeout:
            logger.error(f"CYMONIDES API timeout after {self.timeout}s")
            raise TimeoutError(f"CYMONIDES API request timed out")
        except requests.exceptions.HTTPError as e:
            logger.error(f"CYMONIDES API HTTP error: {e}")
            raise

    def health_check(self) -> bool:
        """Check if CYMONIDES API is healthy."""
        try:
            result = self._request("/health")
            self._healthy = result.get("status") == "healthy"
            return self._healthy
        except Exception as e:
            logger.warning(f"CYMONIDES health check failed: {e}")
            self._healthy = False
            return False

    def search(
        self,
        query: str,
        indices: Optional[List[str]] = None,
        entity_types: Optional[List[str]] = None,
        limit: int = 50
    ) -> RemoteSearchResult:
        """
        Search across all CYMONIDES indices.

        Args:
            query: Search query (name, email, company, etc.)
            indices: Specific indices to search (default: all)
            entity_types: Filter by entity type
            limit: Maximum results

        Returns:
            RemoteSearchResult with matching records
        """
        params = {
            "q": query,
            "limit": limit,
        }
        if indices:
            params["indices"] = ",".join(indices)
        if entity_types:
            params["entity_types"] = ",".join(entity_types)

        result = self._request("/search", params)

        return RemoteSearchResult(
            query=query,
            total=result.get("total", 0),
            results=result.get("hits", []),  # API returns "hits" not "results"
            indices_searched=result.get("indices", []),
            timing_ms=result.get("query_time_ms")
        )

    def geo_search(
        self,
        lat: float,
        lon: float,
        radius_km: float = 10,
        query: Optional[str] = None,
        limit: int = 50
    ) -> RemoteSearchResult:
        """
        Geographic proximity search.

        Uses uk_ccod geo_location field for UK companies.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius in kilometers
            query: Optional text query to filter
            limit: Maximum results

        Returns:
            RemoteSearchResult with nearby records
        """
        params = {
            "lat": lat,
            "lon": lon,
            "radius": radius_km,
            "limit": limit,
        }
        if query:
            params["q"] = query

        result = self._request("/geo", params)

        return RemoteSearchResult(
            query=f"geo:{lat},{lon} radius:{radius_km}km",
            total=result.get("total", 0),
            results=result.get("hits", []),  # API returns "hits"
            indices_searched=result.get("indices", ["uk_ccod"]),
            timing_ms=result.get("query_time_ms")
        )

    def find_by_job(
        self,
        job_cluster: str,
        limit: int = 50
    ) -> RemoteSearchResult:
        """
        Find persons by job cluster.

        Uses job_cluster field derived from 389 clustered job titles.

        Args:
            job_cluster: Cluster name (e.g., "Software Engineer", "CEO")
            limit: Maximum results

        Returns:
            RemoteSearchResult with matching persons
        """
        params = {"limit": limit}
        result = self._request(f"/jobs/{job_cluster}", params)

        return RemoteSearchResult(
            query=f"job_cluster:{job_cluster}",
            total=result.get("total", 0),
            results=result.get("hits", []),  # API returns "hits"
            indices_searched=result.get("indices", ["persons_unified"]),
            timing_ms=result.get("query_time_ms")
        )

    def list_job_clusters(self) -> List[str]:
        """Get list of all job clusters."""
        result = self._request("/clusters")
        return result.get("clusters", [])

    def stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return self._request("/stats")

    def find_person(self, name: str, limit: int = 50) -> RemoteSearchResult:
        """Convenience method: Search for a person by name."""
        return self.search(
            query=name,
            entity_types=["person"],
            limit=limit
        )

    def find_company(self, name: str, limit: int = 50) -> RemoteSearchResult:
        """Convenience method: Search for a company by name."""
        return self.search(
            query=name,
            entity_types=["company", "organization"],
            limit=limit
        )

    def find_email(self, email: str, limit: int = 50) -> RemoteSearchResult:
        """Convenience method: Search for an email address."""
        return self.search(
            query=email,
            indices=["emails_unified"],
            limit=limit
        )

    def find_phone(self, phone: str, limit: int = 50) -> RemoteSearchResult:
        """Convenience method: Search for a phone number."""
        return self.search(
            query=phone,
            indices=["phones_unified"],
            limit=limit
        )

    def uk_company_search(
        self,
        query: str,
        postcode: Optional[str] = None,
        limit: int = 50
    ) -> RemoteSearchResult:
        """
        Search UK companies (uk_ccod index).

        Args:
            query: Company name or other search term
            postcode: Filter by UK postcode
            limit: Maximum results

        Returns:
            RemoteSearchResult with UK company records
        """
        search_query = query
        if postcode:
            search_query = f"{query} {postcode}"

        return self.search(
            query=search_query,
            indices=["uk_ccod"],
            limit=limit
        )


# Singleton instance for convenience
_client = None

def get_client() -> CymonidesRemote:
    """Get or create singleton CYMONIDES client."""
    global _client
    if _client is None:
        _client = CymonidesRemote()
    return _client


# Convenience functions
def cymonides_remote_search(query: str, limit: int = 50) -> RemoteSearchResult:
    """Quick search across remote CYMONIDES."""
    return get_client().search(query, limit=limit)


def cymonides_geo_search(lat: float, lon: float, radius_km: float = 10) -> RemoteSearchResult:
    """Quick geo search."""
    return get_client().geo_search(lat, lon, radius_km)


__all__ = [
    'CymonidesRemote',
    'RemoteSearchResult',
    'get_client',
    'cymonides_remote_search',
    'cymonides_geo_search',
]
