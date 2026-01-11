"""
SASTRE Disambiguation Module - Entity collision resolution.

Resolves entity collisions with FUSE/REPEL/BINARY_STAR physics.

Components:
- Disambiguator: Main disambiguation class
- PassiveChecker: Automatic checks without new queries
- WedgeQueryGenerator: Active disambiguation via targeted queries
- ResolutionEngine: Execute FUSE/REPEL/BINARY_STAR decisions
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from ..contracts import (
    Entity, Collision, NegativeEdge, DisambiguationResult,
    DisambiguationAction, WedgeQuery, BinaryStar
)


# =============================================================================
# DISAMBIGUATOR CLASS (inline to avoid circular import)
# =============================================================================

HARD_IDENTIFIERS = [
    'ssn', 'social_security_number', 'passport_number', 'passport',
    'national_id', 'tax_id', 'vat_number', 'ein',
    'registration_number', 'company_number',
]


class Disambiguator:
    """
    Resolves entity collisions via physics of identity.

    PASSIVE mode (automatic):
    - Temporal impossibility -> AUTO_REPEL
    - Identifier collision -> AUTO_FUSE

    ACTIVE mode (wedge queries):
    - EXCLUSION vector: Find conflicting attributes
    - INTERSECTION vector: Find shared context
    """

    def __init__(self):
        self.resolved_fusions: List[Tuple[str, str]] = []
        self.negative_edges: List[NegativeEdge] = []

    def extract_and_resolve(
        self,
        raw_results: Dict[str, Any],
        known_entities: List[Entity]
    ) -> DisambiguationResult:
        """Extract entities from IO results and resolve collisions."""
        new_entities = self._extract_entities(raw_results)
        collisions = self._detect_collisions(new_entities, known_entities)

        resolved = []
        binary_stars = []
        negative_edges = []
        wedge_queries = []

        for collision in collisions:
            action, reason = self._passive_check(collision)

            if action == DisambiguationAction.FUSE:
                merged = self._fuse_entities(collision.entity_a, collision.entity_b)
                resolved.append(merged)
                self.resolved_fusions.append((collision.entity_a.id, collision.entity_b.id))
            elif action == DisambiguationAction.REPEL:
                resolved.append(collision.entity_a)
                resolved.append(collision.entity_b)
                negative_edges.append(NegativeEdge(
                    entity_a_id=collision.entity_a.id,
                    entity_b_id=collision.entity_b.id,
                    reason=reason
                ))
            else:
                # BINARY_STAR - generate wedge queries
                binary_stars.append(BinaryStar(
                    entity_a_id=collision.entity_a.id,
                    entity_b_id=collision.entity_b.id,
                    similarity_score=collision.similarity
                ))
                wedge_queries.extend(self._generate_wedge_queries(collision))

        # Add non-colliding entities
        for entity in new_entities:
            if not any(e.id == entity.id for e in resolved):
                resolved.append(entity)

        return DisambiguationResult(
            resolved_entities=resolved,
            binary_stars=binary_stars,
            negative_edges=negative_edges,
            wedge_queries=wedge_queries,
            fused_count=len(self.resolved_fusions),
            repelled_count=len(negative_edges)
        )

    def _extract_entities(self, raw_results: Dict[str, Any]) -> List[Entity]:
        """Extract entities from raw IO results."""
        entities = []
        # Handle various result formats
        for key in ['entities', 'persons', 'companies', 'results']:
            if key in raw_results:
                for item in raw_results[key]:
                    if isinstance(item, dict):
                        entities.append(Entity(
                            id=item.get('id', ''),
                            name=item.get('name', item.get('label', '')),
                            entity_type=item.get('type', 'unknown'),
                            source=item.get('source', '')
                        ))
        return entities

    def _detect_collisions(self, new_entities: List[Entity], known_entities: List[Entity]) -> List:
        """Detect potential collisions between new and known entities."""
        @dataclass
        class EntityCollision:
            entity_a: Entity
            entity_b: Entity
            similarity: float = 0.5

        collisions = []
        for new_ent in new_entities:
            for known_ent in known_entities:
                if self._might_be_same(new_ent, known_ent):
                    collisions.append(EntityCollision(
                        entity_a=new_ent,
                        entity_b=known_ent,
                        similarity=self._compute_similarity(new_ent, known_ent)
                    ))
        return collisions

    def _might_be_same(self, a: Entity, b: Entity) -> bool:
        """Check if two entities might be the same."""
        if a.entity_type != b.entity_type:
            return False
        # Name similarity check
        a_tokens = set(a.name.lower().split())
        b_tokens = set(b.name.lower().split())
        if a_tokens & b_tokens:
            return True
        return False

    def _compute_similarity(self, a: Entity, b: Entity) -> float:
        """Compute similarity score between entities."""
        a_tokens = set(a.name.lower().split())
        b_tokens = set(b.name.lower().split())
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        return intersection / union if union > 0 else 0.0

    def _passive_check(self, collision) -> Tuple[DisambiguationAction, str]:
        """Run passive disambiguation checks."""
        # Check for hard identifier match/conflict
        a_attrs = getattr(collision.entity_a, 'attributes', None)
        b_attrs = getattr(collision.entity_b, 'attributes', None)

        if a_attrs and b_attrs:
            a_core = getattr(a_attrs, 'core', {})
            b_core = getattr(b_attrs, 'core', {})

            for identifier in HARD_IDENTIFIERS:
                a_val = a_core.get(identifier)
                b_val = b_core.get(identifier)
                if a_val and b_val:
                    if a_val == b_val:
                        return DisambiguationAction.FUSE, f"Shared {identifier}: {a_val}"
                    else:
                        return DisambiguationAction.REPEL, f"Conflicting {identifier}: {a_val} vs {b_val}"

        # High similarity with same source = likely same
        if collision.similarity > 0.9:
            return DisambiguationAction.FUSE, "High name similarity (>0.9)"

        # Low similarity = likely different
        if collision.similarity < 0.3:
            return DisambiguationAction.REPEL, "Low name similarity (<0.3)"

        return DisambiguationAction.BINARY_STAR, "Inconclusive - needs wedge queries"

    def _fuse_entities(self, a: Entity, b: Entity) -> Entity:
        """Merge two entities into one."""
        # Keep entity A as base, merge B's attributes
        merged = Entity(
            id=a.id,
            name=a.name or b.name,
            entity_type=a.entity_type or b.entity_type,
            source=f"{a.source};{b.source}" if b.source else a.source
        )
        return merged

    def _generate_wedge_queries(self, collision) -> List[WedgeQuery]:
        """Generate wedge queries for a binary star."""
        queries = []
        a_name = collision.entity_a.name
        b_name = collision.entity_b.name

        # Exclusion query - find conflicting attributes
        queries.append(WedgeQuery(
            query_string=f'"{a_name}" NOT "{b_name}"',
            vector_type="exclusion",
            entity_a_id=collision.entity_a.id,
            entity_b_id=collision.entity_b.id
        ))

        # Intersection query - find shared context
        queries.append(WedgeQuery(
            query_string=f'"{a_name}" AND "{b_name}"',
            vector_type="intersection",
            entity_a_id=collision.entity_a.id,
            entity_b_id=collision.entity_b.id
        ))

        return queries


from .passive import (
    PassiveChecker,
    PassiveCheckResult,
    PassiveOutcome,
    check_passive_constraints,
    # Hard identifiers and link strength (consolidated from disambiguation.py)
    HARD_IDENTIFIERS,
    LinkStrength,
)

from .wedge import (
    WedgeQueryGenerator,
    WedgeQuery,
    WedgeQuerySet,
    WedgeType,
    generate_wedge_queries,
)

from .resolution import (
    ResolutionEngine,
    ResolutionResult,
    FuseResult,
    RepelResult,
    BinaryStarResult,
    apply_resolution,
)

from .physics import (
    CollisionCluster,
    cluster_entities,
    split_cluster_by_attribute,
)

from .cascade import (
    BinaryCascade,
)

__all__ = [
    # Main
    'Disambiguator',
    'HARD_IDENTIFIERS',
    # Passive
    'PassiveChecker',
    'PassiveCheckResult',
    'PassiveOutcome',
    'check_passive_constraints',
    'HARD_IDENTIFIERS',
    'LinkStrength',
    # Wedge
    'WedgeQueryGenerator',
    'WedgeQuery',
    'WedgeQuerySet',
    'WedgeType',
    'generate_wedge_queries',
    # Resolution
    'ResolutionEngine',
    'ResolutionResult',
    'FuseResult',
    'RepelResult',
    'BinaryStarResult',
    'apply_resolution',
    # Physics
    'CollisionCluster',
    'cluster_entities',
    'split_cluster_by_attribute',
    # Cascade
    'BinaryCascade',
]
