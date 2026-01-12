"""
C3 Bridge - Query interface to Cymonides-3 (Entity Superindex).

Pre-indexed CommonCrawl-derived data:
- WDC organization entities (9.6M docs, 2023)
- WDC person entities (6.8M docs, 2023)
- WDC product entities (20.3M docs, 2023)
- CC web graph host edges (421M edges, 2024)
- CC host vertices (42.4M hosts, 2024)
- Domains unified (180M domains, multi-year)
- CC PDFs (67K+ PDFs, 2025)
"""

import os
import aiohttp
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

ES_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
ES_USER = os.getenv('ES_USERNAME')
ES_PASS = os.getenv('ES_PASSWORD')


class C3Bridge:
    """
    C3 Bridge - Query interface to Cymonides-3 (Entity Superindex).

    Index catalog with data years:
    - wdc-organization-entities: 9.6M docs (Web Data Commons 2023)
    - wdc-person-entities: 6.8M docs (Web Data Commons 2023)
    - wdc-product-entities: 20.3M docs (Web Data Commons 2023)
    - cc_web_graph_host_edges: 421M edges (CC Web Graph 2024)
    - cc_host_vertices: 42.4M hosts (CC Web Graph 2024)
    - domains_unified: 180M domains (multi-year aggregation)
    - cc_pdfs: 67K+ PDFs (CC PDF Discovery 2025)

    Usage:
        from modules.backdrill.c3_bridge import C3Bridge

        bridge = C3Bridge()
        orgs = await bridge.search_wdc_orgs("Deutsche Bank")
        edges = await bridge.search_webgraph("example.com")
        pdfs = await bridge.search_cc_pdfs("annual report", jurisdiction="DE")
    """

    # Index metadata with data years
    INDEX_METADATA = {
        "wdc-organization-entities": {
            "description": "Web Data Commons organization entities",
            "docs": "9.6M",
            "size": "19.1gb",
            "year": 2023,
            "source": "CommonCrawl WDC extraction",
        },
        "wdc-person-entities": {
            "description": "Web Data Commons person entities",
            "docs": "6.8M",
            "size": "14.5gb",
            "year": 2023,
            "source": "CommonCrawl WDC extraction",
        },
        "wdc-product-entities": {
            "description": "Web Data Commons product entities",
            "docs": "20.3M",
            "size": "36.6gb",
            "year": 2023,
            "source": "CommonCrawl WDC extraction",
        },
        "cc_web_graph_host_edges": {
            "description": "CommonCrawl web graph host-level edges (WDC)",
            "docs": "421M",
            "size": "28.9gb",
            "year": 2024,
            "source": "CommonCrawl Host Graph",
        },
        "cymonides_cc_domain_edges": {
            "description": "Cymonides CC Domain Edges (Original Graph)",
            "docs": "435M",
            "size": "16.5gb",
            "year": 2024,
            "source": "Cymonides Processing",
        },
        "cc_host_vertices": {
            "description": "CommonCrawl host vertices (WDC)",
            "docs": "42.4M",
            "size": "2.3gb",
            "year": 2024,
            "source": "CommonCrawl Host Graph",
        },
        "cymonides_cc_domain_vertices": {
            "description": "Cymonides CC Domain Vertices (Original Graph)",
            "docs": "100M",
            "size": "7.5gb",
            "year": 2024,
            "source": "Cymonides Processing",
        },
        "domains_unified": {
            "description": "Unified domain index",
            "docs": "180M",
            "size": "16.7gb",
            "year": "2020-2024",
            "source": "Multi-source aggregation",
        },
        "cc_pdfs": {
            "description": "CommonCrawl PDF documents",
            "docs": "67K+",
            "size": "varies",
            "year": 2025,
            "source": "CC PDF Discovery",
        },
    }

    def __init__(
        self,
        host: str = ES_URL,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.host = host.rstrip('/')
        self._session = session
        self._own_session = session is None
        self._auth = None
        if ES_USER and ES_PASS:
            self._auth = aiohttp.BasicAuth(ES_USER, ES_PASS)

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    async def _search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Execute an Elasticsearch search."""
        await self._ensure_session()

        body = {
            "query": query,
            "size": size,
        }

        try:
            async with self._session.post(
                f"{self.host}/{index}/_search",
                json=body,
                auth=self._auth,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"ES search failed: {resp.status}")
                    return []

                data = await resp.json()
                hits = data.get("hits", {}).get("hits", [])

                results = []
                for hit in hits:
                    doc = hit.get("_source", {})
                    doc["_id"] = hit.get("_id")
                    doc["_score"] = hit.get("_score")
                    results.append(doc)

                return results

        except Exception as e:
            logger.error(f"ES search error: {e}")
            return []

    def get_index_info(self, index: str) -> Optional[Dict[str, Any]]:
        """Get metadata about an index including data year."""
        return self.INDEX_METADATA.get(index)

    def list_indices(self) -> Dict[str, Dict]:
        """List all available indices with metadata."""
        return self.INDEX_METADATA.copy()

    # -------------------------------------------------------------------------
    # WDC Entity searches
    # -------------------------------------------------------------------------

    async def search_wdc_orgs(
        self,
        query: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search WDC organization entities.

        Index: wdc-organization-entities (9.6M docs, 2023)

        Args:
            query: Search query (company name, etc.)
            limit: Max results

        Returns:
            List of organization entity documents
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["name^3", "legalName^2", "description", "url"],
                "type": "best_fields",
            }
        }
        results = await self._search("wdc-organization-entities", es_query, limit)

        # Add index metadata
        for r in results:
            r["_index_year"] = 2023
            r["_index_source"] = "Web Data Commons"

        return results

    async def search_wdc_persons(
        self,
        query: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search WDC person entities.

        Index: wdc-person-entities (6.8M docs, 2023)

        Args:
            query: Search query (person name)
            limit: Max results

        Returns:
            List of person entity documents
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["name^3", "givenName", "familyName", "jobTitle", "description"],
                "type": "best_fields",
            }
        }
        results = await self._search("wdc-person-entities", es_query, limit)

        for r in results:
            r["_index_year"] = 2023
            r["_index_source"] = "Web Data Commons"

        return results

    async def search_wdc_products(
        self,
        query: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search WDC product entities.

        Index: wdc-product-entities (20.3M docs, 2023)
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["name^3", "description", "brand", "manufacturer"],
                "type": "best_fields",
            }
        }
        results = await self._search("wdc-product-entities", es_query, limit)

        for r in results:
            r["_index_year"] = 2023
            r["_index_source"] = "Web Data Commons"

        return results

    # -------------------------------------------------------------------------
    # Web Graph searches
    # -------------------------------------------------------------------------

    async def search_webgraph(
        self,
        domain: str,
        direction: str = "both",
        limit: int = 100,
        use_original_graph: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Search CC web graph for domain edges (backlinks/outlinks).

        Indices: 
        - cc_web_graph_host_edges (421M edges, WDC)
        - cymonides_cc_domain_edges (435M edges, Original)

        Args:
            domain: Target domain
            direction: "inbound" (backlinks), "outbound" (outlinks), or "both"
            limit: Max results
            use_original_graph: If True, query cymonides_cc_domain_edges instead

        Returns:
            List of edge documents
        """
        queries = []

        # WDC graph uses source_host/target_host
        # Original graph uses source_vertex_id/target_vertex_id (requires resolution)
        # Assuming original graph might have resolved fields or we need vertex lookup first
        # For now, let's assume 'cymonides_cc_domain_edges' works similarly or we search vertex first
        
        index_name = "cymonides_cc_domain_edges" if use_original_graph else "cc_web_graph_host_edges"
        
        # Original graph likely needs vertex ID lookup if it doesn't have hostnames in edges
        if use_original_graph:
            # First find vertex ID for domain
            v_query = {"term": {"domain": domain}}
            v_res = await self._search("cymonides_cc_domain_vertices", v_query, 1)
            if not v_res:
                return []
            vertex_id = v_res[0].get("vertex_id")
            
            queries = []
            if direction in ("inbound", "both"):
                queries.append({"term": {"target_vertex_id": vertex_id}})
            if direction in ("outbound", "both"):
                queries.append({"term": {"source_vertex_id": vertex_id}})
                
        else:
            # WDC Graph logic (host strings)
            if direction in ("inbound", "both"):
                queries.append({"term": {"target_host": domain}})
            if direction in ("outbound", "both"):
                queries.append({"term": {"source_host": domain}})

        es_query = {
            "bool": {
                "should": queries,
                "minimum_should_match": 1
            }
        }

        results = await self._search(index_name, es_query, limit)

        for r in results:
            r["_index_year"] = 2024
            r["_index_source"] = "Cymonides Original" if use_original_graph else "CommonCrawl Host Graph"

        return results

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
        original: bool = False
    ) -> List[Dict[str, Any]]:
        """Get domains linking TO this domain."""
        return await self.search_webgraph(domain, direction="inbound", limit=limit, use_original_graph=original)

    async def get_outlinks(
        self,
        domain: str,
        limit: int = 100,
        original: bool = False
    ) -> List[Dict[str, Any]]:
        """Get domains this domain links TO."""
        return await self.search_webgraph(domain, direction="outbound", limit=limit, use_original_graph=original)

    async def search_host_vertices(
        self,
        query: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search CC host vertices.

        Index: cc_host_vertices (42.4M hosts, 2024)
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["host^3", "domain"],
            }
        }
        results = await self._search("cc_host_vertices", es_query, limit)

        for r in results:
            r["_index_year"] = 2024
            r["_index_source"] = "CommonCrawl Host Graph"

        return results
        
    async def search_cymonides_vertices(
        self,
        query: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search Original Cymonides domain vertices.

        Index: cymonides_cc_domain_vertices (100M domains)
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["domain^3", "reversed_domain"],
            }
        }
        results = await self._search("cymonides_cc_domain_vertices", es_query, limit)

        for r in results:
            r["_index_year"] = 2024
            r["_index_source"] = "Cymonides Original"

        return results

    # -------------------------------------------------------------------------
    # Domain searches
    # -------------------------------------------------------------------------

    async def search_domains(
        self,
        query: str,
        limit: int = 100,
        enrich_with_stats: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search unified domains index.

        Index: domains_unified (180M domains, 2020-2024)

        Args:
            query: Domain name or pattern
            limit: Max results
            enrich_with_stats: If True, fetch backlink counts from edge graph

        Returns:
            List of domain documents
        """
        es_query = {
            "multi_match": {
                "query": query,
                "fields": ["domain^3", "tld", "category"],
            }
        }
        results = await self._search("domains_unified", es_query, limit)

        if not results:
            return []

        # Add index metadata
        for r in results:
            r["_index_year"] = "2020-2024"
            r["_index_source"] = "Multi-source aggregation"

        # Runtime Join: Fetch summary stats from Graph
        if enrich_with_stats:
            await self._enrich_domains_with_graph_stats(results)

        return results

    async def _enrich_domains_with_graph_stats(self, domains: List[Dict[str, Any]]):
        """
        Enrich a list of domain docs with stats from cymonides_cc_domain_edges.
        
        Fetches:
        - inlink_count (approximate)
        """
        domain_names = [d.get("domain") for d in domains if d.get("domain")]
        if not domain_names:
            return

        # We need vertex IDs to query the edge graph efficiently.
        # Assuming domains_unified might have vertex_id, otherwise we search by domain string
        # if the edge graph supports it. 
        # Since cymonides_cc_domain_edges uses vertex_ids, we strictly need to map domain -> vertex_id first
        # OR use the cc_web_graph_host_edges which supports string hostnames.
        
        # Strategy: Use cc_web_graph_host_edges for fast string-based stats
        
        body = {
            "size": 0,
            "query": {
                "terms": {"target_host": domain_names}
            },
            "aggs": {
                "by_domain": {
                    "terms": {"field": "target_host", "size": len(domain_names)},
                    "aggs": {
                        "edge_count": {"value_count": {"field": "source_host"}}
                    }
                }
            }
        }
        
        try:
            async with self._session.post(
                f"{self.host}/cc_web_graph_host_edges/_search",
                json=body,
                auth=self._auth,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    buckets = data.get("aggregations", {}).get("by_domain", {}).get("buckets", [])
                    
                    stats_map = {b["key"]: b["doc_count"] for b in buckets}
                    
                    for d in domains:
                        dom = d.get("domain")
                        if dom in stats_map:
                            d["graph_stats"] = {
                                "inlink_count": stats_map[dom],
                                "source": "cc_web_graph_host_edges"
                            }
        except Exception as e:
            logger.warning(f"Graph enrichment failed: {e}")


    # -------------------------------------------------------------------------
    # PDF searches
    # -------------------------------------------------------------------------

    async def search_cc_pdfs(
        self,
        query: str,
        jurisdiction: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search CC PDF collection.

        Index: cc_pdfs (67K+ PDFs, 2025)

        Args:
            query: Search query (title, content keywords)
            jurisdiction: Optional 2-letter country code (e.g., "DE", "UK")
            limit: Max results

        Returns:
            List of PDF documents with URL, metadata, score
        """
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "url^2", "content", "domain"],
                }
            }
        ]

        if jurisdiction:
            must_clauses.append({
                "term": {"jurisdiction": jurisdiction.upper()}
            })

        es_query = {
            "bool": {
                "must": must_clauses
            }
        }

        results = await self._search("cc_pdfs", es_query, limit)

        for r in results:
            r["_index_year"] = 2025
            r["_index_source"] = "CC PDF Discovery"

        return results

    async def get_pdfs_for_domain(
        self,
        domain: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all indexed PDFs from a specific domain."""
        es_query = {
            "term": {"domain": domain}
        }
        return await self._search("cc_pdfs", es_query, limit)

    # -------------------------------------------------------------------------
    # Raw query
    # -------------------------------------------------------------------------

    async def raw_search(
        self,
        index: str,
        query: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Execute a raw Elasticsearch query on any index.

        For advanced queries not covered by helper methods.
        """
        return await self._search(index, query, size)
