"""
Disambiguation physics - cluster mechanics for identity resolution.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class CollisionCluster:
    """Group of potentially identical entities."""
    key: str
    entity_ids: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().strip().split())


def cluster_entities(entities: List[Dict[str, Any]]) -> List[CollisionCluster]:
    """
    Cluster entities by normalized name as a first-pass collision group.
    """
    clusters: Dict[str, CollisionCluster] = {}
    for entity in entities:
        name = entity.get("name") or entity.get("label") or ""
        if not name:
            continue
        key = _normalize_name(name)
        if key not in clusters:
            clusters[key] = CollisionCluster(key=key)
        entity_id = entity.get("id") or entity.get("entity_id") or ""
        if entity_id and entity_id not in clusters[key].entity_ids:
            clusters[key].entity_ids.append(entity_id)
    return [c for c in clusters.values() if len(c.entity_ids) > 1]


def split_cluster_by_attribute(cluster: CollisionCluster, attribute: str) -> List[CollisionCluster]:
    """
    Placeholder for attribute-based splitting (future enrichment).
    """
    cluster.evidence.append(f"split_by:{attribute}")
    return [cluster]
