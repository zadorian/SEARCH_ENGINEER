"""
Multi-Backend Search Architecture

Distributes queries across multiple backends to:
1. Maximize recall with all query variations
2. Avoid rate limits by distributing across backends
3. Aggregate results from all sources

Backends:
- SerpAPI: Google, Bing, Yandex searches
- Direct APIs: Google CSE, Bing API, Yandex API
- (Future) BrightData SERP when zone is configured

Usage:
    from multi_backend import MultiBackendSearch

    backend = MultiBackendSearch()

    # Search with automatic distribution
    results = await backend.search_google('"exact phrase"', max_results=100)
    results = await backend.search_bing('"exact phrase"', max_results=100)
    results = await backend.search_yandex('"exact phrase"', max_results=100)

    # Or use unified search
    results = await backend.search_all('"exact phrase"', engines=["google", "bing", "yandex"])
"""

import os
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import hashlib

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# API Keys
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "") or os.getenv("GOOGLE_CX", "")
BING_API_KEY = os.getenv("BING_API_KEY", "")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")


class MultiBackendSearch:
    """
    Multi-backend search that distributes queries across SerpAPI and direct APIs.
    """

    def __init__(self):
        self.name = "multi_backend"
        self.code = "MB"

        # Rate limiting state
        self._serpapi_last_call = 0
        self._serpapi_delay = 1.0  # 1 second between SerpAPI calls
        self._google_last_call = 0
        self._google_delay = 1.0
        self._bing_last_call = 0
        self._bing_delay = 0.5

        # Track which backend to use next (round-robin)
        self._google_backend_idx = 0
        self._bing_backend_idx = 0
        self._yandex_backend_idx = 0

        # Dedup cache
        self._seen_urls = set()

    def _rate_limit(self, backend: str) -> None:
        """Apply rate limiting for backend."""
        now = time.time()
        if backend == "serpapi":
            elapsed = now - self._serpapi_last_call
            if elapsed < self._serpapi_delay:
                time.sleep(self._serpapi_delay - elapsed)
            self._serpapi_last_call = time.time()
        elif backend == "google":
            elapsed = now - self._google_last_call
            if elapsed < self._google_delay:
                time.sleep(self._google_delay - elapsed)
            self._google_last_call = time.time()
        elif backend == "bing":
            elapsed = now - self._bing_last_call
            if elapsed < self._bing_delay:
                time.sleep(self._bing_delay - elapsed)
            self._bing_last_call = time.time()

    def _normalize_result(self, result: Dict, engine: str, backend: str) -> Dict:
        """Normalize result to standard format."""
        return {
            "title": result.get("title", ""),
            "url": result.get("link") or result.get("url") or result.get("displayLink", ""),
            "snippet": result.get("snippet") or result.get("description", ""),
            "source": f"{engine.upper()} via {backend}",
            "engine": engine,
            "backend": backend,
            "rank": result.get("position") or result.get("rank"),
        }

    def _dedup(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate URLs."""
        unique = []
        for r in results:
            url = r.get("url", "")
            url_hash = hashlib.md5(url.encode()).hexdigest()
            if url_hash not in self._seen_urls:
                self._seen_urls.add(url_hash)
                unique.append(r)
        return unique

    # ==================== GOOGLE ====================

    async def search_google(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search Google using ALL THREE backends:
        1. Google CSE API (native/direct)
        2. SerpAPI Google
        3. BrightData SERP Google
        """
        all_results = []

        # Calculate how many results from each backend
        per_backend = max_results // 3

        # Use ThreadPoolExecutor for sync API calls
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []

            # 1. Google CSE API (native)
            if GOOGLE_API_KEY and GOOGLE_CSE_ID:
                futures.append(executor.submit(
                    self._search_google_cse, query, per_backend
                ))

            # 2. SerpAPI Google
            if SERPAPI_KEY:
                futures.append(executor.submit(
                    self._search_google_serpapi, query, per_backend
                ))

            # 3. BrightData SERP Google
            futures.append(executor.submit(
                self._search_google_brightdata, query, per_backend
            ))

            for future in futures:
                try:
                    results = future.result(timeout=60)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Google backend error: {e}")

        return self._dedup(all_results)

    def _search_google_serpapi(self, query: str, max_results: int) -> List[Dict]:
        """Search Google via SerpAPI."""
        try:
            from serpapi import GoogleSearch
        except ImportError:
            logger.error("serpapi not installed")
            return []

        self._rate_limit("serpapi")
        results = []

        # Paginate through results (SerpAPI gives ~10 per page)
        for start in range(0, min(max_results, 100), 10):
            try:
                params = {
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "num": 10,
                    "start": start,
                }
                search = GoogleSearch(params)
                data = search.get_dict()

                organic = data.get("organic_results", [])
                for r in organic:
                    results.append(self._normalize_result(r, "google", "serpapi"))

                if len(organic) < 10:  # No more results
                    break

                self._rate_limit("serpapi")

            except Exception as e:
                logger.error(f"SerpAPI Google error at start={start}: {e}")
                break

        logger.info(f"Google SerpAPI: {len(results)} results")
        return results

    def _search_google_cse(self, query: str, max_results: int) -> List[Dict]:
        """Search Google via Custom Search Engine API."""
        import requests

        results = []
        base_url = "https://www.googleapis.com/customsearch/v1"

        # CSE API returns max 10 results per request, max 100 total
        for start in range(1, min(max_results + 1, 101), 10):
            try:
                self._rate_limit("google")

                params = {
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": query,
                    "start": start,
                    "num": 10,
                }

                resp = requests.get(base_url, params=params, timeout=30)

                if resp.status_code != 200:
                    logger.error(f"Google CSE error: {resp.status_code} - {resp.text[:200]}")
                    break

                data = resp.json()
                items = data.get("items", [])

                for r in items:
                    results.append(self._normalize_result(r, "google", "cse_api"))

                if len(items) < 10:
                    break

            except Exception as e:
                logger.error(f"Google CSE error at start={start}: {e}")
                break

        logger.info(f"Google CSE API: {len(results)} results")
        return results

    def _search_google_brightdata(self, query: str, max_results: int) -> List[Dict]:
        """Search Google via BrightData SERP API."""
        try:
            from serp_brightdata import fetch_serp_results
        except ImportError:
            try:
                from engines.serp_brightdata import fetch_serp_results
            except ImportError:
                logger.debug("BrightData SERP not available")
                return []

        results = []
        try:
            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                bd_results = loop.run_until_complete(
                    fetch_serp_results(query, engine="google", num=max_results)
                )
            finally:
                loop.close()

            for r in bd_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": "GOOGLE via brightdata_serp",
                    "engine": "google",
                    "backend": "brightdata_serp",
                })
            logger.info(f"Google BrightData SERP: {len(results)} results")
        except Exception as e:
            logger.warning(f"BrightData SERP Google error: {e}")

        return results

    # ==================== BING ====================

    async def search_bing(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search Bing using ALL THREE backends:
        1. Bing Web Search API (native/direct)
        2. SerpAPI Bing
        3. BrightData SERP Bing
        """
        all_results = []
        per_backend = max_results // 3

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []

            # 1. Bing API (native)
            if BING_API_KEY:
                futures.append(executor.submit(
                    self._search_bing_api, query, per_backend
                ))

            # 2. SerpAPI Bing
            if SERPAPI_KEY:
                futures.append(executor.submit(
                    self._search_bing_serpapi, query, per_backend
                ))

            # 3. BrightData SERP Bing
            futures.append(executor.submit(
                self._search_bing_brightdata, query, per_backend
            ))

            for future in futures:
                try:
                    results = future.result(timeout=60)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Bing backend error: {e}")

        return self._dedup(all_results)

    def _search_bing_serpapi(self, query: str, max_results: int) -> List[Dict]:
        """Search Bing via SerpAPI."""
        try:
            from serpapi import BingSearch
        except ImportError:
            logger.error("serpapi not installed")
            return []

        self._rate_limit("serpapi")
        results = []

        # Paginate (Bing SerpAPI uses first parameter, 1-based)
        offset = 1
        while len(results) < max_results:
            try:
                params = {
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "first": offset,
                    "count": 50,  # Bing allows more per page
                }
                search = BingSearch(params)
                data = search.get_dict()

                organic = data.get("organic_results", [])
                for r in organic:
                    results.append(self._normalize_result(r, "bing", "serpapi"))

                if len(organic) < 10:
                    break

                offset += len(organic)
                self._rate_limit("serpapi")

            except Exception as e:
                logger.error(f"SerpAPI Bing error at offset={offset}: {e}")
                break

        logger.info(f"Bing SerpAPI: {len(results)} results")
        return results[:max_results]

    def _search_bing_api(self, query: str, max_results: int) -> List[Dict]:
        """Search Bing via Web Search API."""
        import requests

        results = []
        base_url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}

        offset = 0
        while len(results) < max_results:
            try:
                self._rate_limit("bing")

                params = {
                    "q": query,
                    "count": 50,
                    "offset": offset,
                    "responseFilter": "Webpages",
                }

                resp = requests.get(base_url, headers=headers, params=params, timeout=30)

                if resp.status_code != 200:
                    logger.error(f"Bing API error: {resp.status_code} - {resp.text[:200]}")
                    break

                data = resp.json()
                webpages = data.get("webPages", {}).get("value", [])

                for r in webpages:
                    results.append({
                        "title": r.get("name", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", ""),
                        "source": "BING via api",
                        "engine": "bing",
                        "backend": "bing_api",
                    })

                if len(webpages) < 10:
                    break

                offset += len(webpages)

            except Exception as e:
                logger.error(f"Bing API error at offset={offset}: {e}")
                break

        logger.info(f"Bing API: {len(results)} results")
        return results[:max_results]

    def _search_bing_brightdata(self, query: str, max_results: int) -> List[Dict]:
        """Search Bing via BrightData SERP API."""
        try:
            from serp_brightdata import fetch_serp_results
        except ImportError:
            try:
                from engines.serp_brightdata import fetch_serp_results
            except ImportError:
                logger.debug("BrightData SERP not available")
                return []

        results = []
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                bd_results = loop.run_until_complete(
                    fetch_serp_results(query, engine="bing", num=max_results)
                )
            finally:
                loop.close()

            for r in bd_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": "BING via brightdata_serp",
                    "engine": "bing",
                    "backend": "brightdata_serp",
                })
            logger.info(f"Bing BrightData SERP: {len(results)} results")
        except Exception as e:
            logger.warning(f"BrightData SERP Bing error: {e}")

        return results

    # ==================== YANDEX ====================

    async def search_yandex(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search Yandex using SerpAPI.
        """
        all_results = []

        # SerpAPI Yandex
        if SERPAPI_KEY:
            results = self._search_yandex_serpapi(query, max_results)
            all_results.extend(results)

        return self._dedup(all_results)

    def _search_yandex_serpapi(self, query: str, max_results: int) -> List[Dict]:
        """Search Yandex via SerpAPI."""
        try:
            from serpapi import YandexSearch
        except ImportError:
            logger.error("serpapi not installed")
            return []

        self._rate_limit("serpapi")
        results = []

        page = 0
        while len(results) < max_results:
            try:
                params = {
                    "text": query,
                    "api_key": SERPAPI_KEY,
                    "p": page,
                }
                search = YandexSearch(params)
                data = search.get_dict()

                organic = data.get("organic_results", [])
                for r in organic:
                    results.append(self._normalize_result(r, "yandex", "serpapi"))

                if len(organic) < 10:
                    break

                page += 1
                self._rate_limit("serpapi")

            except Exception as e:
                logger.error(f"SerpAPI Yandex error at page={page}: {e}")
                break

        logger.info(f"Yandex SerpAPI: {len(results)} results")
        return results[:max_results]

    # ==================== UNIFIED SEARCH ====================

    async def search_all(
        self,
        query: str,
        engines: List[str] = None,
        max_results_per_engine: int = 50
    ) -> List[Dict]:
        """
        Search across all specified engines in parallel.

        Args:
            query: Search query (use quotes for exact phrase)
            engines: List of engines to search ["google", "bing", "yandex"]
            max_results_per_engine: Max results from each engine

        Returns:
            Deduplicated list of all results
        """
        if engines is None:
            engines = ["google", "bing", "yandex"]

        self._seen_urls.clear()  # Reset dedup for new search
        all_results = []

        # Create search tasks
        tasks = []
        for engine in engines:
            if engine == "google":
                tasks.append(self.search_google(query, max_results_per_engine))
            elif engine == "bing":
                tasks.append(self.search_bing(query, max_results_per_engine))
            elif engine == "yandex":
                tasks.append(self.search_yandex(query, max_results_per_engine))

        # Run all searches in parallel
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for results in results_list:
            if isinstance(results, Exception):
                logger.error(f"Search error: {results}")
                continue
            all_results.extend(results)

        return all_results


# Convenience function for CLI usage
async def main():
    """Test multi-backend search."""
    backend = MultiBackendSearch()

    query = '"Backward Spyglass"'
    print(f"Searching for: {query}")
    print("=" * 60)

    results = await backend.search_all(query, max_results_per_engine=20)

    print(f"\nTotal results: {len(results)}")
    for i, r in enumerate(results[:10], 1):
        bknd = r.get('backend', '?')
        title = r.get('title', '')[:50]
        url = r.get('url', '')[:60]
        print(f"{i}. [{bknd}] {title}")
        print(f"   {url}")


if __name__ == "__main__":
    asyncio.run(main())
