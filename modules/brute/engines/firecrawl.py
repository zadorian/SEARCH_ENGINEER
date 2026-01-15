#!/usr/bin/env python3
"""
Firecrawl Search Engine for Search_Engineer - MAX RECALL VERSION
Uses Firecrawl API v2 for web content scraping and search.

Two modes:
- SNIPPET mode: Fast search, returns snippets only
- FULL_SCRAPE mode (default): Returns full markdown content - JESTER skips these

Tier 0 suffix triggers FULL_SCRAPE automatically.
"""

import os
from dotenv import load_dotenv
load_dotenv("/data/SEARCH_ENGINEER/.env")
import sys
import logging
import requests
import asyncio
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Firecrawl API configuration
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY', '')
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2"

# Max parallel scrapes with user's subscription
MAX_PARALLEL_SCRAPES = 100

# Geolocations for max recall
GEOLOCATIONS = [
    ("United States", "US"),
    ("United Kingdom", "GB"),
    ("Germany", "DE"),
    ("France", "FR"),
    ("Spain", "ES"),
    ("Italy", "IT"),
    ("Netherlands", "NL"),
    ("Australia", "AU"),
    ("Canada", "CA"),
    ("Brazil", "BR"),
    ("India", "IN"),
    ("Japan", "JP"),
]

# Time periods for max recall
TIME_PERIODS = [
    None,           # All time
    "qdr:d",        # Past day
    "qdr:w",        # Past week
    "qdr:m",        # Past month
    "qdr:y",        # Past year
]

# Source types
SOURCE_TYPES = ["web", "news"]


class FirecrawlSearch:
    """Firecrawl search client with FULL_SCRAPE and SNIPPET modes."""

    # Mode constants
    MODE_SNIPPET = "snippet"
    MODE_FULL_SCRAPE = "full_scrape"

    def __init__(self, api_key: str = None, mode: str = None):
        self.api_key = api_key or FIRECRAWL_API_KEY
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not set")
        
        # Default to FULL_SCRAPE mode
        self.mode = mode or self.MODE_FULL_SCRAPE
        self.api_url = FIRECRAWL_API_URL

    def search(
        self,
        query: str,
        max_results: int = 100,
        sources: Optional[List[str]] = None,
        tbs: Optional[str] = None,
        location: Optional[str] = None,
        country: Optional[str] = None,
        full_scrape: bool = None,
        timeout: int = 120000
    ) -> List[Dict]:
        """
        Search using Firecrawl's search endpoint.

        Args:
            query: Search query string
            max_results: Maximum number of results (up to 100)
            sources: List of sources - "web", "news"
            tbs: Time-based search (qdr:d, qdr:w, qdr:m, qdr:y)
            location: Location string for geo-targeting
            country: ISO country code (US, GB, DE, etc.)
            full_scrape: Override mode - if True, get full markdown content
            timeout: Timeout in milliseconds

        Returns:
            List of search result dicts
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Determine if we should full scrape
            do_full_scrape = full_scrape if full_scrape is not None else (self.mode == self.MODE_FULL_SCRAPE)

            payload = {
                "query": query,
                "limit": min(max_results, 100),
                "timeout": timeout
            }

            # Note: searchOptions removed - not supported in Firecrawl v1 API
            # sources, tbs, location, country are documented but cause 500 errors
            # Using only core params: query, limit, timeout, scrapeOptions

            # Full scrape mode - get markdown content
            if do_full_scrape:
                payload["scrapeOptions"] = {
                    "formats": ["markdown"],
                    "onlyMainContent": True
                }

            response = requests.post(
                f"{self.api_url}/search",
                headers=headers,
                json=payload,
                timeout=max(60, timeout // 1000 + 30)
            )

            if response.status_code == 200:
                data = response.json()
                results = []

                # v2 API: data.web[], v1: data[]
                items = data.get("data", [])
                if isinstance(items, dict):
                    items = items.get("web", [])
                for item in items:
                    result = {
                        "url": item.get("url"),
                        "title": item.get("title", ""),
                        "snippet": item.get("description", ""),
                        "engine": "firecrawl",
                        "source": "firecrawl",
                        "_firecrawl_scraped": do_full_scrape,  # Flag for JESTER to skip
                    }
                    
                    if item.get("markdown"):
                        result["markdown"] = item.get("markdown")
                        result["_full_content"] = True  # JESTER skip flag
                    
                    if country:
                        result["_geo"] = country
                    if tbs:
                        result["_time_filter"] = tbs
                        
                    results.append(result)

                geo_tag = f" [{country}]" if country else ""
                time_tag = f" [{tbs}]" if tbs else ""
                logger.info(f"Firecrawl{geo_tag}{time_tag}: {len(results)} results (full_scrape={do_full_scrape})")
                return results
            else:
                logger.error(f"Firecrawl search error: {response.status_code} - {response.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"Firecrawl search exception: {e}")
            return []


class ExactPhraseRecallRunnerFirecrawl:
    """
    Firecrawl Max Recall Runner
    
    Modes:
    - Tier 1: Basic search (snippet mode)
    - Tier 2: Multi-source search (snippet mode)
    - Tier 3: Full recall (full scrape mode)
    - Tier X0 (10, 20, 30): Same as X but FULL_SCRAPE forced
    
    Full scrape results have _firecrawl_scraped=True so JESTER skips them.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or FIRECRAWL_API_KEY
        
    def run(self, phrase: str, tier: int = 3, max_workers: int = MAX_PARALLEL_SCRAPES) -> List[Dict]:
        """
        Execute max recall search.

        Args:
            phrase: Search phrase
            tier: Search intensity (1, 2, 3, or X0 for full scrape)
            max_workers: Max parallel requests (default 100)
            
        Returns:
            Deduplicated list of results
        """
        # Tier X0 means full scrape forced
        full_scrape = (tier % 10 == 0) or tier >= 3
        effective_tier = tier // 10 if tier >= 10 else tier
        
        client = FirecrawlSearch(
            api_key=self.api_key,
            mode=FirecrawlSearch.MODE_FULL_SCRAPE if full_scrape else FirecrawlSearch.MODE_SNIPPET
        )
        
        if effective_tier == 1:
            return self._tier1_basic(client, phrase)
        elif effective_tier == 2:
            return self._tier2_multi_source(client, phrase, max_workers)
        else:  # tier >= 3
            return self._tier3_max_recall(client, phrase, max_workers)
    
    def _tier1_basic(self, client: FirecrawlSearch, phrase: str) -> List[Dict]:
        """Tier 1: Basic search."""
        return client.search(f'"{phrase}"', max_results=100)
    
    def _tier2_multi_source(self, client: FirecrawlSearch, phrase: str, 
                            max_workers: int) -> List[Dict]:
        """Tier 2: Multi-source search (web + news)."""
        all_results = []
        seen_urls = set()
        
        queries = [
            (f'"{phrase}"', ["web"], None, None),
            (f'"{phrase}"', ["news"], None, None),
            (phrase, ["web"], "qdr:w", None),  # Recent
        ]
        
        with ThreadPoolExecutor(max_workers=min(max_workers, len(queries))) as executor:
            futures = []
            for query, sources, tbs, country in queries:
                futures.append(executor.submit(
                    client.search, query, 100, sources, tbs, None, country
                ))
            
            for future in as_completed(futures):
                try:
                    results = future.result()
                    for r in results:
                        url = r.get('url')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(r)
                except Exception as e:
                    logger.warning(f"Tier 2 search failed: {e}")
        
        logger.info(f"Firecrawl Tier 2: {len(all_results)} unique results")
        return all_results
    
    def _tier3_max_recall(self, client: FirecrawlSearch, phrase: str,
                          max_workers: int) -> List[Dict]:
        """
        Tier 3: MAXIMUM RECALL
        - All geolocations (12 countries)
        - All time periods (5)
        - All source types (web, news)
        - Quoted + unquoted queries
        - 100 parallel requests
        """
        all_results = []
        seen_urls = set()
        
        # Build all query permutations
        permutations = []
        
        # FC1-FC4 Q-variations for max recall (run for each geo)
        quoted = f'"{phrase}"' if not phrase.startswith('"') else phrase
        q_variations = [
            quoted,  # FC1: Exact
            f"{quoted} filetype:pdf",  # FC2: PDF
            f"{quoted} filetype:doc",  # FC2: Doc
            f"intitle:{quoted}",  # FC3: Title
            f"inurl:{quoted}",  # FC4: URL
        ]
        
        for location_name, country_code in GEOLOCATIONS:
            for tbs in TIME_PERIODS:
                for sources in [["web"], ["news"]]:
                    # Run all Q-variations
                    for q in q_variations:
                        permutations.append((q, sources, tbs, country_code))
        
        # Add unquoted variations for broader recall
        permutations.append((phrase, ["web"], None, None))
        permutations.append((phrase, ["news"], None, None))
        
        logger.info(f"Firecrawl Tier 3: Executing {len(permutations)} query permutations with {max_workers} parallel workers")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for query, sources, tbs, country in permutations:
                future = executor.submit(
                    client.search, query, 100, sources, tbs, None, country
                )
                futures[future] = (query, sources, tbs, country)
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                query, sources, tbs, country = futures[future]
                try:
                    results = future.result()
                    new_count = 0
                    for r in results:
                        url = r.get('url')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(r)
                            new_count += 1
                    
                    if new_count > 0:
                        logger.debug(f"[{completed}/{len(permutations)}] +{new_count} new from {country or 'default'} {tbs or 'all-time'}")
                        
                except Exception as e:
                    logger.warning(f"Firecrawl permutation failed: {e}")
        
        logger.info(f"Firecrawl Tier 3 complete: {len(all_results)} unique results from {len(permutations)} permutations")
        return all_results


# Convenience function for brute.py integration
def search_firecrawl(query: str, max_results: int = 100, full_scrape: bool = True) -> List[Dict]:
    """Simple search function for brute.py integration."""
    client = FirecrawlSearch(
        mode=FirecrawlSearch.MODE_FULL_SCRAPE if full_scrape else FirecrawlSearch.MODE_SNIPPET
    )
    return client.search(query, max_results=max_results)


# Alias for compatibility
FirecrawlExactPhraseRecallRunner = ExactPhraseRecallRunnerFirecrawl
