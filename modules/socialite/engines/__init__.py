"""
SOCIALITE Engines - Search engine integrations for social media discovery.

Provides unified interface to search engines for finding social profiles:
- Google (site:linkedin.com, site:facebook.com, etc.)
- Bing
- DuckDuckGo
- Specialized social search APIs
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Individual search result."""
    url: str
    title: str = ""
    snippet: str = ""
    platform: str = ""
    source_engine: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineConfig:
    """Configuration for a search engine."""
    name: str
    enabled: bool = True
    rate_limit: float = 1.0  # requests per second
    max_results: int = 10
    api_key_env: Optional[str] = None


class BaseEngine:
    """Base class for search engines."""

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig(name="base")

    async def search(self, query: str, **kwargs) -> List[SearchResult]:
        """Execute search query. Override in subclasses."""
        raise NotImplementedError

    def build_social_query(self, name: str, platform: str) -> str:
        """Build a platform-specific search query."""
        site_map = {
            "linkedin": "site:linkedin.com/in",
            "facebook": "site:facebook.com",
            "twitter": "site:twitter.com OR site:x.com",
            "instagram": "site:instagram.com",
            "threads": "site:threads.net",
            "tiktok": "site:tiktok.com/@",
        }
        site = site_map.get(platform.lower(), "")
        return f'"{name}" {site}' if site else f'"{name}"'


class GoogleEngine(BaseEngine):
    """Google search engine."""

    def __init__(self):
        super().__init__(EngineConfig(
            name="google",
            api_key_env="GOOGLE_API_KEY",
            max_results=10
        ))


class BingEngine(BaseEngine):
    """Bing search engine."""

    def __init__(self):
        super().__init__(EngineConfig(
            name="bing",
            api_key_env="BING_API_KEY",
            max_results=10
        ))


class DuckDuckGoEngine(BaseEngine):
    """DuckDuckGo search engine (no API key required)."""

    def __init__(self):
        super().__init__(EngineConfig(
            name="duckduckgo",
            max_results=10
        ))


# Available engines
ENGINES = {
    "google": GoogleEngine,
    "bing": BingEngine,
    "duckduckgo": DuckDuckGoEngine,
}


def get_engine(name: str) -> Optional[BaseEngine]:
    """Get an engine instance by name."""
    engine_class = ENGINES.get(name.lower())
    if engine_class:
        return engine_class()
    return None


def list_engines() -> List[str]:
    """List available engine names."""
    return list(ENGINES.keys())


__all__ = [
    "SearchResult",
    "EngineConfig",
    "BaseEngine",
    "GoogleEngine",
    "BingEngine",
    "DuckDuckGoEngine",
    "ENGINES",
    "get_engine",
    "list_engines",
]
