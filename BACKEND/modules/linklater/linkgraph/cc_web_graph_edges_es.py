"""
LinkLater CC Web Graph Edges Client - Elasticsearch

Query cc_web_graph_edges for page-level URLs + anchor text.
"""

from typing import List, Dict, Any
from urllib.parse import urlparse

from elasticsearch import AsyncElasticsearch
from ..config import ES_HOST, get_es_headers


def _normalize_domain(domain: str) -> str:
    if not domain:
        return ""
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        try:
            domain = urlparse(domain).netloc
        except Exception:
            pass
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _extract_domain(value: str) -> str:
    if not value:
        return ""
    try:
        host = urlparse(value).netloc
    except Exception:
        host = value.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


def _domain_to_url(domain: str) -> str:
    return f"https://{domain}/" if domain else ""


def _build_domain_should(field: str, domain: str, include_subdomains: bool) -> List[Dict[str, Any]]:
    should = [
        {"term": {field: domain}},
        {"term": {field: f"www.{domain}"}},
    ]
    if include_subdomains:
        should.append({"wildcard": {field: f"*.{domain}"}})
    return should


class CCWebGraphEdgesESClient:
    """Client for cc_web_graph_edges (page-level URLs + anchors)."""

    def __init__(self, es_host: str = ES_HOST):
        self.es = AsyncElasticsearch([es_host], headers=get_es_headers())
        self.index = "cc_web_graph_edges"

    async def close(self):
        await self.es.close()

    async def get_backlink_pages(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True
    ) -> List[Dict[str, Any]]:
        return await self._query_edges(
            domain=domain,
            field="target",
            limit=limit,
            include_subdomains=include_subdomains
        )

    async def get_outlink_pages(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True
    ) -> List[Dict[str, Any]]:
        return await self._query_edges(
            domain=domain,
            field="source",
            limit=limit,
            include_subdomains=include_subdomains
        )

    async def _query_edges(
        self,
        domain: str,
        field: str,
        limit: int,
        include_subdomains: bool
    ) -> List[Dict[str, Any]]:
        domain = _normalize_domain(domain)
        if not domain:
            return []

        query = {
            "bool": {
                "should": _build_domain_should(field, domain, include_subdomains),
                "minimum_should_match": 1
            }
        }

        try:
            response = await self.es.search(
                index=self.index,
                body={
                    "query": query,
                    "size": limit,
                    "sort": [{"indexed_at": {"order": "desc"}}],
                    "_source": [
                        "source",
                        "target",
                        "source_url",
                        "target_url",
                        "anchor_text",
                        "collection",
                        "indexed_at"
                    ]
                }
            )
        except Exception:
            return []

        hits = response.get("hits", {}).get("hits", [])
        results: List[Dict[str, Any]] = []
        for hit in hits:
            src = hit.get("_source", {})
            source_domain = _extract_domain(src.get("source_url") or src.get("source", ""))
            target_domain = _extract_domain(src.get("target_url") or src.get("target", ""))
            source_url = src.get("source_url") or _domain_to_url(source_domain)
            target_url = src.get("target_url") or _domain_to_url(target_domain)

            results.append({
                "source": source_url,
                "target": target_url,
                "anchor_text": src.get("anchor_text"),
                "source_domain": source_domain,
                "target_domain": target_domain,
                "provider": "cc_web_graph_edges",
                "metadata": {
                    "collection": src.get("collection"),
                    "indexed_at": src.get("indexed_at")
                }
            })

        return results
