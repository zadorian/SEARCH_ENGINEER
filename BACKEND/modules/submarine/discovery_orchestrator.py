#!/usr/bin/env python3
"""
SUBMARINE Discovery Orchestrator

Implements the `/submarine` command used by SASTRE's UnifiedExecutor.

This is a pragmatic bridge between SASTRE operator syntax and SUBMARINE's
archive-first acquisition pipeline:
  - PLAN: Sonar → Periscope → DivePlanner (domains/records)
  - FETCH: DeepDiver (Common Crawl WARC fetch via ccwarc)
  - EXTRACT: PACMAN (optional, via @ent?)
  - INDEX: CYMONIDES corpus/entities (optional, via /index)

Design goals:
  - Must not crash if optional components (ES, ccwarc, PACMAN) are unavailable
  - Return structured JSON dictionaries for callers (SASTRE executor + MCP)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_domain(domain: str) -> Optional[str]:
    d = (domain or "").strip().lower()
    if not d:
        return None
    if any(ch.isspace() for ch in d) or "/" in d:
        return None
    if d.startswith("www."):
        d = d[4:]
    if ":" in d:
        d = d.split(":", 1)[0]
    if "@" in d:
        return None
    if "." not in d:
        return None
    return d


def _domain_from_any(text: Optional[str]) -> Optional[str]:
    s = (text or "").strip()
    if not s:
        return None
    # Avoid treating emails as domains.
    if "@" in s and " " not in s:
        return None
    # URL → netloc
    if s.lower().startswith(("http://", "https://")):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(s)
            return _normalize_domain(parsed.netloc)
        except Exception:
            return None
    # Bare domain-ish
    return _normalize_domain(s)


def _has_exploration_directives(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(r"\b(?:indom|inurl)\s*:", t, re.IGNORECASE)
        or re.search(r"\bhop\(\d+\)", t, re.IGNORECASE)
    )


def _extract_domains_from_alldom(payload: Any) -> List[str]:
    """Best-effort domain extraction from LINKLATER.full_domain_analysis output."""
    found: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            dom = _domain_from_any(value)
            if dom:
                found.add(dom)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for k, v in value.items():
                kl = str(k).lower()
                if kl in {"domain", "source_domain", "target_domain", "host"} and isinstance(v, str):
                    dom = _domain_from_any(v)
                    if dom:
                        found.add(dom)
                add(v)

    add(payload)
    return sorted(found)


def _parse_int_arg(pattern: str, text: str) -> Tuple[Optional[int], str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None, text
    try:
        value = int(match.group(1))
    except Exception:
        value = None
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return value, cleaned


def _pop_flag(token: str, text: str) -> Tuple[bool, str]:
    pattern = rf"(?i)(?:^|\s){re.escape(token)}(?:\s|$)"
    if not re.search(pattern, text):
        return False, text
    cleaned = re.sub(pattern, " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return True, cleaned


def _extract_scope(text: str) -> Tuple[Optional[str], str]:
    """
    Extract a trailing `:<target>` scope if present.

    Examples:
        "... :?example.com" -> "example.com"
        "... :!example.com" -> "example.com"
        "... :https://example.com" -> "https://example.com"
    """
    match = re.search(r"\s:\s*(\S+)\s*$", text)
    if not match:
        return None, text
    scope = match.group(1).strip()
    cleaned = text[: match.start()].strip()

    # Normalize SASTRE-ish target markers
    if scope.startswith(("?", "!")):
        scope = scope[1:].strip()
    if scope.endswith("!"):
        scope = scope[:-1].strip()

    # Only treat as a scope if it looks like a URL or domain (avoid `:US` jurisdiction tokens).
    if scope and (scope.startswith(("http://", "https://", "www.")) or "." in scope):
        return scope, cleaned
    return None, text


def _extract_jurisdiction(text: str) -> Tuple[Optional[str], str]:
    """
    Extract a trailing `:US` jurisdiction token (2-letter code) if present.

    This mirrors common SASTRE operator syntax where `:<COUNTRY>` is used as a scope.
    """
    match = re.search(r"\s:\s*([A-Za-z]{2})\s*$", text)
    if not match:
        return None, text
    jur = (match.group(1) or "").strip().upper()
    cleaned = text[: match.start()].strip()
    return jur or None, cleaned


def _parse_str_arg(pattern: str, text: str) -> Tuple[Optional[str], str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None, text
    value = (match.group(1) or "").strip().strip('"').strip("'")
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return value or None, cleaned


def _parse_float_arg(pattern: str, text: str) -> Tuple[Optional[float], str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None, text
    value: Optional[float]
    try:
        value = float(match.group(1))
    except Exception:
        value = None
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return value, cleaned


def _parse_list_arg(pattern: str, text: str) -> Tuple[List[str], str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return [], text
    raw = (match.group(1) or "").strip().strip('"').strip("'")
    items = [p.strip() for p in raw.split(",") if p.strip()]
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return items, cleaned


def _extract_bang_filters(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse SASTRE-style `token!` filters out of the order line.

    Supports:
      - news!  → news mode (TORPEDO news domains allowlist)
      - pdf!   → mime=application/pdf
      - gov!/uk!/de!/co.uk! → tld_include
    """
    bang: Dict[str, Any] = {"news": False, "tld_include": [], "mime": None}

    pattern = re.compile(r"(?i)(?:^|\s)([a-z]{2,}(?:\.[a-z]{2,})*)!(?=\s|$)")
    tokens = pattern.findall(text or "")
    if not tokens:
        return bang, text

    for tok in tokens:
        t = (tok or "").strip().lower()
        if not t:
            continue
        if t == "news":
            bang["news"] = True
            continue
        if t in {"pdf"}:
            bang["mime"] = "application/pdf"
            continue
        bang["tld_include"].append(t)

    cleaned = pattern.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    bang["tld_include"] = list(dict.fromkeys(bang["tld_include"]))
    return bang, cleaned


def _load_torpedo_news_domains(
    jurisdiction: Optional[str],
    *,
    min_reliability: float = 0.0,
    limit: int = 50000,
) -> List[str]:
    """
    Load TORPEDO news domains from IO Matrix `sources/news.json`.

    Returns domains sorted by reliability (desc) when available.
    """
    try:
        from TORPEDO.paths import news_sources_path  # type: ignore

        path = Path(news_sources_path())
    except Exception:
        path = Path("/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources/news.json")

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    jur_key: Optional[str] = None
    if jurisdiction:
        jur = jurisdiction.strip().upper()
        if jur == "UK":
            jur = "GB"
        jur_key = jur

    sources: List[Dict[str, Any]] = []
    if jur_key:
        items = data.get(jur_key) or []
        if isinstance(items, list):
            sources = items
    else:
        for items in (data or {}).values():
            if isinstance(items, list):
                sources.extend(items)

    best: Dict[str, float] = {}
    for s in sources:
        if not isinstance(s, dict):
            continue
        dom = _normalize_domain(s.get("domain") or "")
        if not dom:
            continue
        try:
            rel = float(s.get("reliability", 0.0) or 0.0)
        except Exception:
            rel = 0.0
        if rel < float(min_reliability or 0.0):
            continue
        prev = best.get(dom, -1.0)
        if rel > prev:
            best[dom] = rel

    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    domains = [d for d, _ in ranked][: max(0, int(limit))]
    return domains


def _extract_watcher_id(text: str) -> Tuple[Optional[str], str]:
    """
    Extract a watcher ID token if present: watcher(<id>)
    """
    match = re.search(r"\bwatcher\(([^)]+)\)", text, re.IGNORECASE)
    if not match:
        return None, text
    watcher_id = (match.group(1) or "").strip().strip('"').strip("'")
    cleaned = (text[: match.start()] + " " + text[match.end() :]).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return watcher_id or None, cleaned


def _choose_submarine_query(raw_query: str, scope: Optional[str]) -> str:
    """
    Choose the best query string to feed into SUBMARINE's Sonar/DivePlanner.

    SUBMARINE's query classifier is optimized for phones/emails/domains/entities.
    If a domain scope is provided, prefer it (it usually yields the best results).
    """
    if scope:
        return scope
    return raw_query.strip()


def _safe_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    try:
        return asdict(obj)  # dataclasses
    except Exception:
        pass
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return str(obj)


async def run_submarine(query: str, project_id: str = "default") -> Dict[str, Any]:
    """
    Entry point for SASTRE: execute a `/submarine ...` command.

    Args:
        query: Full command string (including `/submarine` prefix)
        project_id: Optional Cymonides project ID for indexing/entities
    """
    from .dive_planner.planner import DivePlanner
    from .deep_dive.diver import DeepDiver
    from .extraction.pacman_bridge import PACMANExtractor

    raw = re.sub(r"(?i)^/submarine\b", "", (query or "")).strip()
    if not raw:
        return {"error": "Missing /submarine arguments", "query": query, "_executor": "submarine"}

    depth, raw = _parse_int_arg(r"\bdepth\((\d+)\)", raw)
    expanse, raw = _parse_int_arg(r"\bexpanse\((\d+)\)", raw)
    status_code, raw = _parse_int_arg(r"\bstatus\((\d+)\)", raw)
    do_scrape, raw = _pop_flag("/scrape", raw)
    do_index, raw = _pop_flag("/index", raw)
    extract_entities, raw = _pop_flag("@ent?", raw)
    news_flag, raw = _pop_flag("/news", raw)
    no_watch, raw = _pop_flag("/nowatch", raw)
    watcher_id, raw = _extract_watcher_id(raw)

    archives, raw = _parse_list_arg(r"\barchives?\(([^)]+)\)", raw)
    keyword, raw = _parse_str_arg(r"\b(?:keyword|inurl|url_contains)\(([^)]+)\)", raw)
    mime, raw = _parse_str_arg(r"\bmime\(([^)]+)\)", raw)
    language, raw = _parse_str_arg(r"\b(?:lang|language)\(([^)]+)\)", raw)
    date_from, raw = _parse_str_arg(r"\bfrom\(([^)]+)\)", raw)
    date_to, raw = _parse_str_arg(r"\bto\(([^)]+)\)", raw)
    min_rel, raw = _parse_float_arg(r"\bminrel\(([^)]+)\)", raw)
    tld_inc_args, raw = _parse_list_arg(r"\btld_include\(([^)]+)\)", raw)
    tld_exc_args, raw = _parse_list_arg(r"\btld_exclude\(([^)]+)\)", raw)

    bang, raw = _extract_bang_filters(raw)
    news_flag = bool(news_flag or bang.get("news"))
    if not mime and bang.get("mime"):
        mime = str(bang.get("mime"))
    tld_include = [*tld_inc_args, *(bang.get("tld_include") or [])]
    tld_exclude = list(tld_exc_args)

    scope, raw = _extract_scope(raw)
    jurisdiction, raw = _extract_jurisdiction(raw)
    submarine_query = _choose_submarine_query(raw, scope)
    submarine_order = raw.strip()

    # Guardrails (env-configurable)
    try:
        max_domains_default = int(os.getenv("SUBMARINE_MAX_DOMAINS", "200"))
    except Exception:
        max_domains_default = 200
    try:
        max_domains_cap = int(os.getenv("SUBMARINE_MAX_DOMAINS_CAP", str(max_domains_default)))
    except Exception:
        max_domains_cap = max_domains_default
    max_domains = max(1, min(max_domains_default, max_domains_cap))

    try:
        max_pages_default = int(os.getenv("SUBMARINE_MAX_PAGES_PER_DOMAIN", "10"))
    except Exception:
        max_pages_default = 10
    try:
        max_pages_cap = int(os.getenv("SUBMARINE_MAX_PAGES_PER_DOMAIN_CAP", "500"))
    except Exception:
        max_pages_cap = 500
    max_pages_per_domain = max(1, min(max_pages_default, max_pages_cap))
    if expanse is not None:
        max_pages_per_domain = max(1, min(expanse, max_pages_cap))
    if depth is not None and depth > 1:
        # Rough heuristic: deeper requests imply larger sample per domain.
        max_pages_per_domain = min(max_pages_per_domain * min(depth, 5), max_pages_cap)

    try:
        overall_cap_setting = int(os.getenv("SUBMARINE_OVERALL_CAP", "500"))
    except Exception:
        overall_cap_setting = 500
    overall_cap_setting = max(1, min(overall_cap_setting, 5000))

    planner = DivePlanner()
    diver = DeepDiver()
    extractor = PACMANExtractor()
    watcher_bridge = None
    watcher_doc_id: Optional[str] = None
    watcher_section_title: Optional[str] = None

    async def _maybe_init_watcher_bridge() -> Any:
        nonlocal watcher_bridge
        if watcher_bridge is not None:
            return watcher_bridge
        try:
            from SASTRE.bridges import WatcherBridge
            watcher_bridge = WatcherBridge()
            return watcher_bridge
        except Exception:
            watcher_bridge = None
            return None

    async def _resolve_watcher_section(wid: str) -> None:
        nonlocal watcher_doc_id, watcher_section_title
        bridge = await _maybe_init_watcher_bridge()
        if bridge is None:
            return
        try:
            watcher_obj = await bridge.get(wid)
            if watcher_obj is None:
                watcher_obj = await bridge.get_watcher(wid)
        except Exception:
            watcher_obj = None
        if not isinstance(watcher_obj, dict):
            return
        watcher_section_title = (
            watcher_obj.get("header")
            or watcher_obj.get("name")
            or watcher_obj.get("label")
            or watcher_obj.get("title")
        )
        watcher_doc_id = (
            watcher_obj.get("parentDocumentId")
            or watcher_obj.get("parent_document_id")
            or watcher_obj.get("documentId")
            or watcher_obj.get("document_id")
            or watcher_obj.get("noteId")
            or watcher_obj.get("note_id")
        )

    async def _stream_to_watcher(text: str, *, source_url: Optional[str] = None) -> None:
        bridge = await _maybe_init_watcher_bridge()
        if bridge is None or not watcher_id or not watcher_doc_id or not watcher_section_title:
            return
        try:
            await bridge.stream_finding_to_section(
                document_id=str(watcher_doc_id),
                section_title=str(watcher_section_title),
                finding_text=text,
                source_url=source_url,
            )
        except Exception:
            return

    try:
        filter_status = status_code if status_code is not None else 200
        cc_archives = archives or None

        domain_allowlist: Optional[List[str]] = None
        if news_flag:
            domain_allowlist = _load_torpedo_news_domains(
                jurisdiction,
                min_reliability=float(min_rel or 0.0),
            )

        alldom = None
        alldom_error = None
        domain_target = _domain_from_any(scope) or _domain_from_any(submarine_query)
        if domain_target:
            try:
                from LINKLATER.api import get_linklater
                linklater = get_linklater()
                # Keep this lightweight for SUBMARINE planning; full entity extraction happens later.
                alldom = await linklater.full_domain_analysis(
                    domain_target,
                    include_archives=False,
                    include_entities=False,
                    limit_per_operation=50,
                )
                try:
                    from .exploration.targets_note import update_targets
                    extra_domains = _extract_domains_from_alldom(alldom)
                    if extra_domains:
                        update_targets(project_id=project_id, add_domains=extra_domains)
                except Exception:
                    pass
            except Exception as e:
                alldom_error = str(e)

        exploration = None
        explored_domains: List[str] = []
        explore_only = False
        exploration_query = submarine_order
        m = re.match(r"(?i)^explore\b[:\\s]*(.*)$", exploration_query or "")
        if m:
            explore_only = True
            exploration_query = (m.group(1) or "").strip()

        if explore_only or _has_exploration_directives(exploration_query):
            from .exploration.explorer import run_exploration

            exploration = await run_exploration(
                query=exploration_query or submarine_query,
                project_id=project_id,
                limit_per_index=200,
                update_note=True,
            )
            explored_domains = list(exploration.get("domains") or [])
            if domain_target and domain_target not in explored_domains:
                explored_domains.insert(0, domain_target)

            if explore_only and not (do_scrape or do_index or extract_entities):
                return {
                    "mode": "explore",
                    "query": query,
                    "project_id": project_id,
                    "exploration": exploration,
                    "alldom": alldom,
                    "alldom_error": alldom_error,
                    "_executor": "submarine",
                }

            if explored_domains:
                if domain_allowlist:
                    allow_set = set(domain_allowlist)

                    def _allowed(d: str) -> bool:
                        dl = _normalize_domain(d) or ""
                        if not dl:
                            return False
                        if dl in allow_set:
                            return True
                        # Allow subdomains by checking parent suffixes (O(labels)).
                        cur = dl
                        while "." in cur:
                            cur = cur.split(".", 1)[1]
                            if cur in allow_set:
                                return True
                        return False

                    explored_domains = [d for d in explored_domains if _allowed(d)]

                if tld_include:
                    inc = [s.strip().lower().lstrip(".") for s in tld_include if (s or "").strip()]
                    if inc:
                        explored_domains = [
                            d for d in explored_domains
                            if any((d or "").lower().endswith(f".{suf}") for suf in inc)
                        ]
                if tld_exclude:
                    exc = [s.strip().lower().lstrip(".") for s in tld_exclude if (s or "").strip()]
                    if exc:
                        explored_domains = [
                            d for d in explored_domains
                            if not any((d or "").lower().endswith(f".{suf}") for suf in exc)
                        ]
                plan = await planner.create_plan_from_domains(
                    query=submarine_query,
                    domains=explored_domains,
                    max_pages_per_domain=max_pages_per_domain,
                    source="exploration",
                    cc_archives=cc_archives,
                    filter_status=filter_status,
                    filter_mime=mime,
                    filter_languages=language,
                    from_ts=date_from,
                    to_ts=date_to,
                    url_contains=keyword,
                )
            else:
                plan = await planner.create_plan(
                    submarine_query,
                    max_domains=max_domains,
                    max_pages_per_domain=max_pages_per_domain,
                    cc_archives=cc_archives,
                    filter_status=filter_status,
                    filter_mime=mime,
                    filter_languages=language,
                    from_ts=date_from,
                    to_ts=date_to,
                    domain_allowlist=domain_allowlist,
                    tld_include=tld_include or None,
                    tld_exclude=tld_exclude or None,
                    url_contains=keyword,
                )
        else:
            plan = await planner.create_plan(
                submarine_query,
                max_domains=max_domains,
                max_pages_per_domain=max_pages_per_domain,
                cc_archives=cc_archives,
                filter_status=filter_status,
                filter_mime=mime,
                filter_languages=language,
                from_ts=date_from,
                to_ts=date_to,
                domain_allowlist=domain_allowlist,
                tld_include=tld_include or None,
                tld_exclude=tld_exclude or None,
                url_contains=keyword,
            )

        plan_file: Optional[Path] = None
        if do_scrape or os.getenv("SUBMARINE_ALWAYS_SAVE_PLAN") == "1":
            plan_dir = Path(os.getenv("SUBMARINE_PLAN_DIR", "/data/SUBMARINE/plans"))
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", submarine_query or "query").strip("_-")
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            plan_file = plan_dir / f"submarine_{project_id}_{slug[:40] or 'query'}_{ts}.json"
            try:
                plan.save(str(plan_file), full=True)
            except Exception:
                plan_file = None

        plan_dict = _safe_to_dict(plan)
        if exploration is not None:
            plan_dict["exploration"] = exploration
        plan_dict["alldom"] = alldom
        plan_dict["alldom_error"] = alldom_error
        plan_dict["plan_file"] = str(plan_file) if plan_file else None

        do_watch = bool(not no_watch)
        pacman_spec = None
        pacman_registry_path = None
        if do_watch:
            # Create a watcher for this mission if not provided.
            bridge = await _maybe_init_watcher_bridge()
            if bridge is not None and not watcher_id:
                try:
                    created = await bridge.create(
                        name=f"SUBMARINE: {submarine_query[:80]}",
                        project_id=project_id,
                        query=None,
                    )
                    watcher_id = (
                        created.get("id")
                        or created.get("watcherId")
                        or created.get("watcher_id")
                    )
                except Exception:
                    watcher_id = None

            if watcher_id:
                await _resolve_watcher_section(watcher_id)

                # Register watcher spec in PACMAN (file-based; cross-process safe).
                try:
                    from PACMAN.watcher_registry import (
                        DEFAULT_REGISTRY_PATH,
                        WatcherSpec,
                        default_targets,
                        get_watcher,
                        register_watcher,
                    )

                    existing = get_watcher(watcher_id)
                    if existing is not None:
                        pacman_spec = existing
                        updated = False
                        try:
                            td = getattr(plan, "total_domains", None)
                            if pacman_spec.domain_count is None and td:
                                pacman_spec.domain_count = int(td)
                                updated = True
                        except Exception:
                            pass
                        if not (pacman_spec.submarine_order or "").strip() and (submarine_order or submarine_query):
                            pacman_spec.submarine_order = submarine_order or submarine_query
                            updated = True
                        if updated:
                            register_watcher(pacman_spec)
                    else:
                        pacman_spec = WatcherSpec(
                            watcher_id=watcher_id,
                            submarine_order=submarine_order or submarine_query,
                            domain_count=getattr(plan, "total_domains", None) or None,
                            targets=default_targets(),
                        )
                        register_watcher(pacman_spec)
                    pacman_registry_path = str(DEFAULT_REGISTRY_PATH)
                except Exception:
                    pacman_spec = None

                # Stream mission header/context once.
                header = (
                    "SUBMARINE ORDER\n"
                    f"- query: {submarine_query}\n"
                    f"- scope: {scope or ''}\n"
                    f"- jurisdiction: {jurisdiction or ''}\n"
                    f"- depth: {depth if depth is not None else ''}\n"
                    f"- expanse: {expanse if expanse is not None else ''}\n"
                    f"- news: {bool(news_flag)}\n"
                    f"- archives: {', '.join(archives) if archives else ''}\n"
                    f"- status: {filter_status}\n"
                    f"- mime: {mime or ''}\n"
                    f"- lang: {language or ''}\n"
                    f"- from: {date_from or ''}\n"
                    f"- to: {date_to or ''}\n"
                    f"- keyword: {keyword or ''}\n"
                    f"- tld_include: {', '.join(tld_include) if tld_include else ''}\n"
                    f"- tld_exclude: {', '.join(tld_exclude) if tld_exclude else ''}\n"
                    f"- min_reliability: {min_rel if min_rel is not None else ''}\n"
                    f"- plan_file: {str(plan_file) if plan_file else ''}\n"
                    f"- overall_cap: {overall_cap_setting}\n"
                )
                await _stream_to_watcher(header)

        result: Dict[str, Any] = {
            "query": query,
            "submarine_query": submarine_query,
            "scope": scope,
            "jurisdiction": jurisdiction,
            "project_id": project_id,
            "watcher_id": watcher_id,
            "pacman_registry": pacman_registry_path,
            "plan_file": str(plan_file) if plan_file else None,
            "mode": {
                "scrape": do_scrape,
                "index": do_index,
                "extract_entities": extract_entities,
                "watch": do_watch,
                "depth": depth,
                "expanse": expanse,
                "news": news_flag,
            },
            "caps": {
                "max_domains": max_domains,
                "max_pages_per_domain": max_pages_per_domain,
                "overall_cap": overall_cap_setting,
            },
            "filters": {
                "archives": archives or None,
                "status": filter_status,
                "mime": mime,
                "language": language,
                "from_ts": date_from,
                "to_ts": date_to,
                "keyword": keyword,
                "tld_include": tld_include or None,
                "tld_exclude": tld_exclude or None,
                "min_reliability": min_rel,
            },
            "plan": plan_dict,
            "domains": sorted(getattr(plan, "targets", []) and [t.domain for t in plan.targets] or []),
            "total_domains": getattr(plan, "total_domains", 0),
            "total_pages": getattr(plan, "total_pages", 0),
            "_executor": "submarine",
        }

        if not do_scrape:
            return result

        if not diver.available:
            result["error"] = "SUBMARINE DeepDiver not available (ccwarc binary missing)"
            return result

        fetched: List[Dict[str, Any]] = []
        entities_agg: Dict[str, List[str]] = {}
        indexed_content: List[Dict[str, Any]] = []
        indexed_entities: Dict[str, List[str]] = {}
        findings_agg: List[Dict[str, Any]] = []
        seen_findings: set[tuple[str, str]] = set()

        pacman_extract = None
        if watcher_id and pacman_spec is not None:
            try:
                from PACMAN.watcher_registry import extract_for_watcher as pacman_extract
            except Exception:
                pacman_extract = None

        # Optional indexer (best-effort)
        indexer = None
        if do_index:
            try:
                from modules.LINKLATER.cymonides_bridge import get_indexer
                indexer = await get_indexer()
            except Exception as e:
                result["index_error"] = f"Indexer unavailable: {e}"
                indexer = None

        # Fetch with an overall cap for safety (env-configurable)
        overall_cap = overall_cap_setting
        count = 0

        async for dive_result in diver.execute_plan(plan, checkpoint_path=plan_file):
            count += 1
            if count > overall_cap:
                break

            dive_dict = _safe_to_dict(dive_result)
            fetched.append(dive_dict)

            extracted_payload = None
            if extract_entities and getattr(dive_result, "content", None):
                extraction = extractor.extract(
                    dive_result.content,
                    url=getattr(dive_result, "url", "") or "",
                    domain=getattr(dive_result, "domain", "") or "",
                )
                extracted_payload = extraction.to_dict()

                # Aggregate by simple buckets for quick use
                for ent in extraction.entities:
                    key = str(ent.entity_type).lower()
                    entities_agg.setdefault(key, []).append(ent.value)

            # Mission PACMAN extraction (snippet-first) for watcher/template population.
            if pacman_extract and getattr(dive_result, "content", None):
                url_val = getattr(dive_result, "url", "") or ""
                try:
                    new_findings = pacman_extract(
                        watcher=pacman_spec,
                        content=dive_result.content,
                        url=url_val,
                        allow_ai=True,
                    )
                except Exception:
                    new_findings = []

                if new_findings:
                    fresh: List[Dict[str, Any]] = []
                    for f in new_findings:
                        try:
                            key = (str(f.get("target") or ""), str(f.get("value") or "").strip().lower())
                        except Exception:
                            continue
                        if not key[0] or not key[1]:
                            continue
                        if key in seen_findings:
                            continue
                        seen_findings.add(key)
                        fresh.append(f)

                    if fresh:
                        findings_agg.extend(fresh)

                        # Stream a single grouped update per page.
                        lines = [f"FROM {url_val}".strip()]
                        for f in fresh[:50]:
                            target = f.get("target") or "extracted"
                            value = f.get("value") or ""
                            snippet = f.get("snippet") or ""
                            lines.append(f"- ({target}) {value}")
                            if snippet:
                                lines.append(f"  {snippet}")
                        await _stream_to_watcher("\n".join(lines), source_url=url_val or None)

            if indexer and getattr(dive_result, "content", None):
                try:
                    content_id = await indexer.index_content(
                        url=getattr(dive_result, "url", "") or "",
                        content=getattr(dive_result, "content", "") or "",
                        domain=getattr(dive_result, "domain", "") or None,
                        title=None,
                        outlinks=None,
                        backlinks=None,
                        archive_url=None,
                        timestamp=getattr(dive_result, "timestamp", None),
                        source="commoncrawl",
                        project_id=project_id or "default",
                        query=query,
                    )
                    indexed_content.append(
                        {"url": getattr(dive_result, "url", ""), "content_id": content_id}
                    )

                    if extract_entities and extracted_payload:
                        # Map to CymonidesIndexer expected keys
                        type_map = {
                            "person": "persons",
                            "company": "companies",
                            "email": "emails",
                            "telephone": "phones",
                            "phone": "phones",
                            "address": "addresses",
                            "crypto": "crypto_wallets",
                        }
                        entities_for_index: Dict[str, List[str]] = {}
                        for k, vals in entities_agg.items():
                            mapped = type_map.get(k, None)
                            if not mapped:
                                continue
                            entities_for_index[mapped] = list(dict.fromkeys(vals))[:500]

                        if entities_for_index and project_id and project_id != "default":
                            indexed_entities = await indexer.index_entities(
                                entities=entities_for_index,
                                project_id=project_id,
                                source_url=getattr(dive_result, "url", "") or None,
                            )
                except Exception as e:
                    result.setdefault("index_failures", []).append(str(e))

        result["fetched_count"] = len(fetched)
        result["fetched"] = fetched[:200]  # cap payload size
        if extract_entities:
            # de-dupe + cap for payload
            result["entities"] = {k: sorted(set(v))[:500] for k, v in entities_agg.items()}
        if watcher_id and findings_agg:
            result["pacman_findings"] = findings_agg[:1000]
        if do_index:
            result["indexed_content"] = indexed_content[:500]
            result["indexed_entities"] = indexed_entities

        # === MISSION FINALIZE (watcher + bundle + optional EDITh) ===
        domains_covered = sorted({(d.get("domain") or "").strip() for d in fetched if isinstance(d, dict)})[:500]
        mission_summary = {
            "query": submarine_query,
            "project_id": project_id,
            "watcher_id": watcher_id,
            "plan_file": str(plan_file) if plan_file else None,
            "fetched_pages": len(fetched),
            "domains_covered": domains_covered[:200],
            "plan_total_domains": getattr(plan, "total_domains", 0),
            "plan_total_pages": getattr(plan, "total_pages", 0),
            "plan_completed_domains": len(getattr(plan, "completed_domains", set()) or set()),
            "findings_count": len(findings_agg),
        }
        result["mission_summary"] = mission_summary

        bundle_path = None
        try:
            bundle_dir = Path(os.getenv("SUBMARINE_BUNDLE_DIR", "/data/SUBMARINE/bundles"))
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", submarine_query or "query").strip("_-")
            bundle_path = bundle_dir / f"bundle_{project_id}_{watcher_id or 'nowatch'}_{slug[:40] or 'query'}_{ts}.json"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            tmp = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "submarine_order": submarine_order,
                        "submarine_query": submarine_query,
                        "scope": scope,
                        "jurisdiction": jurisdiction,
                        "filters": result.get("filters") or {},
                        "caps": result.get("caps") or {},
                        "plan_file": str(plan_file) if plan_file else None,
                        "plan": plan_dict,
                        "mission_summary": mission_summary,
                        "findings": findings_agg[:5000],
                    },
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            tmp.replace(bundle_path)
        except Exception:
            bundle_path = None

        if bundle_path:
            result["bundle_file"] = str(bundle_path)

        async def _stream_to_section(section_title: str, text: str) -> None:
            bridge = await _maybe_init_watcher_bridge()
            if bridge is None or not watcher_id or not watcher_doc_id:
                return
            try:
                await bridge.stream_finding_to_section(
                    document_id=str(watcher_doc_id),
                    section_title=str(section_title),
                    finding_text=text,
                    source_url=None,
                )
            except Exception:
                return

        if watcher_id and watcher_doc_id and watcher_section_title:
            # Compact summary text (write once per mission)
            lines: List[str] = []
            lines.append("SUBMARINE MISSION COMPLETE")
            lines.append(f"- query: {submarine_query}")
            if jurisdiction:
                lines.append(f"- jurisdiction: {jurisdiction}")
            if plan_file:
                lines.append(f"- plan_file: {plan_file}")
            if bundle_path:
                lines.append(f"- bundle_file: {bundle_path}")
            lines.append(f"- fetched_pages: {len(fetched)} (cap={overall_cap_setting})")
            lines.append(f"- domains_covered: {len(domains_covered)}")
            lines.append(f"- plan_domains: {getattr(plan, 'total_domains', 0)}")
            lines.append(f"- plan_completed_domains: {len(getattr(plan, 'completed_domains', set()) or set())}")
            lines.append("")

            if findings_agg:
                preferred = ["companies", "persons", "emails", "phones", "domains", "urls", "addresses"]
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for f in findings_agg:
                    t = str(f.get("target") or "extracted").strip().lower()
                    grouped.setdefault(t, []).append(f)

                def _sort_key(k: str) -> Tuple[int, str]:
                    try:
                        return (preferred.index(k), k)
                    except ValueError:
                        return (999, k)

                lines.append("KEY FINDINGS (sample)")
                for target in sorted(grouped.keys(), key=_sort_key):
                    items = grouped.get(target) or []
                    if not items:
                        continue
                    lines.append(f"{target} ({len(items)})")
                    for item in items[:10]:
                        value = (item.get("value") or "").strip()
                        src = (item.get("source_url") or "").strip()
                        snippet = (item.get("snippet") or "").strip()
                        if not value:
                            continue
                        if src:
                            lines.append(f"- {value} ({src})")
                        else:
                            lines.append(f"- {value}")
                        if snippet:
                            lines.append(f"  {snippet}")
                    lines.append("")

            summary_section = f"{watcher_section_title} — Summary"
            await _stream_to_section(summary_section, "\n".join(lines[:600]))

            # Best-effort watcher status update
            try:
                bridge = await _maybe_init_watcher_bridge()
                if bridge is not None:
                    await bridge.update_status(str(watcher_id), "completed")
            except Exception:
                pass

            # Optional EDITh write-up (gated by env; no AI during pytest)
            edith_writeup = None
            edith_error = None
            if os.getenv("SUBMARINE_FINALIZE_WITH_EDITH") == "1" and not os.getenv("PYTEST_CURRENT_TEST"):
                try:
                    from EDITH.edith_b.ai import load_style_assets, _compact_style_context, run_section_fill  # type: ignore

                    style_context = _compact_style_context(load_style_assets(), genre="due_diligence")
                    context_lines = [
                        "STYLE GUIDE (summary)",
                        style_context,
                        "",
                        "SUBMARINE ORDER",
                        submarine_order or submarine_query,
                        "",
                        "FINDINGS (sample)",
                        "\n".join(lines),
                    ]
                    context = "\n".join(context_lines)
                    context = context[:20000]
                    tier = os.getenv("SUBMARINE_FINALIZE_EDITH_TIER", "fast").strip() or "fast"
                    resp = run_section_fill("Submarine Findings", context, tier=tier)
                    edith_writeup = (resp or {}).get("content")
                    edith_error = (resp or {}).get("error")
                except Exception as e:
                    edith_error = str(e)

            if edith_writeup:
                await _stream_to_section(f"{watcher_section_title} — EDITh", str(edith_writeup)[:20000])
            if edith_error:
                result["edith_finalize_error"] = edith_error
            if edith_writeup:
                result["edith_writeup"] = str(edith_writeup)[:5000]

        return result

    finally:
        try:
            await planner.close()
        except Exception:
            pass
        try:
            if watcher_bridge is not None:
                await watcher_bridge.close()
        except Exception:
            pass
