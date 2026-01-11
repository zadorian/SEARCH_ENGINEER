"""
CyMonides 2.0 - Tool Registry
Tracks available tools and their capabilities for intelligent routing
"""

from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from collections import defaultdict


@dataclass
class ToolDefinition:
    """Definition of a tool's capabilities"""
    name: str
    description: str
    category: str  # enrichment, analysis, export, visualization, search, etc.

    # Input/Output types
    accepts_types: List[str] = field(default_factory=list)  # ["entity:person", "document"]
    produces_types: List[str] = field(default_factory=list)  # ["entity:person:enriched"]

    # Field requirements
    required_fields: List[str] = field(default_factory=list)  # ["email", "name"]
    optional_fields: List[str] = field(default_factory=list)  # ["phone", "linkedin"]
    produces_fields: List[str] = field(default_factory=list)  # ["phone_verified", "employment_history"]

    # Constraints
    min_items: int = 1  # Minimum items required
    max_items: Optional[int] = None  # Maximum items (None = unlimited)
    requires_api_key: bool = False
    cost: int = 1  # Relative cost (1-10)

    # UI hints
    icon: str = "🔧"
    button_label: Optional[str] = None
    button_color: str = "blue"
    show_in_ui: bool = True
    priority: int = 5  # 1-10, higher = more prominent

    # Function reference
    handler: Optional[Callable] = None

    # Usage stats
    usage_count: int = 0
    last_used: Optional[str] = None
    average_runtime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary (excluding handler)"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "accepts_types": self.accepts_types,
            "produces_types": self.produces_types,
            "required_fields": self.required_fields,
            "optional_fields": self.optional_fields,
            "produces_fields": self.produces_fields,
            "min_items": self.min_items,
            "max_items": self.max_items,
            "requires_api_key": self.requires_api_key,
            "cost": self.cost,
            "icon": self.icon,
            "button_label": self.button_label,
            "button_color": self.button_color,
            "show_in_ui": self.show_in_ui,
            "priority": self.priority,
            "usage_count": self.usage_count,
            "last_used": self.last_used,
            "average_runtime_seconds": self.average_runtime_seconds
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolDefinition':
        """Deserialize from dictionary"""
        # Remove handler if present (can't deserialize)
        data.pop("handler", None)
        return cls(**data)

    def can_handle(self, context: Dict[str, Any]) -> bool:
        """
        Check if this tool can handle the given context

        Args:
            context: Current context with selected items, etc.

        Returns:
            True if tool can be used
        """
        selected_items = context.get("selected_items", [])

        # Check minimum items
        if len(selected_items) < self.min_items:
            return False

        # Check maximum items
        if self.max_items and len(selected_items) > self.max_items:
            return False

        # Check accepted types
        if self.accepts_types:
            for item in selected_items:
                item_type = self._get_item_type(item)
                if not any(self._type_matches(item_type, accepted) for accepted in self.accepts_types):
                    return False

        # Check required fields
        if self.required_fields:
            for item in selected_items:
                if not all(field in item for field in self.required_fields):
                    return False

        return True

    def _get_item_type(self, item: Dict[str, Any]) -> str:
        """Get item type string (e.g., 'entity:person')"""
        doc_type = item.get("doc_type", "unknown")
        entity_type = item.get("entity_type")

        if entity_type:
            return f"{doc_type}:{entity_type}"
        return doc_type

    def _type_matches(self, item_type: str, pattern: str) -> bool:
        """Check if item type matches pattern (supports wildcards)"""
        # Exact match
        if item_type == pattern:
            return True

        # Wildcard match (e.g., "entity:*" matches "entity:person")
        if pattern.endswith(":*"):
            prefix = pattern[:-2]
            return item_type.startswith(prefix)

        # Prefix match (e.g., "entity" matches "entity:person")
        if ":" not in pattern and item_type.startswith(pattern + ":"):
            return True

        return False

    def update_stats(self, runtime_seconds: float):
        """Update usage statistics"""
        self.usage_count += 1
        self.last_used = datetime.utcnow().isoformat()

        # Update average runtime (rolling average)
        if self.average_runtime_seconds == 0:
            self.average_runtime_seconds = runtime_seconds
        else:
            # Weighted average (70% old, 30% new)
            self.average_runtime_seconds = (
                0.7 * self.average_runtime_seconds + 0.3 * runtime_seconds
            )


class ToolRegistry:
    """
    Tool Registry System

    Tracks available tools and their capabilities for:
    - Dynamic UI generation (show relevant buttons)
    - Intelligent routing (match tool outputs to inputs)
    - Pipeline suggestions (suggest common workflows)
    - Cost estimation (calculate workflow costs)
    """

    def __init__(self, cache_file: Optional[str] = None):
        """
        Initialize tool registry

        Args:
            cache_file: Optional file to cache tool definitions
        """
        self.cache_file = Path(cache_file) if cache_file else None

        # Tools registry: {tool_name: ToolDefinition}
        self.tools: Dict[str, ToolDefinition] = {}

        # Category index: {category: [tool_name, ...]}
        self.category_index: Dict[str, List[str]] = defaultdict(list)

        # Type index: {type: [tool_name, ...]} for routing
        self.input_type_index: Dict[str, List[str]] = defaultdict(list)
        self.output_type_index: Dict[str, List[str]] = defaultdict(list)

        # Workflow patterns: {(tool_a, tool_b): usage_count}
        self.workflow_patterns: Dict[tuple, int] = defaultdict(int)

        # Load cache if exists
        if self.cache_file and self.cache_file.exists():
            self._load_cache()

    def register_tool(self, tool_def: ToolDefinition):
        """
        Register a new tool

        Args:
            tool_def: Tool definition
        """
        self.tools[tool_def.name] = tool_def

        # Update category index
        self.category_index[tool_def.category].append(tool_def.name)

        # Update type indices
        for input_type in tool_def.accepts_types:
            self.input_type_index[input_type].append(tool_def.name)

        for output_type in tool_def.produces_types:
            self.output_type_index[output_type].append(tool_def.name)

        # Save cache
        if self.cache_file:
            self._save_cache()

        print(f"✅ Registered tool: {tool_def.name} ({tool_def.category})")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name"""
        return self.tools.get(name)

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get all tools in a category"""
        tool_names = self.category_index.get(category, [])
        return [self.tools[name] for name in tool_names]

    def get_compatible_tools(self, context: Dict[str, Any], category: Optional[str] = None) -> List[ToolDefinition]:
        """
        Get tools compatible with current context

        Args:
            context: Current context with selected_items, zone_id, etc.
            category: Optional category filter

        Returns:
            List of compatible tools, sorted by priority
        """
        compatible = []

        tools_to_check = self.tools.values()
        if category:
            tools_to_check = self.get_tools_by_category(category)

        for tool in tools_to_check:
            if tool.can_handle(context) and tool.show_in_ui:
                compatible.append(tool)

        # Sort by priority (descending) then usage count
        compatible.sort(key=lambda t: (t.priority, t.usage_count), reverse=True)

        return compatible

    def find_next_tools(self, current_tool: str, output_data: Dict[str, Any]) -> List[ToolDefinition]:
        """
        Find tools that can consume the output of current tool

        Args:
            current_tool: Name of tool that just ran
            output_data: Data produced by the tool

        Returns:
            List of compatible next tools
        """
        tool_def = self.tools.get(current_tool)
        if not tool_def:
            return []

        compatible_tools = []

        # Get output types from tool definition
        output_types = tool_def.produces_types

        # Find tools that accept these types
        for output_type in output_types:
            # Direct matches
            if output_type in self.input_type_index:
                for tool_name in self.input_type_index[output_type]:
                    if tool_name != current_tool:  # Don't suggest same tool
                        compatible_tools.append(self.tools[tool_name])

            # Pattern matches (e.g., "entity:person:enriched" matches "entity:*")
            for input_pattern, tool_names in self.input_type_index.items():
                if self._type_matches_pattern(output_type, input_pattern):
                    for tool_name in tool_names:
                        if tool_name != current_tool:
                            compatible_tools.append(self.tools[tool_name])

        # Remove duplicates while preserving order
        seen = set()
        unique_tools = []
        for tool in compatible_tools:
            if tool.name not in seen:
                seen.add(tool.name)
                unique_tools.append(tool)

        # Sort by workflow pattern frequency
        def workflow_score(tool: ToolDefinition) -> int:
            pattern = (current_tool, tool.name)
            return self.workflow_patterns.get(pattern, 0)

        unique_tools.sort(key=workflow_score, reverse=True)

        return unique_tools

    def suggest_pipeline(self, start_context: Dict[str, Any], goal: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Suggest a pipeline of tools based on context and goal

        Args:
            start_context: Initial context
            goal: Optional goal description (e.g., "enrich and export")

        Returns:
            Suggested pipeline steps
        """
        pipeline = []

        # Get initial compatible tools
        initial_tools = self.get_compatible_tools(start_context)

        if not initial_tools:
            return pipeline

        # TODO: Implement AI-based pipeline suggestion using goal
        # For now, use simple heuristic based on workflow patterns

        # Start with most used tool
        first_tool = initial_tools[0]
        pipeline.append({
            "step": 1,
            "tool": first_tool.name,
            "description": first_tool.description,
            "confidence": 0.9 if first_tool.usage_count > 10 else 0.6
        })

        # Find next steps based on patterns
        current_tool = first_tool.name
        for step in range(2, 5):  # Max 4 additional steps
            next_tools = self.find_next_tools(current_tool, {})
            if not next_tools:
                break

            next_tool = next_tools[0]
            pattern_count = self.workflow_patterns.get((current_tool, next_tool.name), 0)
            confidence = min(0.9, 0.5 + (pattern_count / 20))

            pipeline.append({
                "step": step,
                "tool": next_tool.name,
                "description": next_tool.description,
                "confidence": confidence
            })

            current_tool = next_tool.name

        return pipeline

    def track_workflow_pattern(self, previous_tool: str, next_tool: str):
        """
        Track a workflow pattern for learning

        Args:
            previous_tool: Previous tool used
            next_tool: Next tool used
        """
        pattern = (previous_tool, next_tool)
        self.workflow_patterns[pattern] += 1

        print(f"📊 Learned pattern: {previous_tool} → {next_tool} (count: {self.workflow_patterns[pattern]})")

        # Save cache
        if self.cache_file:
            self._save_cache()

    def generate_ui_buttons(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate UI button definitions based on context

        Args:
            context: Current context

        Returns:
            List of button definitions for UI
        """
        buttons = []
        compatible_tools = self.get_compatible_tools(context)

        for tool in compatible_tools[:10]:  # Max 10 buttons
            buttons.append({
                "id": tool.name,
                "label": tool.button_label or tool.name.replace("_", " ").title(),
                "icon": tool.icon,
                "color": tool.button_color,
                "tooltip": tool.description,
                "cost": tool.cost,
                "priority": tool.priority,
                "category": tool.category
            })

        return buttons

    def estimate_cost(self, tools: List[str]) -> int:
        """
        Estimate total cost of running multiple tools

        Args:
            tools: List of tool names

        Returns:
            Total cost
        """
        total = 0
        for tool_name in tools:
            if tool := self.tools.get(tool_name):
                total += tool.cost
        return total

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_tools": len(self.tools),
            "categories": {
                cat: len(tools)
                for cat, tools in self.category_index.items()
            },
            "total_patterns": len(self.workflow_patterns),
            "most_used_tools": sorted(
                [(t.name, t.usage_count) for t in self.tools.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "common_patterns": sorted(
                [(f"{a} → {b}", count) for (a, b), count in self.workflow_patterns.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }

    def _type_matches_pattern(self, type_str: str, pattern: str) -> bool:
        """Check if type matches pattern (with wildcard support)"""
        if pattern.endswith(":*"):
            prefix = pattern[:-2]
            return type_str.startswith(prefix)
        return type_str == pattern

    def _save_cache(self):
        """Save registry to cache file"""
        if not self.cache_file:
            return

        try:
            cache_data = {
                "tools": {
                    name: tool.to_dict()
                    for name, tool in self.tools.items()
                },
                "workflow_patterns": {
                    f"{a}→{b}": count
                    for (a, b), count in self.workflow_patterns.items()
                }
            }

            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            print(f"⚠️  Error saving registry cache: {e}")

    def _load_cache(self):
        """Load registry from cache file"""
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            # Load tools
            for name, tool_dict in cache_data.get("tools", {}).items():
                tool = ToolDefinition.from_dict(tool_dict)
                self.tools[name] = tool

                # Rebuild indices
                self.category_index[tool.category].append(name)
                for input_type in tool.accepts_types:
                    self.input_type_index[input_type].append(name)
                for output_type in tool.produces_types:
                    self.output_type_index[output_type].append(name)

            # Load workflow patterns
            for pattern_str, count in cache_data.get("workflow_patterns", {}).items():
                a, b = pattern_str.split("→")
                self.workflow_patterns[(a, b)] = count

            print(f"✅ Loaded registry cache from {self.cache_file}")

        except Exception as e:
            print(f"⚠️  Error loading registry cache: {e}")


# Example tool definitions for common operations
def get_default_tools() -> List[ToolDefinition]:
    """Get default tool definitions"""
    return [
        # Search tools
        ToolDefinition(
            name="search_entities",
            description="Search for entities by name, type, or field",
            category="search",
            produces_types=["entity:*"],
            icon="🔍",
            cost=1,
            priority=9
        ),
        ToolDefinition(
            name="search_documents",
            description="Full-text search across all documents",
            category="search",
            produces_types=["document"],
            icon="📄",
            cost=1,
            priority=9
        ),

        # Enrichment tools
        ToolDefinition(
            name="enrich_person",
            description="Enrich person entity with OSINT data",
            category="enrichment",
            accepts_types=["entity:person"],
            produces_types=["entity:person:enriched"],
            required_fields=["name"],
            optional_fields=["email", "phone"],
            produces_fields=["employment_history", "social_profiles", "location"],
            icon="✨",
            requires_api_key=True,
            cost=3,
            priority=8
        ),
        ToolDefinition(
            name="enrich_company",
            description="Enrich company entity with corporate data",
            category="enrichment",
            accepts_types=["entity:company"],
            produces_types=["entity:company:enriched"],
            required_fields=["name"],
            produces_fields=["employees", "financials", "subsidiaries"],
            icon="🏢",
            requires_api_key=True,
            cost=3,
            priority=8
        ),

        # Analysis tools
        ToolDefinition(
            name="analyze_network",
            description="Analyze relationships and connections",
            category="analysis",
            accepts_types=["entity:*"],
            produces_types=["analysis:network"],
            min_items=2,
            icon="🕸️",
            cost=2,
            priority=7
        ),
        ToolDefinition(
            name="find_connections",
            description="Find connections between entities",
            category="analysis",
            accepts_types=["entity:*"],
            produces_types=["relation"],
            min_items=2,
            icon="🔗",
            cost=2,
            priority=7
        ),

        # Export tools
        ToolDefinition(
            name="export_csv",
            description="Export selected items to CSV",
            category="export",
            accepts_types=["entity:*", "document"],
            produces_types=["file:csv"],
            icon="📊",
            cost=1,
            priority=5
        ),
        ToolDefinition(
            name="export_json",
            description="Export selected items to JSON",
            category="export",
            accepts_types=["entity:*", "document"],
            produces_types=["file:json"],
            icon="📋",
            cost=1,
            priority=5
        ),
        ToolDefinition(
            name="generate_report",
            description="Generate PDF report from selection",
            category="export",
            accepts_types=["entity:*", "document", "analysis:*"],
            produces_types=["file:pdf"],
            icon="📑",
            cost=2,
            priority=6
        ),

        # Visualization tools
        ToolDefinition(
            name="visualize_graph",
            description="Visualize entity relationships as graph",
            category="visualization",
            accepts_types=["entity:*"],
            produces_types=["visualization:graph"],
            min_items=2,
            icon="📈",
            cost=2,
            priority=6
        ),
        ToolDefinition(
            name="create_timeline",
            description="Create timeline from observations",
            category="visualization",
            accepts_types=["entity:*", "observation"],
            produces_types=["visualization:timeline"],
            icon="📅",
            cost=1,
            priority=5
        ),
    ]
