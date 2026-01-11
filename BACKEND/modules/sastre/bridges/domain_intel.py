"""
Domain Intel HTTP Client - Calls Node API domain intelligence endpoints.

14 routers with 40+ endpoints:
- ccBacklinks: Common Crawl Web Graph
- whois: WHOIS + reverse WHOIS
- majestic: 16 Majestic API commands
- subdomains: Discovery via crt.sh, WhoisXML
- websiteIntel: Firecrawl + LLM analysis
- domainSignal: Cloudflare Radar, Tranco, CrUX
"""

import os
import logging
import aiohttp
from typing import Dict, Any

logger = logging.getLogger(__name__)

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")


class DomainIntelBridge:
    """
    HTTP client to domain intelligence endpoints.

    NOT a bridge to a module - this calls Node API endpoints.
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

    # =========================================================================
    # BACKLINKS (CC Web Graph + GlobalLinks)
    # =========================================================================

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        enriched: bool = True
    ) -> Dict[str, Any]:
        """
        Get backlinks from CC Web Graph + GlobalLinks.

        Args:
            domain: Target domain
            limit: Max results
            enriched: Include authority signals (Tranco, OPR, etc.)
        """
        try:
            session = await self._get_session()
            endpoint = "getEnrichedBacklinks" if enriched else "getInboundBacklinks"
            async with session.post(
                f"{self.base_url}/api/trpc/ccBacklinks.{endpoint}",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "backlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"backlinks": []}
        except Exception as e:
            logger.error(f"DomainIntel get_backlinks error: {e}")
            return {"error": str(e), "backlinks": []}

    async def get_outlinks(self, domain: str, limit: int = 100) -> Dict[str, Any]:
        """Get outbound links."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/ccBacklinks.getOutboundLinks",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "outlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"outlinks": []}
        except Exception as e:
            logger.error(f"DomainIntel get_outlinks error: {e}")
            return {"error": str(e), "outlinks": []}

    # =========================================================================
    # WHOIS
    # =========================================================================

    async def whois_lookup(self, domain: str) -> Dict[str, Any]:
        """WHOIS lookup with automatic graph persistence."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/enrichment/whois",
                json={"domain": domain},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"DomainIntel whois_lookup error: {e}")
            return {"error": str(e)}

    async def reverse_whois(
        self,
        query: str,
        query_type: str = "email"
    ) -> Dict[str, Any]:
        """
        Reverse WHOIS search.

        Args:
            query: Search value (email, name, phone, etc.)
            query_type: "domain", "email", "name", "phone", "company"
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/whois.reverseSearch",
                params={"batch": "1"},
                json={"0": {"json": {"query": query, "type": query_type}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "results": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"results": []}
        except Exception as e:
            logger.error(f"DomainIntel reverse_whois error: {e}")
            return {"error": str(e), "results": []}

    # =========================================================================
    # MAJESTIC
    # =========================================================================

    async def majestic_backlinks(
        self,
        domain: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get backlinks via Majestic API."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/majestic.getBackLinks",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "limit": limit}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "backlinks": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"backlinks": []}
        except Exception as e:
            logger.error(f"DomainIntel majestic_backlinks error: {e}")
            return {"error": str(e), "backlinks": []}

    # =========================================================================
    # SUBDOMAINS
    # =========================================================================

    async def discover_subdomains(self, domain: str) -> Dict[str, Any]:
        """Discover subdomains via crt.sh, WhoisXML, Sublist3r."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/subdomains.discover",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain}}},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text(), "subdomains": []}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {"subdomains": []}
        except Exception as e:
            logger.error(f"DomainIntel discover_subdomains error: {e}")
            return {"error": str(e), "subdomains": []}

    # =========================================================================
    # WEBSITE ANALYSIS
    # =========================================================================

    async def analyze_website(
        self,
        domain: str,
        max_pages: int = 10
    ) -> Dict[str, Any]:
        """Full website analysis with Firecrawl + LLM."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/trpc/websiteIntel.analyzeDomain",
                params={"batch": "1"},
                json={"0": {"json": {"domain": domain, "maxPages": max_pages}}},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                result = await resp.json()
                if isinstance(result, list) and result:
                    return result[0].get("result", {}).get("data", {})
                return {}
        except Exception as e:
            logger.error(f"DomainIntel analyze_website error: {e}")
            return {"error": str(e)}


__all__ = ['DomainIntelBridge']
