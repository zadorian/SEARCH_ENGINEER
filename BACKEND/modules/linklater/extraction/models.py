"""
Entity Models

Data classes for extracted entities with provenance tracking.
Also includes Edge models for relationship extraction (Layer 4 - Haiku).

Includes ET3 (Event/Topic/Theme) models for reputation analysis:
- Theme: Classification of coverage (professional, financial, legal, criminal, etc.)
- Phenomenon: Discrete occurrence type (IPO, acquisition, lawsuit, hiring, etc.)
- Event: Phenomenon + Location + Time + Entity = specific occurrence
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


# =============================================================================
# VALID EDGE TYPES - Loaded from ontology/relationships.json
# =============================================================================
# DO NOT HARDCODE - these are loaded dynamically from the authoritative source

def _load_from_ontology():
    """Load valid edges and relations from the ontology module."""
    try:
        from .ontology import get_valid_edges, get_valid_relations
        return get_valid_edges(), get_valid_relations()
    except Exception as e:
        # Fallback if ontology fails to load (for backwards compatibility)
        print(f"[models.py] Warning: Could not load ontology: {e}")
        print("[models.py] Using minimal fallback - relationship extraction may be limited")
        fallback_edges = [
            {"source": "person", "relation": "officer_of", "target": "company"},
            {"source": "person", "relation": "director_of", "target": "company"},
            {"source": "person", "relation": "employed_by", "target": "company"},
            {"source": "company", "relation": "subsidiary_of", "target": "company"},
            {"source": "person", "relation": "married_to", "target": "person"},
        ]
        fallback_relations = [e["relation"] for e in fallback_edges]
        return fallback_edges, fallback_relations


# Load at module import time
VALID_EDGES, VALID_RELATIONS = _load_from_ontology()


@dataclass
class Edge:
    """Extracted relationship/edge between two entities."""
    source_type: str        # "person", "company", "event", etc.
    source_value: str       # The entity value or ID
    relation: str           # Relationship type (from VALID_RELATIONS)
    target_type: str        # "person", "company", "email", "phenomenon", "physical", etc.
    target_value: str       # The target entity value
    confidence: float = 0.8
    evidence: str = ""      # Quote or context from source text
    source_url: str = ""    # Provenance
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional context

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "source_type": self.source_type,
            "source_value": self.source_value,
            "relation": self.relation,
            "target_type": self.target_type,
            "target_value": self.target_value,
            "confidence": self.confidence,
            "evidence": self.evidence[:200] if self.evidence else "",  # Truncate
            "source_url": self.source_url,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    def is_valid(self) -> bool:
        """Check if edge relation is in valid set."""
        return self.relation.lower() in [r.lower() for r in VALID_RELATIONS]


@dataclass
class Entity:
    """Extracted entity with provenance."""
    value: str
    type: str  # "person", "company", "email", "phone"
    archive_urls: List[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    found_in_snapshots: int = 0
    confidence: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "value": self.value,
            "type": self.type,
            "archive_urls": self.archive_urls[:5],  # Limit to 5 URLs
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "found_in_snapshots": self.found_in_snapshots,
            "confidence": self.confidence,
        }


# =============================================================================
# ET3 MODELS - Theme, Phenomenon, Event for reputation analysis
# =============================================================================

# Theme categories (what the coverage is ABOUT)
THEME_CATEGORIES = {
    "professional": "Career, roles, appointments, industry expertise",
    "financial": "Deals, investments, funding, revenue, assets",
    "legal_regulatory": "Lawsuits, compliance, regulatory actions",
    "reputational": "Awards, recognition, reputation, public image",
    "personal": "Family, philanthropy, personal life, lifestyle",
    "criminal": "Investigations, charges, arrests, convictions",
    "political": "Government roles, lobbying, political connections",
    "controversy": "Scandals, disputes, criticism, adverse coverage",
}

# Phenomenon categories (WHAT happened - the event type)
PHENOMENON_CATEGORIES = {
    "corporate": ["ipo", "acquisition", "merger", "spinoff", "bankruptcy", "restructuring", "funding_round"],
    "career": ["hiring", "departure", "promotion", "appointment", "resignation", "retirement", "termination"],
    "legal": ["lawsuit_filed", "lawsuit_settled", "investigation_opened", "charges_filed", "conviction", "acquittal", "regulatory_action"],
    "financial": ["deal_closed", "investment_made", "asset_sale", "dividend_announced", "earnings_reported"],
    "recognition": ["award_received", "ranking_listed", "certification_granted", "honor_bestowed"],
    "crisis": ["scandal_broke", "controversy_emerged", "recall_issued", "incident_occurred"],
}


@dataclass
class Theme:
    """
    Theme extracted from coverage - what the content is ABOUT.

    Node type: theme
    Examples: professional, financial, legal_regulatory, criminal, political
    """
    category: str           # From THEME_CATEGORIES
    label: str              # Human-readable label
    confidence: float = 0.8
    evidence: str = ""      # Quote or context supporting this theme
    source_url: str = ""    # Provenance

    def to_dict(self) -> dict:
        return {
            "type": "theme",
            "category": self.category,
            "label": self.label,
            "confidence": self.confidence,
            "evidence": self.evidence[:200] if self.evidence else "",
            "source_url": self.source_url,
        }


@dataclass
class Phenomenon:
    """
    Phenomenon extracted from coverage - WHAT type of event occurred.

    Node type: phenomenon (maps to ontology "topic" for generic phenomena)
    Examples: ipo, acquisition, lawsuit_filed, hiring, scandal_broke
    """
    category: str           # From PHENOMENON_CATEGORIES keys (corporate, career, legal, etc.)
    phenomenon_type: str    # Specific type (ipo, acquisition, lawsuit_filed, etc.)
    label: str              # Human-readable label
    confidence: float = 0.8
    evidence: str = ""      # Quote or context
    source_url: str = ""    # Provenance

    def to_dict(self) -> dict:
        return {
            "type": "phenomenon",
            "category": self.category,
            "phenomenon_type": self.phenomenon_type,
            "label": self.label,
            "confidence": self.confidence,
            "evidence": self.evidence[:200] if self.evidence else "",
            "source_url": self.source_url,
        }


@dataclass
class Event:
    """
    Discrete event = Phenomenon + Location + Time + Entity.

    Node type: event
    Formula: PHENOMENON + LOCATION + TIME + ENTITY = EVENT
    Example: "IPO" + "NYSE" + "2024-03-15" + "Acme Corp" = "Acme Corp IPO on NYSE"

    Events are the anchored, specific occurrences that link:
    - involves_entity -> person/company
    - anchored_to -> temporal (date)
    - anchored_to -> physical (location)
    - instance_of -> phenomenon (the generic event type)
    """
    # Core identity
    event_id: str                   # Unique identifier
    label: str                      # Human-readable description
    phenomenon_type: str            # From Phenomenon.phenomenon_type
    phenomenon_category: str        # From Phenomenon.category

    # Involved entities
    primary_entity: str             # Main entity involved (person/company name)
    primary_entity_type: str        # "person" or "company"
    related_entities: List[str] = field(default_factory=list)  # Other involved entities

    # Anchors (coordinates)
    date: Optional[str] = None              # ISO date or date range
    date_precision: str = "unknown"         # "exact", "month", "year", "approximate"
    location_geographic: str = ""           # City, country, region
    location_institutional: str = ""        # NYSE, Delaware Court, SEC, etc.

    # Metadata
    confidence: float = 0.8
    evidence: str = ""              # Quote or context
    source_urls: List[str] = field(default_factory=list)  # Multiple sources
    first_seen: str = ""            # First coverage date
    coverage_count: int = 1         # How many sources mention this event

    # Themes associated with this event
    themes: List[str] = field(default_factory=list)  # Theme categories

    def to_dict(self) -> dict:
        return {
            "type": "event",
            "event_id": self.event_id,
            "label": self.label,
            "phenomenon_type": self.phenomenon_type,
            "phenomenon_category": self.phenomenon_category,
            "primary_entity": self.primary_entity,
            "primary_entity_type": self.primary_entity_type,
            "related_entities": self.related_entities,
            "date": self.date,
            "date_precision": self.date_precision,
            "location_geographic": self.location_geographic,
            "location_institutional": self.location_institutional,
            "confidence": self.confidence,
            "evidence": self.evidence[:300] if self.evidence else "",
            "source_urls": self.source_urls[:5],
            "first_seen": self.first_seen,
            "coverage_count": self.coverage_count,
            "themes": self.themes,
        }

    def generate_edges(self) -> List[Edge]:
        """
        Generate ET3 edges for this event.

        Creates edges following the Event formula:
        PHENOMENON + LOCATION + TIME + ENTITY = EVENT

        Edge types:
        - involves_entity → primary and related entities
        - instance_of → phenomenon type (generic event category)
        - anchored_to → location (geographic/institutional)
        - extracted_from → source URLs

        Note: anchored_to temporal is handled separately via generate_temporal_hierarchy()
        which also creates the temporal hierarchy nodes (day→month→year).
        """
        edges = []

        # 1. Event involves primary entity
        edges.append(Edge(
            source_type="event",
            source_value=self.event_id,
            relation="involves_entity",
            target_type=self.primary_entity_type,
            target_value=self.primary_entity,
            confidence=self.confidence,
            evidence=self.evidence,
        ))

        # 2. Event involves related entities
        for entity in self.related_entities:
            edges.append(Edge(
                source_type="event",
                source_value=self.event_id,
                relation="involves_entity",
                target_type="entity",  # Generic, could be person or company
                target_value=entity,
                confidence=self.confidence * 0.9,
            ))

        # 3. Event is instance_of phenomenon type (generic → specific)
        if self.phenomenon_type:
            edges.append(Edge(
                source_type="event",
                source_value=self.event_id,
                relation="instance_of",
                target_type="phenomenon",
                target_value=self.phenomenon_type,
                confidence=1.0,  # Deterministic relationship
                metadata={"category": self.phenomenon_category}
            ))

        # 4. Event anchored_to geographic location
        if self.location_geographic:
            edges.append(Edge(
                source_type="event",
                source_value=self.event_id,
                relation="anchored_to",
                target_type="physical",  # LOCATION class coordinate
                target_value=self.location_geographic,
                confidence=self.confidence,
                metadata={"location_type": "geographic"}
            ))

        # 5. Event anchored_to institutional location (SEC, NYSE, Delaware Court, etc.)
        if self.location_institutional:
            edges.append(Edge(
                source_type="event",
                source_value=self.event_id,
                relation="anchored_to",
                target_type="virtual",  # Institutional = virtual coordinate
                target_value=self.location_institutional,
                confidence=self.confidence,
                metadata={"location_type": "institutional"}
            ))

        # 6. Event extracted_from source URLs
        for url in self.source_urls:
            edges.append(Edge(
                source_type="event",
                source_value=self.event_id,
                relation="extracted_from",
                target_type="url",
                target_value=url,
                confidence=1.0,  # Deterministic provenance
            ))

        return edges


@dataclass
class ExtractionResult:
    """Result from entity extraction and relationship extraction."""
    # Core entities
    persons: List[Entity] = field(default_factory=list)
    companies: List[Entity] = field(default_factory=list)
    emails: List[Entity] = field(default_factory=list)
    phones: List[Entity] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)  # Layer 4: Relationships

    # ET3: Themes, Phenomena, Events
    themes: List[Theme] = field(default_factory=list)
    phenomena: List[Phenomenon] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)

    # Metadata
    backend_used: str = ""
    relationship_backend: str = ""  # Which model extracted relationships
    processing_time: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "persons": [e.to_dict() for e in self.persons],
            "companies": [e.to_dict() for e in self.companies],
            "emails": [e.to_dict() for e in self.emails],
            "phones": [e.to_dict() for e in self.phones],
            "edges": [e.to_dict() for e in self.edges],
            # ET3
            "themes": [t.to_dict() for t in self.themes],
            "phenomena": [p.to_dict() for p in self.phenomena],
            "events": [e.to_dict() for e in self.events],
            # Metadata
            "backend_used": self.backend_used,
            "relationship_backend": self.relationship_backend,
            "processing_time": self.processing_time,
        }

    @property
    def total_entities(self) -> int:
        """Total count of all entities."""
        return len(self.persons) + len(self.companies) + len(self.emails) + len(self.phones)

    @property
    def total_edges(self) -> int:
        """Total count of all relationships/edges."""
        return len(self.edges)

    @property
    def total_et3(self) -> int:
        """Total count of ET3 elements (themes, phenomena, events)."""
        return len(self.themes) + len(self.phenomena) + len(self.events)

    def get_all_event_edges(self) -> List[Edge]:
        """Generate all edges from events."""
        edges = []
        for event in self.events:
            edges.extend(event.generate_edges())
        return edges
