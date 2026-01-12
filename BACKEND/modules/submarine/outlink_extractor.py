"""
Extract outlinks from HTML content.
"""

import re
from typing import List, Dict, Set
from urllib.parse import urljoin, urlparse


def extract_outlinks(html: str, base_url: str, max_links: int = 100) -> List[Dict]:
    """
    Extract links from HTML.

    Returns list of dicts with:
        - url: The full URL
        - text: Anchor text
        - domain: Target domain
        - is_external: True if links to different domain
    """
    if not html:
        return []

    base_domain = urlparse(base_url).netloc.lower().replace("www.", "")

    # Find all href links - pattern: <a href="URL">TEXT</a>
    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\'<>]+)["\'](?:[^>]*>([^<]*)</a)?',
        re.IGNORECASE
    )

    results = []
    seen_urls: Set[str] = set()

    for match in link_pattern.finditer(html):
        href = match.group(1).strip()
        anchor_text = match.group(2).strip() if match.group(2) else ""

        # Skip empty, javascript, mailto, tel links
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)

        # Parse to get domain
        try:
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            target_domain = parsed.netloc.lower().replace("www.", "")
        except:
            continue

        # Skip if already seen
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Determine if external
        is_external = target_domain != base_domain

        results.append({
            "url": full_url,
            "text": anchor_text[:200],  # Limit text length
            "domain": target_domain,
            "is_external": is_external,
        })

        if len(results) >= max_links:
            break

    return results


def extract_external_links(html: str, base_url: str, max_links: int = 50) -> List[Dict]:
    """Extract only external links."""
    all_links = extract_outlinks(html, base_url, max_links * 2)
    return [l for l in all_links if l["is_external"]][:max_links]


if __name__ == "__main__":
    test_html = """
    <html>
    <body>
    <a href="https://google.com">Google</a>
    <a href="/about">About Us</a>
    <a href="https://facebook.com/company">Facebook Page</a>
    <a href="mailto:test@example.com">Email</a>
    <a href="https://linkedin.com/company/acme">LinkedIn</a>
    </body>
    </html>
    """

    links = extract_outlinks(test_html, "https://example.com")
    print("=== ALL LINKS ===")
    for l in links:
        ext = "EXT" if l["is_external"] else "INT"
        print(f"  [{ext}] {l['domain']} - {l['url'][:60]}")

    print("\n=== EXTERNAL ONLY ===")
    ext_links = extract_external_links(test_html, "https://example.com")
    for l in ext_links:
        print(f"  {l['domain']} - {l['text']}")
