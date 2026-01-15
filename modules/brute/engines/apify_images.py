#!/usr/bin/env python3
"""
Apify Google Images Scraper Engine

Uses Apify's Google Images Scraper Actor for image search results.
Actor ID: tnudF2IxzORPhg4r8
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    logger.warning("apify_client not installed")

APIFY_TOKEN = os.getenv('APIFY_API_TOKEN') or os.getenv('APIFY_TOKEN')
IMAGES_ACTOR_ID = "tnudF2IxzORPhg4r8"  # Google Images Scraper


class ApifyImagesSearch:
    """Apify Google Images search client."""

    def __init__(self, api_token: str = None):
        self.api_token = api_token or APIFY_TOKEN
        self.client = ApifyClient(self.api_token) if APIFY_AVAILABLE and self.api_token else None

    def search(
        self,
        query: str,
        max_results: int = 100,
        country_code: str = None,
        language_code: str = None,
        safe_search: str = "off",
        image_type: str = None,
        image_size: str = None,
        image_color: str = None,
        time_filter: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Google Images via Apify Actor.

        Args:
            query: Search query
            max_results: Max results (up to 300 typical)
            country_code: Country code (US, GB, etc.)
            language_code: Language code (en, de, etc.)
            safe_search: Safe search level (off, moderate, strict)
            image_type: Type filter (face, photo, clipart, lineart, animated)
            image_size: Size filter (large, medium, icon)
            image_color: Color filter (color, gray, transparent)
            time_filter: Time filter (past24hours, pastWeek, pastMonth, pastYear)

        Returns:
            List of image results with url, title, source, dimensions
        """
        if not self.client:
            logger.error("Apify client not available")
            return []

        try:
            run_input = {
                "queries": [query],
                "maxResultsPerQuery": max_results,
                "countryCode": country_code,
                "languageCode": language_code,
                "safeSearch": safe_search,
            }
            
            # Add optional filters
            if image_type:
                run_input["imageType"] = image_type
            if image_size:
                run_input["imageSize"] = image_size
            if image_color:
                run_input["imageColor"] = image_color
            if time_filter:
                run_input["timeFilter"] = time_filter

            logger.info(f"Apify Images: Running actor for query: {query[:50]}...")
            
            run = self.client.actor(IMAGES_ACTOR_ID).call(run_input=run_input, timeout_secs=120)

            results = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                # Each item is an image result
                results.append({
                    "url": item.get("imageUrl", "") or item.get("url", ""),
                    "source_url": item.get("sourceUrl", "") or item.get("link", ""),
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "thumbnail": item.get("thumbnailUrl", ""),
                    "engine": "Apify Images",
                    "result_type": "image",
                })

            logger.info(f"Apify Images: Got {len(results)} image results")
            return results[:max_results]

        except Exception as e:
            logger.error(f"Apify Images error: {e}")
            return []


class ExactPhraseRecallRunnerApifyImages:
    """
    Apify Images runner with variations for max recall.
    """

    def __init__(self, api_token: str = None, phrase: str = None, keyword: str = None,
                 max_results: int = 100, event_emitter=None):
        self.phrase = phrase or keyword
        self.keyword = keyword or phrase
        self.max_results = max_results
        self.event_emitter = event_emitter
        self.client = ApifyImagesSearch(api_token)
        self.results = []

    def _get_base_queries(self) -> dict:
        """Image search variations."""
        quoted = f'"{self.phrase}"' if not self.phrase.startswith('"') else self.phrase
        return {
            "AI1_exact": quoted,
            "AI2_photo": quoted,   # image_type=photo
            "AI3_large": quoted,   # image_size=large
            "AI4_recent": quoted,  # time_filter=pastYear
        }

    def run(self) -> List[Dict[str, Any]]:
        """Run all query variations."""
        if not self.client.client:
            logger.warning("Apify client not configured")
            return []

        all_results = []
        seen_urls = set()

        variations = self._get_base_queries()
        per_variation = max(25, self.max_results // len(variations))

        for tag, query in variations.items():
            try:
                # Special parameters for variations
                image_type = None
                image_size = None
                time_filter = None

                if tag == "AI2_photo":
                    image_type = "photo"
                elif tag == "AI3_large":
                    image_size = "large"
                elif tag == "AI4_recent":
                    time_filter = "pastYear"

                results = self.client.search(
                    query=query,
                    max_results=per_variation,
                    image_type=image_type,
                    image_size=image_size,
                    time_filter=time_filter,
                )

                for r in results:
                    url = r.get("url", "") or r.get("source_url", "")
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
                logger.warning(f"Apify Images variation {tag} failed: {e}")
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


class ApifyImagesEngine:
    """Wrapper for brute.py compatibility."""
    code = 'AI'
    name = 'Apify Images'

    def __init__(self):
        self._runner_cls = ExactPhraseRecallRunnerApifyImages

    def is_available(self) -> bool:
        return APIFY_AVAILABLE and bool(APIFY_TOKEN)

    def search(self, query: str, max_results: int = 100, **kwargs) -> List[Dict]:
        runner = self._runner_cls(phrase=query, max_results=max_results)
        return runner.run()


__all__ = ['ApifyImagesSearch', 'ExactPhraseRecallRunnerApifyImages', 'ApifyImagesEngine', 'APIFY_AVAILABLE']
