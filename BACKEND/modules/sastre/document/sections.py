"""
SASTRE Document Sections

Section definitions, states, and streaming targets (watchers).
Each watcher monitors a document section and routes findings to it.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from enum import Enum


class SectionState(Enum):
    """State of a document section."""
    EMPTY = "empty"           # No content yet
    INCOMPLETE = "incomplete" # Has gaps [?] or partial content
    COMPLETE = "complete"     # Sufficiently answered
    PARKED = "parked"         # Explicitly set aside


class SectionIntent(Enum):
    """What this section aims to accomplish."""
    DISCOVER_SUBJECT = "discover_subject"    # Find new entities/topics
    DISCOVER_LOCATION = "discover_location"  # Find new sources/jurisdictions
    ENRICH_SUBJECT = "enrich_subject"        # Fill slots on known entities
    ENRICH_LOCATION = "enrich_location"      # Check known sources deeper


class KUQuadrant(Enum):
    """Known-Unknown classification."""
    VERIFY = "verify"       # K-K: Known subject, known location
    TRACE = "trace"         # K-U: Known subject, unknown location
    EXTRACT = "extract"     # U-K: Unknown subject, known location
    DISCOVER = "discover"   # U-U: Unknown subject, unknown location


@dataclass
class SectionGap:
    """A gap marker [?] in a section."""
    description: str
    position: int           # Character position in content
    priority: str = "medium"
    suggested_query: Optional[str] = None


@dataclass
class SectionMeta:
    """Machine-readable metadata for a section."""
    intent: SectionIntent
    k_u_quadrant: KUQuadrant
    state: SectionState
    target_entities: List[str] = field(default_factory=list)
    target_topics: List[str] = field(default_factory=list)
    filters: Dict[str, str] = field(default_factory=dict)  # ##jurisdiction:CY, etc.


@dataclass
class Section:
    """A section within the investigation document."""
    id: str                              # Unique section ID
    header: str                          # Section header (## Header)
    content: str = ""                    # Markdown content

    # State tracking
    state: SectionState = SectionState.EMPTY
    gaps: List[SectionGap] = field(default_factory=list)

    # Intent and classification
    intent: SectionIntent = SectionIntent.ENRICH_SUBJECT
    k_u_quadrant: KUQuadrant = KUQuadrant.TRACE

    # Watcher meta (for streaming targets)
    watcher_meta: Dict[str, Any] = field(default_factory=dict)

    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    finding_count: int = 0

    @property
    def is_empty(self) -> bool:
        return self.state == SectionState.EMPTY or not self.content.strip()

    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0

    @property
    def clean_header(self) -> str:
        """Header without ## prefix or metadata."""
        h = self.header.replace("## ", "").replace("##", "")
        # Remove inline metadata [KEY:VALUE]
        h = re.sub(r'\[([A-Z_]+):([^\]]+)\]', '', h)
        return h.strip()


@dataclass
class Watcher:
    """
    A watcher monitors a document section and routes findings to it.

    Watchers are the bridge between the investigation loop and the document.
    They define what findings go where and how they should be formatted.
    """
    id: str
    section_id: str
    section_header: str

    # What this watcher is looking for
    target_entities: List[str] = field(default_factory=list)  # Entity IDs to track
    target_topics: List[str] = field(default_factory=list)    # Topics to capture
    entity_types: Set[str] = field(default_factory=set)       # @PERSON, @COMPANY, etc.

    # Filters
    jurisdiction_filter: Optional[str] = None
    time_filter: Optional[str] = None
    source_filter: Optional[str] = None

    # Output configuration
    format_style: str = "core_shell_halo"  # How to format findings
    include_footnotes: bool = True
    confidence_threshold: float = 0.5      # Minimum confidence to include

    # State
    active: bool = True
    finding_count: int = 0
    last_finding: Optional[datetime] = None

    def matches(self, finding: Dict[str, Any]) -> bool:
        """Check if a finding matches this watcher's criteria."""
        # Entity type check
        if self.entity_types:
            finding_type = finding.get("entity_type", "").upper()
            if finding_type and f"@{finding_type}" not in self.entity_types:
                return False

        # Jurisdiction check
        if self.jurisdiction_filter:
            finding_jur = finding.get("jurisdiction", "")
            if finding_jur and finding_jur.upper() != self.jurisdiction_filter.upper():
                return False

        # Target entity check
        if self.target_entities:
            finding_id = finding.get("id", "")
            finding_name = finding.get("name", "").lower()
            if not any(
                t.lower() in finding_name or t == finding_id
                for t in self.target_entities
            ):
                return False

        # Confidence check
        confidence = finding.get("confidence", 1.0)
        if confidence < self.confidence_threshold:
            return False

        return True


class WatcherRegistry:
    """Registry of active watchers for a document."""

    def __init__(self):
        self.watchers: Dict[str, Watcher] = {}  # section_id -> Watcher
        self._by_entity_type: Dict[str, List[str]] = {}  # @TYPE -> [watcher_ids]
        self._by_topic: Dict[str, List[str]] = {}  # topic -> [watcher_ids]

    def register(self, watcher: Watcher) -> None:
        """Register a watcher."""
        self.watchers[watcher.section_id] = watcher

        # Index by entity type
        for et in watcher.entity_types:
            if et not in self._by_entity_type:
                self._by_entity_type[et] = []
            self._by_entity_type[et].append(watcher.id)

        # Index by topic
        for topic in watcher.target_topics:
            if topic not in self._by_topic:
                self._by_topic[topic] = []
            self._by_topic[topic].append(watcher.id)

    def unregister(self, section_id: str) -> None:
        """Unregister a watcher."""
        if section_id in self.watchers:
            watcher = self.watchers[section_id]

            # Remove from indexes
            for et in watcher.entity_types:
                if et in self._by_entity_type:
                    self._by_entity_type[et] = [
                        w for w in self._by_entity_type[et] if w != watcher.id
                    ]

            for topic in watcher.target_topics:
                if topic in self._by_topic:
                    self._by_topic[topic] = [
                        w for w in self._by_topic[topic] if w != watcher.id
                    ]

            del self.watchers[section_id]

    def get(self, section_id: str) -> Optional[Watcher]:
        """Get watcher by section ID."""
        return self.watchers.get(section_id)

    def find_matching(self, finding: Dict[str, Any]) -> List[Watcher]:
        """Find all watchers that match a finding."""
        matching = []
        for watcher in self.watchers.values():
            if watcher.active and watcher.matches(finding):
                matching.append(watcher)
        return matching

    def get_by_entity_type(self, entity_type: str) -> List[Watcher]:
        """Get watchers interested in a specific entity type."""
        watcher_ids = self._by_entity_type.get(entity_type, [])
        return [self.watchers[sid] for sid in watcher_ids if sid in self.watchers]

    def get_by_topic(self, topic: str) -> List[Watcher]:
        """Get watchers interested in a specific topic."""
        watcher_ids = self._by_topic.get(topic, [])
        return [self.watchers[sid] for sid in watcher_ids if sid in self.watchers]

    def all_active(self) -> List[Watcher]:
        """Get all active watchers."""
        return [w for w in self.watchers.values() if w.active]


def create_watcher_from_section(section: Section) -> Watcher:
    """Create a watcher from a section's configuration."""
    import uuid

    # Parse entity types from watcher meta
    entity_types = set()
    if meta := section.watcher_meta:
        for et in meta.get("entity_types", []):
            entity_types.add(et.upper() if et.startswith("@") else f"@{et.upper()}")

    return Watcher(
        id=f"watcher_{uuid.uuid4().hex[:8]}",
        section_id=section.id,
        section_header=section.clean_header,
        target_entities=section.watcher_meta.get("target_entities", []),
        target_topics=section.watcher_meta.get("target_topics", []),
        entity_types=entity_types,
        jurisdiction_filter=section.watcher_meta.get("jurisdiction"),
        time_filter=section.watcher_meta.get("time"),
        source_filter=section.watcher_meta.get("source"),
        format_style=section.watcher_meta.get("format", "core_shell_halo"),
        include_footnotes=section.watcher_meta.get("footnotes", True),
        confidence_threshold=section.watcher_meta.get("confidence_threshold", 0.5),
    )
