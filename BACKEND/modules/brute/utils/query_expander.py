"""
Query expander stub.
"""
from typing import List

class QueryExpander:
    """Stub query expander when full module is not available"""
    def __init__(self, *args, **kwargs):
        pass

    def expand(self, query: str) -> List[str]:
        """Expand query into variations."""
        return [query]

    def get_variations(self, query: str) -> List[str]:
        """Get query variations."""
        return [query]

    def add_synonyms(self, query: str) -> List[str]:
        """Add synonym variations."""
        return [query]

__all__ = ["QueryExpander"]
