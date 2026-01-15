"""
Cymonides Agent Submodules

This package contains supporting modules for the Cymonides agent:
- subagents/: Tool implementations (C3DatasetIndexer, etc.)
- memory/: Status tracking and persistence
- config/: Canonical standards and configuration

The main CymonicesAgent class is in the parent module:
    from modules.cymonides.agent import CymonicesAgent
"""

__version__ = "2.0.0"

# Subagent tools
from .subagents.c3_dataset_indexer import (
    load_dataset_sample,
    get_unified_indices,
    index_test_batch,
    index_full,
    get_indexing_status,
    UNIFIED_INDICES,
)

# Memory/tracking
from .memory.status_tracker import (
    StatusTracker,
    IndexingTask,
    C1BridgeTask,
    get_tracker,
    list_projects,
)

# Configuration
from .config.canonical_standards import (
    CANONICAL_PATHS,
    INDEX_TIERS,
    NODE_CLASSES,
    C3_TEST_PROTOCOL,
    ERA_DEFINITIONS,
    get_era,
    get_decade,
    generate_node_id,
    canonical_value,
)

__all__ = [
    # Tool functions
    "load_dataset_sample",
    "get_unified_indices",
    "index_test_batch",
    "index_full",
    "get_indexing_status",
    "UNIFIED_INDICES",

    # Memory
    "StatusTracker",
    "IndexingTask",
    "C1BridgeTask",
    "get_tracker",
    "list_projects",

    # Config
    "CANONICAL_PATHS",
    "INDEX_TIERS",
    "NODE_CLASSES",
    "C3_TEST_PROTOCOL",
    "ERA_DEFINITIONS",
    "get_era",
    "get_decade",
    "generate_node_id",
    "canonical_value",
]
