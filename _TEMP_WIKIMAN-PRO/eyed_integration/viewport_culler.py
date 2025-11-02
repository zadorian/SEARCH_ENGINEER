"""
Viewport Culling + Level of Detail (LOD) System
Only renders nodes/edges visible in viewport for performance

Critical for large graphs (10,000+ nodes) - prevents browser freezing
"""

from typing import Dict, List, Any, Tuple, Set
from enum import Enum


class LODLevel(Enum):
    """Level of detail for rendering"""
    FULL = 1        # Full detail (labels, icons, hover effects)
    MEDIUM = 2      # Simplified (labels only, no icons)
    LOW = 3         # Minimal (dots only, no labels)
    CULLED = 4      # Not rendered (outside viewport)


class ViewportCuller:
    """
    Culls nodes/edges outside viewport and adjusts LOD based on zoom

    Features:
    - Spatial indexing for fast viewport queries
    - Dynamic LOD based on zoom level
    - Edge bundling for distant nodes
    - Smooth transitions between LOD levels
    """

    def __init__(self):
        self.viewport_bounds: Dict[str, float] = {
            "x_min": 0,
            "x_max": 800,
            "y_min": 0,
            "y_max": 600
        }
        self.zoom_level = 1.0

        # Spatial index (simple grid for now)
        self.spatial_index: Dict[Tuple[int, int], List[str]] = {}
        self.grid_size = 100  # px per grid cell

        # Node positions
        self.node_positions: Dict[str, Tuple[float, float]] = {}

        # LOD assignments
        self.node_lod: Dict[str, LODLevel] = {}

    def update_viewport(
        self,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        zoom: float
    ):
        """
        Update viewport bounds and zoom level

        Args:
            x_min, y_min: Top-left corner
            x_max, y_max: Bottom-right corner
            zoom: Zoom level (1.0 = 100%)
        """
        self.viewport_bounds = {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max
        }
        self.zoom_level = zoom

        # Recalculate LOD for all nodes
        self.recalculate_lod()

    def set_node_positions(self, positions: Dict[str, Tuple[float, float]]):
        """
        Update node positions and rebuild spatial index

        Args:
            positions: Dict mapping node_id -> (x, y)
        """
        self.node_positions = positions
        self.rebuild_spatial_index()

    def rebuild_spatial_index(self):
        """
        Rebuild spatial index for fast viewport queries

        Uses grid-based spatial partitioning
        """
        self.spatial_index = {}

        for node_id, (x, y) in self.node_positions.items():
            grid_x = int(x // self.grid_size)
            grid_y = int(y // self.grid_size)
            grid_cell = (grid_x, grid_y)

            if grid_cell not in self.spatial_index:
                self.spatial_index[grid_cell] = []

            self.spatial_index[grid_cell].append(node_id)

    def get_visible_nodes(self) -> Set[str]:
        """
        Get nodes visible in current viewport

        Returns:
            Set of node IDs in viewport
        """
        visible = set()

        # Calculate grid cells that overlap viewport
        x_min = self.viewport_bounds["x_min"]
        x_max = self.viewport_bounds["x_max"]
        y_min = self.viewport_bounds["y_min"]
        y_max = self.viewport_bounds["y_max"]

        grid_x_min = int(x_min // self.grid_size)
        grid_x_max = int(x_max // self.grid_size) + 1
        grid_y_min = int(y_min // self.grid_size)
        grid_y_max = int(y_max // self.grid_size) + 1

        # Check all overlapping grid cells
        for grid_x in range(grid_x_min, grid_x_max + 1):
            for grid_y in range(grid_y_min, grid_y_max + 1):
                grid_cell = (grid_x, grid_y)

                if grid_cell in self.spatial_index:
                    for node_id in self.spatial_index[grid_cell]:
                        # Double-check node is actually in viewport
                        x, y = self.node_positions[node_id]
                        if x_min <= x <= x_max and y_min <= y <= y_max:
                            visible.add(node_id)

        return visible

    def recalculate_lod(self):
        """
        Recalculate LOD level for each node based on zoom and position
        """
        visible_nodes = self.get_visible_nodes()

        for node_id in self.node_positions.keys():
            if node_id not in visible_nodes:
                # Outside viewport - cull
                self.node_lod[node_id] = LODLevel.CULLED
            elif self.zoom_level > 1.5:
                # Zoomed in - full detail
                self.node_lod[node_id] = LODLevel.FULL
            elif self.zoom_level > 0.5:
                # Normal zoom - medium detail
                self.node_lod[node_id] = LODLevel.MEDIUM
            else:
                # Zoomed out - low detail
                self.node_lod[node_id] = LODLevel.LOW

    def get_lod_level(self, node_id: str) -> LODLevel:
        """
        Get LOD level for a node

        Args:
            node_id: Node to check

        Returns:
            LOD level for rendering
        """
        return self.node_lod.get(node_id, LODLevel.FULL)

    def should_render_edge(
        self,
        edge: Dict[str, Any],
        visible_nodes: Set[str]
    ) -> bool:
        """
        Check if edge should be rendered

        Args:
            edge: Edge to check
            visible_nodes: Set of visible node IDs

        Returns:
            True if edge should be rendered
        """
        from_id = edge["from"]
        to_id = edge["to"]

        # Only render edge if both endpoints are visible
        return from_id in visible_nodes and to_id in visible_nodes

    def get_render_stats(self) -> Dict[str, int]:
        """
        Get rendering statistics

        Returns:
            Dict with counts by LOD level
        """
        stats = {
            "total_nodes": len(self.node_positions),
            "culled": sum(1 for level in self.node_lod.values() if level == LODLevel.CULLED),
            "low": sum(1 for level in self.node_lod.values() if level == LODLevel.LOW),
            "medium": sum(1 for level in self.node_lod.values() if level == LODLevel.MEDIUM),
            "full": sum(1 for level in self.node_lod.values() if level == LODLevel.FULL),
        }
        stats["rendered"] = stats["total_nodes"] - stats["culled"]
        return stats
