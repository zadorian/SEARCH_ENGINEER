"""
PACMAN Embeddings Module
Semantic detection of ownership, compliance, and red flag signals

Contains:
- domain_embedder: OpenAI embeddings with CONCEPT_SETS for semantic classification
- tripwire_embeddings: Red flag pattern embedding matching
- golden_lists: Comprehensive golden lists for company intelligence
"""

from .domain_embedder import (
    DomainEmbedder,
    CONCEPT_SETS,
    EMBEDDING_MODEL,
    EMBEDDING_DIMS,
)

__all__ = [
    'DomainEmbedder',
    'CONCEPT_SETS',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMS',
]
