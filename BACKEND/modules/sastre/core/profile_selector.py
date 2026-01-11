"""
Profile Selector
================

Selects the most relevant investigation profile/template based on:
  - tasking (scenario)
  - genre (report library)
  - jurisdiction (if known)

Uses the mined investigation templates when available via the semantic API,
and falls back to the report library genre map when not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import os
import json

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except Exception:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)

_REPORT_GEN_CACHE: Optional[Dict[str, Any]] = None
_JURIS_ALIAS_CACHE: Optional[Dict[str, Any]] = None

GENRE_TEMPLATE_MAP = {
    "due_diligence": "due_diligence",
    "background_check": "kyc_check",
    "asset_trace": "asset_tracing",
    "corporate_intelligence": "competitor_analysis",
    "litigation_support": "litigation_research",
}

NAME_ALIASES = {
    "united kingdom": "GB",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "britain": "GB",
    "united states": "US",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "america": "US",
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "cyprus": "CY",
    "panama": "PA",
    "bvi": "VG",
}


def _find_matrix_path() -> Path:
    """Find the input_output/matrix directory (same logic as NarrativeGovernor)."""
    candidates = [
        Path(__file__).parent.parent.parent.parent.parent / "input_output" / "matrix",
        Path(__file__).parent.parent.parent.parent.parent / "input_output2" / "matrix",
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output/matrix"),
        Path("/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output2/matrix"),
    ]

    for path in candidates:
        if path.exists() and (path / "report_generation.json").exists():
            return path

    raise FileNotFoundError(f"Could not find matrix directory. Checked: {candidates}")


def _load_report_generation() -> Dict[str, Any]:
    """Load report_generation.json (cached)."""
    global _REPORT_GEN_CACHE
    if _REPORT_GEN_CACHE is not None:
        return _REPORT_GEN_CACHE

    try:
        matrix_path = _find_matrix_path()
        report_path = matrix_path / "report_generation.json"
        with open(report_path, "r") as f:
            _REPORT_GEN_CACHE = json.load(f)
        return _REPORT_GEN_CACHE
    except Exception as exc:
        logger.warning(f"Failed to load report_generation.json: {exc}")
        return {}


def _load_jurisdiction_aliases() -> Dict[str, Any]:
    """Load jurisdiction_aliases.json (cached)."""
    global _JURIS_ALIAS_CACHE
    if _JURIS_ALIAS_CACHE is not None:
        return _JURIS_ALIAS_CACHE

    try:
        matrix_path = _find_matrix_path()
        alias_path = matrix_path / "jurisdiction_aliases.json"
        with open(alias_path, "r") as f:
            _JURIS_ALIAS_CACHE = json.load(f)
        return _JURIS_ALIAS_CACHE
    except Exception as exc:
        logger.warning(f"Failed to load jurisdiction_aliases.json: {exc}")
        return {}


def normalize_jurisdiction(value: Optional[str]) -> Optional[str]:
    """Normalize jurisdiction to ISO-3166 alpha-2 when possible."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Two-letter codes
    if len(raw) == 2 and raw.isalpha():
        code = raw.upper()
        aliases = _load_jurisdiction_aliases()
        default_map = aliases.get("default_by_legacy_key", {}) if isinstance(aliases, dict) else {}
        return default_map.get(code, code)

    # Common names and aliases
    lower = raw.lower()
    if lower in NAME_ALIASES:
        return NAME_ALIASES[lower]

    # cctld overrides (e.g., uk -> GB)
    aliases = _load_jurisdiction_aliases()
    if isinstance(aliases, dict):
        cctld = aliases.get("cctld_overrides", {}) or {}
        cctld_key = lower.lstrip(".")
        if cctld_key in cctld:
            return cctld[cctld_key]
        default_map = aliases.get("default_by_legacy_key", {}) or {}
        if raw.upper() in default_map:
            return default_map[raw.upper()]

    return raw.upper()


def _normalize_genre(genre: Optional[str]) -> Optional[str]:
    if not genre:
        return None
    g = str(genre).strip().lower().replace(" ", "_")
    return g or None


def _select_fallback_template(genre: Optional[str]) -> str:
    report_gen = _load_report_generation()
    genre_profiles = report_gen.get("genre_profiles", {}) if isinstance(report_gen, dict) else {}
    genre_norm = _normalize_genre(genre)
    if genre_norm and genre_norm in genre_profiles:
        return GENRE_TEMPLATE_MAP.get(genre_norm, genre_norm)
    return GENRE_TEMPLATE_MAP.get("due_diligence", "due_diligence")


@dataclass
class ProfileSelection:
    profile_id: str
    template_id: str
    source: str
    confidence: float = 0.0
    label: Optional[str] = None
    jurisdiction: Optional[str] = None
    genre: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> Dict[str, Any]:
        meta = {
            "profile_id": self.profile_id,
            "template_id": self.template_id,
            "profile_source": self.source,
            "profile_confidence": self.confidence,
            "profile_jurisdiction": self.jurisdiction,
            "profile_genre": self.genre,
        }
        if self.label:
            meta["profile_label"] = self.label
        return meta


async def select_profile_template(
    tasking: str,
    genre: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    min_confidence: float = 0.25,
    python_api_url: Optional[str] = None,
) -> ProfileSelection:
    """
    Select the best profile/template for an investigation.

    Uses the semantic suggestion API if available; otherwise falls back to
    report library genre mapping.
    """
    genre_norm = _normalize_genre(genre)
    jurisdiction_norm = normalize_jurisdiction(jurisdiction)
    fallback_template = _select_fallback_template(genre_norm)

    if AIOHTTP_AVAILABLE and tasking and tasking.strip():
        base = python_api_url or os.getenv("PYTHON_API_URL") or os.getenv("PYTHON_BACKEND_URL") or "http://localhost:8000"
        base = base.rstrip("/")
        if base.endswith("/api"):
            url = f"{base}/matrix/semantic/suggest-investigation"
        else:
            url = f"{base}/api/matrix/semantic/suggest-investigation"

        payload = {
            "scenario": f"{genre_norm or 'investigation'}: {tasking}",
            "jurisdiction": jurisdiction_norm,
            "limit": 3,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    if resp.status < 400:
                        data = await resp.json()
                        matched = data.get("matched_template") or {}
                        confidence = float(matched.get("confidence") or 0.0)
                        template_id = matched.get("id") or ""
                        if template_id and confidence >= min_confidence:
                            return ProfileSelection(
                                profile_id=template_id,
                                template_id=template_id,
                                source="semantic",
                                confidence=confidence,
                                label=matched.get("name"),
                                jurisdiction=jurisdiction_norm,
                                genre=genre_norm,
                                details={"candidates": data.get("all_matching_templates", [])[:3]},
                            )
        except Exception as exc:
            logger.debug(f"Semantic template selection failed: {exc}")

    # Fallback to genre-based profile
    return ProfileSelection(
        profile_id=fallback_template,
        template_id=fallback_template,
        source="genre" if genre_norm else "fallback",
        confidence=0.0,
        jurisdiction=jurisdiction_norm,
        genre=genre_norm,
    )
