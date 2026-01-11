"""
SASTRE Surprising AND Detection

When two entities unexpectedly appear together, it may reveal something new.
E.g., Target company officer also appears in unrelated litigation.

The physics:
- Expected co-occurrence: Entities predicted by narrative (not surprising)
- Surprising AND: Entities NOT predicted, but found together
- Anti-correlation: Entities that SHOULD appear together but don't

Detection Process:
1. Build expected co-occurrence matrix from narrative
2. Compare against actual findings
3. Flag deviations as Surprising ANDs
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import hashlib
import uuid

from ..core.state import (
    InvestigationState,
    Entity,
    EntityType,
    NarrativeItem,
    SourceResult,
    SurprisingAnd,
    Edge,
)


# =============================================================================
# SURPRISING AND DATA
# =============================================================================

@dataclass
class ExpectedConnection:
    """A connection expected by narrative."""
    entity_a_type: EntityType
    entity_b_type: EntityType
    relationship: str
    narrative_id: str
    reason: str


@dataclass
class SurprisingAndCandidate:
    """A potential Surprising AND to evaluate."""
    entity_a: Entity
    entity_b: Entity
    source: SourceResult
    context: str
    surprise_score: float
    reasons: List[str] = field(default_factory=list)


# =============================================================================
# SURPRISING AND DETECTOR
# =============================================================================

class SurprisingAndDetector:
    """
    Detects unexpected entity co-occurrences.

    Two phases:
    1. Passive: Check if co-occurrence was predicted by narrative
    2. Active: Evaluate significance of surprise
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.expected_connections: List[ExpectedConnection] = []
        self._build_expectation_matrix()

    def _build_expectation_matrix(self):
        """
        Build matrix of expected co-occurrences from narrative.

        Uses narrative questions to infer what connections we expect:
        - "John Smith's corporate affiliations" → expect PERSON-COMPANY links
        - "Acme Corp's officers" → expect COMPANY-PERSON links
        """
        for narrative in self.state.narrative_items.values():
            question = narrative.question.lower()

            # Infer expected connection types
            if "officer" in question or "director" in question:
                self.expected_connections.append(ExpectedConnection(
                    entity_a_type=EntityType.COMPANY,
                    entity_b_type=EntityType.PERSON,
                    relationship="officer_of",
                    narrative_id=narrative.id,
                    reason=f"Narrative asks about officers: {narrative.question[:50]}"
                ))
            if "shareholder" in question or "owner" in question:
                self.expected_connections.append(ExpectedConnection(
                    entity_a_type=EntityType.COMPANY,
                    entity_b_type=EntityType.PERSON,
                    relationship="shareholder_of",
                    narrative_id=narrative.id,
                    reason=f"Narrative asks about ownership: {narrative.question[:50]}"
                ))
            if "affiliate" in question or "subsidiary" in question:
                self.expected_connections.append(ExpectedConnection(
                    entity_a_type=EntityType.COMPANY,
                    entity_b_type=EntityType.COMPANY,
                    relationship="affiliate_of",
                    narrative_id=narrative.id,
                    reason=f"Narrative asks about corporate structure: {narrative.question[:50]}"
                ))

    def detect_in_source(self, source: SourceResult) -> List[SurprisingAndCandidate]:
        """
        Detect Surprising ANDs in entities from a single source.

        When entities from the same source weren't predicted to co-occur.
        """
        candidates = []
        entity_ids = self.state.source_to_entities.get(source.id, [])
        entities = [self.state.entities[eid] for eid in entity_ids if eid in self.state.entities]

        if len(entities) < 2:
            return []

        # Check all pairs
        for i, entity_a in enumerate(entities):
            for entity_b in entities[i + 1:]:
                if self._is_surprising(entity_a, entity_b):
                    candidate = SurprisingAndCandidate(
                        entity_a=entity_a,
                        entity_b=entity_b,
                        source=source,
                        context=f"Found together in {source.source_name}",
                        surprise_score=self._calculate_surprise_score(entity_a, entity_b, source),
                        reasons=self._get_surprise_reasons(entity_a, entity_b)
                    )
                    candidates.append(candidate)

        return candidates

    def detect_across_sources(self) -> List[SurprisingAndCandidate]:
        """
        Detect Surprising ANDs across all sources.

        When the same entity pair appears in multiple unrelated sources.
        """
        candidates = []

        # Build entity co-occurrence by source
        pair_sources: Dict[Tuple[str, str], List[SourceResult]] = defaultdict(list)

        for source in self.state.sources.values():
            entity_ids = self.state.source_to_entities.get(source.id, [])
            for i, eid_a in enumerate(entity_ids):
                for eid_b in entity_ids[i + 1:]:
                    pair_key = tuple(sorted([eid_a, eid_b]))
                    pair_sources[pair_key].append(source)

        # Check for surprising multi-source occurrences
        for (eid_a, eid_b), sources in pair_sources.items():
            if len(sources) < 2:
                continue

            entity_a = self.state.entities.get(eid_a)
            entity_b = self.state.entities.get(eid_b)
            if not entity_a or not entity_b:
                continue

            # Multiple sources finding same pair = significant
            if self._is_surprising(entity_a, entity_b):
                candidate = SurprisingAndCandidate(
                    entity_a=entity_a,
                    entity_b=entity_b,
                    source=sources[0],  # Primary source
                    context=f"Found together in {len(sources)} sources: {[s.source_name for s in sources[:3]]}",
                    surprise_score=self._calculate_surprise_score(entity_a, entity_b, sources[0]) * len(sources),
                    reasons=self._get_surprise_reasons(entity_a, entity_b) + [
                        f"Appears in {len(sources)} different sources"
                    ]
                )
                candidates.append(candidate)

        return sorted(candidates, key=lambda c: c.surprise_score, reverse=True)

    def _is_surprising(self, entity_a: Entity, entity_b: Entity) -> bool:
        """
        Check if co-occurrence was predicted by narrative.
        """
        # Check if this type of connection was expected
        for expected in self.expected_connections:
            if (entity_a.entity_type == expected.entity_a_type and
                    entity_b.entity_type == expected.entity_b_type):
                return False
            if (entity_a.entity_type == expected.entity_b_type and
                    entity_b.entity_type == expected.entity_a_type):
                return False

        # Check if entities are already connected in graph
        for edge in self.state.graph.edges:
            if ((edge.source_entity_id == entity_a.id and edge.target_entity_id == entity_b.id) or
                    (edge.source_entity_id == entity_b.id and edge.target_entity_id == entity_a.id)):
                if edge.confirmed:
                    return False  # Already known connection

        # Not predicted and not already connected = surprising
        return True

    def _calculate_surprise_score(
            self,
            entity_a: Entity,
            entity_b: Entity,
            source: SourceResult
    ) -> float:
        """
        Score how surprising this co-occurrence is.

        Higher score = more noteworthy.
        """
        score = 1.0

        # Same type entities co-occurring is less surprising
        if entity_a.entity_type == entity_b.entity_type:
            score *= 0.5

        # High-value entity types
        high_value = {EntityType.PERSON, EntityType.COMPANY}
        if entity_a.entity_type in high_value and entity_b.entity_type in high_value:
            score *= 2.0

        # Different jurisdictions co-occurring is more surprising
        a_jurisdiction = entity_a.shell.get("jurisdiction", {})
        b_jurisdiction = entity_b.shell.get("jurisdiction", {})
        if a_jurisdiction and b_jurisdiction:
            a_val = a_jurisdiction.value if hasattr(a_jurisdiction, 'value') else a_jurisdiction
            b_val = b_jurisdiction.value if hasattr(b_jurisdiction, 'value') else b_jurisdiction
            if a_val != b_val:
                score *= 1.5

        # Registry sources more reliable
        if "registry" in source.source_type.lower():
            score *= 1.3

        return score

    def _get_surprise_reasons(self, entity_a: Entity, entity_b: Entity) -> List[str]:
        """Get reasons why this is surprising."""
        reasons = []

        # Check type mismatch
        if entity_a.entity_type != entity_b.entity_type:
            reasons.append(f"Different entity types: {entity_a.entity_type.value} + {entity_b.entity_type.value}")

        # Check if one entity is target of investigation
        for narrative in self.state.narrative_items.values():
            if entity_a.name.lower() in narrative.question.lower():
                reasons.append(f"{entity_b.name} not mentioned in narrative about {entity_a.name}")
            if entity_b.name.lower() in narrative.question.lower():
                reasons.append(f"{entity_a.name} not mentioned in narrative about {entity_b.name}")

        if not reasons:
            reasons.append("Connection not predicted by any narrative question")

        return reasons

    def promote_to_surprising_and(self, candidate: SurprisingAndCandidate) -> SurprisingAnd:
        """
        Promote a candidate to a full SurprisingAnd and add to state.
        """
        surprising = SurprisingAnd(
            id=hashlib.sha256(f"{candidate.entity_a.id}:{candidate.entity_b.id}:{uuid.uuid4()}".encode()).hexdigest()[:12],
            entity_a_id=candidate.entity_a.id,
            entity_b_id=candidate.entity_b.id,
            context=candidate.context,
            discovery_source=candidate.source.url,
            significance="high" if candidate.surprise_score > 2.0 else "medium" if candidate.surprise_score > 1.0 else "low",
        )

        self.state.add_surprising_and(surprising)
        return surprising

    def spawn_narrative_for_surprising(self, surprising: SurprisingAnd) -> NarrativeItem:
        """
        Spawn a new narrative item to investigate this Surprising AND.
        """
        entity_a = self.state.entities.get(surprising.entity_a_id)
        entity_b = self.state.entities.get(surprising.entity_b_id)

        if not entity_a or not entity_b:
            return None

        question = f"What is the connection between {entity_a.name} and {entity_b.name}?"
        narrative = NarrativeItem.create(question)
        narrative.section_header = f"## Unexpected Connection: {entity_a.name} - {entity_b.name}"

        self.state.add_narrative_item(narrative)
        surprising.spawned_narrative_id = narrative.id

        return narrative


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def detect_surprising_ands(state: InvestigationState) -> List[SurprisingAndCandidate]:
    """Detect all Surprising ANDs in current state."""
    detector = SurprisingAndDetector(state)

    candidates = []
    for source in state.sources.values():
        candidates.extend(detector.detect_in_source(source))

    candidates.extend(detector.detect_across_sources())

    return sorted(candidates, key=lambda c: c.surprise_score, reverse=True)


def process_surprising_ands(
        state: InvestigationState,
        threshold: float = 1.5,
        spawn_narratives: bool = True
) -> List[SurprisingAnd]:
    """
    Detect and process Surprising ANDs above threshold.

    Returns list of promoted Surprising ANDs.
    """
    detector = SurprisingAndDetector(state)
    candidates = detect_surprising_ands(state)

    promoted = []
    for candidate in candidates:
        if candidate.surprise_score >= threshold:
            surprising = detector.promote_to_surprising_and(candidate)
            promoted.append(surprising)

            if spawn_narratives:
                detector.spawn_narrative_for_surprising(surprising)

    return promoted
