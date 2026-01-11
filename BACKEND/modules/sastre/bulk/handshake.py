"""
SASTRE Handshake / Beer Operator

N×N pairwise comparison of all selected entities.
"Everyone meets everyone" - finds similarities, shared attributes, and connections.

Syntax:
  (#john AND #jane AND #acme) => 🤝
  (#node1 AND #node2 AND #node3) => beer
  (#entities) => handshake => +#connected_group

Output:
  - Similarity matrix (N×N)
  - Clusters of similar entities
  - Bridges (entities connecting different clusters)
  - Surprising connections (unexpected similarities)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from itertools import combinations

from .selection import BulkSelection, BatchOperation


@dataclass
class PairwiseComparison:
    """Result of comparing two entities."""
    entity_a_id: str
    entity_a_label: str
    entity_b_id: str
    entity_b_label: str
    similarity_score: float                    # 0.0 to 1.0
    shared_attributes: List[str] = field(default_factory=list)
    shared_connections: List[str] = field(default_factory=list)  # Common related nodes
    shared_sources: List[str] = field(default_factory=list)      # URLs mentioning both
    verdict: str = ""                          # SAME, SIMILAR, DIFFERENT, UNKNOWN
    reasoning: str = ""


@dataclass
class SimilarityCluster:
    """A cluster of similar entities."""
    cluster_id: str
    entity_ids: List[str]
    entity_labels: List[str]
    centroid_id: str                           # Most connected entity in cluster
    avg_similarity: float
    cluster_reason: str = ""                   # Why these cluster together


@dataclass
class ClusterBridge:
    """An entity that bridges two clusters."""
    bridge_entity_id: str
    bridge_entity_label: str
    cluster_a_id: str
    cluster_b_id: str
    connection_strength: float


@dataclass
class HandshakeResult:
    """Complete result of handshake operation."""
    batch_id: str
    selection: BulkSelection
    timestamp: datetime = field(default_factory=datetime.now)

    # Raw comparisons
    comparisons: List[PairwiseComparison] = field(default_factory=list)
    total_pairs: int = 0

    # Aggregated results
    similarity_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    clusters: List[SimilarityCluster] = field(default_factory=list)
    bridges: List[ClusterBridge] = field(default_factory=list)

    # Interesting findings
    strongest_connections: List[PairwiseComparison] = field(default_factory=list)
    surprising_connections: List[PairwiseComparison] = field(default_factory=list)
    isolated_entities: List[str] = field(default_factory=list)


# =============================================================================
# PAIRWISE COMPARISON
# =============================================================================

async def compare_pair(
    entity_a: Dict[str, Any],
    entity_b: Dict[str, Any],
    similarity_engine: Any = None,
    graph_provider: Any = None,
) -> PairwiseComparison:
    """
    Compare two entities and return similarity analysis.

    Uses the existing =? compare operator logic internally.
    """
    comparison = PairwiseComparison(
        entity_a_id=entity_a.get("id", ""),
        entity_a_label=entity_a.get("label", entity_a.get("id", "")),
        entity_b_id=entity_b.get("id", ""),
        entity_b_label=entity_b.get("label", entity_b.get("id", "")),
        similarity_score=0.0,
    )

    # Use similarity engine if available
    if similarity_engine:
        try:
            result = await similarity_engine.compare(
                entity_a.get("id"),
                entity_b.get("id")
            )
            comparison.similarity_score = result.get("score", 0.0)
            comparison.shared_attributes = result.get("shared_attributes", [])
            comparison.verdict = result.get("verdict", "UNKNOWN")
            comparison.reasoning = result.get("reasoning", "")
        except Exception:
            pass

    # Find shared connections via graph
    if graph_provider:
        try:
            # Get related nodes for each entity
            related_a = set(n["id"] for n in graph_provider.get_related_nodes(entity_a["id"]))
            related_b = set(n["id"] for n in graph_provider.get_related_nodes(entity_b["id"]))

            # Shared connections
            shared = related_a & related_b
            comparison.shared_connections = list(shared)

            # Boost similarity if they share connections
            if shared and comparison.similarity_score < 0.5:
                connection_boost = min(len(shared) * 0.1, 0.3)
                comparison.similarity_score += connection_boost

        except Exception:
            pass

    # Determine verdict if not set
    if not comparison.verdict:
        if comparison.similarity_score >= 0.9:
            comparison.verdict = "SAME"
        elif comparison.similarity_score >= 0.7:
            comparison.verdict = "SIMILAR"
        elif comparison.similarity_score >= 0.3:
            comparison.verdict = "RELATED"
        else:
            comparison.verdict = "DIFFERENT"

    return comparison


async def execute_handshake(
    batch: BatchOperation,
    similarity_engine: Any = None,
    graph_provider: Any = None,
) -> HandshakeResult:
    """
    Execute N×N pairwise comparison on all selected entities.

    Args:
        batch: The batch operation with selection
        similarity_engine: Engine for computing similarity scores
        graph_provider: Provider for graph operations

    Returns:
        HandshakeResult with all comparisons and analysis
    """
    selection = batch.selection
    result = HandshakeResult(
        batch_id=batch.id,
        selection=selection,
    )

    # Get all entities from selection
    entities = []
    if graph_provider:
        for node_id in selection.node_ids:
            node = graph_provider.get_node(node_id)
            if node:
                entities.append(node)
    else:
        # Fallback: use labels as entity placeholders
        entities = [
            {"id": nid, "label": label}
            for nid, label in zip(selection.node_ids, selection.node_labels)
        ]

    # Calculate total pairs: N choose 2 = N*(N-1)/2
    n = len(entities)
    result.total_pairs = n * (n - 1) // 2

    # Compare all pairs
    for entity_a, entity_b in combinations(entities, 2):
        comparison = await compare_pair(
            entity_a,
            entity_b,
            similarity_engine,
            graph_provider,
        )
        result.comparisons.append(comparison)

        # Build similarity matrix
        a_id = entity_a.get("id", "")
        b_id = entity_b.get("id", "")

        if a_id not in result.similarity_matrix:
            result.similarity_matrix[a_id] = {}
        if b_id not in result.similarity_matrix:
            result.similarity_matrix[b_id] = {}

        result.similarity_matrix[a_id][b_id] = comparison.similarity_score
        result.similarity_matrix[b_id][a_id] = comparison.similarity_score  # Symmetric

    # Find strongest connections (top 5)
    sorted_comparisons = sorted(
        result.comparisons,
        key=lambda c: c.similarity_score,
        reverse=True
    )
    result.strongest_connections = sorted_comparisons[:5]

    # Find surprising connections (high similarity but different types)
    for comp in result.comparisons:
        if comp.similarity_score >= 0.6:
            # Check if entities are different types
            a_type = _get_entity_type(comp.entity_a_id, graph_provider)
            b_type = _get_entity_type(comp.entity_b_id, graph_provider)
            if a_type and b_type and a_type != b_type:
                result.surprising_connections.append(comp)

    # Find isolated entities (low similarity with everyone)
    for entity in entities:
        entity_id = entity.get("id", "")
        similarities = result.similarity_matrix.get(entity_id, {})
        if similarities:
            avg_sim = sum(similarities.values()) / len(similarities)
            if avg_sim < 0.2:
                result.isolated_entities.append(entity_id)

    # Build clusters
    result.clusters = _build_clusters(result.comparisons, entities)

    # Find bridges between clusters
    result.bridges = _find_bridges(result.clusters, result.similarity_matrix)

    return result


def _get_entity_type(entity_id: str, graph_provider: Any) -> Optional[str]:
    """Get entity type from graph."""
    if not graph_provider:
        return None
    try:
        node = graph_provider.get_node(entity_id)
        return node.get("class") or node.get("type")
    except Exception:
        return None


def _build_clusters(
    comparisons: List[PairwiseComparison],
    entities: List[Dict[str, Any]],
    threshold: float = 0.5,
) -> List[SimilarityCluster]:
    """
    Build clusters of similar entities using simple agglomerative clustering.
    """
    if not comparisons:
        return []

    # Start with each entity in its own cluster
    entity_to_cluster: Dict[str, int] = {}
    clusters: Dict[int, Set[str]] = {}

    for i, entity in enumerate(entities):
        entity_id = entity.get("id", "")
        entity_to_cluster[entity_id] = i
        clusters[i] = {entity_id}

    # Merge clusters based on high similarity
    for comp in sorted(comparisons, key=lambda c: c.similarity_score, reverse=True):
        if comp.similarity_score < threshold:
            break

        a_cluster = entity_to_cluster.get(comp.entity_a_id)
        b_cluster = entity_to_cluster.get(comp.entity_b_id)

        if a_cluster is not None and b_cluster is not None and a_cluster != b_cluster:
            # Merge b_cluster into a_cluster
            for entity_id in clusters[b_cluster]:
                clusters[a_cluster].add(entity_id)
                entity_to_cluster[entity_id] = a_cluster
            del clusters[b_cluster]

    # Convert to SimilarityCluster objects
    result = []
    entity_labels = {e.get("id", ""): e.get("label", "") for e in entities}

    for cluster_id, entity_ids in clusters.items():
        if len(entity_ids) > 1:  # Only include multi-entity clusters
            entity_list = list(entity_ids)
            labels = [entity_labels.get(eid, eid) for eid in entity_list]

            # Find centroid (most connected within cluster)
            centroid = _find_centroid(entity_list, comparisons)

            result.append(SimilarityCluster(
                cluster_id=f"cluster_{cluster_id}",
                entity_ids=entity_list,
                entity_labels=labels,
                centroid_id=centroid,
                avg_similarity=_calculate_avg_similarity(entity_list, comparisons),
                cluster_reason=f"Entities with similarity >= {threshold}",
            ))

    return result


def _find_centroid(entity_ids: List[str], comparisons: List[PairwiseComparison]) -> str:
    """Find the entity most connected to others in the cluster."""
    if not entity_ids:
        return ""
    if len(entity_ids) == 1:
        return entity_ids[0]

    entity_set = set(entity_ids)
    connection_scores: Dict[str, float] = {eid: 0.0 for eid in entity_ids}

    for comp in comparisons:
        if comp.entity_a_id in entity_set and comp.entity_b_id in entity_set:
            connection_scores[comp.entity_a_id] += comp.similarity_score
            connection_scores[comp.entity_b_id] += comp.similarity_score

    return max(connection_scores.keys(), key=lambda k: connection_scores[k])


def _calculate_avg_similarity(
    entity_ids: List[str],
    comparisons: List[PairwiseComparison]
) -> float:
    """Calculate average similarity within a cluster."""
    entity_set = set(entity_ids)
    scores = []

    for comp in comparisons:
        if comp.entity_a_id in entity_set and comp.entity_b_id in entity_set:
            scores.append(comp.similarity_score)

    return sum(scores) / len(scores) if scores else 0.0


def _find_bridges(
    clusters: List[SimilarityCluster],
    similarity_matrix: Dict[str, Dict[str, float]],
) -> List[ClusterBridge]:
    """Find entities that bridge different clusters."""
    bridges = []

    if len(clusters) < 2:
        return bridges

    for i, cluster_a in enumerate(clusters):
        for cluster_b in clusters[i+1:]:
            # Find entities in cluster_a connected to cluster_b
            for entity_id in cluster_a.entity_ids:
                connections_to_b = []
                for other_id in cluster_b.entity_ids:
                    sim = similarity_matrix.get(entity_id, {}).get(other_id, 0)
                    if sim > 0.3:  # Threshold for "connected"
                        connections_to_b.append(sim)

                if connections_to_b:
                    # Get label
                    label_idx = cluster_a.entity_ids.index(entity_id)
                    label = cluster_a.entity_labels[label_idx] if label_idx < len(cluster_a.entity_labels) else entity_id

                    bridges.append(ClusterBridge(
                        bridge_entity_id=entity_id,
                        bridge_entity_label=label,
                        cluster_a_id=cluster_a.cluster_id,
                        cluster_b_id=cluster_b.cluster_id,
                        connection_strength=sum(connections_to_b) / len(connections_to_b),
                    ))

    # Sort by connection strength
    bridges.sort(key=lambda b: b.connection_strength, reverse=True)

    return bridges


# =============================================================================
# RESULT TO GRAPH NODES
# =============================================================================

def handshake_to_graph_node(result: HandshakeResult) -> Dict[str, Any]:
    """Convert handshake result to a graph node for persistence."""
    return {
        "id": f"handshake_{result.batch_id}",
        "type": "handshake_analysis",
        "class": "query",
        "label": f"Handshake: {len(result.selection.node_labels)} entities",
        "properties": {
            "batch_id": result.batch_id,
            "timestamp": result.timestamp.isoformat(),
            "total_pairs": result.total_pairs,
            "total_comparisons": len(result.comparisons),
            "cluster_count": len(result.clusters),
            "bridge_count": len(result.bridges),
            "isolated_count": len(result.isolated_entities),
            "strongest_connection": {
                "entities": [result.strongest_connections[0].entity_a_label,
                           result.strongest_connections[0].entity_b_label],
                "score": result.strongest_connections[0].similarity_score,
            } if result.strongest_connections else None,
        }
    }


def handshake_to_edges(result: HandshakeResult) -> List[Dict[str, Any]]:
    """Create edges from handshake analysis."""
    edges = []

    # Create "similar_to" edges for strong connections
    for comp in result.comparisons:
        if comp.similarity_score >= 0.5:  # Threshold for edge creation
            edges.append({
                "source": comp.entity_a_id,
                "target": comp.entity_b_id,
                "type": "similar_to",
                "properties": {
                    "similarity_score": comp.similarity_score,
                    "verdict": comp.verdict,
                    "shared_attributes": comp.shared_attributes,
                    "shared_connections": comp.shared_connections,
                    "batch_id": result.batch_id,
                    "discovered_at": result.timestamp.isoformat(),
                }
            })

    # Create "part_of_cluster" edges
    for cluster in result.clusters:
        for entity_id in cluster.entity_ids:
            edges.append({
                "source": entity_id,
                "target": cluster.cluster_id,
                "type": "part_of_cluster",
                "properties": {
                    "batch_id": result.batch_id,
                    "is_centroid": entity_id == cluster.centroid_id,
                }
            })

    return edges
