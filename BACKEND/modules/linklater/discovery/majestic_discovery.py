#!/usr/bin/env python3
"""
Majestic Discovery Module

Find related/competitor domains using Majestic's co-citation analysis.

Discovery Methods:
1. GetRelatedSites: Find domains sharing backlinks (co-citation neighbors)
2. GetHostedDomains: Find domains co-hosted on same IP/subnet (infrastructure clustering)
3. GetRefDomains: Find unique referring domains linking to target

Use Cases:
- Find competitors: "Who else is linked from sites that link to target?"
- Find affiliates: "What domains are co-hosted with target?"
- Backlink analysis: "Who links to this domain?"
"""

import os
import httpx
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

logger = logging.getLogger(__name__)

# Majestic API configuration
MAJESTIC_API_KEY = os.getenv('MAJESTIC_API_KEY')
MAJESTIC_BASE_URL = "https://api.majestic.com/api/json"


@dataclass
class RelatedSiteResult:
    """Related site discovery result"""
    domain: str
    trust_flow: int = 0
    citation_flow: int = 0
    common_links: int = 0
    source: str = "majestic"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HostedDomainResult:
    """Co-hosted domain discovery result"""
    domain: str
    trust_flow: int = 0
    citation_flow: int = 0
    hosting_type: str = "ip"  # 'ip' or 'subnet'
    source: str = "majestic"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefDomainResult:
    """Referring domain result"""
    domain: str
    trust_flow: int = 0
    citation_flow: int = 0
    backlink_count: int = 0
    first_seen: Optional[str] = None
    source: str = "majestic"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TopicResult:
    """Topical Trust Flow result"""
    topic: str
    trust_flow: int
    citation_flow: int
    topical_trust_flow: int  # Usually same as trust_flow in this context
    source: str = "majestic"


@dataclass
class MajesticDiscoveryResponse:
    """Majestic discovery response"""
    target_domain: str
    method: str
    total_found: int
    results: List[Any]
    elapsed_ms: int = 0
    api_units_used: int = 0


async def majestic_api_call(
    command: str,
    params: Dict[str, Any],
    timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Make a Majestic API call

    Args:
        command: API command (e.g., 'GetRelatedSites')
        params: Command-specific parameters
        timeout: Request timeout in seconds

    Returns:
        API response data
    """
    if not MAJESTIC_API_KEY:
        logger.warning("[Majestic] Missing API key")
        return {"Code": "Error", "ErrorMessage": "Missing API key"}

    full_params = {
        "app_api_key": MAJESTIC_API_KEY,
        "cmd": command,
        **params
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(MAJESTIC_BASE_URL, params=full_params)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"[Majestic {command}] Response code: {data.get('Code')}")
                return data
            else:
                logger.error(f"[Majestic {command}] HTTP {response.status_code}")
                return {"Code": "Error", "ErrorMessage": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"[Majestic {command}] Error: {e}")
            return {"Code": "Error", "ErrorMessage": str(e)}


async def get_related_sites(
    domain: str,
    datasource: str = "fresh",
    max_results: int = 100,
    filter_topic: Optional[str] = None
) -> MajesticDiscoveryResponse:
    """
    Find related/competitor domains via co-citation analysis.

    This discovers domains that share backlinks with the target domain.
    If Sites A and B both link to Target, and Sites A and B also link to Competitor,
    then Competitor is "related" to Target.

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        datasource: 'fresh' (recent 90 days) or 'historic' (5 year index)
        max_results: Maximum related sites to return (max 100)
        filter_topic: Filter by Majestic topic (e.g. "Society/Law")

    Returns:
        MajesticDiscoveryResponse with related domains

    Example:
        response = await get_related_sites("sebgroup.com")
        # Returns competitors like nordea.com, handelsbanken.se, etc.
    """
    import time
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.startswith("http"):
        from urllib.parse import urlparse
        domain = urlparse(domain).netloc

    logger.info(f"[Majestic GetRelatedSites] Finding related sites for: {domain}")

    params = {
        "item": domain,
        "datasource": datasource,
        "MaxResults": min(max_results, 100)
    }
    if filter_topic:
        params["FilterTopic"] = filter_topic

    data = await majestic_api_call("GetRelatedSites", params)

    results: List[RelatedSiteResult] = []

    if data.get("Code") == "OK":
        # Extract from DataTables.Domains.Data (API returns "Domains" not "RelatedSites")
        related_sites = data.get("DataTables", {}).get("Domains", {}).get("Data", [])

        for site in related_sites:
            results.append(RelatedSiteResult(
                domain=site.get("Domain", site.get("Item", "")),
                trust_flow=site.get("TrustFlow", 0),
                citation_flow=site.get("CitationFlow", 0),
                common_links=site.get("Instances", 0),  # Co-citation count
                source="majestic_related_sites",
                metadata={
                    "title": site.get("Title", ""),
                    "unique_contexts": site.get("UniqueContexts", 0),
                    "primary_topic": site.get("PrimaryTopicName", ""),
                    "primary_topic_value": site.get("PrimaryTopicValue", 0)
                }
            ))

        logger.info(f"[Majestic GetRelatedSites] Found {len(results)} related sites for {domain}")
    else:
        error_msg = data.get("ErrorMessage", "Unknown error")
        logger.warning(f"[Majestic GetRelatedSites] API error: {error_msg}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    return MajesticDiscoveryResponse(
        target_domain=domain,
        method="GetRelatedSites",
        total_found=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
        api_units_used=data.get("GlobalVars", {}).get("AnalysisResUnitsUsed", 0)
    )


async def get_hosted_domains(
    domain: str,
    datasource: str = "fresh",
    max_domains: int = 100
) -> MajesticDiscoveryResponse:
    """
    Find domains co-hosted on the same IP or subnet.

    Infrastructure clustering - discovers domains sharing hosting infrastructure.
    Returns two lists: domains on same IP, and domains on same subnet.

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        datasource: 'fresh' or 'historic'
        max_domains: Maximum domains per category (max 100)

    Returns:
        MajesticDiscoveryResponse with co-hosted domains

    Example:
        response = await get_hosted_domains("suspicious-site.com")
        # Returns other domains on same IP - potential affiliated sites
    """
    import time
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]

    logger.info(f"[Majestic GetHostedDomains] Finding co-hosted domains for: {domain}")

    data = await majestic_api_call("GetHostedDomains", {
        "Domain": domain,
        "datasource": datasource,
        "MaxDomains": min(max_domains, 100)
    })

    results: List[HostedDomainResult] = []

    if data.get("Code") == "OK":
        data_tables = data.get("DataTables", {})

        # Domains on same IP
        ip_domains = data_tables.get("DomainsOnIP", {}).get("Data", [])
        for site in ip_domains:
            results.append(HostedDomainResult(
                domain=site.get("Domain", ""),
                trust_flow=site.get("TrustFlow", 0),
                citation_flow=site.get("CitationFlow", 0),
                hosting_type="ip",
                source="majestic_hosted_domains",
                metadata={
                    "ref_domains": site.get("RefDomains", 0),
                    "ext_back_links": site.get("ExtBackLinks", 0),
                    "ip": data.get("RecommendedIP", "")
                }
            ))

        # Domains on same subnet
        subnet_domains = data_tables.get("DomainsOnSubnet", {}).get("Data", [])
        for site in subnet_domains:
            if site.get("Domain") not in [r.domain for r in results]:  # Dedupe
                results.append(HostedDomainResult(
                    domain=site.get("Domain", ""),
                    trust_flow=site.get("TrustFlow", 0),
                    citation_flow=site.get("CitationFlow", 0),
                    hosting_type="subnet",
                    source="majestic_hosted_domains",
                    metadata={
                        "ref_domains": site.get("RefDomains", 0),
                        "ext_back_links": site.get("ExtBackLinks", 0)
                    }
                ))

        logger.info(f"[Majestic GetHostedDomains] Found {len(results)} co-hosted domains for {domain}")
    else:
        error_msg = data.get("ErrorMessage", "Unknown error")
        logger.warning(f"[Majestic GetHostedDomains] API error: {error_msg}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    return MajesticDiscoveryResponse(
        target_domain=domain,
        method="GetHostedDomains",
        total_found=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
        api_units_used=data.get("GlobalVars", {}).get("AnalysisResUnitsUsed", 0)
    )


async def get_ref_domains(
    domain: str,
    datasource: str = "fresh",
    limit: int = 100,
    filter_topic: Optional[str] = None
) -> MajesticDiscoveryResponse:
    """
    Get unique referring domains that link to target.

    Unlike GetBackLinkData (which returns individual backlinks),
    this returns one entry per referring domain with aggregated stats.

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        datasource: 'fresh' or 'historic'
        limit: Maximum referring domains to return (max 1000)
        filter_topic: Filter by Majestic topic

    Returns:
        MajesticDiscoveryResponse with referring domains

    Example:
        response = await get_ref_domains("sebgroup.com")
        # Returns domains linking to SEB: reuters.com, bloomberg.com, etc.
    """
    import time
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]

    logger.info(f"[Majestic GetRefDomains] Finding referring domains for: {domain}")

    params = {
        "item": domain,
        "datasource": datasource,
        "Count": min(limit, 1000)
    }
    if filter_topic:
        params["FilterTopic"] = filter_topic

    data = await majestic_api_call("GetRefDomains", params)

    results: List[RefDomainResult] = []

    if data.get("Code") == "OK":
        ref_domains = data.get("DataTables", {}).get("RefDomains", {}).get("Data", [])

        for ref in ref_domains:
            results.append(RefDomainResult(
                domain=ref.get("Domain", ref.get("RefDomain", "")),
                trust_flow=ref.get("TrustFlow", 0),
                citation_flow=ref.get("CitationFlow", 0),
                backlink_count=ref.get("TotalLinks", ref.get("ExtBackLinks", 0)),
                first_seen=ref.get("FirstIndexedDate"),
                source="majestic_ref_domains",
                metadata={
                    "ref_domain_type": ref.get("RefDomainType", ""),
                    "topical_trust_flow": ref.get("TopicalTrustFlow", [])[:3] if ref.get("TopicalTrustFlow") else []
                }
            ))

        logger.info(f"[Majestic GetRefDomains] Found {len(results)} referring domains for {domain}")
    else:
        error_msg = data.get("ErrorMessage", "Unknown error")
        logger.warning(f"[Majestic GetRefDomains] API error: {error_msg}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    return MajesticDiscoveryResponse(
        target_domain=domain,
        method="GetRefDomains",
        total_found=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
        api_units_used=data.get("GlobalVars", {}).get("AnalysisResUnitsUsed", 0)
    )


@dataclass
class BacklinkResult:
    """Individual backlink result with anchor text"""
    source_url: str
    target_url: str
    anchor_text: str = ""
    trust_flow: int = 0
    citation_flow: int = 0
    source_domain: str = ""
    source_tld: str = ""
    first_seen: Optional[str] = None
    source: str = "majestic"
    metadata: Dict[str, Any] = field(default_factory=dict)


async def get_backlink_data(
    domain: str,
    datasource: str = "fresh",
    limit: int = 100,
    mode: int = 0,
    filter_topic: Optional[str] = None
) -> MajesticDiscoveryResponse:
    """
    Get individual backlinks with anchor text from Majestic.

    This is the key function for page-level backlink discovery with anchor text.
    Unlike GetRefDomains (which returns referring domains), this returns actual
    backlink URLs with full anchor text extraction.

    Args:
        domain: Target domain (e.g., "soax.com")
        datasource: 'fresh' (90 days) or 'historic' (5 years)
        limit: Maximum backlinks to return (max 50000 but API may limit)
        mode: 0 = standard, 1 = only deleted backlinks
        filter_topic: Filter by Majestic topic

    Returns:
        MajesticDiscoveryResponse with BacklinkResult objects containing:
        - source_url: The page linking to target
        - target_url: The URL on target domain being linked to
        - anchor_text: The anchor text of the link
        - trust_flow/citation_flow: Quality metrics
        - source_domain/source_tld: Parsed source domain info

    Example:
        response = await get_backlink_data("soax.com", limit=50)
        for bl in response.results:
            print(f"{bl.source_url} -> {bl.target_url}")
            print(f"  Anchor: '{bl.anchor_text}'")
    """
    import time
    from urllib.parse import urlparse
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.startswith("http"):
        domain = urlparse(domain).netloc

    logger.info(f"[Majestic GetBackLinkData] Finding backlinks for: {domain}")

    params = {
        "item": domain,
        "datasource": datasource,
        "Count": min(limit, 50000),
        "Mode": mode
    }
    if filter_topic:
        params["FilterTopic"] = filter_topic

    data = await majestic_api_call("GetBackLinkData", params)

    results: List[BacklinkResult] = []

    if data.get("Code") == "OK":
        backlinks = data.get("DataTables", {}).get("BackLinks", {}).get("Data", [])

        for bl in backlinks:
            source_url = bl.get("SourceURL", "")
            target_url = bl.get("TargetURL", "")

            # Parse source domain
            try:
                parsed = urlparse(source_url if source_url.startswith("http") else f"http://{source_url}")
                source_domain = parsed.netloc
                source_tld = "." + source_domain.split(".")[-1] if "." in source_domain else ""
            except Exception as e:
                source_domain = source_url.split("/")[0] if "/" in source_url else source_url
                source_tld = ""

            results.append(BacklinkResult(
                source_url=source_url,
                target_url=target_url,
                anchor_text=bl.get("AnchorText", ""),
                trust_flow=bl.get("SourceTrustFlow", 0),
                citation_flow=bl.get("SourceCitationFlow", 0),
                source_domain=source_domain,
                source_tld=source_tld,
                first_seen=bl.get("FirstIndexedDate") or bl.get("FirstSeen"),
                source="majestic_backlinks",
                metadata={
                    "flag_redirect": bl.get("FlagRedirect", False),
                    "flag_frame": bl.get("FlagFrame", False),
                    "flag_nofollow": bl.get("FlagNoFollow", False),
                    "flag_images": bl.get("FlagImages", False),
                    "link_type": bl.get("LinkType", ""),
                    "link_subtype": bl.get("LinkSubType", "")
                }
            ))

        logger.info(f"[Majestic GetBackLinkData] Found {len(results)} backlinks for {domain}")
    else:
        error_msg = data.get("ErrorMessage", "Unknown error")
        logger.warning(f"[Majestic GetBackLinkData] API error: {error_msg}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    return MajesticDiscoveryResponse(
        target_domain=domain,
        method="GetBackLinkData",
        total_found=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
        api_units_used=data.get("GlobalVars", {}).get("AnalysisResUnitsUsed", 0)
    )


async def get_topics(
    domain: str,
    datasource: str = "fresh",
    limit: int = 100
) -> MajesticDiscoveryResponse:
    """
    Get Topical Trust Flow data (GetTopics).

    Returns the topics (categories) associated with the domain,
    ranked by Trust Flow.

    Args:
        domain: Target domain
        datasource: 'fresh' or 'historic'
        limit: Max topics to return

    Returns:
        MajesticDiscoveryResponse with TopicResult objects
    """
    import time
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]

    logger.info(f"[Majestic GetTopics] Finding topics for: {domain}")

    # GetTopics uses 'items' parameter (can be multiple, but we use 1 here)
    data = await majestic_api_call("GetTopics", {
        "items": 1,
        "item0": domain,
        "datasource": datasource
    })

    results: List[TopicResult] = []

    if data.get("Code") == "OK":
        # Structure: DataTables.Topics.Data
        topics = data.get("DataTables", {}).get("Topics", {}).get("Data", [])

        for topic in topics:
            results.append(TopicResult(
                topic=topic.get("Topic", ""),
                trust_flow=topic.get("TrustFlow", 0),
                citation_flow=topic.get("CitationFlow", 0),
                topical_trust_flow=topic.get("TopicalTrustFlow", 0),
                source="majestic_topics"
            ))
            
            if len(results) >= limit:
                break

        logger.info(f"[Majestic GetTopics] Found {len(results)} topics for {domain}")
    else:
        error_msg = data.get("ErrorMessage", "Unknown error")
        logger.warning(f"[Majestic GetTopics] API error: {error_msg}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    return MajesticDiscoveryResponse(
        target_domain=domain,
        method="GetTopics",
        total_found=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
        api_units_used=data.get("GlobalVars", {}).get("AnalysisResUnitsUsed", 0)
    )


async def discover_similar_domains(
    domain: str,
    include_co_hosted: bool = True,
    limit: int = 100
) -> Dict[str, MajesticDiscoveryResponse]:
    """
    Comprehensive similar domain discovery combining multiple methods.

    Runs GetRelatedSites and optionally GetHostedDomains to find
    all potentially related/similar domains.

    Args:
        domain: Target domain
        include_co_hosted: Whether to include infrastructure clustering
        limit: Max results per method

    Returns:
        Dict with 'related_sites' and optionally 'hosted_domains' keys

    Example:
        results = await discover_similar_domains("sebgroup.com")
        # Returns related sites (competitors) AND co-hosted domains (affiliates)
    """
    import asyncio

    tasks = [get_related_sites(domain, max_results=limit)]

    if include_co_hosted:
        tasks.append(get_hosted_domains(domain, max_domains=limit))

    responses = await asyncio.gather(*tasks)

    result = {"related_sites": responses[0]}

    if include_co_hosted and len(responses) > 1:
        result["hosted_domains"] = responses[1]

    return result


# CLI entry point
if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Discover related domains via Majestic")
    parser.add_argument("domain", help="Target domain (e.g., sebgroup.com)")
    parser.add_argument("-m", "--method", default="related",
                        choices=["related", "hosted", "ref", "all"],
                        help="Discovery method")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Max results")

    args = parser.parse_args()

    async def main():
        if args.method == "related":
            response = await get_related_sites(args.domain, max_results=args.limit)
        elif args.method == "hosted":
            response = await get_hosted_domains(args.domain, max_domains=args.limit)
        elif args.method == "ref":
            response = await get_ref_domains(args.domain, limit=args.limit)
        else:  # all
            results = await discover_similar_domains(args.domain, limit=args.limit)
            for method, response in results.items():
                print(f"\n{'='*60}")
                print(f"Method: {method}")
                print(f"Found: {response.total_found}")
                print(f"Time: {response.elapsed_ms}ms")
                for r in response.results[:10]:
                    print(f"  - {r.domain} (TF:{r.trust_flow}, CF:{r.citation_flow})")
            return

        print(f"\n{response.method} for {response.target_domain}")
        print(f"Found: {response.total_found}")
        print(f"Time: {response.elapsed_ms}ms")
        print(f"API Units: {response.api_units_used}")
        print()

        for i, result in enumerate(response.results[:20], 1):
            print(f"{i}. {result.domain}")
            print(f"   TrustFlow: {result.trust_flow}, CitationFlow: {result.citation_flow}")
            if hasattr(result, 'common_links') and result.common_links:
                print(f"   Common Links: {result.common_links}")
            if hasattr(result, 'hosting_type'):
                print(f"   Hosting: {result.hosting_type}")
            print()

    asyncio.run(main())
