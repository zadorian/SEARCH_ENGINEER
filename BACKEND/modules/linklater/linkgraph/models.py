"""
LinkLater Graph Models

Data models for link records and graph operations.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class LinkRecord:
    """Represents a link between two domains."""
    source: str
    target: str
    weight: Optional[int] = None
    anchor_text: Optional[str] = None
    provider: str = "unknown"  # cc_graph, globallinks, etc.

    # Temporal fields (populated by temporal enrichment)
    first_seen: Optional[str] = None  # ISO timestamp
    last_seen: Optional[str] = None   # ISO timestamp
    is_live: Optional[bool] = None
    temporal_source: Optional[str] = None  # wayback, commoncrawl, etc.

    # Additional metadata (source_id, target_id, collection, etc.)
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
