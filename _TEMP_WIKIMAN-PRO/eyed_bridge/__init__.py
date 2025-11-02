"""
Lightweight bridge that exposes the EYE-D UnifiedSearcher inside WIKIMAN-PRO.

This wrapper mirrors the behaviour of the standalone EYE-D MCP server so the
OSINT investigation flow can be triggered directly from the WIKIMAN MCP
without spawning a second process.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locate the EYE-D repository and put it on PYTHONPATH
# ---------------------------------------------------------------------------
_DEFAULT_ROOT_CANDIDATES: List[Path] = []

env_root = os.getenv("EYED_ROOT")
if env_root:
    _DEFAULT_ROOT_CANDIDATES.append(Path(env_root).expanduser())

try:
    repo_root = Path(__file__).resolve().parents[2] / "EYE-D"
    _DEFAULT_ROOT_CANDIDATES.append(repo_root)
except Exception:
    pass

_DEFAULT_ROOT_CANDIDATES.append(
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "01_ACTIVE_PROJECTS"
    / "Development"
    / "EYE-D"
)

_EYED_ROOT: Optional[Path] = None
for candidate in _DEFAULT_ROOT_CANDIDATES:
    if candidate and candidate.exists():
        if str(candidate) not in sys.path:
            sys.path.append(str(candidate))
        _EYED_ROOT = candidate
        break

if not _EYED_ROOT:
    logger.warning("EYE-D repository not found. Set EYED_ROOT to enable OSINT integration.")

# ---------------------------------------------------------------------------
# Optional imports (many backends are graceful when absent)
# ---------------------------------------------------------------------------
try:
    from unified_osint import UnifiedSearcher  # type: ignore
except Exception as exc:  # pragma: no cover - optional dependency
    UnifiedSearcher = None  # type: ignore
    logger.warning("UnifiedSearcher unavailable: %s", exc)

# ---------------------------------------------------------------------------
# Constants copied from the original EYE-D server
# ---------------------------------------------------------------------------
MAX_QUERY_LENGTH = 10000
SEARCH_TIMEOUT = 120.0
DISPLAY_PREVIEW_LIMIT = 10

# ---------------------------------------------------------------------------
# Utility helpers (ported from eyed_mcp_server)
# ---------------------------------------------------------------------------


def escape_markdown(text: str) -> str:
    if not text:
        return text
    markdown_chars = [
        "\\",
        "`",
        "*",
        "_",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "#",
        "+",
        "-",
        ".",
        "!",
        "|",
        "<",
        ">",
    ]
    for char in markdown_chars:
        text = text.replace(char, "\\" + char)
    return text


def parse_batch_query(query: str) -> Optional[List[Tuple[str, str]]]:
    batch_pattern = (
        r"(?:^|\s)"
        r"(e|email|t|tel|d|domain|l|linkedin|n|name|p|person|u|username|pw|pass)"
        r":(\S+(?:\s+\S+)*?)(?=\s+(?:e|email|t|tel|d|domain|l|linkedin|n|name|p|person|u|username|pw|pass):|$)"
    )
    matches = re.findall(batch_pattern, query, re.IGNORECASE)
    if not matches:
        return None

    prefix_map = {
        "e": "email",
        "email": "email",
        "t": "phone",
        "tel": "phone",
        "d": "domain",
        "domain": "domain",
        "l": "linkedin_url",
        "linkedin": "linkedin_url",
        "n": "name",
        "name": "name",
        "p": "name",
        "person": "name",
        "u": "name",
        "username": "name",
        "pw": "password",
        "pass": "password",
    }

    queries: List[Tuple[str, str]] = []
    for prefix, value in matches:
        queries.append((value.strip(), prefix_map.get(prefix.lower(), "term")))
    return queries or None


def extract_discovered_entities(
    query: str,
    input_type: str,
    results: Dict[str, Any],
) -> Dict[str, List[Tuple[str, str, str]]]:
    discovered: Dict[str, List[Tuple[str, str, str]]] = {
        "emails": [],
        "phones": [],
        "domains": [],
        "linkedin_urls": [],
        "names": [],
        "companies": [],  # Add company extraction
        "usernames": [],  # Add username extraction
        "social_urls": [],  # Add social media URLs
    }

    seen: Dict[str, Set[str]] = {key: set() for key in discovered}

    def add_if_new(category: str, value: str, source: str, context: str) -> None:
        if not value:
            return
        if value in seen[category]:
            return
        seen[category].add(value)
        discovered[category].append((value, source, context))

    if input_type == "email" and query:
        add_if_new("emails", query, "Search query", "Original input email")
    if input_type == "phone" and query:
        add_if_new("phones", query, "Search query", "Original input phone")
    if input_type in {"domain", "company_linkedin_url"} and query:
        add_if_new("domains", query, "Search query", "Original input domain")
    if "linkedin.com/" in query.lower():
        add_if_new("linkedin_urls", query, "Search query", "Original LinkedIn URL")
    if input_type in {"name", "name_term", "name_at_company"} and query:
        add_if_new("names", query, "Search query", "Original input name")
    elif "@" not in query and re.search(r"\s", query):
        add_if_new("names", query, "Search query", "Original input")

    rr_data = results.get("rocketreach")
    if rr_data:
        source = "RocketReach"
        try:
            emails = getattr(rr_data, "emails", []) or []
            for email in emails:
                email_value = getattr(email, "email", None) if email else None
                if email_value:
                    add_if_new("emails", email_value, source, "RocketReach profile email")
        except Exception:
            pass
        try:
            phones = getattr(rr_data, "phones", []) or []
            for phone in phones:
                phone_value = getattr(phone, "number", None) if phone else None
                if phone_value:
                    add_if_new("phones", phone_value, source, "RocketReach profile phone")
        except Exception:
            pass
        linkedin_url = getattr(rr_data, "linkedin_url", None)
        if linkedin_url:
            add_if_new("linkedin_urls", linkedin_url, source, "RocketReach profile")
        rr_name = getattr(rr_data, "name", None)
        if rr_name:
            add_if_new("names", rr_name, source, "RocketReach profile name")
        # Extract company information
        current_employer = getattr(rr_data, "current_employer", None)
        if current_employer:
            add_if_new("companies", current_employer, source, "Current employer")
        # Extract social media links
        links = getattr(rr_data, "links", None)
        if isinstance(links, dict):
            for platform, url in links.items():
                if url and platform.lower() not in {"linkedin"}:
                    add_if_new("social_urls", url, source, f"Social: {platform}")

    co_data = results.get("contactout")
    if co_data:
        source = "ContactOut"
        co_email = getattr(co_data, "email", None) or getattr(co_data, "work_email", None)
        if co_email:
            add_if_new("emails", co_email, source, "ContactOut email")
        co_phone = getattr(co_data, "phone", None)
        if co_phone:
            add_if_new("phones", co_phone, source, "ContactOut phone")
        co_linkedin = getattr(co_data, "url", None)
        if co_linkedin:
            add_if_new("linkedin_urls", co_linkedin, source, "ContactOut profile")
        co_name = getattr(co_data, "full_name", None) or getattr(co_data, "name", None)
        if co_name:
            add_if_new("names", co_name, source, "ContactOut profile name")
        # Extract company
        co_company = getattr(co_data, "company", None)
        if co_company:
            add_if_new("companies", co_company, source, "ContactOut company")

    kaspr_data = results.get("kaspr")
    if kaspr_data:
        source = "Kaspr"
        phones = getattr(kaspr_data, "phones", []) or []
        for phone in phones:
            if isinstance(phone, dict):
                add_if_new("phones", phone.get("phone"), source, "Kaspr phone number")
        emails = getattr(kaspr_data, "emails", []) or []
        for email in emails:
            if isinstance(email, dict):
                add_if_new("emails", email.get("email"), source, "Kaspr email")
        linkedin_url = getattr(kaspr_data, "linkedin_url", None)
        if linkedin_url:
            add_if_new("linkedin_urls", linkedin_url, source, "Kaspr profile")
        full_name = getattr(kaspr_data, "full_name", None)
        if full_name:
            add_if_new("names", full_name, source, "Kaspr profile name")
        # Extract company
        kaspr_company = getattr(kaspr_data, "company", None)
        if kaspr_company:
            add_if_new("companies", kaspr_company, source, "Kaspr company")

    if "osint_industries" in results and results["osint_industries"]:
        osint_result = results["osint_industries"]
        source = "OSINT Industries"
        try:
            candidate_emails = getattr(osint_result, "emails", None)
            if isinstance(candidate_emails, list):
                for email in candidate_emails:
                    add_if_new("emails", email, source, "OSINT Industries result")
        except Exception:
            pass
        try:
            profiles = getattr(osint_result, "profiles", None)
            if isinstance(profiles, list):
                for profile in profiles:
                    if hasattr(profile, "link"):
                        add_if_new("linkedin_urls", profile.link, source, "OSINT Industries profile")
        except Exception:
            pass
        try:
            name = getattr(osint_result, "name", None)
            if name:
                add_if_new("names", name, source, "OSINT Industries name")
        except Exception:
            pass

    if "dehashed" in results and results["dehashed"]:
        dehashed_data = results["dehashed"]
        source = "Dehashed breaches"
        if isinstance(dehashed_data, list):
            for record in dehashed_data:
                if not isinstance(record, dict):
                    continue
                email = record.get("email")
                if email:
                    add_if_new("emails", email, source, "Breach record email")
                phone = record.get("phone")
                if phone:
                    add_if_new("phones", phone, source, "Breach record phone")
                password = record.get("password")
                if password:
                    add_if_new("emails", f"{record.get('email')} (password hash)", source, "Breach password hash")
                # Extract usernames separately
                username = record.get("username")
                if username and "@" not in username:  # Don't duplicate emails
                    add_if_new("usernames", username, source, "Breach username")
                for field in ("first_name", "last_name", "name"):
                    val = record.get(field)
                    if val:
                        add_if_new("names", val, source, "Breach record name")

    if "whoisxmlapi_history" in results and results["whoisxmlapi_history"]:
        whois_data = results["whoisxmlapi_history"]
        source = "WHOIS History"
        if isinstance(whois_data, dict):
            if whois_data.get("registrant_email"):
                add_if_new("emails", whois_data["registrant_email"], source, "Registrant email")
            if whois_data.get("registrant"):
                add_if_new("names", whois_data["registrant"], source, "Registrant name")
            if whois_data.get("organization"):
                add_if_new("names", whois_data["organization"], source, "Registrant org")

    if "whoisxmlapi_reverse" in results and results["whoisxmlapi_reverse"]:
        whois_reverse = results["whoisxmlapi_reverse"]
        source = "WHOIS Reverse"
        if isinstance(whois_reverse, list):
            for domain in whois_reverse:
                if isinstance(domain, str):
                    add_if_new("domains", domain, source, "Same registrant")

    # Extract RocketReach company data
    if results.get("rocketreach_company"):
        company = results["rocketreach_company"]
        source = "RocketReach Company"
        company_name = getattr(company, "name", None)
        if company_name:
            add_if_new("companies", company_name, source, "Company profile")
        company_domain = getattr(company, "domain", None)
        if company_domain:
            add_if_new("domains", company_domain, source, "Company domain")

    return discovered


def format_osint_report(query: str, input_type: str, results: Dict[str, Any], execution_time: float) -> str:
    lines: List[str] = []
    lines.append("# 🔍 OSINT Investigation Report")
    lines.append("")
    lines.append(f"**Query**: `{escape_markdown(query)}`")
    lines.append(f"**Type**: {input_type.replace('_', ' ').title()} (auto-detected)")
    lines.append(f"**Timestamp**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Execution Time**: {execution_time:.2f}s")
    lines.append("")

    sources_queried = len(results)
    sources_found = sum(1 for v in results.values() if v and not isinstance(v, str))
    lines.append("## 📊 Summary")
    lines.append(f"- Sources queried: {sources_queried}")
    lines.append(f"- Data found: {sources_found} sources")
    lines.append("")

    def _append_section(title: str) -> None:
        lines.append(title)

    # Due to length, we reuse the same sections as the MCP server.
    # Only key highlights are included here; detailed data remains in structured payload.

    rr_data = results.get("rocketreach")
    if rr_data:
        lines.append("## 🚀 RocketReach (✓ Found)")
        if hasattr(rr_data, "name"):
            lines.append(f"- **Name**: {rr_data.name}")
        if getattr(rr_data, "current_title", None):
            lines.append(f"- **Current Title**: {rr_data.current_title}")
        if getattr(rr_data, "current_employer", None):
            lines.append(f"- **Current Employer**: {rr_data.current_employer}")
        emails = getattr(rr_data, "emails", []) or []
        if emails:
            lines.append("- **Emails**:")
            for email in emails[:DISPLAY_PREVIEW_LIMIT]:
                if hasattr(email, "email"):
                    status_attr = getattr(email, "smtp_valid", None)
                    if status_attr is True:
                        status = " (valid)"
                    elif status_attr is False:
                        status = " (invalid)"
                    elif status_attr:
                        status = f" ({status_attr})"
                    else:
                        status = ""
                    lines.append(f"  - {email.email}{status}")
        phones = getattr(rr_data, "phones", []) or []
        if phones:
            lines.append("- **Phones**:")
            for phone in phones[:DISPLAY_PREVIEW_LIMIT]:
                if hasattr(phone, "number"):
                    lines.append(f"  - {phone.number}")
        linkedin_url = getattr(rr_data, "linkedin_url", None)
        if linkedin_url:
            lines.append(f"- **LinkedIn**: {linkedin_url}")
        links = getattr(rr_data, "links", None)
        if isinstance(links, dict) and links:
            lines.append("- **Social Profiles**:")
            for platform, url in list(links.items())[:DISPLAY_PREVIEW_LIMIT]:
                if url:
                    lines.append(f"  - {platform}: {url}")
        lines.append("")
    elif results.get("rocketreach_error"):
        lines.append("## 🚀 RocketReach (✗ Error)")
        lines.append(f"- Error: {results['rocketreach_error']}")
        lines.append("")

    if results.get("rocketreach_company"):
        company = results["rocketreach_company"]
        lines.append("## 🏢 RocketReach Company Data (✓ Found)")
        if hasattr(company, "name"):
            lines.append(f"- **Company Name**: {company.name}")
        if getattr(company, "domain", None):
            lines.append(f"- **Domain**: {company.domain}")
        if getattr(company, "industry", None):
            lines.append(f"- **Industry**: {company.industry}")
        if getattr(company, "size", None):
            lines.append(f"- **Size**: {company.size}")
        if getattr(company, "location", None):
            lines.append(f"- **Location**: {company.location}")
        lines.append("")

    co_data = results.get("contactout")
    if co_data:
        lines.append("## 📇 ContactOut (✓ Found)")
        if getattr(co_data, "full_name", None):
            lines.append(f"- **Name**: {co_data.full_name}")
        if getattr(co_data, "company", None):
            lines.append(f"- **Company**: {co_data.company}")
        if getattr(co_data, "title", None):
            lines.append(f"- **Title**: {co_data.title}")
        if getattr(co_data, "url", None):
            lines.append(f"- **LinkedIn**: {co_data.url}")
        lines.append("")

    kaspr_data = results.get("kaspr")
    if kaspr_data:
        lines.append("## 🔗 Kaspr (✓ Found)")
        if getattr(kaspr_data, "full_name", None):
            lines.append(f"- **Name**: {kaspr_data.full_name}")
        if getattr(kaspr_data, "position", None):
            lines.append(f"- **Position**: {kaspr_data.position}")
        phones = getattr(kaspr_data, "phones", None)
        if isinstance(phones, list) and phones:
            lines.append("- **Phones**:")
            for phone in phones[:DISPLAY_PREVIEW_LIMIT]:
                if isinstance(phone, dict) and phone.get("phone"):
                    lines.append(f"  - {phone['phone']}")
        emails = getattr(kaspr_data, "emails", None)
        if isinstance(emails, list) and emails:
            lines.append("- **Emails**:")
            for email in emails[:DISPLAY_PREVIEW_LIMIT]:
                if isinstance(email, dict) and email.get("email"):
                    lines.append(f"  - {email['email']}")
        lines.append("")

    osint_data = results.get("osint_industries")
    if osint_data:
        lines.append("## 🕵️ OSINT Industries (✓ Found)")
        if getattr(osint_data, "name", None):
            lines.append(f"- **Name**: {osint_data.name}")
        candidate_emails = getattr(osint_data, "emails", None)
        if isinstance(candidate_emails, list) and candidate_emails:
            lines.append("- **Emails**:")
            for email in candidate_emails[:DISPLAY_PREVIEW_LIMIT]:
                lines.append(f"  - {email}")
        lines.append("")

    dehashed_data = results.get("dehashed")
    if isinstance(dehashed_data, list) and dehashed_data:
        lines.append(f"## 🔓 Dehashed Breaches ({len(dehashed_data)} found)")
        sample = dehashed_data[:DISPLAY_PREVIEW_LIMIT]
        for entry in sample:
            if isinstance(entry, dict):
                email = entry.get("email") or entry.get("username")
                breach = entry.get("source")
                lines.append(f"- {email or 'Unknown'} — {breach or 'Breach record'}")
        if len(dehashed_data) > DISPLAY_PREVIEW_LIMIT:
            lines.append(f"  … and {len(dehashed_data) - DISPLAY_PREVIEW_LIMIT} more")
        lines.append("")

    whois_history = results.get("whoisxmlapi_history")
    if isinstance(whois_history, dict) and whois_history:
        lines.append("## 🌐 WHOIS History")
        if whois_history.get("registrant"):
            lines.append(f"- **Registrant**: {whois_history['registrant']}")
        if whois_history.get("registrant_email"):
            lines.append(f"- **Email**: {whois_history['registrant_email']}")
        if whois_history.get("organization"):
            lines.append(f"- **Organisation**: {whois_history['organization']}")
        lines.append("")

    whois_reverse = results.get("whoisxmlapi_reverse")
    if isinstance(whois_reverse, list) and whois_reverse:
        lines.append(f"## 🔁 Reverse WHOIS (Domains: {len(whois_reverse)})")
        for domain in whois_reverse[:DISPLAY_PREVIEW_LIMIT]:
            lines.append(f"- {domain}")
        if len(whois_reverse) > DISPLAY_PREVIEW_LIMIT:
            lines.append(f"  … and {len(whois_reverse) - DISPLAY_PREVIEW_LIMIT} more")
        lines.append("")

    # Additional sections trimmed for brevity—full detail remains in structured payload
    # to keep this report concise, matching the behaviour of the reference MCP server.

    # Add cross-tool suggestions based on discovered entities
    discovered = extract_discovered_entities(query, input_type, results)
    suggestions: List[str] = []

    # Suggest corporate searches for domains
    if discovered.get("domains"):
        for domain, _, _ in discovered["domains"][:2]:
            suggestions.append(f"`c:{domain}` - Corporate registry search")

    # Suggest Aleph searches for names
    if discovered.get("names"):
        for name, _, _ in discovered["names"][:2]:
            if name and name != query:  # Don't suggest searching the original query
                suggestions.append(f"`aleph:{name}` - Leaked document search")

    # Suggest officer searches for corporate officers
    if results.get("rocketreach_company"):
        company = results["rocketreach_company"]
        company_name = getattr(company, "name", None)
        if company_name:
            suggestions.append(f"`officer:{company_name}` - Find company officers")

    # Suggest OSINT searches for newly discovered emails/phones
    if discovered.get("emails"):
        for email, source, _ in discovered["emails"][:2]:
            if email != query:  # Don't suggest re-searching original
                suggestions.append(f"`investigate:{email}` - Deep OSINT on email")

    if discovered.get("linkedin_urls"):
        for url, _, _ in discovered["linkedin_urls"][:1]:
            if url != query:
                suggestions.append(f"`investigate:{url}` - LinkedIn enrichment")

    if suggestions:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 💡 Suggested Follow-up Searches")
        lines.append("")
        lines.append("*Use these queries with `router_search` for deeper investigation:*")
        lines.append("")
        for suggestion in suggestions[:5]:  # Limit to 5 suggestions
            lines.append(f"- {suggestion}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by EYE-D OSINT integration*")
    return "\n".join(lines)


def _count_sources(result: Optional[Dict[str, Any]]) -> int:
    if not isinstance(result, dict):
        return 0
    return sum(1 for v in result.values() if v and not isinstance(v, str))


def _format_batch_report(
    original_query: str,
    batch_entries: List[Tuple[str, str]],
    batch_results: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[str]]],
    execution_time: float,
) -> str:
    lines: List[str] = []
    lines.append("# 🔍 OSINT Batch Investigation Report")
    lines.append("")
    lines.append(f"**Batch Query**: `{escape_markdown(original_query)}`")
    lines.append(f"**Items Investigated**: {len(batch_entries)}")
    lines.append(f"**Timestamp**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Execution Time**: {execution_time:.2f}s")
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, (query_value, query_type, results, error) in enumerate(batch_results, 1):
        lines.append(f"## {idx}. {query_type.replace('_', ' ').title()}: `{escape_markdown(query_value)}`")
        lines.append("")
        if error:
            lines.append(f"❌ **Error**: {error}")
        elif results:
            sources_found = _count_sources(results)
            lines.append(f"✓ **Data Found**: {sources_found} sources")
            summary: List[str] = []
            rr_data = results.get("rocketreach")
            if rr_data:
                name = getattr(rr_data, "name", None)
                employer = getattr(rr_data, "current_employer", None)
                if name:
                    summary.append(f"**Name**: {name}")
                if employer:
                    summary.append(f"**Employer**: {employer}")
            dehashed_data = results.get("dehashed")
            if isinstance(dehashed_data, list) and dehashed_data:
                summary.append(f"**Breaches**: {len(dehashed_data)} found")
            for item in summary:
                lines.append(f"- {item}")
        else:
            lines.append("⚠️ **No data found**")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("*Batch report generated by EYE-D OSINT integration*")
    lines.append("")
    lines.append("💡 **Tip**: Search individual items for deeper analysis.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API Key Validation
# ---------------------------------------------------------------------------


def validate_api_keys() -> Dict[str, bool]:
    """Check which OSINT API keys are configured."""
    return {
        "rocketreach": bool(os.getenv("ROCKETREACH_API_KEY")),
        "contactout": bool(os.getenv("CONTACTOUT_API_KEY")),
        "kaspr": bool(os.getenv("KASPR_API_KEY")),
        "osint_industries": bool(os.getenv("OSINT_INDUSTRIES_API_KEY")),
        "dehashed": bool(os.getenv("DEHASHED_API_KEY")),
        "whoisxmlapi": bool(os.getenv("WHOISXMLAPI_KEY")),
    }


def get_api_status() -> str:
    """Get human-readable API key status report."""
    status = validate_api_keys()
    lines = ["EYE-D OSINT API Status:"]
    for api, configured in status.items():
        symbol = "✓" if configured else "✗"
        status_text = "configured" if configured else "missing"
        lines.append(f"  {symbol} {api.replace('_', ' ').title()}: {status_text}")

    configured_count = sum(status.values())
    total_count = len(status)
    lines.append(f"\nTotal: {configured_count}/{total_count} APIs configured")

    if configured_count == 0:
        lines.append("\n⚠️  No OSINT APIs configured. Set API keys in wikiman.env")
    elif configured_count < total_count:
        lines.append(f"\n⚠️  {total_count - configured_count} APIs not configured (optional)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UnifiedSearcher lifecycle
# ---------------------------------------------------------------------------
_SEARCHER_LOCK = threading.Lock()
_SEARCHER: Optional[UnifiedSearcher] = None


def _get_searcher() -> UnifiedSearcher:
    if UnifiedSearcher is None:
        raise RuntimeError("UnifiedSearcher class not available")

    global _SEARCHER
    with _SEARCHER_LOCK:
        if _SEARCHER is None:
            logger.info("Initialising UnifiedSearcher for EYE-D integration")
            start_time = time.perf_counter()
            _SEARCHER = UnifiedSearcher()
            init_time = time.perf_counter() - start_time
            logger.info(f"UnifiedSearcher initialized in {init_time:.2f}s")

            # Log API key status
            api_status = validate_api_keys()
            configured = [k for k, v in api_status.items() if v]
            missing = [k for k, v in api_status.items() if not v]
            if configured:
                logger.info(f"OSINT APIs configured: {', '.join(configured)}")
            if missing:
                logger.warning(f"OSINT APIs not configured: {', '.join(missing)}")

        return _SEARCHER


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def investigate(query: str) -> Dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "Query parameter is required."}
    if len(query) > MAX_QUERY_LENGTH:
        return {
            "ok": False,
            "error": f"Query too long (max {MAX_QUERY_LENGTH} characters).",
        }

    try:
        searcher = _get_searcher()
    except Exception as exc:
        return {"ok": False, "error": f"EYE-D searcher unavailable: {exc}"}

    batch_entries = parse_batch_query(query)
    start_time = time.perf_counter()

    if batch_entries:
        results: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[str]]] = []
        for value, qtype in batch_entries:
            try:
                res = searcher.search(value)
                results.append((value, qtype, res, None))
            except Exception as exc:
                logger.error("Batch search failed for %s: %s", value, exc)
                results.append((value, qtype, None, str(exc)))
        duration = time.perf_counter() - start_time
        report = _format_batch_report(query, batch_entries, results, duration)
        structured_items: List[Dict[str, Any]] = []
        for value, qtype, res, error in results:
            structured_items.append(
                {
                    "query": value,
                    "type": qtype,
                    "error": error,
                    "sources_found": _count_sources(res),
                }
            )
        structured = {
            "mode": "batch",
            "items": structured_items,
            "execution_time": duration,
        }
        return {
            "ok": True,
            "source": "eyed_osint",
            "data": {
                "mode": "batch",
                "report": report,
                "structured": structured,
            },
            "metadata": {
                "execution_time": duration,
                "batch_size": len(batch_entries),
                "sources_queried": 6,  # EYE-D queries 6 OSINT sources
            }
        }

    # Single mode
    input_type = searcher.identify_input_type(query)
    try:
        results = searcher.search(query)
    except Exception as exc:
        logger.error("OSINT investigation failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}

    duration = time.perf_counter() - start_time
    discovered = extract_discovered_entities(query, input_type, results)
    report = format_osint_report(query, input_type, results, duration)

    structured_entities = {
        entity_type: [
            {"value": value, "source": source, "context": context}
            for value, source, context in values
        ]
        for entity_type, values in discovered.items()
        if values
    }

    structured = {
        "mode": "single",
        "query": query,
        "input_type": input_type,
        "execution_time": duration,
        "entity_counts": {key: len(val) for key, val in structured_entities.items()},
        "discovered_entities": structured_entities,
    }

    # Count sources that returned data
    sources_found = sum(1 for v in results.values() if v and not isinstance(v, str))

    return {
        "ok": True,
        "source": "eyed_osint",
        "data": {
            "mode": "single",
            "report": report,
            "structured": structured,
        },
        "metadata": {
            "execution_time": duration,
            "input_type": input_type,
            "sources_queried": len(results),
            "sources_found": sources_found,
            "entities_discovered": sum(len(val) for val in structured_entities.values()),
        }
    }
