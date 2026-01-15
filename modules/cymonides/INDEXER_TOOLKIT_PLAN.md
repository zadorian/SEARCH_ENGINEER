# Cymonides Indexer Toolkit - Architecture Plan

**Version:** 1.0  
**Date:** 2026-01-09  
**Status:** PLANNING

---

## Executive Summary

Add a **centralized indexing/ingestion toolkit** to the Cymonides MCP server that provides:
- Unified job management for all data ingestion
- Progress tracking with checkpointing and resume
- Schema registry for consistent mappings
- Deduplication strategies
- Pipeline orchestration

This consolidates the fragmented indexing landscape where BRUTE, EYE-D, SERDAVOS, JESTER, and custom scripts all index to Elasticsearch independently.

---

## Current State Analysis

### Elasticsearch Index Landscape

| Index/Alias | Docs | Purpose | Indexed By |
|-------------|------|---------|------------|
| `cymonides-1-*` | 22 indices | Project graphs (C-1) | Cymonides MCP |
| `cymonides-2` | 152K | Web content corpus (C-2) | BRUTE, custom scripts |
| `cymonides-3` (alias) | **528M** | Consolidated corpus | Manual alias |
| `atlas` | 155M | Domain authority | Manual import |
| `domains_unified` | 180M | WDC company data | Manual import |
| `companies_unified` | 24M | Company records | Manual import |
| `persons_unified` | 15M | Person records | Manual import |
| `cymonides_cc_domain_*` | 143M | Domain graph (C-3) | CC import scripts |
| `onion-pages` | ? | Dark web crawls | SERDAVOS |
| `breaches-*` | ? | Breach data | Unknown (messy) |

### Current Indexing Sources

| System | What It Indexes | Where To | Has Job Tracking? |
|--------|-----------------|----------|-------------------|
| **BRUTE** | Web search results | C-2 | No |
| **EYE-D** | OSINT lookups | SQLite (not ES) | No |
| **SERDAVOS** | Onion pages | `onion-pages` | Partial (async jobs) |
| **JESTER** | Document mining | Custom ES | No |
| **TORPEDO** | News/registries | Not indexed | No |
| **Custom scripts** | Parquet/PDFs | C-2 | No |
| **Breach importer** | Breach dumps | Unknown | Unknown |

### Problems

1. **No central job registry** - Don't know what's running/completed
2. **No resume capability** - Interrupted jobs must restart from scratch
3. **No deduplication** - Same content indexed multiple times
4. **No progress visibility** - Can't monitor long-running jobs
5. **Inconsistent schemas** - Each source defines its own mappings
6. **No pipeline orchestration** - Manual coordination required

---

## Proposed Architecture

### Design Principles

1. **Everything gets indexed** - Never skip, only demote tier
2. **Checkpointing by default** - All jobs can resume
3. **Schema registry** - Consistent mappings from day 1
4. **Job visibility** - Always know what's running
5. **Extend, don't replace** - Add to Cymonides MCP, not separate server

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CYMONIDES MCP SERVER                         │
├─────────────────────────────────────────────────────────────────┤
│  EXISTING TOOLS              │  NEW INDEXER TOOLKIT             │
│  ─────────────────           │  ────────────────────            │
│  • project_*                 │  • ingest_start                  │
│  • node_*                    │  • ingest_status                 │
│  • content_search            │  • ingest_list                   │
│  • domain_*                  │  • ingest_pause/resume           │
│  • search_all                │  • ingest_cancel                 │
│  • assess_structure          │  • index_list                    │
│  • content_ingest            │  • index_create                  │
│                              │  • index_stats                   │
│                              │  • index_schema                  │
│                              │  • index_reindex                 │
└──────────────────────────────┴──────────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
           ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
           │ JOB MANAGER  │      │   PIPELINE   │      │   SCHEMA     │
           │              │      │   ENGINE     │      │   REGISTRY   │
           │ • Job store  │      │              │      │              │
           │ • Checkpoint │      │ • Reader     │      │ • Mappings   │
           │ • Progress   │      │ • Transform  │      │ • Settings   │
           │ • Resume     │      │ • Dedup      │      │ • Aliases    │
           └──────────────┘      │ • Batch      │      └──────────────┘
                    │            │ • Index      │              │
                    │            └──────────────┘              │
                    │                     │                    │
                    └─────────────────────┼────────────────────┘
                                          │
                                          ▼
                              ┌──────────────────────┐
                              │    ELASTICSEARCH     │
                              │                      │
                              │  cymonides-1-*       │
                              │  cymonides-2         │
                              │  cymonides-3         │
                              │  onion-pages         │
                              │  breaches-*          │
                              └──────────────────────┘
```

---

## New MCP Tools Specification

### 1. Job Management Tools

#### `ingest_start`
Start a new indexing job.

```python
{
    "name": "ingest_start",
    "description": "Start a new indexing job with checkpointing and progress tracking.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "source_type": {
                "type": "string",
                "enum": ["file", "directory", "parquet", "api", "elasticsearch"],
                "description": "Type of data source"
            },
            "source_path": {
                "type": "string",
                "description": "Path/URL/index to read from"
            },
            "target_index": {
                "type": "string",
                "description": "Elasticsearch index to write to"
            },
            "pipeline": {
                "type": "string",
                "enum": ["content", "breach", "entity", "domain", "raw"],
                "default": "content",
                "description": "Processing pipeline to use"
            },
            "options": {
                "type": "object",
                "properties": {
                    "batch_size": {"type": "integer", "default": 100},
                    "checkpoint_every": {"type": "integer", "default": 1000},
                    "dedup_field": {"type": "string", "default": "content_hash"},
                    "extract_entities": {"type": "boolean", "default": false},
                    "run_async": {"type": "boolean", "default": true}
                }
            }
        },
        "required": ["source_type", "source_path", "target_index"]
    }
}
```

**Returns:**
```json
{
    "job_id": "ingest-2026010912345",
    "status": "started",
    "source": {"type": "parquet", "path": "/data/pdfs/"},
    "target": "cymonides-2",
    "pipeline": "content",
    "started_at": "2026-01-09T10:30:00Z"
}
```

#### `ingest_status`
Get status of indexing job(s).

```python
{
    "name": "ingest_status",
    "description": "Get status of one or all indexing jobs.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Specific job ID, or 'all' for all jobs"
            },
            "include_completed": {
                "type": "boolean",
                "default": false,
                "description": "Include completed jobs in listing"
            }
        }
    }
}
```

**Returns:**
```json
{
    "jobs": [
        {
            "job_id": "ingest-2026010912345",
            "status": "running",
            "progress": {
                "total": 50000,
                "processed": 12500,
                "indexed": 12000,
                "failed": 50,
                "deduped": 450,
                "percent": 25.0
            },
            "rate": {
                "docs_per_sec": 125,
                "eta_seconds": 300
            },
            "checkpoint": {
                "last_offset": 12500,
                "timestamp": "2026-01-09T10:35:00Z"
            },
            "errors": ["Line 5023: Invalid JSON", "Line 8891: Missing required field"]
        }
    ]
}
```

#### `ingest_list`
List all indexing jobs with filtering.

```python
{
    "name": "ingest_list",
    "description": "List indexing jobs with optional filtering.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "running", "paused", "completed", "failed", "all"],
                "default": "all"
            },
            "target_index": {"type": "string"},
            "limit": {"type": "integer", "default": 50}
        }
    }
}
```

#### `ingest_pause` / `ingest_resume`
Control running jobs.

```python
{
    "name": "ingest_pause",
    "description": "Pause a running indexing job. Creates checkpoint for resume.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "required": true}
        }
    }
}
```

```python
{
    "name": "ingest_resume",
    "description": "Resume a paused or failed job from last checkpoint.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "required": true},
            "from_checkpoint": {
                "type": "boolean",
                "default": true,
                "description": "Resume from checkpoint (true) or restart (false)"
            }
        }
    }
}
```

#### `ingest_cancel`
Cancel and cleanup a job.

```python
{
    "name": "ingest_cancel",
    "description": "Cancel an indexing job and optionally rollback indexed docs.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "required": true},
            "rollback": {
                "type": "boolean",
                "default": false,
                "description": "Delete documents indexed by this job"
            }
        }
    }
}
```

### 2. Index Management Tools

#### `index_list`
List all Elasticsearch indices with stats.

```python
{
    "name": "index_list",
    "description": "List ES indices with document counts and sizes.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "default": "*",
                "description": "Index pattern filter (e.g., 'cymonides-*')"
            },
            "sort_by": {
                "type": "string",
                "enum": ["name", "docs", "size", "created"],
                "default": "name"
            }
        }
    }
}
```

**Returns:**
```json
{
    "indices": [
        {
            "name": "cymonides-2",
            "docs": 152797,
            "size": "1.2gb",
            "status": "green",
            "aliases": [],
            "created": "2025-06-15T00:00:00Z"
        }
    ],
    "total_indices": 45,
    "total_docs": 528000000,
    "total_size": "120gb"
}
```

#### `index_create`
Create a new index with schema from registry.

```python
{
    "name": "index_create",
    "description": "Create new ES index with registered schema.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "index_name": {"type": "string", "required": true},
            "schema": {
                "type": "string",
                "enum": ["content", "entity", "breach", "domain", "onion", "raw"],
                "required": true
            },
            "shards": {"type": "integer", "default": 1},
            "replicas": {"type": "integer", "default": 0}
        }
    }
}
```

#### `index_stats`
Detailed statistics for an index.

```python
{
    "name": "index_stats",
    "description": "Get detailed stats for an index including field distribution.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "index_name": {"type": "string", "required": true},
            "include_field_stats": {"type": "boolean", "default": false},
            "include_sample": {"type": "boolean", "default": false}
        }
    }
}
```

#### `index_schema`
Get or update index mapping.

```python
{
    "name": "index_schema",
    "description": "Get current mapping or apply schema from registry.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "index_name": {"type": "string", "required": true},
            "action": {
                "type": "string",
                "enum": ["get", "apply", "diff"],
                "default": "get"
            },
            "schema": {
                "type": "string",
                "description": "Schema name from registry (for apply/diff)"
            }
        }
    }
}
```

#### `index_reindex`
Reindex from one index to another.

```python
{
    "name": "index_reindex",
    "description": "Reindex documents from source to destination index.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "source_index": {"type": "string", "required": true},
            "dest_index": {"type": "string", "required": true},
            "query": {
                "type": "object",
                "description": "Optional ES query to filter source docs"
            },
            "transform_script": {
                "type": "string",
                "description": "Optional Painless script for transformation"
            },
            "run_async": {"type": "boolean", "default": true}
        }
    }
}
```

---

## Internal Components

### 1. Job Manager (`/data/CYMONIDES/indexer/job_manager.py`)

```python
class IndexingJob:
    """Represents a single indexing job with full lifecycle tracking."""
    
    job_id: str
    status: Literal["pending", "running", "paused", "completed", "failed", "cancelled"]
    
    # Source configuration
    source_type: str  # file, directory, parquet, api, elasticsearch
    source_path: str
    source_config: Dict[str, Any]
    
    # Target configuration
    target_index: str
    pipeline: str
    
    # Progress tracking
    progress: JobProgress
    
    # Checkpoint for resume
    checkpoint: JobCheckpoint
    
    # Timing
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Error tracking
    errors: List[str]
    last_error: Optional[str]


class JobProgress:
    total: int          # Total items to process
    processed: int      # Items processed so far
    indexed: int        # Items successfully indexed
    failed: int         # Items that failed
    deduped: int        # Items skipped as duplicates
    
    @property
    def percent(self) -> float:
        return (self.processed / self.total * 100) if self.total > 0 else 0


class JobCheckpoint:
    last_offset: int              # File offset or record number
    last_id: Optional[str]        # Last processed document ID
    last_timestamp: datetime      # When checkpoint was created
    checkpoint_file: str          # Path to checkpoint file
    
    
class JobManager:
    """Central registry for all indexing jobs."""
    
    def __init__(self, es: Elasticsearch, jobs_dir: str = "/data/CYMONIDES/jobs"):
        self.es = es
        self.jobs_dir = Path(jobs_dir)
        self.jobs_index = "cymonides-jobs"
        self._active_jobs: Dict[str, IndexingJob] = {}
    
    async def create_job(self, config: Dict) -> IndexingJob:
        """Create and register a new job."""
        
    async def start_job(self, job_id: str) -> bool:
        """Start executing a job."""
        
    async def pause_job(self, job_id: str) -> bool:
        """Pause a running job with checkpoint."""
        
    async def resume_job(self, job_id: str, from_checkpoint: bool = True) -> bool:
        """Resume a paused/failed job."""
        
    async def cancel_job(self, job_id: str, rollback: bool = False) -> bool:
        """Cancel a job and optionally rollback."""
        
    async def get_job(self, job_id: str) -> Optional[IndexingJob]:
        """Get job by ID."""
        
    async def list_jobs(self, status: str = "all", limit: int = 50) -> List[IndexingJob]:
        """List jobs with optional status filter."""
        
    def _save_checkpoint(self, job: IndexingJob):
        """Save checkpoint to disk and ES."""
        
    def _load_checkpoint(self, job_id: str) -> Optional[JobCheckpoint]:
        """Load checkpoint from disk."""
```

### 2. Pipeline Engine (`/data/CYMONIDES/indexer/pipeline.py`)

```python
class PipelineStage(ABC):
    """Abstract base for pipeline stages."""
    
    @abstractmethod
    async def process(self, doc: Dict) -> Optional[Dict]:
        """Process a document. Return None to skip."""
        pass


class ReaderStage(PipelineStage):
    """Read documents from source."""
    pass


class TransformStage(PipelineStage):
    """Transform document fields."""
    pass


class DeduplicatorStage(PipelineStage):
    """Check for duplicates."""
    
    def __init__(self, es: Elasticsearch, target_index: str, dedup_field: str = "content_hash"):
        self.es = es
        self.target_index = target_index
        self.dedup_field = dedup_field
        self._seen_hashes: Set[str] = set()
        
    async def process(self, doc: Dict) -> Optional[Dict]:
        hash_val = doc.get(self.dedup_field)
        if hash_val in self._seen_hashes:
            return None  # Skip duplicate
        
        # Check ES
        exists = await self._check_es(hash_val)
        if exists:
            return None
            
        self._seen_hashes.add(hash_val)
        return doc


class IndexerStage(PipelineStage):
    """Batch index to Elasticsearch."""
    
    def __init__(self, es: Elasticsearch, target_index: str, batch_size: int = 100):
        self.es = es
        self.target_index = target_index
        self.batch_size = batch_size
        self._batch: List[Dict] = []
        
    async def process(self, doc: Dict) -> Optional[Dict]:
        self._batch.append(doc)
        if len(self._batch) >= self.batch_size:
            await self._flush()
        return doc
        
    async def _flush(self):
        if self._batch:
            await bulk(self.es, self._batch)
            self._batch = []


class Pipeline:
    """Orchestrates document flow through stages."""
    
    def __init__(self, name: str, stages: List[PipelineStage]):
        self.name = name
        self.stages = stages
        
    async def run(self, source: AsyncIterator[Dict], job: IndexingJob) -> PipelineResult:
        """Execute pipeline on source documents."""
        
        async for doc in source:
            try:
                for stage in self.stages:
                    doc = await stage.process(doc)
                    if doc is None:
                        job.progress.deduped += 1
                        break
                else:
                    job.progress.indexed += 1
            except Exception as e:
                job.progress.failed += 1
                job.errors.append(str(e))
            finally:
                job.progress.processed += 1
                
            # Checkpoint periodically
            if job.progress.processed % job.checkpoint_interval == 0:
                await self._checkpoint(job)
```

### 3. Schema Registry (`/data/CYMONIDES/indexer/schema_registry.py`)

```python
SCHEMA_REGISTRY = {
    "content": {
        "description": "Web content corpus (C-2 compatible)",
        "index_pattern": "cymonides-2",
        "settings": {
            "number_of_shards": 3,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "content_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "source_domain": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "content_analyzer"},
                "content": {"type": "text", "analyzer": "content_analyzer"},
                "content_hash": {"type": "keyword"},
                "language": {"type": "keyword"},
                "word_count": {"type": "integer"},
                "fetched_at": {"type": "date"},
                "metadata": {"type": "object", "enabled": True},
                "concepts": {
                    "properties": {
                        "themes": {"type": "keyword"},
                        "phenomena": {"type": "keyword"},
                        "red_flag_themes": {"type": "keyword"},
                        "methodologies": {"type": "keyword"}
                    }
                },
                "temporal": {
                    "properties": {
                        "published_date": {"type": "date"},
                        "content_years": {"type": "integer"},
                        "temporal_focus": {"type": "keyword"}
                    }
                },
                "dimension_keys": {"type": "keyword"},
                "project_ids": {"type": "keyword"},
                "extracted_entity_ids": {"type": "keyword"},
                "has_embedding": {"type": "boolean"},
                "content_embedding": {"type": "dense_vector", "dims": 768}
            }
        }
    },
    
    "breach": {
        "description": "Breach data records",
        "index_pattern": "breaches-*",
        "settings": {
            "number_of_shards": 2,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "email": {"type": "keyword"},
                "email_domain": {"type": "keyword"},
                "username": {"type": "keyword"},
                "password_hash": {"type": "keyword"},
                "password_plain": {"type": "keyword"},
                "phone": {"type": "keyword"},
                "name": {"type": "text"},
                "ip_address": {"type": "ip"},
                "source_breach": {"type": "keyword"},
                "breach_date": {"type": "date"},
                "indexed_at": {"type": "date"},
                "data_types": {"type": "keyword"},  # [email, password, phone, etc.]
                "metadata": {"type": "object"}
            }
        }
    },
    
    "entity": {
        "description": "C-1 project node graph",
        "index_pattern": "cymonides-1-*",
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "className": {"type": "keyword"},
                "typeName": {"type": "keyword"},
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "canonicalValue": {"type": "keyword"},
                "snippet": {"type": "text"},
                "userId": {"type": "integer"},
                "projectId": {"type": "keyword"},
                "metadata": {"type": "object"},
                "properties": {"type": "object"},
                "embedded_edges": {"type": "nested"},
                "createdAt": {"type": "date"},
                "updatedAt": {"type": "date"}
            }
        }
    },
    
    "domain": {
        "description": "Domain graph vertices (C-3)",
        "index_pattern": "cymonides_cc_domain_vertices",
        "mappings": {
            "properties": {
                "domain": {"type": "keyword"},
                "authority_score": {"type": "float"},
                "category": {"type": "keyword"},
                "country": {"type": "keyword"},
                "language": {"type": "keyword"},
                "rank": {"type": "integer"},
                "metadata": {"type": "object"}
            }
        }
    },
    
    "onion": {
        "description": "Dark web pages from SERDAVOS",
        "index_pattern": "onion-pages",
        "mappings": {
            "properties": {
                "url": {"type": "keyword"},
                "domain": {"type": "keyword"},
                "title": {"type": "text"},
                "content": {"type": "text"},
                "outlinks": {"type": "keyword"},
                "crawled_at": {"type": "date"},
                "source": {"type": "keyword"},
                "screenshot_path": {"type": "keyword"},
                "metadata": {"type": "object"}
            }
        }
    },
    
    "raw": {
        "description": "Raw documents with minimal processing",
        "index_pattern": "raw-*",
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "content": {"type": "text"},
                "metadata": {"type": "object"},
                "indexed_at": {"type": "date"}
            }
        }
    }
}


class SchemaRegistry:
    """Manages index schemas and provides creation/validation."""
    
    def __init__(self):
        self.schemas = SCHEMA_REGISTRY
        
    def get_schema(self, name: str) -> Optional[Dict]:
        return self.schemas.get(name)
        
    def list_schemas(self) -> List[str]:
        return list(self.schemas.keys())
        
    def create_index(self, es: Elasticsearch, index_name: str, schema: str) -> bool:
        """Create index with registered schema."""
        schema_def = self.get_schema(schema)
        if not schema_def:
            raise ValueError(f"Unknown schema: {schema}")
            
        return es.indices.create(
            index=index_name,
            settings=schema_def.get("settings", {}),
            mappings=schema_def.get("mappings", {})
        )
        
    def diff_schema(self, es: Elasticsearch, index_name: str, schema: str) -> Dict:
        """Compare current index mapping with registered schema."""
        pass
```

### 4. Source Readers (`/data/CYMONIDES/indexer/readers/`)

```python
# readers/__init__.py

class BaseReader(ABC):
    """Abstract base for document source readers."""
    
    @abstractmethod
    async def __aiter__(self) -> AsyncIterator[Dict]:
        """Yield documents one at a time."""
        pass
        
    @abstractmethod
    def get_total(self) -> Optional[int]:
        """Get total document count if known."""
        pass
        
    @abstractmethod
    def seek(self, offset: int):
        """Seek to offset for resume."""
        pass


# readers/parquet_reader.py
class ParquetReader(BaseReader):
    """Read from Parquet files."""
    
    def __init__(self, path: str, batch_size: int = 1000):
        self.path = Path(path)
        self.batch_size = batch_size
        self._offset = 0
        
    async def __aiter__(self):
        files = sorted(self.path.glob("*.parquet"))
        for pq_file in files:
            table = pq.read_table(pq_file)
            for batch in table.to_batches(max_chunksize=self.batch_size):
                for row in batch.to_pylist():
                    self._offset += 1
                    yield row


# readers/jsonl_reader.py
class JSONLReader(BaseReader):
    """Read from JSONL files."""
    pass


# readers/elasticsearch_reader.py  
class ElasticsearchReader(BaseReader):
    """Read from another ES index (for reindexing)."""
    pass


# readers/api_reader.py
class APIReader(BaseReader):
    """Read from paginated API endpoint."""
    pass
```

---

## File Structure

```
/data/CYMONIDES/
├── mcp_server.py              # ADD: new tools (12 tools)
├── indexer/                   # NEW: Indexer module
│   ├── __init__.py
│   ├── job_manager.py         # Job lifecycle management
│   ├── pipeline.py            # Pipeline stages and orchestration
│   ├── schema_registry.py     # Index schema definitions
│   ├── checkpoint.py          # Checkpoint/resume logic
│   ├── deduplicator.py        # Deduplication strategies
│   ├── readers/               # Source readers
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── parquet_reader.py
│   │   ├── jsonl_reader.py
│   │   ├── elasticsearch_reader.py
│   │   └── api_reader.py
│   ├── transformers/          # Document transformers
│   │   ├── __init__.py
│   │   ├── content_transformer.py
│   │   ├── breach_transformer.py
│   │   └── entity_transformer.py
│   └── pipelines/             # Pre-built pipelines
│       ├── __init__.py
│       ├── content_pipeline.py
│       ├── breach_pipeline.py
│       └── entity_pipeline.py
├── jobs/                      # NEW: Job state storage
│   └── .gitkeep
├── schemas/                   # NEW: Schema files (backup)
│   ├── content.json
│   ├── breach.json
│   ├── entity.json
│   ├── domain.json
│   └── onion.json
└── (existing files...)
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goal:** Foundation for job management and pipelines.

1. Create `/data/CYMONIDES/indexer/` directory structure
2. Implement `JobManager` class with ES-backed storage
3. Implement `JobProgress` and `JobCheckpoint` models
4. Implement base `Pipeline` and `PipelineStage` classes
5. Implement `SchemaRegistry` with 6 schemas
6. Add basic readers: `ParquetReader`, `JSONLReader`

**Deliverable:** Working job tracking with manual Python API.

### Phase 2: MCP Tools (Week 2)

**Goal:** Expose indexer via MCP.

7. Add to `mcp_server.py`:
   - `ingest_start`
   - `ingest_status`
   - `ingest_list`
   - `ingest_pause`
   - `ingest_resume`
   - `ingest_cancel`
8. Add index management tools:
   - `index_list`
   - `index_create`
   - `index_stats`
   - `index_schema`

**Deliverable:** Full MCP integration, Claude can manage indexing.

### Phase 3: Pipelines (Week 3)

**Goal:** Build specialized pipelines.

9. Implement `ContentPipeline` (for C-2 web content)
10. Implement `BreachPipeline` (for breach data)
11. Implement `EntityPipeline` (for C-1 nodes)
12. Add deduplication strategies
13. Add transformation stages

**Deliverable:** Ready for production indexing.

### Phase 4: Advanced Features (Week 4)

**Goal:** Polish and advanced capabilities.

14. Implement `ElasticsearchReader` for reindexing
15. Add `index_reindex` tool
16. Add monitoring/alerting hooks
17. Add job prioritization
18. Documentation and testing

**Deliverable:** Production-ready indexer toolkit.

---

## Usage Examples

### Start Indexing PDFs

```
User: Index the PDF parquet files to cymonides-2

Claude: [Uses ingest_start]
{
    "source_type": "parquet",
    "source_path": "/data/output/finepdfs_corporate/",
    "target_index": "cymonides-2",
    "pipeline": "content",
    "options": {
        "batch_size": 100,
        "checkpoint_every": 1000,
        "extract_entities": true
    }
}

Response: Job ingest-2026010912345 started. Processing 50,000 documents.
```

### Check Progress

```
User: How's the indexing going?

Claude: [Uses ingest_status]

Response:
Job: ingest-2026010912345
Status: RUNNING
Progress: 25,000/50,000 (50%)
Rate: 150 docs/sec
ETA: 2 minutes 47 seconds
Indexed: 24,500 | Failed: 50 | Deduped: 450
```

### Resume Failed Job

```
User: The indexing job failed, can you resume it?

Claude: [Uses ingest_resume]
{
    "job_id": "ingest-2026010912345",
    "from_checkpoint": true
}

Response: Resuming from checkpoint at offset 25,000. 25,000 documents remaining.
```

### Create New Index

```
User: Create a new breach index for 2026 data

Claude: [Uses index_create]
{
    "index_name": "breaches-2026",
    "schema": "breach",
    "shards": 2
}

Response: Created index breaches-2026 with breach schema.
```

---

## Migration Path

### Existing Systems Integration

| System | Current Behavior | After Integration |
|--------|------------------|-------------------|
| **BRUTE** | Direct ES index | Can use `ingest_start` or keep direct |
| **SERDAVOS** | Own async jobs | Uses JobManager for tracking |
| **Custom scripts** | No tracking | Migrate to `ingest_start` |
| **Breach importer** | Unknown | New `breach` pipeline |

### Backward Compatibility

- Existing `content_ingest` tool remains functional
- Direct ES indexing still works
- New tools are additive, not replacing

---

## Success Metrics

1. **Job visibility**: Can always see what's running/completed
2. **Resume rate**: >95% of interrupted jobs resume successfully
3. **Dedup efficiency**: <1% duplicate documents indexed
4. **Index consistency**: All indices use registered schemas
5. **Throughput**: >100 docs/sec sustained indexing rate

---

## Open Questions

1. **Job storage**: ES index vs file-based vs SQLite?
   - **Recommendation:** ES index (`cymonides-jobs`) for queryability

2. **Real-time progress**: WebSocket/SSE vs polling?
   - **Recommendation:** Polling via `ingest_status` (simpler)

3. **Multi-node**: Single server or distributed?
   - **Recommendation:** Single server initially (176.9.2.153)

4. **Breach data source**: What format? Where located?
   - **Need input from user**

---

## Next Steps

1. **Approve this plan**
2. **Clarify breach data source/format**
3. **Begin Phase 1 implementation**
