#!/usr/bin/env python3
"""
Verify sources using ORIGINAL classifier's strict JESTER_A criteria:
- Content length > 1000 bytes
- No JS indicators (SPA skeleton detection)

This tests sources marked as FIRECRAWL/BRIGHTDATA to see if they
actually NEED those methods or if classification was flawed.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote_plus
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("StrictVerify")

MATRIX_DIR = Path(__file__).resolve().parents[3] / "input_output" / "matrix"
CLASSIFICATION_PATH = MATRIX_DIR / "news_scrape_classification.json"
NEWS_SOURCES_PATH = MATRIX_DIR / "sources" / "news.json"


def detect_js_required(html: str) -> bool:
    """
    EXACT copy of original classifier's JS detection.
    Returns True if page appears to be a JS skeleton.
    """
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
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.I | re.S)
    if body_match:
        body_text = re.sub(r'<[^>]+>', ' ', body_match.group(1))
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        if len(body_text) < 200:
            return True

    return False


async def verify_with_strict_criteria():
    """Verify FIRECRAWL/BRIGHTDATA sources with original strict criteria."""

    # Load classification
    with open(CLASSIFICATION_PATH) as f:
        data = json.load(f)

    # Load source templates
    with open(NEWS_SOURCES_PATH) as f:
        sources_data = json.load(f)

    # Build domain -> template lookup
    templates = {}
    for jur, entries in sources_data.items():
        for entry in entries:
            templates[entry.get("domain")] = entry.get("search_template", "")

    # Find FIRECRAWL and BRIGHTDATA classified sources
    api_sources = [
        r for r in data.get("results", [])
        if r.get("method") in ("FIRECRAWL", "BRIGHTDATA")
    ]

    logger.info(f"Testing {len(api_sources)} sources classified as FIRECRAWL/BRIGHTDATA")
    logger.info("Using ORIGINAL strict criteria: >1000 bytes AND no JS indicators")

    stats = {
        "would_be_jester_a": 0,
        "correctly_needs_api": 0,
        "failed_http": 0,
        "too_short": 0,
        "has_js_indicators": 0,
    }

    http = httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    )

    semaphore = asyncio.Semaphore(20)

    async def test_one(source: dict) -> dict:
        domain = source.get("domain", "")
        template = templates.get(domain, "")

        if not template or "{q}" not in template:
            return {"domain": domain, "reason": "no_template"}

        url = template.replace("{q}", quote_plus("test"))

        async with semaphore:
            try:
                resp = await http.get(url)

                if resp.status_code != 200:
                    return {"domain": domain, "reason": "http_error", "status": resp.status_code}

                content = resp.text
                content_len = len(content)
                needs_js = detect_js_required(content)

                if content_len < 1000:
                    return {"domain": domain, "reason": "too_short", "length": content_len}

                if needs_js:
                    return {"domain": domain, "reason": "needs_js", "length": content_len}

                # PASSES strict criteria!
                return {"domain": domain, "reason": "passes_strict", "length": content_len}

            except Exception as e:
                return {"domain": domain, "reason": "exception", "error": str(e)[:50]}

    # Run tests
    tasks = [test_one(s) for s in api_sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    await http.aclose()

    # Analyze
    passes_strict = []
    for r in results:
        if isinstance(r, Exception):
            stats["failed_http"] += 1
            continue

        reason = r.get("reason")
        if reason == "passes_strict":
            stats["would_be_jester_a"] += 1
            passes_strict.append(r)
        elif reason == "http_error":
            stats["failed_http"] += 1
        elif reason == "too_short":
            stats["too_short"] += 1
        elif reason == "needs_js":
            stats["has_js_indicators"] += 1
        elif reason == "exception":
            stats["failed_http"] += 1
        else:
            stats["correctly_needs_api"] += 1

    # Summary
    print("\n" + "=" * 60)
    print("STRICT CRITERIA VERIFICATION RESULTS")
    print("=" * 60)
    print(f"Total FIRECRAWL/BRIGHTDATA sources: {len(api_sources)}")
    print()
    print(f"Would PASS strict JESTER_A: {stats['would_be_jester_a']} ({100*stats['would_be_jester_a']/len(api_sources):.1f}%)")
    print(f"  - HTTP error / timeout: {stats['failed_http']}")
    print(f"  - Content < 1000 bytes: {stats['too_short']}")
    print(f"  - Has JS indicators:    {stats['has_js_indicators']}")
    print("=" * 60)

    if passes_strict:
        print(f"\nSources that SHOULD have been JESTER_A ({len(passes_strict)}):")
        for p in passes_strict[:20]:
            print(f"  - {p['domain']} ({p['length']} bytes)")
        if len(passes_strict) > 20:
            print(f"  ... and {len(passes_strict) - 20} more")

    return stats, passes_strict


if __name__ == "__main__":
    stats, passes = asyncio.run(verify_with_strict_criteria())
