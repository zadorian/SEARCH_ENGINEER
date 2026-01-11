"""
SASTRE Workstream Linking

Workstreams are narrative notes that explain research intent.
Query nodes attach to workstreams to create audit trails.

A workstream:
- Is a narrative note (class=narrative, type=note)
- Has a tag that identifies it (#German_workstream)
- Collects query nodes that contribute to it
- Tracks progress via attached query results

Example:
  ## German Connections Workstream

  We need to identify which of our subjects appear on German websites,
  particularly in connection with "GmbH" entities.

  Linked Queries:
  - [2024-01-15] brute{de! AND "GmbH"} on john_smith, acme_corp (5 hits)
  - [2024-01-15] brute{de!} on mega_corp (12 hits)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class WorkstreamLink:
    """A link between a query/batch and a workstream."""
    workstream_id: str
    workstream_tag: str
    query_id: str
    batch_id: Optional[str] = None
    linked_at: datetime = field(default_factory=datetime.now)
    result_count: int = 0
    summary: str = ""


@dataclass
class WorkstreamNode:
    """A workstream node in the graph."""
    id: str
    tag: str
    title: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    linked_queries: List[str] = field(default_factory=list)
    total_results: int = 0


# =============================================================================
# WORKSTREAM OPERATIONS
# =============================================================================

def attach_to_workstream(
    workstream_tag: str,
    query_ids: List[str],
    batch_id: str = None,
    result_count: int = 0,
    summary: str = "",
    graph_provider: Any = None,
) -> Optional[WorkstreamLink]:
    """
    Attach queries to a workstream.

    Args:
        workstream_tag: The tag identifying the workstream (e.g., "German_workstream")
        query_ids: Query node IDs to attach
        batch_id: Optional batch operation ID
        result_count: Number of results from this query
        summary: Summary of results
        graph_provider: Provider for graph operations

    Returns:
        WorkstreamLink if successful, None otherwise
    """
    if not graph_provider:
        return None

    # Find workstream by tag
    workstream = graph_provider.get_node_by_tag(workstream_tag)
    if not workstream:
        return None

    # Create links
    for query_id in query_ids:
        graph_provider.create_edge(
            source=query_id,
            target=workstream["id"],
            edge_type="part_of_workstream",
            properties={
                "batch_id": batch_id,
                "linked_at": datetime.now().isoformat(),
            }
        )

    # Update workstream metadata
    linked_queries = workstream.get("properties", {}).get("linked_queries", [])
    linked_queries.extend(query_ids)

    total_results = workstream.get("properties", {}).get("total_results", 0)
    total_results += result_count

    graph_provider.update_node(
        workstream["id"],
        {
            "linked_queries": linked_queries,
            "total_results": total_results,
            "updated_at": datetime.now().isoformat(),
        }
    )

    return WorkstreamLink(
        workstream_id=workstream["id"],
        workstream_tag=workstream_tag,
        query_id=query_ids[0] if query_ids else "",
        batch_id=batch_id,
        result_count=result_count,
        summary=summary,
    )


def get_workstream_queries(
    workstream_tag: str,
    graph_provider: Any = None,
) -> List[Dict[str, Any]]:
    """
    Get all queries linked to a workstream.

    Args:
        workstream_tag: The tag identifying the workstream
        graph_provider: Provider for graph operations

    Returns:
        List of query nodes with their results
    """
    if not graph_provider:
        return []

    # Find workstream by tag
    workstream = graph_provider.get_node_by_tag(workstream_tag)
    if not workstream:
        return []

    # Get all incoming edges of type "part_of_workstream"
    edges = graph_provider.get_edges_to(workstream["id"], edge_type="part_of_workstream")

    # Get the source nodes (queries)
    queries = []
    for edge in edges:
        query_node = graph_provider.get_node(edge["source"])
        if query_node:
            queries.append({
                "query": query_node,
                "linked_at": edge.get("properties", {}).get("linked_at"),
                "batch_id": edge.get("properties", {}).get("batch_id"),
            })

    # Sort by linked_at descending
    queries.sort(
        key=lambda q: q.get("linked_at", ""),
        reverse=True
    )

    return queries


def get_workstream_summary(
    workstream_tag: str,
    graph_provider: Any = None,
) -> Dict[str, Any]:
    """
    Get a summary of a workstream's progress.

    Returns:
        Summary with query count, result count, timeline, etc.
    """
    if not graph_provider:
        return {}

    workstream = graph_provider.get_node_by_tag(workstream_tag)
    if not workstream:
        return {}

    queries = get_workstream_queries(workstream_tag, graph_provider)

    return {
        "workstream_id": workstream["id"],
        "workstream_tag": workstream_tag,
        "title": workstream.get("label", ""),
        "content": workstream.get("properties", {}).get("content", ""),
        "query_count": len(queries),
        "total_results": workstream.get("properties", {}).get("total_results", 0),
        "created_at": workstream.get("properties", {}).get("created_at"),
        "updated_at": workstream.get("properties", {}).get("updated_at"),
        "queries": queries[:10],  # Last 10 queries
    }


# =============================================================================
# WORKSTREAM CREATION
# =============================================================================

def create_workstream_node(
    tag: str,
    title: str,
    content: str,
) -> Dict[str, Any]:
    """
    Create a workstream node for the graph.

    Workstreams are narrative notes that explain research intent.
    """
    return {
        "id": f"workstream_{tag}",
        "type": "note",
        "class": "narrative",
        "label": title,
        "properties": {
            "tag": tag,
            "content": content,
            "linked_queries": [],
            "total_results": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    }


def workstream_to_markdown(
    workstream_tag: str,
    graph_provider: Any = None,
) -> str:
    """
    Convert a workstream to markdown with query history.
    """
    summary = get_workstream_summary(workstream_tag, graph_provider)
    if not summary:
        return f"# Workstream: {workstream_tag}\n\nNo data found."

    lines = [
        f"# {summary.get('title', workstream_tag)}",
        "",
        summary.get('content', ''),
        "",
        f"**Queries:** {summary.get('query_count', 0)}",
        f"**Total Results:** {summary.get('total_results', 0)}",
        "",
        "## Query History",
        "",
    ]

    for q in summary.get("queries", []):
        query_node = q.get("query", {})
        linked_at = q.get("linked_at", "Unknown")
        query_label = query_node.get("label", "Unknown query")
        result_count = query_node.get("properties", {}).get("result_count", 0)

        lines.append(f"- [{linked_at}] {query_label} ({result_count} results)")

    return "\n".join(lines)


# =============================================================================
# WORKSTREAM GRAPH EDGES
# =============================================================================

def create_workstream_edge(
    query_id: str,
    workstream_id: str,
    batch_id: str = None,
) -> Dict[str, Any]:
    """Create an edge from a query to a workstream."""
    return {
        "source": query_id,
        "target": workstream_id,
        "type": "part_of_workstream",
        "properties": {
            "linked_at": datetime.now().isoformat(),
            "batch_id": batch_id,
        }
    }
