"""
LinkLater CC Web Graph Client

Query Common Crawl Web Graph (157M domains, 2.1B edges) via Elasticsearch.
"""

import os
import aiohttp
from typing import List, Optional
from .models import LinkRecord


# Python API URL (from env or default)
PYTHON_API_BASE = os.getenv('PYTHON_API_URL', 'http://localhost:8001')


class CCGraphClient:
    """Client for CC Web Graph (Elasticsearch)."""

    def __init__(self, api_base: Optional[str] = None):
        self.api_base = api_base or PYTHON_API_BASE

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        min_weight: int = 1,
        period: str = "latest",
        level: str = "domain"
    ) -> List[LinkRecord]:
        """
        Get backlinks (domains/hosts linking TO this target).

        Args:
            domain: Target domain/host
            limit: Max results
            min_weight: Minimum link weight
            period: Which CC crawl period
            level: "domain" or "host"

        Returns:
            List of LinkRecord objects
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/cc/inbound-backlinks",
                    json={
                        "targets": [domain],
                        "period": period,
                        "min_weight": min_weight,
                        "limit": limit,
                        "level": level,
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            LinkRecord(
                                source=r.get("src_domain", "") or r.get("source", ""),
                                target=r.get("target_domain", "") or r.get("target", ""),
                                weight=r.get("weight"),
                                provider="cc_graph"
                            )
                            for r in data.get("records", [])
                        ]
        except Exception as e:
            print(f"[CCGraph] Backlinks error: {e}")
        return []

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        min_weight: int = 1,
        period: str = "latest",
        level: str = "domain"
    ) -> List[LinkRecord]:
        """
        Get outlinks (domains/hosts this source links TO).

        Args:
            domain: Source domain/host
            limit: Max results
            min_weight: Minimum link weight
            period: Which CC crawl period
            level: "domain" or "host"

        Returns:
            List of LinkRecord objects
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/api/cc/outbound-outlinks",
                    json={
                        "sources": [domain],
                        "period": period,
                        "min_weight": min_weight,
                        "limit": limit,
                        "level": level,
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            LinkRecord(
                                source=r.get("src_domain", "") or r.get("source", ""),
                                target=r.get("target_domain", "") or r.get("target", ""),
                                weight=r.get("weight"),
                                provider="cc_graph"
                            )
                            for r in data.get("records", [])
                        ]
        except Exception as e:
            print(f"[CCGraph] Outlinks error: {e}")
        return []


# Convenience functions
async def get_backlinks_cc_graph(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get backlinks from CC Graph (standalone function)."""
    client = CCGraphClient()
    return await client.get_backlinks(domain, limit)


async def get_outlinks_cc_graph(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get outlinks from CC Graph (standalone function)."""
    client = CCGraphClient()
    return await client.get_outlinks(domain, limit)
