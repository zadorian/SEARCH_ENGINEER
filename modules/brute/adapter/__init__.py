"""
CyMonides Integration with Drill Search Elasticsearch

This module provides the bridge between CyMonides document processing
and Drill Search's Elasticsearch infrastructure with embedded semantic search.

Features:
- Index nodes/edges into Drill Search's Elasticsearch
- Generate 384-dim embeddings using all-MiniLM-L6-v2
- Validate edges against 69 relationship types (edge_types.json)
- Convert entities to/from FTM (Follow The Money) schemas
- Semantic, hybrid, and keyword search
"""

from pathlib import Path

# Schema file paths
# Navigate up to project root (drill-search-app)
# adapter -> brute -> modules -> python-backend -> drill-search-app
PROJECT_ROOT = Path(__file__).parents[4]
SCHEMA_DIR = PROJECT_ROOT / "input_output" / "ontology"

EDGE_TYPES_PATH = SCHEMA_DIR / "relationships.json"
FTM_SCHEMA_PATH = SCHEMA_DIR / "ftm_mapping.json"

# Import main adapter
try:
    from .drill_search_adapter import DrillSearchAdapter
except ImportError:
    DrillSearchAdapter = None

__all__ = [
    'DrillSearchAdapter',
    'EDGE_TYPES_PATH',
    'FTM_SCHEMA_PATH',
    'SCHEMA_DIR'
]

__version__ = '2.0.0'
