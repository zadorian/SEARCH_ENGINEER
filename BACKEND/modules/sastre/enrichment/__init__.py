"""
SASTRE Enrichment Module

Contains:
- slot_sufficiency.py - Per-slot sufficiency criteria
- slot_iterator.py - Auto-iteration until slot is sufficient
- slot_section_binder.py - Auto-bind slots to report sections
"""

from .slot_sufficiency import SlotSufficiencyConfig, SLOT_SUFFICIENCY_CONFIGS
from .slot_iterator import SlotIterator, SlotIterationState

__all__ = [
    "SlotSufficiencyConfig",
    "SLOT_SUFFICIENCY_CONFIGS",
    "SlotIterator",
    "SlotIterationState",
]
