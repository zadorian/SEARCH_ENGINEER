"""
Cymonides Agent Configuration

Canonical standards and paths for indexing operations.
"""

from .canonical_standards import (
    CANONICAL_PATHS,
    INDEX_TIERS,
    NODE_CLASSES,
    C1_NODE_SCHEMA,
    C3_UNIFIED_SCHEMA,
    C3_TEST_PROTOCOL,
    ERA_DEFINITIONS,
    C1_BRIDGE_TEMPLATE,
    get_era,
    get_decade,
    get_node_class,
    canonical_value,
    generate_node_id,
)

__all__ = [
    "CANONICAL_PATHS",
    "INDEX_TIERS",
    "NODE_CLASSES",
    "C1_NODE_SCHEMA",
    "C3_UNIFIED_SCHEMA",
    "C3_TEST_PROTOCOL",
    "ERA_DEFINITIONS",
    "C1_BRIDGE_TEMPLATE",
    "get_era",
    "get_decade",
    "get_node_class",
    "canonical_value",
    "generate_node_id",
]
