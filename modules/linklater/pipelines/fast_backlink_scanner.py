#!/usr/bin/env python3
"""
FAST BACKLINK SCANNER

Given a list of referring domains (from ES), scan their pages in CC archives
to find actual links pointing to the target domain with anchor text.

Pipeline:
1. Get referring domains from ES (instant)
2. Use ParallelWATFetcher to scan those domains' pages
3. Extract links pointing to target domain with anchor text

Performance: ~20-50x faster than sequential WAT processing
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Set, Optional, AsyncIterator
from urllib.parse import urlparse
import logging

# Add parent paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.linklater.parallel_wat_fetcher import ParallelWATFetcher
from modules.linklater.linkgraph.cc_graph_es import CCGraphESClient
from modules.linklater.linkgraph.host_graph_es import HostGraphESClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FastBacklinkScanner:
    """
    Fast backlink scanner using parallel WAT fetching.

    Uses pre-indexed ES data to know WHICH domains link to target,
    then scans only those domains' pages in CC archives.
    """

    def __init__(self, crawl_id: str = "CC-MAIN-2024-10"):
        self.crawl_id = crawl_id
        self.cc_graph = CCGraphESClient()
        self.host_graph = HostGraphESClient()

    async def close(self):
        await self.cc_graph.close()
        await self.host_graph.close()

    async def get_referring_domains(
        self,
        target_domain: str,
        limit: int = 100
    ) -> List[str]:
        """Get domains that link to target from ES (instant)."""
        # Query Host Graph (421M edges)
        host_results = await self.host_graph.get_backlinks(
            domain=target_domain,
            limit=limit,
            include_subdomains=True
        )

        # Query CC Graph
        cc_results = await self.cc_graph.get_backlinks(
            domain=target_domain,
            limit=limit
        )

        # Combine unique domains
        domains = set()
        for r in host_results + cc_results:
            if r.source:
                domain = urlparse(r.source).netloc if r.source.startswith('http') else r.source.split('/')[0]
                if domain and domain != target_domain:
                    domains.add(domain.lower())

        logger.info(f"Found {len(domains)} referring domains for {target_domain}")
        return list(domains)[:limit]

    async def scan_for_backlinks(
        self,
        target_domain: str,
        referring_domains: List[str],
        max_wat_files: int = 10,  # Limit WAT files for speed
        max_downloads: int = 20
    ) -> AsyncIterator[Dict]:
        """
        Scan referring domains' pages for links to target.

        Args:
            target_domain: Domain we're finding backlinks TO
            referring_domains: Domains to scan FOR links
            max_wat_files: Max WAT files to process (speed vs coverage)
            max_downloads: Concurrent WAT downloads

        Yields:
            Backlink records: {source, target, anchor_text, crawl_date}
        """
        if not referring_domains:
            return

        fetcher = ParallelWATFetcher(
            crawl_id=self.crawl_id,
            max_downloads=max_downloads,
            max_processors=10
        )

        target_lower = target_domain.lower()
        pages_with_backlinks = 0

        logger.info(f"Scanning {len(referring_domains)} domains for links to {target_domain}")
        logger.info(f"Processing max {max_wat_files} WAT files...")

        async for page_data in fetcher.fetch_domains(
            domains=referring_domains,
            max_wat_files=max_wat_files
        ):
            # Check each link in the page
            links = page_data.get('links', [])
            source_url = page_data.get('url', '')
            crawl_date = page_data.get('crawl_date')

            for link in links:
                if not isinstance(link, dict):
                    continue

                href = link.get('url', link.get('href', ''))

                # Check if link points to our target
                if target_lower in href.lower():
                    anchor_text = link.get('text', '')

                    pages_with_backlinks += 1

                    yield {
                        'source': source_url,
                        'target': href,
                        'anchor_text': anchor_text[:200] if anchor_text else None,
                        'crawl_date': crawl_date,
                        'provider': 'cc_wat'
                    }

        stats = fetcher.get_stats()
        logger.info(f"Scan complete: {stats['pages_processed']:,} pages processed")
        logger.info(f"Found {pages_with_backlinks} backlinks to {target_domain}")

    async def find_backlinks(
        self,
        target_domain: str,
        top_domains: int = 50,
        max_wat_files: int = 10
    ) -> List[Dict]:
        """
        Full pipeline: ES → WAT scan → backlinks with anchor text.

        Args:
            target_domain: Domain to find backlinks FOR
            top_domains: How many referring domains to scan
            max_wat_files: Max WAT files per scan (speed vs coverage)

        Returns:
            List of backlink records
        """
        import time
        start = time.time()

        # Step 1: Get referring domains from ES (instant)
        logger.info(f"Step 1: Getting referring domains for {target_domain}...")
        referring = await self.get_referring_domains(target_domain, limit=top_domains)

        if not referring:
            logger.warning(f"No referring domains found for {target_domain}")
            return []

        logger.info(f"Found {len(referring)} referring domains in {time.time() - start:.1f}s")

        # Step 2: Scan those domains for actual links
        logger.info(f"Step 2: Scanning pages for links to {target_domain}...")
        backlinks = []

        async for backlink in self.scan_for_backlinks(
            target_domain=target_domain,
            referring_domains=referring,
            max_wat_files=max_wat_files
        ):
            backlinks.append(backlink)

            # Progress update
            if len(backlinks) % 10 == 0:
                logger.info(f"  Found {len(backlinks)} backlinks so far...")

        elapsed = time.time() - start
        logger.info(f"Complete: {len(backlinks)} backlinks in {elapsed:.1f}s")

        return backlinks


async def main():
    """CLI for testing."""
    import json

    target = sys.argv[1] if len(sys.argv) > 1 else "bbc.com"

    print(f"\n{'='*60}")
    print(f"FAST BACKLINK SCANNER")
    print(f"{'='*60}")
    print(f"Target: {target}")
    print(f"{'='*60}\n")

    scanner = FastBacklinkScanner()

    try:
        backlinks = await scanner.find_backlinks(
            target_domain=target,
            top_domains=20,
            max_wat_files=5  # Quick test
        )

        print(f"\n{'='*60}")
        print(f"RESULTS: {len(backlinks)} backlinks")
        print(f"{'='*60}\n")

        for bl in backlinks[:20]:
            print(f"Source: {bl['source'][:70]}...")
            print(f"  → {bl['target']}")
            if bl.get('anchor_text'):
                print(f"  Anchor: \"{bl['anchor_text'][:50]}...\"")
            print()

    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(main())
