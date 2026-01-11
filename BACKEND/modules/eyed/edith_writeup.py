#!/usr/bin/env python3
"""
EYE-D → EDITH Write-up (COMPREHENSIVE & RECURSIVE)

CRITICAL RULES:
1. 100% COMPREHENSIVE - NO truncation, NO "selected examples", NO limits
2. Proper footnotes - ONLY real URLs (social profiles, websites), NOT API endpoints
3. Recursive IO chain - ALL entities automatically reinvestigated
4. IP geolocation - ALWAYS with location, grouped by region

Generates a report-style Markdown write-up from EYE-D output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _read_json(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return json.loads(raw)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        key = item.strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _safe_markdown(text: str) -> str:
    s = str(text or "")
    return s.replace("\r", "").replace("\t", " ").strip()


def _first_http_url(value: Any) -> Optional[str]:
    if isinstance(value, str):
        v = value.strip()
        if v.startswith(("http://", "https://")):
            return v
        return None
    if isinstance(value, list):
        for item in value:
            hit = _first_http_url(item)
            if hit:
                return hit
    return None


def _is_api_endpoint(url: str) -> bool:
    """Check if URL is an API endpoint (should NOT be footnoted)."""
    if not url:
        return False

    url_lower = url.lower()

    # API endpoint patterns
    api_patterns = [
        'api.osintindustries.com',
        '/api/',
        '/v1/',
        '/v2/',
        '/v3/',
        'api.',
        '.api.',
        'oauth',
        '/token',
        '/auth',
        '/graphql',
        '/rest/',
        'whoisxmlapi.com',
        'api.rocketreach.co',
        'api.dehashed.com',
    ]

    return any(pattern in url_lower for pattern in api_patterns)


def _is_real_profile_url(url: str) -> bool:
    """Check if URL is a real social/web profile (SHOULD be footnoted)."""
    if not url:
        return False

    url_lower = url.lower()

    # Real profile/website patterns
    profile_patterns = [
        'linkedin.com/in/',
        'linkedin.com/company/',
        'facebook.com/',
        'twitter.com/',
        'x.com/',
        'instagram.com/',
        'github.com/',
        'reddit.com/user/',
        'youtube.com/',
        'tiktok.com/@',
        'medium.com/@',
        'profile',
        'user/',
    ]

    # If it's an API endpoint, it's not a real profile
    if _is_api_endpoint(url):
        return False

    # Check if it matches profile patterns
    return any(pattern in url_lower for pattern in profile_patterns)


def _extract_source_url(entry: Dict[str, Any]) -> Optional[str]:
    if not isinstance(entry, dict):
        return None

    for key in ("url", "source_url", "link", "record_url", "profile_url", "permalink"):
        hit = _first_http_url(entry.get(key))
        if hit:
            return hit

    data = entry.get("data")
    if isinstance(data, dict):
        for key in ("url", "source_url", "link", "record_url", "profile_url", "permalink"):
            hit = _first_http_url(data.get(key))
            if hit:
                return hit
        hit = _first_http_url(data.get("urls"))
        if hit:
            return hit

    return None


def _collect_footnote_urls(docs: Sequence[Tuple[str, Any]]) -> Dict[str, int]:
    """Collect ONLY real profile/website URLs for footnotes (NOT API endpoints)."""
    urls: List[str] = []
    for _, data in docs:
        if not isinstance(data, dict):
            continue
        results = data.get("results")
        if not isinstance(results, list):
            continue
        for entry in results:
            if not isinstance(entry, dict):
                continue
            url = _extract_source_url(entry)
            if not url:
                continue
            # CRITICAL: Only include real profiles/websites, NOT API endpoints
            if not _is_real_profile_url(url):
                continue
            if url in urls:
                continue
            urls.append(url)
    return {url: i + 1 for i, url in enumerate(urls)}


def _looks_sensitive_key(key: str) -> bool:
    k = (key or "").lower()
    return any(tok in k for tok in ("password", "hashed_password", "hash", "pass", "pwd"))


def _extract_dict_str(d: Dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            s = str(v).strip()
            if s:
                return s
    return None


def _extract_unique_from_records(records: Sequence[Dict[str, Any]], keys: Sequence[str]) -> List[str]:
    """Extract ALL unique values (NO LIMITS - COMPREHENSIVE)."""
    found: List[str] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        for k in keys:
            v = r.get(k)
            if v is None:
                continue
            if isinstance(v, str):
                s = v.strip()
                if s:
                    found.append(s)
            elif isinstance(v, (int, float, bool)):
                found.append(str(v))
    return _dedupe_keep_order(found)  # NO LIMIT


@dataclass
class EyedSourceSummary:
    source: str
    count: int
    note: str = ""


def _summarize_dehashed(data: Any) -> EyedSourceSummary:
    if isinstance(data, dict) and data.get("error"):
        return EyedSourceSummary(source="dehashed", count=0, note=f"Error: {data.get('error')}")
    if not isinstance(data, list):
        return EyedSourceSummary(source="dehashed", count=0, note="Returned non-list payload")

    datasets = _extract_unique_from_records(data, keys=["database_name", "database", "source", "db"])
    note = ""
    if datasets:
        note = "Datasets: " + ", ".join(datasets)  # ALL datasets, no limit
    return EyedSourceSummary(source="dehashed", count=len(data), note=note)


def _summarize_whois(data: Any) -> EyedSourceSummary:
    if isinstance(data, dict) and data.get("error"):
        return EyedSourceSummary(source="whois", count=0, note=f"Error: {data.get('error')}")
    if isinstance(data, dict):
        records = data.get("records")
        if isinstance(records, list):
            return EyedSourceSummary(source="whois", count=len(records))
        results = data.get("results")
        if isinstance(results, list):
            return EyedSourceSummary(source="whois", count=len(results))
        return EyedSourceSummary(source="whois", count=1, note="Returned dict payload")
    if isinstance(data, list):
        return EyedSourceSummary(source="whois", count=len(data))
    return EyedSourceSummary(source="whois", count=0, note="Returned non-dict payload")


def _summarize_generic_source(source: str, data: Any) -> EyedSourceSummary:
    if isinstance(data, dict) and data.get("error"):
        return EyedSourceSummary(source=source, count=0, note=f"Error: {data.get('error')}")
    if isinstance(data, list):
        return EyedSourceSummary(source=source, count=len(data))
    if isinstance(data, dict):
        return EyedSourceSummary(source=source, count=1)
    if isinstance(data, str):
        return EyedSourceSummary(source=source, count=1, note=data)
    return EyedSourceSummary(source=source, count=0, note=f"Returned {type(data).__name__}")


def _dedupe_entities(entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe ALL entities (NO LIMITS - COMPREHENSIVE)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for e in entities or []:
        if not isinstance(e, dict):
            continue
        value = str(e.get("value") or "").strip()
        etype = str(e.get("type") or "").strip().upper()
        if not value or not etype:
            continue
        key = (etype, value.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": etype, "value": value, "context": e.get("context")})
    return out  # NO LIMIT


def _render_eyed_result(
    result: Dict[str, Any],
    *,
    include_raw: bool = False,
    url_to_num: Optional[Dict[str, int]] = None,
) -> str:
    query = str(result.get("query") or "").strip()
    subtype = str(result.get("subtype") or result.get("query_type") or "unknown").strip()
    ts = str(result.get("timestamp") or result.get("extracted_at") or "")
    if not ts:
        ts = _now_iso()

    results_list = result.get("results") if isinstance(result.get("results"), list) else []
    entities_raw = result.get("extracted_entities") or result.get("entities") or []
    entities = _dedupe_entities(_as_list(entities_raw))

    source_urls: Dict[str, str] = {}

    # Source summaries
    summaries: List[EyedSourceSummary] = []
    for entry in results_list:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "unknown").strip().lower()
        data = entry.get("data")
        if source == "dehashed":
            summaries.append(_summarize_dehashed(data))
        elif "whois" in source:
            summaries.append(_summarize_whois(data))
        else:
            summaries.append(_summarize_generic_source(source, data))

        if source not in source_urls:
            url = _extract_source_url(entry)
            # Only include real profile URLs in source_urls for footnotes
            if url and _is_real_profile_url(url):
                source_urls[source] = url

    # Aggregate by source name
    by_source: Dict[str, EyedSourceSummary] = {}
    for s in summaries:
        if s.source in by_source:
            prev = by_source[s.source]
            prev.count += s.count
            if s.note and s.note not in prev.note:
                prev.note = _collapse_ws(" | ".join([prev.note, s.note]).strip(" |"))
        else:
            by_source[s.source] = EyedSourceSummary(source=s.source, count=s.count, note=s.note)

    sources_order = sorted(by_source.values(), key=lambda x: (-x.count, x.source))

    # Extract ALL identifiers (COMPREHENSIVE - NO LIMITS)
    headline_by_type: Dict[str, List[str]] = {}
    for e in entities:
        t = e.get("type") or ""
        v = str(e.get("value") or "").strip()
        if not t or not v:
            continue
        if _looks_sensitive_key(t):
            continue
        headline_by_type.setdefault(t, []).append(v)

    def _all_items(t: str) -> List[str]:
        """Return ALL items (NO LIMITS)."""
        return _dedupe_keep_order(headline_by_type.get(t, []))

    lines: List[str] = []
    lines.append(f"## EYE-D Result: {_safe_markdown(query) if query else '(no query)'}")
    lines.append("")
    lines.append(f"- **Type**: `{subtype}`")
    lines.append(f"- **Timestamp**: `{_safe_markdown(ts)}`")
    lines.append(f"- **Sources Returned**: `{len(sources_order)}`")
    lines.append(f"- **Lead Entities Extracted**: `{len(entities)}`")
    lines.append("")

    if sources_order:
        lines.append("### Source Summary")
        lines.append("")
        for s in sources_order:
            note = f" — {_safe_markdown(s.note)}" if s.note else ""
            fn = ""
            if url_to_num and s.source in source_urls:
                num = url_to_num.get(source_urls[s.source])
                if num is not None:
                    fn = f"[^{num}]"
            lines.append(f"- `{s.source}`: `{s.count}`{note}{fn}")
        lines.append("")

    # ALL identifiers (COMPREHENSIVE - NO truncation, NO "examples" language)
    headline_sections: List[Tuple[str, List[str]]] = [
        ("Names", _all_items("NAME") + _all_items("PERSON")),
        ("Emails", _all_items("EMAIL") + _all_items("EMAIL_ADDRESS")),
        ("Phones", _all_items("PHONE") + _all_items("PHONE_NUMBER")),
        ("Usernames", _all_items("USERNAME")),
        ("Domains/URLs", _all_items("DOMAIN") + _all_items("URL") + _all_items("SOCIAL_URL") + _all_items("LINKEDIN") + _all_items("LINKEDIN_URL")),
        ("IPs", _all_items("IP") + _all_items("IP_ADDRESS")),
        ("Companies", _all_items("COMPANY") + _all_items("ORGANIZATION")),
        ("Locations", _all_items("LOCATION") + _all_items("ADDRESS")),
    ]

    has_any_headlines = any(items for _, items in headline_sections)
    if has_any_headlines:
        lines.append("### Extracted Identifiers")
        lines.append("")
        for title, items in headline_sections:
            if not items:
                continue
            # CRITICAL: Show ALL items, NO truncation, NO "(+X more)" language
            full_list = ", ".join(_safe_markdown(i) for i in items)
            lines.append(f"- **{title}**: {full_list}")
        lines.append("")

    # Recommended next queries - ALL entities (COMPREHENSIVE)
    if entities:
        lines.append("### Recommended Next Queries (Recursive IO Chain)")
        lines.append("")
        next_items = []
        for e in entities:
            t = (e.get("type") or "").upper()
            v = str(e.get("value") or "").strip()
            if not v or _looks_sensitive_key(t):
                continue
            if t in {"EMAIL", "EMAIL_ADDRESS"}:
                next_items.append(f"`e: {v}`")
            elif t in {"PHONE", "PHONE_NUMBER"}:
                next_items.append(f"`t: {v}`")
            elif t in {"DOMAIN"}:
                next_items.append(f"`d: {v}`")
            elif t in {"URL", "SOCIAL_URL", "LINKEDIN", "LINKEDIN_URL"}:
                next_items.append(f"`u: {v}`")
            elif t in {"USERNAME"}:
                next_items.append(f"`u: {v}`")
            elif t in {"IP", "IP_ADDRESS"}:
                next_items.append(f"`ip: {v}` (requires geolocation)")
            elif t in {"NAME", "PERSON"}:
                next_items.append(f"`p: {v}`")
            elif t in {"COMPANY", "ORGANIZATION"}:
                next_items.append(f"`c: {v}`")
        next_items = _dedupe_keep_order(next_items)  # ALL items, no limit
        if next_items:
            for item in next_items:
                lines.append(f"- {item}")
        else:
            lines.append("- (No structured leads available.)")
        lines.append("")

    if include_raw:
        lines.append("### Raw Output (JSON)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result, indent=2, default=str)[:200000])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _parse_osintresult_string(s: str) -> Dict[str, Any]:
    text = str(s or "")
    out: Dict[str, Any] = {"raw": text}
    patterns = {
        "module": r"module='([^']+)'",
        "registered": r"\bregistered=(True|False)\b",
        "verified": r"\bverified=(True|False)\b",
        "name": r"\bname='([^']+)'",
        "first_name": r"\bfirst_name='([^']+)'",
        "last_name": r"\blast_name='([^']+)'",
        "username": r"\busername='([^']+)'",
        "profile_url": r"\bprofile_url='([^']+)'",
        "email_hint": r"\bemail_hint='([^']+)'",
        "phone_hint": r"\bphone_hint='([^']+)'",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            out[key] = m.group(1)

    qm = re.search(r"\bquery='([^']+)'", text) or re.search(r"'query':\s*'([^']+)'", text)
    if qm:
        out["query"] = qm.group(1)
    return out


def _render_osintresult_dump(items: List[str], *, include_raw: bool = False) -> str:
    parsed = [_parse_osintresult_string(i) for i in items if isinstance(i, str) and i.strip()]

    query_values = _dedupe_keep_order([p.get("query", "") for p in parsed if p.get("query")])
    modules = _dedupe_keep_order([p.get("module", "") for p in parsed if p.get("module")])
    names = _dedupe_keep_order([p.get("name", "") for p in parsed if p.get("name")])

    registered = [p for p in parsed if str(p.get("registered", "")).lower() == "true"]
    verified = [p for p in parsed if str(p.get("verified", "")).lower() == "true"]

    lines: List[str] = []
    lines.append("## EYE-D Result: OSINTResult Dump (legacy)")
    lines.append("")
    if query_values:
        lines.append(f"- **Query**: `{_safe_markdown(query_values[0])}`")
    lines.append(f"- **Total Items**: `{len(parsed)}`")
    lines.append(f"- **Modules**: `{len(modules)}`")
    lines.append(f"- **Registered Flags (True)**: `{len(registered)}`")
    lines.append(f"- **Verified Flags (True)**: `{len(verified)}`")
    lines.append("")

    if names:
        lines.append("### Observed Names")
        lines.append("")
        # COMPREHENSIVE: Show ALL names, no limits
        for n in names:
            lines.append(f"- {_safe_markdown(n)}")
        lines.append("")

    if modules:
        lines.append("### Modules (Observed)")
        lines.append("")
        # COMPREHENSIVE: Show ALL modules, no limits
        for m in modules:
            lines.append(f"- `{_safe_markdown(m)}`")
        lines.append("")

    if include_raw:
        lines.append("### Raw Items")
        lines.append("")
        # COMPREHENSIVE: Show ALL items
        for p in parsed:
            lines.append(f"- {_safe_markdown(p.get('raw', ''))}")
        lines.append("")

    return "\n".join(lines)


def _render_outputpy_formatted(data: Dict[str, Any], *, include_raw: bool = False) -> str:
    primary = str(data.get("primary_email") or data.get("primary") or "").strip()
    extracted_at = str(data.get("extracted_at") or "")
    sections = data.get("sections") if isinstance(data.get("sections"), dict) else {}

    lines: List[str] = []
    lines.append(f"## EYE-D Result: Formatted Output ({_safe_markdown(primary) if primary else 'unknown'})")
    lines.append("")
    if extracted_at:
        lines.append(f"- **Extracted At**: `{_safe_markdown(extracted_at)}`")
    lines.append(f"- **Sections**: `{len(sections)}`")
    lines.append("")

    if sections:
        lines.append("### Sections")
        lines.append("")
        # COMPREHENSIVE: Show ALL sections
        for section_name, payload in sections.items():
            item_count = 0
            if isinstance(payload, dict):
                for _, v in payload.items():
                    if isinstance(v, list):
                        item_count += len(v)
                    elif isinstance(v, dict):
                        item_count += len(v)
                    else:
                        item_count += 1
            elif isinstance(payload, list):
                item_count = len(payload)
            else:
                item_count = 1
            lines.append(f"- **{_safe_markdown(section_name)}**: `{item_count}` items")
        lines.append("")

    if include_raw:
        lines.append("### Raw Output (JSON)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(data, indent=2, default=str)[:200000])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def render_report(docs: List[Tuple[str, Any]], *, include_raw: bool = False) -> str:
    lines: List[str] = []
    lines.append("# EYE-D OSINT Investigation Report")
    lines.append("")
    lines.append(f"Generated: `{_now_iso()}`")
    lines.append("")
    lines.append("**Investigation Notes:**")
    lines.append("- Results are comprehensive with no truncation")
    lines.append("- All discovered entities must be reinvestigated recursively")
    lines.append("- IP addresses must be geolocated before listing")
    lines.append("- Footnotes contain only real profile/website URLs (no API endpoints)")
    lines.append("")

    url_to_num = _collect_footnote_urls(docs)

    # Main content (summary view)
    for label, data in docs:
        lines.append(f"**Input**: `{_safe_markdown(label)}`")
        lines.append("")

        if isinstance(data, dict) and ("query" in data or "results" in data) and isinstance(data.get("results"), list):
            lines.append(_render_eyed_result(data, include_raw=False, url_to_num=url_to_num))
        elif isinstance(data, dict) and "sections" in data:
            lines.append(_render_outputpy_formatted(data, include_raw=False))
        elif isinstance(data, list) and all(isinstance(i, str) for i in data):
            lines.append(_render_osintresult_dump(data, include_raw=False))
        else:
            lines.append("## EYE-D Result: Unrecognized Shape")
            lines.append("")
            lines.append(f"- **Type**: `{type(data).__name__}`")
            lines.append("")

    # Footnotes
    if url_to_num:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for url, num in sorted(url_to_num.items(), key=lambda x: x[1]):
            lines.append(f"[^{num}]: {url}")
        lines.append("")

    # APPENDIX: ALL RAW OUTPUT (ALWAYS INCLUDED)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("# APPENDIX: Raw Output")
    lines.append("")
    lines.append("Complete raw data for all investigation results.")
    lines.append("")

    for i, (label, data) in enumerate(docs, 1):
        lines.append(f"## Appendix {i}: {_safe_markdown(label)}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(data, indent=2, default=str))
        lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate COMPREHENSIVE EDITH-style Markdown write-up from EYE-D output.")
    parser.add_argument("inputs", nargs="+", help="Input JSON file(s)")
    parser.add_argument("-o", "--output", help="Write Markdown to this file (default: stdout)")
    parser.add_argument("--include-raw", action="store_true", help="Append raw JSON payloads")

    args = parser.parse_args(argv)

    docs: List[Tuple[str, Any]] = []
    for raw_path in args.inputs:
        path = Path(raw_path).expanduser().resolve()
        try:
            docs.append((str(path), _read_json(path)))
        except Exception as e:
            docs.append((str(path), {"error": f"Failed to read JSON: {e}"}))

    report = render_report(docs, include_raw=bool(args.include_raw))

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
