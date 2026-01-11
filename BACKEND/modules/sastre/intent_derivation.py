"""
Intent Derivation Layer (V4.2) — THE MOTOR
=========================================

This module makes Intent explicit and binary.

Vision requirement:
    (Grid State + Narrative Context) => INTENT => ACTION

Key rule:
    Gap != Intent.
    - Gap coordinates describe WHAT is missing (sensor output).
    - Intent decides WHAT TO DO (motor output).

No probability framing:
    - This module does not output confidence/percentages.
    - It outputs binary intent + strategy + deterministic reason codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Literal

from .contracts import KUQuadrant, Intent, CognitiveMode
from .goal_context import GoalContext, tokenize_goal_requires


EngineChoice = Literal["profile", "grid"]
Tactic = Literal["spear", "trap", "net"]


@dataclass(frozen=True)
class IntentDecision:
    """
    The motor output.

    - intent: binary intent primitive (ENRICH/DISCOVER × SUBJECT/LOCATION)
    - quadrant: K-U quadrant (VERIFY/TRACE/EXTRACT/DISCOVER) — strategy family
    - tactic: spear/trap/net mapping (still binary; no probability)
    - engine: profile vs grid recommendation (may be overridden by executor constraints)
    - reasons: machine-readable reason codes explaining the decision
    """

    intent: Intent
    quadrant: KUQuadrant
    tactic: Tactic
    engine: EngineChoice
    reasons: List[str]


def derive_intent_decision_from_gap(gap) -> IntentDecision:
    """
    Deterministic intent derivation from a CognitiveGap.

    Uses only:
      - subject_known / location_known
      - discovered_by_mode (narrative/subject/location/nexus)
      - coordinates (subject attribute presence, location hints)
      - ku_quadrant if already computed (fallbacks to K-U boolean derivation)

    NOTE: Narrative context is currently represented by:
      - discovered_by_mode == NARRATIVE (story coherence gap)
      - coordinates.nexus / coordinates.subject.attribute (what the narrative is asking for)
    As richer narrative priority signals are added (goal/track weights),
    they should be fed here, not scattered across the orchestrator.
    """

    # Defensive reads (CognitiveGap is a dataclass in this repo, but keep robust).
    subject_known = bool(getattr(gap, "subject_known", False))
    location_known = bool(getattr(gap, "location_known", False))
    mode = getattr(gap, "discovered_by_mode", None)
    coords = getattr(gap, "coordinates", None)
    attr_missing = False
    if coords and getattr(coords, "subject", None):
        attr_missing = bool(getattr(coords.subject, "attribute", None))

    quadrant = getattr(gap, "ku_quadrant", None)
    if quadrant is None:
        if subject_known and location_known:
            quadrant = KUQuadrant.VERIFY
        elif subject_known and not location_known:
            quadrant = KUQuadrant.TRACE
        elif location_known and not subject_known:
            quadrant = KUQuadrant.EXTRACT
        else:
            quadrant = KUQuadrant.DISCOVER

    reasons: List[str] = [f"KU:{quadrant.value}"]
    if subject_known:
        reasons.append("SUBJECT:KNOWN")
    else:
        reasons.append("SUBJECT:UNKNOWN")
    if location_known:
        reasons.append("LOCATION:KNOWN")
    else:
        reasons.append("LOCATION:UNKNOWN")

    # Slot hunger proxy: attribute specified implies a shaped unknown inside a known container.
    if attr_missing:
        reasons.append("SLOT:HUNGRY")

    # Map to binary intent.
    # These are strict and deterministic; they can be extended, but not made probabilistic.
    if quadrant == KUQuadrant.VERIFY:
        # When both subject and location are known, default to ENRICH SUBJECT unless
        # the gap was discovered by LOCATION mode and there isn't a specific subject attribute.
        if mode == CognitiveMode.LOCATION and not attr_missing:
            intent = Intent.ENRICH_LOCATION
            reasons.append("MODE:LOCATION")
        else:
            intent = Intent.ENRICH_SUBJECT
            reasons.append(f"MODE:{getattr(mode, 'value', str(mode))}")
    elif quadrant == KUQuadrant.TRACE:
        intent = Intent.DISCOVER_LOCATION
    elif quadrant == KUQuadrant.EXTRACT:
        intent = Intent.DISCOVER_SUBJECT
    else:
        # Unknown/unknown frontier: DISCOVER is the only valid motor state.
        # Default to DISCOVER SUBJECT; NEXUS gaps may later route to network-wide NET tactics.
        intent = Intent.DISCOVER_SUBJECT

    # Tactic mapping (Spear/Trap/Net) — still binary, but expresses movement physics.
    if intent in (Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION):
        tactic: Tactic = "spear"
    else:
        # TRACE/EXTRACT/DISCOVER are discovery movements.
        tactic = "net"

    # Engine recommendation:
    # - ENRICH tends toward profile (predictable), but executor may override later.
    # - DISCOVER tends toward grid (exploration).
    engine: EngineChoice = "profile" if intent in (Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION) else "grid"

    return IntentDecision(
        intent=intent,
        quadrant=quadrant,
        tactic=tactic,
        engine=engine,
        reasons=reasons,
    )


def derive_intent_decision(
    gap,
    goal_contexts: Optional[List[GoalContext]] = None,
) -> IntentDecision:
    """
    Goal-aware motor derivation.

    Baseline: derive intent from K-U state + gap coordinates.
    Override (deterministic): if the gap clearly matches an explicit GOAL requirement,
    we bias the target axis and reasons to satisfy the goal.
    """
    base = derive_intent_decision_from_gap(gap)
    if not goal_contexts:
        return base

    # Collect explicit requirement tokens from all active goals.
    tokens: set[str] = set()
    goal_ids: List[str] = []
    for g in goal_contexts:
        tokens |= tokenize_goal_requires(g.requires)
        goal_ids.append(g.note_id)

    # Build a "gap text surface" for deterministic matching (no fuzzy scoring).
    parts: List[str] = []
    desc = getattr(gap, "description", None)
    if isinstance(desc, str) and desc.strip():
        parts.append(desc.lower())
    coords = getattr(gap, "coordinates", None)
    if coords and getattr(coords, "subject", None):
        attr = getattr(coords.subject, "attribute", None)
        if isinstance(attr, str) and attr.strip():
            parts.append(attr.lower())
        et = getattr(coords.subject, "entity_type", None)
        if isinstance(et, str) and et.strip():
            parts.append(et.lower())
    if coords and getattr(coords, "location", None):
        jur = getattr(coords.location, "jurisdiction", None)
        if isinstance(jur, str) and jur.strip():
            parts.append(jur.lower())
    expected_terms = None
    try:
        expected_terms = getattr(coords.nexus, "expected_terms", None) if coords else None
    except Exception:
        expected_terms = None
    if isinstance(expected_terms, list):
        parts.extend([str(t).lower() for t in expected_terms if t])

    surface = " ".join(parts)
    if not surface:
        return base

    # Deterministic requirement match: token substring present.
    matched = []
    for t in tokens:
        if t and t in surface:
            matched.append(t)

    if not matched:
        return base

    # Apply override rules based on matched requirement families.
    reasons = list(base.reasons)
    for gid in goal_ids[:3]:
        reasons.append(f"GOAL_NOTE:{gid}")
    reasons.append(f"GOAL_MATCH:{matched[0]}")

    # Families: location-like vs subject-like.
    location_like = {
        "jurisdiction",
        "country",
        "domain",
        "source",
        "sources",
        "terrain",
        "registry",
        "registries",
    }
    subject_like = {
        "ownership",
        "ubo",
        "beneficial_ownership",
        "beneficial ownership",
        "directors",
        "officers",
        "shareholders",
        "adverse_media",
        "sanctions",
    }

    # If any matched token suggests location, steer toward location target.
    if any(m in location_like for m in matched):
        if base.quadrant == KUQuadrant.VERIFY:
            return IntentDecision(
                intent=Intent.ENRICH_LOCATION,
                quadrant=base.quadrant,
                tactic="spear",
                engine="profile",
                reasons=reasons + ["GOAL_AXIS:LOCATION"],
            )
        return IntentDecision(
            intent=Intent.DISCOVER_LOCATION,
            quadrant=base.quadrant,
            tactic="net",
            engine="grid",
            reasons=reasons + ["GOAL_AXIS:LOCATION"],
        )

    # Otherwise if subject-like, steer toward subject target.
    if any(m in subject_like for m in matched):
        if base.quadrant == KUQuadrant.VERIFY:
            return IntentDecision(
                intent=Intent.ENRICH_SUBJECT,
                quadrant=base.quadrant,
                tactic="spear",
                engine="profile",
                reasons=reasons + ["GOAL_AXIS:SUBJECT"],
            )
        return IntentDecision(
            intent=Intent.DISCOVER_SUBJECT,
            quadrant=base.quadrant,
            tactic="net",
            engine="grid",
            reasons=reasons + ["GOAL_AXIS:SUBJECT"],
        )

    # Fallback: keep baseline intent but retain goal match reasons.
    return IntentDecision(
        intent=base.intent,
        quadrant=base.quadrant,
        tactic=base.tactic,
        engine=base.engine,
        reasons=reasons,
    )


