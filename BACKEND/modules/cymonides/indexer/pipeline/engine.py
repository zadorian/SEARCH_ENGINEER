"""
Pipeline Engine - Main orchestrator for data indexing
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Type
from datetime import datetime
import logging
import json

from ..core.envelope import DocumentEnvelope, EnvelopeStatus, TransformRecord
from ..core.job import IndexingJob, JobStatus, JobProgress, JobCheckpoint
from ..readers.base import BaseReader, ReaderConfig
from ..readers.jsonl_reader import JSONLReader
from ..readers.parquet_reader import ParquetReader
from ..readers.file_reader import FileReader
from ..readers.breach_reader import BreachReader
from .stage import (
    PipelineStage, 
    TransformStage, 
    FilterStage, 
    EnrichStage, 
    DedupeStage,
    StageResult,
    CommonTransforms,
)
from .config import PipelineConfig, StageConfig, OutputMode

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for a pipeline run"""
    total_read: int = 0
    total_processed: int = 0
    total_indexed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    total_dlq: int = 0
    total_deduped: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def docs_per_second(self) -> float:
        if self.duration_seconds > 0:
            return self.total_processed / self.duration_seconds
        return 0.0
    
    @property
    def error_rate(self) -> float:
        if self.total_read > 0:
            return self.total_errors / self.total_read
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_read": self.total_read,
            "total_processed": self.total_processed,
            "total_indexed": self.total_indexed,
            "total_skipped": self.total_skipped,
            "total_errors": self.total_errors,
            "total_dlq": self.total_dlq,
            "total_deduped": self.total_deduped,
            "duration_seconds": self.duration_seconds,
            "docs_per_second": self.docs_per_second,
            "error_rate": self.error_rate,
        }


class PipelineEngine:
    """
    Main pipeline execution engine.
    Coordinates:
    - Reading from sources
    - Processing through stages
    - Batching and indexing to ES
    - Checkpointing and resume
    - Error handling and DLQ
    """
    
    # Reader registry
    READERS: Dict[str, Type[BaseReader]] = {
        "jsonl": JSONLReader,
        "parquet": ParquetReader,
        "csv": FileReader,
        "text": FileReader,
        "breach": BreachReader,
    }
    
    def __init__(
        self,
        es_client,
        config: PipelineConfig,
        job: Optional[IndexingJob] = None,
    ):
        self.es = es_client
        self.config = config
        self.job = job
        self.stats = PipelineStats()
        self.stages: List[PipelineStage] = []
        self._reader: Optional[BaseReader] = None
        self._batch: List[Dict[str, Any]] = []
        self._dlq: List[Dict[str, Any]] = []
        self._is_running = False
        self._should_stop = False
        
        # Build stages from config
        self._build_stages()
    
    def _build_stages(self):
        """Build pipeline stages from config"""
        for stage_config in self.config.stages:
            if not stage_config.enabled:
                continue
            
            stage = self._create_stage(stage_config)
            if stage:
                self.stages.append(stage)
    
    def _create_stage(self, config: StageConfig) -> Optional[PipelineStage]:
        """Create a stage instance from config"""
        stage_type = config.type.lower()
        
        if stage_type == "transform":
            # Parse transform functions
            transforms = {}
            for field, func_name in config.config.get('transforms', {}).items():
                if hasattr(CommonTransforms, func_name):
                    transforms[field] = getattr(CommonTransforms, func_name)
            
            # Parse add_fields with callable detection
            add_fields = {}
            for field, value in config.config.get('add_fields', {}).items():
                if value == "timestamp_now":
                    add_fields[field] = CommonTransforms.timestamp_now
                else:
                    add_fields[field] = value
            
            return TransformStage(
                name=config.name,
                transforms=transforms,
                field_renames=config.config.get('field_renames', {}),
                field_defaults=config.config.get('field_defaults', {}),
                add_fields=add_fields,
                remove_fields=config.config.get('remove_fields', []),
            )
        
        elif stage_type == "filter":
            return FilterStage(
                name=config.name,
                required_fields=config.config.get('required_fields', []),
                min_field_count=config.config.get('min_field_count', 0),
            )
        
        elif stage_type == "enrich":
            enrichments = {}
            for field, func_name in config.config.get('enrichments', {}).items():
                # Could add custom enrichment functions here
                pass
            return EnrichStage(name=config.name, enrichments=enrichments)
        
        elif stage_type == "dedupe":
            return DedupeStage(
                name=config.name,
                key_fields=config.config.get('key_fields', []),
                hash_algorithm=config.config.get('hash_algorithm', 'md5'),
            )
        
        return None
    
    def _create_reader(self, source_path: str) -> BaseReader:
        """Create reader instance for source"""
        reader_type = self.config.reader_type.lower()
        reader_class = self.READERS.get(reader_type)
        
        if not reader_class:
            raise ValueError(f"Unknown reader type: {reader_type}")
        
        reader_config = ReaderConfig(**self.config.reader_config)
        
        if reader_type == "breach":
            return BreachReader(source_path, reader_config)
        elif reader_type == "csv":
            return FileReader(source_path, reader_config, is_csv=True)
        elif reader_type == "text":
            return FileReader(source_path, reader_config, is_csv=False)
        else:
            return reader_class(source_path, reader_config)
    
    def _process_document(self, data: Dict[str, Any], offset: int) -> Optional[DocumentEnvelope]:
        """Process a single document through all stages"""
        envelope = DocumentEnvelope.create(
            source_id=self._reader.source_id if self._reader else "unknown",
            source_offset=offset,
            initial_data=data,
        )
        
        current_data = data
        
        for stage in self.stages:
            result = stage.process(current_data)
            
            # Record transform
            envelope.transforms_applied.append(TransformRecord(
                stage_name=stage.name,
                timestamp=datetime.utcnow(),
                input_hash=envelope._hash_data(current_data),
                output_hash=envelope._hash_data(result.data) if result.data else "",
                success=result.success,
                error=result.error,
            ))
            
            if not result.success:
                envelope.status = EnvelopeStatus.FAILED
                envelope.error_message = result.error
                
                if result.action == "dlq":
                    envelope.status = EnvelopeStatus.DLQ
                    self.stats.total_dlq += 1
                    self._dlq.append(envelope.to_dict())
                else:
                    self.stats.total_errors += 1
                
                return None
            
            if result.action == "skip":
                envelope.status = EnvelopeStatus.SKIPPED
                self.stats.total_skipped += 1
                
                # Check if dedupe
                if isinstance(stage, DedupeStage):
                    self.stats.total_deduped += 1
                
                return None
            
            current_data = result.data
        
        # All stages passed
        envelope.current_data = current_data
        envelope.status = EnvelopeStatus.PROCESSING
        envelope.target_index = self.config.output.index if self.config.output else None
        
        return envelope
    
    async def _index_batch(self):
        """Index current batch to ES"""
        if not self._batch:
            return
        
        output = self.config.output
        if not output:
            logger.warning("No output config, skipping index")
            self._batch = []
            return
        
        # Build bulk actions
        actions = []
        for doc in self._batch:
            action = {"_index": output.index}
            
            if output.doc_id_field and output.doc_id_field in doc:
                action["_id"] = doc[output.doc_id_field]
            
            if output.routing_field and output.routing_field in doc:
                action["_routing"] = doc[output.routing_field]
            
            if output.mode == OutputMode.UPDATE:
                action["_op_type"] = "update"
                action["doc"] = doc
            elif output.mode == OutputMode.UPSERT:
                action["_op_type"] = "index"
                action["_source"] = doc
            else:
                action["_source"] = doc
            
            actions.append(action)
        
        # Execute bulk
        try:
            from elasticsearch.helpers import async_bulk
            success, failed = await async_bulk(
                self.es,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
            )
            self.stats.total_indexed += success
            self.stats.total_errors += len(failed) if failed else 0
        except Exception as e:
            logger.error(f"Bulk index error: {e}")
            self.stats.total_errors += len(self._batch)
        
        self._batch = []
    
    async def run(
        self,
        source_path: str,
        resume_from: Optional[int] = None,
    ) -> PipelineStats:
        """
        Run the pipeline on a source.
        
        Args:
            source_path: Path to source file
            resume_from: Optional offset to resume from
            
        Returns:
            Pipeline statistics
        """
        self._is_running = True
        self._should_stop = False
        self.stats = PipelineStats()
        self.stats.start_time = datetime.utcnow()
        
        logger.info(f"Starting pipeline '{self.config.name}' on {source_path}")
        
        try:
            # Create reader
            self._reader = self._create_reader(source_path)
            
            with self._reader:
                # Resume if specified
                if resume_from:
                    self._reader.seek(resume_from)
                
                # Get total for progress
                total = self._reader.get_total_records()
                if total:
                    logger.info(f"Total records: {total:,}")
                
                # Process records
                for read_result in self._reader:
                    if self._should_stop:
                        logger.info("Pipeline stopped by request")
                        break
                    
                    self.stats.total_read += 1
                    
                    if not read_result.success:
                        self.stats.total_errors += 1
                        continue
                    
                    # Process through stages
                    envelope = self._process_document(
                        read_result.data, 
                        read_result.offset
                    )
                    
                    if envelope:
                        self._batch.append(envelope.current_data)
                        self.stats.total_processed += 1
                        
                        # Check batch size
                        batch_size = self.config.output.batch_size if self.config.output else 500
                        if len(self._batch) >= batch_size:
                            await self._index_batch()
                    
                    # Check error threshold
                    if self.stats.error_rate > self.config.error_threshold:
                        logger.error(f"Error rate {self.stats.error_rate:.2%} exceeded threshold")
                        break
                    
                    # Progress logging
                    if self.stats.total_read % 10000 == 0:
                        logger.info(
                            f"Progress: {self.stats.total_read:,} read, "
                            f"{self.stats.total_indexed:,} indexed, "
                            f"{self.stats.total_errors:,} errors"
                        )
                
                # Index remaining batch
                await self._index_batch()
        
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
        
        finally:
            self._is_running = False
            self.stats.end_time = datetime.utcnow()
        
        logger.info(
            f"Pipeline complete: {self.stats.total_indexed:,} indexed in "
            f"{self.stats.duration_seconds:.1f}s ({self.stats.docs_per_second:.0f} docs/s)"
        )
        
        return self.stats
    
    def stop(self):
        """Request pipeline to stop"""
        self._should_stop = True
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def get_checkpoint(self) -> Dict[str, Any]:
        """Get current checkpoint for resume"""
        return {
            "pipeline_name": self.config.name,
            "reader_checkpoint": self._reader.get_checkpoint() if self._reader else None,
            "stats": self.stats.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_dlq_records(self) -> List[Dict[str, Any]]:
        """Get records sent to DLQ"""
        return self._dlq
