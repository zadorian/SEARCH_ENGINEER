"""
Operator Policy (V4.2) — Motor-Enforced Operator Families
=========================================================

Intent is not advisory. It constrains what operators may be executed.

This module enforces a strict operator family allowlist keyed by motor intent:
  - ENRICH_*  => verification / deterministic enrichment families
  - DISCOVER_* => discovery families (TRACE / EXTRACT / NET)

No probability framing. Outputs are binary rewrites with reason codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .contracts import Intent


IO_PREFIXES = ("p:", "c:", "e:", "d:", "t:")

# “Operator” tokens that show up as the first token in a query string.
DISCOVERY_OPS_LOCATION = {"bl?", "ol?"}
DISCOVERY_OPS_SUBJECT = {"ent?", "p?", "c?", "e?"}
VERIFY_OPS = {"=?"}  # identity/verification primitive
SEARCH_SCOPERS = {"site:", "filetype:"}  # treated as enrich-friendly precision operators


@dataclass(frozen=True)
class OperatorPolicyResult:
    primary_query: str
    variation_queries: List
    reasons: List[str]


def _first_token(query: str) -> str:
    return (query or "").strip().split(maxsplit=1)[0].strip().lower()


def _is_io_prefix(token: str) -> bool:
    token = (token or "").strip().lower()
    return any(token.startswith(p) for p in IO_PREFIXES)


def _is_scoper(token: str) -> bool:
    return token in SEARCH_SCOPERS


def _is_operator_token(token: str) -> bool:
    if not token:
        return False
    if token in VERIFY_OPS:
        return True
    if token in DISCOVERY_OPS_LOCATION or token in DISCOVERY_OPS_SUBJECT:
        return True
    if _is_io_prefix(token):
        return True
    if _is_scoper(token):
        return True
    return False


def _swap_leading_operator(query: str, new_op: str) -> Optional[str]:
    """
    Swap the leading operator token while keeping the rest of the query intact.
    Supports forms:
      - "op rest..."
      - "op: rest..." (io prefixes)
    """
    q = (query or "").strip()
    if not q:
        return None
    parts = q.split(maxsplit=1)
    if not parts:
        return None
    if len(parts) == 1:
        return new_op
    return f"{new_op} {parts[1]}"


def enforce_operator_families(
    *,
    primary_query: str,
    variation_queries: List,
    intent: Intent,
    subject_name: Optional[str] = None,
    subject_type: Optional[str] = None,  # "person" | "company" | etc
    location_target: Optional[str] = None,
) -> OperatorPolicyResult:
    """
    Enforce operator family policy for a given motor intent.

    Strategy:
      - If query is in allowed family: keep.
      - If query is in the wrong discovery family: swap operator (bl? <-> ent?).
      - If query is discovery but intent is ENRICH: rewrite to IO prefix when possible.
      - If we can't rewrite safely: strip operator to plain search (last resort).
    """
    reasons: List[str] = []

    def _enforce_one(q: str) -> str:
        qq = (q or "").strip()
        if not qq:
            return ""
        tok = _first_token(qq)

        # No explicit operator: allow as-is (plain search), but annotate if it violates enrich.
        if not _is_operator_token(tok):
            if intent in (Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION):
                reasons.append("OP_POLICY:PLAIN_SEARCH_UNDER_ENRICH")
            return qq

        # ENRICH intents: allow IO prefixes, verify ops, and precision scopers.
        if intent in (Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION):
            if _is_io_prefix(tok) or tok in VERIFY_OPS or _is_scoper(tok):
                return qq

            # Rewrite discovery operators into deterministic IO prefixes when possible.
            if intent == Intent.ENRICH_SUBJECT and subject_name:
                prefix = "c:" if (subject_type or "").lower() == "company" else "p:"
                reasons.append(f"OP_POLICY:REWRITE {tok}->{prefix.strip()}")
                return f"{prefix} {subject_name}".strip()

            if intent == Intent.ENRICH_LOCATION and location_target:
                # Prefer domain intel prefix for enrich-location when we have a domain-ish target.
                reasons.append(f"OP_POLICY:REWRITE {tok}->d:")
                return f"d: {location_target}".strip()

            # Last resort: strip operator token and fall back to plain search.
            reasons.append(f"OP_POLICY:STRIP_OPERATOR {tok}")
            parts = qq.split(maxsplit=1)
            return parts[1] if len(parts) > 1 else ""

        # DISCOVER intents: enforce correct discovery family.
        if intent == Intent.DISCOVER_LOCATION:
            # Allowed: location discovery operators + plain search
            if tok in DISCOVERY_OPS_LOCATION:
                return qq
            if tok in DISCOVERY_OPS_SUBJECT:
                rewritten = _swap_leading_operator(qq, "bl?")
                reasons.append(f"OP_POLICY:REWRITE {tok}->bl?")
                return rewritten or qq
            if _is_io_prefix(tok):
                # IO prefix is enrichment; strip to plain search under discover.
                reasons.append(f"OP_POLICY:STRIP_IO_PREFIX {tok}")
                parts = qq.split(maxsplit=1)
                return parts[1] if len(parts) > 1 else ""
            # verify op under discover: allow (it may be needed), but note.
            if tok in VERIFY_OPS:
                reasons.append("OP_POLICY:VERIFY_UNDER_DISCOVER")
                return qq
            return qq

        if intent == Intent.DISCOVER_SUBJECT:
            if tok in DISCOVERY_OPS_SUBJECT:
                return qq
            if tok in DISCOVERY_OPS_LOCATION:
                rewritten = _swap_leading_operator(qq, "ent?")
                reasons.append(f"OP_POLICY:REWRITE {tok}->ent?")
                return rewritten or qq
            if _is_io_prefix(tok):
                reasons.append(f"OP_POLICY:STRIP_IO_PREFIX {tok}")
                parts = qq.split(maxsplit=1)
                return parts[1] if len(parts) > 1 else ""
            if tok in VERIFY_OPS:
                reasons.append("OP_POLICY:VERIFY_UNDER_DISCOVER")
                return qq
            return qq

        # Default: return unchanged.
        return qq

    primary_out = _enforce_one(primary_query)

    # Normalize variations: accept either list[str] or list[dict{query,...}]
    variations_out: List = []
    for v in variation_queries or []:
        if isinstance(v, str):
            vv = _enforce_one(v)
            if vv:
                variations_out.append(vv)
        elif isinstance(v, dict):
            q = v.get("query")
            vv = _enforce_one(q) if isinstance(q, str) else ""
            if vv:
                v2 = dict(v)
                v2["query"] = vv
                variations_out.append(v2)
        else:
            continue

    return OperatorPolicyResult(
        primary_query=primary_out,
        variation_queries=variations_out,
        reasons=reasons,
    )


