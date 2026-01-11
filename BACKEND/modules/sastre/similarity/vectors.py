"""
SASTRE Similarity Vectors

Multi-dimensional representation of nodes for similarity computation.
Every node has a position in multi-dimensional space.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Set, List, Tuple
from datetime import date
from enum import Enum
import numpy as np


class EntityType(Enum):
    """Node entity types."""
    PERSON = "person"
    COMPANY = "company"
    ASSET = "asset"
    SOURCE = "source"
    DOCUMENT = "document"
    DOMAIN = "domain"
    QUERY = "query"
    NARRATIVE = "narrative"
    TAG = "tag"
    LOCATION = "location"
    UNKNOWN = "unknown"

    @classmethod
    def from_class(cls, class_name: str) -> "EntityType":
        """Convert @CLASS string to EntityType."""
        mapping = {
            "@PERSON": cls.PERSON,
            "@COMPANY": cls.COMPANY,
            "@ASSET": cls.ASSET,
            "@SOURCE": cls.SOURCE,
            "@DOCUMENT": cls.DOCUMENT,
            "@DOMAIN": cls.DOMAIN,
            "@QUERY": cls.QUERY,
            "@NARRATIVE": cls.NARRATIVE,
            "@TAG": cls.TAG,
            "@LOCATION": cls.LOCATION,
        }
        return mapping.get(class_name.upper(), cls.UNKNOWN)


@dataclass
class TimeRange:
    """Temporal range for activity periods."""
    start: Optional[date] = None
    end: Optional[date] = None

    @property
    def is_set(self) -> bool:
        return self.start is not None or self.end is not None

    def overlaps_with(self, other: "TimeRange") -> bool:
        """Check if two time ranges overlap."""
        if not self.is_set or not other.is_set:
            return False

        self_start = self.start or date.min
        self_end = self.end or date.max
        other_start = other.start or date.min
        other_end = other.end or date.max

        return self_start <= other_end and other_start <= self_end

    def overlap_ratio(self, other: "TimeRange") -> float:
        """Calculate overlap ratio between time ranges."""
        if not self.overlaps_with(other):
            return 0.0

        self_start = self.start or date.min
        self_end = self.end or date.max
        other_start = other.start or date.min
        other_end = other.end or date.max

        overlap_start = max(self_start, other_start)
        overlap_end = min(self_end, other_end)

        if overlap_start > overlap_end:
            return 0.0

        overlap_days = (overlap_end - overlap_start).days
        max_span = max(
            (self_end - self_start).days,
            (other_end - other_start).days,
            1
        )
        return overlap_days / max_span


@dataclass
class SimilarityVector:
    """
    Multi-dimensional position for similarity computation.

    Every node is represented as a point in this high-dimensional space.
    Similarity is computed as distance/overlap across dimensions.
    """

    # Identity
    node_id: str
    entity_type: EntityType

    # === Subject Dimensions ===

    # Name (for embedding-based similarity)
    name: str = ""
    name_embedding: Optional[np.ndarray] = None

    # Attributes (Core/Shell/Halo structure)
    core_attributes: Dict[str, Any] = field(default_factory=dict)  # Unique identifiers, DOB, etc.
    shell_attributes: Dict[str, Any] = field(default_factory=dict)  # Secondary details
    halo_attributes: Dict[str, Any] = field(default_factory=dict)   # Contextual mentions

    # Topics and themes
    topics: Set[str] = field(default_factory=set)     # #FRAUD, #SANCTIONS, etc.
    industries: Set[str] = field(default_factory=set)  # #FINTECH, #REAL_ESTATE
    events: Set[str] = field(default_factory=set)      # #IPO, #BANKRUPTCY

    # === Location Dimensions ===

    # Jurisdiction (where entity appears)
    jurisdictions: Set[str] = field(default_factory=set)  # CY, PA, VG, etc.

    # Source (which sources mention)
    sources: Set[str] = field(default_factory=set)  # Source IDs

    # Temporal (activity period)
    time_range: TimeRange = field(default_factory=TimeRange)

    # === Relationship Dimensions ===

    # Direct connections
    connected_entities: Set[str] = field(default_factory=set)  # Node IDs
    connection_types: Dict[str, Set[str]] = field(default_factory=dict)  # edge_type -> node_ids

    # Shared locations
    shared_addresses: Set[str] = field(default_factory=set)

    # Shared people (for companies)
    shared_officers: Set[str] = field(default_factory=set)
    shared_directors: Set[str] = field(default_factory=set)
    shared_shareholders: Set[str] = field(default_factory=set)

    # Shared companies (for people)
    shared_companies: Set[str] = field(default_factory=set)

    # === Structural Dimensions (for companies) ===

    # Formation info
    formation_agent: Optional[str] = None
    registered_agent: Optional[str] = None

    # Corporate structure
    corporate_structure: Optional[str] = None  # holding, subsidiary, standalone

    # Incorporation info
    incorporation_date: Optional[date] = None
    incorporation_jurisdiction: Optional[str] = None

    def attribute_keys(self) -> Set[str]:
        """Get all attribute keys (Core + Shell)."""
        return set(self.core_attributes.keys()) | set(self.shell_attributes.keys())

    def all_relationships(self) -> Set[str]:
        """Get all connected node IDs regardless of type."""
        result = self.connected_entities.copy()
        for nodes in self.connection_types.values():
            result.update(nodes)
        result.update(self.shared_officers)
        result.update(self.shared_directors)
        result.update(self.shared_shareholders)
        result.update(self.shared_companies)
        return result


@dataclass
class SimilarityScore:
    """Result of similarity computation."""
    total: float                          # 0.0 - 1.0 overall similarity
    breakdown: Dict[str, float]           # Per-dimension scores
    explanation: str                      # Human-readable explanation
    high_dimensions: List[str] = field(default_factory=list)  # Dimensions with high similarity
    low_dimensions: List[str] = field(default_factory=list)   # Dimensions with low similarity

    @property
    def is_high(self) -> bool:
        """Is this a high similarity score?"""
        return self.total > 0.7

    @property
    def is_low(self) -> bool:
        """Is this a low similarity score?"""
        return self.total < 0.3


def build_vector_from_node(node: Dict[str, Any]) -> SimilarityVector:
    """
    Build a SimilarityVector from a node dictionary.

    Expects node structure from Cymonides or Elasticsearch.
    """
    node_id = node.get("id", node.get("_id", ""))
    entity_class = node.get("class", node.get("entityType", "@UNKNOWN"))
    entity_type = EntityType.from_class(entity_class)

    # Extract name
    name = (
        node.get("name", "") or
        node.get("properties", {}).get("name", "") or
        node.get("label", "")
    )

    # Extract attributes by layer
    props = node.get("properties", node.get("data", {}))
    core = {}
    shell = {}
    halo = {}

    # Core: unique identifiers
    for key in ["ssn", "ein", "company_number", "registration_number", "dob", "date_of_birth"]:
        if key in props:
            core[key] = props[key]

    # Shell: secondary details
    for key in ["address", "phone", "email", "nationality", "occupation", "status"]:
        if key in props:
            shell[key] = props[key]

    # Topics/tags
    topics = set(node.get("topics", []))
    topics.update(node.get("tags", []))

    # Jurisdictions
    jurisdictions = set()
    if jur := node.get("jurisdiction"):
        jurisdictions.add(jur)
    jurisdictions.update(node.get("jurisdictions", []))

    # Sources
    sources = set(node.get("source_ids", []))
    if source := node.get("source_id"):
        sources.add(source)

    # Time range
    time_range = TimeRange()
    if first_seen := node.get("first_seen"):
        try:
            time_range.start = date.fromisoformat(first_seen[:10])
        except (ValueError, TypeError):
            pass
    if last_seen := node.get("last_seen"):
        try:
            time_range.end = date.fromisoformat(last_seen[:10])
        except (ValueError, TypeError):
            pass

    # Connected entities (from edges if available)
    connected = set()
    for edge in node.get("edges", []):
        if from_id := edge.get("from_node"):
            if from_id != node_id:
                connected.add(from_id)
        if to_id := edge.get("to_node"):
            if to_id != node_id:
                connected.add(to_id)

    return SimilarityVector(
        node_id=node_id,
        entity_type=entity_type,
        name=name,
        core_attributes=core,
        shell_attributes=shell,
        halo_attributes=halo,
        topics=topics,
        jurisdictions=jurisdictions,
        sources=sources,
        time_range=time_range,
        connected_entities=connected,
    )


def empty_vector(node_id: str, entity_type: EntityType = EntityType.UNKNOWN) -> SimilarityVector:
    """Create an empty vector for a node."""
    return SimilarityVector(node_id=node_id, entity_type=entity_type)
