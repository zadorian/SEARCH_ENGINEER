"""
Slot-to-Section Auto-Binder

When a slot is enriched, automatically routes data to the appropriate
report section(s).

ALIGNS WITH: Abacus System - "Enriched slot auto-routes to report section"
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class BindingMode(Enum):
    AUTO = "auto"  # Automatic binding (default)
    MANUAL = "manual"  # User explicitly set - do not override
    SUGGESTED = "suggested"  # System suggested, user can modify


@dataclass
class SectionBinding:
    """A binding from a slot to a section."""

    section_id: str
    section_header: str
    mode: BindingMode = BindingMode.AUTO
    priority: int = 50  # Higher = more important
    formatter: Optional[str] = None  # Formatter function name
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SlotSectionBinding:
    """Complete binding configuration for a slot."""

    slot_name: str
    entity_type: str
    sections: List[SectionBinding] = field(default_factory=list)

    def get_active_sections(self) -> List[SectionBinding]:
        """Get sections to populate, excluding manual overrides."""
        return [s for s in self.sections if s.mode != BindingMode.MANUAL]


# ========== DEFAULT BINDINGS ==========

SLOT_SECTION_BINDINGS: Dict[str, Dict[str, List[str]]] = {
    "company": {
        # Core slots
        "name": ["COMPANY_OVERVIEW", "EXECUTIVE_SUMMARY"],
        "registration_number": ["COMPANY_OVERVIEW"],
        "jurisdiction": ["COMPANY_OVERVIEW"],
        "status": ["COMPANY_OVERVIEW"],
        "incorporation_date": ["CORPORATE_HISTORY"],
        # Relationship slots
        "officers": ["DIRECTORS_OFFICERS", "KEY_RELATIONSHIPS"],
        "shareholders": ["OWNERSHIP_SHAREHOLDERS", "KEY_RELATIONSHIPS"],
        "beneficial_owners": ["OWNERSHIP_SHAREHOLDERS", "KEY_RELATIONSHIPS"],
        "subsidiaries": ["GROUP_STRUCTURE"],
        "parent_company": ["GROUP_STRUCTURE"],
        # Enrichment slots
        "filings": ["FINANCIAL_STATEMENTS", "REGULATORY_LICENSES"],
        "financials": ["FINANCIAL_STATEMENTS"],
        "litigation": ["LITIGATION_COMPANY"],
        "sanctions": ["SANCTIONS_WATCHLISTS"],
        "adverse_media": ["ADVERSE_MEDIA"],
        "domains": ["WEBSITE_DIGITAL"],
    },
    "person": {
        # Core slots
        "name": ["BIOGRAPHICAL_OVERVIEW", "EXECUTIVE_SUMMARY"],
        "dob": ["BIOGRAPHICAL_OVERVIEW"],
        "nationality": ["BIOGRAPHICAL_OVERVIEW"],
        # Shell slots
        "address": ["BIOGRAPHICAL_OVERVIEW"],
        "occupation": ["CAREER_PROFESSIONAL"],
        "employer": ["CAREER_PROFESSIONAL"],
        # Relationship slots
        "associates": ["FAMILY_ASSOCIATES", "KEY_RELATIONSHIPS"],
        "family": ["FAMILY_ASSOCIATES"],
        # Enrichment slots
        "officers": ["DIRECTORSHIPS_APPOINTMENTS", "CORPORATE_AFFILIATIONS"],
        "shareholders": ["SHAREHOLDINGS_OWNERSHIP", "CORPORATE_AFFILIATIONS"],
        "social_profiles": ["SOCIAL_MEDIA_ONLINE"],
        "news_mentions": ["MEDIA_REPUTATION"],
        "court_records": ["CIVIL_LITIGATION"],
        "property_records": ["PROPERTY_ASSETS"],
        "sanctions": ["SANCTIONS_WATCHLISTS"],
        "pep_status": ["PEP_STATUS"],
        "adverse_media": ["ADVERSE_MEDIA"],
    },
    "domain": {
        "domain": ["WEBSITE_DIGITAL"],
        "registrant": ["WEBSITE_DIGITAL"],
        "backlinks": ["WEBSITE_DIGITAL"],
        "whois_history": ["WEBSITE_DIGITAL"],
    },
}


# ========== FORMATTERS ==========


def format_officers(officers: List[Dict], context: Dict) -> str:
    """Format officers list for DIRECTORS_OFFICERS section."""
    if not officers:
        return "No officers identified in available records."

    lines = [
        "| Name | Position | Appointed | Status |",
        "|------|----------|-----------|--------|",
    ]
    for officer in officers:
        lines.append(
            f"| **{officer.get('name', 'Unknown')}** | "
            f"{officer.get('position', '-')} | "
            f"{officer.get('appointed_date', '-')} | "
            f"{officer.get('status', 'Active')} |"
        )
    return "\n".join(lines)


def format_shareholders(shareholders: List[Dict], context: Dict) -> str:
    """Format shareholders for OWNERSHIP_SHAREHOLDERS section."""
    if not shareholders:
        return "Shareholder information not available in public records."

    lines = [
        "| Shareholder | Type | Shares | % |",
        "|-------------|------|--------|---|",
    ]
    for sh in shareholders:
        lines.append(
            f"| **{sh.get('name', 'Unknown')}** | "
            f"{sh.get('type', '-')} | "
            f"{sh.get('shares', '-')} | "
            f"{sh.get('percentage', '-')}% |"
        )
    return "\n".join(lines)


def format_litigation(cases: List[Dict], context: Dict) -> str:
    """Format litigation for LITIGATION section."""
    if not cases:
        return "No litigation records identified in available sources."

    lines = []
    for case in cases:
        lines.append(f"### {case.get('case_name', 'Case')}")
        lines.append(f"- **Court**: {case.get('court', 'Unknown')}")
        lines.append(f"- **Date**: {case.get('date', 'Unknown')}")
        lines.append(f"- **Status**: {case.get('status', 'Unknown')}")
        if case.get("summary"):
            lines.append(f"- **Summary**: {case.get('summary')}")
        lines.append("")
    return "\n".join(lines)


def format_default(value: Any, context: Dict) -> str:
    """Default formatter for any slot value."""
    if isinstance(value, list):
        if not value:
            return "No information available."
        if isinstance(value[0], dict):
            return "\n".join(f"- {v.get('name', str(v))}" for v in value)
        return "\n".join(f"- {v}" for v in value)
    return str(value) if value else "No information available."


SLOT_FORMATTERS: Dict[str, Callable] = {
    "officers": format_officers,
    "shareholders": format_shareholders,
    "beneficial_owners": format_shareholders,
    "litigation": format_litigation,
    "_default": format_default,
}


def get_formatter(slot_name: str) -> Callable:
    """Get formatter for slot or default."""
    return SLOT_FORMATTERS.get(slot_name, SLOT_FORMATTERS["_default"])


# ========== BINDER ==========


class SlotSectionBinder:
    """
    Core auto-binding engine.

    Responsibilities:
    1. Maintain slot->section mappings
    2. Listen for slot enrichment events
    3. Route enriched data to sections
    4. Preserve manual overrides
    5. Support template-specific bindings
    """

    def __init__(self, template_name: Optional[str] = None):
        self.bindings: Dict[str, Dict[str, SlotSectionBinding]] = {}
        self.template_name = template_name
        self.manual_overrides: Set[str] = set()
        self._on_section_update: Optional[Callable] = None
        self._load_default_bindings()
        if template_name:
            self._load_template_bindings(template_name)

    def _load_default_bindings(self):
        """Load default slot->section mappings."""
        for entity_type, slots in SLOT_SECTION_BINDINGS.items():
            self.bindings[entity_type] = {}
            for slot_name, section_ids in slots.items():
                self.bindings[entity_type][slot_name] = SlotSectionBinding(
                    slot_name=slot_name,
                    entity_type=entity_type,
                    sections=[
                        SectionBinding(section_id=sid, section_header=sid)
                        for sid in section_ids
                    ],
                )

    def _load_template_bindings(self, template_name: str):
        """Load template-specific overrides."""
        # Template-specific bindings would be loaded from config files
        # For now, just use defaults
        logger.info(f"[SlotSectionBinder] Template bindings for {template_name} (using defaults)")

    def register_manual_override(self, section_id: str):
        """Mark a section as manually edited - preserve user content."""
        self.manual_overrides.add(section_id)
        logger.info(f"[SlotSectionBinder] Section {section_id} marked as manual override")

    def set_update_callback(self, callback: Callable):
        """Set callback for section updates."""
        self._on_section_update = callback

    def on_slot_enriched(
        self,
        entity_id: str,
        entity_type: str,
        slot_name: str,
        value: Any,
        source_id: str,
    ) -> List[str]:
        """
        Handle slot enrichment event - route to sections.

        Returns list of section_ids that were updated.
        """
        binding = self.bindings.get(entity_type, {}).get(slot_name)
        if not binding:
            logger.debug(f"[SlotSectionBinder] No binding for {entity_type}.{slot_name}")
            return []

        updated_sections = []
        formatter = get_formatter(slot_name)

        for section_binding in binding.get_active_sections():
            # Skip manual overrides
            if section_binding.section_id in self.manual_overrides:
                logger.debug(f"[SlotSectionBinder] Skipping manual override: {section_binding.section_id}")
                continue

            # Format the value
            formatted_content = formatter(value, {"entity_id": entity_id, "source_id": source_id})

            # Route to section
            self._populate_section(
                section_id=section_binding.section_id,
                slot_name=slot_name,
                value=value,
                formatted_content=formatted_content,
                entity_id=entity_id,
                source_id=source_id,
            )
            updated_sections.append(section_binding.section_id)

        logger.info(f"[SlotSectionBinder] Slot {slot_name} routed to {len(updated_sections)} sections")
        return updated_sections

    def _populate_section(
        self,
        section_id: str,
        slot_name: str,
        value: Any,
        formatted_content: str,
        entity_id: str,
        source_id: str,
    ):
        """Populate a section with slot data."""
        if self._on_section_update:
            self._on_section_update(
                section_id=section_id,
                slot_name=slot_name,
                content=formatted_content,
                entity_id=entity_id,
                source_id=source_id,
            )

    def get_bindings_for_slot(self, entity_type: str, slot_name: str) -> List[str]:
        """Get section IDs bound to a slot."""
        binding = self.bindings.get(entity_type, {}).get(slot_name)
        return [s.section_id for s in binding.sections] if binding else []

    def get_slots_for_section(self, section_id: str) -> List[tuple]:
        """Get all (entity_type, slot_name) pairs that feed a section."""
        result = []
        for entity_type, slots in self.bindings.items():
            for slot_name, binding in slots.items():
                if any(s.section_id == section_id for s in binding.sections):
                    result.append((entity_type, slot_name))
        return result


# ========== CONVENIENCE ==========


def create_binder_with_callback(
    template_name: Optional[str] = None,
    on_section_update: Optional[Callable] = None,
) -> SlotSectionBinder:
    """Create a binder with optional callback."""
    binder = SlotSectionBinder(template_name=template_name)
    if on_section_update:
        binder.set_update_callback(on_section_update)
    return binder
