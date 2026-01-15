"""
SWITCHBOARD: Axis Orchestration System
=======================================
Central logic system for managing interactions between all search axes.
Controls how different components limit and increase possibilities through
combinatorial interactions.

Components:
- axis_orchestrator: Core orchestration logic
- combinatorial_analyzer: Combinatorial analysis for multi-axis queries
- interaction_rules.json: Defines axis interaction rules
"""

from .axis_orchestrator import (
    AxisOrchestrator,
    AxisType,
    LocationCoordinate,
    SubjectType,
    AxisState,
    InteractionRule,
    process_search_query,
    get_compatibility_matrix,
    orchestrator,
)

__all__ = [
    "AxisOrchestrator",
    "AxisType",
    "LocationCoordinate",
    "SubjectType",
    "AxisState",
    "InteractionRule",
    "process_search_query",
    "get_compatibility_matrix",
    "orchestrator",
]
