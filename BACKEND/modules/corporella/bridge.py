"""
CORPORELLA Bridge - Interface for SASTRE and other modules

Bridge to Corporella company intelligence.
Provides:
- Officers (directors, CEOs)
- Shareholders
- Beneficial owners
- Company status
- Filing history

Sources: OpenCorporates, OCCRP Aleph, jurisdiction-specific registries
"""

import os
import logging
import aiohttp
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NODE_API_BASE_URL = os.getenv("NODE_API_BASE_URL", "http://localhost:3000")


class CorporellaBridge:
    """
    Bridge to Corporella company intelligence.

    Endpoints:
    - POST /api/company-enrichment/enrich
    - POST /api/company-search/execute
    - POST /api/company-registries/search
    - tRPC: corporella.*
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

    async def enrich_company(
        self,
        company_name: str,
        jurisdiction: str = None,
        company_number: str = None,
        node_id: str = None
    ) -> Dict[str, Any]:
        """
        Enrich company with officers, shareholders, etc.

        Calls populator.py subprocess for full enrichment.
        """
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/enrichment/enrich",
                json={
                    "companyName": company_name,
                    "jurisdiction": jurisdiction,
                    "companyNumber": company_number,
                    "nodeId": node_id
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Corporella enrich_company error: {e}")
            return {"error": str(e)}

    async def search_company(
        self,
        query: str,
        jurisdiction: str = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Search for companies and auto-create graph nodes."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/search/execute",
                json={
                    "query": query,
                    "jurisdiction": jurisdiction,
                    "limit": limit
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Corporella search_company error: {e}")
            return {"error": str(e)}

    async def search_registry(
        self,
        query: str,
        jurisdiction: str,
        include_officers: bool = True
    ) -> Dict[str, Any]:
        """Search country-specific registry with officer data."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/corporella/country/search",
                json={
                    "query": query,
                    "jurisdiction": jurisdiction,
                    "entryTypes": ["company", "officer"] if include_officers else ["company"],
                    "includeOfficers": include_officers
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status >= 400:
                    return {"error": await resp.text()}
                return await resp.json()
        except Exception as e:
            logger.error(f"Corporella search_registry error: {e}")
            return {"error": str(e)}

    async def get_officers(self, company_name: str, jurisdiction: str = None) -> List[Dict]:
        """Get company officers."""
        result = await self.enrich_company(company_name, jurisdiction)
        return result.get("officers", [])

    async def get_shareholders(self, company_name: str, jurisdiction: str = None) -> List[Dict]:
        """Get company shareholders."""
        result = await self.enrich_company(company_name, jurisdiction)
        return result.get("shareholders", [])


__all__ = ['CorporellaBridge']
