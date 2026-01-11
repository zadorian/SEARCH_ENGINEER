"""
SASTRE Bulk Selection

Parses () selection syntax and creates temporal snapshots.

Syntax:
  (#node1 AND #node2 AND #node3)  - Select multiple nodes
  (@COMPANY ##jurisdiction:CY)    - Select by class + filter

The () creates a SNAPSHOT capturing:
- The selected nodes
- Their related nodes at that moment
- Timestamp of selection
- Auto-generated batch tag
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Set


@dataclass
class NodeSnapshot:
    """Snapshot of a node and its relationships at a point in time."""
    node_id: str
    node_label: str
    node_class: str
    properties: Dict[str, Any] = field(default_factory=dict)
    related_node_ids: List[str] = field(default_factory=list)
    snapshot_time: datetime = field(default_factory=datetime.now)


@dataclass
class BulkSelection:
    """A parsed bulk selection from () syntax."""
    id: str
    raw_syntax: str
    node_ids: List[str]                          # Selected node IDs
    node_labels: List[str]                       # For display
    class_filter: Optional[str] = None           # @COMPANY, @PERSON, etc.
    dimension_filters: Dict[str, str] = field(default_factory=dict)  # ##jurisdiction:CY
    timestamp: datetime = field(default_factory=datetime.now)

    # Snapshots
    node_snapshots: List[NodeSnapshot] = field(default_factory=list)
    related_at_time: List[str] = field(default_factory=list)  # Related node IDs frozen

    # Auto-generated tag
    batch_tag: str = ""


@dataclass
class BatchOperation:
    """A batch operation record for audit trail."""
    id: str
    selection: BulkSelection
    operation: str                               # "brute", "ent?", etc.
    filters: Dict[str, Any] = field(default_factory=dict)  # {"keywords": [], "tld": []}
    output_tags: List[str] = field(default_factory=list)   # Tags to apply to results
    workstream_id: Optional[str] = None          # Linked narrative note

    # Status
    status: str = "pending"                      # pending, running, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Results
    result_count: int = 0
    result_node_ids: List[str] = field(default_factory=list)


# =============================================================================
# PARSING
# =============================================================================

# Pattern: (#node1 AND #node2 AND #node3)
BULK_NODE_PATTERN = re.compile(
    r'\(\s*(#[\w_]+(?:\s+AND\s+#[\w_]+)*)\s*\)',
    re.IGNORECASE
)

# Pattern: (@CLASS ##filter:value)
BULK_CLASS_PATTERN = re.compile(
    r'\(\s*(@\w+)(?:\s+(##\w+:\w+))?\s*\)',
    re.IGNORECASE
)

# Pattern: Extract individual #nodes
NODE_EXTRACT_PATTERN = re.compile(r'#([\w_]+)')

# Pattern: Extract filters ##key:value
FILTER_PATTERN = re.compile(r'##(\w+):(\w+)')


def parse_bulk_selection(syntax: str, graph_provider: Any = None) -> Optional[BulkSelection]:
    """
    Parse bulk selection syntax.

    Args:
        syntax: The raw syntax string, e.g., "(#john AND #acme)"
        graph_provider: Optional provider to resolve node IDs and fetch snapshots

    Returns:
        BulkSelection or None if not valid bulk syntax
    """
    syntax = syntax.strip()

    # Try node-based selection: (#node1 AND #node2)
    node_match = BULK_NODE_PATTERN.match(syntax)
    if node_match:
        inner = node_match.group(1)
        node_labels = NODE_EXTRACT_PATTERN.findall(inner)

        selection = BulkSelection(
            id=f"bulk_{uuid.uuid4().hex[:8]}",
            raw_syntax=syntax,
            node_ids=[],  # Resolved from labels if graph_provider available
            node_labels=node_labels,
            timestamp=datetime.now(),
        )

        # Generate batch tag
        selection.batch_tag = _generate_batch_tag(node_labels)

        # Resolve node IDs and create snapshots if provider available
        if graph_provider:
            _populate_snapshots(selection, graph_provider)

        return selection

    # Try class-based selection: (@COMPANY ##jurisdiction:CY)
    class_match = BULK_CLASS_PATTERN.match(syntax)
    if class_match:
        class_filter = class_match.group(1)
        filter_str = class_match.group(2) if class_match.lastindex >= 2 else None

        dimension_filters = {}
        if filter_str:
            filter_matches = FILTER_PATTERN.findall(filter_str)
            dimension_filters = {k: v for k, v in filter_matches}

        selection = BulkSelection(
            id=f"bulk_{uuid.uuid4().hex[:8]}",
            raw_syntax=syntax,
            node_ids=[],
            node_labels=[],
            class_filter=class_filter,
            dimension_filters=dimension_filters,
            timestamp=datetime.now(),
        )

        # Generate batch tag
        filter_suffix = "_".join(f"{k}{v}" for k, v in dimension_filters.items())
        selection.batch_tag = f"(batch_{class_filter}_{filter_suffix}_{datetime.now().strftime('%Y%m%d_%H%M')})"

        # Resolve matching nodes if provider available
        if graph_provider:
            _populate_class_selection(selection, graph_provider)

        return selection

    return None


def _generate_batch_tag(node_labels: List[str]) -> str:
    """Generate a batch tag from node labels."""
    # Take first 3 labels for readability
    label_part = "_".join(node_labels[:3])
    if len(node_labels) > 3:
        label_part += f"_+{len(node_labels) - 3}"
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    return f"(batch_{label_part}_{timestamp})"


def _populate_snapshots(selection: BulkSelection, graph_provider: Any) -> None:
    """Populate node snapshots from graph provider."""
    for label in selection.node_labels:
        # Resolve label to node ID
        node = graph_provider.get_node_by_label(label)
        if node:
            selection.node_ids.append(node['id'])

            # Get related nodes
            related = graph_provider.get_related_nodes(node['id'])
            related_ids = [r['id'] for r in related]

            snapshot = NodeSnapshot(
                node_id=node['id'],
                node_label=label,
                node_class=node.get('class', 'unknown'),
                properties=node.get('properties', {}),
                related_node_ids=related_ids,
                snapshot_time=selection.timestamp,
            )
            selection.node_snapshots.append(snapshot)
            selection.related_at_time.extend(related_ids)

    # Deduplicate related nodes
    selection.related_at_time = list(set(selection.related_at_time))


def _populate_class_selection(selection: BulkSelection, graph_provider: Any) -> None:
    """Populate selection from class query."""
    nodes = graph_provider.query_nodes_by_class(
        selection.class_filter,
        filters=selection.dimension_filters
    )
    for node in nodes:
        selection.node_ids.append(node['id'])
        selection.node_labels.append(node.get('label', node['id']))

        snapshot = NodeSnapshot(
            node_id=node['id'],
            node_label=node.get('label', node['id']),
            node_class=selection.class_filter,
            properties=node.get('properties', {}),
            related_node_ids=[],  # Could be populated if needed
            snapshot_time=selection.timestamp,
        )
        selection.node_snapshots.append(snapshot)


# =============================================================================
# BATCH OPERATION CREATION
# =============================================================================

def create_batch_operation(
    selection: BulkSelection,
    operation: str,
    filters: Dict[str, Any] = None,
    output_tags: List[str] = None,
    workstream_id: str = None,
) -> BatchOperation:
    """
    Create a batch operation from a selection.

    Args:
        selection: The bulk selection
        operation: Operator to apply (e.g., "brute", "ent?")
        filters: Keyword/TLD filters
        output_tags: Tags to apply to results
        workstream_id: Optional narrative note to link to

    Returns:
        BatchOperation ready for execution
    """
    return BatchOperation(
        id=f"batchop_{uuid.uuid4().hex[:8]}",
        selection=selection,
        operation=operation,
        filters=filters or {},
        output_tags=output_tags or [],
        workstream_id=workstream_id,
    )


def selection_to_graph_node(selection: BulkSelection) -> Dict[str, Any]:
    """Convert a BulkSelection to a graph node for persistence."""
    return {
        "id": selection.id,
        "type": "batch_selection",
        "class": "query",
        "label": f"Batch: {selection.batch_tag}",
        "properties": {
            "raw_syntax": selection.raw_syntax,
            "node_ids": selection.node_ids,
            "node_labels": selection.node_labels,
            "class_filter": selection.class_filter,
            "dimension_filters": selection.dimension_filters,
            "timestamp": selection.timestamp.isoformat(),
            "related_at_time": selection.related_at_time,
            "batch_tag": selection.batch_tag,
        }
    }


def batch_operation_to_graph_node(batch: BatchOperation) -> Dict[str, Any]:
    """Convert a BatchOperation to a graph node for persistence."""
    return {
        "id": batch.id,
        "type": "batch_operation",
        "class": "query",
        "label": f"BatchOp: {batch.operation} on {len(batch.selection.node_ids)} nodes",
        "properties": {
            "selection_id": batch.selection.id,
            "operation": batch.operation,
            "filters": batch.filters,
            "output_tags": batch.output_tags,
            "workstream_id": batch.workstream_id,
            "status": batch.status,
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "result_count": batch.result_count,
            "result_node_ids": batch.result_node_ids,
        }
    }
