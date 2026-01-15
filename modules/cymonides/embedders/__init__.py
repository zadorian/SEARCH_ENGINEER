"""
Sastre Shared Embedders
Standard embedding utilities for all modules.
"""

from .standard_embedder import (
    StandardEmbedder,
    get_embedder,
    encode_query,
    encode_passage,
    encode_queries,
    encode_passages,
    MODEL_NAME,
    EMBEDDING_DIM
)

__all__ = [
    'StandardEmbedder',
    'get_embedder',
    'encode_query',
    'encode_passage',
    'encode_queries',
    'encode_passages',
    'MODEL_NAME',
    'EMBEDDING_DIM',
]
