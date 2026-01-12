"""High-performance archive searcher with maximum coverage."""

from __future__ import annotations

import asyncio
import aiohttp
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
import unicodedata


logger = logging.getLogger(__name__)


class OptimalArchiveSearcher:
    """
    High-performance archive searcher combining Wayback and CommonCrawl.

    Features:
        - 20 concurrent snapshot fetches per year
        - Parallel year fetching across the full range
        - Hybrid Wayback + CommonCrawl sources
        - Streaming results through an async iterator
    """

    def __init__(
        self,
        max_concurrent_per_year: int = 20,
        sources: Optional[Sequence[str]] = None,
        priority_terms: Optional[Sequence[str]] = None,
        ghost_fetch_bytes: int = 0,
        max_outlinks: int = 50,
    ):
        self.wayback_cdx = "https://web.archive.org/cdx/search/cdx"
        self.wayback_base = "https://web.archive.org/web"
        self.commoncrawl_index = "https://index.commoncrawl.org"
        self.commoncrawl_data = "https://data.commoncrawl.org"
        self.max_concurrent_per_year = max_concurrent_per_year
        self._commoncrawl_cache: list[str] | None = None
        self._commoncrawl_cache_time = 0.0
        self.sources = tuple(s.lower() for s in (sources or ("wayback", "commoncrawl")))
        self.priority_terms = [term.lower() for term in (priority_terms or [
            "report",
            "annual",
            "financial",
            "investor",
            "investors",
            "investor-relations",
            "ir",
            "10-k",
            "10q",
            "20-f",
            "prospectus",
            "team",
            "leadership",
            "management",
            "board",
            "about",
            "company",
            "press",
            "news",
            "blog",
        ])]
        self.ghost_fetch_bytes = max(0, int(ghost_fetch_bytes))
        self.max_outlinks = max(0, int(max_outlinks))

    async def search_keywords_streaming(
        self,
        url: str,
        keywords: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        direction: str = "backwards",
        return_html: bool = False,
        fast_first: bool = False,
    ) -> AsyncIterator[Dict]:
        """Stream archive search results with maximum concurrency."""

        if not years:
            current_year = datetime.now().year
            baseline = list(range(current_year, current_year - 4, -1))
            if current_year - 3 > 2022:
                baseline.append(2022)
            years = sorted(set(baseline), reverse=True)

        # Handle None keywords - means fetch all snapshots without filtering
        skip_keyword_filter = keywords is None or keywords == [] or keywords == [""]
        if skip_keyword_filter:
            keywords = [""]  # Placeholder for iteration, but we'll skip matching

        logger.info("Starting optimal archive search for %s", url)
        logger.info("Years: %s, Direction: %s, Keywords: %s, ReturnHTML: %s", years, direction, keywords, return_html)

        result_queue: asyncio.Queue[Dict | None] = asyncio.Queue()

        fetch_task = asyncio.create_task(
            self._fetch_years_parallel(
                url,
                keywords,
                years,
                direction,
                result_queue,
                return_html,
                skip_keyword_filter,
                fast_first,
            )
        )

        results_count = 0
        try:
            while True:
                try:
                    result = await asyncio.wait_for(result_queue.get(), timeout=1.0)
                    if result is None:
                        break
                    results_count += 1
                    yield result
                except asyncio.TimeoutError:
                    if fetch_task.done():
                        break
                    continue
        finally:
            await fetch_task
            logger.info("Optimal archive search complete: %s results", results_count)

    async def _fetch_years_parallel(
        self,
        url: str,
        keywords: List[str],
        years: List[int],
        direction: str,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        # Rate limit concurrent years to prevent connection overload
        # Each year spawns 20 concurrent fetches, so 4 years = 80 concurrent requests max
        MAX_CONCURRENT_YEARS = 4
        year_semaphore = asyncio.Semaphore(MAX_CONCURRENT_YEARS)
        completed_years = 0
        total_years = len(years)

        async def fetch_year_limited(year: int) -> None:
            nonlocal completed_years
            async with year_semaphore:
                await self._fetch_year(
                    url,
                    keywords,
                    year,
                    direction,
                    result_queue,
                    return_html,
                    skip_keyword_filter,
                    fast_first,
                )
                completed_years += 1
                # Emit year completion progress event
                await result_queue.put({
                    "type": "status",
                    "channel": "progress",
                    "state": "year_complete",
                    "year": year,
                    "completed": completed_years,
                    "total": total_years,
                    "percent": int(100 * completed_years / total_years),
                    "message": f"Year {year} complete ({completed_years}/{total_years})"
                })

        tasks = [asyncio.create_task(fetch_year_limited(year)) for year in years]
        await asyncio.gather(*tasks, return_exceptions=True)
        await result_queue.put(None)

    async def _fetch_year(
        self,
        url: str,
        keywords: List[str],
        year: int,
        direction: str,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        async with aiohttp.ClientSession() as session:
            tasks = []
            if "wayback" in self.sources:
                tasks.append(
                    self._fetch_wayback_year(
                        session,
                        url,
                        year,
                        keywords,
                        direction,
                        result_queue,
                        return_html,
                        skip_keyword_filter,
                        fast_first,
                    )
                )

            if "commoncrawl" in self.sources:
                tasks.append(
                    self._fetch_commoncrawl_year(
                        session,
                        url,
                        year,
                        keywords,
                        direction,
                        result_queue,
                        return_html,
                        skip_keyword_filter,
                        fast_first,
                    )
                )

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_wayback_year(
        self,
        session: aiohttp.ClientSession,
        url: str,
        year: int,
        keywords: List[str],
        direction: str,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        try:
            snapshots = await self._get_wayback_snapshots(session, url, year)

            if not snapshots:
                return

            logger.info("Wayback %s: Found %s snapshots", year, len(snapshots))

            semaphore = asyncio.Semaphore(self.max_concurrent_per_year)

            snapshots = self._prioritize_snapshots(snapshots, direction)

            tasks = [
                self._fetch_wayback_snapshot(
                    session,
                    semaphore,
                    timestamp,
                    original_url,
                    digest,
                    keywords,
                    year,
                    result_queue,
                    return_html,
                    skip_keyword_filter,
                    fast_first,
                )
                for timestamp, original_url, digest in snapshots
            ]

            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as exc:
            logger.error("Wayback %s error: %s", year, exc)

    async def _get_wayback_snapshots(
        self,
        session: aiohttp.ClientSession,
        url: str,
        year: int,
    ) -> List[Tuple[str, str, str]]:
        """Get Wayback snapshot metadata for a year."""

        host = urlparse(url if url.startswith("http") else f"http://{url}").netloc
        if not host:
            host = url

        patterns = [
            host,
            f"{host}/*",
            f"www.{host}",
            f"www.{host}/*",
            f"*.{host}/*",
        ]

        seen: Set[Tuple[str, str]] = set()
        snapshots: List[Tuple[str, str, str]] = []

        for pattern in patterns:
            params = {
                "url": pattern,
                "output": "json",
                "fl": "timestamp,original,digest",
                "filter": ["statuscode:200", "mimetype:text/html"],
                "collapse": "digest",
                "from": f"{year}0101",
                "to": f"{year}1231",
            }

            try:
                async with session.get(self.wayback_cdx, params=params, timeout=20) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()
            except Exception as exc:
                logger.debug("Wayback CDX error for %s: %s", pattern, exc)
                continue

            if not data or len(data) <= 1:
                continue

            for row in data[1:]:
                if len(row) < 2:
                    continue
                timestamp, original, *rest = row
                digest = rest[0] if rest else ""
                key = (timestamp, original)
                if key in seen:
                    continue
                seen.add(key)
                snapshots.append((timestamp, original, digest))

        snapshots.sort(key=lambda item: item[0], reverse=True)
        return snapshots

    async def _fetch_wayback_snapshot(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        timestamp: str,
        original_url: str,
        digest: str,
        keywords: List[str],
        year: int,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        async with semaphore:
            try:
                snapshot_url = f"{self.wayback_base}/{timestamp}id_/{original_url}"
                parsed_url = urlparse(original_url)
                display_target = parsed_url.netloc or parsed_url.path or original_url

                await result_queue.put(
                    {
                        "type": "status",
                        "channel": "deep",
                        "state": "progress",
                        "message": f"{year} ▸ {timestamp} ▸ {display_target}",
                    }
                )

                if fast_first and not skip_keyword_filter and self.ghost_fetch_bytes > 0:
                    ghost = await self._ghost_fetch(session, snapshot_url)
                    if ghost:
                        lower = ghost.lower()
                        for keyword in keywords:
                            if keyword.lower() in lower:
                                snapshot_result = {
                                    "url": original_url,
                                    "timestamp": timestamp,
                                    "year": year,
                                    "keyword": keyword,
                                    "source": "wayback",
                                    "digest": digest,
                                    "snippet": self._extract_snippet(ghost, keyword),
                                    "ghost": True,
                                }
                                if return_html:
                                    snapshot_result["html"] = ghost
                                await result_queue.put(snapshot_result)
                                await result_queue.put(
                                    {
                                        "type": "status",
                                        "channel": "deep",
                                        "state": "hit",
                                        "message": f"Match • {keyword} • {display_target} • {timestamp}",
                                        "payload": snapshot_result,
                                    }
                                )
                                return

                async with session.get(snapshot_url, timeout=30) as response:
                    if response.status != 200:
                        return
                    html = await response.text(errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    text = soup.get_text(separator=" ", strip=True)
                    parsed_url = urlparse(original_url)
                    outlinks, outlink_notes, outlink_domains = self._extract_outlinks(
                        soup,
                        original_url,
                        parsed_url.netloc,
                    )

                    # If skip_keyword_filter=True, return ALL snapshots (for entity extraction)
                    if skip_keyword_filter:
                        snapshot_result = {
                            "url": original_url,
                            "timestamp": timestamp,
                            "year": year,
                            "keyword": None,
                            "source": "wayback",
                            "digest": digest,
                            "snippet": text[:300] if text else "",
                            "outlinks": outlinks,
                            "outlink_notes": outlink_notes,
                            "outlink_domains": outlink_domains,
                        }
                        if return_html:
                            snapshot_result["html"] = html
                        await result_queue.put(snapshot_result)
                        return

                    # Normal keyword matching
                    text_lower = text.lower()
                    text_ascii = unicodedata.normalize("NFKD", text_lower)
                    text_ascii = "".join(ch for ch in text_ascii if not unicodedata.combining(ch))

                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        keyword_ascii = unicodedata.normalize("NFKD", keyword_lower)
                        keyword_ascii = "".join(ch for ch in keyword_ascii if not unicodedata.combining(ch))

                        if keyword_lower in text_lower or keyword_ascii in text_ascii:
                            snapshot_result = {
                                "url": original_url,
                                "timestamp": timestamp,
                                "year": year,
                                "keyword": keyword,
                                "source": "wayback",
                                "digest": digest,
                                "snippet": self._extract_snippet(text, keyword),
                                "outlinks": outlinks,
                                "outlink_notes": outlink_notes,
                                "outlink_domains": outlink_domains,
                            }
                            if return_html:
                                snapshot_result["html"] = html

                            await result_queue.put(snapshot_result)
                            await result_queue.put(
                                {
                                    "type": "status",
                                    "channel": "deep",
                                    "state": "hit",
                                    "message": f"Match • {keyword} • {display_target} • {timestamp}",
                                    "payload": snapshot_result,
                                }
                            )
                            return
            except Exception as exc:
                logger.debug("Wayback snapshot fetch error: %s", exc)

    async def _fetch_commoncrawl_year(
        self,
        session: aiohttp.ClientSession,
        url: str,
        year: int,
        keywords: List[str],
        direction: str,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        try:
            crawls = await self._get_commoncrawl_crawls(session)

            year_crawls = [c for c in crawls if str(year) in c][:3]

            if not year_crawls:
                return

            logger.info("CommonCrawl %s: Searching %s crawls", year, len(year_crawls))

            tasks = [
                    self._search_commoncrawl_index(
                        session,
                        crawl_id,
                        url,
                        keywords,
                        year,
                        direction,
                        result_queue,
                        return_html,
                        skip_keyword_filter,
                        fast_first,
                    )
                for crawl_id in year_crawls
            ]

            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as exc:
            logger.error("CommonCrawl %s error: %s", year, exc)

    async def _get_commoncrawl_crawls(self, session: aiohttp.ClientSession) -> List[str]:
        if self._commoncrawl_cache and (time.time() - self._commoncrawl_cache_time) < 3600:
            return self._commoncrawl_cache

        try:
            async with session.get(f"{self.commoncrawl_index}/collinfo.json", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    crawls = [item["id"] for item in sorted(data, key=lambda x: x["id"], reverse=True)]
                    self._commoncrawl_cache = crawls
                    self._commoncrawl_cache_time = time.time()
                    return crawls
        except Exception as exc:
            logger.error("CommonCrawl crawls error: %s", exc)

        return []

    async def _search_commoncrawl_index(
        self,
        session: aiohttp.ClientSession,
        crawl_id: str,
        url: str,
        keywords: List[str],
        year: int,
        direction: str,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        host = urlparse(url if url.startswith("http") else f"http://{url}").netloc

        patterns = [f"{host}/*", f"*.{host}/*", f"{host}"]

        for pattern in patterns:
            try:
                params = {
                    "url": pattern,
                    "output": "json",
                    "limit": 500,
                    "fl": "url,timestamp,status,offset,length,filename,mime,digest",
                }

                index_url = f"{self.commoncrawl_index}/{crawl_id}-index"

                async with session.get(index_url, params=params, timeout=20) as response:
                    if response.status != 200:
                        continue

                    async for line in response.content:
                        if not line:
                            continue

                        try:
                            record = json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue

                        if not record.get("status", "").startswith("200"):
                            continue

                        if "text/html" not in record.get("mime", ""):
                            continue

                        await self._fetch_commoncrawl_content(
                            session,
                            record,
                            keywords,
                            year,
                            result_queue,
                            return_html,
                            skip_keyword_filter,
                            fast_first,
                        )

                    break
            except Exception as exc:
                logger.debug("CommonCrawl index error for %s: %s", pattern, exc)
                continue

    async def _fetch_commoncrawl_content(
        self,
        session: aiohttp.ClientSession,
        record: Dict,
        keywords: List[str],
        year: int,
        result_queue: asyncio.Queue[Dict | None],
        return_html: bool = False,
        skip_keyword_filter: bool = False,
        fast_first: bool = False,
    ) -> None:
        try:
            offset = record.get("offset")
            length = record.get("length")
            filename = record.get("filename")
            digest = record.get("digest", "")

            if offset is None or length is None or not filename:
                return

            warc_url = f"{self.commoncrawl_data}/{filename}"
            headers = {"Range": f"bytes={offset}-{int(offset) + int(length) - 1}"}

            async with session.get(warc_url, headers=headers, timeout=30) as response:
                if response.status != 206:
                    return

                content = await response.text(errors="ignore")
                html_start = content.find("<html")
                if html_start == -1:
                    # Try lowercase
                    html_start = content.lower().find("<html")
                if html_start == -1:
                    return

                html = content[html_start:]
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                page_url = record.get("url", "")
                parsed_url = urlparse(page_url)
                outlinks, outlink_notes, outlink_domains = self._extract_outlinks(
                    soup,
                    page_url,
                    parsed_url.netloc,
                )

                # If skip_keyword_filter=True, return ALL pages (for entity extraction)
                if skip_keyword_filter:
                    cc_result = {
                        "url": record.get("url", ""),
                        "timestamp": record.get("timestamp", ""),
                        "year": year,
                        "keyword": None,
                        "source": "commoncrawl",
                        "digest": digest,
                        "snippet": text[:300] if text else "",
                        "outlinks": outlinks,
                        "outlink_notes": outlink_notes,
                        "outlink_domains": outlink_domains,
                    }
                    if return_html:
                        cc_result["html"] = html
                    await result_queue.put(cc_result)
                    return

                # Normal keyword matching
                lower = text.lower()
                for keyword in keywords:
                    if keyword.lower() in lower:
                        cc_result = {
                            "url": record.get("url", ""),
                            "timestamp": record.get("timestamp", ""),
                            "year": year,
                            "keyword": keyword,
                            "source": "commoncrawl",
                            "digest": digest,
                            "snippet": self._extract_snippet(text, keyword),
                            "outlinks": outlinks,
                            "outlink_notes": outlink_notes,
                            "outlink_domains": outlink_domains,
                        }
                        if return_html:
                            cc_result["html"] = html
                        await result_queue.put(cc_result)
                        break
        except Exception as exc:
            logger.debug("CommonCrawl content fetch error: %s", exc)

    def _prioritize_snapshots(
        self,
        snapshots: List[Tuple[str, str, str]],
        direction: str,
    ) -> List[Tuple[str, str, str]]:
        def score(url: str) -> int:
            url_lower = url.lower()
            points = 0
            if url_lower.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")):
                points += 6
            for term in self.priority_terms:
                if term in url_lower:
                    points += 3
            return points

        def ts_int(ts: str) -> int:
            try:
                return int(ts)
            except ValueError:
                return 0

        reverse_time = direction != "forwards"
        return sorted(
            snapshots,
            key=lambda item: (
                -score(item[1]),
                -ts_int(item[0]) if reverse_time else ts_int(item[0]),
            ),
        )

    async def _ghost_fetch(
        self,
        session: aiohttp.ClientSession,
        snapshot_url: str,
    ) -> Optional[str]:
        headers = {"Range": f"bytes=0-{self.ghost_fetch_bytes - 1}"}
        try:
            async with session.get(snapshot_url, headers=headers, timeout=10) as response:
                if response.status not in (200, 206):
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if content_type and "text" not in content_type and "html" not in content_type:
                    return None
                payload = await response.read()
                return payload.decode(errors="ignore")
        except Exception:
            return None

    def _extract_outlinks(
        self,
        soup: BeautifulSoup,
        base_url: str,
        base_domain: str,
    ) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
        if self.max_outlinks <= 0:
            return [], [], []

        base_domain = (base_domain or "").lower().lstrip("www.")
        seen: Set[str] = set()
        outlinks: List[str] = []
        outlink_notes: List[Dict[str, str]] = []
        outlink_domains: Set[str] = set()

        for tag in soup.find_all("a", href=True):
            href = (tag.get("href") or "").strip()
            if not href:
                continue
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            target_domain = parsed.netloc.lower().lstrip("www.")
            if not target_domain:
                continue
            if base_domain and (target_domain.endswith(base_domain) or base_domain.endswith(target_domain)):
                continue

            if full_url in seen:
                continue
            seen.add(full_url)

            anchor_text = tag.get_text(separator=" ", strip=True)[:200]
            outlinks.append(full_url)
            outlink_domains.add(target_domain)
            if anchor_text:
                outlink_notes.append({"url": full_url, "anchor_text": anchor_text})

            if len(outlinks) >= self.max_outlinks:
                break

        return outlinks, outlink_notes, sorted(outlink_domains)

    @staticmethod
    def _extract_snippet(text: str, keyword: str, context_chars: int = 150) -> str:
        text_lower = text.lower()
        keyword_lower = keyword.lower()

        pos = text_lower.find(keyword_lower)
        if pos == -1:
            return text[:context_chars]

        start = max(0, pos - context_chars // 2)
        end = min(len(text), pos + len(keyword) + context_chars // 2)

        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet
