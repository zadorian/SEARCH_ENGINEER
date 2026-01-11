"""
Nexus assessor - Mode D (Detective).
"""

from typing import List, Any, Set

from ..contracts import UnifiedSlot, SlotType, SlotOrigin, SlotTarget, SlotState, SlotPriority
from .cognitive_types import (
    CognitiveGap,
    CognitiveMode,
    GapCoordinates3D,
    SubjectAxis,
    NexusAxis,
    CertaintyLevel,
    slot_to_gap,
)


class NexusAssessor:
    """Assess connection logic and surprising absences."""

    def __init__(self, state: Any):
        self.state = state

    async def assess(self) -> List[CognitiveGap]:
        gaps: List[CognitiveGap] = []

        graph = getattr(self.state, "graph", None)
        if not graph:
            return gaps

        edges = getattr(graph, "edges", [])
        entities = getattr(self.state, "entities", {})

        for edge in edges:
            if not getattr(edge, "confirmed", True):
                source_id = edge.source_entity_id
                target_id = edge.target_entity_id
                source_name = entities.get(source_id, {})
                target_name = entities.get(target_id, {})

                if hasattr(source_name, "name"):
                    source_name = source_name.name
                if hasattr(target_name, "name"):
                    target_name = target_name.name

                slot_id = f"nexus_{source_id}_{target_id}_unconfirmed"
                unified = UnifiedSlot(
                    slot_id=slot_id,
                    slot_type=SlotType.RELATIONSHIP,
                    origin=SlotOrigin.AGENT,
                    target=SlotTarget.NEXUS,
                    description=f"Unconfirmed connection: {source_name} -> {target_name}",
                    state=SlotState.PARTIAL,
                    priority=SlotPriority.HIGH,
                    entity_id=source_id,
                    relationship_type=getattr(edge, "relationship", "related_to"),
                    coordinates=GapCoordinates3D(
                        subject=SubjectAxis(entity_id=source_id, entity_name=str(source_name)),
                        nexus=NexusAxis(
                            certainty=CertaintyLevel.POSSIBLE,
                            connection_type=getattr(edge, "relationship", "related_to"),
                            expected_terms=[str(source_name), str(target_name)],
                        ),
                        narrative_intent=f"Verify connection: {source_name} to {target_name}",
                    ).to_dict(),
                    metadata={"priority_score": 70, "expected_terms": [str(source_name), str(target_name)]},
                )
                gaps.append(slot_to_gap(unified, CognitiveMode.NEXUS))

        gaps.extend(await self._detect_surprising_absences())
        return gaps

    async def _detect_surprising_absences(self) -> List[CognitiveGap]:
        gaps: List[CognitiveGap] = []
        entities = getattr(self.state, "entities", {})
        graph = getattr(self.state, "graph", None)

        if not graph:
            return gaps

        edges = getattr(graph, "edges", [])
        existing_pairs: Set[tuple] = set()
        for edge in edges:
            existing_pairs.add((edge.source_entity_id, edge.target_entity_id))
            existing_pairs.add((edge.target_entity_id, edge.source_entity_id))

        for entity_id, entity in entities.items():
            entity_type = getattr(entity, "entity_type", "")
            entity_name = getattr(entity, "name", entity_id)

            if entity_type == "company":
                has_officers = any(
                    edge.target_entity_id == entity_id and
                    getattr(edge, "relationship", "") == "officer_of"
                    for edge in edges
                )

                if not has_officers:
                    slot_id = f"nexus_{entity_id}_no_officers"
                    unified = UnifiedSlot(
                        slot_id=slot_id,
                        slot_type=SlotType.RELATIONSHIP,
                        origin=SlotOrigin.INFERRED,
                        target=SlotTarget.NEXUS,
                        description=f"Surprising absence: {entity_name} has no officers",
                        state=SlotState.EMPTY,
                        priority=SlotPriority.HIGH,
                        entity_id=entity_id,
                        entity_type="company",
                        relationship_type="officer_of",
                        coordinates=GapCoordinates3D(
                            subject=SubjectAxis(
                                entity_id=entity_id,
                                entity_name=entity_name,
                                entity_type="company",
                            ),
                            nexus=NexusAxis(
                                surprising_absence=True,
                                connection_type="officer_of",
                                expected_terms=["director", "officer", "CEO", "secretary"],
                            ),
                            narrative_intent=f"Find officers for {entity_name}",
                        ).to_dict(),
                        metadata={
                            "priority_score": 75,
                            "surprising_absence": True,
                            "expected_terms": ["director", "officer", "CEO", "secretary"],
                        },
                    )
                    gaps.append(slot_to_gap(unified, CognitiveMode.NEXUS))

        return gaps
