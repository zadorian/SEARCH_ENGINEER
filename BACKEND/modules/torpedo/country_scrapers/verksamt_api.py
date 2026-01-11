#!/usr/bin/env python3
"""
Sweden Verksamt search (GET-friendly) lightweight integration.
Note: The official Bolagsverket search frontends tend to be form-based.
This module uses verksamt.se/sok which preserves ?query={QUERY}. Results parsing is heuristic.
"""

import aiohttp
import asyncio
import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class SwedenVerksamtAPI:
    def __init__(self):
        self.base = "https://www.verksamt.se/sok"

    async def search_company(self, session: aiohttp.ClientSession, company_name: str) -> List[Dict]:
        params = {"query": company_name}
        try:
            async with session.get(self.base, params=params, timeout=30) as resp:
                html = await resp.text()
        except Exception as e:
            logger.error(f"Sweden Verksamt request error: {e}")
            return []

        # Heuristic: capture result cards with anchors
        results: List[Dict] = []
        for m in re.finditer(r'<a[^>]+href=\"([^\"]+)\"[^>]*>([^<]{3,})</a>', html, re.IGNORECASE):
            href = m.group(1)
            label = re.sub(r"\s+", " ", m.group(2)).strip()
            if not label or not href:
                continue
            # Skip site chrome
            if any(x in href for x in ["/om-verksamt", "/kontakt", "/minasidor", "/sidor/"]):
                continue
            results.append({
                "name": label,
                "jurisdiction": "SE",
                "url": href if href.startswith("http") else ("https://www.verksamt.se" + href),
                "api_source": "sweden_verksamt"
            })

        # Dedup
        seen=set(); ded=[]
        for r in results:
            key=(r.get("name"), r.get("url"))
            if key in seen: continue
            seen.add(key); ded.append(r)
        return ded[:20]


if __name__ == "__main__":
    async def _test():
        async with aiohttp.ClientSession() as s:
            api = SwedenVerksamtAPI()
            print(await api.search_company(s, "IKEA"))
    asyncio.run(_test())


