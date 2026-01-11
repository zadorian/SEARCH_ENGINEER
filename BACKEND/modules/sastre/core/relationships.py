"""
SASTRE Relationship Tracking - Cross-level querying and analysis.

Implements:
1. Query → Narrative progress tracking (not just "ran" but "helped")
2. Source → Query overlap detection (convergence, redundancy, hot spots)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
from enum import Enum

from .state import (
    InvestigationState,
    NarrativeItem,
    NarrativeState,
    Query,
    QueryState,
    SourceResult,
    SourceState,
    Entity,
    Priority,
)


# =============================================================================
# CONTRIBUTION STATUS
# =============================================================================

class ContributionStatus(Enum):
    """Did a query actually help answer a narrative question?"""
    NOT_RUN = "not_run"
    FAILED = "failed"
    RAN_NO_RESULTS = "ran_no_results"
    RAN_IRRELEVANT = "ran_irrelevant"      # Results found but don't help
    RAN_PARTIAL = "ran_partial"            # Partially helps
    CONTRIBUTED = "contributed"            # Actually answered the question


class OverlapType(Enum):
    """Why did multiple queries hit the same source?"""
    CONVERGENCE = "convergence"    # Different narratives finding same evidence (valuable)
    REFINEMENT = "refinement"      # Same narrative, refined queries (expected)
    REDUNDANCY = "redundancy"      # Duplicate effort (wasteful)
    DEAD_END = "dead_end"          # Multiple queries, no results (informative)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class NarrativeProgress:
    """Real progress for a narrative question (not just query count)."""
    narrative_id: str
    total_queries: int
    not_run: int = 0
    ran_no_results: int = 0
    ran_irrelevant: int = 0
    ran_partial: int = 0
    contributed: int = 0
    failed: int = 0
    effective_progress: float = 0.0        # Only counts CONTRIBUTED
    coverage: float = 0.0                  # CONTRIBUTED + PARTIAL


@dataclass
class HotSpot:
    """A source hit by multiple queries."""
    source: SourceResult
    queries: List[Query]
    query_count: int
    overlap_type: OverlapType
    significance: float
    narrative_ids: Set[str] = field(default_factory=set)


@dataclass
class RedundantQueryPair:
    """Two queries that are essentially doing the same thing."""
    query_a: Query
    query_b: Query
    overlap_sources: List[str]
    similarity: float


@dataclass
class SourcePriority:
    """Priority score for an unchecked source."""
    source: SourceResult
    query_demand: int           # How many queries want this source
    narrative_breadth: int      # How many narratives would benefit
    priority_score: float
    reason: str


# =============================================================================
# QUERY → NARRATIVE TRACKER
# =============================================================================

class QueryNarrativeTracker:
    """
    Track which queries actually contribute to answering which narrative questions.
    Not just "query ran" but "query contributed to answer".
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.contribution_matrix: Dict[str, Dict[str, ContributionStatus]] = {}

    def assess_contribution(self, query: Query, narrative: NarrativeItem) -> ContributionStatus:
        """
        Did this query actually help answer this narrative question?
        """
        if query.state == QueryState.PENDING:
            return ContributionStatus.NOT_RUN

        if query.state == QueryState.FAILED:
            return ContributionStatus.FAILED

        # Query ran - but did it help?
        entities_found = self._get_entities_from_query(query)

        if not entities_found:
            return ContributionStatus.RAN_NO_RESULTS

        # Check if entities are relevant to narrative
        relevant = self._entities_relevant_to_narrative(entities_found, narrative)

        if not relevant:
            return ContributionStatus.RAN_IRRELEVANT

        # Check if entities actually answer the question
        if self._entities_answer_question(relevant, narrative):
            return ContributionStatus.CONTRIBUTED
        else:
            return ContributionStatus.RAN_PARTIAL

    def get_narrative_progress(self, narrative: NarrativeItem) -> NarrativeProgress:
        """
        For a narrative question, what's the real progress?
        """
        queries = self.state.get_queries_for_narrative(narrative.id)

        progress = NarrativeProgress(
            narrative_id=narrative.id,
            total_queries=len(queries),
        )

        for query in queries:
            status = self.assess_contribution(query, narrative)

            if status == ContributionStatus.NOT_RUN:
                progress.not_run += 1
            elif status == ContributionStatus.RAN_NO_RESULTS:
                progress.ran_no_results += 1
            elif status == ContributionStatus.RAN_IRRELEVANT:
                progress.ran_irrelevant += 1
            elif status == ContributionStatus.RAN_PARTIAL:
                progress.ran_partial += 1
            elif status == ContributionStatus.CONTRIBUTED:
                progress.contributed += 1
            elif status == ContributionStatus.FAILED:
                progress.failed += 1

        # Calculate real progress
        if progress.total_queries > 0:
            progress.effective_progress = progress.contributed / progress.total_queries
            progress.coverage = (progress.contributed + progress.ran_partial) / progress.total_queries

        return progress

    def find_unproductive_queries(self) -> List[Query]:
        """
        Queries that ran but contributed nothing.
        Indicates: wrong sources, wrong variations, or dead end.
        """
        unproductive = []

        for query in self.state.queries.values():
            if query.state in [QueryState.PENDING, QueryState.FAILED]:
                continue

            # Check all narratives this query was supposed to help
            narrative = self.state.narrative_items.get(query.narrative_id)
            if not narrative:
                continue

            status = self.assess_contribution(query, narrative)
            if status in [ContributionStatus.RAN_NO_RESULTS, ContributionStatus.RAN_IRRELEVANT]:
                unproductive.append(query)

        return unproductive

    def find_high_value_queries(self) -> List[Tuple[Query, int]]:
        """
        Queries that contributed to multiple narratives (if cross-linked).
        """
        query_value: Dict[str, int] = defaultdict(int)

        for narrative in self.state.narrative_items.values():
            for query in self.state.get_queries_for_narrative(narrative.id):
                status = self.assess_contribution(query, narrative)
                if status == ContributionStatus.CONTRIBUTED:
                    query_value[query.id] += 1

        high_value = [
            (self.state.queries[qid], count)
            for qid, count in query_value.items()
            if count > 1
        ]

        return sorted(high_value, key=lambda x: x[1], reverse=True)

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _get_entities_from_query(self, query: Query) -> List[Entity]:
        """Get all entities extracted from this query's sources."""
        entities = []
        for source in self.state.get_sources_for_query(query.id):
            entities.extend(self.state.get_entities_for_source(source.id))
        return entities

    def _entities_relevant_to_narrative(
        self,
        entities: List[Entity],
        narrative: NarrativeItem
    ) -> List[Entity]:
        """Filter entities to those relevant to the narrative question."""
        relevant = []
        question_lower = narrative.question.lower()

        for entity in entities:
            # Check if entity name appears in question
            if entity.name.lower() in question_lower:
                relevant.append(entity)
                continue

            # Check if entity type matches intent
            if narrative.intent.value == 'discover_subject':
                # Looking for entities - any entity is potentially relevant
                relevant.append(entity)
            elif narrative.intent.value == 'enrich_subject':
                # Looking for attributes of known entity
                # Check if this entity is connected to a known one
                known_entities = self._extract_entity_names_from_question(narrative.question)
                for known in known_entities:
                    if self._are_connected(entity.id, known):
                        relevant.append(entity)
                        break

        return relevant

    def _entities_answer_question(
        self,
        entities: List[Entity],
        narrative: NarrativeItem
    ) -> bool:
        """Do these entities actually answer the narrative question?"""
        question_lower = narrative.question.lower()

        # Check for specific question patterns
        if 'who' in question_lower:
            # Looking for persons
            return any(e.entity_type.value == 'person' for e in entities)

        if 'where' in question_lower or 'location' in question_lower:
            # Looking for locations/addresses
            return any(e.entity_type.value in ['address', 'company'] for e in entities)

        if 'offshore' in question_lower or 'shell' in question_lower:
            # Looking for offshore connections
            offshore_jurisdictions = {'cy', 'vg', 'ky', 'bvi', 'panama', 'seychelles'}
            for entity in entities:
                jur = entity.get_attribute('jurisdiction')
                if jur and jur.value.lower() in offshore_jurisdictions:
                    return True

        if 'connection' in question_lower or 'relationship' in question_lower:
            # Looking for connections - need at least 2 entities
            return len(entities) >= 2

        # Default: if we have relevant entities, we've made progress
        return len(entities) > 0

    def _extract_entity_names_from_question(self, question: str) -> List[str]:
        """Extract entity names mentioned in question."""
        # Simple extraction - look for quoted strings or capitalized phrases
        import re
        names = []

        # Quoted strings
        quoted = re.findall(r'"([^"]+)"', question)
        names.extend(quoted)

        # Capitalized phrases (simple heuristic)
        caps = re.findall(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b', question)
        names.extend(caps)

        return names

    def _are_connected(self, entity_id: str, entity_name: str) -> bool:
        """Check if entity is connected to another by name."""
        # Find entity by name
        for e in self.state.entities.values():
            if e.name.lower() == entity_name.lower():
                if self.state.graph.has_edge(entity_id, e.id):
                    return True
        return False


# =============================================================================
# SOURCE → QUERY OVERLAP DETECTOR
# =============================================================================

class SourceQueryOverlapDetector:
    """
    Find where multiple queries hit the same sources.
    Detects: convergence (valuable), redundancy (waste), hot spots (central nodes).
    """

    def __init__(self, state: InvestigationState):
        self.state = state
        self.source_to_queries: Dict[str, List[str]] = self._build_index()

    def _build_index(self) -> Dict[str, List[str]]:
        """Build inverted index from sources to queries that hit them."""
        index = defaultdict(list)

        for query_id, source_ids in self.state.query_to_sources.items():
            for source_id in source_ids:
                index[source_id].append(query_id)

        return index

    def find_hot_spots(self, min_queries: int = 2) -> List[HotSpot]:
        """
        Sources hit by multiple queries = hot spots.

        Could indicate:
        - Convergence: different angles arriving at same evidence (GOOD)
        - Redundancy: same ground covered multiple times (WASTE)
        - Central node: this source is key to investigation (IMPORTANT)
        """
        hot_spots = []

        for source_id, query_ids in self.source_to_queries.items():
            if len(query_ids) >= min_queries:
                source = self.state.sources.get(source_id)
                if not source:
                    continue

                queries = [self.state.queries[qid] for qid in query_ids if qid in self.state.queries]

                # Get narrative IDs
                narrative_ids = set(q.narrative_id for q in queries)

                # Classify the overlap
                overlap_type = self._classify_overlap(source, queries, narrative_ids)

                hot_spots.append(HotSpot(
                    source=source,
                    queries=queries,
                    query_count=len(queries),
                    overlap_type=overlap_type,
                    significance=self._calculate_significance(source, queries, overlap_type),
                    narrative_ids=narrative_ids,
                ))

        return sorted(hot_spots, key=lambda h: h.significance, reverse=True)

    def _classify_overlap(
        self,
        source: SourceResult,
        queries: List[Query],
        narrative_ids: Set[str]
    ) -> OverlapType:
        """Classify why multiple queries hit this source."""

        # Same narrative, different queries = REFINEMENT
        if len(narrative_ids) == 1:
            return OverlapType.REFINEMENT

        # Different narratives converging = CONVERGENCE (valuable)
        entity_ids = self.state.source_to_entities.get(source.id, [])
        if entity_ids:
            return OverlapType.CONVERGENCE

        # Multiple queries, no results = DEAD_END
        if source.state == SourceState.EMPTY:
            return OverlapType.DEAD_END

        # Multiple queries checking same source = possible REDUNDANCY
        return OverlapType.REDUNDANCY

    def _calculate_significance(
        self,
        source: SourceResult,
        queries: List[Query],
        overlap_type: OverlapType
    ) -> float:
        """How significant is this hot spot?"""
        base = len(queries) / 10.0

        multipliers = {
            OverlapType.CONVERGENCE: 2.0,
            OverlapType.REFINEMENT: 1.0,
            OverlapType.REDUNDANCY: 0.5,
            OverlapType.DEAD_END: 0.3,
        }

        # Boost if source has many entities
        entity_count = len(self.state.source_to_entities.get(source.id, []))
        entity_boost = 1.0 + (entity_count * 0.1)

        return base * multipliers[overlap_type] * entity_boost

    def find_redundant_queries(self) -> List[RedundantQueryPair]:
        """
        Find query pairs that are essentially doing the same thing.
        Same sources, similar results = one is redundant.
        """
        redundant = []
        query_ids = list(self.state.queries.keys())

        for i, q1_id in enumerate(query_ids):
            for q2_id in query_ids[i+1:]:
                q1_sources = set(self.state.query_to_sources.get(q1_id, []))
                q2_sources = set(self.state.query_to_sources.get(q2_id, []))

                if not q1_sources or not q2_sources:
                    continue

                # Calculate Jaccard similarity
                intersection = len(q1_sources & q2_sources)
                union = len(q1_sources | q2_sources)
                similarity = intersection / union if union > 0 else 0

                if similarity > 0.7:  # 70% overlap
                    redundant.append(RedundantQueryPair(
                        query_a=self.state.queries[q1_id],
                        query_b=self.state.queries[q2_id],
                        overlap_sources=list(q1_sources & q2_sources),
                        similarity=similarity,
                    ))

        return redundant

    def suggest_source_priorities(self) -> List[SourcePriority]:
        """
        Based on overlaps, which sources should be checked first?
        """
        priorities = []

        for source_id, query_ids in self.source_to_queries.items():
            source = self.state.sources.get(source_id)
            if not source or source.state != SourceState.UNCHECKED:
                continue

            # More queries wanting this source = higher priority
            query_demand = len(query_ids)

            # How many narratives would benefit
            narratives = set()
            for qid in query_ids:
                query = self.state.queries.get(qid)
                if query:
                    narratives.add(query.narrative_id)
            narrative_breadth = len(narratives)

            priority_score = query_demand * narrative_breadth

            priorities.append(SourcePriority(
                source=source,
                query_demand=query_demand,
                narrative_breadth=narrative_breadth,
                priority_score=priority_score,
                reason=f"{query_demand} queries across {narrative_breadth} narratives want this source"
            ))

        return sorted(priorities, key=lambda p: p.priority_score, reverse=True)


# =============================================================================
# UNIFIED RELATIONSHIP TRACKER
# =============================================================================

class RelationshipTracker:
    """Unified interface for all relationship tracking."""

    def __init__(self, state: InvestigationState):
        self.state = state
        self.query_narrative = QueryNarrativeTracker(state)
        self.source_query = SourceQueryOverlapDetector(state)

    def get_narrative_progress(self, narrative_id: str) -> Optional[NarrativeProgress]:
        """Get progress for a specific narrative."""
        narrative = self.state.narrative_items.get(narrative_id)
        if narrative:
            return self.query_narrative.get_narrative_progress(narrative)
        return None

    def get_all_narrative_progress(self) -> Dict[str, NarrativeProgress]:
        """Get progress for all narratives."""
        return {
            n.id: self.query_narrative.get_narrative_progress(n)
            for n in self.state.narrative_items.values()
        }

    def get_hot_spots(self, min_queries: int = 2) -> List[HotSpot]:
        """Get source hot spots."""
        return self.source_query.find_hot_spots(min_queries)

    def get_redundant_queries(self) -> List[RedundantQueryPair]:
        """Get redundant query pairs."""
        return self.source_query.find_redundant_queries()

    def get_source_priorities(self) -> List[SourcePriority]:
        """Get prioritized unchecked sources."""
        return self.source_query.suggest_source_priorities()

    def get_unproductive_queries(self) -> List[Query]:
        """Get queries that ran but didn't help."""
        return self.query_narrative.find_unproductive_queries()

    def get_high_value_queries(self) -> List[Tuple[Query, int]]:
        """Get queries that contributed most."""
        return self.query_narrative.find_high_value_queries()
