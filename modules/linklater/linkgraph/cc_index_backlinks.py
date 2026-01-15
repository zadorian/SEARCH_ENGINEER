"""
CC Index Backlinks - Targeted Backlink Fetcher

Uses CC Index API to find which WAT files contain pages from referring domains,
then streams those WAT files and extracts outlinks to the target domain.

This is the "sniper" approach vs the "trawler" approach of scanning all WAT files.

Architecture:
1. Query CC Index API for pages from known referring domains (from CC Web Graph)
2. Group results by WAT file (many URLs may be in the same file)
3. Stream each unique WAT file with gzip decompression
4. Extract records for our target URLs and scan for outlinks

Key insight: CC Index returns WARC offsets, but those don't work for WAT files.
Instead, we identify which WAT files contain our source domain pages, then
stream those files and match by URL.
"""

import asyncio
import aiohttp
import gzip
import json
import re
from io import BytesIO
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
from collections import defaultdict

# Default CC archive - use latest available
DEFAULT_ARCHIVE = "CC-MAIN-2025-47"

# CC Index API base URL
CC_INDEX_BASE = "https://index.commoncrawl.org"

# AWS S3 URL for Common Crawl (sometimes faster than data.commoncrawl.org)
CC_S3_BASE = "https://data.commoncrawl.org"


@dataclass
class BacklinkRecord:
    """A backlink record from Common Crawl WAT files."""
    source_url: str
    source_domain: str
    target_url: str
    target_domain: str
    anchor_text: str = ""
    link_type: str = ""

    def to_dict(self) -> Dict:
        return {
            "source": self.source_url,
            "target": self.target_url,
            "sourceDomain": self.source_domain,
            "targetDomain": self.target_domain,
            "anchorText": self.anchor_text,
            "linkType": self.link_type,
        }

    def to_ndjson(self) -> str:
        return json.dumps(self.to_dict())


async def query_cc_index(
    domain: str,
    archive: str = DEFAULT_ARCHIVE,
    limit: int = 100
) -> List[Dict]:
    """
    Query CC Index API for all pages from a specific domain.

    Args:
        domain: Domain to search (e.g., "wko.at")
        archive: CC archive name (e.g., "CC-MAIN-2024-10")
        limit: Max records to return

    Returns:
        List of WARC record locations with url, filename, offset, length
    """
    url = f"{CC_INDEX_BASE}/{archive}-index?url={domain}/*&output=json&fl=url,filename,offset,length&limit={limit}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    records = []
                    text = await resp.text()
                    for line in text.strip().split('\n'):
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                    return records
                else:
                    print(f"[CC Index] HTTP {resp.status} for {domain}")
                    return []
        except Exception as e:
            print(f"[CC Index] Error querying {domain}: {e}")
            return []


def warc_to_wat_path(warc_filename: str) -> str:
    """Convert WARC filename to WAT filename."""
    return warc_filename.replace('/warc/', '/wat/').replace('.warc.gz', '.warc.wat.gz')


def group_by_wat_file(cc_records: List[Dict]) -> Dict[str, List[str]]:
    """
    Group CC Index records by their WAT file.

    Returns dict mapping WAT file path -> list of URLs in that file.
    """
    groups = defaultdict(list)
    for record in cc_records:
        warc_file = record.get('filename', '')
        wat_file = warc_to_wat_path(warc_file)
        url = record.get('url', '')
        if wat_file and url:
            groups[wat_file].append(url)
    return dict(groups)


async def stream_wat_records_for_urls(
    session: aiohttp.ClientSession,
    wat_file: str,
    target_urls: Set[str],
    target_domain: str,
    max_chunk_mb: int = 50
) -> List[BacklinkRecord]:
    """
    Stream a WAT file and extract outlinks from records matching target URLs.

    WAT files are gzipped WARC files containing JSON metadata.
    Each record looks like:
    WARC/1.0
    WARC-Type: metadata
    WARC-Target-URI: http://example.com/page
    ...

    {JSON metadata with Links array}

    Args:
        session: aiohttp session
        wat_file: WAT file path
        target_urls: Set of URLs we're looking for
        target_domain: Domain to find outlinks TO
        max_chunk_mb: Max data to download before stopping

    Returns:
        List of BacklinkRecord objects
    """
    url = f"{CC_S3_BASE}/{wat_file}"
    results = []
    bytes_read = 0
    max_bytes = max_chunk_mb * 1024 * 1024

    # Normalize target URLs for matching
    target_urls_normalized = {u.rstrip('/').lower() for u in target_urls}

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                print(f"[WAT Stream] HTTP {resp.status} for {wat_file}")
                return []

            # Stream and decompress
            decompressor = gzip.GzipFile(fileobj=BytesIO())
            buffer = b""
            current_record = ""
            current_url = ""
            in_json = False
            json_buffer = ""
            brace_count = 0

            async for chunk in resp.content.iter_chunked(65536):
                bytes_read += len(chunk)

                # Decompress chunk
                try:
                    # Manual streaming decompression
                    decompressor = gzip.decompress(buffer + chunk)
                    buffer = b""
                    text = decompressor.decode('utf-8', errors='ignore')
                except Exception:
                    buffer += chunk
                    continue

                # Parse WARC records
                for char in text:
                    if not in_json:
                        current_record += char

                        # Look for WARC-Target-URI header
                        if 'WARC-Target-URI:' in current_record:
                            match = re.search(r'WARC-Target-URI:\s*(\S+)', current_record)
                            if match:
                                current_url = match.group(1).rstrip('/').lower()

                        # Start of JSON payload
                        if char == '{':
                            in_json = True
                            json_buffer = char
                            brace_count = 1
                    else:
                        json_buffer += char
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1

                            if brace_count == 0:
                                # Complete JSON record
                                if current_url in target_urls_normalized:
                                    try:
                                        record = json.loads(json_buffer)
                                        backlinks = extract_outlinks_to_target(
                                            current_url, record, target_domain
                                        )
                                        results.extend(backlinks)
                                    except json.JSONDecodeError:
                                        pass

                                # Reset for next record
                                current_record = ""
                                current_url = ""
                                in_json = False
                                json_buffer = ""

                # Safety limit
                if bytes_read > max_bytes:
                    print(f"[WAT Stream] Hit {max_chunk_mb}MB limit for {wat_file}")
                    break

    except Exception as e:
        print(f"[WAT Stream] Error streaming {wat_file}: {e}")

    return results


async def fetch_wat_file_simple(
    session: aiohttp.ClientSession,
    wat_file: str,
    target_urls: Set[str],
    target_domain: str
) -> List[BacklinkRecord]:
    """
    Simpler approach: Download and decompress WAT file, search for URLs.

    This downloads the full file but is more reliable than streaming.
    """
    url = f"{CC_S3_BASE}/{wat_file}"
    results = []

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=180)) as resp:
            if resp.status != 200:
                print(f"[WAT Fetch] HTTP {resp.status} for {wat_file}")
                return []

            # Read and decompress
            compressed = await resp.read()
            try:
                data = gzip.decompress(compressed)
                text = data.decode('utf-8', errors='ignore')
            except Exception as e:
                print(f"[WAT Fetch] Decompress error: {e}")
                return []

            # Find all WARC records with their URLs
            # Split on WARC record boundaries
            records = text.split('WARC/1.0')

            for record in records:
                if not record.strip():
                    continue

                # Extract target URI
                uri_match = re.search(r'WARC-Target-URI:\s*(\S+)', record)
                if not uri_match:
                    continue

                record_url = uri_match.group(1).rstrip('/')
                record_url_lower = record_url.lower()

                # Check if this URL is one we're looking for
                matched = False
                for target_url in target_urls:
                    if record_url_lower == target_url.lower().rstrip('/'):
                        matched = True
                        break

                if not matched:
                    continue

                # Extract JSON payload
                json_start = record.find('{')
                if json_start < 0:
                    continue

                # Find matching closing brace
                json_text = record[json_start:]
                brace_count = 0
                json_end = 0
                for i, c in enumerate(json_text):
                    if c == '{':
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break

                if json_end == 0:
                    continue

                try:
                    wat_record = json.loads(json_text[:json_end])
                    backlinks = extract_outlinks_to_target(
                        record_url, wat_record, target_domain
                    )
                    results.extend(backlinks)
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"[WAT Fetch] Error: {e}")

    return results


def extract_outlinks_to_target(
    page_url: str,
    wat_record: Dict,
    target_domain: str
) -> List[BacklinkRecord]:
    """
    Extract outlinks to target domain from a WAT record.

    Args:
        page_url: Source page URL
        wat_record: Parsed WAT JSON record
        target_domain: Domain to look for in outlinks

    Returns:
        List of BacklinkRecord objects
    """
    results = []
    source_domain = urlparse(page_url).netloc

    try:
        # Navigate WAT structure to find links
        # Structure: Envelope.Payload-Metadata.HTTP-Response-Metadata.HTML-Metadata.Links
        envelope = wat_record.get('Envelope', {})
        payload = envelope.get('Payload-Metadata', {})
        http_meta = payload.get('HTTP-Response-Metadata', {})
        html_meta = http_meta.get('HTML-Metadata', {})
        links = html_meta.get('Links', [])

        target_domain_lower = target_domain.lower()

        for link in links:
            href = link.get('url', '')
            if target_domain_lower in href.lower():
                results.append(BacklinkRecord(
                    source_url=page_url,
                    source_domain=source_domain,
                    target_url=href,
                    target_domain=target_domain,
                    anchor_text=link.get('text', ''),
                    link_type=link.get('path', '')
                ))
    except Exception:
        pass

    return results


async def get_backlinks_from_domain(
    source_domain: str,
    target_domain: str,
    archive: str = DEFAULT_ARCHIVE,
    max_pages: int = 50,
    max_wat_files: int = 3
) -> List[BacklinkRecord]:
    """
    Find all backlinks from source_domain to target_domain.

    Args:
        source_domain: Domain to search for pages (e.g., "wko.at")
        target_domain: Domain to find links TO (e.g., "example.com")
        archive: CC archive name
        max_pages: Max pages to check from source domain
        max_wat_files: Max WAT files to download per source domain

    Returns:
        List of BacklinkRecord objects
    """
    # Step 1: Query CC Index for pages from source domain
    print(f"[CC Index] Querying {source_domain}...")
    cc_records = await query_cc_index(source_domain, archive, max_pages)

    if not cc_records:
        print(f"[CC Index] No records for {source_domain}")
        return []

    print(f"[CC Index] Found {len(cc_records)} pages from {source_domain}")

    # Step 2: Group by WAT file
    wat_groups = group_by_wat_file(cc_records)
    print(f"[CC Index] Pages spread across {len(wat_groups)} WAT files")

    # Step 3: Fetch each WAT file and extract backlinks
    results = []

    # Sort by number of URLs (prioritize files with more of our URLs)
    sorted_wat_files = sorted(wat_groups.items(), key=lambda x: -len(x[1]))

    async with aiohttp.ClientSession() as session:
        for wat_file, urls in sorted_wat_files[:max_wat_files]:
            print(f"[WAT] Fetching {wat_file} ({len(urls)} URLs)...")

            backlinks = await fetch_wat_file_simple(
                session, wat_file, set(urls), target_domain
            )
            results.extend(backlinks)

            print(f"[WAT] Found {len(backlinks)} backlinks in {wat_file}")

    return results


async def get_backlinks_targeted(
    target_domain: str,
    source_domains: List[str],
    archive: str = DEFAULT_ARCHIVE,
    max_pages_per_source: int = 50,
    max_wat_files_per_source: int = 2,
    max_results: int = 100
) -> List[BacklinkRecord]:
    """
    Get backlinks to target_domain from a list of known source domains.

    This is the "sniper" approach - we know which domains link to target
    from the CC Web Graph, so we only search those specific domains.

    Args:
        target_domain: Domain to find backlinks TO
        source_domains: List of domains that link to target (from CC Graph)
        archive: CC archive name
        max_pages_per_source: Max pages to check per source domain
        max_wat_files_per_source: Max WAT files to download per source
        max_results: Total max results to return

    Returns:
        List of BacklinkRecord objects
    """
    all_results = []

    print(f"[Targeted] Finding backlinks to {target_domain} from {len(source_domains)} source domains")

    for source_domain in source_domains:
        if len(all_results) >= max_results:
            break

        print(f"\n[Targeted] Processing source: {source_domain}")

        backlinks = await get_backlinks_from_domain(
            source_domain=source_domain,
            target_domain=target_domain,
            archive=archive,
            max_pages=max_pages_per_source,
            max_wat_files=max_wat_files_per_source
        )

        all_results.extend(backlinks)
        print(f"[Targeted] Running total: {len(all_results)} backlinks")

    return all_results[:max_results]


# CLI interface for testing
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 3:
            print("Usage: python cc_index_backlinks.py <target_domain> <source_domain1,source_domain2,...>")
            print("Example: python cc_index_backlinks.py example.com wko.at,bbc.com")
            sys.exit(1)

        target = sys.argv[1]
        sources = sys.argv[2].split(',')

        print(f"Finding backlinks to {target} from {sources}", file=sys.stderr)

        results = await get_backlinks_targeted(
            target_domain=target,
            source_domains=sources,
            max_pages_per_source=50,
            max_wat_files_per_source=2,
            max_results=100
        )

        print(f"\nFound {len(results)} backlinks total", file=sys.stderr)

        # Output NDJSON to stdout for piping
        for r in results:
            print(r.to_ndjson())

    asyncio.run(main())
