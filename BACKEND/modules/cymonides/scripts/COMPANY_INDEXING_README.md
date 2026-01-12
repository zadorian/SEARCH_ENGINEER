# Company Dataset Indexing for Drill Search

## Overview

This guide explains how to index large company datasets (German CR, UK CCOD, etc.) into Drill Search's Elasticsearch instance.

## Architecture

Drill Search uses a **dual storage system**:

1. **PostgreSQL (Primary)** - Graph database with Drizzle ORM
   - Tables: `nodes`, `edges`, `nodeTypes`, `nodeClasses`
   - Full relational data with JSONB metadata

2. **Elasticsearch (Search Index)** - Fast search and filtering
   - Index: `search_nodes`
   - Powers the Grid/Graph frontend queries
   - Real-time search across all indexed entities

## Schema Mapping

The Elasticsearch `search_nodes` index uses this structure:

```json
{
  "id": "string (unique identifier)",
  "label": "string (company/entity name)",
  "url": "string (canonical URL or slug)",
  "class": "keyword (entity, property, document, etc.)",
  "type": "keyword (company, person, uk_property, etc.)",
  "projectId": "keyword (project identifier)",
  "metadata": "object (flexible JSONB - all dataset-specific fields)",
  "timestamp": "date (ISO 8601)",
  "query": "string (source query)",
  "content": "text (searchable full-text content)"
}
```

### Company Data Mapping

**German Company Register (Handelsregister)**:

- `label`: Company name
- `type`: "company"
- `class`: "entity"
- `projectId`: "german_cr"
- `metadata`: All company-specific fields (officers, jurisdiction, status, etc.)

**UK CCOD (Land Registry)**:

- `label`: Proprietor name (company/owner)
- `type`: "uk_property"
- `class`: "property"
- `projectId`: "ccod_2025"
- `metadata`: All property fields (title number, address, tenure, etc.)

## Prerequisites

1. **Elasticsearch Running**:

   ```bash
   # Check if Elasticsearch is running
   curl http://localhost:9200

   # Start Elasticsearch (if using Docker)
   docker run -d -p 9200:9200 -e "discovery.type=single-node" elasticsearch:8.11.0

   # Or using Homebrew
   brew services start elasticsearch
   ```

2. **Environment Variables**:

   ```bash
   # In .env file
   ELASTICSEARCH_URL=http://localhost:9200
   ```

3. **Python Dependencies**:
   ```bash
   pip install aiohttp psycopg2-binary python-dotenv
   ```

## Usage

### 1. Test with Limited Data (Recommended First)

Index only 10,000 records to test:

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/search_engine_core/scripts

# Test German companies (10k records)
python3 index_companies_bulk.py --dataset german --limit 10000

# Test CCOD properties (10k records)
python3 index_companies_bulk.py --dataset ccod --limit 10000
```

### 2. Full Dataset Indexing

**German Company Register (~5 million companies)**:

```bash
python3 index_companies_bulk.py --dataset german
```

**UK CCOD (full dataset)**:

```bash
python3 index_companies_bulk.py --dataset ccod
```

**All datasets**:

```bash
python3 index_companies_bulk.py --dataset all
```

### 3. Custom Batch Size

For faster indexing (if your Elasticsearch can handle it):

```bash
python3 index_companies_bulk.py --dataset german --batch-size 5000
```

## Querying Indexed Data

### Via FastAPI Backend

```bash
# Search for a company
curl -X POST http://localhost:8000/elastic/nodes/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Volkswagen",
    "filters": {"type": "company"},
    "limit": 50
  }'

# Search UK properties
curl -X POST http://localhost:8000/elastic/nodes/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Rossetti House",
    "filters": {"type": "uk_property"},
    "limit": 100
  }'
```

### Direct Elasticsearch Query

```bash
# Search German companies
curl -X POST http://localhost:9200/search_nodes/_search \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "bool": {
        "must": [
          {"match": {"content": "Volkswagen"}},
          {"term": {"projectId": "german_cr"}}
        ]
      }
    },
    "size": 50
  }'
```

### From the Frontend Grid

Once indexed, the data will automatically appear in the Drill Search Grid/Graph UI:

1. Open the frontend at `http://localhost:5173` (or your configured port)
2. Use the search bar to find companies
3. Filter by `type: company` or `projectId: german_cr`
4. All metadata fields are searchable

## Performance

**Expected Indexing Speed**:

- German CR (~5M records): ~15-30 minutes (batch_size=1000)
- CCOD (full dataset): ~10-20 minutes (batch_size=1000)

**Index Size Estimates**:

- German CR: ~3-5 GB
- CCOD: ~1-2 GB

## Monitoring

Check index status:

```bash
# Get index stats
curl http://localhost:9200/search_nodes/_stats

# Count documents
curl http://localhost:9200/search_nodes/_count

# View index mapping
curl http://localhost:9200/search_nodes/_mapping
```

## Troubleshooting

### Elasticsearch Not Running

```bash
# Check status
curl http://localhost:9200

# If not running, start it
brew services start elasticsearch
# OR
docker start elasticsearch
```

### Out of Memory Errors

Reduce batch size:

```bash
python3 index_companies_bulk.py --dataset german --batch-size 500
```

### Connection Refused

Check `ELASTICSEARCH_URL` in environment:

```bash
echo $ELASTICSEARCH_URL
# Should be: http://localhost:9200
```

## Indexing with Full Graph Relationships

For German Company Registry data with complete graph structure (companies, officers, addresses, locations, and all edges):

```bash
# Test with 50 companies
python3 index_companies_with_edges.py --limit 50

# Full dataset (~5 million companies)
python3 index_companies_with_edges.py
```

This script creates:

- **Company nodes** with full German CR metadata
- **Person nodes** for all officers/directors
- **Address nodes** for registered addresses
- **Location nodes** for officer cities
- **Edges**:
  - `director_of` (person → company)
  - `resides_at` (person → location)
  - `has_address` (company → address)

All metadata is preserved in the `metadata` JSONB field.

## Next Steps

1. **Add More Datasets**: Create similar scripts for:
   - UK CCOD with property ownership edges
   - AshleyMadison breach data
   - Other corporate registries

2. **Verify Graph Structure**: Query relationships in PostgreSQL or via the Grid/Graph UI

3. **Create Project Views**: Use `projectId: "german_cr"` to filter in the UI

## File Locations

- **Indexing Script**: `/Users/attic/DRILL_SEARCH/drill-search-app/python-backend/search_engine_core/scripts/index_companies_bulk.py`
- **Elasticsearch Service**: `/Users/attic/DRILL_SEARCH/drill-search-app/python-backend/search_engine_core/services/elastic_service.py`
- **API Routes**: `/Users/attic/DRILL_SEARCH/drill-search-app/python-backend/api/elastic_routes.py`
- **Sync Script**: `/Users/attic/DRILL_SEARCH/drill-search-app/python-backend/search_engine_core/scripts/sync_sql_to_elastic.py`

## Data Sources

- **German CR**: `/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02.backup/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/CORPORATE-REGISTRY/DE/de_CR.jsonl`
- **UK CCOD**: `/Users/attic/Dropbox/My Mac (Spyborgs-MacBook-Pro.local)/Desktop/data_cr/CCOD_FULL_2025_08.csv`
