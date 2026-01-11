"""
SASTRE Dispatcher - Routes queries to IO CLI

This dispatcher is a THIN LAYER that:
1. Reads rules.json (5,620 transformations)
2. Scores rules based on state (subject/location/intent)
3. Routes execution to IO CLI (which handles actual execution)

The actual execution is done by IO CLI, which automatically:
- Creates nodes in cymonides-1-{projectId}
- Creates edges based on relationships.json
- Returns results with entity IDs

This file just does the ROUTING. IO CLI does the EXECUTION.

Relationship Definitions:
- Dynamically loaded from input_output/ontology/relationships.json
- 81 entity type pairs with 303 unique relationships
- Falls back to hardcoded minimal set if ontology file unavailable
- Relationships inform rule category filtering and scoring
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from .contracts import KUQuadrant, Intent, LOCATION_FIELD_CODES, get_field_codes
from .orchestrator import IOClient


# =============================================================================
# ROUTE SELECTION
# =============================================================================

@dataclass
class SelectedRoute:
    """A route selected by the dispatcher."""
    rule_id: str
    rule_label: str
    rule: Dict[str, Any]
    matched_inputs: List[int]  # Field codes that matched
    expected_outputs: List[int]  # Field codes to expect
    score: float


@dataclass
class RouteState:
    """State for route selection."""
    # What we have (Known Knowns)
    subject_type: str  # person, company, domain
    known_fields: Dict[int, Any]  # Field code -> value

    # What we want (Known Unknowns)
    target_fields: List[int]  # Field codes we want to fill

    # Context
    location_type: str = "virtual"  # virtual, physical
    jurisdiction: str = ""  # US, UK, DE, etc.
    intent: Intent = Intent.DISCOVER_SUBJECT
    quadrant: KUQuadrant = KUQuadrant.DISCOVER


# =============================================================================
# PREDICTABLE RELATIONSHIPS - DYNAMIC LOADER
# =============================================================================

def _load_relationship_definitions() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Load relationship definitions from ontology/relationships.json.

    Returns a dict mapping (source_type, target_type) tuples to relationship metadata.
    The ontology file defines valid edge types per entity type, which we transform into
    the dispatcher's expected format.
    """
    # Find ontology file
    ontology_path = Path(__file__).resolve().parent.parent.parent.parent / "input_output" / "ontology" / "relationships.json"

    if not ontology_path.exists():
        print(f"Warning: relationships.json not found at {ontology_path}, using fallback")
        return _get_fallback_relationships()

    try:
        with open(ontology_path) as f:
            ontology = json.load(f)
    except Exception as e:
        print(f"Error loading relationships.json: {e}, using fallback")
        return _get_fallback_relationships()

    # Transform ontology format to dispatcher format
    relationships: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # Map entity types to "virtual" for dispatcher purposes
    virtual_types = {"domain", "url", "email", "phone", "username", "ip_address"}

    for entity_type, entity_def in ontology.items():
        if entity_type == "et3" or entity_type == "project" or entity_type == "watcher":
            continue  # Skip meta entity types for now

        for edge in entity_def.get("edge_types", []):
            rel_type = edge["relationship_type"]
            direction = edge["direction"]
            source_types = edge.get("source_types", [])
            target_types = edge.get("target_types", [])
            category = edge.get("category", "")

            # Map categories to rule_categories
            rule_categories = _map_category_to_rules(category)

            # Build tuples for all source-target combinations
            for source in source_types:
                for target in target_types:
                    # Normalize types (map virtual types)
                    source_normalized = "virtual" if source in virtual_types else source
                    target_normalized = "virtual" if target in virtual_types else target

                    key = (source_normalized, target_normalized)

                    if key not in relationships:
                        relationships[key] = {
                            "relationships": [],
                            "rule_categories": set(),
                            "friction_priority": ["Open", "Paywalled", "Restricted"],
                        }

                    relationships[key]["relationships"].append(rel_type)
                    relationships[key]["rule_categories"].update(rule_categories)

            # Handle bidirectional relationships
            if direction == "bidirectional":
                for source in source_types:
                    for target in target_types:
                        source_normalized = "virtual" if source in virtual_types else source
                        target_normalized = "virtual" if target in virtual_types else target

                        reverse_key = (target_normalized, source_normalized)

                        if reverse_key not in relationships:
                            relationships[reverse_key] = {
                                "relationships": [],
                                "rule_categories": set(),
                                "friction_priority": ["Open", "Paywalled", "Restricted"],
                            }

                        relationships[reverse_key]["relationships"].append(rel_type)
                        relationships[reverse_key]["rule_categories"].update(rule_categories)

    # Convert sets to lists for final output
    for key in relationships:
        relationships[key]["rule_categories"] = sorted(list(relationships[key]["rule_categories"]))

    return relationships


def _map_category_to_rules(category: str) -> List[str]:
    """Map ontology categories to dispatcher rule categories."""
    mapping = {
        "corporate_structure": ["corporate", "registry"],
        "ownership": ["corporate", "registry"],
        "contact_info": ["person", "corporate"],
        "employment": ["corporate", "person"],
        "family": ["person", "social"],
        "compliance": ["compliance", "registry"],
        "location": ["geo", "registry"],
        "online_presence": ["domain", "social"],
        "social_media": ["social", "domain"],
        "mention": ["news", "entity_extraction"],
        "association": ["corporate", "person"],
        "education": ["person"],
        "regulatory": ["registry", "compliance"],
        "evidence": ["entity_extraction"],
        "operations": ["corporate"],
        "registration": ["registry"],
        "membership": ["corporate", "person"],
        "financial": ["corporate", "registry"],
        "occupancy": ["geo", "property"],
        "link_intelligence": ["domain", "link"],
        "infrastructure": ["domain", "geo"],
        "et3_core": ["entity_extraction", "narrative"],
        "et3_causal": ["entity_extraction", "narrative"],
        "timeline": ["entity_extraction", "narrative"],
        "project_membership": ["project"],
        "context": ["narrative"],
        "provenance": ["entity_extraction"],
        "discovery": ["search", "entity_extraction"],
    }

    return mapping.get(category, ["uncategorized"])


def _get_fallback_relationships() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Fallback relationships if ontology file can't be loaded."""
    return {
        # Person relationships
        ("person", "company"): {
            "relationships": ["officer_of", "shareholder_of", "beneficial_owner_of", "employee_of"],
            "rule_categories": ["corporate", "registry"],
            "friction_priority": ["Open", "Paywalled", "Restricted"],
        },
        ("person", "person"): {
            "relationships": ["family_of", "colleague_of", "co_director", "associate_of"],
            "rule_categories": ["person", "social", "corporate"],
            "friction_priority": ["Open", "Paywalled"],
        },
        ("person", "virtual"): {
            "relationships": ["has_email", "appears_on", "owns_domain", "mentioned_on"],
            "rule_categories": ["domain", "person", "breach", "social"],
            "friction_priority": ["Open", "Paywalled"],
        },

        # Company relationships
        ("company", "company"): {
            "relationships": ["subsidiary_of", "parent_of", "shares_address_with", "shares_officer_with"],
            "rule_categories": ["corporate", "registry"],
            "friction_priority": ["Open", "Paywalled"],
        },
        ("company", "person"): {
            "relationships": ["has_officer", "has_shareholder", "has_ubo", "has_employee"],
            "rule_categories": ["corporate", "registry"],
            "friction_priority": ["Open", "Paywalled"],
        },
        ("company", "virtual"): {
            "relationships": ["owns_domain", "listed_on", "mentioned_on"],
            "rule_categories": ["domain", "corporate", "news"],
            "friction_priority": ["Open", "Paywalled"],
        },

        # Virtual relationships
        ("virtual", "virtual"): {
            "relationships": ["backlinks_to", "shares_ga_with", "shares_hosting_with", "links_to"],
            "rule_categories": ["domain", "link", "archive"],
            "friction_priority": ["Open", "Paywalled"],
        },
        ("virtual", "person"): {
            "relationships": ["mentions", "authored_by", "registered_by"],
            "rule_categories": ["domain", "entity_extraction", "whois"],
            "friction_priority": ["Open", "Paywalled"],
        },
    }


# Load relationships at module level (cached)
PREDICTABLE_RELATIONSHIPS: Dict[Tuple[str, str], Dict[str, Any]] = _load_relationship_definitions()


# =============================================================================
# DISPATCHER
# =============================================================================

class Dispatcher:
    """
    Routes queries to IO CLI based on rules.json scoring.

    This is a THIN LAYER - it selects the route, then IO CLI executes.
    """

    def __init__(self, rules_path: Optional[Path] = None, legend_path: Optional[Path] = None):
        # Find matrix files
        base = Path(__file__).resolve().parent.parent.parent.parent / "input_output2" / "matrix"

        rules_file = rules_path or base / "rules.json"
        legend_file = legend_path or base / "legend.json"

        # Load rules (5,620 transformations)
        if rules_file.exists():
            with open(rules_file) as f:
                self.rules: List[Dict[str, Any]] = json.load(f)
        else:
            self.rules = []
            print(f"Warning: rules.json not found at {rules_file}")

        # Load legend (280 field codes)
        if legend_file.exists():
            with open(legend_file) as f:
                self.legend: Dict[str, str] = json.load(f)
        else:
            self.legend = {}
            print(f"Warning: legend.json not found at {legend_file}")

        # Reverse legend: name -> code
        self.name_to_code: Dict[str, int] = {v: int(k) for k, v in self.legend.items()}

        # Build category index
        self.rules_by_category: Dict[str, List[Dict]] = {}
        for rule in self.rules:
            category = rule.get("category", "uncategorized")
            if category not in self.rules_by_category:
                self.rules_by_category[category] = []
            self.rules_by_category[category].append(rule)

        # IO CLI client
        self.io = IOClient()

    async def close(self):
        """Cleanup resources."""
        await self.io.close()

    def select_route(self, state: RouteState) -> Optional[SelectedRoute]:
        """
        Select best route for given state.

        This is DETERMINISTIC - same state always returns same route.
        """
        candidates: List[SelectedRoute] = []

        # Get relationship constraints
        rel_key = (state.subject_type, state.location_type)
        relationship = PREDICTABLE_RELATIONSHIPS.get(rel_key, {})
        allowed_categories = relationship.get("rule_categories", [])
        friction_priority = relationship.get("friction_priority", ["Open", "Paywalled", "Restricted"])

        # Get rules to check
        if allowed_categories:
            rules_to_check = []
            for cat in allowed_categories:
                rules_to_check.extend(self.rules_by_category.get(cat, []))
        else:
            rules_to_check = self.rules

        have_codes = set(state.known_fields.keys())
        target_codes = set(state.target_fields)

        for rule in rules_to_check:
            # Check inputs
            requires_any = set(rule.get("requires_any", []))
            requires_all = set(rule.get("requires_all", []))

            have_any = bool(requires_any & have_codes) if requires_any else True
            have_all = requires_all.issubset(have_codes) if requires_all else True

            if not have_any or not have_all:
                continue

            # Check outputs
            returns = set(rule.get("returns", []))
            useful_outputs = returns & target_codes if target_codes else returns

            if target_codes and not useful_outputs:
                continue

            # Check friction
            friction = rule.get("friction", "Open")
            if friction not in friction_priority:
                continue

            # Score
            score = self._score_rule(rule, state, useful_outputs, friction_priority)

            candidates.append(SelectedRoute(
                rule_id=rule.get("id", "unknown"),
                rule_label=rule.get("label", ""),
                rule=rule,
                matched_inputs=list(requires_any & have_codes),
                expected_outputs=list(useful_outputs) if useful_outputs else list(returns)[:10],
                score=score
            ))

        if not candidates:
            return None

        # Return highest scoring (deterministic sort)
        candidates.sort(key=lambda r: (-r.score, r.rule_id))
        return candidates[0]

    def _score_rule(
        self,
        rule: Dict[str, Any],
        state: RouteState,
        useful_outputs: set,
        friction_priority: List[str]
    ) -> float:
        """Score a rule (0-100)."""
        score = 0.0
        category = rule.get("category", "")
        rule_id = rule.get("id", "").lower()

        # 1. Intent alignment (25 points)
        if state.intent == Intent.DISCOVER_SUBJECT:
            if category in ["person", "corporate", "entity_extraction", "social"]:
                score += 25
            elif category in ["registry", "breach"]:
                score += 15
        elif state.intent == Intent.DISCOVER_LOCATION:
            if category in ["domain", "link", "geo", "archive"]:
                score += 25
            elif category in ["search", "news"]:
                score += 15
        elif state.intent == Intent.ENRICH_SUBJECT:
            if category in ["corporate", "person", "social", "registry"]:
                score += 20
            elif category in ["breach", "property"]:
                score += 15
        elif state.intent == Intent.ENRICH_LOCATION:
            if category in ["domain", "link", "archive", "whois"]:
                score += 20

        # 2. Quadrant match (20 points)
        if state.quadrant == KUQuadrant.VERIFY:
            if "verify" in rule_id or "check" in rule_id:
                score += 20
        elif state.quadrant == KUQuadrant.TRACE:
            score += 15
        elif state.quadrant == KUQuadrant.EXTRACT:
            if "extract" in rule_id or category == "entity_extraction":
                score += 20
        elif state.quadrant == KUQuadrant.DISCOVER:
            if "discover" in rule_id or "search" in rule_id:
                score += 20

        # 3. Friction (15 points)
        friction = rule.get("friction", "Open")
        try:
            friction_idx = friction_priority.index(friction)
            friction_score = (len(friction_priority) - friction_idx) * 5
            score += min(friction_score, 15)
        except ValueError:
            pass

        # 4. Output coverage (20 points)
        output_count = len(useful_outputs) if useful_outputs else len(rule.get("returns", []))
        score += min(output_count * 2, 20)

        # 5. Jurisdiction match (10 points)
        rule_jurisdiction = rule.get("jurisdiction", "none")
        if rule_jurisdiction == "none":
            score += 5
        elif rule_jurisdiction == state.jurisdiction:
            score += 10

        # 6. Specificity (10 points)
        requires_count = len(rule.get("requires_any", [])) + len(rule.get("requires_all", []))
        score += min(requires_count, 10)

        return score

    async def execute(
        self,
        query: str,
        project_id: str,
        state: Optional[RouteState] = None
    ) -> Dict[str, Any]:
        """
        Execute query via IO CLI.

        Optionally provide state for route selection logging.
        The actual execution goes to IO CLI which handles:
        - Module routing
        - Node/edge creation
        - Result aggregation
        """
        # Select route if state provided
        selected_route = None
        if state:
            selected_route = self.select_route(state)
            if selected_route:
                print(f"Selected route: {selected_route.rule_id} (score: {selected_route.score:.1f})")

        # Execute via IO CLI
        result = await self.io.investigate(
            query=query,
            project_id=project_id
        )

        # Add route info to result
        if selected_route:
            result["selected_route"] = {
                "rule_id": selected_route.rule_id,
                "rule_label": selected_route.rule_label,
                "score": selected_route.score,
                "expected_outputs": selected_route.expected_outputs
            }

        return result

    def get_all_routes(self, state: RouteState, limit: int = 10) -> List[SelectedRoute]:
        """Get all applicable routes ranked by score."""
        candidates: List[SelectedRoute] = []

        rel_key = (state.subject_type, state.location_type)
        relationship = PREDICTABLE_RELATIONSHIPS.get(rel_key, {})
        allowed_categories = relationship.get("rule_categories", [])
        friction_priority = relationship.get("friction_priority", ["Open", "Paywalled", "Restricted"])

        if allowed_categories:
            rules_to_check = []
            for cat in allowed_categories:
                rules_to_check.extend(self.rules_by_category.get(cat, []))
        else:
            rules_to_check = self.rules

        have_codes = set(state.known_fields.keys())
        target_codes = set(state.target_fields)

        for rule in rules_to_check:
            requires_any = set(rule.get("requires_any", []))
            requires_all = set(rule.get("requires_all", []))

            have_any = bool(requires_any & have_codes) if requires_any else True
            have_all = requires_all.issubset(have_codes) if requires_all else True

            if not have_any or not have_all:
                continue

            returns = set(rule.get("returns", []))
            useful_outputs = returns & target_codes if target_codes else returns

            friction = rule.get("friction", "Open")
            if friction not in friction_priority:
                continue

            score = self._score_rule(rule, state, useful_outputs, friction_priority)

            candidates.append(SelectedRoute(
                rule_id=rule.get("id", "unknown"),
                rule_label=rule.get("label", ""),
                rule=rule,
                matched_inputs=list(requires_any & have_codes),
                expected_outputs=list(useful_outputs) if useful_outputs else list(returns)[:10],
                score=score
            ))

        candidates.sort(key=lambda r: (-r.score, r.rule_id))
        return candidates[:limit]

    def explain(self, state: RouteState) -> str:
        """Explain why a route was selected."""
        route = self.select_route(state)
        if not route:
            return "No applicable route found for current state."

        lines = [
            f"Selected Route: {route.rule_id}",
            f"Label: {route.rule_label}",
            f"Score: {route.score:.1f}/100",
            "",
            "State:",
            f"  Subject Type: {state.subject_type}",
            f"  Location Type: {state.location_type}",
            f"  Intent: {state.intent.value}",
            f"  Quadrant: {state.quadrant.value}",
            f"  Known Fields: {list(state.known_fields.keys())}",
            "",
            "Route Match:",
            f"  Matched Inputs: {route.matched_inputs}",
            f"  Expected Outputs: {route.expected_outputs}",
            f"  Friction: {route.rule.get('friction', 'Unknown')}",
            f"  Category: {route.rule.get('category', 'Unknown')}",
        ]

        return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_state(
    entity_type: str,
    known_values: Dict[str, Any],
    target_fields: List[str] = None,
    jurisdiction: str = ""
) -> RouteState:
    """
    Create RouteState from friendly field names.

    Example:
        state = create_state(
            entity_type="company",
            known_values={"name": "Acme Corp"},
            target_fields=["officers", "shareholders"],
            jurisdiction="US"
        )
    """
    # Map field names to codes using dynamic schema loading
    all_fields = get_field_codes(entity_type)

    # Build known_fields with codes
    known_fields: Dict[int, Any] = {}
    for name, value in known_values.items():
        if name in all_fields:
            known_fields[all_fields[name]] = value
        elif isinstance(name, int):
            known_fields[name] = value

    # Build target codes
    target_codes: List[int] = []
    if target_fields:
        for name in target_fields:
            if name in all_fields:
                target_codes.append(all_fields[name])
            elif isinstance(name, int):
                target_codes.append(name)

    return RouteState(
        subject_type=entity_type,
        known_fields=known_fields,
        target_fields=target_codes,
        jurisdiction=jurisdiction
    )
