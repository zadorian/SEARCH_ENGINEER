"""
SWITCHBOARD: Axis Orchestrator
Central logic system for managing interactions between all search axes.
Controls how different components limit and increase possibilities through
combinatorial interactions.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json

class AxisType(Enum):
    """Primary axes in the search architecture"""
    NARRATIVE = "narrative"  # Document processing
    SUBJECT = "subject"      # WHO/WHAT - Entities & topics
    OBJECT = "object"        # HOW - Query methods
    LOCATION = "location"    # WHERE - Search coordinates
    
class LocationCoordinate(Enum):
    """Sub-axes within LOCATION"""
    GEO = "geo"
    TYPE = "type"
    TEMPORAL = "temporal"
    FILETYPE = "filetype"
    URL = "url"
    TOPICAL = "topical"
    PUBLIC_RECORDS = "public_records"
    WEBDOMAIN = "webdomain"
    DOMAIN_RELATIONSHIPS = "domain_relationships"
    SOURCES = "sources"

class SubjectType(Enum):
    """Types within SUBJECT axis"""
    PERSON = "person"
    ORGANISATION = "organisation"
    COMPANY = "company"
    OTHER_ORGANISATION = "other_organisation"
    LOCATION = "location"
    PHONE = "phone"
    EMAIL = "email"
    USERNAME = "username"
    AIRPLANE = "airplane"
    TOPIC = "topic"

@dataclass
class AxisState:
    """Represents the current state of an axis"""
    axis_type: AxisType
    active_components: Set[str] = field(default_factory=set)
    constraints: Dict[str, Any] = field(default_factory=dict)
    capabilities: Set[str] = field(default_factory=set)
    priority: int = 0

@dataclass
class InteractionRule:
    """Defines how axes interact with each other"""
    source_axis: AxisType
    target_axis: AxisType
    condition: str  # Lambda or function name
    effect: str     # "limit", "enhance", "require", "exclude"
    parameters: Dict[str, Any] = field(default_factory=dict)

class AxisOrchestrator:
    """
    Central switchboard for managing interactions between all search axes.
    This system coordinates how different components affect each other.
    """
    
    def __init__(self):
        self.axis_states: Dict[AxisType, AxisState] = {}
        self.interaction_rules: List[InteractionRule] = []
        self.active_context: Dict[str, Any] = {}
        self._initialize_axes()
        self._load_interaction_rules()
    
    def _initialize_axes(self):
        """Initialize all axes with their default states"""
        for axis in AxisType:
            self.axis_states[axis] = AxisState(
                axis_type=axis,
                capabilities=self._get_default_capabilities(axis)
            )
    
    def _get_default_capabilities(self, axis: AxisType) -> Set[str]:
        """Get default capabilities for each axis"""
        capabilities_map = {
            AxisType.NARRATIVE: {
                "document_assembly", "gap_filling", "text_editing",
                "entity_extraction", "fact_verification"
            },
            AxisType.SUBJECT: {
                "entity_recognition", "disambiguation", "variation_generation",
                "relationship_mapping", "topic_classification"
            },
            AxisType.OBJECT: {
                "query_transformation", "operator_parsing", "filter_application",
                "ranking", "parallel_execution", "streaming"
            },
            AxisType.LOCATION: {
                "geo_targeting", "temporal_filtering", "source_selection",
                "domain_analysis", "filetype_restriction"
            }
        }
        return capabilities_map.get(axis, set())
    
    def _load_interaction_rules(self):
        """Load interaction rules that define axis relationships"""
        
        # NARRATIVE → SUBJECT: Document processing triggers entity extraction
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.NARRATIVE,
            target_axis=AxisType.SUBJECT,
            condition="document_loaded",
            effect="enhance",
            parameters={"triggers": ["entity_extraction", "topic_analysis"]}
        ))
        
        # SUBJECT → LOCATION: Entity type constrains search location
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.SUBJECT,
            target_axis=AxisType.LOCATION,
            condition="organisation_entity",
            effect="limit",
            parameters={
                "enable": ["PUBLIC_RECORDS", "WEBDOMAIN"],
                "prioritize": ["company_registries", "corporate_sources"]
            }
        ))
        
        # SUBJECT + LOCATION: Person + Country increases possibilities
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.SUBJECT,
            target_axis=AxisType.LOCATION,
            condition="person_with_country",
            effect="enhance",
            parameters={
                "expand": ["local_sources", "language_variants", "regional_sites"],
                "add_sources": ["local_news", "regional_registries"]
            }
        ))
        
        # LOCATION/GEO → OBJECT: Geographic location affects query methods
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.LOCATION,
            target_axis=AxisType.OBJECT,
            condition="non_english_country",
            effect="enhance",
            parameters={
                "add_operators": ["translation", "transliteration"],
                "modify_query": ["add_language_variants", "local_formats"]
            }
        ))
        
        # TEMPORAL → SOURCES: Time range limits available sources
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.LOCATION,
            target_axis=AxisType.LOCATION,
            condition="historical_date",
            effect="limit",
            parameters={
                "restrict_to": ["archive_sources", "wayback_machine"],
                "exclude": ["real_time_sources", "social_media"]
            }
        ))
        
        # OBJECT → ALL: Operator type affects all axes
        self.interaction_rules.append(InteractionRule(
            source_axis=AxisType.OBJECT,
            target_axis=AxisType.NARRATIVE,
            condition="proximity_operator",
            effect="require",
            parameters={"needs": ["snippet_validation", "context_extraction"]}
        ))
    
    def process_query_context(self, query_components: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a query through the switchboard to determine optimal execution path
        """
        # Reset context
        self.active_context = query_components
        
        # Identify active axes from query
        active_axes = self._identify_active_axes(query_components)
        
        # Apply interaction rules
        execution_plan = self._apply_interaction_rules(active_axes)
        
        # Optimize execution order
        execution_order = self._optimize_execution_order(execution_plan)
        
        return {
            "active_axes": active_axes,
            "execution_plan": execution_plan,
            "execution_order": execution_order,
            "constraints": self._get_active_constraints(),
            "enhancements": self._get_active_enhancements()
        }
    
    def _identify_active_axes(self, components: Dict) -> Set[AxisType]:
        """Identify which axes are active based on query components"""
        active = set()
        
        if components.get("entities") or components.get("topics"):
            active.add(AxisType.SUBJECT)
        
        if components.get("location") or components.get("temporal"):
            active.add(AxisType.LOCATION)
        
        if components.get("operators") or components.get("filters"):
            active.add(AxisType.OBJECT)
        
        if components.get("document") or components.get("narrative_mode"):
            active.add(AxisType.NARRATIVE)
        
        return active
    
    def _apply_interaction_rules(self, active_axes: Set[AxisType]) -> Dict:
        """Apply interaction rules based on active axes"""
        effects = {
            "limit": [],
            "enhance": [],
            "require": [],
            "exclude": []
        }

        for rule in self.interaction_rules:
            if rule.source_axis in active_axes:
                if self._evaluate_condition(rule.condition):
                    effect_key = rule.effect
                    if effect_key in effects:
                        effects[effect_key].append({
                            "source": rule.source_axis.value,
                            "target": rule.target_axis.value,
                            "parameters": rule.parameters
                        })

        return effects
    
    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate if a rule condition is met"""
        condition_map = {
            "document_loaded": lambda: "document" in self.active_context,
            "organisation_entity": lambda: self._has_entity_type("organisation"),
            "person_with_country": lambda: self._has_entity_type("person") and self._has_location("country"),
            "non_english_country": lambda: self._is_non_english_location(),
            "historical_date": lambda: self._is_historical_query(),
            "proximity_operator": lambda: "proximity" in self.active_context.get("operators", [])
        }
        
        evaluator = condition_map.get(condition, lambda: False)
        return evaluator()
    
    def _has_entity_type(self, entity_type: str) -> bool:
        """Check if specific entity type is present"""
        entities = self.active_context.get("entities", [])
        return any(e.get("type") == entity_type for e in entities)
    
    def _has_location(self, location_type: str) -> bool:
        """Check if specific location type is present"""
        location = self.active_context.get("location", {})
        return location_type in location
    
    def _is_non_english_location(self) -> bool:
        """Check if location is non-English speaking"""
        location = self.active_context.get("location", {})
        country = location.get("country", "")
        non_english = ["china", "japan", "russia", "germany", "france", "spain", "italy"]
        return any(c in country.lower() for c in non_english)
    
    def _is_historical_query(self) -> bool:
        """Check if query involves historical data"""
        temporal = self.active_context.get("temporal", {})
        if "date_range" in temporal:
            # Check if date is before current year - 2
            return temporal.get("start_year", 9999) < 2023
        return False
    
    def _optimize_execution_order(self, execution_plan: Dict) -> List[str]:
        """Determine optimal order for executing components"""
        order = []
        
        # Priority order based on dependencies
        priority_map = {
            AxisType.SUBJECT: 1,      # Identify entities first
            AxisType.LOCATION: 2,     # Then determine where to search
            AxisType.OBJECT: 3,        # Apply query methods
            AxisType.NARRATIVE: 4     # Process results
        }
        
        # Sort axes by priority
        active_axes = sorted(
            self.axis_states.keys(),
            key=lambda x: priority_map.get(x, 99)
        )
        
        for axis in active_axes:
            if self.axis_states[axis].active_components:
                order.append(axis.value)
        
        return order
    
    def _get_active_constraints(self) -> Dict[str, List[str]]:
        """Get all active constraints from interaction rules"""
        constraints = {}
        for axis, state in self.axis_states.items():
            if state.constraints:
                constraints[axis.value] = list(state.constraints.keys())
        return constraints
    
    def _get_active_enhancements(self) -> Dict[str, List[str]]:
        """Get all active enhancements from interaction rules"""
        enhancements = {}
        for axis, state in self.axis_states.items():
            enhanced_capabilities = state.capabilities - self._get_default_capabilities(axis)
            if enhanced_capabilities:
                enhancements[axis.value] = list(enhanced_capabilities)
        return enhancements
    
    def get_axis_compatibility_matrix(self) -> Dict[str, Dict[str, str]]:
        """
        Generate a compatibility matrix showing how axes interact
        """
        matrix = {}
        for source in AxisType:
            matrix[source.value] = {}
            for target in AxisType:
                if source == target:
                    matrix[source.value][target.value] = "self"
                else:
                    # Check for interaction rules
                    interaction = self._find_interaction(source, target)
                    if interaction:
                        matrix[source.value][target.value] = interaction.effect
                    else:
                        matrix[source.value][target.value] = "neutral"
        return matrix
    
    def _find_interaction(self, source: AxisType, target: AxisType) -> Optional[InteractionRule]:
        """Find interaction rule between two axes"""
        for rule in self.interaction_rules:
            if rule.source_axis == source and rule.target_axis == target:
                return rule
        return None
    
    def suggest_query_optimizations(self, query_components: Dict) -> List[Dict]:
        """
        Suggest optimizations based on axis interactions
        """
        suggestions = []
        context = self.process_query_context(query_components)
        
        # Check for missing beneficial combinations
        if AxisType.SUBJECT in context["active_axes"]:
            if AxisType.LOCATION not in context["active_axes"]:
                suggestions.append({
                    "type": "enhancement",
                    "suggestion": "Add location constraints to improve entity search precision",
                    "axes": ["SUBJECT", "LOCATION"]
                })
        
        # Check for conflicting combinations
        if self._has_entity_type("person") and "technical" in query_components.get("topics", []):
            suggestions.append({
                "type": "refinement",
                "suggestion": "Person entities with technical topics may benefit from academic/professional sources",
                "axes": ["SUBJECT", "LOCATION/SOURCES"]
            })
        
        return suggestions


# Singleton instance
orchestrator = AxisOrchestrator()

def process_search_query(query: str, components: Dict) -> Dict:
    """
    Main entry point for processing a search query through the switchboard
    """
    return orchestrator.process_query_context(components)

def get_compatibility_matrix() -> Dict:
    """
    Get the current compatibility matrix for all axes
    """
    return orchestrator.get_axis_compatibility_matrix()