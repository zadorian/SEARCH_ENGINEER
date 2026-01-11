"""
SASTRE Sufficiency Checker - Determines when investigation is complete.

Checks:
1. Narrative coverage (questions answered)
2. Entity completeness (Core/Shell filled)
3. Source exhaustion (reasonable sources checked)
4. Disambiguation resolution (collisions resolved)
5. Nexus confirmation (key connections verified)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum

from .state import (
    InvestigationState,
    NarrativeState,
    SourceState,
    Priority,
)
from .schema import check_completeness


# =============================================================================
# SUFFICIENCY RESULT
# =============================================================================

@dataclass
class SufficiencyResult:
    """Result of sufficiency check."""
    is_sufficient: bool
    overall_score: float
    component_scores: Dict[str, float]
    blocking_issues: List[str]
    recommendations: List[str] = field(default_factory=list)

    # Detailed breakdown
    narrative_answered: int = 0
    narrative_total: int = 0
    entities_complete: int = 0
    entities_total: int = 0
    sources_checked: int = 0
    sources_total: int = 0
    collisions_pending: int = 0
    connections_confirmed: int = 0
    connections_total: int = 0


# =============================================================================
# SUFFICIENCY CHECKER
# =============================================================================

class SufficiencyChecker:
    """
    Determines when an investigation is "sufficient" to answer the question.

    Thresholds are configurable but defaults are:
    - Narrative: 75% questions answered
    - Entity: 80% have Core complete, 50% have Shell
    - Source: 60% checked
    - Disambiguation: 100% resolved (blocking)
    - Nexus: 50% connections confirmed
    """

    def __init__(
        self,
        narrative_threshold: float = 0.75,
        entity_threshold: float = 0.80,
        source_threshold: float = 0.60,
        disambiguation_threshold: float = 1.0,
        nexus_threshold: float = 0.50,
        overall_threshold: float = 0.75,
    ):
        self.narrative_threshold = narrative_threshold
        self.entity_threshold = entity_threshold
        self.source_threshold = source_threshold
        self.disambiguation_threshold = disambiguation_threshold
        self.nexus_threshold = nexus_threshold
        self.overall_threshold = overall_threshold

        # Weights for overall score
        self.weights = {
            'narrative': 0.35,
            'entity': 0.25,
            'source': 0.15,
            'disambiguation': 0.15,
            'nexus': 0.10,
        }

    def check(self, state: InvestigationState) -> SufficiencyResult:
        """Run full sufficiency check."""
        scores = {}
        blocking_issues = []
        recommendations = []

        # 1. NARRATIVE COVERAGE
        narrative_score, n_answered, n_total = self._check_narrative(state)
        scores['narrative'] = narrative_score

        if narrative_score < self.narrative_threshold:
            unanswered = [
                n for n in state.narrative_items.values()
                if n.state == NarrativeState.UNANSWERED
            ]
            blocking_issues.append(
                f"{len(unanswered)} narrative questions unanswered"
            )
            for n in unanswered[:3]:
                recommendations.append(f"Run queries for: {n.question[:50]}...")

        # 2. ENTITY COMPLETENESS
        entity_score, e_complete, e_total = self._check_entities(state)
        scores['entity'] = entity_score

        if entity_score < self.entity_threshold:
            incomplete = [
                e for e in state.entities.values()
                if not e.core_complete
            ]
            if incomplete:
                recommendations.append(
                    f"Complete core attributes for {len(incomplete)} entities"
                )

        # 3. SOURCE EXHAUSTION
        source_score, s_checked, s_total = self._check_sources(state)
        scores['source'] = source_score

        if source_score < self.source_threshold:
            unchecked = [
                s for s in state.sources.values()
                if s.state == SourceState.UNCHECKED
            ]
            recommendations.append(
                f"Check {len(unchecked)} unchecked sources"
            )

        # 4. DISAMBIGUATION RESOLUTION
        disambiguation_score = self._check_disambiguation(state)
        scores['disambiguation'] = disambiguation_score

        if disambiguation_score < self.disambiguation_threshold:
            blocking_issues.append(
                f"{len(state.pending_collisions)} entity collisions unresolved"
            )
            recommendations.append("Resolve pending entity collisions before proceeding")

        # 5. NEXUS CONFIRMATION
        nexus_score, c_confirmed, c_total = self._check_nexus(state)
        scores['nexus'] = nexus_score

        if nexus_score < self.nexus_threshold and c_total > 0:
            unconfirmed = c_total - c_confirmed
            recommendations.append(
                f"Confirm {unconfirmed} unverified connections"
            )

        # CALCULATE OVERALL
        overall = sum(scores[k] * self.weights[k] for k in self.weights)

        # Disambiguation is blocking
        if disambiguation_score < 1.0:
            overall = min(overall, 0.5)  # Cap at 50% if collisions pending

        is_sufficient = overall >= self.overall_threshold and len(blocking_issues) == 0

        return SufficiencyResult(
            is_sufficient=is_sufficient,
            overall_score=overall,
            component_scores=scores,
            blocking_issues=blocking_issues,
            recommendations=recommendations,
            narrative_answered=n_answered,
            narrative_total=n_total,
            entities_complete=e_complete,
            entities_total=e_total,
            sources_checked=s_checked,
            sources_total=s_total,
            collisions_pending=len(state.pending_collisions),
            connections_confirmed=c_confirmed,
            connections_total=c_total,
        )

    def _check_narrative(self, state: InvestigationState) -> tuple:
        """Check narrative coverage."""
        items = list(state.narrative_items.values())
        if not items:
            return 1.0, 0, 0

        answered = sum(
            1 for n in items
            if n.state in [NarrativeState.ANSWERED, NarrativeState.PARKED]
        )
        partial = sum(1 for n in items if n.state == NarrativeState.PARTIAL)

        # Partial counts as 0.5
        score = (answered + partial * 0.5) / len(items)

        return score, answered, len(items)

    def _check_entities(self, state: InvestigationState) -> tuple:
        """Check entity completeness."""
        entities = list(state.entities.values())
        if not entities:
            return 1.0, 0, 0

        complete = 0
        for entity in entities:
            completeness = check_completeness(entity)
            if completeness['core_complete']:
                complete += 1

        score = complete / len(entities)

        return score, complete, len(entities)

    def _check_sources(self, state: InvestigationState) -> tuple:
        """Check source exhaustion."""
        sources = list(state.sources.values())
        if not sources:
            return 1.0, 0, 0

        checked = sum(
            1 for s in sources
            if s.state in [SourceState.CHECKED, SourceState.EMPTY]
        )

        score = checked / len(sources)

        return score, checked, len(sources)

    def _check_disambiguation(self, state: InvestigationState) -> float:
        """Check disambiguation resolution."""
        if not state.pending_collisions:
            return 1.0

        # Any pending collision means not fully resolved
        return 0.0

    def _check_nexus(self, state: InvestigationState) -> tuple:
        """Check connection confirmation."""
        edges = state.graph.edges
        if not edges:
            return 1.0, 0, 0

        confirmed = sum(1 for e in edges if e.confirmed)
        score = confirmed / len(edges)

        return score, confirmed, len(edges)


# =============================================================================
# QUICK SUFFICIENCY CHECK
# =============================================================================

def quick_sufficiency_check(state: InvestigationState) -> bool:
    """Quick check without full analysis."""
    # Check blocking conditions first
    if state.pending_collisions:
        return False

    # Check narrative progress
    items = list(state.narrative_items.values())
    if items:
        answered = sum(1 for n in items if n.state == NarrativeState.ANSWERED)
        if answered / len(items) < 0.5:
            return False

    return True
