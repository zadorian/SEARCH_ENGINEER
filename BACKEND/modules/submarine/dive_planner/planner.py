#!/usr/bin/env python3
"""
DIVE PLANNER - Orchestrates smart CC searches

The intelligence layer that:
1. Takes a search target (phone, email, name, domain)
2. Uses SONAR to find relevant domains in our indices
3. Uses PERISCOPE to find CC Index records for those domains
4. Creates an optimized dive plan (which WARCs to fetch, in what order)
5. Estimates time/cost before execution
6. Passes plan to DEEP DIVE for execution

This is the key to turning 24 hours → minutes.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Import our modules
import sys
sys.path.insert(0, "/data/SUBMARINE")

from sonar.elastic_scanner import Sonar, SonarResult
from periscope.cc_index import Periscope, CCRecord


@dataclass
class DiveTarget:
    """A single target to search for in CC."""
    domain: str
    priority: int = 1  # 1=highest, 5=lowest
    source: str = "unknown"  # Where we found this domain
    cc_records: List[CCRecord] = field(default_factory=list)
    estimated_pages: int = 0

    @property
    def estimated_fetch_time(self) -> float:
        """Estimate time to fetch all pages for this domain (seconds)."""
        # ~100ms per fetch with range requests
        return self.estimated_pages * 0.1


@dataclass
class DivePlan:
    """Complete dive plan ready for execution."""
    query: str
    query_type: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Targets ordered by priority
    targets: List[DiveTarget] = field(default_factory=list)

    # Stats
    total_domains: int = 0
    total_pages: int = 0
    estimated_time_seconds: float = 0
    estimated_warc_bytes: int = 0

    # Which indices contributed
    sonar_indices_used: List[str] = field(default_factory=list)
    cc_archives_queried: List[str] = field(default_factory=list)

    # For checkpointing
    completed_domains: Set[str] = field(default_factory=set)

    def add_target(self, target: DiveTarget):
        """Add a target and update stats."""
        self.targets.append(target)
        self.total_domains += 1
        self.total_pages += target.estimated_pages
        self.estimated_time_seconds += target.estimated_fetch_time

    def to_dict(self, full: bool = False) -> Dict[str, Any]:
        """
        Serialize plan for storage/display.

        Args:
            full: If True, include full CC records for resume capability.
                  If False, include summary only for display.
        """
        targets_data = []
        for t in self.targets:
            target_dict = {
                "domain": t.domain,
                "priority": t.priority,
                "source": t.source,
                "estimated_pages": t.estimated_pages,
            }
            if full:
                # Include full CC records for resume
                target_dict["cc_records"] = [
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
                    for r in t.cc_records
                ]
            else:
                target_dict["cc_records_count"] = len(t.cc_records)
            targets_data.append(target_dict)

        return {
            "query": self.query,
            "query_type": self.query_type,
            "created_at": self.created_at.isoformat(),
            "total_domains": self.total_domains,
            "total_pages": self.total_pages,
            "estimated_time_seconds": self.estimated_time_seconds,
            "estimated_time_human": self._format_time(self.estimated_time_seconds),
            "estimated_warc_bytes": self.estimated_warc_bytes,
            "sonar_indices_used": self.sonar_indices_used,
            "cc_archives_queried": self.cc_archives_queried,
            "targets": targets_data if full else targets_data[:100],
            "completed_domains": list(self.completed_domains),
        }

    def _format_time(self, seconds: float) -> str:
        """Format seconds as human-readable."""
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            return f"{seconds/60:.1f} minutes"
        else:
            return f"{seconds/3600:.1f} hours"

    def save(self, path: str, full: bool = True):
        """
        Save plan to file.

        Args:
            path: Output file path
            full: If True (default), save full CC records for resume.
        """
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(self.to_dict(full=full), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(out_path)

    @classmethod
    def load(cls, path: str) -> "DivePlan":
        """
        Load plan from file (for resume).

        Fully restores targets with CC records if they were saved.
        """
        with open(path) as f:
            data = json.load(f)

        plan = cls(
            query=data["query"],
            query_type=data["query_type"],
        )

        # Parse created_at if present
        if "created_at" in data:
            try:
                plan.created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                pass

        plan.total_domains = data.get("total_domains", 0)
        plan.total_pages = data.get("total_pages", 0)
        plan.estimated_time_seconds = data.get("estimated_time_seconds", 0)
        plan.estimated_warc_bytes = data.get("estimated_warc_bytes", 0)
        plan.sonar_indices_used = data.get("sonar_indices_used", [])
        plan.cc_archives_queried = data.get("cc_archives_queried", [])
        plan.completed_domains = set(data.get("completed_domains", []))

        # Restore targets with CC records
        for target_data in data.get("targets", []):
            cc_records = []

            # Restore CC records if saved
            for rec_data in target_data.get("cc_records", []):
                cc_records.append(CCRecord(
                    url=rec_data.get("url", ""),
                    filename=rec_data.get("filename", ""),
                    offset=int(rec_data.get("offset", 0)),
                    length=int(rec_data.get("length", 0)),
                    status=int(rec_data.get("status", 0)),
                    mime=rec_data.get("mime", ""),
                    timestamp=rec_data.get("timestamp", ""),
                    digest=rec_data.get("digest", ""),
                ))

            target = DiveTarget(
                domain=target_data.get("domain", ""),
                priority=target_data.get("priority", 5),
                source=target_data.get("source", "unknown"),
                cc_records=cc_records,
                estimated_pages=target_data.get("estimated_pages", len(cc_records)),
            )
            plan.targets.append(target)

        return plan


class DivePlanner:
    """
    Creates optimized dive plans for CC searches.

    Usage:
        planner = DivePlanner()
        plan = await planner.create_plan("+1-234-567-8900")
        print(f"Found {plan.total_domains} domains, {plan.total_pages} pages")
        print(f"Estimated time: {plan.estimated_time_seconds/60:.1f} minutes")

        # Execute with deep_dive
        await deep_dive.execute(plan)
    """

    def __init__(
        self,
        es_host: str = "http://localhost:9200",
        cc_archive: str = "CC-MAIN-2025-51",
    ):
        self.sonar = Sonar(es_host=es_host)
        self.periscope = Periscope(archive=cc_archive)
        self.cc_archive = cc_archive

    async def close(self):
        """Cleanup resources."""
        await self.sonar.close()
        await self.periscope.close()

    async def create_plan(
        self,
        query: str,
        max_domains: int = 1000,
        max_pages_per_domain: int = 100,
        cc_archives: Optional[List[str]] = None,
        # CC Index filter controls (submerging points)
        filter_status: Optional[int] = 200,
        filter_mime: Optional[str] = None,
        filter_languages: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        # Domain intelligence / constraints
        domain_allowlist: Optional[List[str]] = None,
        domain_denylist: Optional[List[str]] = None,
        tld_include: Optional[List[str]] = None,
        tld_exclude: Optional[List[str]] = None,
        # URL pattern hints
        url_contains: Optional[str] = None,
        # Fallback behavior when SONAR yields no domains
        enable_cc_keyword_fallback: bool = True,
    ) -> DivePlan:
        """
        Create a dive plan for the given query.

        Steps:
        1. SONAR scan - find relevant domains in our indices
        2. PERISCOPE lookup - find CC Index records for those domains
        3. Prioritize and estimate
        4. Return plan ready for execution
        """
        # Step 1: SONAR - find domains in our indices
        logger.info(f"DIVE PLANNER: Starting plan for '{query}'")

        try:
            max_domains_cap = int(os.getenv("SUBMARINE_MAX_DOMAINS_CAP", "5000"))
        except Exception:
            max_domains_cap = 5000
        max_domains = max(1, min(int(max_domains), max_domains_cap))

        try:
            max_pages_cap = int(os.getenv("SUBMARINE_MAX_PAGES_PER_DOMAIN_CAP", "500"))
        except Exception:
            max_pages_cap = 500
        max_pages_per_domain = max(1, min(int(max_pages_per_domain), max_pages_cap))

        filter_mime = self._normalize_mime(filter_mime)
        filter_languages = self._normalize_language(filter_languages)
        from_ts = self._normalize_cc_timestamp(from_ts, end=False)
        to_ts = self._normalize_cc_timestamp(to_ts, end=True)

        sonar_result = await self.sonar.scan_all(query, limit=max_domains * 10)

        plan = DivePlan(
            query=query,
            query_type=self.sonar._detect_query_type(query),
            sonar_indices_used=sonar_result.indices_scanned,
        )

        # Seed domains from SONAR (preferred) or direct query hints.
        seed_domains = self._seed_domains(query, plan.query_type, sonar_result)
        seed_domains = self._apply_domain_filters(
            seed_domains,
            allowlist=domain_allowlist,
            denylist=domain_denylist,
            tld_include=tld_include,
            tld_exclude=tld_exclude,
        )

        if not seed_domains:
            # If a domain allowlist (e.g., TORPEDO news domains) is provided, treat it
            # as a submerging point even when SONAR yields nothing.
            if domain_allowlist:
                seed_domains = self._apply_domain_filters(
                    domain_allowlist,
                    allowlist=None,
                    denylist=domain_denylist,
                    tld_include=tld_include,
                    tld_exclude=tld_exclude,
                )

            if not seed_domains:
                # SONAR (or ES) may be unavailable; still support CC keyword search.
                fallback_keyword = url_contains
                if not fallback_keyword and enable_cc_keyword_fallback and plan.query_type == "entity":
                    fallback_keyword = query

                if enable_cc_keyword_fallback and fallback_keyword:
                    return await self._create_plan_from_cc_keyword(
                        query=query,
                        keyword=fallback_keyword,
                        max_domains=max_domains,
                        max_pages_per_domain=max_pages_per_domain,
                        cc_archives=cc_archives,
                        filter_status=filter_status,
                        filter_mime=filter_mime,
                        filter_languages=filter_languages,
                        from_ts=from_ts,
                        to_ts=to_ts,
                        domain_allowlist=domain_allowlist,
                        domain_denylist=domain_denylist,
                        tld_include=tld_include,
                        tld_exclude=tld_exclude,
                    )

                # If the query itself is a domain, we already tried to seed it above. Nothing left.
                logger.warning(f"No domains available for '{query}' after filters")
                return plan

        logger.info(f"Candidate domains: {len(seed_domains)}")

        # Step 2: Prioritize domains
        # - Exact domain matches get priority 1
        # - Subdomains get priority 2
        # - Related domains get priority 3
        domain_priorities = self._prioritize_domains(query, sonar_result)
        # If filters removed many domains, ensure priorities contains the survivors.
        filtered_set = set(seed_domains)
        domain_priorities = {d: p for d, p in domain_priorities.items() if d in filtered_set}
        default_priority = 5
        if not sonar_result.domains and plan.query_type in {"domain", "url", "email"}:
            default_priority = 1
        for d in seed_domains:
            domain_priorities.setdefault(d, default_priority)

        # Step 3: PERISCOPE - lookup CC Index for each domain
        cc_archives = cc_archives or [self.cc_archive]
        plan.cc_archives_queried = cc_archives

        domains_to_check = sorted(
            domain_priorities.items(),
            key=lambda x: x[1]  # Sort by priority
        )[:max_domains]

        logger.info(f"Looking up {len(domains_to_check)} domains in CC Index...")

        # Batch lookup with bounded concurrency (CC Index can rate-limit).
        concurrency_env = os.getenv("SUBMARINE_CC_INDEX_CONCURRENCY", "").strip()
        try:
            concurrency = int(concurrency_env) if concurrency_env else 8
        except Exception:
            concurrency = 8
        concurrency = max(1, min(concurrency, 32))
        sem = asyncio.Semaphore(concurrency)

        async def _lookup_domain(domain: str, priority: int) -> Tuple[str, int, List[CCRecord], Optional[str]]:
            async with sem:
                try:
                    combined_records: List[CCRecord] = []
                    for archive in cc_archives:
                        records = await self.periscope.lookup_domain(
                            domain,
                            limit=max_pages_per_domain,
                            filter_status=filter_status,
                            filter_mime=filter_mime,
                            filter_languages=filter_languages,
                            from_ts=from_ts,
                            to_ts=to_ts,
                            url_contains=url_contains,
                            archive=archive,
                        )
                        if records:
                            combined_records.extend(records)
                        if len(combined_records) >= max_pages_per_domain:
                            break

                    # Dedupe combined records (multi-archive plans).
                    if combined_records:
                        seen = set()
                        records_out: List[CCRecord] = []
                        for r in combined_records:
                            key = (r.filename, r.offset, r.length)
                            if key in seen:
                                continue
                            seen.add(key)
                            records_out.append(r)
                            if len(records_out) >= max_pages_per_domain:
                                break
                    else:
                        records_out = []

                    return domain, priority, records_out, None
                except Exception as e:
                    return domain, priority, [], str(e)

        tasks = [asyncio.create_task(_lookup_domain(d, p)) for d, p in domains_to_check]
        for fut in asyncio.as_completed(tasks):
            domain, priority, records, err = await fut
            if err:
                logger.warning(f"Error looking up {domain} in CC Index: {err}")
                continue
            if not records:
                continue
            target = DiveTarget(
                domain=domain,
                priority=priority,
                source=self._get_domain_source(domain, sonar_result),
                cc_records=records,
                estimated_pages=len(records),
            )
            plan.add_target(target)
            for r in records:
                plan.estimated_warc_bytes += r.length

        # Sort targets by priority
        plan.targets.sort(key=lambda t: t.priority)

        logger.info(
            f"DIVE PLAN READY: {plan.total_domains} domains, "
            f"{plan.total_pages} pages, ~{plan.estimated_time_seconds/60:.1f} min"
        )

        return plan

    async def create_plan_from_domains(
        self,
        query: str,
        domains: List[str],
        max_pages_per_domain: int = 100,
        source: str = "exploration",
        cc_archives: Optional[List[str]] = None,
        priorities: Optional[Dict[str, int]] = None,
        filter_status: Optional[int] = 200,
        filter_mime: Optional[str] = None,
        filter_languages: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        url_contains: Optional[str] = None,
    ) -> DivePlan:
        """
        Create a dive plan when domains are already known.

        Used by exploration workflows (indom/inurl) where SONAR's query classifier
        would not necessarily produce the desired domain list.
        """
        plan = DivePlan(
            query=query,
            query_type="domain_list",
            sonar_indices_used=[source],
        )

        try:
            max_pages_cap = int(os.getenv("SUBMARINE_MAX_PAGES_PER_DOMAIN_CAP", "500"))
        except Exception:
            max_pages_cap = 500
        max_pages_per_domain = max(1, min(int(max_pages_per_domain), max_pages_cap))

        filter_mime = self._normalize_mime(filter_mime)
        filter_languages = self._normalize_language(filter_languages)
        from_ts = self._normalize_cc_timestamp(from_ts, end=False)
        to_ts = self._normalize_cc_timestamp(to_ts, end=True)

        cleaned: List[str] = []
        seen: Set[str] = set()
        for d in domains or []:
            dl = (d or "").strip().lower()
            if dl.startswith("www."):
                dl = dl[4:]
            if not dl or "." not in dl:
                continue
            if dl in seen:
                continue
            seen.add(dl)
            cleaned.append(dl)

        if not cleaned:
            logger.warning("No domains provided to create_plan_from_domains")
            return plan

        # PERISCOPE lookup for each domain
        cc_archives = cc_archives or [self.cc_archive]
        plan.cc_archives_queried = cc_archives

        domain_priorities = priorities or {d: 1 for d in cleaned}
        domains_to_check = sorted(domain_priorities.items(), key=lambda x: x[1])[:1000]

        concurrency_env = os.getenv("SUBMARINE_CC_INDEX_CONCURRENCY", "").strip()
        try:
            concurrency = int(concurrency_env) if concurrency_env else 8
        except Exception:
            concurrency = 8
        concurrency = max(1, min(concurrency, 32))
        sem = asyncio.Semaphore(concurrency)

        async def _lookup_domain(domain: str, priority: int) -> Tuple[str, int, List[CCRecord], Optional[str]]:
            async with sem:
                try:
                    combined_records: List[CCRecord] = []
                    for archive in cc_archives:
                        recs = await self.periscope.lookup_domain(
                            domain,
                            limit=max_pages_per_domain,
                            filter_status=filter_status,
                            filter_mime=filter_mime,
                            filter_languages=filter_languages,
                            from_ts=from_ts,
                            to_ts=to_ts,
                            url_contains=url_contains,
                            archive=archive,
                        )
                        if recs:
                            combined_records.extend(recs)
                        if len(combined_records) >= max_pages_per_domain:
                            break

                    # Dedupe combined records.
                    if combined_records:
                        seen = set()
                        records_out: List[CCRecord] = []
                        for r in combined_records:
                            key = (r.filename, r.offset, r.length)
                            if key in seen:
                                continue
                            seen.add(key)
                            records_out.append(r)
                            if len(records_out) >= max_pages_per_domain:
                                break
                    else:
                        records_out = []

                    return domain, priority, records_out, None
                except Exception as e:
                    return domain, priority, [], str(e)

        tasks = [asyncio.create_task(_lookup_domain(d, p)) for d, p in domains_to_check]
        for fut in asyncio.as_completed(tasks):
            domain, priority, records, err = await fut
            if err:
                logger.warning(f"Error looking up {domain} in CC Index: {err}")
                continue
            if not records:
                continue
            target = DiveTarget(
                domain=domain,
                priority=priority,
                source=source,
                cc_records=records,
                estimated_pages=len(records),
            )
            plan.add_target(target)
            for r in records:
                plan.estimated_warc_bytes += r.length

        plan.targets.sort(key=lambda t: t.priority)
        return plan

    def _seed_domains(self, query: str, query_type: str, sonar_result: SonarResult) -> List[str]:
        # Start from SONAR hits if present.
        domains: List[str] = sorted({(d or "").strip().lower() for d in (sonar_result.domains or []) if d})

        # If SONAR produced nothing, fall back to direct query parsing for domain/url/email inputs.
        if domains:
            return self._normalize_domains(domains)

        q = (query or "").strip()
        if not q:
            return []

        seed: List[str] = []
        if query_type == "domain":
            seed.append(q)
        elif query_type == "url":
            try:
                parsed = urlparse(q)
                if parsed.netloc:
                    seed.append(parsed.netloc)
            except Exception:
                pass
        elif query_type == "email" and "@" in q:
            seed.append(q.split("@")[-1])

        return self._normalize_domains(seed)

    def _normalize_domains(self, domains: List[str]) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for d in domains or []:
            dl = (d or "").strip().lower()
            if dl.startswith("www."):
                dl = dl[4:]
            if ":" in dl:
                dl = dl.split(":", 1)[0]
            if not dl or "." not in dl:
                continue
            if dl in seen:
                continue
            seen.add(dl)
            out.append(dl)
        return out

    def _apply_domain_filters(
        self,
        domains: List[str],
        *,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
        tld_include: Optional[List[str]] = None,
        tld_exclude: Optional[List[str]] = None,
    ) -> List[str]:
        if not domains:
            return []

        allow_set = set(self._normalize_domains(allowlist or []))
        deny_set = set(self._normalize_domains(denylist or []))
        tld_inc = self._normalize_suffixes(tld_include or [])
        tld_exc = self._normalize_suffixes(tld_exclude or [])

        def _matches_base(domain: str, bases: set[str]) -> bool:
            if not bases:
                return False
            cur = domain
            while True:
                if cur in bases:
                    return True
                if "." not in cur:
                    return False
                cur = cur.split(".", 1)[1]

        def _suffix_match(domain: str, suffixes: List[str]) -> bool:
            for suf in suffixes:
                if domain.endswith(f".{suf}"):
                    return True
            return False

        out: List[str] = []
        for d in self._normalize_domains(domains):
            if allow_set and not _matches_base(d, allow_set):
                continue
            if deny_set and _matches_base(d, deny_set):
                continue
            if tld_inc and not _suffix_match(d, tld_inc):
                continue
            if tld_exc and _suffix_match(d, tld_exc):
                continue
            out.append(d)
        return out

    def _normalize_suffixes(self, suffixes: List[str]) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for s in suffixes or []:
            suf = (s or "").strip().lower().lstrip(".")
            if not suf:
                continue
            if suf in seen:
                continue
            seen.add(suf)
            out.append(suf)
        return out

    def _normalize_cc_timestamp(self, value: Optional[str], *, end: bool) -> Optional[str]:
        v = (value or "").strip()
        if not v:
            return None

        if re.fullmatch(r"\d{14}", v):
            return v

        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            v = "".join(m.groups())

        if re.fullmatch(r"\d{8}", v):
            return v + ("235959" if end else "000000")

        # Best-effort: let CC Index handle unknown formats (or ignore).
        return v

    def _normalize_mime(self, mime: Optional[str]) -> Optional[str]:
        m = (mime or "").strip().lower()
        if not m:
            return None
        if m in {"pdf", ".pdf"}:
            return "application/pdf"
        if m in {"html", ".html", "htm", ".htm"}:
            return "text/html"
        return m

    def _normalize_language(self, language: Optional[str]) -> Optional[str]:
        l = (language or "").strip().lower()
        if not l:
            return None
        # Common Crawl uses 3-letter codes (e.g., "eng"). Best-effort mapping for 2-letter inputs.
        if len(l) == 2:
            return {
                "en": "eng",
                "de": "deu",
                "fr": "fra",
                "es": "spa",
                "pt": "por",
                "ru": "rus",
                "it": "ita",
                "nl": "nld",
            }.get(l, l)
        return l

    def _keyword_to_cc_pattern(self, keyword: str) -> str:
        kw = (keyword or "").strip()
        if not kw:
            return ""
        if "*" in kw:
            return kw
        kw = re.sub(r"\s+", "*", kw)
        if not kw.startswith("*"):
            kw = "*" + kw
        if not kw.endswith("*"):
            kw = kw + "*"
        return kw

    async def _create_plan_from_cc_keyword(
        self,
        *,
        query: str,
        keyword: str,
        max_domains: int,
        max_pages_per_domain: int,
        cc_archives: Optional[List[str]],
        filter_status: Optional[int],
        filter_mime: Optional[str],
        filter_languages: Optional[str],
        from_ts: Optional[str],
        to_ts: Optional[str],
        domain_allowlist: Optional[List[str]],
        domain_denylist: Optional[List[str]],
        tld_include: Optional[List[str]],
        tld_exclude: Optional[List[str]],
    ) -> DivePlan:
        plan = DivePlan(
            query=query,
            query_type="cc_keyword",
            sonar_indices_used=["periscope"],
        )

        pattern = self._keyword_to_cc_pattern(keyword)
        if not pattern:
            return plan

        cc_archives = cc_archives or [self.cc_archive]
        plan.cc_archives_queried = cc_archives

        combined: List[CCRecord] = []
        for archive in cc_archives:
            try:
                # Cap search to avoid massive queries; we re-bucket by domain below.
                limit = max_domains * max_pages_per_domain
                try:
                    cap = int(os.getenv("SUBMARINE_CC_KEYWORD_RECORD_CAP", "5000"))
                except Exception:
                    cap = 5000
                limit = max(100, min(limit, max(100, cap)))
                records = await self.periscope.search(
                    pattern,
                    limit=limit,
                    filter_status=filter_status,
                    filter_mime=filter_mime,
                    filter_languages=filter_languages,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    archive=archive,
                )
                if records:
                    combined.extend(records)
            except Exception as e:
                logger.warning(f"CC keyword search failed for archive {archive}: {e}")

        if not combined:
            return plan

        # Dedupe by WARC coordinates.
        seen_coords: Set[Tuple[str, int, int]] = set()
        deduped: List[CCRecord] = []
        for r in combined:
            key = (r.filename, r.offset, r.length)
            if key in seen_coords:
                continue
            seen_coords.add(key)
            deduped.append(r)

        # Bucket by domain, then apply domain intelligence filters.
        buckets: Dict[str, List[CCRecord]] = {}
        for r in deduped:
            dom = self._domain_from_url(r.url)
            if not dom:
                continue
            buckets.setdefault(dom, []).append(r)

        candidate_domains = sorted(buckets.keys(), key=lambda d: len(buckets[d]), reverse=True)
        candidate_domains = self._apply_domain_filters(
            candidate_domains,
            allowlist=domain_allowlist,
            denylist=domain_denylist,
            tld_include=tld_include,
            tld_exclude=tld_exclude,
        )
        candidate_domains = candidate_domains[:max_domains]

        for dom in candidate_domains:
            recs = buckets.get(dom) or []
            if not recs:
                continue
            target = DiveTarget(
                domain=dom,
                priority=1,
                source="periscope_keyword",
                cc_records=recs[:max_pages_per_domain],
                estimated_pages=min(len(recs), max_pages_per_domain),
            )
            plan.add_target(target)
            for r in target.cc_records:
                plan.estimated_warc_bytes += r.length

        return plan

    def _domain_from_url(self, url: str) -> Optional[str]:
        u = (url or "").strip()
        if not u:
            return None
        try:
            parsed = urlparse(u if "://" in u else f"https://{u}")
            dom = (parsed.netloc or "").strip().lower()
            if dom.startswith("www."):
                dom = dom[4:]
            if ":" in dom:
                dom = dom.split(":", 1)[0]
            if dom and "." in dom:
                return dom
        except Exception:
            return None
        return None

    def _prioritize_domains(
        self,
        query: str,
        sonar_result: SonarResult
    ) -> Dict[str, int]:
        """
        Assign priorities to domains based on relevance.

        Priority 1: Exact match / direct hit
        Priority 2: Subdomain of target
        Priority 3: Same TLD pattern
        Priority 4: Graph connected
        Priority 5: Loosely related
        """
        priorities: Dict[str, int] = {}
        query_lower = query.lower().strip()

        # Check if query looks like a domain
        is_domain_query = "." in query_lower and " " not in query_lower

        for domain in sonar_result.domains:
            domain_lower = domain.lower()

            if is_domain_query:
                # Exact match
                if domain_lower == query_lower:
                    priorities[domain] = 1
                # Subdomain
                elif domain_lower.endswith(f".{query_lower}"):
                    priorities[domain] = 2
                # Same base domain
                elif query_lower in domain_lower:
                    priorities[domain] = 3
                else:
                    priorities[domain] = 4
            else:
                # For non-domain queries, check which index it came from
                for hit in sonar_result.hits:
                    if hit.domain == domain or (hit.url and domain in hit.url):
                        if hit.match_type in ("phone", "email", "breach"):
                            priorities[domain] = 1  # Direct contact match
                        elif hit.match_type == "entity":
                            priorities[domain] = 2  # Entity found on this domain
                        elif hit.match_type == "graph":
                            priorities[domain] = 3  # Graph connected
                        else:
                            priorities[domain] = 4
                        break
                else:
                    priorities[domain] = 5

        return priorities

    def _get_domain_source(self, domain: str, sonar_result: SonarResult) -> str:
        """Get which index contributed this domain."""
        for hit in sonar_result.hits:
            if hit.domain == domain or (hit.url and domain in hit.url):
                return hit.index
        return "unknown"

    async def estimate_brute_force(self, month: str = "2024-51") -> Dict[str, Any]:
        """
        Estimate time for brute-force CC scan (for comparison).

        Shows why smart planning matters.
        """
        # CC stats for a typical month
        CC_STATS = {
            "total_pages": 3_000_000_000,  # 3 billion pages
            "total_warc_size_tb": 80,
            "warc_files": 90_000,
            "avg_pages_per_warc": 33_000,
        }

        # Our server capabilities
        SERVER_CAPABILITIES = {
            "network_mbps": 1000,  # 1 Gbps
            "concurrent_streams": 100,
            "processing_rate_pages_per_sec": 10_000,  # With Go streamer
        }

        # Calculate brute force time
        total_bytes = CC_STATS["total_warc_size_tb"] * 1e12
        download_time_sec = total_bytes / (SERVER_CAPABILITIES["network_mbps"] * 1e6 / 8)
        processing_time_sec = CC_STATS["total_pages"] / SERVER_CAPABILITIES["processing_rate_pages_per_sec"]

        total_time_sec = max(download_time_sec, processing_time_sec)

        return {
            "month": month,
            "cc_stats": CC_STATS,
            "brute_force_estimate": {
                "download_time_hours": download_time_sec / 3600,
                "processing_time_hours": processing_time_sec / 3600,
                "total_time_hours": total_time_sec / 3600,
                "total_time_days": total_time_sec / 86400,
            },
            "message": (
                f"Brute-force scanning would take ~{total_time_sec/86400:.1f} days. "
                "SUBMARINE's smart planning reduces this to minutes."
            ),
        }


# Quick test
if __name__ == "__main__":
    async def test():
        planner = DivePlanner()

        print("Creating dive plan for 'portofino.com'...")
        plan = await planner.create_plan("portofino.com", max_domains=50)

        print(f"\n=== DIVE PLAN ===")
        print(f"Query: {plan.query}")
        print(f"Type: {plan.query_type}")
        print(f"Domains: {plan.total_domains}")
        print(f"Pages: {plan.total_pages}")
        print(f"Estimated time: {plan.estimated_time_seconds/60:.1f} minutes")
        print(f"SONAR indices: {plan.sonar_indices_used}")
        print(f"CC archives: {plan.cc_archives_queried}")

        print(f"\nTop 10 targets:")
        for t in plan.targets[:10]:
            print(f"  [{t.priority}] {t.domain}: {t.estimated_pages} pages (from {t.source})")

        # Compare to brute force
        print("\n=== VS BRUTE FORCE ===")
        brute = await planner.estimate_brute_force()
        print(brute["message"])

        await planner.close()

    asyncio.run(test())
