#!/usr/bin/env python3
"""
Apify Google SERP Search Engine

Uses Apify's Google Search Results Scraper Actor for reliable SERP results.
Actor ID: nFJndFXA5zjCTuudP
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Import reverse embedding collector for related queries
try:
    from modules.brute.reverse_embedding import RelatedQueryCollector
    REVERSE_EMBEDDING_AVAILABLE = True
except ImportError:
    REVERSE_EMBEDDING_AVAILABLE = False
    logger.debug("Reverse embedding module not available")

# Try to import Apify client
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    logger.warning("apify_client not installed: pip install apify-client")

APIFY_TOKEN = os.getenv('APIFY_API_TOKEN') or os.getenv('APIFY_TOKEN')
ACTOR_ID = "nFJndFXA5zjCTuudP"  # Google Search Results Scraper

# Proxy types for bypassing blocks
PROXY_CONFIGS = {
    'datacenter': {'useApifyProxy': True},
    'residential': {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL']},
    'residential_us': {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL'], 'apifyProxyCountry': 'US'},
    'none': None,
}


class ApifySerpSearch:
    """Apify Google SERP search client."""

    def __init__(self, api_token: str = None):
        self.api_token = api_token or APIFY_TOKEN
        if not self.api_token:
            logger.warning("APIFY_API_TOKEN not set")
        self.client = ApifyClient(self.api_token) if APIFY_AVAILABLE and self.api_token else None

    def search(
        self,
        query: str,
        max_results: int = 100,
        country_code: str = None,
        language_code: str = None,
        force_exact_match: bool = True,
        file_types: List[str] = None,
        site: str = None,
        words_in_title: List[str] = None,
        words_in_url: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Google via Apify SERP Actor.

        Args:
            query: Search query
            max_results: Max results (up to 100 per page)
            country_code: Country code (US, GB, DE, etc.)
            language_code: Language code (en, de, fr, etc.)
            force_exact_match: Force exact phrase matching
            file_types: List of file types (pdf, doc, etc.)
            site: Limit to specific site
            words_in_title: Words that must appear in title
            words_in_url: Words that must appear in URL

        Returns:
            List of search results
        """
        if not self.client:
            logger.error("Apify client not available")
            return []

        try:
            run_input = {
                "queries": query,
                "resultsPerPage": min(max_results, 100),
                "maxPagesPerQuery": max(1, max_results // 100),
                "aiMode": "aiModeOff",
                "forceExactMatch": force_exact_match,
                "countryCode": country_code,
                "languageCode": language_code or "",
                "searchLanguage": "",
                "fileTypes": ",".join(file_types) if file_types else None,
                "site": site,
                "wordsInTitle": words_in_title or [],
                "wordsInUrl": words_in_url or [],
                "wordsInText": [],
                "mobileResults": False,
                "includeUnfilteredResults": False,
                "saveHtml": False,
                "saveHtmlToKeyValueStore": False,
                "includeIcons": False,
                "focusOnPaidAds": False,
                "maximumLeadsEnrichmentRecords": 0,
            }

            logger.info(f"Apify SERP: Running actor for query: {query[:50]}...")
            
            # Run the Actor and wait for completion
            run = self.client.actor(ACTOR_ID).call(run_input=run_input, timeout_secs=120)

            results = []
            # Initialize collector for related queries
            collector = None
            if REVERSE_EMBEDDING_AVAILABLE:
                try:
                    collector = RelatedQueryCollector()
                except Exception as e:
                    logger.debug(f"Could not init collector: {e}")
            
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                # Extract organic results
                organic = item.get("organicResults", [])
                for r in organic:
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("description", "") or r.get("snippet", ""),
                        "position": r.get("position"),
                        "engine": "Apify",
                        "source": "apify_serp",
                    })
                
                # Collect related queries and PAA for reverse embedding
                if collector:
                    try:
                        collector.collect_from_apify(query, item)
                    except Exception as e:
                        logger.debug(f"Failed to collect related: {e}")

            logger.info(f"Apify SERP: Got {len(results)} results")
            return results[:max_results]

        except Exception as e:
            logger.error(f"Apify SERP error: {e}")
            return []


class ExactPhraseRecallRunnerApify:
    """
    Apify SERP runner with Q-variations for max recall.
    """

    def __init__(self, api_token: str = None, phrase: str = None, keyword: str = None,
                 max_results: int = 100, event_emitter=None):
        self.phrase = phrase or keyword
        self.keyword = keyword or phrase
        self.max_results = max_results
        self.event_emitter = event_emitter
        self.client = ApifySerpSearch(api_token)
        self.results = []

    def _get_base_queries(self) -> dict:
        """AP1-AP4 variations for max recall."""
        quoted = f'"{self.phrase}"' if not self.phrase.startswith('"') else self.phrase
        return {
            "AP1_exact": quoted,
            "AP2_pdf": f"{quoted} filetype:pdf",
            "AP2_doc": f"{quoted} filetype:doc",
            "AP3_intitle": quoted,  # Use wordsInTitle parameter
            "AP4_inurl": quoted,    # Use wordsInUrl parameter
        }

    def run(self) -> List[Dict[str, Any]]:
        """Run all query variations."""
        if not self.client.client:
            logger.warning("Apify client not configured")
            return []

        all_results = []
        seen_urls = set()

        variations = self._get_base_queries()
        per_variation = max(20, self.max_results // len(variations))

        for tag, query in variations.items():
            try:
                # Special handling for intitle/inurl variations
                words_in_title = None
                words_in_url = None
                file_types = None
                search_query = query

                if tag == "AP3_intitle":
                    words_in_title = [self.phrase.strip('"')]
                    search_query = self.phrase
                elif tag == "AP4_inurl":
                    words_in_url = [self.phrase.strip('"').replace(' ', '-')]
                    search_query = self.phrase
                elif "filetype:" in query:
                    # Extract filetype
                    parts = query.split("filetype:")
                    search_query = parts[0].strip()
                    file_types = [parts[1].strip()]

                results = self.client.search(
                    query=search_query,
                    max_results=per_variation,
                    force_exact_match=True,
                    file_types=file_types,
                    words_in_title=words_in_title,
                    words_in_url=words_in_url,
                )

                for r in results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        r["_query_tag"] = tag
                        all_results.append(r)

                        if self.event_emitter:
                            try:
                                self.event_emitter(r)
                            except:
                                pass

            except Exception as e:
                logger.warning(f"Apify variation {tag} failed: {e}")
                continue

        self.results = all_results[:self.max_results]
        return self.results

    async def run_async(self):
        """Async wrapper."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            return await loop.run_in_executor(executor, self.run)


class ApifyEngine:
    """Wrapper for brute.py compatibility."""
    code = 'AP'
    name = 'Apify SERP'

    def __init__(self):
        self._runner_cls = ExactPhraseRecallRunnerApify

    def is_available(self) -> bool:
        return APIFY_AVAILABLE and bool(APIFY_TOKEN)

    def search(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        runner = self._runner_cls(phrase=query, max_results=max_results)
        return runner.run()


__all__ = ['ApifySerpSearch', 'ExactPhraseRecallRunnerApify', 'ApifyEngine', 'APIFY_AVAILABLE']
