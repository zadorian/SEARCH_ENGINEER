"""
Google Analytics Tracker Discovery
====================================
Find related domains via shared GA/GTM tracking codes using Wayback Machine.

Adapted from: C0GN1T0-STANDALONE/corporate/historic_google_analytics.py
Enhanced for: LinkLater integration

Three discovery modes:
1. Forward: Domain → GA codes (current + historical)
2. Reverse: GA code → All domains using it
3. Network: Domain → GA codes → Related domains

Usage:
    from modules.linklater.mapping.ga_tracker import GATracker

    tracker = GATracker()

    # Get all GA codes from a domain (current + historical)
    result = await tracker.discover_codes("sebgroup.com")
    # Returns: {
    #   'domain': 'sebgroup.com',
    #   'current_codes': {'UA': [...], 'GA': [...], 'GTM': [...]},
    #   'historical_codes': {
    #     'UA': {'UA-12345-1': {'first_seen': '2020-01-15', 'last_seen': '2023-06-30'}},
    #     ...
    #   },
    #   'timeline': [...]  # All snapshots with code changes
    # }

    # Find all domains sharing a GA code (reverse lookup)
    domains = await tracker.reverse_lookup("UA-12345-1")
    # Returns: ['domain1.com', 'domain2.com', ...]

    # Find related domains via shared GA codes
    related = await tracker.find_related_domains("sebgroup.com")
    # Returns: {
    #   'UA-12345-1': ['related1.com', 'related2.com'],
    #   'GTM-ABC123': ['related3.com'],
    #   ...
    # }
"""

import aiohttp
import asyncio
import hashlib
import os
import re
from datetime import datetime
from typing import Dict, List, Set, Optional, Any
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# Elasticsearch configuration
ES_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
ES_USER = os.getenv('ES_USERNAME', None)
ES_PASS = os.getenv('ES_PASSWORD', None)

# Regular expressions for analytics codes
UA_PATTERN = r'UA-\d+-\d+'
GA4_PATTERN = r'G-[A-Z0-9]{7,}'
GTM_PATTERN = r'GTM-[A-Z0-9]+'


class GATracker:
    """
    Discover domain relationships via shared Google Analytics tracking codes.

    Uses Wayback Machine to extract current and historical GA/GTM codes,
    then performs reverse lookups to find all domains sharing those codes.
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize GA tracker.

        Args:
            session: Optional aiohttp session (creates new one if not provided)
        """
        self._session = session
        self._own_session = session is None

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self._session:
            await self._session.close()

    @staticmethod
    def _format_timestamp(timestamp: str) -> str:
        """Convert 14-digit Wayback timestamp to readable date."""
        try:
            dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
            return dt.strftime("%Y-%m-%d")
        except Exception as e:
            return timestamp

    @staticmethod
    def _get_14_digit_timestamp(date_str: str) -> str:
        """Convert date string to 14-digit Wayback timestamp."""
        dt = datetime.strptime(date_str, "%d/%m/%Y:%H:%M")
        return dt.strftime("%Y%m%d%H%M%S")

    async def _fetch_snapshots(
        self,
        url: str,
        from_date: str,
        to_date: Optional[str] = None
    ) -> List[str]:
        """
        Fetch list of Wayback snapshots for a URL.

        Args:
            url: Target URL
            from_date: Start date (14-digit timestamp)
            to_date: Optional end date (14-digit timestamp)

        Returns:
            List of timestamps
        """
        cdx_url = "https://web.archive.org/cdx/search/cdx"
        params = {
            'url': url,
            'output': 'json',
            'fl': 'timestamp',
            'filter': '!statuscode:[45]..',  # Exclude error pages
            'from': from_date,
            'to': to_date if to_date else '',
            'collapse': 'timestamp:8'  # One snapshot per day
        }

        try:
            async with self._session.get(cdx_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return [row[0] for row in data[1:]] if len(data) > 1 else []
        except Exception as e:
            logger.error(f"Failed to fetch snapshots for {url}: {e}")

        return []

    async def _fetch_snapshot_content(self, url: str, timestamp: str) -> str:
        """
        Fetch content of a specific Wayback snapshot.

        Args:
            url: Target URL
            timestamp: Wayback timestamp

        Returns:
            Snapshot HTML content
        """
        wb_url = f"https://web.archive.org/web/{timestamp}/{url}"

        try:
            async with self._session.get(wb_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            logger.debug(f"Failed to fetch snapshot {timestamp} for {url}: {e}")

        return ""

    async def discover_codes(
        self,
        domain: str,
        from_date: str = "01/10/2012:00:00",
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Discover all GA/GTM codes used by a domain (current + historical).

        Args:
            domain: Target domain (e.g., "sebgroup.com")
            from_date: Start date for historical search
            to_date: Optional end date

        Returns:
            Dict with current_codes, historical_codes, and timeline
        """
        url = domain if domain.startswith('http') else f'http://{domain}'

        result = {
            'domain': domain,
            'current_codes': {'UA': [], 'GA': [], 'GTM': []},
            'historical_codes': {'UA': {}, 'GA': {}, 'GTM': {}},
            'timeline': []
        }

        try:
            # Convert dates to timestamps
            start_timestamp = self._get_14_digit_timestamp(from_date)
            end_timestamp = self._get_14_digit_timestamp(to_date) if to_date else None

            # Get snapshots
            snapshots = await self._fetch_snapshots(url, start_timestamp, end_timestamp)
            logger.info(f"Found {len(snapshots)} snapshots for {domain}")

            # Track code appearances
            code_dates = {'UA': {}, 'GA': {}, 'GTM': {}}

            # Process each snapshot
            for timestamp in snapshots:
                content = await self._fetch_snapshot_content(url, timestamp)
                if not content:
                    continue

                # Extract codes
                ua_codes = set(re.findall(UA_PATTERN, content))
                ga_codes = set(re.findall(GA4_PATTERN, content))
                gtm_codes = set(re.findall(GTM_PATTERN, content))

                formatted_date = self._format_timestamp(timestamp)

                # Update tracking
                for code in ua_codes:
                    if code not in code_dates['UA']:
                        code_dates['UA'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                    else:
                        code_dates['UA'][code]['last_seen'] = formatted_date

                for code in ga_codes:
                    if code not in code_dates['GA']:
                        code_dates['GA'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                    else:
                        code_dates['GA'][code]['last_seen'] = formatted_date

                for code in gtm_codes:
                    if code not in code_dates['GTM']:
                        code_dates['GTM'][code] = {'first_seen': formatted_date, 'last_seen': formatted_date}
                    else:
                        code_dates['GTM'][code]['last_seen'] = formatted_date

                # Add to timeline
                if ua_codes or ga_codes or gtm_codes:
                    result['timeline'].append({
                        'date': formatted_date,
                        'timestamp': timestamp,
                        'UA': list(ua_codes),
                        'GA': list(ga_codes),
                        'GTM': list(gtm_codes)
                    })

            # Get current codes (most recent snapshot or live)
            try:
                current_content = await self._fetch_snapshot_content(url, "")
                result['current_codes']['UA'] = list(set(re.findall(UA_PATTERN, current_content)))
                result['current_codes']['GA'] = list(set(re.findall(GA4_PATTERN, current_content)))
                result['current_codes']['GTM'] = list(set(re.findall(GTM_PATTERN, current_content)))
            except Exception as e:
                # Use most recent snapshot codes if live fetch fails
                if result['timeline']:
                    latest = result['timeline'][-1]
                    result['current_codes']['UA'] = latest['UA']
                    result['current_codes']['GA'] = latest['GA']
                    result['current_codes']['GTM'] = latest['GTM']

            # Set historical data
            result['historical_codes'] = code_dates

            logger.info(f"Discovered {len(code_dates['UA'])} UA codes, {len(code_dates['GA'])} GA4 codes, {len(code_dates['GTM'])} GTM codes for {domain}")

        except Exception as e:
            logger.error(f"Failed to discover codes for {domain}: {e}")

        return result

    async def reverse_lookup(
        self,
        ga_code: str,
        limit: int = 100,
        exclude_domains: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Find all domains using a specific GA/GTM code (reverse lookup).

        Args:
            ga_code: GA tracking code (e.g., "UA-12345-1")
            limit: Max domains to check
            exclude_domains: Domains to exclude from results

        Returns:
            List of domains using this code
        """
        exclude_domains = exclude_domains or set()
        discovered_domains = []

        logger.info(f"Reverse lookup for {ga_code} (limit: {limit})")

        try:
            # Search CDX for candidate domains
            cdx_url = "https://web.archive.org/cdx/search/cdx"

            # Try multiple TLDs
            tlds = ['com', 'net', 'org', 'io', 'co']

            for tld in tlds:
                params = {
                    'url': f'*.{tld}',
                    'matchType': 'domain',
                    'output': 'json',
                    'fl': 'original,timestamp',
                    'collapse': 'urlkey',
                    'limit': limit
                }

                async with self._session.get(cdx_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        continue

                    data = await response.json()

                    # Check a sample of snapshots for the GA code
                    for row in data[1:min(50, len(data))]:  # Limit to avoid rate limiting
                        url = row[0]
                        timestamp = row[1]

                        # Extract domain
                        parsed = urlparse(url if url.startswith('http') else f'http://{url}')
                        domain = parsed.netloc or parsed.path.split('/')[0]

                        if domain in exclude_domains or domain in discovered_domains:
                            continue

                        # Check if snapshot contains the GA code
                        content = await self._fetch_snapshot_content(url, timestamp)
                        if ga_code in content:
                            discovered_domains.append(domain)
                            logger.info(f"Found {ga_code} on {domain}")

                        await asyncio.sleep(0.5)  # Rate limiting

                if len(discovered_domains) >= limit:
                    break

        except Exception as e:
            logger.error(f"Reverse lookup failed for {ga_code}: {e}")

        return discovered_domains[:limit]

    async def find_related_domains(
        self,
        domain: str,
        max_per_code: int = 20
    ) -> Dict[str, List[str]]:
        """
        Find domains related via shared GA/GTM codes.

        Workflow:
        1. Discover all GA codes from target domain
        2. For each code, find other domains using it
        3. Return mapping of code → related domains

        Args:
            domain: Target domain
            max_per_code: Max related domains per GA code

        Returns:
            Dict mapping GA codes to lists of related domains
        """
        related = {}

        logger.info(f"Finding domains related to {domain} via GA codes")

        # Step 1: Discover codes from target domain
        codes_result = await self.discover_codes(domain)

        # Collect all codes (current + historical)
        all_codes = set()
        for code_type in ['UA', 'GA', 'GTM']:
            all_codes.update(codes_result['current_codes'][code_type])
            all_codes.update(codes_result['historical_codes'][code_type].keys())

        logger.info(f"Found {len(all_codes)} unique codes on {domain}")

        # Step 2: Reverse lookup for each code
        exclude = {domain}  # Don't include the original domain

        for code in all_codes:
            try:
                domains = await self.reverse_lookup(code, limit=max_per_code, exclude_domains=exclude)
                if domains:
                    related[code] = domains
                    logger.info(f"{code}: {len(domains)} related domains")

                await asyncio.sleep(1)  # Rate limiting between codes
            except Exception as e:
                logger.error(f"Failed reverse lookup for {code}: {e}")

        return related

    async def track_and_graph(
        self,
        domain: str,
        max_per_code: int = 20,
        index_name: str = "ga-edges"
    ) -> Dict[str, Any]:
        """
        Find related domains via GA codes AND add them as edges to the linkgraph.

        This is the key integration - auto-expands the network via analytics fingerprinting.

        Args:
            domain: Target domain
            max_per_code: Max related domains per GA code
            index_name: Elasticsearch index for GA edges

        Returns:
            Dict with:
            - source_domain: Original domain
            - codes_found: Number of GA codes discovered
            - related_domains: Dict of code → [domains]
            - edges_created: Number of graph edges created
        """
        result = {
            "source_domain": domain,
            "codes_found": 0,
            "related_domains": {},
            "edges_created": 0,
            "errors": []
        }

        # Ensure GA edges index exists
        await self._ensure_ga_index(index_name)

        # Step 1: Find related domains via GA codes
        logger.info(f"[track_and_graph] Finding related domains for {domain}")
        related = await self.find_related_domains(domain, max_per_code=max_per_code)

        result["related_domains"] = related
        result["codes_found"] = len(related)

        # Step 2: Create graph edges for each relationship
        now = datetime.utcnow().isoformat() + "Z"

        for ga_code, domains in related.items():
            for related_domain in domains:
                try:
                    edge_doc = {
                        # Source (original domain)
                        "source_domain": domain,
                        "source_url": f"https://{domain}/",

                        # Target (related domain)
                        "target_domain": related_domain,
                        "target_url": f"https://{related_domain}/",

                        # Edge metadata
                        "edge_type": "shared_ga",
                        "ga_code": ga_code,
                        "ga_code_type": self._classify_ga_code(ga_code),

                        # Timestamps
                        "discovered_at": now,
                        "indexed_at": now,

                        # Provenance
                        "provider": "ga_tracker",
                        "verified": False,
                    }

                    # Create unique document ID
                    doc_id = hashlib.sha256(
                        f"{domain}:{related_domain}:{ga_code}".encode()
                    ).hexdigest()[:16]

                    # Index to Elasticsearch
                    indexed = await self._index_edge(index_name, doc_id, edge_doc)
                    if indexed:
                        result["edges_created"] += 1

                except Exception as e:
                    result["errors"].append(f"Failed to index edge {domain}→{related_domain}: {e}")
                    logger.error(f"[track_and_graph] Edge indexing error: {e}")

        logger.info(
            f"[track_and_graph] {domain}: {result['codes_found']} codes, "
            f"{result['edges_created']} edges created"
        )

        return result

    @staticmethod
    def _classify_ga_code(code: str) -> str:
        """Classify GA code type."""
        if code.startswith('UA-'):
            return 'universal_analytics'
        elif code.startswith('G-'):
            return 'ga4'
        elif code.startswith('GTM-'):
            return 'tag_manager'
        return 'unknown'

    async def _ensure_ga_index(self, index_name: str) -> bool:
        """Create GA edges index if it doesn't exist."""
        mapping = {
            "mappings": {
                "properties": {
                    "source_domain": {"type": "keyword"},
                    "source_url": {"type": "keyword"},
                    "target_domain": {"type": "keyword"},
                    "target_url": {"type": "keyword"},
                    "edge_type": {"type": "keyword"},
                    "ga_code": {"type": "keyword"},
                    "ga_code_type": {"type": "keyword"},
                    "discovered_at": {"type": "date"},
                    "indexed_at": {"type": "date"},
                    "provider": {"type": "keyword"},
                    "verified": {"type": "boolean"},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }

        try:
            auth = aiohttp.BasicAuth(ES_USER or "", ES_PASS or "") if ES_USER else None

            async with self._session.head(
                f"{ES_URL}/{index_name}",
                auth=auth
            ) as resp:
                if resp.status == 200:
                    return True  # Index already exists

            # Create index
            async with self._session.put(
                f"{ES_URL}/{index_name}",
                json=mapping,
                auth=auth,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(f"[GA Tracker] Created index {index_name}")
                    return True
                else:
                    logger.error(f"[GA Tracker] Failed to create index: {resp.status}")
                    return False

        except Exception as e:
            logger.error(f"[GA Tracker] Index creation error: {e}")
            return False

    async def _index_edge(
        self,
        index_name: str,
        doc_id: str,
        edge_doc: Dict[str, Any]
    ) -> bool:
        """Index a GA edge to Elasticsearch."""
        try:
            auth = aiohttp.BasicAuth(ES_USER or "", ES_PASS or "") if ES_USER else None

            async with self._session.put(
                f"{ES_URL}/{index_name}/_doc/{doc_id}",
                json=edge_doc,
                auth=auth,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status in (200, 201)

        except Exception as e:
            logger.error(f"[GA Tracker] Edge indexing error: {e}")
            return False

    async def get_domains_by_ga_code(
        self,
        ga_code: str,
        index_name: str = "ga-edges",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query Elasticsearch for all domains sharing a GA code.

        Args:
            ga_code: The GA/GTM code to search for
            index_name: Elasticsearch index
            limit: Maximum results

        Returns:
            List of edge documents
        """
        query = {
            "query": {"term": {"ga_code": ga_code}},
            "size": limit,
            "sort": [{"discovered_at": {"order": "desc"}}]
        }

        try:
            auth = aiohttp.BasicAuth(ES_USER or "", ES_PASS or "") if ES_USER else None

            async with self._session.post(
                f"{ES_URL}/{index_name}/_search",
                json=query,
                auth=auth,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [hit["_source"] for hit in data.get("hits", {}).get("hits", [])]

        except Exception as e:
            logger.error(f"[GA Tracker] Query error: {e}")

        return []

    async def get_ga_connections_for_domain(
        self,
        domain: str,
        index_name: str = "ga-edges",
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get all GA-based connections for a domain.

        Args:
            domain: Target domain
            index_name: Elasticsearch index
            limit: Maximum results

        Returns:
            Dict with inbound and outbound GA connections
        """
        result = {
            "domain": domain,
            "outbound": [],  # Domains we share GA codes with (we're source)
            "inbound": [],   # Domains that share GA codes with us (we're target)
            "ga_codes": set()
        }

        # Get outbound (domain as source)
        outbound_query = {
            "query": {"term": {"source_domain": domain}},
            "size": limit
        }

        # Get inbound (domain as target)
        inbound_query = {
            "query": {"term": {"target_domain": domain}},
            "size": limit
        }

        try:
            auth = aiohttp.BasicAuth(ES_USER or "", ES_PASS or "") if ES_USER else None

            async with self._session.post(
                f"{ES_URL}/{index_name}/_search",
                json=outbound_query,
                auth=auth,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for hit in data.get("hits", {}).get("hits", []):
                        src = hit["_source"]
                        result["outbound"].append({
                            "domain": src["target_domain"],
                            "ga_code": src["ga_code"],
                            "discovered_at": src.get("discovered_at")
                        })
                        result["ga_codes"].add(src["ga_code"])

            async with self._session.post(
                f"{ES_URL}/{index_name}/_search",
                json=inbound_query,
                auth=auth,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for hit in data.get("hits", {}).get("hits", []):
                        src = hit["_source"]
                        result["inbound"].append({
                            "domain": src["source_domain"],
                            "ga_code": src["ga_code"],
                            "discovered_at": src.get("discovered_at")
                        })
                        result["ga_codes"].add(src["ga_code"])

        except Exception as e:
            logger.error(f"[GA Tracker] Connection query error: {e}")

        result["ga_codes"] = list(result["ga_codes"])
        return result


# Convenience function
async def discover_ga_codes(domain: str) -> Dict[str, Any]:
    """Discover GA codes from a domain (convenience function)."""
    async with GATracker() as tracker:
        return await tracker.discover_codes(domain)


async def find_related_via_ga(domain: str) -> Dict[str, List[str]]:
    """Find related domains via shared GA codes (convenience function)."""
    async with GATracker() as tracker:
        return await tracker.find_related_domains(domain)


async def track_and_graph(domain: str, max_per_code: int = 20) -> Dict[str, Any]:
    """
    Find related domains AND add them to the linkgraph (convenience function).

    This auto-expands the network via analytics fingerprinting.
    """
    async with GATracker() as tracker:
        return await tracker.track_and_graph(domain, max_per_code=max_per_code)


async def get_ga_connections(domain: str) -> Dict[str, Any]:
    """Get all GA-based connections for a domain from the graph (convenience function)."""
    async with GATracker() as tracker:
        return await tracker.get_ga_connections_for_domain(domain)


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GA Tracker - Analytics Fingerprinting")
    parser.add_argument("domain", help="Domain to analyze")
    parser.add_argument("--graph", action="store_true", help="Also add edges to linkgraph")
    parser.add_argument("--connections", action="store_true", help="Query existing GA connections from graph")
    parser.add_argument("--max-per-code", type=int, default=10, help="Max domains per GA code")

    args = parser.parse_args()

    async def main():
        domain = args.domain

        if args.connections:
            # Query existing connections from the graph
            print(f"\n📊 Querying GA connections for {domain}...\n")
            async with GATracker() as tracker:
                result = await tracker.get_ga_connections_for_domain(domain)

            print("=" * 80)
            print(f"GA Connections: {domain}")
            print("=" * 80)

            print(f"\n🔗 GA Codes: {len(result['ga_codes'])}")
            for code in result['ga_codes']:
                print(f"  • {code}")

            print(f"\n📤 Outbound ({len(result['outbound'])} domains sharing our GA codes):")
            for conn in result['outbound'][:20]:
                print(f"  → {conn['domain']} (via {conn['ga_code']})")

            print(f"\n📥 Inbound ({len(result['inbound'])} domains we share GA with):")
            for conn in result['inbound'][:20]:
                print(f"  ← {conn['domain']} (via {conn['ga_code']})")

            return

        print(f"\n🔍 Discovering GA codes for {domain}...\n")

        async with GATracker() as tracker:
            # Discover codes
            result = await tracker.discover_codes(domain)

            print("=" * 80)
            print(f"Domain: {domain}")
            print("=" * 80)

            # Current codes
            print("\n📊 Current Codes:")
            for code_type in ['UA', 'GA', 'GTM']:
                if result['current_codes'][code_type]:
                    for code in result['current_codes'][code_type]:
                        print(f"  {code_type}: {code}")

            # Historical codes
            print("\n📜 Historical Codes:")
            for code_type in ['UA', 'GA', 'GTM']:
                if result['historical_codes'][code_type]:
                    for code, dates in result['historical_codes'][code_type].items():
                        print(f"  {code_type}: {code} ({dates['first_seen']} to {dates['last_seen']})")

            print(f"\n📸 Snapshots analyzed: {len(result['timeline'])}")

            # Find related domains (and optionally graph them)
            if result['historical_codes']['UA'] or result['historical_codes']['GA'] or result['historical_codes']['GTM']:
                if args.graph:
                    print("\n🔗 Finding related domains AND adding to linkgraph...\n")
                    graph_result = await tracker.track_and_graph(domain, max_per_code=args.max_per_code)

                    print("=" * 80)
                    print("Graph Expansion Results")
                    print("=" * 80)

                    print(f"\n📈 GA codes found: {graph_result['codes_found']}")
                    print(f"🔗 Edges created: {graph_result['edges_created']}")

                    if graph_result['errors']:
                        print(f"\n⚠️  Errors: {len(graph_result['errors'])}")

                    for code, domains in graph_result['related_domains'].items():
                        print(f"\n{code}:")
                        for d in domains:
                            print(f"  → {d}")
                else:
                    print("\n🔗 Finding related domains...\n")
                    related = await tracker.find_related_domains(domain, max_per_code=args.max_per_code)

                    if related:
                        print("=" * 80)
                        print("Related Domains (via shared GA codes)")
                        print("=" * 80)
                        print("\n💡 Use --graph to add these as edges to the linkgraph\n")

                        for code, domains in related.items():
                            print(f"\n{code}:")
                            for d in domains:
                                print(f"  • {d}")
                    else:
                        print("No related domains found")

    asyncio.run(main())
