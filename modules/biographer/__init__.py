"""
BIOGRAPHER - Person Profile Aggregator Module

Handles the `p:` operator by coordinating multiple OSINT specialists:
- EYE-D for email, phone, username, LinkedIn, WHOIS
- CORPORELLA for company affiliations, directorships
- SOCIALITE for social media profiles

Components:
- biographer_cli.py: Main CLI entry point
- nodes.py: Node creation utilities (query, primary, secondary)
- verification.py: Verification tag system and consolidation logic
- watcher.py: Watcher integration with project notes
- context.py: Context assembly for biographer_ai disambiguation

Architecture:
    Query Node: "p: John Smith"
        ├── [searched] → PRIMARY: "John Smith" (consolidated by biographer_ai)
        ├── [found] → SECONDARY (a): "John Smith (a)" ← EYE-D
        ├── [found] → SECONDARY (b): "John Smith (b)" ← CORPORELLA
        └── [found] → SECONDARY (c): "John Smith (c)" ← SOCIALITE

Watcher Integration:
    - Watcher attached to PROJECT (not just primary node)
    - Parent document = dedicated note for person profile
    - All BRUTE query results scanned by Haiku
    - Findings stream to dedicated note under section headings
    - biographer_ai makes ADD_VERIFIED/ADD_UNVERIFIED/REJECT decisions

Context Assembly:
    - Project Note with template sections
    - Active watchers + attached context
    - Disambiguation anchors (location, temporal, industry, phenomena)
    - IO routing suggestions (unfilled fields → sources)
"""

from .nodes import (
    Node,
    Edge,
    BiographerNodeSet,
    create_query_node,
    create_primary_person_node,
    create_secondary_person_node,
    create_biographer_node_set,
    get_suffix_for_source,
    SOURCE_SUFFIXES,
)

from .verification import (
    VerificationStatus,
    VerificationResult,
    ConsolidationResult,
    DecisionAction,
    BiographerDecision,
    RejectionRecord,
    create_verification_tag,
    compare_field,
    consolidate_secondaries,
    apply_consolidation,
    apply_decision,
)

from .watcher import (
    WatcherType,
    BiographerWatcher,
    WatcherFinding,
    PERSON_NOTE_HEADINGS,
    create_biographer_watcher,
    create_section_watchers,
    execute_watcher_scan,
    stream_finding_to_note,
    process_finding_decision,
    initialize_biographer_with_project_note,
    save_watcher_state,
    load_watcher_state,
)

from .context import (
    DisambiguationAnchors,
    IORoutingSuggestion,
    WatcherContext,
    BiographerContext,
    PERSON_NODE_SCHEMA,
    get_routing_suggestions_for_field,
    get_all_routing_suggestions,
    assemble_biographer_context,
    format_context_for_ai,
    get_biographer_context,
)

from .disambiguator_bridge import (
    save_wedge_queries,
    load_wedge_queries,
    record_wedge_result,
    get_pending_wedge_count,
    clear_wedge_queries,
    clear_disambiguation_cache,
)

__all__ = [
    # Nodes
    "Node",
    "Edge",
    "BiographerNodeSet",
    "create_query_node",
    "create_primary_person_node",
    "create_secondary_person_node",
    "create_biographer_node_set",
    "get_suffix_for_source",
    "SOURCE_SUFFIXES",
    # Verification
    "VerificationStatus",
    "VerificationResult",
    "ConsolidationResult",
    "DecisionAction",
    "BiographerDecision",
    "RejectionRecord",
    "create_verification_tag",
    "compare_field",
    "consolidate_secondaries",
    "apply_consolidation",
    "apply_decision",
    # Watcher
    "WatcherType",
    "BiographerWatcher",
    "WatcherFinding",
    "PERSON_NOTE_HEADINGS",
    "create_biographer_watcher",
    "create_section_watchers",
    "execute_watcher_scan",
    "stream_finding_to_note",
    "process_finding_decision",
    "initialize_biographer_with_project_note",
    "save_watcher_state",
    "load_watcher_state",
    # Context
    "DisambiguationAnchors",
    "IORoutingSuggestion",
    "WatcherContext",
    "BiographerContext",
    "PERSON_NODE_SCHEMA",
    "get_routing_suggestions_for_field",
    "get_all_routing_suggestions",
    "assemble_biographer_context",
    "format_context_for_ai",
    "get_biographer_context",
    # Disambiguation persistence
    "save_wedge_queries",
    "load_wedge_queries",
    "record_wedge_result",
    "get_pending_wedge_count",
    "clear_wedge_queries",
    "clear_disambiguation_cache",
]
