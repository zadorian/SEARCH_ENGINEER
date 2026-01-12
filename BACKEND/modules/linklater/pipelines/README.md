# LinkLater Backlink Discovery Pipelines

**ALL backlink pipeline scripts must be placed in this directory.**

## Available Pipelines

### 1. production_backlink_discovery.py (28KB) ⭐ PRIMARY
**Status:** Production-ready
**Features:**
- Full multi-source integration (CC Graph, GlobalLinks, Majestic Fresh + Historic, Wayback)
- Entity extraction with 7 types (email, phone, URL, company, person, money, date)
- Keyword scanning with 100-char context snippets
- Smart deduplication with quality scoring (Majestic=4, CC Archive=3, GlobalLinks=2, CC Graph=1)
- Source URL tracking for all extractions
- Wayback Machine fallback when CC Archive fails

**Output Format:**
```python
{
    'source_url': 'https://example.com/page',
    'entities': {
        'email': [{'value': 'test@example.com', 'snippet': '...contact us at test@example.com for...'}],
        'company': [{'value': 'Acme Corp', 'snippet': '...founded by Acme Corp in...'}]
    },
    'keywords': [{'keyword': 'libya', 'snippet': '...investments in libya were...'}]
}
```

**Usage:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/production_backlink_discovery.py
```

### 2. automated_backlink_pipeline.py (12KB)
**Status:** Functional (subset of production pipeline)
**Features:**
- CC Index API query to find WARC files
- GlobalLinks extraction for outbound URLs
- Parallel Majestic queries (Fresh + Historic)
- Basic deduplication

**Limitations:**
- No entity extraction
- No Wayback fallback
- Less sophisticated deduplication

### 3. scan_pages_for_outlinks.py (5.9KB)
**Status:** Completed, found 0 results
**Purpose:** Direct CC Archive page scanning
**Note:** Links may be in different archives than domain graph aggregates

### 4. get_referring_pages.py (7.2KB)
**Status:** Failed - WAT file offset mismatch
**Purpose:** WAT file parser attempt
**Issue:** WARC offsets don't map 1:1 to WAT files

## Pipeline Selection Guide

| Use Case | Recommended Pipeline |
|----------|---------------------|
| Production investigations | production_backlink_discovery.py |
| Quick backlink discovery | automated_backlink_pipeline.py |
| Entity/keyword extraction | production_backlink_discovery.py |
| Historical research | production_backlink_discovery.py (includes Wayback) |

## Adding New Pipelines

When creating new backlink pipelines:

1. ✅ Place in `/modules/linklater/pipelines/`
2. ✅ Import from `modules.linklater.api import linklater`
3. ✅ Use environment variables from project root `.env`
4. ✅ Document features and limitations in this README
5. ❌ NEVER place pipelines in `/python-backend/` root

## Entity Extraction Patterns

The production pipeline uses these regex patterns:

- **email:** `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
- **phone:** `\+?[\d\s\-\(\)]{10,20}`
- **url:** `https?://[^\s<>"]+`
- **company:** Companies with Inc/LLC/Ltd/Corp/GmbH/SA/AB/AS suffixes
- **person:** Capitalized first/last names (2-3 words)
- **money:** Currency symbols or amounts with USD/EUR/million/billion
- **date:** Various date formats (DD/MM/YYYY, Month DD YYYY, etc.)

All matches include 100 characters of context on each side for GPT-5-nano filtering.
