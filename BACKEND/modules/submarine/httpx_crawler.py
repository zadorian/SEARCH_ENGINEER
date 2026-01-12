"""
FAST httpx-based domain crawler.
Optimized for speed: short timeout, no delay, skip 404-heavy sites.
"""

import asyncio
import re
import httpx
from urllib.parse import urljoin, urlparse
from typing import AsyncGenerator, Set, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CrawledPage:
    url: str
    html: str
    text: str
    title: Optional[str]
    status_code: int
    depth: int
    links: list


async def crawl_domain_httpx(
    start_url: str,
    max_pages: int = 50,
    max_depth: int = 3,
    delay: float = 0.0,  # No delay for speed
    timeout: float = 5.0,  # Short timeout
) -> AsyncGenerator[CrawledPage, None]:
    """Fast domain crawler."""
    parsed = urlparse(start_url)
    base_domain = parsed.netloc.lower()

    visited: Set[str] = set()
    queue: list = [(start_url, 0)]
    pages_crawled = 0
    errors_404 = 0
    max_404 = 5  # Stop if too many 404s

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        verify=False,
    ) as client:
        while queue and pages_crawled < max_pages and errors_404 < max_404:
            url, depth = queue.pop(0)
            url = url.split("#")[0]

            if url in visited:
                continue
            visited.add(url)

            # Skip non-HTML extensions
            if any(url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.gif', '.css', '.js', '.ico', '.xml', '.json', '.zip', '.mp4', '.mp3']):
                continue

            try:
                resp = await client.get(url)

                if resp.status_code == 404:
                    errors_404 += 1
                    continue

                if resp.status_code != 200:
                    continue

                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    continue

                html = resp.text
                if len(html) < 100:
                    continue

                # Fast text extraction
                text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()

                title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
                title = title_match.group(1).strip() if title_match else None

                # Extract links
                links = []
                if depth < max_depth:
                    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
                        href = match.group(1)
                        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                            continue
                        full_url = urljoin(url, href)
                        parsed_link = urlparse(full_url)
                        if parsed_link.netloc.lower() == base_domain:
                            clean_url = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
                            if clean_url not in visited and len(queue) < 100:
                                links.append(clean_url)
                                queue.append((clean_url, depth + 1))

                pages_crawled += 1

                yield CrawledPage(
                    url=url,
                    html=html,
                    text=text[:50000],
                    title=title,
                    status_code=resp.status_code,
                    depth=depth,
                    links=links[:50],
                )

            except Exception:
                continue


if __name__ == "__main__":
    async def test():
        count = 0
        async for page in crawl_domain_httpx("https://example.com", max_pages=5):
            count += 1
            print(f"[{count}] {page.url}")
        print(f"Done: {count} pages")
    asyncio.run(test())
