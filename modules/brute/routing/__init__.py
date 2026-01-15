"""
Query Routing Module
====================
Intelligent engine selection based on multi-axis query analysis.

Three routing systems available:

1. **QueryRouter** (simple): Fast SWITCHBOARD-style routing for common queries
   - SUBJECT axis: Entity types (person, company, phone, email, topic)
   - LOCATION axis: Geographic context
   - OBJECT axis: Query operators (site:, filetype:, etc.)
   - TEMPORAL axis: Time-based constraints
   - Reduces engine count from 65 to 10-15 per query

2. **MatrixQueryRouter** (full): Complete NSOL routing with UNIFIED_MATRIX
   - L1/L2/L3 tiers for all search types
   - 7 LOCATION dimensions (temporal, geographic, linguistic, textual, address, format, category)
   - 23+ category types (news, academic, social, books, legal, etc.)
   - Operator detection and module routing

3. **AxisOrchestrator** (SWITCHBOARD): Central axis interaction system
   - Manages interactions between NARRATIVE, SUBJECT, OBJECT, LOCATION axes
   - Defines interaction rules for axis combinations
   - Optimizes execution order based on dependencies

Additional Components:
- **PatternDetector**: Centralized pattern detection for all search operators
- **search_routing_system**: JSON configs for engine assignments and availability
"""
from .query_router import QueryRouter, QueryAnalysis, EngineRecommendation
from .axis_analyzer import AxisAnalyzer, SubjectType, LocationContext, ObjectOperator

# Full matrix routing
from .matrix_registry import UNIFIED_MATRIX, DEFAULT_MATRIX, get_engines, load_engine_matrix
from .matrix_router import MatrixQueryRouter, analyze_query, route_and_execute

# Pattern detection
from .pattern_detector import PatternDetector

# SWITCHBOARD axis orchestration
from .SWITCHBOARD import (
    AxisOrchestrator,
    AxisType,
    LocationCoordinate,
    SubjectType as SwitchboardSubjectType,
    process_search_query,
    get_compatibility_matrix,
)

# Search routing system configs
from .search_routing_system import (
    load_engine_matrix_external,
    load_search_type_to_engines,
    load_engine_availability,
    load_category_matrix,
)

# Capabilities registry
from .capabilities_registry import filter_engine_codes

__all__ = [
    # Simple router
    "QueryRouter",
    "QueryAnalysis",
    "EngineRecommendation",
    "AxisAnalyzer",
    "SubjectType",
    "LocationContext",
    "ObjectOperator",
    # Full matrix router
    "MatrixQueryRouter",
    "UNIFIED_MATRIX",
    "DEFAULT_MATRIX",
    "get_engines",
    "load_engine_matrix",
    "analyze_query",
    "route_and_execute",
    # Pattern detection
    "PatternDetector",
    # SWITCHBOARD
    "AxisOrchestrator",
    "AxisType",
    "LocationCoordinate",
    "SwitchboardSubjectType",
    "process_search_query",
    "get_compatibility_matrix",
    # Search routing system
    "load_engine_matrix_external",
    "load_search_type_to_engines",
    "load_engine_availability",
    "load_category_matrix",
    # Capabilities
    "filter_engine_codes",
]
