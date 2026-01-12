"""
Source - Registered data source with persistent state.

Sources are first-class entities that track sync state, health metrics,
and configuration for incremental ingestion.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class SourceType(Enum):
    """Types of data sources."""
    FILE = "file"                 # Single file
    DIRECTORY = "directory"       # Directory of files
    PARQUET = "parquet"           # Parquet files
    JSONL = "jsonl"               # JSONL files
    API = "api"                   # REST API endpoint
    ELASTICSEARCH = "elasticsearch"  # Another ES index
    STREAM = "stream"             # Kafka/streaming
    BREACH_DUMP = "breach_dump"   # Breach data dump


class SourceStatus(Enum):
    """Source health status."""
    HEALTHY = "healthy"           # Last sync succeeded
    DEGRADED = "degraded"         # Partial success or warnings
    FAILED = "failed"             # Last sync failed
    DISABLED = "disabled"         # Manually disabled
    UNKNOWN = "unknown"           # Never synced


@dataclass
class SourceConfig:
    """
    Type-specific source configuration.
    
    Examples:
        FILE: {"path": "/data/breach.jsonl", "format": "jsonl"}
        DIRECTORY: {"path": "/data/breaches/", "pattern": "*.jsonl", "recursive": true}
        PARQUET: {"path": "/data/pdfs/", "partition_cols": ["date"]}
        API: {"url": "https://api.example.com/data", "auth": "bearer", "pagination": "cursor"}
        ELASTICSEARCH: {"index": "old-index", "query": {"match_all": {}}}
    """
    path: Optional[str] = None
    format: Optional[str] = None
    pattern: Optional[str] = None
    recursive: bool = False
    partition_cols: List[str] = field(default_factory=list)
    
    # API-specific
    url: Optional[str] = None
    auth_type: Optional[str] = None
    auth_config: Dict[str, str] = field(default_factory=dict)
    pagination_type: Optional[str] = None
    pagination_config: Dict[str, Any] = field(default_factory=dict)
    
    # ES-specific
    index: Optional[str] = None
    query: Dict[str, Any] = field(default_factory=dict)
    
    # Breach-specific
    breach_name: Optional[str] = None
    breach_date: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != [] and v != {}}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceConfig":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k) or k in cls.__dataclass_fields__})


@dataclass
class Source:
    """
    Registered data source with sync state and health metrics.
    
    Sources track:
    - Configuration (how to read)
    - Sync state (cursor for incremental)
    - Health metrics (error rate, throughput)
    - Statistics (docs indexed, deduped)
    """
    
    # === Identity ===
    id: str = field(default_factory=lambda: f"src-{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    
    # === Type & Config ===
    type: SourceType = SourceType.FILE
    config: SourceConfig = field(default_factory=SourceConfig)
    
    # === Schema ===
    input_schema: Optional[str] = None    # Expected raw format
    output_pipeline: str = "content"      # Pipeline to use
    target_tier: str = "c2"               # Default target tier
    
    # === State ===
    enabled: bool = True
    status: SourceStatus = SourceStatus.UNKNOWN
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # === Sync State ===
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_job_id: Optional[str] = None
    sync_cursor: Dict[str, Any] = field(default_factory=dict)  # Opaque cursor for incremental
    
    # === Metrics ===
    total_docs_seen: int = 0
    total_docs_indexed: int = 0
    total_docs_failed: int = 0
    total_docs_deduped: int = 0
    avg_doc_quality: float = 0.0
    avg_throughput: float = 0.0           # docs/sec
    
    # === Health ===
    error_rate_7d: float = 0.0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    consecutive_failures: int = 0
    
    # === Metadata ===
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_sync_state(
        self,
        status: str,
        cursor: Dict[str, Any],
        docs_processed: int,
        docs_indexed: int,
        docs_failed: int,
        docs_deduped: int,
        job_id: str
    ):
        """Update source after a sync operation."""
        self.last_sync_at = datetime.utcnow()
        self.last_sync_status = status
        self.last_sync_job_id = job_id
        self.sync_cursor = cursor
        self.updated_at = datetime.utcnow()
        
        self.total_docs_seen += docs_processed
        self.total_docs_indexed += docs_indexed
        self.total_docs_failed += docs_failed
        self.total_docs_deduped += docs_deduped
        
        if status == "success":
            self.status = SourceStatus.HEALTHY
            self.consecutive_failures = 0
        elif status == "partial":
            self.status = SourceStatus.DEGRADED
        else:
            self.status = SourceStatus.FAILED
            self.consecutive_failures += 1
            
    def record_error(self, error: str):
        """Record an error for this source."""
        self.last_error = error
        self.last_error_at = datetime.utcnow()
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.status = SourceStatus.FAILED
            
    def disable(self, reason: str = ""):
        """Disable the source."""
        self.enabled = False
        self.status = SourceStatus.DISABLED
        self.metadata["disabled_reason"] = reason
        self.metadata["disabled_at"] = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow()
        
    def enable(self):
        """Re-enable the source."""
        self.enabled = True
        self.status = SourceStatus.UNKNOWN
        self.metadata.pop("disabled_reason", None)
        self.metadata.pop("disabled_at", None)
        self.updated_at = datetime.utcnow()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ES storage."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type.value,
            "config": self.config.to_dict(),
            "input_schema": self.input_schema,
            "output_pipeline": self.output_pipeline,
            "target_tier": self.target_tier,
            "enabled": self.enabled,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "last_sync_job_id": self.last_sync_job_id,
            "sync_cursor": self.sync_cursor,
            "total_docs_seen": self.total_docs_seen,
            "total_docs_indexed": self.total_docs_indexed,
            "total_docs_failed": self.total_docs_failed,
            "total_docs_deduped": self.total_docs_deduped,
            "avg_doc_quality": self.avg_doc_quality,
            "avg_throughput": self.avg_throughput,
            "error_rate_7d": self.error_rate_7d,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "consecutive_failures": self.consecutive_failures,
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Source":
        """Create source from dictionary."""
        source = cls(
            id=data.get("id", f"src-{uuid.uuid4().hex[:8]}"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            type=SourceType(data.get("type", "file")),
            config=SourceConfig.from_dict(data.get("config", {})),
            input_schema=data.get("input_schema"),
            output_pipeline=data.get("output_pipeline", "content"),
            target_tier=data.get("target_tier", "c2"),
            enabled=data.get("enabled", True),
            status=SourceStatus(data.get("status", "unknown")),
            sync_cursor=data.get("sync_cursor", {}),
            total_docs_seen=data.get("total_docs_seen", 0),
            total_docs_indexed=data.get("total_docs_indexed", 0),
            total_docs_failed=data.get("total_docs_failed", 0),
            total_docs_deduped=data.get("total_docs_deduped", 0),
            avg_doc_quality=data.get("avg_doc_quality", 0.0),
            avg_throughput=data.get("avg_throughput", 0.0),
            error_rate_7d=data.get("error_rate_7d", 0.0),
            last_error=data.get("last_error"),
            consecutive_failures=data.get("consecutive_failures", 0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        
        # Parse dates
        if data.get("created_at"):
            source.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            source.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("last_sync_at"):
            source.last_sync_at = datetime.fromisoformat(data["last_sync_at"])
        if data.get("last_error_at"):
            source.last_error_at = datetime.fromisoformat(data["last_error_at"])
            
        source.last_sync_status = data.get("last_sync_status")
        source.last_sync_job_id = data.get("last_sync_job_id")
        
        return source
