"""
SASTRE Disambiguator - Entity Resolution via FUSE/REPEL/BINARY_STAR

This is a THIN WRAPPER around the disambiguation package.
All core logic lives in disambiguation/:
- passive.py: PassiveChecker, HARD_IDENTIFIERS, LinkStrength
- wedge.py: WedgeQueryGenerator, 7 wedge types
- resolution.py: ResolutionEngine, FUSE/REPEL/BINARY_STAR

This file provides:
1. Backward-compatible imports
2. Simple standalone functions for quick use

Physics of Identity:
Disambiguation is a COLLISION EVENT. Two entities must resolve to:
1. FUSE - Confirmed same entity
2. REPEL - Confirmed different entities (negative edge)
3. BINARY_STAR - Ambiguous, orbiting, watching

Asymmetry of Proof:
- To prove SAME: Need ONE definitive match (shared identifier)
- To prove DIFFERENT: Need ONE impossible contradiction
- One hard NO kills a thousand soft YESes
"""

from typing import List, Dict, Any, Optional

# =============================================================================
# RE-EXPORT FROM PACKAGE (Primary API)
# =============================================================================

from .disambiguation import (
    # Passive checks
    PassiveChecker,
    PassiveCheckResult,
    PassiveOutcome,
    check_passive_constraints,
    HARD_IDENTIFIERS,
    LinkStrength,
    # Wedge queries
    WedgeQueryGenerator,
    WedgeQuery,
    WedgeQuerySet,
    WedgeType,
    generate_wedge_queries,
    # Resolution
    ResolutionEngine,
    ResolutionResult,
    FuseResult,
    RepelResult,
    BinaryStarResult,
    apply_resolution,
)

# =============================================================================
# SIMPLE STANDALONE FUNCTIONS (Convenience API)
# =============================================================================

from .contracts import Collision, CollisionType


def detect_collision(
    entity_id: str,
    field_name: str,
    value_a: Any,
    value_b: Any,
    similarity_threshold: float = 0.7,
) -> Optional[Collision]:
    """
    Simple collision detection for slot feeding.

    Args:
        entity_id: ID of the entity
        field_name: Name of the field with conflicting values
        value_a: First value
        value_b: Second value
        similarity_threshold: Threshold for considering values similar

    Returns:
        Collision if detected, None otherwise
    """
    # Exact match - no collision
    if value_a == value_b:
        return None

    # String comparison
    str_a = str(value_a).lower().strip()
    str_b = str(value_b).lower().strip()

    if str_a == str_b:
        return None

    # Calculate simple Jaccard similarity
    def jaccard_similarity(s1: str, s2: str) -> float:
        set1 = set(s1.split())
        set2 = set(s2.split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union else 0.0

    similarity = jaccard_similarity(str_a, str_b)

    if similarity < similarity_threshold:
        # Low similarity = definite collision (different values)
        return Collision(
            entity_a_id=entity_id,
            entity_b_id=f"{entity_id}_{field_name}",
            collision_type=CollisionType.VALUE_CONFLICT,
            similarity_score=similarity,
            field_name=field_name,
            value_a=str(value_a),
            value_b=str(value_b),
        )

    return None


def create_wedge_queries(
    entity_id: str,
    field_name: str,
    conflicting_values: List[Any],
) -> List[Dict[str, Any]]:
    """
    Create simple wedge queries to resolve conflicting values.

    For full wedge query generation with 7 types, use:
        from SASTRE.disambiguation import WedgeQueryGenerator
        generator = WedgeQueryGenerator()
        queries = generator.generate(entity_a, entity_b, collision)

    Args:
        entity_id: ID of the entity
        field_name: Name of the field with conflicts
        conflicting_values: List of conflicting values

    Returns:
        List of simple wedge query specifications
    """
    queries = []

    if len(conflicting_values) < 2:
        return queries

    # For each pair of conflicting values, create exclusion and intersection queries
    for i, val_a in enumerate(conflicting_values):
        for val_b in conflicting_values[i+1:]:
            str_a = str(val_a)
            str_b = str(val_b)

            # Exclusion query: Find evidence that contradicts one value
            queries.append({
                "query_type": "exclusion",
                "target": f"{entity_id}.{field_name}",
                "query": f'"{str_a}" NOT "{str_b}"',
                "description": f"Find evidence supporting {str_a} and excluding {str_b}",
            })

            queries.append({
                "query_type": "exclusion",
                "target": f"{entity_id}.{field_name}",
                "query": f'"{str_b}" NOT "{str_a}"',
                "description": f"Find evidence supporting {str_b} and excluding {str_a}",
            })

            # Intersection query: Find evidence that both could be valid
            queries.append({
                "query_type": "intersection",
                "target": f"{entity_id}.{field_name}",
                "query": f'"{str_a}" AND "{str_b}"',
                "description": f"Find evidence that both values coexist",
            })

    return queries


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Package re-exports
    'PassiveChecker',
    'PassiveCheckResult',
    'PassiveOutcome',
    'check_passive_constraints',
    'HARD_IDENTIFIERS',
    'LinkStrength',
    'WedgeQueryGenerator',
    'WedgeQuery',
    'WedgeQuerySet',
    'WedgeType',
    'generate_wedge_queries',
    'ResolutionEngine',
    'ResolutionResult',
    'FuseResult',
    'RepelResult',
    'BinaryStarResult',
    'apply_resolution',
    # Simple convenience functions
    'detect_collision',
    'create_wedge_queries',
]
