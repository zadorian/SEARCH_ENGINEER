"""
BRUTE Bridge - Interface for SASTRE and other modules

Bridge to BruteSearch multi-engine search.
40+ search engines in 8-wave progressive execution.
"""

import os
import logging
import aiohttp
from typing import Dict, Any

logger = logging.getLogger(__name__)

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")


class SearchBridge:
    """
    Bridge to BruteSearch multi-engine search.

    40+ search engines in 8-wave progressive execution:
    - Tier 0: Elastic Corpus, Sastre InURL
    - Tier 1: Google, Bing, Brave, Perplexity, Exa, Archive.org, etc.
    - Tier 2: DuckDuckGo, Yandex, NewsAPI, GDELT, Wikipedia, etc.
    - Tier 3: Semantic Scholar, PubMed, ArXiv, etc.

    Endpoints:
    - tRPC: search.search (streaming)
    - tRPC: drillSearch.advancedSearch
    """

    def __init__(self, base_url: str = NODE_API_BASE_URL):
        self.base_url = base_url
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def broad_search(
        self,
        query: str,
        limit: int = 100,
        include_filetype_discovery: bool = True
    ) -> Dict[str, Any]:
        """
        Run broad search across 40+ engines.

        Args:
            query: Search query
            limit: Max results
            include_filetype_discovery: Include filetype discovery pass

        Returns:
            {
                "results": [...],
                "metadata": {
                    "enginesUsed": [...],
                    "tier1Results": int,
                    "multiHitResults": int,
                    ...
                }
            }
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/search.search",
                params={"batch": "1"},
                json={
                    "0": {
                        "json": {
                            "query": query,
                            "limit": limit,
                            "includeFiletypeDiscovery": include_filetype_discovery
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"error": "Invalid response", "results": []}
        except Exception as e:
            logger.error(f"SearchBridge broad_search error: {e}")
            return {"error": str(e), "results": []}

    async def advanced_search(
        self,
        query: str,
        collapse_digest: bool = True
    ) -> Dict[str, Any]:
        """
        Advanced search with deduplication.

        Args:
            query: Search query
            collapse_digest: Collapse duplicate results by content digest
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/drillSearch.advancedSearch",
                params={"batch": "1"},
                json={
                    "0": {
                        "json": {
                            "query": query,
                            "collapseDigest": collapse_digest
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"error": "Invalid response", "results": []}
        except Exception as e:
            logger.error(f"SearchBridge advanced_search error: {e}")
            return {"error": str(e), "results": []}


__all__ = ['SearchBridge']
