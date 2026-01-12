"""
Breach Reader - Specialized reader for breach dump formats
Handles various breach formats: combo lists, database dumps, etc.
"""

import re
import hashlib
from typing import Optional, Dict, Any, List, TextIO
from .base import BaseReader, ReaderConfig, ReadResult


class BreachReader(BaseReader):
    """
    Specialized reader for breach data dumps.
    Auto-detects and parses common breach formats:
    - email:password combo lists
    - email:hash combos
    - Delimited exports (email|username|password|etc)
    - Database dumps
    """
    
    # Common breach patterns
    PATTERNS = {
        "email_pass": re.compile(r'^([^:;|]+@[^:;|]+)[:|;](.+)$'),
        "email_hash": re.compile(r'^([^:;|]+@[^:;|]+)[:|;]([a-fA-F0-9]{32,})$'),
        "user_pass": re.compile(r'^([^:;|@]+)[:|;](.+)$'),
        "delimited": re.compile(r'^[^|:;]+[|:;][^|:;]+'),
    }
    
    def __init__(
        self,
        source_path: str,
        config: Optional[ReaderConfig] = None,
        breach_name: Optional[str] = None,
        breach_date: Optional[str] = None,
        force_format: Optional[str] = None,  # email_pass, delimited, etc.
        field_order: Optional[List[str]] = None,  # For delimited: [email, password, username, ...]
    ):
        super().__init__(source_path, config)
        self.breach_name = breach_name or self._extract_breach_name()
        self.breach_date = breach_date
        self.force_format = force_format
        self.field_order = field_order
        self._file: Optional[TextIO] = None
        self._detected_format: Optional[str] = None
        self._detected_delimiter: str = ":"
    
    @property
    def reader_type(self) -> str:
        return "breach"
    
    def _extract_breach_name(self) -> str:
        """Extract breach name from file path"""
        import os
        basename = os.path.basename(self.source_path)
        name = os.path.splitext(basename)[0]
        # Remove common suffixes
        for suffix in ['_combo', '_dump', '_leak', '_breach', '_data']:
            name = name.replace(suffix, '')
        return name
    
    def open(self) -> None:
        if self._is_open:
            return
        
        self._file = open(
            self.source_path, 
            'r', 
            encoding=self.config.encoding,
            errors='replace'
        )
        self._is_open = True
        
        # Detect format from first few lines
        if not self.force_format:
            self._detect_format()
        else:
            self._detected_format = self.force_format
        
        if self.current_offset > 0:
            self.seek(self.current_offset)
    
    def _detect_format(self) -> None:
        """Detect breach format from sample lines"""
        sample_lines = []
        for _ in range(100):
            line = self._file.readline()
            if not line:
                break
            line = line.strip()
            if line:
                sample_lines.append(line)
        
        # Reset file
        self._file.seek(0)
        
        if not sample_lines:
            self._detected_format = "unknown"
            return
        
        # Count delimiter occurrences
        delimiters = {':', ';', '|', '\t', ','}
        delimiter_counts = {d: 0 for d in delimiters}
        
        for line in sample_lines:
            for d in delimiters:
                if d in line:
                    delimiter_counts[d] += line.count(d)
        
        # Use most common delimiter
        self._detected_delimiter = max(delimiter_counts, key=delimiter_counts.get)
        
        # Check for email:password pattern
        email_pass_count = 0
        for line in sample_lines:
            if self.PATTERNS["email_pass"].match(line):
                email_pass_count += 1
        
        if email_pass_count > len(sample_lines) * 0.7:
            self._detected_format = "email_pass"
        else:
            # Check column count for delimited
            col_counts = [len(line.split(self._detected_delimiter)) for line in sample_lines]
            avg_cols = sum(col_counts) / len(col_counts) if col_counts else 0
            
            if avg_cols > 2:
                self._detected_format = "delimited"
            else:
                self._detected_format = "email_pass"
    
    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._is_open = False
    
    def _parse_email_pass(self, line: str) -> Dict[str, Any]:
        """Parse email:password format"""
        match = self.PATTERNS["email_pass"].match(line)
        if match:
            email = match.group(1).strip().lower()
            password = match.group(2).strip()
            
            # Check if password is a hash
            password_type = "plaintext"
            if re.match(r'^[a-fA-F0-9]{32}$', password):
                password_type = "md5"
            elif re.match(r'^[a-fA-F0-9]{40}$', password):
                password_type = "sha1"
            elif re.match(r'^[a-fA-F0-9]{64}$', password):
                password_type = "sha256"
            elif password.startswith(''):
                password_type = "bcrypt"
            
            return {
                "email": email,
                "email_domain": email.split('@')[1] if '@' in email else None,
                "password_hash" if password_type != "plaintext" else "password_plain": password,
                "password_type": password_type,
            }
        
        return {"raw_line": line}
    
    def _parse_delimited(self, line: str) -> Dict[str, Any]:
        """Parse delimited format"""
        parts = line.split(self._detected_delimiter)
        
        if self.field_order:
            # Use provided field order
            data = {}
            for i, field in enumerate(self.field_order):
                if i < len(parts):
                    value = parts[i].strip()
                    if value and value not in self.config.null_values:
                        data[field] = value
            return data
        
        # Auto-detect fields
        data = {}
        for i, part in enumerate(parts):
            part = part.strip()
            if not part or part in self.config.null_values:
                continue
            
            # Try to identify field type
            if '@' in part and '.' in part:
                data["email"] = part.lower()
                data["email_domain"] = part.split('@')[1].lower()
            elif re.match(r'^[a-fA-F0-9]{32,}$', part):
                data["password_hash"] = part
            elif i == len(parts) - 1 and not data.get("password_plain"):
                # Last field often password
                data["password_plain"] = part
            else:
                data[f"field_{i}"] = part
        
        return data
    
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
            
            # Parse based on detected format
            if self._detected_format == "email_pass":
                data = self._parse_email_pass(line)
            elif self._detected_format == "delimited":
                data = self._parse_delimited(line)
            else:
                data = {"raw_line": line}
            
            # Add breach metadata
            data["breach_name"] = self.breach_name
            if self.breach_date:
                data["breach_date"] = self.breach_date
            data["source_file"] = self.source_path
            data["line_number"] = self.current_offset
            
            # Generate record hash
            hash_input = f"{data.get('email', '')}{data.get('password_hash', data.get('password_plain', ''))}{self.breach_name}"
            data["record_hash"] = hashlib.md5(hash_input.encode()).hexdigest()
            
            data = self.apply_field_mapping(data)
            self.records_read += 1
            
            return ReadResult(
                success=True,
                data=data,
                offset=self.current_offset,
                source_id=self.source_id,
                raw_record=line[:500],
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
        if not self._is_open:
            self.open()
        
        self._file.seek(0)
        self.current_offset = 0
        
        for _ in range(offset):
            if not self._file.readline():
                break
            self.current_offset += 1
    
    def get_total_records(self) -> Optional[int]:
        count = 0
        with open(self.source_path, 'r', encoding=self.config.encoding, errors='replace') as f:
            for _ in f:
                count += 1
        return count
    
    def get_detected_format(self) -> Dict[str, Any]:
        """Get detected format info"""
        return {
            "format": self._detected_format,
            "delimiter": self._detected_delimiter,
            "breach_name": self.breach_name,
            "breach_date": self.breach_date,
        }
