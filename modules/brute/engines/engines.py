#!/usr/bin/env python3
"""
Base Engine Classes for Brute Search
Provides the foundational interfaces for all search engines
"""

from abc import ABC
from typing import Any, Dict, List, Optional


class BaseEngine(ABC):
    """Base class for all search engines"""

    code: str = 'ENG'  # Short engine code (e.g., 'GO' for Google)
    name: str = 'BaseEngine'  # Human readable name

    def search(self, query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute search query and return results

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            **kwargs: Engine-specific parameters

        Returns:
            List of result dicts with at minimum:
            - url: Result URL
            - title: Result title
            - snippet: Description/snippet text
        """
        raise NotImplementedError("Subclasses must implement search()")

    def is_available(self) -> bool:
        """Check if engine is properly configured and available"""
        return True

    def get_search_url(self, query: str) -> Optional[str]:
        """Generate a URL for manual search on this engine"""
        return None


class StreamingEngine(BaseEngine):
    """Base class for engines that support streaming results"""

    def search_stream(self, query: str, max_results: int = 50, **kwargs):
        """
        Generator that yields results as they become available

        Yields:
            Dict with result data
        """
        # Default implementation falls back to batch search
        results = self.search(query, max_results, **kwargs)
        for result in results:
            yield result


class AsyncEngine(BaseEngine):
    """Base class for engines with async support"""

    async def search_async(self, query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Async version of search"""
        # Default implementation falls back to sync
        return self.search(query, max_results, **kwargs)


__all__ = ['BaseEngine', 'StreamingEngine', 'AsyncEngine']
