#!/usr/bin/env python3
"""
Engine capabilities/availability registry.

Loads an optional JSON file listing engine codes to include/exclude and
capabilities like regions, modalities, or rate-limit status.

If no file is present, returns pass-through (no filtering).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

CAPABILITIES_FILENAMES = [
    'engine_capabilities.json',
    'engine_capabilities.local.json',
]

_CACHE: Optional[Dict] = None


def _load_capabilities() -> Optional[Dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    router_dir = Path(__file__).parent
    for fname in CAPABILITIES_FILENAMES:
        path = router_dir / fname
        if path.exists():
            try:
                with open(path, 'r') as f:
                    _CACHE = json.load(f)
                    return _CACHE
            except Exception:
                # If malformed, ignore and fall through to default
                pass
    _CACHE = None
    return _CACHE


def filter_engine_codes(
    engine_codes: List[str],
    operator_type: str,
    level: str,
    region: Optional[str] = None,
    modality: Optional[str] = None,
) -> List[str]:
    """
    Filter engine codes based on optional capabilities JSON.

    JSON format (examples):
    {
      "include": ["GO", "BI", "BR", "YT"],
      "exclude": ["YA"],
      "per_operator": {"image_search": {"exclude": ["GO"]}},
      "per_level": {"L3": {"exclude": ["EX"]}},
      "metadata": {"BR": {"region": ["US","EU"], "modalities": ["web"]}}
    }
    """
    caps = _load_capabilities()
    if not caps:
        return engine_codes

    include: Set[str] = set(caps.get('include', []) or [])
    exclude: Set[str] = set(caps.get('exclude', []) or [])

    # Operator-specific overrides
    per_op = (caps.get('per_operator', {}) or {}).get(operator_type, {})
    include |= set(per_op.get('include', []) or [])
    exclude |= set(per_op.get('exclude', []) or [])

    # Level-specific overrides
    per_lvl = (caps.get('per_level', {}) or {}).get(level, {})
    include |= set(per_lvl.get('include', []) or [])
    exclude |= set(per_lvl.get('exclude', []) or [])

    filtered = []
    for code in engine_codes:
        if include and code not in include:
            continue
        if code in exclude:
            continue

        # Optional metadata checks (region/modality)
        meta = (caps.get('metadata', {}) or {}).get(code, {})
        if region:
            allowed_regions = meta.get('region')
            if isinstance(allowed_regions, list) and allowed_regions:
                if region not in allowed_regions:
                    continue
        if modality:
            allowed_modalities = meta.get('modalities')
            if isinstance(allowed_modalities, list) and allowed_modalities:
                if modality not in allowed_modalities:
                    continue

        filtered.append(code)

    return filtered


__all__ = [
    'filter_engine_codes',
]


