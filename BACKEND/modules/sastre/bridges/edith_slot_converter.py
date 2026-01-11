"""
EDITH → Slot Converter

Converts EDITH template context (ALLOWED_ACTIONS, dd_sections) into UnifiedSlot
objects that can be processed by the SlotIterator and QueryLab.

THE MISSING LINK:
=================
EDITH compose_context() returns:
- allowed_actions: ["SEARCH_REGISTRY", "SEARCH_OFFICERS", ...]
- dd_sections: ["CORPORATE_PROFILE", "DIRECTORS_OFFICERS", ...]

SlotIterator expects:
- UnifiedSlot objects with slot_type, target, jurisdiction, etc.

This converter bridges that gap, mapping:
- ALLOWED_ACTIONS → Investigation intents (what to search for)
- dd_sections → Slot targets (what to fill)
- arbitrage_routes → Alternative paths when primary fails

ALIGNS WITH: Abacus v4.2 - "EDITH ALLOWED_ACTIONS define the space of valid queries"
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ..contracts import (
    UnifiedSlot, SlotType, SlotTarget, SlotState, SlotPriority,
    SlotOrigin, SlotStrategy,
)
from ..query.lab import (
    QueryLab, CompilationResult, Silo,
    REGISTRY_OPERATORS, NEXUS_RELATIONSHIP_TYPES,
)

logger = logging.getLogger(__name__)


# =============================================================================
# EDITH ACTION → SLOT MAPPINGS
# =============================================================================

@dataclass
class ActionMapping:
    """Maps an EDITH action to slot parameters."""
    slot_type: SlotType
    target: SlotTarget
    slot_name: str
    registry_slot: Optional[str] = None
    relationship_type: Optional[str] = None
    source_type: Optional[str] = None
    priority: SlotPriority = SlotPriority.MEDIUM


# EDITH ALLOWED_ACTIONS → Slot mappings
ACTION_TO_SLOT: Dict[str, ActionMapping] = {
    # Registry searches
    "SEARCH_REGISTRY": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="corporate_profile",
        registry_slot="profile",
        source_type="corporate_registry",
        priority=SlotPriority.HIGH,
    ),
    "SEARCH_OFFICERS": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="officers",
        registry_slot="officers",
        relationship_type="officer_of",
        source_type="corporate_registry",
        priority=SlotPriority.HIGH,
    ),
    "SEARCH_SHAREHOLDERS": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="shareholders",
        registry_slot="shareholders",
        relationship_type="shareholder_of",
        source_type="corporate_registry",
        priority=SlotPriority.HIGH,
    ),
    "SEARCH_UBO": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="ubo",
        registry_slot="ubo",
        relationship_type="beneficial_owner_of",
        source_type="corporate_registry",
        priority=SlotPriority.CRITICAL,
    ),
    "SEARCH_FILINGS": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="filings",
        registry_slot="filings",
        source_type="corporate_registry",
        priority=SlotPriority.MEDIUM,
    ),

    # Litigation
    "SEARCH_LITIGATION": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="litigation",
        registry_slot="litigation",
        relationship_type="party_to",
        source_type="court_records",
        priority=SlotPriority.HIGH,
    ),
    "SEARCH_COURTS": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="court_records",
        source_type="court_records",
        priority=SlotPriority.MEDIUM,
    ),

    # Sanctions & Watchlists
    "SEARCH_SANCTIONS": ActionMapping(
        slot_type=SlotType.ATTRIBUTE,
        target=SlotTarget.SUBJECT,
        slot_name="sanctions",
        relationship_type="sanctioned_by",
        source_type="sanctions_list",
        priority=SlotPriority.CRITICAL,
    ),
    "SEARCH_WATCHLISTS": ActionMapping(
        slot_type=SlotType.ATTRIBUTE,
        target=SlotTarget.SUBJECT,
        slot_name="watchlists",
        source_type="watchlist",
        priority=SlotPriority.HIGH,
    ),

    # News & Media
    "SEARCH_NEWS": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="news_media",
        source_type="news",
        priority=SlotPriority.MEDIUM,
    ),
    "SEARCH_ADVERSE_MEDIA": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="adverse_media",
        source_type="news",
        priority=SlotPriority.HIGH,
    ),

    # Property
    "SEARCH_PROPERTY": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="property_records",
        registry_slot="property",
        source_type="land_registry",
        priority=SlotPriority.MEDIUM,
    ),

    # Social Media
    "SEARCH_LINKEDIN": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="linkedin",
        source_type="social_media",
        priority=SlotPriority.LOW,
    ),

    # Open Web
    "SEARCH_WEB": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="open_web",
        source_type="web",
        priority=SlotPriority.LOW,
    ),
}


# DD Section → Slot mappings
SECTION_TO_SLOT: Dict[str, ActionMapping] = {
    "CORPORATE_PROFILE": ActionMapping(
        slot_type=SlotType.ATTRIBUTE,
        target=SlotTarget.SUBJECT,
        slot_name="corporate_profile",
        registry_slot="profile",
        priority=SlotPriority.HIGH,
    ),
    "DIRECTORS_OFFICERS": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="directors_officers",
        registry_slot="officers",
        relationship_type="officer_of",
        priority=SlotPriority.HIGH,
    ),
    "OWNERSHIP_SHAREHOLDERS": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="ownership",
        registry_slot="shareholders",
        relationship_type="shareholder_of",
        priority=SlotPriority.HIGH,
    ),
    "BENEFICIAL_OWNERSHIP": ActionMapping(
        slot_type=SlotType.RELATIONSHIP,
        target=SlotTarget.NEXUS,
        slot_name="beneficial_ownership",
        registry_slot="ubo",
        relationship_type="beneficial_owner_of",
        priority=SlotPriority.CRITICAL,
    ),
    "LITIGATION_REGULATORY": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="litigation",
        registry_slot="litigation",
        relationship_type="party_to",
        source_type="court_records",
        priority=SlotPriority.HIGH,
    ),
    "SANCTIONS_WATCHLISTS": ActionMapping(
        slot_type=SlotType.ATTRIBUTE,
        target=SlotTarget.SUBJECT,
        slot_name="sanctions",
        source_type="sanctions_list",
        priority=SlotPriority.CRITICAL,
    ),
    "ADVERSE_MEDIA": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="adverse_media",
        source_type="news",
        priority=SlotPriority.HIGH,
    ),
    "FINANCIAL_HISTORY": ActionMapping(
        slot_type=SlotType.ATTRIBUTE,
        target=SlotTarget.SUBJECT,
        slot_name="financials",
        source_type="corporate_registry",
        priority=SlotPriority.MEDIUM,
    ),
    "PROPERTY_ASSETS": ActionMapping(
        slot_type=SlotType.COVERAGE,
        target=SlotTarget.LOCATION,
        slot_name="property",
        registry_slot="property",
        source_type="land_registry",
        priority=SlotPriority.MEDIUM,
    ),
}


# =============================================================================
# EDITH → SLOT CONVERTER
# =============================================================================

@dataclass
class EdithConversionResult:
    """Result of converting EDITH context to slots."""
    slots: List[UnifiedSlot] = field(default_factory=list)
    queries: List[CompilationResult] = field(default_factory=list)
    dead_ends: List[str] = field(default_factory=list)  # Actions blocked by dead-ends
    arbitrage_suggestions: List[Dict[str, Any]] = field(default_factory=list)


class EdithSlotConverter:
    """
    Converts EDITH template context into investigation slots.

    Takes EDITH compose_context() output and produces:
    1. UnifiedSlot objects for each allowed action
    2. Initial queries compiled via QueryLab
    3. Filtered actions based on dead-ends
    """

    def __init__(self, query_lab: Optional[QueryLab] = None):
        self.query_lab = query_lab or QueryLab()

    def convert(
        self,
        edith_context: Dict[str, Any],
        generate_queries: bool = True,
    ) -> EdithConversionResult:
        """
        Convert EDITH context to slots and queries.

        Args:
            edith_context: Output from EdithBridge.compose_context()
            generate_queries: Whether to compile initial queries

        Returns:
            EdithConversionResult with slots, queries, and dead-ends
        """
        result = EdithConversionResult()

        # Extract EDITH context fields
        jurisdiction = edith_context.get("jurisdiction", "")
        entity = edith_context.get("entity", "")
        allowed_actions = edith_context.get("allowed_actions", [])
        dd_sections = edith_context.get("dd_sections", [])
        dead_end_warnings = edith_context.get("dead_end_warnings", [])
        arbitrage_routes = edith_context.get("arbitrage_routes", [])

        # Track blocked actions from dead-ends
        blocked_actions = set()
        for warning in dead_end_warnings:
            action = warning.get("action", "")
            if action:
                blocked_actions.add(action)
                result.dead_ends.append(action)

        # Convert DD sections to slots (primary)
        for section in dd_sections:
            mapping = SECTION_TO_SLOT.get(section)
            if mapping:
                slot = self._mapping_to_slot(
                    mapping=mapping,
                    entity_name=entity,
                    jurisdiction=jurisdiction,
                    source_id=f"edith_section_{section.lower()}",
                )
                result.slots.append(slot)

                # Generate query if not blocked
                if generate_queries and mapping.slot_name not in blocked_actions:
                    query = self._generate_query_for_mapping(
                        mapping=mapping,
                        entity_name=entity,
                        jurisdiction=jurisdiction,
                    )
                    if query:
                        result.queries.append(query)

        # Convert allowed actions to additional slots (if not covered by sections)
        existing_slot_names = {s.field_name for s in result.slots}

        for action in allowed_actions:
            if action in blocked_actions:
                continue

            mapping = ACTION_TO_SLOT.get(action)
            if mapping and mapping.slot_name not in existing_slot_names:
                slot = self._mapping_to_slot(
                    mapping=mapping,
                    entity_name=entity,
                    jurisdiction=jurisdiction,
                    source_id=f"edith_action_{action.lower()}",
                )
                result.slots.append(slot)

                if generate_queries:
                    query = self._generate_query_for_mapping(
                        mapping=mapping,
                        entity_name=entity,
                        jurisdiction=jurisdiction,
                    )
                    if query:
                        result.queries.append(query)

        # Add arbitrage suggestions
        for route in arbitrage_routes:
            result.arbitrage_suggestions.append({
                "from_jurisdiction": jurisdiction,
                "to_jurisdiction": route.get("target_jurisdiction"),
                "reason": route.get("reason"),
                "slot_name": route.get("slot_name"),
            })

        return result

    def _mapping_to_slot(
        self,
        mapping: ActionMapping,
        entity_name: str,
        jurisdiction: str,
        source_id: str,
    ) -> UnifiedSlot:
        """Convert an ActionMapping to a UnifiedSlot."""
        return UnifiedSlot(
            slot_id=f"{source_id}_{entity_name[:20].lower().replace(' ', '_')}",
            slot_type=mapping.slot_type,
            origin=SlotOrigin.AGENT,
            target=mapping.target,
            description=f"Fill {mapping.slot_name} for {entity_name}",
            state=SlotState.EMPTY,
            priority=mapping.priority,
            entity_type="company",  # EDITH is primarily for company DD
            field_name=mapping.slot_name,
            relationship_type=mapping.relationship_type,
            source_type=mapping.source_type,
            jurisdiction=jurisdiction.upper() if jurisdiction else None,
            metadata={
                "registry_slot": mapping.registry_slot,
                "edith_source": source_id,
            },
        )

    def _generate_query_for_mapping(
        self,
        mapping: ActionMapping,
        entity_name: str,
        jurisdiction: str,
    ) -> Optional[CompilationResult]:
        """Generate a query for an ActionMapping using QueryLab."""
        try:
            # Use NEXUS compiler for relationship slots
            if mapping.relationship_type:
                return self.query_lab.compile_nexus(
                    relationship_type=mapping.relationship_type,
                    from_entity={"name": entity_name, "type": "company"},
                    jurisdiction=jurisdiction,
                )

            # Use standard compiler for other slots
            return self.query_lab.compile(
                entity_name=entity_name,
                entity_type="company",
                jurisdiction=jurisdiction,
                slot_type=mapping.registry_slot or mapping.slot_name,
            )

        except Exception as e:
            logger.error(f"Failed to generate query for {mapping.slot_name}: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def edith_to_slots(edith_context: Dict[str, Any]) -> List[UnifiedSlot]:
    """
    Convert EDITH context to slots.

    Usage:
        context = await edith_bridge.compose_context("uk", "company_dd", "Test Ltd")
        slots = edith_to_slots(context)
    """
    converter = EdithSlotConverter()
    result = converter.convert(edith_context, generate_queries=False)
    return result.slots


def edith_to_queries(
    edith_context: Dict[str, Any],
) -> List[CompilationResult]:
    """
    Convert EDITH context directly to compiled queries.

    Usage:
        context = await edith_bridge.compose_context("uk", "company_dd", "Test Ltd")
        queries = edith_to_queries(context)
        for q in queries:
            print(q.to_ir())
    """
    converter = EdithSlotConverter()
    result = converter.convert(edith_context, generate_queries=True)
    return result.queries


async def route_and_convert(
    query: str,
    edith_bridge: Any,  # EdithBridge
) -> EdithConversionResult:
    """
    Route a query through EDITH and convert to slots.

    Full pipeline:
    1. Route query to jurisdiction/genre
    2. Compose template context
    3. Convert to slots and queries

    Usage:
        from SASTRE.bridges.edith_bridge import EdithBridge
        from SASTRE.bridges.edith_slot_converter import route_and_convert

        bridge = EdithBridge()
        result = await route_and_convert("DD on UK company Test Ltd", bridge)
    """
    # Route the query
    routing = await edith_bridge.route_investigation(query)

    if routing.get("status") == "missing":
        return EdithConversionResult()

    # Compose context
    context = await edith_bridge.compose_context(
        jurisdiction=routing.get("jurisdiction_id", ""),
        genre=routing.get("genre_id", ""),
        entity=routing.get("entity_name", ""),
        strict_mode=True,  # Remove dead-end actions
    )

    # Convert to slots
    converter = EdithSlotConverter()
    return converter.convert(context)
