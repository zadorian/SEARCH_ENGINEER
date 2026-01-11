#!/usr/bin/env python3
"""
TORPEDO NEWS PROCESSOR - News Source Scrape Classification

Simple processor for news sources. Only determines:
1. Which scrape method works (jester_bridge cascade)
2. Saves scrape_method to sources/news.json

News sources don't have "outputs" like CR sources - they return articles,
not structured company data. So no field extraction or IO Matrix codes.

Usage:
    python -m TORPEDO.PROCESSING.news_processor --jurisdiction UK --concurrent 20
    python -m TORPEDO.PROCESSING.news_processor --all
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Date filter detection
from .date_filter_detector import DateFilterDetector, detect_date_filters_for_sources
# Pagination detection
from .pagination_detector import PaginationDetector, detect_pagination_for_sources


from ..paths import env_file, news_sources_path as _default_news_sources_path

# Paths
SCRIPT_DIR = Path(__file__).parent
MODULE_DIR = SCRIPT_DIR.parent  # TORPEDO

_env = env_file()
if _env:
    load_dotenv(_env)

# Import jester_bridge for scraping (relative import from parent TORPEDO module)
from ..jester_bridge import TorpedoScraper, ScrapeMethod, ScrapeResult

logger = logging.getLogger("TORPEDO.NewsProcessor")

# Source files
DEFAULT_NEWS_SOURCES_PATH = _default_news_sources_path()

# Test queries by jurisdiction
TEST_QUERIES = {
    "UK": "breaking news",
    "GB": "breaking news",
    "US": "breaking news",
    "DE": "aktuell nachrichten",
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
    "GLOBAL": "news today",
}


@dataclass
class NewsProcessorResult:
    """Result of processing a news source."""
    domain: str
    jurisdiction: str
    source_id: str

    # Scrape classification
    scrape_method: str
    latency_ms: int
    status_code: int
    content_length: int

    # Pagination detection
    pagination: Optional[Dict] = None

    # Status
    success: bool = False
    error: Optional[str] = None
    notes: str = ""
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # HTML content (for pagination detection, not serialized)
    _html: Optional[str] = field(default=None, repr=False)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d.pop('_html', None)  # Don't include HTML in serialization
        return d


class NewsProcessor:
    """
    News Source Processor.

    Tests which scrape method works for each news source.
    Saves scrape_method to sources/news.json for EXECUTION routing.
    """

    def __init__(self, sources_path: Optional[str | Path] = None):
        self.scraper = TorpedoScraper()
        self.pagination_detector = PaginationDetector()
        self.results: List[NewsProcessorResult] = []
        self.sources_by_jurisdiction: Dict[str, List[Dict]] = {}
        self.loaded = False
        self.sources_path = Path(sources_path) if sources_path else DEFAULT_NEWS_SOURCES_PATH

        # Stats
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "jester_a": 0,
            "jester_b": 0,
            "jester_c": 0,
            "firecrawl": 0,
            "brightdata": 0,
            "pagination_detected": 0,
        }

    async def load_sources(self, sources_path: Optional[str | Path] = None) -> int:
        """Load news sources from sources/news.json (jurisdiction-keyed format)."""
        if self.loaded:
            return sum(len(s) for s in self.sources_by_jurisdiction.values())

        if sources_path:
            self.sources_path = Path(sources_path)

        if not self.sources_path.exists():
            logger.error(f"Missing news sources file: {self.sources_path}")
            return 0

        logger.info(f"Loading from {self.sources_path}")

        try:
            with open(self.sources_path) as f:
                data = json.load(f)

            count = 0

            # Handle jurisdiction-keyed format: {"AF": [...], "GB": [...], ...}
            if isinstance(data, dict) and all(isinstance(v, list) for v in list(data.values())[:5]):
                for jur_code, sources_list in data.items():
                    if not isinstance(sources_list, list):
                        continue

                    jur = jur_code if jur_code != "GB" else "UK"

                    for source in sources_list:
                        template = source.get("search_template") or source.get("search_url")
                        if not template or "{q}" not in template:
                            continue

                        domain = source.get("domain", "")
                        if not domain:
                            continue

                        if jur not in self.sources_by_jurisdiction:
                            self.sources_by_jurisdiction[jur] = []

                        self.sources_by_jurisdiction[jur].append({
                            "domain": domain,
                            "search_template": template,
                            "jurisdiction": jur,
                            "name": source.get("name", domain),
                            "source_id": source.get("id", f"{jur}_{domain.replace('.', '_')}"),
                            "reliability": source.get("reliability", 0.5),
                            "scrape_method": source.get("scrape_method"),  # Track if already classified
                        })
                        count += 1
            else:
                logger.error("Invalid news.json format (expected jurisdiction-keyed lists)")
                return 0

            self.loaded = True
            logger.info(f"Loaded {count} news sources across {len(self.sources_by_jurisdiction)} jurisdictions")
            return count

        except Exception as e:
            logger.error(f"Failed to load news sources: {e}")
            return 0

    def get_jurisdictions(self) -> List[str]:
        """Get list of jurisdictions with news sources."""
        return sorted(self.sources_by_jurisdiction.keys())

    def get_sources_for_jurisdiction(self, jurisdiction: str) -> List[Dict]:
        """Get news sources for a jurisdiction."""
        if jurisdiction == "GB":
            jurisdiction = "UK"
        return self.sources_by_jurisdiction.get(jurisdiction.upper(), [])

    async def process_source(self, source: Dict) -> NewsProcessorResult:
        """
        Process a single news source - test which scrape method works.
        Also detects pagination capability from the HTML response.
        """
        domain = source["domain"]
        jur = source["jurisdiction"]
        template = source["search_template"]
        source_id = source["source_id"]

        # Build test URL
        test_query = TEST_QUERIES.get(jur, TEST_QUERIES["GLOBAL"])
        url = template.replace("{q}", quote_plus(test_query))

        logger.debug(f"  Testing {domain}...")

        # Scrape with cascade
        scrape_result = await self.scraper.scrape(url)

        # Detect pagination from HTML (if successful)
        pagination = None
        if scrape_result.success and scrape_result.html:
            pagination = self.pagination_detector.detect(
                domain=domain,
                html=scrape_result.html,
                url=url
            )
            if pagination:
                self.stats["pagination_detected"] += 1
                logger.debug(f"  [{domain}] Pagination: {pagination.get('type')}")

        # Build result
        result = NewsProcessorResult(
            domain=domain,
            jurisdiction=jur,
            source_id=source_id,
            scrape_method=scrape_result.method.value if scrape_result.success else "failed",
            latency_ms=scrape_result.latency_ms,
            status_code=scrape_result.status_code,
            content_length=scrape_result.content_length,
            pagination=pagination,
            success=scrape_result.success,
            error=scrape_result.error,
            notes=f"Method: {scrape_result.method.value}" if scrape_result.success else scrape_result.error,
            _html=scrape_result.html if scrape_result.success else None
        )

        self.results.append(result)

        # Update stats
        self.stats["total"] += 1
        if scrape_result.success:
            self.stats["success"] += 1
            method_key = scrape_result.method.value.lower()
            if method_key in self.stats:
                self.stats[method_key] += 1
        else:
            self.stats["failed"] += 1

        return result

    async def process_jurisdiction(
        self,
        jurisdiction: str,
        concurrent: int = 20
    ) -> List[NewsProcessorResult]:
        """Process all sources for a jurisdiction."""
        if not self.loaded:
            await self.load_sources()

        sources = self.get_sources_for_jurisdiction(jurisdiction)
        if not sources:
            logger.warning(f"No news sources for {jurisdiction}")
            return []

        logger.info(f"Processing {len(sources)} news sources for {jurisdiction}")

        semaphore = asyncio.Semaphore(concurrent)

        async def process_one(source: Dict) -> NewsProcessorResult:
            async with semaphore:
                return await self.process_source(source)

        tasks = [process_one(s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                source = sources[i]
                final_results.append(NewsProcessorResult(
                    domain=source["domain"],
                    jurisdiction=jurisdiction,
                    source_id=source["source_id"],
                    scrape_method="failed",
                    latency_ms=0,
                    status_code=0,
                    content_length=0,
                    success=False,
                    error=str(r)
                ))
                self.stats["failed"] += 1
            else:
                final_results.append(r)

        return final_results

    async def process_all(
        self,
        concurrent: int = 20,
        jurisdictions: List[str] = None
    ) -> List[NewsProcessorResult]:
        """Process all news sources."""
        if not self.loaded:
            await self.load_sources()

        jurs = jurisdictions or self.get_jurisdictions()
        all_results = []

        for jur in jurs:
            results = await self.process_jurisdiction(jur, concurrent)
            all_results.extend(results)

        return all_results

    def save_to_sources_json(self):
        """
        Update sources/news.json with scrape_method, date_filtering, and pagination.

        News sources get:
        - scrape_method
        - http_latency
        - last_processed
        - search_recipe (if detected)
        - date_filtering (if detected)
        - pagination (if detected)

        No outputs (news doesn't have structured fields like CR).
        """
        with open(self.sources_path) as f:
            data = json.load(f)

        # Build lookup by domain
        by_domain = {r.domain: r for r in self.results}

        # Initialize detectors
        date_detector = DateFilterDetector()

        updated = 0
        date_updated = 0
        pagination_updated = 0

        # Handle jurisdiction-keyed format: {"AF": [...], "GB": [...], ...}
        if isinstance(data, dict) and all(isinstance(v, list) for v in list(data.values())[:5]):
            for jur_code, sources_list in data.items():
                if not isinstance(sources_list, list):
                    continue
                for source in sources_list:
                    domain = source.get("domain", "")
                    result = by_domain.get(domain)
                    if result and result.success:
                        source["scrape_method"] = result.scrape_method
                        source["http_latency"] = result.latency_ms
                        source["last_processed"] = result.processed_at
                        updated += 1

                        # Save pagination if detected
                        if result.pagination:
                            source["pagination"] = result.pagination
                            pagination_updated += 1

                    # Always try to detect date filtering
                    template = source.get("search_template", "")
                    date_config = date_detector.detect(domain, template)
                    if date_config:
                        source["date_filtering"] = date_config
                        date_updated += 1
        else:
            # Fallback: domain-keyed format
            sources_dict = data.get("sources", data)
            for domain, source in sources_dict.items():
                result = by_domain.get(domain)
                if result and result.success:
                    source["scrape_method"] = result.scrape_method
                    source["http_latency"] = result.latency_ms
                    source["last_processed"] = result.processed_at
                    if result.pagination:
                        source["pagination"] = result.pagination
                        pagination_updated += 1
                    updated += 1

        # Write back
        with open(self.sources_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Updated {updated} scrape methods, {date_updated} date filters, {pagination_updated} pagination configs")

    def save_results_json(self, output_path: Path):
        """Save detailed results to separate JSON file."""
        output = {
            "processed_at": datetime.now().isoformat(),
            "stats": self.stats,
            "results": [r.to_dict() for r in self.results]
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved {len(self.results)} results to {output_path}")

    async def close(self):
        """Close connections."""
        await self.scraper.close()


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

async def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="TORPEDO News Processor")
    parser.add_argument("--jurisdiction", "-j", help="Single jurisdiction to process")
    parser.add_argument("--all", action="store_true", help="Process all jurisdictions")
    parser.add_argument("--concurrent", "-c", type=int, default=20, help="Concurrent requests")
    parser.add_argument("--output", "-o", help="Output path for detailed results")
    parser.add_argument("--list-jurisdictions", action="store_true", help="List available jurisdictions")
    args = parser.parse_args()

    processor = NewsProcessor()
    await processor.load_sources()

    if args.list_jurisdictions:
        jurs = processor.get_jurisdictions()
        print(f"Available jurisdictions ({len(jurs)}):")
        for j in jurs:
            count = len(processor.get_sources_for_jurisdiction(j))
            print(f"  {j}: {count} sources")
        return

    # Process
    if args.jurisdiction:
        await processor.process_jurisdiction(args.jurisdiction, concurrent=args.concurrent)
    elif args.all:
        await processor.process_all(concurrent=args.concurrent)
    else:
        print("Specify --jurisdiction XX or --all")
        return

    # Save to sources JSON
    processor.save_to_sources_json()

    # Save detailed results
    output_path = Path(args.output) if args.output else MODULE_DIR / "PROCESSING" / "news_processing_results.json"
    processor.save_results_json(output_path)

    # Summary
    print(f"\n{'='*50}")
    print("NEWS PROCESSING COMPLETE")
    print(f"{'='*50}")
    print(f"  Total: {processor.stats['total']}")
    print(f"  Success: {processor.stats['success']}")
    print(f"  Failed: {processor.stats['failed']}")
    print(f"  Pagination detected: {processor.stats['pagination_detected']}")
    print(f"\nMethods:")
    for method in ["jester_a", "jester_b", "jester_c", "firecrawl", "brightdata"]:
        if processor.stats[method] > 0:
            print(f"  {method}: {processor.stats[method]}")

    await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
