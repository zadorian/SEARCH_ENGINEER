# WDC Schema.org Integration

## Architecture: Single Extraction System

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         UNIFIED EXTRACTION PIPELINE                         │
│                                                                            │
│  WDC Data (Already Extracted)     HTML Content (Needs Extraction)         │
│        │                                    │                              │
│        ▼                                    ▼                              │
│  ┌─────────────────┐              ┌─────────────────────────────────┐     │
│  │ CYMONIDES       │              │ LINKLATER extraction/           │     │
│  │ scripts/wdc/    │              │                                 │     │
│  │                 │              │ Layer 1: Schema.org JSON-LD     │     │
│  │ Materialization │              │ Layer 2: Backends (Gemini/GPT/  │     │
│  │ only - no       │              │          GLiNER/Regex)          │     │
│  │ extraction      │              │ Layer 3: Merge & Dedupe         │     │
│  │                 │              │ Layer 4: Haiku relationships    │     │
│  └────────┬────────┘              └────────────────┬────────────────┘     │
│           │                                        │                       │
│           ▼                                        ▼                       │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                      CYMONIDES-1                                 │      │
│  │                    Entity Graph                                  │      │
│  │                                                                  │      │
│  │  Deterministic IDs: hash(value + type)                          │      │
│  │  Edges: officer_of, shareholder_of, family_of, etc.             │      │
│  └─────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────┘
```

## Key Principles

### 1. LINKLATER Owns Extraction

All entity extraction from raw content goes through `LINKLATER/extraction/`:

```python
from LINKLATER.extraction import extract_entities

# Full extraction pipeline with all backends
result = await extract_entities(
    html="<html>...",
    url="https://example.com",
    backend="auto",  # Gemini, GPT, GLiNER, or Regex
    extract_relationships=True,  # Layer 4: Haiku for edges
)
```

Available backends:
- **Gemini 2.0 Flash**: Default cloud API
- **GPT-5-nano**: OpenAI alternative
- **GLiNER**: Local model
- **Regex**: Fallback patterns
- **Haiku 4.5**: Relationship extraction (Layer 4)

### 2. WDC Data is Already Extracted

WDC Schema.org data is machine-readable markup that websites have already published.
It doesn't need extraction - it needs **materialization** (conversion to C-1 nodes).

```python
from CYMONIDES.scripts.wdc import WDCMaterializer

# Materialize WDC search results to C-1
materializer = WDCMaterializer()
await materializer.connect()

result = await materializer.materialize_batch(
    wdc_entities=[...],
    project_id="proj_123",
    discovery_query="[restaurant] : geo:de",
)
```

### 3. CYMONIDES Owns Materialization

The `CYMONIDES/scripts/wdc/` module handles converting WDC data to C-1 nodes:

- Maps Schema.org types to Cymonides entity types
- Creates deterministic node IDs
- Tracks discovery provenance
- Respects relevance thresholds

### 4. DEFINITIONAL Owns LOCATION (WHERE)

`DEFINITIONAL` determines WHERE to search using:
- WDC domain profiles (entity type + language + geo)
- TLD patterns
- Site category filters

It does NOT do extraction - it delegates to LINKLATER when content analysis is needed.

## Data Flow

```
User Query: [restaurant] : geo:de lang:de
         │
         ▼
┌─────────────────┐
│  DEFINITIONAL   │
│  LOCATION Methods   │ ─── "Find German restaurant domains"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  WDC Query      │
│  Service        │ ─── Returns domain profiles with entities
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CYMONIDES WDC  │
│  Materializer   │ ─── Converts to C-1 nodes
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  (Optional)     │
│  LINKLATER      │ ─── Scrapes pages, extracts MORE entities
│  Extraction     │     (if discovery_mode enabled)
└─────────────────┘
```

## Usage Examples

### Search and Materialize WDC Entities

```python
from DEFINITIONAL.wdc_query import search_and_materialize

# Search WDC, auto-materialize high-relevance results
result = await search_and_materialize(
    entity_type="Restaurant",
    project_id="german_restaurants",
    discovery_query="[restaurant] : geo:de",
    geo="de",
    relevance_threshold=0.7,
)

print(f"Found {result['total']} entities")
print(f"Materialized {result['materialized_count']} to C-1")
```

### Extract from Live Pages (Use LINKLATER)

```python
from LINKLATER.extraction import extract_entities

# Scrape and extract
html = await fetch_page("https://berliner-kebab.de/team")
entities = await extract_entities(
    html=html,
    url="https://berliner-kebab.de/team",
    extract_relationships=True,  # Find person→company edges
)

# Then materialize to C-1
from LINKLATER.cymonides_bridge import CymonidesIndexer
indexer = CymonidesIndexer()
await indexer.index_entities(entities, source_url=url, project_id="proj_123")
```

## File Locations

| Component | Location | Purpose |
|-----------|----------|---------|
| WDC Materialization | `CYMONIDES/scripts/wdc/` | Convert WDC→C-1 nodes |
| Entity Extraction | `LINKLATER/extraction/` | Extract from HTML |
| Extraction Backends | `LINKLATER/extraction/backends/` | Gemini, GPT, GLiNER, Haiku |
| LOCATION Methods | `DEFINITIONAL/loci_methods.py` | WHERE to search |
| WDC Queries | `DEFINITIONAL/wdc_query.py` | Query WDC profiles |
| C-1 Indexing | `LINKLATER/cymonides_bridge/` | Index to C-1 graph |
