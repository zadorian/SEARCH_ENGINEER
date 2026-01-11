"""
Shared cognitive types for Grid assessors and the Cognitive Engine.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime

from ..contracts import (
    KUQuadrant,
    SlotType,
    SlotOrigin,
    SlotTarget,
    SlotState,
    SlotPriority,
    SlotStrategy,
    UnifiedSlot,
)


class CognitiveMode(Enum):
    """
    The four cognitive centricities.
    Each mode reveals gaps that others miss.
    """
    NARRATIVE = "narrative"   # The Editor - Story coherence
    SUBJECT = "subject"       # The Biographer - Profile completeness
    LOCATION = "location"     # The Cartographer - Terrain coverage
    NEXUS = "nexus"           # The Detective - Connection logic


class GapDimension(Enum):
    """Dimensions for gap analysis."""
    GEOGRAPHIC = "geographic"   # Where
    TEMPORAL = "temporal"       # When
    SOURCE = "source"           # Which source
    FORMAT = "format"           # What type (PDF, registry, news)


class CertaintyLevel(Enum):
    """Nexus axis certainty levels."""
    CONFIRMED = "confirmed"       # Verified connection
    PROBABLE = "probable"         # Likely but unverified
    POSSIBLE = "possible"         # Speculative
    UNKNOWN = "unknown"           # No information
    CONTRADICTED = "contradicted" # Evidence against


@dataclass
class SubjectAxis:
    """Subject dimension of a gap."""
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None   # person, company, domain
    attribute: Optional[str] = None      # The specific slot (dob, address, etc.)

    def __str__(self) -> str:
        if self.entity_name and self.attribute:
            return f"[#{self.entity_name}:{self.attribute}]"
        if self.entity_name:
            return f"[#{self.entity_name}]"
        return "[?subject]"


@dataclass
class LocationAxis:
    """Location dimension of a gap."""
    domain: Optional[str] = None          # Virtual: domain or URL
    jurisdiction: Optional[str] = None    # Physical: country/region
    source_type: Optional[str] = None     # registry, news, court, etc.
    temporal_range: Optional[Tuple[datetime, datetime]] = None
    format_type: Optional[str] = None     # pdf, html, database

    def __str__(self) -> str:
        parts = []
        if self.jurisdiction:
            parts.append(f"@{self.jurisdiction}")
        if self.source_type:
            parts.append(f":{self.source_type}")
        if self.domain:
            parts.append(f"!{self.domain}")
        return f"[{''.join(parts) or '?location'}]"


@dataclass
class NexusAxis:
    """Nexus/connection dimension of a gap."""
    certainty: CertaintyLevel = CertaintyLevel.UNKNOWN
    connection_type: Optional[str] = None  # officer_of, shareholder_of, etc.
    expected_terms: List[str] = field(default_factory=list)
    surprising_absence: bool = False       # Should exist but doesn't

    def __str__(self) -> str:
        cert = self.certainty.value[:3].upper()
        return f"[{cert}:{self.connection_type or '?'}]"


@dataclass
class GapCoordinates3D:
    """
    Full 3D coordinates of a gap.

    Formula: Gap = (Subject × Location × Nexus)
    """
    subject: SubjectAxis = field(default_factory=SubjectAxis)
    location: LocationAxis = field(default_factory=LocationAxis)
    nexus: NexusAxis = field(default_factory=NexusAxis)
    narrative_intent: str = ""            # What question does this answer?

    def __str__(self) -> str:
        return f"{self.subject} × {self.location} × {self.nexus}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": {
                "entity_id": self.subject.entity_id,
                "entity_name": self.subject.entity_name,
                "entity_type": self.subject.entity_type,
                "attribute": self.subject.attribute,
            },
            "location": {
                "domain": self.location.domain,
                "jurisdiction": self.location.jurisdiction,
                "source_type": self.location.source_type,
                "format_type": self.location.format_type,
            },
            "nexus": {
                "certainty": self.nexus.certainty.value,
                "connection_type": self.nexus.connection_type,
                "expected_terms": self.nexus.expected_terms,
                "surprising_absence": self.nexus.surprising_absence,
            },
            "narrative_intent": self.narrative_intent,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "GapCoordinates3D":
        """Build coordinates from a dict (e.g., UnifiedSlot.coordinates)."""
        subject = data.get("subject", {}) if isinstance(data, dict) else {}
        location = data.get("location", {}) if isinstance(data, dict) else {}
        nexus = data.get("nexus", {}) if isinstance(data, dict) else {}

        certainty_val = nexus.get("certainty", CertaintyLevel.UNKNOWN.value)
        try:
            certainty = CertaintyLevel(certainty_val)
        except ValueError:
            certainty = CertaintyLevel.UNKNOWN

        return GapCoordinates3D(
            subject=SubjectAxis(
                entity_id=subject.get("entity_id"),
                entity_name=subject.get("entity_name"),
                entity_type=subject.get("entity_type"),
                attribute=subject.get("attribute"),
            ),
            location=LocationAxis(
                domain=location.get("domain"),
                jurisdiction=location.get("jurisdiction"),
                source_type=location.get("source_type"),
                format_type=location.get("format_type"),
            ),
            nexus=NexusAxis(
                certainty=certainty,
                connection_type=nexus.get("connection_type"),
                expected_terms=nexus.get("expected_terms", []) or [],
                surprising_absence=bool(nexus.get("surprising_absence")),
            ),
            narrative_intent=data.get("narrative_intent", "") if isinstance(data, dict) else "",
        )


@dataclass
class CognitiveGap:
    """
    A gap identified by the Cognitive Engine.

    Has 3D coordinates and K-U state for intent derivation downstream.
    """
    id: str
    description: str
    discovered_by_mode: CognitiveMode
    coordinates: GapCoordinates3D
    priority: int = 50                    # 0-100, higher = more important

    # K-U state (Sensor output, no intent derivation here)
    subject_known: bool = False
    location_known: bool = False
    ku_quadrant: Optional[KUQuadrant] = None

    # Cross-pollination
    cross_pollination_source: Optional[CognitiveMode] = None
    cross_pollination_insight: str = ""

    # Corpus check result
    corpus_checked: bool = False
    found_in_corpus: bool = False
    corpus_node_ids: List[str] = field(default_factory=list)

    # Resolution
    resolved: bool = False
    resolution_method: str = ""

    # Optional unified slot reference (gap is a view over slots)
    slot: Optional[UnifiedSlot] = None

    def to_unified_slot(self) -> UnifiedSlot:
        """Convert this gap to a unified slot (best-effort)."""
        slot_type = {
            CognitiveMode.SUBJECT: SlotType.ATTRIBUTE,
            CognitiveMode.LOCATION: SlotType.COVERAGE,
            CognitiveMode.NEXUS: SlotType.RELATIONSHIP,
            CognitiveMode.NARRATIVE: SlotType.NARRATIVE,
        }.get(self.discovered_by_mode, SlotType.NARRATIVE)

        target = {
            SlotType.ATTRIBUTE: SlotTarget.SUBJECT,
            SlotType.COVERAGE: SlotTarget.LOCATION,
            SlotType.RELATIONSHIP: SlotTarget.NEXUS,
            SlotType.NARRATIVE: SlotTarget.NARRATIVE,
        }.get(slot_type, SlotTarget.NARRATIVE)

        return UnifiedSlot(
            slot_id=self.id,
            slot_type=slot_type,
            origin=SlotOrigin.AGENT,
            target=target,
            description=self.description,
            state=SlotState.EMPTY,
            priority=SlotPriority.MEDIUM,
            entity_id=self.coordinates.subject.entity_id,
            entity_type=self.coordinates.subject.entity_type,
            field_name=self.coordinates.subject.attribute,
            relationship_type=self.coordinates.nexus.connection_type,
            source_type=self.coordinates.location.source_type,
            jurisdiction=self.coordinates.location.jurisdiction,
            domain=self.coordinates.location.domain,
            coordinates=self.coordinates.to_dict(),
            metadata={
                "priority_score": self.priority,
                "cross_pollination_source": self.cross_pollination_source.value if self.cross_pollination_source else None,
                "cross_pollination_insight": self.cross_pollination_insight or None,
            },
        )


def _infer_mode_from_slot(slot: UnifiedSlot) -> CognitiveMode:
    """Map slot type to cognitive mode."""
    return {
        SlotType.ATTRIBUTE: CognitiveMode.SUBJECT,
        SlotType.COVERAGE: CognitiveMode.LOCATION,
        SlotType.RELATIONSHIP: CognitiveMode.NEXUS,
        SlotType.NARRATIVE: CognitiveMode.NARRATIVE,
    }.get(slot.slot_type, CognitiveMode.NARRATIVE)


def _priority_score_for_slot(slot: UnifiedSlot) -> int:
    """Map slot priority to numeric score (overrideable via metadata)."""
    override = slot.metadata.get("priority_score")
    if isinstance(override, int):
        return override

    return {
        SlotPriority.CRITICAL: 80,
        SlotPriority.HIGH: 70,
        SlotPriority.MEDIUM: 60,
        SlotPriority.LOW: 40,
    }.get(slot.priority, 50)


def slot_to_gap(slot: UnifiedSlot, mode: Optional[CognitiveMode] = None) -> CognitiveGap:
    """Convert a unified slot into a CognitiveGap view."""
    coordinates = GapCoordinates3D.from_dict(slot.coordinates) if slot.coordinates else GapCoordinates3D(
        subject=SubjectAxis(
            entity_id=slot.entity_id,
            entity_name=None,
            entity_type=slot.entity_type,
            attribute=slot.field_name,
        ),
        location=LocationAxis(
            domain=slot.domain,
            jurisdiction=slot.jurisdiction,
            source_type=slot.source_type,
        ),
        nexus=NexusAxis(
            connection_type=slot.relationship_type,
            surprising_absence=bool(slot.metadata.get("surprising_absence")),
        ),
        narrative_intent=slot.description,
    )

    return CognitiveGap(
        id=slot.slot_id,
        description=slot.description,
        discovered_by_mode=mode or _infer_mode_from_slot(slot),
        coordinates=coordinates,
        priority=_priority_score_for_slot(slot),
        slot=slot,
    )
