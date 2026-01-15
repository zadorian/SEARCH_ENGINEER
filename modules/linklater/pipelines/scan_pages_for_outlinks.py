#!/usr/bin/env python3
"""
SCAN PAGES FOR OUTLINKS

Fetch archived pages from Common Crawl and scan for outlinks to target domain.
No local storage - just rapid scanning.
"""
import asyncio
import aiohttp
import requests
import json
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urlparse
import re

TARGET_DOMAIN = "sebgroup.com"
REFERRING_DOMAINS = ["cryptonews.com.au", "wko.at", "ots.at", "easybank.at"]
CC_INDEX_URL = "https://index.commoncrawl.org/CC-MAIN-2025-47-index"


def get_pages_from_domain(domain: str, limit: int = 100) -> List[Dict]:
    """Get list of pages from CC Index."""
    print(f"\n🔍 Querying CC Index for: {domain}")

    url = f"{CC_INDEX_URL}?url={domain}/*&output=json"

    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            records = []
            for line in response.text.strip().split('\n')[:limit]:
                if line:
                    records.append(json.loads(line))

            print(f"   Found {len(records)} pages")
            return records
        else:
            print(f"   ⚠️  HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


async def fetch_page_content(session: aiohttp.ClientSession, url: str, filename: str, offset: int, length: int) -> str:
    """Fetch actual page content from Common Crawl."""
    cc_url = f"https://data.commoncrawl.org/{filename}"
    headers = {'Range': f'bytes={offset}-{offset+length-1}'}

    try:
        async with session.get(cc_url, headers=headers, timeout=30) as response:
            if response.status in (200, 206):
                content = await response.text()

                # WARC records have headers, extract HTML body
                # Format: WARC headers, HTTP headers, then HTML
                parts = content.split('\r\n\r\n', 2)
                if len(parts) >= 3:
                    return parts[2]  # HTML content
                elif len(parts) >= 2:
                    return parts[1]  # Fallback
                else:
                    return content
            else:
                return ""
    except Exception as e:
        return ""


def extract_outlinks(html: str, target_domain: str) -> List[str]:
    """Extract outlinks to target domain from HTML."""
    try:
        soup = BeautifulSoup(html, 'html.parser')

        outlinks = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')

            # Check if link points to target domain
            if target_domain in href:
                outlinks.append({
                    'url': href,
                    'text': link.get_text(strip=True)[:100]
                })

        return outlinks
    except Exception as e:
        return []


async def scan_domain_for_outlinks(domain: str, target_domain: str, max_pages: int = 100) -> List[Dict]:
    """Scan pages from domain for outlinks to target."""
    print(f"\n{'='*100}")
    print(f"SCANNING: {domain} → {target_domain}")
    print(f"{'='*100}")

    # Get pages from CC Index
    pages = get_pages_from_domain(domain, limit=max_pages)

    if not pages:
        return []

    print(f"\n📊 Scanning {len(pages)} pages...")

    results = []

    async with aiohttp.ClientSession() as session:
        for i, page in enumerate(pages, 1):
            page_url = page['url']
            filename = page['filename']
            offset = int(page['offset'])
            length = int(page['length'])

            if i % 10 == 0:
                print(f"   Scanned {i}/{len(pages)} pages... ({len(results)} matches)")

            # Fetch page content
            html = await fetch_page_content(session, page_url, filename, offset, length)

            if not html:
                continue

            # Extract outlinks to target
            outlinks = extract_outlinks(html, target_domain)

            if outlinks:
                print(f"\n   ✅ FOUND: {page_url}")
                for link in outlinks:
                    print(f"      → {link['url']}")
                    if link['text']:
                        print(f"        Text: \"{link['text']}\"")

                results.append({
                    'source_url': page_url,
                    'outlinks': outlinks
                })

    print(f"\n📊 RESULT: {len(results)} pages with outlinks to {target_domain}")
    return results


async def main():
    """Scan all referring domains."""
    print("="*100)
    print(f"PAGE SCANNING: {TARGET_DOMAIN}")
    print("="*100)
    print(f"\nTarget: {TARGET_DOMAIN}")
    print(f"Referring Domains: {', '.join(REFERRING_DOMAINS)}")
    print(f"Archive: CC-MAIN-2025-47 (November 2025)")
    print()

    all_results = {}

    for domain in REFERRING_DOMAINS:
        results = await scan_domain_for_outlinks(domain, TARGET_DOMAIN, max_pages=100)
        all_results[domain] = results

    # Summary
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)

    total_pages = sum(len(pages) for pages in all_results.values())

    for domain, pages in all_results.items():
        print(f"\n{domain}: {len(pages)} referring pages")
        for i, page in enumerate(pages[:5], 1):
            print(f"   {i}. {page['source_url']}")
            for link in page['outlinks'][:3]:
                print(f"      → {link['url']}")
                if link.get('text'):
                    print(f"        \"{link['text']}\"")

    if total_pages == 0:
        print("\n⚠️  NO REFERRING PAGES FOUND")
        print("\nPossible reasons:")
        print("1. Links might be in different CC archive (not November 2025)")
        print("2. Links might be JavaScript-generated (not in HTML)")
        print("3. Domain graph shows aggregated data from multiple archives")
    else:
        print(f"\n✅ TOTAL: {total_pages} referring pages found")

    print("="*100)


if __name__ == "__main__":
    asyncio.run(main())
