from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from ..core.state import (
    InvestigationState, Query, NarrativeItem, SourceResult, 
    QueryState, SourceState, Entity, KUQuadrant
)

class ContributionStatus(Enum):
    NOT_RUN = "not_run"
    FAILED = "failed"
    RAN_NO_RESULTS = "ran_no_results"
    RAN_IRRELEVANT = "ran_irrelevant"      # Results found but don't help
    RAN_PARTIAL = "ran_partial"            # Partially helps
    CONTRIBUTED = "contributed"            # Actually answered the question

@dataclass
class NarrativeProgress:
    narrative_id: str
    total_queries: int
    not_run: int
    ran_no_results: int
    ran_irrelevant: int
    ran_partial: int
    contributed: int
    failed: int
    effective_progress: float = 0.0        # Only counts CONTRIBUTED
    coverage: float = 0.0                  # CONTRIBUTED + PARTIAL

class OverlapType(Enum):
    CONVERGENCE = "convergence"    # Different narratives finding same evidence
    REFINEMENT = "refinement"      # Same narrative, refined queries
    REDUNDANCY = "redundancy"      # Duplicate effort
    DEAD_END = "dead_end"          # Multiple queries, no results

@dataclass
class HotSpot:
    source: SourceResult
    queries: List[Query]
    query_count: int
    overlap_type: OverlapType
    significance: float

@dataclass
class RedundantQueryPair:
    query_a: Query
    query_b: Query
    overlap_sources: List[str]
    similarity: float

@dataclass
class SourcePriority:
    source: SourceResult
    query_demand: int
    narrative_breadth: int
    priority_score: float
    reason: str


class QueryNarrativeTracker:
    """
    Query nodes against Narrative nodes to track progress.
    Not just "query ran" but "query contributed to answer".
    """
    
    def __init__(self, state: InvestigationState):
        self.state = state
        # Matrix: narrative_id → query_id → contribution_status
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

    def _get_entities_from_query(self, query: Query) -> List[Entity]:
        """Helper to get entities found by a query."""
        entities = []
        for source_id in query.source_ids:
            if source_id in self.state.source_to_entities:
                entity_ids = self.state.source_to_entities[source_id]
                for eid in entity_ids:
                    if eid in self.state.entities:
                        entities.append(self.state.entities[eid])
        return entities

    def _entities_relevant_to_narrative(self, entities: List[Entity], narrative: NarrativeItem) -> List[Entity]:
        """
        Determine relevance via simple keyword matching or intent alignment.
        (Placeholder for more complex NLP relevance)
        """
        relevant = []
        keywords = narrative.question.lower().split()
        for entity in entities:
            # Simple check: does entity name overlap with question?
            # Or matches intent?
            relevant.append(entity) # Assume relevant for now if found in query context
        return relevant

    def _entities_answer_question(self, entities: List[Entity], narrative: NarrativeItem) -> bool:
        """
        Do these entities provide a sufficient answer?
        """
        # Heuristic: if we have verified entities with high confidence
        high_confidence = [e for e in entities if e.confidence > 0.8]
        return len(high_confidence) > 0
    
    def get_narrative_progress(self, narrative: NarrativeItem) -> NarrativeProgress:
        """
        For a narrative question, what's the real progress?
        """
        queries = self.state.get_queries_for_narrative(narrative.id)
        
        progress = NarrativeProgress(
            narrative_id=narrative.id,
            total_queries=len(queries),
            not_run=0,
            ran_no_results=0,
            ran_irrelevant=0,
            ran_partial=0,
            contributed=0,
            failed=0
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
        
        # Calculate real progress (not just "queries run")
        total = max(1, progress.total_queries)
        progress.effective_progress = progress.contributed / total
        progress.coverage = (progress.contributed + progress.ran_partial) / total
        
        return progress
    
    def find_unproductive_queries(self) -> List[Query]:
        """
        Queries that ran but contributed nothing.
        """
        unproductive = []
        
        for query in self.state.queries.values():
            # Check all narratives this query was supposed to help
            narrative = self.state.narrative_items.get(query.narrative_id)
            if not narrative:
                continue
                
            status = self.assess_contribution(query, narrative)
            
            if status in [ContributionStatus.RAN_NO_RESULTS, ContributionStatus.RAN_IRRELEVANT] \
               and query.state not in [QueryState.PENDING, QueryState.FAILED]:
                unproductive.append(query)
        
        return unproductive


class SourceQueryOverlapDetector:
    """
    Source nodes against Query nodes to find overlaps.
    Multiple queries hitting same source = pattern worth investigating.
    """
    
    def __init__(self, state: InvestigationState):
        self.state = state
        # Inverted index: source_id → List[query_id]
        self.source_to_queries: Dict[str, List[str]] = self.build_index()
    
    def build_index(self) -> Dict[str, List[str]]:
        """Build inverted index from sources to queries that hit them."""
        index = defaultdict(list)
        
        for query_id, source_ids in self.state.query_to_sources.items():
            for source_id in source_ids:
                index[source_id].append(query_id)
        
        return index
    
    def find_hot_spots(self, min_queries: int = 2) -> List[HotSpot]:
        """
        Sources hit by multiple queries = hot spots.
        """
        hot_spots = []
        
        for source_id, query_ids in self.source_to_queries.items():
            if len(query_ids) >= min_queries:
                source = self.state.sources.get(source_id)
                if not source:
                    continue
                    
                queries = [self.state.queries[qid] for qid in query_ids if qid in self.state.queries]
                
                # Classify the overlap
                overlap_type = self.classify_overlap(source, queries)
                
                hot_spots.append(HotSpot(
                    source=source,
                    queries=queries,
                    query_count=len(queries),
                    overlap_type=overlap_type,
                    significance=self.calculate_significance(source, queries, overlap_type)
                ))
        
        return sorted(hot_spots, key=lambda h: h.significance, reverse=True)
    
    def classify_overlap(self, source: SourceResult, queries: List[Query]) -> OverlapType:
        """
        Classify why multiple queries hit this source.
        """
        # Get the narrative items behind each query
        narratives = set()
        for query in queries:
            narratives.add(query.narrative_id)
        
        # Same narrative, different queries = REFINEMENT
        if len(narratives) == 1:
            return OverlapType.REFINEMENT
        
        # Different narratives converging = CONVERGENCE (valuable)
        # Check if entities from this source answer multiple questions
        entities = self.state.source_to_entities.get(source.id, [])
        if entities:
            return OverlapType.CONVERGENCE
        
        # Multiple queries, no results = DEAD_END
        if source.state == SourceState.EMPTY:
            return OverlapType.DEAD_END
        
        # Multiple queries checking same source = possible REDUNDANCY
        return OverlapType.REDUNDANCY
    
    def calculate_significance(
        self, 
        source: SourceResult, 
        queries: List[Query], 
        overlap_type: OverlapType
    ) -> float:
        """
        How significant is this hot spot?
        """
        base = len(queries) / 10.0  # More queries = more significant
        
        multipliers = {
            OverlapType.CONVERGENCE: 2.0,    # Very valuable
            OverlapType.REFINEMENT: 1.0,     # Expected
            OverlapType.REDUNDANCY: 0.5,     # Wasteful but informative
            OverlapType.DEAD_END: 0.3,       # Worth noting
        }
        
        # Boost if source has many entities
        entity_count = len(self.state.source_to_entities.get(source.id, []))
        entity_boost = 1.0 + (entity_count * 0.1)
        
        return base * multipliers.get(overlap_type, 1.0) * entity_boost
    
    def find_redundant_queries(self) -> List[RedundantQueryPair]:
        """
        Find query pairs that are essentially doing the same thing.
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
                
                if similarity > 0.7:  # 70% overlap = likely redundant
                    redundant.append(RedundantQueryPair(
                        query_a=self.state.queries[q1_id],
                        query_b=self.state.queries[q2_id],
                        overlap_sources=list(q1_sources & q2_sources),
                        similarity=similarity
                    ))
        
        return redundant
    
    def suggest_source_priorities(self) -> List[SourcePriority]:
        """
        Based on overlaps, which sources should be checked first?
        """
        priorities = []
        
        for source_id, query_ids in self.source_to_queries.items():
            source = self.state.sources.get(source_id)
            if not source:
                continue
            
            if source.state != SourceState.UNCHECKED:
                continue
            
            # More queries wanting this source = higher priority
            query_demand = len(query_ids)
            
            # Check how many narratives would benefit
            narratives = set()
            for qid in query_ids:
                q = self.state.queries.get(qid)
                if q:
                    narratives.add(q.narrative_id)
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
