"""
Gap → Watcher Bridge

Converts high-priority cognitive gaps into active watchers that drive the investigation.

THE MISSING LINK:
=================
The CognitiveGapAnalyzer detects gaps (missing slots, unconfirmed edges, coverage holes).
The WatcherService creates queries that fill gaps.
But there was no automatic conversion - gaps sat there until manually addressed.

This bridge:
1. Listens for high-priority gaps from Grid assessment
2. Creates appropriate watchers (entity, event, topic) based on gap type
3. Connects those watchers to the SlotIterator for query generation
4. Feeds results back to update slot states

ALIGNS WITH: Abacus v4.2 - "Hungry slots drive intent; the loop runs until sufficiency"
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from ..contracts import (
    UnifiedSlot, SlotType, SlotTarget, SlotState, SlotPriority,
    KUQuadrant,
)
from ..grid.cognitive_types import (
    CognitiveGap, CognitiveMode, GapCoordinates3D,
    NexusAxis, SubjectAxis, LocationAxis, CertaintyLevel,
)
from ..query.lab import (
    QueryLab, CompilationResult, Silo,
    KUTarget, KUCube, classify_ku_cube,
    NEXUS_RELATIONSHIP_TYPES,
)

logger = logging.getLogger(__name__)


# =============================================================================
# WATCHER TYPES (matching watcherRouter.ts)
# =============================================================================

class WatcherType(Enum):
    """Types of watchers that can be created from gaps."""
    ENTITY = "entity"      # Watch for specific entity (person, company)
    EVENT = "event"        # Watch for events (IPO, lawsuit, breach)
    TOPIC = "topic"        # Watch for topics (sanctions, compliance)
    NEXUS = "nexus"        # Watch for relationships (officer_of, shareholder_of)


@dataclass
class WatcherSpec:
    """Specification for creating a watcher from a gap."""
    watcher_type: WatcherType
    name: str
    description: str
    target_entity_id: Optional[str] = None
    target_entity_name: Optional[str] = None
    target_entity_type: Optional[str] = None
    relationship_type: Optional[str] = None  # For NEXUS watchers
    jurisdiction: Optional[str] = None
    event_type: Optional[str] = None  # For EVENT watchers
    topic_keywords: List[str] = field(default_factory=list)  # For TOPIC watchers
    priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatcherCreationResult:
    """Result of converting gaps to watchers."""
    watchers_created: List[WatcherSpec] = field(default_factory=list)
    gaps_converted: List[str] = field(default_factory=list)  # Gap IDs
    gaps_skipped: List[Tuple[str, str]] = field(default_factory=list)  # (gap_id, reason)
    queries_generated: List[CompilationResult] = field(default_factory=list)


# =============================================================================
# GAP → WATCHER CONVERSION LOGIC
# =============================================================================

class GapWatcherBridge:
    """
    Bridges gaps to watchers, creating active investigation tasks.

    The bridge:
    1. Filters gaps by priority threshold
    2. Determines appropriate watcher type from gap's cognitive mode
    3. Extracts watcher parameters from gap coordinates
    4. Generates initial query using QueryLab compiler
    """

    # Priority threshold for automatic watcher creation
    AUTO_WATCHER_THRESHOLD = 70  # Only HIGH and CRITICAL priority

    # Maximum watchers per gap batch (prevent runaway)
    MAX_WATCHERS_PER_BATCH = 10

    def __init__(self, query_lab: Optional[QueryLab] = None):
        self.query_lab = query_lab or QueryLab()

    def convert_gaps_to_watchers(
        self,
        gaps: List[CognitiveGap],
        auto_generate_queries: bool = True,
        priority_threshold: Optional[int] = None,
    ) -> WatcherCreationResult:
        """
        Convert cognitive gaps to watcher specifications.

        Args:
            gaps: List of gaps from CognitiveGapAnalyzer
            auto_generate_queries: Whether to compile initial queries
            priority_threshold: Override default threshold (0-100)

        Returns:
            WatcherCreationResult with specs and any queries
        """
        result = WatcherCreationResult()
        threshold = priority_threshold or self.AUTO_WATCHER_THRESHOLD

        # Sort by priority (highest first) and limit
        sorted_gaps = sorted(gaps, key=lambda g: g.priority, reverse=True)

        for gap in sorted_gaps[:self.MAX_WATCHERS_PER_BATCH]:
            # Filter by priority
            if gap.priority < threshold:
                result.gaps_skipped.append((gap.id, f"Priority {gap.priority} below threshold {threshold}"))
                continue

            # Skip already resolved gaps
            if gap.resolved:
                result.gaps_skipped.append((gap.id, "Already resolved"))
                continue

            # Convert gap to watcher spec
            try:
                spec = self._gap_to_watcher_spec(gap)
                if spec:
                    result.watchers_created.append(spec)
                    result.gaps_converted.append(gap.id)

                    # Generate initial query if requested
                    if auto_generate_queries:
                        query = self._generate_query_for_spec(spec, gap)
                        if query:
                            result.queries_generated.append(query)
                else:
                    result.gaps_skipped.append((gap.id, "Could not determine watcher type"))

            except Exception as e:
                logger.error(f"Failed to convert gap {gap.id}: {e}")
                result.gaps_skipped.append((gap.id, str(e)))

        return result

    def _gap_to_watcher_spec(self, gap: CognitiveGap) -> Optional[WatcherSpec]:
        """Convert a single gap to a watcher specification."""
        coords = gap.coordinates
        mode = gap.discovered_by_mode

        # Route to appropriate converter based on cognitive mode
        if mode == CognitiveMode.SUBJECT:
            return self._subject_gap_to_watcher(gap, coords)
        elif mode == CognitiveMode.LOCATION:
            return self._location_gap_to_watcher(gap, coords)
        elif mode == CognitiveMode.NEXUS:
            return self._nexus_gap_to_watcher(gap, coords)
        elif mode == CognitiveMode.NARRATIVE:
            return self._narrative_gap_to_watcher(gap, coords)
        else:
            return None

    def _subject_gap_to_watcher(
        self,
        gap: CognitiveGap,
        coords: GapCoordinates3D,
    ) -> Optional[WatcherSpec]:
        """Convert SUBJECT mode gap to entity watcher."""
        subject = coords.subject

        if not subject.entity_name and not subject.entity_id:
            # Can't create entity watcher without entity reference
            return None

        return WatcherSpec(
            watcher_type=WatcherType.ENTITY,
            name=f"Watch: {subject.entity_name or subject.entity_id}",
            description=f"Fill missing {subject.attribute or 'information'} for {subject.entity_name}",
            target_entity_id=subject.entity_id,
            target_entity_name=subject.entity_name,
            target_entity_type=subject.entity_type,
            jurisdiction=coords.location.jurisdiction,
            priority=gap.priority,
            metadata={
                "gap_id": gap.id,
                "slot_attribute": subject.attribute,
                "source_mode": "subject",
            },
        )

    def _location_gap_to_watcher(
        self,
        gap: CognitiveGap,
        coords: GapCoordinates3D,
    ) -> Optional[WatcherSpec]:
        """Convert LOCATION mode gap to topic watcher (coverage gap)."""
        location = coords.location

        # Location gaps are usually coverage issues - watch for any content in that location
        keywords = []
        if location.source_type:
            keywords.append(location.source_type)
        if location.jurisdiction:
            keywords.append(location.jurisdiction)

        return WatcherSpec(
            watcher_type=WatcherType.TOPIC,
            name=f"Coverage: {location.jurisdiction or location.domain or 'unknown'}",
            description=f"Monitor {location.source_type or 'sources'} in {location.jurisdiction or 'target location'}",
            jurisdiction=location.jurisdiction,
            topic_keywords=keywords or ["corporate", "registry"],
            priority=gap.priority,
            metadata={
                "gap_id": gap.id,
                "domain": location.domain,
                "source_type": location.source_type,
                "source_mode": "location",
            },
        )

    def _nexus_gap_to_watcher(
        self,
        gap: CognitiveGap,
        coords: GapCoordinates3D,
    ) -> Optional[WatcherSpec]:
        """Convert NEXUS mode gap to nexus watcher (relationship gap)."""
        nexus = coords.nexus
        subject = coords.subject

        if not nexus.connection_type:
            # Can't create nexus watcher without relationship type
            # Fall back to entity watcher if we have subject
            if subject.entity_name:
                return self._subject_gap_to_watcher(gap, coords)
            return None

        return WatcherSpec(
            watcher_type=WatcherType.NEXUS,
            name=f"Nexus: {nexus.connection_type}",
            description=f"Find {nexus.connection_type} relationships" +
                       (f" for {subject.entity_name}" if subject.entity_name else ""),
            target_entity_id=subject.entity_id,
            target_entity_name=subject.entity_name,
            target_entity_type=subject.entity_type,
            relationship_type=nexus.connection_type,
            jurisdiction=coords.location.jurisdiction,
            priority=gap.priority,
            metadata={
                "gap_id": gap.id,
                "surprising_absence": nexus.surprising_absence,
                "certainty": nexus.certainty.value if nexus.certainty else None,
                "expected_terms": nexus.expected_terms,
                "source_mode": "nexus",
            },
        )

    def _narrative_gap_to_watcher(
        self,
        gap: CognitiveGap,
        coords: GapCoordinates3D,
    ) -> Optional[WatcherSpec]:
        """Convert NARRATIVE mode gap to event or topic watcher."""
        intent = coords.narrative_intent

        # Parse narrative intent for keywords
        keywords = self._extract_keywords_from_intent(intent)

        # Determine if this is an event or topic watcher
        event_indicators = ["IPO", "lawsuit", "breach", "merger", "acquisition", "sanction"]
        is_event = any(k.lower() in intent.lower() for k in event_indicators)

        if is_event:
            return WatcherSpec(
                watcher_type=WatcherType.EVENT,
                name=f"Event: {intent[:50]}",
                description=intent,
                event_type=self._infer_event_type(intent),
                jurisdiction=coords.location.jurisdiction,
                topic_keywords=keywords,
                priority=gap.priority,
                metadata={
                    "gap_id": gap.id,
                    "narrative_intent": intent,
                    "source_mode": "narrative",
                },
            )
        else:
            return WatcherSpec(
                watcher_type=WatcherType.TOPIC,
                name=f"Topic: {intent[:50]}",
                description=intent,
                jurisdiction=coords.location.jurisdiction,
                topic_keywords=keywords,
                priority=gap.priority,
                metadata={
                    "gap_id": gap.id,
                    "narrative_intent": intent,
                    "source_mode": "narrative",
                },
            )

    def _extract_keywords_from_intent(self, intent: str) -> List[str]:
        """Extract searchable keywords from narrative intent."""
        # Simple extraction - in production would use NLP
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "must", "shall",
                      "can", "need", "dare", "ought", "used", "to", "of", "in",
                      "for", "on", "with", "at", "by", "from", "as", "into",
                      "through", "during", "before", "after", "above", "below",
                      "between", "under", "again", "further", "then", "once",
                      "what", "which", "who", "whom", "this", "that", "these",
                      "those", "am", "and", "or", "but", "if", "because", "until",
                      "while", "find", "get", "look", "search", "identify"}

        words = intent.lower().split()
        keywords = [w.strip(".,?!\"'") for w in words
                   if len(w) > 3 and w.lower() not in stop_words]
        return keywords[:10]  # Limit to 10 keywords

    def _infer_event_type(self, intent: str) -> Optional[str]:
        """Infer event type from narrative intent."""
        intent_lower = intent.lower()

        event_patterns = {
            "evt_ipo": ["ipo", "initial public offering", "going public"],
            "evt_lawsuit": ["lawsuit", "litigation", "sued", "court case"],
            "evt_breach": ["data breach", "security breach", "hack"],
            "evt_merger": ["merger", "acquisition", "acquired", "merged"],
            "evt_sanction": ["sanction", "blacklist", "designated"],
            "evt_bankruptcy": ["bankruptcy", "insolvency", "liquidation"],
        }

        for event_type, patterns in event_patterns.items():
            if any(p in intent_lower for p in patterns):
                return event_type

        return None

    def _generate_query_for_spec(
        self,
        spec: WatcherSpec,
        gap: CognitiveGap,
    ) -> Optional[CompilationResult]:
        """Generate initial query for a watcher spec using QueryLab."""
        try:
            # Route to appropriate compiler based on watcher type
            if spec.watcher_type == WatcherType.ENTITY:
                return self.query_lab.compile(
                    entity_name=spec.target_entity_name or "",
                    entity_type=spec.target_entity_type or "unknown",
                    jurisdiction=spec.jurisdiction,
                    slot_type=spec.metadata.get("slot_attribute"),
                    context={
                        "watcher_id": spec.name,
                        "gap_id": gap.id,
                    },
                )

            elif spec.watcher_type == WatcherType.NEXUS:
                return self.query_lab.compile_nexus(
                    relationship_type=spec.relationship_type or "associated_with",
                    from_entity={"name": spec.target_entity_name, "type": spec.target_entity_type}
                                if spec.target_entity_name else None,
                    jurisdiction=spec.jurisdiction,
                    context={
                        "watcher_id": spec.name,
                        "gap_id": gap.id,
                    },
                )

            elif spec.watcher_type in (WatcherType.EVENT, WatcherType.TOPIC):
                # Use general compile with keywords
                keywords = " ".join(spec.topic_keywords[:5])
                return self.query_lab.compile(
                    entity_name=keywords,
                    entity_type="topic",
                    jurisdiction=spec.jurisdiction,
                    context={
                        "watcher_id": spec.name,
                        "gap_id": gap.id,
                        "is_topic_search": True,
                    },
                )

            return None

        except Exception as e:
            logger.error(f"Failed to generate query for {spec.name}: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def gaps_to_watchers(
    gaps: List[CognitiveGap],
    priority_threshold: int = 70,
) -> WatcherCreationResult:
    """
    Convenience function to convert gaps to watchers.

    Usage:
        from SASTRE.bridges.gap_watcher_bridge import gaps_to_watchers

        result = gaps_to_watchers(analyzer.gaps, priority_threshold=60)
        for spec in result.watchers_created:
            watcher_service.create(spec)
    """
    bridge = GapWatcherBridge()
    return bridge.convert_gaps_to_watchers(gaps, priority_threshold=priority_threshold)


def create_nexus_watcher(
    relationship_type: str,
    entity_name: Optional[str] = None,
    entity_type: Optional[str] = None,
    jurisdiction: Optional[str] = None,
) -> Tuple[WatcherSpec, CompilationResult]:
    """
    Create a NEXUS watcher for a specific relationship type.

    Usage:
        spec, query = create_nexus_watcher(
            "officer_of",
            entity_name="Acme Corp",
            jurisdiction="UK"
        )
    """
    bridge = GapWatcherBridge()

    spec = WatcherSpec(
        watcher_type=WatcherType.NEXUS,
        name=f"Nexus: {relationship_type}" + (f" - {entity_name}" if entity_name else ""),
        description=f"Watch for {relationship_type} relationships",
        target_entity_name=entity_name,
        target_entity_type=entity_type,
        relationship_type=relationship_type,
        jurisdiction=jurisdiction,
        priority=70,
    )

    query = bridge.query_lab.compile_nexus(
        relationship_type=relationship_type,
        from_entity={"name": entity_name, "type": entity_type} if entity_name else None,
        jurisdiction=jurisdiction,
    )

    return spec, query
