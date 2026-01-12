"""
CC Index Client - Fast Page URL Discovery

Uses Common Crawl Index API to get page URLs from specific domains
WITHOUT downloading WAT files.

This is the "sniper" approach - ~800ms per domain query.
No WAT file downloads needed to get page URLs.

For anchor text extraction, use cc_index_backlinks.py which downloads WAT files.
"""

import asyncio
import aiohttp
import json
from typing import List, Dict, Optional
from dataclasses import dataclass


# CC Index API base
CC_INDEX_BASE = "https://index.commoncrawl.org"

# Known good archives
ARCHIVES = [
    "CC-MAIN-2024-10",
    "CC-MAIN-2024-18",
    "CC-MAIN-2024-22",
    "CC-MAIN-2024-26",
    "CC-MAIN-2024-30",
]


@dataclass
class PageRecord:
    """A page record from CC Index."""
    url: str
    domain: str
    filename: str
    offset: int
    length: int

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "filename": self.filename,
            "offset": self.offset,
            "length": self.length,
        }


class CCIndexClient:
    """
    Client for Common Crawl Index API.

    Gets page URLs instantly (~800ms per domain) without downloading WAT files.
    """

    def __init__(self, archive: str = "CC-MAIN-2024-10"):
        """
        Initialize CC Index client.

        Args:
            archive: CC archive name (e.g., "CC-MAIN-2024-10")
        """
        self.archive = archive
        self.base_url = f"{CC_INDEX_BASE}/{archive}-index"

    async def get_pages_from_domain(
        self,
        domain: str,
        limit: int = 100,
        filter_keywords: Optional[List[str]] = None
    ) -> List[PageRecord]:
        """
        Get all pages from a specific domain in the CC archive.

        FAST: ~800ms per domain query. No WAT downloads.

        Args:
            domain: Domain to search (e.g., "shopify.com")
            limit: Max pages to return
            filter_keywords: Only include URLs containing these keywords

        Returns:
            List of PageRecord objects with URL, filename, offset, length
        """
        # Query CC Index for all pages from this domain
        url = f"{self.base_url}?url={domain}/*&output=json&fl=url,filename,offset,length&limit={limit}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        print(f"[CCIndex] HTTP {resp.status} for {domain}")
                        return []

                    text = await resp.text()
                    records = []

                    for line in text.strip().split('\n'):
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            page_url = data.get("url", "")

                            # Apply keyword filter if specified
                            if filter_keywords:
                                if not any(kw.lower() in page_url.lower() for kw in filter_keywords):
                                    continue

                            records.append(PageRecord(
                                url=page_url,
                                domain=domain,
                                filename=data.get("filename", ""),
                                offset=int(data.get("offset", 0)),
                                length=int(data.get("length", 0)),
                            ))
                        except (json.JSONDecodeError, ValueError):
                            continue

                    return records[:limit]

            except Exception as e:
                print(f"[CCIndex] Error querying {domain}: {e}")
                return []

    async def get_pages_from_domains_parallel(
        self,
        domains: List[str],
        limit_per_domain: int = 50,
        filter_keywords: Optional[List[str]] = None,
        max_concurrent: int = 10
    ) -> List[PageRecord]:
        """
        Get pages from multiple domains in parallel.

        FAST: ~800ms total for 10 domains (parallel queries).

        Args:
            domains: List of domains to query
            limit_per_domain: Max pages per domain
            filter_keywords: Only include URLs containing these keywords
            max_concurrent: Max concurrent API requests

        Returns:
            Combined list of PageRecord objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def query_domain(domain: str) -> List[PageRecord]:
            async with semaphore:
                return await self.get_pages_from_domain(
                    domain, limit_per_domain, filter_keywords
                )

        # Query all domains in parallel
        results = await asyncio.gather(
            *[query_domain(d) for d in domains],
            return_exceptions=True
        )

        # Flatten results
        all_pages = []
        for result in results:
            if isinstance(result, list):
                all_pages.extend(result)

        return all_pages

    async def find_pages_linking_to(
        self,
        target_domain: str,
        source_domains: List[str],
        limit_per_source: int = 50,
        max_concurrent: int = 10
    ) -> List[PageRecord]:
        """
        Find pages from source_domains that MIGHT link to target_domain.

        Uses URL keyword filtering to find likely candidates.
        Returns page URLs - actual link verification requires WAT parsing.

        FAST: ~800ms for 10 source domains (parallel).

        Args:
            target_domain: Domain being linked TO
            source_domains: Domains to search for pages
            limit_per_source: Max pages per source domain
            max_concurrent: Max concurrent API requests

        Returns:
            List of PageRecord objects (potential referring pages)
        """
        # Filter for pages whose URLs might mention the target
        # This is a heuristic - actual links need WAT verification
        filter_keywords = [target_domain.split('.')[0]]  # e.g., "soax" from "soax.com"

        return await self.get_pages_from_domains_parallel(
            domains=source_domains,
            limit_per_domain=limit_per_source,
            filter_keywords=filter_keywords,
            max_concurrent=max_concurrent
        )


# Convenience function
async def get_pages_from_domain(
    domain: str,
    archive: str = "CC-MAIN-2024-10",
    limit: int = 100
) -> List[PageRecord]:
    """
    Get pages from a domain using CC Index API.

    INSTANT: ~800ms per domain, no WAT downloads.

    Args:
        domain: Domain to query
        archive: CC archive name
        limit: Max pages

    Returns:
        List of PageRecord objects
    """
    client = CCIndexClient(archive)
    return await client.get_pages_from_domain(domain, limit)


# CLI test
if __name__ == "__main__":
    import sys
    import time

    async def main():
        domain = sys.argv[1] if len(sys.argv) > 1 else "shopify.com"

        print(f"\n{'='*60}")
        print(f"CC Index Client - Fast Page Discovery")
        print(f"{'='*60}")
        print(f"Domain: {domain}")
        print(f"{'='*60}\n")

        client = CCIndexClient()

        start = time.time()
        pages = await client.get_pages_from_domain(domain, limit=10)
        elapsed = (time.time() - start) * 1000

        print(f"Query time: {elapsed:.0f}ms")
        print(f"Pages found: {len(pages)}")
        print()

        for page in pages[:5]:
            print(f"  {page.url[:80]}...")

    asyncio.run(main())
