# Domains List Use Case

**Purpose:** Domain intelligence, lookup, ranking, and network analysis

## Indices Used

> **📊 See [DATASETS.md](DATASETS.md) for complete inventory: CC graph (536M+ docs), Majestic API, Tranco, Umbrella, and more**

### Domain Master List
- **`cymonides_cc_domain_vertices`** (100M+ domains)
  - Location: `../metadata/cymonides_cc_domain_vertices/`
  - Purpose: Every domain in Common Crawl with vertex_id
  - Fields: `domain`, `reversed_domain`, `vertex_id`, `count`
  - Size: 7.5GB, 100,662,487 docs
  - Used for: Domain existence checks, ID lookups, TLD grouping

### Link Graph
- **`cymonides_cc_domain_edges`** (435M+ edges)
  - Location: `../metadata/cymonides_cc_domain_edges/`
  - Purpose: Who links to/from whom
  - Fields: `source_domain`, `target_domain`, `source_vertex_id`, `target_vertex_id`, `count`
  - Size: 16.5GB, 435,770,000 docs
  - Used for: Backlink analysis, authority scoring, network mapping

### Domain Enrichment
- **`cymonides_source_enrichments`**
  - Location: `../metadata/cymonides_source_enrichments/`
  - Purpose: Per-domain metadata from DRILL operations
  - Fields: `domain`, `cc_coverage`, `search_pages`, `api_endpoints`, `entity_pages`, `outlinks`
  - Used for: Site structure, crawlability, technical footprint

### Search Shortcuts
- **`cymonides_bangs`** (20K+ shortcuts)
  - Location: `../metadata/cymonides_bangs/`
  - Purpose: DuckDuckGo-style !bang shortcuts for direct site search
  - Fields: `bang`, `domain`, `category`, `search_url`
  - Used for: Quick site-specific searches

### Entity Extraction (Domain Source)
- **`cymonides_source_entities`**
  - Location: `../metadata/cymonides_source_entities/`
  - Purpose: Entities extracted from domain pages
  - Fields: `domain`, `name`, `entity_type`, `page_url`, `snippet`
  - Used for: "What entities are mentioned on this domain?"

### Text Corpus (Domain-Filtered)
- **`cymonides-2`** (filtered by source_domain)
  - Location: `../metadata/cymonides-2/`
  - Purpose: Full-text content indexed from domains
  - Query: `source_domain:"example.com"`
  - Used for: Content analysis, keyword extraction

## Typical Workflows

### 1. Domain Lookup
```bash
# Check if domain exists in CC
curl "http://localhost:9200/cymonides_cc_domain_vertices/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "domain": "example.com" } }
}'
```

### 2. Backlink Analysis
```bash
# Who links TO this domain?
curl "http://localhost:9200/cymonides_cc_domain_edges/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "target_domain": "example.com" } },
  "size": 1000,
  "sort": [{ "count": "desc" }]
}'
```

### 3. Outlink Analysis
```bash
# Who does this domain link TO?
curl "http://localhost:9200/cymonides_cc_domain_edges/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { "term": { "source_domain": "example.com" } },
  "size": 1000
}'
```

### 4. Domain Enrichment Check
```bash
# Get DRILL enrichment data
curl "http://localhost:9200/cymonides_source_enrichments/_doc/{source_id}"
```

### 5. TLD Analysis
```bash
# Find all .gov domains
curl "http://localhost:9200/cymonides_cc_domain_vertices/_search" \
  -H 'Content-Type: application/json' -d '{
  "query": { 
    "prefix": { "reversed_domain": "gov." }
  },
  "size": 1000
}'
```

## Data Flow

```
Domain Input → Vertex Lookup (cymonides_cc_domain_vertices)
                             ↓
           Get vertex_id → Edge Lookup (cymonides_cc_domain_edges)
                             ↓
         Backlinks/Outlinks → Rank by Count
                             ↓
     DRILL Enrichment → cymonides_source_enrichments
                             ↓
  Entity Extraction → cymonides_source_entities
                             ↓
Content Indexing → cymonides-2 (filtered by source_domain)
```

## Related Modules

- **LinkLater** (`python-backend/modules/linklater/`)
  - Node.js service: `server/services/linklater.ts` (uses ES indices)
  - Python module: Uses file-based CC access via AllDom
  
- **AllDom** (`python-backend/modules/alldom/`)
  - Domain intelligence and ranking
  - File-based CC graph access (421M edges)
  
- **DRILL** (`python-backend/modules/linklater/drill/`)
  - Domain crawling and enrichment
  - Populates `cymonides_source_enrichments`

## File Locations Referenced

### ES Indices (documented here)
- `cymonides_cc_domain_vertices/metadata.json`
- `cymonides_cc_domain_edges/metadata.json`
- `cymonides_source_enrichments/metadata.json`
- `cymonides_bangs/metadata.json`

### File-Based CC Data (Python)
- `/Users/attic/Library/CloudStorage/GoogleDrive-tyrion02@gmail.com/My Drive/Datasets/cc_webgraph_host_edges_indexed_421M/`
- Used by: `python-backend/modules/alldom/`

## Cross-Reference

This use case overlaps with:
- **`company-profiles`** (company domain lookups)
- **`red-flags`** (suspicious domain patterns, link networks)

## Performance Notes

- **Vertex lookups**: Fast (keyword match on 100M docs)
- **Edge lookups**: Can be slow (435M docs, use filters)
- **TLD queries**: Use `reversed_domain` prefix for efficiency
- **Backlink counts**: Pre-aggregated in `count` field
