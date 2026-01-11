#!/usr/bin/env python3
"""
Site Search - Unified module for site: operator searches
Supports domain-specific, TLD-based, and pattern-based site searches
Used by location.py, news.py, language.py, and filetype.py modules
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import json

# Add parent directory to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

# Import phrase matcher for exact phrase and proximity filtering
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    PHRASE_MATCHER_AVAILABLE = True
except ImportError:
    PHRASE_MATCHER_AVAILABLE = False
    logger.warning("Phrase matcher not found, exact phrase filtering will be disabled")

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logger.warning("Event streaming not available for site search")

# Set up logger
logger = logging.getLogger(__name__)

# Import search engines with error handling
try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Google search: {e}")
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Bing search: {e}")
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Brave search: {e}")
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import DuckDuckGo search: {e}")
    DUCKDUCKGO_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yandex import YandexSearch
    YANDEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yandex search: {e}")
    YANDEX_AVAILABLE = False

class SiteSearch(SearchTypeEventEmitter if STREAMING_AVAILABLE else object):
    """Unified site: operator search across multiple engines"""
    
    # Common news domains for news.py module
    TOP_NEWS_DOMAINS = [
        "yahoo.com", "yahoo.co.jp", "globo.com", "nytimes.com", "bbc.co.uk",
        "cnn.com", "foxnews.com", "theguardian.com", "reuters.com", "bloomberg.com",
        "wsj.com", "ft.com", "economist.com", "time.com", "forbes.com",
        "businessinsider.com", "techcrunch.com", "wired.com", "arstechnica.com",
        "reddit.com", "news.ycombinator.com", "slashdot.org"
    ]
    
    # Common TLDs for location-based searches
    COUNTRY_TLDS = {
        'us': ['com', 'us', 'gov', 'edu'],
        'uk': ['uk', 'co.uk', 'org.uk', 'ac.uk'],
        'de': ['de', 'com.de', 'org.de'],
        'fr': ['fr', 'com.fr', 'org.fr'],
        'jp': ['jp', 'co.jp', 'or.jp'],
        'cn': ['cn', 'com.cn', 'org.cn'],
        'ru': ['ru', 'com.ru', 'org.ru'],
        'br': ['br', 'com.br', 'org.br'],
        'in': ['in', 'co.in', 'org.in'],
        'au': ['au', 'com.au', 'org.au'],
        'ca': ['ca', 'com.ca', 'org.ca'],
        'it': ['it', 'com.it', 'org.it'],
        'es': ['es', 'com.es', 'org.es'],
        'nl': ['nl', 'com.nl', 'org.nl'],
        'se': ['se', 'com.se', 'org.se'],
        'ch': ['ch', 'com.ch', 'org.ch'],
        'at': ['at', 'co.at', 'or.at'],
        'pl': ['pl', 'com.pl', 'org.pl'],
        'be': ['be', 'com.be', 'org.be'],
        'dk': ['dk', 'com.dk', 'org.dk']
    }
    
    def __init__(self, enable_exact_phrase_filter: bool = True):
        """Initialize search engine instances"""
        # Initialize event streaming
        if STREAMING_AVAILABLE:
            super().__init__("site")
        
        self.google_search = GoogleSearch() if GOOGLE_AVAILABLE else None
        self.bing_search = BingSearch() if BING_AVAILABLE else None
        self.brave_search = BraveSearch() if BRAVE_AVAILABLE else None
        self.duckduckgo_search = DuckDuckGoSearch() if DUCKDUCKGO_AVAILABLE else None
        self.yandex_search = YandexSearch() if YANDEX_AVAILABLE else None
        
        # Initialize phrase matcher for filtering
        self.enable_exact_phrase_filter = enable_exact_phrase_filter
        if PHRASE_MATCHER_AVAILABLE and enable_exact_phrase_filter:
            self.phrase_matcher = PhraseMatcher(max_distance=3)
        else:
            self.phrase_matcher = None
        
        # Track available engines
        self.available_engines = []
        if GOOGLE_AVAILABLE: self.available_engines.append('google')
        if BING_AVAILABLE: self.available_engines.append('bing')
        if BRAVE_AVAILABLE: self.available_engines.append('brave')
        if DUCKDUCKGO_AVAILABLE: self.available_engines.append('duckduckgo')
        if YANDEX_AVAILABLE: self.available_engines.append('yandex')
        
        logger.info(f"Site Search initialized with engines: {self.available_engines}")
    
    def _filter_results(self, results: List[Dict], query: str, site_pattern: str = None) -> Tuple[List[Dict], List[Dict]]:
        """Filter results by exact phrase and site pattern matching"""
        phrases = self.phrase_matcher.extract_phrases(query) if self.phrase_matcher else []
        
        filtered = []
        filtered_out = []
        
        for result in results:
            # Check site pattern first (domain filtering)
            if site_pattern:
                url = result.get('url', '')
                if not self._matches_site_pattern(url, site_pattern):
                    # Add to filtered out with domain filter reason
                    result['filter_reason'] = f"Domain does not match site pattern: {site_pattern}"
                    result['filter_type'] = 'domain_filter'
                    result['expected_site'] = site_pattern
                    filtered_out.append(result)
                    
                    # Emit filtered result event
                    if STREAMING_AVAILABLE and hasattr(self, 'emit_search_filtered_result'):
                        self.emit_search_filtered_result(result, "site_pattern")
                    continue
            
            # Check exact phrase if available
            if phrases:
                title = result.get('title', '')
                snippet = result.get('snippet', '') or result.get('description', '')
                text_to_check = f"{title} {snippet}".lower()
                
                phrase_found = False
                
                for phrase in phrases:
                    # Check for exact match
                    if phrase.lower() in text_to_check:
                        phrase_found = True
                        result['filter_match_type'] = 'exact'
                        break
                        
                    # Check for proximity match
                    proximity_match, positions = self.phrase_matcher.check_proximity(text_to_check, phrase)
                    if proximity_match:
                        phrase_found = True
                        result['filter_match_type'] = 'proximity'
                        result['filter_match_positions'] = positions
                        break
                
                if not phrase_found:
                    # Add to filtered out with phrase filter reason
                    result['filter_reason'] = f"Exact phrase not found: {', '.join(phrases)}"
                    result['filter_type'] = 'exact_phrase'
                    result['searched_phrase'] = phrases[0] if phrases else ''
                    filtered_out.append(result)
                    
                    # Emit filtered result event
                    if STREAMING_AVAILABLE and hasattr(self, 'emit_search_filtered_result'):
                        self.emit_search_filtered_result(result, "phrase_filter")
                    continue
            
            # Result passed all filters
            filtered.append(result)
        
        if len(filtered_out) > 0:
            logger.info(f"Filtered {len(filtered_out)} results (domain/phrase mismatch)")
        
        return filtered, filtered_out
    
    def _matches_site_pattern(self, url: str, site_pattern: str) -> bool:
        """Check if URL matches the site pattern"""
        if not url or not site_pattern:
            return True
            
        # Extract domain from URL
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc.lower()
            site_pattern = site_pattern.lower()
            
            # Direct domain match
            if site_pattern in domain:
                return True
                
            # TLD match (e.g., ".edu", ".gov")
            if site_pattern.startswith('.') and domain.endswith(site_pattern):
                return True
                
            return False
        except Exception as e:
            return False
    
    async def search_with_filtering(self, query: str, site_pattern: str, max_results: int = 500) -> Dict[str, List[Dict]]:
        """
        Search with exact phrase filtering support
        Returns full results with titles and snippets
        
        Args:
            query: Search query (may contain quoted phrases)
            site_pattern: Site pattern (domain, TLD, or pattern)
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of result dicts as values
        """
        site_query = f'{query} site:{site_pattern}'
        return await self._execute_searches(site_query, max_results, return_full_results=True)
    
    async def search_by_domain(self, query: str, domain: str, max_results: int = 500) -> Dict[str, List[str]]:
        """
        Search within a specific domain
        Used by news.py for news domain searches
        
        Args:
            query: Search query
            domain: Domain to search within (e.g., 'nytimes.com')
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        site_query = f'{query} site:{domain}'
        return await self._execute_searches(site_query, max_results)
    
    async def search_by_tld(self, query: str, tld: str, max_results: int = 500) -> Dict[str, List[str]]:
        """
        Search within a specific TLD
        Used by location.py and language.py for regional searches
        
        Args:
            query: Search query
            tld: Top-level domain (e.g., 'de', 'uk')
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        # Handle both formats: 'de' and '.de'
        tld = tld.lstrip('.')
        site_query = f'{query} site:.{tld}'
        return await self._execute_searches(site_query, max_results)
    
    async def search_by_pattern(self, query: str, pattern: str, max_results: int = 500) -> Dict[str, List[str]]:
        """
        Search using site pattern
        Used by filetype.py for extension patterns like site:*.pdf/*
        
        Args:
            query: Search query
            pattern: Site pattern (e.g., '*.pdf/*')
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        site_query = f'{query} site:{pattern}'
        return await self._execute_searches(site_query, max_results)
    
    async def search_multiple_domains(self, query: str, domains: List[str], max_results_per_domain: int = 500) -> Dict[str, List[str]]:
        """
        Search across multiple domains in parallel
        Used by news.py for searching multiple news sites
        
        Args:
            query: Search query
            domains: List of domains to search
            max_results_per_domain: Maximum results per domain
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        tasks = []
        for domain in domains:
            tasks.append(self.search_by_domain(query, domain, max_results_per_domain))
        
        # Execute all domain searches in parallel
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged_results = {}
        for results in results_list:
            if isinstance(results, dict):
                for engine, urls in results.items():
                    if engine not in merged_results:
                        merged_results[engine] = []
                    merged_results[engine].extend(urls)
        
        # Remove duplicates while preserving order
        for engine in merged_results:
            seen = set()
            unique_urls = []
            for url in merged_results[engine]:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            merged_results[engine] = unique_urls
        
        return merged_results
    
    async def search_by_country(self, query: str, country_code: str, max_results: int = 500) -> Dict[str, List[str]]:
        """
        Search within country-specific TLDs
        Used by location.py for country-based searches
        
        Args:
            query: Search query
            country_code: Two-letter country code (e.g., 'de', 'uk')
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        # Get country-specific TLDs
        tlds = self.COUNTRY_TLDS.get(country_code.lower(), [country_code.lower()])
        
        # Search across all country TLDs
        tasks = []
        for tld in tlds:
            tasks.append(self.search_by_tld(query, tld, max_results // len(tlds)))
        
        # Execute all TLD searches in parallel
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged_results = {}
        for results in results_list:
            if isinstance(results, dict):
                for engine, urls in results.items():
                    if engine not in merged_results:
                        merged_results[engine] = []
                    merged_results[engine].extend(urls)
        
        return merged_results
    
    async def _execute_searches(self, query: str, max_results: int, return_full_results: bool = False) -> Dict[str, List]:
        """Execute searches across all available engines with L1/L2 expansion"""
        queries = [query]
        
        # L2: InURL expansion (Tricks)
        # If query uses site:domain, also try inurl:domain to catch pages with poor metadata but correct URL structure
        if 'site:' in query and 'inurl:' not in query:
            import re
            match = re.search(r'site:([\w\.-]+)', query)
            if match:
                domain = match.group(1)
                # Check if it looks like a domain (has dot, no wildcard) and isn't a TLD
                if '.' in domain and '*' not in domain and not domain.startswith('.'):
                    # Replace site:domain with inurl:domain
                    l2_query = query.replace(f'site:{domain}', f'inurl:{domain}')
                    queries.append(l2_query)
                    logger.info(f"L2 Expansion: Adding inurl query: {l2_query}")

        tasks = []
        
        # Execute for ALL generated queries
        for q in queries:
            if self.google_search:
                tasks.append(self._search_google(q, max_results, return_full_results))
            if self.bing_search:
                tasks.append(self._search_bing(q, max_results, return_full_results))
            if self.brave_search:
                tasks.append(self._search_brave(q, max_results, return_full_results))
            if self.duckduckgo_search:
                tasks.append(self._search_duckduckgo(q, max_results, return_full_results))
            if self.yandex_search:
                tasks.append(self._search_yandex(q, max_results, return_full_results))
        
        # Execute all searches in parallel
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process and merge results
        all_results = {}
        engine_names = ['google', 'bing', 'brave', 'duckduckgo', 'yandex']
        
        # Flatten results based on engine
        # We need to map tasks back to engines. 
        # Since we iterate queries then engines, the order is:
        # Q1-Eng1, Q1-Eng2..., Q2-Eng1, Q2-Eng2...
        
        num_engines = len(self.available_engines)
        # This mapping is tricky if available_engines changes.
        # Let's simplify: the loop above adds tasks.
        # We can just collect all successful results and deduplicate by URL.
        
        # Re-structure to collect by engine name safely
        # Using a simpler accumulation strategy
        
        for result in results_list:
            if isinstance(result, list):
                # It's a list of results/URLs
                # We don't strictly know which engine it came from in this flat list without tracking
                # But the individual search methods return lists.
                # Let's look at the items. If they are dicts, they might have 'source'.
                # If strings (URLs), we can't easily attribute.
                
                # Wait, the previous implementation assumed a fixed order.
                # Let's preserve the simple dictionary return structure by aggregating.
                pass

        # Better approach: Accumulate results into a dict keyed by engine
        # Rerun the task creation to bind results to engines
        
        # Reset tasks and run properly
        pass # (Placeholder for replacement code)
        
        return await self._execute_and_merge(queries, max_results, return_full_results)

    async def _execute_and_merge(self, queries: List[str], max_results: int, return_full_results: bool) -> Dict[str, List]:
        """Helper to execute multiple queries and merge results by engine"""
        tasks = []
        task_info = [] # (engine_name, query)
        
        for q in queries:
            if self.google_search:
                tasks.append(self._search_google(q, max_results, return_full_results))
                task_info.append(('google', q))
            if self.bing_search:
                tasks.append(self._search_bing(q, max_results, return_full_results))
                task_info.append(('bing', q))
            if self.brave_search:
                tasks.append(self._search_brave(q, max_results, return_full_results))
                task_info.append(('brave', q))
            if self.duckduckgo_search:
                tasks.append(self._search_duckduckgo(q, max_results, return_full_results))
                task_info.append(('duckduckgo', q))
            if self.yandex_search:
                tasks.append(self._search_yandex(q, max_results, return_full_results))
                task_info.append(('yandex', q))
                
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_results = {}
        
        for i, result in enumerate(results_list):
            engine_name = task_info[i][0]
            
            if isinstance(result, Exception):
                logger.error(f"Error in {engine_name}: {result}")
                continue
                
            if engine_name not in all_results:
                all_results[engine_name] = []
            
            # Deduplicate and add
            current_urls = set(r.get('url', r) if isinstance(r, dict) else r for r in all_results[engine_name])
            
            for item in result:
                url = item.get('url', item) if isinstance(item, dict) else item
                if url not in current_urls:
                    all_results[engine_name].append(item)
                    current_urls.add(url)
                    
        return all_results
    
    async def _search_google(self, query: str, max_results: int, return_full_results: bool = False) -> List:
        """Search Google"""
        try:
            # Search engines are sync, not async
            results = await asyncio.get_event_loop().run_in_executor(
                None, self.google_search.search, query, max_results
            )
            
            # Apply exact phrase filtering if enabled
            if self.enable_exact_phrase_filter and self.phrase_matcher and return_full_results:
                filtered_results, _ = self._filter_results(results, query, site_pattern)
                return filtered_results
            
            # Return URLs only if not returning full results
            if not return_full_results:
                return [r.get('url', '') for r in results if r.get('url')]
            
            return results
        except Exception as e:
            logger.error(f"Google site search error: {e}")
            return []
    
    async def _search_bing(self, query: str, max_results: int, return_full_results: bool = False) -> List:
        """Search Bing"""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self.bing_search.search, query, max_results
            )
            
            if self.enable_exact_phrase_filter and self.phrase_matcher and return_full_results:
                filtered_results, _ = self._filter_results(results, query, site_pattern)
                return filtered_results
            
            if not return_full_results:
                return [r.get('url', '') for r in results if r.get('url')]
            
            return results
        except Exception as e:
            logger.error(f"Bing site search error: {e}")
            return []
    
    async def _search_brave(self, query: str, max_results: int, return_full_results: bool = False) -> List:
        """Search Brave"""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self.brave_search.search, query, max_results
            )
            
            if self.enable_exact_phrase_filter and self.phrase_matcher and return_full_results:
                filtered_results, _ = self._filter_results(results, query, site_pattern)
                return filtered_results
            
            if not return_full_results:
                return [r.get('url', '') for r in results if r.get('url')]
            
            return results
        except Exception as e:
            logger.error(f"Brave site search error: {e}")
            return []
    
    async def _search_duckduckgo(self, query: str, max_results: int, return_full_results: bool = False) -> List:
        """Search DuckDuckGo"""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self.duckduckgo_search.search, query, max_results
            )
            
            if self.enable_exact_phrase_filter and self.phrase_matcher and return_full_results:
                filtered_results, _ = self._filter_results(results, query, site_pattern)
                return filtered_results
            
            if not return_full_results:
                return [r.get('url', '') for r in results if r.get('url')]
            
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo site search error: {e}")
            return []
    
    async def _search_yandex(self, query: str, max_results: int, return_full_results: bool = False) -> List:
        """Search Yandex"""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self.yandex_search.search, query, max_results
            )
            
            if self.enable_exact_phrase_filter and self.phrase_matcher and return_full_results:
                filtered_results, _ = self._filter_results(results, query, site_pattern)
                return filtered_results
            
            if not return_full_results:
                return [r.get('url', '') for r in results if r.get('url')]
            
            return results
        except Exception as e:
            logger.error(f"Yandex site search error: {e}")
            return []

def is_site_query(query: str) -> bool:
    """Check if query contains site: operator"""
    return 'site:' in query.lower()

def extract_site_info(query: str) -> Tuple[str, str]:
    """
    Extract base query and site restriction from a site: query
    
    Returns:
        Tuple of (base_query, site_restriction)
    """
    if 'site:' not in query.lower():
        return query, ""
    
    # Split on site: and extract
    parts = query.split('site:', 1)
    base_query = parts[0].strip()
    
    # Extract site restriction (handle quotes)
    site_part = parts[1].strip()
    if ' ' in site_part:
        # Site restriction ends at first space
        site_restriction = site_part.split()[0]
    else:
        site_restriction = site_part
    
    return base_query, site_restriction

async def main():
    """Main function for testing"""
    logger.info("""
    Site Search - Domain/TLD-restricted search
    
    Examples:
    - Domain: "artificial intelligence site:nytimes.com"
    - TLD: "German companies site:.de"
    - Pattern: "annual report site:*.pdf/*"
    """)
    
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
    else:
        query = input("Enter site search query: ").strip()
    
    if not query:
        logger.error("Query required!")
        return
    
    searcher = SiteSearch()
    
    # Determine search type
    if is_site_query(query):
        base_query, site_restriction = extract_site_info(query)
        
        if site_restriction.startswith('.'):
            # TLD search
            results = await searcher.search_by_tld(base_query, site_restriction[1:])
        elif '*' in site_restriction:
            # Pattern search
            results = await searcher.search_by_pattern(base_query, site_restriction)
        else:
            # Domain search
            results = await searcher.search_by_domain(base_query, site_restriction)
    else:
        # No site restriction, just do regular search
        results = await searcher._execute_searches(query, 100)
    
    # Display results
    logger.info(f"\nResults for: {query}")
    logger.info("=" * 60)
    
    total_results = 0
    for engine, urls in results.items():
        logger.info(f"\n{engine.upper()} ({len(urls)} results):")
        for url in urls[:10]:  # Show first 10 from each engine
            logger.info(f"  {url}")
        total_results += len(urls)
    
    logger.info(f"\nTotal results found: {total_results}")

if __name__ == "__main__":
    asyncio.run(main())