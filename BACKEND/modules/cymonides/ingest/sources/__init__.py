"""
CYMONIDES Ingest Sources
========================

Each source is a single file containing ALL rules for that data source.
No hunting through multiple files.

Sources:
- Pacman.py  : CommonCrawl PDF 2025 dataset
- (add more as needed)
"""

from .Pacman import (
    # Source metadata
    SOURCE_ID,
    SOURCE_TYPE,
    TARGET_INDEX,

    # Tier system
    Tier,
    TierDecision,

    # Classification
    classify,

    # Document building
    build_document,

    # Context extraction
    CONTEXT_WORDS_BEFORE,
    CONTEXT_WORDS_AFTER,
    extract_context,

    # Domain loaders
    load_domain_set,
    load_all_domain_sets,
    load_tripwire_entities,
    build_tripwire_automaton,

    # Progress & Checkpointing
    IngestionProgress,
    CheckpointManager,
    PacmanRunner,
    CHECKPOINT_INTERVAL,
    CHECKPOINT_TIME_INTERVAL,
)

__all__ = [
    "SOURCE_ID",
    "SOURCE_TYPE",
    "TARGET_INDEX",
    "Tier",
    "TierDecision",
    "classify",
    "build_document",
    "CONTEXT_WORDS_BEFORE",
    "CONTEXT_WORDS_AFTER",
    "extract_context",
    "load_domain_set",
    "load_all_domain_sets",
    "load_tripwire_entities",
    "build_tripwire_automaton",
    "IngestionProgress",
    "CheckpointManager",
    "PacmanRunner",
    "CHECKPOINT_INTERVAL",
    "CHECKPOINT_TIME_INTERVAL",
]
