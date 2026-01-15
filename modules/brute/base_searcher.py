#!/usr/bin/env python3
"""
Base Searcher Classes for Brute Search
Provides dataclasses and base interfaces for search operations
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class SearchResult:
    """Standard search result data class"""
    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""
    engine: str = ""
    engine_code: str = ""
    timestamp: Optional[datetime] = None
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'url': self.url,
            'title': self.title,
            'snippet': self.snippet,
            'source': self.source,
            'engine': self.engine,
            'engine_code': self.engine_code,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'score': self.score,
            **self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        """Create from dictionary"""
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            url=data.get('url', ''),
            title=data.get('title', ''),
            snippet=data.get('snippet', ''),
            source=data.get('source', ''),
            engine=data.get('engine', ''),
            engine_code=data.get('engine_code', ''),
            timestamp=timestamp,
            score=data.get('score', 0.0),
            metadata={k: v for k, v in data.items() if k not in
                     ['url', 'title', 'snippet', 'source', 'engine', 'engine_code', 'timestamp', 'score']}
        )


class BaseSearcher:
    """Base class for search implementations"""

    name: str = "BaseSearcher"
    code: str = "BASE"

    def __init__(self, **kwargs):
        self.config = kwargs

    def search(self, query: str, max_results: int = 50, **kwargs) -> List[SearchResult]:
        """Execute search and return results"""
        raise NotImplementedError("Subclasses must implement search()")

    async def search_async(self, query: str, max_results: int = 50, **kwargs) -> List[SearchResult]:
        """Async search implementation"""
        return self.search(query, max_results, **kwargs)

    def is_available(self) -> bool:
        """Check if searcher is properly configured"""
        return True


__all__ = ['SearchResult', 'BaseSearcher']
