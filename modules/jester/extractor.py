"""
JESTER Extractor - Unified scrape + extract
============================================

Uses JESTER scraping chain then extracts:
- Outlinks (external links)
- Internal links
- Entities (via GlinerExtractor)

Usage:
    from jester.extractor import JesterExtractor

    extractor = JesterExtractor()
    result = await extractor.extract_outlinks("https://example.com")
    # Returns: ["https://nytimes.com/...", "https://github.com/..."]
"""

import asyncio
import logging
import re
from typing import List, Set, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass, field

from .scraper import Jester, JesterResult, JesterMethod

logger = logging.getLogger("JESTER.extractor")


@dataclass
class ExtractionResult:
    """Result from jester extraction."""
    url: str
    outlinks: List[str] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    scrape_method: Optional[str] = None
    scrape_latency_ms: int = 0
    error: Optional[str] = None


class JesterExtractor:
    """
    JESTER-based extraction.

    Scrapes via JESTER chain (A→B→C→D→Firecrawl→BrightData)
    then extracts links and entities from HTML.
    """

    # URL pattern for link extraction
    URL_PATTERN = re.compile(
        r'href=["\']([^"\']+)["\']',
        re.IGNORECASE
    )

    # Skip patterns for non-content links
    SKIP_PATTERNS = [
        'javascript:', 'mailto:', 'tel:', '#',
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.woff',
        'facebook.com/sharer', 'twitter.com/intent', 'twitter.com/share',
        'linkedin.com/share', 'pinterest.com/pin', 'reddit.com/submit',
    ]

    def __init__(self, jester: Optional[Jester] = None):
        """
        Initialize extractor.

        Args:
            jester: Optional Jester instance (creates one if not provided)
        """
        self.jester = jester or Jester()

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract clean domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain if domain else None
        except Exception:
            return None

    def _extract_links_from_html(
        self,
        html: str,
        source_url: str,
    ) -> Tuple[List[str], List[str]]:
        """
        Extract links from HTML.

        Args:
            html: HTML content
            source_url: URL the HTML was fetched from

        Returns:
            Tuple of (outlinks, internal_links)
        """
        source_domain = self._extract_domain(source_url)
        if not source_domain:
            return [], []

        outlinks: Set[str] = set()
        internal: Set[str] = set()

        for match in self.URL_PATTERN.finditer(html):
            href = match.group(1)

            # Skip non-http links and common non-content
            if not href or any(skip in href.lower() for skip in self.SKIP_PATTERNS):
                continue

            # Resolve relative URLs
            if not href.startswith(('http://', 'https://')):
                try:
                    href = urljoin(source_url, href)
                except Exception:
                    continue

            # Must be http/https
            if not href.startswith(('http://', 'https://')):
                continue

            try:
                link_domain = self._extract_domain(href)
                if not link_domain:
                    continue

                # Classify as internal or external
                if link_domain == source_domain or link_domain.endswith('.' + source_domain):
                    internal.add(href)
                else:
                    outlinks.add(href)
            except Exception:
                continue

        return sorted(outlinks), sorted(internal)

    async def extract(
        self,
        url: str,
        extract_entities: bool = False,
    ) -> ExtractionResult:
        """
        Scrape URL via JESTER and extract links/entities.

        Args:
            url: URL to scrape and extract from
            extract_entities: Whether to also extract entities (slower)

        Returns:
            ExtractionResult with outlinks, internal_links, entities
        """
        result = ExtractionResult(url=url)

        try:
            # Scrape via JESTER chain
            scrape_result: JesterResult = await self.jester.scrape(url)

            if not scrape_result.html or scrape_result.method == JesterMethod.BLOCKED:
                result.error = scrape_result.error or "Scrape failed"
                return result

            result.scrape_method = scrape_result.method.value
            result.scrape_latency_ms = scrape_result.latency_ms

            # Extract links
            outlinks, internal = self._extract_links_from_html(scrape_result.html, url)
            result.outlinks = outlinks
            result.internal_links = internal

            # Optionally extract entities
            if extract_entities:
                try:
                    from .gliner_extractor import GlinerExtractor
                    entity_extractor = GlinerExtractor()
                    # Strip HTML for entity extraction
                    text = re.sub(r'<[^>]+>', ' ', scrape_result.html)
                    text = re.sub(r'\s+', ' ', text).strip()
                    result.entities = entity_extractor.extract(text)
                except Exception as e:
                    logger.warning(f"Entity extraction failed: {e}")

            logger.info(f"[JesterExtractor] {url}: {len(outlinks)} outlinks, {len(internal)} internal via {result.scrape_method}")
            return result

        except Exception as e:
            result.error = str(e)
            logger.error(f"[JesterExtractor] Failed: {e}")
            return result

    async def extract_outlinks(self, url: str) -> List[str]:
        """
        Convenience method to just get outlinks.

        Args:
            url: URL to scrape

        Returns:
            List of external outlink URLs
        """
        result = await self.extract(url, extract_entities=False)
        return result.outlinks

    async def get_external_domains(self, url: str) -> Set[str]:
        """
        Get unique external domains linked from URL.

        Args:
            url: URL to scrape

        Returns:
            Set of external domain names
        """
        outlinks = await self.extract_outlinks(url)
        domains = set()
        for link in outlinks:
            domain = self._extract_domain(link)
            if domain:
                domains.add(domain)
        return domains

    async def batch_extract_outlinks(
        self,
        urls: List[str],
        max_concurrent: int = 10,
    ) -> Dict[str, List[str]]:
        """
        Extract outlinks from multiple URLs concurrently.

        Args:
            urls: List of URLs to process
            max_concurrent: Max concurrent extractions

        Returns:
            Dict mapping url -> list of outlinks
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results: Dict[str, List[str]] = {}

        async def extract_one(url: str):
            async with semaphore:
                outlinks = await self.extract_outlinks(url)
                results[url] = outlinks

        await asyncio.gather(*[extract_one(url) for url in urls], return_exceptions=True)
        return results


# Module-level convenience
_extractor: Optional[JesterExtractor] = None

def get_extractor() -> JesterExtractor:
    """Get or create global JesterExtractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = JesterExtractor()
    return _extractor


async def extract_outlinks(url: str) -> List[str]:
    """Extract outlinks from URL (convenience function)."""
    return await get_extractor().extract_outlinks(url)


async def get_external_domains(url: str) -> Set[str]:
    """Get external domains from URL (convenience function)."""
    return await get_extractor().get_external_domains(url)
