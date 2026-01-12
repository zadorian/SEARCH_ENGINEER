#!/usr/bin/env python3
"""
WHOIS Discovery Module

Discover related domains through WHOIS data clustering.

Discovery Methods:
1. Registrant Lookup: Find domains registered by same person/org
2. Nameserver Clustering: Find domains using same nameservers
3. Email Pattern Matching: Find domains with same registrant email

Use Cases:
- Find all domains owned by a company: "What other domains does X own?"
- Network mapping: "What domains share infrastructure?"
- Attribution: "Who registered this suspicious domain?"

NOTE: This module uses the shared whoisxmlapi helper for historic/reverse lookups.
"""

import sys
import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
import asyncio

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Add BACKEND/modules to path for ALLDOM WHOIS
BACKEND_MODULES = PROJECT_ROOT / 'BACKEND' / 'modules'
if str(BACKEND_MODULES) not in sys.path:
    sys.path.insert(0, str(BACKEND_MODULES))

# WHOIS now lives in ALLDOM (moved from EYE-D Jan 2026)
from modules.alldom.whoisxmlapi import (
    get_whois_history,
    reverse_whois_search,
    fetch_current_whois_record,
    reverse_nameserver_search,
    normalize_domain,
)

logger = logging.getLogger(__name__)

# Privacy indicators - if any of these appear in registrant data, it's redacted
# Also includes generic placeholder names that would match too many unrelated domains
PRIVACY_INDICATORS = [
    "data redacted",
    "redacted for privacy",
    "privacy protect",
    "whoisguard",
    "domains by proxy",
    "domainsbyproxy",
    "contact privacy",
    "private registration",
    "identity protect",
    "withheld for privacy",
    "not disclosed",
    "gdpr masked",
    "redacted",
    "privacyguardian",
    # Generic placeholder names (would match millions of unrelated domains)
    "registration private",
    "domain administrator",
    "domain admin",
    "dns admin",
    "hostmaster",
    "domain owner",
    "administrator",
    "admin contact",
    "technical contact",
    "tech contact",
    "abuse@",  # Generic abuse emails
    "postmaster@",
    "hostmaster@",
    "webmaster@",
    "noreply@",
    "no-reply@",
]


@dataclass
class WhoisRecord:
    """WHOIS record for a domain"""
    domain: str
    registrant_name: Optional[str] = None
    registrant_org: Optional[str] = None
    registrant_email: Optional[str] = None
    registrant_country: Optional[str] = None
    registrar: Optional[str] = None
    created_date: Optional[str] = None
    updated_date: Optional[str] = None
    expires_date: Optional[str] = None
    nameservers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WhoisClusterResult:
    """Result from WHOIS clustering"""
    domain: str
    match_type: str  # registrant_name, registrant_org, registrant_email, nameserver
    match_value: str
    confidence: float
    whois_data: Optional[Dict[str, Any]] = None


@dataclass
class WhoisDiscoveryResponse:
    """WHOIS discovery response"""
    query_domain: str
    method: str
    total_found: int
    results: List[WhoisClusterResult]
    elapsed_ms: int = 0
    api_calls_used: int = 0


async def whois_lookup(domain: str, timeout: float = 30.0) -> Optional[WhoisRecord]:
    """
    Lookup WHOIS data for a domain.

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        timeout: Request timeout

    Returns:
        WhoisRecord with parsed WHOIS data
    """
    # Normalize domain
    domain = normalize_domain(domain)

    logger.info(f"[WHOIS] Looking up: {domain}")
    try:
        whois_record = await asyncio.to_thread(fetch_current_whois_record, domain, timeout)
        if not whois_record:
            return None

        registrant = whois_record.get("registrant", {})

        nameservers = []
        ns_data = whois_record.get("nameServers", {})
        if isinstance(ns_data, dict):
            hostnames = ns_data.get("hostNames", [])
            if isinstance(hostnames, list):
                nameservers = [ns.lower() for ns in hostnames]

        status = whois_record.get("status", [])
        if isinstance(status, str):
            status = [status]

        return WhoisRecord(
            domain=domain,
            registrant_name=registrant.get("name"),
            registrant_org=registrant.get("organization"),
            registrant_email=registrant.get("email"),
            registrant_country=registrant.get("countryCode"),
            registrar=whois_record.get("registrarName"),
            created_date=whois_record.get("createdDate"),
            updated_date=whois_record.get("updatedDate"),
            expires_date=whois_record.get("expiresDate"),
            nameservers=nameservers,
            status=status,
            raw_data=whois_record,
        )
    except Exception as e:
        logger.error(f"[WHOIS] Lookup error: {e}")
        return None


def is_privacy_protected(value: Optional[str]) -> bool:
    """Check if a WHOIS field value indicates privacy protection."""
    if not value:
        return False
    value_lower = value.lower()
    return any(indicator in value_lower for indicator in PRIVACY_INDICATORS)


def historic_whois_lookup_sync(domain: str) -> List[WhoisRecord]:
    """
    Lookup historic WHOIS data for a domain using EYE-D's implementation.

    Returns historical records that may contain pre-privacy registrant data.

    Args:
        domain: Target domain (e.g., "soax.com")

    Returns:
        List of WhoisRecord from historical data
    """
    logger.info(f"[WHOIS History] Looking up historic records for: {domain}")

    try:
        # Use EYE-D's get_whois_history (synchronous)
        records = get_whois_history(domain)

        if not records:
            logger.info(f"[WHOIS History] No historic records found for {domain}")
            return []

        logger.info(f"[WHOIS History] Found {len(records)} historic records for {domain}")

        historic_records = []
        for rec in records:
            # EYE-D returns records with registrantContact structure
            registrant = rec.get("registrantContact", {})

            # Extract nameservers
            nameservers = []
            ns_data = rec.get("nameServers", [])
            if isinstance(ns_data, list):
                # May be pipe-separated string in list
                for ns in ns_data:
                    if isinstance(ns, str):
                        nameservers.extend([n.strip().lower() for n in ns.split('|')])

            historic_records.append(WhoisRecord(
                domain=domain,
                registrant_name=registrant.get("name"),
                registrant_org=registrant.get("organization"),
                registrant_email=registrant.get("email"),
                registrant_country=registrant.get("country"),
                registrar=rec.get("registrarName"),
                created_date=rec.get("audit", {}).get("createdDate") or rec.get("createdDateISO8601"),
                updated_date=rec.get("updatedDateISO8601"),
                expires_date=rec.get("expiresDateISO8601"),
                nameservers=nameservers,
                status=rec.get("status", []),
                raw_data=rec
            ))

        return historic_records

    except Exception as e:
        logger.error(f"[WHOIS History] Lookup error: {e}")
        return []


async def historic_whois_lookup(domain: str) -> List[WhoisRecord]:
    """Async wrapper for historic_whois_lookup_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, historic_whois_lookup_sync, domain)


def find_usable_registrant_from_history(records: List[WhoisRecord]) -> Optional[WhoisRecord]:
    """
    Find the first historic record with non-privacy-protected registrant data.

    Args:
        records: List of historic WhoisRecord (should be sorted oldest first)

    Returns:
        First record with usable registrant info, or None
    """
    for record in records:
        # Check if this record has usable (non-redacted) registrant data
        has_usable_name = record.registrant_name and not is_privacy_protected(record.registrant_name)
        has_usable_org = record.registrant_org and not is_privacy_protected(record.registrant_org)
        has_usable_email = record.registrant_email and not is_privacy_protected(record.registrant_email)

        if has_usable_name or has_usable_org or has_usable_email:
            logger.info(f"[WHOIS History] Found usable historic record from {record.created_date}")
            if has_usable_name:
                logger.info(f"  - Registrant Name: {record.registrant_name}")
            if has_usable_org:
                logger.info(f"  - Registrant Org: {record.registrant_org}")
            if has_usable_email:
                logger.info(f"  - Registrant Email: {record.registrant_email}")
            return record

    return None


def find_all_distinct_registrants(records: List[WhoisRecord]) -> List[Dict[str, str]]:
    """
    Find ALL distinct registrant names/orgs/emails from historic records.

    This captures ownership changes over time - a domain may have had
    multiple different owners.

    Args:
        records: List of historic WhoisRecord

    Returns:
        List of dicts with 'value' and 'type' keys for each distinct registrant
    """
    seen = set()
    registrants = []

    for record in records:
        # Check registrant name
        if record.registrant_name and not is_privacy_protected(record.registrant_name):
            name_normalized = record.registrant_name.strip().upper()
            if name_normalized and name_normalized not in seen and name_normalized != 'NA':
                seen.add(name_normalized)
                registrants.append({
                    'value': record.registrant_name.strip(),
                    'type': 'name',
                    'date': record.created_date
                })

        # Check registrant org
        if record.registrant_org and not is_privacy_protected(record.registrant_org):
            org_normalized = record.registrant_org.strip().upper()
            if org_normalized and org_normalized not in seen and org_normalized != 'NA':
                seen.add(org_normalized)
                registrants.append({
                    'value': record.registrant_org.strip(),
                    'type': 'org',
                    'date': record.created_date
                })

        # Check registrant email
        if record.registrant_email and not is_privacy_protected(record.registrant_email):
            email_normalized = record.registrant_email.strip().lower()
            if email_normalized and email_normalized not in seen:
                seen.add(email_normalized)
                registrants.append({
                    'value': record.registrant_email.strip(),
                    'type': 'email',
                    'date': record.created_date
                })

    logger.info(f"[WHOIS History] Found {len(registrants)} distinct registrants across all historic records")
    for r in registrants:
        logger.info(f"  - {r['type']}: {r['value']} (from {r['date']})")

    return registrants


def reverse_whois_by_registrant_sync(
    registrant: str,
    limit: int = 100
) -> List[WhoisClusterResult]:
    """
    Find domains registered by the same registrant using EYE-D's implementation.

    EYE-D's reverse_whois_search uses 'searchType': 'historic' by default,
    which finds domains even when current WHOIS is privacy-protected.

    Args:
        registrant: Registrant name, organization, or email to search
        limit: Maximum results

    Returns:
        List of domains with the same registrant
    """
    logger.info(f"[WHOIS Reverse] Searching for registrant: {registrant} (using EYE-D historic search)")

    results = []

    try:
        # Use EYE-D's reverse_whois_search (uses historic mode by default)
        response = reverse_whois_search(registrant, "basicSearchTerms")

        domains = response.get('domains', [])
        count = response.get('domains_count', 0)

        logger.info(f"[WHOIS Reverse] Found {count} domains for '{registrant}'")

        for domain in domains[:limit]:
            if isinstance(domain, str):
                results.append(WhoisClusterResult(
                    domain=domain,
                    match_type="registrant_historic",
                    match_value=registrant,
                    confidence=0.9
                ))

    except Exception as e:
        logger.error(f"[WHOIS Reverse] Error: {e}")

    return results[:limit]


async def reverse_whois_by_registrant(
    registrant: str,
    search_type: str = "registrant",
    use_historic: bool = True,  # Always use historic (via EYE-D)
    limit: int = 100
) -> List[WhoisClusterResult]:
    """Async wrapper for reverse_whois_by_registrant_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        reverse_whois_by_registrant_sync,
        registrant,
        limit
    )


async def find_domains_by_nameserver(
    nameserver: str,
    limit: int = 100
) -> List[WhoisClusterResult]:
    """
    Find domains using the same nameserver.

    This is useful for discovering domains that share DNS infrastructure,
    which often indicates common ownership or management.

    Args:
        nameserver: Nameserver hostname (e.g., "ns1.seb.se")
        limit: Maximum results

    Returns:
        List of domains using the same nameserver
    """
    nameserver = nameserver.lower().strip()
    logger.info(f"[WHOIS NS] Finding domains using nameserver: {nameserver}")
    results = []

    try:
        domains_list = await asyncio.to_thread(reverse_nameserver_search, nameserver, limit)
        for domain in domains_list[:limit]:
            if isinstance(domain, str):
                results.append(WhoisClusterResult(
                    domain=domain,
                    match_type="nameserver",
                    match_value=nameserver,
                    confidence=0.85
                ))
        logger.info(f"[WHOIS NS] Found {len(domains_list)} domains using {nameserver}")
    except Exception as e:
        logger.error(f"[WHOIS NS] Error: {e}")

    return results[:limit]


async def cluster_domains_by_whois(
    domain: str,
    include_nameserver: bool = True,
    limit: int = 100
) -> WhoisDiscoveryResponse:
    """
    Comprehensive domain clustering via WHOIS data.

    This function:
    1. Looks up WHOIS for the target domain
    2. Fetches HISTORIC WHOIS to find ALL distinct registrants over time
    3. Searches for other domains for EACH historic registrant (captures ownership changes)
    4. Optionally searches for domains sharing nameservers

    Args:
        domain: Target domain to cluster around
        include_nameserver: Also search by nameserver
        limit: Maximum results per method

    Returns:
        WhoisDiscoveryResponse with clustered domains
    """
    import time
    start_time = time.time()

    logger.info(f"[WHOIS Cluster] Starting comprehensive clustering for: {domain}")

    # First, get current WHOIS data for target domain
    whois_record = await whois_lookup(domain)
    api_calls = 1

    if not whois_record:
        logger.warning(f"[WHOIS Cluster] Could not get WHOIS for {domain}")
        return WhoisDiscoveryResponse(
            query_domain=domain,
            method="whois_cluster",
            total_found=0,
            results=[],
            elapsed_ms=int((time.time() - start_time) * 1000),
            api_calls_used=1
        )

    # Helper to check if value is unusable
    def is_unusable(value: Optional[str]) -> bool:
        if not value:
            return True
        return is_privacy_protected(value)

    all_results: List[WhoisClusterResult] = []
    searched_registrants: Set[str] = set()  # Track what we've already searched

    # ALWAYS fetch historic WHOIS to find ALL distinct registrants over time
    # This captures ownership changes (e.g., NICHOLAS MERCADER → SOAX LTD)
    logger.info(f"[WHOIS Cluster] Fetching historic WHOIS to find ALL distinct registrants...")
    historic_records = await historic_whois_lookup(domain)
    api_calls += 1

    if historic_records:
        # Find ALL distinct registrants across history
        distinct_registrants = find_all_distinct_registrants(historic_records)
        logger.info(f"[WHOIS Cluster] Found {len(distinct_registrants)} distinct historic registrants")

        # Search for domains for EACH distinct registrant
        for reg in distinct_registrants:
            reg_value = reg['value']
            reg_type = reg['type']
            reg_date = reg.get('date', 'unknown')

            # Skip if already searched (normalized comparison)
            normalized = reg_value.strip().upper()
            if normalized in searched_registrants:
                continue
            searched_registrants.add(normalized)

            logger.info(f"[WHOIS Cluster] Searching for '{reg_value}' ({reg_type} from {reg_date})...")

            try:
                results = await reverse_whois_by_registrant(
                    reg_value,
                    search_type="registrant" if reg_type != "email" else "email",
                    use_historic=True
                )
                logger.info(f"[WHOIS Cluster]   -> Found {len(results)} domains for '{reg_value}'")
                all_results.extend(results)
                api_calls += 1
            except Exception as e:
                logger.warning(f"[WHOIS Cluster] Error searching for '{reg_value}': {e}")

    else:
        logger.info(f"[WHOIS Cluster] No historic records, using current WHOIS only")

        # Fall back to current WHOIS if no historic available
        if whois_record.registrant_org and not is_unusable(whois_record.registrant_org):
            results = await reverse_whois_by_registrant(
                whois_record.registrant_org,
                search_type="registrant",
                use_historic=True
            )
            all_results.extend(results)
            api_calls += 1

        if (whois_record.registrant_name and
            whois_record.registrant_name != whois_record.registrant_org and
            not is_unusable(whois_record.registrant_name)):
            results = await reverse_whois_by_registrant(
                whois_record.registrant_name,
                search_type="registrant",
                use_historic=True
            )
            all_results.extend(results)
            api_calls += 1

        if whois_record.registrant_email and not is_unusable(whois_record.registrant_email):
            results = await reverse_whois_by_registrant(
                whois_record.registrant_email,
                search_type="email",
                use_historic=True
            )
            all_results.extend(results)
            api_calls += 1

    # Search by nameserver (optional)
    if include_nameserver and whois_record.nameservers:
        for ns in whois_record.nameservers[:2]:  # Top 2 nameservers
            ns_results = await find_domains_by_nameserver(ns, limit=limit // 2)
            all_results.extend(ns_results)
            api_calls += 1

    # Deduplicate and remove self
    seen = set()
    unique_results = []
    for r in all_results:
        if r.domain not in seen and r.domain != domain:
            seen.add(r.domain)
            unique_results.append(r)

    # Sort by confidence
    unique_results.sort(key=lambda x: x.confidence, reverse=True)

    elapsed_ms = int((time.time() - start_time) * 1000)

    method = "whois_cluster_all_historic" if historic_records else "whois_cluster"
    logger.info(f"[WHOIS Cluster] Found {len(unique_results)} related domains in {elapsed_ms}ms")
    logger.info(f"[WHOIS Cluster] Searched {len(searched_registrants)} distinct registrants, used {api_calls} API calls")

    return WhoisDiscoveryResponse(
        query_domain=domain,
        method=method,
        total_found=len(unique_results),
        results=unique_results[:limit],
        elapsed_ms=elapsed_ms,
        api_calls_used=api_calls
    )


async def batch_whois_lookup(
    domains: List[str],
    max_concurrent: int = 5
) -> Dict[str, WhoisRecord]:
    """
    Batch WHOIS lookup for multiple domains.

    Args:
        domains: List of domains to lookup
        max_concurrent: Maximum concurrent requests

    Returns:
        Dict mapping domain to WhoisRecord
    """
    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def lookup_with_semaphore(domain: str):
        async with semaphore:
            return domain, await whois_lookup(domain)

    tasks = [lookup_with_semaphore(d) for d in domains]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if isinstance(resp, Exception):
            logger.error(f"[WHOIS Batch] Error: {resp}")
            continue
        domain, record = resp
        if record:
            results[domain] = record

    return results


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WHOIS discovery and clustering")
    parser.add_argument("domain", help="Target domain (e.g., sebgroup.com)")
    parser.add_argument("-c", "--cluster", action="store_true", help="Run full clustering")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Max results")

    args = parser.parse_args()

    async def main():
        if args.cluster:
            print(f"\n🔍 Clustering domains related to: {args.domain}")
            response = await cluster_domains_by_whois(args.domain, limit=args.limit)

            print(f"\nFound {response.total_found} related domains in {response.elapsed_ms}ms")
            print(f"API calls used: {response.api_calls_used}")
            print()

            for i, result in enumerate(response.results[:20], 1):
                print(f"{i}. {result.domain}")
                print(f"   Match: {result.match_type} = {result.match_value}")
                print(f"   Confidence: {result.confidence:.0%}")
                print()
        else:
            print(f"\n📋 WHOIS lookup for: {args.domain}")
            record = await whois_lookup(args.domain)

            if record:
                print(f"\nDomain: {record.domain}")
                print(f"Registrant Name: {record.registrant_name}")
                print(f"Registrant Org: {record.registrant_org}")
                print(f"Registrant Email: {record.registrant_email}")
                print(f"Registrar: {record.registrar}")
                print(f"Created: {record.created_date}")
                print(f"Expires: {record.expires_date}")
                print(f"Nameservers: {', '.join(record.nameservers)}")
            else:
                print("WHOIS lookup failed")

    asyncio.run(main())
