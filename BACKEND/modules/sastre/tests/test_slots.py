"""
Tests for SASTRE Slot System - V4 Spec alignment.

Tests the hunger/feeding/mutation mechanics for entity slots.
"""

import pytest
from datetime import datetime


class TestSlotStateEnum:
    """Test SlotState enum values."""

    def test_import_slot_state(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState is not None

    def test_slot_state_empty(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState.EMPTY.value == "empty"

    def test_slot_state_partial(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState.PARTIAL.value == "partial"

    def test_slot_state_filled(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState.FILLED.value == "filled"

    def test_slot_state_void(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState.VOID.value == "void"

    def test_slot_state_contested(self):
        from BACKEND.modules.SASTRE.contracts import SlotState
        assert SlotState.CONTESTED.value == "contested"


class TestSlotPriorityEnum:
    """Test SlotPriority enum values."""

    def test_import_slot_priority(self):
        from BACKEND.modules.SASTRE.contracts import SlotPriority
        assert SlotPriority is not None

    def test_priority_critical(self):
        from BACKEND.modules.SASTRE.contracts import SlotPriority
        assert SlotPriority.CRITICAL.value == "critical"

    def test_priority_high(self):
        from BACKEND.modules.SASTRE.contracts import SlotPriority
        assert SlotPriority.HIGH.value == "high"

    def test_priority_medium(self):
        from BACKEND.modules.SASTRE.contracts import SlotPriority
        assert SlotPriority.MEDIUM.value == "medium"

    def test_priority_low(self):
        from BACKEND.modules.SASTRE.contracts import SlotPriority
        assert SlotPriority.LOW.value == "low"


class TestEntitySlot:
    """Test EntitySlot dataclass and hunger mechanics."""

    def test_import_entity_slot(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot
        assert EntitySlot is not None

    def test_create_empty_slot(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot, SlotState
        slot = EntitySlot(
            slot_id="test_slot",
            field_name="email",
            entity_id="entity_1",
            entity_type="person"
        )
        assert slot.state == SlotState.EMPTY
        assert slot.hunger == 1.0
        assert slot.is_hungry is True

    def test_feed_slot(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot, SlotState
        slot = EntitySlot(
            slot_id="test_slot",
            field_name="email",
            entity_id="entity_1",
            entity_type="person"
        )
        slot.feed("test@example.com", "source_1")
        assert slot.state == SlotState.FILLED
        assert slot.hunger < 1.0
        assert slot.primary_value == "test@example.com"

    def test_feed_conflicting_value(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot, SlotState
        slot = EntitySlot(
            slot_id="test_slot",
            field_name="email",
            entity_id="entity_1",
            entity_type="person"
        )
        slot.feed("test@example.com", "source_1")
        slot.feed("different@example.com", "source_2")
        assert slot.state == SlotState.CONTESTED
        assert len(slot.values) == 2
        assert slot.needs_resolution is True

    def test_feed_confirmation(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot, SlotState
        slot = EntitySlot(
            slot_id="test_slot",
            field_name="email",
            entity_id="entity_1",
            entity_type="person"
        )
        slot.feed("test@example.com", "source_1")
        initial_hunger = slot.hunger
        slot.feed("test@example.com", "source_2")  # Same value
        assert slot.hunger < initial_hunger  # Hunger reduced by confirmation
        assert slot.state == SlotState.FILLED

    def test_mark_void(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlot, SlotState
        slot = EntitySlot(
            slot_id="test_slot",
            field_name="email",
            entity_id="entity_1",
            entity_type="person"
        )
        slot.mark_void("source_1")
        assert slot.state == SlotState.VOID
        assert slot.hunger < 1.0


class TestEntitySlotSet:
    """Test EntitySlotSet collection."""

    def test_import_entity_slot_set(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlotSet
        assert EntitySlotSet is not None

    def test_create_slot_set(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlotSet
        slot_set = EntitySlotSet(entity_id="entity_1", entity_type="person")
        assert slot_set.entity_id == "entity_1"
        assert slot_set.overall_hunger() == 1.0  # Empty = max hunger

    def test_get_hungry_slots(self):
        from BACKEND.modules.SASTRE.contracts import EntitySlotSet, EntitySlot, SlotPriority
        slot_set = EntitySlotSet(entity_id="entity_1", entity_type="person")
        slot_set.slots["email"] = EntitySlot(
            slot_id="s1", field_name="email",
            entity_id="entity_1", entity_type="person",
            priority=SlotPriority.HIGH
        )
        slot_set.slots["name"] = EntitySlot(
            slot_id="s2", field_name="name",
            entity_id="entity_1", entity_type="person",
            priority=SlotPriority.CRITICAL
        )
        hungry = slot_set.get_hungry_slots()
        assert len(hungry) == 2
        # CRITICAL should be first
        assert hungry[0].field_name == "name"


class TestCreateSlotsForEntity:
    """Test slot template creation."""

    def test_import_create_slots(self):
        from BACKEND.modules.SASTRE.contracts import create_slots_for_entity
        assert create_slots_for_entity is not None

    def test_create_person_slots(self):
        from BACKEND.modules.SASTRE.contracts import create_slots_for_entity, SlotPriority
        slot_set = create_slots_for_entity("person_1", "person")
        assert "name" in slot_set.slots
        assert "email" in slot_set.slots
        assert slot_set.slots["name"].priority == SlotPriority.CRITICAL

    def test_create_company_slots(self):
        from BACKEND.modules.SASTRE.contracts import create_slots_for_entity
        slot_set = create_slots_for_entity("company_1", "company")
        assert "name" in slot_set.slots
        assert "registration_number" in slot_set.slots
        assert "officers" in slot_set.slots

    def test_create_domain_slots(self):
        from BACKEND.modules.SASTRE.contracts import create_slots_for_entity
        slot_set = create_slots_for_entity("domain_1", "domain")
        assert "domain" in slot_set.slots
        assert "registrant" in slot_set.slots
        assert "backlinks" in slot_set.slots


class TestSlotTemplates:
    """Test SLOT_TEMPLATES constant."""

    def test_import_templates(self):
        from BACKEND.modules.SASTRE.contracts import SLOT_TEMPLATES
        assert SLOT_TEMPLATES is not None

    def test_person_template_exists(self):
        from BACKEND.modules.SASTRE.contracts import SLOT_TEMPLATES
        assert "person" in SLOT_TEMPLATES

    def test_company_template_exists(self):
        from BACKEND.modules.SASTRE.contracts import SLOT_TEMPLATES
        assert "company" in SLOT_TEMPLATES

    def test_domain_template_exists(self):
        from BACKEND.modules.SASTRE.contracts import SLOT_TEMPLATES
        assert "domain" in SLOT_TEMPLATES
