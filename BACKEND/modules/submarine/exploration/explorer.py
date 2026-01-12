#!/usr/bin/env python3
"""
SUBMARINE Exploration Engine

Purpose:
  - Discover target domains/URLs when the user didn't provide an explicit domain
  - Support explicit `indom:` (keyword-in-domain) and `inurl:` (keyword-in-URL) searches
  - Use LOCAL Cymonides/ATLAS domain indices first, then optional BRUTE helpers
  - Persist discovered targets/rules into an EDITh-B targets note for the project

This is intentionally conservative:
  - Bounded result sizes per index
  - Best-effort optional integrations (BRUTE, LinkLater WHOIS/alldom)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from elasticsearch import AsyncElasticsearch

from .targets_note import update_targets

logger = logging.getLogger(__name__)


def _normalize_domain(domain: str) -> Optional[str]:
    d = (domain or "").strip().lower()
    if not d:
        return None
    if d.startswith("www."):
        d = d[4:]
    if ":" in d:
        d = d.split(":", 1)[0]
    if "." not in d:
        return None
    return d


def _domain_from_url(url: str) -> Optional[str]:
    u = (url or "").strip()
    if not u:
        return None
    try:
        parsed = urlparse(u if "://" in u else f"https://{u}")
        return _normalize_domain(parsed.netloc)
    except Exception:
        return None


def _dedupe(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        v = (item or "").strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _parse_directives(text: str) -> Dict[str, List[str]]:
    """
    Parse directives from a query string.

    Supported:
      - indom:<kw> / indom: "<kw phrase>"
      - inurl:<kw> / inurl: "<kw phrase>"
      - hop(<n>) for graph expansion
    """
    directives: Dict[str, List[str]] = {"indom": [], "inurl": []}
    if not text:
        return directives

    try:
        tokens = shlex.split(text)
    except Exception:
        tokens = text.split()

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        m = re.match(r"^(indom|inurl)\s*:(.*)$", tok, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            rest = (m.group(2) or "").strip()
            if rest:
                directives[kind].append(rest)
            elif i + 1 < len(tokens):
                directives[kind].append(tokens[i + 1])
                i += 1
            i += 1
            continue

        # Support "indom:" "<kw>" split tokens.
        if tok.lower() in {"indom:", "inurl:"}:
            kind = tok[:-1].lower()
            if i + 1 < len(tokens):
                directives[kind].append(tokens[i + 1])
                i += 2
                continue

        i += 1

    directives["indom"] = _dedupe(directives["indom"])
    directives["inurl"] = _dedupe(directives["inurl"])
    return directives


def _parse_hops(text: str) -> int:
    m = re.search(r"\bhop\((\d+)\)", text or "", re.IGNORECASE)
    if not m:
        return 0
    try:
        return max(0, min(int(m.group(1)), 5))
    except Exception:
        return 0


@dataclass
class ExplorationResult:
    query: str
    indom_keywords: List[str]
    inurl_keywords: List[str]
    hop_depth: int
    domains: List[str]
    urls: List[str]
    sources: Dict[str, Any]
    edith: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "indom_keywords": self.indom_keywords,
            "inurl_keywords": self.inurl_keywords,
            "hop_depth": self.hop_depth,
            "domains": self.domains,
            "urls": self.urls,
            "sources": self.sources,
            "edith": self.edith,
        }


class ExplorationEngine:
    DOMAIN_INDICES_DEFAULT = [
        "atlas_domains_unified",
        "domains_unified",
        "atlas",
        "top_domains",
        "unified_domain_profiles",
        "wdc-domain-profiles",
        "cymonides_cc_domain_vertices",
    ]

    CORPUS_INDICES_DEFAULT = [
        # Prefer home/unified alias if present; fall back to raw.
        "cymonides-3",
        "cymonides-2",
    ]

    def __init__(self, es_host: str = "http://localhost:9200"):
        self.es_host = es_host
        self.es: Optional[AsyncElasticsearch] = None

    async def _get_client(self) -> AsyncElasticsearch:
        if not self.es:
            self.es = AsyncElasticsearch([self.es_host])
        return self.es

    async def close(self) -> None:
        if self.es:
            await self.es.close()
            self.es = None

    def _domain_indices(self) -> List[str]:
        env = os.getenv("SUBMARINE_DOMAIN_INDICES", "").strip()
        if env:
            return [p.strip() for p in env.split(",") if p.strip()]
        return list(self.DOMAIN_INDICES_DEFAULT)

    def _corpus_indices(self) -> List[str]:
        env = os.getenv("SUBMARINE_CORPUS_INDICES", "").strip()
        if env:
            return [p.strip() for p in env.split(",") if p.strip()]
        return list(self.CORPUS_INDICES_DEFAULT)

    async def search_indom(self, keyword: str, limit_per_index: int = 200) -> Tuple[List[str], Dict[str, Any]]:
        """Find domains whose domain string contains keyword."""
        es = await self._get_client()
        kw = (keyword or "").strip().lower()
        if not kw:
            return [], {"error": "empty_keyword"}

        indices = self._domain_indices()
        domains: List[str] = []
        scanned: List[str] = []
        errors: Dict[str, str] = {}

        for index in indices:
            try:
                if not await es.indices.exists(index=index):
                    continue
                scanned.append(index)

                # Field variance: most indices have keyword `domain`, CC vertices have `domain.keyword`.
                domain_field = "domain.keyword" if index == "cymonides_cc_domain_vertices" else "domain"

                q = {"wildcard": {domain_field: f"*{kw}*"}}

                resp = await es.search(
                    index=index,
                    query=q,
                    size=min(limit_per_index, 1000),
                    track_total_hits=False,
                    _source=["domain"],
                )

                for hit in resp.get("hits", {}).get("hits", []):
                    src = hit.get("_source") or {}
                    d = src.get("domain")
                    nd = _normalize_domain(d) if isinstance(d, str) else None
                    if nd:
                        domains.append(nd)
            except Exception as e:
                errors[index] = str(e)

        # Optional BRUTE indom helper (best-effort)
        brute_domains: List[str] = []
        brute_error: Optional[str] = None
        try:
            from brute.targeted_searches.domain.indom import IndomSearcher  # type: ignore

            searcher = IndomSearcher()
            brute_result = await searcher.search_async(f"indom:{kw}")
            for item in (brute_result or {}).get("results", [])[:500]:
                d = item.get("domain") or _domain_from_url(item.get("url") or "")
                nd = _normalize_domain(d) if isinstance(d, str) else None
                if nd:
                    brute_domains.append(nd)
        except Exception as e:
            brute_error = str(e)

        domains = _dedupe(domains + brute_domains)
        return domains, {
            "keyword": kw,
            "indices_scanned": scanned,
            "limit_per_index": limit_per_index,
            "brute_used": bool(brute_domains),
            "brute_error": brute_error,
            "errors": errors,
        }

    async def search_inurl(self, keyword: str, limit_per_index: int = 200) -> Tuple[List[str], List[str], Dict[str, Any]]:
        """Find URLs containing keyword; returns (domains, urls, meta)."""
        es = await self._get_client()
        kw = (keyword or "").strip()
        if not kw:
            return [], [], {"error": "empty_keyword"}

        kw_lower = kw.lower()
        urls: List[str] = []
        domains: List[str] = []
        scanned: List[str] = []
        errors: Dict[str, str] = {}

        # Search corpus indices for url fields
        for index in self._corpus_indices():
            try:
                if not await es.indices.exists(index=index):
                    continue
                scanned.append(index)

                q = {
                    "bool": {
                        "should": [
                            {"wildcard": {"source_url.keyword": f"*{kw_lower}*"}},
                            {"wildcard": {"url.keyword": f"*{kw_lower}*"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
                resp = await es.search(
                    index=index,
                    query=q,
                    size=min(limit_per_index, 1000),
                    track_total_hits=False,
                    _source=["source_url", "url", "source_domain", "domain"],
                )
                for hit in resp.get("hits", {}).get("hits", []):
                    src = hit.get("_source") or {}
                    for fld in ("source_url", "url"):
                        u = src.get(fld)
                        if isinstance(u, str) and u:
                            urls.append(u)
                            d = _domain_from_url(u)
                            if d:
                                domains.append(d)
                    for fld in ("source_domain", "domain"):
                        d = src.get(fld)
                        if isinstance(d, str):
                            nd = _normalize_domain(d)
                            if nd:
                                domains.append(nd)
            except Exception as e:
                errors[index] = str(e)

        # Search domain indices for url-like fields (best-effort)
        for index in self._domain_indices():
            if index in scanned:
                continue
            try:
                if not await es.indices.exists(index=index):
                    continue
                scanned.append(index)

                # Many domain indices only have `domain`; `url` is not guaranteed.
                q = {
                    "bool": {
                        "should": [
                            {"wildcard": {"url.keyword": f"*{kw_lower}*"}},
                            {"wildcard": {"url": f"*{kw_lower}*"}},
                            {"wildcard": {"website.keyword": f"*{kw_lower}*"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
                resp = await es.search(
                    index=index,
                    query=q,
                    size=min(limit_per_index, 500),
                    track_total_hits=False,
                    _source=["domain", "url", "website"],
                )
                for hit in resp.get("hits", {}).get("hits", []):
                    src = hit.get("_source") or {}
                    d = src.get("domain")
                    if isinstance(d, str):
                        nd = _normalize_domain(d)
                        if nd:
                            domains.append(nd)
                    for fld in ("url", "website"):
                        u = src.get(fld)
                        if isinstance(u, str) and u:
                            urls.append(u)
                            dd = _domain_from_url(u)
                            if dd:
                                domains.append(dd)
            except Exception as e:
                errors[index] = str(e)

        # Optional BRUTE inurl helper (best-effort; may require API keys)
        brute_urls: List[str] = []
        brute_error: Optional[str] = None
        try:
            from brute.targeted_searches.content.inurl import InURLSearch  # type: ignore

            searcher = InURLSearch()
            if hasattr(searcher, "search_urls") and asyncio.iscoroutinefunction(searcher.search_urls):
                brute_result = await searcher.search_urls(keyword=kw, max_results=100)
                for engine_urls in (brute_result or {}).values():
                    if isinstance(engine_urls, list):
                        for u in engine_urls:
                            if isinstance(u, str) and u:
                                brute_urls.append(u)
            else:
                brute_result = searcher.search(kw)
                for item in (brute_result or {}).get("results", [])[:500]:
                    u = item.get("url")
                    if isinstance(u, str) and u:
                        brute_urls.append(u)
        except Exception as e:
            brute_error = str(e)

        if brute_urls:
            urls.extend(brute_urls)
            for u in brute_urls:
                d = _domain_from_url(u)
                if d:
                    domains.append(d)

        urls = _dedupe(urls)
        domains = _dedupe(domains)
        return domains, urls, {
            "keyword": kw,
            "indices_scanned": scanned,
            "limit_per_index": limit_per_index,
            "brute_used": bool(brute_urls),
            "brute_error": brute_error,
            "errors": errors,
        }

    async def expand_via_webgraph(
        self,
        seed_domains: List[str],
        hops: int = 1,
        per_domain_limit: int = 500,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """Expand domains using cc_web_graph_host_edges (fast domain->domain links)."""
        es = await self._get_client()
        hops = max(0, min(hops, 5))
        per_domain_limit = max(10, min(per_domain_limit, 5000))

        if hops == 0:
            return _dedupe([d for d in seed_domains if d]), {"hops": 0, "expanded": 0}

        if not await es.indices.exists(index="cc_web_graph_host_edges"):
            return _dedupe([d for d in seed_domains if d]), {
                "hops": hops,
                "expanded": 0,
                "error": "cc_web_graph_host_edges missing",
            }

        visited: Set[str] = set()
        frontier: List[str] = []
        for d in seed_domains:
            nd = _normalize_domain(d)
            if not nd or nd in visited:
                continue
            visited.add(nd)
            frontier.append(nd)

        scanned_domains = 0
        for _hop in range(hops):
            next_frontier: List[str] = []
            for domain in list(frontier):
                scanned_domains += 1
                q = {
                    "bool": {
                        "should": [
                            {"term": {"source": domain}},
                            {"term": {"target": domain}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
                try:
                    resp = await es.search(
                        index="cc_web_graph_host_edges",
                        query=q,
                        size=per_domain_limit,
                        track_total_hits=False,
                        _source=["source", "target"],
                    )
                except Exception:
                    continue

                for hit in resp.get("hits", {}).get("hits", []):
                    src = hit.get("_source") or {}
                    s = _normalize_domain(src.get("source") or "")
                    t = _normalize_domain(src.get("target") or "")
                    for candidate in (s, t):
                        if not candidate or candidate in visited:
                            continue
                        visited.add(candidate)
                        next_frontier.append(candidate)

            frontier = _dedupe(next_frontier)
            if not frontier:
                break

        return _dedupe(list(visited)), {
            "hops": hops,
            "seed_count": len(_dedupe(seed_domains)),
            "expanded": len(visited),
            "scanned_domains": scanned_domains,
            "per_domain_limit": per_domain_limit,
        }

    async def explore(
        self,
        query: str,
        project_id: str = "default",
        limit_per_index: int = 200,
        update_note: bool = True,
    ) -> ExplorationResult:
        directives = _parse_directives(query)
        hop_depth = _parse_hops(query)

        all_domains: List[str] = []
        all_urls: List[str] = []
        sources: Dict[str, Any] = {"indom": [], "inurl": [], "webgraph": None}

        for kw in directives.get("indom", []):
            domains, meta = await self.search_indom(kw, limit_per_index=limit_per_index)
            sources["indom"].append(meta)
            all_domains.extend(domains)

        for kw in directives.get("inurl", []):
            domains, urls, meta = await self.search_inurl(kw, limit_per_index=limit_per_index)
            sources["inurl"].append(meta)
            all_domains.extend(domains)
            all_urls.extend(urls)

        all_domains = _dedupe([d for d in all_domains if d])
        all_urls = _dedupe([u for u in all_urls if u])

        if hop_depth and all_domains:
            expanded, meta = await self.expand_via_webgraph(all_domains, hops=hop_depth)
            sources["webgraph"] = meta
            all_domains = _dedupe(all_domains + expanded)

        edith_info: Dict[str, Any] = {"updated": False}
        if update_note:
            try:
                doc, merged = update_targets(
                    project_id=project_id,
                    add_domains=all_domains,
                    add_urls=all_urls,
                    add_domain_rules=directives.get("indom") or [],
                    add_url_rules=directives.get("inurl") or [],
                )
                edith_info = {
                    "updated": True,
                    "document_id": doc.get("id"),
                    "document_title": doc.get("title"),
                    "counts": (doc.get("metadata") or {}).get("submarine", {}).get("counts"),
                    "targets": merged.to_dict(),
                }
            except Exception as e:
                edith_info = {"updated": False, "error": str(e)}

        return ExplorationResult(
            query=query,
            indom_keywords=directives.get("indom") or [],
            inurl_keywords=directives.get("inurl") or [],
            hop_depth=hop_depth,
            domains=all_domains,
            urls=all_urls,
            sources=sources,
            edith=edith_info,
        )


async def run_exploration(
    query: str,
    project_id: str = "default",
    es_host: str = "http://localhost:9200",
    limit_per_index: int = 200,
    update_note: bool = True,
) -> Dict[str, Any]:
    engine = ExplorationEngine(es_host=es_host)
    try:
        result = await engine.explore(
            query=query,
            project_id=project_id,
            limit_per_index=limit_per_index,
            update_note=update_note,
        )
        return result.to_dict()
    finally:
        await engine.close()
