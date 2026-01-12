"""
CommonCrawl Index API for BACKDRILL.

Query the CC Index to find WARC locations for URLs/domains.
Uses cluster.idx binary search for fast domain lookups.

Based on:
- LINKLATER/scraping/web/cc_offline_sniper.py
"""

import asyncio
import aiohttp
import bisect
import gzip
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

CC_DATA_URL = "https://data.commoncrawl.org"
CC_INDEX_URL = "https://index.commoncrawl.org"
DATA_DIR = Path(__file__).parent / "data"


class CCIndex:
    """
    CommonCrawl Index client.

    Provides two modes:
    1. CDX Server API - Simple queries for single URLs
    2. Cluster.idx binary search - Fast domain-wide lookups

    Available archives (newest first):
    - CC-MAIN-2024-51, CC-MAIN-2024-46, CC-MAIN-2024-42, ...
    - CC-MAIN-2023-50, CC-MAIN-2023-40, CC-MAIN-2023-23, ...
    - CC-MAIN-2022-49, CC-MAIN-2022-40, ...

    Usage:
        idx = CCIndex()

        # Simple URL lookup via CDX Server
        records = await idx.lookup_url("https://example.com/page")

        # Domain-wide scan via cluster.idx
        records = await idx.scan_domain("example.com", limit=1000)

        # Check if URL exists
        exists = await idx.exists("https://example.com")
    """

    # Available CC archives
    ARCHIVES = [
        "CC-MAIN-2024-51", "CC-MAIN-2024-46", "CC-MAIN-2024-42",
        "CC-MAIN-2024-38", "CC-MAIN-2024-33", "CC-MAIN-2024-30",
        "CC-MAIN-2024-26", "CC-MAIN-2024-22", "CC-MAIN-2024-18",
        "CC-MAIN-2024-10", "CC-MAIN-2023-50", "CC-MAIN-2023-40",
        "CC-MAIN-2023-23", "CC-MAIN-2023-14", "CC-MAIN-2023-06",
        "CC-MAIN-2022-49", "CC-MAIN-2022-40", "CC-MAIN-2022-33",
    ]

    def __init__(
        self,
        archive: str = "CC-MAIN-2024-51",
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.archive = archive
        self._session = session
        self._own_session = session is None
        self._cluster_idx: List[tuple] = []
        self._cluster_keys: List[str] = []

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    # -------------------------------------------------------------------------
    # CDX Server API (simple URL lookups)
    # -------------------------------------------------------------------------

    async def lookup_url(
        self,
        url: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query CC CDX Server for a specific URL.

        Returns list of index records with WARC locations.
        """
        await self._ensure_session()

        params = {
            "url": url,
            "output": "json",
            "limit": limit,
        }

        try:
            api_url = f"{CC_INDEX_URL}/{self.archive}-index"
            async with self._session.get(api_url, params=params, timeout=30) as resp:
                if resp.status != 200:
                    return []

                records = []
                text = await resp.text()
                for line in text.strip().split('\n'):
                    if line:
                        try:
                            record = json.loads(line)
                            records.append({
                                "url": record.get("url"),
                                "timestamp": record.get("timestamp"),
                                "status": record.get("status"),
                                "mime": record.get("mime"),
                                "digest": record.get("digest"),
                                "warc_filename": record.get("filename"),
                                "warc_offset": record.get("offset"),
                                "warc_length": record.get("length"),
                            })
                        except json.JSONDecodeError:
                            continue

                return records

        except Exception as e:
            logger.error(f"CC Index query failed: {e}")
            return []

    async def exists(self, url: str) -> bool:
        """Check if URL exists in CC Index."""
        records = await self.lookup_url(url, limit=1)
        return len(records) > 0

    # -------------------------------------------------------------------------
    # Cluster.idx binary search (fast domain lookups)
    # -------------------------------------------------------------------------

    async def _load_cluster_index(self):
        """Download and load cluster.idx for binary search."""
        if self._cluster_idx:
            return

        await self._ensure_session()

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        idx_path = DATA_DIR / f"cluster_{self.archive}.idx"

        if not idx_path.exists():
            logger.info(f"Downloading cluster index for {self.archive}...")
            url = f"{CC_DATA_URL}/cc-index/collections/{self.archive}/indexes/cluster.idx"
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download cluster.idx: {resp.status}")
                content = await resp.read()
                with open(idx_path, 'wb') as f:
                    f.write(content)
            logger.info(f"Saved cluster index to {idx_path}")

        # Load into memory
        with open(idx_path, 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        self._cluster_idx.append((
                            parts[0],  # key (SURT)
                            parts[2],  # filename
                            int(parts[3]),  # offset
                            int(parts[4])   # length
                        ))
                    except ValueError:
                        continue

        self._cluster_keys = [x[0] for x in self._cluster_idx]
        logger.info(f"Loaded {len(self._cluster_idx)} index blocks")

    def _domain_to_surt(self, domain: str) -> str:
        """Convert domain to SURT key (reversed domain)."""
        parts = domain.lower().split('.')
        return ",".join(parts[::-1])

    async def scan_domain(
        self,
        domain: str,
        limit: int = 1000,
        max_blocks: int = 20,
        concurrent: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Scan CC Index for all URLs from a domain.

        Uses cluster.idx binary search for efficient lookup.

        Args:
            domain: Target domain
            limit: Max URLs to return
            max_blocks: Max index blocks to scan
            concurrent: Parallel block fetches

        Returns:
            List of index records with WARC locations
        """
        await self._load_cluster_index()
        await self._ensure_session()

        surt_key = self._domain_to_surt(domain)
        idx = bisect.bisect_right(self._cluster_keys, surt_key) - 1

        if idx < 0:
            return []

        # Find relevant blocks
        blocks = []
        for i in range(idx, min(len(self._cluster_idx), idx + max_blocks)):
            block_key = self._cluster_idx[i][0]
            if i > idx and block_key > surt_key and not block_key.startswith(surt_key):
                break
            blocks.append(self._cluster_idx[i])

        if not blocks:
            return []

        # Fetch blocks in parallel
        async def fetch_block(block):
            _, filename, offset, length = block
            url = f"{CC_DATA_URL}/cc-index/collections/{self.archive}/indexes/{filename}"
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}

            try:
                async with self._session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status not in (200, 206):
                        return []
                    content = gzip.decompress(await resp.read())
                    return content.decode('utf-8', errors='ignore').splitlines()
            except Exception as e:
                logger.debug(f"Block fetch failed: {e}")
                return []

        # Parallel fetch with semaphore
        sem = asyncio.Semaphore(concurrent)

        async def guarded_fetch(block):
            async with sem:
                return await fetch_block(block)

        tasks = [guarded_fetch(b) for b in blocks]
        block_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        results = []
        seen_urls = set()

        for lines in block_results:
            if isinstance(lines, Exception) or not lines:
                continue

            for line in lines:
                try:
                    parts = line.split(None, 2)
                    if len(parts) < 3:
                        continue

                    key = parts[0]
                    if not key.startswith(surt_key):
                        continue

                    # Check boundary
                    suffix = key[len(surt_key):]
                    if suffix and suffix[0] not in [')', ',']:
                        continue

                    meta = json.loads(parts[2])
                    url = meta.get('url')

                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    warc_file = meta.get('filename', '')
                    if 'robotstxt' in warc_file or 'crawldiagnostics' in warc_file:
                        continue

                    results.append({
                        'url': url,
                        'timestamp': meta.get('timestamp'),
                        'status': meta.get('status'),
                        'mime': meta.get('mime'),
                        'digest': meta.get('digest'),
                        'warc_filename': warc_file,
                        'warc_offset': meta.get('offset'),
                        'warc_length': meta.get('length'),
                    })

                    if len(results) >= limit:
                        return results

                except Exception:
                    continue

        return results

    async def list_snapshots(
        self,
        url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get all CC snapshots for a URL.

        Wrapper for lookup_url with date filtering.
        """
        records = await self.lookup_url(url, limit=limit * 2)

        # Filter by date if provided
        if start_date or end_date:
            filtered = []
            for r in records:
                ts = r.get('timestamp', '')
                if start_date and ts < start_date.replace("-", ""):
                    continue
                if end_date and ts > end_date.replace("-", ""):
                    continue
                filtered.append(r)
            records = filtered

        return records[:limit]
