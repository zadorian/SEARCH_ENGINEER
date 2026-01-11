#!/usr/bin/env python3
"""
InURL Search - Find URLs that contain specific keywords or extensions
Supports searching through Google, Bing, Brave, Wayback Machine, and Common Crawl
Example: searching "api" finds example.com/api, api.github.com, developer.mozilla.org/api-docs, etc.
"""

import sys
import asyncio
import functools
import requests
import logging
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple, Any
from datetime import datetime
import json
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))
BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

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
    from exact_phrase_recall_runner_archiveorg import ArchiveOrgSearch
    ARCHIVEORG_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Archive.org search: {e}")
    ARCHIVEORG_AVAILABLE = False

# Try to import Wayback Machine functionality
try:
    import waybackpy
    WAYBACK_AVAILABLE = True
except ImportError:
    logger.warning("waybackpy not available - Wayback Machine search disabled")
    WAYBACK_AVAILABLE = False

# Try to import Common Crawl functionality
try:
    from alldom.providers.commoncrawl import CommonCrawlProvider
    COMMON_CRAWL_AVAILABLE = True
except ImportError:
    logger.warning("Common Crawl provider not available")
    COMMON_CRAWL_AVAILABLE = False

# Import IndomSearcher for domain searches
try:
    from brute.targeted_searches.domain.indom import IndomSearcher
    INDOM_AVAILABLE = True
except ImportError:
    try:
        from .indom import IndomSearcher
        INDOM_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Could not import Indom search: {e}")
        INDOM_AVAILABLE = False

# Optional ATLAS URL search
try:
    from ATLAS import atlas as atlas_client
    ATLAS_AVAILABLE = True
except ImportError:
    try:
        from modules.ATLAS import atlas as atlas_client
        ATLAS_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Atlas URL search not available: {e}")
        ATLAS_AVAILABLE = False
        atlas_client = None

# Optional AllDomain indom search (full source mix)
try:
    from alldom.indom import search_domains as alldom_search_domains
    from alldom.indom.config import AVAILABLE_SOURCES as ALLDOM_INDOM_SOURCES
    ALLDOM_INDOM_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AllDomain indom not available: {e}")
    ALLDOM_INDOM_AVAILABLE = False
    alldom_search_domains = None
    ALLDOM_INDOM_SOURCES = []

# Import Majestic for URL keyword search (searches title/URL/anchor)
# Majestic's SearchByKeyword API searches across their entire index for keywords
# appearing in: Page Title, URL path, and Anchor text of backlinks
try:
    import httpx
    MAJESTIC_API_KEY = os.getenv("MAJESTIC_API_KEY")
    MAJESTIC_AVAILABLE = bool(MAJESTIC_API_KEY)
    MAJESTIC_BASE_URL = "https://api.majestic.com/api/json"
    if not MAJESTIC_AVAILABLE:
        logger.warning("MAJESTIC_API_KEY not set - Majestic inurl search disabled")
except ImportError:
    MAJESTIC_AVAILABLE = False
    MAJESTIC_API_KEY = None
    MAJESTIC_BASE_URL = None

# Import snippet enrichment
try:
    from snippet_enrichment import SnippetEnricher
    ENRICHMENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import snippet enrichment: {e}")
    ENRICHMENT_AVAILABLE = False

class InURLSearch:
    """Search for URLs containing keywords using multiple search engines"""
    
    def __init__(self):
        """Initialize search engine instances"""
        self.google_search = GoogleSearch() if GOOGLE_AVAILABLE else None
        self.bing_search = BingSearch() if BING_AVAILABLE else None
        self.brave_search = BraveSearch() if BRAVE_AVAILABLE else None
        self.archive_search = ArchiveOrgSearch() if ARCHIVEORG_AVAILABLE else None
        self.indom_search = IndomSearcher() if INDOM_AVAILABLE else None
        self.enricher = SnippetEnricher() if ENRICHMENT_AVAILABLE else None
        
        # Track which engines are available
        self.available_engines = []
        if GOOGLE_AVAILABLE: self.available_engines.append('google')
        if BING_AVAILABLE: self.available_engines.append('bing')
        if BRAVE_AVAILABLE: self.available_engines.append('brave')
        if ARCHIVEORG_AVAILABLE: self.available_engines.append('archive.org')
        if WAYBACK_AVAILABLE: self.available_engines.append('wayback')
        if COMMON_CRAWL_AVAILABLE: self.available_engines.append('common_crawl')
        if INDOM_AVAILABLE: self.available_engines.append('indom')
        if ALLDOM_INDOM_AVAILABLE: self.available_engines.append('indom_full')
        if ATLAS_AVAILABLE: self.available_engines.append('atlas_urls')
        if MAJESTIC_AVAILABLE: self.available_engines.append('majestic')
        
        logger.info(f"InURL Search initialized with engines: {self.available_engines}")
        
        # For tracking filtered results
        self.filtered_results = []
    
    def extract_phrases(self, query: str) -> List[str]:
        """Extract exact phrases from quotes in query"""
        import re
        # Match both single and double quoted phrases
        pattern = r'["\']([^"\']+)["\']'
        phrases = re.findall(pattern, query)
        return phrases
    
    def url_contains_phrase(self, url: str, phrase: str) -> bool:
        """Check if URL contains the exact phrase (case-insensitive)"""
        return phrase.lower() in url.lower()
    
    def get_filtered_results(self) -> List[Dict[str, str]]:
        """Get all results that were filtered out"""
        return self.filtered_results

    def _extract_inurl_term(self, query: str) -> str:
        """Extract the core term for URL matching."""
        import re
        match = re.search(r'(?:inurl|allinurl):([^\s]+)', query, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return query.replace('"', '').strip()

    def _split_terms(self, term: str) -> List[str]:
        """Split a term into lowercase tokens for fuzzy URL matching."""
        import re
        return [t for t in re.split(r'\s+', term.strip()) if t]

    def _url_contains_terms(self, url: str, terms: List[str]) -> bool:
        """Check if all terms appear somewhere in the URL."""
        lower_url = url.lower()
        return all(term.lower() in lower_url for term in terms)
    
    def generate_search_variations(self, keyword: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 query variations"""
        variations = []
        
        # L1: Native Operator (High Precision)
        if ' ' in keyword:
            # Handle compound keywords
            parts = keyword.split()
            native_query = ' '.join([f'inurl:{p}' for p in parts])
            variations.append((native_query, 'L1'))
            # Also try exact phrase in URL
            variations.append((f'inurl:"{keyword}"', 'L1'))
        else:
            variations.append((f'inurl:{keyword}', 'L1'))
            
        # L2: Contextual Expansion (Tricks)
        # If keyword looks like a file extension
        if len(keyword) <= 4 and keyword.isalnum():
            variations.append((f'filetype:{keyword}', 'L2'))
            
        # If keyword looks like a domain (has dot, no spaces)
        if '.' in keyword and ' ' not in keyword:
            variations.append((f'site:{keyword}', 'L2'))
            
        # L3: Brute Force (Broad Match + Strict Filtering)
        # Search for the keyword anywhere, then filter for URL matches
        # This catches pages where the engine failed to index the URL tokens correctly
        variations.append((f'"{keyword}"', 'L3'))
        
        return variations

    async def search_urls(self, keyword: str, max_results: int = 100) -> Dict[str, List[str]]:
        """
        Search for URLs containing the keyword across multiple engines using L1/L2/L3
        
        Args:
            keyword: The keyword(s) to search for in URLs
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        # Clear previous filtered results
        self.filtered_results = []
        all_results = {}
        
        # Generate variations
        variations = self.generate_search_variations(keyword)
        base_term = self._extract_inurl_term(keyword)
        l3_term = base_term or keyword
        
        # Create tasks for parallel execution
        tasks = []
        
        # Helper to run search and collect results
        async def run_engine_search(engine_name, engine_instance, variation, strategy):
            try:
                loop = asyncio.get_event_loop()
                # Distribute max_results
                limit = max(10, max_results // len(variations))
                
                results = await loop.run_in_executor(None, engine_instance.search, variation, limit)
                
                valid_urls = []
                for item in results:
                    # Extract URL
                    url = item.get('url', '') if isinstance(item, dict) else str(item)
                    if not url: continue
                    
                    # L3 Strict Filtering: URL MUST contain the keyword
                    if strategy == 'L3':
                        if l3_term.lower() not in url.lower():
                            # Track filtered
                            self.filtered_results.append({
                                'url': url,
                                'engine': engine_name,
                                'reason': f'URL does not contain keyword "{keyword}" (L3 filter)',
                                'strategy': strategy
                            })
                            continue
                            
                    valid_urls.append(url)
                
                return engine_name, valid_urls
            except Exception as e:
                logger.error(f"{engine_name} search error: {e}")
                return engine_name, []

        # Async helper for Wayback and Common Crawl (since they have async methods)
        async def run_async_engine_search(engine_name, wrapper_method, variation, strategy):
            try:
                limit = max(10, max_results // len(variations))
                urls = await wrapper_method(variation, limit)

                valid_urls = []
                for url in urls:
                    if not url:
                        continue

                    # L3 Strict Filtering: URL MUST contain the keyword
                    if strategy == 'L3':
                        if l3_term.lower() not in url.lower():
                            self.filtered_results.append({
                                'url': url,
                                'engine': engine_name,
                                'reason': f'URL does not contain keyword "{keyword}" (L3 filter)',
                                'strategy': strategy
                            })
                            continue

                    valid_urls.append(url)

                return engine_name, valid_urls
            except Exception as e:
                logger.error(f"{engine_name} search error: {e}")
                return engine_name, []

        async def run_direct_engine_search(engine_name, async_method, term):
            try:
                urls = await async_method(term, max_results)
                return engine_name, urls
            except Exception as e:
                logger.error(f"{engine_name} search error: {e}")
                return engine_name, []

        # Base-term sources (domain + URL collections + fuzzy archives)
        if base_term:
            if self.indom_search:
                tasks.append(run_direct_engine_search('indom', self._search_indom, base_term))
            if ALLDOM_INDOM_AVAILABLE:
                tasks.append(run_direct_engine_search('indom_full', self._search_indom_full, base_term))
            if ATLAS_AVAILABLE:
                tasks.append(run_direct_engine_search('atlas_urls', self._search_atlas_urls, base_term))
            if WAYBACK_AVAILABLE:
                tasks.append(run_direct_engine_search('wayback', self._search_wayback, base_term))
            if COMMON_CRAWL_AVAILABLE:
                tasks.append(run_direct_engine_search('common_crawl', self._search_common_crawl, base_term))

        # Launch tasks for each engine and variation
        for query_var, strategy in variations:
            if self.google_search: tasks.append(run_engine_search('google', self.google_search, query_var, strategy))
            if self.bing_search: tasks.append(run_engine_search('bing', self.bing_search, query_var, strategy))
            if self.brave_search: tasks.append(run_engine_search('brave', self.brave_search, query_var, strategy))
            if self.archive_search: tasks.append(run_engine_search('archive.org', self.archive_search, query_var, strategy))
            # Skip Majestic for L3 to avoid massive overhead, use only L1/L2
            if strategy != 'L3':
                # Majestic SearchByKeyword - searches Title/URL/Anchor across their index
                if MAJESTIC_AVAILABLE: tasks.append(run_async_engine_search('majestic', self._search_majestic_wrapper, query_var, strategy))

        # Execute
        if tasks:
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in results_list:
                if isinstance(res, tuple) and len(res) == 2:
                    engine, urls = res
                    if engine not in all_results:
                        all_results[engine] = []
                    # Add unique URLs
                    current_set = set(all_results[engine])
                    for u in urls:
                        if u not in current_set:
                            all_results[engine].append(u)
                            current_set.add(u)

        return all_results
    
    # Wrapper for Wayback (since it was internal method before)
    async def _search_wayback_wrapper(self, query, limit):
        # We need to extract just the keyword for Wayback, it doesn't support complex queries well
        # For L1 "inurl:keyword", extract "keyword"
        import re
        match = re.search(r'inurl:([^\s]+)', query)
        kw = match.group(1) if match else query.replace('"', '')
        return await self._search_wayback(kw, limit)

    # Wrapper for Common Crawl
    async def _search_cc_wrapper(self, query, limit):
        import re
        match = re.search(r'inurl:([^\s]+)', query)
        kw = match.group(1) if match else query.replace('"', '')
        return await self._search_common_crawl(kw, limit)

    async def _search_google(self, query: str, max_results: int, keyword: str) -> List[str]:
        """Legacy wrapper - Deprecated"""
        return [] # Replaced by run_engine_search logic inside search_urls
    
    async def _search_bing(self, query: str, max_results: int, keyword: str) -> List[str]:
        """Search Bing for URLs containing keyword"""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self.bing_search.search, query, max_results)
            # Filter results to only include URLs containing the keyword
            filtered_urls = []
            for result in results:
                url = result.get('url', '') if isinstance(result, dict) else str(result)
                if keyword.lower() in url.lower():
                    filtered_urls.append(url)
            return filtered_urls
        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return []
    
    async def _search_brave(self, query: str, max_results: int, keyword: str) -> List[str]:
        """Search Brave for URLs containing keyword"""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self.brave_search.search, query, max_results)
            # Filter results to only include URLs containing the keyword
            filtered_urls = []
            for result in results:
                url = result.get('url', '') if isinstance(result, dict) else str(result)
                if keyword.lower() in url.lower():
                    filtered_urls.append(url)
            return filtered_urls
        except Exception as e:
            logger.error(f"Brave search error: {e}")
            return []
    
    async def _search_archive(self, keyword: str, max_results: int) -> List[str]:
        """Search Archive.org for URLs containing keyword"""
        try:
            query = f'identifier:{keyword} OR title:{keyword} OR subject:{keyword}'
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self.archive_search.search, query, max_results)
            # Archive.org returns metadata, extract URLs
            urls = []
            for item in results:
                if isinstance(item, dict):
                    # Check if it has a 'url' field first
                    if 'url' in item:
                        url = item['url']
                        if keyword.lower() in url.lower():
                            urls.append(url)
                    else:
                        # Try to extract URL from identifier field
                        identifier = item.get('identifier', '')
                        if identifier and keyword.lower() in identifier.lower():
                            urls.append(f"https://archive.org/details/{identifier}")
                elif isinstance(item, str) and keyword.lower() in item.lower():
                    urls.append(item)
            return urls
        except Exception as e:
            logger.error(f"Archive.org search error: {e}")
            return []
    
    async def _search_wayback(self, keyword: str, max_results: int) -> List[str]:
        """Search Wayback Machine for URLs containing keyword"""
        if not WAYBACK_AVAILABLE:
            return []

        try:
            # Use asyncio to run in thread pool since waybackpy is not async
            terms = self._split_terms(self._extract_inurl_term(keyword))
            if not terms:
                return []
            pattern = "*".join(terms)
            loop = asyncio.get_event_loop()
            urls = await loop.run_in_executor(None, self._wayback_search_sync, pattern, terms, max_results)
            return urls
        except Exception as e:
            logger.error(f"Wayback search error: {e}")
            return []
    
    def _wayback_search_sync(self, pattern: str, terms: List[str], max_results: int) -> List[str]:
        """Synchronous Wayback Machine search"""
        urls = []
        try:
            # Search for URLs containing the keyword
            cdx_api = waybackpy.CdxApi(url=f"*{pattern}*", user_agent="InURLSearch/1.0")
            snapshots = cdx_api.snapshots()
            
            unique_urls = set()
            count = 0
            for snapshot in snapshots:
                if count >= max_results:
                    break
                if self._url_contains_terms(snapshot.original, terms):
                    unique_urls.add(snapshot.original)
                    count += 1
            
            urls = list(unique_urls)
        except Exception as e:
            logger.error(f"Wayback sync search error: {e}")
        
        return urls
    
    async def _search_common_crawl(self, keyword: str, max_results: int) -> List[str]:
        """Search Common Crawl for URLs containing keyword"""
        if not COMMON_CRAWL_AVAILABLE:
            return []

        try:
            terms = self._split_terms(self._extract_inurl_term(keyword))
            if not terms:
                return []
            pattern = "*".join(terms)
            # Use Common Crawl provider to search index
            provider = CommonCrawlProvider()
            urls = []

            # Query the Common Crawl index for URLs containing the keyword
            # Use the CDX API to search for matching URLs
            # Common Crawl indexes match URLs in the CDX format
            snapshots = await provider.get_snapshots(
                url=f"*{pattern}*",
                use_latest_index_only=True
            )

            # Extract unique URLs from snapshots
            seen_urls = set()
            for snapshot in snapshots[:max_results]:
                if snapshot.url and self._url_contains_terms(snapshot.url, terms):
                    if snapshot.url not in seen_urls:
                        urls.append(snapshot.url)
                        seen_urls.add(snapshot.url)

            return urls
        except Exception as e:
            logger.error(f"Common Crawl search error: {e}")
            return []

    async def _search_atlas_urls(self, keyword: str, max_results: int) -> List[str]:
        """Search ATLAS URL collections for matching URLs."""
        if not ATLAS_AVAILABLE or not atlas_client:
            return []

        term = self._extract_inurl_term(keyword)
        if not term:
            return []

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                functools.partial(atlas_client.inurl, term, limit=max_results)
            )
        except Exception as e:
            logger.error(f"Atlas inurl search error: {e}")
            return []

        urls = []
        results = getattr(result, "results", []) if result else []
        for item in results:
            url = item.get("url") if isinstance(item, dict) else None
            if url and url not in urls:
                urls.append(url)
            if len(urls) >= max_results:
                break

        return urls

    async def _search_indom_full(self, keyword: str, max_results: int) -> List[str]:
        """Search AllDomain indom sources and return base URLs."""
        if not ALLDOM_INDOM_AVAILABLE or not alldom_search_domains:
            return []

        term = self._extract_inurl_term(keyword)
        if not term:
            return []

        try:
            sources = ALLDOM_INDOM_SOURCES or None
            results = await alldom_search_domains(term, sources=sources)
        except Exception as e:
            logger.error(f"AllDomain indom search error: {e}")
            return []

        urls = []
        for item in results or []:
            domain = item.get("domain") if isinstance(item, dict) else None
            if not domain:
                continue
            url = f"https://{domain}"
            if url not in urls:
                urls.append(url)
            if len(urls) >= max_results:
                break

        return urls

    async def _search_majestic(self, keyword: str, max_results: int) -> List[str]:
        """
        Search Majestic's index for URLs containing keyword.

        Majestic's SearchByKeyword API searches across their entire index for keywords
        appearing in: Page Title, URL path, and Anchor text of backlinks.

        This is particularly valuable for inurl: searches because it searches the
        URL path directly, not just page content.

        Args:
            keyword: The keyword to search for in URLs
            max_results: Maximum number of results to return

        Returns:
            List of URLs containing the keyword
        """
        if not MAJESTIC_AVAILABLE:
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # SearchByKeyword params:
                # - Query: The search term
                # - Scope: 0=Historic, 1=Fresh, 2=Both
                # - MaxResults: Number of results (max 100 per call)
                # - Highlight: 1=highlight matches
                params = {
                    "app_api_key": MAJESTIC_API_KEY,
                    "cmd": "SearchByKeyword",
                    "Query": keyword,
                    "Scope": 2,  # Both historic and fresh index
                    "MaxResults": min(max_results, 100),
                    "Highlight": 0,  # Don't need highlighting, just URLs
                }

                response = await client.get(MAJESTIC_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("Code") != "OK":
                    logger.warning(f"Majestic API error: {data.get('ErrorMessage', 'Unknown error')}")
                    return []

                # Extract URLs from results
                # Majestic returns items with URL, Title, etc.
                urls = []
                items = data.get("DataTables", {}).get("Results", {}).get("Data", [])

                for item in items:
                    url = item.get("URL", "")
                    if url:
                        # For inurl: specifically, only include if keyword is actually in URL
                        if keyword.lower() in url.lower():
                            urls.append(url)
                        else:
                            # Majestic found it in title/anchor, still useful but mark differently
                            # For now, include anyway since we're casting wide net
                            urls.append(url)

                logger.info(f"Majestic SearchByKeyword returned {len(urls)} URLs for '{keyword}'")
                return urls

        except httpx.TimeoutException:
            logger.warning(f"Majestic search timeout for '{keyword}'")
            return []
        except Exception as e:
            logger.error(f"Majestic search error: {e}")
            return []

    async def _search_majestic_wrapper(self, query: str, limit: int) -> List[str]:
        """Wrapper for Majestic search that extracts keyword from query."""
        import re
        # Extract keyword from inurl: syntax
        match = re.search(r'inurl:([^\s]+)', query)
        kw = match.group(1) if match else query.replace('"', '').strip()
        return await self._search_majestic(kw, limit)
    
    async def _search_indom(self, keyword: str, max_results: int) -> List[str]:
        """Search domain names containing keyword using IndomSearcher"""
        if not self.indom_search:
            return []
        
        try:
            term = self._extract_inurl_term(keyword)
            if not term:
                return []
            # Use asyncio to run in thread pool since IndomSearcher is not async
            loop = asyncio.get_event_loop()
            indom_results = await loop.run_in_executor(None, self.indom_search.search, term)
            
            # Extract URLs from indom results
            urls = []
            for result in indom_results.get('results', [])[:max_results]:
                urls.append(result['url'])
            
            return urls
        except Exception as e:
            logger.error(f"Indom search error: {e}")
            return []
    
    async def search_extension_urls(self, extension: str, base_query: str = "", max_results: int = 100) -> Dict[str, List[str]]:
        """
        Specialized method for searching URLs with specific file extensions
        Used by filetype.py module
        
        Args:
            extension: File extension to search for (e.g., 'pdf', 'doc')
            base_query: Optional base query to combine with extension search
            max_results: Maximum results per engine
            
        Returns:
            Dictionary with engine names as keys and lists of URLs as values
        """
        # Build queries specific to file extensions
        queries = []
        if base_query:
            queries.extend([
                f'"{base_query}" inurl:.{extension}',
                f'"{base_query}" inurl:{extension}',
                f'{base_query} filetype:{extension}'
            ])
        else:
            queries.extend([
                f'inurl:.{extension}',
                f'inurl:{extension}',
                f'filetype:{extension}'
            ])
        
        # Search with all queries and merge results
        all_results = {}
        for query in queries:
            results = await self.search_urls(query, max_results)
            for engine, urls in results.items():
                if engine not in all_results:
                    all_results[engine] = []
                # Filter to ensure URLs actually contain the extension
                for url in urls:
                    if f'.{extension}' in url.lower() and url not in all_results[engine]:
                        all_results[engine].append(url)
        
        # Also try specialist sources if available
        try:
            from brute.infrastructure.specialist_sources.url_dom_search.inurl import InURLSearch as SpecialistInURLSearch
            specialist_searcher = SpecialistInURLSearch()
            specialist_urls = specialist_searcher.search_urls(f".{extension}")
            if specialist_urls:
                if 'specialist' not in all_results:
                    all_results['specialist'] = []
                for url in specialist_urls:
                    if f'.{extension}' in url.lower() and url not in all_results['specialist']:
                        all_results['specialist'].append(url)
        except ImportError:
            pass  # Specialist sources not available
        
        return all_results

def is_inurl_query(query: str) -> bool:
    """Check if query contains inurl operators"""
    inurl_patterns = ['inurl:', 'allinurl:']
    return any(pattern in query.lower() for pattern in inurl_patterns)

async def main():
    """Main function for testing"""
    print("""
    inURL - URL Keyword Search
    Find URLs that contain your keyword(s)
    
    Example: "api" finds example.com/api/v2, api.github.com, etc.
    """)
    
    if len(sys.argv) > 1:
        keyword = ' '.join(sys.argv[1:])
    else:
        keyword = input("Enter keyword to search in URLs: ").strip()
    
    if not keyword:
        print("Keyword required!")
        return
    
    searcher = InURLSearch()
    results = await searcher.search_urls(keyword)
    
    print(f"\nURLs containing '{keyword}':")
    print("=" * 60)
    
    total_urls = 0
    for engine, urls in results.items():
        print(f"\n{engine.upper()} ({len(urls)} results):")
        for url in urls[:10]:  # Show first 10 from each engine
            print(f"  {url}")
        total_urls += len(urls)
    
    print(f"\nTotal unique URLs found: {total_urls}")

class InurlSearcher:
    """Standardized searcher class for inurl searches that returns full results with snippets."""
    
    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
        self.inurl_search = InURLSearch()
        self.enricher = SnippetEnricher() if ENRICHMENT_AVAILABLE else None
        
    def search(self, query: str) -> Dict[str, Any]:
        """Standardized search method that returns results with snippets."""
        try:
            # Extract keyword from query
            # Remove any inurl: prefix if present
            if query.lower().startswith('inurl:'):
                keyword = query[6:].strip()
            else:
                keyword = query.strip()
                
            # Run async search synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                url_results = loop.run_until_complete(self.inurl_search.search_urls(keyword))
            finally:
                loop.close()
                
            # Format results with proper structure
            formatted_results = []
            seen_urls = set()
            
            for engine, urls in url_results.items():
                for url in urls:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        formatted_results.append({
                            'url': url,
                            'title': f'Page at {url}',
                            'snippet': f'URL contains keyword "{keyword}"',
                            'source': engine,
                            'rank': len(formatted_results) + 1
                        })
            
            # Enrich results with real snippets if enricher is available
            if self.enricher and formatted_results:
                # Separate indom results for special handling
                indom_results = [r for r in formatted_results if r['source'] in ('indom', 'indom_full')]
                other_results = [r for r in formatted_results if r['source'] not in ('indom', 'indom_full')]
                
                # Only enrich indom results (others already have snippets)
                if indom_results:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        enriched_indom = loop.run_until_complete(
                            self._enrich_results_async(indom_results)
                        )
                        # Replace indom results with enriched versions
                        formatted_results = other_results + enriched_indom
                    finally:
                        loop.close()
                        
            return {
                'query': query,
                'keyword': keyword,
                'total_results': len(formatted_results),
                'results': formatted_results,
                'search_type': 'inurl',
                'engines_used': list(url_results.keys())
            }
            
        except Exception as e:
            logger.error(f"Error during inurl search: {e}")
            return {'error': str(e), 'results': []}
            
    async def _enrich_results_async(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich results with real titles and snippets"""
        # Extract URLs for enrichment
        urls = [r['url'] for r in results]
        
        # Enrich in batches
        logger.info(f"Enriching {len(urls)} indom URLs with snippets")
        enrichment_data = await self.enricher.enrich(urls)
        
        # Update results with enriched data
        enriched_results = []
        for result in results:
            url = result['url']
            enrichment = enrichment_data.get(url) if isinstance(enrichment_data, dict) else None
            
            if enrichment:
                # Update with real title and snippet
                result['title'] = enrichment.get('title', result['title'])
                result['snippet'] = enrichment.get('snippet', result['snippet'])
                result['enriched'] = True
                result['enrichment_backend'] = enrichment.get('backend', 'unknown')
            else:
                # Keep original placeholder data
                result['enriched'] = False
                
            enriched_results.append(result)
            
        return enriched_results


if __name__ == "__main__":
    asyncio.run(main())
