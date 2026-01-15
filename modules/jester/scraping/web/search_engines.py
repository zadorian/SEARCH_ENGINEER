#!/usr/bin/env python3
"""
LinkLater Search Engine Discovery - Multi-source with graceful fallbacks

✅ MOVED FROM ALLDOM TO LINKLATER (architecture cleanup)

Supports: Google, Bing, Brave

URL Discovery via Search Engines:
- Google Custom Search API (with scraping fallback)
- Brave Search API
- Bing Search API
"""

import asyncio
import aiohttp
import logging
import os
import sys
from pathlib import Path
from contextlib import suppress
from typing import AsyncGenerator
from datetime import datetime
from dataclasses import dataclass
from bs4 import BeautifulSoup

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)


# Load API keys from environment
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")


@dataclass
class DiscoveredURL:
    """A URL discovered from a source."""
    url: str
    clean_url: str
    source: str
    discovered_at: float
    category: str = "search_engine"


class SearchEngineDiscovery:
    """
    Multi-source search engine discovery with graceful degradation

    Strategy:
    1. Try API endpoints first (fastest, most reliable)
    2. Fall back to web scraping if no API key
    3. Handle rate limits and errors gracefully
    """

    def __init__(self):
        self.brave_key = BRAVE_API_KEY
        self.google_key = GOOGLE_API_KEY
        self.google_cse_id = GOOGLE_CSE_ID

        # User agents for scraping fallback
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        ]

    async def search_all(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Run all search engines in parallel and stream results as they arrive.

        Uses: Google, Brave, Bing

        Args:
            domain: Domain to search

        Yields:
            DiscoveredURL objects from all sources
        """
        generators = [
            self.search_google(domain),
            self.search_brave(domain),
            self.search_bing(domain)
        ]

        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(gen):
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                logger.error(f"Search engine generator raised error: {exc}", exc_info=True)
            finally:
                await queue.put(sentinel)

        tasks = [asyncio.create_task(consume(gen)) for gen in generators]

        completed = 0
        try:
            while completed < len(tasks):
                item = await queue.get()
                if item is sentinel:
                    completed += 1
                    continue
                if item is not None:
                    yield item
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task

    async def search_google(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Google site: search

        Uses Google Custom Search API if key available, otherwise scrapes
        """
        if self.google_key and self.google_cse_id:
            async for url in self._google_api_search(domain):
                yield url
        else:
            async for url in self._google_scrape_search(domain):
                yield url

    async def _google_api_search(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Google Custom Search API"""
        logger.info(f"Google API search for: {domain}")

        url = "https://www.googleapis.com/customsearch/v1"

        try:
            async with aiohttp.ClientSession() as session:
                # Google limits to 100 results per query (10 per page, 10 pages max)
                for start_index in range(1, 100, 10):
                    params = {
                        'key': self.google_key,
                        'cx': self.google_cse_id,
                        'q': f'site:{domain} inurl:{domain}',
                        'start': start_index,
                        'num': 10
                    }

                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            data = await response.json()

                            items = data.get('items', [])
                            if not items:
                                break  # No more results

                            for item in items:
                                result_url = item.get('link')
                                if result_url:
                                    yield DiscoveredURL(
                                        url=result_url,
                                        clean_url=result_url,
                                        source="google_api",
                                        discovered_at=datetime.now().timestamp()
                                    )

                            # Check if more results available
                            if 'nextPage' not in data.get('queries', {}):
                                break

                            # Rate limit: 100 queries per 100 seconds
                            await asyncio.sleep(1.0)

                        elif response.status == 429:
                            logger.warning("Google API rate limit exceeded")
                            break
                        else:
                            logger.error(f"Google API error: {response.status}")
                            break

        except Exception as e:
            logger.error(f"Google API search exception: {e}", exc_info=True)

    async def _google_scrape_search(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Google web scraping fallback"""
        logger.info(f"Google scraping fallback for: {domain}")

        try:
            async with aiohttp.ClientSession() as session:
                for page in range(0, 100, 10):
                    url = "https://www.google.com/search"
                    params = {
                        'q': f'site:{domain} inurl:{domain}',
                        'start': page,
                        'num': 10
                    }
                    headers = {
                        'User-Agent': self.user_agents[0]
                    }

                    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Extract result URLs
                            for link in soup.select('a[href^="/url?q="]'):
                                href = link.get('href')
                                if href:
                                    # Extract actual URL from Google redirect
                                    actual_url = href.split('/url?q=')[1].split('&')[0]
                                    if domain in actual_url:
                                        yield DiscoveredURL(
                                            url=actual_url,
                                            clean_url=actual_url,
                                            source="google_scrape",
                                            discovered_at=datetime.now().timestamp()
                                        )

                            # Be polite with scraping
                            await asyncio.sleep(2.0)

                        else:
                            logger.warning(f"Google scraping blocked: {response.status}")
                            break

        except Exception as e:
            logger.error(f"Google scraping exception: {e}", exc_info=True)

    async def search_brave(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Brave Search API"""
        if not self.brave_key:
            logger.info("Skipping Brave - no API key")
            return

        logger.info(f"Brave API search for: {domain}")

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            'Accept': 'application/json',
            'X-Subscription-Token': self.brave_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Brave allows pagination with offset 0-9 only (10 pages max)
                for offset in range(0, 10):
                    params = {
                        'q': f'site:{domain} inurl:{domain}',
                        'count': 20,
                        'offset': offset
                    }

                    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            data = await response.json()

                            results = data.get('web', {}).get('results', [])
                            if not results:
                                break

                            for result in results:
                                result_url = result.get('url')
                                if result_url:
                                    yield DiscoveredURL(
                                        url=result_url,
                                        clean_url=result_url,
                                        source="brave_api",
                                        discovered_at=datetime.now().timestamp()
                                    )

                            # Rate limiting
                            await asyncio.sleep(1.0)

                        elif response.status == 429:
                            logger.warning("Brave API rate limit exceeded")
                            break
                        else:
                            logger.error(f"Brave API error: {response.status}")
                            break

        except Exception as e:
            logger.error(f"Brave search exception: {e}", exc_info=True)

    async def search_bing(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Bing web scraping (no API key required)"""
        logger.info(f"Bing scraping for: {domain}")

        try:
            async with aiohttp.ClientSession() as session:
                for page in range(1, 11):  # First 10 pages
                    url = "https://www.bing.com/search"
                    params = {
                        'q': f'site:{domain} inurl:{domain}',
                        'first': (page - 1) * 10 + 1
                    }
                    headers = {
                        'User-Agent': self.user_agents[1]
                    }

                    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Extract result URLs
                            for link in soup.select('li.b_algo h2 a'):
                                href = link.get('href')
                                if href and domain in href:
                                    yield DiscoveredURL(
                                        url=href,
                                        clean_url=href,
                                        source="bing_scrape",
                                        discovered_at=datetime.now().timestamp()
                                    )

                            await asyncio.sleep(2.0)

                        else:
                            logger.warning(f"Bing scraping blocked: {response.status}")
                            break

        except Exception as e:
            logger.error(f"Bing scraping exception: {e}", exc_info=True)

    async def search_duckduckgo(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """DuckDuckGo HTML scraping"""
        logger.info(f"DuckDuckGo scraping for: {domain}")

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://html.duckduckgo.com/html/"
                data = {
                    'q': f'site:{domain} inurl:{domain}'
                }
                headers = {
                    'User-Agent': self.user_agents[0]
                }

                async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Extract result URLs
                        for link in soup.select('a.result__url'):
                            href = link.get('href')
                            if href and domain in href:
                                # DDG uses redirect URLs
                                if '/l/?uddg=' in href:
                                    actual_url = href.split('/l/?uddg=')[1].split('&')[0]
                                else:
                                    actual_url = href

                                yield DiscoveredURL(
                                    url=actual_url,
                                    clean_url=actual_url,
                                    source="duckduckgo_scrape",
                                    discovered_at=datetime.now().timestamp()
                                )

        except Exception as e:
            logger.error(f"DuckDuckGo scraping exception: {e}", exc_info=True)

    async def search_yandex(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Yandex web scraping"""
        logger.info(f"Yandex scraping for: {domain}")

        try:
            async with aiohttp.ClientSession() as session:
                for page in range(0, 5):  # First 5 pages
                    url = "https://yandex.com/search/"
                    params = {
                        'text': f'host:{domain} inurl:{domain}',
                        'p': page
                    }
                    headers = {
                        'User-Agent': self.user_agents[0]
                    }

                    async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Extract result URLs
                            for link in soup.select('a.OrganicTitle-Link'):
                                href = link.get('href')
                                if href and domain in href:
                                    yield DiscoveredURL(
                                        url=href,
                                        clean_url=href,
                                        source="yandex_scrape",
                                        discovered_at=datetime.now().timestamp()
                                    )

                            await asyncio.sleep(2.0)

                        else:
                            logger.warning(f"Yandex scraping blocked: {response.status}")
                            break

        except Exception as e:
            logger.error(f"Yandex scraping exception: {e}", exc_info=True)

    async def search_exa(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """Exa API search"""
        if not self.exa_key:
            logger.info("Skipping Exa - no API key")
            return

        logger.info(f"Exa API search for: {domain}")

        url = "https://api.exa.ai/search"
        headers = {
            'x-api-key': self.exa_key,
            'Content-Type': 'application/json'
        }

        payload = {
            'query': f'site:{domain} inurl:{domain}',
            'num_results': 100,
            'type': 'neural'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()

                        for result in data.get('results', []):
                            result_url = result.get('url')
                            if result_url:
                                yield DiscoveredURL(
                                    url=result_url,
                                    clean_url=result_url,
                                    source="exa_api",
                                    discovered_at=datetime.now().timestamp()
                                )

                    else:
                        logger.error(f"Exa API error: {response.status}")

        except Exception as e:
            logger.error(f"Exa search exception: {e}", exc_info=True)
