"""
LINKLATER PRIORITY SCRAPER
==========================

Priority scraper for bang search results with multi-source fallback chain:
1. Self-hosted Firecrawl (fastest, highest quality)
2. Common Crawl (free, bulk archives)
3. Wayback Machine (free, historical)
4. Scrapy (last resort, direct scraping)

Includes GPT-5-nano snippet cleanup for improved result quality.

Usage:
    scraper = LinkLaterPriorityScraper()
    results = await scraper.scrape_bang_results(bang_results)
"""

from __future__ import annotations

import os
import asyncio
import aiohttp
import json
import re
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import hashlib

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Import CC-first scraper for archive fallback
import sys
sys.path.insert(0, str(PROJECT_ROOT / 'python-backend'))

try:
    from modules.cc_content.cc_first_scraper import CCFirstScraper, ScrapeResult
    CC_SCRAPER_AVAILABLE = True
except ImportError:
    CC_SCRAPER_AVAILABLE = False
    print("[linklater_priority] Warning: CCFirstScraper not available")


@dataclass
class PriorityScrapeResult:
    """Result from priority scraper with source chain info."""
    url: str
    content: str
    snippet: str
    source: str  # 'self_firecrawl', 'cc', 'wayback', 'scrapy', 'failed'
    source_chain: List[str] = field(default_factory=list)  # Order of sources tried
    timestamp: Optional[str] = None
    cleaned: bool = False  # Whether snippet was cleaned by GPT-5-nano
    entities: Dict[str, List[str]] = field(default_factory=dict)
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class ScrapeStats:
    """Statistics for scraping session."""
    self_firecrawl_hits: int = 0
    cc_hits: int = 0
    wayback_hits: int = 0
    scrapy_hits: int = 0
    failures: int = 0
    cleaned_snippets: int = 0
    total_time: float = 0.0


class LinkLaterPriorityScraper:
    """
    Priority scraper with multi-source fallback chain for bang results.

    Features:
    - Self-hosted Firecrawl for highest quality (if available)
    - CC/Wayback fallback for free bulk scraping
    - GPT-5-nano snippet cleanup for better quality
    - Parallel processing with configurable concurrency
    """

    def __init__(
        self,
        self_hosted_firecrawl_url: Optional[str] = None,
        firecrawl_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        timeout: float = 20.0,
        max_concurrent: int = 20,
        enable_snippet_cleanup: bool = True,
    ):
        """
        Initialize priority scraper.

        Args:
            self_hosted_firecrawl_url: URL for self-hosted Firecrawl (e.g., http://localhost:3002)
            firecrawl_api_key: Fallback to cloud Firecrawl if self-hosted fails
            openai_api_key: For GPT-5-nano snippet cleanup
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests
            enable_snippet_cleanup: Whether to clean snippets with GPT-5-nano
        """
        self.self_hosted_url = self_hosted_firecrawl_url or os.getenv('SELF_HOSTED_FIRECRAWL_URL')
        self.firecrawl_key = firecrawl_api_key or os.getenv('FIRECRAWL_API_KEY')
        self.openai_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=5.0)
        self.max_concurrent = max_concurrent
        self.enable_snippet_cleanup = enable_snippet_cleanup
        self.stats = ScrapeStats()
        self._session: Optional[aiohttp.ClientSession] = None
        self._cc_scraper: Optional[CCFirstScraper] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self.max_concurrent * 2,
                limit_per_host=10,
                keepalive_timeout=30,
            )
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
            )
        return self._session

    async def _get_cc_scraper(self) -> Optional[CCFirstScraper]:
        """Get CC-first scraper instance."""
        if not CC_SCRAPER_AVAILABLE:
            return None
        if self._cc_scraper is None:
            self._cc_scraper = CCFirstScraper(
                firecrawl_api_key=self.firecrawl_key,
                cc_only=False,  # Allow Firecrawl fallback in CC scraper too
            )
        return self._cc_scraper

    async def close(self):
        """Close all sessions."""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._cc_scraper:
            await self._cc_scraper.close()

    async def scrape_self_hosted_firecrawl(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Try self-hosted Firecrawl first (fastest, highest quality).

        Args:
            url: URL to scrape

        Returns:
            Dict with markdown content or None if fails
        """
        if not self.self_hosted_url:
            return None

        session = await self._get_session()

        try:
            # Self-hosted Firecrawl API
            async with session.post(
                f"{self.self_hosted_url}/v1/scrape",
                headers={'Content-Type': 'application/json'},
                json={
                    'url': url,
                    'formats': ['markdown'],
                    'onlyMainContent': True,
                },
                timeout=aiohttp.ClientTimeout(total=15.0)  # Faster timeout for self-hosted
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success'):
                        return {
                            'content': data.get('data', {}).get('markdown', ''),
                            'source': 'self_firecrawl',
                            'timestamp': datetime.utcnow().isoformat(),
                        }
        except asyncio.TimeoutError:
            pass  # Fall through to next source
        except Exception as e:
            print(f"[linklater_priority] Self-hosted Firecrawl error: {e}")

        return None

    async def scrape_with_cc_chain(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fallback to CC-first scraper (CC → Wayback → cloud Firecrawl).

        Args:
            url: URL to scrape

        Returns:
            Dict with content or None if fails
        """
        cc_scraper = await self._get_cc_scraper()
        if not cc_scraper:
            return None

        result = await cc_scraper.get_content(url)

        if result.content and result.source != 'failed':
            return {
                'content': result.content,
                'source': result.source,  # 'cc', 'wayback', or 'firecrawl'
                'timestamp': result.timestamp,
            }

        return None

    async def scrape_with_scrapy(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Last resort: Direct scraping with basic HTML parsing.

        Args:
            url: URL to scrape

        Returns:
            Dict with content or None if fails
        """
        session = await self._get_session()

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }

            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Basic HTML to text extraction
                    content = self._html_to_text(html)
                    if content:
                        return {
                            'content': content,
                            'source': 'scrapy',
                            'timestamp': datetime.utcnow().isoformat(),
                        }
        except Exception as e:
            print(f"[linklater_priority] Scrapy error for {url}: {e}")

        return None

    def _html_to_text(self, html: str) -> str:
        """Basic HTML to text conversion."""
        import re

        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text[:50000]  # Limit size

    async def clean_snippet_with_gpt5nano(self, snippet: str, query: str) -> str:
        """
        Clean and improve snippet quality using GPT-5-nano.

        Args:
            snippet: Raw snippet text
            query: Original search query

        Returns:
            Cleaned snippet or original if cleaning fails
        """
        if not self.openai_key or not self.enable_snippet_cleanup:
            return snippet

        if not snippet or len(snippet) < 10:
            return snippet

        session = await self._get_session()

        try:
            prompt = f"""Clean this search result snippet. Remove navigation, boilerplate, and formatting artifacts.
Keep only the relevant text mentioning "{query}". Output the cleaned snippet only, max 300 chars.

Snippet: {snippet[:500]}"""

            async with session.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openai_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'gpt-4.1-nano',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 150,
                    'temperature': 0.1,
                },
                timeout=aiohttp.ClientTimeout(total=5.0)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cleaned = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if cleaned and len(cleaned) > 20:
                        self.stats.cleaned_snippets += 1
                        return cleaned.strip()
        except Exception as e:
            pass  # Return original snippet on error

        return snippet

    async def scrape_url(self, url: str, query: str = '', on_progress: Optional[Callable[[str], None]] = None) -> PriorityScrapeResult:
        """
        Scrape a single URL with full fallback chain.

        Args:
            url: URL to scrape
            query: Original search query (for snippet cleanup)
            on_progress: Optional callback for log messages

        Returns:
            PriorityScrapeResult with content and source chain info
        """
        start_time = time.time()
        source_chain = []

        # Try sources in priority order

        # 1. Self-hosted Firecrawl
        if on_progress: on_progress(f"Trying Firecrawl")
        source_chain.append('self_firecrawl')
        result = await self.scrape_self_hosted_firecrawl(url)
        if result:
            self.stats.self_firecrawl_hits += 1
            content = result['content']
            snippet = content[:500] if content else ''

            # Clean snippet with GPT-5-nano
            if self.enable_snippet_cleanup and snippet:
                snippet = await self.clean_snippet_with_gpt5nano(snippet, query)

            return PriorityScrapeResult(
                url=url,
                content=content,
                snippet=snippet,
                source='self_firecrawl',
                source_chain=source_chain,
                timestamp=result.get('timestamp'),
                cleaned=self.stats.cleaned_snippets > 0,
                latency_ms=int((time.time() - start_time) * 1000),
            )
        
        if on_progress: on_progress(f"Firecrawl failed, trying Archive/CC")

        # 2. CC-first chain (CC → Wayback → cloud Firecrawl)
        source_chain.append('cc_chain')
        result = await self.scrape_with_cc_chain(url)
        if result:
            source = result['source']
            if source == 'cc':
                self.stats.cc_hits += 1
            elif source == 'wayback':
                self.stats.wayback_hits += 1
            else:
                self.stats.self_firecrawl_hits += 1  # Cloud Firecrawl

            content = result['content']
            snippet = content[:500] if content else ''

            # Clean snippet with GPT-5-nano
            if self.enable_snippet_cleanup and snippet:
                snippet = await self.clean_snippet_with_gpt5nano(snippet, query)

            return PriorityScrapeResult(
                url=url,
                content=content,
                snippet=snippet,
                source=source,
                source_chain=source_chain,
                timestamp=result.get('timestamp'),
                cleaned=self.stats.cleaned_snippets > 0,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        if on_progress: on_progress(f"Archive failed, trying Scrapy")

        # 3. Direct Scrapy (last resort)
        source_chain.append('scrapy')
        result = await self.scrape_with_scrapy(url)
        if result:
            self.stats.scrapy_hits += 1
            content = result['content']
            snippet = content[:500] if content else ''

            # Clean snippet with GPT-5-nano
            if self.enable_snippet_cleanup and snippet:
                snippet = await self.clean_snippet_with_gpt5nano(snippet, query)

            return PriorityScrapeResult(
                url=url,
                content=content,
                snippet=snippet,
                source='scrapy',
                source_chain=source_chain,
                timestamp=result.get('timestamp'),
                cleaned=self.stats.cleaned_snippets > 0,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        if on_progress: on_progress(f"All sources failed")

        # All sources failed
        self.stats.failures += 1
        return PriorityScrapeResult(
            url=url,
            content='',
            snippet='',
            source='failed',
            source_chain=source_chain,
            error='All scraping sources failed',
            latency_ms=int((time.time() - start_time) * 1000),
        )

    async def scrape_bang_results(
        self,
        bang_results: List[Dict[str, Any]],
        query: str = '',
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> List[PriorityScrapeResult]:
        """
        Scrape multiple bang search results with priority chain.

        Args:
            bang_results: List of bang search results with 'url' field
            query: Original search query (for snippet cleanup)
            progress_callback: Optional callback(completed, total, url)
            log_callback: Optional callback(message) for granular logs

        Returns:
            List of PriorityScrapeResult objects
        """
        start_time = time.time()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: List[PriorityScrapeResult] = []
        completed = 0

        async def scrape_one(item: Dict[str, Any]) -> PriorityScrapeResult:
            nonlocal completed
            url = item.get('url', '')

            async with semaphore:
                result = await self.scrape_url(url, query, on_progress=log_callback)
                completed += 1

                if progress_callback:
                    progress_callback(completed, len(bang_results), url)

                return result

        # Extract unique URLs
        seen_urls = set()
        items_to_scrape = []
        for item in bang_results:
            url = item.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                items_to_scrape.append(item)

        # Scrape all URLs in parallel
        tasks = [scrape_one(item) for item in items_to_scrape]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                print(f"[linklater_priority] Task exception: {r}")
                continue
            valid_results.append(r)

        self.stats.total_time = time.time() - start_time
        return valid_results

    def get_stats(self) -> Dict[str, Any]:
        """Get scraping statistics."""
        total = (self.stats.self_firecrawl_hits + self.stats.cc_hits +
                 self.stats.wayback_hits + self.stats.scrapy_hits + self.stats.failures)

        return {
            'self_firecrawl_hits': self.stats.self_firecrawl_hits,
            'cc_hits': self.stats.cc_hits,
            'wayback_hits': self.stats.wayback_hits,
            'scrapy_hits': self.stats.scrapy_hits,
            'failures': self.stats.failures,
            'cleaned_snippets': self.stats.cleaned_snippets,
            'total_urls': total,
            'success_rate': f"{((total - self.stats.failures) / total * 100):.1f}%" if total > 0 else "0%",
            'archive_rate': f"{((self.stats.cc_hits + self.stats.wayback_hits) / total * 100):.1f}%" if total > 0 else "0%",
            'total_time': f"{self.stats.total_time:.2f}s",
        }


# Convenience functions for quick usage

async def scrape_bang_results_priority(
    bang_results: List[Dict[str, Any]],
    query: str = '',
) -> List[PriorityScrapeResult]:
    """
    Quick function to scrape bang results with priority chain.

    Args:
        bang_results: List of bang search results
        query: Original search query

    Returns:
        List of PriorityScrapeResult objects
    """
    scraper = LinkLaterPriorityScraper()
    try:
        return await scraper.scrape_bang_results(bang_results, query)
    finally:
        await scraper.close()


def normalize_priority_result_to_search_result(result: PriorityScrapeResult, query: str) -> Dict[str, Any]:
    """
    Convert PriorityScrapeResult to standard search result format for grid display.

    Args:
        result: PriorityScrapeResult from scraping
        query: Original search query

    Returns:
        Dict in standard search result format
    """
    # Extract domain from URL
    from urllib.parse import urlparse
    parsed = urlparse(result.url)
    domain = parsed.netloc.lower().replace('www.', '')

    return {
        'url': result.url,
        'title': f"Content from {domain}",
        'snippet': result.snippet or f"Content scraped via {result.source}",
        'content': result.content, # Include full content for Corpus indexing
        'source': f'linklater:{result.source}',
        'engines': [result.source.upper()],
        'category': 'scraped',
        'timestamp': result.timestamp,
        'metadata': {
            'query': query,
            'scrape_source': result.source,
            'source_chain': result.source_chain,
            'latency_ms': result.latency_ms,
            'cleaned': result.cleaned,
        },
        'entities': result.entities,
    }
