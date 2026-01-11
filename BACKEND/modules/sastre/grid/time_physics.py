"""
Time Physics - The Temporal Topology Module
Implements the Multi-Resolution Time Model where TimeNodes are hierarchical containers.
"""

from typing import List, Optional, Literal, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class TimeNode:
    """
    The Temporal Container.
    Evidence attaches to the container matching its resolution.
    
    Attributes:
        type: "span" (Year/Month) or "point" (Day/Timestamp)
        resolution: Precision level
        value: ISO string or formatted value ("2024", "2024-01", "2024-01-12")
        tags: Contextual tags (e.g. #ElectionYear)
        parent: The container this node belongs to
        children: Sub-containers or points within this span
    """
    type: Literal["span", "point"]
    resolution: Literal["year", "month", "day", "timestamp"]
    value: str 
    tags: List[str] = field(default_factory=list)
    parent: Optional['TimeNode'] = None
    children: List['TimeNode'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_context(self) -> List[str]:
        """
        Inheritance flows down.
        Point[2024-01-12] inherits tags (#ElectionYear) from Span[2024].
        """
        inherited = self.parent.get_context() if self.parent else []
        # Return unique combined tags
        return list(set(inherited + self.tags))

    def add_child(self, child: 'TimeNode'):
        """Attach a child node to this container."""
        child.parent = self
        self.children.append(child)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for Grid/Elastic."""
        return {
            "class": "time",
            "type": self.type,
            "resolution": self.resolution,
            "value": self.value,
            "tags": self.tags,
            "context_inherited": self.get_context(),
            "parent_value": self.parent.value if self.parent else None
        }

class TimeTopology:
    """
    Manages the web of TimeNodes.
    Ensures that "2024-01-12" is correctly attached to "2024-01" and "2024".
    """
    
    def __init__(self):
        self.nodes: Dict[str, TimeNode] = {} # Map value -> TimeNode

    def get_or_create(self, value: str, resolution: str = None) -> TimeNode:
        """
        Get existing TimeNode or create it (and its parents) recursively.
        Example: get_or_create("2024-01-12") -> creates 2024-01-12, 2024-01, and 2024.
        """
        if value in self.nodes:
            return self.nodes[value]

        # Infer resolution if not provided
        if not resolution:
            resolution = self._infer_resolution(value)

        node_type = "point" if resolution in ["day", "timestamp"] else "span"
        
        node = TimeNode(
            type=node_type,
            resolution=resolution,
            value=value
        )

        # Recursively ensure parent exists
        parent_val = self._get_parent_value(value, resolution)
        if parent_val:
            parent = self.get_or_create(parent_val)
            parent.add_child(node)
        
        self.nodes[value] = node
        return node

    def _infer_resolution(self, value: str) -> str:
        if len(value) == 4 and value.isdigit():
            return "year"
        if len(value) == 7 and value[4] == '-': # YYYY-MM
            return "month"
        if len(value) == 10 and value[4] == '-' and value[7] == '-': # YYYY-MM-DD
            return "day"
        if 'T' in value or ':' in value:
            return "timestamp"
        return "unknown"

    def _get_parent_value(self, value: str, resolution: str) -> Optional[str]:
        if resolution == "timestamp":
            return value.split('T')[0] # Parent is Day
        if resolution == "day":
            return value[:7] # YYYY-MM
        if resolution == "month":
            return value[:4] # YYYY
        return None
