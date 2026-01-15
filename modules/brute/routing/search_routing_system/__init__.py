"""
Search Routing System
=====================
Query routing and analysis for search integration.

JSON Configs:
- engine_to_search_type_matrix_external.json: L1/L2/L3 engine assignments
- search_type_to_engines.json: Current and recommended engines per search type
- engine_availability.json: Engine metadata (auth, operators, categories)
- category_matrix.json: Category-specific data sources

Python Modules:
- query_routing.py: QueryRouter class for operator detection and routing
"""

import json
from pathlib import Path

_DIR = Path(__file__).parent

# Load JSON configs lazily
def load_engine_matrix_external():
    """Load the external engine-to-search-type matrix."""
    with open(_DIR / "engine_to_search_type_matrix_external.json") as f:
        return json.load(f)

def load_search_type_to_engines():
    """Load the search type to engines mapping."""
    with open(_DIR / "search_type_to_engines.json") as f:
        return json.load(f)

def load_engine_availability():
    """Load engine availability metadata."""
    with open(_DIR / "engine_availability.json") as f:
        return json.load(f)

def load_category_matrix():
    """Load category-specific source matrix."""
    with open(_DIR / "category_matrix.json") as f:
        return json.load(f)

# Import QueryRouter
try:
    from .query_routing import QueryRouter
except ImportError:
    QueryRouter = None

__all__ = [
    "load_engine_matrix_external",
    "load_search_type_to_engines",
    "load_engine_availability",
    "load_category_matrix",
    "QueryRouter",
]
