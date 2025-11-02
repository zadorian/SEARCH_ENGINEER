"""
Cognitive Load Manager
Progressive disclosure system for large graphs (10,000+ nodes)

Prevents information overload by intelligently showing/hiding nodes
based on relevance, proximity, and user focus
"""

from typing import Dict, List, Set, Any
from enum import Enum


class DisclosureLevel(Enum):
    """Levels of detail for progressive disclosure"""
    CRITICAL = 1      # Always show (root query nodes)
    HIGH = 2          # Show by default (1st degree connections)
    MEDIUM = 3        # Show on hover/click (2nd degree)
    LOW = 4           # Show on explicit expand (3rd degree+)
    HIDDEN = 5        # Never show unless searched


class CognitiveLoadManager:
    """
    Manages which nodes/edges are visible to prevent cognitive overload

    Strategies:
    - Progressive disclosure (show important nodes first)
    - Proximity-based visibility (show nodes near focus)
    - Relevance scoring (show high-confidence relationships)
    - User attention tracking (adapt to user behavior)
    """

    def __init__(self, max_visible_nodes: int = 100):
        self.max_visible_nodes = max_visible_nodes
        self.focus_node: str | None = None
        self.visible_nodes: Set[str] = set()
        self.visible_edges: Set[tuple[str, str]] = set()

        # Node metadata
        self.node_levels: Dict[str, DisclosureLevel] = {}
        self.node_distances: Dict[str, int] = {}  # Distance from focus
        self.node_relevance: Dict[str, float] = {}  # Relevance score

    def set_focus(self, node_id: str):
        """
        Set focused node and recalculate visibility

        Args:
            node_id: ID of node user is focusing on
        """
        self.focus_node = node_id
        self.recalculate_visibility()

    def calculate_disclosure_levels(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        root_nodes: List[str]
    ):
        """
        Calculate disclosure level for each node

        Args:
            nodes: All graph nodes
            edges: All graph edges
            root_nodes: Query result nodes (always CRITICAL)
        """
        # Mark root nodes as CRITICAL
        for node_id in root_nodes:
            self.node_levels[node_id] = DisclosureLevel.CRITICAL
            self.node_distances[node_id] = 0

        # Calculate distances from root nodes (BFS)
        visited = set(root_nodes)
        queue = [(node_id, 0) for node_id in root_nodes]

        while queue:
            current_id, distance = queue.pop(0)

            # Find neighbors
            for edge in edges:
                if edge["from"] == current_id:
                    neighbor_id = edge["to"]
                elif edge["to"] == current_id:
                    neighbor_id = edge["from"]
                else:
                    continue

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    self.node_distances[neighbor_id] = distance + 1
                    queue.append((neighbor_id, distance + 1))

                    # Assign disclosure level based on distance
                    if distance + 1 == 1:
                        self.node_levels[neighbor_id] = DisclosureLevel.HIGH
                    elif distance + 1 == 2:
                        self.node_levels[neighbor_id] = DisclosureLevel.MEDIUM
                    else:
                        self.node_levels[neighbor_id] = DisclosureLevel.LOW

    def recalculate_visibility(self):
        """
        Recalculate which nodes/edges should be visible

        Based on:
        - Disclosure levels
        - Distance from focus node
        - Max visible nodes limit
        - Relevance scores
        """
        # TODO: Implement smart visibility calculation
        # For now, show nodes by disclosure level until limit reached

        visible = []

        # Always show CRITICAL nodes
        for node_id, level in self.node_levels.items():
            if level == DisclosureLevel.CRITICAL:
                visible.append((node_id, level.value))

        # Add HIGH importance nodes
        for node_id, level in self.node_levels.items():
            if level == DisclosureLevel.HIGH:
                visible.append((node_id, level.value))

        # Add MEDIUM if under limit
        for node_id, level in self.node_levels.items():
            if level == DisclosureLevel.MEDIUM and len(visible) < self.max_visible_nodes:
                visible.append((node_id, level.value))

        self.visible_nodes = {node_id for node_id, _ in visible}

    def should_show_node(self, node_id: str) -> bool:
        """
        Check if node should be visible

        Args:
            node_id: Node to check

        Returns:
            True if node should be visible
        """
        return node_id in self.visible_nodes

    def should_show_edge(self, edge: Dict[str, Any]) -> bool:
        """
        Check if edge should be visible

        Args:
            edge: Edge to check

        Returns:
            True if edge should be visible (both endpoints visible)
        """
        from_id = edge["from"]
        to_id = edge["to"]
        return from_id in self.visible_nodes and to_id in self.visible_nodes

    def get_visibility_stats(self) -> Dict[str, int]:
        """
        Get visibility statistics

        Returns:
            Dict with counts by disclosure level
        """
        stats = {
            "total_nodes": len(self.node_levels),
            "visible_nodes": len(self.visible_nodes),
            "critical": sum(1 for level in self.node_levels.values() if level == DisclosureLevel.CRITICAL),
            "high": sum(1 for level in self.node_levels.values() if level == DisclosureLevel.HIGH),
            "medium": sum(1 for level in self.node_levels.values() if level == DisclosureLevel.MEDIUM),
            "low": sum(1 for level in self.node_levels.values() if level == DisclosureLevel.LOW),
        }
        return stats
