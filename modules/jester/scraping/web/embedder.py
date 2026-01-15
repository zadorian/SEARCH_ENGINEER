"""
DRILL Embedder

Fast local embeddings using FastEmbed (free, no API keys).
Generates 384-dimensional vectors for semantic search in Elasticsearch.

Uses BAAI/bge-small-en-v1.5:
- 33MB model size
- 384 dimensions
- ~1ms per embedding
- Apache 2.0 license
"""

import asyncio
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import numpy as np
from pathlib import Path
import json
import hashlib

# FastEmbed - lightweight embedding library
try:
    from fastembed import TextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False
    TextEmbedding = None


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""
    text: str
    embedding: List[float]
    model: str
    dimensions: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "embedding": self.embedding,
            "model": self.model,
            "dimensions": self.dimensions,
        }


class DrillEmbedder:
    """
    Fast local embeddings for DRILL crawler.

    No API keys required - runs entirely locally.
    Optimized for investigation text: company names, person names, snippets.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"  # 33MB, 384 dims, fast
    ALTERNATIVE_MODELS = {
        "small": "BAAI/bge-small-en-v1.5",      # 33MB, 384 dims
        "base": "BAAI/bge-base-en-v1.5",        # 110MB, 768 dims
        "large": "BAAI/bge-large-en-v1.5",      # 335MB, 1024 dims
        "multilingual": "BAAI/bge-small-zh-v1.5",  # For Chinese/multilingual
    }

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Optional[Path] = None,
        batch_size: int = 32,
    ):
        """
        Initialize embedder.

        Args:
            model_name: FastEmbed model name (default: bge-small-en-v1.5)
            cache_dir: Optional cache directory for embeddings
            batch_size: Batch size for bulk embedding
        """
        if not FASTEMBED_AVAILABLE:
            raise ImportError(
                "FastEmbed not installed. Run: pip install fastembed"
            )

        self.model_name = model_name
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        self._model: Optional[TextEmbedding] = None
        self._cache: Dict[str, List[float]] = {}

        # Load cache if exists
        if cache_dir:
            self._load_cache()

    @property
    def model(self) -> TextEmbedding:
        """Lazy load model on first use."""
        if self._model is None:
            self._model = TextEmbedding(self.model_name)
        return self._model

    @property
    def dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        dims_map = {
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-large-en-v1.5": 1024,
            "BAAI/bge-small-zh-v1.5": 512,
        }
        return dims_map.get(self.model_name, 384)

    def embed(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector)
        """
        # Check cache
        cache_key = self._cache_key(text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Generate embedding
        embeddings = list(self.model.embed([text]))
        embedding = embeddings[0].tolist()

        # Cache
        self._cache[cache_key] = embedding

        return embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        results = []
        uncached_texts = []
        uncached_indices = []

        # Check cache first
        for i, text in enumerate(texts):
            cache_key = self._cache_key(text)
            if cache_key in self._cache:
                results.append(self._cache[cache_key])
            else:
                results.append(None)  # Placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Embed uncached texts in batches
        if uncached_texts:
            for batch_start in range(0, len(uncached_texts), self.batch_size):
                batch = uncached_texts[batch_start:batch_start + self.batch_size]
                embeddings = list(self.model.embed(batch))

                for j, embedding in enumerate(embeddings):
                    idx = uncached_indices[batch_start + j]
                    emb_list = embedding.tolist()
                    results[idx] = emb_list

                    # Cache
                    cache_key = self._cache_key(uncached_texts[batch_start + j])
                    self._cache[cache_key] = emb_list

        return results

    def embed_entities(
        self,
        entities: Dict[str, List[str]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Embed extracted entities by type.

        Args:
            entities: Dict with keys like 'companies', 'persons', etc.

        Returns:
            Dict with same keys, values are lists of {text, embedding}
        """
        result = {}

        for entity_type, texts in entities.items():
            if not texts:
                result[entity_type] = []
                continue

            embeddings = self.embed_batch(texts)
            result[entity_type] = [
                {"text": text, "embedding": emb}
                for text, emb in zip(texts, embeddings)
            ]

        return result

    async def embed_async(self, text: str) -> List[float]:
        """Async wrapper for embed (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def embed_batch_async(self, texts: List[str]) -> List[List[float]]:
        """Async wrapper for batch embedding."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)

    def similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score between -1 and 1
        """
        a = np.array(embedding1)
        b = np.array(embedding2)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def find_similar(
        self,
        query_embedding: List[float],
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
        min_similarity: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Find most similar items from candidates.

        Args:
            query_embedding: Query vector
            candidates: List of dicts with 'embedding' key
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold

        Returns:
            Top-k similar items with similarity scores
        """
        results = []

        for candidate in candidates:
            if 'embedding' not in candidate:
                continue

            sim = self.similarity(query_embedding, candidate['embedding'])
            if sim >= min_similarity:
                results.append({
                    **candidate,
                    'similarity': sim,
                })

        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)

        return results[:top_k]

    def _cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()

    def _load_cache(self):
        """Load embedding cache from disk."""
        if not self.cache_dir:
            return

        cache_file = Path(self.cache_dir) / "drill_embeddings_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def save_cache(self):
        """Save embedding cache to disk."""
        if not self.cache_dir:
            return

        cache_file = Path(self.cache_dir) / "drill_embeddings_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_file, 'w') as f:
            json.dump(self._cache, f)

    def clear_cache(self):
        """Clear in-memory cache."""
        self._cache = {}


# Singleton instance for convenience
_default_embedder: Optional[DrillEmbedder] = None


def get_embedder() -> DrillEmbedder:
    """Get default embedder instance (lazy initialization)."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = DrillEmbedder()
    return _default_embedder


def embed(text: str) -> List[float]:
    """Quick embed using default embedder."""
    return get_embedder().embed(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Quick batch embed using default embedder."""
    return get_embedder().embed_batch(texts)
