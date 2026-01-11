"""
InvestigationPlanner - Connects IO Matrix, SASTRE Query Compiler, and Slot System.

This module integrates:
1. IO Matrix (flows.json, chain_mappings.json) - Jurisdiction-specific source routes
2. SASTRE Query Compiler - Intent translation, variators, K-U quadrant
3. query_lab concepts - Tier system, strength scoring
4. Slot System - Track what's found/hungry/contested

The planner generates multi-step investigation plans per jurisdiction.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

from .contracts import (
    KUQuadrant, Intent, Gap, Collision,
    SlotState, SlotPriority, EntitySlot, EntitySlotSet,
    create_slots_for_entity, derive_quadrant,
    SufficiencyResult
)

# Import Tactical Layer (Spear/Trap/Net)
from .tactical import (
    TacticType, TacticResult, TacticalSelector,
    select_tactic, generate_tactical_queries,
)

# Import SASTRE's existing variators and translator
from .query.variations import VariationGenerator, expand_free_ors
from .syntax.translator import IntentTranslator, TranslatedQuery, QueryIntentType


# =============================================================================
# Query Tier System (from query_lab)
# =============================================================================

class QueryTier(Enum):
    """Query precision/recall tiers from query_lab."""
    T0A = "0A"  # Mandatory solo - high precision
    T0B = "0B"  # Optional solo
    T1 = "1"    # Minimal combo
    T2 = "2"    # T1 + WHERE/operators
    T3 = "3"    # Phrase/proximity - high recall
    M = "M"     # Multi-concept merge


@dataclass
class PlanStep:
    """A single step in the investigation plan."""
    step_id: str
    description: str
    input_type: str
    input_value: str
    source_id: str
    source_label: str
    country: str
    output_columns: List[str]
    reliability: str
    ku_quadrant: str
    tier: QueryTier = QueryTier.T1
    strength: int = 3  # 1-5 scoring
    friction: str = "open"  # open, gated, licensed
    notes: str = ""
    depends_on: List[str] = field(default_factory=list)
    feeds_slots: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "input_type": self.input_type,
            "input_value": self.input_value,
            "source_id": self.source_id,
            "source_label": self.source_label,
            "country": self.country,
            "output_columns": self.output_columns,
            "reliability": self.reliability,
            "ku_quadrant": self.ku_quadrant,
            "tier": self.tier.value,
            "strength": self.strength,
            "friction": self.friction,
            "notes": self.notes,
            "depends_on": self.depends_on,
            "feeds_slots": self.feeds_slots,
        }


@dataclass
class InvestigationPlan:
    """Complete investigation plan for an entity."""
    entity_id: str
    entity_type: str
    entity_name: str
    jurisdiction: str
    ku_quadrant: KUQuadrant
    tactic: TacticType = TacticType.TRAP  # Default to TRAP (balanced)
    steps: List[PlanStep] = field(default_factory=list)
    slot_set: Optional[EntitySlotSet] = None
    chains: List[Dict[str, Any]] = field(default_factory=list)
    estimated_completeness: float = 0.0
    tactic_rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "jurisdiction": self.jurisdiction,
            "ku_quadrant": self.ku_quadrant.value,
            "tactic": self.tactic.value,
            "tactic_rationale": self.tactic_rationale,
            "steps": [s.to_dict() for s in self.steps],
            "chains": self.chains,
            "estimated_completeness": self.estimated_completeness,
            "total_steps": len(self.steps),
        }


# =============================================================================
# IO Matrix Loader
# =============================================================================

class IOMatrixLoader:
    """Loads and queries the IO Matrix files."""

    def __init__(self, matrix_dir: Optional[Path] = None):
        if matrix_dir is None:
            # Default to input_output2/matrix relative to project root
            self.matrix_dir = Path(__file__).parent.parent.parent.parent / "input_output2" / "matrix"
        else:
            self.matrix_dir = Path(matrix_dir)

        self._flows: Dict[str, List[Dict]] = {}
        self._chains: Dict[str, Any] = {}
        self._jurisdiction_intel: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all matrix files."""
        if self._loaded:
            return

        # Load flows.json (jurisdiction -> source routes)
        flows_path = self.matrix_dir / "flows.json"
        if flows_path.exists():
            with open(flows_path, 'r') as f:
                self._flows = json.load(f)

        # Load chain_mappings.json (output -> input mappings)
        chains_path = self.matrix_dir / "chain_mappings.json"
        if chains_path.exists():
            with open(chains_path, 'r') as f:
                self._chains = json.load(f)

        # Load jurisdiction_intel.json (country-specific capabilities)
        intel_path = self.matrix_dir / "jurisdiction_intel.json"
        if intel_path.exists():
            with open(intel_path, 'r') as f:
                self._jurisdiction_intel = json.load(f)

        self._loaded = True

    def get_routes_for_country(self, country_code: str) -> List[Dict]:
        """Get all source routes for a country."""
        self.load()
        return self._flows.get(country_code.upper(), [])

    def get_routes_by_input_type(self, country_code: str, input_type: str) -> List[Dict]:
        """Get routes for a specific input type in a country."""
        routes = self.get_routes_for_country(country_code)
        return [r for r in routes if r.get("input_type") == input_type]

    def get_chain_mappings(self, output_code: int) -> List[Dict]:
        """Get chain mappings for a given output code."""
        self.load()
        mappings = self._chains.get("entity_to_search_mappings", {}).get("mappings", [])
        return [m for m in mappings if m.get("output_code") == output_code]

    def get_jurisdiction_intel(self, country_code: str) -> Dict:
        """Get intelligence about a jurisdiction's data availability."""
        self.load()
        return self._jurisdiction_intel.get(country_code.upper(), {})


# =============================================================================
# Variator Strength Scorer (from query_lab concepts)
# =============================================================================

class StrengthScorer:
    """Assigns strength scores (1-5) to query variations."""

    # Strength scoring based on query_lab's 12-step process
    SCORING_RULES = {
        # 5: ≥70% prevalence, low ambiguity
        "exact_match": 5,
        "official_registry": 5,
        "unique_identifier": 5,

        # 4: 40-70% prevalence
        "standard_variation": 4,
        "common_abbreviation": 4,

        # 3: 20-40% prevalence
        "alternative_spelling": 3,
        "translation": 3,

        # 2: 5-20% prevalence
        "nickname": 2,
        "informal": 2,

        # 1: <5% prevalence, high noise
        "rare_variation": 1,
        "speculative": 1,
    }

    @classmethod
    def score_variation(cls, variation_type: str, source_reliability: str) -> int:
        """Score a variation based on type and source reliability."""
        base_score = cls.SCORING_RULES.get(variation_type, 3)

        # Adjust based on source reliability
        reliability_modifier = {
            "high": 1,
            "medium": 0,
            "low": -1,
        }
        modifier = reliability_modifier.get(source_reliability, 0)

        return max(1, min(5, base_score + modifier))


# =============================================================================
# Investigation Planner
# =============================================================================

class InvestigationPlanner:
    """
    Plans multi-step investigations using IO Matrix and SASTRE concepts.

    Usage:
        planner = InvestigationPlanner()
        plan = planner.create_plan(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="AE",
            known_data={"email": "john@example.com"}
        )
    """

    def __init__(self, matrix_dir: Optional[Path] = None):
        self.matrix = IOMatrixLoader(matrix_dir)
        self.scorer = StrengthScorer()

    def create_plan(
        self,
        entity_type: str,
        entity_name: str,
        jurisdiction: str,
        known_data: Optional[Dict[str, Any]] = None,
        intent: Optional[Intent] = None,
    ) -> InvestigationPlan:
        """
        Create an investigation plan for an entity.

        Args:
            entity_type: "person", "company", or "domain"
            entity_name: Name of the entity to investigate
            jurisdiction: 2-letter country code
            known_data: Already known data points
            intent: Investigation intent (optional)

        Returns:
            InvestigationPlan with ordered steps
        """
        known_data = known_data or {}
        entity_id = f"{entity_type}_{hash(entity_name) % 10000:04d}"

        # Create slot set for tracking
        slot_set = create_slots_for_entity(entity_id, entity_type)

        # Pre-fill known data into slots
        for field_name, value in known_data.items():
            if field_name in slot_set.slots:
                slot_set.slots[field_name].feed(value, "initial_input")

        # Derive K-U quadrant
        subject_known = len(known_data) > 0
        location_known = bool(jurisdiction and jurisdiction != "UNKNOWN")
        ku_quadrant = derive_quadrant(subject_known, location_known)

        # Select tactical approach (Spear/Trap/Net)
        tactical_result = generate_tactical_queries(
            ku_quadrant=ku_quadrant,
            target=entity_name,
            entity_type=entity_type,
            jurisdiction=jurisdiction,
            slots=slot_set,
            known_sources=list(self.matrix.get_routes_for_country(jurisdiction)[:5]),
        )
        selected_tactic = tactical_result.tactic
        tactic_rationale = tactical_result.rationale

        # Get available routes for jurisdiction
        routes = self.matrix.get_routes_for_country(jurisdiction)

        # Build steps based on what's known and what slots are hungry
        steps = self._build_steps(
            entity_type=entity_type,
            entity_name=entity_name,
            jurisdiction=jurisdiction,
            known_data=known_data,
            routes=routes,
            slot_set=slot_set,
            ku_quadrant=ku_quadrant,
        )

        # Calculate chains (how outputs feed into next inputs)
        chains = self._calculate_chains(steps)

        # Estimate completeness
        estimated_completeness = self._estimate_completeness(steps, slot_set)

        return InvestigationPlan(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_name=entity_name,
            jurisdiction=jurisdiction,
            ku_quadrant=ku_quadrant,
            tactic=selected_tactic,
            tactic_rationale=tactic_rationale,
            steps=steps,
            slot_set=slot_set,
            chains=chains,
            estimated_completeness=estimated_completeness,
        )

    def _build_steps(
        self,
        entity_type: str,
        entity_name: str,
        jurisdiction: str,
        known_data: Dict[str, Any],
        routes: List[Dict],
        slot_set: EntitySlotSet,
        ku_quadrant: KUQuadrant,
    ) -> List[PlanStep]:
        """Build ordered plan steps based on available routes."""
        steps = []
        step_counter = 0

        # Map entity type to input types
        input_type_map = {
            "person": ["person_name", "email_address", "phone_number"],
            "company": ["company_name", "company_reg_id", "company_tax_id"],
            "domain": ["domain_name", "url"],
        }

        relevant_input_types = input_type_map.get(entity_type, ["person_name"])

        # Priority queue: Critical slots first
        hungry_slots = slot_set.get_hungry_slots()
        priority_fields = [s.field_name for s in hungry_slots if s.priority == SlotPriority.CRITICAL]

        # Phase 1: Direct searches with known data
        for input_type in relevant_input_types:
            # Find routes that accept this input type
            matching_routes = [r for r in routes if r.get("input_type") == input_type]

            # Determine input value
            input_value = self._get_input_value(input_type, entity_name, known_data)
            if not input_value:
                continue

            for route in matching_routes:
                step_counter += 1
                output_cols = route.get("output_columns_array", [])

                # Determine which slots this feeds
                feeds_slots = [col for col in output_cols if col in slot_set.slots]

                # Score the step
                reliability = route.get("reliability", "medium")
                strength = self.scorer.score_variation("standard_variation", reliability)

                # Assign tier based on strength and input type
                tier = self._assign_tier(strength, input_type, len(matching_routes))

                step = PlanStep(
                    step_id=f"step_{step_counter:03d}",
                    description=f"Query {route.get('source_label', 'source')} with {input_type}",
                    input_type=input_type,
                    input_value=input_value,
                    source_id=route.get("source_id", "unknown"),
                    source_label=route.get("source_label", "Unknown Source"),
                    country=jurisdiction,
                    output_columns=output_cols,
                    reliability=reliability,
                    ku_quadrant=ku_quadrant.value,
                    tier=tier,
                    strength=strength,
                    friction=route.get("friction", "open"),
                    notes=route.get("notes", ""),
                    feeds_slots=feeds_slots,
                )
                steps.append(step)

        # Phase 2: Chain searches (output becomes input)
        # This creates dependencies between steps
        for i, step in enumerate(steps):
            # Check if any output can feed another input
            for output_col in step.output_columns:
                chain_input_type = self._output_to_input_type(output_col)
                if chain_input_type:
                    # Find routes that can use this chained input
                    chain_routes = [r for r in routes if r.get("input_type") == chain_input_type]
                    for route in chain_routes[:2]:  # Limit chain expansion
                        step_counter += 1
                        chain_step = PlanStep(
                            step_id=f"step_{step_counter:03d}",
                            description=f"Chain: {output_col} → {route.get('source_label', 'source')}",
                            input_type=chain_input_type,
                            input_value=f"[from {step.step_id}.{output_col}]",
                            source_id=route.get("source_id", "unknown"),
                            source_label=route.get("source_label", "Unknown Source"),
                            country=jurisdiction,
                            output_columns=route.get("output_columns_array", []),
                            reliability=route.get("reliability", "medium"),
                            ku_quadrant=ku_quadrant.value,
                            tier=QueryTier.T2,  # Chained queries are T2
                            strength=3,
                            friction=route.get("friction", "open"),
                            notes=f"Chained from {step.step_id}",
                            depends_on=[step.step_id],
                            feeds_slots=[],
                        )
                        steps.append(chain_step)

        # Sort by tier (T0A first) then by strength (highest first)
        tier_order = {"0A": 0, "0B": 1, "1": 2, "2": 3, "3": 4, "M": 5}
        steps.sort(key=lambda s: (tier_order.get(s.tier.value, 99), -s.strength))

        return steps

    def _get_input_value(
        self,
        input_type: str,
        entity_name: str,
        known_data: Dict[str, Any]
    ) -> Optional[str]:
        """Get the input value for a given input type."""
        # Map input types to known data fields
        field_map = {
            "person_name": ["name", "full_name", "person_name"],
            "company_name": ["name", "company_name", "business_name"],
            "email_address": ["email", "email_address"],
            "phone_number": ["phone", "phone_number", "mobile"],
            "domain_name": ["domain", "website"],
            "company_reg_id": ["registration_number", "reg_id", "company_number"],
            "company_tax_id": ["tax_id", "vat_number", "ein"],
        }

        # Check known data first
        for field in field_map.get(input_type, []):
            if field in known_data:
                return str(known_data[field])

        # Fall back to entity name for name-type inputs
        if input_type in ["person_name", "company_name"]:
            return entity_name

        return None

    def _assign_tier(self, strength: int, input_type: str, route_count: int) -> QueryTier:
        """Assign a query tier based on strength and context."""
        if strength >= 5:
            return QueryTier.T0A  # High precision mandatory
        elif strength >= 4:
            return QueryTier.T0B  # Optional high precision
        elif strength >= 3:
            return QueryTier.T1   # Minimal combo
        elif route_count > 5:
            return QueryTier.T2   # Many routes = broader search
        else:
            return QueryTier.T3   # Low strength = proximity/phrase

    def _output_to_input_type(self, output_column: str) -> Optional[str]:
        """Map output columns to input types for chaining."""
        chain_map = {
            "email_addresses": "email_address",
            "extracted_emails": "email_address",
            "phone_numbers": "phone_number",
            "extracted_phones": "phone_number",
            "associated_companies": "company_name",
            "extracted_companies": "company_name",
            "associated_persons": "person_name",
            "extracted_persons": "person_name",
            "domains": "domain_name",
            "registrant_details": "person_name",
        }
        return chain_map.get(output_column)

    def _calculate_chains(self, steps: List[PlanStep]) -> List[Dict[str, Any]]:
        """Calculate execution chains between steps."""
        chains = []

        for step in steps:
            if step.depends_on:
                for dep in step.depends_on:
                    chains.append({
                        "from_step": dep,
                        "to_step": step.step_id,
                        "chain_type": "output_to_input",
                        "description": f"{dep} outputs feed into {step.step_id}",
                    })

        return chains

    def _estimate_completeness(
        self,
        steps: List[PlanStep],
        slot_set: EntitySlotSet
    ) -> float:
        """Estimate how complete the investigation will be after all steps."""
        if not steps:
            return 0.0

        # Count unique slots that will be fed
        slots_to_feed = set()
        for step in steps:
            slots_to_feed.update(step.feeds_slots)

        total_slots = len(slot_set.slots)
        if total_slots == 0:
            return 1.0

        # Estimate based on slots covered
        return min(1.0, len(slots_to_feed) / total_slots)

    def check_sufficiency(self, plan: InvestigationPlan) -> SufficiencyResult:
        """Check if the plan would satisfy investigation requirements."""
        if not plan.slot_set:
            return SufficiencyResult()

        # Check core fields
        critical_slots = [s for s in plan.slot_set.slots.values()
                        if s.priority == SlotPriority.CRITICAL]
        core_fields_populated = all(s.state != SlotState.EMPTY for s in critical_slots)

        # Check high-weight absences
        hungry_high = [s for s in plan.slot_set.get_hungry_slots()
                      if s.priority in [SlotPriority.CRITICAL, SlotPriority.HIGH]]
        no_high_weight_absences = len(hungry_high) == 0

        return SufficiencyResult(
            core_fields_populated=core_fields_populated,
            tasking_headers_addressed=len(plan.steps) > 0,
            no_high_weight_absences=no_high_weight_absences,
            disambiguation_resolved=True,  # Assume no collisions in planning
            surprising_ands_processed=True,  # No surprising connections yet
        )


# =============================================================================
# Helper Functions
# =============================================================================

def plan_investigation(
    entity_type: str,
    entity_name: str,
    jurisdiction: str,
    known_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to plan an investigation.

    Example:
        plan = plan_investigation(
            entity_type="person",
            entity_name="John Smith",
            jurisdiction="AE",
            known_data={"email": "john@example.com"}
        )
    """
    planner = InvestigationPlanner()
    plan = planner.create_plan(
        entity_type=entity_type,
        entity_name=entity_name,
        jurisdiction=jurisdiction,
        known_data=known_data,
    )
    return plan.to_dict()


def get_available_routes(jurisdiction: str) -> List[Dict]:
    """Get all available routes for a jurisdiction."""
    loader = IOMatrixLoader()
    return loader.get_routes_for_country(jurisdiction)


def get_route_summary(jurisdiction: str) -> Dict[str, Any]:
    """Get a summary of available routes for a jurisdiction."""
    routes = get_available_routes(jurisdiction)

    # Group by input type
    by_input_type = {}
    for route in routes:
        input_type = route.get("input_type", "unknown")
        if input_type not in by_input_type:
            by_input_type[input_type] = []
        by_input_type[input_type].append(route.get("source_label", "Unknown"))

    return {
        "jurisdiction": jurisdiction,
        "total_routes": len(routes),
        "by_input_type": {k: len(v) for k, v in by_input_type.items()},
        "sources_by_input": by_input_type,
    }


# =============================================================================
# Query Generation with Variations
# =============================================================================

@dataclass
class GeneratedQuery:
    """A generated query with variations and metadata."""
    primary: str
    variations: List[str]
    tier: QueryTier
    strength: int
    entity_type: str
    intent: str
    free_ors: str  # Expanded OR query

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary": self.primary,
            "variations": self.variations,
            "tier": self.tier.value,
            "strength": self.strength,
            "entity_type": self.entity_type,
            "intent": self.intent,
            "free_ors": self.free_ors,
        }


class QueryGenerator:
    """
    Generates queries using SASTRE's variators and intent translator.

    Combines:
    - VariationGenerator for name/company/domain variations
    - IntentTranslator for natural language → syntax
    - QueryTier for precision/recall classification
    """

    def __init__(self):
        self.variator = VariationGenerator(include_transliterations=True, max_variations=15)
        self.translator = IntentTranslator()
        self.scorer = StrengthScorer()

    def generate_for_entity(
        self,
        entity_name: str,
        entity_type: str,
        intent: str = "discover",
    ) -> GeneratedQuery:
        """
        Generate a query with variations for an entity.

        Args:
            entity_name: Name of the entity
            entity_type: "person", "company", or "domain"
            intent: Natural language intent

        Returns:
            GeneratedQuery with variations and scoring
        """
        # Generate variations
        variations = self.variator.generate(entity_name, entity_type)

        # Score based on entity type
        if entity_type == "person":
            strength = 4  # Names have moderate uniqueness
        elif entity_type == "company":
            strength = 4  # Companies more unique with registration
        else:
            strength = 3  # Default

        # Assign tier
        tier = QueryTier.T0A if strength >= 5 else QueryTier.T1

        # Generate Free ORs expansion
        free_ors = expand_free_ors(entity_name, entity_type)

        return GeneratedQuery(
            primary=entity_name,
            variations=variations,
            tier=tier,
            strength=strength,
            entity_type=entity_type,
            intent=intent,
            free_ors=free_ors,
        )

    def translate_intent(
        self,
        intent: str,
        context: Optional[Dict[str, Any]] = None
    ) -> TranslatedQuery:
        """
        Translate natural language intent to query syntax.

        Example:
            query = generator.translate_intent("Find companies connected to John Smith")
            # Returns TranslatedQuery with syntax, operators, targets
        """
        return self.translator.translate(intent, context)

    def generate_plan_queries(
        self,
        plan: InvestigationPlan,
        include_variations: bool = True
    ) -> List[GeneratedQuery]:
        """
        Generate executable queries for all steps in a plan.

        Args:
            plan: InvestigationPlan with steps
            include_variations: Whether to include name variations

        Returns:
            List of GeneratedQuery objects
        """
        queries = []

        for step in plan.steps:
            if step.input_value.startswith("[from"):
                # Chained step - skip for now, will be generated dynamically
                continue

            query = self.generate_for_entity(
                entity_name=step.input_value,
                entity_type=self._input_type_to_entity_type(step.input_type),
                intent=step.description,
            )
            query.tier = step.tier
            query.strength = step.strength
            queries.append(query)

        return queries

    def _input_type_to_entity_type(self, input_type: str) -> str:
        """Map input types to entity types for variation generation."""
        mapping = {
            "person_name": "person",
            "company_name": "company",
            "domain_name": "domain",
            "email_address": "person",  # Emails often lead to people
            "phone_number": "person",
            "company_reg_id": "company",
            "company_tax_id": "company",
        }
        return mapping.get(input_type, "unknown")


# =============================================================================
# Natural Language Planning
# =============================================================================

def plan_from_tasking(tasking: str, jurisdiction: str = "UNKNOWN") -> Dict[str, Any]:
    """
    Create an investigation plan from natural language tasking.

    Example:
        plan = plan_from_tasking(
            "Investigate John Smith, director of Acme Corp in Dubai",
            jurisdiction="AE"
        )
    """
    # Parse the tasking
    translator = IntentTranslator()
    translated = translator.translate(tasking)

    # Extract entities from targets
    planner = InvestigationPlanner()
    results = {
        "tasking": tasking,
        "translated": {
            "syntax": translated.syntax,
            "intent": translated.intent.value,
            "operators": translated.operators,
            "targets": translated.targets,
            "explanation": translated.explanation,
        },
        "plans": [],
    }

    # Create plan for each target
    for target in translated.targets:
        if target.startswith("#"):
            continue  # Skip grid references for now

        # Determine entity type from operators
        entity_type = "person"  # Default
        if "c?" in translated.operators:
            entity_type = "company"
        elif "p?" in translated.operators:
            entity_type = "person"
        elif "d?" in translated.operators or "." in target:
            entity_type = "domain"

        plan = planner.create_plan(
            entity_type=entity_type,
            entity_name=target,
            jurisdiction=jurisdiction,
        )
        results["plans"].append(plan.to_dict())

    return results


def generate_queries(
    entity_name: str,
    entity_type: str = "person",
    intent: str = "discover"
) -> Dict[str, Any]:
    """
    Generate queries with variations for an entity.

    Example:
        queries = generate_queries("John Smith", "person", "find companies")
    """
    generator = QueryGenerator()
    query = generator.generate_for_entity(entity_name, entity_type, intent)
    return query.to_dict()
