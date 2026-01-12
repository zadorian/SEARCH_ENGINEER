#!/usr/bin/env python3
"""
PRODUCTION BACKLINK DISCOVERY PIPELINE

Hardcoded, optimized pipeline combining:
1. FREE sources first (CC Archive scan, CC Graph, GlobalLinks)
2. Majestic (API key required, fast + high quality)
3. Smart deduplication and merging

INPUT: Target domain
OUTPUT: Comprehensive backlink dataset with page URLs, anchors, and metadata

Design principles:
- Prioritize free/fast sources
- Run expensive queries in parallel
- Deduplicate intelligently
- Return results ASAP (streaming where possible)
"""

import asyncio
import aiohttp
import json
import re
from typing import List, Dict, Set, Optional
from collections import defaultdict
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent))
from modules.linklater.api import linklater

# Centralized CC config
from ..cc_config import build_index_url, get_default_archive

# Entity extraction patterns (permissive)
ENTITY_PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\+?[\d\s\-\(\)]{10,20}',
    'url': r'https?://[^\s<>"]+',
    'company': r'\b[A-Z][A-Za-z0-9\s&,\.]{2,50}(?:\s(?:Inc|LLC|Ltd|Corp|GmbH|SA|AB|AS)\.?)\b',
    'person': r'\b[A-Z][a-z]+\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b',
    'money': r'[\$€£¥]\s*[\d,]+(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP|million|billion)',
    'date': r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b'
}


@dataclass
class BacklinkResult:
    """Unified backlink result."""
    source_url: str
    target_url: str = ""
    source_domain: str = ""
    anchor_text: str = ""
    provider: str = ""
    trust_flow: int = 0
    citation_flow: int = 0
    timestamp: str = ""
    entities: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)  # entity_type -> list of {value, snippet}
    keywords: List[Dict[str, str]] = field(default_factory=list)  # list of {keyword, snippet}
    page_text: str = ""  # For fallback if needed


class ProductionBacklinkPipeline:
    """
    Production-grade backlink discovery.

    Strategy:
    1. Start all free sources in parallel (CC Graph, GlobalLinks)
    2. Start Majestic in parallel
    3. For missing domains from step 1, run CC Archive deep scan
    4. Merge and deduplicate
    5. Return comprehensive dataset
    """

    def __init__(self, target_domain: str, keywords: List[str] = None):
        self.target_domain = target_domain
        self.keywords = keywords or []
        self.cc_index_url = build_index_url()  # Uses centralized config
        self.wayback_cdx_url = "https://web.archive.org/cdx/search/cdx"
        self._session: Optional[aiohttp.ClientSession] = None

    async def discover_backlinks(
        self,
        max_results: int = 1000,
        deep_scan_domains: List[str] = None,
        include_majestic: bool = True,
        include_cc_scan: bool = True
    ) -> Dict:
        """
        Execute full discovery pipeline.

        Args:
            max_results: Max backlinks per source
            deep_scan_domains: Specific domains to deep scan (if known from graph)
            include_majestic: Include Majestic (requires API key)
            include_cc_scan: Include deep CC Archive scan

        Returns:
            Comprehensive backlink dataset
        """

        print("=" * 100)
        print(f"PRODUCTION BACKLINK DISCOVERY: {self.target_domain}")
        print("=" * 100)
        print(f"\nStrategy:")
        print(f"  1. CC Graph (domain-level, FREE, FAST)")
        print(f"  2. GlobalLinks (page-level WAT files, FREE)")
        print(f"  3. Majestic Fresh + Historic (page-level, API)")
        if include_cc_scan:
            print(f"  4. CC Archive Deep Scan (page-level, FREE, SLOW)")
        print()

        # PHASE 1: Free sources in parallel (CC Graph + GlobalLinks)
        print("PHASE 1: Free Sources (Parallel)")
        print("-" * 100)

        cc_graph_task = self.get_cc_graph_backlinks(max_results)
        globallinks_task = self.get_globallinks_backlinks(max_results)

        # PHASE 2: Majestic in parallel (if enabled)
        majestic_tasks = []
        if include_majestic:
            print("PHASE 2: Majestic API (Parallel)")
            print("-" * 100)
            majestic_tasks = [
                self.get_majestic_backlinks("fresh", max_results),
                self.get_majestic_backlinks("historic", max_results)
            ]

        # Wait for Phase 1 + 2
        results = await asyncio.gather(
            cc_graph_task,
            globallinks_task,
            *majestic_tasks,
            return_exceptions=True
        )

        cc_graph_results = results[0] if not isinstance(results[0], Exception) else []
        globallinks_results = results[1] if not isinstance(results[1], Exception) else []
        majestic_results = []

        if include_majestic and len(results) > 2:
            majestic_fresh = results[2] if not isinstance(results[2], Exception) else []
            majestic_historic = results[3] if not isinstance(results[3], Exception) else []
            majestic_results = majestic_fresh + majestic_historic

        print(f"\nPhase 1+2 Results:")
        print(f"  CC Graph: {len(cc_graph_results)} backlinks")
        print(f"  GlobalLinks: {len(globallinks_results)} backlinks")
        print(f"  Majestic: {len(majestic_results)} backlinks")

        # PHASE 3: Deep scan for specific domains (if needed)
        cc_scan_results = []
        if include_cc_scan and deep_scan_domains:
            print(f"\nPHASE 3: CC Archive Deep Scan")
            print("-" * 100)
            print(f"Scanning {len(deep_scan_domains)} specific domains...")

            cc_scan_results = await self.deep_scan_domains(
                deep_scan_domains,
                max_pages_per_domain=100
            )

            print(f"  CC Archive Scan: {len(cc_scan_results)} backlinks")

        # PHASE 4: Merge and deduplicate
        print(f"\nPHASE 4: Merging & Deduplication")
        print("-" * 100)

        merged = self.merge_results(
            cc_graph_results,
            globallinks_results,
            majestic_results,
            cc_scan_results
        )

        return merged

    async def get_cc_graph_backlinks(self, limit: int) -> List[BacklinkResult]:
        """Get backlinks from CC Graph (domain-level)."""
        print("📊 CC Graph: Querying domain graph...")

        try:
            # Use linklater unified API
            records = await linklater.get_backlinks(
                self.target_domain,
                limit=limit,
                use_globallinks=False  # We'll call GlobalLinks separately
            )

            results = []
            for record in records:
                if record.provider == 'cc_graph':
                    results.append(BacklinkResult(
                        source_url=f"http://{record.source}",
                        source_domain=record.source,
                        target_url=f"http://{record.target}",
                        provider="cc_graph"
                    ))

            print(f"   ✅ Found {len(results)} backlinks")
            return results

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []

    async def get_globallinks_backlinks(self, limit: int) -> List[BacklinkResult]:
        """Get backlinks from GlobalLinks (page-level WAT files)."""
        print("📊 GlobalLinks: Querying WAT files...")

        try:
            records = await linklater.get_backlinks(
                self.target_domain,
                limit=limit,
                use_globallinks=True
            )

            results = []
            for record in records:
                if record.provider == 'globallinks':
                    results.append(BacklinkResult(
                        source_url=record.source,
                        target_url=record.target,
                        anchor_text=record.anchor_text or "",
                        provider="globallinks"
                    ))

            print(f"   ✅ Found {len(results)} backlinks")
            return results

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []

    async def get_majestic_backlinks(self, mode: str, limit: int) -> List[BacklinkResult]:
        """Get backlinks from Majestic API."""
        print(f"📊 Majestic {mode.title()}: Querying...")

        try:
            backlinks = await linklater.get_majestic_backlinks(
                self.target_domain,
                mode=mode,
                result_type="pages",
                max_results=limit
            )

            results = []
            for bl in backlinks:
                results.append(BacklinkResult(
                    source_url=bl.get('source_url', ''),
                    target_url=bl.get('target_url', ''),
                    source_domain=bl.get('source_domain', ''),
                    anchor_text=bl.get('anchor_text', ''),
                    trust_flow=bl.get('trust_flow', 0),
                    citation_flow=bl.get('citation_flow', 0),
                    provider=f"majestic_{mode}"
                ))

            print(f"   ✅ Found {len(results)} backlinks")
            return results

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []

    async def deep_scan_domains(
        self,
        domains: List[str],
        max_pages_per_domain: int = 100,
        use_wayback_fallback: bool = True
    ) -> List[BacklinkResult]:
        """
        Deep scan specific domains by fetching their pages from CC Archive.

        With Wayback Machine fallback when CC Archive fails.

        Args:
            domains: List of domains to scan
            max_pages_per_domain: Max pages to scan per domain
            use_wayback_fallback: Use Wayback if CC Archive has no results

        Returns:
            List of backlinks found
        """

        results = []

        async with aiohttp.ClientSession() as session:
            for domain in domains:
                print(f"   Scanning {domain}...")

                # Try CC Archive first
                pages = self.get_pages_from_cc_index(domain, max_pages_per_domain)

                if pages:
                    # Scan pages for outlinks
                    domain_results = await self.scan_pages_for_outlinks(
                        session,
                        pages,
                        self.target_domain
                    )

                    results.extend(domain_results)
                    print(f"     → CC Archive: Found {len(domain_results)} backlinks")

                # Fallback to Wayback if no results and fallback enabled
                elif use_wayback_fallback:
                    print(f"     ⚠️  No CC Archive results, trying Wayback...")
                    wayback_results = await self.scan_wayback_for_outlinks(
                        session,
                        domain,
                        self.target_domain,
                        max_snapshots=50
                    )

                    results.extend(wayback_results)
                    print(f"     → Wayback: Found {len(wayback_results)} backlinks")
                else:
                    print(f"     → No results")

        return results

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            )
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_pages_from_cc_index(self, domain: str, limit: int) -> List[Dict]:
        """Get list of pages from CC Index (async)."""
        url = f"{self.cc_index_url}?url={domain}/*&output=json"

        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    records = []
                    text = await response.text()
                    for line in text.strip().split('\n')[:limit]:
                        if line:
                            records.append(json.loads(line))
                    return records
        except Exception:
            pass

        return []

    def extract_entities(self, text: str, source_url: str, snippet_size: int = 100) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract entities with surrounding context snippets.

        Args:
            text: Text content to extract from
            source_url: Source URL for tracking
            snippet_size: Characters of context around match

        Returns:
            Dict of entity_type -> list of {value, snippet}
        """
        entities = {}

        for entity_type, pattern in ENTITY_PATTERNS.items():
            matches_with_snippets = []
            seen_values = set()

            # Use finditer to get match positions
            for match in re.finditer(pattern, text, re.IGNORECASE if entity_type != 'company' else 0):
                value = match.group(0)

                # Skip duplicates
                if value in seen_values:
                    continue
                seen_values.add(value)

                # Extract snippet around match
                start = max(0, match.start() - snippet_size)
                end = min(len(text), match.end() + snippet_size)
                snippet = text[start:end].strip()

                # Add ellipsis if truncated
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."

                matches_with_snippets.append({
                    'value': value,
                    'snippet': snippet
                })

            if matches_with_snippets:
                entities[entity_type] = matches_with_snippets

        return entities

    def scan_for_keywords(self, text: str, keywords: List[str], snippet_size: int = 100) -> List[Dict[str, str]]:
        """
        Scan text for keywords with surrounding context.

        Args:
            text: Text to scan
            keywords: List of keywords to search for
            snippet_size: Characters of context around match

        Returns:
            List of {keyword, snippet}
        """
        found = []
        text_lower = text.lower()

        for keyword in keywords:
            keyword_lower = keyword.lower()
            pos = text_lower.find(keyword_lower)

            if pos >= 0:
                # Extract snippet around match
                start = max(0, pos - snippet_size)
                end = min(len(text), pos + len(keyword) + snippet_size)
                snippet = text[start:end].strip()

                # Add ellipsis if truncated
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."

                found.append({
                    'keyword': keyword,
                    'snippet': snippet
                })

        return found

    async def get_wayback_snapshots(self, domain: str, limit: int = 50) -> List[Dict]:
        """
        Get Wayback Machine snapshots for a domain (async).

        Args:
            domain: Domain to query
            limit: Max snapshots to return

        Returns:
            List of snapshot metadata
        """
        try:
            # Query Wayback CDX API
            params = {
                'url': f'{domain}/*',
                'output': 'json',
                'limit': limit,
                'fl': 'timestamp,original,statuscode,mimetype,digest'
            }

            session = await self._get_session()
            async with session.get(self.wayback_cdx_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Skip header row
                    if len(data) > 1:
                        snapshots = []
                        for row in data[1:]:
                            snapshots.append({
                                'timestamp': row[0],
                                'url': row[1],
                                'status': row[2],
                                'mimetype': row[3],
                                'digest': row[4]
                            })
                        return snapshots
        except Exception as e:
            print(f"   Wayback error: {e}")

        return []

    async def scan_wayback_for_outlinks(
        self,
        session: aiohttp.ClientSession,
        domain: str,
        target_domain: str,
        max_snapshots: int = 50
    ) -> List[BacklinkResult]:
        """
        Fallback to Wayback Machine when CC Archive fails.

        Args:
            session: aiohttp session
            domain: Source domain to scan
            target_domain: Target domain to find
            max_snapshots: Max snapshots to scan

        Returns:
            List of backlinks found
        """
        print(f"   🔄 Wayback fallback: {domain}")

        # Get snapshots
        snapshots = await self.get_wayback_snapshots(domain, max_snapshots)

        if not snapshots:
            return []

        print(f"      Found {len(snapshots)} snapshots")

        results = []

        for i, snapshot in enumerate(snapshots, 1):
            try:
                # Construct Wayback playback URL
                timestamp = snapshot['timestamp']
                original_url = snapshot['url']
                wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"

                # Fetch snapshot content
                async with session.get(wayback_url, timeout=20) as response:
                    if response.status == 200:
                        html = await response.text()

                        # Extract text for entity/keyword scanning
                        soup = BeautifulSoup(html, 'html.parser')
                        page_text = soup.get_text(separator=' ', strip=True)

                        # Find outlinks to target
                        found_outlinks = False
                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')

                            if target_domain in href:
                                found_outlinks = True

                                # Extract entities and keywords from page
                                entities = self.extract_entities(page_text[:10000], original_url)  # First 10K chars
                                keywords = self.scan_for_keywords(page_text[:10000], self.keywords)

                                results.append(BacklinkResult(
                                    source_url=original_url,
                                    target_url=href,
                                    anchor_text=link.get_text(strip=True)[:200],
                                    provider="wayback",
                                    timestamp=timestamp,
                                    entities=entities,
                                    keywords=keywords,
                                    page_text=page_text[:5000]  # First 5K for GPT-5-nano
                                ))

                        if found_outlinks and i % 10 == 0:
                            print(f"      Scanned {i}/{len(snapshots)} snapshots... ({len(results)} matches)")

            except Exception:
                continue

        print(f"      ✅ Found {len(results)} backlinks from Wayback")
        return results

    async def scan_pages_for_outlinks(
        self,
        session: aiohttp.ClientSession,
        pages: List[Dict],
        target_domain: str
    ) -> List[BacklinkResult]:
        """
        Scan pages for outlinks to target with entity/keyword extraction.

        Enhanced with:
        - Entity extraction (email, phone, company, person, etc.)
        - Keyword scanning
        - Page text capture for GPT-5-nano processing
        """

        results = []

        for page in pages:
            try:
                # Fetch page content
                cc_url = f"https://data.commoncrawl.org/{page['filename']}"
                offset = int(page['offset'])
                length = int(page['length'])

                headers = {'Range': f'bytes={offset}-{offset+length-1}'}

                async with session.get(cc_url, headers=headers, timeout=30) as response:
                    if response.status in (200, 206):
                        content = await response.text()

                        # Extract HTML from WARC record
                        parts = content.split('\r\n\r\n', 2)
                        html = parts[2] if len(parts) >= 3 else content

                        # Parse and find outlinks
                        soup = BeautifulSoup(html, 'html.parser')

                        # Extract page text for entity/keyword scanning
                        page_text = soup.get_text(separator=' ', strip=True)

                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')

                            if target_domain in href:
                                # Extract entities and keywords from page
                                entities = self.extract_entities(page_text[:10000], page['url'])
                                keywords = self.scan_for_keywords(page_text[:10000], self.keywords)

                                results.append(BacklinkResult(
                                    source_url=page['url'],
                                    target_url=href,
                                    anchor_text=link.get_text(strip=True)[:200],
                                    provider="cc_archive_scan",
                                    entities=entities,
                                    keywords=keywords,
                                    page_text=page_text[:5000]  # First 5K for GPT-5-nano
                                ))

            except Exception:
                continue

        return results

    def merge_results(
        self,
        cc_graph: List[BacklinkResult],
        globallinks: List[BacklinkResult],
        majestic: List[BacklinkResult],
        cc_scan: List[BacklinkResult]
    ) -> Dict:
        """
        Merge and deduplicate results from all sources.

        Deduplication strategy:
        1. By source URL (page-level)
        2. By source domain if no URL available
        3. Preserve best quality data (prefer Majestic for anchors/metrics)
        """

        # Index by source URL
        by_url = defaultdict(lambda: {
            'providers': set(),
            'data': None,
            'quality_score': 0
        })

        all_results = [
            ('cc_graph', cc_graph, 1),
            ('globallinks', globallinks, 2),
            ('majestic', majestic, 4),
            ('cc_scan', cc_scan, 3)
        ]

        for source_name, results, quality_score in all_results:
            for result in results:
                key = result.source_url or result.source_domain

                if not key:
                    continue

                by_url[key]['providers'].add(result.provider)

                # Keep highest quality data
                if by_url[key]['quality_score'] < quality_score:
                    by_url[key]['data'] = result
                    by_url[key]['quality_score'] = quality_score
                elif by_url[key]['quality_score'] == quality_score:
                    # Merge data (prefer non-empty fields)
                    existing = by_url[key]['data']
                    if not existing.anchor_text and result.anchor_text:
                        existing.anchor_text = result.anchor_text
                    if not existing.trust_flow and result.trust_flow:
                        existing.trust_flow = result.trust_flow

        # Convert to list
        merged_backlinks = []
        for url, info in by_url.items():
            data = info['data']
            merged_backlinks.append({
                'source_url': data.source_url,
                'target_url': data.target_url,
                'source_domain': data.source_domain,
                'anchor_text': data.anchor_text,
                'trust_flow': data.trust_flow,
                'citation_flow': data.citation_flow,
                'providers': list(info['providers']),
                'entities': data.entities,
                'keywords': data.keywords,
                'timestamp': data.timestamp
            })

        # Group by provider
        by_provider = defaultdict(int)
        for bl in merged_backlinks:
            for provider in bl['providers']:
                by_provider[provider] += 1

        print(f"\n✅ Merged Results:")
        print(f"   Total unique backlinks: {len(merged_backlinks)}")
        print(f"   By provider:")
        for provider, count in sorted(by_provider.items()):
            print(f"     - {provider}: {count}")

        # Analyze
        domains = set()
        with_anchors = 0
        with_metrics = 0

        for bl in merged_backlinks:
            if bl['source_domain']:
                domains.add(bl['source_domain'])
            if bl['anchor_text']:
                with_anchors += 1
            if bl['trust_flow'] > 0:
                with_metrics += 1

        print(f"\n📊 Analysis:")
        print(f"   Unique referring domains: {len(domains)}")
        print(f"   Backlinks with anchor text: {with_anchors}")
        print(f"   Backlinks with quality metrics: {with_metrics}")

        return {
            'target_domain': self.target_domain,
            'total_backlinks': len(merged_backlinks),
            'unique_domains': len(domains),
            'backlinks': merged_backlinks,
            'by_provider': dict(by_provider)
        }


async def main():
    """Example usage with enhanced entity/keyword scanning."""
    target = "sebgroup.com"

    # Keywords to scan for (Libyan connections example)
    keywords = [
        "libya", "libyan", "tripoli", "benghazi", "gaddafi", "qaddafi",
        "LIA", "LAFICO", "sovereign wealth", "sanctions"
    ]

    # Known domains to deep scan (from CC Graph)
    deep_scan_domains = ["cryptonews.com.au", "wko.at", "ots.at", "easybank.at"]

    pipeline = ProductionBacklinkPipeline(target, keywords=keywords)

    results = await pipeline.discover_backlinks(
        max_results=1000,
        deep_scan_domains=deep_scan_domains,
        include_majestic=True,
        include_cc_scan=True
    )

    # Show sample results with entity/keyword data
    print("\n" + "=" * 100)
    print("SAMPLE RESULTS (with Entity/Keyword Extraction)")
    print("=" * 100)

    for i, bl in enumerate(results['backlinks'][:10], 1):
        print(f"\n{i}. {bl['source_url']}")
        if bl['anchor_text']:
            print(f"   Anchor: \"{bl['anchor_text'][:100]}\"")
        if bl['trust_flow']:
            print(f"   TrustFlow: {bl['trust_flow']}")
        print(f"   Found in: {', '.join(bl['providers'])}")

        # Show extracted entities with snippets
        if bl.get('entities'):
            for entity_type, matches in bl['entities'].items():
                if matches:
                    print(f"   {entity_type.title()}: {len(matches)} found")
                    for match in matches[:3]:  # Show first 3
                        print(f"      - {match['value']}")
                        print(f"        \"{match['snippet'][:150]}...\"")

        # Show found keywords with snippets
        if bl.get('keywords'):
            print(f"   Keywords: {len(bl['keywords'])} found")
            for kw_data in bl['keywords'][:3]:  # Show first 3
                print(f"      - {kw_data['keyword']}")
                print(f"        \"{kw_data['snippet'][:150]}...\"")

        if bl.get('timestamp'):
            print(f"   Timestamp: {bl['timestamp']}")

    # Show keyword analysis with snippets
    keyword_data = defaultdict(list)
    for bl in results['backlinks']:
        if bl.get('keywords'):
            for kw_info in bl['keywords']:
                keyword_data[kw_info['keyword']].append({
                    'url': bl['source_url'],
                    'snippet': kw_info['snippet']
                })

    if keyword_data:
        print("\n" + "=" * 100)
        print("KEYWORD ANALYSIS (with Context)")
        print("=" * 100)
        for keyword, occurrences in sorted(keyword_data.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n'{keyword}' found in {len(occurrences)} backlinks:")
            for occ in occurrences[:3]:  # Show first 3
                print(f"   {occ['url']}")
                print(f"   \"{occ['snippet'][:150]}...\"")
                print()

    # Show entity analysis
    entity_counts = defaultdict(int)
    for bl in results['backlinks']:
        if bl.get('entities'):
            for entity_type, matches in bl['entities'].items():
                entity_counts[entity_type] += len(matches)

    if entity_counts:
        print("\n" + "=" * 100)
        print("ENTITY ANALYSIS")
        print("=" * 100)
        for entity_type, count in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {entity_type}: {count} extracted")


if __name__ == "__main__":
    asyncio.run(main())
