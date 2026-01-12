#!/usr/bin/env python3
"""
IO Router - The Brain: Implements Qualified Operators and determines Intel vs Action.

This is TIER 2 of the Ultimate Unification Plan - the Modular Engine (routing logic).

Operator Syntax:
- Input Type Only: p:, e:, c:, t:, d: (Person, Email, Company, Phone, Domain)
- Qualified (Type + Jurisdiction): pde: (Person in Germany), cnl: (Company in Netherlands)
- Qualified (Jurisdiction + Type): atcr: (Austria Corporate Registry), ukch: (UK Companies House)
- Qualified (Intent + Jurisdiction): litde: (German Litigation), newsuk: (UK News)

Two Operational Modes:
- INTEL MODE: Operator without value → Returns wiki wisdom, registry profile, dead ends
- ACTION MODE: Operator with value → Executes search, returns IOResult

Usage:
    router = IORouter(compiler)

    # Parse operator
    context = router.parse_operator("atcr:")        # Intel mode
    context = router.parse_operator("atcr: Siemens") # Action mode

    # Route to handler
    route = router.route(context)
"""

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

from io_compiler import IOCompiler, UnifiedSource

# Mined intelligence for chains, dead ends, arbitrage
try:
    from mined_intelligence import get_mined_intelligence, MinedIntelligence
    MINED_AVAILABLE = True
except ImportError:
    get_mined_intelligence = None
    MinedIntelligence = None
    MINED_AVAILABLE = False

logger = logging.getLogger(__name__)

MATRIX_DIR = Path(__file__).parent


# =============================================================================
# OPERATOR SYNTAX DEFINITIONS
# =============================================================================

# Entity type operators (single letter)
ENTITY_TYPE_OPERATORS = {
    "p": "person",
    "c": "company",
    "e": "email",
    "t": "phone",
    "d": "domain",
    "u": "username",
    "a": "address",
}

# Intent operators
INTENT_OPERATORS = {
    "lit": "litigation",
    "news": "news",
    "reg": "regulatory",
    "sanc": "sanctions",
    "pep": "pep",
    "adv": "adverse_media",
    "fin": "financial",
    "asset": "asset",
    "prop": "property",
    "ip": "intellectual_property",
    "social": "social_media",
}

# Source type operators
SOURCE_OPERATORS = {
    "cr": "corporate_registry",
    "ch": "companies_house",  # UK specific
    "br": "business_registry",
    "ct": "court_records",
    "lr": "land_registry",
    "tr": "trademark_registry",
    "ar": "archive",
}

# Common jurisdiction codes (2-letter ISO)
JURISDICTION_CODES = {
    "at", "au", "be", "bg", "br", "ca", "ch", "cn", "cz", "de", "dk",
    "ee", "es", "fi", "fr", "gb", "gr", "hr", "hu", "ie", "in", "it",
    "jp", "kr", "lt", "lu", "lv", "mx", "nl", "no", "nz", "pl", "pt",
    "ro", "ru", "se", "sg", "si", "sk", "uk", "us", "za",
}

# UK aliases
UK_ALIASES = {"uk", "gb", "gbr"}


@dataclass
class OperatorContext:
    """Parsed operator context with all components."""

    raw_query: str                   # Original query string
    operator: str                    # Just the operator part (e.g., "atcr")
    value: Optional[str]             # The value after operator (e.g., "Siemens")
    mode: str                        # "intel" or "action"

    # Parsed components
    jurisdiction: Optional[str] = None   # e.g., "AT", "GB"
    entity_type: Optional[str] = None    # e.g., "person", "company"
    intent: Optional[str] = None         # e.g., "litigation", "news"
    source_type: Optional[str] = None    # e.g., "corporate_registry"

    # Resolved information
    resolved_jurisdiction: Optional[str] = None  # ISO-resolved
    matched_sources: List[str] = field(default_factory=list)


@dataclass
class RouteResult:
    """Result of routing an operator."""

    mode: str                        # "intel" or "action"
    context: OperatorContext         # Original parsed context

    # Intel mode fields
    sources: List[Dict] = field(default_factory=list)     # Available sources
    wiki: Dict = field(default_factory=dict)              # Wiki wisdom
    dead_ends: List[Dict] = field(default_factory=list)   # Impossible routes
    arbitrage: List[Dict] = field(default_factory=list)   # Alternative paths
    mined_chains: List[Dict] = field(default_factory=list)  # Mined execution chains

    # Action mode fields
    rule: Optional[Dict] = None                           # Matched rule for execution
    handler: Optional[str] = None                         # Handler type
    fallback_chain: List[str] = field(default_factory=list)  # Fallback handlers

    # Execution hints
    search_template: Optional[str] = None                 # URL template
    methodology: Optional[str] = None                     # Methodology atom


class IORouter:
    """
    The Brain - Implements Qualified Operators and determines Intel vs Action.

    Parses queries like:
    - "atcr:" → Intel mode for Austrian Corporate Registry
    - "atcr: Siemens" → Action mode, search Siemens in Austrian registry
    - "p: John Smith" → Person search (global)
    - "pde: Hans Mueller" → Person search in Germany
    """

    def __init__(self, compiler: Optional[IOCompiler] = None):
        self.compiler = compiler or IOCompiler()
        self._rules = self._load_rules()
        self._flows = self._load_flows()
        self._registries = self._load_registries()
        self._mined = get_mined_intelligence() if MINED_AVAILABLE else None

    def _load_rules(self) -> Dict[str, Dict]:
        """Load rules.json indexed by ID."""
        rules_path = MATRIX_DIR / "rules.json"
        if not rules_path.exists():
            return {}
        with open(rules_path) as f:
            data = json.load(f)
            # Handle both formats: list of rules or {meta, rules} dict
            if isinstance(data, list):
                return {rule.get("id", ""): rule for rule in data if rule.get("id")}
            elif isinstance(data, dict):
                # New format with meta + rules dict
                rules_dict = data.get("rules", {})
                if isinstance(rules_dict, dict):
                    return rules_dict
                elif isinstance(rules_dict, list):
                    return {rule.get("id", ""): rule for rule in rules_dict if rule.get("id")}
            return {}

    def _load_flows(self) -> Dict[str, Dict]:
        """Load flows.json for routing."""
        flows_path = MATRIX_DIR / "flows.json"
        if not flows_path.exists():
            return {}
        with open(flows_path) as f:
            return json.load(f)

    def _load_registries(self) -> Dict[str, Dict]:
        """Load registries.json for URL resolution."""
        registries_path = MATRIX_DIR / "registries.json"
        if not registries_path.exists():
            return {}
        with open(registries_path) as f:
            return json.load(f)

    # ==========================================================================
    # MINED INTELLIGENCE INTEGRATION
    # ==========================================================================

    def find_mined_chain(
        self,
        jurisdiction: str,
        entity_type: str = None,
        intent: str = None,
        goal: str = None
    ) -> Optional[Dict]:
        """
        Find a mined chain for the given context.

        Mined chains are derived from 6,126+ proven investigation patterns
        and provide jurisdiction-specific execution paths.

        Args:
            jurisdiction: Target jurisdiction (e.g., "HU", "CH")
            entity_type: Entity type (e.g., "company", "person")
            intent: Search intent (e.g., "litigation", "news")
            goal: Investigation goal (e.g., "trace_ubo", "corporate_structure")

        Returns:
            Best matching chain or None
        """
        if not self._mined:
            return None

        # Map entity_type to goal if not provided
        if not goal:
            if entity_type == "company":
                goal = "corporate_structure"
            elif entity_type == "person":
                goal = "verify_identity"
            elif intent == "litigation":
                goal = "litigation_history"
            elif intent in ("asset", "property"):
                goal = "find_assets"

        if goal:
            return self._mined.get_best_chain(goal, jurisdiction.upper())

        # Fallback: get any chains for jurisdiction
        chains = self._mined.get_chains_for_jurisdiction(jurisdiction.upper())
        return chains[0] if chains else None

    def get_mined_chains(
        self,
        jurisdiction: str,
        max_results: int = 10
    ) -> List[Dict]:
        """Get all mined chains for a jurisdiction."""
        if not self._mined:
            return []
        return self._mined.get_chains_for_jurisdiction(jurisdiction.upper())[:max_results]

    def check_dead_end(self, query: str, jurisdiction: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a query is a known dead end for the jurisdiction.

        Returns:
            Tuple of (is_dead_end, reason)
        """
        if not self._mined:
            return False, None
        return self._mined.is_dead_end(query, jurisdiction.upper())

    def get_arbitrage_suggestions(
        self,
        jurisdiction: str,
        query: str
    ) -> List[Dict]:
        """Get arbitrage alternatives for a failing query."""
        if not self._mined:
            return []
        return self._mined.suggest_arbitrage(jurisdiction.upper(), query)

    # ==========================================================================
    # OPERATOR PARSING
    # ==========================================================================

    def parse_operator(self, query: str) -> OperatorContext:
        """
        Parse query into structured context.

        Examples:
        - "atcr:" → Intel mode (no value) → Return registry profile
        - "atcr: Siemens" → Action mode → Execute search
        - "p: John Smith" → Action mode → Person search
        - "pde: John Smith" → Action mode → German person search
        - "lituk: Apple" → Action mode → UK litigation search
        """
        query = query.strip()

        # Split operator from value
        operator, value = self._split_operator_value(query)

        # Determine mode
        mode = "action" if value else "intel"

        context = OperatorContext(
            raw_query=query,
            operator=operator.lower(),
            value=value.strip() if value else None,
            mode=mode
        )

        # Parse operator components
        self._parse_operator_components(context)

        # Resolve jurisdiction
        if context.jurisdiction:
            context.resolved_jurisdiction = self.compiler.resolve_jurisdiction(
                context.jurisdiction.upper()
            )

        return context

    def _split_operator_value(self, query: str) -> Tuple[str, Optional[str]]:
        """Split query into operator and value parts."""
        # Pattern: operator: value OR operator (no colon for intel)
        # operator can be like: p, pde, atcr, lituk, etc.

        # Check for colon separator
        if ":" in query:
            parts = query.split(":", 1)
            operator = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
            return operator, value
        else:
            # No colon - treat entire query as operator (intel mode)
            return query.strip(), None

    def _parse_operator_components(self, context: OperatorContext):
        """
        Parse operator into jurisdiction, entity_type, intent, source_type.

        Patterns:
        - Single letter: p, c, e, t, d → entity type (global)
        - 2 letters: de, uk, at → jurisdiction only
        - 3 letters: pde, cuk → entity + jurisdiction
        - 4 letters: atcr, ukch → jurisdiction + source
        - 5+ letters: lituk, newsde → intent + jurisdiction
        """
        op = context.operator.lower()

        # Try each parsing strategy

        # 1. Single letter entity type
        if len(op) == 1 and op in ENTITY_TYPE_OPERATORS:
            context.entity_type = ENTITY_TYPE_OPERATORS[op]
            return

        # 2. Two letters - could be jurisdiction
        if len(op) == 2 and op in JURISDICTION_CODES:
            context.jurisdiction = op
            return

        # 3. Three letters - entity + jurisdiction (e.g., pde, cuk)
        if len(op) == 3:
            first = op[0]
            rest = op[1:]
            if first in ENTITY_TYPE_OPERATORS and rest in JURISDICTION_CODES:
                context.entity_type = ENTITY_TYPE_OPERATORS[first]
                context.jurisdiction = rest
                return

        # 4. Four letters - jurisdiction + source (e.g., atcr, ukch)
        if len(op) == 4:
            jur = op[:2]
            src = op[2:]
            if jur in JURISDICTION_CODES and src in SOURCE_OPERATORS:
                context.jurisdiction = jur
                context.source_type = SOURCE_OPERATORS[src]
                return
            # Also try reversed: source + jurisdiction
            src = op[:2]
            jur = op[2:]
            if jur in JURISDICTION_CODES and src in SOURCE_OPERATORS:
                context.jurisdiction = jur
                context.source_type = SOURCE_OPERATORS[src]
                return

        # 5. Five+ letters - intent + jurisdiction (e.g., lituk, newsde)
        if len(op) >= 4:
            # Try to find intent prefix
            for intent_prefix, intent_name in INTENT_OPERATORS.items():
                if op.startswith(intent_prefix):
                    jur = op[len(intent_prefix):]
                    if jur in JURISDICTION_CODES or jur in UK_ALIASES:
                        context.intent = intent_name
                        context.jurisdiction = jur
                        return

            # Try intent suffix
            for intent_prefix, intent_name in INTENT_OPERATORS.items():
                if op.endswith(intent_prefix):
                    jur = op[:-len(intent_prefix)]
                    if jur in JURISDICTION_CODES or jur in UK_ALIASES:
                        context.intent = intent_name
                        context.jurisdiction = jur
                        return

        # 6. Fallback - try to extract any known jurisdiction
        for jur in JURISDICTION_CODES:
            if jur in op:
                context.jurisdiction = jur
                remaining = op.replace(jur, "")
                # Check remaining for entity or intent
                if remaining in ENTITY_TYPE_OPERATORS:
                    context.entity_type = ENTITY_TYPE_OPERATORS[remaining]
                elif remaining in SOURCE_OPERATORS:
                    context.source_type = SOURCE_OPERATORS[remaining]
                break

    # ==========================================================================
    # ROUTING
    # ==========================================================================

    def route(self, context: OperatorContext) -> RouteResult:
        """Route to appropriate handler based on context."""
        if context.mode == "intel":
            return self._route_intel(context)
        else:
            return self._route_action(context)

    def _route_intel(self, context: OperatorContext) -> RouteResult:
        """
        Intelligence Mode - Return registry profile without execution.

        Returns:
        - Registry name and URL
        - Wiki wisdom (search tips)
        - Dead ends for this jurisdiction
        - Arbitrage paths
        - Available execution scripts
        """
        result = RouteResult(mode="intel", context=context)

        # Get jurisdiction-specific info
        jur = context.resolved_jurisdiction or context.jurisdiction
        if jur:
            jur_upper = jur.upper()

            # Get sources for jurisdiction
            sources = self.compiler.get_sources_for_jurisdiction(jur_upper)

            # Filter by source_type if specified
            if context.source_type:
                sources = [s for s in sources if s.category == context.source_type]

            result.sources = [s.to_dict() for s in sources]

            # Get wiki wisdom
            result.wiki = self.compiler.get_wiki_for_jurisdiction(jur_upper)

            # Get dead ends
            result.dead_ends = self.compiler.get_dead_ends_for_jurisdiction(jur_upper)

            # Get arbitrage paths
            result.arbitrage = self.compiler.get_arbitrage_paths(jur_upper)

            # Get mined chains for this jurisdiction
            result.mined_chains = self.get_mined_chains(jur_upper, max_results=10)

            # Get registry info if source_type is corporate_registry
            if context.source_type == "corporate_registry" or jur_upper in self._registries:
                reg = self._registries.get(jur_upper, {})
                if reg:
                    result.search_template = reg.get("search_url_template", "")

        return result

    def _route_action(self, context: OperatorContext) -> RouteResult:
        """
        Action Mode - Determine execution path.

        Routes to:
        - Torpedo (scraping with recipes)
        - Corporella (corporate intelligence aggregator)
        - EYE-D (OSINT searches)
        - LINKLATER (archive/domain intel)
        - Direct APIs (Companies House, etc.)
        - Country engines (specific registry adapters)
        """
        result = RouteResult(mode="action", context=context)

        # Find matching rule
        rule = self._find_rule_for_context(context)
        result.rule = rule

        if rule:
            # Determine handler
            result.handler = self._determine_handler(rule, context)
            result.methodology = rule.get("methodology", "")

            # Get fallback chain
            result.fallback_chain = self._get_fallback_chain(rule.get("id", ""))

            # Get search template from rule or registry
            jur = context.resolved_jurisdiction or context.jurisdiction
            if jur:
                reg = self._registries.get(jur.upper(), {})
                result.search_template = rule.get("search_url_template") or reg.get("search_url_template", "")
        else:
            # No specific rule - use generic handler based on entity type
            result.handler = self._get_generic_handler(context)

        return result

    def _find_rule_for_context(self, context: OperatorContext) -> Optional[Dict]:
        """Find a matching rule for the context."""
        jur = (context.resolved_jurisdiction or context.jurisdiction or "").upper()

        # Build potential rule IDs to search
        potential_ids = []

        # Based on entity type
        if context.entity_type == "company":
            potential_ids.extend([
                f"COMPANY_CORE_{jur}",
                f"COMPANY_SEARCH_{jur}",
                f"CORPORATE_REGISTRY_{jur}",
            ])
        elif context.entity_type == "person":
            potential_ids.extend([
                f"PERSON_SEARCH_{jur}",
                f"PERSON_PROFILE_{jur}",
            ])
        elif context.source_type == "corporate_registry":
            potential_ids.extend([
                f"COMPANY_CORE_{jur}",
                f"CORPORATE_REGISTRY_{jur}",
                f"COMPANY_OFFICERS_{jur}",
            ])

        # Based on intent
        if context.intent == "litigation":
            potential_ids.extend([
                f"LITIGATION_{jur}",
                f"COURT_RECORDS_{jur}",
            ])
        elif context.intent == "news":
            potential_ids.extend([
                f"NEWS_SEARCH_{jur}",
                f"MEDIA_{jur}",
            ])

        # Generic fallbacks
        potential_ids.extend([
            f"DEFAULT_{jur}",
            "GLOBAL_SEARCH",
        ])

        # Find first matching rule
        for rule_id in potential_ids:
            if rule_id in self._rules:
                return self._rules[rule_id]

        # Search rules by jurisdiction field
        for rule_id, rule in self._rules.items():
            rule_jur = rule.get("jurisdiction", "").upper()
            if rule_jur == jur:
                # Check if rule matches entity type or intent
                if context.entity_type:
                    if context.entity_type.upper() in rule_id:
                        return rule
                elif context.source_type:
                    if "COMPANY" in rule_id or "CORPORATE" in rule_id:
                        return rule
                else:
                    return rule

        # Fallback: Try to find a mined chain
        if jur and self._mined:
            mined_chain = self.find_mined_chain(
                jurisdiction=jur,
                entity_type=context.entity_type,
                intent=context.intent
            )
            if mined_chain:
                # Convert mined chain to rule-like format
                return {
                    "id": mined_chain.get("id", "MINED_CHAIN"),
                    "jurisdiction": jur,
                    "mined": True,
                    "success_count": mined_chain.get("success_count", 0),
                    "friction": mined_chain.get("friction", "Open"),
                    "methodology": mined_chain.get("category", ""),
                    "resources": mined_chain.get("resources", []),
                    "chain_config": mined_chain.get("chain_config", {}),
                    "original_description": mined_chain.get("original_description", ""),
                }

        return None

    def _determine_handler(self, rule: Dict, context: OperatorContext) -> str:
        """Determine which handler should execute the rule."""
        # Check rule's execution_method
        exec_method = rule.get("execution_method", "")
        if exec_method:
            return exec_method

        # Check resources for handler hints
        resources = rule.get("resources", [])
        for res in resources:
            handler = res.get("handler", "")
            if handler:
                return handler

        # Determine by context
        jur = (context.resolved_jurisdiction or context.jurisdiction or "").upper()

        # Jurisdictions with specialized Country APIs (Primary)
        api_jurs = {"UK", "GB", "DE", "FR", "NL", "CH", "BE", "DK", "NO", "SE", "FI", "IE", "AT", "PL", "CZ", "SK", "US", "CA"}
        if jur in api_jurs and (context.entity_type == "company" or context.source_type == "corporate_registry"):
            return "country_api"

        # Jurisdictions with Torpedo recipes (Secondary/Fallback)
        torpedo_jurs = {"AT", "DE", "CH", "FR", "NL", "BE", "HR", "HU", "PL", "CZ", "SK"}
        if jur in torpedo_jurs:
            return "torpedo"

        # Entity-type handlers
        if context.entity_type == "person":
            return "eye-d"
        elif context.entity_type in ("email", "phone", "username", "linkedin_url", "linkedin_username"):
            return "eye-d"
        elif context.entity_type == "domain":
            return "linklater"

        # Default to corporella for company searches
        if context.entity_type == "company" or context.source_type == "corporate_registry":
            return "corporella"

        return "brute"  # Generic web search

    def _get_fallback_chain(self, rule_id: str) -> List[str]:
        """Get fallback handler chain for a rule."""
        # Default fallback chains by category
        if "COMPANY" in rule_id or "CORPORATE" in rule_id:
            return ["torpedo", "corporella", "opencorporates", "brute"]
        elif "PERSON" in rule_id:
            return ["eye-d", "brute"]
        elif "LITIGATION" in rule_id:
            return ["brute"]
        else:
            return ["brute"]

    def _get_generic_handler(self, context: OperatorContext) -> str:
        """Get generic handler when no specific rule matches."""
        jur = (context.resolved_jurisdiction or context.jurisdiction or "").upper()

        if context.entity_type == "person":
            # Unified Person Search (EYE-D + Corporella + Socialite) handled by IOExecutor
            return "eye-d"
        elif context.entity_type == "company":
            # Specialized Country APIs
            api_jurs = {"UK", "GB", "DE", "FR", "NL", "CH", "BE", "DK", "NO", "SE", "FI", "IE", "AT", "PL", "CZ", "SK", "US", "CA"}
            if jur in api_jurs:
                return "country_api"
            
            # Jurisdictions with Torpedo recipes
            torpedo_jurs = {"AT", "DE", "CH", "FR", "NL", "BE", "HR", "HU", "PL", "CZ", "SK"}
            if jur in torpedo_jurs:
                return "torpedo"
            return "corporella"
        elif context.entity_type in ("email", "phone", "username", "linkedin_url", "linkedin_username"):
            return "eye-d"
        elif context.entity_type == "domain":
            return "linklater"
        else:
            return "brute"

    # ==========================================================================
    # CONVENIENCE METHODS
    # ==========================================================================

    def get_all_operators(self) -> Dict[str, List[str]]:
        """Get all supported operators grouped by category."""
        return {
            "entity_types": list(ENTITY_TYPE_OPERATORS.keys()),
            "intents": list(INTENT_OPERATORS.keys()),
            "source_types": list(SOURCE_OPERATORS.keys()),
            "jurisdictions": list(JURISDICTION_CODES),
        }

    def suggest_operators(self, jurisdiction: str) -> List[str]:
        """Suggest available operators for a jurisdiction."""
        jur = jurisdiction.lower()
        suggestions = []

        # Entity + jurisdiction
        for et in ENTITY_TYPE_OPERATORS.keys():
            suggestions.append(f"{et}{jur}:")

        # Jurisdiction + source
        for st in SOURCE_OPERATORS.keys():
            suggestions.append(f"{jur}{st}:")

        # Intent + jurisdiction
        for intent in INTENT_OPERATORS.keys():
            suggestions.append(f"{intent}{jur}:")

        return suggestions


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for testing IORouter."""
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="IO Router - Parse and route operators")
    parser.add_argument("query", nargs="?", help="Query to parse and route (e.g., 'atcr: Siemens')")
    parser.add_argument("--operators", action="store_true", help="Show all operators")
    parser.add_argument("--suggest", "-s", help="Suggest operators for jurisdiction")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    router = IORouter()

    if args.operators:
        ops = router.get_all_operators()
        if args.json:
            print(json.dumps(ops, indent=2))
        else:
            print("\nSupported Operators:")
            print(f"\nEntity Types: {', '.join(ops['entity_types'])}")
            print(f"Intents: {', '.join(ops['intents'])}")
            print(f"Source Types: {', '.join(ops['source_types'])}")
            print(f"Jurisdictions: {', '.join(sorted(ops['jurisdictions']))}")

    elif args.suggest:
        suggestions = router.suggest_operators(args.suggest)
        if args.json:
            print(json.dumps(suggestions, indent=2))
        else:
            print(f"\nSuggested operators for {args.suggest}:")
            for s in suggestions:
                print(f"  {s}")

    elif args.query:
        # Parse and route
        context = router.parse_operator(args.query)
        route = router.route(context)

        if args.json:
            output = {
                "context": {
                    "raw_query": context.raw_query,
                    "operator": context.operator,
                    "value": context.value,
                    "mode": context.mode,
                    "jurisdiction": context.jurisdiction,
                    "resolved_jurisdiction": context.resolved_jurisdiction,
                    "entity_type": context.entity_type,
                    "intent": context.intent,
                    "source_type": context.source_type,
                },
                "route": {
                    "mode": route.mode,
                    "handler": route.handler,
                    "rule": route.rule.get("id") if route.rule else None,
                    "search_template": route.search_template,
                    "fallback_chain": route.fallback_chain,
                    "sources_count": len(route.sources),
                }
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"Query: {context.raw_query}")
            print(f"{'='*60}")
            print(f"\nParsed Context:")
            print(f"  Operator: {context.operator}")
            print(f"  Value: {context.value}")
            print(f"  Mode: {context.mode}")
            print(f"  Jurisdiction: {context.jurisdiction} -> {context.resolved_jurisdiction}")
            print(f"  Entity Type: {context.entity_type}")
            print(f"  Intent: {context.intent}")
            print(f"  Source Type: {context.source_type}")

            print(f"\nRoute Result:")
            print(f"  Mode: {route.mode}")
            print(f"  Handler: {route.handler}")
            print(f"  Rule: {route.rule.get('id') if route.rule else 'None'}")
            print(f"  Search Template: {route.search_template}")
            print(f"  Fallback Chain: {route.fallback_chain}")

            if route.mode == "intel":
                print(f"\nIntel Mode Results:")
                print(f"  Sources: {len(route.sources)}")
                if route.sources:
                    for s in route.sources[:5]:
                        print(f"    - {s.get('name')} ({s.get('category')})")
                    if len(route.sources) > 5:
                        print(f"    ... and {len(route.sources)-5} more")
                print(f"  Dead Ends: {len(route.dead_ends)}")
                if route.wiki:
                    print(f"  Wiki Sections: {list(route.wiki.get('sections', {}).keys())}")

    else:
        print("Usage: python io_router.py 'atcr: Siemens'")
        print("       python io_router.py --operators")
        print("       python io_router.py --suggest AT")


if __name__ == "__main__":
    main()
