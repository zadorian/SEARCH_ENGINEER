"""
CYMONIDES Indexers

Central utilities for all Elasticsearch indexing and search operations.

Index Architecture:
  - cymonides-1: Node graph (entities, relationships, SUBJECT categories, NEXUS edges)
  - cymonides-2: Raw incoming search results
  - cymonides-3: Unified document index (millions of docs under consolidation)

This module provides:
  - Keyword indexing
  - Embedding vector indexing
  - Hybrid search (BM25 + semantic)
  - Node graph operations (C-1)
  - Document consolidation (C-3)
"""

from pathlib import Path

INDEXERS_DIR = Path(__file__).parent
