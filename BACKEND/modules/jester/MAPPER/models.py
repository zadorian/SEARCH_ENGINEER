"""
JESTER MAPPER - Data Models
============================

Core data structures for URL discovery.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class DiscoveredURL:
    """
    A URL discovered during domain mapping.

    Attributes:
        url: The full URL (e.g., https://example.com/page)
        source: Discovery source (e.g., "crt.sh", "firecrawl_map", "wayback")
        discovered_at: Unix timestamp when discovered

        # Optional metadata
        domain: The root domain (e.g., "example.com")
        subdomain: The subdomain if any (e.g., "api" from api.example.com)
        path: The URL path (e.g., "/page")
        title: Page title if known
        description: Page description if known
        parent_url: URL that linked to this URL (for crawl discovery)

        # Source-specific metadata
        timestamp: Archive timestamp (for Wayback/CC)
        status_code: HTTP status if known
        content_type: Content-Type if known
        priority: sitemap.xml priority if known
        trust_flow: Majestic Trust Flow if known
        citation_flow: Majestic Citation Flow if known
        ref_domains: Number of referring domains (backlink sources)
    """
    url: str
    source: str
    discovered_at: float = field(default_factory=lambda: datetime.now().timestamp())

    # Optional metadata
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    parent_url: Optional[str] = None

    # Archive metadata
    timestamp: Optional[str] = None  # Wayback/CC timestamp (e.g., "20240115120000")
    is_archived: bool = False  # Was this discovered from an archive source?
    archive_url: Optional[str] = None  # URL to view archived version (e.g., web.archive.org/...)
    archive_source: Optional[str] = None  # "wayback" or "commoncrawl"

    # Current existence verification
    current_exists: Optional[bool] = None  # Does URL currently exist? None = not checked
    current_status: Optional[int] = None  # HTTP status when verifying current version
    current_checked_at: Optional[float] = None  # When we checked current existence

    # HTTP metadata (from discovery, NOT verification)
    status_code: Optional[int] = None  # Historical status from archive
    content_type: Optional[str] = None

    # Sitemap metadata
    priority: Optional[float] = None
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None

    # Backlink metadata
    trust_flow: Optional[int] = None
    citation_flow: Optional[int] = None
    ref_domains: Optional[int] = None

    # Raw data from source
    raw: Optional[Dict[str, Any]] = None

    def __hash__(self):
        """Hash by URL for deduplication."""
        return hash(self.url)

    def __eq__(self, other):
        """Equal if URLs match."""
        if isinstance(other, DiscoveredURL):
            return self.url == other.url
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "source": self.source,
            "discovered_at": self.discovered_at,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "path": self.path,
            "title": self.title,
            "description": self.description,
            "parent_url": self.parent_url,
            # Archive fields
            "timestamp": self.timestamp,
            "is_archived": self.is_archived,
            "archive_url": self.archive_url,
            "archive_source": self.archive_source,
            # Current existence
            "current_exists": self.current_exists,
            "current_status": self.current_status,
            "current_checked_at": self.current_checked_at,
            # HTTP metadata
            "status_code": self.status_code,
            "content_type": self.content_type,
            "priority": self.priority,
            "lastmod": self.lastmod,
            "changefreq": self.changefreq,
            "trust_flow": self.trust_flow,
            "citation_flow": self.citation_flow,
            "ref_domains": self.ref_domains,
        }


@dataclass
class MappingResult:
    """
    Result of a domain mapping operation.

    Attributes:
        domain: The domain that was mapped
        urls: List of discovered URLs
        sources_completed: Dict of source -> count of URLs found
        sources_failed: Dict of source -> error message
        duration_seconds: Total time taken
        deduplicated: Whether URLs were deduplicated
    """
    domain: str
    urls: List[DiscoveredURL] = field(default_factory=list)
    sources_completed: Dict[str, int] = field(default_factory=dict)
    sources_failed: Dict[str, str] = field(default_factory=dict)
    duration_seconds: float = 0.0
    deduplicated: bool = True

    @property
    def total_urls(self) -> int:
        return len(self.urls)

    @property
    def total_sources(self) -> int:
        return len(self.sources_completed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "total_urls": self.total_urls,
            "sources_completed": self.sources_completed,
            "sources_failed": self.sources_failed,
            "duration_seconds": self.duration_seconds,
            "urls": [u.to_dict() for u in self.urls],
        }
