# Cymonides Index Storage & Metadata
**Location:** `/Users/attic/01. DRILL_SEARCH/drill-search-app/cymonides/`

## Structure

```
cymonides/
├── README.md (this file)
├── indices/
│   └── _elasticsearch_data -> /var/lib/docker/volumes/drill-search-app_elasticsearch_data/_data
│                               (symlink to actual Elasticsearch storage in OrbStack)
├── use-cases/                               (Use-case-centric documentation)
│   ├── README.md                            (Overview and cross-reference matrix)
│   ├── company-profiles/README.md           (Entity intelligence workflows)
│   ├── domains-list/README.md               (Domain lookup and network analysis)
│   ├── red-flags/README.md                  (Anomaly detection patterns)
│   ├── data-breaches/README.md              (Breach data and credential intelligence)
│   └── country-indexes/README.md            (Country-specific datasets - KZ, RU)
└── metadata/                                (Index-centric documentation)
    ├── cymonides-2/                         (Global text corpus - 532,630 docs)
    │   ├── metadata.json                    (Unified metadata: stats, mapping, settings, sample)
    │   ├── SOURCES_README.md                (Source breakdown and queries)
    │   └── sources/                         (Separate logs per source even when merged)
    │       ├── youtube/metadata.json        (487,600 docs - migrated from youtube_commons)
    │       ├── reports/metadata.json        (45,030 docs - uploaded PDFs/docs)
    │       ├── books/metadata.json          (Post-Soviet book collection)
    │       └── scraped_content/metadata.json (Future: crawled web pages)
    ├── cymonides-1-project-ge13t70tq8v0hw0h994z1v64/
    │   └── metadata.json
    ├── cymonides-1-project-test/
    │   └── metadata.json
    ├── cymonides-1-project-y5p1ujpf31j4vtil3fi80hx5/
    │   └── metadata.json
    ├── bangs/
    │   └── metadata.json
    ├── cc_domain_edges/
    │   └── metadata.json
    ├── cc_domain_vertices/
    │   └── metadata.json
    ├── source_enrichments/
    │   └── metadata.json
    ├── source_entities/
    │   └── metadata.json
    ├── nexus_breach_records/
    │   └── metadata.json
    ├── nexus_breaches/
    │   └── metadata.json
    └── kazaword_emails/
        └── metadata.json
```

## Metadata JSON Format

Each `metadata.json` contains:

```json
{
  "index_name": "cymonides-2",
  "stats": "health status index uuid pri rep docs.count ...",
  "mapping": {
    "cymonides-2": {
      "mappings": {
        "properties": { ... }
      }
    }
  },
  "settings": {
    "cymonides-2": {
      "settings": {
        "index": { ... }
      }
    }
  },
  "sample_document": {
    "hits": {
      "hits": [
        {
          "_source": { ... }
        }
      ]
    }
  }
}
```

## Actual Index Data

**Physical Location:** OrbStack Docker Volume
- Path: `/var/lib/docker/volumes/drill-search-app_elasticsearch_data/_data`
- Container: `drill-search-elasticsearch`
- Access: Via symlink at `cymonides/indices/_elasticsearch_data`

**Note:** The actual index shards, segments, and Lucene data live in the OrbStack Docker volume. This folder provides metadata and documentation about what's stored there.

## All Cymonides Indices (13 total)

| Index | Docs | Size | Purpose |
|-------|------|------|---------|
| cymonides-2 | 532,630 | 5.1GB | Text corpus (C-2) |
| cymonides-1-project-ge13t70tq8v0hw0h994z1v64 | 1,722 | 23MB | Entity storage (C-1) |
| cymonides-1-project-test | 7 | 26KB | Test instance |
| cymonides-1-project-y5p1ujpf31j4vtil3fi80hx5 | 1 | 8KB | Entity storage (C-1) |
| bangs | 20,389 | 5.2MB | Search shortcuts |
| cc_domain_edges | 435,770,000 | 16.5GB | CC link graph edges |
| cc_domain_vertices | 100,662,487 | 7.5GB | CC link graph vertices |
| source_enrichments | 5 | 34KB | Enrichment metadata |
| source_entities | 8 | 47KB | Entity source registry |
| nexus_breach_records | 197,668 | 90.3MB | Breach data |
| nexus_breaches | 6 | 21.9KB | Breach metadata |
| kazaword_emails | 92,416 | 225.7MB | KZ/RU emails |

**Total:** 537,277,333 documents, ~29.5GB
**Note:** Removed cymonides_unified (1 doc, 49KB) - consolidated into other indices

## How to Use

### View index metadata:
```bash
cat cymonides/metadata/cymonides-2/metadata.json | jq .
```

### Extract just the mapping:
```bash
jq '.mapping."cymonides-2".mappings.properties' cymonides/metadata/cymonides-2/metadata.json
```

### Get field list:
```bash
jq '.mapping."cymonides-2".mappings.properties | keys' cymonides/metadata/cymonides-2/metadata.json
```

### View sample document:
```bash
jq '.sample_document.hits.hits[0]._source' cymonides/metadata/cymonides-2/metadata.json
```

### Query by source type:
```bash
# See all sources in cymonides-2
cat cymonides/metadata/cymonides-2/SOURCES_README.md

# Query YouTube content only
curl "http://localhost:9200/cymonides-2/_search?q=source_type:youtube&size=10"

# Query reports only
curl "http://localhost:9200/cymonides-2/_search?q=source_type:report&size=10"
```

### Access actual data (requires Docker/root):
```bash
ls -la cymonides/indices/_elasticsearch_data/nodes/0/indices/
```

## Regenerate Metadata

To update all metadata files:
```bash
cd /Users/attic/01. DRILL_SEARCH/drill-search-app
./scripts/regenerate_cymonides_metadata.sh  # (if script exists)
```

Or manually:
```bash
curl -s "http://localhost:9200/cymonides-2/_mapping" > mapping.json
curl -s "http://localhost:9200/cymonides-2/_settings" > settings.json
curl -s "http://localhost:9200/cymonides-2/_search?size=1" > sample.json
# Combine into metadata.json
```

## Use Cases

See **`use-cases/`** folder for workflow-oriented documentation:
- **`company-profiles/`** - Entity intelligence and enrichment workflows
- **`domains-list/`** - Domain lookup, ranking, and network analysis
- **`red-flags/`** - Anomaly detection and risk indicators

These folders document **how indices work together** for specific investigative tasks, with example queries and data flows.

## Related Documentation

- **Master Registry:** `data/CYMONIDES_INDEX_REGISTRY.md`
- **LinkLater Indices:** `python-backend/modules/linklater/LINKLATER_ELASTICSEARCH_INDEX_MAP.md`
- **Use Case Workflows:** `use-cases/README.md`
- **Elasticsearch:** http://localhost:9200
