"""
SASTRE Grid Module - The Cognitive Engine (V4.2)

The Grid is NOT just a view; it is the system's BRAIN.

The system does not merely "check for empty fields."
It actively THINKS by rotating through four Cognitive Modes (Centricities).
Each rotation reveals gaps that the others miss.

V4.2 CORRECTION - SENSOR OUTPUT:
    The Grid maps K-U state and gaps. Intent derivation lives in the
    Orchestrator/Navigator (the Motor).

    K-U Matrix:
        (K-K) Known Subject + Known Location   -> VERIFY
        (K-U) Known Subject + Unknown Location -> TRACE
        (U-K) Unknown Subject + Known Location -> EXTRACT
        (U-U) Unknown Subject + Unknown Location -> DISCOVER

Cognitive Modes:
- NARRATIVE: The Editor - Story coherence and sufficiency
- SUBJECT: The Biographer - Profile completeness
- LOCATION: The Cartographer - Terrain coverage
- NEXUS: The Detective - Connection logic

Gap Formula: (Subject Axis × Location Axis × Nexus Axis) + Narrative Intent
"""

from .assessor import (
    # Cymonides thin interface
    CymonidesGridAssessor,
    CymonidesAssessment,
    ViewAssessment,
    ViewMode,
    VIEW_MODE_FILTERS,
    assess_investigation,
    # State-based assessor (for in-memory analysis)
    GridAssessor as StateGridAssessor,
    EnhancedGridAssessor,
    GridAssessment,
    EnhancedGridAssessment,
    # Query generator
    GapQueryGenerator,
    GeneratedQuery,
    build_query_batch,
)

from .cognitive_types import (
    CognitiveMode,
    CognitiveGap,
    GapCoordinates3D,
    SubjectAxis,
    LocationAxis,
    NexusAxis,
    CertaintyLevel,
    GapDimension,
)

from .cognitive_engine import (
    # The Brain (V4.2)
    CognitiveEngine,
    # Cross-pollination
    CrossPollinationAction,
    # Dimensional analysis
    DimensionalAnalysis,
    DimensionalCorrelation,
    DimensionalContrast,
    # Corpus check
    CorpusCheckResult,
    # Convenience function
    run_cognitive_analysis,
)

from .narrative_assessor import NarrativeAssessor
from .subject_assessor import SubjectAssessor
from .location_assessor import LocationAssessor
from .nexus_assessor import NexusAssessor

# Primary assessor is now the Cognitive Engine
GridAssessor = CognitiveEngine

__all__ = [
    # === THE BRAIN (V4.2) ===
    'CognitiveEngine',
    'CognitiveMode',
    'CognitiveGap',
    # 3D Coordinates
    'GapCoordinates3D',
    'SubjectAxis',
    'LocationAxis',
    'NexusAxis',
    'CertaintyLevel',
    'GapDimension',
    # Cross-pollination
    'CrossPollinationAction',
    # Dimensional analysis
    'DimensionalAnalysis',
    'DimensionalCorrelation',
    'DimensionalContrast',
    # Corpus check
    'CorpusCheckResult',
    # Convenience function
    'run_cognitive_analysis',
    # Mode assessors
    'NarrativeAssessor',
    'SubjectAssessor',
    'LocationAssessor',
    'NexusAssessor',

    # === LEGACY ASSESSORS ===
    # Cymonides thin interface
    'CymonidesGridAssessor',
    'CymonidesAssessment',
    'ViewAssessment',
    'ViewMode',
    'VIEW_MODE_FILTERS',
    'assess_investigation',
    # Alias for compatibility
    'GridAssessor',
    # State-based assessor
    'StateGridAssessor',
    'EnhancedGridAssessor',
    'GridAssessment',
    'EnhancedGridAssessment',
    # Query generator
    'GapQueryGenerator',
    'GeneratedQuery',
    'build_query_batch',
]
