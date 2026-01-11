"""
SASTRE Graph Provider

Implements the GraphProvider interface for tagging operations.
Wraps InvestigationGraph with methods required by apply_tag_chain().

Required methods:
- add_tag(node_id, tag_name)
- remove_tag(node_id, tag_name)
- get_workstream_by_tag(tag_name)
- link_to_workstream(node_id, workstream_id)
- get_node_by_label(label)
- get_related_nodes(node_id)
- get_nodes_by_tag(tag_name)
- evaluate_tag_query(query) - for (#a AND #b) / (#a OR #b)
"""

from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class TagNode:
    """A tag node in the graph."""
    id: str
    tag_name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    node_ids: Set[str] = field(default_factory=set)  # Entities with this tag


@dataclass
class Workstream:
    """A workstream (narrative note container)."""
    id: str
    tag_name: str
    title: str
    node_ids: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)


class GraphProvider:
    """
    Provides tagging operations for InvestigationGraph.

    This is the interface required by apply_tag_chain() in tagging.py.
    """

    def __init__(self, graph=None):
        """
        Initialize GraphProvider.

        Args:
            graph: Optional InvestigationGraph to wrap
        """
        self._graph = graph

        # Tag storage (in-memory, or backed by graph)
        self._tags: Dict[str, TagNode] = {}  # tag_name -> TagNode
        self._node_tags: Dict[str, Set[str]] = {}  # node_id -> {tag_names}

        # Workstream storage
        self._workstreams: Dict[str, Workstream] = {}  # workstream_id -> Workstream
        self._tag_to_workstream: Dict[str, str] = {}  # tag_name -> workstream_id

    def set_graph(self, graph) -> None:
        """Set or update the underlying graph."""
        self._graph = graph

    # =========================================================================
    # TAG OPERATIONS (required by apply_tag_chain)
    # =========================================================================

    def add_tag(self, node_id: str, tag_name: str) -> bool:
        """
        Add a tag to a node.

        Args:
            node_id: The entity/node ID
            tag_name: The tag name (without #)

        Returns:
            True if tag was added, False if already exists
        """
        # Normalize tag name
        tag_name = tag_name.lstrip('#').lower()

        # Create tag if doesn't exist
        if tag_name not in self._tags:
            self._tags[tag_name] = TagNode(
                id=f"tag_{tag_name}",
                tag_name=tag_name,
            )

        tag_node = self._tags[tag_name]

        # Check if already tagged
        if node_id in tag_node.node_ids:
            return False

        # Add to tag's node set
        tag_node.node_ids.add(node_id)

        # Add to node's tag set
        if node_id not in self._node_tags:
            self._node_tags[node_id] = set()
        self._node_tags[node_id].add(tag_name)

        logger.debug(f"Added tag #{tag_name} to node {node_id}")
        return True

    def remove_tag(self, node_id: str, tag_name: str) -> bool:
        """
        Remove a tag from a node.

        Args:
            node_id: The entity/node ID
            tag_name: The tag name (without #)

        Returns:
            True if tag was removed, False if didn't exist
        """
        tag_name = tag_name.lstrip('#').lower()

        if tag_name not in self._tags:
            return False

        tag_node = self._tags[tag_name]

        if node_id not in tag_node.node_ids:
            return False

        # Remove from tag's node set
        tag_node.node_ids.discard(node_id)

        # Remove from node's tag set
        if node_id in self._node_tags:
            self._node_tags[node_id].discard(tag_name)

        logger.debug(f"Removed tag #{tag_name} from node {node_id}")
        return True

    def has_tag(self, node_id: str, tag_name: str) -> bool:
        """Check if a node has a specific tag."""
        tag_name = tag_name.lstrip('#').lower()
        return (
            node_id in self._node_tags and
            tag_name in self._node_tags[node_id]
        )

    def get_node_tags(self, node_id: str) -> List[str]:
        """Get all tags for a node."""
        return list(self._node_tags.get(node_id, set()))

    def get_nodes_by_tag(self, tag_name: str) -> List[str]:
        """Get all nodes with a specific tag."""
        tag_name = tag_name.lstrip('#').lower()

        if tag_name not in self._tags:
            return []

        return list(self._tags[tag_name].node_ids)

    # =========================================================================
    # WORKSTREAM OPERATIONS
    # =========================================================================

    def create_workstream(self, tag_name: str, title: str = None) -> Workstream:
        """
        Create a workstream (narrative note container).

        Workstreams are tagged with _workstream or _ws suffix by convention.
        """
        tag_name = tag_name.lstrip('#').lower()
        workstream_id = f"workstream_{tag_name}"

        workstream = Workstream(
            id=workstream_id,
            tag_name=tag_name,
            title=title or f"Workstream: {tag_name}",
        )

        self._workstreams[workstream_id] = workstream
        self._tag_to_workstream[tag_name] = workstream_id

        return workstream

    def get_workstream_by_tag(self, tag_name: str) -> Optional[str]:
        """
        Get workstream ID by tag name.

        Args:
            tag_name: The tag name (e.g., "offshore_ws" or "german_workstream")

        Returns:
            Workstream ID if exists, None otherwise
        """
        tag_name = tag_name.lstrip('#').lower()

        # Check direct mapping
        if tag_name in self._tag_to_workstream:
            return self._tag_to_workstream[tag_name]

        # Try creating workstream for _ws/_workstream tags
        if tag_name.endswith('_ws') or tag_name.endswith('_workstream'):
            workstream = self.create_workstream(tag_name)
            return workstream.id

        return None

    def link_to_workstream(self, node_id: str, workstream_id: str) -> bool:
        """
        Link a node to a workstream.

        Args:
            node_id: The entity/node ID
            workstream_id: The workstream ID

        Returns:
            True if linked, False if already linked
        """
        if workstream_id not in self._workstreams:
            return False

        workstream = self._workstreams[workstream_id]

        if node_id in workstream.node_ids:
            return False

        workstream.node_ids.add(node_id)
        logger.debug(f"Linked node {node_id} to workstream {workstream_id}")
        return True

    def get_workstream_nodes(self, workstream_id: str) -> List[str]:
        """Get all nodes in a workstream."""
        if workstream_id not in self._workstreams:
            return []
        return list(self._workstreams[workstream_id].node_ids)

    # =========================================================================
    # NODE LOOKUP OPERATIONS
    # =========================================================================

    def get_node_by_label(self, label: str) -> Optional[str]:
        """
        Get node ID by label (value).

        If wrapped graph exists, uses its entity lookup.
        """
        if self._graph:
            entity = self._graph.get_entity_by_value(label)
            if entity:
                return entity.id
        return None

    def get_related_nodes(self, node_id: str) -> List[str]:
        """
        Get nodes related to the given node via edges.

        If wrapped graph exists, traverses its edges.
        """
        related = []

        if self._graph:
            # Get outgoing edges
            edges_from = self._graph.get_edges_from(node_id)
            for edge in edges_from:
                related.append(edge.target_id)

            # Get incoming edges
            edges_to = self._graph.get_edges_to(node_id)
            for edge in edges_to:
                related.append(edge.source_id)

        return related

    # =========================================================================
    # BOOLEAN TAG QUERIES: (#a AND #b), (#a OR #b)
    # =========================================================================

    def evaluate_tag_query(self, query: str) -> List[str]:
        """
        Evaluate a boolean tag query.

        Syntax:
            (#tag1 AND #tag2)    → Nodes with BOTH tags
            (#tag1 OR #tag2)     → Nodes with EITHER tag
            (#a AND #b AND #c)   → Nodes with ALL tags
            (#a OR #b OR #c)     → Nodes with ANY tag

        Args:
            query: The boolean tag query string

        Returns:
            List of node IDs matching the query
        """
        # Normalize
        query = query.strip()

        # Remove outer parentheses
        if query.startswith('(') and query.endswith(')'):
            query = query[1:-1].strip()

        # Extract tags and operator
        and_pattern = re.compile(r'#(\w+)\s+AND\s+', re.IGNORECASE)
        or_pattern = re.compile(r'#(\w+)\s+OR\s+', re.IGNORECASE)

        # Detect operator type
        has_and = ' AND ' in query.upper()
        has_or = ' OR ' in query.upper()

        # Mixed operators not supported in this simple implementation
        if has_and and has_or:
            logger.warning(f"Mixed AND/OR not supported: {query}")
            return []

        # Split by operator
        if has_and:
            parts = re.split(r'\s+AND\s+', query, flags=re.IGNORECASE)
            return self._evaluate_and(parts)
        elif has_or:
            parts = re.split(r'\s+OR\s+', query, flags=re.IGNORECASE)
            return self._evaluate_or(parts)
        else:
            # Single tag
            tag = query.lstrip('#').strip()
            return self.get_nodes_by_tag(tag)

    def _evaluate_and(self, tag_parts: List[str]) -> List[str]:
        """Evaluate AND query - nodes with ALL tags."""
        if not tag_parts:
            return []

        # Get nodes for first tag
        first_tag = tag_parts[0].lstrip('#').strip()
        result_set = set(self.get_nodes_by_tag(first_tag))

        # Intersect with remaining tags
        for part in tag_parts[1:]:
            tag = part.lstrip('#').strip()
            tag_nodes = set(self.get_nodes_by_tag(tag))
            result_set &= tag_nodes

        return list(result_set)

    def _evaluate_or(self, tag_parts: List[str]) -> List[str]:
        """Evaluate OR query - nodes with ANY tag."""
        result_set = set()

        for part in tag_parts:
            tag = part.lstrip('#').strip()
            result_set.update(self.get_nodes_by_tag(tag))

        return list(result_set)

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def tag_multiple(self, node_ids: List[str], tag_name: str) -> int:
        """Tag multiple nodes. Returns count of nodes tagged."""
        count = 0
        for node_id in node_ids:
            if self.add_tag(node_id, tag_name):
                count += 1
        return count

    def untag_multiple(self, node_ids: List[str], tag_name: str) -> int:
        """Remove tag from multiple nodes. Returns count of nodes untagged."""
        count = 0
        for node_id in node_ids:
            if self.remove_tag(node_id, tag_name):
                count += 1
        return count

    # =========================================================================
    # EXPORT / SERIALIZATION
    # =========================================================================

    def get_tag_summary(self) -> Dict[str, Any]:
        """Get summary of all tags and counts."""
        return {
            tag_name: {
                "id": tag_node.id,
                "count": len(tag_node.node_ids),
                "created_at": tag_node.created_at.isoformat(),
            }
            for tag_name, tag_node in self._tags.items()
        }

    def export_tags(self) -> Dict[str, Any]:
        """Export all tag data for persistence."""
        return {
            "tags": {
                name: {
                    "id": tag.id,
                    "tag_name": tag.tag_name,
                    "created_at": tag.created_at.isoformat(),
                    "node_ids": list(tag.node_ids),
                }
                for name, tag in self._tags.items()
            },
            "workstreams": {
                ws_id: {
                    "id": ws.id,
                    "tag_name": ws.tag_name,
                    "title": ws.title,
                    "node_ids": list(ws.node_ids),
                    "created_at": ws.created_at.isoformat(),
                }
                for ws_id, ws in self._workstreams.items()
            },
        }

    def import_tags(self, data: Dict[str, Any]) -> None:
        """Import tag data from exported format."""
        # Import tags
        for name, tag_data in data.get("tags", {}).items():
            self._tags[name] = TagNode(
                id=tag_data["id"],
                tag_name=tag_data["tag_name"],
                created_at=datetime.fromisoformat(tag_data["created_at"]),
                node_ids=set(tag_data["node_ids"]),
            )
            # Rebuild node_tags index
            for node_id in tag_data["node_ids"]:
                if node_id not in self._node_tags:
                    self._node_tags[node_id] = set()
                self._node_tags[node_id].add(name)

        # Import workstreams
        for ws_id, ws_data in data.get("workstreams", {}).items():
            self._workstreams[ws_id] = Workstream(
                id=ws_data["id"],
                tag_name=ws_data["tag_name"],
                title=ws_data["title"],
                node_ids=set(ws_data["node_ids"]),
                created_at=datetime.fromisoformat(ws_data["created_at"]),
            )
            self._tag_to_workstream[ws_data["tag_name"]] = ws_id


# =============================================================================
# SINGLETON / FACTORY
# =============================================================================

_default_provider: Optional[GraphProvider] = None


def get_graph_provider(graph=None) -> GraphProvider:
    """
    Get the default GraphProvider instance.

    Args:
        graph: Optional InvestigationGraph to wrap

    Returns:
        GraphProvider instance
    """
    global _default_provider

    if _default_provider is None:
        _default_provider = GraphProvider(graph)
    elif graph is not None:
        _default_provider.set_graph(graph)

    return _default_provider


def reset_graph_provider() -> None:
    """Reset the default provider (for testing)."""
    global _default_provider
    _default_provider = None
