#!/usr/bin/env python3
"""
Full SeekLeech run on ALL domains without templates.

Runs 50 concurrent direct + Firecrawl fallback.
Progress saved after each domain - fully resumable.

Usage:
    python run_seekleech_full.py
    python run_seekleech_full.py --concurrent 100  # Go harder
    python run_seekleech_full.py --dry-run         # Just show stats
"""

import asyncio
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

from seekleech import SeekLeech

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SeekLeech.Runner")

# Paths (PROJECT_ROOT already defined above for .env loading)
SOURCES_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources.json"
OUTPUT_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "seekleech_results.json"


async def main():
    parser = argparse.ArgumentParser(description="Run SeekLeech on all domains without templates")
    parser.add_argument("--concurrent", type=int, default=150, help="Concurrent requests (default: 150 - uses model pool)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of domains (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Just show stats, don't run")
    parser.add_argument("--no-validate", action="store_true", help="Skip template validation")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="Output path")
    args = parser.parse_args()

    # Load sources
    logger.info(f"Loading sources from {SOURCES_PATH}")
    with open(SOURCES_PATH) as f:
        sources = json.load(f)

    # Collect all domains without templates
    registries = []
    for jur, entries in sources.items():
        for e in entries:
            if not e.get("search_template"):
                registries.append(e)

    # Sort by url_count (most used first)
    registries.sort(key=lambda r: -(r.get("metadata", {}).get("url_count_in_reports", 0)))

    if args.limit:
        registries = registries[:args.limit]

    logger.info(f"Found {len(registries)} domains without templates")

    if args.dry_run:
        # Show stats by jurisdiction
        by_jur = {}
        for r in registries:
            j = r.get("jurisdiction", "??")
            by_jur[j] = by_jur.get(j, 0) + 1

        logger.info("\nBy jurisdiction:")
        for jur, count in sorted(by_jur.items(), key=lambda x: -x[1])[:30]:
            logger.info(f"  {jur}: {count}")

        # Show top domains by url_count
        logger.info("\nTop 20 by usage:")
        for r in registries[:20]:
            count = r.get("metadata", {}).get("url_count_in_reports", 0)
            logger.info(f"  {r.get('domain')}: {count} refs")

        return

    # Check for existing progress
    output_path = Path(args.output)
    done_count = 0
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
                done_count = len(existing)
        except:
            pass

    logger.info(f"")
    logger.info(f"=" * 60)
    logger.info(f"SEEKLEECH FULL RUN")
    logger.info(f"=" * 60)
    logger.info(f"Domains to process: {len(registries)}")
    logger.info(f"Already done: {done_count}")
    logger.info(f"Remaining: {len(registries) - done_count} (approx)")
    logger.info(f"Concurrent: {args.concurrent}")
    logger.info(f"Output: {args.output}")
    logger.info(f"=" * 60)
    logger.info(f"")

    # Estimate time
    # ~3 seconds per domain with high concurrency and model pool
    remaining = max(0, len(registries) - done_count)
    est_seconds = (remaining / args.concurrent) * 3
    est_minutes = est_seconds / 60
    logger.info(f"Estimated time: ~{est_minutes:.0f} minutes ({est_seconds/3600:.1f} hours)")
    logger.info(f"Using model pool across multiple providers for max throughput")
    logger.info(f"")

    # Run
    start_time = datetime.now()

    leech = SeekLeech()
    try:
        results = await leech.run(
            registries,
            output=output_path,
            concurrent=args.concurrent,
            resume=True,
            validate=not args.no_validate
        )

        # Final stats
        elapsed = (datetime.now() - start_time).total_seconds()
        found = sum(1 for r in results if r.get("status") == "found")
        profiles = sum(1 for r in results if "profile" in r.get("status", ""))
        failed = sum(1 for r in results if "failed" in r.get("status", ""))

        logger.info(f"")
        logger.info(f"=" * 60)
        logger.info(f"COMPLETE")
        logger.info(f"=" * 60)
        logger.info(f"Total processed: {len(results)}")
        logger.info(f"Search templates found: {found}")
        logger.info(f"Profile templates only: {profiles}")
        logger.info(f"Failed to scrape: {failed}")
        logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
        logger.info(f"Results saved to: {args.output}")

    finally:
        await leech.close()


if __name__ == "__main__":
    asyncio.run(main())
