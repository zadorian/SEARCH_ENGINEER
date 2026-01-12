#!/usr/bin/env python3
"""
SONAR - Elastic Index Scanner

Scans our Elasticsearch indices to identify relevant domains/URLs
before touching raw WARC data. Uses all available "submerging points":

1. DOMAIN INDICES:
   - domains_unified (180M) - Master domain list
   - atlas_domains_unified (100M) - Unified with metadata
   - atlas (155M) - Raw atlas records

2. ENTITY INDICES:
   - wdc-person-entities (6.8M) - Extracted persons
   - persons_unified (15M) - Unified person records
   - openownership (36M) - Beneficial ownership

3. CONTACT INDICES:
   - phones_unified (49K) - Phone numbers
   - emails_unified (220K) - Email addresses
   - breach_records (33M) - Data breaches

4. GRAPH INDICES:
   - cc_web_graph_host_edges (421M) - Web graph
   - entity_links (4.7M) - Entity relationships
   - entity-mentions (3.9M) - Entity mentions
"""

import asyncio
import logging
import os
import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from elasticsearch import AsyncElasticsearch
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SonarHit:
    """A single search hit from our indices."""
    index: str
    doc_id: str
    domain: Optional[str] = None
    url: Optional[str] = None
    score: float = 0.0
    source: Dict[str, Any] = field(default_factory=dict)
    match_type: str = "unknown"  # domain, url, email, phone, entity, graph


@dataclass
class SonarResult:
    """Aggregated results from scanning our indices."""
    query: str
    domains: Set[str] = field(default_factory=set)
    urls: Set[str] = field(default_factory=set)
    hits: List[SonarHit] = field(default_factory=list)
    indices_scanned: List[str] = field(default_factory=list)
    total_hits: int = 0

    def add_domain(self, domain: str):
        """Add a domain, normalizing it first."""
        if domain:
            clean = domain.lower().strip()
            if clean and "." in clean:
                self.domains.add(clean)

    def add_url(self, url: str):
        """Add a URL and extract its domain."""
        if url:
            self.urls.add(url)
            try:
                parsed = urlparse(url if "://" in url else f"https://{url}")
                if parsed.netloc:
                    self.add_domain(parsed.netloc)
            except:
                pass


class Sonar:
    """
    Elastic Index Scanner for identifying relevant domains/URLs.

    Usage:
        sonar = Sonar()
        result = await sonar.scan_all("+1-234-567-8900")  # Phone
        result = await sonar.scan_all("john.smith@example.com")  # Email
        result = await sonar.scan_all("John Smith")  # Name
        result = await sonar.scan_all("example.com")  # Domain

        # Specific scans
        result = await sonar.scan_domains("example.com")
        result = await sonar.scan_entities("John Smith")
        result = await sonar.scan_contacts("+1-234-567-8900")
        result = await sonar.scan_graph("example.com")
    """

    # Index groups
    DOMAIN_INDICES = [
        "domains_unified",
        "atlas_domains_unified",
        "atlas",
        "unified_domain_profiles",
        "wdc-domain-profiles",
    ]

    ENTITY_INDICES = [
        "wdc-person-entities",
        "persons_unified",
        "wdc-localbusiness-entities",
        "openownership",
    ]

    CONTACT_INDICES = [
        "phones_unified",
        "emails_unified",
        "breach_records",
    ]

    GRAPH_INDICES = [
        "cc_web_graph_host_edges",
        "entity_links",
        "entity-mentions",
        "search_edges",
    ]

    UK_INDICES = [
        "uk_ccod",
        "uk_ocod",
        "uk_addresses",
    ]

    CORPUS_INDICES_DEFAULT = [
        # Home/unified corpus (preferred; may not exist yet during consolidation)
        "cymonides-3",
        # Raw ingest / staging corpus
        "cymonides-2",
        # Legacy/aux corpus
        "linklater_corpus",
    ]

    def __init__(self, es_host: str = "http://localhost:9200"):
        self.es_host = es_host
        self.es: Optional[AsyncElasticsearch] = None

    async def _get_client(self) -> AsyncElasticsearch:
        if not self.es:
            self.es = AsyncElasticsearch([self.es_host])
        return self.es

    async def close(self):
        if self.es:
            await self.es.close()
            self.es = None

    def _detect_query_type(self, query: str) -> str:
        """Detect what type of entity the query represents."""
        query = query.strip()

        # Phone number patterns
        if re.match(r'^[\+\d\s\-\(\)]{10,}$', query):
            return "phone"

        # Email pattern
        if "@" in query and "." in query.split("@")[-1]:
            return "email"

        # URL pattern
        if query.startswith(("http://", "https://", "www.")):
            return "url"

        # Domain pattern (has dots, no spaces, looks like domain)
        if "." in query and " " not in query and len(query) < 100:
            parts = query.split(".")
            if all(p.isalnum() or p.replace("-", "").isalnum() for p in parts):
                return "domain"

        # Default: entity name
        return "entity"

    async def scan_all(self, query: str, limit: int = 10000) -> SonarResult:
        """
        Scan ALL relevant indices based on query type.
        This is the main entry point for smart pre-filtering.
        """
        result = SonarResult(query=query)
        query_type = self._detect_query_type(query)

        logger.info(f"SONAR: Scanning for '{query}' (detected type: {query_type})")

        # Route to appropriate scanners based on type
        if query_type == "phone":
            await self._scan_contacts_phone(query, result, limit)
            await self._scan_breaches_phone(query, result, limit)
            await self._scan_corpus_indices(query, query_type, result, limit)

        elif query_type == "email":
            await self._scan_contacts_email(query, result, limit)
            await self._scan_breaches_email(query, result, limit)
            # Also scan domain from email
            domain = query.split("@")[-1]
            await self._scan_domain_indices(domain, result, limit)
            await self._scan_corpus_indices(query, query_type, result, limit)

        elif query_type == "url":
            parsed = urlparse(query)
            if parsed.netloc:
                await self._scan_domain_indices(parsed.netloc, result, limit)
                await self._scan_graph_backlinks(parsed.netloc, result, limit)
            await self._scan_corpus_indices(query, query_type, result, limit)

        elif query_type == "domain":
            await self._scan_domain_indices(query, result, limit)
            await self._scan_graph_backlinks(query, result, limit)
            await self._scan_entity_domain(query, result, limit)
            await self._scan_corpus_indices(query, query_type, result, limit)

        else:  # entity name
            await self._scan_entity_indices(query, result, limit)
            await self._scan_ownership(query, result, limit)
            await self._scan_uk_companies(query, result, limit)
            await self._scan_corpus_indices(query, query_type, result, limit)

        logger.info(f"SONAR: Found {len(result.domains)} domains, {len(result.urls)} URLs, {result.total_hits} total hits")
        return result

    async def _scan_domain_indices(self, domain: str, result: SonarResult, limit: int):
        """Scan domain-focused indices."""
        es = await self._get_client()

        for index in self.DOMAIN_INDICES:
            try:
                # Check if index exists
                if not await es.indices.exists(index=index):
                    continue

                result.indices_scanned.append(index)

                # Build query based on known field patterns
                query = {
                    "bool": {
                        "should": [
                            {"match": {"domain": domain}},
                            {"match": {"url": f"*{domain}*"}},
                            {"wildcard": {"domain": f"*{domain}*"}},
                            {"wildcard": {"url.keyword": f"*{domain}*"}},
                        ],
                        "minimum_should_match": 1
                    }
                }

                resp = await es.search(
                    index=index,
                    query=query,
                    size=min(limit, 1000),
                    _source=True
                )

                for hit in resp["hits"]["hits"]:
                    src = hit["_source"]
                    sonar_hit = SonarHit(
                        index=index,
                        doc_id=hit["_id"],
                        score=hit["_score"] or 0,
                        source=src,
                        match_type="domain"
                    )

                    # Extract domain/URL from various field patterns
                    for fld in ["domain", "url", "host", "source_url"]:
                        if fld in src:
                            val = src[fld]
                            if isinstance(val, str):
                                if "/" in val or "://" in val:
                                    result.add_url(val)
                                    sonar_hit.url = val
                                else:
                                    result.add_domain(val)
                                    sonar_hit.domain = val

                    result.hits.append(sonar_hit)
                    result.total_hits += 1

            except Exception as e:
                logger.warning(f"Error scanning {index}: {e}")

    async def _scan_entity_indices(self, name: str, result: SonarResult, limit: int):
        """Scan entity indices for person/company names."""
        es = await self._get_client()

        for index in self.ENTITY_INDICES:
            try:
                if not await es.indices.exists(index=index):
                    continue

                result.indices_scanned.append(index)

                query = {
                    "bool": {
                        "should": [
                            {"match_phrase": {"name": name}},
                            {"match_phrase": {"full_name": name}},
                            {"match_phrase": {"company_name": name}},
                            {"match": {"name": {"query": name, "fuzziness": "AUTO"}}},
                        ],
                        "minimum_should_match": 1
                    }
                }

                resp = await es.search(
                    index=index,
                    query=query,
                    size=min(limit, 1000),
                    _source=True
                )

                for hit in resp["hits"]["hits"]:
                    src = hit["_source"]
                    sonar_hit = SonarHit(
                        index=index,
                        doc_id=hit["_id"],
                        score=hit["_score"] or 0,
                        source=src,
                        match_type="entity"
                    )

                    # Extract domains from entity records
                    for fld in ["url", "source_url", "website", "domain", "page_url"]:
                        if fld in src:
                            val = src[fld]
                            if isinstance(val, str):
                                result.add_url(val)
                                sonar_hit.url = val

                    result.hits.append(sonar_hit)
                    result.total_hits += 1

            except Exception as e:
                logger.warning(f"Error scanning {index}: {e}")

    async def _scan_contacts_phone(self, phone: str, result: SonarResult, limit: int):
        """Scan for phone number matches."""
        es = await self._get_client()

        # Normalize phone for search
        phone_normalized = re.sub(r'[\s\-\(\)]', '', phone)

        try:
            if not await es.indices.exists(index="phones_unified"):
                return

            result.indices_scanned.append("phones_unified")

            query = {
                "bool": {
                    "should": [
                        {"match": {"phone": phone}},
                        {"match": {"phone_normalized": phone_normalized}},
                        {"wildcard": {"phone": f"*{phone_normalized[-10:]}*"}}  # Last 10 digits
                    ],
                    "minimum_should_match": 1
                }
            }

            resp = await es.search(
                index="phones_unified",
                query=query,
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="phones_unified",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="phone"
                )

                for fld in ["domain", "source_url", "url"]:
                    if fld in src:
                        result.add_url(src[fld])
                        sonar_hit.url = src[fld]

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning phones_unified: {e}")

    async def _scan_contacts_email(self, email: str, result: SonarResult, limit: int):
        """Scan for email matches."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="emails_unified"):
                return

            result.indices_scanned.append("emails_unified")

            query = {
                "bool": {
                    "should": [
                        {"term": {"email.keyword": email.lower()}},
                        {"match": {"email": email}},
                    ],
                    "minimum_should_match": 1
                }
            }

            resp = await es.search(
                index="emails_unified",
                query=query,
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="emails_unified",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="email"
                )

                for fld in ["domain", "source_url", "url", "source_domain"]:
                    if fld in src:
                        result.add_url(src[fld])
                        sonar_hit.url = src[fld]

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning emails_unified: {e}")

    async def _scan_breaches_phone(self, phone: str, result: SonarResult, limit: int):
        """Scan breach records for phone number."""
        es = await self._get_client()
        phone_normalized = re.sub(r'[\s\-\(\)]', '', phone)

        try:
            if not await es.indices.exists(index="breach_records"):
                return

            result.indices_scanned.append("breach_records")

            resp = await es.search(
                index="breach_records",
                query={"match": {"phone": phone_normalized}},
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="breach_records",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="breach"
                )

                # Breach records often have source/database field
                if "source" in src:
                    result.add_domain(src["source"])

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning breach_records: {e}")

    async def _scan_breaches_email(self, email: str, result: SonarResult, limit: int):
        """Scan breach records for email."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="breach_records"):
                return

            result.indices_scanned.append("breach_records")

            resp = await es.search(
                index="breach_records",
                query={"term": {"email.keyword": email.lower()}},
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="breach_records",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="breach"
                )

                if "source" in src:
                    result.add_domain(src["source"])

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning breach_records: {e}")

    async def _scan_graph_backlinks(self, domain: str, result: SonarResult, limit: int):
        """Scan web graph for backlinks to/from domain."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="cc_web_graph_host_edges"):
                return

            result.indices_scanned.append("cc_web_graph_host_edges")

            # Look for domain as target (who links TO it) and source (who it links TO)
            query = {
                "bool": {
                    "should": [
                        {"term": {"target": domain}},
                        {"term": {"source": domain}},
                        {"wildcard": {"target": f"*.{domain}"}},
                        {"wildcard": {"source": f"*.{domain}"}},
                    ],
                    "minimum_should_match": 1
                }
            }

            resp = await es.search(
                index="cc_web_graph_host_edges",
                query=query,
                size=min(limit, 5000),  # Graph can have many edges
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="cc_web_graph_host_edges",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="graph"
                )

                # Add both source and target domains
                if "source" in src:
                    result.add_domain(src["source"])
                if "target" in src:
                    result.add_domain(src["target"])

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning cc_web_graph_host_edges: {e}")

    def _get_corpus_indices(self) -> List[str]:
        env = os.getenv("SUBMARINE_CORPUS_INDICES", "").strip()
        if env:
            return [p.strip() for p in env.split(",") if p.strip()]
        return list(self.CORPUS_INDICES_DEFAULT)

    def _extract_domains_urls_from_corpus_source(self, src: Dict[str, Any], result: SonarResult, sonar_hit: SonarHit):
        def _add_domain(val: Any):
            if isinstance(val, str) and val:
                result.add_domain(val)
                sonar_hit.domain = sonar_hit.domain or val

        def _add_url(val: Any):
            if isinstance(val, str) and val:
                result.add_url(val)
                sonar_hit.url = sonar_hit.url or val

        for fld in ("source_domain", "domain"):
            _add_domain(src.get(fld))

        for fld in ("source_url", "url"):
            _add_url(src.get(fld))

        extracted = src.get("extracted_entities")
        if isinstance(extracted, dict):
            domains = extracted.get("domains")
            urls = extracted.get("urls")

            if isinstance(domains, list):
                for d in domains:
                    _add_domain(d)
            else:
                _add_domain(domains)

            if isinstance(urls, list):
                for u in urls:
                    _add_url(u)
            else:
                _add_url(urls)

    async def _scan_corpus_indices(self, query: str, query_type: str, result: SonarResult, limit: int):
        """Scan the CYMONIDES corpus indices (cymonides-3/home, cymonides-2/raw) for relevant docs."""
        es = await self._get_client()

        corpus_indices = self._get_corpus_indices()
        if not corpus_indices:
            return

        email = query.lower().strip() if query_type == "email" else None
        phone_digits = re.sub(r"\D", "", query) if query_type == "phone" else None

        # Keep corpus scans bounded; these indices can be large/full-text.
        size_cap = 200
        if query_type in {"domain", "url"}:
            size_cap = 1000
        elif query_type in {"email", "phone"}:
            size_cap = 500

        for index in corpus_indices:
            try:
                if not await es.indices.exists(index=index):
                    continue

                result.indices_scanned.append(index)

                if query_type == "email" and email:
                    q = {
                        "bool": {
                            "should": [
                                {"term": {"extracted_entities.emails.keyword": email}},
                                {"term": {"email.keyword": email}},
                                {
                                    "simple_query_string": {
                                        "query": email,
                                        "fields": ["content", "title", "snippet", "source_url", "url"],
                                        "default_operator": "and",
                                        "lenient": True,
                                    }
                                },
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                elif query_type == "phone" and phone_digits:
                    should = [
                        {"term": {"extracted_entities.phones.keyword": query}},
                        {"term": {"extracted_entities.phones.keyword": phone_digits}},
                        {"term": {"phone.keyword": query}},
                        {"term": {"phone.keyword": phone_digits}},
                    ]
                    if len(phone_digits) >= 7:
                        should.append({"wildcard": {"content": f"*{phone_digits[-7:]}*"}})
                    q = {"bool": {"should": should, "minimum_should_match": 1}}
                elif query_type == "domain":
                    dom = query.lower().strip()
                    q = {
                        "bool": {
                            "should": [
                                {"term": {"source_domain.keyword": dom}},
                                {"term": {"domain.keyword": dom}},
                                {"term": {"extracted_entities.domains.keyword": dom}},
                                {"wildcard": {"source_url.keyword": f"*{dom}*"}},
                                {"wildcard": {"url.keyword": f"*{dom}*"}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                elif query_type == "url":
                    url = query.strip()
                    q = {
                        "bool": {
                            "should": [
                                {"term": {"source_url.keyword": url}},
                                {"term": {"url.keyword": url}},
                                {"wildcard": {"source_url.keyword": f"*{url}*"}},
                                {"wildcard": {"url.keyword": f"*{url}*"}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                else:
                    q = {
                        "simple_query_string": {
                            "query": query,
                            "fields": [
                                "title",
                                "content",
                                "snippet",
                                "keywords",
                                "source_url",
                                "source_domain",
                                "url",
                                "domain",
                                "wdc_entity_name",
                            ],
                            "default_operator": "and",
                            "lenient": True,
                        }
                    }

                resp = await es.search(
                    index=index,
                    query=q,
                    size=min(limit, size_cap),
                    track_total_hits=False,
                    _source=True,
                )

                for hit in resp.get("hits", {}).get("hits", []):
                    src = hit.get("_source", {}) or {}
                    sonar_hit = SonarHit(
                        index=index,
                        doc_id=hit.get("_id", ""),
                        score=hit.get("_score") or 0,
                        source=src,
                        match_type="corpus",
                    )
                    self._extract_domains_urls_from_corpus_source(src, result, sonar_hit)
                    result.hits.append(sonar_hit)
                    result.total_hits += 1

            except Exception as e:
                logger.warning(f"Error scanning {index}: {e}")

    async def _scan_entity_domain(self, domain: str, result: SonarResult, limit: int):
        """Scan entity mentions index for domain references."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="entity-mentions"):
                return

            result.indices_scanned.append("entity-mentions")

            resp = await es.search(
                index="entity-mentions",
                query={"match": {"source_domain": domain}},
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="entity-mentions",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="mention"
                )

                if "url" in src:
                    result.add_url(src["url"])
                    sonar_hit.url = src["url"]

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning entity-mentions: {e}")

    async def _scan_ownership(self, name: str, result: SonarResult, limit: int):
        """Scan OpenOwnership for beneficial ownership records."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="openownership"):
                return

            result.indices_scanned.append("openownership")

            query = {
                "bool": {
                    "should": [
                        {"match_phrase": {"interested_party.name": name}},
                        {"match_phrase": {"subject.name": name}},
                        {"match": {"interested_party.name": {"query": name, "fuzziness": "AUTO"}}},
                    ],
                    "minimum_should_match": 1
                }
            }

            resp = await es.search(
                index="openownership",
                query=query,
                size=min(limit, 1000),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="openownership",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="ownership"
                )

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning openownership: {e}")

    async def _scan_uk_companies(self, name: str, result: SonarResult, limit: int):
        """Scan UK Companies House indices."""
        es = await self._get_client()

        try:
            if not await es.indices.exists(index="uk_ccod"):
                return

            result.indices_scanned.append("uk_ccod")

            query = {
                "bool": {
                    "should": [
                        {"match_phrase": {"company_name": name}},
                        {"match": {"company_name": {"query": name, "fuzziness": "AUTO"}}},
                    ],
                    "minimum_should_match": 1
                }
            }

            resp = await es.search(
                index="uk_ccod",
                query=query,
                size=min(limit, 500),
                _source=True
            )

            for hit in resp["hits"]["hits"]:
                src = hit["_source"]
                sonar_hit = SonarHit(
                    index="uk_ccod",
                    doc_id=hit["_id"],
                    score=hit["_score"] or 0,
                    source=src,
                    match_type="uk_company"
                )

                # UK company numbers can lead to Companies House URLs
                if "company_number" in src:
                    ch_url = f"https://find-and-update.company-information.service.gov.uk/company/{src['company_number']}"
                    result.add_url(ch_url)
                    sonar_hit.url = ch_url

                result.hits.append(sonar_hit)
                result.total_hits += 1

        except Exception as e:
            logger.warning(f"Error scanning uk_ccod: {e}")


# Quick test
if __name__ == "__main__":
    async def test():
        sonar = Sonar()

        print("Testing domain scan...")
        result = await sonar.scan_all("portofino.com")
        print(f"Found {len(result.domains)} domains, {result.total_hits} hits")
        print(f"Indices scanned: {result.indices_scanned}")

        print("\nTesting entity scan...")
        result = await sonar.scan_all("John Smith")
        print(f"Found {len(result.domains)} domains, {result.total_hits} hits")

        await sonar.close()

    asyncio.run(test())
