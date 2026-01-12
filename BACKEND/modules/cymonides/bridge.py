"""
CYMONIDES Bridge - Interface for SASTRE and other modules

Provides access to Cymonides entity storage and WDC indices.
This is the UNKNOWN KNOWNS check - search what we already have
before going to external sources.

Primary: Local WDC service (localhost:9200)
Fallback: Remote CYMONIDES API on sastre (176.9.2.153:8100) with 59.9M+ records
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CymonidesBridge:
    """
    Bridge to Cymonides entity storage and WDC indices.

    This is the UNKNOWN KNOWNS check - search what we already have
    before going to external sources.

    Uses (local):
    - wdc-person-entities: Person records from Schema.org
    - wdc-organization-entities: Company/org records
    - wdc-localbusiness-entities: Local business records
    - wdc-product-entities: Product records

    Uses (remote via sastre):
    - persons_unified: 6.3M persons (breach data)
    - linkedin_unified: 2.8M LinkedIn profiles
    - emails_unified: 220K emails with breach_risk_tier
    - phones_unified: 49K phones with phone_country
    - uk_ccod: 4.29M UK companies with geo_location
    - wdc-*: 40M+ WDC entities
    """

    def __init__(self, prefer_remote: bool = False):
        """
        Initialize CYMONIDES bridge.

        Args:
            prefer_remote: If True, use remote sastre API as primary
        """
        self._wdc_service = None
        self._remote_client = None
        self._loaded = False
        self._prefer_remote = prefer_remote

    def _lazy_load(self):
        """Lazy load WDC service and remote client."""
        if self._loaded:
            return

        # Try local WDC service first (unless prefer_remote)
        if not self._prefer_remote:
            try:
                from DEFINITIONAL.wdc_query import (
                    WDCQueryService,
                    search_person_entities,
                    search_organization_entities,
                    search_localbusiness_entities,
                    search_product_entities,
                )
                self._wdc_service = WDCQueryService()
                self._search_person = search_person_entities
                self._search_org = search_organization_entities
                self._search_local = search_localbusiness_entities
                self._search_product = search_product_entities
                logger.info("Cymonides/WDC bridge loaded (local)")
            except ImportError as e:
                logger.warning(f"Could not import WDC service: {e}")

        # Try remote CYMONIDES API as fallback/primary
        try:
            try:
                from BACKEND.modules.CYMONIDES.cymonides_remote import CymonidesRemote
            except ImportError:
                # Fallback to direct import (if CYMONIDES in path)
                try:
                    from cymonides_remote import CymonidesRemote
                except ImportError:
                     from CYMONIDES.cymonides_remote import CymonidesRemote

            self._remote_client = CymonidesRemote()
            if self._remote_client.health_check():
                logger.info("Cymonides remote client loaded (sastre: 59.9M+ records)")
            else:
                self._remote_client = None
                logger.warning("Remote CYMONIDES API not available")
        except Exception as e:
            logger.warning(f"Could not load remote CYMONIDES client: {e}")

        self._loaded = True

    def check_unknown_knowns(
        self,
        entity_type: str,
        value: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Check corpus for existing knowledge about an entity.

        This is the UNKNOWN KNOWNS check - we might already have
        relevant data in our indices.

        Args:
            entity_type: Type of entity ('person', 'company', 'email', etc.)
            value: Entity value to search for
            limit: Max results

        Returns:
            List of matching entities from corpus
        """
        self._lazy_load()

        results = []

        # Try local WDC service first
        if self._wdc_service and not self._prefer_remote:
            try:
                if entity_type in ('person', 'p:'):
                    results = self._search_person(name=value, limit=limit)
                elif entity_type in ('company', 'c:', 'organization'):
                    results = self._search_org(name=value, limit=limit)
                elif entity_type in ('email', 'e:'):
                    results = self._wdc_service.search_by_email(value, exact=False, limit=limit)
                elif entity_type in ('phone', 't:'):
                    results = self._wdc_service.search_by_phone(value, limit=limit)
                elif entity_type in ('domain', 'd:'):
                    results = self._wdc_service.find_by_domain(value, limit=limit).get('results', [])
                else:
                    results = self._wdc_service.search_entities(value, limit=limit).get('results', [])
            except Exception as e:
                logger.warning(f"Local WDC search error: {e}")

        # Use remote CYMONIDES if local failed or prefer_remote
        if (not results or self._prefer_remote) and self._remote_client:
            try:
                if entity_type in ('person', 'p:'):
                    remote_result = self._remote_client.find_person(value, limit=limit)
                elif entity_type in ('company', 'c:', 'organization'):
                    remote_result = self._remote_client.find_company(value, limit=limit)
                elif entity_type in ('email', 'e:'):
                    remote_result = self._remote_client.find_email(value, limit=limit)
                elif entity_type in ('phone', 't:'):
                    remote_result = self._remote_client.find_phone(value, limit=limit)
                else:
                    remote_result = self._remote_client.search(value, limit=limit)

                if remote_result and remote_result.results:
                    results.extend(remote_result.results)
                    logger.debug(f"Remote CYMONIDES returned {len(remote_result.results)} results")
            except Exception as e:
                logger.warning(f"Remote CYMONIDES search error: {e}")

        return results

    def search_by_email(self, email: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search corpus by email address."""
        self._lazy_load()
        results = []

        if self._wdc_service and not self._prefer_remote:
            try:
                result = self._wdc_service.search_by_email(email, exact=False, limit=limit)
                results = result if isinstance(result, list) else []
            except Exception as e:
                logger.warning(f"Local email search error: {e}")

        if (not results or self._prefer_remote) and self._remote_client:
            try:
                remote_result = self._remote_client.find_email(email, limit=limit)
                if remote_result and remote_result.results:
                    results.extend(remote_result.results)
            except Exception as e:
                logger.warning(f"Remote email search error: {e}")

        return results

    def search_by_phone(self, phone: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search corpus by phone number."""
        self._lazy_load()
        results = []

        if self._wdc_service and not self._prefer_remote:
            try:
                result = self._wdc_service.search_by_phone(phone, limit=limit)
                results = result if isinstance(result, list) else []
            except Exception as e:
                logger.warning(f"Local phone search error: {e}")

        if (not results or self._prefer_remote) and self._remote_client:
            try:
                remote_result = self._remote_client.find_phone(phone, limit=limit)
                if remote_result and remote_result.results:
                    results.extend(remote_result.results)
            except Exception as e:
                logger.warning(f"Remote phone search error: {e}")

        return results

    def geo_search(
        self,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
        query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Geographic proximity search (UK companies via sastre).

        Uses uk_ccod geo_location field for UK companies.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius in kilometers
            query: Optional text filter
            limit: Max results

        Returns:
            List of nearby UK companies
        """
        self._lazy_load()
        if self._remote_client:
            try:
                result = self._remote_client.geo_search(lat, lon, radius_km, query, limit)
                return result.results if result else []
            except Exception as e:
                logger.error(f"Geo search error: {e}")
        return []

    def find_by_job_cluster(self, job_cluster: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Find persons by job cluster (via sastre).

        Args:
            job_cluster: Cluster name (e.g., 'Journalist', 'CEO')
            limit: Max results

        Returns:
            List of matching persons
        """
        self._lazy_load()
        if self._remote_client:
            try:
                result = self._remote_client.find_by_job(job_cluster, limit)
                return result.results if result else []
            except Exception as e:
                logger.error(f"Job cluster search error: {e}")
        return []

    def list_job_clusters(self) -> List[str]:
        """Get available job clusters (via sastre)."""
        self._lazy_load()
        if self._remote_client:
            try:
                return self._remote_client.list_job_clusters()
            except Exception as e:
                logger.error(f"List job clusters error: {e}")
        return []

    def get_domains_with_entity_type(
        self,
        entity_type: str,
        geo: Optional[str] = None,
        limit: int = 1000
    ) -> List[str]:
        """
        Get domains that have entities of a specific type.

        Useful for targeted searches - find where to look first.
        """
        self._lazy_load()
        if self._wdc_service:
            try:
                result = self._wdc_service.get_domains_by_type(entity_type, geo=geo, limit=limit)
                return result if isinstance(result, list) else []
            except Exception as e:
                logger.error(f"Get domains error: {e}")
        return []

    def stats(self) -> Dict[str, Any]:
        """Get CYMONIDES statistics (remote)."""
        self._lazy_load()
        if self._remote_client:
            try:
                return self._remote_client.stats()
            except Exception as e:
                logger.error(f"Stats error: {e}")
        return {}


__all__ = ['CymonidesBridge']
