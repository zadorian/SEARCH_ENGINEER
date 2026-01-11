"""
SASTRE V62 - Query Lab with Watcher Integration
================================================

The V62 module bridges Query Lab (search construction) with the Watcher System
(extraction intelligence) through the Navigator loop.

Components:
- query_watcher_integration: Data structures and integration functions
- navigator: Autonomous investigation loop
- generative_watcher: LLM-driven watcher creation

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                          V62 ARCHITECTURE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  QueryRecipe (Search)  +  WatcherSpec[] (Extraction)  =  QueryExecutionPlan │
│         ↓                        ↓                              ↓           │
│    Location axis           Quote watchers                Navigator loop     │
│    Subject axis            ET3 watchers                 Slot feeding        │
│    Nexus terms             Entity watchers              Sufficiency check   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from SASTRE.v62 import Navigator, NavigatorConfig
    from SASTRE.v62 import build_execution_plan_with_watchers
    from SASTRE.v62 import generate_watchers_from_slots
    
    # Run investigation
    navigator = Navigator()
    async for event in navigator.run(
        narrative_goal="Identify John Smith's corporate connections",
        initial_query='"John Smith" +w[DOB?] +w[Companies?]',
    ):
        print(event)
"""

from .query_watcher_integration import (
    # Enums
    WatcherContextMode,
    
    # Data structures
    WatcherSpec,
    ExtractionHints,
    QueryExecutionPlan,
    WatcherFinding,
    WatcherExecutionResult,
    GenerativeWatcherRequest,
    GeneratedWatcher,
    
    # Functions
    parse_watcher_syntax,
    build_execution_plan_with_watchers,
)

from .navigator import (
    # Enums
    Intent,
    Strategy,
    Target,
    
    # Data structures
    SlotState,
    EntityKUState,
    LocationKUState,
    NexusState,
    GridAssessment,
    SufficiencyResult,
    NavigatorConfig,
    NavigatorState,
    NavigatorEvent,
    
    # Classes
    Navigator,
    
    # Functions
    check_sufficiency,
    derive_intent,
    run_navigator,
)

from .generative_watcher import (
    # Constants
    EVENT_TYPES,
    TOPIC_TYPES,
    SLOT_TO_WATCHER_HINTS,
    
    # Data structures (re-exported)
    # GenerativeWatcherRequest (already in query_watcher_integration)
    # GeneratedWatcher (already in query_watcher_integration)
    GenerativeWatcherResult,
    
    # Classes
    GenerativeWatcherCreator,
    
    # Functions
    generate_watchers_from_slots,
    generate_watchers_from_narrative,
    generate_watchers_from_slots_sync,
)

__all__ = [
    # Enums
    "WatcherContextMode",
    "Intent",
    "Strategy",
    "Target",
    
    # Data structures
    "WatcherSpec",
    "ExtractionHints",
    "QueryExecutionPlan",
    "WatcherFinding",
    "WatcherExecutionResult",
    "GenerativeWatcherRequest",
    "GeneratedWatcher",
    "GenerativeWatcherResult",
    "SlotState",
    "EntityKUState",
    "LocationKUState",
    "NexusState",
    "GridAssessment",
    "SufficiencyResult",
    "NavigatorConfig",
    "NavigatorState",
    "NavigatorEvent",
    
    # Classes
    "Navigator",
    "GenerativeWatcherCreator",
    
    # Functions
    "parse_watcher_syntax",
    "build_execution_plan_with_watchers",
    "check_sufficiency",
    "derive_intent",
    "run_navigator",
    "generate_watchers_from_slots",
    "generate_watchers_from_narrative",
    "generate_watchers_from_slots_sync",
    
    # Constants
    "EVENT_TYPES",
    "TOPIC_TYPES",
    "SLOT_TO_WATCHER_HINTS",
]
