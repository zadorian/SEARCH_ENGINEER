"""
SASTRE Grid Assessor - Completeness assessment logic.

Includes:
1. LegacyGridAssessor: Old Cymonides-based assessor (kept for reference)
2. GridAssessor: New state-based assessor with 4 modes
3. EnhancedGridAssessor: Adds cross-level querying (Query->Narrative, Source->Query)
4. GapQueryGenerator: Converts gaps into executable SASTRE syntax queries
"""

import asyncio
import aiohttp
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from collections import defaultdict

from ..core.state import (
    InvestigationState, NarrativeState, QueryState, SourceState,
    Priority, NarrativeItem, Entity, Edge, KUQuadrant
)
from .cross_level import (
    QueryNarrativeTracker, SourceQueryOverlapDetector,
    NarrativeProgress, HotSpot, RedundantQueryPair, SourcePriority, OverlapType
)


# =============================================================================
# VIEW MODES (Four centricities - filters on cymonides-1-{projectId})
# =============================================================================

class ViewMode(Enum):
    """
    Four centricities - different FILTERS on same Cymonides index.

    Each maps to node_class or type filters in Elasticsearch.
    """
    SUBJECT = "subject"       # node_class: entity (person, company, etc.)
    LOCATION = "location"     # node_class: domain, source, jurisdiction
    NARRATIVE = "narrative"   # node_class: narrative (documents, notes)
    NEXUS = "nexus"           # node_class: search (queries, intersections)


# Node class filters for each view mode
VIEW_MODE_FILTERS = {
    ViewMode.SUBJECT: {
        "node_class": ["entity"],
        "type": ["person", "company", "organization", "event", "topic", "theme"],
    },
    ViewMode.LOCATION: {
        "node_class": ["domain", "source", "jurisdiction"],
        "type": ["domain", "website", "registry", "jurisdiction", "country"],
    },
    ViewMode.NARRATIVE: {
        "node_class": ["narrative"],
        "type": ["document", "note", "section", "report"],
    },
    ViewMode.NEXUS: {
        "node_class": ["search", "query", "intersection"],
        "type": ["search", "query", "nexus", "intersection"],
    },
}


# =============================================================================
# VIEW ASSESSMENT (Thin interface to Cymonides)
# =============================================================================

@dataclass
class ViewAssessment:
    """Assessment of a single view mode from Cymonides."""
    mode: ViewMode
    total_nodes: int
    nodes_with_edges: int
    coverage_score: float  # 0-1: how complete is this view
    gaps: List[str]        # What's missing
    hot_spots: List[str]   # Most connected nodes
    sample_nodes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CymonidesAssessment:
    """Full four-centric assessment from Cymonides."""
    project_id: str
    subject: ViewAssessment
    location: ViewAssessment
    narrative: ViewAssessment
    nexus: ViewAssessment

    # Cross-view analysis
    subject_location_overlap: List[str] = field(default_factory=list)
    narrative_gaps: List[str] = field(default_factory=list)
    nexus_hot_spots: List[str] = field(default_factory=list)

    overall_completeness: float = 0.0


class CymonidesGridAssessor:
    """
    Thin interface to Cymonides for four-centric assessment.

    This queries cymonides-1-{projectId} with different filters
    for each view mode. Does NOT store data.
    """

    def __init__(
        self,
        project_id: str,
        elastic_url: str = "http://localhost:9200",
        ts_api_url: str = "http://localhost:3001"
    ):
        self.project_id = project_id
        self.elastic_url = elastic_url
        self.ts_api_url = ts_api_url
        self.index_name = f"cymonides-1-{project_id}"
        self._session = None

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def assess(self) -> CymonidesAssessment:
        """Run full four-centric assessment."""
        results = await asyncio.gather(
            self._assess_view(ViewMode.SUBJECT),
            self._assess_view(ViewMode.LOCATION),
            self._assess_view(ViewMode.NARRATIVE),
            self._assess_view(ViewMode.NEXUS),
            return_exceptions=True
        )

        # Handle any exceptions
        subject = results[0] if not isinstance(results[0], Exception) else self._empty_view(ViewMode.SUBJECT)
        location = results[1] if not isinstance(results[1], Exception) else self._empty_view(ViewMode.LOCATION)
        narrative = results[2] if not isinstance(results[2], Exception) else self._empty_view(ViewMode.NARRATIVE)
        nexus = results[3] if not isinstance(results[3], Exception) else self._empty_view(ViewMode.NEXUS)

        # Calculate overall completeness
        scores = [subject.coverage_score, location.coverage_score,
                  narrative.coverage_score, nexus.coverage_score]
        overall = sum(scores) / len(scores) if scores else 0

        return CymonidesAssessment(
            project_id=self.project_id,
            subject=subject,
            location=location,
            narrative=narrative,
            nexus=nexus,
            overall_completeness=overall,
        )

    def _empty_view(self, mode: ViewMode) -> ViewAssessment:
        """Return empty assessment for a view."""
        return ViewAssessment(
            mode=mode,
            total_nodes=0,
            nodes_with_edges=0,
            coverage_score=0,
            gaps=[f"No {mode.value} data found"],
            hot_spots=[],
        )

    async def _assess_view(self, mode: ViewMode) -> ViewAssessment:
        """Assess a single view by querying Cymonides."""
        filters = VIEW_MODE_FILTERS[mode]

        # Build Elasticsearch query
        query = {
            "bool": {
                "should": [
                    {"terms": {"node_class": filters["node_class"]}},
                    {"terms": {"type": filters["type"]}},
                ],
                "minimum_should_match": 1
            }
        }

        body = {
            "query": query,
            "size": 20,
            "aggs": {
                "by_type": {"terms": {"field": "type", "size": 20}},
            }
        }

        result = await self._query_elasticsearch(body)

        if not result:
            return self._empty_view(mode)

        # Parse results
        total = result.get("hits", {}).get("total", {})
        total_count = total.get("value", 0) if isinstance(total, dict) else total

        hits = result.get("hits", {}).get("hits", [])
        sample_nodes = [h.get("_source", {}) for h in hits[:10]]

        # Simple coverage estimate
        coverage = min(total_count / 10, 1.0) if total_count > 0 else 0

        # Identify gaps based on mode
        gaps = self._identify_gaps(mode, result.get("aggregations", {}))

        return ViewAssessment(
            mode=mode,
            total_nodes=total_count,
            nodes_with_edges=0,  # Would need nested query
            coverage_score=coverage,
            gaps=gaps,
            hot_spots=[],
            sample_nodes=sample_nodes,
        )

    def _identify_gaps(self, mode: ViewMode, aggs: Dict) -> List[str]:
        """Identify gaps in a view."""
        gaps = []
        type_buckets = aggs.get("by_type", {}).get("buckets", [])
        type_counts = {b["key"]: b["doc_count"] for b in type_buckets}

        if mode == ViewMode.SUBJECT:
            for t in ["person", "company", "organization"]:
                if t not in type_counts:
                    gaps.append(f"No {t} entities found")
        elif mode == ViewMode.LOCATION:
            for t in ["domain", "jurisdiction"]:
                if t not in type_counts:
                    gaps.append(f"No {t} locations found")
        elif mode == ViewMode.NARRATIVE:
            if not type_counts:
                gaps.append("No narrative documents created")
        elif mode == ViewMode.NEXUS:
            if not type_counts:
                gaps.append("No query intersections tracked")

        return gaps

    async def _query_elasticsearch(self, body: Dict) -> Optional[Dict]:
        """Execute Elasticsearch query."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.elastic_url}/{self.index_name}/_search",
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    return None
                else:
                    return None
        except Exception:
            return None


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def assess_investigation(project_id: str) -> CymonidesAssessment:
    """Quick assessment of investigation completeness."""
    assessor = CymonidesGridAssessor(project_id)
    try:
        return await assessor.assess()
    finally:
        await assessor.close()


# =============================================================================
# ASSESSMENT DATA CLASSES
# =============================================================================

@dataclass
class Gap:
    type: str
    target: Any
    description: str
    priority: Priority
    suggested_action: str


@dataclass
class NarrativeAssessment:
    unanswered: List[NarrativeItem] = field(default_factory=list)
    partial: List[NarrativeItem] = field(default_factory=list)
    answered: List[NarrativeItem] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)


@dataclass
class SubjectAssessment:
    incomplete_core: List[Entity] = field(default_factory=list)
    incomplete_shell: List[Entity] = field(default_factory=list)
    needs_disambiguation: List[Entity] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)


@dataclass
class LocationAssessment:
    unchecked_sources: List[Any] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)


@dataclass
class NexusAssessment:
    confirmed_connections: List[Edge] = field(default_factory=list)
    unconfirmed_connections: List[Edge] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)


@dataclass
class CrossPollinatedAction:
    from_mode: str
    to_mode: str
    insight: str
    action: str
    priority: Priority


@dataclass
class PriorityAction:
    type: str
    target: Any
    reason: str
    priority: Priority


@dataclass
class GridAssessment:
    narrative: NarrativeAssessment
    subject: SubjectAssessment
    location: LocationAssessment
    nexus: NexusAssessment
    cross_pollinated: List[CrossPollinatedAction]

    def get_priority_actions(self) -> List[PriorityAction]:
        actions = []
        
        # From narrative gaps
        for gap in self.narrative.gaps:
            actions.append(PriorityAction(
                type="NARRATIVE_GAP",
                target=gap.target,
                reason=gap.description,
                priority=gap.priority
            ))
        
        # From subject gaps
        for gap in self.subject.gaps:
            actions.append(PriorityAction(
                type="SUBJECT_GAP",
                target=gap.target,
                reason=gap.description,
                priority=gap.priority
            ))
        
        # From location gaps
        for gap in self.location.gaps:
            actions.append(PriorityAction(
                type="LOCATION_GAP",
                target=gap.target,
                reason=gap.description,
                priority=gap.priority
            ))
        
        # From nexus gaps
        for edge in self.nexus.unconfirmed_connections:
            actions.append(PriorityAction(
                type="UNCONFIRMED_CONNECTION",
                target=(edge.source_entity_id, edge.target_entity_id),
                reason=f"Unconfirmed connection: {edge.relationship}",
                priority=Priority.MEDIUM
            ))
            
        for gap in self.nexus.gaps:
             actions.append(PriorityAction(
                type="NEXUS_GAP",
                target=gap.target,
                reason=gap.description,
                priority=gap.priority
            ))
        
        # From cross-pollination
        for item in self.cross_pollinated:
            actions.append(PriorityAction(
                type="CROSS_POLLINATED",
                target=item.action,
                reason=item.insight,
                priority=item.priority
            ))
        
        # Sort by priority
        return sorted(actions, key=lambda a: a.priority.value, reverse=True)


@dataclass
class EnhancedGridAssessment(GridAssessment):
    narrative_progress: Dict[str, NarrativeProgress]
    hot_spots: List[HotSpot]
    redundant_queries: List[RedundantQueryPair]
    source_priorities: List[SourcePriority]
    unproductive_queries: List[Any]


# =============================================================================
# MAIN ASSESSOR LOGIC
# =============================================================================

class GridAssessor:
    """
    Assesses investigation completeness from four perspectives.
    """
    
    def __init__(self, state: InvestigationState):
        self.state = state
    
    def full_assessment(self) -> GridAssessment:
        """Run all four assessment modes plus cross-pollination."""
        return GridAssessment(
            narrative=self.narrative_mode(),
            subject=self.subject_mode(),
            location=self.location_mode(),
            nexus=self.nexus_mode(),
            cross_pollinated=self.cross_pollinate()
        )
    
    # ─────────────────────────────────────────────────────────────
    # MODE 1: NARRATIVE-CENTRIC
    # ─────────────────────────────────────────────────────────────
    
    def narrative_mode(self) -> NarrativeAssessment:
        assessment = NarrativeAssessment()
        
        for item in self.state.narrative_items.values():
            if item.state == NarrativeState.UNANSWERED:
                assessment.unanswered.append(item)
                assessment.gaps.append(Gap(
                    type="NARRATIVE_UNANSWERED",
                    target=item.id,
                    description=f"Question not yet investigated: {item.question}",
                    priority=item.priority,
                    suggested_action=f"Run initial queries for: {item.question}"
                ))
            elif item.state == NarrativeState.PARTIAL:
                assessment.partial.append(item)
                queries = self.state.get_queries_for_narrative(item.id)
                run_queries = len([q for q in queries if q.state != QueryState.PENDING])
                total_queries = len(queries)
                assessment.gaps.append(Gap(
                    type="NARRATIVE_PARTIAL",
                    target=item.id,
                    description=f"Question partially answered: {run_queries}/{total_queries} queries run",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Run remaining {total_queries - run_queries} queries"
                ))
            else:
                assessment.answered.append(item)
        
        return assessment
    
    # ─────────────────────────────────────────────────────────────
    # MODE 2: SUBJECT-CENTRIC
    # ─────────────────────────────────────────────────────────────
    
    def subject_mode(self) -> SubjectAssessment:
        assessment = SubjectAssessment()
        
        for entity in self.state.entities.values():
            # Check Core completeness
            if not entity.core_complete:
                assessment.incomplete_core.append(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_CORE_INCOMPLETE",
                    target=entity.id,
                    description=f"Entity {entity.name} missing core attributes",
                    priority=Priority.HIGH,
                    suggested_action=f"Enrich core for {entity.name}"
                ))
            
            # Check Shell completeness
            elif not entity.shell_complete:
                assessment.incomplete_shell.append(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_SHELL_INCOMPLETE",
                    target=entity.id,
                    description=f"Entity {entity.name} has Core but no Shell",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Enrich shell for {entity.name}"
                ))
            
            # Check for disambiguation needs
            if entity.collision_flags:
                assessment.needs_disambiguation.append(entity)
                assessment.gaps.append(Gap(
                    type="ENTITY_COLLISION",
                    target=entity.id,
                    description=f"Entity {entity.name} may be confused with others",
                    priority=Priority.HIGH,
                    suggested_action="Run wedge queries for disambiguation"
                ))
        
        return assessment
    
    # ─────────────────────────────────────────────────────────────
    # MODE 3: LOCATION-CENTRIC
    # ─────────────────────────────────────────────────────────────
    
    def location_mode(self) -> LocationAssessment:
        assessment = LocationAssessment()
        
        # Group sources by jurisdiction
        by_jurisdiction = defaultdict(list)
        for source in self.state.sources.values():
            by_jurisdiction[source.jurisdiction].append(source)
        
        for jurisdiction, sources in by_jurisdiction.items():
            checked = [s for s in sources if s.state == SourceState.CHECKED]
            unchecked = [s for s in sources if s.state == SourceState.UNCHECKED]
            
            if unchecked:
                assessment.unchecked_sources.extend(unchecked)
                assessment.gaps.append(Gap(
                    type="LOCATION_UNCHECKED",
                    target=jurisdiction,
                    description=f"{jurisdiction}: {len(checked)}/{len(sources)} sources checked",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Check {len(unchecked)} remaining sources in {jurisdiction}"
                ))
        
        return assessment
    
    # ─────────────────────────────────────────────────────────────
    # MODE 4: NEXUS-CENTRIC
    # ─────────────────────────────────────────────────────────────
    
    def nexus_mode(self) -> NexusAssessment:
        assessment = NexusAssessment()
        
        for edge in self.state.graph.edges:
            if edge.confirmed:
                assessment.confirmed_connections.append(edge)
            else:
                assessment.unconfirmed_connections.append(edge)
                assessment.gaps.append(Gap(
                    type="NEXUS_UNCONFIRMED",
                    target=(edge.source_entity_id, edge.target_entity_id),
                    description=f"Connection {edge.source_entity_id} -> {edge.target_entity_id} unconfirmed",
                    priority=Priority.MEDIUM,
                    suggested_action=f"Verify connection"
                ))
        
        return assessment

    # ─────────────────────────────────────────────────────────────
    # CROSS-POLLINATION
    # ─────────────────────────────────────────────────────────────
    
    def cross_pollinate(self) -> List[CrossPollinatedAction]:
        actions = []
        
        # Subject → Location: Entity implies jurisdiction to check
        for entity in self.state.entities.values():
            if "jurisdiction" in entity.shell:
                jurisdiction = entity.shell["jurisdiction"].value
                unchecked = self._get_unchecked_sources_for_jurisdiction(jurisdiction)
                if unchecked:
                    actions.append(CrossPollinatedAction(
                        from_mode="SUBJECT",
                        to_mode="LOCATION",
                        insight=f"Entity {entity.name} implies jurisdiction {jurisdiction}",
                        action=f"Check {len(unchecked)} unchecked sources in {jurisdiction}",
                        priority=Priority.HIGH
                    ))
        
        # Location → Subject: Source checked but entities not extracted
        for source in self.state.sources.values():
            if source.state == SourceState.CHECKED:
                entity_count = len(self.state.source_to_entities.get(source.id, []))
                if source.raw_results > 0 and entity_count == 0:
                    actions.append(CrossPollinatedAction(
                        from_mode="LOCATION",
                        to_mode="SUBJECT",
                        insight=f"Source {source.source_name} has results but no extracted entities",
                        action=f"Run entity extraction on {source.source_name}",
                        priority=Priority.MEDIUM
                    ))
        
        return actions

    def _get_unchecked_sources_for_jurisdiction(self, jurisdiction: str) -> List[Any]:
        return [
            s for s in self.state.sources.values() 
            if s.jurisdiction == jurisdiction and s.state == SourceState.UNCHECKED
        ]


# =============================================================================
# ENHANCED GRID ASSESSOR
# =============================================================================

class EnhancedGridAssessor(GridAssessor):
    """
    Grid assessment enhanced with cross-level querying.
    """
    
    def __init__(self, state: InvestigationState):
        super().__init__(state)
        self.query_narrative_tracker = QueryNarrativeTracker(state)
        self.overlap_detector = SourceQueryOverlapDetector(state)
    
    def full_assessment(self) -> EnhancedGridAssessment:
        """Run all assessments including cross-level analysis."""
        base = super().full_assessment()
        
        return EnhancedGridAssessment(
            # Original four modes
            narrative=base.narrative,
            subject=base.subject,
            location=base.location,
            nexus=base.nexus,
            cross_pollinated=base.cross_pollinated,
            
            # NEW: Cross-level insights
            narrative_progress=self.assess_all_narrative_progress(),
            hot_spots=self.overlap_detector.find_hot_spots(),
            redundant_queries=self.overlap_detector.find_redundant_queries(),
            source_priorities=self.overlap_detector.suggest_source_priorities(),
            unproductive_queries=self.query_narrative_tracker.find_unproductive_queries()
        )
    
    def assess_all_narrative_progress(self) -> Dict[str, NarrativeProgress]:
        """Real progress for each narrative item."""
        progress = {}
        for narrative in self.state.narrative_items.values():
            progress[narrative.id] = self.query_narrative_tracker.get_narrative_progress(narrative)
        return progress
    
    def get_priority_actions(self, assessment: EnhancedGridAssessment) -> List[PriorityAction]:
        """
        Priority actions informed by cross-level analysis.
        """
        actions = assessment.get_priority_actions() # Get base actions
        
        # Add actions from cross-level insights
        
        # 1. Prioritize sources that multiple queries need
        for sp in assessment.source_priorities[:5]:
            actions.append(PriorityAction(
                type="HIGH_DEMAND_SOURCE",
                target=sp.source.id,
                reason=sp.reason,
                priority=Priority.HIGH
            ))
        
        # 2. Flag redundant queries for review
        for rq in assessment.redundant_queries:
            actions.append(PriorityAction(
                type="REDUNDANT_QUERY_PAIR",
                target=(rq.query_a.id, rq.query_b.id),
                reason=f"Queries {rq.similarity:.0%} similar - consider merging",
                priority=Priority.LOW
            ))
        
        # 3. Investigate convergence hot spots
        for hs in assessment.hot_spots:
            if hs.overlap_type == OverlapType.CONVERGENCE:
                actions.append(PriorityAction(
                    type="CONVERGENCE_HOT_SPOT",
                    target=hs.source.id,
                    reason=f"{hs.query_count} queries from different narratives converge here",
                    priority=Priority.HIGH
                ))
        
        # 4. Flag narratives with low effective progress
        for narrative_id, progress in assessment.narrative_progress.items():
            if progress.coverage > 0.5 and progress.effective_progress < 0.2:
                actions.append(PriorityAction(
                    type="LOW_EFFECTIVENESS",
                    target=narrative_id,
                    reason=f"Narrative has {progress.coverage:.0%} coverage but only {progress.effective_progress:.0%} effective progress",
                    priority=Priority.MEDIUM
                ))

        return sorted(actions, key=lambda a: a.priority.value, reverse=True)


# =============================================================================
# GAP-TO-QUERY GENERATOR
# =============================================================================

@dataclass
class GeneratedQuery:
    """A query generated from a gap."""
    syntax: str                              # Actual SASTRE syntax (e.g., "p: John Smith")
    intent: str                              # discover_subject, enrich_subject, etc.
    quadrant: str                            # verify, trace, extract, discover
    source_gap: Gap                          # Original gap this addresses
    priority: int                            # Execution priority (higher = sooner)
    variations: List[str] = field(default_factory=list)  # Alternative phrasings
    io_module: Optional[str] = None          # Suggested IO module
    expected_yield: str = ""                 # What we expect to get


class GapQueryGenerator:
    """
    Converts grid assessment gaps into executable SASTRE syntax queries.

    Uses:
    - Entity type to select prefix (p:, c:, e:, d:, t:)
    - K-U quadrant to shape query strategy
    - Slot hunger to prioritize fields
    - Cross-pollination to combine insights
    """

    # Entity type → IO prefix mapping
    PREFIX_MAP = {
        "person": "p:",
        "company": "c:",
        "email": "e:",
        "domain": "d:",
        "phone": "t:",
        "address": "a:",
    }

    # Gap type → query strategy mapping
    GAP_STRATEGIES = {
        "NARRATIVE_UNANSWERED": "discover",      # Need to find new info
        "NARRATIVE_PARTIAL": "enrich",           # Need to fill remaining
        "ENTITY_CORE_INCOMPLETE": "enrich",      # Need core attributes
        "ENTITY_SHELL_INCOMPLETE": "enrich",     # Need shell attributes
        "ENTITY_COLLISION": "disambiguate",      # Need wedge queries
        "LOCATION_UNCHECKED": "trace",           # Need to check location
        "NEXUS_UNCONFIRMED": "verify",           # Need to confirm edge
    }

    # Field → IO route mapping (which module fills which field)
    FIELD_ROUTES = {
        # Person fields
        "email": ("eye-d", "breachdb"),
        "phone": ("eye-d", "socialmedia"),
        "address": ("corporella", "registry"),
        "dob": ("corporella", "registry"),
        "employer": ("linklater", "linkedin"),
        "aliases": ("linklater", "news"),
        # Company fields
        "registration_number": ("torpedo", "registry"),
        "officers": ("corporella", "registry"),
        "shareholders": ("corporella", "registry"),
        "beneficial_owners": ("corporella", "registry"),
        "status": ("torpedo", "registry"),
        # Domain fields
        "registrant": ("linklater", "whois"),
        "backlinks": ("linklater", "seo"),
    }

    def __init__(self, state: InvestigationState):
        self.state = state

    def generate_from_assessment(self, assessment: GridAssessment) -> List[GeneratedQuery]:
        """
        Generate queries from all gaps in an assessment.

        Returns queries sorted by priority (highest first).
        """
        queries = []

        # Generate from narrative gaps
        for gap in assessment.narrative.gaps:
            queries.extend(self._generate_from_narrative_gap(gap))

        # Generate from subject gaps
        for gap in assessment.subject.gaps:
            queries.extend(self._generate_from_subject_gap(gap))

        # Generate from location gaps
        for gap in assessment.location.gaps:
            queries.extend(self._generate_from_location_gap(gap))

        # Generate from nexus gaps
        for gap in assessment.nexus.gaps:
            queries.extend(self._generate_from_nexus_gap(gap))

        # Generate from cross-pollination actions
        for action in assessment.cross_pollinated:
            queries.extend(self._generate_from_cross_pollination(action))

        # Sort by priority
        return sorted(queries, key=lambda q: q.priority, reverse=True)

    def _generate_from_narrative_gap(self, gap: Gap) -> List[GeneratedQuery]:
        """Generate queries for a narrative gap."""
        queries = []
        narrative_id = gap.target
        narrative = self.state.narrative_items.get(narrative_id)

        if not narrative:
            return queries

        question = narrative.question

        # Extract entities mentioned in the question
        entities = self._extract_entities_from_text(question)

        if not entities:
            # No entities found - do a broad search
            queries.append(GeneratedQuery(
                syntax=f'"{question}"',
                intent="discover_subject",
                quadrant="discover",
                source_gap=gap,
                priority=gap.priority.value * 10,
                variations=[f'"{question}" site:linkedin.com', f'"{question}" filetype:pdf'],
                expected_yield="Documents mentioning the question terms"
            ))
        else:
            # Generate targeted queries for each entity
            for entity_name, entity_type in entities:
                prefix = self.PREFIX_MAP.get(entity_type, "p:")
                syntax = f"{prefix} {entity_name}"

                queries.append(GeneratedQuery(
                    syntax=syntax,
                    intent="discover_subject" if gap.type == "NARRATIVE_UNANSWERED" else "enrich_subject",
                    quadrant="trace" if gap.type == "NARRATIVE_UNANSWERED" else "verify",
                    source_gap=gap,
                    priority=gap.priority.value * 10 + 5,
                    io_module="eye-d" if entity_type in ["person", "email"] else "corporella",
                    variations=self._generate_variations(entity_name, entity_type),
                    expected_yield=f"Profile data for {entity_name}"
                ))

        return queries

    def _generate_from_subject_gap(self, gap: Gap) -> List[GeneratedQuery]:
        """Generate queries for a subject (entity) gap."""
        queries = []
        entity_id = gap.target
        entity = self.state.entities.get(entity_id)

        if not entity:
            return queries

        entity_type = entity.entity_type
        prefix = self.PREFIX_MAP.get(entity_type, "p:")

        if gap.type == "ENTITY_CORE_INCOMPLETE":
            # Need core fields - direct IO lookup
            syntax = f"{prefix} {entity.name}"

            queries.append(GeneratedQuery(
                syntax=syntax,
                intent="enrich_subject",
                quadrant="verify",
                source_gap=gap,
                priority=100,  # Core = highest priority
                io_module=self._get_io_module_for_type(entity_type),
                variations=[],
                expected_yield=f"Core attributes (identifiers, dates)"
            ))

            # If we have partial data, use it to narrow
            if entity.core.get("jurisdiction"):
                jurisdiction = entity.core["jurisdiction"].value
                queries.append(GeneratedQuery(
                    syntax=f"{prefix} {entity.name} => registry:{jurisdiction}",
                    intent="enrich_subject",
                    quadrant="verify",
                    source_gap=gap,
                    priority=95,
                    io_module="torpedo",
                    expected_yield=f"Official registry data from {jurisdiction}"
                ))

        elif gap.type == "ENTITY_SHELL_INCOMPLETE":
            # Need shell fields - targeted enrichment
            missing_fields = self._get_missing_shell_fields(entity)

            for field_name in missing_fields[:3]:  # Top 3 missing fields
                route = self.FIELD_ROUTES.get(field_name)
                if route:
                    io_module, source_type = route
                    syntax = f"{prefix} {entity.name} => {io_module}"

                    queries.append(GeneratedQuery(
                        syntax=syntax,
                        intent="enrich_subject",
                        quadrant="trace",
                        source_gap=gap,
                        priority=70 - missing_fields.index(field_name) * 5,
                        io_module=io_module,
                        expected_yield=f"Field: {field_name}"
                    ))

        elif gap.type == "ENTITY_COLLISION":
            # Need disambiguation - generate wedge queries
            queries.extend(self._generate_wedge_queries(entity, gap))

        return queries

    def _generate_from_location_gap(self, gap: Gap) -> List[GeneratedQuery]:
        """Generate queries for a location gap."""
        queries = []
        jurisdiction = gap.target

        # Get entities that should appear in this jurisdiction
        entities_in_jurisdiction = [
            e for e in self.state.entities.values()
            if e.shell.get("jurisdiction", {}).get("value") == jurisdiction
        ]

        if entities_in_jurisdiction:
            # Check each entity against this jurisdiction's sources
            for entity in entities_in_jurisdiction[:5]:  # Top 5
                prefix = self.PREFIX_MAP.get(entity.entity_type, "p:")
                syntax = f"{prefix} {entity.name} => registry:{jurisdiction}"

                queries.append(GeneratedQuery(
                    syntax=syntax,
                    intent="trace",
                    quadrant="trace",
                    source_gap=gap,
                    priority=60,
                    io_module="torpedo",
                    expected_yield=f"Registry presence in {jurisdiction}"
                ))
        else:
            # No specific entities - general jurisdiction scan
            queries.append(GeneratedQuery(
                syntax=f"registry:{jurisdiction} scan",
                intent="discover_location",
                quadrant="extract",
                source_gap=gap,
                priority=40,
                expected_yield=f"All entities from {jurisdiction} registry"
            ))

        return queries

    def _generate_from_nexus_gap(self, gap: Gap) -> List[GeneratedQuery]:
        """Generate queries for a connection gap."""
        queries = []

        if gap.type == "NEXUS_UNCONFIRMED":
            source_id, target_id = gap.target
            source_entity = self.state.entities.get(source_id)
            target_entity = self.state.entities.get(target_id)

            if source_entity and target_entity:
                # Search for both names together
                syntax = f'"{source_entity.name}" AND "{target_entity.name}"'

                queries.append(GeneratedQuery(
                    syntax=syntax,
                    intent="verify",
                    quadrant="verify",
                    source_gap=gap,
                    priority=80,  # Connection verification = high priority
                    variations=[
                        f'"{source_entity.name}" "{target_entity.name}" site:linkedin.com',
                        f'"{source_entity.name}" "{target_entity.name}" filetype:pdf',
                    ],
                    expected_yield="Documents showing both entities together"
                ))

                # Also check if this is a surprising AND
                queries.append(GeneratedQuery(
                    syntax=f'"{source_entity.name}" =? "{target_entity.name}"',
                    intent="compare",
                    quadrant="verify",
                    source_gap=gap,
                    priority=75,
                    expected_yield="Similarity assessment"
                ))

        return queries

    def _generate_from_cross_pollination(self, action: CrossPollinatedAction) -> List[GeneratedQuery]:
        """Generate queries from cross-pollination insights."""
        queries = []

        if action.from_mode == "SUBJECT" and action.to_mode == "LOCATION":
            # Entity implies jurisdiction to check
            # Parse the action text to extract details
            match = re.search(r"Entity (.+?) implies jurisdiction (.+)", action.insight)
            if match:
                entity_name, jurisdiction = match.groups()
                syntax = f'"{entity_name}" site:.{jurisdiction.lower()}'

                queries.append(GeneratedQuery(
                    syntax=syntax,
                    intent="trace",
                    quadrant="trace",
                    source_gap=Gap(
                        type="CROSS_POLLINATED",
                        target=action.action,
                        description=action.insight,
                        priority=action.priority,
                        suggested_action=action.action
                    ),
                    priority=action.priority.value * 10,
                    variations=[f'"{entity_name}" registry:{jurisdiction}'],
                    expected_yield=f"Results from {jurisdiction} domain"
                ))

        elif action.from_mode == "LOCATION" and action.to_mode == "SUBJECT":
            # Source has results but no entities extracted
            match = re.search(r"Source (.+?) has results", action.insight)
            if match:
                source_name = match.groups()[0]

                queries.append(GeneratedQuery(
                    syntax=f"extract: {source_name}",
                    intent="extract",
                    quadrant="extract",
                    source_gap=Gap(
                        type="CROSS_POLLINATED",
                        target=action.action,
                        description=action.insight,
                        priority=action.priority,
                        suggested_action=action.action
                    ),
                    priority=action.priority.value * 10,
                    io_module="eye-d",
                    expected_yield="Extracted entities from source"
                ))

        return queries

    def _generate_wedge_queries(self, entity: Entity, gap: Gap) -> List[GeneratedQuery]:
        """Generate wedge queries for disambiguation."""
        queries = []

        # Get collision flags to understand what's conflicting
        for collision_type in entity.collision_flags:
            if collision_type == "name_collision":
                # Same name, need to differentiate
                # Use temporal wedge
                queries.append(GeneratedQuery(
                    syntax=f'"{entity.name}" :2020!',
                    intent="disambiguate",
                    quadrant="verify",
                    source_gap=gap,
                    priority=90,
                    expected_yield="Temporal context for disambiguation"
                ))

                # Use geographic wedge if we have jurisdiction
                if entity.shell.get("jurisdiction"):
                    jur = entity.shell["jurisdiction"].value
                    queries.append(GeneratedQuery(
                        syntax=f'"{entity.name}" {jur}!',
                        intent="disambiguate",
                        quadrant="verify",
                        source_gap=gap,
                        priority=85,
                        expected_yield="Geographic context for disambiguation"
                    ))

                # Use identifier wedge if we have partial identifiers
                if entity.core.get("registration_number"):
                    reg = entity.core["registration_number"].value
                    queries.append(GeneratedQuery(
                        syntax=f'"{reg}"',
                        intent="disambiguate",
                        quadrant="verify",
                        source_gap=gap,
                        priority=95,
                        expected_yield="Identifier-based disambiguation"
                    ))

        return queries

    def _extract_entities_from_text(self, text: str) -> List[Tuple[str, str]]:
        """Extract potential entity names and types from text."""
        entities = []

        # Look for quoted strings
        quoted = re.findall(r'"([^"]+)"', text)
        for q in quoted:
            entity_type = self._infer_entity_type(q)
            entities.append((q, entity_type))

        # Look for capitalized phrases (potential names)
        caps = re.findall(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b', text)
        for c in caps:
            if c not in [e[0] for e in entities]:
                entity_type = self._infer_entity_type(c)
                entities.append((c, entity_type))

        # Look for known patterns
        emails = re.findall(r'\b[\w.-]+@[\w.-]+\.\w+\b', text)
        for e in emails:
            entities.append((e, "email"))

        domains = re.findall(r'\b(?:www\.)?[\w-]+\.(?:com|org|net|io|co)\b', text)
        for d in domains:
            entities.append((d, "domain"))

        return entities

    def _infer_entity_type(self, name: str) -> str:
        """Infer entity type from name patterns."""
        name_lower = name.lower()

        # Company indicators
        company_suffixes = ["ltd", "inc", "corp", "gmbh", "llc", "plc", "ag", "sa", "bv", "d.d.", "d.o.o."]
        if any(suffix in name_lower for suffix in company_suffixes):
            return "company"

        # Email
        if "@" in name:
            return "email"

        # Domain
        if "." in name and " " not in name:
            return "domain"

        # Default to person
        return "person"

    def _get_io_module_for_type(self, entity_type: str) -> str:
        """Get the primary IO module for an entity type."""
        mapping = {
            "person": "eye-d",
            "email": "eye-d",
            "company": "corporella",
            "domain": "linklater",
            "phone": "eye-d",
        }
        return mapping.get(entity_type, "eye-d")

    def _get_missing_shell_fields(self, entity: Entity) -> List[str]:
        """Get list of missing shell fields for an entity, sorted by priority."""
        # Shell field priority by entity type
        shell_priority = {
            "person": ["email", "phone", "address", "employer", "occupation"],
            "company": ["status", "officers", "shareholders", "address", "website"],
            "domain": ["registrant", "registrar", "creation_date", "backlinks"],
        }

        priority_list = shell_priority.get(entity.entity_type, [])
        missing = [f for f in priority_list if f not in entity.shell or not entity.shell[f].value]
        return missing

    def _generate_variations(self, name: str, entity_type: str) -> List[str]:
        """Generate query variations for an entity."""
        variations = []
        prefix = self.PREFIX_MAP.get(entity_type, "p:")

        # Site-specific variations
        if entity_type == "person":
            variations.extend([
                f'{prefix} {name} site:linkedin.com',
                f'{prefix} {name} site:facebook.com',
                f'"{name}" filetype:pdf',
            ])
        elif entity_type == "company":
            variations.extend([
                f'{prefix} {name} site:opencorporates.com',
                f'{prefix} {name} filetype:pdf annual report',
                f'"{name}" officers directors',
            ])

        return variations


# =============================================================================
# QUERY BATCH BUILDER
# =============================================================================

def build_query_batch(
    assessment: GridAssessment,
    state: InvestigationState,
    max_queries: int = 10
) -> List[GeneratedQuery]:
    """
    Build an optimized batch of queries from an assessment.

    Deduplicates, prioritizes, and limits to max_queries.
    """
    generator = GapQueryGenerator(state)
    all_queries = generator.generate_from_assessment(assessment)

    # Deduplicate by syntax
    seen_syntax = set()
    unique_queries = []
    for q in all_queries:
        if q.syntax not in seen_syntax:
            seen_syntax.add(q.syntax)
            unique_queries.append(q)

    # Take top N by priority
    return unique_queries[:max_queries]