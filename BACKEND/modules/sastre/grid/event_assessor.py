"""
Event Assessor - The "Brain" of the Reality Engine.
Reads event_templates.json to detect physics violations (Hunger) in Event Nodes.
"""

import json
import os
from typing import List, Any, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

# Assuming unified slot definitions exist in contracts (mimicking LocationAssessor)
# In a real implementation, we'd import these. For this artifact, we define local types or assume imports.
# from ..contracts import UnifiedSlot, SlotType, SlotOrigin, SlotTarget, SlotState, SlotPriority
# from .cognitive_types import CognitiveGap, CognitiveMode, GapCoordinates3D, slot_to_gap

# --- Mocking dependencies for self-contained artifact execution if needed ---
@dataclass
class CognitiveGap:
    id: str
    description: str
    intent: str
    query: str
    priority: int

class EventAssessor:
    """
    Assesses Event Nodes against Templates to find empty 'sockets'.
    """

    def __init__(self, state: Any, templates_path: str = None):
        self.state = state
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
                # Index by trigger concept or ID for fast lookup
                return {t["id"]: t for t in data.get("event_templates", [])}
        except Exception as e:
            print(f"[EventAssessor] Failed to load templates: {e}")
            return {}

    def assess(self) -> List[CognitiveGap]:
        """
        Scan all Event Nodes in the state.
        For each event, find its matching template.
        Check if mandatory roles are filled.
        If not, create a CognitiveGap (Hunger).
        """
        gaps: List[CognitiveGap] = []
        
        # State is expected to be a Snapshot or Graph object containing nodes/edges
        nodes = getattr(self.state, "nodes", {})
        edges = getattr(self.state, "edges", [])

        # Filter for Event Nodes
        event_nodes = [n for n in nodes.values() if getattr(n, "class", "") == "event"]

        for event in event_nodes:
            # 1. Identify Template
            # In a mature system, the event has a 'template_id' property.
            # Fallback: Infer from 'type' or 'label'
            template = self._identify_template(event)
            if not template:
                continue

            # 2. Map current connections to Roles
            # Find edges connected to this event
            connected_edges = [e for e in edges if e.source == event.id or e.target == event.id]
            
            filled_roles = {}
            for role_name, role_def in template.get("roles", {}).items():
                # Check if an edge of type 'edge_type' exists connected to a node of 'class'
                # Edge logic: Event -> (edge_type) -> Node  OR  Node -> (inverse) -> Event
                # For this spec, we assume the Template defines the edge type FROM the Event perspective or bi-directional check
                target_edge_type = role_def["edge_type"]
                
                match = next((e for e in connected_edges if e.relationship == target_edge_type), None)
                if match:
                    filled_roles[role_name] = match

            # 3. Check Physics (Hunger)
            physics_rules = template.get("physics", [])
            for rule in physics_rules:
                condition = rule["condition"] # e.g., "beneficiary IS EMPTY"
                
                if self._check_condition(condition, filled_roles):
                    # HUNGER DETECTED
                    gap = self._create_gap(event, rule, template)
                    gaps.append(gap)

        return gaps

    def _identify_template(self, event_node) -> Optional[Dict]:
        # Simple lookup by property 'template_id' or type matching name
        t_id = getattr(event_node, "properties", {}).get("template_id")
        if t_id and t_id in self.templates:
            return self.templates[t_id]
        
        # Fallback: Match event type to template name
        e_type = getattr(event_node, "type", "").upper()
        for t in self.templates.values():
            if t["name"] == e_type:
                return t
        return None

    def _check_condition(self, condition: str, filled_roles: Dict) -> bool:
        """
        Parses simple physics conditions like "beneficiary IS EMPTY"
        """
        parts = condition.split(" ")
        if len(parts) >= 3 and parts[1] == "IS" and parts[2] == "EMPTY":
            role = parts[0]
            return role not in filled_roles
        return False

    def _create_gap(self, event_node, rule: Dict, template: Dict) -> CognitiveGap:
        """
        Construct the Gap object using the template's strategy.
        """
        # Interpolate the Hunger Query
        # e.g. "who received money from {originator}?"
        # We need to fetch the value of {originator} if it exists
        query_template = rule["hunger_query"]
        
        # This interpolation would need to fetch the actual label of the node filling the 'originator' role
        # For now, we leave it as a formatted string or do basic replacement if we had the edge targets
        
        return CognitiveGap(
            id=f"gap__event__{event_node.id}__{rule['intent']}",
            description=f"Physics violation in {template['name']}: {rule['condition']}",
            intent=rule["intent"],
            query=query_template,
            priority=80 # High priority for physics violations
        )
