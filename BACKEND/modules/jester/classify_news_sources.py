#!/usr/bin/env python3
"""
JESTER News Source Classifier

Classifies news sources by which scraping method they require.

JESTER Scraping Hierarchy:
- JESTER_A: httpx direct (fastest, simple HTTP)
- JESTER_B: Colly Go crawler (high-performance static HTML)
- JESTER_C: Rod Go crawler (JS rendering)
- JESTER_D: [TODO: Custom headless browser - Firecrawl/Crawlee inspired]
- FIRECRAWL: External Firecrawl API
- BRIGHTDATA: BrightData proxy (for blocked sites)
- MICROLINK: [TODO: Microlink proxy API]

Usage:
    python classify_news_sources.py                    # Classify all sources
    python classify_news_sources.py --test 10          # Test first 10 sources
    python classify_news_sources.py --output results.json
"""

import asyncio
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import quote_plus
from dataclasses import dataclass, asdict
from datetime import datetime

import httpx
from dotenv import load_dotenv

# Load environment from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# Paths
BACKEND_DIR = Path(__file__).resolve().parents[2]
MATRIX_DIR = BACKEND_DIR.parent / "input_output" / "matrix"
NEWS_SOURCES_PATH = MATRIX_DIR / "sources" / "news.json"
OUTPUT_PATH = MATRIX_DIR / "news_scrape_classification.json"

# Go binaries
GO_BIN_DIR = BACKEND_DIR / "modules" / "LINKLATER" / "scraping" / "web" / "go" / "bin"
COLLY_BIN = GO_BIN_DIR / "colly_crawler"
ROD_BIN = GO_BIN_DIR / "rod_crawler"

logger = logging.getLogger("NewsClassifier")


@dataclass
class ClassificationResult:
    """Result of classifying a news source."""
    source_id: str
    domain: str
    jurisdiction: str
    method: str  # JESTER_A, JESTER_B, JESTER_C, JESTER_D, FIRECRAWL, BRIGHTDATA, BLOCKED, FAILED
    latency_ms: int
    content_length: int
    status_code: int
    needs_js: bool
    error: Optional[str] = None
    tested_at: str = ""


class NewsSourceClassifier:
    """
    Classifies news sources by required scraping method.

    Tests each method in sequence until one works, then records the first
    successful method as the source's classification.
    """

    def __init__(self, firecrawl_api_key: str = None, brightdata_api_key: str = None):
        import os
        self.firecrawl_api_key = firecrawl_api_key or os.getenv("FIRECRAWL_API_KEY")
        self.brightdata_api_key = brightdata_api_key or os.getenv("BRIGHTDATA_API_KEY")

        self.http = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )

        # Check Go binaries availability
        self.colly_available = COLLY_BIN.exists()
        self.rod_available = ROD_BIN.exists()

        logger.info(f"Colly available: {self.colly_available}")
        logger.info(f"Rod available: {self.rod_available}")
        logger.info(f"Firecrawl available: {bool(self.firecrawl_api_key)}")
        logger.info(f"BrightData available: {bool(self.brightdata_api_key)}")

    async def close(self):
        await self.http.aclose()

    async def classify_source(self, source: Dict) -> ClassificationResult:
        """
        Classify a single news source by testing each method in sequence.

        Order: JESTER_A (httpx) -> JESTER_B (Colly) -> JESTER_C (Rod) -> FIRECRAWL -> BRIGHTDATA
        """
        domain = source.get("domain", "")
        jurisdiction = source.get("jurisdiction", "")
        source_id = f"{jurisdiction}_{domain}".replace(".", "_")

        # Build test URL
        template = source.get("search_template", "")
        if not template or "{q}" not in template:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NO_TEMPLATE",
                latency_ms=0,
                content_length=0,
                status_code=0,
                needs_js=False,
                error="No search template with {q}",
                tested_at=datetime.utcnow().isoformat()
            )

        test_url = template.replace("{q}", quote_plus("test"))

        # Test JESTER_A: Direct HTTP (httpx)
        result = await self._test_jester_a(test_url, source_id, domain, jurisdiction)
        if result.method == "JESTER_A":
            return result

        # Test JESTER_B: Colly Go crawler
        if self.colly_available:
            result = await self._test_jester_b(test_url, source_id, domain, jurisdiction)
            if result.method == "JESTER_B":
                return result

        # Test JESTER_C: Rod Go JS renderer
        if self.rod_available:
            result = await self._test_jester_c(test_url, source_id, domain, jurisdiction)
            if result.method == "JESTER_C":
                return result

        # Test FIRECRAWL
        if self.firecrawl_api_key:
            result = await self._test_firecrawl(test_url, source_id, domain, jurisdiction)
            if result.method == "FIRECRAWL":
                return result

        # Test BRIGHTDATA
        if self.brightdata_api_key:
            result = await self._test_brightdata(test_url, source_id, domain, jurisdiction)
            if result.method == "BRIGHTDATA":
                return result

        # All methods failed
        return ClassificationResult(
            source_id=source_id,
            domain=domain,
            jurisdiction=jurisdiction,
            method="BLOCKED",
            latency_ms=0,
            content_length=0,
            status_code=0,
            needs_js=False,
            error="All scraping methods failed",
            tested_at=datetime.utcnow().isoformat()
        )

    async def _test_jester_a(self, url: str, source_id: str, domain: str, jurisdiction: str) -> ClassificationResult:
        """Test JESTER_A: Direct HTTP with httpx."""
        start = time.time()
        try:
            resp = await self.http.get(url, timeout=15)
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200:
                content = resp.text
                needs_js = self._detect_js_required(content)

                if len(content) > 1000 and not needs_js:
                    return ClassificationResult(
                        source_id=source_id,
                        domain=domain,
                        jurisdiction=jurisdiction,
                        method="JESTER_A",
                        latency_ms=latency,
                        content_length=len(content),
                        status_code=resp.status_code,
                        needs_js=False,
                        tested_at=datetime.utcnow().isoformat()
                    )

                # Content too short or needs JS - try next method
                return ClassificationResult(
                    source_id=source_id,
                    domain=domain,
                    jurisdiction=jurisdiction,
                    method="NEEDS_HIGHER",
                    latency_ms=latency,
                    content_length=len(content),
                    status_code=resp.status_code,
                    needs_js=needs_js,
                    error="Content too short or needs JS",
                    tested_at=datetime.utcnow().isoformat()
                )

            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=latency,
                content_length=0,
                status_code=resp.status_code,
                needs_js=False,
                error=f"HTTP {resp.status_code}",
                tested_at=datetime.utcnow().isoformat()
            )

        except Exception as e:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=int((time.time() - start) * 1000),
                content_length=0,
                status_code=0,
                needs_js=False,
                error=str(e)[:100],
                tested_at=datetime.utcnow().isoformat()
            )

    async def _test_jester_b(self, url: str, source_id: str, domain: str, jurisdiction: str) -> ClassificationResult:
        """Test JESTER_B: Colly Go crawler for static HTML."""
        start = time.time()
        try:
            # Call Colly binary - uses 'test <url>' format
            result = await asyncio.create_subprocess_exec(
                str(COLLY_BIN),
                "test", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=20)
            latency = int((time.time() - start) * 1000)

            if result.returncode == 0 and stdout:
                output = stdout.decode("utf-8", errors="ignore")
                # Parse JSON output from Colly (may be pretty-printed multi-line)
                try:
                    # Find JSON block - starts with { ends with }
                    json_start = output.find('{')
                    json_end = output.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = output[json_start:json_end]
                        data = json.loads(json_str)
                        content = data.get("content", "")
                        status_code = data.get("status_code", 0)
                        if status_code == 200 and len(content) > 1000:
                            return ClassificationResult(
                                source_id=source_id,
                                domain=domain,
                                jurisdiction=jurisdiction,
                                method="JESTER_B",
                                latency_ms=latency,
                                content_length=len(content),
                                status_code=status_code,
                                needs_js=False,
                                tested_at=datetime.utcnow().isoformat()
                            )
                except json.JSONDecodeError:
                    pass  # Fall through to NEEDS_HIGHER

            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=latency,
                content_length=0,
                status_code=0,
                needs_js=True,
                error="Colly returned insufficient content or non-200 status",
                tested_at=datetime.utcnow().isoformat()
            )

        except asyncio.TimeoutError:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=20000,
                content_length=0,
                status_code=0,
                needs_js=True,
                error="Colly timeout",
                tested_at=datetime.utcnow().isoformat()
            )
        except Exception as e:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=int((time.time() - start) * 1000),
                content_length=0,
                status_code=0,
                needs_js=True,
                error=str(e)[:100],
                tested_at=datetime.utcnow().isoformat()
            )

    async def _test_jester_c(self, url: str, source_id: str, domain: str, jurisdiction: str) -> ClassificationResult:
        """Test JESTER_C: Rod Go JS renderer."""
        start = time.time()
        try:
            # Call Rod binary - uses 'test <url>' format
            result = await asyncio.create_subprocess_exec(
                str(ROD_BIN),
                "test", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=25)
            latency = int((time.time() - start) * 1000)

            if result.returncode == 0 and stdout:
                output = stdout.decode("utf-8", errors="ignore")
                # Parse JSON output from Rod (may be pretty-printed multi-line)
                try:
                    # Find JSON block - starts with { ends with }
                    json_start = output.find('{')
                    json_end = output.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = output[json_start:json_end]
                        data = json.loads(json_str)
                        content = data.get("content", "")
                        status_code = data.get("status_code", 0)
                        if status_code == 200 and len(content) > 500:  # Lower threshold for JS-rendered
                            return ClassificationResult(
                                source_id=source_id,
                                domain=domain,
                                jurisdiction=jurisdiction,
                                method="JESTER_C",
                                latency_ms=latency,
                                content_length=len(content),
                                status_code=status_code,
                                needs_js=True,
                                tested_at=datetime.utcnow().isoformat()
                            )
                except json.JSONDecodeError:
                    pass  # Fall through to NEEDS_HIGHER

            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=latency,
                content_length=0,
                status_code=0,
                needs_js=True,
                error="Rod returned insufficient content or non-200 status",
                tested_at=datetime.utcnow().isoformat()
            )

        except asyncio.TimeoutError:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=25000,
                content_length=0,
                status_code=0,
                needs_js=True,
                error="Rod timeout",
                tested_at=datetime.utcnow().isoformat()
            )
        except Exception as e:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=int((time.time() - start) * 1000),
                content_length=0,
                status_code=0,
                needs_js=True,
                error=str(e)[:100],
                tested_at=datetime.utcnow().isoformat()
            )

    async def _test_firecrawl(self, url: str, source_id: str, domain: str, jurisdiction: str) -> ClassificationResult:
        """Test Firecrawl external API."""
        start = time.time()
        try:
            resp = await self.http.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {self.firecrawl_api_key}",
                    "Content-Type": "application/json"
                },
                json={"url": url, "formats": ["html"]},
                timeout=30
            )
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("data", {}).get("html"):
                    content = data["data"]["html"]
                    return ClassificationResult(
                        source_id=source_id,
                        domain=domain,
                        jurisdiction=jurisdiction,
                        method="FIRECRAWL",
                        latency_ms=latency,
                        content_length=len(content),
                        status_code=200,
                        needs_js=True,
                        tested_at=datetime.utcnow().isoformat()
                    )

            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=latency,
                content_length=0,
                status_code=resp.status_code,
                needs_js=True,
                error=f"Firecrawl failed: {resp.status_code}",
                tested_at=datetime.utcnow().isoformat()
            )

        except Exception as e:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="NEEDS_HIGHER",
                latency_ms=int((time.time() - start) * 1000),
                content_length=0,
                status_code=0,
                needs_js=True,
                error=str(e)[:100],
                tested_at=datetime.utcnow().isoformat()
            )

    async def _test_brightdata(self, url: str, source_id: str, domain: str, jurisdiction: str) -> ClassificationResult:
        """Test BrightData proxy API."""
        start = time.time()
        try:
            resp = await self.http.post(
                "https://api.brightdata.com/request",
                headers={
                    "Authorization": f"Bearer {self.brightdata_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "zone": "mcp_unlocker",
                    "url": url,
                    "format": "raw"
                },
                timeout=60
            )
            latency = int((time.time() - start) * 1000)

            if resp.status_code == 200 and len(resp.text) > 1000:
                return ClassificationResult(
                    source_id=source_id,
                    domain=domain,
                    jurisdiction=jurisdiction,
                    method="BRIGHTDATA",
                    latency_ms=latency,
                    content_length=len(resp.text),
                    status_code=200,
                    needs_js=True,
                    tested_at=datetime.utcnow().isoformat()
                )

            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="BLOCKED",
                latency_ms=latency,
                content_length=0,
                status_code=resp.status_code,
                needs_js=True,
                error=f"BrightData failed: {resp.status_code}",
                tested_at=datetime.utcnow().isoformat()
            )

        except Exception as e:
            return ClassificationResult(
                source_id=source_id,
                domain=domain,
                jurisdiction=jurisdiction,
                method="BLOCKED",
                latency_ms=int((time.time() - start) * 1000),
                content_length=0,
                status_code=0,
                needs_js=True,
                error=str(e)[:100],
                tested_at=datetime.utcnow().isoformat()
            )

    def _detect_js_required(self, html: str) -> bool:
        """Detect if HTML content requires JavaScript rendering."""
        # SPA indicators
        spa_indicators = [
            '<div id="root"></div>',
            '<div id="__next"></div>',
            '<div id="app"></div>',
            '<div id="__nuxt"></div>',
            '<app-root></app-root>',
            '__NEXT_DATA__',
            '__NUXT__',
            'window.__INITIAL_STATE__',
        ]

        for indicator in spa_indicators:
            if indicator in html:
                return True

        # Check for empty body
        import re
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.I | re.S)
        if body_match:
            body_text = re.sub(r'<[^>]+>', ' ', body_match.group(1))
            body_text = re.sub(r'\s+', ' ', body_text).strip()
            if len(body_text) < 200:
                return True

        return False

    async def classify_all(
        self,
        sources: List[Dict],
        max_concurrent: int = 10,
        progress_callback=None
    ) -> List[ClassificationResult]:
        """Classify all sources with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def classify_with_semaphore(source: Dict, index: int) -> ClassificationResult:
            async with semaphore:
                result = await self.classify_source(source)
                if progress_callback:
                    progress_callback(index + 1, len(sources), result)
                return result

        tasks = [
            classify_with_semaphore(source, i)
            for i, source in enumerate(sources)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source = sources[i]
                final_results.append(ClassificationResult(
                    source_id=f"{source.get('jurisdiction', '')}_{source.get('domain', '')}",
                    domain=source.get("domain", ""),
                    jurisdiction=source.get("jurisdiction", ""),
                    method="ERROR",
                    latency_ms=0,
                    content_length=0,
                    status_code=0,
                    needs_js=False,
                    error=str(result)[:100],
                    tested_at=datetime.utcnow().isoformat()
                ))
            else:
                final_results.append(result)

        return final_results


def load_news_sources() -> List[Dict]:
    """Load news sources from JSON."""
    if not NEWS_SOURCES_PATH.exists():
        raise FileNotFoundError(f"News sources not found: {NEWS_SOURCES_PATH}")

    with open(NEWS_SOURCES_PATH) as f:
        data = json.load(f)

    sources = []
    for jur, entries in data.items():
        for entry in entries:
            entry["jurisdiction"] = jur
            sources.append(entry)

    return sources


def print_progress(current: int, total: int, result: ClassificationResult):
    """Print progress update."""
    pct = current / total * 100
    status = f"[{result.method}]" if result.method not in ["NEEDS_HIGHER", "ERROR"] else f"[{result.error[:20]}...]"
    print(f"\r[{current}/{total}] {pct:.1f}% - {result.domain[:30]} {status}", end="", flush=True)


async def main():
    parser = argparse.ArgumentParser(description="Classify news sources by scraping method")
    parser.add_argument("--test", type=int, help="Test first N sources only")
    parser.add_argument("--concurrent", type=int, default=10, help="Max concurrent requests")
    parser.add_argument("--output", type=str, help="Output JSON path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    print("Loading news sources...")
    sources = load_news_sources()
    print(f"Loaded {len(sources)} news sources")

    if args.test:
        sources = sources[:args.test]
        print(f"Testing first {len(sources)} sources only")

    classifier = NewsSourceClassifier()

    print(f"\nClassifying {len(sources)} sources...")
    print(f"Concurrent: {args.concurrent}")
    print()

    try:
        results = await classifier.classify_all(
            sources,
            max_concurrent=args.concurrent,
            progress_callback=print_progress
        )
    finally:
        await classifier.close()

    print("\n")

    # Generate summary
    method_counts = {}
    for r in results:
        method_counts[r.method] = method_counts.get(r.method, 0) + 1

    print("=" * 60)
    print("CLASSIFICATION RESULTS")
    print("=" * 60)
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")
    print("=" * 60)

    # Save results
    output_path = Path(args.output) if args.output else OUTPUT_PATH
    output_data = {
        "classified_at": datetime.utcnow().isoformat(),
        "total_sources": len(sources),
        "summary": method_counts,
        "results": [asdict(r) for r in results]
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
