"""
KU Router - Known/Unknown Matrix Router

Routes UNKNOWN nodes to concrete discovery/enrichment actions
based on CLASS, type, and KNOWN context.

KU Matrix:
    - UNKNOWN: What we're seeking (subject-side)
    - KNOWN: Context/constraint we have (location-side)

Usage:
    from modules.syntax.ku_router import KURouter, route_ku

    router = KURouter()

    # Route an unknown node given known context
    action = router.route(
        unknown={"class": "SUBJECT", "type": "person"},
        known={"class": "LOCATION", "type": "jurisdiction", "value": "UK"}
    )
    # Returns: {"intent": "EXTRACT", "engine": "companies_house_api", "syntax": "puk: :#anchor", ...}

    # Get enrichment slots for a known node
    slots = router.get_enrichment_slots("SUBJECT", "company")
    # Returns: ["registration_number", "status", "incorporation_date", ...]

    # Determine intent from triad pattern
    intent = router.triad_intent("[K]-[U]-[K]")
    # Returns: {"intent": "DISCOVER", "subtype": "TRACE", "action": "Find link between known endpoints"}
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum


class Intent(Enum):
    DISCOVER = "DISCOVER"
    ENRICH = "ENRICH"


class DiscoverSubtype(Enum):
    TRACE = "TRACE"      # Known anchor, unknown venue
    EXTRACT = "EXTRACT"  # Unknown anchor, known venue
    NET = "NET"          # Both unknown


class EnrichSubtype(Enum):
    FILL = "FILL"        # Populate empty slots
    VERIFY = "VERIFY"    # Confirm existing values


@dataclass
class UnknownNode:
    """An UNKNOWN node - what we're seeking (subject-side)."""
    node_class: str  # SUBJECT, LOCATION, NEXUS, NARRATIVE
    node_type: str   # person, company, jurisdiction, domain, etc.
    constraints: Dict[str, Any] = None
    state: str = "SOUGHT"  # SOUGHT or SPECULATED

    def __post_init__(self):
        if self.constraints is None:
            self.constraints = {}

    @property
    def key(self) -> str:
        """Generate lookup key."""
        return f"{self.node_class}:{self.node_type}"

    def to_notation(self) -> str:
        """Convert to syntax notation [U:Type #constraints]."""
        parts = [f"U:{self.node_type.capitalize()}"]
        for k, v in self.constraints.items():
            if k == "tags":
                parts.extend(v)
            elif k == "jurisdiction":
                if isinstance(v, list):
                    parts.extend([f"#{j}" for j in v])
                else:
                    parts.append(f"#{v}")
        return f"[{' '.join(parts)}]"


@dataclass
class KnownNode:
    """A KNOWN node - context/constraint we have (location-side)."""
    node_class: str
    node_type: str
    value: Any = None

    @property
    def key(self) -> str:
        """Generate lookup key."""
        jurisdiction = None
        if self.node_type == "jurisdiction" and self.value:
            jurisdiction = self.value
        return f"{self.node_class}:{self.node_type}:{jurisdiction or '*'}"


@dataclass
class RoutingAction:
    """The concrete action to take."""
    intent: str
    subtype: Optional[str]
    engine: str
    syntax: str
    extractor: Optional[str] = None
    fallback: Optional[str] = None
    creates_unknowns: Optional[List[str]] = None
    void_is_finding: bool = False


class KURouter:
    """Routes UNKNOWN nodes to concrete actions based on KNOWN context."""

    def __init__(self, config_dir: Path = None):
        if config_dir is None:
            config_dir = Path(__file__).parent

        self.config_dir = config_dir
        self._load_configs()

    def _load_configs(self):
        """Load routing configuration from JSON files."""
        # Load main routing matrix
        matrix_path = self.config_dir / "discovery_routing_matrix.json"
        if matrix_path.exists():
            with open(matrix_path) as f:
                self.matrix = json.load(f)
        else:
            self.matrix = {}

        # Load fast lookup table
        lookup_path = self.config_dir / "routing_lookup.json"
        if lookup_path.exists():
            with open(lookup_path) as f:
                self.lookup = json.load(f)
        else:
            self.lookup = {"lookup": {}, "enrichment_slots": {}, "triad_to_intent": {}}

    def route(
        self,
        unknown: Union[UnknownNode, Dict],
        known: Union[KnownNode, Dict, List[Dict], None] = None
    ) -> Optional[RoutingAction]:
        """
        Route an UNKNOWN node to a concrete action.

        Args:
            unknown: The UNKNOWN node (what we're looking for / subject-side)
            known: The KNOWN context (where/what we know / location-side)

        Returns:
            RoutingAction with engine, syntax, etc.
        """
        # Normalize inputs
        if isinstance(unknown, dict):
            unknown = UnknownNode(
                node_class=unknown.get("class"),
                node_type=unknown.get("type"),
                constraints=unknown.get("constraints", {})
            )

        if known is None:
            known_key = "null:null:null"
        elif isinstance(known, dict):
            known = KnownNode(
                node_class=known.get("class"),
                node_type=known.get("type"),
                value=known.get("value")
            )
            known_key = known.key
        elif isinstance(known, KnownNode):
            known_key = known.key
        elif isinstance(known, list):
            # Multiple known nodes - use first for now
            k = known[0]
            known_key = f"{k.get('class')}:{k.get('type')}:*"
        else:
            known_key = "null:null:null"

        # Build lookup key
        lookup_key = f"{unknown.key}:{known_key}"

        # Try exact match first
        if lookup_key in self.lookup.get("lookup", {}):
            action_data = self.lookup["lookup"][lookup_key]
            return self._build_action(action_data)

        # Try wildcard match
        wildcard_key = f"{unknown.key}:{unknown.node_class}:{unknown.node_type}:*"
        if wildcard_key in self.lookup.get("lookup", {}):
            action_data = self.lookup["lookup"][wildcard_key]
            return self._build_action(action_data)

        # Try class-level wildcard
        for key, action_data in self.lookup.get("lookup", {}).items():
            if key.startswith(f"{unknown.key}:") and key.endswith(":*"):
                return self._build_action(action_data)

        # Fall back to NET discovery
        net_key = f"{unknown.key}:null:null:null"
        if net_key in self.lookup.get("lookup", {}):
            action_data = self.lookup["lookup"][net_key]
            return self._build_action(action_data)

        return None

    def _build_action(self, data: Dict) -> RoutingAction:
        """Build RoutingAction from dict."""
        return RoutingAction(
            intent=data.get("intent"),
            subtype=data.get("subtype"),
            engine=data.get("engine"),
            syntax=data.get("syntax"),
            extractor=data.get("extractor"),
            fallback=data.get("fallback"),
            creates_unknowns=data.get("creates_unknowns"),
            void_is_finding=data.get("void_is_finding", False)
        )

    def get_enrichment_slots(self, node_class: str, node_type: str) -> List[str]:
        """Get the slots that can be enriched for a node type."""
        key = f"{node_class}:{node_type}"
        slot_config = self.lookup.get("enrichment_slots", {}).get(key, {})
        return slot_config.get("slots", [])

    def get_enrichment_route(
        self,
        node_class: str,
        node_type: str,
        slot: str
    ) -> Optional[Dict]:
        """Get the route for enriching a specific slot."""
        key = f"{node_class}:{node_type}"
        slot_config = self.lookup.get("enrichment_slots", {}).get(key, {})
        routes = slot_config.get("routes", {})

        # Check for specific slot route
        if slot in routes:
            return routes[slot]

        # Check for wildcard route
        if "*" in routes:
            return routes["*"]

        return None

    def triad_intent(self, pattern: str) -> Optional[Dict]:
        """
        Determine intent from triad pattern.

        Args:
            pattern: e.g., "[K]-[U]-[K]" or "[U]-[U]-[K]"

        Returns:
            Dict with intent, subtype, action
        """
        # Normalize to [U] notation (the canonical form)
        normalized = pattern.replace("[?]", "[U]")
        return self.lookup.get("triad_to_intent", {}).get(normalized)

    def analyze_triad(
        self,
        a: Union[str, UnknownNode, KnownNode],
        r: Union[str, UnknownNode, KnownNode],
        b: Union[str, UnknownNode, KnownNode]
    ) -> Dict:
        """
        Analyze a triad and determine routing.

        Args:
            a: Party A (can be "K", "U", UnknownNode, or KnownNode)
            r: Relationship
            b: Party B

        Returns:
            Dict with intent, actions, and unknown specifications
        """
        def to_symbol(node):
            if node == "K" or isinstance(node, KnownNode):
                return "K"
            elif node in ("U", "?") or isinstance(node, UnknownNode):
                return "U"
            elif isinstance(node, dict):
                if node.get("known"):
                    return "K"
                return "U"
            return "U"

        pattern = f"[{to_symbol(a)}]-[{to_symbol(r)}]-[{to_symbol(b)}]"
        intent_info = self.triad_intent(pattern)

        result = {
            "pattern": pattern,
            "intent_info": intent_info,
            "unknowns": [],
            "actions": []
        }

        # Collect unknown nodes that need routing
        for node, label in [(a, "A"), (r, "R"), (b, "B")]:
            if isinstance(node, UnknownNode):
                action = self.route(node)
                result["unknowns"].append({
                    "position": label,
                    "unknown": node,
                    "action": action
                })
            elif isinstance(node, dict) and not node.get("known"):
                unknown = UnknownNode(
                    node_class=node.get("class", "SUBJECT"),
                    node_type=node.get("type", "unknown")
                )
                action = self.route(unknown)
                result["unknowns"].append({
                    "position": label,
                    "unknown": unknown,
                    "action": action
                })

        return result

    def is_void_finding(self, check_type: str) -> Optional[Dict]:
        """
        Check if void result for this check type is a finding.

        Args:
            check_type: e.g., "sanctions?", "pep?", "reg{cc}:"

        Returns:
            Dict with result label and confidence, or None
        """
        return self.lookup.get("void_is_finding", {}).get(check_type)

    def get_class_info(self, class_name: str) -> Optional[Dict]:
        """Get information about a CLASS."""
        return self.matrix.get("classes", {}).get(class_name)

    def get_all_types(self, class_name: str) -> List[str]:
        """Get all types under a CLASS."""
        class_info = self.get_class_info(class_name)
        if class_info:
            return class_info.get("types", [])
        return []


# =============================================================================
# Convenience functions
# =============================================================================

_router = None


def get_ku_router() -> KURouter:
    """Get singleton router instance."""
    global _router
    if _router is None:
        _router = KURouter()
    return _router


def route_ku(
    unknown_class: str,
    unknown_type: str,
    known_class: str = None,
    known_type: str = None,
    known_value: Any = None
) -> Optional[RoutingAction]:
    """
    Quick routing function using KU matrix.

    Args:
        unknown_class: SUBJECT, LOCATION, NEXUS, NARRATIVE (what we're seeking)
        unknown_type: person, company, jurisdiction, etc.
        known_class: Class of known context (location-side)
        known_type: Type of known context
        known_value: Value of known context (e.g., "UK" for jurisdiction)

    Returns:
        RoutingAction or None
    """
    router = get_ku_router()

    unknown = UnknownNode(node_class=unknown_class, node_type=unknown_type)

    known = None
    if known_class and known_type:
        known = KnownNode(
            node_class=known_class,
            node_type=known_type,
            value=known_value
        )

    return router.route(unknown, known)


def get_intent(pattern: str) -> Optional[Dict]:
    """Get intent from triad pattern."""
    return get_ku_router().triad_intent(pattern)


# Example usage
if __name__ == "__main__":
    router = KURouter()

    # Test 1: Person in UK jurisdiction
    print("=== Test 1: Person (UNKNOWN) in UK (KNOWN) ===")
    action = router.route(
        unknown={"class": "SUBJECT", "type": "person"},
        known={"class": "LOCATION", "type": "jurisdiction", "value": "UK"}
    )
    print(f"Action: {action}")

    # Test 2: Company with no known context (NET)
    print("\n=== Test 2: Company (UNKNOWN) - no KNOWN context ===")
    action = router.route(
        unknown={"class": "SUBJECT", "type": "company"},
        known=None
    )
    print(f"Action: {action}")

    # Test 3: Triad intent
    print("\n=== Test 3: Triad Intent [K]-[U]-[K] ===")
    intent = router.triad_intent("[K]-[U]-[K]")
    print(f"Intent: {intent}")

    # Test 4: Enrichment slots
    print("\n=== Test 4: Enrichment Slots ===")
    slots = router.get_enrichment_slots("SUBJECT", "person")
    print(f"Slots: {slots}")
