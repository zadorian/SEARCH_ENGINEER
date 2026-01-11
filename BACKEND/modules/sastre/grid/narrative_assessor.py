"""
Narrative assessor - Mode A (Editor).
"""

from typing import List, Any

from ..contracts import UnifiedSlot, SlotType, SlotOrigin, SlotTarget, SlotState, SlotPriority
from .cognitive_types import (
    CognitiveGap,
    CognitiveMode,
    GapCoordinates3D,
    slot_to_gap,
)


class NarrativeAssessor:
    """Assess narrative coherence and unanswered questions."""

    def __init__(self, state: Any):
        self.state = state

    def assess(self) -> List[CognitiveGap]:
        gaps: List[CognitiveGap] = []

        narrative_items = getattr(self.state, "narrative_items", {})

        for item_id, item in narrative_items.items():
            if hasattr(item, "state") and item.state.value == "unanswered":
                slot_id = f"narrative_{item_id}_unanswered"
                priority = getattr(item, "priority", {}).get("value", 50) if hasattr(item, "priority") else 50
                unified = UnifiedSlot(
                    slot_id=slot_id,
                    slot_type=SlotType.NARRATIVE,
                    origin=SlotOrigin.AGENT,
                    target=SlotTarget.NARRATIVE,
                    description=f"Unanswered question: {item.question}",
                    state=SlotState.EMPTY,
                    priority=SlotPriority.MEDIUM,
                    narrative_section=getattr(item, "section_id", None),
                    coordinates=GapCoordinates3D(
                        narrative_intent=item.question,
                    ).to_dict(),
                    metadata={"priority_score": priority},
                )
                gaps.append(slot_to_gap(unified, CognitiveMode.NARRATIVE))
            elif hasattr(item, "state") and item.state.value == "partial":
                slot_id = f"narrative_{item_id}_partial"
                unified = UnifiedSlot(
                    slot_id=slot_id,
                    slot_type=SlotType.NARRATIVE,
                    origin=SlotOrigin.AGENT,
                    target=SlotTarget.NARRATIVE,
                    description=f"Partially answered: {item.question}",
                    state=SlotState.PARTIAL,
                    priority=SlotPriority.MEDIUM,
                    narrative_section=getattr(item, "section_id", None),
                    coordinates=GapCoordinates3D(
                        narrative_intent=f"Complete answer for: {item.question}",
                    ).to_dict(),
                    metadata={"priority_score": 40},
                )
                gaps.append(slot_to_gap(unified, CognitiveMode.NARRATIVE))

        document = getattr(self.state, "document", None)
        if document and hasattr(document, "sections"):
            for section in document.sections:
                if hasattr(section, "content") and section.content:
                    if self._has_unsupported_claims(section.content):
                        slot_id = f"narrative_unsupported_{section.header[:20]}"
                        unified = UnifiedSlot(
                            slot_id=slot_id,
                            slot_type=SlotType.NARRATIVE,
                            origin=SlotOrigin.AGENT,
                            target=SlotTarget.NARRATIVE,
                            description=f"Unsupported claims in: {section.header}",
                            state=SlotState.EMPTY,
                            priority=SlotPriority.HIGH,
                            narrative_section=getattr(section, "id", None),
                            coordinates=GapCoordinates3D(
                                narrative_intent=f"Find evidence for claims in {section.header}",
                            ).to_dict(),
                            metadata={"priority_score": 60},
                        )
                        gaps.append(slot_to_gap(unified, CognitiveMode.NARRATIVE))

        return gaps

    def _has_unsupported_claims(self, content: str) -> bool:
        """Check if content has claims without citations."""
        claim_patterns = ["allegedly", "reportedly", "is believed to", "has been linked"]
        citation_patterns = ["[", "(source:", "according to"]

        has_claims = any(p in content.lower() for p in claim_patterns)
        has_citations = any(p in content.lower() for p in citation_patterns)

        return has_claims and not has_citations
