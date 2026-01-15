# Cymonides-2 (C-2): Global Text Corpus

**Purpose:** Unified full-text search across all documents, regardless of source or project

## Overview

Cymonides-2 is the **text storage layer** of DRILL Search. Unlike C-1 (project-scoped entity graphs), C-2 is a **single global index** containing full-text content from all sources.

**Index Name:** `cymonides-2`
**Documents:** 532,630 docs (~5.1GB)

---

## Why C-2 Exists

### The Search Problem

**Problem:** You don't know which project a document belongs to, or you want to search across ALL documents at once:
- "Find all mentions of 'Bank Vostok' across everything"
- "Which documents discuss cryptocurrency regulation?"
- "Search my entire book library for 'post-Soviet transition'"
- "Find all YouTube transcripts mentioning 'sanctions'"

**Solution:** C-2 is a **global searchable corpus** that:
- Aggregates content from all sources (YouTube, PDFs, books, scraped pages)
- Provides full-text search with semantic capabilities
- Tracks source type and origin for filtering
- Links to C-1 entities for structured data

### C-1 vs C-2

| Aspect | C-1 (Entity Graphs) | C-2 (Text Corpus) |
|--------|---------------------|-------------------|
| **Scope** | Per-project | Global (all projects) |
| **Storage** | Structured nodes/edges | Full-text documents |
| **Queries** | Graph traversal | Keyword/semantic search |
| **Updates** | Mutable (entities evolve) | Immutable (append-only) |
| **Size** | Small per project | Large (532K docs) |
| **Use** | "Show me X's network" | "Find documents about X" |

**They work together:**
```
1. User uploads PDF → Full text indexed in C-2
2. Entities extracted → Created in C-1
3. C-2 doc contains: extracted_entity_ids → [entity_1, entity_2]
4. C-1 entities contain: mentioned_in → [doc_id]
5. User can navigate both ways: Text ↔ Entities
```

---

## Source Tracking

C-2 contains content from **4 source types:**

### 1. YouTube (487,600 docs)
- **Origin:** `youtube_commons` index (migrated 2025-12-03)
- **Content:** Video transcripts
- **Query:** `source_type:youtube`
- **Display:** Standard (title, URL, snippet)

### 2. Reports (45,030 docs)
- **Content:** Uploaded PDFs, Word docs, investigative reports
- **Query:** `source_type:report`
- **Display:** Report title as URL, snippet from content
- **Note:** May contain narrative report node names (e.g., "EIB Report re...")

### 3. Books (count TBD)
- **Content:** Post-Soviet academic and research books
- **Topics:** Central Asia, Russia, regional studies
- **Query:** `source_type:book`
- **Display:**
  - **URL field:** Book title (e.g., "Kazakhstan: Political Transitions")
  - **Title field:** Author (e.g., "Smith, John")
  - **Snippet field:** Relevant content around search term
  - **Multiple instances:** Show "more instances" indicator

### 4. Scraped Content (0 docs - future)
- **Content:** Web pages crawled from investigations
- **Query:** `source_type:scraped`
- **Status:** Not yet implemented

### 5. Davos Onion Torsite Scrapes
- **Content:** Dark web pages crawled via Tor from .onion sites
- **Query:** `source_type:davos_onion`
- **Display:** URL (.onion), title, snippet from content
- **Note:** Scraped via LINKLATER Tor crawler infrastructure

**Metadata Location:** `../../metadata/cymonides-2/sources/`

---

## Schema Structure

### Core Fields

```json
{
  "_id": "unique_doc_id",
  "source_type": "youtube|report|book|scraped",
  "title": "Document title or video title or book title",
  "content": "Full text content...",
  "url": "Original URL (if applicable)",
  "file_name": "Original filename (for uploads)",
  "author": "Author name (for books)",
  "indexed_at": "2025-12-03T...",
  "extracted_entity_ids": ["entity_id_1", "entity_id_2"],
  "source_domain": "example.com",
  "language": "en",
  "metadata": {
    "source_specific_fields": "..."
  }
}
```

### Source-Specific Fields

**YouTube:**
```json
{
  "source_type": "youtube",
  "title": "Video title",
  "url": "https://youtube.com/watch?v=...",
  "metadata": {
    "channel": "Channel name",
    "upload_date": "2024-01-01",
    "duration": "PT10M30S"
  }
}
```

**Books:**
```json
{
  "source_type": "book",
  "title": "Book title",
  "author": "Author name",
  "content": "Full book text...",
  "metadata": {
    "publisher": "Publisher name",
    "year": "2010",
    "isbn": "978-..."
  }
}
```

**Reports:**
```json
{
  "source_type": "report",
  "title": "Report title or filename",
  "file_name": "original_filename.pdf",
  "content": "Extracted text...",
  "metadata": {
    "uploaded_by": "user_id",
    "uploaded_at": "2025-12-03T...",
    "file_size": 1024000
  }
}
```

---

## Query Patterns

### 1. Simple Keyword Search
```bash
curl "http://localhost:9200/cymonides-2/_search?q=cryptocurrency&size=10"
```

### 2. Filter by Source Type
```bash
# Only books
curl "http://localhost:9200/cymonides-2/_search" -H 'Content-Type: application/json' -d '{
  "query": {
    "bool": {
      "must": [
        {"match": {"content": "sanctions"}},
        {"term": {"source_type.keyword": "book"}}
      ]
    }
  }
}'
```

### 3. Semantic Search (if embeddings enabled)
```bash
curl "http://localhost:9200/cymonides-2/_search" -H 'Content-Type: application/json' -d '{
  "query": {
    "knn": {
      "field": "content_embedding",
      "query_vector": [...],
      "k": 10
    }
  }
}'
```

### 4. Search with Snippet Highlighting
```bash
curl "http://localhost:9200/cymonides-2/_search" -H 'Content-Type: application/json' -d '{
  "query": {"match": {"content": "Bank Vostok"}},
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 3
      }
    }
  }
}'
```

### 5. Aggregate by Source
```bash
curl "http://localhost:9200/cymonides-2/_search?size=0" -H 'Content-Type: application/json' -d '{
  "aggs": {
    "by_source": {
      "terms": {"field": "source_type.keyword"}
    }
  }
}'
```

---

## Integration with C-1 (Entity Graphs)

### Document → Entities

When a document is indexed in C-2:

```
1. Document uploaded → Full text stored in C-2
2. Claude Haiku extraction triggered
3. Entities created in C-1 (for active project)
4. C-2 doc updated: extracted_entity_ids = [id1, id2, id3]
5. C-1 entities updated: mentioned_in = [doc_id]
```

### Bi-Directional Navigation

**From Document to Entities:**
```typescript
// Get document
const doc = await getDoc('cymonides-2', docId);
// Get associated entities from C-1
const entities = await getEntities(doc.extracted_entity_ids);
```

**From Entity to Documents:**
```typescript
// Get entity from C-1
const entity = await getEntity('cymonides-1-project-{id}', entityId);
// Get documents mentioning this entity
const docs = await searchDocs({
  query: {
    terms: { _id: entity.mentioned_in }
  }
});
```

---

## Display Format by Source Type

### YouTube Videos
- **URL:** Video URL
- **Title:** Video title
- **Snippet:** Transcript excerpt with search term highlighted

### Reports
- **URL:** Report title (filename or narrative node name)
- **Title:** Report metadata (date, author, etc.)
- **Snippet:** Relevant excerpt from content

### Books
- **URL:** Book title (e.g., "Post-Soviet Transitions")
- **Title:** Author name (e.g., "Smith, John")
- **Snippet:** Relevant excerpt around search term
- **Multiple Hits:** If search term appears multiple times:
  - Show "N more instances"
  - Link to page listing all instances

### Scraped Content (Future)
- **URL:** Original web page URL
- **Title:** Page title
- **Snippet:** Relevant excerpt from page

---

## Use Cases That Rely on C-2

| Use Case | How C-2 is Used |
|----------|-----------------|
| **Company Profiles** | Search for documents mentioning company |
| **Domains List** | Filter content by source_domain |
| **Red Flags** | Contradiction detection across documents |
| **Data Breaches** | Context for breach records |
| **Country Indexes** | Regional content filtering |

---

## Performance Notes

- **Full-text search:** Fast (5.1GB, 532K docs)
- **Source filtering:** Very fast (keyword field)
- **Cross-source search:** No penalty (single index)
- **Semantic search:** Moderate (if embeddings used)
- **Aggregations:** Fast for source_type, domain

---

## Maintenance

### Add New Document
```bash
curl -X POST "http://localhost:9200/cymonides-2/_doc" -H 'Content-Type: application/json' -d '{
  "source_type": "report",
  "title": "New Report",
  "content": "Full text...",
  "indexed_at": "2025-12-03T..."
}'
```

### Query Document Count by Source
```bash
curl "http://localhost:9200/cymonides-2/_search?size=0" -H 'Content-Type: application/json' -d '{
  "aggs": {
    "counts": {
      "terms": {"field": "source_type.keyword"}
    }
  }
}'
```

### Reindex from youtube_commons (if needed)
```bash
curl -X POST "http://localhost:9200/_reindex" -H 'Content-Type: application/json' -d '{
  "source": {"index": "youtube_commons"},
  "dest": {"index": "cymonides-2"},
  "script": {
    "source": "ctx._source.source_type = 'youtube'"
  }
}'
```

---

## Related Documentation

- **C-1 Integration:** `../cymonides-1/README.md`
- **Source Breakdown:** `../../metadata/cymonides-2/SOURCES_README.md`
- **YouTube Source:** `../../metadata/cymonides-2/sources/youtube/metadata.json`
- **Books Source:** `../../metadata/cymonides-2/sources/books/metadata.json`
- **Reports Source:** `../../metadata/cymonides-2/sources/reports/metadata.json`
- **Entity Extraction:** `../../server/services/cymonides-2/EntityExtractor.ts`
- **C-2 Metadata:** `../../metadata/cymonides-2/metadata.json`

---

## Future Enhancements

1. **Semantic Search:** Embed all documents for similarity search
2. **Deduplication:** Detect and merge duplicate documents
3. **Cross-Project Tagging:** Tag documents with relevant project IDs
4. **Temporal Search:** Filter by date ranges, track document history
5. **Multi-Language:** Language detection and translation
