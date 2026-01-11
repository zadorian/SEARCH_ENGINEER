#!/usr/bin/env python3
"""
LinkLater Historical Keyword Search - The "Time Machine" Sniper

Combines:
1. Offline Index Lookup (The Map) - Locates specific files via cluster.idx
2. Parallel WAT Fetcher (The Engine) - High-speed async downloading
3. Keyword Grep (The Filter) - Scans content for specific terms

Usage:
    python3 historical_search.py --domain bbc.com --keyword "climate change" --archive CC-MAIN-2024-10
"""

import asyncio
import sys
import os
import json
import logging
import aiohttp
from pathlib import Path
from typing import List, Optional, Set

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # BACKEND/modules
sys.path.insert(0, str(Path(__file__).parent.parent))         # BACKEND/modules/LINKLATER

from modules.LINKLATER.scraping.web.cc_offline_sniper import CCIndexOfflineLookup
from modules.LINKLATER.parallel_wat_fetcher import ParallelWATFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HistoricalSearch")

class HistoricalSearcher:
    def __init__(
        self,
        archive: str = "CC-MAIN-2024-10",
        threads: int = 20,
        priority_terms: Optional[List[str]] = None,
        max_concurrent_index: int = 8,
    ):
        self.archive = archive
        self.threads = threads
        self.max_concurrent_index = max(1, int(max_concurrent_index))
        self.lookup = CCIndexOfflineLookup(archive)
        self.fetcher = ParallelWATFetcher(
            crawl_id=archive,
            max_downloads=threads,
            max_processors=threads
        )
        self.priority_terms = [term.lower() for term in (priority_terms or [
            "report",
            "annual",
            "financial",
            "investor",
            "investors",
            "investor-relations",
            "ir",
            "10-k",
            "10q",
            "20-f",
            "prospectus",
            "team",
            "leadership",
            "management",
            "board",
            "about",
            "company",
            "press",
            "news",
            "blog",
        ])]

    async def search(
        self,
        domain: str,
        keywords: List[str],
        stop_on_first: bool = False,
    ):
        """
        Execute the search pipeline.
        """
        logger.info(f"🔎 Phase 1: Mapping history for {domain} in {self.archive}...")
        
        # 1. Locate Files (The Map)
        # We increase limit to find MORE files for historical coverage
        wat_records = []
        if hasattr(self.lookup, "lookup_domain_async"):
            wat_records = await self.lookup.lookup_domain_async(
                domain,
                limit=500,
                max_concurrent=self.max_concurrent_index,
            )
        else:
            loop = asyncio.get_running_loop()
            wat_records = await loop.run_in_executor(
                None,
                lambda: self.lookup.lookup_domain(domain, limit=500)
            )
        
        if not wat_records:
            logger.error(f"❌ No historical records found for {domain} in this archive.")
            return

        wat_records = self._prioritize_records(wat_records)

        # Deduplicate WAT filenames (preserve priority ordering)
        unique_wats = []
        seen_wats = set()
        for record in wat_records:
            wat_file = record.get('wat_filename')
            if not wat_file or wat_file in seen_wats:
                continue
            seen_wats.add(wat_file)
            unique_wats.append(wat_file)
        logger.info(f"✅ Found {len(unique_wats)} unique archive files containing {domain}")
        
        # 2. Parallel Fetch & Scan (The Engine)
        logger.info(f"🚀 Phase 2: Parallel scanning of {len(unique_wats)} files...")
        
        total_matches = 0
        files_processed = 0
        
        # We manually orchestrate the fetcher to use our specific list
        # instead of the fetcher's default "download everything" mode
        
        async with aiohttp.ClientSession() as session:
            # Process in batches based on thread count
            for i in range(0, len(unique_wats), self.threads):
                batch = unique_wats[i : i + self.threads]
                batch_num = i // self.threads + 1
                total_batches = (len(unique_wats) - 1) // self.threads + 1
                
                logger.info(f"Batch {batch_num}/{total_batches}: Scanning {len(batch)} files...")
                
                # Create download tasks
                tasks = [self.fetcher.download_wat_file(path, session) for path in batch]
                contents = await asyncio.gather(*tasks)
                
                # Process contents
                for wat_content in contents:
                    if not wat_content: 
                        continue
                        
                    files_processed += 1
                    
                    # Parse WARC records
                    records = wat_content.split(b'WARC/1.0')
                    for record_bytes in records:
                        if not record_bytes.strip(): continue
                        
                        # Parse using fetcher's parser
                        # Pass None for target_domains to get all pages, then filter loosely for subdomains
                        page = self.fetcher._parse_warc_record(record_bytes, target_domains=None)
                        
                        if page:
                            # Check if page domain matches our target (handling subdomains like www.)
                            page_domain = page.get('domain', '')
                            if not page_domain.endswith(domain):
                                continue

                            # 3. Keyword Match (The Filter)
                            # Check title and content (anchor text context)
                            text_to_search = (page.get('title', '') + " " + page.get('content', '')).lower()
                            
                            for kw in keywords:
                                if kw.lower() in text_to_search:
                                    total_matches += 1
                                    print(f"\n[MATCH] {page['crawl_date']} - {page['url']}")
                                    print(f"Title: {page['title']}")
                                    print(f"Keyword: {kw}")
                                    print("-" * 40)
                                    if stop_on_first:
                                        logger.info("✅ Stop-on-first enabled, exiting early.")
                                        return

        logger.info(f"🏁 Search complete. Scanned {files_processed} files. Found {total_matches} matches.")

    def _prioritize_records(self, records: List[dict]) -> List[dict]:
        def score(url: str) -> int:
            url_lower = (url or "").lower()
            points = 0
            if url_lower.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")):
                points += 6
            for term in self.priority_terms:
                if term in url_lower:
                    points += 3
            return points

        return sorted(
            records,
            key=lambda rec: (-score(rec.get("url", "")), rec.get("timestamp", "")),
        )

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Historical Keyword Search")
    parser.add_argument("--domain", required=True, help="Target domain (e.g., bbc.com)")
    parser.add_argument("--keyword", required=True, help="Keyword to search")
    parser.add_argument("--archive", default="CC-MAIN-2024-10", help="CC Archive ID")
    parser.add_argument("--threads", type=int, default=20, help="Parallelism level")
    parser.add_argument("--stop-on-first", action="store_true", help="Stop after first match")
    
    args = parser.parse_args()
    
    searcher = HistoricalSearcher(args.archive, args.threads)
    await searcher.search(args.domain, [args.keyword], stop_on_first=args.stop_on_first)

if __name__ == "__main__":
    # Fix for import issues when running as script
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent.parent)) # Add BACKEND
    
    asyncio.run(main())
