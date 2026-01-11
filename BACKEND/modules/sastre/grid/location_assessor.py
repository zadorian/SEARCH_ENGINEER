"""
Location assessor - Mode C (Cartographer).
"""

from typing import List, Any, Dict
from collections import defaultdict

from ..contracts import UnifiedSlot, SlotType, SlotOrigin, SlotTarget, SlotState, SlotPriority
from .cognitive_types import (
    CognitiveGap,
    CognitiveMode,
    GapCoordinates3D,
    LocationAxis,
    slot_to_gap,
)


class LocationAssessor:
    """Assess terrain coverage and implied jurisdictions."""

    def __init__(self, state: Any):
        self.state = state

    def assess(self) -> List[CognitiveGap]:
        gaps: List[CognitiveGap] = []

        sources = getattr(self.state, "sources", {})
        entities = getattr(self.state, "entities", {})

        by_jurisdiction: Dict[str, List[Any]] = defaultdict(list)
        for source in sources.values():
            jur = getattr(source, "jurisdiction", "unknown")
            by_jurisdiction[jur].append(source)

        for jurisdiction, source_list in by_jurisdiction.items():
            unchecked = [
                s for s in source_list
                if getattr(s, "state", None) and s.state.value == "unchecked"
            ]
            if unchecked:
                slot_id = f"location_{jurisdiction}_unchecked"
                unified = UnifiedSlot(
                    slot_id=slot_id,
                    slot_type=SlotType.COVERAGE,
                    origin=SlotOrigin.AGENT,
                    target=SlotTarget.LOCATION,
                    description=f"{jurisdiction}: {len(unchecked)}/{len(source_list)} sources unchecked",
                    state=SlotState.EMPTY,
                    priority=SlotPriority.MEDIUM,
                    jurisdiction=jurisdiction,
                    coordinates=GapCoordinates3D(
                        location=LocationAxis(
                            jurisdiction=jurisdiction,
                        ),
                        narrative_intent=f"Check remaining sources in {jurisdiction}",
                    ).to_dict(),
                    metadata={"priority_score": 50, "unchecked_count": len(unchecked), "total_sources": len(source_list)},
                )
                gaps.append(slot_to_gap(unified, CognitiveMode.LOCATION))

        implied_jurisdictions = set()
        for entity in entities.values():
            shell = getattr(entity, "shell", {})
            if "jurisdiction" in shell:
                jur = shell["jurisdiction"]
                if hasattr(jur, "value"):
                    implied_jurisdictions.add(jur.value)

        explored = set(by_jurisdiction.keys())
        unexplored = implied_jurisdictions - explored

        for jur in unexplored:
            slot_id = f"location_{jur}_implied"
            unified = UnifiedSlot(
                slot_id=slot_id,
                slot_type=SlotType.COVERAGE,
                origin=SlotOrigin.INFERRED,
                target=SlotTarget.LOCATION,
                description=f"Implied jurisdiction not explored: {jur}",
                state=SlotState.EMPTY,
                priority=SlotPriority.HIGH,
                jurisdiction=jur,
                source_type="registry",
                coordinates=GapCoordinates3D(
                    location=LocationAxis(
                        jurisdiction=jur,
                        source_type="registry",
                    ),
                    narrative_intent=f"Explore implied jurisdiction: {jur}",
                ).to_dict(),
                metadata={"priority_score": 65, "implied": True},
            )
            gaps.append(slot_to_gap(unified, CognitiveMode.LOCATION))

        return gaps
