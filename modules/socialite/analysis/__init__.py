"""
SOCIALITE Analysis - Social media profile and network analysis tools.

Provides:
- Profile comparison and deduplication
- Network/connection analysis
- Engagement metrics analysis
- Cross-platform identity linking
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProfileMatch:
    """Result of profile comparison."""
    profile_a: Dict[str, Any]
    profile_b: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    matching_fields: List[str] = field(default_factory=list)
    conflicting_fields: List[str] = field(default_factory=list)


@dataclass
class NetworkNode:
    """Node in a social network graph."""
    id: str
    platform: str
    username: str
    display_name: str = ""
    followers: int = 0
    following: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NetworkEdge:
    """Edge between two network nodes."""
    source_id: str
    target_id: str
    relationship: str  # "follows", "friend", "connection", etc.
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngagementMetrics:
    """Engagement statistics for a profile or post."""
    likes: int = 0
    comments: int = 0
    shares: int = 0
    views: int = 0
    engagement_rate: float = 0.0
    period_days: int = 0
    captured_at: str = ""


class ProfileAnalyzer:
    """Analyze and compare social media profiles."""

    def __init__(self):
        self.comparison_weights = {
            "name": 0.3,
            "username": 0.2,
            "email": 0.25,
            "phone": 0.25,
            "location": 0.1,
            "bio": 0.1,
            "profile_image": 0.05,
        }

    def compare_profiles(
        self,
        profile_a: Dict[str, Any],
        profile_b: Dict[str, Any]
    ) -> ProfileMatch:
        """Compare two profiles and return match confidence."""
        matching = []
        conflicting = []
        score = 0.0

        for field_name, weight in self.comparison_weights.items():
            val_a = profile_a.get(field_name, "").lower().strip()
            val_b = profile_b.get(field_name, "").lower().strip()

            if not val_a or not val_b:
                continue

            if val_a == val_b:
                matching.append(field_name)
                score += weight
            else:
                conflicting.append(field_name)

        return ProfileMatch(
            profile_a=profile_a,
            profile_b=profile_b,
            confidence=min(score, 1.0),
            matching_fields=matching,
            conflicting_fields=conflicting,
        )

    def deduplicate_profiles(
        self,
        profiles: List[Dict[str, Any]],
        threshold: float = 0.7
    ) -> List[List[Dict[str, Any]]]:
        """Group profiles that likely belong to the same person."""
        if not profiles:
            return []

        groups: List[Set[int]] = []

        for i, profile_a in enumerate(profiles):
            matched_group = None

            for group in groups:
                for j in group:
                    match = self.compare_profiles(profile_a, profiles[j])
                    if match.confidence >= threshold:
                        matched_group = group
                        break
                if matched_group:
                    break

            if matched_group:
                matched_group.add(i)
            else:
                groups.append({i})

        return [[profiles[i] for i in group] for group in groups]


class NetworkAnalyzer:
    """Analyze social network connections."""

    def __init__(self):
        self.nodes: Dict[str, NetworkNode] = {}
        self.edges: List[NetworkEdge] = []

    def add_node(self, node: NetworkNode) -> None:
        """Add a node to the network."""
        self.nodes[node.id] = node

    def add_edge(self, edge: NetworkEdge) -> None:
        """Add an edge to the network."""
        self.edges.append(edge)

    def get_connections(self, node_id: str) -> List[NetworkNode]:
        """Get all nodes connected to a given node."""
        connected_ids = set()
        for edge in self.edges:
            if edge.source_id == node_id:
                connected_ids.add(edge.target_id)
            elif edge.target_id == node_id:
                connected_ids.add(edge.source_id)

        return [self.nodes[nid] for nid in connected_ids if nid in self.nodes]

    def get_mutual_connections(
        self,
        node_id_a: str,
        node_id_b: str
    ) -> List[NetworkNode]:
        """Get nodes connected to both given nodes."""
        connections_a = set(n.id for n in self.get_connections(node_id_a))
        connections_b = set(n.id for n in self.get_connections(node_id_b))
        mutual = connections_a & connections_b
        return [self.nodes[nid] for nid in mutual if nid in self.nodes]


class EngagementAnalyzer:
    """Analyze engagement metrics."""

    @staticmethod
    def calculate_engagement_rate(
        likes: int,
        comments: int,
        shares: int,
        followers: int
    ) -> float:
        """Calculate engagement rate as percentage."""
        if followers <= 0:
            return 0.0
        total_engagement = likes + comments + shares
        return (total_engagement / followers) * 100

    @staticmethod
    def analyze_posts(posts: List[Dict[str, Any]]) -> EngagementMetrics:
        """Aggregate engagement metrics from multiple posts."""
        if not posts:
            return EngagementMetrics()

        total_likes = sum(p.get("likes", 0) for p in posts)
        total_comments = sum(p.get("comments", 0) for p in posts)
        total_shares = sum(p.get("shares", 0) for p in posts)
        total_views = sum(p.get("views", 0) for p in posts)

        return EngagementMetrics(
            likes=total_likes,
            comments=total_comments,
            shares=total_shares,
            views=total_views,
            captured_at=datetime.utcnow().isoformat(),
        )


__all__ = [
    "ProfileMatch",
    "NetworkNode",
    "NetworkEdge",
    "EngagementMetrics",
    "ProfileAnalyzer",
    "NetworkAnalyzer",
    "EngagementAnalyzer",
]
