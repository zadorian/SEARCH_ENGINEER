#!/usr/bin/env python3
"""
TORPEDO PROCESSOR BASE - Classification & IO Routing Layer

Shared logic for TORPEDO processors (CR, News). This layer:
1. Tests which scrape method works for each source (via scraper_base)
2. Logs classifications to IO matrix JSON for executor routing
3. Provides jurisdiction-aware test query generation
4. Tracks processing stats

The key distinction:
- TORPEDO PROCESSOR = Tests sites, determines which JESTER method works, saves classification
- TORPEDO EXECUTOR = Uses the already-classified method from IO for each site (no testing)

Usage in processors:
    from TORPEDO.processor_base import TorpedoProcessor, ProcessorResult

    processor = TorpedoProcessor()
    result = await processor.classify_source(source, jurisdiction="HR")

    # Batch processing:
    results = await processor.classify_batch(sources, concurrent=20)

    # Save to IO matrix:
    processor.save_classification(output_path)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote_plus

from dotenv import load_dotenv

from ..paths import env_file

# Load environment (best-effort)
SCRIPT_DIR = Path(__file__).parent  # PROCESSING
MODULE_DIR = SCRIPT_DIR.parent  # TORPEDO
_env = env_file()
if _env:
    load_dotenv(_env)

# Import jester_bridge for scraping (relative import from parent TORPEDO module)
from ..jester_bridge import TorpedoScraper, ScrapeMethod, ScrapeResult

logger = logging.getLogger("TORPEDO.Processor")

# ─────────────────────────────────────────────────────────────
# Test queries by jurisdiction - used to construct test URLs
# ─────────────────────────────────────────────────────────────

TEST_QUERIES_CR = {
    # Corporate registry test queries (company types)
    "HU": "kft",
    "DE": "gmbh",
    "AT": "gmbh",
    "CH": "ag",
    "FR": "sarl",
    "ES": "sl",
    "IT": "srl",
    "NL": "bv",
    "BE": "bvba",
    "PL": "sp",
    "CZ": "sro",
    "RO": "srl",
    "BG": "eood",
    "GB": "ltd",
    "UK": "ltd",
    "IE": "ltd",
    "US": "llc",
    "CA": "inc",
    "AU": "pty",
    "BR": "ltda",
    "AR": "sa",
    "MX": "sa",
    "HR": "d.o.o.",
    "RS": "d.o.o.",
    "SI": "d.o.o.",
    "BA": "d.o.o.",
    "GLOBAL": "bank",
}

TEST_QUERIES_NEWS = {
    # News test queries (common words)
    "UK": "breaking",
    "GB": "breaking",
    "US": "breaking",
    "DE": "aktuell",
    "FR": "actualite",
    "AT": "aktuell",
    "CH": "aktuell",
    "NL": "nieuws",
    "IE": "breaking",
    "ES": "noticias",
    "IT": "notizie",
    "PL": "wiadomosci",
    "CZ": "zpravy",
    "HU": "hirek",
    "HR": "vijesti",
    "RS": "vesti",
    "GLOBAL": "news",
}


def get_test_query(jurisdiction: str, query_type: str = "cr") -> str:
    """Get test query for a jurisdiction."""
    queries = TEST_QUERIES_CR if query_type == "cr" else TEST_QUERIES_NEWS
    return queries.get(jurisdiction.upper(), queries.get("GLOBAL", "test"))


# ─────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────

@dataclass
class SourceConfig:
    """Configuration for a source to classify."""
    domain: str
    search_template: str  # URL with {q} placeholder
    jurisdiction: str = "GLOBAL"
    name: str = ""
    source_id: str = ""
    source_type: str = "cr"  # "cr" or "news"

    def __post_init__(self):
        if not self.name:
            self.name = self.domain
        if not self.source_id:
            jur = self.jurisdiction.replace("GB", "UK")
            self.source_id = f"{jur}_{self.domain.replace('.', '_')}"

    @classmethod
    def from_dict(cls, d: Dict, jurisdiction: str = "GLOBAL") -> 'SourceConfig':
        search_template = (
            d.get("search_template")
            or d.get("search_url")
            or d.get("searchUrl")
            or ""
        )
        return cls(
            domain=d.get("domain", ""),
            search_template=search_template,
            jurisdiction=d.get("jurisdiction", jurisdiction),
            name=d.get("name", d.get("domain", "")),
            source_id=d.get("source_id") or d.get("id", ""),
            source_type=d.get("source_type", "cr")
        )


@dataclass
class ProcessorResult:
    """Result of classifying a source."""
    source_id: str
    domain: str
    jurisdiction: str

    # Scrape classification
    scrape_method: str  # JESTER_A, JESTER_B, etc.
    latency_ms: int
    status_code: int
    content_length: int
    needs_js: bool

    # Status
    success: bool
    error: Optional[str] = None

    # Timestamps
    classified_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_scrape_result(cls, source: SourceConfig, result: ScrapeResult) -> 'ProcessorResult':
        return cls(
            source_id=source.source_id,
            domain=source.domain,
            jurisdiction=source.jurisdiction,
            scrape_method=result.method.value,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            content_length=result.content_length,
            needs_js=result.needs_js,
            success=result.success,
            error=result.error
        )


# ─────────────────────────────────────────────────────────────
# Main Processor Class
# ─────────────────────────────────────────────────────────────

class TorpedoProcessor:
    """
    TORPEDO Processor - Classification Layer.

    Tests sources using the scraper cascade and logs which method
    works for each site. This classification is saved to IO matrix
    JSON for executor routing.
    """

    def __init__(self, source_type: str = "cr"):
        """
        Initialize processor.

        Args:
            source_type: "cr" for corporate registries, "news" for news sources
        """
        self.source_type = source_type
        self.scraper = TorpedoScraper()
        self.results: List[ProcessorResult] = []
        self.stats = {
            "jester_a": 0,
            "jester_b": 0,
            "jester_c": 0,
            "jester_d": 0,
            "firecrawl": 0,
            "brightdata": 0,
            "failed": 0,
            "total": 0,
        }

    async def classify_source(self, source: SourceConfig) -> ProcessorResult:
        """
        Classify a single source by testing which scrape method works.

        Args:
            source: Source configuration with domain and search_template

        Returns:
            ProcessorResult with classification
        """
        if not source.search_template or "{q}" not in source.search_template:
            return ProcessorResult(
                source_id=source.source_id,
                domain=source.domain,
                jurisdiction=source.jurisdiction,
                scrape_method="failed",
                latency_ms=0,
                status_code=0,
                content_length=0,
                needs_js=False,
                success=False,
                error="No search template or missing {q} placeholder"
            )

        # Build test URL
        query = get_test_query(source.jurisdiction, self.source_type)
        url = source.search_template.replace("{q}", quote_plus(query))

        # Run scrape cascade
        scrape_result = await self.scraper.scrape(url)

        # Convert to processor result
        result = ProcessorResult.from_scrape_result(source, scrape_result)

        # Update stats
        method_key = result.scrape_method.lower().replace("scrapemethod.", "")
        if method_key in self.stats:
            self.stats[method_key] += 1
        else:
            self.stats["failed"] += 1
        self.stats["total"] += 1

        self.results.append(result)
        return result

    async def classify_batch(
        self,
        sources: List[SourceConfig],
        concurrent: int = 20,
        progress_callback: callable = None
    ) -> List[ProcessorResult]:
        """
        Classify multiple sources concurrently.

        Args:
            sources: List of source configurations
            concurrent: Max concurrent requests
            progress_callback: Optional callback(done, total, stats)

        Returns:
            List of ProcessorResults
        """
        semaphore = asyncio.Semaphore(concurrent)

        async def classify_one(source: SourceConfig) -> ProcessorResult:
            async with semaphore:
                return await self.classify_source(source)

        # Process in batches for progress reporting
        batch_size = 50
        results = []

        for i in range(0, len(sources), batch_size):
            batch = sources[i:i + batch_size]
            tasks = [classify_one(s) for s in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    source = batch[j]
                    result = ProcessorResult(
                        source_id=source.source_id,
                        domain=source.domain,
                        jurisdiction=source.jurisdiction,
                        scrape_method="failed",
                        latency_ms=0,
                        status_code=0,
                        content_length=0,
                        needs_js=False,
                        success=False,
                        error=str(result)
                    )
                    self.stats["failed"] += 1
                    self.stats["total"] += 1
                results.append(result)

            done = min(i + batch_size, len(sources))
            if progress_callback:
                progress_callback(done, len(sources), self.stats)
            else:
                logger.info(f"Progress: {done}/{len(sources)} - {self.stats}")

        return results

    async def close(self):
        """Close scraper connections."""
        await self.scraper.close()

    # ─────────────────────────────────────────────────────────────
    # IO Matrix Integration
    # ─────────────────────────────────────────────────────────────

    def save_classification(self, output_path: Path) -> Dict:
        """
        Save classification results in IO matrix format.

        This output is used by TORPEDO EXECUTOR to route each
        site to the correct JESTER method without re-testing.

        Args:
            output_path: Path to save JSON

        Returns:
            Classification data dict
        """
        output = {
            "classified_at": datetime.now().isoformat(),
            "source_type": self.source_type,
            "total_sources": self.stats["total"],
            "summary": {k: v for k, v in self.stats.items() if k != "total"},
            "results": [r.to_dict() for r in self.results]
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved classification to {output_path}")
        return output

    def update_sources_json(self, sources_path: Path):
        """
        Update a sources JSON file with classification results.

        Adds scrape_method and http_latency fields to each source
        for executor routing.

        Args:
            sources_path: Path to sources JSON file
        """
        # Build lookup by domain
        by_domain = {r.domain: r for r in self.results}
        by_source_id = {r.source_id: r for r in self.results}

        with open(sources_path) as f:
            sources = json.load(f)

        updated = 0

        if isinstance(sources, dict):
            # Jurisdiction-keyed format: {"HR": [...], "DE": [...]}
            for jur, entries in sources.items():
                for source in entries:
                    domain = source.get("domain", "")
                    source_id = source.get("id") or source.get("source_id", "")

                    result = by_source_id.get(source_id) or by_domain.get(domain)
                    if result:
                        source["scrape_method"] = result.scrape_method
                        source["http_latency"] = result.latency_ms
                        source["needs_js"] = result.needs_js
                        updated += 1
        else:
            # List format
            for source in sources:
                domain = source.get("domain", "")
                source_id = source.get("id") or source.get("source_id", "")

                result = by_source_id.get(source_id) or by_domain.get(domain)
                if result:
                    source["scrape_method"] = result.scrape_method
                    source["http_latency"] = result.latency_ms
                    source["needs_js"] = result.needs_js
                    updated += 1

        with open(sources_path, 'w') as f:
            json.dump(sources, f, indent=2)

        logger.info(f"Updated {updated} sources in {sources_path}")


# ─────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────

async def classify_sources_from_json(
    sources_path: Path,
    output_path: Optional[Path] = None,
    source_type: str = "cr",
    concurrent: int = 20,
    limit: Optional[int] = None,
    jurisdiction_filter: Optional[List[str]] = None
) -> Dict:
    """
    Load sources from JSON and classify them.

    Args:
        sources_path: Path to sources JSON file
        output_path: Where to save classification (default: same dir with .classified suffix)
        source_type: "cr" or "news"
        concurrent: Max concurrent requests
        limit: Max sources to process
        jurisdiction_filter: Only process these jurisdictions

    Returns:
        Classification summary dict
    """
    with open(sources_path) as f:
        data = json.load(f)

    # Parse sources
    sources = []
    if isinstance(data, dict):
        for jur, entries in data.items():
            if jurisdiction_filter and jur not in jurisdiction_filter:
                continue
            for entry in entries:
                sources.append(SourceConfig.from_dict(entry, jurisdiction=jur))
    else:
        for entry in data:
            jur = entry.get("jurisdiction", "GLOBAL")
            if jurisdiction_filter and jur not in jurisdiction_filter:
                continue
            sources.append(SourceConfig.from_dict(entry))

    # Apply source type
    for s in sources:
        s.source_type = source_type

    if limit:
        sources = sources[:limit]

    logger.info(f"Classifying {len(sources)} {source_type} sources")

    # Run classification
    processor = TorpedoProcessor(source_type=source_type)
    await processor.classify_batch(sources, concurrent=concurrent)

    # Save results
    if not output_path:
        output_path = sources_path.with_suffix(f".{source_type}.classified.json")

    result = processor.save_classification(output_path)
    await processor.close()

    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="TORPEDO Processor - Classify sources for executor routing")
    parser.add_argument("sources", help="Path to sources JSON")
    parser.add_argument("--output", "-o", help="Output path for classification")
    parser.add_argument("--type", "-t", choices=["cr", "news"], default="cr", help="Source type")
    parser.add_argument("--concurrent", "-c", type=int, default=20, help="Concurrent requests")
    parser.add_argument("--limit", "-l", type=int, help="Limit sources")
    parser.add_argument("--jurisdiction", "-j", help="Filter by jurisdiction (comma-separated)")
    parser.add_argument("--update-sources", action="store_true", help="Update source file with results")
    args = parser.parse_args()

    sources_path = Path(args.sources)
    output_path = Path(args.output) if args.output else None
    jurisdiction_filter = args.jurisdiction.split(",") if args.jurisdiction else None

    result = await classify_sources_from_json(
        sources_path,
        output_path,
        source_type=args.type,
        concurrent=args.concurrent,
        limit=args.limit,
        jurisdiction_filter=jurisdiction_filter
    )

    print(f"\nClassification Summary:")
    print(f"  Total: {result['total_sources']}")
    for method, count in result['summary'].items():
        pct = 100 * count / max(result['total_sources'], 1)
        print(f"  {method}: {count} ({pct:.1f}%)")

    if args.update_sources:
        processor = TorpedoProcessor(source_type=args.type)
        processor.results = [ProcessorResult(**r) for r in result['results']]
        processor.update_sources_json(sources_path)


if __name__ == "__main__":
    asyncio.run(main())
