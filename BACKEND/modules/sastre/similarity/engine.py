"""
SASTRE Similarity Engine

Computes multi-dimensional similarity between nodes.
Used by the =? operator for identity comparison and similarity search.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Tuple, Any
from difflib import SequenceMatcher
import numpy as np

from .vectors import (
    SimilarityVector,
    SimilarityScore,
    EntityType,
    TimeRange,
)


@dataclass
class DimensionWeight:
    """Weight configuration for a dimension."""
    name: str
    weight: float
    description: str


class SimilarityEngine:
    """
    Compute multi-dimensional similarity between nodes.

    Similarity is computed across:
    - Subject dimensions (entity type, name, attributes, topics)
    - Location dimensions (jurisdictions, sources, time)
    - Relationship dimensions (shared connections, addresses, officers)
    """

    # Default dimension weights (can be overridden)
    DEFAULT_WEIGHTS: Dict[str, float] = {
        "entity_type": 0.10,       # Must be same type
        "name": 0.15,              # Name similarity
        "attributes": 0.15,        # Shared attribute slots
        "topics": 0.10,            # Topic/theme overlap
        "jurisdictions": 0.15,     # Geographic overlap
        "sources": 0.05,           # Same sources
        "time_overlap": 0.10,      # Temporal overlap
        "shared_connections": 0.20,  # Structural similarity (highest weight)
    }

    # Thresholds
    HIGH_SIMILARITY_THRESHOLD = 0.7
    LOW_SIMILARITY_THRESHOLD = 0.3

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize engine with optional custom weights.

        Args:
            weights: Custom dimension weights (default weights used for missing keys)
        """
        self.weights = self.DEFAULT_WEIGHTS.copy()
        if weights:
            self.weights.update(weights)

    def compute_similarity(
        self,
        a: SimilarityVector,
        b: SimilarityVector
    ) -> SimilarityScore:
        """
        Compute weighted similarity across all dimensions.

        Returns score 0.0 - 1.0 plus breakdown by dimension.
        """
        scores: Dict[str, float] = {}

        # Entity type match (binary)
        scores["entity_type"] = 1.0 if a.entity_type == b.entity_type else 0.0

        # Name similarity
        scores["name"] = self._name_similarity(a.name, b.name, a.name_embedding, b.name_embedding)

        # Attribute overlap (Jaccard on filled slots)
        scores["attributes"] = self._jaccard(a.attribute_keys(), b.attribute_keys())

        # Topic overlap
        scores["topics"] = self._jaccard(a.topics, b.topics)

        # Jurisdiction overlap
        scores["jurisdictions"] = self._jaccard(a.jurisdictions, b.jurisdictions)

        # Source overlap
        scores["sources"] = self._jaccard(a.sources, b.sources)

        # Temporal overlap
        scores["time_overlap"] = a.time_range.overlap_ratio(b.time_range) if a.time_range.is_set and b.time_range.is_set else 0.0

        # Shared connections (structural similarity)
        scores["shared_connections"] = self._connection_similarity(a, b)

        # Compute weighted total
        total = sum(
            scores[dim] * self.weights.get(dim, 0.0)
            for dim in scores
        )

        # Normalize by total weight
        total_weight = sum(self.weights.get(dim, 0.0) for dim in scores)
        if total_weight > 0:
            total = total / total_weight
        else:
            total = 0.0

        # Identify high/low dimensions
        high_dims = [dim for dim, score in scores.items() if score > self.HIGH_SIMILARITY_THRESHOLD]
        low_dims = [dim for dim, score in scores.items() if score < self.LOW_SIMILARITY_THRESHOLD]

        return SimilarityScore(
            total=total,
            breakdown=scores,
            explanation=self._explain_similarity(scores, high_dims),
            high_dimensions=high_dims,
            low_dimensions=low_dims,
        )

    def _name_similarity(
        self,
        name_a: str,
        name_b: str,
        embedding_a: Optional[np.ndarray] = None,
        embedding_b: Optional[np.ndarray] = None
    ) -> float:
        """
        Compute name similarity.

        Uses embeddings if available, falls back to string similarity.
        """
        if embedding_a is not None and embedding_b is not None:
            return self._cosine_similarity(embedding_a, embedding_b)

        # Normalize names
        a_norm = self._normalize_name(name_a)
        b_norm = self._normalize_name(name_b)

        if not a_norm or not b_norm:
            return 0.0

        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison."""
        if not name:
            return ""

        # Lowercase
        name = name.lower().strip()

        # Remove common suffixes
        for suffix in [" ltd", " ltd.", " limited", " inc", " inc.", " corp", " corp.", " llc", " llp", " plc", " gmbh", " ag", " sa", " bv", " nv"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()

        # Remove punctuation except hyphens
        name = "".join(c if c.isalnum() or c in " -" else "" for c in name)

        # Normalize whitespace
        name = " ".join(name.split())

        return name

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between vectors."""
        if a.size == 0 or b.size == 0:
            return 0.0

        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot / (norm_a * norm_b))

    def _jaccard(self, a: Set, b: Set) -> float:
        """Compute Jaccard similarity between sets."""
        if not a and not b:
            return 0.0
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    def _connection_similarity(self, a: SimilarityVector, b: SimilarityVector) -> float:
        """
        Compute structural similarity based on shared connections.

        This is the most important signal - entities that share connections
        are likely related even if names differ.
        """
        # Direct connections
        shared_direct = len(a.connected_entities & b.connected_entities)

        # Shared addresses
        shared_addr = len(a.shared_addresses & b.shared_addresses)

        # Shared officers (for companies)
        shared_off = len(a.shared_officers & b.shared_officers)
        shared_dir = len(a.shared_directors & b.shared_directors)
        shared_sh = len(a.shared_shareholders & b.shared_shareholders)

        # Shared companies (for people)
        shared_comp = len(a.shared_companies & b.shared_companies)

        # Formation agent (strong signal)
        agent_match = 0
        if a.formation_agent and b.formation_agent and a.formation_agent == b.formation_agent:
            agent_match = 1

        # Total shared
        total_shared = (
            shared_direct +
            shared_addr * 2 +  # Addresses are strong signal
            shared_off +
            shared_dir +
            shared_sh +
            shared_comp +
            agent_match * 2  # Formation agent is strong signal
        )

        # Max possible (use max of either's connections)
        max_possible = max(
            len(a.all_relationships()) + len(b.all_relationships()),
            1
        )

        return min(total_shared / max_possible, 1.0)

    def _explain_similarity(self, scores: Dict[str, float], high_dims: List[str]) -> str:
        """Generate human-readable explanation of similarity."""
        if not high_dims:
            return "Low similarity across all dimensions"

        # Map dimension names to readable descriptions
        readable = {
            "entity_type": "same type",
            "name": "similar names",
            "attributes": "shared attributes",
            "topics": "common topics",
            "jurisdictions": "same jurisdictions",
            "sources": "same sources",
            "time_overlap": "overlapping time periods",
            "shared_connections": "shared connections",
        }

        high_readable = [readable.get(dim, dim) for dim in high_dims]
        return f"High similarity in: {', '.join(high_readable)}"

    def find_similar(
        self,
        target: SimilarityVector,
        candidates: List[SimilarityVector],
        limit: int = 10,
        min_score: float = 0.1,
        exclude_linked: bool = False,
        linked_ids: Optional[Set[str]] = None
    ) -> List[Tuple[SimilarityVector, SimilarityScore]]:
        """
        Find nodes most similar to target.

        Args:
            target: Target vector to compare against
            candidates: List of candidate vectors
            limit: Maximum number of results
            min_score: Minimum similarity score to include
            exclude_linked: If True, exclude already-linked nodes
            linked_ids: Set of node IDs that are linked to target

        Returns:
            List of (vector, score) tuples sorted by score descending
        """
        linked_ids = linked_ids or set()
        results = []

        for candidate in candidates:
            # Skip self
            if candidate.node_id == target.node_id:
                continue

            # Skip linked if requested
            if exclude_linked and candidate.node_id in linked_ids:
                continue

            score = self.compute_similarity(target, candidate)

            if score.total >= min_score:
                results.append((candidate, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1].total, reverse=True)

        return results[:limit]

    def cluster(
        self,
        vectors: List[SimilarityVector],
        threshold: float = 0.6
    ) -> List[List[SimilarityVector]]:
        """
        Cluster vectors by similarity using agglomerative clustering.

        Args:
            vectors: List of vectors to cluster
            threshold: Similarity threshold for merging clusters

        Returns:
            List of clusters (each cluster is a list of vectors)
        """
        if not vectors:
            return []

        n = len(vectors)
        if n == 1:
            return [vectors]

        # Build similarity matrix
        similarity_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                score = self.compute_similarity(vectors[i], vectors[j])
                similarity_matrix[i][j] = score.total
                similarity_matrix[j][i] = score.total

        # Simple agglomerative clustering
        # Start with each vector in its own cluster
        clusters = [[i] for i in range(n)]

        while len(clusters) > 1:
            # Find most similar pair of clusters
            best_sim = -1
            best_pair = (0, 1)

            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    # Average linkage
                    sim = np.mean([
                        similarity_matrix[a][b]
                        for a in clusters[i]
                        for b in clusters[j]
                    ])
                    if sim > best_sim:
                        best_sim = sim
                        best_pair = (i, j)

            # Stop if best similarity is below threshold
            if best_sim < threshold:
                break

            # Merge clusters
            i, j = best_pair
            clusters[i].extend(clusters[j])
            clusters.pop(j)

        # Convert indices back to vectors
        return [[vectors[idx] for idx in cluster] for cluster in clusters]

    def find_bridges(
        self,
        targets: List[SimilarityVector],
        candidates: List[SimilarityVector],
        min_similarity: float = 0.3,
        limit: int = 10
    ) -> List[Tuple[SimilarityVector, Dict[str, SimilarityScore]]]:
        """
        Find entities similar to multiple targets (potential bridges).

        Args:
            targets: Target vectors to find bridges between
            candidates: Candidate vectors to check
            min_similarity: Minimum similarity to ALL targets
            limit: Maximum number of results

        Returns:
            List of (bridge_vector, {target_id: score}) tuples
        """
        target_ids = {t.node_id for t in targets}
        bridges = []

        for candidate in candidates:
            # Skip targets themselves
            if candidate.node_id in target_ids:
                continue

            # Compute similarity to each target
            target_scores = {}
            min_score = 1.0

            for target in targets:
                score = self.compute_similarity(candidate, target)
                target_scores[target.node_id] = score
                min_score = min(min_score, score.total)

            # Must be at least somewhat similar to ALL targets
            if min_score >= min_similarity:
                bridges.append((candidate, target_scores))

        # Sort by minimum similarity (best bridges are similar to all targets)
        bridges.sort(
            key=lambda x: min(s.total for s in x[1].values()),
            reverse=True
        )

        return bridges[:limit]
