#!/usr/bin/env python3
"""
Unified Discovery Engine

COMPREHENSIVE discovery service integrating ALL available data sources:

LEVEL 1: Domain Set Discovery (find domains)
- LinkedIn Company Index (2.85M companies → instant domain lookup)
- CC Web Graph (90M domains, 166M+ edges → backlinks/outlinks)
- InDom Search (search engine aggregation)
- AllDomain Discovery (Firecrawl, sitemaps, subdomain enumeration)

LEVEL 2: Domain Enrichment
- LinkedIn company data (industry, size, authority)
- CC Web Graph (backlink/outlink counts)
- Majestic SEO (related sites, trust flow, citation flow)
- Technology stack detection
- WHOIS patterns

DETERMINISTIC ROUTING:
Given "what we have" + "what we want" → optimal discovery path
"""

import asyncio
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

# Elasticsearch connection
ES_HOST = "http://localhost:9200"
es = Elasticsearch([ES_HOST])


class InputType(Enum):
    """What we have"""
    COMPANY_NAME = "company_name"
    DOMAIN = "domain"
    PERSON_NAME = "person_name"
    KEYWORD = "keyword"
    INDUSTRY = "industry"
    LINKEDIN_URL = "linkedin_url"
    WEBSITE_URL = "website_url"


class OutputType(Enum):
    """What we want"""
    DOMAIN = "domain"
    DOMAINS = "domains"  # Multiple domains
    COMPANY_INFO = "company_info"
    BACKLINKS = "backlinks"
    OUTLINKS = "outlinks"
    SIMILAR_SITES = "similar_sites"
    OFFICERS = "officers"
    SUBSIDIARIES = "subsidiaries"


@dataclass
class DiscoveryResult:
    """Single discovery result"""
    domain: str
    url: Optional[str] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    score: float = 0.0
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResponse:
    """Discovery response with results and diagnostics"""
    query: str
    input_type: str
    output_type: str
    results: List[DiscoveryResult]
    total_found: int
    sources_used: List[str]
    elapsed_ms: int = 0
    route_used: str = ""


# =============================================================================
# DISCOVERY ROUTES - Deterministic path selection
# =============================================================================

# Country codes supported by Country Engines (direct registry APIs or batch-imported data)
COUNTRY_ENGINE_JURISDICTIONS = {
    "AT": "austria",      # FirmenABC (batch imported)
    "DE": "germany",      # Unternehmensregister API
    "CH": "switzerland",  # Zefix
    "NL": "netherlands",  # KvK
    "FR": "france",       # SIRENE
    "BE": "belgium",      # KBO
    "DK": "denmark",      # Virk
    "NO": "norway",       # Brreg
    "SE": "sweden",       # Verksamt
    "FI": "finland",      # PRH
    "IE": "ireland",      # CRO
    "UY": "uruguay",      # Uruguay registry
}

DISCOVERY_ROUTES = {
    "company_name": {
        "to_domain": [
            # Priority 0: Country-specific data (free, instant, high quality)
            {"method": "country_profile_es_lookup", "cost": 0, "speed": "instant", "priority": 0},
            {"method": "linkedin_es_lookup", "cost": 0, "speed": "instant", "priority": 1},
            {"method": "google_search", "cost": 0.01, "speed": "fast", "priority": 2},
            {"method": "brave_search", "cost": 0.01, "speed": "fast", "priority": 3},
        ],
        "to_domains": [
            {"method": "country_profile_es_lookup", "cost": 0, "speed": "instant", "priority": 0},
            {"method": "linkedin_es_search", "cost": 0, "speed": "instant", "priority": 1},
            {"method": "indom_search", "cost": 0.01, "speed": "medium", "priority": 2},
        ],
        "to_company_info": [
            {"method": "country_profile_es_lookup", "cost": 0, "speed": "instant", "priority": 0},
            {"method": "linkedin_es_lookup", "cost": 0, "speed": "instant", "priority": 1},
        ],
    },
    "domain": {
        "to_backlinks": [
            {"method": "cc_web_graph_backlinks", "cost": 0, "speed": "instant", "priority": 1},
            {"method": "majestic_backlinks", "cost": 0.05, "speed": "fast", "priority": 2},
        ],
        "to_outlinks": [
            {"method": "cc_web_graph_outlinks", "cost": 0, "speed": "instant", "priority": 1},
            {"method": "firecrawl_live", "cost": 0.01, "speed": "medium", "priority": 2},
        ],
        "to_similar_sites": [
            {"method": "majestic_related_sites", "cost": 0.05, "speed": "fast", "priority": 1},
            {"method": "cc_web_graph_neighbors", "cost": 0, "speed": "instant", "priority": 2},
        ],
        "to_company_info": [
            {"method": "linkedin_es_by_domain", "cost": 0, "speed": "instant", "priority": 1},
        ],
    },
    "keyword": {
        "to_domains": [
            {"method": "indom_search", "cost": 0.01, "speed": "medium", "priority": 1},
            {"method": "brave_search", "cost": 0.01, "speed": "fast", "priority": 2},
            {"method": "google_search", "cost": 0.01, "speed": "fast", "priority": 3},
        ],
    },
    "industry": {
        "to_domains": [
            {"method": "linkedin_es_by_industry", "cost": 0, "speed": "instant", "priority": 1},
        ],
    },
}


# =============================================================================
# ELASTICSEARCH LINKEDIN INDEX
# =============================================================================

async def linkedin_es_lookup(company_name: str, limit: int = 10) -> List[DiscoveryResult]:
    """
    Instant company→domain lookup from Elasticsearch LinkedIn index
    Index: affiliate_linkedin_companies (2.85M companies)
    """
    try:
        result = es.search(
            index="affiliate_linkedin_companies",
            body={
                "query": {
                    "match": {
                        "company_name": {
                            "query": company_name,
                            "fuzziness": "AUTO"
                        }
                    }
                },
                "size": limit,
                "_source": ["domain", "company_name", "industry", "linkedin_url", "website_url"]
            }
        )

        results = []
        for hit in result['hits']['hits']:
            src = hit['_source']
            results.append(DiscoveryResult(
                domain=src.get('domain', ''),
                company_name=src.get('company_name'),
                industry=src.get('industry'),
                linkedin_url=src.get('linkedin_url'),
                website_url=src.get('website_url'),
                score=hit['_score'],
                source="linkedin_es",
                metadata={"es_score": hit['_score']}
            ))

        logger.info(f"[LinkedIn ES] Found {len(results)} companies for '{company_name}'")
        return results

    except Exception as e:
        logger.error(f"[LinkedIn ES] Lookup error: {e}")
        return []


async def linkedin_es_by_domain(domain: str) -> Optional[DiscoveryResult]:
    """
    Instant domain→company lookup from Elasticsearch
    """
    try:
        # Normalize domain
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]

        result = es.search(
            index="affiliate_linkedin_companies",
            body={
                "query": {
                    "term": {"domain": domain}
                },
                "size": 1,
                "_source": ["domain", "company_name", "industry", "linkedin_url", "website_url"]
            }
        )

        if result['hits']['total']['value'] > 0:
            src = result['hits']['hits'][0]['_source']
            return DiscoveryResult(
                domain=src.get('domain', ''),
                company_name=src.get('company_name'),
                industry=src.get('industry'),
                linkedin_url=src.get('linkedin_url'),
                website_url=src.get('website_url'),
                score=1.0,
                source="linkedin_es"
            )

        return None

    except Exception as e:
        logger.error(f"[LinkedIn ES] Domain lookup error: {e}")
        return None


async def linkedin_es_by_industry(industry: str, limit: int = 100) -> List[DiscoveryResult]:
    """
    Find companies by industry
    """
    try:
        result = es.search(
            index="affiliate_linkedin_companies",
            body={
                "query": {
                    "match": {"industry": industry}
                },
                "size": limit,
                "_source": ["domain", "company_name", "industry", "linkedin_url", "website_url"]
            }
        )

        results = []
        for hit in result['hits']['hits']:
            src = hit['_source']
            results.append(DiscoveryResult(
                domain=src.get('domain', ''),
                company_name=src.get('company_name'),
                industry=src.get('industry'),
                linkedin_url=src.get('linkedin_url'),
                website_url=src.get('website_url'),
                score=hit['_score'],
                source="linkedin_es"
            ))

        return results

    except Exception as e:
        logger.error(f"[LinkedIn ES] Industry search error: {e}")
        return []


# =============================================================================
# COUNTRY PROFILE ES INDEX (Batch-imported country registry data)
# =============================================================================

async def country_profile_es_lookup(
    company_name: str,
    jurisdiction: Optional[str] = None,
    limit: int = 10
) -> List[DiscoveryResult]:
    """
    Lookup company→domain from batch-imported country registry data.

    This index contains data from:
    - Austria: FirmenABC (900K companies)
    - Switzerland: Zefix
    - Netherlands: KvK
    - etc.

    Priority over LinkedIn because:
    - FREE (no API cost)
    - Higher quality (official registry data)
    - Instant (local ES query)

    Args:
        company_name: Company name to search
        jurisdiction: Optional 2-letter country code (AT, DE, CH, etc.)
        limit: Max results to return

    Returns:
        List of DiscoveryResult with domain data
    """
    try:
        # Build query
        must_clauses = [
            {
                "match": {
                    "company_name": {
                        "query": company_name,
                        "fuzziness": "AUTO",
                        "operator": "and"
                    }
                }
            }
        ]

        # Filter by jurisdiction if provided
        if jurisdiction:
            # Normalize jurisdiction to uppercase
            jurisdiction = jurisdiction.upper()
            must_clauses.append({"term": {"country": jurisdiction}})

        result = es.search(
            index="company_profiles",
            body={
                "query": {
                    "bool": {
                        "must": must_clauses,
                        # Only return results that have a domain
                        "filter": {"exists": {"field": "domain"}}
                    }
                },
                "size": limit,
                "_source": ["company_name", "domain", "country", "industry", "source_flags"]
            }
        )

        results = []
        for hit in result['hits']['hits']:
            src = hit['_source']
            domain = src.get('domain', '')

            # Skip empty domains
            if not domain:
                continue

            results.append(DiscoveryResult(
                domain=domain,
                company_name=src.get('company_name'),
                industry=src.get('industry'),
                score=hit['_score'],
                source=f"country_registry_{src.get('country', 'unknown')}",
                metadata={
                    "country": src.get('country'),
                    "source_flags": src.get('source_flags', []),
                    "es_score": hit['_score']
                }
            ))

        if results:
            countries = set(r.metadata.get('country', '') for r in results)
            logger.info(f"[Country Profile] Found {len(results)} companies for '{company_name}' (jurisdictions: {countries})")

        return results

    except Exception as e:
        # Index may not exist or have issues - silently fallback
        logger.debug(f"[Country Profile] Lookup skipped or failed: {e}")
        return []


async def country_profile_by_domain(domain: str) -> Optional[DiscoveryResult]:
    """
    Reverse lookup: domain → company info from country registries.

    Args:
        domain: Domain to look up

    Returns:
        DiscoveryResult with company info if found
    """
    try:
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]

        result = es.search(
            index="company_profiles",
            body={
                "query": {"term": {"domain": domain}},
                "size": 1,
                "_source": ["company_name", "domain", "country", "industry", "source_flags"]
            }
        )

        if result['hits']['total']['value'] > 0:
            src = result['hits']['hits'][0]['_source']
            return DiscoveryResult(
                domain=src.get('domain', ''),
                company_name=src.get('company_name'),
                industry=src.get('industry'),
                score=1.0,
                source=f"country_registry_{src.get('country', 'unknown')}",
                metadata={
                    "country": src.get('country'),
                    "source_flags": src.get('source_flags', [])
                }
            )

        return None

    except Exception as e:
        logger.debug(f"[Country Profile] Domain lookup failed: {e}")
        return None


# =============================================================================
# CC WEB GRAPH (90M domains, 166M+ edges)
# =============================================================================

async def cc_web_graph_get_vertex_id(domain: str) -> Optional[int]:
    """
    Get CC Web Graph vertex ID for a domain
    Index: cymonides_cc_domain_vertices (90M domains)
    """
    try:
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]

        result = es.search(
            index="cymonides_cc_domain_vertices",
            body={
                "query": {"term": {"domain": domain}},
                "size": 1,
                "_source": ["vertex_id", "domain", "count"]
            }
        )

        if result['hits']['total']['value'] > 0:
            return result['hits']['hits'][0]['_source']['vertex_id']

        return None

    except Exception as e:
        logger.error(f"[CC Graph] Vertex lookup error: {e}")
        return None


async def cc_web_graph_backlinks(domain: str, limit: int = 100, min_link_count: int = 1) -> List[DiscoveryResult]:
    """
    Find domains linking TO this domain (backlinks)
    Index: cymonides_cc_domain_edges (166M+ edges)
    """
    try:
        # Get vertex ID
        vertex_id = await cc_web_graph_get_vertex_id(domain)
        if not vertex_id:
            logger.warning(f"[CC Graph] Domain not found: {domain}")
            return []

        # Find edges where target_vertex_id = our domain
        result = es.search(
            index="cymonides_cc_domain_edges",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"target_vertex_id": vertex_id}},
                            {"range": {"link_count": {"gte": min_link_count}}}
                        ]
                    }
                },
                "size": limit,
                "sort": [{"link_count": {"order": "desc"}}],
                "_source": ["source_vertex_id", "link_count"]
            }
        )

        # Resolve vertex IDs to domains
        results = []
        vertex_ids = [hit['_source']['source_vertex_id'] for hit in result['hits']['hits']]
        link_counts = {hit['_source']['source_vertex_id']: hit['_source']['link_count']
                       for hit in result['hits']['hits']}

        if vertex_ids:
            # Batch lookup domains
            domain_result = es.search(
                index="cymonides_cc_domain_vertices",
                body={
                    "query": {"terms": {"vertex_id": vertex_ids}},
                    "size": len(vertex_ids),
                    "_source": ["vertex_id", "domain"]
                }
            )

            for hit in domain_result['hits']['hits']:
                src = hit['_source']
                vid = src['vertex_id']
                results.append(DiscoveryResult(
                    domain=src['domain'],
                    url=f"https://{src['domain']}",
                    score=link_counts.get(vid, 1) / 100,  # Normalize score
                    source="cc_web_graph",
                    metadata={
                        "link_count": link_counts.get(vid, 1),
                        "relationship": "backlink",
                        "vertex_id": vid
                    }
                ))

        # Sort by link count
        results.sort(key=lambda r: r.metadata.get('link_count', 0), reverse=True)
        logger.info(f"[CC Graph] Found {len(results)} backlinks for {domain}")
        return results

    except Exception as e:
        logger.error(f"[CC Graph] Backlinks error: {e}")
        return []


async def cc_web_graph_outlinks(domain: str, limit: int = 100, min_link_count: int = 1) -> List[DiscoveryResult]:
    """
    Find domains linked FROM this domain (outlinks)
    """
    try:
        vertex_id = await cc_web_graph_get_vertex_id(domain)
        if not vertex_id:
            return []

        result = es.search(
            index="cymonides_cc_domain_edges",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"source_vertex_id": vertex_id}},
                            {"range": {"link_count": {"gte": min_link_count}}}
                        ]
                    }
                },
                "size": limit,
                "sort": [{"link_count": {"order": "desc"}}],
                "_source": ["target_vertex_id", "link_count"]
            }
        )

        results = []
        vertex_ids = [hit['_source']['target_vertex_id'] for hit in result['hits']['hits']]
        link_counts = {hit['_source']['target_vertex_id']: hit['_source']['link_count']
                       for hit in result['hits']['hits']}

        if vertex_ids:
            domain_result = es.search(
                index="cymonides_cc_domain_vertices",
                body={
                    "query": {"terms": {"vertex_id": vertex_ids}},
                    "size": len(vertex_ids),
                    "_source": ["vertex_id", "domain"]
                }
            )

            for hit in domain_result['hits']['hits']:
                src = hit['_source']
                vid = src['vertex_id']
                results.append(DiscoveryResult(
                    domain=src['domain'],
                    url=f"https://{src['domain']}",
                    score=link_counts.get(vid, 1) / 100,
                    source="cc_web_graph",
                    metadata={
                        "link_count": link_counts.get(vid, 1),
                        "relationship": "outlink",
                        "vertex_id": vid
                    }
                ))

        results.sort(key=lambda r: r.metadata.get('link_count', 0), reverse=True)
        logger.info(f"[CC Graph] Found {len(results)} outlinks for {domain}")
        return results

    except Exception as e:
        logger.error(f"[CC Graph] Outlinks error: {e}")
        return []


async def cc_web_graph_neighbors(domain: str, limit: int = 50) -> List[DiscoveryResult]:
    """
    Find neighboring domains (both backlinks AND outlinks)
    Useful for finding related/similar sites
    """
    backlinks = await cc_web_graph_backlinks(domain, limit=limit)
    outlinks = await cc_web_graph_outlinks(domain, limit=limit)

    # Combine and deduplicate
    seen: Set[str] = set()
    results = []

    for r in backlinks + outlinks:
        if r.domain not in seen:
            seen.add(r.domain)
            results.append(r)

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


# =============================================================================
# DETERMINISTIC DISCOVERY ROUTER
# =============================================================================

async def discover(
    query: str,
    input_type: InputType,
    output_type: OutputType,
    limit: int = 50,
    use_fallbacks: bool = True,
    **kwargs
) -> DiscoveryResponse:
    """
    Main discovery function - routes to optimal method based on input/output types

    Examples:
        discover("Tesla", InputType.COMPANY_NAME, OutputType.DOMAIN)
        discover("tesla.com", InputType.DOMAIN, OutputType.BACKLINKS)
        discover("Automotive", InputType.INDUSTRY, OutputType.DOMAINS)
    """
    import time
    start_time = time.time()

    input_key = input_type.value
    output_key = f"to_{output_type.value}"

    # Get routes for this input→output combination
    routes = DISCOVERY_ROUTES.get(input_key, {}).get(output_key, [])

    if not routes:
        logger.warning(f"[Discovery] No route for {input_key} → {output_key}")
        return DiscoveryResponse(
            query=query,
            input_type=input_key,
            output_type=output_type.value,
            results=[],
            total_found=0,
            sources_used=[],
            route_used="none"
        )

    # Sort by priority
    routes = sorted(routes, key=lambda r: r['priority'])

    results: List[DiscoveryResult] = []
    sources_used: List[str] = []
    route_used = ""

    for route in routes:
        method_name = route['method']
        method_results: List[DiscoveryResult] = []

        try:
            # Call the appropriate method
            if method_name == "country_profile_es_lookup":
                # Country profile lookup - supports optional jurisdiction kwarg
                jurisdiction = kwargs.get('jurisdiction')
                method_results = await country_profile_es_lookup(query, jurisdiction, limit)
            elif method_name == "linkedin_es_lookup":
                method_results = await linkedin_es_lookup(query, limit)
            elif method_name == "linkedin_es_search":
                method_results = await linkedin_es_lookup(query, limit)
            elif method_name == "linkedin_es_by_domain":
                result = await linkedin_es_by_domain(query)
                method_results = [result] if result else []
            elif method_name == "linkedin_es_by_industry":
                method_results = await linkedin_es_by_industry(query, limit)
            elif method_name == "cc_web_graph_backlinks":
                method_results = await cc_web_graph_backlinks(query, limit, kwargs.get('min_link_count', 1))
            elif method_name == "cc_web_graph_outlinks":
                method_results = await cc_web_graph_outlinks(query, limit, kwargs.get('min_link_count', 1))
            elif method_name == "cc_web_graph_neighbors":
                method_results = await cc_web_graph_neighbors(query, limit)
            elif method_name == "majestic_related_sites":
                # TODO: Implement Majestic integration
                method_results = []
            elif method_name == "majestic_backlinks":
                # TODO: Implement Majestic integration
                method_results = []
            elif method_name == "firecrawl_live":
                # TODO: Integrate with Firecrawl
                method_results = []
            elif method_name == "indom_search":
                # TODO: Integrate with InDom
                method_results = []
            elif method_name == "google_search":
                # TODO: Integrate with Google CSE
                method_results = []
            elif method_name == "brave_search":
                # TODO: Integrate with Brave Search
                method_results = []
            else:
                logger.warning(f"[Discovery] Unknown method: {method_name}")
                continue

            # Only use these results if we got something
            if method_results:
                results = method_results  # Use this method's results
                sources_used.append(method_name)
                route_used = method_name
                break  # Stop at first successful method (fallback logic: try until one works)

        except Exception as e:
            logger.error(f"[Discovery] Method {method_name} failed: {e}")
            continue

    elapsed_ms = int((time.time() - start_time) * 1000)

    return DiscoveryResponse(
        query=query,
        input_type=input_key,
        output_type=output_type.value,
        results=results[:limit],
        total_found=len(results),
        sources_used=sources_used,
        elapsed_ms=elapsed_ms,
        route_used=route_used
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def company_to_domain(
    company_name: str,
    jurisdiction: Optional[str] = None
) -> Optional[str]:
    """
    Quick company name → domain lookup.

    Tries country-specific registries first (if jurisdiction provided or found),
    then falls back to LinkedIn ES.

    Args:
        company_name: Company name to look up
        jurisdiction: Optional 2-letter country code (AT, DE, CH, etc.)

    Returns:
        Domain string if found, None otherwise
    """
    # Priority 0: Try country profile lookup first
    country_results = await country_profile_es_lookup(company_name, jurisdiction, limit=1)
    if country_results and country_results[0].domain:
        return country_results[0].domain

    # Priority 1: Fall back to LinkedIn ES
    linkedin_results = await linkedin_es_lookup(company_name, limit=1)
    return linkedin_results[0].domain if linkedin_results else None


async def domain_to_company(domain: str) -> Optional[Dict[str, Any]]:
    """
    Quick domain → company info lookup.

    Tries country registries first, then LinkedIn ES.
    """
    # Try country profile first
    country_result = await country_profile_by_domain(domain)
    if country_result:
        return {
            "company_name": country_result.company_name,
            "industry": country_result.industry,
            "source": country_result.source,
            "country": country_result.metadata.get("country")
        }

    # Fall back to LinkedIn
    result = await linkedin_es_by_domain(domain)
    if result:
        return {
            "company_name": result.company_name,
            "industry": result.industry,
            "linkedin_url": result.linkedin_url,
            "website_url": result.website_url
        }
    return None


async def find_backlinks(domain: str, limit: int = 100) -> List[str]:
    """Quick backlink lookup - returns list of domains"""
    results = await cc_web_graph_backlinks(domain, limit)
    return [r.domain for r in results]


async def find_outlinks(domain: str, limit: int = 100) -> List[str]:
    """Quick outlink lookup - returns list of domains"""
    results = await cc_web_graph_outlinks(domain, limit)
    return [r.domain for r in results]


async def find_similar_domains(domain: str, limit: int = 50) -> List[str]:
    """Find similar/related domains based on link graph"""
    results = await cc_web_graph_neighbors(domain, limit)
    return [r.domain for r in results]


# =============================================================================
# HOST GRAPH ES (421M HOST-LEVEL EDGES)
# =============================================================================

def _reverse_domain(domain: str) -> str:
    """Convert domain to reversed notation for Host Graph ES queries."""
    parts = domain.lower().strip().split('.')
    return '.'.join(reversed(parts))


def _unreverse_domain(reversed_domain: str) -> str:
    """Convert reversed domain back to normal notation."""
    parts = reversed_domain.split('.')
    return '.'.join(reversed(parts))


async def host_graph_backlinks(
    domain: str,
    limit: int = 100,
    include_subdomains: bool = True
) -> List[DiscoveryResult]:
    """
    Find hosts linking TO this domain using Host Graph ES (421M edges).

    INSTANT queries (~50ms) against pre-indexed host-level edges.
    Index: cc_web_graph_host_edges

    Args:
        domain: Target domain (e.g., "bbc.com")
        limit: Maximum results (default 100)
        include_subdomains: If True, includes links to *.domain (e.g., www.bbc.com)

    Returns:
        List of DiscoveryResult objects with source domains
    """
    try:
        reversed_domain = _reverse_domain(domain)

        # Build query - exact match or prefix for subdomains
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

        result = es.search(
            index="cc_web_graph_host_edges",
            body={
                "query": query,
                "size": limit,
                "_source": ["source", "target", "source_id", "target_id", "collection"]
            }
        )

        results = []
        for hit in result['hits']['hits']:
            src = hit['_source']
            source_domain = _unreverse_domain(src['source'])
            target_domain = _unreverse_domain(src['target'])

            results.append(DiscoveryResult(
                domain=source_domain,
                url=f"https://{source_domain}",
                score=1.0,
                source="host_graph_es",
                metadata={
                    "target_host": target_domain,
                    "source_id": src.get('source_id'),
                    "target_id": src.get('target_id'),
                    "collection": src.get('collection'),
                    "relationship": "backlink",
                    "level": "host"
                }
            ))

        logger.info(f"[Host Graph ES] Found {len(results)} host-level backlinks for {domain}")
        return results

    except Exception as e:
        logger.error(f"[Host Graph ES] Backlinks error: {e}")
        return []


async def host_graph_outlinks(
    domain: str,
    limit: int = 100,
    include_subdomains: bool = True
) -> List[DiscoveryResult]:
    """
    Find hosts that this domain links TO using Host Graph ES (421M edges).

    INSTANT queries (~50ms) against pre-indexed host-level edges.

    Args:
        domain: Source domain (e.g., "bbc.com")
        limit: Maximum results
        include_subdomains: If True, includes links from *.domain

    Returns:
        List of DiscoveryResult objects with target domains
    """
    try:
        reversed_domain = _reverse_domain(domain)

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

        result = es.search(
            index="cc_web_graph_host_edges",
            body={
                "query": query,
                "size": limit,
                "_source": ["source", "target", "source_id", "target_id", "collection"]
            }
        )

        results = []
        for hit in result['hits']['hits']:
            src = hit['_source']
            source_domain = _unreverse_domain(src['source'])
            target_domain = _unreverse_domain(src['target'])

            results.append(DiscoveryResult(
                domain=target_domain,
                url=f"https://{target_domain}",
                score=1.0,
                source="host_graph_es",
                metadata={
                    "source_host": source_domain,
                    "source_id": src.get('source_id'),
                    "target_id": src.get('target_id'),
                    "collection": src.get('collection'),
                    "relationship": "outlink",
                    "level": "host"
                }
            ))

        logger.info(f"[Host Graph ES] Found {len(results)} host-level outlinks for {domain}")
        return results

    except Exception as e:
        logger.error(f"[Host Graph ES] Outlinks error: {e}")
        return []


async def host_graph_count(domain: str, include_subdomains: bool = True) -> Dict[str, int]:
    """
    Count backlinks and outlinks in Host Graph ES (421M edges).

    Args:
        domain: Target domain
        include_subdomains: Include *.domain

    Returns:
        Dict with backlink_count and outlink_count
    """
    try:
        reversed_domain = _reverse_domain(domain)

        if include_subdomains:
            backlink_query = {
                "bool": {
                    "should": [
                        {"term": {"target": reversed_domain}},
                        {"prefix": {"target": f"{reversed_domain}."}}
                    ],
                    "minimum_should_match": 1
                }
            }
            outlink_query = {
                "bool": {
                    "should": [
                        {"term": {"source": reversed_domain}},
                        {"prefix": {"source": f"{reversed_domain}."}}
                    ],
                    "minimum_should_match": 1
                }
            }
        else:
            backlink_query = {"term": {"target": reversed_domain}}
            outlink_query = {"term": {"source": reversed_domain}}

        backlink_count = es.count(index="cc_web_graph_host_edges", body={"query": backlink_query})['count']
        outlink_count = es.count(index="cc_web_graph_host_edges", body={"query": outlink_query})['count']

        return {
            "backlink_count": backlink_count,
            "outlink_count": outlink_count,
            "total": backlink_count + outlink_count
        }

    except Exception as e:
        logger.error(f"[Host Graph ES] Count error: {e}")
        return {"backlink_count": 0, "outlink_count": 0, "total": 0}


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        print("\n" + "="*60)
        print("UNIFIED DISCOVERY ENGINE TEST")
        print("="*60)

        # Test 1: Company → Domain
        print("\n[Test 1] Company → Domain: 'Tesla'")
        results = await linkedin_es_lookup("Tesla", limit=5)
        for r in results:
            print(f"  {r.company_name} → {r.domain} (industry: {r.industry})")

        # Test 2: Domain → Company
        print("\n[Test 2] Domain → Company: 'tesla.com'")
        result = await linkedin_es_by_domain("tesla.com")
        if result:
            print(f"  {result.domain} → {result.company_name}")
            print(f"  Industry: {result.industry}")
            print(f"  LinkedIn: {result.linkedin_url}")

        # Test 3: Domain → Backlinks
        print("\n[Test 3] Domain → Backlinks: 'sebgroup.com'")
        backlinks = await cc_web_graph_backlinks("sebgroup.com", limit=10)
        print(f"  Found {len(backlinks)} backlinks:")
        for r in backlinks[:5]:
            print(f"    {r.domain} ({r.metadata.get('link_count', 0)} links)")

        # Test 4: Domain → Outlinks
        print("\n[Test 4] Domain → Outlinks: 'sebgroup.com'")
        outlinks = await cc_web_graph_outlinks("sebgroup.com", limit=10)
        print(f"  Found {len(outlinks)} outlinks:")
        for r in outlinks[:5]:
            print(f"    {r.domain} ({r.metadata.get('link_count', 0)} links)")

        # Test 5: Full discovery router
        print("\n[Test 5] Discovery Router: company_name → domain")
        response = await discover("Microsoft", InputType.COMPANY_NAME, OutputType.DOMAIN)
        print(f"  Query: {response.query}")
        print(f"  Route used: {response.route_used}")
        print(f"  Elapsed: {response.elapsed_ms}ms")
        print(f"  Results: {response.total_found}")
        for r in response.results[:3]:
            print(f"    {r.company_name} → {r.domain}")

        print("\n" + "="*60)
        print("TEST COMPLETE")
        print("="*60)

    asyncio.run(test())
