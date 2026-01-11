"""
Slot Sufficiency Configuration

Defines per-slot-type sufficiency criteria for the "Loop Until Sufficient" system.

ALIGNS WITH: Abacus System - "Auto-iterate until slot is filled"
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SlotSufficiencyConfig:
    """Per-slot-type sufficiency criteria."""

    slot_type: str
    min_results: int = 1
    min_confidence: float = 0.7
    max_attempts: int = 5
    required_sources: int = 1
    void_is_finding: bool = False
    strategies: Optional[List[str]] = None

    def __post_init__(self):
        if self.strategies is None:
            self.strategies = ["variation", "fallback", "broaden"]


# Default configurations per slot type
SLOT_SUFFICIENCY_CONFIGS = {
    # ========== PERSON SLOTS ==========
    "name": SlotSufficiencyConfig(
        slot_type="name",
        min_results=1,
        min_confidence=0.9,
        max_attempts=2,
    ),
    "dob": SlotSufficiencyConfig(
        slot_type="dob",
        min_results=1,
        min_confidence=0.8,
        max_attempts=3,
    ),
    "nationality": SlotSufficiencyConfig(
        slot_type="nationality",
        min_results=1,
        max_attempts=3,
    ),
    "address": SlotSufficiencyConfig(
        slot_type="address",
        min_results=1,
        max_attempts=4,
    ),
    "occupation": SlotSufficiencyConfig(
        slot_type="occupation",
        min_results=1,
        max_attempts=3,
    ),
    "sanctions_status": SlotSufficiencyConfig(
        slot_type="sanctions_status",
        min_results=0,
        void_is_finding=True,
        max_attempts=2,
        strategies=["direct_api"],
    ),
    "pep_status": SlotSufficiencyConfig(
        slot_type="pep_status",
        min_results=0,
        void_is_finding=True,
        max_attempts=2,
        strategies=["direct_api"],
    ),
    # ========== COMPANY SLOTS ==========
    "registration_number": SlotSufficiencyConfig(
        slot_type="registration_number",
        min_results=1,
        min_confidence=0.95,
        max_attempts=2,
    ),
    "status": SlotSufficiencyConfig(
        slot_type="status",
        min_results=1,
        max_attempts=3,
    ),
    "incorporation_date": SlotSufficiencyConfig(
        slot_type="incorporation_date",
        min_results=1,
        max_attempts=2,
    ),
    "officers": SlotSufficiencyConfig(
        slot_type="officers",
        min_results=1,
        max_attempts=5,
        strategies=["variation", "registry_chain", "archive"],
    ),
    "shareholders": SlotSufficiencyConfig(
        slot_type="shareholders",
        min_results=1,
        max_attempts=5,
        strategies=["variation", "registry_chain", "archive"],
    ),
    "ubo": SlotSufficiencyConfig(
        slot_type="ubo",
        min_results=1,
        min_confidence=0.85,
        max_attempts=10,
        required_sources=2,
        strategies=["variation", "registry_chain", "archive", "jurisdiction_pivot"],
    ),
    "financials": SlotSufficiencyConfig(
        slot_type="financials",
        min_results=1,
        max_attempts=4,
    ),
    "litigation": SlotSufficiencyConfig(
        slot_type="litigation",
        min_results=0,
        void_is_finding=True,
        max_attempts=3,
    ),
    # ========== DOMAIN SLOTS ==========
    "registrant": SlotSufficiencyConfig(
        slot_type="registrant",
        min_results=1,
        max_attempts=2,
    ),
    "creation_date": SlotSufficiencyConfig(
        slot_type="creation_date",
        min_results=1,
        max_attempts=2,
    ),
    "nameservers": SlotSufficiencyConfig(
        slot_type="nameservers",
        min_results=1,
        max_attempts=2,
    ),
    # ========== DEFAULT ==========
    "_default": SlotSufficiencyConfig(
        slot_type="_default",
        min_results=1,
        max_attempts=3,
    ),
}


def get_slot_config(slot_type: str) -> SlotSufficiencyConfig:
    """Get sufficiency config for a slot type, with fallback to default."""
    return SLOT_SUFFICIENCY_CONFIGS.get(
        slot_type,
        SLOT_SUFFICIENCY_CONFIGS["_default"],
    )
