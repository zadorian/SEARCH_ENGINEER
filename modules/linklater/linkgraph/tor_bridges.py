"""
LinkLater Tor Bridges Client

Query Tor bridge edges (onion → clearnet links) from Elasticsearch.
Bridges reveal clearnet infrastructure connected to hidden services.
"""

import os
import aiohttp
from typing import List, Optional, Dict, Any
from .models import LinkRecord


# Elasticsearch URL from env or default
ES_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
ES_USER = os.getenv('ES_USERNAME', None)
ES_PASS = os.getenv('ES_PASSWORD', None)


class TorBridgesClient:
    """
    Client for Tor bridge edges stored in Elasticsearch.

    Bridges connect .onion pages to clearnet URLs, revealing:
    - Clearnet infrastructure operated by hidden services
    - Payment processors, hosting providers, contact info
    - Cross-reference targets for clearnet investigations

    Index: tor-bridges (created by TorCrawler when extract_bridges=True)
    """

    DEFAULT_INDEX = "tor-bridges"

    def __init__(
        self,
        es_url: Optional[str] = None,
        index_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.es_url = (es_url or ES_URL).rstrip("/")
        self.index_name = index_name or self.DEFAULT_INDEX
        self.auth = aiohttp.BasicAuth(
            username or ES_USER or "",
            password or ES_PASS or ""
        ) if (username or ES_USER) else None

    async def get_bridges_by_onion(
        self,
        onion_domain: str,
        limit: int = 100,
    ) -> List[LinkRecord]:
        """
        Get clearnet bridges for a specific .onion domain.

        Args:
            onion_domain: The .onion domain (with or without .onion suffix)
            limit: Max results

        Returns:
            List of LinkRecord objects (source = onion, target = clearnet)
        """
        if not onion_domain.endswith('.onion'):
            onion_domain = f"{onion_domain}.onion"

        query = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"source_domain": onion_domain}},
                        {"wildcard": {"source_domain": f"*{onion_domain}"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [{"discovered_at": {"order": "desc"}}]
        }

        return await self._search(query)

    async def get_bridges_to_clearnet(
        self,
        clearnet_domain: str,
        limit: int = 100,
    ) -> List[LinkRecord]:
        """
        Find .onion domains linking to a specific clearnet domain.

        This is the reverse lookup - "who in the dark web links to this clearnet site?"

        Args:
            clearnet_domain: The clearnet domain
            limit: Max results

        Returns:
            List of LinkRecord objects (source = onion, target = clearnet)
        """
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"target_domain": clearnet_domain}},
                        {"wildcard": {"target_domain": f"*{clearnet_domain}"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "size": limit,
            "sort": [{"discovered_at": {"order": "desc"}}]
        }

        return await self._search(query)

    async def get_recent_bridges(
        self,
        limit: int = 100,
        days: int = 7,
    ) -> List[LinkRecord]:
        """
        Get recently discovered bridges.

        Args:
            limit: Max results
            days: How many days back to look

        Returns:
            List of LinkRecord objects
        """
        query = {
            "query": {
                "range": {
                    "discovered_at": {
                        "gte": f"now-{days}d/d"
                    }
                }
            },
            "size": limit,
            "sort": [{"discovered_at": {"order": "desc"}}]
        }

        return await self._search(query)

    async def search_by_anchor_text(
        self,
        text: str,
        limit: int = 100,
    ) -> List[LinkRecord]:
        """
        Search bridges by anchor text.

        Args:
            text: Text to search for in anchor text
            limit: Max results

        Returns:
            List of LinkRecord objects
        """
        query = {
            "query": {
                "match": {
                    "anchor_text": text
                }
            },
            "size": limit,
            "sort": [{"_score": {"order": "desc"}}]
        }

        return await self._search(query)

    async def get_unique_clearnet_domains(
        self,
        onion_domain: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get unique clearnet domains found in bridges.

        Args:
            onion_domain: Optionally filter to a specific .onion domain
            limit: Max unique domains to return

        Returns:
            List of {domain, count} dicts
        """
        query: Dict[str, Any] = {"match_all": {}}
        if onion_domain:
            if not onion_domain.endswith('.onion'):
                onion_domain = f"{onion_domain}.onion"
            query = {"term": {"source_domain": onion_domain}}

        agg_query = {
            "query": query,
            "size": 0,
            "aggs": {
                "unique_targets": {
                    "terms": {
                        "field": "target_domain",
                        "size": limit
                    }
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.es_url}/{self.index_name}/_search",
                    json=agg_query,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        buckets = data.get("aggregations", {}).get("unique_targets", {}).get("buckets", [])
                        return [
                            {"domain": b["key"], "count": b["doc_count"]}
                            for b in buckets
                        ]
        except Exception as e:
            print(f"[TorBridges] Aggregation error: {e}")
        return []

    async def get_bridge_stats(self) -> Dict[str, Any]:
        """
        Get statistics about indexed bridges.

        Returns:
            Dict with total bridges, unique onions, unique clearnet domains
        """
        agg_query = {
            "size": 0,
            "aggs": {
                "unique_onions": {
                    "cardinality": {"field": "source_domain"}
                },
                "unique_clearnet": {
                    "cardinality": {"field": "target_domain"}
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Get count
                count_resp = await session.get(
                    f"{self.es_url}/{self.index_name}/_count",
                    auth=self.auth
                )
                count = 0
                if count_resp.status == 200:
                    count = (await count_resp.json()).get("count", 0)

                # Get aggregations
                async with session.post(
                    f"{self.es_url}/{self.index_name}/_search",
                    json=agg_query,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        aggs = data.get("aggregations", {})
                        return {
                            "total_bridges": count,
                            "unique_onion_domains": aggs.get("unique_onions", {}).get("value", 0),
                            "unique_clearnet_domains": aggs.get("unique_clearnet", {}).get("value", 0),
                        }
        except Exception as e:
            print(f"[TorBridges] Stats error: {e}")
        return {"total_bridges": 0, "unique_onion_domains": 0, "unique_clearnet_domains": 0}

    async def _search(self, query: Dict[str, Any]) -> List[LinkRecord]:
        """Execute search and convert to LinkRecord objects."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.es_url}/{self.index_name}/_search",
                    json=query,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        records = []
                        for hit in data.get("hits", {}).get("hits", []):
                            src = hit.get("_source", {})
                            records.append(LinkRecord(
                                source=src.get("source_url", ""),
                                target=src.get("target_url", ""),
                                anchor_text=src.get("anchor_text"),
                                provider="tor_bridge",
                                first_seen=src.get("discovered_at"),
                            ))
                        return records
                    else:
                        print(f"[TorBridges] Search error: {resp.status}")
        except Exception as e:
            print(f"[TorBridges] Search error: {e}")
        return []


# Convenience functions

async def get_bridges_for_onion(onion_domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get clearnet bridges for a .onion domain."""
    client = TorBridgesClient()
    return await client.get_bridges_by_onion(onion_domain, limit)


async def get_onions_linking_to(clearnet_domain: str, limit: int = 100) -> List[LinkRecord]:
    """Find .onion domains linking to a clearnet domain."""
    client = TorBridgesClient()
    return await client.get_bridges_to_clearnet(clearnet_domain, limit)


async def get_bridge_statistics() -> Dict[str, Any]:
    """Get bridge index statistics."""
    client = TorBridgesClient()
    return await client.get_bridge_stats()
