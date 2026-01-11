"""
SASTRE Similarity Module

Multi-dimensional similarity computation for identity resolution,
similarity search, clustering, and NEXUS intersection intelligence.

The =? operator is the most powerful in the system.
"""

# Vectors
from .vectors import (
    SimilarityVector,
    SimilarityScore,
    EntityType,
    TimeRange,
    build_vector_from_node,
    empty_vector,
)

# Engine
from .engine import (
    SimilarityEngine,
    DimensionWeight,
)

# Compare operator
from .compare import (
    CompareOperator,
    CompareResult,
    CompareMode,
    IdentityVerdict,
    PairComparison,
    SimilarEntity,
    Cluster,
    BridgeEntity,
)

# NEXUS expectations
from .expectations import (
    NexusEvaluator,
    Expectation,
    ExpectationState,
    ExpectationBasis,
    IntersectionResult,
    SurprisingAnd,
    DIMENSION_MATRIX,
    evaluate_dimension_intersection,
)


__all__ = [
    # Vectors
    "SimilarityVector",
    "SimilarityScore",
    "EntityType",
    "TimeRange",
    "build_vector_from_node",
    "empty_vector",
    # Engine
    "SimilarityEngine",
    "DimensionWeight",
    # Compare operator
    "CompareOperator",
    "CompareResult",
    "CompareMode",
    "IdentityVerdict",
    "PairComparison",
    "SimilarEntity",
    "Cluster",
    "BridgeEntity",
    # NEXUS expectations
    "NexusEvaluator",
    "Expectation",
    "ExpectationState",
    "ExpectationBasis",
    "IntersectionResult",
    "SurprisingAnd",
    "DIMENSION_MATRIX",
    "evaluate_dimension_intersection",
]
