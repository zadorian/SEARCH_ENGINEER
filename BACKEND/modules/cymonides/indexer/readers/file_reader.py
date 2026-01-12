"""
File Reader - Generic text/CSV file reader
"""

import csv
import os
from typing import Optional, Dict, Any, List, TextIO
from .base import BaseReader, ReaderConfig, ReadResult


class FileReader(BaseReader):
    """
    Generic file reader for text and CSV files.
    Supports:
    - Plain text files (line by line)
    - CSV files with headers
    - Custom delimiters
    """
    
    def __init__(
        self, 
        source_path: str, 
        config: Optional[ReaderConfig] = None,
        is_csv: bool = True,
        headers: Optional[List[str]] = None,
    ):
        super().__init__(source_path, config)
        self.is_csv = is_csv
        self.headers = headers
        self._file: Optional[TextIO] = None
        self._csv_reader = None
        self._detected_headers: List[str] = []
    
    @property
    def reader_type(self) -> str:
        return "csv" if self.is_csv else "text"
    
    def open(self) -> None:
        if self._is_open:
            return
        
        self._file = open(
            self.source_path, 
            'r', 
            encoding=self.config.encoding,
            errors='replace'
        )
        
        if self.is_csv:
            self._csv_reader = csv.reader(
                self._file,
                delimiter=self.config.delimiter,
                quotechar=self.config.quote_char,
            )
            
            # Read header row
            if self.headers:
                self._detected_headers = self.headers
                if not self.config.skip_header:
                    next(self._csv_reader, None)  # Skip if external headers provided
            else:
                self._detected_headers = next(self._csv_reader, [])
            
            self.current_offset = 1  # Account for header
        
        self._is_open = True
        
        if self.current_offset > 1:
            self.seek(self.current_offset)
    
    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._csv_reader = None
        self._is_open = False
    
    def read_record(self) -> Optional[ReadResult]:
        if not self._is_open:
            return None
        
        try:
            if self.is_csv and self._csv_reader:
                row = next(self._csv_reader, None)
                if row is None:
                    return None
                
                self.current_offset += 1
                
                # Convert to dict
                if len(row) != len(self._detected_headers):
                    # Handle mismatched columns
                    if len(row) < len(self._detected_headers):
                        row = row + [''] * (len(self._detected_headers) - len(row))
                    else:
                        row = row[:len(self._detected_headers)]
                
                data = dict(zip(self._detected_headers, row))
                data = self.apply_field_mapping(data)
                self.records_read += 1
                
                return ReadResult(
                    success=True,
                    data=data,
                    offset=self.current_offset,
                    source_id=self.source_id,
                    raw_record=self.config.delimiter.join(row)[:1000],
                )
            
            else:
                # Plain text - one line per record
                line = self._file.readline()
                if not line:
                    return None
                
                self.current_offset += 1
                self.records_read += 1
                
                return ReadResult(
                    success=True,
                    data={"line": line.strip(), "line_number": self.current_offset},
                    offset=self.current_offset,
                    source_id=self.source_id,
                    raw_record=line[:1000],
                )
        
        except Exception as e:
            self.errors_count += 1
            self.current_offset += 1
            
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
        """Seek to line number"""
        if not self._is_open:
            self.open()
            return
        
        # Reset to start
        self._file.seek(0)
        self.current_offset = 0
        
        if self.is_csv:
            self._csv_reader = csv.reader(
                self._file,
                delimiter=self.config.delimiter,
                quotechar=self.config.quote_char,
            )
            # Skip header
            next(self._csv_reader, None)
            self.current_offset = 1
        
        # Skip to offset
        while self.current_offset < offset:
            if self.is_csv:
                if next(self._csv_reader, None) is None:
                    break
            else:
                if not self._file.readline():
                    break
            self.current_offset += 1
    
    def get_total_records(self) -> Optional[int]:
        """Count total lines"""
        count = 0
        with open(self.source_path, 'r', encoding=self.config.encoding, errors='replace') as f:
            for _ in f:
                count += 1
        
        # Subtract header row for CSV
        if self.is_csv:
            count -= 1
        
        return max(count, 0)
    
    def get_detected_headers(self) -> List[str]:
        """Get detected/provided column headers"""
        return self._detected_headers
