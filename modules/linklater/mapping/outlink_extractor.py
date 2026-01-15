"""
Firecrawl Outlink Discovery
============================
Extract outbound links from URLs using Firecrawl's structured links format.

Uses Firecrawl's formats=["links"] for clean, structured link extraction
without HTML parsing overhead.

Usage:
    from modules.linklater.mapping.outlink_extractor import OutlinkExtractor

    extractor = OutlinkExtractor()

    # Get all external domains from a page
    domains = await extractor.get_external_domains("https://example.com")
    # Returns: {"nytimes.com", "github.com", "wikipedia.org", ...}

    # Get all links (not just domains)
    links = await extractor.extract_outlinks("https://example.com")
    # Returns: ["https://nytimes.com/article", "https://github.com/user/repo", ...]
"""

import os
import asyncio
import httpx
from typing import List, Set, Optional, Dict, Any
from urllib.parse import urlparse
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class OutlinkExtractor:
    """
    Extract outbound links using Firecrawl's structured links API.

    Advantages over HTML parsing:
    - No BeautifulSoup parsing needed
    - Structured JSON response
    - Handles JavaScript-rendered links
    - Cleaner, more reliable extraction
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize outlink extractor.

        Args:
            api_key: Firecrawl API key (reads from env if not provided)
        """
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY") or os.getenv("FC_API_KEY")

        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in environment")

        self.base_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
        api_version = os.getenv("FIRECRAWL_API_VERSION", "v2").lower()
        self.scrape_endpoint = f"{self.base_url}/{api_version}/scrape"

        logger.info(f"OutlinkExtractor initialized (endpoint: {self.scrape_endpoint})")

    def _extract_domain(self, url: str) -> Optional[str]:
        """
        Extract clean domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain without www. prefix (e.g., "example.com")
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            return domain if domain else None
        except Exception:
            return None

    async def extract_outlinks(
        self,
        url: str,
        timeout: int = 30,
        wait_for: int = 0
    ) -> List[str]:
        """
        Extract all outbound links from a URL.

        Args:
            url: Source URL to extract links from
            timeout: Request timeout in seconds
            wait_for: Time to wait for page load (ms)

        Returns:
            List of all outbound URLs
        """
        try:
            payload = {
                "url": url,
                "formats": ["links"],  # Only request links, no content
                "onlyMainContent": False,  # Get ALL links, not just main content
                "waitFor": wait_for,
                "timeout": timeout * 1000,
                "skipTlsVerification": True,
                "blockAds": True
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                response = await client.post(
                    self.scrape_endpoint,
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"Firecrawl API error {response.status_code}: {response.text}")
                    return []

                data = response.json()

                if not data.get("success"):
                    logger.warning(f"Firecrawl scrape failed for {url}: {data.get('error')}")
                    return []

                # Extract links from response
                links = data.get("data", {}).get("links", [])

                logger.info(f"Extracted {len(links)} links from {url}")

                return links

        except Exception as e:
            logger.error(f"Failed to extract outlinks from {url}: {e}")
            return []

    async def get_external_domains(
        self,
        url: str,
        timeout: int = 30,
        wait_for: int = 0
    ) -> Set[str]:
        """
        Get all unique external domains linked from a URL.

        Args:
            url: Source URL
            timeout: Request timeout in seconds
            wait_for: Time to wait for page load (ms)

        Returns:
            Set of external domain names (excluding source domain)
        """
        # Extract source domain
        source_domain = self._extract_domain(url)

        if not source_domain:
            logger.error(f"Invalid URL: {url}")
            return set()

        # Get all outlinks
        links = await self.extract_outlinks(url, timeout, wait_for)

        # Extract unique external domains
        external_domains = set()

        for link in links:
            target_domain = self._extract_domain(link)

            # Only include external domains (not same domain)
            if target_domain and target_domain != source_domain:
                external_domains.add(target_domain)

        logger.info(f"Found {len(external_domains)} unique external domains from {url}")

        return external_domains

    async def batch_extract_domains(
        self,
        urls: List[str],
        max_concurrent: int = 5,
        timeout: int = 30
    ) -> Dict[str, Set[str]]:
        """
        Extract external domains from multiple URLs concurrently.

        Args:
            urls: List of source URLs
            max_concurrent: Max concurrent requests
            timeout: Request timeout per URL

        Returns:
            Dict mapping source_url -> set of external domains
        """
        results = {}

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_with_semaphore(url: str):
            async with semaphore:
                domains = await self.get_external_domains(url, timeout)
                results[url] = domains

        # Run all extractions concurrently (with semaphore limit)
        await asyncio.gather(*[extract_with_semaphore(url) for url in urls])

        return results


# Convenience functions
_extractor = None

def _get_extractor() -> OutlinkExtractor:
    """Get or create global extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = OutlinkExtractor()
    return _extractor


async def extract_outlinks(url: str) -> List[str]:
    """Extract all outlinks from URL (convenience function)."""
    extractor = _get_extractor()
    return await extractor.extract_outlinks(url)


async def get_external_domains(url: str) -> Set[str]:
    """Get external domains from URL (convenience function)."""
    extractor = _get_extractor()
    return await extractor.get_external_domains(url)


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract outlinks using Firecrawl")
    parser.add_argument("url", help="URL to extract outlinks from")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--wait", type=int, default=0, help="Wait for page load (ms)")
    parser.add_argument("--domains-only", action="store_true", help="Show only unique domains")

    args = parser.parse_args()

    async def main():
        extractor = OutlinkExtractor()

        if args.domains_only:
            print(f"\n🔍 Extracting external domains from: {args.url}\n")
            domains = await extractor.get_external_domains(args.url, args.timeout, args.wait)

            print(f"Found {len(domains)} unique external domains:\n")
            for domain in sorted(domains):
                print(f"  • {domain}")
        else:
            print(f"\n🔍 Extracting all outlinks from: {args.url}\n")
            links = await extractor.extract_outlinks(args.url, args.timeout, args.wait)

            print(f"Found {len(links)} outlinks:\n")
            for link in links:
                print(f"  • {link}")

    asyncio.run(main())
