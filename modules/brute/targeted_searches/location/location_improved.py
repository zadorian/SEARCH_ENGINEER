#!/usr/bin/env python3
"""
Improved Location-based search with proper resource management
Uses the new base engine class and utilities
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import utilities and base classes
from brute.infrastructure.base_engine import BaseSearchEngine, MultiEngineSearchOrchestrator
from brute.infrastructure.common import BoundedResultsBuffer, with_timeout
from brute.infrastructure.settings import get_settings

# Import search engines from brute.engines
try:
    from brute.engines.google import GoogleSearch
    from brute.engines.bing import BingSearch
    from brute.engines.yandex import YandexSearch
    from brute.engines.brave import BraveSearch
except ImportError:
    # Fallback to path-based import
    sys.path.insert(0, str(PROJECT_ROOT / 'engines'))
    from exact_phrase_recall_runner_google import GoogleSearch
    from exact_phrase_recall_runner_bing import BingSearch
    from exact_phrase_recall_runner_yandex import YandexSearch
    from exact_phrase_recall_runner_brave import BraveSearch

logger = logging.getLogger(__name__)

# Location data
LOCATION_KEYWORDS = {
    'local': ['near me', 'nearby', 'local', 'close by', 'in my area'],
    'city': ['in {city}', 'at {city}', '{city} area', '{city} location'],
    'state': ['in {state}', '{state} state', 'state of {state}'],
    'country': ['in {country}', '{country} nationwide', 'across {country}']
}

COMMON_LOCATIONS = [
    'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix',
    'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose',
    'London', 'Paris', 'Tokyo', 'Berlin', 'Madrid', 'Rome',
    'Sydney', 'Melbourne', 'Toronto', 'Vancouver', 'Mumbai', 'Delhi'
]

# Market codes for different regions
MARKET_CODES = {
    'en-US': 'United States',
    'en-GB': 'United Kingdom', 
    'en-CA': 'Canada',
    'en-AU': 'Australia',
    'en-IN': 'India',
    'de-DE': 'Germany',
    'fr-FR': 'France',
    'es-ES': 'Spain',
    'it-IT': 'Italy',
    'ja-JP': 'Japan',
    'zh-CN': 'China',
    'pt-BR': 'Brazil',
    'ru-RU': 'Russia',
    'ko-KR': 'South Korea',
    'nl-NL': 'Netherlands'
}


class GoogleLocationEngine(BaseSearchEngine):
    """Google search with location support"""
    
    def __init__(self):
        super().__init__('GO', 'Google Location')
        self.engine = GoogleSearch()
    
    async def _search_impl(self, query: str, location: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Implement location-based Google search"""
        # Run synchronous search in executor
        loop = asyncio.get_event_loop()
        
        # Modify query with location if provided
        if location:
            search_query = f"{query} {location}"
        else:
            search_query = query
        
        # Use cr parameter for country restrict
        cr_param = kwargs.get('cr')
        if cr_param:
            # Google uses cr parameter for country restrict
            results = await loop.run_in_executor(
                None,
                lambda: self.engine.search(search_query, cr=cr_param)
            )
        else:
            results = await loop.run_in_executor(
                None,
                self.engine.search,
                search_query
            )
        
        return results


class BingLocationEngine(BaseSearchEngine):
    """Bing search with location support"""
    
    def __init__(self):
        super().__init__('BI', 'Bing Location')
        self.engine = BingSearch()
    
    async def _search_impl(self, query: str, location: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Implement location-based Bing search"""
        loop = asyncio.get_event_loop()
        
        # Bing uses mkt parameter for market/location
        mkt = kwargs.get('mkt', 'en-US')
        
        # Modify query with location
        if location:
            search_query = f"{query} location:{location}"
        else:
            search_query = query
        
        results = await loop.run_in_executor(
            None,
            lambda: self.engine.search(search_query, mkt=mkt)
        )
        
        return results


class YandexLocationEngine(BaseSearchEngine):
    """Yandex search with location support"""
    
    def __init__(self):
        super().__init__('YA', 'Yandex Location')
        self.engine = YandexSearch()
    
    async def _search_impl(self, query: str, location: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Implement location-based Yandex search"""
        loop = asyncio.get_event_loop()
        
        # Yandex uses lr parameter for region
        lr = kwargs.get('lr', '225')  # Default to Russia
        
        if location:
            search_query = f"{query} {location}"
        else:
            search_query = query
        
        results = await loop.run_in_executor(
            None,
            lambda: self.engine.search(search_query, lr=lr)
        )
        
        return results


class BraveLocationEngine(BaseSearchEngine):
    """Brave search with location support"""
    
    def __init__(self):
        super().__init__('BR', 'Brave Location')
        self.engine = BraveSearch()
    
    async def _search_impl(self, query: str, location: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Implement location-based Brave search"""
        loop = asyncio.get_event_loop()
        
        # Brave uses country parameter
        country = kwargs.get('country', 'US')
        
        if location:
            search_query = f"{query} {location}"
        else:
            search_query = query
        
        results = await loop.run_in_executor(
            None,
            lambda: self.engine.search(search_query, country=country)
        )
        
        return results


class ImprovedLocationSearch:
    """Improved location-based search orchestrator"""
    
    def __init__(self):
        self.settings = get_settings()
        self.results_buffer = BoundedResultsBuffer()
        
        # Initialize engines
        self.engines = {
            'google': GoogleLocationEngine(),
            'bing': BingLocationEngine(),
            'yandex': YandexLocationEngine(),
            'brave': BraveLocationEngine()
        }
        
        # Create orchestrator
        self.orchestrator = MultiEngineSearchOrchestrator(list(self.engines.values()))
    
    def parse_location_query(self, query: str) -> Dict[str, any]:
        """Parse query to extract location information"""
        query_lower = query.lower()
        
        # Check for explicit location markers
        location_markers = ['in', 'at', 'near', 'around', 'location:', 'loc:']
        
        location = None
        clean_query = query
        
        for marker in location_markers:
            if marker in query_lower:
                parts = query.split(marker, 1)
                if len(parts) == 2:
                    clean_query = parts[0].strip()
                    location = parts[1].strip().split()[0]  # Take first word after marker
                    break
        
        # Check for common locations in query
        if not location:
            for loc in COMMON_LOCATIONS:
                if loc.lower() in query_lower:
                    location = loc
                    clean_query = query.replace(loc, '').replace(loc.lower(), '').strip()
                    break
        
        # Detect location type
        location_type = 'local'
        if location:
            if any(country in location.lower() for country in ['usa', 'uk', 'canada', 'australia']):
                location_type = 'country'
            elif len(location.split()) > 1:
                location_type = 'city'
            else:
                location_type = 'local'
        
        return {
            'original_query': query,
            'clean_query': clean_query,
            'location': location,
            'location_type': location_type
        }
    
    def get_market_parameters(self, location: Optional[str]) -> Dict[str, str]:
        """Get market-specific parameters for each engine"""
        params = {}
        
        if not location:
            return {
                'mkt': 'en-US',
                'cr': 'countryUS',
                'lr': '225',
                'country': 'US'
            }
        
        # Try to match location to market
        location_lower = location.lower()
        
        # Check market codes
        for code, country in MARKET_CODES.items():
            if country.lower() in location_lower:
                lang, region = code.split('-')
                params['mkt'] = code  # Bing
                params['cr'] = f'country{region}'  # Google
                params['country'] = region  # Brave
                
                # Yandex region codes (simplified)
                yandex_regions = {
                    'US': '225', 'GB': '226', 'DE': '96',
                    'FR': '124', 'JP': '137', 'CN': '134'
                }
                params['lr'] = yandex_regions.get(region, '225')
                break
        
        return params
    
    @with_timeout(60)  # 1 minute timeout for location search
    async def search_location(self, query: str, engines: Optional[List[str]] = None,
                            max_results: int = 30) -> Dict[str, Any]:
        """
        Perform location-based search across multiple engines
        
        Args:
            query: Search query with optional location
            engines: List of engine names to use (default: all)
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with results and metadata
        """
        # Parse location from query
        parsed = self.parse_location_query(query)
        location = parsed['location']
        clean_query = parsed['clean_query']
        
        logger.info(f"Location search: query='{clean_query}', location='{location}'")
        
        # Get market parameters
        market_params = self.get_market_parameters(location)
        
        # Select engines
        if engines:
            selected_engines = [self.engines[e] for e in engines if e in self.engines]
        else:
            selected_engines = list(self.engines.values())
        
        # Create search tasks with location parameters
        tasks = []
        for engine in selected_engines:
            # Create engine-specific parameters
            engine_params = {
                'location': location,
                'max_results': max_results
            }
            
            # Add market parameters based on engine type
            if 'Google' in engine.engine_name:
                engine_params['cr'] = market_params.get('cr')
            elif 'Bing' in engine.engine_name:
                engine_params['mkt'] = market_params.get('mkt')
            elif 'Yandex' in engine.engine_name:
                engine_params['lr'] = market_params.get('lr')
            elif 'Brave' in engine.engine_name:
                engine_params['country'] = market_params.get('country')
            
            task = engine.search(clean_query, **engine_params)
            tasks.append(task)
        
        # Execute searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_results = []
        unique_urls = set()
        engine_stats = {}
        
        for engine, result in zip(selected_engines, results):
            if isinstance(result, Exception):
                logger.error(f"{engine.engine_name} failed: {result}")
                engine_stats[engine.engine_name] = {'error': str(result)}
            else:
                # Deduplicate results
                unique_count = 0
                for res in result:
                    url = res.get('url')
                    if url and url not in unique_urls:
                        unique_urls.add(url)
                        res['location_searched'] = location or 'global'
                        all_results.append(res)
                        unique_count += 1
                
                engine_stats[engine.engine_name] = {
                    'total': len(result),
                    'unique': unique_count
                }
        
        # Sort by relevance (could be improved with scoring)
        all_results.sort(key=lambda x: x.get('rank', 999))
        
        return {
            'query': query,
            'parsed_query': parsed,
            'location': location,
            'market_params': market_params,
            'results': all_results[:max_results * len(selected_engines)],
            'statistics': {
                'total_results': len(all_results),
                'unique_urls': len(unique_urls),
                'engines_used': [e.engine_name for e in selected_engines],
                'engine_stats': engine_stats
            }
        }
    
    async def search_multiple_locations(self, query: str, locations: List[str],
                                      max_results_per_location: int = 10) -> Dict[str, Any]:
        """Search the same query across multiple locations"""
        all_results = []
        location_results = {}
        
        # Search each location
        tasks = []
        for location in locations:
            location_query = f"{query} in {location}"
            task = self.search_location(location_query, max_results=max_results_per_location)
            tasks.append(task)
        
        # Execute in parallel with semaphore to limit concurrency
        sem = asyncio.Semaphore(3)  # Max 3 concurrent location searches
        
        async def search_with_sem(location_query, location):
            async with sem:
                result = await self.search_location(location_query, max_results=max_results_per_location)
                return location, result
        
        location_tasks = [
            search_with_sem(f"{query} in {loc}", loc) 
            for loc in locations
        ]
        
        results = await asyncio.gather(*location_tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Location search failed: {result}")
            else:
                location, search_result = result
                location_results[location] = {
                    'results': search_result['results'],
                    'count': len(search_result['results'])
                }
                all_results.extend(search_result['results'])
        
        return {
            'query': query,
            'locations_searched': locations,
            'location_results': location_results,
            'all_results': all_results,
            'total_results': len(all_results)
        }


# Example usage
async def main():
    """Example usage of improved location search"""
    searcher = ImprovedLocationSearch()
    
    # Example 1: Search with location in query
    results = await searcher.search_location("restaurants in New York")
    print(f"Found {results['statistics']['total_results']} results for restaurants in New York")
    
    # Example 2: Search multiple locations
    locations = ['London', 'Paris', 'Tokyo']
    multi_results = await searcher.search_multiple_locations("coffee shops", locations)
    print(f"\nResults across {len(locations)} locations:")
    for loc, data in multi_results['location_results'].items():
        print(f"  {loc}: {data['count']} results")


if __name__ == '__main__':
    asyncio.run(main())