# Cymonides Indexer Toolkit V2 - Intelligence-Grade Architecture

**Version:** 2.0  
**Date:** 2026-01-09  
**Status:** PLANNING (IMPROVED)

---

## What Changed from V1

| Aspect | V1 (Basic ETL) | V2 (Intelligence Platform) |
|--------|----------------|---------------------------|
| **Mental model** | Data loader | Intelligence aggregator |
| **Data unit** | Raw dict | DocumentEnvelope with full lineage |
| **Sources** | Just paths | First-class Source registry with state |
| **Pipelines** | Hardcoded Python | Declarative YAML, versionable |
| **Failures** | Log and skip | DLQ with auto-retry + inspection |
| **Dedup** | Simple hash | Multi-field + fuzzy + merge strategies |
| **Entity linking** | None | Auto-link to C-1 graph during indexing |
| **Quality** | None | Quality gates + confidence scoring |
| **Routing** | Single target | Rule-based multi-target routing |
| **Observability** | Basic progress | Full metrics, tracing, alerting |
| **Tools** | 12 | 20 |

**Key insight:** For investigative OSINT, indexing IS the intelligence operation. The indexer doesn't just load data—it connects, enriches, validates, and links entities across sources.

---

## Core Concepts

### 1. Document Envelope

Every document travels through the pipeline wrapped in an envelope that accumulates metadata:

```python
@dataclass
class DocumentEnvelope:
    """Immutable wrapper carrying document + processing metadata."""
    
    # === Identity ===
    envelope_id: str              # Unique processing attempt ID
    document_id: str              # Content-derived ID (for dedup)
    
    # === Provenance ===
    source_id: str                # Which registered source
    source_offset: int            # Position in source (for resume)
    source_record: Dict           # Original source metadata
    extracted_at: datetime
    
    # === Content ===
    raw_data: bytes               # Original unchanged (for replay)
    current_data: Dict            # After transforms
    
    # === Processing Trail ===
    transforms_applied: List[TransformRecord]
    validation_result: Optional[ValidationResult]
    enrichments: Dict[str, Any]   # Added computed fields
    
    # === Entity Links ===
    entity_links: List[EntityLink]  # Links to C-1 canonical entities
    
    # === Routing ===
    target_index: str             # Where it will go
    routing_rule: str             # Which rule matched
    priority: int                 # Indexing priority
    
    # === Quality ===
    quality_score: float          # 0-1 confidence
    flags: Set[str]               # {needs_review, high_value, duplicate_candidate}
    
    # === Outcome ===
    status: EnvelopeStatus        # pending, indexed, failed, dlq
    indexed_at: Optional[datetime]
    error: Optional[str]
```

**Why this matters:**
- Full audit trail for every document
- Can replay processing with different pipeline
- Know exactly why each routing decision was made
- Track quality across sources

---

### 2. Source Registry

Sources are first-class entities with persistent state:

```python
@dataclass
class Source:
    """Registered data source with sync state."""
    
    # === Identity ===
    id: str                       # Unique identifier (e.g., "breach-linkedin-2023")
    name: str                     # Human name
    description: str
    
    # === Type & Config ===
    type: SourceType              # file, directory, api, elasticsearch, stream
    config: SourceConfig          # Type-specific configuration
    
    # === Schema ===
    input_schema: str             # Expected raw format
    output_pipeline: str          # Pipeline to use
    
    # === State (Persisted) ===
    enabled: bool
    created_at: datetime
    last_sync_at: Optional[datetime]
    last_sync_status: str         # success, partial, failed
    sync_cursor: Dict             # Opaque cursor for incremental sync
    
    # === Metrics ===
    total_docs_seen: int
    total_docs_indexed: int
    total_docs_failed: int
    total_docs_deduped: int
    avg_doc_quality: float
    error_rate_7d: float
    
    # === Health ===
    last_error: Optional[str]
    last_error_at: Optional[datetime]
    consecutive_failures: int
```

**Source Types:**

| Type | Config | Incremental Support |
|------|--------|---------------------|
| `file` | `{path, format}` | Modified time |
| `directory` | `{path, pattern, recursive}` | File list diff |
| `parquet` | `{path, partition_cols}` | Partition tracking |
| `api` | `{url, auth, pagination}` | Cursor/offset |
| `elasticsearch` | `{index, query}` | Scroll + timestamp |
| `stream` | `{kafka_topic, consumer_group}` | Offset commit |
| `breach_dump` | `{path, format, breach_name}` | Full rescan |

---

### 3. Declarative Pipelines

Pipelines defined in YAML, stored in `/data/CYMONIDES/pipelines/`:

```yaml
# pipelines/breach.yaml
name: breach_pipeline
version: 2.1
description: "Process breach dumps into searchable intelligence"

# Schema validation
input_schema: raw_breach
output_schema: breach

# Processing stages (executed in order)
stages:

  # === VALIDATION ===
  - name: require_identifier
    type: validator
    description: "Must have at least one identifier"
    config:
      required_one_of: [email, username, phone]
      on_fail: dead_letter
      
  - name: validate_email_format
    type: validator
    when: "email != null"
    config:
      field: email
      pattern: "^[^@]+@[^@]+\\.[^@]+$"
      on_fail: flag  # Don't reject, just flag
      flag: invalid_email
      
  # === NORMALIZATION ===
  - name: normalize_identifiers
    type: transform
    config:
      operations:
        - field: email
          ops: [lowercase, trim, remove_dots_before_at]
        - field: username
          ops: [lowercase, trim]
        - field: phone
          ops: [normalize_phone, e164_format]
          
  - name: derive_email_domain
    type: transform
    when: "email != null"
    config:
      operations:
        - field: email_domain
          derive_from: email
          op: extract_domain
        - field: email_local
          derive_from: email
          op: extract_local_part
          
  # === SECURITY ===
  - name: hash_sensitive
    type: transform
    config:
      operations:
        - field: password_hash
          derive_from: password_plain
          op: sha256
          when: "password_plain != null AND password_hash == null"
        - field: password_plain
          op: redact  # Remove plaintext from final doc
          
  # === ENRICHMENT ===
  - name: detect_email_patterns
    type: enricher
    config:
      enrichments:
        - name: disposable_email
          field: email_domain
          lookup: lists/disposable_domains.txt
          add_flag: disposable_email
          
        - name: corporate_email
          field: email_domain
          lookup: lists/fortune500_domains.txt
          add_flag: corporate_target
          add_field: corporate_company
          
        - name: government_email
          field: email_domain
          lookup: lists/government_domains.txt
          add_flag: government_target
          priority_boost: 100
          
  - name: password_analysis
    type: enricher
    when: "password_hash != null"
    config:
      enrichments:
        - name: known_password
          field: password_hash
          lookup_index: known_passwords
          add_flag: weak_password
          add_field: password_commonality_rank
          
  # === ENTITY LINKING ===
  - name: link_to_entities
    type: entity_linker
    config:
      strategies:
        - field: email
          linker: email
          create_if_missing: true
          entity_type: person
          
        - field: phone
          linker: phone
          create_if_missing: true
          entity_type: person
          
        - field: email_domain
          linker: domain
          create_if_missing: false
          entity_type: company
          
  # === DEDUPLICATION ===
  - name: deduplicate
    type: dedup
    config:
      # Primary key for exact dedup
      key: [email, source_breach]
      
      # Strategy when duplicate found
      strategy: merge_newest  # keep_first, keep_newest, merge_newest, merge_all
      
      # Fields to merge (for merge strategies)
      merge_fields: [password_hash, phone, name, data_types]
      
      # Fuzzy dedup (optional second pass)
      fuzzy:
        enabled: true
        candidates:
          - fields: [email_local, email_domain]
            threshold: 0.9
        action: flag  # Don't merge, just flag for review
        flag: possible_duplicate
        
  # === QUALITY GATE ===
  - name: quality_check
    type: quality_gate
    config:
      rules:
        - name: min_fields
          check: "len(non_null_fields) >= 2"
          weight: 0.3
          
        - name: valid_identifier
          check: "email_valid OR phone_valid OR username != null"
          weight: 0.5
          
        - name: has_enrichment
          check: "len(entity_links) > 0"
          weight: 0.2
          
      min_score: 0.5
      on_fail: index_with_flag  # index anyway, but flag
      flag: low_quality
      
  # === ROUTING ===
  - name: route_to_index
    type: router
    config:
      rules:
        - name: corporate_breaches
          when: "flags contains 'corporate_target'"
          target: breaches-corporate
          priority: 100
          
        - name: government_breaches
          when: "flags contains 'government_target'"
          target: breaches-government
          priority: 200
          
        - name: by_source
          when: "source_breach in ['linkedin', 'facebook', 'twitter']"
          target: "breaches-{source_breach}"
          
        - name: default
          when: "true"
          target: breaches-general

# Pipeline metadata
metadata:
  author: system
  created: 2026-01-09
  tags: [breach, osint, pii]
  estimated_throughput: 500/sec
```

---

### 4. Dead Letter Queue

Failed documents go to DLQ for inspection and retry:

```python
@dataclass
class DLQEntry:
    """Document that failed processing."""
    
    id: str
    envelope: DocumentEnvelope    # Full envelope at time of failure
    
    # Failure info
    error_type: str               # validation, transform, index, timeout, unknown
    error_message: str
    error_stage: str              # Which pipeline stage
    error_traceback: str
    
    # Job context
    job_id: str
    pipeline: str
    pipeline_version: str
    
    # Retry tracking
    attempts: int
    first_failure_at: datetime
    last_failure_at: datetime
    next_retry_at: Optional[datetime]
    
    # Status
    status: DLQStatus             # pending_retry, manual_review, abandoned, resolved
    resolution: Optional[str]     # How it was resolved
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]


class DeadLetterQueue:
    """Manages failed documents with retry logic."""
    
    index: str = "cymonides-dlq"
    
    # Retry policy
    RETRY_POLICY = {
        "max_attempts": 5,
        "initial_delay_seconds": 60,
        "backoff_multiplier": 2,
        "max_delay_seconds": 3600,
        "retryable_errors": [
            "timeout", 
            "es_unavailable", 
            "rate_limited",
            "temporary_failure"
        ]
    }
    
    async def add(
        self, 
        envelope: DocumentEnvelope, 
        error: Exception, 
        stage: str,
        job_id: str
    ) -> str:
        """Add failed document to DLQ."""
        
    async def get(self, dlq_id: str) -> DLQEntry:
        """Get single DLQ entry for inspection."""
        
    async def list(
        self,
        status: Optional[DLQStatus] = None,
        error_type: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 100
    ) -> List[DLQEntry]:
        """List DLQ entries with filters."""
        
    async def retry(
        self, 
        dlq_id: str,
        force: bool = False  # Retry even if max attempts reached
    ) -> RetryResult:
        """Retry single entry."""
        
    async def retry_batch(
        self,
        filter: DLQFilter,
        max_batch: int = 100
    ) -> BatchRetryResult:
        """Retry multiple entries matching filter."""
        
    async def abandon(
        self,
        dlq_id: str,
        reason: str
    ) -> bool:
        """Mark as not retryable."""
        
    async def resolve(
        self,
        dlq_id: str,
        resolution: str,
        resolved_by: str = "system"
    ) -> bool:
        """Mark as resolved (e.g., manually fixed and reindexed)."""
        
    async def stats(self) -> DLQStats:
        """Get DLQ statistics."""
        
    async def process_retries(self) -> int:
        """Background task: process pending retries. Returns count processed."""
```

---

### 5. Entity Linking

Auto-link documents to canonical entities in C-1 during indexing:

```python
class EntityLinker:
    """Links document fields to canonical C-1 entities."""
    
    def __init__(self, es: Elasticsearch, c1_index_pattern: str = "cymonides-1-*"):
        self.es = es
        self.c1_pattern = c1_index_pattern
        
        # Linker strategies by field type
        self.linkers = {
            "email": EmailLinker(es),
            "phone": PhoneLinker(es),
            "name": NameLinker(es),
            "domain": DomainLinker(es),
            "company": CompanyLinker(es),
            "username": UsernameLinker(es),
        }
        
    async def link(
        self,
        doc: Dict,
        strategies: List[LinkStrategy],
        project_id: Optional[str] = None
    ) -> List[EntityLink]:
        """
        Find or create entity links for document fields.
        
        Args:
            doc: Document with fields to link
            strategies: Which fields to link and how
            project_id: Optional C-1 project to link within
            
        Returns:
            List of EntityLink objects to store with document
        """
        links = []
        
        for strategy in strategies:
            field = strategy.field
            value = doc.get(field)
            
            if value is None:
                continue
                
            linker = self.linkers.get(strategy.linker)
            if linker is None:
                continue
                
            # Find existing entity
            entity = await linker.find(
                value,
                entity_type=strategy.entity_type,
                project_id=project_id
            )
            
            if entity is None and strategy.create_if_missing:
                # Create new canonical entity
                entity = await linker.create(
                    value,
                    entity_type=strategy.entity_type,
                    project_id=project_id,
                    source_doc_id=doc.get("id")
                )
                
            if entity:
                links.append(EntityLink(
                    field=field,
                    value=value,
                    entity_id=entity.id,
                    entity_type=entity.type,
                    entity_label=entity.label,
                    confidence=entity.match_confidence,
                    link_type=strategy.link_type or "extracted_from"
                ))
                
        return links


@dataclass
class EntityLink:
    """Link from document field to C-1 entity."""
    
    field: str                    # Source field in document
    value: str                    # Field value that was linked
    entity_id: str                # C-1 entity ID
    entity_type: str              # person, company, domain, etc.
    entity_label: str             # Entity display label
    confidence: float             # 0-1 match confidence
    link_type: str                # extracted_from, mentioned_in, etc.
```

**Example flow:**

```
1. Breach record arrives:
   {email: "john.smith@acme.com", password_hash: "abc123"}

2. EmailLinker searches C-1:
   - Finds existing person entity "person-12345" (John Smith at Acme)
   - Match confidence: 0.95

3. Document gets entity_links:
   [{
     field: "email",
     value: "john.smith@acme.com",
     entity_id: "person-12345",
     entity_type: "person",
     entity_label: "John Smith",
     confidence: 0.95,
     link_type: "extracted_from"
   }]

4. Document indexed with links

5. Later: Query "Show all data for person-12345"
   → Returns: breach records, social profiles, corporate filings, etc.
```

---

### 6. Quality Gates

Validate data quality before indexing:

```python
@dataclass
class QualityRule:
    """Single quality check rule."""
    
    name: str
    check: str                    # Expression to evaluate
    weight: float                 # Weight in final score (0-1)
    on_fail: str                  # continue, flag, reject
    flag: Optional[str]           # Flag to add on fail


@dataclass
class QualityResult:
    """Result of quality check."""
    
    passed: bool
    score: float                  # 0-1 aggregate score
    rule_results: Dict[str, bool]
    flags_added: Set[str]
    rejection_reason: Optional[str]


class QualityGate:
    """Validates document quality."""
    
    def __init__(self, rules: List[QualityRule], min_score: float = 0.5):
        self.rules = rules
        self.min_score = min_score
        
    def check(self, doc: Dict, envelope: DocumentEnvelope) -> QualityResult:
        """
        Run all quality rules against document.
        
        Context available to rules:
        - doc: The document fields
        - envelope: Full envelope with metadata
        - non_null_fields: List of fields with values
        - entity_links: Links created by entity linker
        - flags: Current flags on envelope
        """
        context = {
            "doc": doc,
            "envelope": envelope,
            "non_null_fields": [k for k, v in doc.items() if v is not None],
            "entity_links": envelope.entity_links,
            "flags": envelope.flags,
            # Helper functions
            "len": len,
            "any": any,
            "all": all,
        }
        
        total_weight = sum(r.weight for r in self.rules)
        earned_weight = 0
        rule_results = {}
        flags_added = set()
        
        for rule in self.rules:
            try:
                passed = eval(rule.check, {"__builtins__": {}}, context)
                rule_results[rule.name] = passed
                
                if passed:
                    earned_weight += rule.weight
                else:
                    if rule.flag:
                        flags_added.add(rule.flag)
            except Exception as e:
                rule_results[rule.name] = False
                
        score = earned_weight / total_weight if total_weight > 0 else 0
        passed = score >= self.min_score
        
        return QualityResult(
            passed=passed,
            score=score,
            rule_results=rule_results,
            flags_added=flags_added,
            rejection_reason=None if passed else f"Score {score:.2f} < {self.min_score}"
        )
```

---

## MCP Tools (20 Total)

### Job Management (6 tools)

| Tool | Description |
|------|-------------|
| `ingest_start` | Start new indexing job with source/pipeline config |
| `ingest_status` | Get job progress, rate, ETA, errors |
| `ingest_list` | List jobs with status filter |
| `ingest_pause` | Pause job with checkpoint |
| `ingest_resume` | Resume from checkpoint |
| `ingest_cancel` | Cancel job, optional rollback |

### Source Management (4 tools)

| Tool | Description |
|------|-------------|
| `source_register` | Register new data source |
| `source_list` | List sources with health metrics |
| `source_sync` | Trigger incremental sync |
| `source_disable` | Disable problematic source |

### Index Management (5 tools)

| Tool | Description |
|------|-------------|
| `index_list` | List indices with stats |
| `index_create` | Create with registered schema |
| `index_stats` | Detailed index statistics |
| `index_schema` | Get/apply/diff mappings |
| `index_reindex` | Reindex between indices |

### Pipeline Management (2 tools)

| Tool | Description |
|------|-------------|
| `pipeline_list` | List available pipelines |
| `pipeline_validate` | Validate pipeline YAML |

### Dead Letter Queue (3 tools)

| Tool | Description |
|------|-------------|
| `dlq_list` | List failed documents |
| `dlq_retry` | Retry failed documents |
| `dlq_stats` | Error distribution, retry rates |

---

## File Structure

```
/data/CYMONIDES/
├── mcp_server.py                    # Add 20 new tools
│
├── indexer/                         # NEW: Core indexer module
│   ├── __init__.py
│   │
│   ├── core/                        # Core abstractions
│   │   ├── __init__.py
│   │   ├── envelope.py              # DocumentEnvelope
│   │   ├── source.py                # Source model
│   │   ├── job.py                   # Job model
│   │   └── result.py                # Result types
│   │
│   ├── jobs/                        # Job management
│   │   ├── __init__.py
│   │   ├── manager.py               # JobManager
│   │   ├── checkpoint.py            # Checkpoint/resume
│   │   └── scheduler.py             # Job scheduling
│   │
│   ├── sources/                     # Source registry
│   │   ├── __init__.py
│   │   ├── registry.py              # SourceRegistry
│   │   └── sync.py                  # Incremental sync logic
│   │
│   ├── readers/                     # Source readers
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseReader ABC
│   │   ├── file_reader.py
│   │   ├── parquet_reader.py
│   │   ├── jsonl_reader.py
│   │   ├── api_reader.py
│   │   └── elasticsearch_reader.py
│   │
│   ├── pipeline/                    # Pipeline engine
│   │   ├── __init__.py
│   │   ├── engine.py                # PipelineEngine
│   │   ├── loader.py                # Load YAML pipelines
│   │   └── stages/                  # Stage implementations
│   │       ├── __init__.py
│   │       ├── base.py              # BaseStage ABC
│   │       ├── validator.py
│   │       ├── transformer.py
│   │       ├── enricher.py
│   │       ├── deduplicator.py
│   │       ├── entity_linker.py
│   │       ├── quality_gate.py
│   │       ├── router.py
│   │       └── indexer.py
│   │
│   ├── dlq/                         # Dead Letter Queue
│   │   ├── __init__.py
│   │   ├── queue.py                 # DeadLetterQueue
│   │   └── retry.py                 # Retry logic
│   │
│   ├── linking/                     # Entity linking
│   │   ├── __init__.py
│   │   ├── linker.py                # EntityLinker
│   │   └── strategies/              # Linking strategies
│   │       ├── __init__.py
│   │       ├── email.py
│   │       ├── phone.py
│   │       ├── name.py
│   │       ├── domain.py
│   │       └── company.py
│   │
│   ├── quality/                     # Quality management
│   │   ├── __init__.py
│   │   └── gate.py                  # QualityGate
│   │
│   ├── schemas/                     # Schema registry
│   │   ├── __init__.py
│   │   ├── registry.py              # SchemaRegistry
│   │   └── definitions/             # Schema JSON files
│   │       ├── content.json
│   │       ├── breach.json
│   │       ├── entity.json
│   │       ├── domain.json
│   │       └── onion.json
│   │
│   └── metrics/                     # Observability
│       ├── __init__.py
│       ├── collector.py             # MetricsCollector
│       └── exporter.py              # Export to Prometheus/etc
│
├── pipelines/                       # NEW: Pipeline definitions (YAML)
│   ├── content.yaml                 # Web content pipeline
│   ├── breach.yaml                  # Breach data pipeline
│   ├── entity.yaml                  # Entity/node pipeline
│   └── onion.yaml                   # Dark web pipeline
│
├── jobs/                            # NEW: Job state storage
│   └── .gitkeep
│
├── lists/                           # NEW: Lookup lists for enrichment
│   ├── disposable_domains.txt
│   ├── fortune500_domains.txt
│   ├── government_domains.txt
│   └── suspicious_tlds.txt
│
└── (existing files...)
```

---

## Implementation Phases

### Phase 1: Foundation (5 days)
- [ ] Core models: DocumentEnvelope, Source, Job
- [ ] JobManager with ES persistence
- [ ] Checkpoint/resume logic
- [ ] Basic readers: File, JSONL, Parquet
- [ ] Schema registry with 5 schemas

### Phase 2: Pipeline Engine (5 days)
- [ ] YAML pipeline loader
- [ ] Stage base class and registry
- [ ] Stages: validator, transformer, deduplicator, router, indexer
- [ ] Pipeline execution engine

### Phase 3: Intelligence Features (5 days)
- [ ] Entity linking with 5 strategies
- [ ] Quality gates
- [ ] Enricher stage with list lookups
- [ ] Dead letter queue with retry

### Phase 4: MCP Integration (3 days)
- [ ] Add all 20 tools to mcp_server.py
- [ ] Source registry tools
- [ ] DLQ tools
- [ ] Pipeline tools

### Phase 5: Polish (2 days)
- [ ] Metrics collection
- [ ] Sample pipelines (content, breach, entity)
- [ ] Documentation
- [ ] Testing

**Total: ~20 days** (but can parallelize phases 2+3)

---

## Usage Examples

### Register a Breach Source

```
User: Register the LinkedIn 2021 breach dump

Claude: [Uses source_register]
{
    "name": "LinkedIn 2021 Breach",
    "type": "file",
    "config": {
        "path": "/data/breaches/linkedin_2021.jsonl",
        "format": "jsonl"
    },
    "pipeline": "breach",
    "metadata": {
        "breach_name": "linkedin",
        "breach_date": "2021-06-22",
        "record_count_estimate": 700000000
    }
}

Response: 
Source registered: src-linkedin-2021
Pipeline: breach_pipeline v2.1
Estimated records: 700M
Ready for sync.
```

### Start Indexing

```
User: Index the LinkedIn breach

Claude: [Uses source_sync]
{
    "source_id": "src-linkedin-2021",
    "options": {
        "batch_size": 500,
        "checkpoint_every": 10000
    }
}

Response:
Job started: job-2026010915432
Source: LinkedIn 2021 Breach
Pipeline: breach_pipeline v2.1
Target indices: breaches-linkedin, breaches-corporate (routed)
Estimated time: 4 hours
```

### Check DLQ

```
User: Any indexing failures?

Claude: [Uses dlq_stats]

Response:
Dead Letter Queue Summary:
├── Total entries: 1,247
├── Pending retry: 892
├── Manual review: 312
├── Abandoned: 43
│
├── By error type:
│   ├── validation: 756 (60.6%)
│   ├── transform: 234 (18.8%)
│   ├── timeout: 189 (15.2%)
│   └── other: 68 (5.5%)
│
├── Retry success rate: 73.2%
└── Oldest entry: 2 hours ago

Want me to show details or retry some?
```

### Inspect Entity Links

```
User: What did we link from the LinkedIn data?

Claude: [Uses index_stats with entity_links analysis]

Response:
Entity Links from LinkedIn Breach:
├── Total documents: 156,234,891
├── Documents with entity links: 134,567,234 (86.1%)
│
├── Links created:
│   ├── person entities: 98,234,567 (new: 12,456,789)
│   ├── company entities: 45,678 (new: 2,345)
│   └── domain entities: 234,567 (new: 45,678)
│
├── High-confidence links (>0.9): 89,234,567 (66.3%)
├── Medium-confidence (0.7-0.9): 34,567,890 (25.7%)
└── Low-confidence (<0.7): 10,764,777 (8.0%)
```

---

## Key Differences Summary

| Feature | V1 | V2 |
|---------|----|----|
| Document tracking | Basic dict | Full envelope with lineage |
| Sources | Ad-hoc paths | Registered with state |
| Pipelines | Python code | Declarative YAML |
| Entity linking | Manual | Automatic during indexing |
| Quality | None | Gates + scoring |
| Failures | Log & skip | DLQ + auto-retry |
| Routing | Single target | Rule-based multi-target |
| Dedup | Hash only | Multi-field + fuzzy + merge |
| Tools | 12 | 20 |

**V2 transforms the indexer from a data loader into an intelligence aggregation platform.**

---

## Open Questions

1. **Entity linking scope**: Link within single project or global?
   - Recommendation: Configurable per-pipeline

2. **DLQ retention**: How long to keep failed docs?
   - Recommendation: 30 days default, configurable

3. **Pipeline versioning**: How to handle schema migrations?
   - Recommendation: Version in pipeline name, reindex on breaking changes

4. **Metrics backend**: Prometheus, ES, or both?
   - Recommendation: ES index for simplicity, Prometheus export optional

---

## Next Steps

1. **Approve V2 plan**
2. **Clarify breach data format** (so I can write breach.yaml pipeline)
3. **Say "start"** when ready for implementation
