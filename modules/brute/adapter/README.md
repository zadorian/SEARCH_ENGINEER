# CyMonides → Drill Search Integration

**CyMonides can now ingest/index anything into Drill Search's Elasticsearch with the same vector embeddings.**

## ✅ What's Set Up

### Core Files

- `drill_search_adapter.py` - **Main adapter** to index into `search_nodes` with embeddings
- `elasticsearch_backend.py` - Original CyMonides ES backend (reference)
- `vector_embedder.py` - Vector embedding utilities
- `unified_backend.py` - Backend abstraction layer

### Integration Features

✅ Uses **same Elasticsearch index**: `search_nodes` and `search_edges`
✅ Uses **same embedding model**: `all-MiniLM-L6-v2` (384 dimensions)
✅ Follows **Drill Search node schema**: `id`, `label`, `className`, `type`, `metadata`, etc.
✅ Generates **same vectors**: `description_vector` + `content_vector`
✅ **Semantic search** compatible with Drill Search's kNN queries
✅ **Hybrid search**: BM25 keyword + vector similarity
✅ **Schema validation**: Validates all 69 edge types from `edge_types.json`
✅ **FTM conversion**: Converts to/from Follow The Money schemas
✅ **Metadata validation**: Checks required edge metadata fields

---

## 🚀 Usage

### Python API

```python
from server.services.cymonides.drill_search_adapter import DrillSearchAdapter

# Initialize adapter
adapter = DrillSearchAdapter()

# Index a document with automatic embeddings
doc = adapter.index_node(
    label="Panama Papers Analysis",
    content="Investigation into offshore entities revealed in Panama Papers leak",
    className="source",
    typeName="investigation_note",
    url="https://example.com/panama-papers",
    metadata={
        "jurisdiction": "Panama",
        "keyphrases": ["offshore", "Mossack Fonseca", "beneficial ownership"],
        "ftm_origin": True,
        "dataset_source": "icij_panama_papers"
    }
)

# Index an edge (relationship)
edge = adapter.index_edge(
    from_node="person_123",
    to_node="company_456",
    relation="beneficial_owner",
    metadata={"confidence": 0.95}
)

# Semantic search
results = adapter.search_semantic(
    query="offshore shell companies tax evasion",
    k=10,
    vector_field="description_vector"
)

# Hybrid search (keyword + semantic)
results = adapter.search_hybrid(
    query="money laundering networks",
    k=20,
    keyword_weight=0.5  # 50% keyword, 50% semantic
)

# Keyword-only search
results = adapter.search_keyword(query="BVI companies", k=10)
```

### Quick Functions

```python
from server.services.cymonides.drill_search_adapter import index_document, search

# Quick index
doc = index_document(
    content="Offshore company setup guide",
    label="BVI Formation Guide",
    className="source"
)

# Quick search
results = search("beneficial ownership", k=5, mode="semantic")
```

---

## 📊 Node Schema

CyMonides indexes follow the **exact same schema** as Drill Search:

```python
{
    "id": "cymonides_abc123",
    "label": "Document Title",
    "content": "Full text content...",
    "className": "source",  # source, subject, object, location, narrative
    "typeName": "webpage",  # webpage, person, company, investigation_note, etc.
    "url": "https://...",
    "metadata": {
        "jurisdiction": "Panama",
        "keyphrases": ["offshore", "tax haven"],
        "ftm_origin": True,
        "dataset_source": "opensanctions"
    },
    "embedding_status": "embedded",
    "embedding_updated": "2025-01-23T02:00:00Z",
    "description_vector": [0.123, ...],  # 384-dim
    "content_vector": [0.456, ...],       # 384-dim
    "timestamp": "2025-01-23T01:00:00Z",
    "createdAt": "2025-01-23T01:00:00Z",
    "updatedAt": "2025-01-23T01:00:00Z"
}
```

---

## 🔍 Search Modes

### 1. Semantic Search (Pure Vector)

Best for: Finding conceptually similar content

```python
results = adapter.search_semantic(
    query="offshore tax evasion schemes",
    k=10,
    vector_field="description_vector"
)
```

### 2. Hybrid Search (Keyword + Vector)

Best for: Balanced precision and recall

```python
results = adapter.search_hybrid(
    query="Panama Papers Mossack Fonseca",
    k=20,
    keyword_weight=0.5  # Balance between keyword and semantic
)
```

### 3. Keyword Search (BM25 Only)

Best for: Exact term matching

```python
results = adapter.search_keyword(
    query="British Virgin Islands",
    k=10
)
```

---

## 🎯 Use Cases

### 1. Index Web Scraping Results

```python
# After scraping a website
adapter.index_node(
    label=page_title,
    content=scraped_text,
    className="source",
    typeName="webpage",
    url=page_url,
    metadata={
        "scrape_date": datetime.now().isoformat(),
        "domain": urlparse(page_url).netloc
    }
)
```

### 2. Index Investigation Notes

```python
adapter.index_node(
    label="Target Company Analysis",
    content=investigation_text,
    className="narrative",
    typeName="investigation_note",
    metadata={
        "investigator": "analyst_01",
        "case_id": "case_123",
        "tags": ["money-laundering", "offshore"]
    }
)
```

### 3. Index Entity Data (FTM-compatible)

```python
adapter.index_node(
    label="ACME Corporation Ltd",
    content="Offshore company registered in BVI",
    className="subject",
    typeName="company",
    metadata={
        "ftm_origin": True,
        "dataset_source": "opencorporates",
        "jurisdiction": "British Virgin Islands",
        "registration_number": "123456"
    }
)
```

### 4. Build Knowledge Graphs with Validation

```python
# Create entity nodes
company_id = adapter.index_node(
    label="ACME Corp",
    className="subject",
    typeName="company"
)['id']

person_id = adapter.index_node(
    label="John Doe",
    className="subject",
    typeName="person"
)['id']

# Link them with validation
adapter.index_edge(
    from_node=person_id,
    to_node=company_id,
    relation="beneficial_owner_of",
    source_type="person",
    target_type="company",
    metadata={
        "share_pct": 75.5,
        "natures_of_control": ["ownership-of-shares-75-to-100-percent"]
    }
)
# ✅ Validates against edge_types.json
# ⚠️  Warns if required metadata fields are missing
```

### 5. FTM (Follow The Money) Integration

```python
# Convert Drill Search node to FTM schema
node = {
    'id': 'person_123',
    'label': 'John Doe',
    'className': 'subject',
    'typeName': 'person',
    'metadata': {
        'birth_date': '1980-01-01',
        'nationality': 'US'
    }
}

ftm_entity = adapter.to_ftm(node)
# Returns:
# {
#   'schema': 'Person',
#   'id': 'person_123',
#   'properties': {
#     'name': 'John Doe',
#     'birthDate': '1980-01-01',
#     'nationality': 'US'
#   }
# }

# Convert FTM entity back to Drill Search
drill_node = adapter.from_ftm(ftm_entity)
# Automatically adds ftm_origin: True to metadata
```

### 6. Discover Valid Edge Types

```python
# List all valid edges for a person
valid_edges = adapter.list_valid_edges_for_type('person', direction='outgoing')
# Returns all person edges: has_phone, has_email, employed_by, director_of, owns, etc.

# Get metadata schema for a specific edge type
schema = adapter.get_edge_metadata_schema('beneficial_owner_of')
# Returns required/optional fields and custom field definitions
```

---

## 🔧 Configuration

Set environment variables (already configured in `.env`):

```bash
# Elasticsearch connection
ELASTICSEARCH_URL=http://localhost:9200
ELASTIC_NODES_INDEX=search_nodes
ELASTIC_EDGES_INDEX=search_edges

# Enable embeddings
ENABLE_EMBEDDINGS=true
```

---

## 🧪 Testing

```bash
# Test the adapter directly
cd /Users/attic/DRILL_SEARCH/drill-search-app
ENABLE_EMBEDDINGS=true ELASTICSEARCH_URL=http://localhost:9200 python3 -m server.services.cymonides.drill_search_adapter
```

Expected output:

```
✅ Embedding model loaded
✅ Indexed node: cymonides_abc123 (Offshore Company Formation Guide...)
📊 Indexed document:
   ID: cymonides_abc123
   Embedding status: embedded
   Has description_vector: True
   Has content_vector: True
🔍 Testing semantic search...
   Found 1 results
   1. [1.000] Offshore Company Formation Guide
```

---

## 🎓 Key Differences from Original CyMonides

| Feature         | Original CyMonides                                   | Drill Search Adapter                   |
| --------------- | ---------------------------------------------------- | -------------------------------------- |
| **Indexes**     | Custom CyMonides index                               | `search_nodes` + `search_edges`        |
| **Schema**      | Custom unified schema                                | Drill Search node schema               |
| **Vectors**     | `content_vector`, `schema_vector`, `metadata_vector` | `description_vector`, `content_vector` |
| **Model**       | Configurable                                         | Fixed: `all-MiniLM-L6-v2`              |
| **Dimensions**  | Configurable                                         | Fixed: 384                             |
| **Integration** | Standalone                                           | Fully compatible with Drill Search     |

---

## ✅ Next Steps

1. **Batch Import**: Use adapter to import existing CyMonides data
2. **MCP Integration**: Expose adapter via MCP server for Claude Code
3. **UI Integration**: Add CyMonides indexing controls to Drill Search UI
4. **Migration Tool**: Migrate data from old Whoosh/Vector stores to Elasticsearch

---

**All CyMonides capabilities are now available with Drill Search's Elasticsearch infrastructure!**
