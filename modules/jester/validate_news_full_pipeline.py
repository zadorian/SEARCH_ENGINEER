#!/usr/bin/env python3
"""
Full Pipeline News Source Validator

Tests the COMPLETE workflow:
1. Search with real keyword (not just "test")
2. Parse search results to extract article URLs
3. Check if articles contain exact phrase
4. Pull full article content

This validates the ACTUAL use case, not just "can we load the page."

Usage:
    python validate_news_full_pipeline.py --sample 20
    python validate_news_full_pipeline.py --domain bbc.co.uk
    python validate_news_full_pipeline.py --method JESTER_A --sample 50
"""

import asyncio
import json
import logging
import argparse
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)
logger = logging.getLogger("FullPipelineValidator")

# Paths
MATRIX_DIR = PROJECT_ROOT / "input_output" / "matrix"
CLASSIFICATION_PATH = MATRIX_DIR / "news_scrape_classification.json"
VALIDATION_OUTPUT_PATH = MATRIX_DIR / "news_full_pipeline_validation.json"

# Go binaries
GO_BIN_DIR = PROJECT_ROOT / "BACKEND" / "modules" / "LINKLATER" / "scraping" / "web" / "go" / "bin"
COLLY_BIN = GO_BIN_DIR / "colly_crawler"
ROD_BIN = GO_BIN_DIR / "rod_crawler"

# Test keywords - real investigative terms that should appear in news
TEST_KEYWORDS = [
    "corruption scandal",
    "fraud investigation",
    "money laundering",
    "sanctions",
    "bankruptcy",
]

# Common search result selectors (fallback patterns)
RESULT_SELECTORS = [
    "article a[href]",
    ".search-result a[href]",
    ".result a[href]",
    ".article-link",
    "h2 a[href]",
    "h3 a[href]",
    ".headline a[href]",
    ".title a[href]",
    ".story a[href]",
    ".news-item a[href]",
    ".list-item a[href]",
    "[class*='result'] a[href]",
    "[class*='article'] a[href]",
    "[class*='story'] a[href]",
]


@dataclass
class ArticleResult:
    """A single article extracted from search results."""
    url: str
    title: str = ""
    contains_phrase: bool = False
    content_length: int = 0
    extracted_content: str = ""
    error: Optional[str] = None


@dataclass
class PipelineValidation:
    """Full pipeline validation result for a news source."""
    source_id: str
    domain: str
    jurisdiction: str
    original_method: str
    keyword_used: str

    # Step 1: Search
    search_success: bool = False
    search_url: str = ""
    search_html_length: int = 0

    # Step 2: Parse results
    articles_found: int = 0
    article_urls: List[str] = field(default_factory=list)

    # Step 3: Filter by phrase
    articles_with_phrase: int = 0

    # Step 4: Full content extraction
    full_content_extracted: int = 0
    sample_articles: List[Dict] = field(default_factory=list)

    # Overall
    pipeline_success: bool = False
    validated_method: str = ""  # Actual working method after validation
    error: Optional[str] = None
    tested_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class FullPipelineValidator:
    """Validates news sources with complete two-step workflow."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self.brightdata_key = os.getenv("BRIGHTDATA_API_KEY")

    async def close(self):
        await self.client.aclose()

    def _build_search_url(self, domain: str, keyword: str) -> str:
        """Build search URL for a news domain."""
        # Common search URL patterns
        patterns = [
            f"https://www.{domain}/search?q={keyword.replace(' ', '+')}",
            f"https://{domain}/search?q={keyword.replace(' ', '+')}",
            f"https://www.{domain}/?s={keyword.replace(' ', '+')}",
            f"https://{domain}/?s={keyword.replace(' ', '+')}",
        ]
        return patterns[0]  # Start with most common

    async def _fetch_httpx(self, url: str) -> Tuple[bool, str, int]:
        """Fetch with httpx (JESTER_A)."""
        try:
            resp = await self.client.get(url)
            if resp.status_code == 200:
                return True, resp.text, len(resp.text)
        except Exception as e:
            pass
        return False, "", 0

    async def _fetch_colly(self, url: str) -> Tuple[bool, str, int]:
        """Fetch with Colly Go binary (JESTER_B)."""
        if not COLLY_BIN.exists():
            return False, "", 0
        try:
            result = await asyncio.create_subprocess_exec(
                str(COLLY_BIN), "test", url,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=30)
            if result.returncode == 0 and stdout:
                output = stdout.decode("utf-8", errors="ignore")
                json_start = output.find('{')
                json_end = output.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(output[json_start:json_end])
                    content = data.get("content", "")
                    if data.get("status_code") == 200 and len(content) > 500:
                        return True, content, len(content)
        except Exception:
            pass
        return False, "", 0

    async def _fetch_rod(self, url: str) -> Tuple[bool, str, int]:
        """Fetch with Rod Go binary (JESTER_C) - handles JS."""
        if not ROD_BIN.exists():
            return False, "", 0
        try:
            result = await asyncio.create_subprocess_exec(
                str(ROD_BIN), "test", url,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=45)
            if result.returncode == 0 and stdout:
                output = stdout.decode("utf-8", errors="ignore")
                json_start = output.find('{')
                json_end = output.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(output[json_start:json_end])
                    content = data.get("content", "")
                    if data.get("status_code") == 200 and len(content) > 500:
                        return True, content, len(content)
        except Exception:
            pass
        return False, "", 0

    async def _fetch_firecrawl(self, url: str) -> Tuple[bool, str, int]:
        """Fetch with Firecrawl API."""
        if not self.firecrawl_key:
            return False, "", 0
        try:
            resp = await self.client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {self.firecrawl_key}"},
                json={"url": url, "formats": ["html"]},
                timeout=30.0
            )
            if resp.status_code == 200:
                data = resp.json()
                html = data.get("data", {}).get("html", "")
                if len(html) > 500:
                    return True, html, len(html)
        except Exception:
            pass
        return False, "", 0

    def _extract_article_urls(self, html: str, base_url: str) -> List[str]:
        """Extract article URLs from search results HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        urls = set()

        # Try each selector pattern
        for selector in RESULT_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    href = el.get('href', '')
                    if href and not href.startswith('#') and not href.startswith('javascript:'):
                        # Make absolute URL
                        full_url = urljoin(base_url, href)
                        # Filter out non-article URLs
                        if self._is_likely_article(full_url, base_url):
                            urls.add(full_url)
            except Exception:
                continue

        return list(urls)[:20]  # Limit to 20 articles

    def _is_likely_article(self, url: str, base_url: str) -> bool:
        """Check if URL is likely an article (not navigation/category)."""
        parsed = urlparse(url)
        base_parsed = urlparse(base_url)

        # Must be same domain
        if parsed.netloc != base_parsed.netloc and not parsed.netloc.endswith(base_parsed.netloc):
            return False

        path = parsed.path.lower()

        # Skip navigation pages
        skip_patterns = [
            '/search', '/category/', '/tag/', '/author/', '/page/',
            '/about', '/contact', '/privacy', '/terms', '/login',
            '/subscribe', '/newsletter', '/rss', '/feed'
        ]
        if any(p in path for p in skip_patterns):
            return False

        # Likely article patterns
        article_patterns = [
            r'/\d{4}/',  # Year in URL
            r'/article/',
            r'/news/',
            r'/story/',
            r'/post/',
            r'-[a-z0-9]+$',  # Slug ending
        ]

        # Has date or slug pattern
        if any(re.search(p, path) for p in article_patterns):
            return True

        # Has sufficient path depth
        if path.count('/') >= 2:
            return True

        return False

    def _check_phrase_in_content(self, content: str, phrase: str) -> bool:
        """Check if exact phrase appears in content (case-insensitive)."""
        return phrase.lower() in content.lower()

    async def _fetch_with_method(self, url: str, method: str) -> Tuple[bool, str, int]:
        """Fetch URL using specified method."""
        if method == "JESTER_A":
            return await self._fetch_httpx(url)
        elif method == "JESTER_B":
            return await self._fetch_colly(url)
        elif method == "JESTER_C":
            return await self._fetch_rod(url)
        elif method == "FIRECRAWL":
            return await self._fetch_firecrawl(url)
        return False, "", 0

    async def validate_source(
        self,
        source: Dict,
        keyword: str = "corruption scandal"
    ) -> PipelineValidation:
        """Run full pipeline validation on a single source."""

        result = PipelineValidation(
            source_id=source.get("source_id", ""),
            domain=source.get("domain", ""),
            jurisdiction=source.get("jurisdiction", ""),
            original_method=source.get("method", ""),
            keyword_used=keyword,
            tested_at=datetime.now(UTC).isoformat()
        )

        domain = result.domain
        method = result.original_method

        # Step 1: Search
        search_url = self._build_search_url(domain, keyword)
        result.search_url = search_url

        success, html, length = await self._fetch_with_method(search_url, method)

        if not success:
            result.error = f"Search page fetch failed with {method}"
            return result

        result.search_success = True
        result.search_html_length = length

        # Step 2: Parse search results
        article_urls = self._extract_article_urls(html, search_url)
        result.articles_found = len(article_urls)
        result.article_urls = article_urls[:5]  # Store sample

        if not article_urls:
            result.error = "No article URLs found in search results"
            return result

        # Step 3 & 4: Check phrase and extract content (sample 3 articles)
        articles_with_phrase = 0
        full_content_count = 0
        sample_articles = []

        for url in article_urls[:5]:  # Test up to 5 articles
            article = ArticleResult(url=url)

            success, content, length = await self._fetch_with_method(url, method)

            if success and length > 1000:
                article.content_length = length
                article.extracted_content = content[:500]  # Sample
                full_content_count += 1

                # Check for phrase
                if self._check_phrase_in_content(content, keyword):
                    article.contains_phrase = True
                    articles_with_phrase += 1

                    # Extract title
                    soup = BeautifulSoup(content, 'html.parser')
                    title_el = soup.find('h1') or soup.find('title')
                    if title_el:
                        article.title = title_el.get_text(strip=True)[:100]
            else:
                article.error = "Failed to fetch article content"

            sample_articles.append({
                "url": article.url,
                "title": article.title,
                "contains_phrase": article.contains_phrase,
                "content_length": article.content_length,
                "error": article.error
            })

        result.articles_with_phrase = articles_with_phrase
        result.full_content_extracted = full_content_count
        result.sample_articles = sample_articles

        # Determine success
        if full_content_count >= 2 and articles_with_phrase >= 1:
            result.pipeline_success = True
            result.validated_method = method
        elif full_content_count >= 1:
            result.error = f"Content extracted but phrase not found (got {full_content_count} articles)"
        else:
            result.error = f"Failed to extract article content"

        return result


async def main():
    parser = argparse.ArgumentParser(description="Full pipeline news source validation")
    parser.add_argument("--sample", type=int, default=20, help="Number of sources to test")
    parser.add_argument("--domain", type=str, help="Test specific domain")
    parser.add_argument("--method", type=str, help="Filter by method (JESTER_A, JESTER_B, etc)")
    parser.add_argument("--keyword", type=str, default="corruption scandal", help="Search keyword")
    args = parser.parse_args()

    # Load classification
    with open(CLASSIFICATION_PATH) as f:
        data = json.load(f)

    sources = data.get("results", [])

    # Filter
    if args.domain:
        sources = [s for s in sources if args.domain in s.get("domain", "")]
    if args.method:
        sources = [s for s in sources if s.get("method") == args.method]

    # Exclude BLOCKED
    sources = [s for s in sources if s.get("method") != "BLOCKED"]

    # Sample
    import random
    if len(sources) > args.sample:
        sources = random.sample(sources, args.sample)

    print(f"\n{'='*60}")
    print(f"FULL PIPELINE VALIDATION")
    print(f"Testing {len(sources)} sources with keyword: \"{args.keyword}\"")
    print(f"{'='*60}\n")

    validator = FullPipelineValidator()
    results = []

    success_count = 0

    for i, source in enumerate(sources, 1):
        domain = source.get("domain", "")
        method = source.get("method", "")

        print(f"[{i}/{len(sources)}] {domain} ({method})...", end=" ", flush=True)

        try:
            result = await validator.validate_source(source, args.keyword)
            results.append(result.to_dict())

            if result.pipeline_success:
                success_count += 1
                print(f"✓ Found {result.articles_with_phrase} articles with phrase")
            else:
                print(f"✗ {result.error}")
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append({
                "source_id": source.get("source_id"),
                "domain": domain,
                "error": str(e),
                "pipeline_success": False
            })

        # Small delay to avoid hammering
        await asyncio.sleep(0.5)

    await validator.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"VALIDATION RESULTS")
    print(f"{'='*60}")
    print(f"  Sources tested: {len(results)}")
    print(f"  Pipeline success: {success_count} ({100*success_count/len(results):.1f}%)")
    print(f"  Pipeline failed: {len(results) - success_count}")
    print(f"{'='*60}\n")

    # Save results
    output = {
        "validated_at": datetime.now(UTC).isoformat(),
        "keyword": args.keyword,
        "total_tested": len(results),
        "success_count": success_count,
        "results": results
    }

    with open(VALIDATION_OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Results saved to: {VALIDATION_OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
