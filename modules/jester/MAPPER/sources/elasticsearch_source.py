"""
JESTER MAPPER - Elasticsearch Discovery
=========================================

Discover URLs from our own Elasticsearch indexes.

Indexes:
    - crawled_pages: Pages we've already scraped
    - referring_domains: CC WebGraph data
    - domain_profiles: Company/domain profiles

Usage:
    discovery = ElasticsearchDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source)
"""

import asyncio
import aiohttp
import logging
from typing import AsyncGenerator, Set, List
from urllib.parse import urlparse

from ..models import DiscoveredURL
from ..config import ES_HOST, TIMEOUTS

logger = logging.getLogger(__name__)


class ElasticsearchDiscovery:
    """
    Elasticsearch-based URL discovery.

    Queries our own indexed data to find:
    1. Previously crawled pages
    2. Domain relationships from CC WebGraph
    3. Known URLs from domain profiles
    """

    def __init__(self, es_host: str = None):
        self.es_host = es_host or ES_HOST

    async def discover_all(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query all relevant ES indexes.

        Args:
            domain: Target domain

        Yields:
            DiscoveredURL objects
        """
        seen: Set[str] = set()

        # Query multiple indexes
        indexes = [
            ("crawled_pages", self._query_crawled_pages),
            ("io_urls", self._query_io_urls),
        ]

        for index_name, query_func in indexes:
            try:
                async for url in query_func(domain):
                    if url.url not in seen:
                        seen.add(url.url)
                        yield url
            except Exception as e:
                logger.debug(f"[elasticsearch:{index_name}] Error: {e}")

        logger.info(f"[elasticsearch] Found {len(seen)} URLs from local indexes")

    async def _query_crawled_pages(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query crawled_pages index for previously scraped URLs.

        Args:
            domain: Target domain

        Yields:
            DiscoveredURL objects
        """
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"domain.keyword": domain}},
                        {"wildcard": {"domain.keyword": f"*.{domain}"}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": 10000,
            "_source": ["url", "title", "scraped_at", "status_code"],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.es_host}/crawled_pages/_search",
                    json=query,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return

                    data = await response.json()
                    hits = data.get("hits", {}).get("hits", [])

                    for hit in hits:
                        source = hit.get("_source", {})
                        url_str = source.get("url")
                        if url_str:
                            yield DiscoveredURL(
                                url=url_str,
                                source="elasticsearch:crawled_pages",
                                domain=domain,
                                title=source.get("title"),
                                status_code=source.get("status_code"),
                            )

        except Exception as e:
            logger.debug(f"[elasticsearch:crawled_pages] Error: {e}")

    async def _query_io_urls(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query io index for URLs discovered by IO Matrix.

        Args:
            domain: Target domain

        Yields:
            DiscoveredURL objects
        """
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "url"}},
                    ],
                    "should": [
                        {"term": {"domain.keyword": domain}},
                        {"wildcard": {"url.keyword": f"*{domain}*"}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": 5000,
            "_source": ["url", "title", "source", "discovered_at"],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.es_host}/io/_search",
                    json=query,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return

                    data = await response.json()
                    hits = data.get("hits", {}).get("hits", [])

                    for hit in hits:
                        source = hit.get("_source", {})
                        url_str = source.get("url")
                        if url_str:
                            yield DiscoveredURL(
                                url=url_str,
                                source="elasticsearch:io",
                                domain=domain,
                                title=source.get("title"),
                            )

        except Exception as e:
            logger.debug(f"[elasticsearch:io] Error: {e}")

    async def query_index(
        self,
        index: str,
        domain: str,
        url_field: str = "url",
        max_results: int = 10000,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Generic index query for domain-related URLs.

        Args:
            index: ES index name
            domain: Target domain
            url_field: Field containing URLs
            max_results: Maximum results

        Yields:
            DiscoveredURL objects
        """
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"wildcard": {f"{url_field}.keyword": f"*{domain}*"}},
                        {"match": {"domain": domain}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": max_results,
            "_source": [url_field, "title", "description"],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.es_host}/{index}/_search",
                    json=query,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return

                    data = await response.json()
                    hits = data.get("hits", {}).get("hits", [])

                    for hit in hits:
                        source = hit.get("_source", {})
                        url_str = source.get(url_field)
                        if url_str:
                            yield DiscoveredURL(
                                url=url_str,
                                source=f"elasticsearch:{index}",
                                domain=domain,
                                title=source.get("title"),
                                description=source.get("description"),
                            )

        except Exception as e:
            logger.debug(f"[elasticsearch:{index}] Error: {e}")
