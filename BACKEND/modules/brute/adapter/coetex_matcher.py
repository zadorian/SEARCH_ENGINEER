"""
CyMonides 2.0 - Coetex Matcher
Intelligent routing engine that matches content with tools for dynamic workflows
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class RoutingDecision:
    """A routing decision made by Coetex"""
    confidence: float  # 0.0 - 1.0
    recommended_tools: List[str]
    reason: str
    alternative_tools: List[str] = None
    suggested_pipeline: List[Dict[str, Any]] = None
    ui_modifications: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "confidence": self.confidence,
            "recommended_tools": self.recommended_tools,
            "reason": self.reason,
            "alternative_tools": self.alternative_tools or [],
            "suggested_pipeline": self.suggested_pipeline or [],
            "ui_modifications": self.ui_modifications or {}
        }


class CoetexMatcher:
    """
    Coetex Intelligent Routing Engine

    Matches content inventory with tool registry to:
    - Show relevant tools based on what user has
    - Automatically route tool outputs to compatible inputs
    - Suggest intelligent workflows
    - Generate dynamic UI (buttons, filters, suggestions)
    - Learn from user behavior
    """

    def __init__(self, content_inventory, tool_registry):
        """
        Initialize Coetex matcher

        Args:
            content_inventory: ContentInventory instance
            tool_registry: ToolRegistry instance
        """
        self.inventory = content_inventory
        self.registry = tool_registry

        # Learning data
        self.user_preferences = {}  # User-specific preferences
        self.rejection_patterns = []  # Tools user has rejected

    def analyze_context(self, context: Dict[str, Any]) -> RoutingDecision:
        """
        Analyze context and make routing decision

        Args:
            context: Current context
                {
                    "selected_items": [...],
                    "zone_id": "default",
                    "user_id": "optional",
                    "last_action": "optional",
                    "goal": "optional description"
                }

        Returns:
            Routing decision with recommendations
        """
        zone_id = context.get("zone_id", "default")
        selected_items = context.get("selected_items", [])
        last_action = context.get("last_action")
        goal = context.get("goal")

        # Get compatible tools from registry
        compatible_tools = self.registry.get_compatible_tools(context)

        if not compatible_tools:
            return RoutingDecision(
                confidence=0.0,
                recommended_tools=[],
                reason="No compatible tools found for current selection",
                alternative_tools=[]
            )

        # Score tools based on multiple factors
        tool_scores = []
        for tool in compatible_tools:
            score = self._score_tool(tool, context, zone_id)
            tool_scores.append((tool.name, score, tool))

        # Sort by score
        tool_scores.sort(key=lambda x: x[1], reverse=True)

        # Extract top recommendations
        recommended = [name for name, score, _ in tool_scores[:3]]
        alternatives = [name for name, score, _ in tool_scores[3:7]]

        # Calculate confidence based on top score vs second score
        if len(tool_scores) == 1:
            confidence = 0.9
        else:
            top_score = tool_scores[0][1]
            second_score = tool_scores[1][1]
            confidence = min(0.95, top_score / (second_score + 0.1))

        # Generate reason
        reason = self._generate_reason(tool_scores[0][2], context, zone_id)

        # Suggest pipeline if appropriate
        suggested_pipeline = None
        if goal or last_action:
            suggested_pipeline = self._suggest_pipeline_for_context(context, tool_scores[0][2])

        # Generate UI modifications
        ui_mods = self._generate_ui_modifications(context, tool_scores)

        return RoutingDecision(
            confidence=confidence,
            recommended_tools=recommended,
            reason=reason,
            alternative_tools=alternatives,
            suggested_pipeline=suggested_pipeline,
            ui_modifications=ui_mods
        )

    def auto_route_output(self, source_tool: str, output_data: Dict[str, Any], context: Dict[str, Any]) -> Optional[RoutingDecision]:
        """
        Automatically route tool output to next compatible tool

        Args:
            source_tool: Tool that produced the output
            output_data: Data produced by the tool
            context: Current context

        Returns:
            Routing decision if auto-routing is possible, None otherwise
        """
        # Find compatible next tools
        next_tools = self.registry.find_next_tools(source_tool, output_data)

        if not next_tools:
            return None

        # Check if we have high confidence in auto-routing
        # (e.g., workflow pattern count > 10)
        top_tool = next_tools[0]
        pattern = (source_tool, top_tool.name)
        pattern_count = self.registry.workflow_patterns.get(pattern, 0)

        if pattern_count < 5:
            # Not enough confidence for auto-routing
            return None

        confidence = min(0.95, 0.5 + (pattern_count / 30))

        return RoutingDecision(
            confidence=confidence,
            recommended_tools=[top_tool.name],
            reason=f"Common workflow: {source_tool} → {top_tool.name} (used {pattern_count} times)",
            alternative_tools=[t.name for t in next_tools[1:3]],
            ui_modifications={
                "show_auto_route_prompt": True,
                "auto_route_tool": top_tool.name,
                "auto_route_confidence": confidence
            }
        )

    def generate_dynamic_ui(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate complete dynamic UI based on context

        Args:
            context: Current context

        Returns:
            UI definition with buttons, filters, suggestions
        """
        zone_id = context.get("zone_id", "default")
        selected_items = context.get("selected_items", [])

        # Get routing decision
        decision = self.analyze_context(context)

        # Generate buttons from compatible tools
        buttons = self.registry.generate_ui_buttons(context)

        # Generate smart filters based on actual data
        filters = self.inventory.generate_smart_filters(zone_id)

        # Generate content stats
        inventory_summary = self.inventory.get_summary(zone_id)

        # Generate suggestions
        suggestions = []

        # Suggestion 1: Pipeline suggestion
        if decision.suggested_pipeline:
            suggestions.append({
                "type": "pipeline",
                "title": "Suggested Workflow",
                "steps": decision.suggested_pipeline,
                "confidence": decision.confidence
            })

        # Suggestion 2: Data gaps
        data_gaps = self._identify_data_gaps(zone_id)
        if data_gaps:
            suggestions.append({
                "type": "data_gap",
                "title": "Enrich Your Data",
                "gaps": data_gaps
            })

        # Suggestion 3: Common patterns
        common_patterns = self._get_common_patterns_for_zone(zone_id)
        if common_patterns:
            suggestions.append({
                "type": "pattern",
                "title": "Common Actions",
                "patterns": common_patterns
            })

        return {
            "buttons": buttons,
            "filters": filters,
            "suggestions": suggestions,
            "stats": inventory_summary,
            "routing_decision": decision.to_dict(),
            "context_summary": {
                "selected_count": len(selected_items),
                "zone_id": zone_id,
                "available_actions": len(buttons)
            }
        }

    def learn_from_action(self, context: Dict[str, Any], chosen_tool: str, outcome: str = "success"):
        """
        Learn from user action

        Args:
            context: Context when action was taken
            chosen_tool: Tool the user chose
            outcome: "success", "failure", or "rejected"
        """
        last_action = context.get("last_action")

        # Track workflow pattern if there was a previous action
        if last_action and outcome == "success":
            self.registry.track_workflow_pattern(last_action, chosen_tool)

        # Track rejections for negative learning
        if outcome == "rejected":
            self.rejection_patterns.append({
                "context_hash": self._hash_context(context),
                "rejected_tool": chosen_tool
            })

        # Update user preferences
        user_id = context.get("user_id")
        if user_id:
            if user_id not in self.user_preferences:
                self.user_preferences[user_id] = {"preferred_tools": {}, "avoided_tools": set()}

            if outcome == "success":
                prefs = self.user_preferences[user_id]["preferred_tools"]
                prefs[chosen_tool] = prefs.get(chosen_tool, 0) + 1
            elif outcome == "rejected":
                self.user_preferences[user_id]["avoided_tools"].add(chosen_tool)

    def suggest_missing_data(self, zone_id: str = "default") -> List[Dict[str, Any]]:
        """
        Suggest what data is missing that could unlock more tools

        Args:
            zone_id: Zone to analyze

        Returns:
            List of suggestions for missing data
        """
        suggestions = []
        zone_inventory = self.inventory.get_zone_inventory(zone_id)

        if not zone_inventory:
            return [{
                "type": "empty_zone",
                "message": "This zone has no data. Start by importing documents or creating entities.",
                "actions": ["import_documents", "create_entity"]
            }]

        # Check what fields are commonly missing
        for doc_type, meta in zone_inventory.items():
            # Check for entities with missing contact info
            if doc_type == "entity" and "person" in meta.entity_types:
                missing_fields = []
                if "email" not in meta.available_fields:
                    missing_fields.append("email")
                if "phone" not in meta.available_fields:
                    missing_fields.append("phone")

                if missing_fields:
                    suggestions.append({
                        "type": "missing_fields",
                        "entity_type": "person",
                        "count": meta.count,
                        "missing_fields": missing_fields,
                        "message": f"{meta.count} people missing {', '.join(missing_fields)}",
                        "recommended_tool": "enrich_person"
                    })

            # Check for lack of relations
            if doc_type == "entity" and "relation" not in zone_inventory:
                suggestions.append({
                    "type": "missing_relations",
                    "message": f"You have {meta.count} entities but no relationships mapped",
                    "recommended_tool": "find_connections"
                })

        return suggestions

    def _score_tool(self, tool, context: Dict[str, Any], zone_id: str) -> float:
        """
        Score a tool based on multiple factors

        Returns:
            Score (higher = better match)
        """
        score = 0.0

        # Factor 1: Base priority from tool definition
        score += tool.priority * 10

        # Factor 2: Usage count (popular tools)
        score += min(20, tool.usage_count / 5)

        # Factor 3: Workflow pattern (if last_action exists)
        last_action = context.get("last_action")
        if last_action:
            pattern = (last_action, tool.name)
            pattern_count = self.registry.workflow_patterns.get(pattern, 0)
            score += min(30, pattern_count * 3)

        # Factor 4: User preferences
        user_id = context.get("user_id")
        if user_id and user_id in self.user_preferences:
            prefs = self.user_preferences[user_id]
            if tool.name in prefs["preferred_tools"]:
                score += prefs["preferred_tools"][tool.name] * 2
            if tool.name in prefs["avoided_tools"]:
                score -= 20

        # Factor 5: Rejection patterns
        context_hash = self._hash_context(context)
        for rejection in self.rejection_patterns:
            if rejection["context_hash"] == context_hash and rejection["rejected_tool"] == tool.name:
                score -= 15

        # Factor 6: Category relevance
        selected_items = context.get("selected_items", [])
        if selected_items:
            # Prefer enrichment if items lack fields
            if tool.category == "enrichment":
                items_needing_enrichment = sum(
                    1 for item in selected_items
                    if not any(item.get(field) for field in ["email", "phone", "address"])
                )
                score += items_needing_enrichment * 5

            # Prefer analysis if multiple items selected
            if tool.category == "analysis" and len(selected_items) > 1:
                score += 10

        # Factor 7: Cost consideration (slightly prefer cheaper tools)
        score -= tool.cost * 0.5

        return score

    def _generate_reason(self, tool, context: Dict[str, Any], zone_id: str) -> str:
        """Generate human-readable reason for recommendation"""
        reasons = []

        # Check if it's a workflow pattern
        last_action = context.get("last_action")
        if last_action:
            pattern = (last_action, tool.name)
            pattern_count = self.registry.workflow_patterns.get(pattern, 0)
            if pattern_count > 5:
                reasons.append(f"commonly follows {last_action}")

        # Check usage
        if tool.usage_count > 10:
            reasons.append(f"frequently used ({tool.usage_count} times)")

        # Check data match
        selected_items = context.get("selected_items", [])
        if selected_items:
            item_types = set(item.get("entity_type") or item.get("doc_type") for item in selected_items)
            if item_types.intersection(tool.accepts_types):
                reasons.append(f"matches selected items")

        if not reasons:
            reasons.append("available for current selection")

        return f"{tool.description} - {', '.join(reasons)}"

    def _suggest_pipeline_for_context(self, context: Dict[str, Any], starting_tool) -> List[Dict[str, Any]]:
        """Suggest a pipeline starting from the recommended tool"""
        pipeline = [{
            "step": 1,
            "tool": starting_tool.name,
            "description": starting_tool.description
        }]

        # Find next tools
        current_tool = starting_tool.name
        for step in range(2, 4):
            next_tools = self.registry.find_next_tools(current_tool, {})
            if not next_tools:
                break

            next_tool = next_tools[0]
            pattern = (current_tool, next_tool.name)
            pattern_count = self.registry.workflow_patterns.get(pattern, 0)

            pipeline.append({
                "step": step,
                "tool": next_tool.name,
                "description": next_tool.description,
                "confidence": min(0.9, 0.5 + (pattern_count / 20))
            })

            current_tool = next_tool.name

        return pipeline if len(pipeline) > 1 else None

    def _generate_ui_modifications(self, context: Dict[str, Any], tool_scores: List) -> Dict[str, Any]:
        """Generate UI modifications based on context"""
        modifications = {}

        # Highlight top tool if confidence is high
        if tool_scores and tool_scores[0][1] > 70:
            modifications["highlight_tool"] = tool_scores[0][0]

        # Show cost warning if total cost is high
        selected_items = context.get("selected_items", [])
        if len(selected_items) > 100:
            modifications["show_cost_warning"] = True
            modifications["estimated_cost"] = len(selected_items) * tool_scores[0][2].cost

        # Show pipeline mode if workflow pattern exists
        last_action = context.get("last_action")
        if last_action and tool_scores:
            pattern = (last_action, tool_scores[0][0])
            if self.registry.workflow_patterns.get(pattern, 0) > 5:
                modifications["suggest_pipeline_mode"] = True

        return modifications

    def _identify_data_gaps(self, zone_id: str) -> List[Dict[str, Any]]:
        """Identify gaps in data that limit available tools"""
        gaps = []
        zone_inventory = self.inventory.get_zone_inventory(zone_id)

        for doc_type, meta in zone_inventory.items():
            # Check for missing common fields
            common_fields = ["email", "phone", "address", "website", "linkedin"]
            missing = [f for f in common_fields if f not in meta.available_fields]

            if missing and doc_type == "entity":
                gaps.append({
                    "type": "missing_fields",
                    "doc_type": doc_type,
                    "fields": missing,
                    "message": f"Add {', '.join(missing[:2])} to unlock more tools"
                })

        return gaps

    def _get_common_patterns_for_zone(self, zone_id: str) -> List[Dict[str, Any]]:
        """Get common workflow patterns relevant to this zone"""
        patterns = []

        # Get top 3 patterns overall
        sorted_patterns = sorted(
            self.registry.workflow_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        for (tool_a, tool_b), count in sorted_patterns:
            patterns.append({
                "from_tool": tool_a,
                "to_tool": tool_b,
                "count": count,
                "description": f"{tool_a} → {tool_b} ({count} times)"
            })

        return patterns

    def _hash_context(self, context: Dict[str, Any]) -> str:
        """Create hash of context for comparison"""
        # Simple hash based on selected items and zone
        selected_items = context.get("selected_items", [])
        zone_id = context.get("zone_id", "default")

        item_types = sorted(set(
            item.get("entity_type") or item.get("doc_type")
            for item in selected_items
        ))

        return f"{zone_id}:{len(selected_items)}:{','.join(item_types)}"

    def get_stats(self) -> Dict[str, Any]:
        """Get Coetex statistics"""
        return {
            "total_users": len(self.user_preferences),
            "rejection_patterns": len(self.rejection_patterns),
            "workflow_patterns": len(self.registry.workflow_patterns),
            "top_preferences": [
                (user, sorted(prefs["preferred_tools"].items(), key=lambda x: x[1], reverse=True)[:3])
                for user, prefs in list(self.user_preferences.items())[:5]
            ]
        }
