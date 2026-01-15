"""
DocumentEnvelope - Immutable wrapper for documents flowing through the pipeline.

Every document travels through the pipeline wrapped in an envelope that 
accumulates metadata for full lineage tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import hashlib
import uuid


class EnvelopeStatus(Enum):
    """Status of document in pipeline."""
    PENDING = "pending"           # Not yet processed
    PROCESSING = "processing"     # Currently in pipeline
    INDEXED = "indexed"           # Successfully indexed
    FAILED = "failed"             # Processing failed
    DLQ = "dlq"                   # In dead letter queue
    SKIPPED = "skipped"           # Skipped (dedup, filter, etc.)


@dataclass
class TransformRecord:
    """Record of a transformation applied to document."""
    stage_name: str
    timestamp: datetime
    input_hash: str = ""
    output_hash: str = ""
    success: bool = True
    error: Optional[str] = None
    fields_modified: List[str] = field(default_factory=list)
    fields_added: List[str] = field(default_factory=list)
    fields_removed: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class EntityLink:
    """Link from document field to C-1 canonical entity."""
    field: str                    # Source field in document
    value: str                    # Field value that was linked
    entity_id: str                # C-1 entity ID
    entity_type: str              # person, company, domain, etc.
    entity_label: str             # Entity display label
    confidence: float             # 0-1 match confidence
    link_type: str                # extracted_from, mentioned_in, etc.
    created: bool = False         # True if entity was created (not found)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_label": self.entity_label,
            "confidence": self.confidence,
            "link_type": self.link_type,
            "created": self.created,
        }


@dataclass
class DocumentEnvelope:
    """
    Immutable wrapper carrying document + processing metadata.
    
    This envelope travels through the entire pipeline, accumulating
    metadata at each stage. At the end, both the document AND envelope
    metadata are preserved for full lineage.
    """
    
    # === Identity ===
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_id: Optional[str] = None  # Content-derived ID (for dedup)
    
    # === Provenance ===
    source_id: str = ""               # Which registered source
    source_offset: int = 0            # Position in source (for resume)
    source_record: Dict[str, Any] = field(default_factory=dict)
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    
    # === Content ===
    raw_data: Optional[bytes] = None  # Original unchanged (for replay)
    current_data: Dict[str, Any] = field(default_factory=dict)
    
    # === Processing Trail ===
    transforms_applied: List[TransformRecord] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    enrichments: Dict[str, Any] = field(default_factory=dict)
    
    # === Entity Links ===
    entity_links: List[EntityLink] = field(default_factory=list)
    
    # === Routing ===
    target_index: Optional[str] = None
    routing_rule: Optional[str] = None
    priority: int = 0
    
    # === Quality ===
    quality_score: float = 0.0
    flags: Set[str] = field(default_factory=set)
    
    # === Outcome ===
    status: EnvelopeStatus = EnvelopeStatus.PENDING
    indexed_at: Optional[datetime] = None
    error: Optional[str] = None
    error_stage: Optional[str] = None
    
    # === Job Context ===
    job_id: Optional[str] = None
    pipeline_name: Optional[str] = None
    pipeline_version: Optional[str] = None
    
    def compute_document_id(self, fields: List[str] = None) -> str:
        """
        Compute content-derived document ID for deduplication.
        
        Args:
            fields: Fields to include in hash. If None, uses all data.
        """
        if fields:
            data_to_hash = {k: self.current_data.get(k) for k in fields}
        else:
            data_to_hash = self.current_data
            
        content = str(sorted(data_to_hash.items())).encode()
        self.document_id = hashlib.sha256(content).hexdigest()[:16]
        return self.document_id
    
    def add_flag(self, flag: str):
        """Add a flag to the envelope."""
        self.flags.add(flag)
        
    def has_flag(self, flag: str) -> bool:
        """Check if envelope has a flag."""
        return flag in self.flags
        
    def record_transform(
        self,
        stage_name: str,
        input_data: Dict,
        output_data: Dict,
        duration_ms: float
    ):
        """Record a transformation in the audit trail."""
        input_hash = hashlib.md5(str(sorted(input_data.items())).encode()).hexdigest()[:8]
        output_hash = hashlib.md5(str(sorted(output_data.items())).encode()).hexdigest()[:8]
        
        input_keys = set(input_data.keys())
        output_keys = set(output_data.keys())
        
        record = TransformRecord(
            stage_name=stage_name,
            timestamp=datetime.utcnow(),
            input_hash=input_hash,
            output_hash=output_hash,
            fields_modified=[k for k in input_keys & output_keys if input_data.get(k) != output_data.get(k)],
            fields_added=list(output_keys - input_keys),
            fields_removed=list(input_keys - output_keys),
            duration_ms=duration_ms,
        )
        self.transforms_applied.append(record)
        self.current_data = output_data
        
    def mark_indexed(self, index_name: str):
        """Mark envelope as successfully indexed."""
        self.status = EnvelopeStatus.INDEXED
        self.indexed_at = datetime.utcnow()
        self.target_index = index_name
        
    def mark_failed(self, error: str, stage: str):
        """Mark envelope as failed."""
        self.status = EnvelopeStatus.FAILED
        self.error = error
        self.error_stage = stage
        
    def mark_skipped(self, reason: str):
        """Mark envelope as skipped (dedup, filter, etc.)."""
        self.status = EnvelopeStatus.SKIPPED
        self.add_flag(f"skipped:{reason}")
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "envelope_id": self.envelope_id,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "source_offset": self.source_offset,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "current_data": self.current_data,
            "transforms_count": len(self.transforms_applied),
            "entity_links": [link.to_dict() for link in self.entity_links],
            "target_index": self.target_index,
            "routing_rule": self.routing_rule,
            "quality_score": self.quality_score,
            "flags": list(self.flags),
            "status": self.status.value,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "error": self.error,
            "error_stage": self.error_stage,
            "job_id": self.job_id,
            "pipeline_name": self.pipeline_name,
        }
    

    @classmethod
    def create(
        cls,
        source_id: str,
        source_offset: int,
        initial_data: Dict[str, Any],
        job_id: str = None,
    ) -> "DocumentEnvelope":
        """Factory method to create a new envelope from source data."""
        return cls(
            source_id=source_id,
            source_offset=source_offset,
            current_data=initial_data.copy(),
            source_record=initial_data.copy(),
            job_id=job_id,
        )
    
    def _hash_data(self, data: Dict[str, Any]) -> str:
        """Create hash of data for transform tracking."""
        import json
        try:
            serialized = json.dumps(data, sort_keys=True, default=str)
            return hashlib.md5(serialized.encode()).hexdigest()[:16]
        except:
            return ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentEnvelope":
        """Create envelope from dictionary."""
        envelope = cls(
            envelope_id=data.get("envelope_id", str(uuid.uuid4())),
            document_id=data.get("document_id"),
            source_id=data.get("source_id", ""),
            source_offset=data.get("source_offset", 0),
            current_data=data.get("current_data", {}),
            target_index=data.get("target_index"),
            routing_rule=data.get("routing_rule"),
            quality_score=data.get("quality_score", 0.0),
            flags=set(data.get("flags", [])),
            error=data.get("error"),
            error_stage=data.get("error_stage"),
            job_id=data.get("job_id"),
            pipeline_name=data.get("pipeline_name"),
        )
        
        if data.get("extracted_at"):
            envelope.extracted_at = datetime.fromisoformat(data["extracted_at"])
        if data.get("indexed_at"):
            envelope.indexed_at = datetime.fromisoformat(data["indexed_at"])
        if data.get("status"):
            envelope.status = EnvelopeStatus(data["status"])
            
        # Reconstruct entity links
        for link_data in data.get("entity_links", []):
            envelope.entity_links.append(EntityLink(**link_data))
            
        return envelope
