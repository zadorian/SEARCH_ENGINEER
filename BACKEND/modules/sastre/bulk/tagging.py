"""
SASTRE Bulk Tagging

Parses => tag chain syntax and applies tags to nodes.

Syntax:
  => +#tag           - Add tag to results
  => -#tag           - Remove tag from results
  => #workstream     - Link to workstream (narrative note)

Chain:
  (#node1 AND #node2) => brute{de!} => +#German_hits => +#German_workstream
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class TagOperationType(Enum):
    """Type of tag operation."""
    ADD = "add"           # +#tag
    REMOVE = "remove"     # -#tag
    LINK = "link"         # #workstream (no +/-)


@dataclass
class TagOperation:
    """A single tag operation in a chain."""
    operation: TagOperationType
    tag_name: str
    is_workstream: bool = False  # If true, this links to a narrative note


@dataclass
class TagChain:
    """A chain of tag operations parsed from => syntax."""
    raw_syntax: str
    operations: List[TagOperation] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    # Execution state
    nodes_tagged: int = 0
    nodes_untagged: int = 0
    workstreams_linked: int = 0


# =============================================================================
# PARSING
# =============================================================================

# Pattern: => +#tag or => -#tag or => #workstream
TAG_CHAIN_PATTERN = re.compile(
    r'=>\s*([+-]?)#([\w_]+)',
    re.IGNORECASE
)

# Pattern for workstream indicators (convention: ends with _workstream or _ws)
WORKSTREAM_PATTERN = re.compile(r'.*_(workstream|ws)$', re.IGNORECASE)


def parse_tag_chain(syntax: str) -> TagChain:
    """
    Parse a tag chain from => syntax.

    Args:
        syntax: The raw syntax string containing => operations

    Returns:
        TagChain with parsed operations
    """
    chain = TagChain(raw_syntax=syntax)

    for match in TAG_CHAIN_PATTERN.finditer(syntax):
        modifier = match.group(1)  # + or - or empty
        tag_name = match.group(2)

        # Determine operation type
        if modifier == "+":
            op_type = TagOperationType.ADD
        elif modifier == "-":
            op_type = TagOperationType.REMOVE
        else:
            # No modifier - this is a workstream link
            op_type = TagOperationType.LINK

        # Check if this looks like a workstream
        is_workstream = (
            op_type == TagOperationType.LINK or
            WORKSTREAM_PATTERN.match(tag_name) is not None
        )

        chain.operations.append(TagOperation(
            operation=op_type,
            tag_name=tag_name,
            is_workstream=is_workstream,
        ))

    return chain


def extract_tag_names(chain: TagChain, include_workstreams: bool = True) -> List[str]:
    """Extract all tag names from a chain."""
    tags = []
    for op in chain.operations:
        if include_workstreams or not op.is_workstream:
            tags.append(op.tag_name)
    return tags


# =============================================================================
# TAG APPLICATION
# =============================================================================

def apply_tag_chain(
    chain: TagChain,
    node_ids: List[str],
    graph_provider: Any = None,
) -> TagChain:
    """
    Apply a tag chain to a list of nodes.

    Args:
        chain: The parsed tag chain
        node_ids: Node IDs to apply tags to
        graph_provider: Provider for graph operations

    Returns:
        Updated TagChain with execution stats
    """
    if not graph_provider:
        return chain

    for op in chain.operations:
        if op.operation == TagOperationType.ADD:
            # Add tag to all nodes
            for node_id in node_ids:
                graph_provider.add_tag(node_id, op.tag_name)
                chain.nodes_tagged += 1

        elif op.operation == TagOperationType.REMOVE:
            # Remove tag from all nodes
            for node_id in node_ids:
                graph_provider.remove_tag(node_id, op.tag_name)
                chain.nodes_untagged += 1

        elif op.operation == TagOperationType.LINK:
            # Link to workstream
            if op.is_workstream:
                workstream_id = graph_provider.get_workstream_by_tag(op.tag_name)
                if workstream_id:
                    for node_id in node_ids:
                        graph_provider.link_to_workstream(node_id, workstream_id)
                        chain.workstreams_linked += 1

    return chain


# =============================================================================
# TAG NODES FOR GRAPH
# =============================================================================

def create_tag_node(tag_name: str, batch_id: str = None) -> Dict[str, Any]:
    """Create a tag node for the graph."""
    return {
        "id": f"tag_{tag_name}",
        "type": "tag",
        "class": "tag",
        "label": f"#{tag_name}",
        "properties": {
            "tag_name": tag_name,
            "created_at": datetime.now().isoformat(),
            "batch_id": batch_id,
        }
    }


def create_tag_edge(node_id: str, tag_name: str, batch_id: str = None) -> Dict[str, Any]:
    """Create an edge from a node to a tag."""
    return {
        "source": node_id,
        "target": f"tag_{tag_name}",
        "type": "tagged_with",
        "properties": {
            "applied_at": datetime.now().isoformat(),
            "batch_id": batch_id,
        }
    }


def chain_to_graph_operations(
    chain: TagChain,
    node_ids: List[str],
    batch_id: str = None,
) -> Dict[str, Any]:
    """
    Convert a tag chain to graph operations (nodes and edges).

    Returns dict with:
        - tag_nodes: List of tag nodes to create
        - tag_edges: List of edges from nodes to tags
        - workstream_edges: List of edges to workstreams
    """
    result = {
        "tag_nodes": [],
        "tag_edges": [],
        "workstream_edges": [],
    }

    created_tags = set()

    for op in chain.operations:
        if op.operation == TagOperationType.ADD:
            # Create tag node if not already created
            if op.tag_name not in created_tags:
                result["tag_nodes"].append(create_tag_node(op.tag_name, batch_id))
                created_tags.add(op.tag_name)

            # Create edges from all nodes to tag
            for node_id in node_ids:
                result["tag_edges"].append(create_tag_edge(node_id, op.tag_name, batch_id))

        elif op.operation == TagOperationType.LINK and op.is_workstream:
            # Create edges to workstream
            for node_id in node_ids:
                result["workstream_edges"].append({
                    "source": node_id,
                    "target": f"workstream_{op.tag_name}",  # Will be resolved
                    "type": "part_of_workstream",
                    "properties": {
                        "linked_at": datetime.now().isoformat(),
                        "batch_id": batch_id,
                    }
                })

    return result


# =============================================================================
# BATCH TAG GENERATION
# =============================================================================

def generate_batch_tag(
    node_labels: List[str],
    operation: str,
    filters: Dict[str, Any] = None,
) -> str:
    """
    Generate a batch tag that describes the operation.

    Format: (batch_<labels>_<operation>_<filters>_<timestamp>)

    Examples:
        (batch_john_acme_brute_de_20250101_1430)
        (batch_COMPANY_CY_brute_20250101_1430)
    """
    # First 3 labels
    label_part = "_".join(node_labels[:3])
    if len(node_labels) > 3:
        label_part += f"_+{len(node_labels) - 3}"

    # Operation
    op_part = operation.replace("!", "").replace("?", "")

    # Filters
    filter_parts = []
    if filters:
        for key, val in filters.items():
            if isinstance(val, list):
                filter_parts.extend(v.replace("!", "") for v in val if isinstance(v, str))
            elif isinstance(val, str):
                filter_parts.append(val.replace("!", ""))
    filter_str = "_".join(filter_parts) if filter_parts else ""

    # Timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Combine
    parts = [p for p in ["batch", label_part, op_part, filter_str, timestamp] if p]
    return f"({'_'.join(parts)})"
