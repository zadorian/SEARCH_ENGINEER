"""
LinkLater CC Web Graph Client - ELASTICSEARCH VERSION

Query CC Web Graph from Elasticsearch indices (INSTANT queries).
Supports two index formats:
1. cc_web_graph_host_edges (421M docs) - SURT format (source/target)
2. cymonides_cc_domain_edges/vertices - vertex ID format
"""

import asyncio
from typing import List, Optional, Dict
from elasticsearch import AsyncElasticsearch
from .models import LinkRecord


def domain_to_surt(domain: str) -> str:
    """Convert domain to SURT format (com.example)."""
    parts = domain.lower().split('.')
    return '.'.join(reversed(parts))


def surt_to_domain(surt: str) -> str:
    """Convert SURT format back to domain (example.com)."""
    parts = surt.split('.')
    return '.'.join(reversed(parts))


class CCGraphESClient:
    """Client for CC Web Graph using Elasticsearch (FAST)."""

    def __init__(self, es_host: str = "http://localhost:9200"):
        """Initialize ES client."""
        self.es = AsyncElasticsearch([es_host], request_timeout=30)
        # Primary index (SURT format, 421M docs)
        self.surt_edges_index = "cc_web_graph_host_edges"
        # Fallback indices (vertex ID format)
        self.edges_index = "cymonides_cc_domain_edges"
        self.vertices_index = "cymonides_cc_domain_vertices"

    async def close(self):
        """Close ES connection."""
        await self.es.close()

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        min_weight: int = 1
    ) -> List[LinkRecord]:
        """
        Get backlinks (domains linking TO this domain) from Elasticsearch.

        Args:
            domain: Target domain
            limit: Max results
            min_weight: Minimum link weight (only for vertex-based index)

        Returns:
            List of LinkRecord objects
        """
        # Try SURT-based index first (more complete data)
        records = await self._get_backlinks_surt(domain, limit)
        if records:
            return records

        # Fall back to vertex-based index
        return await self._get_backlinks_vertex(domain, limit, min_weight)

    async def _get_backlinks_surt(self, domain: str, limit: int) -> List[LinkRecord]:
        """Get backlinks from SURT-format index (cc_web_graph_host_edges)."""
        try:
            target_surt = domain_to_surt(domain)

            response = await self.es.search(
                index=self.surt_edges_index,
                body={
                    "query": {"term": {"target": target_surt}},
                    "size": limit,
                    "_source": ["source", "target"]
                }
            )

            records = []
            for hit in response['hits']['hits']:
                src = hit['_source']
                source_domain = surt_to_domain(src.get('source', ''))
                records.append(LinkRecord(
                    source=source_domain,
                    target=domain,
                    weight=1,
                    provider="cc_web_graph"
                ))

            return records

        except Exception as e:
            # Index might not exist, fall through to vertex-based
            return []

    async def _get_backlinks_vertex(
        self, domain: str, limit: int, min_weight: int
    ) -> List[LinkRecord]:
        """Get backlinks from vertex-based index."""
        try:
            # Get vertex ID for target domain
            target_id = await self._domain_to_vertex_id(domain)
            if not target_id:
                return []

            query = {
                "query": {"term": {"target_vertex_id": target_id}},
                "size": limit,
                "_source": ["source_vertex_id", "link_count"]
            }

            if min_weight > 1:
                query["query"] = {
                    "bool": {
                        "must": [
                            {"term": {"target_vertex_id": target_id}},
                            {"range": {"link_count": {"gte": min_weight}}}
                        ]
                    }
                }

            response = await self.es.search(index=self.edges_index, body=query)

            source_ids = [hit['_source']['source_vertex_id'] for hit in response['hits']['hits']]
            if not source_ids:
                return []

            id_to_domain = await self._vertex_ids_to_domains(source_ids)

            records = []
            for hit in response['hits']['hits']:
                src_id = hit['_source']['source_vertex_id']
                src_domain = id_to_domain.get(src_id)
                if src_domain:
                    records.append(LinkRecord(
                        source=src_domain,
                        target=domain,
                        weight=hit['_source'].get('link_count', 1),
                        provider="cc_graph_es"
                    ))

            return records

        except Exception as e:
            print(f"[CCGraphES] Vertex backlinks error: {e}")
            return []

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        min_weight: int = 1
    ) -> List[LinkRecord]:
        """
        Get outlinks (domains this domain links TO) from Elasticsearch.

        Args:
            domain: Source domain
            limit: Max results
            min_weight: Minimum link weight

        Returns:
            List of LinkRecord objects
        """
        # Try SURT-based index first
        records = await self._get_outlinks_surt(domain, limit)
        if records:
            return records

        # Fall back to vertex-based index
        return await self._get_outlinks_vertex(domain, limit, min_weight)

    async def _get_outlinks_surt(self, domain: str, limit: int) -> List[LinkRecord]:
        """Get outlinks from SURT-format index."""
        try:
            source_surt = domain_to_surt(domain)

            response = await self.es.search(
                index=self.surt_edges_index,
                body={
                    "query": {"term": {"source": source_surt}},
                    "size": limit,
                    "_source": ["source", "target"]
                }
            )

            records = []
            for hit in response['hits']['hits']:
                src = hit['_source']
                target_domain = surt_to_domain(src.get('target', ''))
                records.append(LinkRecord(
                    source=domain,
                    target=target_domain,
                    weight=1,
                    provider="cc_web_graph"
                ))

            return records

        except Exception as e:
            return []

    async def _get_outlinks_vertex(
        self, domain: str, limit: int, min_weight: int
    ) -> List[LinkRecord]:
        """Get outlinks from vertex-based index."""
        try:
            source_id = await self._domain_to_vertex_id(domain)
            if not source_id:
                return []

            query = {
                "query": {"term": {"source_vertex_id": source_id}},
                "size": limit,
                "_source": ["target_vertex_id", "link_count"]
            }

            if min_weight > 1:
                query["query"] = {
                    "bool": {
                        "must": [
                            {"term": {"source_vertex_id": source_id}},
                            {"range": {"link_count": {"gte": min_weight}}}
                        ]
                    }
                }

            response = await self.es.search(index=self.edges_index, body=query)

            target_ids = [hit['_source']['target_vertex_id'] for hit in response['hits']['hits']]
            if not target_ids:
                return []

            id_to_domain = await self._vertex_ids_to_domains(target_ids)

            records = []
            for hit in response['hits']['hits']:
                tgt_id = hit['_source']['target_vertex_id']
                tgt_domain = id_to_domain.get(tgt_id)
                if tgt_domain:
                    records.append(LinkRecord(
                        source=domain,
                        target=tgt_domain,
                        weight=hit['_source'].get('link_count', 1),
                        provider="cc_graph_es"
                    ))

            return records

        except Exception as e:
            print(f"[CCGraphES] Vertex outlinks error: {e}")
            return []

    async def _domain_to_vertex_id(self, domain: str) -> Optional[int]:
        """Look up vertex ID for a domain."""
        try:
            response = await self.es.search(
                index=self.vertices_index,
                body={
                    "query": {"term": {"domain.keyword": domain}},
                    "size": 1
                }
            )
            hits = response['hits']['hits']
            if hits:
                return hits[0]['_source']['vertex_id']
            return None
        except Exception as e:
            return None

    async def _vertex_ids_to_domains(self, vertex_ids: List[int]) -> Dict[int, str]:
        """Batch lookup domains for vertex IDs."""
        try:
            response = await self.es.search(
                index=self.vertices_index,
                body={
                    "query": {"terms": {"vertex_id": vertex_ids}},
                    "size": len(vertex_ids),
                    "_source": ["vertex_id", "domain"]
                }
            )
            return {
                hit['_source']['vertex_id']: hit['_source']['domain']
                for hit in response['hits']['hits']
            }
        except Exception as e:
            return {}

    async def get_stats(self) -> dict:
        """Get index statistics."""
        try:
            stats = {}

            # SURT index
            try:
                surt_count = await self.es.count(index=self.surt_edges_index)
                stats['surt_edges_count'] = surt_count['count']
            except:
                stats['surt_edges_count'] = 0

            # Vertex indices
            try:
                edges_count = await self.es.count(index=self.edges_index)
                stats['vertex_edges_count'] = edges_count['count']
            except:
                stats['vertex_edges_count'] = 0

            try:
                vertices_count = await self.es.count(index=self.vertices_index)
                stats['vertices_count'] = vertices_count['count']
            except:
                stats['vertices_count'] = 0

            return stats
        except Exception as e:
            print(f"[CCGraphES] Stats error: {e}")
            return {}


# Convenience functions
async def get_backlinks_cc_graph_es(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get backlinks from CC Graph ES (standalone function)."""
    client = CCGraphESClient()
    try:
        return await client.get_backlinks(domain, limit)
    finally:
        await client.close()


async def get_outlinks_cc_graph_es(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get outlinks from CC Graph ES (standalone function)."""
    client = CCGraphESClient()
    try:
        return await client.get_outlinks(domain, limit)
    finally:
        await client.close()
