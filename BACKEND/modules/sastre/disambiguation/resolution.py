"""
SASTRE Resolution Engine - Applies disambiguation decisions.

Once we've determined FUSE, REPEL, or BINARY_STAR, this module
executes the resolution:

FUSE: Merge entities, combine attributes, track provenance
REPEL: Separate entities, mark as distinct
BINARY_STAR: Create linked pair, both exist but are connected

The physics metaphor:
- FUSE = gravitational collapse (same entity)
- REPEL = electromagnetic repulsion (different entities)
- BINARY_STAR = orbital binding (distinct but connected)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import hashlib
import json

from ..core.state import (
    Entity, EntityCollision, Resolution, DisambiguationAction,
    Attribute, EntityType, EntityGraph, Edge
)

# Alias for backward compatibility
EntityAttribute = Attribute


# =============================================================================
# RESOLUTION RESULT
# =============================================================================

@dataclass
class FuseResult:
    """Result of a FUSE operation."""
    merged_entity: Entity
    absorbed_entity_ids: List[str]
    attribute_conflicts: List[Dict[str, Any]]
    provenance: List[Dict[str, Any]]


@dataclass
class RepelResult:
    """Result of a REPEL operation."""
    entity_a: Entity
    entity_b: Entity
    distinguishing_attributes: List[str]
    never_merge_flag: bool


@dataclass
class BinaryStarResult:
    """Result of a BINARY_STAR operation."""
    entity_a: Entity
    entity_b: Entity
    binding_type: str  # e.g., "family", "business", "alias"
    binding_evidence: List[str]


@dataclass
class ResolutionResult:
    """Overall resolution result."""
    action: DisambiguationAction
    fuse_result: Optional[FuseResult] = None
    repel_result: Optional[RepelResult] = None
    binary_star_result: Optional[BinaryStarResult] = None
    graph_updates: List[Dict[str, Any]] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# RESOLUTION ENGINE
# =============================================================================

class ResolutionEngine:
    """
    Executes disambiguation resolutions.

    Takes a collision and resolution decision, applies the appropriate
    physics to the entity graph.
    """

    def __init__(self, graph: EntityGraph = None):
        self.graph = graph or EntityGraph()

    def resolve(
        self,
        entity_a: Entity,
        entity_b: Entity,
        collision: EntityCollision,
        resolution: Resolution
    ) -> ResolutionResult:
        """
        Execute a resolution.
        """
        audit_trail = [{
            'timestamp': datetime.utcnow().isoformat(),
            'action': resolution.action.value,
            'confidence': resolution.confidence,
            'reason': resolution.reason,
            'entity_a_id': entity_a.entity_id,
            'entity_b_id': entity_b.entity_id,
        }]

        result = ResolutionResult(
            action=resolution.action,
            audit_trail=audit_trail,
        )

        if resolution.action == DisambiguationAction.FUSE:
            result.fuse_result = self._execute_fuse(entity_a, entity_b, resolution)
            result.graph_updates = self._build_fuse_updates(result.fuse_result)

        elif resolution.action == DisambiguationAction.REPEL:
            result.repel_result = self._execute_repel(entity_a, entity_b, resolution)
            result.graph_updates = self._build_repel_updates(result.repel_result)

        elif resolution.action == DisambiguationAction.BINARY_STAR:
            result.binary_star_result = self._execute_binary_star(entity_a, entity_b, resolution)
            result.graph_updates = self._build_binary_star_updates(result.binary_star_result)

        return result

    def _execute_fuse(
        self,
        entity_a: Entity,
        entity_b: Entity,
        resolution: Resolution
    ) -> FuseResult:
        """
        Execute FUSE - merge two entities into one.

        Strategy:
        1. Choose primary entity (higher confidence or more data)
        2. Merge attributes with conflict resolution
        3. Track provenance of merged attributes
        4. Create unified entity
        """
        # Determine primary entity
        primary, secondary = self._choose_primary(entity_a, entity_b)

        # Track attribute conflicts and provenance
        conflicts = []
        provenance = []

        # Merge core attributes
        merged_core = dict(primary.core)
        for attr_name, attr in secondary.core.items():
            if attr_name in merged_core:
                # Conflict - need to resolve
                existing = merged_core[attr_name]
                winner, conflict_info = self._resolve_attribute_conflict(existing, attr)
                if conflict_info:
                    conflicts.append(conflict_info)
                merged_core[attr_name] = winner
            else:
                merged_core[attr_name] = attr
                provenance.append({
                    'attribute': attr_name,
                    'from_entity': secondary.entity_id,
                    'layer': 'core'
                })

        # Merge shell attributes
        merged_shell = dict(primary.shell)
        for attr_name, attr in secondary.shell.items():
            if attr_name in merged_shell:
                existing = merged_shell[attr_name]
                winner, conflict_info = self._resolve_attribute_conflict(existing, attr)
                if conflict_info:
                    conflicts.append(conflict_info)
                merged_shell[attr_name] = winner
            else:
                merged_shell[attr_name] = attr
                provenance.append({
                    'attribute': attr_name,
                    'from_entity': secondary.entity_id,
                    'layer': 'shell'
                })

        # Merge halo attributes (these can coexist more easily)
        merged_halo = dict(primary.halo)
        for attr_name, attr in secondary.halo.items():
            if attr_name in merged_halo:
                # For halo, try to merge lists or keep both
                existing = merged_halo[attr_name]
                merged_attr = self._merge_halo_attributes(existing, attr)
                merged_halo[attr_name] = merged_attr
            else:
                merged_halo[attr_name] = attr
                provenance.append({
                    'attribute': attr_name,
                    'from_entity': secondary.entity_id,
                    'layer': 'halo'
                })

        # Combine source tracking
        merged_sources = list(set(primary.sources + secondary.sources))

        # Create merged entity
        merged_entity = Entity(
            entity_id=primary.entity_id,  # Keep primary's ID
            entity_type=primary.entity_type,
            display_name=primary.display_name,
            core=merged_core,
            shell=merged_shell,
            halo=merged_halo,
            confidence=max(primary.confidence, secondary.confidence),
            sources=merged_sources,
        )

        # Add provenance tracking to merged entity
        merged_entity.halo['_fused_from'] = EntityAttribute(
            name='_fused_from',
            value=[secondary.entity_id],
            confidence=1.0,
            source='disambiguation',
        )

        return FuseResult(
            merged_entity=merged_entity,
            absorbed_entity_ids=[secondary.entity_id],
            attribute_conflicts=conflicts,
            provenance=provenance,
        )

    def _execute_repel(
        self,
        entity_a: Entity,
        entity_b: Entity,
        resolution: Resolution
    ) -> RepelResult:
        """
        Execute REPEL - mark entities as distinct.

        Strategy:
        1. Identify distinguishing attributes
        2. Mark as never-merge pair
        3. Update both entities with disambiguation info
        """
        # Find distinguishing attributes
        distinguishing = []

        for attr_name in entity_a.core.keys():
            if attr_name in entity_b.core:
                a_val = str(entity_a.core[attr_name].value)
                b_val = str(entity_b.core[attr_name].value)
                if a_val != b_val:
                    distinguishing.append(attr_name)

        # Mark entities with repel info
        entity_a.halo['_repelled_from'] = EntityAttribute(
            name='_repelled_from',
            value=[entity_b.entity_id],
            confidence=resolution.confidence,
            source='disambiguation',
        )

        entity_b.halo['_repelled_from'] = EntityAttribute(
            name='_repelled_from',
            value=[entity_a.entity_id],
            confidence=resolution.confidence,
            source='disambiguation',
        )

        return RepelResult(
            entity_a=entity_a,
            entity_b=entity_b,
            distinguishing_attributes=distinguishing,
            never_merge_flag=True,
        )

    def _execute_binary_star(
        self,
        entity_a: Entity,
        entity_b: Entity,
        resolution: Resolution
    ) -> BinaryStarResult:
        """
        Execute BINARY_STAR - create linked pair.

        These are distinct entities with a special relationship:
        - Namesakes who are related
        - Company and its subsidiary
        - Person and their alias
        """
        # Determine binding type from evidence
        binding_type = self._infer_binding_type(entity_a, entity_b, resolution)

        # Create bidirectional edge
        entity_a.halo['_binary_star'] = EntityAttribute(
            name='_binary_star',
            value=entity_b.entity_id,
            confidence=resolution.confidence,
            source='disambiguation',
        )
        entity_a.halo['_binary_star_type'] = EntityAttribute(
            name='_binary_star_type',
            value=binding_type,
            confidence=resolution.confidence,
            source='disambiguation',
        )

        entity_b.halo['_binary_star'] = EntityAttribute(
            name='_binary_star',
            value=entity_a.entity_id,
            confidence=resolution.confidence,
            source='disambiguation',
        )
        entity_b.halo['_binary_star_type'] = EntityAttribute(
            name='_binary_star_type',
            value=binding_type,
            confidence=resolution.confidence,
            source='disambiguation',
        )

        return BinaryStarResult(
            entity_a=entity_a,
            entity_b=entity_b,
            binding_type=binding_type,
            binding_evidence=resolution.supporting_evidence,
        )

    def _choose_primary(
        self,
        entity_a: Entity,
        entity_b: Entity
    ) -> Tuple[Entity, Entity]:
        """Choose which entity should be primary in a merge."""
        # Score based on data completeness and confidence
        a_score = (
            len(entity_a.core) * 3 +
            len(entity_a.shell) * 2 +
            len(entity_a.halo) * 1 +
            entity_a.confidence * 10
        )

        b_score = (
            len(entity_b.core) * 3 +
            len(entity_b.shell) * 2 +
            len(entity_b.halo) * 1 +
            entity_b.confidence * 10
        )

        if a_score >= b_score:
            return entity_a, entity_b
        else:
            return entity_b, entity_a

    def _resolve_attribute_conflict(
        self,
        attr_a: EntityAttribute,
        attr_b: EntityAttribute
    ) -> Tuple[EntityAttribute, Optional[Dict[str, Any]]]:
        """
        Resolve conflict between two attributes.

        Returns (winner, conflict_info or None)
        """
        # If values match, no conflict
        if str(attr_a.value) == str(attr_b.value):
            return attr_a, None

        # Choose by confidence
        if attr_a.confidence > attr_b.confidence:
            return attr_a, {
                'attribute': attr_a.name,
                'kept': str(attr_a.value),
                'discarded': str(attr_b.value),
                'reason': 'higher_confidence'
            }
        elif attr_b.confidence > attr_a.confidence:
            return attr_b, {
                'attribute': attr_a.name,
                'kept': str(attr_b.value),
                'discarded': str(attr_a.value),
                'reason': 'higher_confidence'
            }
        else:
            # Equal confidence - prefer more recent or more specific
            # For now, keep attr_a
            return attr_a, {
                'attribute': attr_a.name,
                'kept': str(attr_a.value),
                'discarded': str(attr_b.value),
                'reason': 'arbitrary_tiebreak'
            }

    def _merge_halo_attributes(
        self,
        attr_a: EntityAttribute,
        attr_b: EntityAttribute
    ) -> EntityAttribute:
        """Merge halo attributes (more permissive than core/shell)."""
        # Try to combine as list
        a_val = attr_a.value if isinstance(attr_a.value, list) else [attr_a.value]
        b_val = attr_b.value if isinstance(attr_b.value, list) else [attr_b.value]

        combined = list(set(str(v) for v in a_val + b_val))

        return EntityAttribute(
            name=attr_a.name,
            value=combined,
            confidence=max(attr_a.confidence, attr_b.confidence),
            source=f"{attr_a.source}+{attr_b.source}",
        )

    def _infer_binding_type(
        self,
        entity_a: Entity,
        entity_b: Entity,
        resolution: Resolution
    ) -> str:
        """Infer the type of binding for binary star."""
        evidence = ' '.join(resolution.supporting_evidence).lower()

        if 'family' in evidence or 'relative' in evidence or 'father' in evidence or 'son' in evidence:
            return 'family'
        elif 'alias' in evidence or 'aka' in evidence or 'known as' in evidence:
            return 'alias'
        elif 'subsidiary' in evidence or 'parent' in evidence or 'holding' in evidence:
            return 'corporate_group'
        elif 'partner' in evidence or 'business' in evidence:
            return 'business_relationship'
        else:
            return 'namesake'

    def _build_fuse_updates(self, fuse_result: FuseResult) -> List[Dict[str, Any]]:
        """Build graph update operations for FUSE."""
        updates = []

        # Update: replace merged entity
        updates.append({
            'operation': 'upsert_entity',
            'entity_id': fuse_result.merged_entity.entity_id,
            'data': self._entity_to_dict(fuse_result.merged_entity),
        })

        # Delete: absorbed entities
        for absorbed_id in fuse_result.absorbed_entity_ids:
            updates.append({
                'operation': 'delete_entity',
                'entity_id': absorbed_id,
            })

            # Redirect edges from absorbed to merged
            updates.append({
                'operation': 'redirect_edges',
                'from_entity_id': absorbed_id,
                'to_entity_id': fuse_result.merged_entity.entity_id,
            })

        return updates

    def _build_repel_updates(self, repel_result: RepelResult) -> List[Dict[str, Any]]:
        """Build graph update operations for REPEL."""
        updates = []

        # Update both entities with repel markers
        updates.append({
            'operation': 'upsert_entity',
            'entity_id': repel_result.entity_a.entity_id,
            'data': self._entity_to_dict(repel_result.entity_a),
        })
        updates.append({
            'operation': 'upsert_entity',
            'entity_id': repel_result.entity_b.entity_id,
            'data': self._entity_to_dict(repel_result.entity_b),
        })

        # Add repel edge
        updates.append({
            'operation': 'add_edge',
            'edge_type': 'repel',
            'from_id': repel_result.entity_a.entity_id,
            'to_id': repel_result.entity_b.entity_id,
            'metadata': {
                'distinguishing_attributes': repel_result.distinguishing_attributes,
                'never_merge': repel_result.never_merge_flag,
            }
        })

        return updates

    def _build_binary_star_updates(self, bs_result: BinaryStarResult) -> List[Dict[str, Any]]:
        """Build graph update operations for BINARY_STAR."""
        updates = []

        # Update both entities
        updates.append({
            'operation': 'upsert_entity',
            'entity_id': bs_result.entity_a.entity_id,
            'data': self._entity_to_dict(bs_result.entity_a),
        })
        updates.append({
            'operation': 'upsert_entity',
            'entity_id': bs_result.entity_b.entity_id,
            'data': self._entity_to_dict(bs_result.entity_b),
        })

        # Add binary star edge
        updates.append({
            'operation': 'add_edge',
            'edge_type': 'binary_star',
            'from_id': bs_result.entity_a.entity_id,
            'to_id': bs_result.entity_b.entity_id,
            'metadata': {
                'binding_type': bs_result.binding_type,
                'evidence': bs_result.binding_evidence,
            }
        })

        return updates

    def _entity_to_dict(self, entity: Entity) -> Dict[str, Any]:
        """Convert entity to dict for storage."""
        return {
            'entity_id': entity.entity_id,
            'entity_type': entity.entity_type.value,
            'display_name': entity.display_name,
            'core': {k: {'value': v.value, 'confidence': v.confidence, 'source': v.source}
                    for k, v in entity.core.items()},
            'shell': {k: {'value': v.value, 'confidence': v.confidence, 'source': v.source}
                     for k, v in entity.shell.items()},
            'halo': {k: {'value': v.value, 'confidence': v.confidence, 'source': v.source}
                    for k, v in entity.halo.items()},
            'confidence': entity.confidence,
            'sources': entity.sources,
        }


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def apply_resolution(
    entity_a: Entity,
    entity_b: Entity,
    collision: EntityCollision,
    resolution: Resolution,
    graph: EntityGraph = None
) -> ResolutionResult:
    """Apply a resolution to colliding entities."""
    return ResolutionEngine(graph).resolve(entity_a, entity_b, collision, resolution)
