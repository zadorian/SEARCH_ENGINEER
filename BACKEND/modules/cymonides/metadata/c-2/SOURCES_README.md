# Cymonides-2 Source Breakdown

Cymonides-2 is a **unified global text corpus** containing content from multiple sources. While all content is merged into one index, we track each source separately for audit and filtering purposes.

## Current Sources

### 1. YouTube Commons (487,600 docs)
- **Origin:** `youtube_commons` index (migrated 2025-12-03)
- **Content:** YouTube video transcripts
- **Query:** `source_type:youtube`
- **Status:** ✅ Fully merged

### 2. Uploaded Reports (45,030 docs)
- **Content:** PDFs, Word docs, investigative reports
- **Query:** `source_type:report`
- **Status:** ✅ Active

### 3. Book Collection (count TBD)
- **Content:** Post-Soviet academic and research books
- **Topics:** Central Asia, Russia, regional studies
- **Query:** `source_type:book`
- **Display:** Book title as URL, author as title
- **Status:** ✅ Merged

### 4. Scraped Content (0 docs)
- **Content:** Web pages crawled from any project
- **Query:** `source_type:scraped`
- **Status:** ⏳ Pending - not yet implemented

## Total Documents
**532,630 docs** (~5.1GB)

*Note: Book count included in total but not separately tracked. To get exact count, query by source_type.*

## How to Query by Source

```bash
# Get YouTube content only
curl "http://localhost:9200/C-2/_search?q=source_type:youtube&size=10"

# Get reports only
curl "http://localhost:9200/C-2/_search?q=source_type:report&size=10"

# Get books only
curl "http://localhost:9200/C-2/_search?q=source_type:book&size=10"

# Aggregate by source
curl -X POST "http://localhost:9200/C-2/_search?size=0" -H 'Content-Type: application/json' -d '{
  "aggs": {
    "by_source": {
      "terms": { "field": "source_type" }
    }
  }
}'
```

## Maintenance

### Verify YouTube migration completed
```bash
curl "http://localhost:9200/youtube_commons/_count"
# Should match: 487,600 docs
# Then safe to delete: curl -X DELETE "http://localhost:9200/youtube_commons"
```

### Add new sources
When adding new content sources, create a subfolder in `sources/` with metadata.json tracking:
- Origin
- Document count
- Query filter
- Migration/merge status
