#!/usr/bin/env python3
"""
SASTRE Budget Enforcer (Artificial Scarcity)
===========================================
Deterministically limits *keyword* specificity to avoid over-filtering and
reduce "lazy" query stuffing.

This module does NOT change operator syntax; it only selects which *keyword
terms* are included inside query strings produced by the query compiler.

Core idea:
- A hard budget forces a "knapsack-like" selection among candidate terms.
- Anchor must always be included.
- Structural constraints like `site:` / `filetype:` / parentheses groups are
  treated as filters and are not part of the keyword budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by",
    "with", "from", "as", "is", "are", "was", "were",
}

# Lightweight "vanity tax" list; can be expanded / made data-driven later.
_HIGH_NOISE_FIRSTNAMES = {
    "elon", "donald", "barack", "taylor", "kim", "kanye", "rihanna", "madonna",
}


def _strip_quotes(term: str) -> str:
    t = term.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        return t[1:-1].strip()
    return t


def _is_filter_token(term: str) -> bool:
    """Tokens that are structural filters, not keyword terms."""
    t = term.strip()
    return (
        t.startswith("site:")
        or t.startswith("filetype:")
        or t.startswith("inurl:")
        or t.startswith("intitle:")
        or t.startswith("##")
        # Parentheses are ambiguous: they can be keyword groups or filter groups.
        # Treat as filters only when they contain explicit filter syntax.
        or ("site:" in t or "filetype:" in t or "inurl:" in t or "intitle:" in t)
    )


def _looks_like_year(term: str) -> bool:
    t = _strip_quotes(term)
    return t.isdigit() and len(t) == 4 and t.startswith(("18", "19", "20"))


def _looks_like_identifier(term: str) -> bool:
    t = _strip_quotes(term)
    # Heuristic: contains digits and letters, or long digit sequences
    has_alpha = any(c.isalpha() for c in t)
    has_digit = any(c.isdigit() for c in t)
    long_digits = sum(c.isdigit() for c in t) >= 8
    return (has_alpha and has_digit) or long_digits


@dataclass(frozen=True)
class TokenCandidate:
    """
    term: as it should appear in the query (may include quotes)
    kind: optional hint from the caller (anchor/associate/company/industry/role/etc.)
    """
    term: str
    kind: str = "generic"


class QueryEconomist:
    """
    Selects the best subset of keyword terms under a hard budget.
    """

    def __init__(self, default_budget: int = 3):
        self.default_budget = max(1, int(default_budget))

    def recommended_budget(self, anchor_strength: int) -> int:
        """
        Dynamic budget by anchor strength:
        - Strong anchor (4-5): can stay lean
        - Weak anchor (1-2): needs extra context to avoid noise
        """
        if anchor_strength >= 5:
            return 2
        if anchor_strength == 4:
            return 3
        if anchor_strength == 3:
            return 3
        if anchor_strength == 2:
            return 4
        return 5

    def appraise(self, cand: TokenCandidate, *, anchor_term: str) -> int:
        """
        Assign deterministic ROI to a term.
        Higher is better; negative means "toxic asset".
        """
        raw = _strip_quotes(cand.term).lower()
        anchor_raw = _strip_quotes(anchor_term).lower()

        # Never treat structural tokens as part of this; caller should separate.
        if _is_filter_token(cand.term):
            return 0

        # Always keep the anchor (caller also enforces hard include)
        if raw == anchor_raw:
            return 60

        # Hard identifiers / years are high ROI (contextual discriminators)
        if _looks_like_identifier(cand.term):
            return 80
        if _looks_like_year(cand.term):
            return 55

        # Role/industry/company/associate hints
        kind = (cand.kind or "generic").lower()
        if kind in {"technical_target", "needle"}:
            return 90
        if kind in {"associate", "company"}:
            return 70
        if kind in {"role", "industry", "disambiguator"}:
            return 50
        if kind in {"where", "location"}:
            return 45

        # Vanity tax: famous first names often add noise; penalize only when
        # we already have a stronger anchor (surname/company core).
        if raw in _HIGH_NOISE_FIRSTNAMES and raw != anchor_raw:
            return -10

        # Generic penalties
        if raw in _STOPWORDS:
            return -5
        if len(raw) <= 2:
            return -2

        # Default
        return 10

    def optimize_keywords(
        self,
        candidates: Iterable[TokenCandidate],
        *,
        budget: Optional[int] = None,
        anchor_term: str,
    ) -> Tuple[List[str], List[Tuple[str, int]]]:
        """
        Returns:
          (chosen_terms, scored_ledger)
        """
        b = self.default_budget if budget is None else max(1, int(budget))

        # De-dup while preserving original order
        seen = set()
        deduped: List[TokenCandidate] = []
        for c in candidates:
            key = c.term.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(c)

        scored: List[Tuple[TokenCandidate, int, int]] = []
        for idx, c in enumerate(deduped):
            v = self.appraise(c, anchor_term=anchor_term)
            scored.append((c, v, idx))

        # Anchor must be included if present among candidates
        anchor_raw = _strip_quotes(anchor_term).lower()
        chosen: List[str] = []
        if anchor_term:
            chosen.append(anchor_term)

        # Sort remaining by score desc, tie-break by original order
        scored_sorted = sorted(scored, key=lambda x: (x[1], -x[2]), reverse=True)
        ledger = [(c.term, v) for (c, v, _idx) in scored_sorted]

        for c, v, _idx in scored_sorted:
            if len(chosen) >= b:
                break
            # Skip anchor duplicate
            if _strip_quotes(c.term).lower() == anchor_raw:
                continue
            # Skip toxic terms
            if v < 0:
                continue
            chosen.append(c.term)

        # Final dedup in case anchor duplicates slipped in
        out_seen = set()
        out: List[str] = []
        for t in chosen:
            k = t.strip()
            if k and k not in out_seen:
                out_seen.add(k)
                out.append(k)

        return out, ledger

    def compose_and_query(
        self,
        candidates: Iterable[TokenCandidate],
        *,
        budget: Optional[int] = None,
        anchor_term: str,
    ) -> Tuple[str, List[Tuple[str, int]]]:
        chosen, ledger = self.optimize_keywords(
            candidates, budget=budget, anchor_term=anchor_term
        )
        return " AND ".join(chosen), ledger

