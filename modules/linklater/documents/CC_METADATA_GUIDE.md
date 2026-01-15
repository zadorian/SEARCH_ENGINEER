# Common Crawl Metadata in LinkStream

**Last Updated**: 2025-10-17

---

## 🎯 What CC Metadata is Available

When processing links from Common Crawl, the following metadata is captured:

### Core Link Data

- **source_domain** - Domain where the link appears
- **target_domain** - Domain being linked to
- **source_url** - Full URL of the page containing the link
- **target_url** - Full URL being linked to

### Crawl Metadata

- **crawl_date** - Date when CC crawled this page (YYYY-MM-DD format)
- **crawl_timestamp** - Full timestamp of the crawl (ISO 8601)
- **warc_filename** - Reference to the WARC archive file
- **http_status** - HTTP status code from the crawl (200, 404, etc.)

### Link Context

- **link_type** - Link relationship (dofollow, nofollow, etc.)
- **anchor_text** - Text of the link anchor
- **context** - Surrounding text context

---

## 📊 Storage Modes

LinkStream offers three storage modes for metadata:

### 1. Index-Only Mode (Default)

**Storage**: ~1-10 MB for 100K links
**What's Saved**:

- Domain→domain link summary
- Link counts
- First/last crawl dates
- Sample anchor text
- Top keywords

**Use Case**: Continuous monitoring, quick queries

```bash
./linkstream.py search --target yourdomain.com --index-only
```

### 2. Selective Metadata Mode

**Storage**: ~10-100 MB depending on matches
**What's Saved**:

- Everything in index-only mode PLUS
- Full metadata for matched links only
- Complete anchor text and context
- All crawl timestamps
- WARC file references

**Use Case**: Targeted investigation, high-value backlinks

```bash
./linkstream.py search --target yourdomain.com \
  --source-rank-max 10000 \
  --save-matches
```

### 3. Full Metadata Mode

**Storage**: 100s MB to GBs
**What's Saved**:

- Detailed metadata for ALL matched links
- Multiple crawl instances per link
- Complete historical timeline

**Use Case**: Deep analysis, research projects

```bash
./linkstream.py search --target yourdomain.com \
  --source-country US,UK,DE \
  --save-matches
```

---

## 🔍 Querying Metadata

### Query by Crawl Date

Find all links from a specific date range:

```bash
# CLI
./enhanced_index.py metadata-date 2024-10-15 --end-date 2024-10-20 --limit 50

# Python
from enhanced_index import EnhancedIndex

index = EnhancedIndex()
results = index.query_metadata_by_crawl_date('2024-10-15', '2024-10-20', limit=50)

for meta in results:
    print(f"{meta['source_domain']} → {meta['target_domain']}")
    print(f"  Crawled: {meta['crawl_date']}")
    print(f"  HTTP: {meta['http_status']}")
    print(f"  Anchor: {meta['anchor_text']}")
```

### Query by Domain

Get all metadata for a specific domain:

```bash
# CLI - Both directions
./enhanced_index.py metadata-domain yourdomain.com --mode both --limit 20

# CLI - Only backlinks (incoming)
./enhanced_index.py metadata-domain yourdomain.com --mode target --limit 20

# CLI - Only outlinks (outgoing)
./enhanced_index.py metadata-domain yourdomain.com --mode source --limit 20

# Python
index = EnhancedIndex()

# Get all metadata for domain
results = index.query_metadata_by_domain('yourdomain.com', mode='both', limit=20)

for meta in results:
    print(f"{meta['direction']}: {meta['source_domain']} → {meta['target_domain']}")
    print(f"  Crawled: {meta['crawl_date']} | HTTP: {meta['http_status']}")
```

### Query Specific Link

See how a specific link appeared across multiple crawls:

```bash
# CLI
./enhanced_index.py metadata-link nytimes.com yourdomain.com

# Python
results = index.query_metadata_by_link('nytimes.com', 'yourdomain.com')

for meta in results:
    print(f"Crawled: {meta['crawl_date']}")
    print(f"  Timestamp: {meta['crawl_timestamp']}")
    print(f"  WARC: {meta['warc_filename']}")
    print(f"  HTTP: {meta['http_status']}")
    print(f"  Anchor: {meta['anchor_text']}")
```

### List Available Crawl Dates

See what crawl dates are in your index:

```bash
# CLI
./enhanced_index.py crawl-dates

# Python
dates = index.query_crawl_dates()

for date_info in dates:
    print(f"{date_info['crawl_date']}: {date_info['link_count']:,} links")
```

---

## 📈 Statistics with Metadata

The enhanced stats command now shows metadata statistics:

```bash
./enhanced_index.py stats
```

Output includes:

```
📊 Index Statistics:

   Links:
      Unique links: 45,234
      Total instances: 127,891
      Source domains: 8,432
      Target domains: 12,876

   Keywords:
      Unique keywords: 23,456
      Total occurrences: 156,789

   Metadata:
      Total records: 45,234
      Unique crawl dates: 12

   Top crawl dates:
      2024-10-15: 12,345
      2024-10-01: 11,234
      2024-09-15: 10,123

   Storage:
      Index size: 28.5 MB
```

---

## 🔧 Integration with LinkStream

### Automatic Metadata Capture

When using LinkStream with `--save-matches`, metadata is automatically saved:

```bash
# This will save full metadata for all matches
./linkstream.py search \
  --target yourdomain.com \
  --source-rank-max 50000 \
  --save-matches \
  --backend cc-stream
```

### Python API

```python
from linkstream import LinkStreamAPI

api = LinkStreamAPI()

# Search with metadata saving
results = api.search(
    target_domains=['yourdomain.com'],
    source_filter={'max_rank': 50000},
    save_matches=True,  # This enables metadata saving
    backend='cc-stream'
)

# Query metadata afterwards
from enhanced_index import EnhancedIndex
index = EnhancedIndex()

# Get metadata by date
recent_links = index.query_metadata_by_crawl_date('2024-10-15', limit=50)

# Get metadata for domain
domain_meta = index.query_metadata_by_domain('yourdomain.com', mode='both')
```

---

## 🎯 Use Cases

### 1. Link Timeline Analysis

See when and how your backlinks evolved:

```python
# Get all metadata for a specific link
history = index.query_metadata_by_link('nytimes.com', 'yourdomain.com')

print(f"Link appeared in {len(history)} crawls")
for meta in history:
    print(f"{meta['crawl_date']}: {meta['anchor_text']}")
```

### 2. Fresh vs. Stale Backlinks

Find recent backlinks vs. old ones:

```python
# Recent (last month)
recent = index.query_metadata_by_crawl_date('2024-09-17', '2024-10-17')

# Older (3 months ago)
older = index.query_metadata_by_crawl_date('2024-07-17', '2024-08-17')

print(f"Recent backlinks: {len(recent)}")
print(f"Older backlinks: {len(older)}")
```

### 3. HTTP Status Analysis

Find broken links or redirects:

```python
meta = index.query_metadata_by_domain('yourdomain.com', mode='target')

status_counts = {}
for m in meta:
    status = m['http_status']
    status_counts[status] = status_counts.get(status, 0) + 1

print("HTTP Status Distribution:")
for status, count in sorted(status_counts.items()):
    print(f"  {status}: {count} links")
```

### 4. WARC File Lookup

Find exact WARC file for a link:

```python
meta = index.query_metadata_by_link('nytimes.com', 'yourdomain.com')

if meta:
    print(f"Latest crawl:")
    print(f"  Date: {meta[0]['crawl_date']}")
    print(f"  WARC: {meta[0]['warc_filename']}")
    print(f"  URL: {meta[0]['source_url']}")
```

---

## 💡 Best Practices

### 1. Start with Index-Only

Always start without metadata to understand scale:

```bash
# First: See how many links exist
./linkstream.py search --target yourdomain.com --index-only

# Then: Check results
./linkstream.py query --target yourdomain.com

# Finally: If needed, extract with metadata
./linkstream.py search --target yourdomain.com --save-matches
```

### 2. Use Date Filters

Don't query all metadata at once - filter by date:

```python
# Get metadata for specific time period
recent = index.query_metadata_by_crawl_date('2024-10-01', '2024-10-17', limit=100)
```

### 3. Selective Metadata Saving

Only save metadata for important links:

```bash
# Only save metadata for high-ranking sources
./linkstream.py search \
  --target yourdomain.com \
  --source-rank-max 10000 \
  --save-matches  # Metadata only saved for top 10K sites
```

### 4. Regular Cleanup

Metadata can accumulate - clean old data periodically:

```python
# Custom cleanup script
# Delete metadata older than 6 months
index.conn.execute('''
    DELETE FROM link_metadata
    WHERE crawl_date < date('now', '-6 months')
''')
index.conn.commit()
```

---

## 📊 Storage Estimates

| Matches    | Index-Only | With Metadata | Full Metadata |
| ---------- | ---------- | ------------- | ------------- |
| 1K links   | 100 KB     | 500 KB        | 2-5 MB        |
| 10K links  | 1 MB       | 5 MB          | 20-50 MB      |
| 100K links | 10 MB      | 50 MB         | 200-500 MB    |
| 1M links   | 100 MB     | 500 MB        | 2-5 GB        |

**Note**: Full metadata includes multiple crawl instances per link over time.

---

## 🚀 Next Steps

1. **Start with index-only** to understand your data
2. **Query crawl dates** to see what's available
3. **Selectively save metadata** for important links only
4. **Use date filters** when querying to reduce load
5. **Clean old metadata** periodically

For more details:

- `LINKSTREAM_GUIDE.md` - Full LinkStream documentation
- `enhanced_index.py` - Source code with all query methods
- `linkstream.py` - Main CLI and API

---

**Last Updated**: 2025-10-17
**Version**: 1.0
