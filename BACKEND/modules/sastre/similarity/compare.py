"""
SASTRE Compare Operator (=?)

The most powerful operator in the system.
Computes multi-dimensional similarity between nodes.

Forms:
- =? :#a #b               Compare specific nodes
- =? :#target :@CLASS     Find similar in class
- =? :#target :@CLASS ##unlinked  Find similar but unconnected
- =? :@CLASS ##cluster    Cluster by similarity
- =? :#a :#b :@CLASS ##bridge  Find bridge entities
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum

from .vectors import SimilarityVector, SimilarityScore, build_vector_from_node
from .engine import SimilarityEngine


class IdentityVerdict(Enum):
    """Result of identity comparison."""
    FUSE = "fuse"                     # High confidence same entity - merge recommended
    REPEL = "repel"                   # Confirmed different entities - keep separate
    BINARY_STAR = "binary_star"       # Related but distinct (father/son, shell/parent)
    INCONCLUSIVE = "inconclusive"     # Need more data - wedge queries suggested


class CompareMode(Enum):
    """Mode of comparison operation."""
    IDENTITY = "identity"       # Compare specific nodes: =? :#a #b
    SIMILARITY = "similarity"   # Find similar: =? :#target :@CLASS
    CLUSTER = "cluster"         # Cluster: =? :@CLASS ##cluster
    BRIDGE = "bridge"           # Find bridges: =? :#a :#b :@CLASS ##bridge
    ANOMALY = "anomaly"         # Find anomalies: =? :#typical :@CLASS ##anomaly


@dataclass
class PairComparison:
    """Result of comparing two specific nodes."""
    node_a_id: str
    node_b_id: str
    score: SimilarityScore
    verdict: IdentityVerdict
    repel_reasons: List[str] = field(default_factory=list)
    fuse_reasons: List[str] = field(default_factory=list)
    wedge_queries: List[str] = field(default_factory=list)  # Suggested disambiguation queries


@dataclass
class SimilarEntity:
    """A similar entity from similarity search."""
    node_id: str
    score: SimilarityScore
    is_linked: bool               # Already has edge to target
    why_similar: str              # Explanation


@dataclass
class Cluster:
    """A cluster of similar entities."""
    cluster_id: int
    members: List[str]            # Node IDs in cluster
    centroid_id: Optional[str]    # Most central node
    avg_similarity: float


@dataclass
class BridgeEntity:
    """An entity that bridges multiple targets."""
    node_id: str
    min_similarity: float         # Lowest similarity to any target
    avg_similarity: float         # Average similarity to all targets
    target_scores: Dict[str, float]  # Similarity to each target


@dataclass
class CompareResult:
    """Result of a compare operation."""
    mode: CompareMode
    query: str

    # For identity mode
    comparisons: List[PairComparison] = field(default_factory=list)
    overall_verdict: Optional[IdentityVerdict] = None

    # For similarity mode
    target_id: Optional[str] = None
    similar: List[SimilarEntity] = field(default_factory=list)

    # For cluster mode
    clusters: List[Cluster] = field(default_factory=list)

    # For bridge mode
    target_ids: List[str] = field(default_factory=list)
    bridges: List[BridgeEntity] = field(default_factory=list)

    # For anomaly mode
    typical_id: Optional[str] = None
    anomalies: List[SimilarEntity] = field(default_factory=list)


class CompareOperator:
    """
    The =? operator: compare and similarity search.

    This operator powers:
    - Identity resolution (are these the same person?)
    - Similarity search (what else looks like this?)
    - Clustering (group similar entities)
    - Bridge finding (what connects these groups?)
    - Anomaly detection (what doesn't fit?)
    """

    # Thresholds for verdicts
    FUSE_THRESHOLD = 0.85
    REPEL_THRESHOLD = 0.30
    BINARY_STAR_CONNECTION_THRESHOLD = 0.8
    BINARY_STAR_NAME_THRESHOLD = 0.5

    def __init__(
        self,
        similarity_engine: Optional[SimilarityEngine] = None,
        state_provider: Optional[Any] = None
    ):
        """
        Initialize compare operator.

        Args:
            similarity_engine: Engine for computing similarity
            state_provider: Provider for getting nodes from state/graph
        """
        self.engine = similarity_engine or SimilarityEngine()
        self.state = state_provider

    def compare_nodes(
        self,
        node_ids: List[str],
        nodes: Optional[Dict[str, Dict]] = None
    ) -> CompareResult:
        """
        Compare specific nodes for identity resolution.

        Args:
            node_ids: List of node IDs to compare
            nodes: Optional dict of node_id -> node_data (if not using state provider)

        Returns:
            CompareResult with pairwise comparisons and overall verdict
        """
        # Get node data
        if nodes:
            node_data = {nid: nodes.get(nid, {}) for nid in node_ids}
        elif self.state:
            node_data = {nid: self.state.get_node(nid) for nid in node_ids}
        else:
            raise ValueError("No nodes provided and no state provider configured")

        # Build vectors
        vectors = {
            nid: build_vector_from_node(data)
            for nid, data in node_data.items()
            if data
        }

        # Pairwise comparison
        comparisons = []
        ids = list(vectors.keys())

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                a_vec, b_vec = vectors[a_id], vectors[b_id]

                score = self.engine.compute_similarity(a_vec, b_vec)
                verdict, repel_reasons, fuse_reasons = self._determine_verdict(
                    a_vec, b_vec, score
                )
                wedge_queries = self._suggest_wedge_queries(a_vec, b_vec, score, verdict)

                comparisons.append(PairComparison(
                    node_a_id=a_id,
                    node_b_id=b_id,
                    score=score,
                    verdict=verdict,
                    repel_reasons=repel_reasons,
                    fuse_reasons=fuse_reasons,
                    wedge_queries=wedge_queries,
                ))

        # Aggregate verdict
        overall = self._aggregate_verdict(comparisons)

        return CompareResult(
            mode=CompareMode.IDENTITY,
            query=f"=? :{' '.join('#' + nid for nid in node_ids)}",
            comparisons=comparisons,
            overall_verdict=overall,
        )

    def find_similar(
        self,
        target_id: str,
        search_class: str,
        candidates: Optional[List[Dict]] = None,
        filters: Optional[List[str]] = None,
        limit: int = 10,
        exclude_linked: bool = False,
        target_node: Optional[Dict] = None
    ) -> CompareResult:
        """
        Find entities most similar to target.

        Args:
            target_id: Target node ID
            search_class: Node class to search (@COMPANY, @PERSON, etc.)
            candidates: Optional list of candidate nodes
            filters: Dimension filters (##jurisdiction:CY, ##unlinked, etc.)
            limit: Max results
            exclude_linked: If True, exclude already-linked nodes
            target_node: Optional target node data

        Returns:
            CompareResult with ranked similar entities
        """
        filters = filters or []

        # Get target
        if target_node:
            target_data = target_node
        elif self.state:
            target_data = self.state.get_node(target_id)
        else:
            raise ValueError("No target node provided")

        target_vec = build_vector_from_node(target_data)

        # Get candidates
        if candidates is not None:
            candidate_data = candidates
        elif self.state:
            candidate_data = self.state.get_nodes_by_class(search_class)
        else:
            raise ValueError("No candidates provided")

        # Build candidate vectors
        candidate_vecs = [
            build_vector_from_node(c)
            for c in candidate_data
            if c.get("id") != target_id
        ]

        # Apply filters
        candidate_vecs = self._apply_filters(candidate_vecs, filters)

        # Handle ##unlinked filter
        linked_ids: Set[str] = set()
        if "##unlinked" in filters or exclude_linked:
            if self.state:
                linked_ids = self.state.get_connected_node_ids(target_id)
            candidate_vecs = [
                c for c in candidate_vecs
                if c.node_id not in linked_ids
            ]

        # Find similar
        results = self.engine.find_similar(
            target_vec,
            candidate_vecs,
            limit=limit,
            linked_ids=linked_ids,
        )

        # Convert to result format
        similar = []
        for vec, score in results:
            is_linked = vec.node_id in linked_ids
            similar.append(SimilarEntity(
                node_id=vec.node_id,
                score=score,
                is_linked=is_linked,
                why_similar=score.explanation,
            ))

        return CompareResult(
            mode=CompareMode.SIMILARITY,
            query=f"=? :#{target_id} :{search_class}",
            target_id=target_id,
            similar=similar,
        )

    def cluster_by_similarity(
        self,
        search_class: str,
        candidates: Optional[List[Dict]] = None,
        filters: Optional[List[str]] = None,
        threshold: float = 0.6
    ) -> CompareResult:
        """
        Cluster entities by similarity.

        Args:
            search_class: Node class to cluster
            candidates: Optional list of candidate nodes
            filters: Dimension filters
            threshold: Similarity threshold for merging clusters

        Returns:
            CompareResult with clusters
        """
        filters = filters or []

        # Get candidates
        if candidates is not None:
            candidate_data = candidates
        elif self.state:
            candidate_data = self.state.get_nodes_by_class(search_class)
        else:
            raise ValueError("No candidates provided")

        # Build vectors
        vectors = [build_vector_from_node(c) for c in candidate_data]

        # Apply filters
        vectors = self._apply_filters(vectors, filters)

        if not vectors:
            return CompareResult(
                mode=CompareMode.CLUSTER,
                query=f"=? :{search_class} ##cluster",
                clusters=[],
            )

        # Cluster
        raw_clusters = self.engine.cluster(vectors, threshold=threshold)

        # Convert to result format
        clusters = []
        for i, member_vecs in enumerate(raw_clusters):
            member_ids = [v.node_id for v in member_vecs]

            # Find centroid (most similar to all others)
            centroid_id = None
            if len(member_vecs) > 1:
                best_avg = -1
                for v in member_vecs:
                    avg = sum(
                        self.engine.compute_similarity(v, other).total
                        for other in member_vecs if other.node_id != v.node_id
                    ) / (len(member_vecs) - 1)
                    if avg > best_avg:
                        best_avg = avg
                        centroid_id = v.node_id
            else:
                centroid_id = member_ids[0]
                best_avg = 1.0

            clusters.append(Cluster(
                cluster_id=i,
                members=member_ids,
                centroid_id=centroid_id,
                avg_similarity=best_avg,
            ))

        return CompareResult(
            mode=CompareMode.CLUSTER,
            query=f"=? :{search_class} ##cluster",
            clusters=clusters,
        )

    def find_bridges(
        self,
        target_ids: List[str],
        search_class: str,
        candidates: Optional[List[Dict]] = None,
        target_nodes: Optional[Dict[str, Dict]] = None,
        min_similarity: float = 0.3,
        limit: int = 10
    ) -> CompareResult:
        """
        Find entities similar to multiple targets (potential bridges).

        Args:
            target_ids: Target node IDs to find bridges between
            search_class: Node class to search
            candidates: Optional candidate nodes
            target_nodes: Optional target node data
            min_similarity: Minimum similarity to ALL targets
            limit: Max results

        Returns:
            CompareResult with bridge entities
        """
        # Get target vectors
        if target_nodes:
            target_vecs = [
                build_vector_from_node(target_nodes[tid])
                for tid in target_ids
                if tid in target_nodes
            ]
        elif self.state:
            target_vecs = [
                build_vector_from_node(self.state.get_node(tid))
                for tid in target_ids
            ]
        else:
            raise ValueError("No target nodes provided")

        # Get candidates
        if candidates is not None:
            candidate_data = candidates
        elif self.state:
            candidate_data = self.state.get_nodes_by_class(search_class)
        else:
            raise ValueError("No candidates provided")

        candidate_vecs = [
            build_vector_from_node(c)
            for c in candidate_data
            if c.get("id") not in target_ids
        ]

        # Find bridges
        bridge_results = self.engine.find_bridges(
            target_vecs,
            candidate_vecs,
            min_similarity=min_similarity,
            limit=limit,
        )

        # Convert to result format
        bridges = []
        for vec, target_scores in bridge_results:
            min_sim = min(s.total for s in target_scores.values())
            avg_sim = sum(s.total for s in target_scores.values()) / len(target_scores)

            bridges.append(BridgeEntity(
                node_id=vec.node_id,
                min_similarity=min_sim,
                avg_similarity=avg_sim,
                target_scores={tid: s.total for tid, s in target_scores.items()},
            ))

        return CompareResult(
            mode=CompareMode.BRIDGE,
            query=f"=? :{' '.join('#' + tid for tid in target_ids)} :{search_class} ##bridge",
            target_ids=target_ids,
            bridges=bridges,
        )

    def _determine_verdict(
        self,
        a: SimilarityVector,
        b: SimilarityVector,
        score: SimilarityScore
    ) -> Tuple[IdentityVerdict, List[str], List[str]]:
        """
        Determine FUSE/REPEL/BINARY_STAR/INCONCLUSIVE verdict.

        Returns:
            (verdict, repel_reasons, fuse_reasons)
        """
        repel_reasons = []
        fuse_reasons = []

        # Check for automatic REPEL signals
        if a.entity_type != b.entity_type:
            repel_reasons.append(f"Different entity types: {a.entity_type.value} vs {b.entity_type.value}")
            return IdentityVerdict.REPEL, repel_reasons, fuse_reasons

        # Check for automatic FUSE signals (same unique identifier)
        for key in ["ssn", "ein", "company_number", "registration_number"]:
            a_val = a.core_attributes.get(key)
            b_val = b.core_attributes.get(key)
            if a_val and b_val:
                if a_val == b_val:
                    fuse_reasons.append(f"Same {key}: {a_val}")
                    return IdentityVerdict.FUSE, repel_reasons, fuse_reasons
                else:
                    repel_reasons.append(f"Different {key}: {a_val} vs {b_val}")
                    return IdentityVerdict.REPEL, repel_reasons, fuse_reasons

        # Score-based determination
        if score.total > self.FUSE_THRESHOLD:
            # Check if BINARY_STAR (related but distinct)
            if self._appears_related_not_same(a, b, score):
                return IdentityVerdict.BINARY_STAR, repel_reasons, fuse_reasons
            fuse_reasons.append(f"High overall similarity: {score.total:.1%}")
            return IdentityVerdict.FUSE, repel_reasons, fuse_reasons

        elif score.total < self.REPEL_THRESHOLD:
            repel_reasons.append(f"Low overall similarity: {score.total:.1%}")
            return IdentityVerdict.REPEL, repel_reasons, fuse_reasons

        else:
            return IdentityVerdict.INCONCLUSIVE, repel_reasons, fuse_reasons

    def _appears_related_not_same(
        self,
        a: SimilarityVector,
        b: SimilarityVector,
        score: SimilarityScore
    ) -> bool:
        """Check if entities are related but distinct (father/son, shell/parent)."""
        # High shared connections but different names
        connections = score.breakdown.get("shared_connections", 0)
        name_sim = score.breakdown.get("name", 0)

        if connections > self.BINARY_STAR_CONNECTION_THRESHOLD and name_sim < self.BINARY_STAR_NAME_THRESHOLD:
            return True

        # Same address, different company types
        if a.shared_addresses & b.shared_addresses:
            if a.corporate_structure != b.corporate_structure:
                return True

        return False

    def _suggest_wedge_queries(
        self,
        a: SimilarityVector,
        b: SimilarityVector,
        score: SimilarityScore,
        verdict: IdentityVerdict
    ) -> List[str]:
        """Suggest disambiguation queries for INCONCLUSIVE verdict."""
        if verdict != IdentityVerdict.INCONCLUSIVE:
            return []

        queries = []

        # If name is ambiguous, search for distinguishing attributes
        if score.breakdown.get("name", 0) > 0.5:
            # Look for DOB
            if "dob" not in a.core_attributes and "dob" not in b.core_attributes:
                queries.append(f'"{a.name}" date of birth')

            # Look for other identifiers
            queries.append(f'"{a.name}" company registry')
            queries.append(f'"{a.name}" LinkedIn profile')

        # If jurisdictions don't overlap, look for connections
        if not (a.jurisdictions & b.jurisdictions):
            for jur in a.jurisdictions:
                queries.append(f'"{b.name}" {jur}')

        return queries[:3]

    def _aggregate_verdict(self, comparisons: List[PairComparison]) -> IdentityVerdict:
        """Aggregate verdict from multiple pairwise comparisons."""
        if not comparisons:
            return IdentityVerdict.INCONCLUSIVE

        verdicts = [c.verdict for c in comparisons]

        # Any REPEL = overall REPEL
        if IdentityVerdict.REPEL in verdicts:
            return IdentityVerdict.REPEL

        # All FUSE = overall FUSE
        if all(v == IdentityVerdict.FUSE for v in verdicts):
            return IdentityVerdict.FUSE

        # Any BINARY_STAR = overall BINARY_STAR
        if IdentityVerdict.BINARY_STAR in verdicts:
            return IdentityVerdict.BINARY_STAR

        return IdentityVerdict.INCONCLUSIVE

    def _apply_filters(
        self,
        vectors: List[SimilarityVector],
        filters: List[str]
    ) -> List[SimilarityVector]:
        """Apply dimension filters to vectors."""
        result = vectors

        for f in filters:
            if f.startswith("##jurisdiction:"):
                jur = f.split(":")[1].upper()
                result = [v for v in result if jur in v.jurisdictions]
            elif f.startswith("##source:"):
                src = f.split(":")[1]
                result = [v for v in result if src in v.sources]
            elif f.startswith("##") and f[2:].isdigit():
                # Year filter - check time range
                year = int(f[2:])
                result = [
                    v for v in result
                    if v.time_range.is_set and
                    (v.time_range.start is None or v.time_range.start.year <= year) and
                    (v.time_range.end is None or v.time_range.end.year >= year)
                ]
            # ##unlinked is handled separately in find_similar

        return result
