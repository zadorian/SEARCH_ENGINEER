"""
Parquet Reader - Reads Apache Parquet columnar files
Efficient for large analytical datasets (Common Crawl, etc.)
"""

import os
from typing import Optional, Dict, Any, List, Iterator
from .base import BaseReader, ReaderConfig, ReadResult

try:
    import pyarrow.parquet as pq
    import pyarrow as pa
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False


class ParquetReader(BaseReader):
    """
    Reader for Apache Parquet files.
    Supports:
    - Single parquet files
    - Partitioned datasets (directories)
    - Column projection
    - Row group batching
    - Predicate pushdown filters
    """
    
    def __init__(
        self,
        source_path: str,
        config: Optional[ReaderConfig] = None,
        columns: Optional[List[str]] = None,
        filters: Optional[List[tuple]] = None,
    ):
        if not HAS_PYARROW:
            raise ImportError("pyarrow is required for ParquetReader. pip install pyarrow")
        
        super().__init__(source_path, config)
        self.columns = columns  # Column projection
        self.filters = filters  # Predicate pushdown
        self._table: Optional[pa.Table] = None
        self._iterator: Optional[Iterator] = None
        self._total_rows: Optional[int] = None
        self._current_batch: List[Dict] = []
        self._batch_index = 0
    
    @property
    def reader_type(self) -> str:
        return "parquet"
    
    def open(self) -> None:
        if self._is_open:
            return
        
        # Check if path is directory (partitioned dataset) or file
        if os.path.isdir(self.source_path):
            self._table = pq.read_table(
                self.source_path,
                columns=self.columns,
                filters=self.filters,
            )
        else:
            self._table = pq.read_table(
                self.source_path,
                columns=self.columns,
                filters=self.filters,
            )
        
        self._total_rows = len(self._table)
        self._iterator = self._table.to_batches(max_chunksize=self.config.batch_size)
        self._is_open = True
        
        # Seek to offset if needed
        if self.current_offset > 0:
            self.seek(self.current_offset)
    
    def close(self) -> None:
        self._table = None
        self._iterator = None
        self._current_batch = []
        self._batch_index = 0
        self._is_open = False
    
    def _load_next_batch(self) -> bool:
        """Load next batch of records"""
        if not self._iterator:
            return False
        
        try:
            batch = next(self._iterator)
            self._current_batch = batch.to_pylist()
            self._batch_index = 0
            return True
        except StopIteration:
            self._current_batch = []
            return False
    
    def read_record(self) -> Optional[ReadResult]:
        if not self._is_open:
            return None
        
        # Check if we need to load next batch
        if self._batch_index >= len(self._current_batch):
            if not self._load_next_batch():
                return None
        
        try:
            data = self._current_batch[self._batch_index]
            data = self.apply_field_mapping(data)
            
            self._batch_index += 1
            self.current_offset += 1
            self.records_read += 1
            
            return ReadResult(
                success=True,
                data=data,
                offset=self.current_offset,
                source_id=self.source_id,
            )
        
        except Exception as e:
            self.errors_count += 1
            self._batch_index += 1
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
        """Seek to row offset"""
        if not self._is_open:
            self.open()
        
        # Slice table from offset
        if offset > 0 and self._table:
            self._table = self._table.slice(offset)
            self._iterator = self._table.to_batches(max_chunksize=self.config.batch_size)
            self._current_batch = []
            self._batch_index = 0
        
        self.current_offset = offset
    
    def get_total_records(self) -> Optional[int]:
        """Get total row count"""
        if self._total_rows is not None:
            return self._total_rows
        
        # Read metadata without loading full file
        try:
            if os.path.isfile(self.source_path):
                parquet_file = pq.ParquetFile(self.source_path)
                return parquet_file.metadata.num_rows
        except:
            pass
        
        return None
    
    def get_schema(self) -> Dict[str, str]:
        """Get parquet schema as dict of field: type"""
        if not self._is_open:
            self.open()
        
        if self._table:
            return {
                field.name: str(field.type) 
                for field in self._table.schema
            }
        return {}
    
    def get_row_groups_info(self) -> List[Dict[str, Any]]:
        """Get info about row groups (for parallel processing)"""
        if os.path.isfile(self.source_path):
            parquet_file = pq.ParquetFile(self.source_path)
            return [
                {
                    "index": i,
                    "num_rows": parquet_file.metadata.row_group(i).num_rows,
                    "total_byte_size": parquet_file.metadata.row_group(i).total_byte_size,
                }
                for i in range(parquet_file.metadata.num_row_groups)
            ]
        return []
