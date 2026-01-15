"""
Combinatorial Analyzer for Multi-Axis Interactions
Dynamically computes how different axis combinations affect search possibilities
"""

from typing import Dict, List, Set, Tuple, Optional, Any
from itertools import combinations, product
from dataclasses import dataclass
import json
import math

@dataclass
class AxisCombination:
    """Represents a specific combination of axis states"""
    axes: Tuple[str, ...]
    values: Tuple[Any, ...]
    interaction_score: float = 0.0
    effect_type: str = "neutral"  # enhance, limit, transform, conflict
    
class CombinatorialAnalyzer:
    """
    Analyzes combinatorial interactions between search axes
    to determine optimal search strategies
    """
    
    def __init__(self):
        self.load_interaction_rules()
        self.interaction_cache = {}
        
    def load_interaction_rules(self):
        """Load interaction rules from configuration"""
        with open("interaction_rules.json", "r") as f:
            self.rules = json.load(f)
    
    def analyze_combination(self, active_components: Dict[str, Any]) -> Dict:
        """
        Analyze a specific combination of active components
        Returns interaction effects and recommendations
        """
        # Get all active axes
        active_axes = list(active_components.keys())
        
        # Analyze pairwise interactions
        pairwise_effects = self._analyze_pairwise(active_axes, active_components)
        
        # Analyze higher-order interactions
        higher_order_effects = self._analyze_higher_order(active_axes, active_components)
        
        # Compute overall effect
        overall_effect = self._compute_overall_effect(pairwise_effects, higher_order_effects)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(overall_effect, active_components)
        
        return {
            "active_axes": active_axes,
            "pairwise_effects": pairwise_effects,
            "higher_order_effects": higher_order_effects,
            "overall_effect": overall_effect,
            "recommendations": recommendations,
            "search_space_modifier": self._calculate_search_space_modifier(overall_effect)
        }
    
    def _analyze_pairwise(self, axes: List[str], components: Dict) -> List[Dict]:
        """Analyze all pairwise interactions between axes"""
        effects = []
        
        for axis1, axis2 in combinations(axes, 2):
            interaction_key = f"{axis1}_{axis2}"
            reverse_key = f"{axis2}_{axis1}"
            
            # Check if interaction is defined
            if interaction_key in self.rules.get("axis_interactions", {}):
                rule = self.rules["axis_interactions"][interaction_key]
                effect = self._evaluate_interaction(axis1, axis2, components, rule)
                effects.append(effect)
            elif reverse_key in self.rules.get("axis_interactions", {}):
                rule = self.rules["axis_interactions"][reverse_key]
                effect = self._evaluate_interaction(axis2, axis1, components, rule)
                effects.append(effect)
        
        return effects
    
    def _analyze_higher_order(self, axes: List[str], components: Dict) -> List[Dict]:
        """Analyze interactions involving 3 or more axes"""
        effects = []
        
        # Check for 3-way interactions
        for combo in combinations(axes, 3):
            effect = self._evaluate_triple_interaction(combo, components)
            if effect:
                effects.append(effect)
        
        # Check for 4+ way interactions (if performance allows)
        if len(axes) >= 4:
            for combo in combinations(axes, 4):
                effect = self._evaluate_complex_interaction(combo, components)
                if effect:
                    effects.append(effect)
        
        return effects
    
    def _evaluate_interaction(self, axis1: str, axis2: str, 
                             components: Dict, rule: Dict) -> Dict:
        """Evaluate a specific interaction between two axes"""
        # Check if the specific combination exists
        component1 = components.get(axis1)
        component2 = components.get(axis2)
        
        # Calculate interaction strength
        strength = self._calculate_interaction_strength(component1, component2, rule)
        
        return {
            "axes": [axis1, axis2],
            "effect": rule.get("effect", "neutral"),
            "strength": strength,
            "description": rule.get("description", ""),
            "modifiers": rule.get("enables", []) + rule.get("restricts_to", [])
        }
    
    def _evaluate_triple_interaction(self, axes: Tuple[str, str, str], 
                                    components: Dict) -> Optional[Dict]:
        """Evaluate three-way interactions"""
        # Special handling for known powerful combinations
        triple_patterns = {
            ("SUBJECT", "LOCATION", "TEMPORAL"): {
                "effect": "precise",
                "description": "Person/org + location + time enables precise historical tracking",
                "strength": 0.9
            },
            ("SUBJECT", "OBJECT", "NARRATIVE"): {
                "effect": "comprehensive",
                "description": "Entity + operators + narrative enables full analysis",
                "strength": 0.85
            },
            ("LOCATION", "TEMPORAL", "SOURCES"): {
                "effect": "contextual",
                "description": "Location + time + sources provides historical context",
                "strength": 0.8
            }
        }
        
        # Check if this combination matches a pattern
        for pattern, effect_data in triple_patterns.items():
            if set(axes) == set(pattern):
                return {
                    "axes": list(axes),
                    "effect": effect_data["effect"],
                    "strength": effect_data["strength"],
                    "description": effect_data["description"]
                }
        
        return None
    
    def _evaluate_complex_interaction(self, axes: Tuple, components: Dict) -> Optional[Dict]:
        """Evaluate complex multi-axis interactions"""
        if len(axes) >= 4:
            # Complex interactions often have diminishing returns
            base_strength = 0.7
            complexity_penalty = 0.1 * (len(axes) - 4)
            
            return {
                "axes": list(axes),
                "effect": "complex",
                "strength": max(0.3, base_strength - complexity_penalty),
                "description": f"Complex {len(axes)}-way interaction",
                "warning": "May require staged execution for optimal results"
            }
        
        return None
    
    def _calculate_interaction_strength(self, comp1: Any, comp2: Any, 
                                       rule: Dict) -> float:
        """Calculate the strength of an interaction"""
        base_strength = 0.5
        
        # Adjust based on effect type
        effect_modifiers = {
            "enhance": 0.3,
            "limit": -0.2,
            "transform": 0.1,
            "require": 0.2,
            "conflict": -0.4
        }
        
        effect = rule.get("effect", "neutral")
        modifier = effect_modifiers.get(effect, 0)
        
        return min(1.0, max(0.0, base_strength + modifier))
    
    def _compute_overall_effect(self, pairwise: List[Dict], 
                               higher_order: List[Dict]) -> Dict:
        """Compute the overall effect of all interactions"""
        all_effects = pairwise + higher_order
        
        if not all_effects:
            return {
                "type": "neutral",
                "strength": 0.5,
                "dominant_interaction": None
            }
        
        # Calculate weighted average strength
        total_strength = sum(e["strength"] for e in all_effects)
        avg_strength = total_strength / len(all_effects)
        
        # Determine dominant effect type
        effect_counts = {}
        for effect in all_effects:
            effect_type = effect.get("effect", "neutral")
            effect_counts[effect_type] = effect_counts.get(effect_type, 0) + 1
        
        dominant_effect = max(effect_counts, key=effect_counts.get)
        
        # Find strongest interaction
        strongest = max(all_effects, key=lambda x: x["strength"])
        
        return {
            "type": dominant_effect,
            "strength": avg_strength,
            "dominant_interaction": strongest,
            "total_interactions": len(all_effects)
        }
    
    def _calculate_search_space_modifier(self, overall_effect: Dict) -> float:
        """
        Calculate how the interactions modify the search space
        1.0 = no change, >1.0 = expansion, <1.0 = reduction
        """
        base = 1.0
        strength = overall_effect.get("strength", 0.5)
        effect_type = overall_effect.get("type", "neutral")
        
        modifiers = {
            "enhance": 1.0 + (strength * 0.5),
            "limit": 1.0 - (strength * 0.3),
            "transform": 1.0 + (strength * 0.2),
            "precise": 0.7,  # Reduces space but increases relevance
            "comprehensive": 1.3,
            "complex": 1.1,
            "conflict": 0.8,
            "neutral": 1.0
        }
        
        return modifiers.get(effect_type, 1.0)
    
    def _generate_recommendations(self, overall_effect: Dict, 
                                 components: Dict) -> List[Dict]:
        """Generate recommendations based on the analysis"""
        recommendations = []
        
        # Check if search space is too broad
        if overall_effect.get("strength", 0) < 0.3:
            recommendations.append({
                "type": "warning",
                "message": "Low interaction strength - consider adding more constraints",
                "suggestion": "Add location or temporal constraints to focus the search"
            })
        
        # Check if search is too complex
        if overall_effect.get("total_interactions", 0) > 5:
            recommendations.append({
                "type": "optimization",
                "message": "Complex query with many interactions",
                "suggestion": "Consider breaking into multiple staged searches"
            })
        
        # Check for conflicts
        if overall_effect.get("type") == "conflict":
            recommendations.append({
                "type": "conflict",
                "message": "Conflicting constraints detected",
                "suggestion": "Review and prioritize search requirements"
            })
        
        # Suggest enhancements
        if overall_effect.get("type") == "enhance":
            recommendations.append({
                "type": "opportunity",
                "message": "Strong positive interactions detected",
                "suggestion": "Current combination is optimal for comprehensive results"
            })
        
        return recommendations
    
    def suggest_missing_axes(self, active_components: Dict) -> List[Dict]:
        """Suggest additional axes that would enhance the search"""
        suggestions = []
        active_axes = set(active_components.keys())
        
        # Define beneficial combinations
        beneficial_combos = {
            frozenset(["SUBJECT", "LOCATION"]): ["TEMPORAL", "SOURCES"],
            frozenset(["SUBJECT", "TEMPORAL"]): ["LOCATION", "NARRATIVE"],
            frozenset(["LOCATION", "TEMPORAL"]): ["SUBJECT", "SOURCES"],
            frozenset(["OBJECT", "SUBJECT"]): ["NARRATIVE", "LOCATION"]
        }
        
        for combo, suggested in beneficial_combos.items():
            if combo.issubset(active_axes):
                for axis in suggested:
                    if axis not in active_axes:
                        suggestions.append({
                            "axis": axis,
                            "reason": f"Would enhance {', '.join(combo)} combination",
                            "expected_benefit": "increased precision and recall"
                        })
        
        return suggestions
    
    def compute_execution_strategy(self, components: Dict) -> Dict:
        """
        Compute optimal execution strategy based on interactions
        """
        analysis = self.analyze_combination(components)
        
        # Determine execution mode
        if analysis["overall_effect"]["strength"] > 0.7:
            mode = "parallel"  # Strong interactions benefit from parallel execution
        elif analysis["overall_effect"]["total_interactions"] > 4:
            mode = "staged"  # Complex queries need staged execution
        else:
            mode = "sequential"  # Default sequential execution
        
        # Determine priority order
        priority_order = self._determine_priority_order(components, analysis)
        
        # Estimate resource requirements
        resources = self._estimate_resources(analysis)
        
        return {
            "mode": mode,
            "priority_order": priority_order,
            "estimated_time": resources["time"],
            "estimated_api_calls": resources["api_calls"],
            "parallelization_factor": resources["parallel_factor"],
            "optimization_hints": analysis["recommendations"]
        }
    
    def _determine_priority_order(self, components: Dict, 
                                 analysis: Dict) -> List[str]:
        """Determine optimal execution order for components"""
        # Base priority scores
        base_priority = {
            "SUBJECT": 1,  # Identify what we're looking for first
            "LOCATION": 2,  # Then where to look
            "TEMPORAL": 3,  # Filter by time
            "OBJECT": 4,    # Apply operators
            "NARRATIVE": 5  # Process results
        }
        
        # Adjust based on interactions
        adjusted_priority = {}
        for axis in components.keys():
            score = base_priority.get(axis, 99)
            
            # Boost priority if axis is involved in strong interactions
            for effect in analysis["pairwise_effects"]:
                if axis in effect["axes"] and effect["strength"] > 0.7:
                    score -= 0.5  # Lower score = higher priority
            
            adjusted_priority[axis] = score
        
        # Sort by priority
        return sorted(components.keys(), key=lambda x: adjusted_priority.get(x, 99))
    
    def _estimate_resources(self, analysis: Dict) -> Dict:
        """Estimate resource requirements based on interaction analysis"""
        base_time = 10  # seconds
        base_api_calls = 5
        
        # Adjust based on search space modifier
        space_modifier = analysis["search_space_modifier"]
        
        # More interactions generally mean more processing
        interaction_factor = 1 + (analysis["overall_effect"]["total_interactions"] * 0.1)
        
        # Calculate parallelization potential
        if analysis["overall_effect"]["type"] in ["enhance", "comprehensive"]:
            parallel_factor = min(5, 1 + analysis["overall_effect"]["total_interactions"])
        else:
            parallel_factor = 1
        
        return {
            "time": base_time * space_modifier * interaction_factor / parallel_factor,
            "api_calls": int(base_api_calls * space_modifier * interaction_factor),
            "parallel_factor": parallel_factor
        }


# Example usage
def analyze_search_query(query_components: Dict) -> Dict:
    """Main entry point for combinatorial analysis"""
    analyzer = CombinatorialAnalyzer()
    
    # Perform analysis
    analysis = analyzer.analyze_combination(query_components)
    
    # Get execution strategy
    strategy = analyzer.compute_execution_strategy(query_components)
    
    # Get suggestions for improvement
    suggestions = analyzer.suggest_missing_axes(query_components)
    
    return {
        "analysis": analysis,
        "strategy": strategy,
        "suggestions": suggestions
    }