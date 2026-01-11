"""
Run Enhanced Discovery on all sources to extract:
- input_schema (what input type each search accepts)
- thematic_tags (classification)

Usage:
    python run_enhanced_discovery.py --limit 500 --concurrent 5
    python run_enhanced_discovery.py --jurisdiction HU --limit 100
"""

import asyncio
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCES_V2 = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v2.json"
SOURCES_V3 = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"

from seekleech import SeekLeech, get_model_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("EnhancedDiscovery")


async def enrich_source(leech: SeekLeech, source: Dict) -> Dict:
    """
    Enrich a single source with input_schema and thematic_tags.
    Uses the existing search_template to analyze the search page.
    """
    domain = source.get("domain", "")
    template = source.get("search_template", "")

    if not template:
        return source  # Skip sources without templates

    # Build search page URL from template
    search_url = template.split("?")[0] if "?" in template else template.replace("{q}", "").rstrip("/")

    try:
        # Scrape the search page
        html, method = await leech.scrape(search_url)

        if not html:
            logger.debug(f"  ✗ Failed to scrape {domain}")
            return source

        # Extract essentials and analyze
        content = leech.extract_essentials(html, search_url)
        analysis = await leech.analyze_page(domain, content, "Analyzing for input_schema and thematic classification.")

        # Enrich source with new fields
        if analysis:
            source["input_schema"] = analysis.get("input_schema", {})
            source["thematic_tags"] = analysis.get("thematic_tags", [])
            source["language"] = analysis.get("language", "")
            source["requires_translation"] = analysis.get("requires_translation", False)
            source["enhanced_at"] = datetime.now().isoformat()

            logger.info(f"  ✓ {domain}: {source.get('thematic_tags', [])}")

        return source

    except Exception as e:
        logger.warning(f"  ✗ {domain}: {e}")
        return source


async def run_batch(
    sources: List[Dict],
    output_path: Path,
    concurrent: int = 5,
    save_interval: int = 50
):
    """Process sources in batches with progress saving."""

    leech = SeekLeech()
    sem = asyncio.Semaphore(concurrent)

    # Load existing progress
    enriched = {}
    if output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
                for jur, srcs in existing.items():
                    for s in srcs:
                        key = s.get("id") or s.get("domain")
                        if s.get("input_schema") or s.get("thematic_tags"):
                            enriched[key] = s
            logger.info(f"Loaded {len(enriched)} already enriched sources")
        except:
            pass

    # Filter to sources needing enrichment
    to_process = []
    for s in sources:
        key = s.get("id") or s.get("domain")
        if key not in enriched and s.get("search_template"):
            to_process.append(s)

    logger.info(f"Processing {len(to_process)} sources ({len(enriched)} already done)")

    results = []
    processed = 0

    async def process_one(source: Dict):
        nonlocal processed
        async with sem:
            result = await enrich_source(leech, source)
            processed += 1

            if processed % 10 == 0:
                logger.info(f"  Progress: {processed}/{len(to_process)}")

            return result

    # Process in chunks for progress saving
    chunk_size = save_interval
    for i in range(0, len(to_process), chunk_size):
        chunk = to_process[i:i+chunk_size]

        tasks = [process_one(s) for s in chunk]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in chunk_results:
            if isinstance(r, dict):
                results.append(r)

        # Save progress
        save_results(results, enriched, output_path)
        logger.info(f"Saved progress: {len(results)} processed")

    await leech.close()
    return results


def save_results(results: List[Dict], existing: Dict, output_path: Path):
    """Save results merged with existing, grouped by jurisdiction."""

    # Merge new results with existing
    all_sources = dict(existing)
    for r in results:
        key = r.get("id") or r.get("domain")
        all_sources[key] = r

    # Group by jurisdiction
    by_jurisdiction = {}
    for s in all_sources.values():
        jur = s.get("jurisdiction", "UNKNOWN")
        if jur not in by_jurisdiction:
            by_jurisdiction[jur] = []
        by_jurisdiction[jur].append(s)

    with open(output_path, 'w') as f:
        json.dump(by_jurisdiction, f, indent=2)


async def main():
    parser = argparse.ArgumentParser(description="Run Enhanced Discovery on sources")
    parser.add_argument("--input", default=str(SOURCES_V2), help="Input sources JSON")
    parser.add_argument("--output", default=str(SOURCES_V3), help="Output enriched JSON")
    parser.add_argument("--jurisdiction", "-j", help="Filter by jurisdiction")
    parser.add_argument("--limit", type=int, default=500, help="Max sources to process")
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--priority", action="store_true", help="Process high-priority sources first")
    args = parser.parse_args()

    # Load sources
    with open(args.input) as f:
        sources_by_jur = json.load(f)

    # Flatten and filter
    sources = []
    for jur, entries in sources_by_jur.items():
        if args.jurisdiction and jur != args.jurisdiction:
            continue
        for e in entries:
            e["jurisdiction"] = jur  # Ensure jurisdiction is set
            if e.get("search_template"):  # Only sources with templates
                sources.append(e)

    # Sort by priority (url_count_in_reports or refs)
    if args.priority:
        sources.sort(
            key=lambda s: -(s.get("metadata", {}).get("url_count_in_reports", 0) or
                          s.get("refs", 0)),
            reverse=False
        )

    sources = sources[:args.limit]

    if not sources:
        logger.error("No sources to process!")
        return

    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"ENHANCED DISCOVERY")
    logger.info(f"{'='*60}")
    logger.info(f"Sources to process: {len(sources)}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Concurrent: {args.concurrent}")
    logger.info(f"{'='*60}")
    logger.info(f"")

    results = await run_batch(
        sources,
        output_path=Path(args.output),
        concurrent=args.concurrent
    )

    # Stats
    with_schema = sum(1 for r in results if r.get("input_schema"))
    with_tags = sum(1 for r in results if r.get("thematic_tags"))

    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"DONE")
    logger.info(f"{'='*60}")
    logger.info(f"Processed: {len(results)}")
    logger.info(f"With input_schema: {with_schema}")
    logger.info(f"With thematic_tags: {with_tags}")


if __name__ == "__main__":
    asyncio.run(main())
