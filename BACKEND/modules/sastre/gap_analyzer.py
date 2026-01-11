"""
SASTRE Gap Analyzer - Cognitive Framework for Investigation Gap Detection

THE GRID AS THE SYSTEM'S BRAIN

The Gap Analyzer doesn't just "find missing fields." It THINKS using the Four Centricities
as cognitive modes, rotating through them rapidly to discover different gap types.

COGNITIVE ROTATION:
├── NARRATIVE MODE: "What story are we building? What gaps prevent coherence?"
├── SUBJECT MODE: "What entities do we have? What slots are empty?"
├── LOCATION MODE: "What terrain have we defined? What sources unchecked?"
└── NEXUS MODE: "What connections exist? What's suspiciously unconnected?"

Each rotation reveals different gaps. The system cycles through rapidly, not linearly.

K-U MATRIX (embedded within rotation):
- VERIFY: Known Subject + Known Location -> Confirm what we think
- TRACE: Known Subject + Unknown Location -> Find where subject appears
- EXTRACT: Unknown Subject + Known Location -> Find what's in location
- DISCOVER: Unknown Subject + Unknown Location -> Explore frontier

3D COORDINATE SYSTEM for gap location:
- SUBJECT axis (Y): Which entity? What attribute?
- LOCATION axis (X): Which facet? (GEO, TEMPORAL, SOURCE, FORMAT...)
- NEXUS axis (Z): What connection type? CERTAIN or UNCERTAIN?
- NARRATIVE layer: What intent? Why does this matter?
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
import uuid
import logging

from .contracts import (
    Gap, Query, Section, Document, Entity,
    KUQuadrant, Intent, AbsenceType,
    CognitiveMode, Dimension,
    GapCoordinates, CrossPollinationAction, DimensionalGap, CorpusHit,
    CognitiveAnalysisLog, GapAnalyzerOutput, SufficiencyResult,
    UnifiedSlot, SlotType, SlotOrigin, SlotTarget, SlotState, SlotPriority,
)
# EntityClass doesn't exist in schema_reader - only get_schema_reader is used
from .core.schema_reader import get_schema_reader

logger = logging.getLogger(__name__)


# =============================================================================
# K-U MATRIX CLASSIFICATION (unchanged but integrated)
# =============================================================================

def classify_gap(gap: Gap) -> KUQuadrant:
    """Classify gap into K-U Matrix quadrant based on what's known."""
    has_subject = gap.target_subject is not None and len(gap.target_subject) > 0
    has_location = gap.target_location is not None and len(gap.target_location) > 0

    if has_subject and has_location:
        return KUQuadrant.VERIFY
    elif has_subject and not has_location:
        return KUQuadrant.TRACE
    elif not has_subject and has_location:
        return KUQuadrant.EXTRACT
    else:
        return KUQuadrant.DISCOVER


def assign_intent(gap: Gap) -> Intent:
    """Assign binary intent to gap."""
    is_discovery = gap.is_looking_for_new_entities
    target_is_subject = gap.target_subject is not None or not gap.target_location

    if is_discovery:
        return Intent.DISCOVER_SUBJECT if target_is_subject else Intent.DISCOVER_LOCATION
    else:
        return Intent.ENRICH_SUBJECT if target_is_subject else Intent.ENRICH_LOCATION


# =============================================================================
# ABSENCE HIERARCHY - Dynamic field lists from CYMONIDES schema
# =============================================================================

def _get_expected_fields(entity_type: str) -> List[str]:
    """Get expected (required) fields for an entity type from the schema."""
    schema_reader = get_schema_reader()
    type_def = schema_reader.get_entity_type(entity_type)
    if not type_def:
        logger.warning(f"Unknown entity type: {entity_type}")
        return []
    return [p.name for p in type_def.required_properties]


def _get_possible_fields(entity_type: str) -> List[str]:
    """Get possible (optional) fields for an entity type from the schema."""
    schema_reader = get_schema_reader()
    type_def = schema_reader.get_entity_type(entity_type)
    if not type_def:
        return []
    return [p.name for p in type_def.optional_properties]


def get_absence_type(field: str, entity_type: str) -> AbsenceType:
    """Determine priority of a missing field based on expectedness."""
    expected = _get_expected_fields(entity_type)
    possible = _get_possible_fields(entity_type)
    field_lower = field.lower()

    if any(f in field_lower for f in expected):
        return AbsenceType.EXPECTED_NOT_FOUND
    elif any(f in field_lower for f in possible):
        return AbsenceType.POSSIBLE_NOT_FOUND
    else:
        return AbsenceType.RARE_NOT_FOUND


def calculate_priority(gap: Gap) -> int:
    """Calculate gap priority (0-100, higher = more important)."""
    base = 50

    if gap.absence_type == AbsenceType.EXPECTED_NOT_FOUND:
        base += 30
    elif gap.absence_type == AbsenceType.POSSIBLE_NOT_FOUND:
        base += 15

    if gap.k_u_quadrant == KUQuadrant.VERIFY:
        base += 20
    elif gap.k_u_quadrant == KUQuadrant.TRACE:
        base += 10
    elif gap.k_u_quadrant == KUQuadrant.EXTRACT:
        base += 5

    if gap.intent in [Intent.ENRICH_SUBJECT, Intent.ENRICH_LOCATION]:
        base += 5

    return min(100, max(0, base))


def _slot_type_for_mode(mode: Optional[CognitiveMode]) -> SlotType:
    """Map cognitive mode to unified slot type."""
    return {
        CognitiveMode.SUBJECT: SlotType.ATTRIBUTE,
        CognitiveMode.LOCATION: SlotType.COVERAGE,
        CognitiveMode.NEXUS: SlotType.RELATIONSHIP,
        CognitiveMode.NARRATIVE: SlotType.NARRATIVE,
    }.get(mode, SlotType.NARRATIVE)


def _slot_state_for_gap(gap: Gap) -> SlotState:
    """Infer slot state from gap attributes."""
    if gap.absence_type in (AbsenceType.INCOMPLETE, AbsenceType.UNVERIFIED, AbsenceType.STALE):
        return SlotState.PARTIAL
    if gap.absence_type == AbsenceType.NOT_APPLICABLE:
        return SlotState.VOID
    return SlotState.EMPTY


def _slot_priority_from_score(score: int) -> SlotPriority:
    """Map numeric priority to slot priority bucket."""
    if score >= 80:
        return SlotPriority.CRITICAL
    if score >= 70:
        return SlotPriority.HIGH
    if score >= 50:
        return SlotPriority.MEDIUM
    return SlotPriority.LOW


def _gap_to_unified_slot(gap: Gap) -> UnifiedSlot:
    """Convert a gap into a unified slot for the gap view."""
    slot_type = _slot_type_for_mode(gap.discovered_by_mode)
    target = {
        SlotType.ATTRIBUTE: SlotTarget.SUBJECT,
        SlotType.COVERAGE: SlotTarget.LOCATION,
        SlotType.RELATIONSHIP: SlotTarget.NEXUS,
        SlotType.NARRATIVE: SlotTarget.NARRATIVE,
    }.get(slot_type, SlotTarget.NARRATIVE)

    coordinates = {}
    if gap.coordinates:
        coordinates = {
            "subject": {
                "entity_name": gap.coordinates.subject_entity,
                "entity_type": gap.coordinates.subject_type,
                "attribute": getattr(gap.coordinates, "subject_attribute", None),
            },
            "location": {
                "domain": gap.coordinates.location_domain,
                "jurisdiction": gap.coordinates.location_jurisdiction,
                "source_type": getattr(gap.coordinates, "location_source", None),
                "format_type": getattr(gap.coordinates, "location_format", None),
            },
            "nexus": {
                "connection_type": getattr(gap.coordinates, "nexus_connection_type", None),
            },
            "narrative_intent": getattr(gap.coordinates, "narrative_intent", None),
        }

    return UnifiedSlot(
        slot_id=gap.id,
        slot_type=slot_type,
        origin=SlotOrigin.AGENT,
        target=target,
        description=gap.description,
        state=_slot_state_for_gap(gap),
        priority=_slot_priority_from_score(gap.priority),
        entity_id=None,
        entity_type=gap.coordinates.subject_type if gap.coordinates else None,
        field_name=getattr(gap.coordinates, "subject_attribute", None) if gap.coordinates else None,
        relationship_type=getattr(gap.coordinates, "nexus_connection_type", None) if gap.coordinates else None,
        jurisdiction=gap.coordinates.location_jurisdiction if gap.coordinates else None,
        domain=gap.coordinates.location_domain if gap.coordinates else None,
        narrative_section=gap.target_section,
        coordinates=coordinates,
        metadata={
            "priority_score": gap.priority,
            "k_u_quadrant": gap.k_u_quadrant.value if gap.k_u_quadrant else None,
            "intent": gap.intent.value if gap.intent else None,
            "is_looking_for_new_entities": gap.is_looking_for_new_entities,
        },
    )


# =============================================================================
# COGNITIVE GAP ANALYZER - The Brain
# =============================================================================

class CognitiveGapAnalyzer:
    """
    The system's BRAIN that rotates through four cognitive modes.

    Implements:
    1. Four cognitive mode rotation (centricities)
    2. Cross-pollination between views
    3. 3D coordinate system for gap location
    4. Corpus check for unknown knowns
    5. Dimensional analysis (correlate/contrast)
    6. Four-way fused query construction
    """

    def __init__(self, corpus_client=None, graph_client=None):
        """
        Initialize with optional corpus and graph clients.

        Args:
            corpus_client: Client for WDC/Cymonides corpus queries
            graph_client: Client for entity graph queries
        """
        self.corpus_client = corpus_client
        self.graph_client = graph_client
        self.known_subjects: List[str] = []
        self.known_locations: List[str] = []
        self.known_entities: List[Entity] = []
        self.cognitive_log: List[CognitiveAnalysisLog] = []

    def analyze(self, document: Document) -> GapAnalyzerOutput:
        """
        Full cognitive analysis producing contract output.

        THE ROTATING GAP-ANALYZER ALGORITHM:
        1. Rotate through four cognitive modes
        2. Check corpus for unknown knowns
        3. Run dimensional analysis
        4. Cross-pollinate insights
        5. Locate gaps in coordinate space
        6. Construct four-way fused queries
        7. Check sufficiency
        """
        all_gaps: List[Gap] = []
        self.cognitive_log = []

        # Build knowledge base
        self._build_knowledge_base(document)

        # ===== COGNITIVE ROTATION =====
        for mode in [CognitiveMode.NARRATIVE, CognitiveMode.SUBJECT,
                     CognitiveMode.LOCATION, CognitiveMode.NEXUS]:
            mode_gaps, log_entry = self._analyze_in_mode(document, mode)
            all_gaps.extend(mode_gaps)
            self.cognitive_log.append(log_entry)
            logger.info(f"Mode {mode.value}: found {len(mode_gaps)} gaps")

        # ===== UNKNOWN KNOWNS CHECK =====
        unknown_knowns_count = 0
        if self.corpus_client:
            for gap in all_gaps:
                hits = self._check_corpus(gap)
                if hits:
                    gap.corpus_checked = True
                    gap.corpus_hits = hits
                    unknown_knowns_count += len(hits)
                    logger.info(f"Gap {gap.id}: found {len(hits)} corpus hits")

        # ===== DIMENSIONAL ANALYSIS =====
        dimensional_gaps = self._dimensional_analysis(document, all_gaps)
        # Note: dimensional_gaps are kept separate (different type than Gap)

        # ===== CROSS-POLLINATION =====
        cross_actions = self._cross_pollinate(all_gaps)
        for gap in all_gaps:
            relevant_actions = [a for a in cross_actions
                                if gap.discovered_by_mode == a.source_mode]
            gap.cross_pollination_actions = relevant_actions

        # ===== LOCATE IN COORDINATE SPACE =====
        for gap in all_gaps:
            gap.coordinates = self._locate_gap(gap, document)

        # ===== CLASSIFY AND PRIORITIZE =====
        for gap in all_gaps:
            gap.k_u_quadrant = classify_gap(gap)
            gap.intent = assign_intent(gap)
            gap.priority = calculate_priority(gap)

        # Sort by priority
        all_gaps.sort(key=lambda g: g.priority, reverse=True)

        # ===== GENERATE QUERIES =====
        queries = []
        for gap in all_gaps[:10]:  # Top 10 priority gaps
            gap_queries = self._generate_fused_queries(gap)
            queries.extend(gap_queries)

        # ===== SUFFICIENCY CHECK =====
        from .sufficiency import check_sufficiency
        sufficiency = check_sufficiency(document)

        slots = [_gap_to_unified_slot(gap) for gap in all_gaps]

        return GapAnalyzerOutput(
            next_queries=queries,
            disambiguation_queries=[],
            sufficiency=sufficiency,
            all_gaps=all_gaps,
            cognitive_log=self.cognitive_log,
            corpus_checked=bool(self.corpus_client),
            unknown_knowns_found=unknown_knowns_count,
            dimensional_gaps=dimensional_gaps,
            cross_pollination_actions=cross_actions,
            slots=slots,
            total_gaps=len(all_gaps),
            priority_gaps=len([g for g in all_gaps if g.priority >= 70]),
        )

    # =========================================================================
    # COGNITIVE MODE IMPLEMENTATIONS
    # =========================================================================

    def _analyze_in_mode(self, document: Document, mode: CognitiveMode
                         ) -> Tuple[List[Gap], CognitiveAnalysisLog]:
        """
        Analyze document from one cognitive perspective.
        Each mode asks different questions and reveals different gaps.
        """
        gaps = []
        insights = []
        cross_actions = []

        if mode == CognitiveMode.NARRATIVE:
            gaps, insights, cross_actions = self._narrative_mode(document)
        elif mode == CognitiveMode.SUBJECT:
            gaps, insights, cross_actions = self._subject_mode(document)
        elif mode == CognitiveMode.LOCATION:
            gaps, insights, cross_actions = self._location_mode(document)
        elif mode == CognitiveMode.NEXUS:
            gaps, insights, cross_actions = self._nexus_mode(document)

        # Tag all gaps with discovering mode
        for gap in gaps:
            gap.discovered_by_mode = mode

        log = CognitiveAnalysisLog(
            mode=mode.value if hasattr(mode, 'value') else str(mode),
            gaps_found=len(gaps),
            entities_analyzed=len(document.known_entities) if document.known_entities else 0,
            cross_pollinations=len(cross_actions),
        )

        return gaps, log

    def _narrative_mode(self, document: Document
                        ) -> Tuple[List[Gap], List[str], List[CrossPollinationAction]]:
        """
        NARRATIVE-CENTRIC THINKING:
        - "What story are we building?"
        - "What gaps prevent the story from being coherent?"
        - "What would a reader ask that we can't answer?"
        """
        gaps = []
        insights = []
        cross_actions = []

        # Check tasking alignment
        tasking_keywords = self._extract_keywords(document.tasking)
        addressed_keywords = set()

        for section in document.sections:
            section_keywords = self._extract_keywords(section.header + " " + section.content)
            addressed_keywords.update(section_keywords & tasking_keywords)

            # Check for incomplete sections
            if section.state in ['empty', 'incomplete']:
                gap = Gap(
                    id=f"narrative_{uuid.uuid4().hex[:8]}",
                    description=f"Story gap: '{section.header}' not addressed",
                    target_section=section.header,
                    k_u_quadrant=KUQuadrant.TRACE,
                    intent=Intent.ENRICH_SUBJECT,
                )
                gaps.append(gap)

        # Find unaddressed tasking elements
        unaddressed = tasking_keywords - addressed_keywords
        for keyword in unaddressed:
            insights.append(f"Tasking element '{keyword}' not addressed in document")
            # Generate cross-pollination to SUBJECT mode
            cross_actions.append(CrossPollinationAction(
                source_mode=CognitiveMode.NARRATIVE.value,
                target_mode=CognitiveMode.SUBJECT.value,
                description=f"Check if '{keyword}' relates to known entities (unaddressed tasking)",
                priority=70,
            ))

        # Check for unanswered reader questions
        reader_questions = self._generate_reader_questions(document)
        for question in reader_questions:
            if not self._question_answered(question, document):
                gap = Gap(
                    id=f"reader_{uuid.uuid4().hex[:8]}",
                    description=f"Reader would ask: {question}",
                    target_section="## Unanswered Questions",
                    k_u_quadrant=KUQuadrant.DISCOVER,
                    intent=Intent.DISCOVER_SUBJECT,
                    is_looking_for_new_entities=True,
                )
                gaps.append(gap)
                insights.append(f"Unanswered question: {question}")

        return gaps, insights, cross_actions

    def _subject_mode(self, document: Document
                      ) -> Tuple[List[Gap], List[str], List[CrossPollinationAction]]:
        """
        SUBJECT-CENTRIC THINKING:
        - "What entities do we have?"
        - "What slots are empty in their profiles?"
        - "What enrichment routes exist for each entity type?"
        """
        gaps = []
        insights = []
        cross_actions = []

        for entity in document.known_entities:
            entity_type = entity.entity_type

            # Check expected fields (from schema)
            expected = _get_expected_fields(entity_type)
            for field in expected:
                if not self._entity_has_field(entity, field):
                    gap = Gap(
                        id=f"subject_{uuid.uuid4().hex[:8]}",
                        description=f"Missing {field} for {entity.name}",
                        target_section=f"## {entity.name}",
                        k_u_quadrant=KUQuadrant.TRACE,
                        intent=Intent.ENRICH_SUBJECT,
                        target_subject=entity.name,
                        absence_type=AbsenceType.EXPECTED_NOT_FOUND,
                    )
                    gaps.append(gap)

            # Check possible fields (from schema)
            possible = _get_possible_fields(entity_type)
            for field in possible:
                if not self._entity_has_field(entity, field):
                    gap = Gap(
                        id=f"subject_{uuid.uuid4().hex[:8]}",
                        description=f"No {field} for {entity.name}",
                        target_section=f"## {entity.name}",
                        k_u_quadrant=KUQuadrant.TRACE,
                        intent=Intent.ENRICH_SUBJECT,
                        target_subject=entity.name,
                        absence_type=AbsenceType.POSSIBLE_NOT_FOUND,
                    )
                    gaps.append(gap)

            # Generate cross-pollination to LOCATION mode
            if entity_type == 'company':
                jurisdiction = entity.attributes.core.get('jurisdiction')
                if jurisdiction:
                    cross_actions.append(CrossPollinationAction(
                        source_mode=CognitiveMode.SUBJECT.value,
                        target_mode=CognitiveMode.LOCATION.value,
                        description=f"Check {jurisdiction} registry for {entity.name}",
                        priority=80,
                    ))
                    insights.append(f"Entity {entity.name} implies location: {jurisdiction}")

        return gaps, insights, cross_actions

    def _location_mode(self, document: Document
                       ) -> Tuple[List[Gap], List[str], List[CrossPollinationAction]]:
        """
        LOCATION-CENTRIC THINKING:
        - "What terrain have we defined?"
        - "What sources exist that we haven't checked?"
        - "What jurisdictions are implied but unexplored?"
        """
        gaps = []
        insights = []
        cross_actions = []

        # Extract mentioned locations/jurisdictions
        mentioned_locations = self._extract_locations(document)
        checked_locations = set()

        # Check which locations have been searched
        for section in document.sections:
            watcher_meta = section.watcher_meta
            if watcher_meta and 'sources_searched' in watcher_meta:
                checked_locations.update(watcher_meta['sources_searched'])

        # Find unchecked locations
        for location in mentioned_locations:
            if location not in checked_locations:
                gap = Gap(
                    id=f"location_{uuid.uuid4().hex[:8]}",
                    description=f"Location mentioned but not searched: {location}",
                    target_section="## Sources",
                    k_u_quadrant=KUQuadrant.EXTRACT,
                    intent=Intent.DISCOVER_SUBJECT,
                    target_location=location,
                    is_looking_for_new_entities=True,
                )
                gaps.append(gap)
                insights.append(f"Unchecked location: {location}")

                # Cross-pollinate to SUBJECT mode
                cross_actions.append(CrossPollinationAction(
                    source_mode=CognitiveMode.LOCATION.value,
                    target_mode=CognitiveMode.SUBJECT.value,
                    description=f"Extract entities from {location}",
                    priority=75,
                ))

        # Check for implied jurisdictions from company names
        for entity in document.known_entities:
            if entity.entity_type == 'company':
                implied_jurisdictions = self._infer_jurisdictions(entity.name)
                for jur in implied_jurisdictions:
                    if jur not in checked_locations:
                        gap = Gap(
                            id=f"implied_jur_{uuid.uuid4().hex[:8]}",
                            description=f"Implied jurisdiction not checked: {jur}",
                            target_section=f"## {entity.name}",
                            k_u_quadrant=KUQuadrant.VERIFY,
                            intent=Intent.ENRICH_SUBJECT,
                            target_subject=entity.name,
                            target_location=jur,
                        )
                        gaps.append(gap)

        return gaps, insights, cross_actions

    def _nexus_mode(self, document: Document
                    ) -> Tuple[List[Gap], List[str], List[CrossPollinationAction]]:
        """
        NEXUS-CENTRIC THINKING:
        - "What connections exist?"
        - "What's suspiciously unconnected?"
        - "What SHOULD connect but doesn't?"
        """
        gaps = []
        insights = []
        cross_actions = []

        entities = document.known_entities
        if len(entities) < 2:
            return gaps, insights, cross_actions

        # Build connection map
        connected_pairs: Set[Tuple[str, str]] = set()
        for edge in getattr(document, 'edges', []):
            connected_pairs.add((edge.source_id, edge.target_id))
            connected_pairs.add((edge.target_id, edge.source_id))

        # Check for expected connections that don't exist
        for i, entity_a in enumerate(entities):
            for entity_b in entities[i+1:]:
                pair = (entity_a.id, entity_b.id)
                reverse_pair = (entity_b.id, entity_a.id)

                # Same jurisdiction implies possible connection
                jur_a = entity_a.attributes.core.get('jurisdiction') if entity_a.attributes else None
                jur_b = entity_b.attributes.core.get('jurisdiction') if entity_b.attributes else None

                if jur_a and jur_b and jur_a == jur_b:
                    if pair not in connected_pairs and reverse_pair not in connected_pairs:
                        gap = Gap(
                            id=f"nexus_{uuid.uuid4().hex[:8]}",
                            description=f"Unverified connection: {entity_a.name} ↔ {entity_b.name} (same jurisdiction: {jur_a})",
                            target_section="## Connections",
                            k_u_quadrant=KUQuadrant.VERIFY,
                            intent=Intent.ENRICH_SUBJECT,
                            target_subject=entity_a.name,
                            target_location=jur_a,
                        )
                        gaps.append(gap)
                        insights.append(f"Possible unverified link: {entity_a.name} - {entity_b.name}")

        # Check for surprising ANDs (unexpected connections)
        for surprising in document.surprising_ands:
            if not surprising.investigated:
                gap = Gap(
                    id=f"surprising_{uuid.uuid4().hex[:8]}",
                    description=f"Unexpected connection needs investigation: {surprising.connection}",
                    target_section="## Surprising Connections",
                    k_u_quadrant=KUQuadrant.VERIFY,
                    intent=Intent.ENRICH_SUBJECT,
                    is_looking_for_new_entities=False,
                )
                gaps.append(gap)

                # Cross-pollinate to NARRATIVE mode
                cross_actions.append(CrossPollinationAction(
                    source_mode=CognitiveMode.NEXUS.value,
                    target_mode=CognitiveMode.NARRATIVE.value,
                    description=f"Explain connection: {surprising.connection}",
                    priority=85,
                ))

        return gaps, insights, cross_actions

    # =========================================================================
    # CORPUS CHECK (Unknown Knowns)
    # =========================================================================

    def _check_corpus(self, gap: Gap) -> List[CorpusHit]:
        """
        Before searching externally, check: do we already HAVE something relevant?
        The "old lady on the corner" - she's in our data, we just didn't know she was relevant.
        """
        if not self.corpus_client:
            return []

        hits = []
        search_terms = []

        if gap.target_subject:
            search_terms.append(gap.target_subject)
        if gap.target_location:
            search_terms.append(gap.target_location)
        if gap.description:
            # Extract key nouns from description
            keywords = self._extract_keywords(gap.description)
            search_terms.extend(list(keywords)[:3])

        for term in search_terms:
            try:
                # Use CorpusChecker to search cymonides-2 and WDC indices
                from .query.corpus import CorpusChecker

                if isinstance(self.corpus_client, CorpusChecker):
                    # Use CorpusChecker's check method
                    result = self.corpus_client.check(term, limit=5)
                    hits.extend(result.hits)
                else:
                    # Legacy interface - assume it has a search method
                    results = self.corpus_client.search(term, limit=5)

                    for result in results:
                        hits.append(CorpusHit(
                            source_id=result.get('id', ''),
                            match_type=result.get('match_type', 'fuzzy'),
                            relevance=result.get('score', 0.0),
                            content_preview=result.get('preview', '')[:200],
                        ))
            except Exception as e:
                logger.warning(f"Corpus search failed for '{term}': {e}")

        return hits

    # =========================================================================
    # DIMENSIONAL ANALYSIS
    # =========================================================================

    def _dimensional_analysis(self, document: Document, existing_gaps: List[Gap]
                              ) -> List[DimensionalGap]:
        """
        Gap analysis isn't just "what's empty." It's correlation and contrast
        across dimensions: GEO, TEMPORAL, SOURCE, FORMAT, GENRE, LINK.
        """
        dimensional_gaps = []

        entities = document.known_entities
        if len(entities) < 2:
            return dimensional_gaps

        # ===== GEO DIMENSION =====
        # CORRELATE: Where do these entities BOTH appear?
        # CONTRAST: Where does A appear that B doesn't?
        geo_map: Dict[str, List[str]] = {}
        for entity in entities:
            jur = entity.attributes.core.get('jurisdiction')
            if jur:
                if jur not in geo_map:
                    geo_map[jur] = []
                geo_map[jur].append(entity.name)

        # Find jurisdictions with only one entity (contrast gap)
        for jur, entity_names in geo_map.items():
            if len(entity_names) == 1 and len(entities) > 1:
                other_entities = [e.name for e in entities if e.name not in entity_names]
                query_terms = '" OR "'.join(other_entities) if other_entities else ""
                dimensional_gaps.append(DimensionalGap(
                    gap_id=f"geo_{uuid.uuid4().hex[:8]}",
                    dimension=Dimension.SPATIAL.value,
                    description=f"Only {entity_names[0]} appears in {jur}. Check if others have presence.",
                    target_location=jur,
                    target_subject=entity_names[0] if entity_names else None,
                ))

        # ===== TEMPORAL DIMENSION =====
        # What changed between periods? Timeline gaps?
        # TODO: Implement temporal correlation when we have dated events

        # ===== SOURCE DIMENSION =====
        # Which sources mention both? Any source type unchecked?
        source_types_used: Set[str] = set()
        for section in document.sections:
            if section.watcher_meta and 'source_types' in section.watcher_meta:
                source_types_used.update(section.watcher_meta['source_types'])

        # Get all SOURCE types from schema dynamically
        schema_reader = get_schema_reader()
        # Abacus semantics: LOCATION class (storage SOURCE)
        source_types = schema_reader.get_entity_types_by_class("LOCATION")
        all_source_types = {st.type_name for st in source_types}
        unchecked_sources = all_source_types - source_types_used

        for source_type in unchecked_sources:
            dimensional_gaps.append(DimensionalGap(
                gap_id=f"src_{uuid.uuid4().hex[:8]}",
                dimension=Dimension.ATTRIBUTIVE.value,
                description=f"Source type '{source_type}' not yet checked",
                target_subject=entities[0].name if entities else None,
            ))

        return dimensional_gaps

    # =========================================================================
    # CROSS-POLLINATION
    # =========================================================================

    def _cross_pollinate(self, gaps: List[Gap]) -> List[CrossPollinationAction]:
        """
        Insights from one view reveal actions in another.
        Every view should surface actions for other views.
        """
        all_actions = []

        for gap in gaps:
            # Already collected from mode analysis
            if hasattr(gap, 'cross_pollination') and gap.cross_pollination:
                all_actions.append(gap.cross_pollination)

            # Additional cross-pollination based on gap characteristics
            if gap.discovered_by_mode == CognitiveMode.SUBJECT:
                # Subject profile gap → Location action
                if gap.target_subject and not gap.target_location:
                    all_actions.append(CrossPollinationAction(
                        source_mode=CognitiveMode.SUBJECT.value,
                        target_mode=CognitiveMode.LOCATION.value,
                        description=f"Find where '{gap.target_subject}' appears",
                        priority=60,
                    ))

            elif gap.discovered_by_mode == CognitiveMode.LOCATION:
                # Source gap → Subject extraction
                if gap.target_location and not gap.target_subject:
                    all_actions.append(CrossPollinationAction(
                        source_mode=CognitiveMode.LOCATION.value,
                        target_mode=CognitiveMode.SUBJECT.value,
                        description=f"Extract entities from '{gap.target_location}'",
                        priority=60,
                    ))

            elif gap.discovered_by_mode == CognitiveMode.NEXUS:
                # Connection gap → Narrative question
                all_actions.append(CrossPollinationAction(
                    source_mode=CognitiveMode.NEXUS.value,
                    target_mode=CognitiveMode.NARRATIVE.value,
                    description=f"Why is this connection important? {gap.description}",
                    priority=50,
                ))

        return all_actions

    # =========================================================================
    # 3D COORDINATE SYSTEM
    # =========================================================================

    def _locate_gap(self, gap: Gap, document: Document) -> GapCoordinates:
        """
        Locate gap precisely in 3D coordinate space.
        Enables targeted queries instead of broad sweeps.
        Maps to GapCoordinates contract fields.
        """
        coords = GapCoordinates()

        # SUBJECT axis - using contract fields
        coords.subject_entity = gap.target_subject
        coords.subject_type = self._infer_entity_type(gap.target_subject, document)

        # LOCATION axis - map to contract fields
        coords.location_jurisdiction = gap.target_location
        coords.location_domain = self._infer_source_type(gap)
        coords.temporal_range = self._infer_temporal(gap, document)

        # NARRATIVE layer - using contract field
        coords.narrative_section = gap.target_section

        return coords

    # =========================================================================
    # FOUR-WAY FUSED QUERY CONSTRUCTION
    # =========================================================================

    def _generate_fused_queries(self, gap: Gap) -> List[Query]:
        """
        Every query should fuse all four classes:
        - LOCATION (Definitional): "I am searching in [terrain]"
        - SUBJECT (Material): "I am looking for [entity]"
        - NEXUS (Probe): "Using [method]"
        - NARRATIVE (Intent): "Because [reason]"
        """
        queries = []
        coords = gap.coordinates or GapCoordinates()

        # Build query components - using contract fields
        location_component = ""
        if coords.location_jurisdiction:
            location_component = f"site:*.{coords.location_jurisdiction.lower()}.*"
        elif coords.location_domain:
            location_component = f"({coords.location_domain})"

        subject_component = ""
        if coords.subject_entity:
            # Add variations
            variations = self._generate_variations(coords.subject_entity)
            subject_component = ' OR '.join([f'"{v}"' for v in variations[:3]])

        # Fuse components (no nexus_connection_type in contract)
        query_parts = [p for p in [subject_component, location_component] if p]
        query_string = ' '.join(query_parts) if query_parts else gap.description

        # Determine IO module
        io_module = self._select_io_module(gap, coords)

        # Create query using contract fields
        queries.append(Query(
            id=f"q_{gap.id}",
            query_string=query_string,
            quadrant=gap.k_u_quadrant or KUQuadrant.DISCOVER,
            intent=gap.intent or Intent.DISCOVER_SUBJECT,
            priority=gap.priority,
            io_module=io_module,
        ))

        # Add supplementary queries based on K-U quadrant
        if gap.k_u_quadrant == KUQuadrant.TRACE and coords.subject_entity:
            # Add social media search
            queries.append(Query(
                id=f"q_{gap.id}_social",
                query_string=f'"{coords.subject_entity}" (linkedin OR twitter OR facebook)',
                quadrant=KUQuadrant.TRACE,
                intent=gap.intent or Intent.DISCOVER_SUBJECT,
                priority=gap.priority - 10,
                io_module='eye-d',
            ))

        elif gap.k_u_quadrant == KUQuadrant.EXTRACT and coords.location_jurisdiction:
            # Add registry search
            queries.append(Query(
                id=f"q_{gap.id}_registry",
                query_string=f'company registry {coords.location_jurisdiction}',
                quadrant=KUQuadrant.EXTRACT,
                intent=gap.intent or Intent.DISCOVER_SUBJECT,
                priority=gap.priority - 10,
                io_module='torpedo',
            ))

        return queries

    def _build_macro(self, gap: Gap, coords: GapCoordinates) -> str:
        """Build MACRO representation of the query."""
        parts = []

        if coords.subject_entity:
            parts.append(f'"{coords.subject_entity}"')

        if coords.location_jurisdiction:
            parts.append(f'!{coords.location_jurisdiction}')
        elif coords.location_domain:
            parts.append(f'!{coords.location_domain}')

        if gap.k_u_quadrant == KUQuadrant.VERIFY:
            parts.append('verify!')
        elif gap.k_u_quadrant == KUQuadrant.TRACE:
            parts.append('*')
        elif gap.k_u_quadrant == KUQuadrant.EXTRACT:
            parts.append('entities?')
        else:
            parts.append('discover!')

        return ' => '.join(parts) if parts else gap.description

    def _select_io_module(self, gap: Gap, coords: GapCoordinates) -> str:
        """Select the best IO module for this gap."""
        # Priority order based on gap type
        if coords.subject_type == 'person':
            if 'email' in gap.description.lower():
                return 'eye-d'
            if 'social' in gap.description.lower() or 'linkedin' in gap.description.lower():
                return 'eye-d'
            return 'brute'  # BrightData SERP

        if coords.subject_type == 'company':
            if coords.location_jurisdiction:
                return 'torpedo'  # Registry lookup
            return 'corporella'

        if coords.subject_type == 'domain':
            return 'linklater'

        # Default based on K-U quadrant
        if gap.k_u_quadrant == KUQuadrant.DISCOVER:
            return 'brute'
        elif gap.k_u_quadrant == KUQuadrant.EXTRACT:
            return 'linklater'

        return 'brute'

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _build_knowledge_base(self, document: Document):
        """Extract known subjects and locations from document."""
        self.known_subjects = []
        self.known_locations = []
        self.known_entities = document.known_entities

        for entity in document.known_entities:
            self.known_subjects.append(entity.name)
            if entity.entity_type == 'company':
                jur = entity.attributes.core.get('jurisdiction')
                if jur:
                    self.known_locations.append(jur)
            elif entity.entity_type == 'domain':
                self.known_locations.append(entity.name)

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract significant keywords from text."""
        if not text:
            return set()
        # Simple extraction - could be enhanced with NLP
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        words += [w for w in text.lower().split() if len(w) > 4]
        return set(words)

    def _extract_locations(self, document: Document) -> Set[str]:
        """Extract mentioned locations/jurisdictions from document."""
        locations = set()

        # From entities
        for entity in document.known_entities:
            jur = entity.attributes.core.get('jurisdiction')
            if jur:
                locations.add(jur)

        # From content (simple pattern matching)
        jurisdiction_patterns = [
            r'\b(UK|US|DE|FR|CH|CY|BVI|Cayman|Panama|Luxembourg|Ireland|Netherlands)\b',
            r'\b(United Kingdom|United States|Germany|France|Switzerland|Cyprus)\b',
        ]

        full_text = document.tasking + ' ' + ' '.join(s.content for s in document.sections)
        for pattern in jurisdiction_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            locations.update(m.upper() if len(m) <= 3 else m for m in matches)

        return locations

    def _infer_jurisdictions(self, company_name: str) -> List[str]:
        """Infer possible jurisdictions from company name patterns."""
        jurisdictions = []

        patterns = {
            r'\bLtd\.?\b': 'UK',
            r'\bLLC\b': 'US',
            r'\bGmbH\b': 'DE',
            r'\bS\.?A\.?\b': 'ES',
            r'\bB\.?V\.?\b': 'NL',
            r'\bLimited\b': 'UK',
            r'\bCorp\.?\b': 'US',
            r'\bInc\.?\b': 'US',
        }

        for pattern, jur in patterns.items():
            if re.search(pattern, company_name, re.IGNORECASE):
                jurisdictions.append(jur)

        return jurisdictions

    def _entity_has_field(self, entity: Entity, field: str) -> bool:
        """Check if entity has a specific field populated."""
        # Check core
        if field in entity.attributes.core and entity.attributes.core[field]:
            return True
        # Check shell
        if field in entity.attributes.shell and entity.attributes.shell[field]:
            return True
        # Check halo
        if field in entity.attributes.halo and entity.attributes.halo[field]:
            return True
        return False

    def _generate_reader_questions(self, document: Document) -> List[str]:
        """Generate questions a reader would ask about the document."""
        questions = []

        # Based on entities
        for entity in document.known_entities[:3]:
            if entity.entity_type == 'person':
                questions.extend([
                    f"Who is {entity.name}?",
                    f"What is {entity.name}'s background?",
                    f"What are {entity.name}'s connections?",
                ])
            elif entity.entity_type == 'company':
                questions.extend([
                    f"What does {entity.name} do?",
                    f"Who owns {entity.name}?",
                    f"Who runs {entity.name}?",
                ])

        # Based on tasking
        if 'offshore' in document.tasking.lower():
            questions.append("What offshore connections exist?")
        if 'fraud' in document.tasking.lower() or 'suspicious' in document.tasking.lower():
            questions.append("What red flags were identified?")

        return questions[:5]  # Limit to 5 questions

    def _question_answered(self, question: str, document: Document) -> bool:
        """Check if a question is addressed in the document."""
        question_keywords = self._extract_keywords(question)
        for section in document.sections:
            if section.state == 'complete':
                section_keywords = self._extract_keywords(section.content)
                if question_keywords & section_keywords:
                    return True
        return False

    def _extract_attribute_from_description(self, description: str) -> Optional[str]:
        """Extract the attribute being sought from gap description."""
        attribute_keywords = {
            'dob': ['dob', 'birth', 'born'],
            'address': ['address', 'residence', 'located'],
            'email': ['email', 'e-mail', 'mail'],
            'phone': ['phone', 'telephone', 'mobile'],
            'education': ['education', 'university', 'degree', 'school'],
            'officers': ['officer', 'director', 'board'],
            'shareholders': ['shareholder', 'owner', 'beneficial'],
        }

        desc_lower = description.lower()
        for attr, keywords in attribute_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                return attr
        return None

    def _infer_entity_type(self, subject: Optional[str], document: Document) -> Optional[str]:
        """Infer entity type from subject name or document context."""
        if not subject:
            return None

        for entity in document.known_entities:
            if entity.name.lower() == subject.lower():
                return entity.entity_type

        # Heuristics
        if re.search(r'\b(Ltd|LLC|GmbH|Corp|Inc|Limited|S\.A\.|B\.V\.)\b', subject, re.IGNORECASE):
            return 'company'
        if '@' in subject:
            return 'email'
        if re.match(r'^[\w.-]+\.[a-z]{2,}$', subject.lower()):
            return 'domain'

        return 'person'  # Default assumption

    def _infer_source_type(self, gap: Gap) -> Optional[str]:
        """Infer source type from gap characteristics."""
        desc_lower = gap.description.lower()

        if any(kw in desc_lower for kw in ['registry', 'registered', 'registration']):
            return 'registry'
        if any(kw in desc_lower for kw in ['news', 'article', 'press']):
            return 'news'
        if any(kw in desc_lower for kw in ['social', 'linkedin', 'twitter', 'facebook']):
            return 'social'
        if any(kw in desc_lower for kw in ['court', 'legal', 'lawsuit', 'filing']):
            return 'legal'
        if any(kw in desc_lower for kw in ['financial', 'annual', 'report', 'accounts']):
            return 'financial'

        return None

    def _infer_format(self, gap: Gap) -> Optional[str]:
        """Infer expected format from gap characteristics."""
        desc_lower = gap.description.lower()

        if 'pdf' in desc_lower:
            return 'PDF'
        if any(kw in desc_lower for kw in ['database', 'registry']):
            return 'database'
        if any(kw in desc_lower for kw in ['document', 'filing']):
            return 'document'

        return None

    def _infer_temporal(self, gap: Gap, document: Document) -> Optional[str]:
        """Infer temporal context from gap."""
        # Look for year patterns in description
        years = re.findall(r'\b(19|20)\d{2}\b', gap.description)
        if years:
            return f"{min(years)}-{max(years)}" if len(years) > 1 else years[0]
        return None

    def _infer_certainty(self, gap: Gap) -> str:
        """Infer certainty level of gap."""
        if gap.k_u_quadrant == KUQuadrant.VERIFY:
            return "probable"
        elif gap.k_u_quadrant == KUQuadrant.TRACE:
            return "uncertain"
        elif gap.k_u_quadrant == KUQuadrant.EXTRACT:
            return "uncertain"
        else:
            return "unknown"

    def _extract_connection_type(self, description: str) -> Optional[str]:
        """Extract connection type from description."""
        connection_keywords = {
            'director_of': ['director', 'board member'],
            'officer_of': ['officer', 'executive'],
            'shareholder_of': ['shareholder', 'owner', 'owns'],
            'subsidiary_of': ['subsidiary', 'parent'],
            'associated_with': ['associated', 'connected', 'linked'],
        }

        desc_lower = description.lower()
        for conn_type, keywords in connection_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                return conn_type
        return None

    def _map_priority_to_label(self, priority: int) -> str:
        """Map numeric priority to label."""
        if priority >= 80:
            return "critical"
        elif priority >= 60:
            return "high"
        elif priority >= 40:
            return "medium"
        else:
            return "low"

    def _generate_narrative_question(self, gap: Gap) -> Optional[str]:
        """Generate the narrative question this gap represents."""
        if gap.target_subject:
            return f"What do we know about {gap.target_subject}?"
        if gap.target_location:
            return f"What entities exist in {gap.target_location}?"
        return f"What information is missing: {gap.description}?"

    def _generate_variations(self, name: str) -> List[str]:
        """Generate name variations for search."""
        variations = [name]

        # Common variations
        if ' ' in name:
            parts = name.split()
            # Last, First
            if len(parts) == 2:
                variations.append(f"{parts[1]}, {parts[0]}")
                variations.append(f"{parts[0][0]}. {parts[1]}")
            # ALL CAPS
            variations.append(name.upper())
            # lowercase
            variations.append(name.lower())

        return variations


# =============================================================================
# BACKWARD COMPATIBILITY - Keep old class name working
# =============================================================================

class GapAnalyzer(CognitiveGapAnalyzer):
    """
    Backward-compatible alias for CognitiveGapAnalyzer.
    Use CognitiveGapAnalyzer for new code.
    """
    pass
