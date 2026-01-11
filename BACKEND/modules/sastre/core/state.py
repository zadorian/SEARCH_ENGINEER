"""
SASTRE Core State - Central state models for the investigation system.

This file defines ALL the state types used across SASTRE:
- Investigation: Top-level container with relationship tracking
- Narrative: Questions, sections, documents
- Query: Search operations with K-U classification
- Source: Documents, URLs, registries
- Entity: People, companies, domains, etc.
- Disambiguation: Collision resolution

RELATIONSHIP HIERARCHY:
    Goal (1) → Track (many) → Path (many) → NarrativeItem (many)
         → Query (many) → Source (many) → Entity (many)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum
from datetime import datetime
from collections import defaultdict

from ..contracts import (
    KUQuadrant,
    Intent,
    DisambiguationAction,
    NarrativeGoal,
    NarrativeTrack,
    NarrativePath,
)
import uuid
import hashlib


# =============================================================================
# ENUMS
# =============================================================================

class InvestigationPhase(Enum):
    """Investigation lifecycle phases."""
    INITIALIZING = "initializing"
    ASSESSING = "assessing"
    INVESTIGATING = "investigating"
    DISAMBIGUATING = "disambiguating"
    WRITING = "writing"
    CHECKING = "checking"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    PAUSED = "paused"


class Priority(Enum):
    """Priority levels for gaps and queries."""
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class EntityType(Enum):
    """Types of entities we track."""
    PERSON = "person"
    COMPANY = "company"
    ORGANIZATION = "organization"
    DOMAIN = "domain"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    DOCUMENT = "document"
    EVENT = "event"
    TOPIC = "topic"
    THEME = "theme"
    IDENTIFIER = "identifier"
    UNKNOWN = "unknown"


class NarrativeState(Enum):
    """State of a narrative item."""
    UNANSWERED = "unanswered"
    PARTIAL = "partial"
    ANSWERED = "answered"
    PARKED = "parked"
    CONTRADICTED = "contradicted"


class QueryState(Enum):
    """State of a query."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class SourceState(Enum):
    """State of a source."""
    UNCHECKED = "unchecked"
    CHECKING = "checking"
    CHECKED = "checked"
    EMPTY = "empty"
    FAILED = "failed"


class DisambiguationState(Enum):
    """Disambiguation state for an entity."""
    UNIQUE = "unique"
    PENDING = "pending"
    FUSED = "fused"
    REPELLED = "repelled"


# =============================================================================
# ATTRIBUTE AND ENTITY
# =============================================================================

@dataclass
class Attribute:
    """
    An attribute of an entity (Core/Shell/Halo layer).
    """
    name: str
    value: Any
    confidence: float = 0.8
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))


# Alias for backward compatibility
EntityAttribute = Attribute


@dataclass
class Entity:
    """
    An entity in the investigation (person, company, domain, etc.).

    Uses Core/Shell/Halo layering:
    - Core: High confidence, hard identifiers (passport, reg number)
    - Shell: Medium confidence, contextual (name, address, role)
    - Halo: Low confidence, circumstantial (patterns, associations)
    """
    id: str
    entity_type: EntityType
    name: str

    # Core/Shell/Halo layers
    core: Dict[str, Attribute] = field(default_factory=dict)
    shell: Dict[str, Attribute] = field(default_factory=dict)
    halo: Dict[str, Attribute] = field(default_factory=dict)

    confidence: float = 0.8
    sources: List[str] = field(default_factory=list)

    # Disambiguation tracking
    disambiguation_state: DisambiguationState = DisambiguationState.UNIQUE
    collision_with: List[str] = field(default_factory=list)

    # Expected fields by entity type (for completeness checking)
    _CORE_FIELDS = {
        EntityType.PERSON: {"name", "dob", "nationality"},
        EntityType.COMPANY: {"name", "registration_number", "jurisdiction"},
        EntityType.DOMAIN: {"domain", "registrar"},
        EntityType.EMAIL: {"email"},
    }
    _SHELL_FIELDS = {
        EntityType.PERSON: {"address", "occupation", "employer"},
        EntityType.COMPANY: {"address", "status", "incorporation_date"},
        EntityType.DOMAIN: {"ip_address", "hosting_provider"},
    }

    @classmethod
    def create(cls, name: str, entity_type: EntityType = EntityType.UNKNOWN) -> 'Entity':
        """Create a new entity with auto-generated ID."""
        entity_id = hashlib.sha256(f"{name}:{entity_type.value}:{uuid.uuid4()}".encode()).hexdigest()[:16]
        return cls(id=entity_id, entity_type=entity_type, name=name)

    @property
    def core_complete(self) -> bool:
        """Check if all expected core fields are present."""
        expected = self._CORE_FIELDS.get(self.entity_type, set())
        present = set(self.core.keys())
        return expected.issubset(present)

    @property
    def shell_complete(self) -> bool:
        """Check if all expected shell fields are present."""
        expected = self._SHELL_FIELDS.get(self.entity_type, set())
        present = set(self.shell.keys())
        return expected.issubset(present)

    @property
    def core_missing(self) -> Set[str]:
        """Return missing core fields."""
        expected = self._CORE_FIELDS.get(self.entity_type, set())
        present = set(self.core.keys())
        return expected - present

    @property
    def shell_missing(self) -> Set[str]:
        """Return missing shell fields."""
        expected = self._SHELL_FIELDS.get(self.entity_type, set())
        present = set(self.shell.keys())
        return expected - present

    @property
    def collision_flags(self) -> bool:
        """Check if entity has pending collisions."""
        return self.disambiguation_state == DisambiguationState.PENDING or len(self.collision_with) > 0

    @property
    def display_name(self) -> str:
        """For backward compatibility."""
        return self.name

    @property
    def entity_id(self) -> str:
        """For backward compatibility."""
        return self.id

    def has_attribute(self, attr_name: str) -> bool:
        """Check if entity has an attribute in any layer."""
        return (
            attr_name in self.core or
            attr_name in self.shell or
            attr_name in self.halo
        )

    def get_attribute(self, attr_name: str) -> Optional[Attribute]:
        """Get attribute from any layer (Core first, then Shell, then Halo)."""
        if attr_name in self.core:
            return self.core[attr_name]
        if attr_name in self.shell:
            return self.shell[attr_name]
        if attr_name in self.halo:
            return self.halo[attr_name]
        return None


@dataclass
class Edge:
    """A relationship between two entities."""
    id: str
    source_entity_id: str
    target_entity_id: str
    relationship: str
    confidence: float = 0.8
    confirmed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, source_id: str, target_id: str, relationship: str) -> 'Edge':
        edge_id = hashlib.sha256(f"{source_id}:{target_id}:{relationship}:{uuid.uuid4()}".encode()).hexdigest()[:12]
        return cls(id=edge_id, source_entity_id=source_id, target_entity_id=target_id, relationship=relationship)


@dataclass
class EntityGraph:
    """Container for entities and edges."""
    entities: Dict[str, Entity] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_entity(self, entity: Entity):
        self.entities[entity.id] = entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def add_edge(self, edge: Edge):
        self.edges.append(edge)


@dataclass
class EntityCollision:
    """A collision between two potentially identical entities."""
    id: str
    entity_a_id: str
    entity_b_id: str
    collision_type: str
    evidence: List[str] = field(default_factory=list)
    created: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Resolution:
    """Resolution of an entity collision."""
    action: DisambiguationAction
    confidence: float
    reason: str
    supporting_evidence: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# NARRATIVE LAYER
# =============================================================================

@dataclass
class NarrativeItem:
    """
    A narrative item - a question or statement we're investigating.
    Maps to document sections or investigation questions.
    """
    id: str
    question: str
    state: NarrativeState = NarrativeState.UNANSWERED
    intent: Intent = Intent.DISCOVER_SUBJECT
    priority: Priority = Priority.MEDIUM

    # Section mapping
    header_id: str = ""
    section_header: str = ""

    # Evidence tracking
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)

    # Query IDs linked to this narrative
    query_ids: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, question: str, priority: Priority = Priority.MEDIUM) -> 'NarrativeItem':
        item_id = hashlib.sha256(f"{question}:{uuid.uuid4()}".encode()).hexdigest()[:12]
        return cls(id=item_id, question=question, priority=priority)

    @property
    def content(self) -> str:
        """For backward compatibility."""
        return self.question

    def add_query(self, query_id: str) -> None:
        """Attach a query ID to this narrative item."""
        if not query_id:
            return
        if query_id not in self.query_ids:
            self.query_ids.append(query_id)


@dataclass
class Section:
    """A document section for reporting."""
    id: str
    header: str
    content: str = ""
    footnotes: List['Footnote'] = field(default_factory=list)
    order: int = 0


@dataclass
class Footnote:
    """A footnote/citation in a document."""
    id: str
    number: int
    text: str
    source_url: str = ""


@dataclass
class SurprisingAnd:
    """
    A surprising conjunction - when two entities unexpectedly appear together.
    E.g., Target company officer also appears in unrelated litigation.
    """
    id: str
    entity_a_id: str
    entity_b_id: str
    context: str
    discovery_source: str
    significance: str = "medium"
    spawned_narrative_id: str = ""


# =============================================================================
# QUERY LAYER
# =============================================================================

@dataclass
class Query:
    """
    A query in the investigation.
    Each query has a K-U classification that determines its shape.
    """
    id: str
    macro: str  # The query string/macro
    state: QueryState = QueryState.PENDING

    # K-U classification
    ku_quadrant: KUQuadrant = KUQuadrant.DISCOVER
    intent: Intent = Intent.DISCOVER_SUBJECT

    # Targeting
    subject: str = ""
    location: str = ""

    # Parent narrative
    narrative_id: str = ""

    # Source IDs this query produced
    source_ids: List[str] = field(default_factory=list)

    # Results
    result_count: int = 0
    relevant_count: int = 0

    created: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(cls, macro: str, narrative_id: str = "", ku: KUQuadrant = KUQuadrant.DISCOVER) -> 'Query':
        query_id = hashlib.sha256(f"{macro}:{uuid.uuid4()}".encode()).hexdigest()[:12]
        return cls(id=query_id, macro=macro, narrative_id=narrative_id, ku_quadrant=ku)

    @property
    def query_string(self) -> str:
        """For backward compatibility."""
        return self.macro


# =============================================================================
# SOURCE LAYER
# =============================================================================

@dataclass
class SourceResult:
    """
    A source document/URL from a query.
    Tracks extraction state and entity links.
    """
    id: str
    url: str
    source_name: str = ""
    title: str = ""
    state: SourceState = SourceState.UNCHECKED

    # Location info
    jurisdiction: str = ""
    source_type: str = ""  # registry, news, court, etc.

    # Content
    content: str = ""
    content_type: str = ""

    # Provenance
    query_id: str = ""
    discovered: datetime = field(default_factory=datetime.utcnow)

    # Results
    raw_results: int = 0
    entity_ids: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, url: str, query_id: str = "", source_name: str = "") -> 'SourceResult':
        source_id = hashlib.sha256(f"{url}:{uuid.uuid4()}".encode()).hexdigest()[:12]
        return cls(id=source_id, url=url, query_id=query_id, source_name=source_name)


# =============================================================================
# COVERAGE TRACKING
# =============================================================================

@dataclass
class NarrativeCoverage:
    """Coverage stats for a narrative item."""
    total_queries: int = 0
    executed_queries: int = 0
    pending_queries: int = 0
    total_sources: int = 0
    checked_sources: int = 0
    total_entities: int = 0


@dataclass
class EntityCoverage:
    """Coverage stats for an entity."""
    core_completeness: float = 0.0
    shell_completeness: float = 0.0
    core_known: Set[str] = field(default_factory=set)
    core_missing: Set[str] = field(default_factory=set)
    shell_known: Set[str] = field(default_factory=set)
    shell_missing: Set[str] = field(default_factory=set)


# =============================================================================
# TOP-LEVEL STATE
# =============================================================================

@dataclass
class Document:
    """Document container for reporting."""
    id: str
    title: str
    sections: List[Section] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)


@dataclass
class InvestigationState:
    """
    Top-level investigation state with relationship tracking.

    RELATIONSHIP HIERARCHY (1:many at each level):
        Goal → Track → Path → NarrativeItem → Query → Source → Entity

    Tracked via:
        narrative_to_queries: Dict[narrative_id, List[query_id]]
        query_to_sources: Dict[query_id, List[source_id]]
        source_to_entities: Dict[source_id, List[entity_id]]
    """
    id: str
    project_id: str
    tasking: str
    phase: InvestigationPhase = InvestigationPhase.INITIALIZING

    # Four layers (Dict[id, object] for O(1) lookup)
    narrative_items: Dict[str, NarrativeItem] = field(default_factory=dict)
    goals: Dict[str, NarrativeGoal] = field(default_factory=dict)
    tracks: Dict[str, NarrativeTrack] = field(default_factory=dict)
    paths: Dict[str, NarrativePath] = field(default_factory=dict)
    queries: Dict[str, Query] = field(default_factory=dict)
    sources: Dict[str, SourceResult] = field(default_factory=dict)
    entities: Dict[str, Entity] = field(default_factory=dict)

    # RELATIONSHIP TRACKING
    narrative_to_queries: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    query_to_sources: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    source_to_entities: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    # Entity graph for connections
    graph: EntityGraph = field(default_factory=EntityGraph)

    # Disambiguation queue
    pending_collisions: List[EntityCollision] = field(default_factory=list)
    resolved_collisions: List[Resolution] = field(default_factory=list)

    # Surprising ANDs detected
    surprising_ands: List[SurprisingAnd] = field(default_factory=list)

    # Document (for Writer agent)
    document: Optional[Document] = None

    # Metadata
    created: datetime = field(default_factory=datetime.utcnow)
    updated: datetime = field(default_factory=datetime.utcnow)
    iteration: int = 0

    @classmethod
    def create(cls, project_id: str, tasking: str) -> 'InvestigationState':
        inv_id = hashlib.sha256(f"{project_id}:{tasking}:{uuid.uuid4()}".encode()).hexdigest()[:16]
        state = cls(id=inv_id, project_id=project_id, tasking=tasking)
        # Initialize defaultdicts properly
        state.narrative_to_queries = defaultdict(list)
        state.query_to_sources = defaultdict(list)
        state.source_to_entities = defaultdict(list)
        return state

    # ─────────────────────────────────────────────────────────────
    # ADD METHODS (maintain relationships)
    # ─────────────────────────────────────────────────────────────

    def add_narrative_item(self, item: NarrativeItem):
        """Add a narrative item."""
        self.narrative_items[item.id] = item
        self.updated = datetime.utcnow()

    def add_goal(self, goal: NarrativeGoal):
        """Add a narrative goal."""
        self.goals[goal.id] = goal
        self.updated = datetime.utcnow()

    def add_track(self, track: NarrativeTrack):
        """Add a narrative track and link to its goal."""
        self.tracks[track.id] = track
        if track.goal_id and track.goal_id in self.goals:
            if track.id not in self.goals[track.goal_id].track_ids:
                self.goals[track.goal_id].track_ids.append(track.id)
        self.updated = datetime.utcnow()

    def add_path(self, path: NarrativePath):
        """Add a narrative path and link to its track."""
        self.paths[path.id] = path
        if path.track_id and path.track_id in self.tracks:
            if path.id not in self.tracks[path.track_id].path_ids:
                self.tracks[path.track_id].path_ids.append(path.id)
        self.updated = datetime.utcnow()

    def link_path_query(self, path_id: str, query_id: str):
        """Attach a query to a narrative path."""
        path = self.paths.get(path_id)
        if not path:
            return
        if query_id not in path.query_ids:
            path.query_ids.append(query_id)
        self.updated = datetime.utcnow()

    def link_path_source(self, path_id: str, source_id: str):
        """Attach a source to a narrative path."""
        path = self.paths.get(path_id)
        if not path:
            return
        if source_id not in path.source_ids:
            path.source_ids.append(source_id)
        self.updated = datetime.utcnow()

    def link_path_entity(self, path_id: str, entity_id: str):
        """Attach an entity to a narrative path."""
        path = self.paths.get(path_id)
        if not path:
            return
        if entity_id not in path.entity_ids:
            path.entity_ids.append(entity_id)
        self.updated = datetime.utcnow()

    def add_query(self, query: Query, narrative_id: str = None):
        """Add a query and link to narrative."""
        self.queries[query.id] = query
        if narrative_id:
            query.narrative_id = narrative_id
            self.narrative_to_queries[narrative_id].append(query.id)
            # Update narrative's query list
            if narrative_id in self.narrative_items:
                self.narrative_items[narrative_id].query_ids.append(query.id)
        self.updated = datetime.utcnow()

    def add_source(self, source: SourceResult, query_id: str = None):
        """Add a source and link to query."""
        self.sources[source.id] = source
        if query_id:
            source.query_id = query_id
            self.query_to_sources[query_id].append(source.id)
            # Update query's source list
            if query_id in self.queries:
                self.queries[query_id].source_ids.append(source.id)
        self.updated = datetime.utcnow()

    def add_entity(self, entity: Entity, source_id: str = None):
        """Add an entity and link to source."""
        self.entities[entity.id] = entity
        self.graph.add_entity(entity)
        if source_id:
            self.source_to_entities[source_id].append(entity.id)
            # Update source's entity list
            if source_id in self.sources:
                self.sources[source_id].entity_ids.append(entity.id)
        self.updated = datetime.utcnow()

    def add_edge(self, edge: Edge):
        """Add an edge to the graph."""
        self.graph.add_edge(edge)
        self.updated = datetime.utcnow()

    def add_collision(self, collision: EntityCollision):
        """Add a collision to pending."""
        self.pending_collisions.append(collision)
        # Mark entities as having collisions
        if collision.entity_a_id in self.entities:
            self.entities[collision.entity_a_id].collision_with.append(collision.entity_b_id)
            self.entities[collision.entity_a_id].disambiguation_state = DisambiguationState.PENDING
        if collision.entity_b_id in self.entities:
            self.entities[collision.entity_b_id].collision_with.append(collision.entity_a_id)
            self.entities[collision.entity_b_id].disambiguation_state = DisambiguationState.PENDING
        self.updated = datetime.utcnow()

    def resolve_collision(self, collision: EntityCollision, resolution: str):
        """
        Resolve a collision with FUSE/REPEL/BINARY_STAR.

        Args:
            collision: The collision to resolve
            resolution: "FUSE", "REPEL", or "BINARY_STAR"
        """
        # Remove from pending
        self.pending_collisions = [c for c in self.pending_collisions
                                   if not (c.entity_a_id == collision.entity_a_id
                                          and c.entity_b_id == collision.entity_b_id)]

        entity_a = self.entities.get(collision.entity_a_id)
        entity_b = self.entities.get(collision.entity_b_id)

        if resolution == "FUSE":
            # Merge entity_b into entity_a
            if entity_a and entity_b:
                # Merge attributes
                for k, v in entity_b.core.items():
                    if k not in entity_a.core:
                        entity_a.core[k] = v
                for k, v in entity_b.shell.items():
                    if k not in entity_a.shell:
                        entity_a.shell[k] = v
                for k, v in entity_b.halo.items():
                    if k not in entity_a.halo:
                        entity_a.halo[k] = v

                entity_a.disambiguation_state = DisambiguationState.FUSED
                entity_a.collision_with = []

                # Remove entity_b
                del self.entities[collision.entity_b_id]

        elif resolution == "REPEL":
            # Mark as different entities
            if entity_a:
                entity_a.disambiguation_state = DisambiguationState.REPELLED
                entity_a.collision_with = [c for c in entity_a.collision_with
                                           if c != collision.entity_b_id]
            if entity_b:
                entity_b.disambiguation_state = DisambiguationState.REPELLED
                entity_b.collision_with = [c for c in entity_b.collision_with
                                           if c != collision.entity_a_id]

            # Add negative edge
            self.graph.add_edge(Edge(
                source_entity_id=collision.entity_a_id,
                target_entity_id=collision.entity_b_id,
                relationship="DIFFERENT_FROM",
                confidence=0.9,
                confirmed=True,
            ))

        else:  # BINARY_STAR
            # Leave in pending state for human review
            if entity_a:
                entity_a.disambiguation_state = DisambiguationState.PENDING
            if entity_b:
                entity_b.disambiguation_state = DisambiguationState.PENDING

        self.updated = datetime.utcnow()

    def add_surprising_and(self, surprising: SurprisingAnd):
        """Add a surprising AND."""
        self.surprising_ands.append(surprising)
        self.updated = datetime.utcnow()

    # ─────────────────────────────────────────────────────────────
    # QUERY METHODS (traverse relationships)
    # ─────────────────────────────────────────────────────────────

    def get_queries_for_narrative(self, narrative_id: str) -> List[Query]:
        """Get all queries linked to a narrative item."""
        query_ids = self.narrative_to_queries.get(narrative_id, [])
        return [self.queries[qid] for qid in query_ids if qid in self.queries]

    def get_sources_for_query(self, query_id: str) -> List[SourceResult]:
        """Get all sources from a query."""
        source_ids = self.query_to_sources.get(query_id, [])
        return [self.sources[sid] for sid in source_ids if sid in self.sources]

    def get_entities_for_source(self, source_id: str) -> List[Entity]:
        """Get all entities from a source."""
        entity_ids = self.source_to_entities.get(source_id, [])
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def get_entities_for_narrative(self, narrative_id: str) -> List[Entity]:
        """Get all entities linked to a narrative (through queries and sources)."""
        entities = []
        for query in self.get_queries_for_narrative(narrative_id):
            for source in self.get_sources_for_query(query.id):
                entities.extend(self.get_entities_for_source(source.id))
        return entities

    # ─────────────────────────────────────────────────────────────
    # COVERAGE COMPUTATION
    # ─────────────────────────────────────────────────────────────

    def get_narrative_coverage(self, narrative_id: str) -> NarrativeCoverage:
        """Compute coverage stats for a narrative item."""
        queries = self.get_queries_for_narrative(narrative_id)
        executed = [q for q in queries if q.state != QueryState.PENDING]
        pending = [q for q in queries if q.state == QueryState.PENDING]

        sources = []
        checked = []
        for q in queries:
            q_sources = self.get_sources_for_query(q.id)
            sources.extend(q_sources)
            checked.extend([s for s in q_sources if s.state == SourceState.CHECKED])

        entities = self.get_entities_for_narrative(narrative_id)

        return NarrativeCoverage(
            total_queries=len(queries),
            executed_queries=len(executed),
            pending_queries=len(pending),
            total_sources=len(sources),
            checked_sources=len(checked),
            total_entities=len(entities),
        )

    def get_entity_coverage(self, entity_id: str) -> EntityCoverage:
        """Compute coverage stats for an entity."""
        entity = self.entities.get(entity_id)
        if not entity:
            return EntityCoverage()

        expected_core = entity._CORE_FIELDS.get(entity.entity_type, set())
        expected_shell = entity._SHELL_FIELDS.get(entity.entity_type, set())

        core_known = set(entity.core.keys())
        shell_known = set(entity.shell.keys())

        return EntityCoverage(
            core_completeness=len(core_known & expected_core) / max(len(expected_core), 1),
            shell_completeness=len(shell_known & expected_shell) / max(len(expected_shell), 1),
            core_known=core_known,
            core_missing=expected_core - core_known,
            shell_known=shell_known,
            shell_missing=expected_shell - shell_known,
        )

    # ─────────────────────────────────────────────────────────────
    # STATE UPDATES
    # ─────────────────────────────────────────────────────────────

    def update_narrative_state(self, narrative_id: str):
        """Update narrative state based on coverage."""
        if narrative_id not in self.narrative_items:
            return

        coverage = self.get_narrative_coverage(narrative_id)
        item = self.narrative_items[narrative_id]

        if coverage.total_queries == 0:
            item.state = NarrativeState.UNANSWERED
        elif coverage.executed_queries == 0:
            item.state = NarrativeState.UNANSWERED
        elif coverage.total_entities > 0:
            # Has some results
            if coverage.pending_queries == 0:
                item.state = NarrativeState.ANSWERED
            else:
                item.state = NarrativeState.PARTIAL
        else:
            item.state = NarrativeState.PARTIAL

    def update_all_narrative_states(self):
        """Update all narrative states."""
        for narrative_id in self.narrative_items:
            self.update_narrative_state(narrative_id)

    # ─────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dict."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "tasking": self.tasking,
            "phase": self.phase.value,
            "iteration": self.iteration,
            "narrative_count": len(self.narrative_items),
            "query_count": len(self.queries),
            "source_count": len(self.sources),
            "entity_count": len(self.entities),
            "pending_collisions": len(self.pending_collisions),
            "surprising_ands": len(self.surprising_ands),
        }
