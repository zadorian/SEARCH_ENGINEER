#!/usr/bin/env python3
"""
JESTER MAPPER - Benchmark Script
================================

Test the MAPPER with different archive modes.

Usage:
    python benchmark.py elicius.co.uk                    # THOROUGH + both (default)
    python benchmark.py elicius.co.uk --fast             # FAST + both
    python benchmark.py elicius.co.uk --current-only     # Only live URLs
    python benchmark.py elicius.co.uk --archived-only    # Only dead URLs
"""

import asyncio
import sys
import time
from pathlib import Path

# Fix imports
MAPPER_DIR = Path(__file__).parent
MODULES_DIR = MAPPER_DIR.parent.parent
sys.path.insert(0, str(MODULES_DIR))

from JESTER.MAPPER.mapper import Mapper
from JESTER.MAPPER.config import FAST_SOURCES, THOROUGH_SOURCES


async def benchmark(domain: str, fast: bool = False, archive_mode: str = "both"):
    """Run benchmark on a domain."""
    mode = "FAST" if fast else "THOROUGH"
    sources = FAST_SOURCES if fast else THOROUGH_SOURCES

    print(f"\n{'='*60}")
    print(f"JESTER MAPPER Benchmark")
    print(f"{'='*60}")
    print(f"Domain: {domain}")
    print(f"Mode: {mode}")
    print(f"Archive Mode: {archive_mode}")
    print(f"Sources: {len(sources)}")
    print(f"{'='*60}\n")

    url_count = 0
    archived_count = 0
    live_count = 0
    source_counts = {}
    first_url_time = None

    start_time = time.perf_counter()

    async with Mapper() as mapper:
        async for url in mapper.map_domain(
            domain,
            fast=fast,
            archive_mode=archive_mode,
            verify_archives=True
        ):
            url_count += 1

            if first_url_time is None:
                first_url_time = time.perf_counter() - start_time

            source = url.source
            source_counts[source] = source_counts.get(source, 0) + 1

            # Track archive stats
            if url.is_archived:
                archived_count += 1
                if url.current_exists:
                    live_count += 1

            if url_count % 50 == 0:
                elapsed = time.perf_counter() - start_time
                print(f"[{elapsed:.1f}s] {url_count} URLs...")

    total_time = time.perf_counter() - start_time

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Total URLs: {url_count}")
    print(f"  - From archives: {archived_count}")
    print(f"  - Archives still live: {live_count}")
    print(f"Total time: {total_time:.2f}s")
    print(f"First URL at: {first_url_time:.2f}s" if first_url_time else "No URLs found")
    print(f"Rate: {url_count/total_time:.1f} URLs/sec" if total_time > 0 else "N/A")
    print(f"\nBy Source:")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")
    print(f"{'='*60}\n")


async def main():
    domain = sys.argv[1] if len(sys.argv) > 1 else "elicius.co.uk"
    fast = "--fast" in sys.argv
    
    if "--current-only" in sys.argv:
        archive_mode = "current_only"
    elif "--archived-only" in sys.argv:
        archive_mode = "archived_only"
    else:
        archive_mode = "both"

    await benchmark(domain, fast=fast, archive_mode=archive_mode)


if __name__ == "__main__":
    asyncio.run(main())
