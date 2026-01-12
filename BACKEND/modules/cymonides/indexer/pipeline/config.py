"""
Pipeline Configuration - YAML-based declarative pipeline definitions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import yaml


class OutputMode(Enum):
    INDEX = "index"      # Create new docs
    UPDATE = "update"    # Update existing
    UPSERT = "upsert"    # Create or update


@dataclass
class StageConfig:
    """Configuration for a pipeline stage"""
    type: str  # transform, filter, enrich, dedupe
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class OutputConfig:
    """Configuration for pipeline output"""
    index: str
    mode: OutputMode = OutputMode.INDEX
    doc_id_field: Optional[str] = None
    routing_field: Optional[str] = None
    batch_size: int = 500
    refresh: bool = False


@dataclass
class PipelineConfig:
    """Full pipeline configuration"""
    name: str
    description: str = ""
    reader_type: str = "jsonl"
    reader_config: Dict[str, Any] = field(default_factory=dict)
    stages: List[StageConfig] = field(default_factory=list)
    output: OutputConfig = None
    
    # Error handling
    error_threshold: float = 0.1  # Stop if error rate exceeds this
    dlq_enabled: bool = True
    
    # Checkpointing
    checkpoint_interval: int = 10000
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'PipelineConfig':
        """Load pipeline config from YAML file"""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineConfig':
        """Create config from dictionary"""
        stages = [
            StageConfig(**s) for s in data.get('stages', [])
        ]
        
        output_data = data.get('output', {})
        output = OutputConfig(
            index=output_data.get('index', ''),
            mode=OutputMode(output_data.get('mode', 'index')),
            doc_id_field=output_data.get('doc_id_field'),
            routing_field=output_data.get('routing_field'),
            batch_size=output_data.get('batch_size', 500),
            refresh=output_data.get('refresh', False),
        )
        
        return cls(
            name=data.get('name', 'unnamed'),
            description=data.get('description', ''),
            reader_type=data.get('reader_type', 'jsonl'),
            reader_config=data.get('reader_config', {}),
            stages=stages,
            output=output,
            error_threshold=data.get('error_threshold', 0.1),
            dlq_enabled=data.get('dlq_enabled', True),
            checkpoint_interval=data.get('checkpoint_interval', 10000),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export config as dictionary"""
        return {
            'name': self.name,
            'description': self.description,
            'reader_type': self.reader_type,
            'reader_config': self.reader_config,
            'stages': [
                {'type': s.type, 'name': s.name, 'config': s.config, 'enabled': s.enabled}
                for s in self.stages
            ],
            'output': {
                'index': self.output.index if self.output else '',
                'mode': self.output.mode.value if self.output else 'index',
                'doc_id_field': self.output.doc_id_field if self.output else None,
                'routing_field': self.output.routing_field if self.output else None,
                'batch_size': self.output.batch_size if self.output else 500,
            },
            'error_threshold': self.error_threshold,
            'dlq_enabled': self.dlq_enabled,
            'checkpoint_interval': self.checkpoint_interval,
        }
    
    def to_yaml(self) -> str:
        """Export config as YAML string"""
        return yaml.dump(self.to_dict(), default_flow_style=False)


# Pre-built pipeline configs for common use cases
BREACH_PIPELINE = PipelineConfig(
    name="breach_indexer",
    description="Standard pipeline for breach data",
    reader_type="breach",
    stages=[
        StageConfig(
            type="filter",
            name="require_email",
            config={"required_fields": ["email"]},
        ),
        StageConfig(
            type="transform",
            name="normalize",
            config={
                "transforms": {"email": "lowercase", "email_domain": "lowercase"},
                "add_fields": {"indexed_at": "timestamp_now"},
            },
        ),
        StageConfig(
            type="dedupe",
            name="dedupe_email_breach",
            config={"key_fields": ["email", "breach_name"]},
        ),
    ],
    output=OutputConfig(
        index="breach_compilation",
        mode=OutputMode.INDEX,
        doc_id_field="record_hash",
        batch_size=1000,
    ),
)

CONTENT_PIPELINE = PipelineConfig(
    name="content_indexer",
    description="Pipeline for scraped web content (C-2)",
    reader_type="jsonl",
    stages=[
        StageConfig(
            type="filter",
            name="require_url",
            config={"required_fields": ["url"], "min_field_count": 2},
        ),
        StageConfig(
            type="enrich",
            name="extract_domain",
            config={"enrichments": {"domain": "extract_domain_from_url"}},
        ),
        StageConfig(
            type="transform",
            name="add_metadata",
            config={"add_fields": {"indexed_at": "timestamp_now"}},
        ),
    ],
    output=OutputConfig(
        index="cymonides-2",
        mode=OutputMode.UPSERT,
        doc_id_field="url_hash",
        batch_size=500,
    ),
)

ENTITY_PIPELINE = PipelineConfig(
    name="entity_indexer",
    description="Pipeline for entity data (C-3)",
    reader_type="jsonl",
    stages=[
        StageConfig(
            type="filter",
            name="require_entity_id",
            config={"required_fields": ["entity_id", "entity_type"]},
        ),
        StageConfig(
            type="dedupe",
            name="dedupe_entity",
            config={"key_fields": ["entity_id"]},
        ),
    ],
    output=OutputConfig(
        index="persons_unified"  # Default, actual routing by entity_type in mcp_tools,
        mode=OutputMode.UPSERT,
        doc_id_field="entity_id",
        batch_size=500,
    ),
)
