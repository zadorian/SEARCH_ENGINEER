"""
SASTRE Tactical Layer - Spear / Trap / Net

The Tactical Triad selects query strategy based on K-U quadrant and slot hunger.

SPEAR: Precision strike
    - Known subject + Known location
    - Single targeted query
    - High confidence expectation
    - Example: "Get John Smith's record from UK Companies House"

TRAP: Baited net
    - Known subject + Unknown locations OR Unknown subject + Known location
    - Multiple queries with filters
    - Moderate confidence, looking to narrow
    - Example: "Find all mentions of Acme Corp in news sources"

NET: Maximum recall
    - Unknown subject + Unknown location
    - Broad brute search across all sources
    - Low confidence, discovery mode
    - Example: "Extract all entities from this domain"

Usage:
    from SASTRE.tactical import TacticalSelector, Tactic

    selector = TacticalSelector()
    tactic = selector.select(ku_quadrant, slot_hunger, context)
    queries = tactic.generate_queries(target)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from abc import ABC, abstractmethod

from .contracts import KUQuadrant, EntitySlot, EntitySlotSet, SlotPriority


# =============================================================================
# TACTIC TYPES
# =============================================================================

class TacticType(Enum):
    """The three tactical approaches."""
    SPEAR = "spear"  # Precision: Known-Known
    TRAP = "trap"    # Filtered: Known-Unknown or Unknown-Known
    NET = "net"      # Broad: Unknown-Unknown


@dataclass
class TacticResult:
    """Result of tactical query generation."""
    tactic: TacticType
    queries: List[Dict[str, Any]]
    expected_yield: str  # What we expect to find
    confidence: float    # 0.0-1.0 expected success rate
    rationale: str       # Why this tactic was chosen


# =============================================================================
# BASE TACTIC
# =============================================================================

class Tactic(ABC):
    """Base class for tactical approaches."""

    tactic_type: TacticType

    @abstractmethod
    def generate_queries(
        self,
        target: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        slots: Optional[EntitySlotSet] = None,
    ) -> TacticResult:
        """Generate queries based on this tactic."""
        pass

    @abstractmethod
    def matches(
        self,
        ku_quadrant: KUQuadrant,
        has_hungry_slots: bool,
        has_known_sources: bool,
    ) -> float:
        """Return match score (0.0-1.0) for this tactic given context."""
        pass


# =============================================================================
# SPEAR TACTIC - Precision Strike
# =============================================================================

class SpearTactic(Tactic):
    """
    Precision strike for Known-Known situations.

    Use when:
    - Subject is identified (name, ID, etc.)
    - Location is known (specific registry, database)
    - High confidence in where to look

    Generates single, targeted queries.
    """

    tactic_type = TacticType.SPEAR

    def generate_queries(
        self,
        target: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        slots: Optional[EntitySlotSet] = None,
    ) -> TacticResult:
        queries = []

        # Determine specific source based on entity type and jurisdiction
        if entity_type == "company" and jurisdiction:
            # Direct registry lookup
            queries.append({
                "type": "registry",
                "syntax": f"registry? :!{target}",
                "source": f"{jurisdiction.lower()}_registry",
                "priority": 1,
            })
        elif entity_type == "person":
            # Specific person enrichment
            queries.append({
                "type": "enrich",
                "syntax": f"enrich? :!{target}",
                "source": "person_enrichment",
                "priority": 1,
            })
        elif entity_type == "domain":
            # WHOIS lookup
            queries.append({
                "type": "whois",
                "syntax": f"whois? :{target}",
                "source": "whois",
                "priority": 1,
            })
        else:
            # Generic entity lookup
            queries.append({
                "type": "lookup",
                "syntax": f"ent? :!{target}",
                "source": "primary",
                "priority": 1,
            })

        # If we have hungry slots, add targeted queries for them
        if slots:
            hungry = slots.get_hungry_slots()
            for slot in hungry[:3]:  # Top 3 hungry slots
                if slot.priority in [SlotPriority.CRITICAL, SlotPriority.HIGH]:
                    queries.append({
                        "type": "slot_fill",
                        "syntax": f"{slot.field_name}? :!{target}",
                        "source": "slot_specific",
                        "priority": 2,
                        "slot": slot.field_name,
                    })

        return TacticResult(
            tactic=TacticType.SPEAR,
            queries=queries,
            expected_yield=f"Specific {entity_type} record",
            confidence=0.85,
            rationale=f"Known target '{target}' with known source location",
        )

    def matches(
        self,
        ku_quadrant: KUQuadrant,
        has_hungry_slots: bool,
        has_known_sources: bool,
    ) -> float:
        if ku_quadrant == KUQuadrant.VERIFY:
            return 1.0  # Perfect match
        elif ku_quadrant == KUQuadrant.TRACE and has_known_sources:
            return 0.7  # Good match if we know where to look
        return 0.2  # Low match otherwise


# =============================================================================
# TRAP TACTIC - Baited Net with Filters
# =============================================================================

class TrapTactic(Tactic):
    """
    Baited net for Known-Unknown or Unknown-Known situations.

    Use when:
    - Subject is known but location unknown (TRACE)
    - Location is known but subject unknown (EXTRACT)
    - Need to cast wider but with filters

    Generates multiple queries with discrimination.
    """

    tactic_type = TacticType.TRAP

    def generate_queries(
        self,
        target: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        slots: Optional[EntitySlotSet] = None,
    ) -> TacticResult:
        queries = []

        if entity_type in ["person", "company"]:
            # Multi-source search with entity type filter
            sources = ["news", "corporate", "social", "government"]
            for i, source in enumerate(sources):
                queries.append({
                    "type": "filtered_search",
                    "syntax": f"ent? :!{target} @{source}",
                    "source": source,
                    "priority": i + 1,
                    "filter": entity_type,
                })

            # Add jurisdiction-specific if known
            if jurisdiction:
                queries.append({
                    "type": "jurisdiction_sweep",
                    "syntax": f"ent? :!{target} :{jurisdiction}",
                    "source": f"{jurisdiction.lower()}_all",
                    "priority": 0,  # Highest priority
                })

        elif entity_type == "domain":
            # Link analysis + entity extraction
            queries.extend([
                {
                    "type": "backlinks",
                    "syntax": f"bl? :!{target}",
                    "source": "backlink_index",
                    "priority": 1,
                },
                {
                    "type": "entities",
                    "syntax": f"ent? :!{target}",
                    "source": "domain_content",
                    "priority": 2,
                },
                {
                    "type": "outlinks",
                    "syntax": f"ol? :!{target}",
                    "source": "outlink_index",
                    "priority": 3,
                },
            ])

        else:
            # Generic multi-source trap
            queries.append({
                "type": "broad_search",
                "syntax": f"ent? :!{target}",
                "source": "all",
                "priority": 1,
            })

        return TacticResult(
            tactic=TacticType.TRAP,
            queries=queries,
            expected_yield=f"Multiple {entity_type} mentions across sources",
            confidence=0.60,
            rationale=f"Casting filtered net for '{target}' across multiple sources",
        )

    def matches(
        self,
        ku_quadrant: KUQuadrant,
        has_hungry_slots: bool,
        has_known_sources: bool,
    ) -> float:
        if ku_quadrant == KUQuadrant.TRACE:
            return 0.9  # Known subject, looking for locations
        elif ku_quadrant == KUQuadrant.EXTRACT:
            return 0.9  # Known location, extracting subjects
        elif ku_quadrant == KUQuadrant.VERIFY and has_hungry_slots:
            return 0.5  # Might need broader search to fill slots
        return 0.3


# =============================================================================
# NET TACTIC - Maximum Recall Brute Search
# =============================================================================

class NetTactic(Tactic):
    """
    Maximum recall brute search for Unknown-Unknown situations.

    Use when:
    - Neither subject nor location is well-defined
    - Discovery/exploration mode
    - Initial investigation phase

    Generates broad queries across all available sources.
    """

    tactic_type = TacticType.NET

    def generate_queries(
        self,
        target: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        slots: Optional[EntitySlotSet] = None,
    ) -> TacticResult:
        queries = []

        # Wave 1: Fast sources
        queries.append({
            "type": "brute_wave1",
            "syntax": f"ent? :!{target} ##wave1",
            "source": "fast_engines",
            "priority": 1,
            "engines": ["google", "bing", "duckduckgo"],
        })

        # Wave 2: Deep sources
        queries.append({
            "type": "brute_wave2",
            "syntax": f"ent? :!{target} ##wave2",
            "source": "deep_engines",
            "priority": 2,
            "engines": ["corporate_registries", "news_archives", "court_records"],
        })

        # Wave 3: Specialized sources
        queries.append({
            "type": "brute_wave3",
            "syntax": f"ent? :!{target} ##wave3",
            "source": "specialized",
            "priority": 3,
            "engines": ["sanctions", "pep_lists", "adverse_media"],
        })

        # If entity type hints at specific sources
        if entity_type == "company":
            queries.append({
                "type": "company_brute",
                "syntax": f"c? :!{target} ##all",
                "source": "company_global",
                "priority": 0,
            })
        elif entity_type == "person":
            queries.append({
                "type": "person_brute",
                "syntax": f"p? :!{target} ##all",
                "source": "person_global",
                "priority": 0,
            })

        return TacticResult(
            tactic=TacticType.NET,
            queries=queries,
            expected_yield=f"All available {entity_type} data",
            confidence=0.40,
            rationale=f"Discovery mode - casting wide net for '{target}'",
        )

    def matches(
        self,
        ku_quadrant: KUQuadrant,
        has_hungry_slots: bool,
        has_known_sources: bool,
    ) -> float:
        if ku_quadrant == KUQuadrant.DISCOVER:
            return 1.0  # Perfect match
        elif ku_quadrant == KUQuadrant.EXTRACT and not has_known_sources:
            return 0.6  # No known sources, need to search broadly
        elif has_hungry_slots and not has_known_sources:
            return 0.5  # Many gaps, no clear path
        return 0.2


# =============================================================================
# TACTICAL SELECTOR
# =============================================================================

class TacticalSelector:
    """
    Selects the appropriate tactic based on K-U quadrant and context.

    Decision matrix:
        VERIFY (Known-Known)     → SPEAR (precision)
        TRACE (Known-Unknown)    → TRAP (filtered search)
        EXTRACT (Unknown-Known)  → TRAP (targeted extraction)
        DISCOVER (Unknown-Unknown) → NET (brute search)

    Slot hunger and source availability modify the selection.
    """

    def __init__(self):
        self.tactics = [
            SpearTactic(),
            TrapTactic(),
            NetTactic(),
        ]

    def select(
        self,
        ku_quadrant: KUQuadrant,
        slots: Optional[EntitySlotSet] = None,
        known_sources: Optional[List[str]] = None,
    ) -> Tactic:
        """
        Select the best tactic for the given context.

        Args:
            ku_quadrant: Current K-U position
            slots: Entity slots (for hunger calculation)
            known_sources: List of known source IDs

        Returns:
            The selected Tactic
        """
        has_hungry_slots = False
        if slots:
            hungry = slots.get_hungry_slots()
            has_hungry_slots = len(hungry) > 0

        has_known_sources = bool(known_sources and len(known_sources) > 0)

        # Score each tactic
        scored = []
        for tactic in self.tactics:
            score = tactic.matches(ku_quadrant, has_hungry_slots, has_known_sources)
            scored.append((score, tactic))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return scored[0][1]

    def select_and_generate(
        self,
        ku_quadrant: KUQuadrant,
        target: str,
        entity_type: str,
        jurisdiction: Optional[str] = None,
        slots: Optional[EntitySlotSet] = None,
        known_sources: Optional[List[str]] = None,
    ) -> TacticResult:
        """
        Select tactic and generate queries in one call.

        Args:
            ku_quadrant: Current K-U position
            target: The target entity/query
            entity_type: Type of entity (person, company, domain, etc.)
            jurisdiction: Optional jurisdiction code
            slots: Entity slots (for hunger calculation)
            known_sources: List of known source IDs

        Returns:
            TacticResult with selected tactic and generated queries
        """
        tactic = self.select(ku_quadrant, slots, known_sources)
        return tactic.generate_queries(target, entity_type, jurisdiction, slots)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def select_tactic(
    ku_quadrant: KUQuadrant,
    slots: Optional[EntitySlotSet] = None,
    known_sources: Optional[List[str]] = None,
) -> Tactic:
    """Select the best tactic for the given context."""
    selector = TacticalSelector()
    return selector.select(ku_quadrant, slots, known_sources)


def generate_tactical_queries(
    ku_quadrant: KUQuadrant,
    target: str,
    entity_type: str,
    jurisdiction: Optional[str] = None,
    slots: Optional[EntitySlotSet] = None,
    known_sources: Optional[List[str]] = None,
) -> TacticResult:
    """Select tactic and generate queries."""
    selector = TacticalSelector()
    return selector.select_and_generate(
        ku_quadrant, target, entity_type, jurisdiction, slots, known_sources
    )


# =============================================================================
# K-U TO TACTIC MAPPING (Reference)
# =============================================================================

KU_TACTIC_MAP = {
    KUQuadrant.VERIFY: TacticType.SPEAR,    # Known-Known → Precision
    KUQuadrant.TRACE: TacticType.TRAP,      # Known-Unknown → Filtered
    KUQuadrant.EXTRACT: TacticType.TRAP,    # Unknown-Known → Extraction
    KUQuadrant.DISCOVER: TacticType.NET,    # Unknown-Unknown → Brute
}


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    from .contracts import create_slots_for_entity

    # Example: Known company, known jurisdiction → SPEAR
    result = generate_tactical_queries(
        ku_quadrant=KUQuadrant.VERIFY,
        target="Acme Corporation",
        entity_type="company",
        jurisdiction="US",
    )
    print(f"Tactic: {result.tactic.value}")
    print(f"Queries: {len(result.queries)}")
    print(f"Confidence: {result.confidence}")
    print(f"Rationale: {result.rationale}")
    print()

    # Example: Known person, unknown sources → TRAP
    result = generate_tactical_queries(
        ku_quadrant=KUQuadrant.TRACE,
        target="John Smith",
        entity_type="person",
    )
    print(f"Tactic: {result.tactic.value}")
    print(f"Queries: {len(result.queries)}")

    # Example: Discovery mode → NET
    result = generate_tactical_queries(
        ku_quadrant=KUQuadrant.DISCOVER,
        target="suspicious-domain.com",
        entity_type="domain",
    )
    print(f"Tactic: {result.tactic.value}")
    print(f"Queries: {len(result.queries)}")
