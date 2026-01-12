# CYMONIDES Architecture

**Three-tier Elasticsearch index system for investigation data.**

## Index Tiers

| Tier | Index Pattern | Purpose | Docs | Storage |
|------|---------------|---------|------|---------|
| **C-1** | `cymonides-1-{projectId}` | Per-project node graphs | 4,500+ | Varies |
| **C-2** | `cymonides-2` | Search result content corpus | 152,796 | 1.2GB |
| **C-3** | `cymonides-3` (alias) | Consolidated corpus | **527.8M** | 66GB |

## C-1: Project Graph Indices

**Pattern:** `cymonides-1-{projectId}`

Each project gets its own ES index containing:
- **Nodes**: Entities, events, topics, locations, documents
- **Embedded Edges**: Relationships stored inside node documents
- **Graph Layout**: X/Y positions for visualization

### Creating a Project
```python
from CLASSES.NARRATIVE.PROJECT import create_project, reset_project

# Creates cymonides-1-alpha-investigation
project = create_project(user_id=1, name="Alpha Investigation")

# Wipe and restart
reset_project(user_id=1, project_id="alpha-investigation")
```

### Node Schema
```json
{
  "id": "node-123",
  "className": "entity",
  "typeName": "person",
  "label": "John Smith",
  "projectId": "alpha-investigation",
  "embedded_edges": [
    {
      "edge_id": "e-456",
      "relationship": "officer_of",
      "direction": "outgoing",
      "target_id": "acme-corp",
      "target_label": "Acme Corp"
    }
  ]
}
```

---

## C-2: Content Corpus

**Index:** `cymonides-2` (single global index)

Stores scraped web content from brute searches:
- Full page text
- Extracted entities
- Query provenance (which searches found this URL)
- Engine provenance (which engines returned it)

### Automatic Ingestion

When brute search runs:
1. Results stored as C-1 `source` nodes
2. URLs automatically scraped (CC-First strategy)
3. Content indexed to `cymonides-2`
4. Entities extracted and linked back to C-1

### Fields
- `source_url`, `source_domain`, `source_type`
- `title`, `content`, `summary`
- `content_hash` (MD5 for dedup)
- `query_node_ids` (which C-1 queries found this)
- `extracted_entity_ids` (linked to C-1)

---

## C-3: Consolidated Corpus

**Alias:** `cymonides-3` → Points to multiple indices

This is the **528M+ document corpus** for corpus-first searching.

### Underlying Indices

| Index | Documents | Content |
|-------|-----------|---------|
| `atlas` | 155.5M | Domain authority, categories |
| `domains_unified` | 180.3M | WDC company enrichment |
| `companies_unified` | 24.6M | Company records |
| `persons_unified` | 15.2M | Person records |
| `cymonides_cc_domain_edges` | 139.4M | Domain hyperlinks |
| `top_domains` | 8.7M | Tranco-ranked domains |
| `cymonides_cc_domain_vertices` | 4.0M | Domain graph vertices |

### Creating/Updating Alias
```bash
curl -X POST "localhost:9200/_aliases" -H "Content-Type: application/json" -d '{
  "actions": [
    { "add": { "index": "atlas", "alias": "cymonides-3" }},
    { "add": { "index": "domains_unified", "alias": "cymonides-3" }},
    { "add": { "index": "companies_unified", "alias": "cymonides-3" }},
    { "add": { "index": "persons_unified", "alias": "cymonides-3" }}
  ]
}'
```

---

## CYMONIDES as Brute Engine

**Engine Code:** `CY`

Registered in `brute.py` ENGINE_CONFIG. Searches local ES corpus before external APIs.

### Usage in Brute
```python
# Include CY in engine list
python brute.py -q "BMW" -e "GO,BI,CY"

# CY-only (corpus search)
python brute.py -q "fintech startup" -e "CY"
```

### What CY Searches
1. **C-3** (corpus alias) - 528M domains/entities
2. **C-2** (content corpus) - 152K scraped pages
3. **PDF indices** - 1.75M corporate PDFs

---

## Operators

All from `operators.json` with `engine: "cymonides"`:

| Operator | Example | Function |
|----------|---------|----------|
| Definitional | `[German car manufacturer]` | Category search |
| Location | `de!` | German TLD/lang/geo |
| Domain TLD | `dom{fr}!` | French domains only |
| Language | `lang{de}!` | German content |
| Rank | `rank(<1000)` | Top 1K authority |
| Authority | `authority(high)` | High-authority sites |
| PDF | `pdf!` | PDF corpus only |
| Entity | `@p?` `@c?` `@e?` | Extract persons/companies/emails |

---

## File Locations

| Component | Path |
|-----------|------|
| Unified Search | `BACKEND/modules/CYMONIDES/cymonides_unified.py` |
| Brute Engine | `BACKEND/modules/brute/engines/cymonides.py` |
| C-1 Indexer | `BACKEND/modules/CYMONIDES/indexers/c1_node_indexer.py` |
| Project Manager | `CLASSES/NARRATIVE/PROJECT/` (sastre) |
| Index Registry | `BACKEND/modules/CYMONIDES/metadata/index_registry/` |

---

## Server Location

**sastre** (176.9.2.153)
- Elasticsearch 8.x on localhost:9200
- All indices stored in `/data`
