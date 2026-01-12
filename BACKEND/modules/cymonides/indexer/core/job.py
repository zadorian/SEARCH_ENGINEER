"""
IndexingJob - Represents a single indexing job with full lifecycle tracking.

Jobs have:
- Configuration (source, target, pipeline)
- Progress tracking (processed, indexed, failed, deduped)
- Checkpointing for resume
- Error tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class JobStatus(Enum):
    """Job lifecycle status."""
    PENDING = "pending"           # Created but not started
    RUNNING = "running"           # Currently executing
    PAUSED = "paused"             # Paused by user
    COMPLETED = "completed"       # Successfully completed
    FAILED = "failed"             # Failed with error
    CANCELLED = "cancelled"       # Cancelled by user


@dataclass
class JobProgress:
    """Progress tracking for an indexing job."""
    
    total: int = 0                # Total items to process (if known)
    processed: int = 0            # Items processed so far
    indexed: int = 0              # Items successfully indexed
    failed: int = 0               # Items that failed
    deduped: int = 0              # Items skipped as duplicates
    skipped: int = 0              # Items skipped (filter, validation)
    
    # Rate tracking
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None
    
    @property
    def percent(self) -> float:
        """Calculate completion percentage."""
        if self.total > 0:
            return (self.processed / self.total) * 100
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.processed > 0:
            return (self.indexed / self.processed) * 100
        return 0.0
    
    @property
    def docs_per_second(self) -> float:
        """Calculate processing rate."""
        if self.start_time and self.last_update:
            elapsed = (self.last_update - self.start_time).total_seconds()
            if elapsed > 0:
                return self.processed / elapsed
        return 0.0
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate time remaining."""
        rate = self.docs_per_second
        if rate > 0 and self.total > 0:
            remaining = self.total - self.processed
            return remaining / rate
        return None
    
    def update(self, indexed: int = 0, failed: int = 0, deduped: int = 0, skipped: int = 0):
        """Update progress counters."""
        self.indexed += indexed
        self.failed += failed
        self.deduped += deduped
        self.skipped += skipped
        self.processed = self.indexed + self.failed + self.deduped + self.skipped
        self.last_update = datetime.utcnow()
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "processed": self.processed,
            "indexed": self.indexed,
            "failed": self.failed,
            "deduped": self.deduped,
            "skipped": self.skipped,
            "percent": round(self.percent, 2),
            "success_rate": round(self.success_rate, 2),
            "docs_per_second": round(self.docs_per_second, 2),
            "eta_seconds": round(self.eta_seconds, 0) if self.eta_seconds else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


@dataclass
class JobCheckpoint:
    """Checkpoint for resuming interrupted jobs."""
    
    last_offset: int = 0              # File offset or record number
    last_id: Optional[str] = None     # Last processed document ID
    last_source_cursor: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    checkpoint_file: Optional[str] = None
    
    # Progress at checkpoint
    progress_snapshot: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_offset": self.last_offset,
            "last_id": self.last_id,
            "last_source_cursor": self.last_source_cursor,
            "timestamp": self.timestamp.isoformat(),
            "checkpoint_file": self.checkpoint_file,
            "progress_snapshot": self.progress_snapshot,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobCheckpoint":
        checkpoint = cls(
            last_offset=data.get("last_offset", 0),
            last_id=data.get("last_id"),
            last_source_cursor=data.get("last_source_cursor", {}),
            checkpoint_file=data.get("checkpoint_file"),
            progress_snapshot=data.get("progress_snapshot", {}),
        )
        if data.get("timestamp"):
            checkpoint.timestamp = datetime.fromisoformat(data["timestamp"])
        return checkpoint


@dataclass
class IndexingJob:
    """
    Represents a single indexing job with full lifecycle tracking.
    
    Jobs are persisted to ES for durability and queryability.
    """
    
    # === Identity ===
    job_id: str = field(default_factory=lambda: f"job-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}")
    name: Optional[str] = None
    
    # === Status ===
    status: JobStatus = JobStatus.PENDING
    
    # === Source Configuration ===
    source_id: Optional[str] = None       # Registered source ID
    source_type: str = "file"             # file, directory, parquet, etc.
    source_path: str = ""                 # Path/URL to read from
    source_config: Dict[str, Any] = field(default_factory=dict)
    
    # === Target Configuration ===
    target_index: str = ""                # ES index to write to
    target_tier: str = "c2"               # c1, c2, c3
    
    # === Pipeline ===
    pipeline: str = "content"             # Pipeline name
    pipeline_version: Optional[str] = None
    pipeline_config: Dict[str, Any] = field(default_factory=dict)
    
    # === Options ===
    batch_size: int = 100
    checkpoint_every: int = 1000
    dedup_enabled: bool = True
    dedup_field: str = "content_hash"
    extract_entities: bool = False
    link_entities: bool = False
    run_async: bool = True
    
    # === Progress ===
    progress: JobProgress = field(default_factory=JobProgress)
    
    # === Checkpoint ===
    checkpoint: Optional[JobCheckpoint] = None
    checkpoint_count: int = 0
    
    # === Timing ===
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # === Errors ===
    errors: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    
    # === Results ===
    result_summary: Dict[str, Any] = field(default_factory=dict)
    dlq_count: int = 0                    # Documents sent to DLQ
    
    # === Metadata ===
    created_by: str = "system"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def start(self):
        """Mark job as started."""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.progress.start_time = self.started_at
        
    def pause(self):
        """Pause the job."""
        self.status = JobStatus.PAUSED
        self.paused_at = datetime.utcnow()
        
    def resume(self):
        """Resume from paused state."""
        self.status = JobStatus.RUNNING
        self.paused_at = None
        
    def complete(self, summary: Dict[str, Any] = None):
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if summary:
            self.result_summary = summary
            
    def fail(self, error: str):
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.last_error = error
        self.last_error_at = datetime.utcnow()
        self.errors.append(f"[{datetime.utcnow().isoformat()}] {error}")
        
    def cancel(self, reason: str = ""):
        """Cancel the job."""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        self.metadata["cancel_reason"] = reason
        
    def add_error(self, error: str):
        """Add error to error log (without failing job)."""
        self.errors.append(f"[{datetime.utcnow().isoformat()}] {error}")
        self.last_error = error
        self.last_error_at = datetime.utcnow()
        # Keep only last 100 errors
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
            
    def save_checkpoint(self, offset: int, doc_id: str = None, cursor: Dict = None):
        """Save a checkpoint."""
        self.checkpoint = JobCheckpoint(
            last_offset=offset,
            last_id=doc_id,
            last_source_cursor=cursor or {},
            timestamp=datetime.utcnow(),
            checkpoint_file=f"/data/CYMONIDES/jobs/{self.job_id}.checkpoint",
            progress_snapshot=self.progress.to_dict(),
        )
        self.checkpoint_count += 1
        
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration."""
        if self.started_at:
            end_time = self.completed_at or datetime.utcnow()
            return (end_time - self.started_at).total_seconds()
        return None
    
    @property
    def is_running(self) -> bool:
        return self.status == JobStatus.RUNNING
    
    @property
    def is_finished(self) -> bool:
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ES storage."""
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "source_config": self.source_config,
            "target_index": self.target_index,
            "target_tier": self.target_tier,
            "pipeline": self.pipeline,
            "pipeline_version": self.pipeline_version,
            "pipeline_config": self.pipeline_config,
            "batch_size": self.batch_size,
            "checkpoint_every": self.checkpoint_every,
            "dedup_enabled": self.dedup_enabled,
            "dedup_field": self.dedup_field,
            "extract_entities": self.extract_entities,
            "link_entities": self.link_entities,
            "run_async": self.run_async,
            "progress": self.progress.to_dict(),
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "checkpoint_count": self.checkpoint_count,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors[-10:],  # Only last 10 in summary
            "error_count": len(self.errors),
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "result_summary": self.result_summary,
            "dlq_count": self.dlq_count,
            "created_by": self.created_by,
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexingJob":
        """Create job from dictionary."""
        job = cls(
            job_id=data.get("job_id", f"job-{uuid.uuid4().hex[:8]}"),
            name=data.get("name"),
            status=JobStatus(data.get("status", "pending")),
            source_id=data.get("source_id"),
            source_type=data.get("source_type", "file"),
            source_path=data.get("source_path", ""),
            source_config=data.get("source_config", {}),
            target_index=data.get("target_index", ""),
            target_tier=data.get("target_tier", "c2"),
            pipeline=data.get("pipeline", "content"),
            pipeline_version=data.get("pipeline_version"),
            pipeline_config=data.get("pipeline_config", {}),
            batch_size=data.get("batch_size", 100),
            checkpoint_every=data.get("checkpoint_every", 1000),
            dedup_enabled=data.get("dedup_enabled", True),
            dedup_field=data.get("dedup_field", "content_hash"),
            extract_entities=data.get("extract_entities", False),
            link_entities=data.get("link_entities", False),
            run_async=data.get("run_async", True),
            checkpoint_count=data.get("checkpoint_count", 0),
            errors=data.get("errors", []),
            last_error=data.get("last_error"),
            result_summary=data.get("result_summary", {}),
            dlq_count=data.get("dlq_count", 0),
            created_by=data.get("created_by", "system"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        
        # Parse progress
        if data.get("progress"):
            prog = data["progress"]
            job.progress = JobProgress(
                total=prog.get("total", 0),
                processed=prog.get("processed", 0),
                indexed=prog.get("indexed", 0),
                failed=prog.get("failed", 0),
                deduped=prog.get("deduped", 0),
                skipped=prog.get("skipped", 0),
            )
            if prog.get("start_time"):
                job.progress.start_time = datetime.fromisoformat(prog["start_time"])
            if prog.get("last_update"):
                job.progress.last_update = datetime.fromisoformat(prog["last_update"])
                
        # Parse checkpoint
        if data.get("checkpoint"):
            job.checkpoint = JobCheckpoint.from_dict(data["checkpoint"])
            
        # Parse dates
        if data.get("created_at"):
            job.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            job.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("paused_at"):
            job.paused_at = datetime.fromisoformat(data["paused_at"])
        if data.get("completed_at"):
            job.completed_at = datetime.fromisoformat(data["completed_at"])
        if data.get("last_error_at"):
            job.last_error_at = datetime.fromisoformat(data["last_error_at"])
            
        return job
