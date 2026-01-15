"""
LinkLater Host Graph Client - 421M Pre-Indexed Edges

Query the cc_web_graph_host_edges index for INSTANT host-level backlinks.
This is the "GlobalLinks" data - pre-indexed, no WAT file downloads needed.

Index: cc_web_graph_host_edges (421M edges)
Format: Reversed domain notation (e.g., com.bbc.www for www.bbc.com)
"""

import asyncio
from typing import List, Optional, Dict
from elasticsearch import AsyncElasticsearch
from .models import LinkRecord


def reverse_domain(domain: str) -> str:
    """
    Convert domain to reversed notation for ES queries.

    Examples:
        bbc.com -> com.bbc
        www.bbc.com -> com.bbc.www
        api.example.co.uk -> uk.co.example.api
    """
    parts = domain.lower().strip().split('.')
    return '.'.join(reversed(parts))


def unreverse_domain(reversed_domain: str) -> str:
    """
    Convert reversed domain back to normal notation.

    Examples:
        com.bbc -> bbc.com
        com.bbc.www -> www.bbc.com
        uk.co.example.api -> api.example.co.uk
    """
    parts = reversed_domain.split('.')
    return '.'.join(reversed(parts))


class HostGraphESClient:
    """
    Client for CC Web Graph Host Edges (421M pre-indexed edges).

    This queries the cc_web_graph_host_edges index which stores
    host-level (subdomain) link relationships in reversed domain format.

    INSTANT queries (~50ms) - no WAT file downloads needed!
    """

    def __init__(self, es_host: str = "http://localhost:9200"):
        """Initialize ES client."""
        self.es = AsyncElasticsearch([es_host])
        self.index = "cc_web_graph_host_edges"

    async def close(self):
        """Close ES connection."""
        await self.es.close()

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True
    ) -> List[LinkRecord]:
        """
        Get backlinks (hosts linking TO this domain) from Elasticsearch.

        INSTANT query against 421M pre-indexed edges.

        Args:
            domain: Target domain (e.g., "bbc.com")
            limit: Max results (default 100)
            include_subdomains: If True, includes links to *.domain (e.g., www.bbc.com)

        Returns:
            List of LinkRecord objects with source/target hosts
        """
        try:
            reversed_domain = reverse_domain(domain)

            # Build query - either exact match or prefix for subdomains
            if include_subdomains:
                query = {
                    "bool": {
                        "should": [
                            {"term": {"target": reversed_domain}},
                            {"prefix": {"target": f"{reversed_domain}."}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            else:
                query = {"term": {"target": reversed_domain}}

            response = await self.es.search(
                index=self.index,
                body={
                    "query": query,
                    "size": limit,
                    "_source": ["source", "target", "source_id", "target_id", "collection"]
                }
            )

            records = []
            for hit in response['hits']['hits']:
                src = hit['_source']
                records.append(LinkRecord(
                    source=unreverse_domain(src['source']),
                    target=unreverse_domain(src['target']),
                    provider="host_graph_es",
                    metadata={
                        "source_id": src.get('source_id'),
                        "target_id": src.get('target_id'),
                        "collection": src.get('collection')
                    }
                ))

            return records

        except Exception as e:
            print(f"[HostGraphES] Backlinks error: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True
    ) -> List[LinkRecord]:
        """
        Get outlinks (hosts this domain links TO) from Elasticsearch.

        INSTANT query against 421M pre-indexed edges.

        Args:
            domain: Source domain (e.g., "bbc.com")
            limit: Max results
            include_subdomains: If True, includes links from *.domain

        Returns:
            List of LinkRecord objects
        """
        try:
            reversed_domain = reverse_domain(domain)

            if include_subdomains:
                query = {
                    "bool": {
                        "should": [
                            {"term": {"source": reversed_domain}},
                            {"prefix": {"source": f"{reversed_domain}."}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            else:
                query = {"term": {"source": reversed_domain}}

            response = await self.es.search(
                index=self.index,
                body={
                    "query": query,
                    "size": limit,
                    "_source": ["source", "target", "source_id", "target_id", "collection"]
                }
            )

            records = []
            for hit in response['hits']['hits']:
                src = hit['_source']
                records.append(LinkRecord(
                    source=unreverse_domain(src['source']),
                    target=unreverse_domain(src['target']),
                    provider="host_graph_es",
                    metadata={
                        "source_id": src.get('source_id'),
                        "target_id": src.get('target_id'),
                        "collection": src.get('collection')
                    }
                ))

            return records

        except Exception as e:
            print(f"[HostGraphES] Outlinks error: {e}")
            return []

    async def count_backlinks(self, domain: str, include_subdomains: bool = True) -> int:
        """Count total backlinks to a domain."""
        try:
            reversed_domain = reverse_domain(domain)

            if include_subdomains:
                query = {
                    "bool": {
                        "should": [
                            {"term": {"target": reversed_domain}},
                            {"prefix": {"target": f"{reversed_domain}."}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            else:
                query = {"term": {"target": reversed_domain}}

            response = await self.es.count(
                index=self.index,
                body={"query": query}
            )
            return response['count']

        except Exception as e:
            print(f"[HostGraphES] Count error: {e}")
            return 0

    async def get_stats(self) -> dict:
        """Get index statistics."""
        try:
            count = await self.es.count(index=self.index)
            return {
                'total_edges': count['count'],
                'index': self.index
            }
        except Exception as e:
            print(f"[HostGraphES] Stats error: {e}")
            return {}


# Convenience functions for standalone use
async def get_backlinks_host_graph(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get backlinks from Host Graph ES (421M edges, instant)."""
    client = HostGraphESClient()
    try:
        return await client.get_backlinks(domain, limit)
    finally:
        await client.close()


async def get_outlinks_host_graph(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get outlinks from Host Graph ES (421M edges, instant)."""
    client = HostGraphESClient()
    try:
        return await client.get_outlinks(domain, limit)
    finally:
        await client.close()


# CLI test
if __name__ == "__main__":
    import sys

    async def main():
        domain = sys.argv[1] if len(sys.argv) > 1 else "bbc.com"

        client = HostGraphESClient()
        try:
            # Get stats
            stats = await client.get_stats()
            print(f"Index stats: {stats}")

            # Count backlinks
            count = await client.count_backlinks(domain)
            print(f"\nTotal backlinks to {domain}: {count}")

            # Get sample backlinks
            print(f"\nSample backlinks to {domain}:")
            records = await client.get_backlinks(domain, limit=10)
            for r in records:
                print(f"  {r.source} -> {r.target}")

        finally:
            await client.close()

    asyncio.run(main())
