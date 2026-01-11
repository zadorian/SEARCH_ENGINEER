"""US source resolution helpers for state-aware routing."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from .us_state_data import US_STATES, US_STATE_CODES

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SOURCES_PATH = PROJECT_ROOT / "input_output" / "matrix" / "sources.json"

_SOURCES_CACHE: Optional[Dict[str, Dict]] = None
_STATE_SOURCE_CACHE: Dict[tuple, List[Dict]] = {}

SECTION_ALIASES = {
    "cr": {"cr", "corporate_registry", "company_registry", "registry"},
    "reg": {"reg", "regulatory", "licensing", "sanctions"},
    "lit": {"lit", "litigation", "court", "legal", "case"},
    "ass": {"ass", "asset", "assets", "property", "land", "cadastre"},
    "news": {"news", "media", "press"},
}

STATE_ALIAS_OVERRIDES = {
    "DC": ["district of columbia", "washington dc", "washington d.c."],
    "WA": ["washington state", "state of washington"],
}


def _load_sources() -> Dict[str, Dict]:
    global _SOURCES_CACHE
    if _SOURCES_CACHE is None:
        with SOURCES_PATH.open() as f:
            data = json.load(f)
        _SOURCES_CACHE = data.get("sources", {})
    return _SOURCES_CACHE


def _collect_jurisdictions(source: Dict) -> List[str]:
    jurisdictions = []
    raw = source.get("jurisdictions")
    if isinstance(raw, list):
        jurisdictions.extend([j for j in raw if isinstance(j, str)])
    elif isinstance(raw, str):
        jurisdictions.append(raw)

    for key in ("jurisdiction", "_sourceJurisdiction"):
        value = source.get(key)
        if isinstance(value, str):
            jurisdictions.append(value)

    return jurisdictions


def _is_us_source(source: Dict) -> bool:
    jurisdictions = _collect_jurisdictions(source)
    if any(jur == "US" for jur in jurisdictions):
        return True
    if any(jur.startswith("US_") for jur in jurisdictions if isinstance(jur, str)):
        return True
    return False


def _state_aliases(state_code: str) -> List[str]:
    name = US_STATES.get(state_code, "")
    aliases = [name.lower()] if name else []
    aliases.extend(STATE_ALIAS_OVERRIDES.get(state_code, []))
    return [alias for alias in aliases if alias]


def _domain_tokens(state_code: str) -> List[str]:
    name = US_STATES.get(state_code, "").lower()
    slug = name.replace(" ", "") if name else ""
    code = state_code.lower()
    tokens = []
    if code:
        tokens.append(f".{code}.gov")
    if slug:
        tokens.append(f".{slug}.gov")
    if state_code == "DC":
        tokens.append(".dc.gov")
    return tokens


def source_matches_section(source: Dict, section: Optional[str]) -> bool:
    if not section:
        return True
    section = section.lower()
    aliases = SECTION_ALIASES.get(section, {section})

    for key in ("section", "category", "type"):
        value = source.get(key)
        if isinstance(value, str) and value.lower() in aliases:
            return True

    tags = source.get("thematic_tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, str):
                continue
            tag_lower = tag.lower()
            if tag_lower in aliases:
                return True
            if any(alias in tag_lower for alias in aliases):
                return True

    return False


def source_matches_state(source: Dict, state_code: str) -> bool:
    if state_code not in US_STATE_CODES:
        return False

    jurisdictions = _collect_jurisdictions(source)
    if f"US_{state_code}" in jurisdictions:
        return True

    if not _is_us_source(source):
        return False

    name = (source.get("name") or "").lower()
    notes = (source.get("notes") or "").lower()
    wiki_context = (source.get("wiki_context") or "").lower()
    domain = (source.get("domain") or "").lower()
    url = (source.get("url") or "").lower()

    for token in _domain_tokens(state_code):
        if token and (domain.endswith(token) or token in url):
            return True

    aliases = _state_aliases(state_code)
    searchable = " ".join([name, notes, wiki_context])

    for alias in aliases:
        if alias in searchable:
            if state_code == "WA" and "washington dc" in searchable:
                continue
            return True

    return False


def get_state_sources(state_code: Optional[str], section: Optional[str] = None) -> List[Dict]:
    cache_key = (state_code or "US", section or "all")
    if cache_key in _STATE_SOURCE_CACHE:
        return _STATE_SOURCE_CACHE[cache_key]

    sources = []
    for source in _load_sources().values():
        if not isinstance(source, dict):
            continue
        if state_code:
            if not source_matches_state(source, state_code):
                continue
        else:
            if not _is_us_source(source):
                continue

        if not source_matches_section(source, section):
            continue

        sources.append(source)

    _STATE_SOURCE_CACHE[cache_key] = sources
    return sources


def build_search_url(source: Dict, query: str) -> str:
    query = query or ""
    for key in ("search_template", "search_url", "url"):
        template = source.get(key)
        if not isinstance(template, str) or not template:
            continue
        if "{q}" in template:
            return template.replace("{q}", quote_plus(query))
        return template
    return ""


def build_source_link(source: Dict, query: str, jurisdiction: str, section: str) -> Dict:
    return {
        "source_id": source.get("id") or source.get("domain"),
        "name": source.get("name") or source.get("domain"),
        "domain": source.get("domain"),
        "url": build_search_url(source, query),
        "section": source.get("section") or section,
        "category": source.get("category"),
        "type": source.get("type"),
        "handled_by": source.get("handled_by"),
        "aggregator": source.get("aggregator"),
        "jurisdiction": jurisdiction,
        "access": source.get("access") or source.get("friction"),
    }
