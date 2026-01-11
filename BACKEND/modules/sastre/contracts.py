"""
SASTRE Contracts - Thin wrappers for API data

Since all state lives in Cymonides-1 (Elasticsearch), these are just:
1. Constants for field codes and relationships
2. Thin dataclasses for type hints
3. Helpers for working with CymonidesNode data

The heavy dataclasses are gone - we use the Elasticsearch documents directly.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Literal, Tuple
from enum import Enum
from datetime import datetime, date


# =============================================================================
# DOCUMENT ENUMS
# =============================================================================

class SectionState(Enum):
    """State of a document section."""
    EMPTY = "empty"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


# =============================================================================
# ENUMS - Classification constants
# =============================================================================

class KUQuadrant(Enum):
    """K-U Matrix quadrants - determines query strategy"""
    VERIFY = "verify"       # Known Subject + Known Location -> Confirm what we think
    TRACE = "trace"         # Known Subject + Unknown Location -> Find where subject appears
    EXTRACT = "extract"     # Unknown Subject + Known Location -> Find what's in location
    DISCOVER = "discover"   # Unknown Subject + Unknown Location -> Explore frontier


class Intent(Enum):
    """Binary intent primitive"""
    DISCOVER_SUBJECT = "discover_subject"    # Find who/what (broad sweep)
    DISCOVER_LOCATION = "discover_location"  # Find where (broad sweep)
    ENRICH_SUBJECT = "enrich_subject"        # More about who/what (precision)
    ENRICH_LOCATION = "enrich_location"      # More about where (precision)


class DisambiguationAction(Enum):
    """Physics of identity - collision outcomes"""
    FUSE = "fuse"              # Confirmed same entity
    REPEL = "repel"            # Confirmed different entities (negative edge)
    BINARY_STAR = "binary_star"  # Ambiguous, orbiting, watching


class AbsenceType(Enum):
    """Classification of missing data - for gap analysis"""
    # Basic states (from slot system)
    EMPTY = "empty"              # No data at all
    INCOMPLETE = "incomplete"    # Partial data
    STALE = "stale"             # Data exists but outdated
    UNVERIFIED = "unverified"   # Data exists but not confirmed
    # Priority-based classification
    EXPECTED_NOT_FOUND = "expected_not_found"    # High priority gap (e.g., company without reg number)
    POSSIBLE_NOT_FOUND = "possible_not_found"    # Medium priority (e.g., person without middle name)
    RARE_NOT_FOUND = "rare_not_found"            # Low priority (e.g., historical data)
    NOT_APPLICABLE = "not_applicable"            # Field doesn't apply to this entity type


class CognitiveMode(Enum):
    """The four centricities/perspectives for grid rotation"""
    NARRATIVE = "narrative"    # Document-centric: gaps in story
    SUBJECT = "subject"        # Entity-centric: incomplete profiles
    LOCATION = "location"      # Source-centric: unchecked jurisdictions
    NEXUS = "nexus"            # Connection-centric: unverified links


class Dimension(Enum):
    """Dimensions for gap classification"""
    TEMPORAL = "temporal"      # Time-based gaps
    SPATIAL = "spatial"        # Location-based gaps
    RELATIONAL = "relational"  # Connection-based gaps
    ATTRIBUTIVE = "attributive"  # Property-based gaps


class NodeClass(Enum):
    """CymonidesNode class types"""
    ENTITY = "entity"
    QUERY = "query"
    NOTE = "note"
    NARRATIVE = "narrative"
    SOURCE = "source"
    WATCHER = "watcher"


# =============================================================================
# FIELD CODE MAPPINGS - Dynamically loaded from CYMONIDES schema
# =============================================================================

def _load_field_codes_from_schema(entity_type: str) -> Dict[str, int]:
    """
    Load field codes for an entity type from the REAL CYMONIDES schema.

    This replaces hardcoded PERSON_CODES, COMPANY_CODES, etc.
    Each property in the schema has a 'codes' array - we take the first code.

    Args:
        entity_type: Entity type name (person, company, domain, etc.)

    Returns:
        Dict mapping property_name -> field_code
    """
    try:
        # Use absolute import for robustness
        try:
            from SASTRE.core.schema_reader import get_schema_reader
        except ImportError:
            from .core.schema_reader import get_schema_reader

        reader = get_schema_reader()
        type_def = reader.get_entity_type(entity_type)

        if not type_def:
            return {}

        field_codes = {}
        for prop_name, prop_def in type_def.properties.items():
            # Take the first code if property has codes
            if prop_def.codes:
                field_codes[prop_name] = prop_def.codes[0]

        return field_codes
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load field codes for {entity_type}: {e}")
        return {}


def _load_all_codes_for_entity(entity_type: str) -> List[int]:
    """
    Get ALL field codes associated with an entity type.

    Returns the complete list from the schema's 'codes' array.
    """
    try:
        # Use absolute import for robustness
        try:
            from SASTRE.core.schema_reader import get_schema_reader
        except ImportError:
            from .core.schema_reader import get_schema_reader

        reader = get_schema_reader()
        type_def = reader.get_entity_type(entity_type)

        if not type_def:
            return []

        # Collect all unique codes from all properties
        all_codes = set()
        for prop_def in type_def.properties.values():
            all_codes.update(prop_def.codes)

        return sorted(list(all_codes))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load all codes for {entity_type}: {e}")
        return []


# Cache for loaded field codes
_FIELD_CODES_CACHE: Dict[str, Dict[str, int]] = {}


def get_field_codes(entity_type: str) -> Dict[str, int]:
    """Get field codes for an entity type (cached)."""
    if entity_type not in _FIELD_CODES_CACHE:
        _FIELD_CODES_CACHE[entity_type] = _load_field_codes_from_schema(entity_type)
    return _FIELD_CODES_CACHE[entity_type]


# Backwards compatibility - lazy-loaded dicts
class _FieldCodesProxy:
    """Lazy-loading proxy for field codes to maintain backwards compatibility."""

    def __init__(self, entity_type: str):
        self._entity_type = entity_type
        self._codes = None

    def __getitem__(self, key: str) -> int:
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return self._codes.get(key, 0)

    def __contains__(self, key: str) -> bool:
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return key in self._codes

    def get(self, key: str, default=None):
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return self._codes.get(key, default)

    def items(self):
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return self._codes.items()

    def keys(self):
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return self._codes.keys()

    def values(self):
        if self._codes is None:
            self._codes = get_field_codes(self._entity_type)
        return self._codes.values()


# Backwards-compatible constants (now dynamically loaded)
PERSON_CODES = _FieldCodesProxy("person")
COMPANY_CODES = _FieldCodesProxy("company")
DOMAIN_CODES = _FieldCodesProxy("domain")

# Legacy SUBJECT_FIELD_CODES structure
# Now dynamically built from schema's required vs optional properties
SUBJECT_FIELD_CODES = {
    "person": {
        "core": [],      # Populated on first access
        "shell": [],     # Populated on first access
        "enrichment": [], # Populated on first access
    },
    "company": {
        "core": [],      # Populated on first access
        "shell": [],     # Populated on first access
        "enrichment": [], # Populated on first access
    },
}

# Location codes - these are cross-entity, so we keep them but mark as legacy
LOCATION_FIELD_CODES = {
    "virtual": {
        "domain": [6, 129, 141, 191, 200, 203, 212],
        "url": [5, 38, 34, 46],
    },
    "physical": {
        "address": [20, 35, 47],
        "jurisdiction": [36, 48, 63, 70],
    },
}


# =============================================================================
# THIN DATACLASSES (for type hints)
# =============================================================================

@dataclass
class CymonidesNodeRef:
    """
    Reference to a Cymonides node.

    This is NOT the full node - just enough to identify it.
    Use the CymonidesClient to get full details.
    """
    id: str
    node_class: str  # entity, query, narrative, source, watcher
    node_type: str   # person, company, domain, investigation, etc.
    label: str
    project_id: str


@dataclass
class EdgeRef:
    """Reference to an edge between nodes."""
    edge_id: str
    source_id: str
    target_id: str
    relationship: str
    confidence: float = 0.9


@dataclass
class Gap:
    """
    A gap identified from grid rotation.

    Gaps are derived from Cymonides grid queries, not stored.
    """
    id: str
    description: str
    section: str = ""
    quadrant: str = ""
    intent: Optional[Intent] = None
    suggested_query: str = ""
    priority: int = 50
    target_subject: Optional[str] = None
    target_location: Optional[str] = None
    target_section: Optional[str] = None
    k_u_quadrant: Optional[KUQuadrant] = None
    is_looking_for_new_entities: bool = False
    absence_type: Optional[AbsenceType] = None
    discovered_by_mode: Optional[CognitiveMode] = None
    cross_pollination_actions: List["CrossPollinationAction"] = field(default_factory=list)
    coordinates: Optional["GapCoordinates"] = None
    corpus_checked: bool = False
    corpus_hits: List["CorpusHit"] = field(default_factory=list)


@dataclass
class NarrativeGoal:
    """Top-level investigation goal (strategic objective)."""
    id: str
    title: str
    description: str = ""
    status: str = "active"
    track_ids: List[str] = field(default_factory=list)


@dataclass
class NarrativeTrack:
    """Line of inquiry within a goal (container for paths)."""
    id: str
    goal_id: str
    title: str
    description: str = ""
    status: str = "active"
    path_ids: List[str] = field(default_factory=list)


@dataclass
class NarrativePath:
    """Specific route within a track (query → source → entity chain)."""
    id: str
    track_id: str
    title: str
    description: str = ""
    status: str = "active"
    query_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)


@dataclass
class InvestigationSummary:
    """
    Thin summary of an investigation (Cymonides-backed).

    This is derived from the investigation node in Cymonides and is NOT
    the in-memory graph state (see core.state.InvestigationState).
    """
    investigation_id: str
    project_id: str
    phase: str
    iteration: int
    tasking: str
    gaps_remaining: int = 0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def node_ref_from_dict(data: Dict[str, Any], project_id: str) -> CymonidesNodeRef:
    """Convert API response dict to CymonidesNodeRef."""
    return CymonidesNodeRef(
        id=data.get("id", ""),
        node_class=data.get("class", data.get("className", "")),
        node_type=data.get("type", data.get("typeName", "")),
        label=data.get("label", ""),
        project_id=project_id
    )


def get_completeness(node_data: Dict[str, Any], entity_type: str) -> str:
    """
    Assess entity completeness based on filled fields.

    Now uses REAL schema from CYMONIDES instead of hardcoded lists.

    Returns: "complete", "partial", or "stub"
    """
    try:
        # Use absolute import for robustness
        try:
            from SASTRE.core.schema_reader import get_schema_reader
        except ImportError:
            from .core.schema_reader import get_schema_reader

        reader = get_schema_reader()
        type_def = reader.get_entity_type(entity_type)

        if not type_def:
            return "stub"

        properties = node_data.get("properties", {})

        # Check required fields (core)
        required_props = type_def.required_properties
        required_filled = sum(
            1 for prop in required_props
            if prop.name in properties and properties.get(prop.name)
        )

        if not required_props or required_filled < len(required_props) * 0.5:
            return "stub"

        # Check optional fields (shell)
        optional_props = type_def.optional_properties
        optional_filled = sum(
            1 for prop in optional_props
            if prop.name in properties and properties.get(prop.name)
        )

        total_props = len(required_props) + len(optional_props)
        total_filled = required_filled + optional_filled

        if total_props > 0 and total_filled >= total_props * 0.7:
            return "complete"

        return "partial"

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Completeness check failed for {entity_type}: {e}")
        return "stub"


def infer_entity_type(value: str) -> str:
    """Infer entity type from value string."""
    value_lower = value.lower()

    if "@" in value_lower:
        return "email"
    if any(suffix in value_lower for suffix in ["ltd", "inc", "corp", "gmbh", "llc", "plc"]):
        return "company"
    if "." in value_lower and " " not in value_lower:
        return "domain"

    return "person"


def get_prefix_for_type(entity_type: str) -> str:
    """Get IO prefix for entity type."""
    prefix_map = {
        "person": "p:",
        "company": "c:",
        "email": "e:",
        "phone": "t:",
        "domain": "d:",
        "backlinks": "b:",
    }
    return prefix_map.get(entity_type, "p:")


def derive_quadrant(subject_known: bool, location_known: bool) -> KUQuadrant:
    """
    Derive K-U quadrant from what's known.

    KNOWN-KNOWN (VERIFY): Subject known, Location known → confirm
    KNOWN-UNKNOWN (TRACE): Subject known, Location unknown → find where
    UNKNOWN-KNOWN (EXTRACT): Subject unknown, Location known → mine location
    UNKNOWN-UNKNOWN (DISCOVER): Both unknown → frontier exploration
    """
    if subject_known and location_known:
        return KUQuadrant.VERIFY
    if subject_known:
        return KUQuadrant.TRACE
    if location_known:
        return KUQuadrant.EXTRACT
    return KUQuadrant.DISCOVER


def derive_intent(quadrant: KUQuadrant, is_looking_for_entities: bool) -> Intent:
    """Derive intent from quadrant and search type."""
    if is_looking_for_entities:
        if quadrant in [KUQuadrant.DISCOVER, KUQuadrant.EXTRACT]:
            return Intent.DISCOVER_SUBJECT
        return Intent.DISCOVER_LOCATION

    if quadrant == KUQuadrant.TRACE:
        return Intent.DISCOVER_LOCATION
    if quadrant == KUQuadrant.EXTRACT:
        return Intent.DISCOVER_SUBJECT
    if quadrant == KUQuadrant.VERIFY:
        return Intent.ENRICH_SUBJECT

    return Intent.DISCOVER_SUBJECT


# =============================================================================
# DOCUMENT DATACLASSES (for DocumentInterface)
# =============================================================================

@dataclass
class EntityAttributes:
    """Core/Shell/Halo attribute structure."""
    core: Dict[str, Any] = field(default_factory=dict)
    shell: Dict[str, Any] = field(default_factory=dict)
    halo: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Entity:
    """Entity for document display (not the full state Entity)."""
    id: str = ""
    name: str = ""
    entity_type: str = "unknown"
    source: str = ""
    attributes: EntityAttributes = field(default_factory=EntityAttributes)


@dataclass
class EntityCluster:
    """A cluster of related entities."""
    entities: List[Entity] = field(default_factory=list)
    relationship: str = ""


@dataclass
class Section:
    """A section of the document."""
    header: str = ""
    intent: Intent = Intent.ENRICH_SUBJECT
    state: SectionState = SectionState.EMPTY
    content: str = ""
    gaps: List[str] = field(default_factory=list)
    k_u_quadrant: KUQuadrant = KUQuadrant.TRACE
    watcher_meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class SurprisingAnd:
    """An unexpected co-occurrence detected during investigation."""
    connection: str = ""
    discovered_in: str = ""
    entities_involved: List[str] = field(default_factory=list)
    confidence: float = 0.7
    section_spawned: bool = False


class CollisionType(Enum):
    """Types of entity collisions."""
    NAME_MATCH = "name_match"
    IDENTIFIER_MATCH = "identifier_match"
    ATTRIBUTE_OVERLAP = "attribute_overlap"
    VALUE_CONFLICT = "value_conflict"


@dataclass
class Collision:
    """A potential entity collision."""
    entity_a_id: str = ""
    entity_b_id: str = ""
    collision_type: CollisionType = CollisionType.NAME_MATCH
    similarity_score: float = 0.0
    resolution: str = ""  # FUSE, REPEL, BINARY_STAR
    field_name: str = ""
    value_a: str = ""
    value_b: str = ""
    # Legacy alias
    @property
    def similarity(self) -> float:
        return self.similarity_score


@dataclass
class NegativeEdge:
    """A confirmed 'different from' relationship."""
    entity_a_id: str = ""
    entity_b_id: str = ""
    reason: str = ""


@dataclass
class Document:
    """The investigation document - primary user interface."""
    id: str = ""
    title: str = ""
    tasking: str = ""
    sections: List[Section] = field(default_factory=list)
    footnotes: List[str] = field(default_factory=list)
    known_entities: List[Entity] = field(default_factory=list)
    surprising_ands: List[SurprisingAnd] = field(default_factory=list)
    collisions: List[Collision] = field(default_factory=list)
    negative_edges: List[NegativeEdge] = field(default_factory=list)
    iteration_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    max_iterations: int = 10
    binary_stars: List['BinaryStar'] = field(default_factory=list)


# =============================================================================
# QUERY DATACLASSES (for gap analyzer)
# =============================================================================

@dataclass
class Query:
    """A query to be executed."""
    id: str = ""
    query_string: str = ""
    quadrant: KUQuadrant = KUQuadrant.DISCOVER
    intent: Intent = Intent.DISCOVER_SUBJECT
    io_module: str = ""  # eye-d, torpedo, corporella, linklater
    priority: int = 50
    variations: List[str] = field(default_factory=list)
    executed: bool = False
    result_count: int = 0


@dataclass
class WedgeQuery:
    """A targeted query for disambiguation."""
    id: str = ""
    query_string: str = ""
    vector_type: str = ""  # exclusion, intersection, narrative
    entity_a_id: str = ""
    entity_b_id: str = ""
    expected_if_same: str = ""
    expected_if_different: str = ""


@dataclass
class BinaryStar:
    """Two entities that might be the same, orbiting unresolved."""
    entity_a_id: str = ""
    entity_b_id: str = ""
    similarity_score: float = 0.5
    wedge_queries_pending: List[WedgeQuery] = field(default_factory=list)
    evidence_for_fuse: List[str] = field(default_factory=list)
    evidence_for_repel: List[str] = field(default_factory=list)


@dataclass
class DisambiguationResult:
    """Result of disambiguation process."""
    resolved_entities: List[Entity] = field(default_factory=list)
    binary_stars: List[BinaryStar] = field(default_factory=list)
    negative_edges: List[NegativeEdge] = field(default_factory=list)
    wedge_queries: List[WedgeQuery] = field(default_factory=list)
    fused_count: int = 0
    repelled_count: int = 0


# =============================================================================
# GAP ANALYZER DATACLASSES
# =============================================================================

@dataclass
class GapCoordinates:
    """3D coordinates for precise gap location."""
    subject_entity: Optional[str] = None
    subject_type: Optional[str] = None
    location_domain: Optional[str] = None
    location_jurisdiction: Optional[str] = None
    temporal_range: Optional[str] = None
    narrative_section: Optional[str] = None


@dataclass
class CrossPollinationAction:
    """Action to cross-pollinate between cognitive modes."""
    source_mode: str = ""  # CognitiveMode value
    target_mode: str = ""  # CognitiveMode value
    description: str = ""
    priority: int = 50


@dataclass
class DimensionalGap:
    """A gap with dimensional classification."""
    gap_id: str = ""
    description: str = ""
    dimension: str = ""  # Dimension value
    discovered_by_mode: str = ""  # CognitiveMode value
    absence_type: str = ""  # AbsenceType value
    target_subject: Optional[str] = None
    target_location: Optional[str] = None
    coordinates: Optional[GapCoordinates] = None
    cross_pollination: Optional[CrossPollinationAction] = None
    priority: int = 50


@dataclass
class CorpusHit:
    """A hit from corpus search."""
    document_id: str = ""
    snippet: str = ""
    relevance_score: float = 0.0
    source_url: Optional[str] = None


@dataclass
class CognitiveAnalysisLog:
    """Log entry for cognitive analysis."""
    mode: str = ""  # CognitiveMode value
    gaps_found: int = 0
    entities_analyzed: int = 0
    cross_pollinations: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GapAnalyzerOutput:
    """Complete output from gap analyzer."""
    gaps: List[DimensionalGap] = field(default_factory=list)
    cross_pollinations: List[CrossPollinationAction] = field(default_factory=list)
    logs: List[CognitiveAnalysisLog] = field(default_factory=list)
    total_gaps: int = 0
    priority_gaps: int = 0
    # Unified slot view (optional)
    slots: List["UnifiedSlot"] = field(default_factory=list)

    # Backwards-compatible fields used by CognitiveGapAnalyzer
    all_gaps: List[Any] = field(default_factory=list)
    next_queries: List[Any] = field(default_factory=list)
    disambiguation_queries: List[Any] = field(default_factory=list)
    sufficiency: Optional["SufficiencyResult"] = None
    cognitive_log: List[CognitiveAnalysisLog] = field(default_factory=list)
    corpus_checked: bool = False
    unknown_knowns_found: int = 0
    dimensional_gaps: List[Any] = field(default_factory=list)
    cross_pollination_actions: List[Any] = field(default_factory=list)


@dataclass
class SufficiencyResult:
    """Result of sufficiency check - combines 5 binary constraints with scores."""
    # 5 binary constraints (V4 spec)
    core_fields_populated: bool = False
    tasking_headers_addressed: bool = False
    no_high_weight_absences: bool = False
    disambiguation_resolved: bool = False
    surprising_ands_processed: bool = False
    # Score-based metrics (4-centricity)
    is_sufficient: bool = False
    overall_score: float = 0.0
    narrative_score: float = 0.0
    subject_score: float = 0.0
    location_score: float = 0.0
    nexus_score: float = 0.0
    remaining_gaps: int = 0
    collisions_pending: int = 0
    recommendation: str = ""

    @property
    def is_complete(self) -> bool:
        """All 5 constraints must be True for completion."""
        return all([
            self.core_fields_populated,
            self.tasking_headers_addressed,
            self.no_high_weight_absences,
            self.disambiguation_resolved,
            self.surprising_ands_processed,
        ])

    @property
    def constraints_met(self) -> int:
        """Count of met constraints."""
        return sum([
            self.core_fields_populated,
            self.tasking_headers_addressed,
            self.no_high_weight_absences,
            self.disambiguation_resolved,
            self.surprising_ands_processed,
        ])


# =============================================================================
# SLOT SYSTEM - Entity field state tracking with hunger mechanics
# =============================================================================

@dataclass
class TemporalValue:
    """
    A value with temporal metadata.

    Enables tracking of attribute changes over time:
    - value_date: When this value was true/valid (e.g., "address as of 2018")
    - observed_at: When we discovered/recorded this value
    - source_id: Where we got this information
    - confidence: How confident we are in this value
    """
    value: Any
    value_date: Optional[datetime] = None      # When this value was true
    observed_at: datetime = field(default_factory=datetime.now)  # When we discovered it
    source_id: str = ""
    confidence: float = 1.0
    superseded_by: Optional[str] = None        # ID of the value that replaced this

    @property
    def is_current(self) -> bool:
        """Is this the most recent known value?"""
        return self.superseded_by is None

    def __str__(self) -> str:
        date_str = self.value_date.strftime("%Y-%m-%d") if self.value_date else "unknown date"
        return f"{self.value} (as of {date_str})"


@dataclass
class ValueHistory:
    """
    Complete history of values for a slot.

    Implements a temporal stack:
    - Current value is always at the top
    - Historical values are preserved in order
    - Can query value at any point in time
    """
    entries: List[TemporalValue] = field(default_factory=list)

    def add(self, value: Any, source_id: str, value_date: Optional[datetime] = None,
            confidence: float = 1.0) -> TemporalValue:
        """Add a new value to the history stack."""
        # Mark previous current values as superseded
        new_entry = TemporalValue(
            value=value,
            value_date=value_date,
            source_id=source_id,
            confidence=confidence,
        )

        # If we have a value_date, insert in chronological order
        if value_date:
            # Find the right position
            insert_idx = len(self.entries)
            for i, entry in enumerate(self.entries):
                if entry.value_date and entry.value_date > value_date:
                    insert_idx = i
                    break
            self.entries.insert(insert_idx, new_entry)

            # Update supersession chain
            if insert_idx > 0:
                self.entries[insert_idx - 1].superseded_by = str(id(new_entry))
            if insert_idx < len(self.entries) - 1:
                new_entry.superseded_by = str(id(self.entries[insert_idx + 1]))
        else:
            # No date - assume it's the most recent
            if self.entries:
                self.entries[-1].superseded_by = str(id(new_entry))
            self.entries.append(new_entry)

        return new_entry

    @property
    def current(self) -> Optional[TemporalValue]:
        """Get the current (most recent) value."""
        if not self.entries:
            return None
        # Return the entry with no supersession (or last if none)
        for entry in reversed(self.entries):
            if entry.is_current:
                return entry
        return self.entries[-1] if self.entries else None

    @property
    def current_value(self) -> Optional[Any]:
        """Get just the current value (unwrapped)."""
        curr = self.current
        return curr.value if curr else None

    def value_at(self, target_date: datetime) -> Optional[TemporalValue]:
        """
        Get the value that was valid at a specific date.

        Returns the most recent value with value_date <= target_date.
        """
        if not self.entries:
            return None

        # Filter entries with known dates before target
        candidates = [
            e for e in self.entries
            if e.value_date and e.value_date <= target_date
        ]

        if not candidates:
            # No dated entries before target - return first known if any
            dated = [e for e in self.entries if e.value_date]
            return dated[0] if dated else self.entries[0]

        # Return the most recent candidate
        return max(candidates, key=lambda e: e.value_date)

    def value_in_range(self, start: datetime, end: datetime) -> List[TemporalValue]:
        """Get all values valid within a date range."""
        return [
            e for e in self.entries
            if e.value_date and start <= e.value_date <= end
        ]

    def all_values(self) -> List[Any]:
        """Get all unique values ever recorded."""
        seen = set()
        result = []
        for entry in self.entries:
            val_key = str(entry.value)
            if val_key not in seen:
                seen.add(val_key)
                result.append(entry.value)
        return result

    def has_changed(self) -> bool:
        """Has this value changed over time?"""
        unique = self.all_values()
        return len(unique) > 1

    def timeline(self) -> List[Tuple[Optional[datetime], Any]]:
        """Get a timeline of (date, value) pairs."""
        return [(e.value_date, e.value) for e in self.entries if e.value_date]

    def __len__(self) -> int:
        return len(self.entries)


class SlotState(Enum):
    """
    State of an entity slot (field).

    V4 Spec: "The Tag dictates the Future of the Result."
    Slots are auto-generated based on entity type and track field population state.
    """
    EMPTY = "empty"           # No data yet - slot is hungry
    PARTIAL = "partial"       # Some data, but incomplete
    FILLED = "filled"         # Slot satisfied with data
    VOID = "void"             # Actively searched, confirmed nothing exists
    CONTESTED = "contested"   # Multiple conflicting values found
    DEFERRED = "deferred"     # Blocked with current tools, cannot formulate valid plan


class SlotPriority(Enum):
    """Priority level for slot filling."""
    CRITICAL = "critical"     # Core fields - must have
    HIGH = "high"             # Shell fields - should have
    MEDIUM = "medium"         # Enrichment fields - nice to have
    LOW = "low"               # Halo fields - if time permits


class SlotType(Enum):
    """Unified slot categories for all requirement types."""
    ATTRIBUTE = "attribute"       # Node field completeness
    RELATIONSHIP = "relationship" # Missing/expected edges
    COVERAGE = "coverage"         # Unchecked sources/territories
    NARRATIVE = "narrative"       # Story gaps/watchers


class SlotOrigin(Enum):
    """Where a slot requirement originated."""
    SCHEMA = "schema"
    PROFILE = "profile"
    USER = "user"
    AGENT = "agent"
    WATCHER = "watcher"
    INFERRED = "inferred"


class SlotTarget(Enum):
    """Which axis a slot primarily targets."""
    SUBJECT = "subject"
    LOCATION = "location"
    NARRATIVE = "narrative"
    NEXUS = "nexus"


class SlotStrategy(Enum):
    """Preferred tactic for satisfying a slot."""
    SEARCH = "search"
    WATCH = "watch"


@dataclass
class UnifiedSlot:
    """
    Unified requirement primitive (attribute, relationship, coverage, narrative).

    Gaps are a view over unsatisfied slots. Attribute slots remain implicit
    (derived from entity fields), while explicit slots cover requirements that
    cannot be represented as simple fields.
    """
    slot_id: str
    slot_type: SlotType
    origin: SlotOrigin
    target: SlotTarget
    description: str

    # State
    state: SlotState = SlotState.EMPTY
    priority: SlotPriority = SlotPriority.MEDIUM

    # Optional strategy (e.g., TRAP/watch)
    strategy: Optional[SlotStrategy] = None

    # Association (optional)
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    field_name: Optional[str] = None
    relationship_type: Optional[str] = None
    source_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    domain: Optional[str] = None
    narrative_section: Optional[str] = None
    watcher_id: Optional[str] = None

    # Coordinate hints (use GapCoordinates3D.to_dict() or similar)
    coordinates: Dict[str, Any] = field(default_factory=dict)

    # Provenance/extension
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_hungry(self) -> bool:
        """Unified hunger check for gaps view."""
        return self.state in (SlotState.EMPTY, SlotState.PARTIAL, SlotState.CONTESTED)

    def mark_filled(self) -> None:
        """Mark slot as filled and update timestamp."""
        self.state = SlotState.FILLED
        self.updated_at = datetime.utcnow()

    def mark_void(self) -> None:
        """Mark slot as void (confirmed absence)."""
        self.state = SlotState.VOID
        self.updated_at = datetime.utcnow()


@dataclass
class EntitySlot:
    """
    A slot (field) on an entity that can be filled.

    Implements hunger/feeding mechanics:
    - Hungry slots drive query generation
    - Fed slots reduce hunger
    - Mutation when values conflict

    Now with temporal tracking:
    - history: Complete ValueHistory stack
    - Can query value_at(date) for historical values
    - Tracks when values changed
    """
    slot_id: str
    field_name: str
    entity_id: str
    entity_type: str

    # State
    state: SlotState = SlotState.EMPTY
    priority: SlotPriority = SlotPriority.MEDIUM

    # Values (kept for backwards compatibility)
    values: List[Any] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)  # Source IDs for each value

    # Temporal history stack (new)
    history: ValueHistory = field(default_factory=ValueHistory)

    # Hunger mechanics
    hunger: float = 1.0       # 0.0 = satisfied, 1.0 = starving
    query_count: int = 0      # How many queries have tried to fill this
    last_fed: Optional[datetime] = None

    # Layer info
    layer: str = "shell"      # core, shell, or halo

    def feed(self, value: Any, source_id: str, value_date: Optional[datetime] = None,
             confidence: float = 1.0) -> None:
        """
        Feed the slot with a value from a source.

        Args:
            value: The value to store
            source_id: ID of the source where value was found
            value_date: When this value was valid (e.g., "address as of 2018")
            confidence: Confidence in this value (0.0 to 1.0)
        """
        if value is None:
            return

        self.query_count += 1
        self.last_fed = datetime.now()

        # Add to history stack with temporal metadata
        self.history.add(
            value=value,
            source_id=source_id,
            value_date=value_date,
            confidence=confidence,
        )

        # Update flat values list (backwards compatibility)
        if not self.values:
            # First value
            self.values.append(value)
            self.sources.append(source_id)
            self.state = SlotState.FILLED
            self.hunger = 0.2  # Still slightly hungry for confirmation
        elif value in self.values:
            # Confirmation - reduce hunger further
            self.hunger = max(0.0, self.hunger - 0.1)
        else:
            # Different value - could be temporal change or conflict
            self.values.append(value)
            self.sources.append(source_id)

            # If we have dated values, this might be temporal not contested
            if self.history.has_changed() and all(e.value_date for e in self.history.entries):
                # All values have dates - this is temporal progression, not conflict
                self.state = SlotState.FILLED
                self.hunger = 0.1  # Very satisfied - we have history
            else:
                # Conflicting values without dates - needs resolution
                self.state = SlotState.CONTESTED
                self.hunger = 0.8  # Need resolution

    def mark_void(self, source_id: str) -> None:
        """Mark slot as actively empty (searched, nothing found)."""
        self.query_count += 1
        self.last_fed = datetime.now()
        self.sources.append(source_id)

        if self.state == SlotState.EMPTY:
            self.state = SlotState.VOID
            self.hunger = 0.3  # Reduced hunger, might still try other sources

    def value_at(self, target_date: datetime) -> Optional[Any]:
        """
        Get the value that was valid at a specific date.

        Example: slot.value_at(datetime(2018, 1, 1)) returns the address in 2018.
        """
        temporal_val = self.history.value_at(target_date)
        return temporal_val.value if temporal_val else None

    def value_timeline(self) -> List[Tuple[Optional[datetime], Any]]:
        """Get the complete timeline of value changes."""
        return self.history.timeline()

    def has_temporal_changes(self) -> bool:
        """Has this slot's value changed over time?"""
        return self.history.has_changed()

    @property
    def is_hungry(self) -> bool:
        """Is this slot still hungry for data?"""
        return self.hunger > 0.5

    @property
    def needs_resolution(self) -> bool:
        """Does this slot have conflicting values needing resolution?"""
        return self.state == SlotState.CONTESTED

    @property
    def primary_value(self) -> Optional[Any]:
        """Get the primary (current) value if any."""
        # Prefer current from history, fallback to first in values list
        hist_current = self.history.current_value
        if hist_current is not None:
            return hist_current
        return self.values[0] if self.values else None

    @property
    def all_historical_values(self) -> List[Any]:
        """Get all unique values ever recorded for this slot."""
        return self.history.all_values()


@dataclass
class EntitySlotSet:
    """Collection of slots for an entity."""
    entity_id: str
    entity_type: str
    slots: Dict[str, EntitySlot] = field(default_factory=dict)

    def get_hungry_slots(self) -> List[EntitySlot]:
        """Get all hungry slots sorted by priority."""
        hungry = [s for s in self.slots.values() if s.is_hungry]
        priority_order = {
            SlotPriority.CRITICAL: 0,
            SlotPriority.HIGH: 1,
            SlotPriority.MEDIUM: 2,
            SlotPriority.LOW: 3,
        }
        return sorted(hungry, key=lambda s: priority_order.get(s.priority, 4))

    def get_contested_slots(self) -> List[EntitySlot]:
        """Get all slots needing disambiguation."""
        return [s for s in self.slots.values() if s.needs_resolution]

    def get_temporal_slots(self) -> List[EntitySlot]:
        """Get all slots that have temporal history (values changed over time)."""
        return [s for s in self.slots.values() if s.has_temporal_changes()]

    def snapshot_at(self, target_date: datetime) -> Dict[str, Any]:
        """
        Get entity state at a specific point in time.

        Returns a dict of field_name -> value as it was at target_date.
        Useful for: "What was this company's address in 2018?"
        """
        snapshot = {}
        for field_name, slot in self.slots.items():
            val = slot.value_at(target_date)
            if val is not None:
                snapshot[field_name] = val
        return snapshot

    def detect_temporal_anomalies(self) -> List[Dict[str, Any]]:
        """
        Detect anomalies in temporal data.

        Returns list of anomalies like:
        - Retroactive changes (later source claims earlier date)
        - Implausible transitions (e.g., address changed 10 times in a month)
        - Confidence drops in recent data
        """
        anomalies = []

        for field_name, slot in self.slots.items():
            if len(slot.history) < 2:
                continue

            entries = slot.history.entries
            for i in range(1, len(entries)):
                prev = entries[i - 1]
                curr = entries[i]

                # Check for retroactive claims
                if prev.observed_at and curr.observed_at and prev.value_date and curr.value_date:
                    if curr.observed_at > prev.observed_at and curr.value_date < prev.value_date:
                        anomalies.append({
                            "type": "retroactive_claim",
                            "field": field_name,
                            "description": f"Later source ({curr.source_id}) claims earlier date",
                            "prev_value": prev.value,
                            "curr_value": curr.value,
                        })

                # Check for confidence drops
                if curr.confidence < prev.confidence * 0.7:
                    anomalies.append({
                        "type": "confidence_drop",
                        "field": field_name,
                        "description": f"Confidence dropped from {prev.confidence:.2f} to {curr.confidence:.2f}",
                        "value": curr.value,
                    })

        return anomalies

    def temporal_diff(self, date_a: datetime, date_b: datetime) -> Dict[str, Dict[str, Any]]:
        """
        Compare entity state between two dates.

        Returns dict of changed fields with before/after values.
        """
        diff = {}
        snapshot_a = self.snapshot_at(date_a)
        snapshot_b = self.snapshot_at(date_b)

        all_fields = set(snapshot_a.keys()) | set(snapshot_b.keys())
        for field_name in all_fields:
            val_a = snapshot_a.get(field_name)
            val_b = snapshot_b.get(field_name)
            if val_a != val_b:
                diff[field_name] = {
                    "before": val_a,
                    "after": val_b,
                    "date_a": date_a,
                    "date_b": date_b,
                }

        return diff

    def overall_hunger(self) -> float:
        """Calculate overall hunger level (0.0 = satisfied, 1.0 = starving)."""
        if not self.slots:
            return 1.0
        total_hunger = sum(s.hunger for s in self.slots.values())
        return total_hunger / len(self.slots)

    def completeness_score(self) -> float:
        """
        Calculate completeness (0.0 = empty, 1.0 = fully filled).

        V4.2+ schemas include many optional HALO fields (graphs, lists, history),
        so a raw filled/total ratio severely underestimates progress during early
        investigations. We instead score by layer with weights:
          - core: identity/required fields (dominant)
          - shell: primary descriptive fields
          - halo: relationships/derived history (least important)
        """
        if not self.slots:
            return 0.0

        layer_weights = {"core": 0.6, "shell": 0.3, "halo": 0.1}
        by_layer: Dict[str, List[EntitySlot]] = {"core": [], "shell": [], "halo": []}
        for slot in self.slots.values():
            by_layer.setdefault(slot.layer, []).append(slot)

        def layer_score(slots: List[EntitySlot]) -> float:
            if not slots:
                return 0.0
            filled = sum(1 for s in slots if s.state in [SlotState.FILLED, SlotState.VOID])
            return filled / len(slots)

        numerator = 0.0
        denom = 0.0
        for layer, slots in by_layer.items():
            if not slots:
                continue
            w = layer_weights.get(layer, 0.0)
            if w <= 0:
                continue
            numerator += w * layer_score(slots)
            denom += w

        return numerator / denom if denom > 0 else 0.0

    def temporal_richness(self) -> float:
        """
        Calculate how much temporal history we have (0.0 = none, 1.0 = rich history).

        Higher score = more slots with temporal changes tracked.
        """
        if not self.slots:
            return 0.0
        temporal_count = sum(1 for s in self.slots.values() if len(s.history) > 1)
        return temporal_count / len(self.slots)


# =============================================================================
# SLOT TEMPLATES - Now dynamically loaded from CYMONIDES schema
# =============================================================================
#
# DEPRECATED: The old hardcoded SLOT_TEMPLATES has been replaced with
# dynamic schema loading. Use get_slot_template() instead.
#
# The templates are now generated from:
#   BACKEND/modules/CYMONIDES/metadata/c-1/matrix_schema/nodes.json
#
# This ensures slots match the REAL entity properties in Cymonides-1.
# =============================================================================

def _get_slot_template_from_schema(entity_type: str) -> Dict[str, Dict[str, Any]]:
    """
    Get slot template from the REAL CYMONIDES schema.

    Reads from: CYMONIDES/metadata/c-1/matrix_schema/nodes.json
    Maps schema properties to slot configurations.
    """
    try:
        from .core.schema_reader import get_schema_reader
        reader = get_schema_reader()
        type_def = reader.get_entity_type(entity_type)

        if not type_def:
            return {}

        template = {}
        for prop_name, prop_def in type_def.properties.items():
            # Map schema to slot config
            if prop_def.required:
                layer = "core"
                priority = SlotPriority.CRITICAL
            elif prop_def.is_array or prop_def.is_object:
                # Arrays/objects tend to be halo (relationships, lists)
                layer = "halo"
                priority = SlotPriority.MEDIUM
            else:
                layer = "shell"
                priority = SlotPriority.HIGH

            template[prop_name] = {
                "layer": layer,
                "priority": priority,
            }

        return template
    except Exception as e:
        # Fallback to empty template if schema loading fails
        import logging
        logging.getLogger(__name__).warning(f"Schema loading failed for {entity_type}: {e}")
        return {}


# Legacy SLOT_TEMPLATES for backwards compatibility
# Will be populated on first access from schema
_SLOT_TEMPLATES_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def get_slot_template(entity_type: str) -> Dict[str, Dict[str, Any]]:
    """Get slot template for an entity type (from schema or cache)."""
    if entity_type not in _SLOT_TEMPLATES_CACHE:
        template = _get_slot_template_from_schema(entity_type)

        # Backwards-compatible aliases for older slot templates/tests.
        if entity_type == "domain":
            template.setdefault(
                "registrant",
                {"layer": "shell", "priority": SlotPriority.HIGH},
            )

        _SLOT_TEMPLATES_CACHE[entity_type] = template
    return _SLOT_TEMPLATES_CACHE[entity_type]


# For backwards compatibility, SLOT_TEMPLATES is now a lazy-loaded dict-like accessor
# Tests that import SLOT_TEMPLATES directly will still work
SLOT_TEMPLATES: Dict[str, Dict[str, Dict[str, Any]]] = {
    # Populated lazily - kept for import compatibility
    "person": {},
    "company": {},
    "domain": {},
}


def create_slots_for_entity(entity_id: str, entity_type: str) -> EntitySlotSet:
    """
    Create a slot set for an entity based on its type.

    V4.2: Now reads from the REAL CYMONIDES schema instead of hardcoded templates.
    This ensures slots match actual entity properties in Cymonides-1 Elasticsearch.
    """
    slot_set = EntitySlotSet(entity_id=entity_id, entity_type=entity_type)

    # Get template from REAL schema
    template = get_slot_template(entity_type)

    for field_name, config in template.items():
        slot = EntitySlot(
            slot_id=f"{entity_id}_{field_name}",
            field_name=field_name,
            entity_id=entity_id,
            entity_type=entity_type,
            layer=config.get("layer", "shell"),
            priority=config.get("priority", SlotPriority.MEDIUM),
        )
        slot_set.slots[field_name] = slot

    return slot_set


# =============================================================================
# NARRATIVE GOVERNOR - Template-based stopping conditions
# =============================================================================
#
# The Narrative is not just output; it is the Governor.
# Templates define depth (word count, sections, drill depth).
# The cognitive engine drills until the template requirements are met.
#
# Loaded from: input_output/matrix/report_generation.json
#              input_output/matrix/section_templates_catalog.json
#              input_output/matrix/writing_guide.json
# =============================================================================

class DepthLevel(Enum):
    """Report depth levels from genre profiles."""
    BASIC = "basic"
    ENHANCED = "enhanced"
    COMPREHENSIVE = "comprehensive"


@dataclass
class SectionConstraint:
    """Constraints for a specific section type."""
    section_name: str
    min_words: int = 50
    max_words: int = 500
    avg_words: int = 200
    required_content: List[str] = field(default_factory=list)
    key_phrases: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)


@dataclass
class VoiceProfile:
    """Writing voice constraints."""
    voice_type: str  # third_person, first_plural, etc.
    description: str = ""
    example_openings: List[str] = field(default_factory=list)
    prohibited_phrases: List[str] = field(default_factory=list)
    sample_rules: List[str] = field(default_factory=list)


@dataclass
class CertaintyPhrases:
    """Certainty calibration phrases by confidence level."""
    verified_facts: List[str] = field(default_factory=list)
    high_confidence: List[str] = field(default_factory=list)
    medium_confidence: List[str] = field(default_factory=list)
    inference: List[str] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)


@dataclass
class NarrativeGovernor:
    """
    The Governor - Template-based stopping conditions for investigations.

    The template defines drill depth; output format dictates input effort.
    When the story is satisfied for this genre at this depth, STOP drilling.

    Loaded from:
        - report_generation.json: genre profiles, depth_levels, writing_style_rules
        - section_templates_catalog.json: section word counts, required content
        - writing_guide.json: exemplar passages, voice patterns
    """
    # Identity
    genre: str  # due_diligence, background_check, asset_trace, corporate_intelligence, litigation_support
    depth_level: DepthLevel = DepthLevel.ENHANCED

    # Hard constraints (stopping conditions)
    max_word_count: int = 5000
    max_sections: int = 8
    max_drill_iterations: int = 10
    required_sections: List[str] = field(default_factory=list)

    # Section constraints (from section_templates_catalog.json)
    section_constraints: Dict[str, SectionConstraint] = field(default_factory=dict)

    # Voice and style (from report_generation.json + writing_guide.json)
    voice: Optional[VoiceProfile] = None
    formality: str = "professional"  # professional, legal, analytical
    stance: str = "neutral_observer"  # neutral_observer, investigator, factual_documenter
    attribution_style: str = "footnoted"  # footnoted, embedded, inline_parenthetical

    # Certainty calibration (from writing_style_rules)
    certainty_phrases: Optional[CertaintyPhrases] = None

    # Professional conventions
    entity_introduction_company: str = ""
    entity_introduction_person: str = ""
    date_format: str = "DD Month YYYY"
    currency_format: str = "€53.02 million"
    negative_finding_phrase: str = "No adverse information was identified."

    # Runtime tracking
    current_word_count: int = 0
    current_iteration: int = 0
    sections_filled: Set[str] = field(default_factory=set)

    def should_continue_drilling(self) -> bool:
        """
        The Governor's decision: Should we drill deeper?

        Returns False when the story is satisfied for this genre/depth.
        """
        # Hard stops
        if self.current_iteration >= self.max_drill_iterations:
            return False
        if self.current_word_count >= self.max_word_count:
            return False

        # Section requirements
        if self.required_sections:
            missing_sections = set(self.required_sections) - self.sections_filled
            if not missing_sections:
                # All required sections filled - check word count threshold
                # At 80% of max words, we can stop
                if self.current_word_count >= self.max_word_count * 0.8:
                    return False

        return True

    def section_needs_more(self, section_name: str, current_words: int) -> bool:
        """Does this section need more content?"""
        constraint = self.section_constraints.get(section_name.lower())
        if constraint:
            return current_words < constraint.min_words
        # Default: at least 100 words per section
        return current_words < 100

    def section_over_limit(self, section_name: str, current_words: int) -> bool:
        """Is this section over its limit?"""
        constraint = self.section_constraints.get(section_name.lower())
        if constraint:
            return current_words > constraint.max_words
        # Default: max 1500 words per section
        return current_words > 1500

    def update_progress(self, word_count: int, filled_section: Optional[str] = None):
        """Update progress tracking."""
        self.current_word_count = word_count
        if filled_section:
            self.sections_filled.add(filled_section)

    def increment_iteration(self):
        """Mark a drill iteration complete."""
        self.current_iteration += 1

    def get_remaining_budget(self) -> int:
        """Get remaining word budget."""
        return max(0, self.max_word_count - self.current_word_count)

    def get_missing_sections(self) -> List[str]:
        """Get sections still required but not filled."""
        if not self.required_sections:
            return []
        return list(set(self.required_sections) - self.sections_filled)

    def get_voice_rule(self) -> str:
        """Get the primary voice rule for prompts."""
        if self.voice and self.voice.sample_rules:
            return self.voice.sample_rules[0]
        return f"Use {self.stance} voice with {self.formality} tone."

    def get_certainty_phrase(self, confidence_level: str) -> str:
        """Get an appropriate certainty phrase for the confidence level."""
        if not self.certainty_phrases:
            return ""

        phrases_map = {
            "verified": self.certainty_phrases.verified_facts,
            "high": self.certainty_phrases.high_confidence,
            "medium": self.certainty_phrases.medium_confidence,
            "inference": self.certainty_phrases.inference,
            "unverified": self.certainty_phrases.unverified,
        }
        phrases = phrases_map.get(confidence_level, [])
        return phrases[0] if phrases else ""

    def to_prompt_block(self) -> str:
        """Generate prompt block for LLM context."""
        lines = [
            f"## Writing Constraints ({self.genre} - {self.depth_level.value})",
            f"Target word count: {self.max_word_count} words",
            f"Remaining budget: {self.get_remaining_budget()} words",
            "",
        ]

        if self.voice:
            lines.append(f"### Voice: {self.voice.voice_type}")
            if self.voice.description:
                lines.append(f"- {self.voice.description}")
            if self.voice.prohibited_phrases:
                lines.append(f"- Avoid: {', '.join(repr(p) for p in self.voice.prohibited_phrases[:5])}")
            lines.append("")

        if self.certainty_phrases:
            lines.append("### Certainty Calibration")
            if self.certainty_phrases.verified_facts:
                lines.append(f"- Verified: {self.certainty_phrases.verified_facts[0]}")
            if self.certainty_phrases.unverified:
                lines.append(f"- Unverified: {self.certainty_phrases.unverified[0]}")
            lines.append("")

        missing = self.get_missing_sections()
        if missing:
            lines.append(f"### Required Sections Still Needed")
            for section in missing[:5]:
                lines.append(f"- {section}")

        return "\n".join(lines)
