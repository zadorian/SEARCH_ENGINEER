"""
Unified Aleph Module for Corporella Claude

Combines:
1. Official OCCRP Aleph API client (api.py)
2. Enhanced search with network analysis (search.py)
3. Country-specific collection mappings (flows/)
4. Smart routing integration

This module provides a clean interface for Aleph searches with automatic
collection selection based on country and data availability.
"""

import csv
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import official Aleph client
from .api import AlephAPI
from .errors import AlephException

# We'll use the official API for now
# search.py has enhanced features we can add later

# Flow data loader
class FlowDataLoader:
    """
    Loads country-specific collection metadata from flow CSV files
    """

    def __init__(self, flows_dir: Optional[str] = None):
        if flows_dir is None:
            flows_dir = Path(__file__).parent / "flows"
        self.flows_dir = Path(flows_dir)
        self._cache = {}

    def load_country(self, country_code: str) -> Dict[str, Any]:
        """
        Load flow data for a specific country

        Returns:
            {
                'country': 'GB',
                'collections': {
                    '809': {
                        'name': 'UK Companies House',
                        'inputs': ['company_name', 'company_id', ...],
                        'outputs': {...}
                    },
                    ...
                }
            }
        """
        if country_code in self._cache:
            return self._cache[country_code]

        csv_file = self.flows_dir / f"{country_code}.csv"
        if not csv_file.exists():
            return {'country': country_code, 'collections': {}}

        collections = {}
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                coll_id = row['source_id']
                if coll_id not in collections:
                    collections[coll_id] = {
                        'name': row['source_label'],
                        'kind': row.get('kind', ''),
                        'publisher': row.get('publisher', ''),
                        'inputs': set(),
                        'outputs': {}
                    }

                # Track input types
                input_type = row.get('input_type', '')
                if input_type:
                    collections[coll_id]['inputs'].add(input_type)

                    # Track output schema per input type
                    output_schema = row.get('output_schema', '')
                    if output_schema:
                        collections[coll_id]['outputs'][input_type] = output_schema

        # Convert sets to lists for JSON serialization
        for coll in collections.values():
            coll['inputs'] = list(coll['inputs'])

        result = {
            'country': country_code,
            'collections': collections
        }

        self._cache[country_code] = result
        return result

    def get_available_countries(self) -> List[str]:
        """Get list of countries with flow data"""
        return [f.stem for f in self.flows_dir.glob("*.csv")]

    def get_collection_by_feature(self, country: str, feature: str) -> List[str]:
        """
        Find collections that provide a specific feature

        Args:
            country: Country code (e.g., 'GB')
            feature: Feature name (e.g., 'beneficial_ownership', 'sanctions')

        Returns:
            List of collection IDs that provide this feature
        """
        # Feature mappings (hardcoded for now, could be in flow data)
        FEATURE_MAP = {
            'GB': {
                'beneficial_ownership': ['2053'],  # UK PSC
                'sanctions': ['1303'],  # HM Treasury Sanctions
                'regulatory': ['fca_register'],  # FCA
                'disqualifications': ['2302'],  # Disqualified Directors
                'political_exposure': ['153'],  # Parliamentary Inquiries
                'company_profile': ['809'],  # Companies House
            }
        }

        return FEATURE_MAP.get(country, {}).get(feature, [])


# Unified Aleph interface
class UnifiedAleph:
    """
    Unified interface combining official API client, enhanced search,
    and flow-based collection routing
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize Aleph client

        Args:
            api_key: Aleph API key (defaults to env ALEPH_API_KEY)
            base_url: Aleph instance URL (defaults to https://aleph.occrp.org)
        """
        self.api = AlephAPI(
            host=base_url or os.getenv('ALEPH_BASE_URL', 'https://aleph.occrp.org'),
            api_key=api_key or os.getenv('ALEPH_API_KEY', '')
        )
        self.flow_loader = FlowDataLoader()

    def search_entity(
        self,
        query: str,
        country: Optional[str] = None,
        collection_id: Optional[str] = None,
        schema: Optional[str] = None,
        filters: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        Search for entities with automatic collection selection

        Args:
            query: Search query (company name, person name, etc.)
            country: Country code (e.g., 'GB') - auto-selects collections
            collection_id: Specific collection ID (overrides country)
            schema: Entity schema ('Company', 'Person', etc.)
            filters: Additional filters as list of tuples

        Returns:
            {
                'results': [...],
                'total': int,
                'collection_used': str,
                'source': 'aleph'
            }
        """
        filters_list = list(filters) if filters else []

        # Add collection filter
        if collection_id:
            filters_list.append(('collection_id', collection_id))
        elif country:
            # If country specified but no collection, search all collections for that country
            flow_data = self.flow_loader.load_country(country)
            # For now, search without collection filter (searches all)
            # Could optimize by searching specific collections based on schema

        # Add schema filter
        if schema:
            filters_list.append(('schema', schema))

        # Execute search via official API
        try:
            result_set = self.api.search(
                query=query,
                filters=filters_list
            )

            results = []
            for entity in result_set:
                results.append(entity)

            return {
                'results': results,
                'total': len(results),
                'collection_used': collection_id or f'{country}_all' if country else 'global',
                'source': 'aleph'
            }

        except Exception as e:
            return {
                'results': [],
                'total': 0,
                'error': str(e),
                'source': 'aleph'
            }

    def get_collections_for_country(self, country: str) -> Dict[str, Any]:
        """
        Get available collections for a country

        Returns:
            {
                'country': 'GB',
                'collections': {
                    '809': {'name': 'UK Companies House', 'inputs': [...], ...},
                    ...
                },
                'total': 6
            }
        """
        flow_data = self.flow_loader.load_country(country)
        flow_data['total'] = len(flow_data['collections'])
        return flow_data

    def get_available_countries(self) -> List[str]:
        """Get list of countries with Aleph data"""
        return self.flow_loader.get_available_countries()

    def search_with_routing(
        self,
        query: str,
        country: str,
        target_feature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search with smart collection routing based on target feature

        Args:
            query: Search query
            country: Country code
            target_feature: 'beneficial_ownership', 'sanctions', 'regulatory', etc.

        Returns:
            Results from the most appropriate collection
        """
        # Get relevant collections
        if target_feature:
            collection_ids = self.flow_loader.get_collection_by_feature(country, target_feature)
            if collection_ids:
                # Search the primary collection for this feature
                return self.search_entity(
                    query=query,
                    collection_id=collection_ids[0],
                    country=country
                )

        # Fallback: search all collections for this country
        return self.search_entity(query=query, country=country)


# Export main classes
__all__ = [
    'UnifiedAleph',
    'AlephAPI',
    'AlephException',
    'FlowDataLoader'
]

# Convenience instantiation
def get_aleph_client(api_key: Optional[str] = None) -> UnifiedAleph:
    """Get configured Aleph client"""
    return UnifiedAleph(api_key=api_key)
