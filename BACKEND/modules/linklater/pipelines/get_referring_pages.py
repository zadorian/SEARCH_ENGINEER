#!/usr/bin/env python3
"""
GET REFERRING PAGES FROM SPECIFIC DOMAINS

Given a target domain and a list of referring domains, find the ACTUAL page URLs
that link to the target using Common Crawl Index API + WAT file parsing.
"""
import asyncio
import requests
import json
from typing import List, Dict
from collections import defaultdict

TARGET_DOMAIN = "sebgroup.com"
REFERRING_DOMAINS = ["cryptonews.com.au", "wko.at", "ots.at", "easybank.at"]

# Use November 2025 archive (matches domain graph)
CC_INDEX_URL = "https://index.commoncrawl.org/CC-MAIN-2025-47-index"


def query_cc_index_for_domain(domain: str) -> List[Dict]:
    """
    Query Common Crawl Index API for all pages from a specific domain.

    Args:
        domain: Domain to search (e.g., "wko.at")

    Returns:
        List of WARC record locations
    """
    print(f"\n🔍 Querying CC Index for pages from: {domain}")

    # Query for all URLs from this domain
    url = f"{CC_INDEX_URL}?url={domain}/*&output=json&fl=url,filename,offset,length"

    try:
        response = requests.get(url, timeout=60)

        if response.status_code == 200:
            records = []
            for line in response.text.strip().split('\n'):
                if line:
                    record = json.loads(line)
                    records.append(record)

            print(f"   Found {len(records)} pages from {domain}")
            return records
        else:
            print(f"   ⚠️  HTTP {response.status_code}")
            return []

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def fetch_wat_record(filename: str, offset: int, length: int) -> Dict:
    """
    Fetch a single WAT record from Common Crawl.

    Args:
        filename: WARC filename
        offset: Byte offset
        length: Record length

    Returns:
        Parsed WAT record
    """
    wat_filename = filename.replace('/warc/', '/wat/').replace('.warc.gz', '.warc.wat.gz')
    url = f"https://data.commoncrawl.org/{wat_filename}"

    headers = {'Range': f'bytes={offset}-{offset+length-1}'}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code in (200, 206):
            # Parse WARC record (WAT files are WARC-formatted JSON)
            # This is simplified - full implementation would parse WARC headers
            return response.json() if response.text else {}
        else:
            print(f"      ⚠️  WAT fetch HTTP {response.status_code}")
            return {}
    except Exception as e:
        print(f"      ❌ WAT fetch error: {e}")
        return {}


def check_for_outlinks_to_target(page_url: str, wat_record: Dict, target_domain: str) -> List[Dict]:
    """
    Check if a WAT record contains outlinks to the target domain.

    Args:
        page_url: Source page URL
        wat_record: Parsed WAT record
        target_domain: Target domain to look for

    Returns:
        List of outlinks to target
    """
    outlinks = []

    # WAT files have structure: {"Envelope": {"Payload-Metadata": {"HTTP-Response-Metadata": {"Links": [...]}}}}
    try:
        links = wat_record.get('Envelope', {}).get('Payload-Metadata', {}).get('HTTP-Response-Metadata', {}).get('HTML-Metadata', {}).get('Links', [])

        for link in links:
            href = link.get('url', '')
            if target_domain in href:
                outlinks.append({
                    'source_url': page_url,
                    'target_url': href,
                    'anchor_text': link.get('text', ''),
                    'link_type': link.get('path', '')
                })
    except Exception as e:
        pass  # Silently skip malformed records

    return outlinks


async def find_referring_pages_from_domain(referring_domain: str, target_domain: str, max_pages: int = 50) -> List[Dict]:
    """
    Find all pages from referring_domain that link to target_domain.

    Args:
        referring_domain: Domain to search (e.g., "wko.at")
        target_domain: Target domain (e.g., "sebgroup.com")
        max_pages: Max pages to check from referring domain

    Returns:
        List of referring page URLs with outlinks
    """
    print(f"\n{'='*100}")
    print(f"SEARCHING: {referring_domain} → {target_domain}")
    print(f"{'='*100}")

    # Step 1: Get all pages from referring domain in CC Index
    cc_records = query_cc_index_for_domain(referring_domain)

    if not cc_records:
        print(f"\n⚠️  No pages found from {referring_domain} in CC Index")
        return []

    # Limit to max_pages
    cc_records = cc_records[:max_pages]

    # Step 2: For each page, fetch WAT record and check for outlinks to target
    referring_pages = []

    print(f"\n📊 Checking {len(cc_records)} pages for outlinks to {target_domain}...")

    for i, record in enumerate(cc_records, 1):
        page_url = record['url']
        filename = record['filename']
        offset = int(record['offset'])
        length = int(record['length'])

        if i % 10 == 0:
            print(f"   Checked {i}/{len(cc_records)} pages...")

        # Fetch WAT record
        wat_record = fetch_wat_record(filename, offset, length)

        # Check for outlinks to target
        outlinks = check_for_outlinks_to_target(page_url, wat_record, target_domain)

        if outlinks:
            print(f"\n   ✅ FOUND: {page_url}")
            for link in outlinks:
                print(f"      → {link['target_url']}")
                if link.get('anchor_text'):
                    print(f"        Anchor: \"{link['anchor_text']}\"")

            referring_pages.extend(outlinks)

    print(f"\n📊 RESULT: Found {len(referring_pages)} outlinks from {referring_domain}")

    return referring_pages


async def main():
    """Find referring pages from all target domains."""

    print("="*100)
    print(f"REFERRING PAGE DISCOVERY: {TARGET_DOMAIN}")
    print("="*100)
    print(f"\nTarget: {TARGET_DOMAIN}")
    print(f"Referring Domains: {', '.join(REFERRING_DOMAINS)}")
    print(f"Archive: CC-MAIN-2025-47 (November 2025)")
    print()

    all_results = {}

    for referring_domain in REFERRING_DOMAINS:
        results = await find_referring_pages_from_domain(
            referring_domain,
            TARGET_DOMAIN,
            max_pages=50
        )
        all_results[referring_domain] = results

    # Summary
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)

    total_pages = sum(len(pages) for pages in all_results.values())

    for domain, pages in all_results.items():
        print(f"\n{domain}: {len(pages)} referring pages")
        for i, page in enumerate(pages[:5], 1):  # Show first 5
            print(f"   {i}. {page['source_url']}")
            if page.get('anchor_text'):
                print(f"      Anchor: \"{page['anchor_text']}\"")

    if total_pages == 0:
        print("\n⚠️  NO REFERRING PAGES FOUND")
        print("\nPossible reasons:")
        print("1. Pages exist in domain graph (aggregate) but not in WAT files (page-level)")
        print("2. CC-MAIN-2025-47 might not be the correct archive for these links")
        print("3. Links might be in JavaScript/dynamic content not captured by WAT files")
    else:
        print(f"\n✅ TOTAL: {total_pages} referring pages found")

    print("="*100)


if __name__ == "__main__":
    asyncio.run(main())
