"""
JSONL Reader - Reads newline-delimited JSON files
Primary reader for breach data, API exports, and structured data
"""

import json
import gzip
import os
from typing import Optional, Dict, Any, TextIO, BinaryIO
from .base import BaseReader, ReaderConfig, ReadResult


class JSONLReader(BaseReader):
    """
    Reader for JSONL (newline-delimited JSON) files.
    Supports:
    - Plain .jsonl files
    - Gzipped .jsonl.gz files
    - Streaming large files
    - Checkpoint/resume
    """
    
    def __init__(self, source_path: str, config: Optional[ReaderConfig] = None):
        super().__init__(source_path, config)
        self._file: Optional[TextIO] = None
        self._gzip_file: Optional[BinaryIO] = None
        self._is_gzipped = source_path.endswith('.gz')
        self._file_size: Optional[int] = None
    
    @property
    def reader_type(self) -> str:
        return "jsonl"
    
    def open(self) -> None:
        if self._is_open:
            return
        
        # Get file size for progress tracking
        self._file_size = os.path.getsize(self.source_path)
        
        if self._is_gzipped:
            self._gzip_file = gzip.open(self.source_path, 'rt', encoding=self.config.encoding)
            self._file = self._gzip_file
        else:
            self._file = open(self.source_path, 'r', encoding=self.config.encoding)
        
        self._is_open = True
        
        # Skip to checkpoint if set
        if self.current_offset > 0:
            self.seek(self.current_offset)
    
    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        if self._gzip_file:
            self._gzip_file = None
        self._is_open = False
    
    def read_record(self) -> Optional[ReadResult]:
        if not self._is_open or not self._file:
            return None
        
        try:
            line = self._file.readline()
            if not line:
                return None
            
            self.current_offset += 1
            line = line.strip()
            
            # Skip empty lines
            if not line:
                return self.read_record()
            
            try:
                data = json.loads(line)
                data = self.apply_field_mapping(data)
                self.records_read += 1
                
                return ReadResult(
                    success=True,
                    data=data,
                    offset=self.current_offset,
                    source_id=self.source_id,
                    raw_record=line[:1000] if len(line) > 1000 else line,
                )
            except json.JSONDecodeError as e:
                self.errors_count += 1
                
                if self.config.error_handling == "raise":
                    raise
                
                return ReadResult(
                    success=False,
                    data=None,
                    offset=self.current_offset,
                    source_id=self.source_id,
                    raw_record=line[:1000],
                    error=f"JSON decode error: {str(e)}",
                )
        
        except Exception as e:
            self.errors_count += 1
            if self.config.error_handling == "raise":
                raise
            
            return ReadResult(
                success=False,
                data=None,
                offset=self.current_offset,
                source_id=self.source_id,
                error=str(e),
            )
    
    def seek(self, offset: int) -> None:
        """Seek to line number (offset)"""
        if not self._is_open:
            self.open()
        
        # Reset to beginning
        self._file.seek(0)
        self.current_offset = 0
        
        # Skip lines to reach offset
        for _ in range(offset):
            line = self._file.readline()
            if not line:
                break
            self.current_offset += 1
    
    def get_total_records(self) -> Optional[int]:
        """Count total lines (records) in file"""
        if self._is_gzipped:
            # For gzipped files, we need to decompress to count
            # This is expensive, so return None for large files
            if self._file_size and self._file_size > 100 * 1024 * 1024:  # 100MB
                return None
        
        count = 0
        current_pos = self._file.tell() if self._file else 0
        
        try:
            if self._is_gzipped:
                with gzip.open(self.source_path, 'rt') as f:
                    for _ in f:
                        count += 1
            else:
                with open(self.source_path, 'r') as f:
                    for _ in f:
                        count += 1
            
            # Restore position
            if self._file:
                self._file.seek(current_pos)
            
            return count
        except:
            return None
    
    def estimate_progress(self) -> float:
        """Estimate progress through file (0.0 to 1.0)"""
        if not self._file_size:
            return 0.0
        
        try:
            if hasattr(self._file, 'tell'):
                current_pos = self._file.tell()
                return min(current_pos / self._file_size, 1.0)
        except:
            pass
        
        return 0.0
