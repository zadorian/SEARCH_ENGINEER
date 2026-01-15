#!/usr/bin/env python3
"""
Quick HTTP Classifier - Determine which sources are Go-scrapeable

Runs HTTP GET on all sources to classify:
- "direct" = returns HTML via simple HTTP (Go binary can handle)
- "browser" = needs JavaScript rendering (Firecrawl/Puppeteer)
- "blocked" = returns 403/captcha
- "failed" = connection error

This is FAST - no AI, just HTTP requests.

Usage:
    python classify_scrape_method.py                    # Run on all
    python classify_scrape_method.py --concurrent 50   # Adjust parallelism
    python classify_scrape_method.py --update-v3       # Update sources_v3.json directly
"""

import asyncio
import json
import logging
import argparse
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import quote_plus
import httpx
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ScrapeClassifier")

# Paths
SOURCES_V3_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"
SOURCES_V2_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v2.json"
CLASSIFICATION_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "scrape_classification.json"

# Test queries by jurisdiction
TEST_QUERIES = {
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
    "IE": "ltd",
    "US": "llc",
    "CA": "inc",
    "AU": "pty",
    "BR": "ltda",
    "AR": "sa",
    "MX": "sa",
    "GLOBAL": "bank",
}

def get_test_query(jurisdiction: str) -> str:
    return TEST_QUERIES.get(jurisdiction, TEST_QUERIES.get("GLOBAL", "test"))


class ScrapeClassifier:
    """Fast HTTP-only classifier for scrape method."""

    def __init__(self, concurrent: int = 30):
        self.concurrent = concurrent
        self.semaphore = asyncio.Semaphore(concurrent)
        self.http = None
        self.results = {}
        self.stats = {
            "direct": 0,
            "browser": 0,
            "blocked": 0,
            "failed": 0,
            "total": 0
        }

    async def setup(self):
        self.http = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )

    async def close(self):
        if self.http:
            await self.http.aclose()

    async def classify_source(self, source: Dict, jurisdiction: str) -> Tuple[str, str, float]:
        """
        Classify a single source.
        Returns: (source_id, method, latency)
        """
        domain = source.get("domain", "")
        template = source.get("search_template", "")
        source_id = source.get("id", domain)

        if not template or "{q}" not in template:
            return source_id, "no_template", 0.0

        query = get_test_query(jurisdiction)
        url = template.replace("{q}", quote_plus(query))

        async with self.semaphore:
            start = time.time()
            try:
                resp = await self.http.get(url)
                latency = time.time() - start

                content_type = resp.headers.get("content-type", "").lower()
                content = resp.text[:5000] if resp.status_code == 200 else ""

                # Classify based on response
                if resp.status_code == 403:
                    return source_id, "blocked", latency

                if resp.status_code == 503:
                    return source_id, "blocked", latency

                if resp.status_code >= 400:
                    return source_id, "failed", latency

                # Check for captcha/bot detection
                captcha_indicators = [
                    "captcha", "recaptcha", "hcaptcha", "challenge",
                    "cloudflare", "ddos-guard", "please verify",
                    "access denied", "bot detected"
                ]
                content_lower = content.lower()
                if any(ind in content_lower for ind in captcha_indicators):
                    return source_id, "blocked", latency

                # Check for JS-required indicators
                js_indicators = [
                    "javascript is required",
                    "enable javascript",
                    "please enable js",
                    "noscript",
                    "__NEXT_DATA__",  # Next.js
                    "window.__INITIAL_STATE__",  # React SSR
                    "<div id=\"root\"></div>",  # Empty React root
                    "<div id=\"app\"></div>",  # Empty Vue root
                ]
                if any(ind in content for ind in js_indicators):
                    # But check if there's actual content too
                    if len(content) < 1000 or content.count("<") < 20:
                        return source_id, "browser", latency

                # Check for actual HTML content
                if "text/html" in content_type and len(content) > 500:
                    # Has real HTML content - direct scrapeable
                    return source_id, "direct", latency

                # JSON API response
                if "application/json" in content_type:
                    return source_id, "api", latency

                # Default to browser if uncertain
                return source_id, "browser", latency

            except httpx.TimeoutException:
                return source_id, "timeout", time.time() - start
            except Exception as e:
                return source_id, "failed", time.time() - start

    async def classify_batch(self, sources: List[Tuple[Dict, str]]) -> Dict[str, Dict]:
        """Classify a batch of sources."""
        tasks = [
            self.classify_source(source, jur)
            for source, jur in sources
        ]

        results = await asyncio.gather(*tasks)

        classified = {}
        for source_id, method, latency in results:
            classified[source_id] = {
                "scrape_method": method,
                "latency": latency
            }

            # Update stats
            if method in self.stats:
                self.stats[method] += 1
            self.stats["total"] += 1

        return classified

    async def run(self, sources_data: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """Run classification on all sources."""
        await self.setup()

        # Collect all sources with templates
        all_sources = []
        for jur, entries in sources_data.items():
            for source in entries:
                if source.get("search_template"):
                    all_sources.append((source, jur))

        logger.info(f"Classifying {len(all_sources)} sources with {self.concurrent} concurrent requests")

        # Process in batches
        batch_size = 100
        all_results = {}

        for i in range(0, len(all_sources), batch_size):
            batch = all_sources[i:i + batch_size]
            results = await self.classify_batch(batch)
            all_results.update(results)

            # Progress
            done = min(i + batch_size, len(all_sources))
            logger.info(f"Progress: {done}/{len(all_sources)} ({100*done/len(all_sources):.1f}%)")
            logger.info(f"  Direct: {self.stats['direct']}, Browser: {self.stats['browser']}, Blocked: {self.stats['blocked']}")

        await self.close()
        return all_results


def update_sources_v3(classification: Dict[str, Dict], v3_path: Path):
    """Update sources_v3.json with classification results."""
    logger.info(f"Updating {v3_path}...")

    with open(v3_path) as f:
        sources = json.load(f)

    updated = 0
    for jur, entries in sources.items():
        for source in entries:
            source_id = source.get("id", source.get("domain"))
            if source_id in classification:
                source["scrape_method"] = classification[source_id]["scrape_method"]
                source["http_latency"] = classification[source_id]["latency"]
                updated += 1

    with open(v3_path, 'w') as f:
        json.dump(sources, f, indent=2)

    logger.info(f"Updated {updated} sources in sources_v3.json")


async def main():
    parser = argparse.ArgumentParser(description="Classify source scrape methods")
    parser.add_argument("--concurrent", type=int, default=30, help="Concurrent requests")
    parser.add_argument("--update-v3", action="store_true", help="Update sources_v3.json")
    parser.add_argument("--source", "-s", choices=["v2", "v3"], default="v3", help="Source file")
    args = parser.parse_args()

    # Load sources
    source_path = SOURCES_V3_PATH if args.source == "v3" else SOURCES_V2_PATH
    if not source_path.exists():
        source_path = SOURCES_V2_PATH

    logger.info(f"Loading sources from {source_path}")
    with open(source_path) as f:
        sources_data = json.load(f)

    # Run classifier
    classifier = ScrapeClassifier(concurrent=args.concurrent)
    results = await classifier.run(sources_data)

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "stats": classifier.stats,
        "classification": results
    }

    with open(CLASSIFICATION_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Saved classification to {CLASSIFICATION_PATH}")

    # Summary
    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total sources: {classifier.stats['total']}")
    print(f"")
    print(f"Direct (Go-scrapeable):  {classifier.stats['direct']:,} ({100*classifier.stats['direct']/max(classifier.stats['total'],1):.1f}%)")
    print(f"Browser (JS required):   {classifier.stats['browser']:,} ({100*classifier.stats['browser']/max(classifier.stats['total'],1):.1f}%)")
    print(f"API (JSON response):     {classifier.stats.get('api', 0):,}")
    print(f"Blocked (captcha/403):   {classifier.stats['blocked']:,}")
    print(f"Failed (errors):         {classifier.stats['failed']:,}")
    print(f"Timeout:                 {classifier.stats.get('timeout', 0):,}")

    # Update v3 if requested
    if args.update_v3 and SOURCES_V3_PATH.exists():
        update_sources_v3(results, SOURCES_V3_PATH)


if __name__ == "__main__":
    asyncio.run(main())
