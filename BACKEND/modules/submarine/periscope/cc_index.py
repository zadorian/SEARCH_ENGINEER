#!/usr/bin/env python3
"""
PERISCOPE - Common Crawl Index Client

Queries CC Index API to find WARC coordinates for target URLs/domains.
Returns precise (warc_file, offset, length) tuples for surgical fetches.
"""

import aiohttp
import asyncio
import json
import logging
import os
import re
import time
from hashlib import sha256
from pathlib import Path
from random import random
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple, Union
from dataclasses import dataclass
from urllib.parse import quote

logger = logging.getLogger(__name__)

CC_INDEX_BASE = "https://index.commoncrawl.org"
DEFAULT_ARCHIVE = "CC-MAIN-2025-51"  # Latest as of Jan 2026

@dataclass
class CCRecord:
    """A single CC Index record pointing to WARC content."""
    url: str
    filename: str  # WARC filename in S3
    offset: int    # Byte offset in WARC
    length: int    # Compressed length
    status: int    # HTTP status
    mime: str
    timestamp: str
    digest: str

    @property
    def s3_url(self) -> str:
        return f"https://data.commoncrawl.org/{self.filename}"

    @property
    def range_header(self) -> str:
        return f"bytes={self.offset}-{self.offset + self.length - 1}"


class Periscope:
    """
    CC Index API client for surgical WARC lookups.

    Usage:
        periscope = Periscope()
        records = await periscope.lookup_domain("example.com", limit=1000)
        records = await periscope.lookup_url("https://example.com/page")
        records = await periscope.search("*.example.com/*")
    """

    def __init__(
        self,
        archive: str = DEFAULT_ARCHIVE,
        *,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        cache_dir: Optional[str | Path] = None,
        cache_ttl_seconds: Optional[int] = None,
    ):
        self.archive = archive
        self.session: Optional[aiohttp.ClientSession] = None

        timeout_val = timeout_seconds if timeout_seconds is not None else os.getenv("SUBMARINE_CC_INDEX_TIMEOUT_SEC", "60")
        try:
            self.timeout_seconds = float(timeout_val)
        except Exception:
            self.timeout_seconds = 60.0

        retries_val = max_retries if max_retries is not None else os.getenv("SUBMARINE_CC_INDEX_MAX_RETRIES", "3")
        try:
            self.max_retries = int(retries_val)
        except Exception:
            self.max_retries = 3

        ttl = cache_ttl_seconds if cache_ttl_seconds is not None else os.getenv("SUBMARINE_CC_INDEX_CACHE_TTL_SEC", "86400")
        try:
            self.cache_ttl_seconds = int(ttl)
        except Exception:
            self.cache_ttl_seconds = 86400

        cache_env = os.getenv("SUBMARINE_CC_INDEX_CACHE_DIR", "").strip()
        resolved_cache_dir = cache_dir or (Path(cache_env) if cache_env else Path("/data/.cache/submarine_cc_index"))
        self.cache_dir = Path(resolved_cache_dir) if resolved_cache_dir else None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            )
        return self.session

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def lookup_domain(
        self,
        domain: str,
        limit: int = 10000,
        filter_status: Optional[int] = 200,
        filter_mime: Optional[str] = None,
        filter_languages: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        url_contains: Optional[str] = None,
        archive: Optional[str] = None,
    ) -> List[CCRecord]:
        """
        Lookup all pages for a domain in CC Index.

        Args:
            domain: Domain to search (e.g., "example.com")
            limit: Max records to return
            filter_status: Only return this HTTP status (default 200)
            filter_mime: Only return this MIME type
            filter_languages: Only return this language code (e.g., "eng")
            from_ts: Lower bound timestamp (YYYYMMDDhhmmss)
            to_ts: Upper bound timestamp (YYYYMMDDhhmmss)
            url_contains: Optional URL substring hint (translated into CC wildcard pattern)
        """
        # CC Index accepts domain/* pattern directly
        url_pattern = f"*.{domain}/*" if not domain.startswith("*.") else f"{domain}/*"
        if url_contains:
            kw = self._keyword_to_wildcard(url_contains)
            if kw:
                # Replace the trailing "*" in "domain/*" with "*<kw>*"
                if url_pattern.endswith("*"):
                    url_pattern = url_pattern[:-1] + kw
                else:
                    url_pattern = url_pattern + kw

        return await self._query(
            url_pattern,
            limit=limit,
            filter_status=filter_status,
            filter_mime=filter_mime,
            filter_languages=filter_languages,
            from_ts=from_ts,
            to_ts=to_ts,
            archive=archive,
        )

    async def lookup_url(self, url: str) -> List[CCRecord]:
        """Lookup exact URL in CC Index."""
        return await self._query(url, limit=100)

    async def search(
        self,
        pattern: str,
        limit: int = 10000,
        filter_status: Optional[int] = 200,
        filter_mime: Optional[str] = None,
        filter_languages: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        archive: Optional[str] = None,
    ) -> List[CCRecord]:
        """
        Search CC Index with URL pattern.

        Pattern examples:
            "*.example.com/*" - all subdomains
            "*keyword*" - URLs containing keyword
        """
        return await self._query(
            pattern,
            limit=limit,
            filter_status=filter_status,
            filter_mime=filter_mime,
            filter_languages=filter_languages,
            from_ts=from_ts,
            to_ts=to_ts,
            archive=archive,
        )

    async def _query(
        self,
        url_pattern: str,
        limit: int = 10000,
        filter_status: Optional[int] = None,
        filter_mime: Optional[str] = None,
        filter_languages: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        archive: Optional[str] = None,
    ) -> List[CCRecord]:
        """Execute CC Index query."""
        session = await self._get_session()

        params: List[Tuple[str, Union[str, int]]] = [
            ("url", url_pattern),
            ("output", "json"),
            ("limit", limit),
        ]

        filters: List[str] = []
        if filter_status is not None:
            filters.append(f"status:{filter_status}")
        if filter_mime:
            filters.append(f"mime:{filter_mime}")
        if filter_languages:
            filters.append(f"languages:{filter_languages}")
        for f in filters:
            params.append(("filter", f))
        if from_ts:
            params.append(("from", from_ts))
        if to_ts:
            params.append(("to", to_ts))

        chosen_archive = archive or self.archive
        # API endpoint uses archive-index format
        api_url = f"{CC_INDEX_BASE}/{chosen_archive}-index"

        cache_key = self._cache_key(
            archive=chosen_archive,
            url_pattern=url_pattern,
            limit=limit,
            filters=tuple(f for f in (filter_status, filter_mime, filter_languages, from_ts, to_ts) if f is not None),
            params=params,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        records = []

        retryable_statuses = {429, 500, 502, 503, 504}
        attempts = max(0, self.max_retries)
        for attempt in range(attempts + 1):
            try:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        # Check if it's just "no captures" which is fine
                        if "No Captures found" in text:
                            logger.debug(f"No captures for {url_pattern}")
                            self._cache_set(cache_key, [])
                            return []

                        if resp.status in retryable_statuses and attempt < attempts:
                            retry_after = resp.headers.get("Retry-After")
                            sleep_for = self._backoff_seconds(attempt, retry_after=retry_after)
                            await asyncio.sleep(sleep_for)
                            continue

                        logger.error(f"CC Index error {resp.status}: {text[:200]}")
                        return []

                    # CC Index returns NDJSON
                    text = await resp.text()
                    for line in text.strip().split("\n"):
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            # Skip error messages
                            if "message" in data and "error" in data.get("message", "").lower():
                                continue
                            records.append(CCRecord(
                                url=data.get("url", ""),
                                filename=data.get("filename", ""),
                                offset=int(data.get("offset", 0)),
                                length=int(data.get("length", 0)),
                                status=int(data.get("status", 0)),
                                mime=data.get("mime", ""),
                                timestamp=data.get("timestamp", ""),
                                digest=data.get("digest", ""),
                            ))
                        except (json.JSONDecodeError, ValueError):
                            # Handle non-JSON responses gracefully
                            if "No Captures" not in line:
                                logger.warning(f"Failed to parse CC record: {line[:100]}")
                            continue

                    self._cache_set(cache_key, records)
                    break

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < attempts:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                logger.error(f"CC Index query failed: {e}")
                return []
            except Exception as e:
                logger.error(f"CC Index query failed: {e}")
                return []

        if records:
            logger.info(f"Periscope found {len(records)} records for {url_pattern}")
        return records

    def _keyword_to_wildcard(self, keyword: str) -> str:
        kw = (keyword or "").strip()
        if not kw:
            return ""
        kw = re.sub(r"\s+", "*", kw)
        if not kw.startswith("*"):
            kw = "*" + kw
        if not kw.endswith("*"):
            kw = kw + "*"
        return kw

    def _backoff_seconds(self, attempt: int, *, retry_after: Optional[str] = None) -> float:
        if retry_after:
            try:
                ra = float(retry_after.strip())
                if ra > 0:
                    return min(ra, 60.0)
            except Exception:
                pass
        base = 0.5 * (2 ** max(0, attempt))
        return min(base + (random() * 0.25), 10.0)

    def _cache_key(
        self,
        *,
        archive: str,
        url_pattern: str,
        limit: int,
        filters: Tuple[Any, ...],
        params: List[Tuple[str, Union[str, int]]],
    ) -> str:
        key = {
            "archive": archive,
            "url": url_pattern,
            "limit": int(limit),
            "params": [(k, str(v)) for k, v in params],
        }
        blob = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(blob).hexdigest()

    def _cache_path(self, cache_key: str) -> Optional[Path]:
        if not self.cache_dir or self.cache_ttl_seconds <= 0:
            return None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        return self.cache_dir / f"{cache_key}.json"

    def _cache_get(self, cache_key: str) -> Optional[List[CCRecord]]:
        path = self._cache_path(cache_key)
        if not path or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cached_at = float(data.get("cached_at", 0.0) or 0.0)
            if cached_at and (time.time() - cached_at) > float(self.cache_ttl_seconds):
                return None
            items = data.get("records") or []
            out: List[CCRecord] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                out.append(CCRecord(
                    url=item.get("url", ""),
                    filename=item.get("filename", ""),
                    offset=int(item.get("offset", 0)),
                    length=int(item.get("length", 0)),
                    status=int(item.get("status", 0)),
                    mime=item.get("mime", ""),
                    timestamp=item.get("timestamp", ""),
                    digest=item.get("digest", ""),
                ))
            return out
        except Exception:
            return None

    def _cache_set(self, cache_key: str, records: List[CCRecord]) -> None:
        path = self._cache_path(cache_key)
        if not path:
            return
        payload = {
            "cached_at": time.time(),
            "records": [
                {
                    "url": r.url,
                    "filename": r.filename,
                    "offset": r.offset,
                    "length": r.length,
                    "status": r.status,
                    "mime": r.mime,
                    "timestamp": r.timestamp,
                    "digest": r.digest,
                }
                for r in records
            ],
        }
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            return

    async def stream_lookup(
        self,
        domains: List[str],
        limit_per_domain: int = 1000,
    ) -> AsyncIterator[CCRecord]:
        """
        Stream CC records for multiple domains.
        Yields records as they are found.
        """
        for domain in domains:
            records = await self.lookup_domain(domain, limit=limit_per_domain)
            for record in records:
                yield record

    def estimate_fetch_size(self, records: List[CCRecord]) -> Dict[str, Any]:
        """Estimate total download size and time for records."""
        total_bytes = sum(r.length for r in records)
        unique_warcs = len(set(r.filename for r in records))

        # Estimate based on 200 MB/s throughput
        est_seconds = total_bytes / (200 * 1024 * 1024) if total_bytes > 0 else 0

        return {
            "record_count": len(records),
            "total_bytes": total_bytes,
            "total_mb": total_bytes / (1024 * 1024),
            "unique_warc_files": unique_warcs,
            "est_seconds": est_seconds,
            "est_minutes": est_seconds / 60,
        }


# List available CC archives
AVAILABLE_ARCHIVES = [
    "CC-MAIN-2025-51",
    "CC-MAIN-2025-47",
    "CC-MAIN-2025-43",
    "CC-MAIN-2025-38",
    "CC-MAIN-2025-33",
    "CC-MAIN-2025-30",
    "CC-MAIN-2025-22",
    "CC-MAIN-2025-18",
    "CC-MAIN-2025-13",
    "CC-MAIN-2025-08",
    "CC-MAIN-2024-51",
    "CC-MAIN-2024-46",
]


async def main():
    """Test periscope."""
    import sys
    domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"

    periscope = Periscope()
    try:
        print(f"Looking up {domain} in CC Index...")
        records = await periscope.lookup_domain(domain, limit=100)
        estimate = periscope.estimate_fetch_size(records)

        print(f"Domain: {domain}")
        print(f"Records found: {len(records)}")
        print(f"Total size: {estimate['total_mb']:.1f} MB")
        print(f"Est. time: {estimate['est_minutes']:.1f} min")
        print(f"\nFirst 5 records:")
        for r in records[:5]:
            print(f"  {r.url[:80]}...")
    finally:
        await periscope.close()


if __name__ == "__main__":
    asyncio.run(main())
