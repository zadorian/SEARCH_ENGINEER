"""
LinkLater C-2 Outlinks Client - Elasticsearch

Query cymonides-2 for outlinks that point to a target domain.
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


def _matches_domain(url: str, domain: str, include_subdomains: bool) -> bool:
    host = _extract_domain(url)
    if not host or not domain:
        return False
    if host == domain:
        return True
    if include_subdomains and host.endswith(f".{domain}"):
        return True
    return False


class C2OutlinksESClient:
    """Client for cymonides-2 outlinks + outlink_notes."""

    def __init__(self, es_host: str = ES_HOST):
        self.es = AsyncElasticsearch([es_host], headers=get_es_headers())
        self.index = "cymonides-2"

    async def close(self):
        await self.es.close()

    async def get_backlink_pages(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True,
        max_docs: int = 200
    ) -> List[Dict[str, Any]]:
        domain = _normalize_domain(domain)
        if not domain:
            return []

        should = [
            {"prefix": {"outlinks": f"http://{domain}"}},
            {"prefix": {"outlinks": f"https://{domain}"}},
            {"prefix": {"outlinks": f"http://www.{domain}"}},
            {"prefix": {"outlinks": f"https://www.{domain}"}},
        ]
        if include_subdomains:
            should.append({"wildcard": {"outlinks": f"*://*.{domain}/*"}})

        query = {
            "bool": {
                "should": should,
                "minimum_should_match": 1
            }
        }

        try:
            response = await self.es.search(
                index=self.index,
                body={
                    "query": query,
                    "size": max_docs,
                    "_source": ["source_url", "source_domain", "outlinks", "outlink_notes"]
                }
            )
        except Exception:
            return []

        hits = response.get("hits", {}).get("hits", [])
        results: List[Dict[str, Any]] = []

        for hit in hits:
            src = hit.get("_source", {})
            source_url = src.get("source_url") or src.get("url", "")
            source_domain = src.get("source_domain") or _extract_domain(source_url)
            outlinks = src.get("outlinks") or []
            notes = src.get("outlink_notes") or []
            note_map = {
                n.get("url"): n.get("anchor_text")
                for n in notes
                if isinstance(n, dict) and n.get("url")
            }

            for outlink in outlinks:
                if not _matches_domain(outlink, domain, include_subdomains):
                    continue
                results.append({
                    "source": source_url,
                    "target": outlink,
                    "anchor_text": note_map.get(outlink),
                    "source_domain": source_domain,
                    "target_domain": _extract_domain(outlink),
                    "provider": "cymonides-2",
                })
                if 0 < limit <= len(results):
                    return results

        return results

    async def get_outlink_pages(
        self,
        domain: str,
        limit: int = 100,
        include_subdomains: bool = True,
        max_docs: int = 200
    ) -> List[Dict[str, Any]]:
        domain = _normalize_domain(domain)
        if not domain:
            return []

        should = [
            {"term": {"source_domain": domain}},
            {"term": {"source_domain": f"www.{domain}"}},
            {"term": {"domain": domain}},
            {"term": {"domain": f"www.{domain}"}},
        ]
        if include_subdomains:
            should.append({"wildcard": {"source_domain": f"*.{domain}"}})
            should.append({"wildcard": {"domain": f"*.{domain}"}})

        query = {
            "bool": {
                "should": should,
                "minimum_should_match": 1
            }
        }

        try:
            response = await self.es.search(
                index=self.index,
                body={
                    "query": query,
                    "size": max_docs,
                    "_source": ["source_url", "source_domain", "outlinks", "outlink_notes", "url", "domain"]
                }
            )
        except Exception:
            return []

        hits = response.get("hits", {}).get("hits", [])
        results: List[Dict[str, Any]] = []

        for hit in hits:
            src = hit.get("_source", {})
            source_url = src.get("source_url") or src.get("url", "")
            source_domain = src.get("source_domain") or src.get("domain") or _extract_domain(source_url)
            outlinks = src.get("outlinks") or []
            notes = src.get("outlink_notes") or []
            note_map = {
                n.get("url"): n.get("anchor_text")
                for n in notes
                if isinstance(n, dict) and n.get("url")
            }

            for outlink in outlinks:
                results.append({
                    "source": source_url,
                    "target": outlink,
                    "anchor_text": note_map.get(outlink),
                    "source_domain": source_domain,
                    "target_domain": _extract_domain(outlink),
                    "provider": "cymonides-2",
                })
                if 0 < limit <= len(results):
                    return results

        return results
