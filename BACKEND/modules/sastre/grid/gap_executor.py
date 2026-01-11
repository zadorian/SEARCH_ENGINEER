"""
Gap Executor - The "Hand" of the Reality Engine.
Takes a CognitiveGap (Hunger), resolves its variables, and executes the necessary search actions.
"""

import re
import json
import os
from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ExecutionResult:
    gap_id: str
    status: str
    resolved_query: str
    data: Any
    error: Optional[str] = None

class GapExecutor:
    """
    Resolves and executes CognitiveGaps.
    """

    def __init__(self, templates_path: str = None):
        self.templates_path = templates_path or self._resolve_templates_path()
        self.templates = self._load_templates()

    def _resolve_templates_path(self) -> str:
        env_path = os.environ.get("EVENT_TEMPLATES_PATH")
        if env_path:
            p = Path(env_path).expanduser()
            if p.exists():
                return str(p)

        candidates = [
            Path("INPUT_OUTPUT/matrix/schema/event_templates.json"),
            Path("input_output/matrix/schema/event_templates.json"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        for parent in Path(__file__).resolve().parents:
            for rel in ("INPUT_OUTPUT/matrix/schema/event_templates.json", "input_output/matrix/schema/event_templates.json"):
                candidate = parent / rel
                if candidate.exists():
                    return str(candidate)

        return str(candidates[0])

    def _load_templates(self) -> Dict[str, Any]:
        try:
            with open(self.templates_path, 'r') as f:
                data = json.load(f)
                return {t["id"]: t for t in data.get("event_templates", [])}
        except Exception as e:
            print(f"[GapExecutor] Failed to load templates: {e}")
            return {}

    def resolve_query(self, query_template: str, context_nodes: Dict[str, Any], context_edges: List[Any], origin_event_id: str = None) -> str:
        """
        Interpolates variables in the query string using the graph context and Event Templates.
        Template: "who received money from {originator}?"
        Logic: 
          1. Find the Event Node (origin_event_id).
          2. Identify its Template (e.g. EVT_001).
          3. Look up the Role definition in the Template (originator -> edge_type: originated).
          4. Find the edge connected to the Event with that relationship.
          5. Get the label of the connected node.
        """
        
        variables = re.findall(r'\{(.*?)\}', query_template)
        if not variables:
            return query_template

        replacements = {}
        
        # 1. Find Event Node to get its Template ID
        event_node = context_nodes.get(origin_event_id) if origin_event_id else None
        template_id = None
        if event_node:
            props = getattr(event_node, 'properties', {}) or {}
            if isinstance(props, dict):
                template_id = props.get('template_id')
            # Fallback: if not in properties, maybe the Type matches the Name?
            if not template_id:
                e_type = getattr(event_node, 'type', '').upper()
                for tid, t in self.templates.items():
                    if t.get('name') == e_type:
                        template_id = tid
                        break
        
        template = self.templates.get(template_id)
        
        # Filter edges connected to the event
        relevant_edges = []
        if origin_event_id:
            relevant_edges = [
                e for e in context_edges 
                if getattr(e, 'source', '') == origin_event_id or getattr(e, 'target', '') == origin_event_id
            ]

        for var in variables:
            val = "Unknown"
            target_edge_type = None
            
            # A. Template-Based Resolution (Preferred)
            if template:
                role_def = template.get("roles", {}).get(var)
                if role_def:
                    target_edge_type = role_def.get("edge_type")
            
            # B. Fallback: Fuzzy Match (Legacy)
            # Find the edge
            match_edge = None
            if target_edge_type:
                match_edge = next((e for e in relevant_edges if getattr(e, 'relationship', '') == target_edge_type), None)
            else:
                # Fuzzy fallback
                match_edge = next((e for e in relevant_edges if var in getattr(e, 'relationship', '')), None)
            
            if match_edge:
                # Find the 'other' node
                other_id = None
                if origin_event_id:
                    if match_edge.source == origin_event_id:
                        other_id = match_edge.target
                    elif match_edge.target == origin_event_id:
                        other_id = match_edge.source
                if other_id is None:
                    other_id = getattr(match_edge, 'target', None)
                if other_id and other_id in context_nodes:
                    val = getattr(context_nodes[other_id], "label", other_id)
            
            replacements[var] = val

        # Replace in string
        resolved = query_template
        for var, val in replacements.items():
            resolved = resolved.replace(f'{{{var}}}', str(val))
            
        return resolved

    async def execute(self, gap: Any, search_runner: Callable[[str], Any], context: Any) -> ExecutionResult:
        """
        Execute the gap.
        1. Resolve the query.
        2. Call the search runner.
        """
        try:
            nodes = getattr(context, 'nodes', {})
            edges = getattr(context, 'edges', [])
            
            # Extract Event ID from Gap ID "gap__event__{id}__{intent}" or "gap_event_{id}_{intent}"
            event_id = None
            if hasattr(gap, 'id') and gap.id.startswith('gap__event__'):
                parts = gap.id.split('__')
                if len(parts) >= 3:
                    event_id = parts[2]
            elif hasattr(gap, 'id') and gap.id.startswith('gap_event_'):
                parts = gap.id.split('_')
                if len(parts) >= 3:
                    event_id = parts[2]

            resolved_query = self.resolve_query(gap.query, nodes, edges, event_id)
            
            print(f"[GapExecutor] Resolved Query: {resolved_query}")
            
            # Execute Search
            result_data = await search_runner(resolved_query)
            
            return ExecutionResult(
                gap_id=gap.id,
                status="success",
                resolved_query=resolved_query,
                data=result_data
            )
            
        except Exception as e:
            return ExecutionResult(
                gap_id=getattr(gap, 'id', 'unknown'),
                status="error",
                resolved_query=gap.query, 
                data=None,
                error=str(e)
            )
