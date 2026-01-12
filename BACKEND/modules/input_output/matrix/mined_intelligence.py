"""
Mined Intelligence Loader - Quick access to 636K+ lines of mined investigation patterns.

This module provides efficient access to:
- Dead ends: Known failing queries by jurisdiction (avoid wasted API calls)
- Arbitrage routes: Cross-jurisdictional information shortcuts
- Methodology patterns: Proven investigation approaches
- Section templates: 4,568 templates by section type
- Writing styles: Voice and attribution patterns

Usage:
    from mined_intelligence import MinedIntelligence

    mi = MinedIntelligence()

    # Check if a query is a dead end before executing
    if mi.is_dead_end("beneficial_ownership", "CH"):
        print("Skip: Swiss UBO not publicly available")

    # Get arbitrage routes for a jurisdiction
    routes = mi.get_arbitrage_routes("CH")  # Get Swiss info via other registries

    # Get methodology for investigation type
    methodology = mi.get_methodology("corporate_structure")
"""

import json
import logging
from pathlib import Path
from functools import lru_cache
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

MINED_DIR = Path(__file__).parent / "mined"
BACKUP_DIR = Path(__file__).parent.parent / "matrix_backup_20251125" / "mined"


@dataclass
class DeadEnd:
    """A known dead-end query pattern."""
    sought: str
    jurisdiction: str
    reason: str
    attempted_sources: List[str]

    def matches(self, query: str, jurisdiction: str) -> bool:
        """Check if this dead end matches the query."""
        query_lower = query.lower()
        sought_lower = self.sought.lower()

        # Exact jurisdiction match required
        if self.jurisdiction not in (jurisdiction, "GLOBAL"):
            return False

        # Check for keyword overlap
        query_keywords = set(query_lower.split())
        sought_keywords = set(sought_lower.split())

        # If >50% of sought keywords appear in query, it's a match
        overlap = query_keywords & sought_keywords
        if len(overlap) >= len(sought_keywords) * 0.5:
            return True

        # Check for key phrases
        key_phrases = [
            ("beneficial owner", "beneficial_ownership"),
            ("ubo", "beneficial_ownership"),
            ("shareholder", "ownership"),
            ("ownership percentage", "ownership"),
            ("criminal record", "criminal"),
            ("litigation", "litigation"),
            ("court record", "litigation"),
        ]

        for phrase, category in key_phrases:
            if phrase in query_lower and phrase in sought_lower:
                return True

        return False


@dataclass
class ArbitrageRoute:
    """A cross-jurisdictional information shortcut."""
    target_jurisdiction: str
    source_jurisdiction: str
    source_registry: str
    info_types: List[str]
    arbitrage_type: str
    explanation: str


class MinedIntelligence:
    """Central access point for all mined investigation intelligence."""

    def __init__(self, mined_dir: Optional[Path] = None):
        self.mined_dir = mined_dir or MINED_DIR
        self.backup_dir = BACKUP_DIR

        # Lazy-loaded caches
        self._dead_ends: Optional[List[DeadEnd]] = None
        self._dead_end_index: Optional[Dict[str, List[DeadEnd]]] = None
        self._arbitrage: Optional[List[ArbitrageRoute]] = None
        self._arbitrage_index: Optional[Dict[str, List[ArbitrageRoute]]] = None
        self._methodology: Optional[Dict] = None
        self._section_templates: Optional[Dict] = None
        self._writing_styles: Optional[Dict] = None
        self._routes: Optional[Dict] = None
        self._jurisdictions: Optional[Dict] = None

    def _load_json(self, filename: str) -> Dict:
        """Load mined JSON file with fallback to backup."""
        live_path = self.mined_dir / filename
        backup_path = self.backup_dir / filename

        if live_path.exists():
            try:
                return json.loads(live_path.read_text())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse {live_path}: {e}")

        if backup_path.exists():
            try:
                return json.loads(backup_path.read_text())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse {backup_path}: {e}")

        logger.warning(f"Mined file not found: {filename}")
        return {}

    # =========================================================================
    # DEAD ENDS - Skip known failing queries
    # =========================================================================

    def _load_dead_ends(self) -> None:
        """Load and index dead ends by jurisdiction."""
        if self._dead_ends is not None:
            return

        data = self._load_json("mined_dead_ends.json")
        raw_dead_ends = data.get("dead_ends", [])

        self._dead_ends = []
        self._dead_end_index = defaultdict(list)

        for de in raw_dead_ends:
            dead_end = DeadEnd(
                sought=de.get("sought", ""),
                jurisdiction=de.get("jurisdiction", ""),
                reason=de.get("reason", ""),
                attempted_sources=de.get("attempted_sources", [])
            )
            self._dead_ends.append(dead_end)
            self._dead_end_index[dead_end.jurisdiction].append(dead_end)

        # Also index under GLOBAL for universal patterns
        logger.info(f"Loaded {len(self._dead_ends)} dead-end patterns")

    def is_dead_end(self, query: str, jurisdiction: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a query is a known dead end for the jurisdiction.

        Returns:
            Tuple of (is_dead_end: bool, reason: Optional[str])
        """
        self._load_dead_ends()

        # Check jurisdiction-specific dead ends
        for de in self._dead_end_index.get(jurisdiction, []):
            if de.matches(query, jurisdiction):
                return True, de.reason

        # Check global dead ends
        for de in self._dead_end_index.get("GLOBAL", []):
            if de.matches(query, jurisdiction):
                return True, de.reason

        return False, None

    def get_dead_ends_for_jurisdiction(self, jurisdiction: str) -> List[DeadEnd]:
        """Get all known dead ends for a jurisdiction."""
        self._load_dead_ends()
        result = self._dead_end_index.get(jurisdiction, []).copy()
        result.extend(self._dead_end_index.get("GLOBAL", []))
        return result

    def get_dead_end_stats(self) -> Dict[str, int]:
        """Get count of dead ends by jurisdiction."""
        self._load_dead_ends()
        return {k: len(v) for k, v in self._dead_end_index.items()}

    # =========================================================================
    # ARBITRAGE - Cross-jurisdictional information routes
    # =========================================================================

    def _load_arbitrage(self) -> None:
        """Load and index arbitrage patterns."""
        if self._arbitrage is not None:
            return

        data = self._load_json("mined_arbitrage.json")
        raw_patterns = data.get("arbitrage_patterns", [])

        self._arbitrage = []
        self._arbitrage_index = defaultdict(list)

        for ap in raw_patterns:
            route = ArbitrageRoute(
                target_jurisdiction=ap.get("target_jurisdiction", ""),
                source_jurisdiction=ap.get("source_jurisdiction", ""),
                source_registry=ap.get("source_registry", ""),
                info_types=ap.get("info_obtained", []),
                arbitrage_type=ap.get("arbitrage_type", ""),
                explanation=ap.get("explanation", "")
            )
            self._arbitrage.append(route)
            self._arbitrage_index[route.target_jurisdiction].append(route)

        logger.info(f"Loaded {len(self._arbitrage)} arbitrage patterns")

    def get_arbitrage_routes(self, target_jurisdiction: str,
                            info_type: Optional[str] = None) -> List[ArbitrageRoute]:
        """
        Get alternative routes to obtain information about entities in target_jurisdiction.

        Args:
            target_jurisdiction: The jurisdiction where the target entity is based
            info_type: Optional filter for type of info needed (e.g., "beneficial_ownership")

        Returns:
            List of ArbitrageRoute objects suggesting alternative sources
        """
        self._load_arbitrage()

        routes = self._arbitrage_index.get(target_jurisdiction, [])

        if info_type:
            info_lower = info_type.lower()
            routes = [r for r in routes
                     if any(info_lower in it.lower() for it in r.info_types)]

        return routes

    def suggest_arbitrage(self, target_jurisdiction: str,
                         query: str) -> List[Dict[str, Any]]:
        """
        Given a failed query in target_jurisdiction, suggest alternative routes.

        Returns list of suggestions with source_jurisdiction, registry, and explanation.
        """
        self._load_arbitrage()

        suggestions = []
        query_lower = query.lower()

        # Keywords to info_type mapping
        keyword_map = {
            "owner": ["ownership", "beneficial", "shareholder"],
            "ubo": ["beneficial", "ownership"],
            "director": ["director", "officer"],
            "address": ["address", "residential"],
            "financial": ["financial", "revenue", "asset"],
        }

        # Determine what info types might be relevant
        relevant_types = set()
        for keyword, types in keyword_map.items():
            if keyword in query_lower:
                relevant_types.update(types)

        routes = self._arbitrage_index.get(target_jurisdiction, [])

        for route in routes:
            # Check if route provides relevant info
            route_info_lower = [it.lower() for it in route.info_types]
            if not relevant_types or any(rt in " ".join(route_info_lower)
                                         for rt in relevant_types):
                suggestions.append({
                    "source_jurisdiction": route.source_jurisdiction,
                    "source_registry": route.source_registry,
                    "info_available": route.info_types,
                    "arbitrage_type": route.arbitrage_type,
                    "explanation": route.explanation,
                    "confidence": "high" if relevant_types else "medium"
                })

        return suggestions

    # =========================================================================
    # METHODOLOGY - Proven investigation approaches
    # =========================================================================

    def _load_methodology(self) -> None:
        """Load methodology patterns."""
        if self._methodology is not None:
            return
        self._methodology = self._load_json("mined_methodology.json")

    def get_methodology(self, investigation_type: str) -> List[Dict]:
        """Get methodology patterns for an investigation type."""
        self._load_methodology()

        patterns = self._methodology.get("methodology_patterns", [])
        type_lower = investigation_type.lower()

        return [p for p in patterns
                if type_lower in p.get("category", "").lower() or
                   type_lower in p.get("description", "").lower()]

    def get_methodology_by_jurisdiction(self, jurisdiction: str) -> List[Dict]:
        """Get methodology patterns that mention a specific jurisdiction."""
        self._load_methodology()

        patterns = self._methodology.get("methodology_patterns", [])
        return [p for p in patterns
                if jurisdiction in p.get("jurisdictions", []) or
                   jurisdiction.lower() in p.get("description", "").lower()]

    # =========================================================================
    # NORMALIZED METHODOLOGY - Maps to IO Matrix codes and modules
    # =========================================================================

    def _load_mappings(self) -> Dict:
        """Load methodology mappings to IO Matrix ontology."""
        return self._load_json("methodology_mappings.json")

    def get_goal_codes(self, investigation_goal: str) -> Dict[str, Any]:
        """
        Get IO Matrix output codes for an investigation goal.

        Returns:
            {
                "output_codes": [67, 72, 73, 74],
                "output_names": ["company_beneficial_owner_name", ...],
                "relationships": ["beneficial_owner_of", "shareholder_of"],
                "keywords": ["beneficial", "owner", ...]
            }
        """
        mappings = self._load_mappings()
        goals = mappings.get("investigation_goals_to_codes", {})
        return goals.get(investigation_goal, {})

    def get_module_for_method(self, method_type: str) -> Optional[str]:
        """
        Get the IO Matrix module for a methodology type.

        Args:
            method_type: e.g., "corporate_registry_search", "humint"

        Returns:
            Module name like "corporella", "eyed", "alldom" or None
        """
        mappings = self._load_mappings()
        methods = mappings.get("methods_to_modules", {})
        method_info = methods.get(method_type, {})
        return method_info.get("module")

    def get_aggregator_for_source(self, source_name: str) -> Optional[str]:
        """
        Normalize a source name to its aggregator domain.

        Args:
            source_name: e.g., "UK land registry", "Companies House"

        Returns:
            Aggregator domain like "landregistry.data.gov.uk"
        """
        mappings = self._load_mappings()
        sources = mappings.get("sources_to_aggregators", {})
        return sources.get(source_name)

    def get_normalized_methodology(self, investigation_goal: str,
                                   jurisdiction: str) -> Dict[str, Any]:
        """
        Get methodology advice normalized to IO Matrix ontology.

        This is the primary method for AI agents - returns actionable guidance
        mapped to our existing codes and modules.

        Returns:
            {
                "goal": "trace_ubo",
                "jurisdiction": "HU",
                "output_codes": [67, 72, 73, 74],
                "relationships": ["beneficial_owner_of", ...],
                "recommended_modules": [
                    {"module": "corporella", "method": "corporate_registry_search", "success_rate": 0.95, "friction": "open"},
                    ...
                ],
                "sources_by_friction": {
                    "open": [{"source": "e-cegjegyzek.hu", "method": "corporate_registry_search", "success_rate": 0.92}],
                    "restricted": [...],
                    "paywalled": [...]
                },
                "avoid_methods": ["court_search", ...],
                "dead_end_count": 182
            }
        """
        self._load_methodology()

        # Get goal mapping
        goal_info = self.get_goal_codes(investigation_goal)

        # Load raw methodology
        methodology_data = self._load_json("mined_methodology.json")
        patterns = methodology_data.get("patterns", [])

        # Filter by jurisdiction
        jur_patterns = [p for p in patterns if p.get("jurisdiction") == jurisdiction]

        # Group by method and calculate success rates
        method_stats = {}
        for p in jur_patterns:
            method = p.get("method", "unknown")
            if method not in method_stats:
                method_stats[method] = {"success": 0, "fail": 0, "sources": [], "friction": set()}

            if p.get("success"):
                method_stats[method]["success"] += 1
            else:
                method_stats[method]["fail"] += 1

            source = p.get("source_used", "")
            friction = p.get("friction", "unknown")
            if source:
                method_stats[method]["sources"].append(source)
                method_stats[method]["friction"].add(friction)

        # Build recommended modules list
        recommended_modules = []
        for method, stats in method_stats.items():
            total = stats["success"] + stats["fail"]
            if total == 0:
                continue

            success_rate = stats["success"] / total
            module = self.get_module_for_method(method)

            # Determine primary friction level
            frictions = stats["friction"]
            if "open" in frictions:
                primary_friction = "open"
            elif "restricted" in frictions:
                primary_friction = "restricted"
            elif "paywalled" in frictions:
                primary_friction = "paywalled"
            else:
                primary_friction = "unknown"

            recommended_modules.append({
                "module": module,
                "method": method,
                "success_rate": round(success_rate, 2),
                "sample_size": total,
                "friction": primary_friction,
                "sources": list(set(stats["sources"]))[:5]
            })

        # Sort by success rate
        recommended_modules.sort(key=lambda x: -x["success_rate"])

        # Group sources by friction
        sources_by_friction = {"open": [], "restricted": [], "paywalled": [], "impossible": []}
        for p in jur_patterns:
            if p.get("success"):
                friction = p.get("friction", "unknown")
                if friction in sources_by_friction:
                    source = p.get("source_used", "")
                    method = p.get("method", "")
                    if source:
                        # Normalize source to aggregator
                        aggregator = self.get_aggregator_for_source(source) or source
                        sources_by_friction[friction].append({
                            "source": aggregator,
                            "original_name": source,
                            "method": method
                        })

        # Deduplicate sources
        for friction in sources_by_friction:
            seen = set()
            unique = []
            for s in sources_by_friction[friction]:
                if s["source"] not in seen:
                    seen.add(s["source"])
                    unique.append(s)
            sources_by_friction[friction] = unique[:10]

        # Identify methods to avoid (low success rate)
        avoid_methods = [
            method for method, stats in method_stats.items()
            if stats["fail"] > 5 and stats["success"] / max(1, stats["success"] + stats["fail"]) < 0.5
        ]

        # Get dead end count
        dead_ends = self.get_dead_ends_for_jurisdiction(jurisdiction)

        return {
            "goal": investigation_goal,
            "jurisdiction": jurisdiction,
            "output_codes": goal_info.get("output_codes", []),
            "output_names": goal_info.get("output_names", []),
            "relationships": goal_info.get("relationships", []),
            "recommended_modules": recommended_modules[:8],
            "sources_by_friction": sources_by_friction,
            "avoid_methods": avoid_methods,
            "dead_end_count": len(dead_ends)
        }

    # =========================================================================
    # SECTION TEMPLATES - Pre-built section structures
    # =========================================================================

    def _load_section_templates(self) -> None:
        """Load section templates."""
        if self._section_templates is not None:
            return
        self._section_templates = self._load_json("mined_section_templates.json")

    def get_section_template(self, section_type: str,
                            jurisdiction: Optional[str] = None) -> Optional[Dict]:
        """
        Get a template for a specific section type.

        Args:
            section_type: e.g., "corporate_structure", "biographical", "litigation"
            jurisdiction: Optional filter for jurisdiction-specific templates
        """
        self._load_section_templates()

        templates = self._section_templates.get("templates", [])
        type_lower = section_type.lower()

        matches = [t for t in templates if t.get("type", "").lower() == type_lower]

        if jurisdiction and matches:
            # Prefer jurisdiction-specific templates
            jurisdiction_matches = [m for m in matches
                                   if jurisdiction in m.get("jurisdictions", [])]
            if jurisdiction_matches:
                return jurisdiction_matches[0]

        return matches[0] if matches else None

    def get_section_types(self) -> List[str]:
        """Get all available section types."""
        self._load_section_templates()
        templates = self._section_templates.get("templates", [])
        return list(set(t.get("type", "") for t in templates))

    # =========================================================================
    # WRITING STYLES - Voice and attribution patterns
    # =========================================================================

    def _load_writing_styles(self) -> None:
        """Load writing style patterns."""
        if self._writing_styles is not None:
            return
        self._writing_styles = self._load_json("mined_writing_styles.json")

    def get_writing_style(self, voice: str = "third_person_professional",
                         attribution: str = "footnoted") -> Optional[Dict]:
        """Get a writing style example matching the requested voice and attribution."""
        self._load_writing_styles()

        styles = self._writing_styles.get("styles", [])

        for style in styles:
            if (style.get("voice", "").lower() == voice.lower() and
                style.get("attribution", "").lower() == attribution.lower()):
                return style

        # Fallback: return any style with matching voice
        for style in styles:
            if style.get("voice", "").lower() == voice.lower():
                return style

        return styles[0] if styles else None

    # =========================================================================
    # GENERATED CHAINS - Executable chain definitions from mined patterns
    # =========================================================================

    def _load_chains(self) -> None:
        """Load generated chains from mined methodology."""
        if not hasattr(self, '_chains') or self._chains is None:
            data = self._load_json("generated_chains.json")
            self._chains = data.get("automatable_chains", [])
            self._manual_tasks = data.get("manual_tasks", [])
            self._chain_stats = data.get("statistics", {})

            # Build indexes
            self._chains_by_id = {c["id"]: c for c in self._chains}
            self._chains_by_jurisdiction = defaultdict(list)
            self._chains_by_category = defaultdict(list)

            for chain in self._chains:
                self._chains_by_jurisdiction[chain.get("jurisdiction", "GLOBAL")].append(chain)
                self._chains_by_category[chain.get("category", "")].append(chain)

            logger.info(f"Loaded {len(self._chains)} generated chains, {len(self._manual_tasks)} manual tasks")

    def get_chain_by_id(self, chain_id: str) -> Optional[Dict]:
        """Get a specific chain by its ID."""
        self._load_chains()
        return self._chains_by_id.get(chain_id)

    def get_chains_for_jurisdiction(self, jurisdiction: str,
                                    friction_filter: Optional[str] = None) -> List[Dict]:
        """
        Get all chains available for a jurisdiction.

        Args:
            jurisdiction: ISO country code (e.g., "CH", "HU", "GB")
            friction_filter: Optional filter by friction level ("Open", "Restricted", "Paywalled")

        Returns:
            List of chain definitions sorted by success_count
        """
        self._load_chains()

        chains = self._chains_by_jurisdiction.get(jurisdiction, [])

        if friction_filter:
            chains = [c for c in chains if c.get("friction", "").lower() == friction_filter.lower()]

        # Sort by success count descending
        return sorted(chains, key=lambda c: -c.get("success_count", 0))

    def get_chains_for_goal(self, investigation_goal: str,
                           jurisdiction: Optional[str] = None) -> List[Dict]:
        """
        Get chains relevant to an investigation goal.

        Args:
            investigation_goal: e.g., "trace_ubo", "corporate_structure", "find_assets"
            jurisdiction: Optional filter by jurisdiction

        Returns:
            List of chain definitions sorted by success_count
        """
        self._load_chains()

        chains = self._chains_by_category.get(investigation_goal, [])

        if jurisdiction:
            chains = [c for c in chains if c.get("jurisdiction") == jurisdiction]

        return sorted(chains, key=lambda c: -c.get("success_count", 0))

    def find_chains(self, input_codes: Optional[List[int]] = None,
                   output_codes: Optional[List[int]] = None,
                   jurisdiction: Optional[str] = None,
                   goal: Optional[str] = None,
                   max_friction: Optional[str] = None) -> List[Dict]:
        """
        Find chains matching multiple criteria.

        Args:
            input_codes: Codes you have (chain must accept any of these)
            output_codes: Codes you want (chain must return any of these)
            jurisdiction: Filter by jurisdiction
            goal: Filter by investigation goal
            max_friction: Maximum friction level ("Open", "Restricted", "Paywalled")

        Returns:
            List of matching chains sorted by relevance
        """
        self._load_chains()

        friction_order = {"open": 1, "restricted": 2, "paywalled": 3}
        max_friction_level = friction_order.get(max_friction.lower() if max_friction else "paywalled", 3)

        results = []
        for chain in self._chains:
            # Jurisdiction filter
            if jurisdiction and chain.get("jurisdiction") != jurisdiction:
                continue

            # Goal filter
            if goal and chain.get("category") != goal:
                continue

            # Friction filter
            chain_friction = friction_order.get(chain.get("friction", "").lower(), 3)
            if chain_friction > max_friction_level:
                continue

            # Input codes filter (chain must accept at least one of our input codes)
            if input_codes:
                chain_inputs = set(chain.get("requires_any", []))
                if not chain_inputs.intersection(input_codes):
                    continue

            # Output codes filter (chain must return at least one desired output)
            if output_codes:
                chain_outputs = set(chain.get("returns", []))
                if not chain_outputs.intersection(output_codes):
                    continue

            # Calculate relevance score
            score = chain.get("success_count", 0)
            if output_codes:
                # Bonus for chains that return more of what we want
                overlap = len(set(chain.get("returns", [])).intersection(output_codes))
                score += overlap * 10
            if chain_friction == 1:  # Open sources preferred
                score += 5

            results.append((score, chain))

        # Sort by score descending
        results.sort(key=lambda x: -x[0])
        return [chain for _, chain in results]

    def get_manual_tasks(self, jurisdiction: Optional[str] = None) -> List[Dict]:
        """
        Get manual (non-automatable) task definitions.

        These require human intervention (HUMINT, surveillance, etc.)
        """
        self._load_chains()

        tasks = self._manual_tasks

        if jurisdiction:
            tasks = [t for t in tasks if t.get("jurisdiction") == jurisdiction]

        return tasks

    def get_chain_stats(self) -> Dict[str, Any]:
        """Get statistics about generated chains."""
        self._load_chains()
        return self._chain_stats

    def get_best_chain(self, goal: str, jurisdiction: str,
                      prefer_open: bool = True) -> Optional[Dict]:
        """
        Get the single best chain for a goal/jurisdiction combination.

        Args:
            goal: Investigation goal (e.g., "trace_ubo")
            jurisdiction: Target jurisdiction
            prefer_open: If True, prefer Open friction sources

        Returns:
            Best matching chain or None
        """
        chains = self.find_chains(goal=goal, jurisdiction=jurisdiction)

        if not chains:
            return None

        if prefer_open:
            open_chains = [c for c in chains if c.get("friction", "").lower() == "open"]
            if open_chains:
                return open_chains[0]

        return chains[0]

    # =========================================================================
    # ROUTES - Known working data routes
    # =========================================================================

    def _load_routes(self) -> None:
        """Load route patterns."""
        if self._routes is not None:
            return
        self._routes = self._load_json("mined_routes.json")

    def get_routes_for_input(self, input_type: str) -> List[Dict]:
        """Get routes that accept a specific input type."""
        self._load_routes()

        routes = self._routes.get("routes", [])
        return [r for r in routes if input_type in r.get("inputs", [])]

    def get_routes_for_output(self, output_type: str) -> List[Dict]:
        """Get routes that produce a specific output type."""
        self._load_routes()

        routes = self._routes.get("routes", [])
        return [r for r in routes if output_type in r.get("outputs", [])]

    # =========================================================================
    # JURISDICTIONS - Known jurisdiction characteristics
    # =========================================================================

    def _load_jurisdictions(self) -> None:
        """Load jurisdiction metadata."""
        if self._jurisdictions is not None:
            return
        self._jurisdictions = self._load_json("mined_jurisdictions.json")

    def get_jurisdiction_info(self, jurisdiction: str) -> Optional[Dict]:
        """Get known characteristics of a jurisdiction."""
        self._load_jurisdictions()

        jurisdictions = self._jurisdictions.get("jurisdictions", {})
        return jurisdictions.get(jurisdiction)

    def get_opaque_jurisdictions(self) -> List[str]:
        """Get list of jurisdictions known to be opaque/limited disclosure."""
        self._load_jurisdictions()

        jurisdictions = self._jurisdictions.get("jurisdictions", {})
        return [code for code, info in jurisdictions.items()
                if info.get("transparency", "medium") == "low"]

    # =========================================================================
    # COMBINED INTELLIGENCE - Pre-action advice
    # =========================================================================

    def advise_before_action(self, action_id: str, entity: str,
                            jurisdiction: str) -> Dict[str, Any]:
        """
        Get comprehensive advice before executing an action.

        Returns:
            Dict with:
            - proceed: bool - whether to proceed
            - dead_end: Optional reason if it's a dead end
            - alternatives: List of arbitrage alternatives
            - methodology: Relevant methodology patterns
            - estimated_success: low/medium/high
        """
        advice = {
            "proceed": True,
            "dead_end_reason": None,
            "alternatives": [],
            "methodology": [],
            "estimated_success": "medium"
        }

        # Check for dead ends
        is_dead, reason = self.is_dead_end(action_id, jurisdiction)
        if is_dead:
            advice["proceed"] = False
            advice["dead_end_reason"] = reason
            advice["estimated_success"] = "low"

            # Suggest alternatives via arbitrage
            advice["alternatives"] = self.suggest_arbitrage(jurisdiction, action_id)
            if advice["alternatives"]:
                advice["proceed"] = True  # Proceed via alternative route
                advice["estimated_success"] = "medium"

        # Get relevant methodology
        advice["methodology"] = self.get_methodology(action_id)[:3]  # Top 3

        return advice


# Singleton instance for easy import
_instance: Optional[MinedIntelligence] = None

def get_mined_intelligence() -> MinedIntelligence:
    """Get the singleton MinedIntelligence instance."""
    global _instance
    if _instance is None:
        _instance = MinedIntelligence()
    return _instance


# Convenience functions for quick access
def is_dead_end(query: str, jurisdiction: str) -> Tuple[bool, Optional[str]]:
    """Quick check if query is a dead end."""
    return get_mined_intelligence().is_dead_end(query, jurisdiction)

def get_arbitrage(target_jurisdiction: str) -> List[ArbitrageRoute]:
    """Quick access to arbitrage routes."""
    return get_mined_intelligence().get_arbitrage_routes(target_jurisdiction)

def advise(action_id: str, entity: str, jurisdiction: str) -> Dict[str, Any]:
    """Quick pre-action advice."""
    return get_mined_intelligence().advise_before_action(action_id, entity, jurisdiction)


# Chain convenience functions
def find_chains(input_codes: Optional[List[int]] = None,
               output_codes: Optional[List[int]] = None,
               jurisdiction: Optional[str] = None,
               goal: Optional[str] = None,
               max_friction: Optional[str] = None) -> List[Dict]:
    """Quick chain finder with multiple filters."""
    return get_mined_intelligence().find_chains(
        input_codes=input_codes,
        output_codes=output_codes,
        jurisdiction=jurisdiction,
        goal=goal,
        max_friction=max_friction
    )


def get_best_chain(goal: str, jurisdiction: str) -> Optional[Dict]:
    """Get the single best chain for a goal/jurisdiction."""
    return get_mined_intelligence().get_best_chain(goal, jurisdiction)


def get_chains_for_codes(have_codes: List[int], want_codes: List[int],
                        jurisdiction: Optional[str] = None) -> List[Dict]:
    """
    Find chains that transform what you HAVE into what you WANT.

    Example:
        # I have company_name (13), I want beneficial_owner (67)
        chains = get_chains_for_codes([13], [67], "CH")
    """
    return get_mined_intelligence().find_chains(
        input_codes=have_codes,
        output_codes=want_codes,
        jurisdiction=jurisdiction
    )
