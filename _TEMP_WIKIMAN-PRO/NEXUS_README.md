# NEXUS - Named Entity eXtraction Unified System

## 🌐 Overview

NEXUS is a unified knowledge graph database system that aggregates entities from multiple sources into a single, queryable graph structure. It combines compliance data, company profiles, video transcripts, and more into an interconnected knowledge base.

## 🗄️ Core Databases

### 1. **nexus_graph.db** (Main Graph Database)
**Location:** `/Volumes/My Book/NEXUS/databases/nexus_graph.db`
**Size:** Growing (currently ~50MB with test data)
**Purpose:** Central graph database with all entities and relationships

**Node Types:**
- `person` - Biographical profiles
- `company` - Business entities
- `organization` - Non-commercial organizations (KGB, UN, etc.)
- `red_flag` - Compliance/risk flags
- `email` - Email addresses
- `phone` - Phone numbers
- `username` - Online identities
- `password` - Credential data
- `vehicle` - Cars, boats, planes
- `intellectual_property` - Patents, trademarks
- `art` - Artworks, cultural artifacts
- `url` - Web sources

**Relationship Types:**
- `flagged_with` - Entity has compliance flag
- `employed_by` - Person works for company
- `owns` - Ownership relationships
- `married_to` - Family relationships
- `director_of` - Leadership positions
- Plus 50+ other relationship types

### 2. **company_profiles.db** (Company Index)
**Location:** `/Volumes/My Book/NEXUS/databases/company_profiles.db`
**Size:** 11 GB
**Records:** 14.4M+ companies
**Sources:** fr3on, LinkedIn, BigPicture, CompanyWeb

### 3. **youtube_commons.db** (Transcript Index)
**Location:** `/Volumes/My Book/NEXUS/databases/youtube_commons.db`
**Size:** 35 GB
**Records:** 5M+ video transcripts
**Purpose:** Full-text searchable educational content

## 📊 Data Sources

| Source | Type | Records | Status |
|--------|------|---------|--------|
| **World-Check** | Compliance | 5.4M | ✅ Ready (10 test records ingested) |
| **fr3on** | Companies | 14.4M | ✅ Integrated |
| **LinkedIn** | Companies | 1M | 🔄 Processing |
| **YouTube Commons** | Transcripts | 5M+ | 🔄 Processing |
| **BigPicture** | Companies | 2-3M | ⏳ Pending |
| **CompanyWeb** | Companies | 500K | ⏳ Pending |

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│            INPUT SOURCES                │
│  World-Check │ Companies │ Transcripts  │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         INGESTION LAYER                 │
│  Template-based extraction with AI      │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│           NEXUS GRAPH                   │
│  Nodes (Entities) + Edges (Relations)   │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         ACCESS LAYER                    │
│  WIKIMAN │ Search-Engineer │ Graph UI   │
└─────────────────────────────────────────┘
```

## 🚀 Quick Start

### Query the Graph Database
```python
import sqlite3

conn = sqlite3.connect('/Volumes/My Book/NEXUS/databases/nexus_graph.db')
cursor = conn.cursor()

# Find all people with financial crime flags
cursor.execute("""
    SELECT n1.name, n2.name, n2.value
    FROM nodes n1
    JOIN edges e ON n1.node_id = e.source_node_id
    JOIN nodes n2 ON e.target_node_id = n2.node_id
    WHERE n1.node_type = 'person'
    AND n2.node_type = 'red_flag'
    AND n2.value LIKE '%FINANCIAL%'
""")
```

### Search Companies
```python
# Full-text search in company profiles
cursor.execute("""
    SELECT company_name, website, description
    FROM company_profiles_fts
    WHERE company_profiles_fts MATCH 'technology'
    LIMIT 10
""")
```

### Process World-Check Data
```bash
cd "/Volumes/My Book/NEXUS/ingestion/worldcheck"
python3 ingest_worldcheck_unified.py
```

The ingestion script offers:
- **Option 1**: Test with 10 records (quick verification)
- **Option 2**: Test with 100 records
- **Option 3**: Test with 1,000 records
- **Option 4**: Process ALL 5.4M records (takes hours)
- **Option 5**: Verify existing integration

Test results (10 records):
- 10 PERSON entities created
- 5 RED_FLAG nodes created
- 5 RED_FLAGS reused (deduplication working)
- 10 'flagged_with' edges created

## 📋 Entity Templates

All entities follow structured JSON templates stored in `/NEXUS/schemas/entity_templates/`:

- **person_entity_template.json** - Full biographical structure
- **company_entity_template.json** - Business entity fields
- **red_flag_entity_template.json** - Compliance flag structure
- **organization_entity_template.json** - Non-commercial orgs

Each template ensures consistent data structure across all sources.

## 🔗 Key Features

### Deduplication
- Companies deduplicated by domain
- People deduplicated by name + DOB
- RED_FLAGS deduplicated by category + keyword
- Prevents redundant data while maintaining relationships

### Template Preservation
- Full JSON templates stored in `template_data` field
- Original source data preserved in `raw_data` field
- Zero data loss during transformation

### Universal Compatibility
- Works with WIKIMAN-PRO graph interface
- Compatible with Search-Engineer.02 templates
- Standard SQLite format readable by any tool

## 📈 Statistics

### Current Database Status (Oct 26, 2025)
- **Graph Database Entities:** 15 nodes (10 persons, 5 red_flags)
- **Graph Relationships:** 10 edges (flagged_with)
- **Company Profiles:** 14.4M+ (external database, symlinked)
- **YouTube Transcripts:** 5M+ (external database, symlinked)
- **RED_FLAGS:** 5 unique flags (deduped from 10 test records)
- **Data Sources:** 2 integrated (World-Check test, fr3on), 4 processing/pending

### Performance
- Query response: <100ms for indexed searches
- Ingestion rate: 50-100 records/second
- Deduplication: Real-time during ingestion

## 🛠️ Maintenance

### Backup Command
```bash
rsync -av /Volumes/My\ Book/NEXUS/ /backup/location/NEXUS/
```

### Verify Integrity
```bash
sqlite3 /Volumes/My\ Book/NEXUS/databases/nexus_graph.db "PRAGMA integrity_check"
```

### Check Statistics
```bash
# Node counts by type
sqlite3 /Volumes/My\ Book/NEXUS/databases/nexus_graph.db \
  "SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type"

# Relationship counts
sqlite3 /Volumes/My\ Book/NEXUS/databases/nexus_graph.db \
  "SELECT relationship_type, COUNT(*) FROM edges GROUP BY relationship_type"
```

## 📚 Documentation

- **[SCHEMAS.md](./docs/SCHEMAS.md)** - Database schemas and field definitions
- **[API.md](./docs/API.md)** - Query API documentation
- **[SOURCES.md](./docs/SOURCES.md)** - Data source integration guides
- **[WORLDCHECK_FIELD_MAPPING.md](./docs/WORLDCHECK_FIELD_MAPPING.md)** - World-Check specific mappings

## 🔐 Security Notes

- External drive must be mounted at `/Volumes/My Book/`
- Sensitive data (passwords, PII) stored with appropriate flags
- Compliance data requires authorized access only
- Regular backups recommended

## 🎯 Future Roadmap

- [ ] Vector embeddings for semantic search
- [ ] GraphQL API endpoint
- [ ] Real-time streaming ingestion
- [ ] Automated source updates
- [ ] Cross-entity resolution ML
- [ ] Blockchain verification layer

---

**NEXUS** - Your unified knowledge graph for entity intelligence

*Last Updated: October 26, 2025*