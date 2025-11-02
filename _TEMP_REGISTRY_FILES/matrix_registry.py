#!/usr/bin/env python3
from __future__ import annotations

"""
Unified engine matrix (single source of truth).

ONE list encodes everything: families (SUBJECT, OBJECT, LOCATION),
LOCATION coordinate dimensions, and per‑search‑type L1/L2/L3 engines.

Routing consumes a flattened DEFAULT_MATRIX derived from UNIFIED_MATRIX,
optionally merged with external JSONs for legacy extension. Do not author
any other matrix structures elsewhere.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


# =========================
# UNIFIED (authoritative)
# =========================

UNIFIED_MATRIX: Dict[str, Any] = {
  "SUBJECT": {
    "person":    {"L1": ["SS","LI","EX","GO","PX","FC"], "L2": ["BR","DD","YA","PX","FC"], "L3": ["AR","W","PX","FC"]},
    "company":   {"L1": ["LI","EX","GO","PX","FC"],      "L2": ["BR","DD","YA","PX","FC"], "L3": ["AR","W","PX","FC"]},
    "username":  {"L1": ["YTU","SS","LI","XT","PX","FC"],"L2": ["YT","EX","GO","PX","FC"], "L3": ["GO","BI","BR","PX","FC"]},
    "isbn":      {"L1": ["OL","GU","AR","AA","LG"], "L2": ["GO","BI","BR","DD"], "L3": ["AO"]}
  },
  "TOPICAL": {
    "about": {
      "L1": ["GO","BI","BR","DD","YA","QW","ST","MJ","SO","SZ","YH","AR","PX","FC"],
      "L2": ["GO","BI","BR","DD","YA","QW","YEP","MJ","AR","PX","FC"],
      "L3": ["GO","BI","BR","DD","YA","NV","SZ","SGO","AR","PX","FC"]
    }
  },
  "OBJECT": {
    # Exact phrase search - engines with strong "quoted phrase" support
    "exact_phrase": {"L1": ["BS","GO","BI","DD","YA","YC","BR","AR","PX","FC"], "L2": ["QW","ST","PX","FC"], "L3": ["EX","AO","PX","FC"]},
    # Native numeric proximity at L1 (Google AROUND, Bing NEAR, Archive "\"…\"~N")
    # Creative overlap at L2 (Yandex sentence‑level, Brave, DD) + strict post‑filter
    "proximity": {"L1": ["GO","BI","YC","AR","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","AR","PX","FC"], "L3": ["GO","BI","BR","DD","YA","YC","AR","PX","FC"]},
    "not_search": {"L1": ["GO","BI","BR","DD","YA","YC","MJ","SO","SZ","YH","PX","FC"], "L2": ["QW","ST","EX","PX","FC"], "L3": ["AO","PX","FC"]},
    "or_search":  {"L1": ["GO","BI","BR","DD","YA","YC","PX","FC"], "L2": ["QW","ST","EX","PX","FC"], "L3": ["AO","PX","FC"]},
    "handshake":  {"L1": ["GO","BI"], "L2": ["GO","BI","BR","DD"], "L3": ["YA","AR"]},
    "wildcards":  {"L1": ["GO","BI","YA"], "L2": ["DD","BR"], "L3": ["QW"]}
  },
  "LOCATION": {
    # Temporal (time)
    "temporal": {
      "date":  {"L1": ["GO","BI","BR","YA","YC","MJ","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","EX","GD","PX","FC"], "L3": ["GO","BI","BR","DD","YA","YC","AO","W","PX","FC"]},
      "event": {"L1": ["GO","BI","BR","DD","PX","FC"], "L2": ["QW","ST","PX","FC"], "L3": ["YA","AO","PX","FC"]}
    },
    # Geographical (jurisdiction/TLD)
    "geographical": {
      "site":    {"L1": ["GO","BI","BR","DD","YA","YC","BA","QW","EX","AR","MJ","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","EX","YEP","ME","PX","FC"],
                   "L3": ["GO","BI","BR","DD","YA","YC","BA","QW","EX","NV","SZ","SGO","GR","W","PX","FC"]},
      "address": {"L1": ["GO","BI","BR","DD","YA","PX","FC"], "L2": ["YA","QW","PX","FC"], "L3": ["AO","PX","FC"]}
    },
    # Linguistic (language)
    "linguistic": {
      "language":    {"L1": ["GO","BI","QW","ST","YA","YC","DD","BR","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","QW","PX","FC"],
                       "L3": ["GO","BI","BR","DD","YA","YC","NV","SZ","SGO","AR","PX","FC"]}
    },
    # Textual (content fields)
    "textual": {
      "intitle": {"L1": ["GO","BI","YA","BR","BA","DD","MJ","SO","SZ","YH","AR","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YEP","PX","FC"],
                   "L3": ["GO","BI","BR","DD","YA","YC","NV","SZ","SGO","AR","PX","FC"]},
      "author":  {"L1": ["OL","GU","AR","AA","LG","CR","PM","AX","YC","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","PX","FC"], "L3": ["AO","PX","FC"]},
      "anchor":  {"L1": ["GO","BI","YA","MJ","YH","PX","FC"], "L2": ["DD","BR","PW","PX","FC"], "L3": ["AO","PX","FC"]}
    },
    # Address (URL path/host)
    "address": {
      "inurl":  {"L1": ["GO","BI","BR","DD","YA","YC","BA","HFU","PW","MM","MJ","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","BR","DD","YA","YC","HFU","MM","PX","FC"],
                  "L3": ["GO","BI","BR","DD","YA","YC","NV","SZ","SGO","HFU","MM","PX","FC"]},
      "indom":  {"L1": ["GO","BI","DD","YA","PX","FC"], "L2": ["BR","PX","FC"], "L3": ["AO","PX","FC"]},
      "alldom": {"L1": ["HFU","MM","PW","QW","DD","PX","FC"], "L2": ["GO","BI","BR","YA","PX","FC"], "L3": ["AR","PX","FC"]}
    },
    # Format (file/media type)
    "format": {
      "filetype":     {"L1": ["GO","BI","BR","DD","YA","YC","BA","PW","ST","AR","EX","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","AR","PW","PX","FC"]},
      "pdf":          {"L1": ["GO","BI","BR","DD","YA","YC","BA","ST","AR","EX","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","AR","PW","PX","FC"]},
      "document":     {"L1": ["GO","BI","BR","DD","YA","YC","BA","ST","EX","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","PW","PX","FC"]},
      "spreadsheet":  {"L1": ["GO","BI","BR","DD","YA","YC","BA","ST","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","PW","PX","FC"]},
      "presentation": {"L1": ["GO","BI","BR","DD","YA","YC","BA","ST","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","PW","PX","FC"]},
      "text":         {"L1": ["GO","BI","BR","DD","YA","YC","PW","ST","MJ","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","PW","PX","FC"]},
      "archive":      {"L1": ["GO","BI","BR","DD","YA","YC","AR","PW","ST","SO","SZ","YH","PX","FC"], "L2": ["GO","BI","ST","QW","MJ","ME","DP","PX","FC"], "L3": ["BR","DD","AR","PW","PX","FC"]},
      "image":        {"L1": ["DDI","BRI","YA","PX","FC"], "L2": ["EX","AO","PX","FC"], "L3": ["GO","BI","BR","PX","FC"]},
      "audio":        {"L1": ["GO","BI","DD","YA","AR","YT","BS","PX","FC"], "L2": ["BR","AO","SS","RD","PX","FC"], "L3": ["EX","PX","FC"]},
      "media":        {"L1": ["GO","BI","DD","YA","AR","YT","PX","FC"], "L2": ["BR","EX","BS","SS","PX","FC"], "L3": ["AO","RD","PX","FC"]},
      "torrent":      {"L1": ["GO","BI","DD","YA","BS"], "L2": ["QW","ST","PW"], "L3": ["BR"]}
    },
    # Category (source type)
    "category": {
      "news":          {"L1": ["EX","QW","ST","BS","NA","GD","AR","PX","FC"], "L2": ["GO","BI","BR","DD","EX","AO","PX","FC"], "L3": ["GO","BI","BR","DD","W","PX","FC"]},
      "academic":      {"L1": ["OA","CR","SE","PM","AX","NT","JS","MU","SG","WP","EX","PX","FC"], "L2": ["GO","BI","ST","QW","PX","FC"], "L3": ["BR","DD","AR","PX","FC"]},
      "medical":       {"L1": ["PM","SE"], "L2": ["GO","BI","BR","DD"], "L3": ["YA","AO"]},
      "edu":           {"L1": ["GO","BI","BR","DD"], "L2": ["YA","SE"], "L3": ["AO","AR"]},
      "product":       {"L1": ["GO","BI","BR","DD"], "L2": ["YA","QW"], "L3": ["ST","AO"]},
      "code":          {"L1": ["GO","BI","BR","DD","YA"], "L2": ["GO","BI","BR","DD","YA","QW"], "L3": ["AR","PW"]},
      "forum":         {"L1": ["SS","RD","GR","BR"], "L2": ["GO","BI","DD","QW","ST"], "L3": ["YA"]},
      "blog":          {"L1": ["GO","BI","BR","DD"], "L2": ["QW","ST","YA"], "L3": ["AO"]},
      "social":        {"L1": ["SS","YT","YTU","RD","FB","XT"], "L2": ["EX","GO"], "L3": ["BR","DD"]},
      "recruitment":   {"L1": ["GO","BI","BR","DD","YA"], "L2": ["ST","QW"], "L3": ["AO"]},
      "financial":     {"L1": ["GO","BI","BR","DD","AR"], "L2": ["YA","ST"], "L3": ["AO"]},
      "patents":       {"L1": ["GO","BI","BR","DD","AR"], "L2": ["YA","EX"], "L3": ["AO"]},
      "review":        {"L1": ["GO","BI","BR","DD"], "L2": ["YA","QW"], "L3": ["ST","AO"]},
      "sales_leads":  {"L1": ["GO","BI","BR","DD"], "L2": ["YA","QW"], "L3": ["ST","AO"]},
      "scientific":   {"L1": ["GO","BI","BR","DD","AR"], "L2": ["YA","EX"], "L3": ["ST"]},
      "social_media": {"L1": ["SS","YT","YTU","RD","GR"], "L2": ["GO","BI","BR","DD"], "L3": ["YA","ST"]},
      "media":        {"L1": ["YT","YTU","BR","AR"], "L2": ["GO","BI","BR","DD"], "L3": ["YA","ST"]},
      "platforms":    {"L1": ["GO","BI","BR","DD"], "L2": ["YA","QW"], "L3": ["ST","AO"]},
      "tor":          {"L1": ["GO","BI","BR","DD","YC"], "L2": ["YA","YC","QW"], "L3": ["ST","AO"]},
      "dataset":       {"L1": ["GO","BI","DD","AR","PX","FC"], "L2": ["PX","FC"], "L3": ["BR","YA","PX","FC"]},
      "book":          {"L1": ["AA","LG","GU","OL","AR","GO"], "L2": ["AA","LG","GU","OL","AO","BI","YA"], "L3": ["BR","DD","BA","EX"]},
      "public_records": {"L1": ["GO","BI","BR","DD","AR"], "L2": ["YA","ST"], "L3": ["AO"]},
      "legal":         {"L1": ["GO","BI","BR","DD","AR"], "L2": ["YA","ST"], "L3": ["AO"]}
    }
  }
}


# ==================================
# Flatten for routing (legacy calls)
# ==================================

DEFAULT_MATRIX: Dict[str, Dict[str, List[str]]] = {}
for fam, section in UNIFIED_MATRIX.items():
  if fam == "LOCATION":
    for dim, types in section.items():
      for st, lv in types.items():
        DEFAULT_MATRIX[st] = lv
  else:
    for st, lv in section.items():
      DEFAULT_MATRIX[st] = lv


# =============================
# Loader / accessors (unchanged)
# =============================

def _merge_matrices(target: Dict, source: Dict) -> Dict:
    """Merge two matrices: union engine codes, preserving appearance order."""
    for search_type, levels in source.items():
        if not isinstance(levels, dict):
            continue
        dst_levels = target.setdefault(search_type, {})
        for level_key, engines in levels.items():
            if not isinstance(engines, list):
                continue
            existing = dst_levels.setdefault(level_key, [])
            for code in engines:
                if code not in existing:
                    existing.append(code)
    return target


def _load_json(path: Path) -> Dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_engine_matrix() -> Dict[str, Dict[str, List[str]]]:
    """Return flattened matrix merged with optional external JSONs."""
    router_root = Path(__file__).resolve().parent
    candidates: List[Path] = [
        router_root / "search_routing_system" / "engine_to_search_type_matrix.json",
        router_root / "engine_to_search_type_matrix_SE1.json",
        router_root / "search_routing_system" / "engine_to_search_type_matrix_external.json",
    ]
    merged: Dict[str, Dict[str, List[str]]] = {}
    _merge_matrices(merged, DEFAULT_MATRIX)
    for p in candidates:
        if p.exists():
            data = _load_json(p)
            if data:
                _merge_matrices(merged, data)
    return merged


_MATRIX_CACHE: Dict[str, Dict[str, List[str]]] | None = None


def get_engines(search_type: str, level: str = "L1") -> List[str]:
    """Get engine codes for a search type and level from the merged matrix."""
    global _MATRIX_CACHE
    if _MATRIX_CACHE is None:
        _MATRIX_CACHE = load_engine_matrix()
    st = search_type.lower().strip()
    if st == "title":
        st = "intitle"
    levels = _MATRIX_CACHE.get(st)
    if not levels:
        return []
    return list(levels.get(level.upper(), []))


__all__ = ["UNIFIED_MATRIX", "load_engine_matrix", "get_engines", "DEFAULT_MATRIX"]
