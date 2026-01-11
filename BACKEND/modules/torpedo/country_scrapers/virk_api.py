#!/usr/bin/env python3
"""
Denmark CVR/Virk integration (lightweight)

Primary: UI GET endpoint (datacvr.virk.dk) for quick name lookup.
Note: The page is a dynamic SPA; this module does a best-effort HTML parse.
For production-grade scraping, prefer a headless driver (or Firecrawl) if needed.
"""

import aiohttp
import asyncio
import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class DenmarkVirkAPI:
    """Denmark business registry lightweight client."""

    def __init__(self):
        self.search_url = "https://datacvr.virk.dk/data/"

    async def search_company(self, session: aiohttp.ClientSession, company_name: str) -> List[Dict]:
        """Perform a lightweight search on datacvr.virk.dk using the GET-friendly query param.
        Returns a basic list of matches (name, url) when detectable.
        """
        params = {"search": company_name}
        try:
            async with session.get(self.search_url, params=params, timeout=30) as resp:
                text = await resp.text()
        except Exception as e:
            logger.error(f"Denmark VIRK request error: {e}")
            return []

        # Very simple extraction: anchor tags that likely represent entities
        # This is heuristic and may need upgrading to a headless approach
        results: List[Dict] = []
        for m in re.finditer(r'<a\s+href=\"([^\"]+)\"[^>]*>([^<]{3,})</a>', text, re.IGNORECASE):
            href = m.group(1)
            label = re.sub(r"\s+", " ", m.group(2)).strip()
            if not label or not href:
                continue
            # Filter obvious nav links
            if any(x in href for x in ["/help", "/om", "/kontakt", "/privacy", "/cookie"]):
                continue
            results.append({
                "name": label,
                "jurisdiction": "DK",
                "url": href if href.startswith("http") else ("https://datacvr.virk.dk" + href),
                "api_source": "denmark_virk"
            })

        # De-dup by name+url
        seen = set()
        dedup: List[Dict] = []
        for r in results:
            key = (r.get("name"), r.get("url"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        return dedup[:20]


if __name__ == "__main__":
    async def _test():
        async with aiohttp.ClientSession() as s:
            api = DenmarkVirkAPI()
            res = await api.search_company(s, "Novo Nordisk")
            print(res[:5])
    asyncio.run(_test())


