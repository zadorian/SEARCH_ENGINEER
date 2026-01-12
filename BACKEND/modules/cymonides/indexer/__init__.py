"""
Cymonides Indexer Toolkit v2.0
Centralized indexing infrastructure for Elasticsearch

Tier Structure:
  C-1: cymonides-1-{projectId} - Project-specific investigation graphs
  C-2: cymonides-2 - Content corpus (scraped websites, documents)
  C-3: cymonides-3 alias -> Entity superindex (atlas, domains_unified, etc.)
  CC Graph: cc_refdom alias -> Domain reference graph (edges, vertices)
"""

from .core.envelope import DocumentEnvelope, EnvelopeStatus, TransformRecord, EntityLink
from .core.source import Source, SourceType, SourceConfig
from .core.job import IndexingJob, JobProgress, JobCheckpoint, JobStatus
from .jobs.manager import JobManager
from .schemas.registry import SchemaRegistry, TierConfig, SchemaDefinition, Tier, DataType
from .readers.base import BaseReader, ReaderConfig, ReadResult
from .readers.jsonl_reader import JSONLReader
from .readers.parquet_reader import ParquetReader
from .readers.file_reader import FileReader
from .readers.breach_reader import BreachReader
from .pipeline.engine import PipelineEngine, PipelineStats
from .pipeline.stage import PipelineStage, TransformStage, FilterStage, EnrichStage, DedupeStage
from .pipeline.config import PipelineConfig, StageConfig, OutputConfig, OutputMode

__version__ = "2.0.0"

__all__ = [
    # Core
    'DocumentEnvelope', 'EnvelopeStatus', 'TransformRecord', 'EntityLink',
    'Source', 'SourceType', 'SourceConfig',
    'IndexingJob', 'JobProgress', 'JobCheckpoint', 'JobStatus',
    
    # Jobs
    'JobManager',
    
    # Schemas
    'SchemaRegistry', 'TierConfig', 'SchemaDefinition', 'Tier', 'DataType',
    
    # Readers
    'BaseReader', 'ReaderConfig', 'ReadResult',
    'JSONLReader', 'ParquetReader', 'FileReader', 'BreachReader',
    
    # Pipeline
    'PipelineEngine', 'PipelineStats',
    'PipelineStage', 'TransformStage', 'FilterStage', 'EnrichStage', 'DedupeStage',
    'PipelineConfig', 'StageConfig', 'OutputConfig', 'OutputMode',
]
from .linking.linker import EntityLinker, LinkResult
