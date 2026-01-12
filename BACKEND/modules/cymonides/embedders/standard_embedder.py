#!/usr/bin/env python3
"""
Sastre Standard Embedder
Single interface for all vector embeddings across Sastre infrastructure.

Model: intfloat/multilingual-e5-large (1024D)
Usage: query/passage prefixes for asymmetric search
"""

import torch
import numpy as np
from typing import List, Union, Optional
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# SASTRE STANDARD MODEL
MODEL_NAME = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024


class StandardEmbedder:
    """
    Standardized embedder for all Sastre modules.
    Uses intfloat/multilingual-e5-large (1024D) for consistency.
    
    Singleton pattern - only one model loaded per process.
    """

    _instance = None  # Singleton

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info(f"Loading Sastre standard model: {MODEL_NAME}")

        # Detect device
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        logger.info(f"Using device: {self.device}")

        # Load model
        self.model = SentenceTransformer(MODEL_NAME, device=self.device)
        self._initialized = True

        logger.info(f"Embedder initialized: {EMBEDDING_DIM}D, device={self.device}")

    def encode_query(self, text: str, normalize: bool = True) -> List[float]:
        """
        Encode search query.
        e5 models use 'query:' prefix for asymmetric search.
        
        Args:
            text: Query text
            normalize: Normalize embeddings (default True)
            
        Returns:
            1024-dimensional embedding as list
        """
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIM
            
        prefixed = f"query: {text}"
        embedding = self.model.encode(
            prefixed,
            convert_to_numpy=True,
            normalize_embeddings=normalize
        )
        return embedding.tolist()

    def encode_passage(self, text: str, normalize: bool = True) -> List[float]:
        """
        Encode document/passage.
        e5 models use 'passage:' prefix for indexing.
        
        Args:
            text: Document text
            normalize: Normalize embeddings (default True)
            
        Returns:
            1024-dimensional embedding as list
        """
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIM
            
        prefixed = f"passage: {text}"
        embedding = self.model.encode(
            prefixed,
            convert_to_numpy=True,
            normalize_embeddings=normalize
        )
        return embedding.tolist()

    def encode_batch_queries(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Batch encode queries.
        
        Args:
            texts: List of query texts
            normalize: Normalize embeddings
            batch_size: Batch size for encoding
            show_progress: Show progress bar
            
        Returns:
            List of 1024D embeddings
        """
        if not texts:
            return []
            
        prefixed = [f"query: {t}" if t and t.strip() else "query: " for t in texts]
        embeddings = self.model.encode(
            prefixed,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            batch_size=batch_size,
            show_progress_bar=show_progress
        )
        return embeddings.tolist()

    def encode_batch_passages(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Batch encode passages.
        
        Args:
            texts: List of document texts
            normalize: Normalize embeddings
            batch_size: Batch size for encoding
            show_progress: Show progress bar
            
        Returns:
            List of 1024D embeddings
        """
        if not texts:
            return []
            
        prefixed = [f"passage: {t}" if t and t.strip() else "passage: " for t in texts]
        embeddings = self.model.encode(
            prefixed,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            batch_size=batch_size,
            show_progress_bar=show_progress
        )
        return embeddings.tolist()

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return EMBEDDING_DIM

    @property
    def model_name(self) -> str:
        """Return model name."""
        return MODEL_NAME


# Singleton instance
_embedder = None


def get_embedder() -> StandardEmbedder:
    """
    Get singleton embedder instance.
    Creates on first call, reuses thereafter.
    """
    global _embedder
    if _embedder is None:
        _embedder = StandardEmbedder()
    return _embedder


# Convenience functions
def encode_query(text: str) -> List[float]:
    """Quick encode query."""
    return get_embedder().encode_query(text)


def encode_passage(text: str) -> List[float]:
    """Quick encode passage."""
    return get_embedder().encode_passage(text)


def encode_queries(texts: List[str], batch_size: int = 32, show_progress: bool = False) -> List[List[float]]:
    """Quick batch encode queries."""
    return get_embedder().encode_batch_queries(texts, batch_size=batch_size, show_progress=show_progress)


def encode_passages(texts: List[str], batch_size: int = 32, show_progress: bool = False) -> List[List[float]]:
    """Quick batch encode passages."""
    return get_embedder().encode_batch_passages(texts, batch_size=batch_size, show_progress=show_progress)


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== Sastre Standard Embedder Test ===")
    print(f"Model: {MODEL_NAME}")
    print(f"Dimensions: {EMBEDDING_DIM}")
    
    embedder = get_embedder()
    
    # Test single encoding
    query_vec = embedder.encode_query("artificial intelligence research")
    passage_vec = embedder.encode_passage("This company specializes in AI and machine learning")
    
    print(f"\nQuery vector length: {len(query_vec)}")
    print(f"Passage vector length: {len(passage_vec)}")
    print(f"Query vector sample: {query_vec[:5]}")
    
    # Test cosine similarity
    from numpy import dot
    from numpy.linalg import norm
    
    similarity = dot(query_vec, passage_vec) / (norm(query_vec) * norm(passage_vec))
    print(f"\nCosine similarity: {similarity:.4f}")
    
    # Test batch encoding
    queries = ["machine learning", "data science", "natural language processing"]
    passages = ["AI research company", "Statistical analysis firm", "Text processing software"]
    
    query_vecs = embedder.encode_batch_queries(queries, show_progress=True)
    passage_vecs = embedder.encode_batch_passages(passages, show_progress=True)
    
    print(f"\nBatch encoded {len(query_vecs)} queries and {len(passage_vecs)} passages")
    print("✅ All tests passed")
