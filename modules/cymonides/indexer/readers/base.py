"""
Base Reader - Abstract base class for all data readers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Iterator, AsyncIterator
from datetime import datetime
import hashlib


@dataclass
class ReaderConfig:
    """Configuration for a reader"""
    batch_size: int = 1000
    skip_header: bool = False
    encoding: str = "utf-8"
    delimiter: str = ","
    quote_char: str = '"'
    null_values: List[str] = field(default_factory=lambda: ["", "NULL", "null", "None", "none"])
    max_field_size: int = 10 * 1024 * 1024  # 10MB
    error_handling: str = "skip"  # skip, raise, dlq
    
    # Checkpoint config
    enable_checkpointing: bool = True
    checkpoint_interval: int = 10000  # Records between checkpoints
    
    # Field mapping
    field_mapping: Dict[str, str] = field(default_factory=dict)
    include_fields: Optional[List[str]] = None
    exclude_fields: Optional[List[str]] = None


@dataclass
class ReadResult:
    """Result from reading a record"""
    success: bool
    data: Optional[Dict[str, Any]]
    offset: int  # Position in source (line number, byte offset, etc.)
    source_id: str
    raw_record: Optional[str] = None  # Original record for debugging
    error: Optional[str] = None
    
    def to_envelope_data(self) -> Dict[str, Any]:
        """Convert to data suitable for DocumentEnvelope"""
        return {
            "data": self.data,
            "source_offset": self.offset,
            "source_id": self.source_id,
            "raw": self.raw_record[:1000] if self.raw_record else None,
        }


class BaseReader(ABC):
    """
    Abstract base class for data readers.
    Readers are responsible for:
    - Opening and iterating over data sources
    - Converting raw records to dictionaries
    - Tracking position for checkpointing
    - Handling errors gracefully
    """
    
    def __init__(self, source_path: str, config: Optional[ReaderConfig] = None):
        self.source_path = source_path
        self.config = config or ReaderConfig()
        self.source_id = self._generate_source_id()
        self.current_offset = 0
        self.records_read = 0
        self.errors_count = 0
        self._is_open = False
    
    def _generate_source_id(self) -> str:
        """Generate unique source ID from path"""
        return hashlib.md5(self.source_path.encode()).hexdigest()[:16]
    
    @property
    @abstractmethod
    def reader_type(self) -> str:
        """Return the type of reader (file, jsonl, parquet, etc.)"""
        pass
    
    @abstractmethod
    def open(self) -> None:
        """Open the data source"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the data source"""
        pass
    
    @abstractmethod
    def read_record(self) -> Optional[ReadResult]:
        """Read a single record, return None at end"""
        pass
    
    @abstractmethod
    def seek(self, offset: int) -> None:
        """Seek to a specific offset (for resume)"""
        pass
    
    @abstractmethod
    def get_total_records(self) -> Optional[int]:
        """Get total record count if known, None otherwise"""
        pass
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def __iter__(self) -> Iterator[ReadResult]:
        """Iterate over all records"""
        if not self._is_open:
            self.open()
        
        while True:
            result = self.read_record()
            if result is None:
                break
            yield result
    
    def read_batch(self, size: Optional[int] = None) -> List[ReadResult]:
        """Read a batch of records"""
        batch_size = size or self.config.batch_size
        batch = []
        
        for _ in range(batch_size):
            result = self.read_record()
            if result is None:
                break
            batch.append(result)
        
        return batch
    
    def apply_field_mapping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply field mapping and filtering"""
        if not data:
            return data
        
        # Apply field mapping
        if self.config.field_mapping:
            mapped = {}
            for key, value in data.items():
                new_key = self.config.field_mapping.get(key, key)
                mapped[new_key] = value
            data = mapped
        
        # Apply include filter
        if self.config.include_fields:
            data = {k: v for k, v in data.items() if k in self.config.include_fields}
        
        # Apply exclude filter
        if self.config.exclude_fields:
            data = {k: v for k, v in data.items() if k not in self.config.exclude_fields}
        
        # Convert null values
        for key, value in data.items():
            if value in self.config.null_values:
                data[key] = None
        
        return data
    
    def get_checkpoint(self) -> Dict[str, Any]:
        """Get current checkpoint data for resume"""
        return {
            "source_path": self.source_path,
            "source_id": self.source_id,
            "reader_type": self.reader_type,
            "current_offset": self.current_offset,
            "records_read": self.records_read,
            "errors_count": self.errors_count,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def restore_from_checkpoint(self, checkpoint: Dict[str, Any]) -> None:
        """Restore reader state from checkpoint"""
        if checkpoint.get("source_id") != self.source_id:
            raise ValueError("Checkpoint source_id mismatch")
        
        self.current_offset = checkpoint.get("current_offset", 0)
        self.records_read = checkpoint.get("records_read", 0)
        self.errors_count = checkpoint.get("errors_count", 0)
        
        # Seek to checkpoint position
        if self._is_open:
            self.seek(self.current_offset)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get reader statistics"""
        return {
            "source_path": self.source_path,
            "source_id": self.source_id,
            "reader_type": self.reader_type,
            "records_read": self.records_read,
            "errors_count": self.errors_count,
            "error_rate": self.errors_count / max(self.records_read, 1),
            "current_offset": self.current_offset,
            "is_open": self._is_open,
        }
