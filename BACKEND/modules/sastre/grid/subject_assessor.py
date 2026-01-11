"""
Subject assessor - Mode B (Biographer).

Updated for V4.2 Slot System:
- Uses EntitySlotSet to track hunger/void/contested states.
- Respects CYMONIDES schema via contracts.py.
"""

from typing import List, Any, Dict

from ..contracts import create_slots_for_entity, SlotState, SlotPriority
from .cognitive_types import (
    CognitiveGap,
    CognitiveMode,
    GapCoordinates3D,
    SubjectAxis,
    NexusAxis,
    CertaintyLevel,
)


class SubjectAssessor:
    """Assess profile completeness using Slot mechanics."""

    def __init__(self, state: Any):
        self.state = state

    def assess(self) -> List[CognitiveGap]:
        gaps: List[CognitiveGap] = []

        entities = getattr(self.state, "entities", {})

        for entity_id, entity in entities.items():
            entity_name = getattr(entity, "name", entity_id)
            entity_type = getattr(entity, "entity_type", "unknown")
            if hasattr(entity_type, "value"):
                entity_type = entity_type.value

            # 1. Initialize Slot Set from Schema
            slots = create_slots_for_entity(entity_id, entity_type)

            # 2. Feed Slots from current state
            # Core attributes
            core = getattr(entity, "core", {})
            for key, attr in core.items():
                if key in slots.slots:
                    val = getattr(attr, "value", attr)
                    src = getattr(attr, "source", "unknown")
                    slots.slots[key].feed(val, src)

            # Shell attributes
            shell = getattr(entity, "shell", {})
            for key, attr in shell.items():
                if key in slots.slots:
                    val = getattr(attr, "value", attr)
                    src = getattr(attr, "source", "unknown")
                    slots.slots[key].feed(val, src)

            # 3. Analyze Slot States
            
            # A. HUNGRY SLOTS (Empty + High Priority)
            hungry = slots.get_hungry_slots()
            for slot in hungry:
                # Only report top 3 to avoid flooding
                if len(gaps) >= 3 and slot.priority != SlotPriority.CRITICAL:
                    continue
                
                priority = 80 if slot.priority == SlotPriority.CRITICAL else 60
                gaps.append(CognitiveGap(
                    id=f"subject_{entity_id}_hungry_{slot.field_name}",
                    description=f"Hungry slot: {entity_name}.{slot.field_name}",
                    discovered_by_mode=CognitiveMode.SUBJECT,
                    coordinates=GapCoordinates3D(
                        subject=SubjectAxis(
                            entity_id=entity_id,
                            entity_name=entity_name,
                            entity_type=entity_type,
                            attribute=slot.field_name,
                        ),
                        narrative_intent=f"Fill {slot.field_name} for {entity_name}",
                    ),
                    priority=priority,
                ))

            # B. VOID SLOTS (Confirmed Empty) -> Trigger Path Spawning
            # (Note: In a real run, VOID comes from failed queries. 
            # Here we might not see it unless we track query history vs slots.
            # For now, we skip generating VOID gaps from static state unless explicitly marked).

            # C. CONTESTED SLOTS (Conflicting Values) -> Disambiguation
            contested = slots.get_contested_slots()
            for slot in contested:
                gaps.append(CognitiveGap(
                    id=f"subject_{entity_id}_contested_{slot.field_name}",
                    description=f"Contested slot: {entity_name}.{slot.field_name}",
                    discovered_by_mode=CognitiveMode.SUBJECT,
                    coordinates=GapCoordinates3D(
                        subject=SubjectAxis(
                            entity_id=entity_id,
                            entity_name=entity_name,
                            entity_type=entity_type,
                            attribute=slot.field_name,
                        ),
                        nexus=NexusAxis(
                            certainty=CertaintyLevel.UNKNOWN, # Contested
                        ),
                        narrative_intent=f"Resolve conflict in {slot.field_name}",
                    ),
                    priority=85, # High priority to resolve truth
                ))

            # D. IDENTITY COLLISIONS (Legacy/Global check)
            if hasattr(entity, "collision_flags") and entity.collision_flags:
                gaps.append(CognitiveGap(
                    id=f"subject_{entity_id}_disambiguation",
                    description=f"Identity disambiguation needed: {entity_name}",
                    discovered_by_mode=CognitiveMode.SUBJECT,
                    coordinates=GapCoordinates3D(
                        subject=SubjectAxis(
                            entity_id=entity_id,
                            entity_name=entity_name,
                            entity_type=entity_type,
                        ),
                        nexus=NexusAxis(
                            certainty=CertaintyLevel.UNKNOWN,
                        ),
                        narrative_intent=f"Resolve identity: Is this one {entity_name} or multiple?",
                    ),
                    priority=90,
                ))

        return gaps