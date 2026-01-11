"""
SASTRE Core - State, Relationships, Phases, Schema

Central data structures for the investigation system.
"""

from .state import (
    # Enums
    InvestigationPhase,
    KUQuadrant,
    Intent,
    Priority,
    EntityType,
    NarrativeState,
    QueryState,
    SourceState,
    DisambiguationAction,
    DisambiguationState,

    # Core types
    Attribute,
    EntityAttribute,  # Alias
    Entity,
    Edge,
    EntityGraph,
    EntityCollision,
    Resolution,

    # Narrative
    NarrativeItem,
    NarrativeGoal,
    NarrativeTrack,
    NarrativePath,
    Section,
    Footnote,
    SurprisingAnd,

    # Query
    Query,

    # Source
    SourceResult,

    # Coverage
    NarrativeCoverage,
    EntityCoverage,

    # Top-level
    Document,
    InvestigationState,
)

from .schema import (
    ENTITY_SCHEMA,
    EXPECTED_FIELDS,
    POSSIBLE_FIELDS,
    get_required_fields,
    get_optional_fields,
    check_completeness,
    # Edge types
    EDGE_TYPES,
    get_edge_type,
    is_valid_edge,
)

from .relationships import (
    RelationshipTracker,
    QueryNarrativeTracker,
    SourceQueryOverlapDetector,
    ContributionStatus,
    NarrativeProgress,
    HotSpot,
    OverlapType,
)

from .sufficiency import (
    SufficiencyChecker,
    SufficiencyResult,
)

__all__ = [
    # Enums
    'InvestigationPhase',
    'KUQuadrant',
    'Intent',
    'Priority',
    'EntityType',
    'NarrativeState',
    'QueryState',
    'SourceState',
    'DisambiguationAction',
    'DisambiguationState',

    # Core types
    'Attribute',
    'EntityAttribute',
    'Entity',
    'Edge',
    'EntityGraph',
    'EntityCollision',
    'Resolution',

    # Narrative
    'NarrativeItem',
    'NarrativeGoal',
    'NarrativeTrack',
    'NarrativePath',
    'Section',
    'Footnote',
    'SurprisingAnd',

    # Query
    'Query',

    # Source
    'SourceResult',

    # Coverage
    'NarrativeCoverage',
    'EntityCoverage',

    # Top-level
    'Document',
    'InvestigationState',

    # Schema
    'ENTITY_SCHEMA',
    'EXPECTED_FIELDS',
    'POSSIBLE_FIELDS',
    'get_required_fields',
    'get_optional_fields',
    'check_completeness',

    # Edge types
    'EDGE_TYPES',
    'get_edge_type',
    'is_valid_edge',

    # Relationships
    'RelationshipTracker',
    'QueryNarrativeTracker',
    'SourceQueryOverlapDetector',
    'ContributionStatus',
    'NarrativeProgress',
    'HotSpot',
    'OverlapType',

    # Sufficiency
    'SufficiencyChecker',
    'SufficiencyResult',
]
