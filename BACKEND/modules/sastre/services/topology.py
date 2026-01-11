"""
SASTRE Topology Service - Extract narrative topology from investigation state.

Derives Goal → Track → Path hierarchy from the investigation:
- Goal: Each major subject entity or investigation question
- Track: Each narrative item or line of inquiry
- Path: Each query → source → entity chain

This is a READ-ONLY view that projects the flat state into a hierarchical structure.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import hashlib

from ..core.state import (
    InvestigationState,
    NarrativeItem,
    Query,
    SourceResult,
    Entity,
    EntityType,
)
from ..contracts import NarrativeGoal, NarrativeTrack, NarrativePath


@dataclass
class TopologyNode:
    """A node in the topology tree."""
    id: str
    title: str
    type: str  # goal, track, path
    status: str = "active"
    children: List['TopologyNode'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TopologySummary:
    """Summary statistics for the topology."""
    total_goals: int = 0
    total_tracks: int = 0
    total_paths: int = 0
    total_queries: int = 0
    total_sources: int = 0
    total_entities: int = 0
    answered_tracks: int = 0
    pending_tracks: int = 0


def extract_topology(state: InvestigationState) -> Dict[str, Any]:
    """
    Extract topology from investigation state.

    Returns a hierarchical structure:
    {
        "goals": [...],
        "tracks": [...],
        "paths": [...],
        "summary": {...}
    }
    """
    # If state has explicit goals, use them
    if state.goals:
        return _extract_explicit_topology(state)

    # Otherwise, derive from the investigation structure
    return _derive_topology(state)


def _extract_explicit_topology(state: InvestigationState) -> Dict[str, Any]:
    """Extract topology when Goals/Tracks/Paths are explicitly defined."""
    goals = []
    tracks = []
    paths = []

    for goal_id, goal in state.goals.items():
        goal_dict = {
            "id": goal.id,
            "title": goal.title,
            "description": goal.description,
            "status": goal.status,
            "track_ids": goal.track_ids,
        }
        goals.append(goal_dict)

    for track_id, track in state.tracks.items():
        track_dict = {
            "id": track.id,
            "goal_id": track.goal_id,
            "title": track.title,
            "description": track.description,
            "status": track.status,
            "path_ids": track.path_ids,
        }
        tracks.append(track_dict)

    for path_id, path in state.paths.items():
        path_dict = {
            "id": path.id,
            "track_id": path.track_id,
            "title": path.title,
            "description": path.description,
            "status": path.status,
            "query_count": len(path.query_ids),
            "source_count": len(path.source_ids),
            "entity_count": len(path.entity_ids),
        }
        paths.append(path_dict)

    summary = TopologySummary(
        total_goals=len(goals),
        total_tracks=len(tracks),
        total_paths=len(paths),
        total_queries=len(state.queries),
        total_sources=len(state.sources),
        total_entities=len(state.entities),
    )

    return {
        "goals": goals,
        "tracks": tracks,
        "paths": paths,
        "summary": asdict(summary),
    }


def _derive_topology(state: InvestigationState) -> Dict[str, Any]:
    """
    Derive topology from flat investigation structure.

    Strategy:
    - Primary subject entities → Goals
    - Narrative items → Tracks
    - Query chains → Paths
    """
    goals = []
    tracks = []
    paths = []

    # Identify primary subject entities (companies, people with many connections)
    primary_entities = _identify_primary_entities(state)

    # Create a goal for the investigation tasking
    main_goal_id = _hash_id(f"goal:{state.tasking}")
    main_goal = {
        "id": main_goal_id,
        "title": state.tasking[:100],
        "description": f"Investigation: {state.tasking}",
        "status": state.phase.value if hasattr(state.phase, 'value') else str(state.phase),
        "track_ids": [],
    }

    # Create tracks from narrative items
    for narrative_id, item in state.narrative_items.items():
        track_id = _hash_id(f"track:{narrative_id}")
        track = {
            "id": track_id,
            "goal_id": main_goal_id,
            "title": item.question[:80] if item.question else f"Track {track_id[:8]}",
            "description": item.question,
            "status": item.state.value if hasattr(item.state, 'value') else str(item.state),
            "path_ids": [],
        }

        # Create paths from queries linked to this narrative
        query_ids = state.narrative_to_queries.get(narrative_id, [])
        for query_id in query_ids:
            query = state.queries.get(query_id)
            if not query:
                continue

            path_id = _hash_id(f"path:{query_id}")

            # Count sources and entities for this path
            source_ids = state.query_to_sources.get(query_id, [])
            entity_count = 0
            for source_id in source_ids:
                entity_count += len(state.source_to_entities.get(source_id, []))

            path = {
                "id": path_id,
                "track_id": track_id,
                "title": query.macro[:60] if query.macro else f"Query {path_id[:8]}",
                "description": f"K-U: {query.ku_quadrant.value if hasattr(query.ku_quadrant, 'value') else query.ku_quadrant}",
                "status": query.state.value if hasattr(query.state, 'value') else str(query.state),
                "query_count": 1,
                "source_count": len(source_ids),
                "entity_count": entity_count,
            }
            paths.append(path)
            track["path_ids"].append(path_id)

        tracks.append(track)
        main_goal["track_ids"].append(track_id)

    # If no narrative items, create tracks from entities
    if not state.narrative_items and primary_entities:
        for entity in primary_entities[:5]:  # Top 5 entities as tracks
            track_id = _hash_id(f"track:entity:{entity.id}")
            track = {
                "id": track_id,
                "goal_id": main_goal_id,
                "title": entity.name[:80],
                "description": f"{entity.entity_type.value if hasattr(entity.entity_type, 'value') else entity.entity_type}: {entity.name}",
                "status": "active",
                "path_ids": [],
            }
            tracks.append(track)
            main_goal["track_ids"].append(track_id)

    goals.append(main_goal)

    # Count answered vs pending
    answered = sum(1 for t in tracks if t["status"] in ("answered", "complete"))
    pending = len(tracks) - answered

    summary = TopologySummary(
        total_goals=len(goals),
        total_tracks=len(tracks),
        total_paths=len(paths),
        total_queries=len(state.queries),
        total_sources=len(state.sources),
        total_entities=len(state.entities),
        answered_tracks=answered,
        pending_tracks=pending,
    )

    return {
        "goals": goals,
        "tracks": tracks,
        "paths": paths,
        "summary": asdict(summary),
    }


def _identify_primary_entities(state: InvestigationState) -> List[Entity]:
    """Identify primary subject entities (companies, people with connections)."""
    # Score entities by type and connections
    entity_scores = []

    for entity_id, entity in state.entities.items():
        score = 0

        # Type scoring
        if entity.entity_type == EntityType.COMPANY:
            score += 10
        elif entity.entity_type == EntityType.PERSON:
            score += 8
        elif entity.entity_type == EntityType.ORGANIZATION:
            score += 7

        # Connection scoring
        edge_count = sum(1 for e in state.graph.edges
                        if e.source_entity_id == entity_id or e.target_entity_id == entity_id)
        score += edge_count * 2

        # Source coverage scoring
        source_count = sum(1 for s_id, e_ids in state.source_to_entities.items()
                         if entity_id in e_ids)
        score += source_count

        entity_scores.append((entity, score))

    # Sort by score descending
    entity_scores.sort(key=lambda x: x[1], reverse=True)

    return [e for e, s in entity_scores]


def _hash_id(content: str) -> str:
    """Generate a short hash ID."""
    return hashlib.sha256(content.encode()).hexdigest()[:12]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_topology_for_project(project_id: str) -> Dict[str, Any]:
    """
    Get topology for a project by loading the most recent investigation state.

    This is called by the Node.js router.
    """
    # For now, return empty topology
    # In production, this would load from Cymonides or a state store
    return {
        "goals": [],
        "tracks": [],
        "paths": [],
        "summary": {
            "total_goals": 0,
            "total_tracks": 0,
            "total_paths": 0,
            "total_queries": 0,
            "total_sources": 0,
            "total_entities": 0,
            "answered_tracks": 0,
            "pending_tracks": 0,
        }
    }


def topology_to_tree(topology: Dict[str, Any]) -> List[TopologyNode]:
    """Convert flat topology to tree structure for UI rendering."""
    goals = topology.get("goals", [])
    tracks_by_goal = defaultdict(list)
    paths_by_track = defaultdict(list)

    for track in topology.get("tracks", []):
        tracks_by_goal[track.get("goal_id", "")].append(track)

    for path in topology.get("paths", []):
        paths_by_track[path.get("track_id", "")].append(path)

    tree = []
    for goal in goals:
        goal_node = TopologyNode(
            id=goal["id"],
            title=goal["title"],
            type="goal",
            status=goal.get("status", "active"),
            metadata={"description": goal.get("description", "")},
        )

        for track in tracks_by_goal.get(goal["id"], []):
            track_node = TopologyNode(
                id=track["id"],
                title=track["title"],
                type="track",
                status=track.get("status", "active"),
                metadata={"description": track.get("description", "")},
            )

            for path in paths_by_track.get(track["id"], []):
                path_node = TopologyNode(
                    id=path["id"],
                    title=path["title"],
                    type="path",
                    status=path.get("status", "active"),
                    metadata={
                        "query_count": path.get("query_count", 0),
                        "source_count": path.get("source_count", 0),
                        "entity_count": path.get("entity_count", 0),
                    },
                )
                track_node.children.append(path_node)

            goal_node.children.append(track_node)

        tree.append(goal_node)

    return tree
