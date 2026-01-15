"""
Stub intelligent categorizer when full module is not available.
"""
from typing import List, Dict, Any

class IntelligentCategorizer:
    """Minimal stub when full categorizer is not available"""
    def __init__(self, *args, **kwargs):
        pass

    async def categorize(self, results: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
        """Categorize results."""
        return results

    async def categorize_batch(self, results: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
        """Categorize batch of results."""
        return results

    def get_category(self, url: str, title: str = "", description: str = "") -> str:
        """Get category for a single URL."""
        return "miscellaneous"

__all__ = ["IntelligentCategorizer"]
