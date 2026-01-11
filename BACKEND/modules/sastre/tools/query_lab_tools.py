"""
Query Lab tools - expose Match + Test + Fuse for agents.
"""

from typing import Dict, Any, List, Optional

from ..contracts import Intent, KUQuadrant
from ..query.lab import QueryLab, QueryLabInput


def _parse_intent(value: Optional[str]) -> Intent:
    if not value:
        return Intent.DISCOVER_SUBJECT
    value = value.strip().lower()
    for intent in Intent:
        if intent.value == value:
            return intent
    return Intent.DISCOVER_SUBJECT


def _parse_quadrant(value: Optional[str]) -> KUQuadrant:
    if not value:
        return KUQuadrant.DISCOVER
    value = value.strip().lower()
    for quadrant in KUQuadrant:
        if quadrant.value == value:
            return quadrant
    return KUQuadrant.DISCOVER


def build_fused_query_handler(
    intent: str = "",
    ku_quadrant: str = "",
    subject_name: str = "",
    subject_type: str = "",
    subject_attribute: str = "",
    location_domain: str = "",
    location_jurisdiction: str = "",
    location_source_type: str = "",
    expected_terms: Optional[List[str]] = None,
    narrative_question: str = "",
) -> Dict[str, Any]:
    """
    Build a fused query using Query Lab.
    """
    lab = QueryLab()
    request = QueryLabInput(
        intent=_parse_intent(intent),
        ku_quadrant=_parse_quadrant(ku_quadrant),
        subject_name=subject_name or None,
        subject_type=subject_type or None,
        subject_attribute=subject_attribute or None,
        location_domain=location_domain or None,
        location_jurisdiction=location_jurisdiction or None,
        location_source_type=location_source_type or None,
        expected_terms=expected_terms or [],
        narrative_question=narrative_question or None,
    )
    result = lab.construct(request)
    return {
        "primary_query": result.primary_query,
        "variation_queries": result.variation_queries,
        "intent": result.intent.value,
        "ku_quadrant": result.ku_quadrant.value,
        "operators": result.operators,
        "notes": result.notes,
    }
