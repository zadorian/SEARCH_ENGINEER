"""
LinkLater CC Web Graph Client - ELASTICSEARCH VERSION

Query CC Web Graph from Elasticsearch indices (INSTANT queries).
This replaces the slow S3 file scanning in cc_graph.py.
"""

import asyncio
from typing import List, Optional, Dict
from elasticsearch import AsyncElasticsearch
from .models import LinkRecord


class CCGraphESClient:
    """Client for CC Web Graph using Elasticsearch (FAST)."""

    def __init__(self, es_host: str = "http://localhost:9200"):
        """Initialize ES client."""
        self.es = AsyncElasticsearch([es_host])
        self.edges_index = "cymonides_cc_domain_edges"
        self.vertices_index = "cymonides_cc_domain_vertices"

    async def close(self):
        """Close ES connection."""
        await self.es.close()

    async def _domain_to_vertex_id(self, domain: str) -> Optional[int]:
        """Look up vertex ID for a domain."""
        try:
            response = await self.es.search(
                index=self.vertices_index,
                body={
                    "query": {"term": {"domain": domain}},
                    "size": 1
                }
            )
            hits = response['hits']['hits']
            if hits:
                return hits[0]['_source']['vertex_id']
            return None
        except Exception as e:
            print(f"[CCGraphES] Domain lookup error: {e}")
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
            print(f"[CCGraphES] Batch domain lookup error: {e}")
            return {}

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
            min_weight: Minimum link weight

        Returns:
            List of LinkRecord objects
        """
        try:
            # Step 1: Get vertex ID for target domain
            target_id = await self._domain_to_vertex_id(domain)
            if not target_id:
                print(f"[CCGraphES] Domain not found: {domain}")
                return []

            # Step 2: Query edges where target_vertex_id = target_id
            query = {
                "query": {
                    "term": {"target_vertex_id": target_id}
                },
                "size": limit,
                "sort": [{"link_count": {"order": "desc"}}],
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

            # Step 3: Get source vertex IDs
            source_ids = [hit['_source']['source_vertex_id'] for hit in response['hits']['hits']]
            if not source_ids:
                return []

            # Step 4: Batch lookup source domain names
            id_to_domain = await self._vertex_ids_to_domains(source_ids)

            # Step 5: Build records
            records = []
            for hit in response['hits']['hits']:
                src_id = hit['_source']['source_vertex_id']
                src_domain = id_to_domain.get(src_id)
                if src_domain:
                    records.append(LinkRecord(
                        source=src_domain,
                        target=domain,
                        weight=hit['_source']['link_count'],
                        provider="cc_graph_es"
                    ))

            return records

        except Exception as e:
            print(f"[CCGraphES] Backlinks error: {e}")
            import traceback
            traceback.print_exc()
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
        try:
            # Query ES for edges where source = domain
            query = {
                "query": {
                    "term": {"source.keyword": domain}
                },
                "size": limit,
                "sort": [
                    {"weight": {"order": "desc"}}
                ]
            }

            if min_weight > 1:
                query["query"] = {
                    "bool": {
                        "must": [
                            {"term": {"source.keyword": domain}},
                            {"range": {"weight": {"gte": min_weight}}}
                        ]
                    }
                }

            response = await self.es.search(
                index=self.edges_index,
                body=query
            )

            records = []
            for hit in response['hits']['hits']:
                source_data = hit['_source']
                records.append(LinkRecord(
                    source=source_data.get('source'),
                    target=source_data.get('target'),
                    weight=source_data.get('weight', 1),
                    provider="cc_graph_es"
                ))

            return records

        except Exception as e:
            print(f"[CCGraphES] Outlinks error: {e}")
            return []

    async def get_stats(self) -> dict:
        """Get index statistics."""
        try:
            edges_count = await self.es.count(index=self.edges_index)
            vertices_count = await self.es.count(index=self.vertices_index)

            return {
                'edges_count': edges_count['count'],
                'vertices_count': vertices_count['count'],
                'indices': {
                    'edges': self.edges_index,
                    'vertices': self.vertices_index
                }
            }
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
