# LinkLater Pipeline Execution Index

**Authoritative reference of how to execute each pipeline.**

---

## Pipeline Overview

All pipelines are located in: `/modules/linklater/pipelines/`

| Pipeline | Size | Status | Use Case |
|----------|------|--------|----------|
| `production_backlink_discovery.py` | 28KB | ⭐ PRIMARY | Full investigation with entity extraction |
| `automated_backlink_pipeline.py` | 12KB | Functional | Quick multi-source backlink discovery |
| `scan_pages_for_outlinks.py` | 5.9KB | Completed (0 results) | Direct CC Archive page scanning |
| `get_referring_pages.py` | 7.2KB | Failed (WAT offset issue) | WAT file parser attempt |

---

## 1. Production Backlink Discovery (PRIMARY)

**File:** `/modules/linklater/pipelines/production_backlink_discovery.py`

**Status:** ✅ Production Ready

**Features:**
- ✅ CC Graph + GlobalLinks + Majestic (Fresh + Historic) + Wayback
- ✅ Entity extraction (7 types) with 100-char context snippets
- ✅ Keyword scanning with context snippets
- ✅ Smart deduplication with quality scoring
- ✅ Source URL tracking for all extractions

### Execution

**From project root:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/production_backlink_discovery.py
```

**From python-backend:**
```bash
cd python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/production_backlink_discovery.py
```

**Standalone:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/pipelines
source ../../../../venv/bin/activate
python production_backlink_discovery.py
```

### Configuration (Edit in file)

**Line 28-48: Target & Keywords**
```python
TARGET_DOMAIN = "sebgroup.com"

LIBYAN_KEYWORDS = [
    'libya', 'libyan', 'tripoli', 'benghazi',
    'gaddafi', 'qadhafi', 'LIA',
    'libya investment authority',
    '.ly', 'libyan.'
]

SPECIFIC_DOMAINS_TO_SCAN = [
    'cryptonews.com.au',
    'wko.at',
    'ots.at',
    'easybank.at'
]
```

### Output Format

```python
{
    'source_url': 'https://example.com/page',
    'source_domain': 'example.com',
    'target_url': 'https://sebgroup.com/path',
    'anchor_text': 'SEB Bank',
    'provider': 'majestic_fresh',
    'quality_score': 4,  # Majestic=4, CC Archive=3, GlobalLinks=2, CC Graph=1
    'entities': {
        'email': [
            {'value': 'test@example.com', 'snippet': '...contact us at test@example.com for...'}
        ],
        'company': [
            {'value': 'Acme Corp', 'snippet': '...founded by Acme Corp in...'}
        ],
        'person': [
            {'value': 'John Smith', 'snippet': '...CEO John Smith announced...'}
        ],
        'phone': [...],
        'url': [...],
        'money': [...],
        'date': [...]
    },
    'keywords': [
        {'keyword': 'libya', 'snippet': '...investments in libya were...'},
        {'keyword': 'tripoli', 'snippet': '...office in tripoli handles...'}
    ]
}
```

### Pipeline Phases

**Phase 1:** CC Graph + GlobalLinks (Parallel, FREE)
- CC Graph: Domain-level backlinks (157M domains)
- GlobalLinks: Page-level backlinks from WAT files

**Phase 2:** Majestic Fresh + Historic (Parallel, PAID)
- Fresh: Last 90 days
- Historic: Last 5 years
- Includes anchor text, TrustFlow, CitationFlow

**Phase 3:** CC Archive Deep Scan (Sequential, FREE, SLOW)
- Scans specific domains from Phase 1/2
- Fetches actual WARC files
- Extracts entities and keywords with context

**Phase 4:** Wayback Fallback (If CC Archive fails)
- Internet Archive CDX API
- Fetches archived pages
- Same entity/keyword extraction

**Phase 5:** Merge & Deduplicate
- Quality-based scoring (Majestic > CC Archive > GlobalLinks > CC Graph)
- Preserve best metadata for each unique URL pair

### Expected Runtime

- **Fast path** (CC Graph + GlobalLinks + Majestic): 10-30 seconds
- **With CC Archive scan** (4 specific domains): 2-5 minutes
- **Full historical scan** (all sources + deep scan): 5-15 minutes

### Required Services

- ✅ FastAPI backend on port 8001 (for CC Graph)
- ✅ Majestic API key in `.env`
- ✅ Internet connection

**Optional:**
- GlobalLinks binaries (automatically detected)
- Elasticsearch (for caching results)

---

## 2. Automated Backlink Pipeline

**File:** `/modules/linklater/pipelines/automated_backlink_pipeline.py`

**Status:** ✅ Functional

**Features:**
- ✅ CC Index API query to find WARC files
- ✅ GlobalLinks extraction for outbound URLs
- ✅ Parallel Majestic queries (Fresh + Historic)
- ❌ No entity extraction
- ❌ No Wayback fallback

### Execution

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/automated_backlink_pipeline.py
```

### Configuration (Edit in file)

**Line 15-20:**
```python
TARGET_DOMAIN = "sebgroup.com"
SOURCE_DOMAINS = ["cryptonews.com.au", "wko.at", "ots.at", "easybank.at"]
ARCHIVE = "CC-MAIN-2025-47"
```

### Output Format

```python
{
    'source_url': 'https://example.com/page',
    'target_url': 'https://sebgroup.com/',
    'anchor_text': 'SEB Group',
    'provider': 'majestic_fresh'
}
```

**Simpler than production pipeline** - no entity extraction, no keyword snippets.

### Expected Runtime

- **Typical:** 30-60 seconds
- **Faster than production** (skips entity extraction and Wayback)

---

## 3. Scan Pages for Outlinks

**File:** `/modules/linklater/pipelines/scan_pages_for_outlinks.py`

**Status:** ⚠️ Completed but found 0 results

**Purpose:** Direct CC Archive page scanning

**Why 0 results:** Domain graph aggregates multiple archives; specific links may be in different archives than CC-MAIN-2025-47.

### Execution

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/scan_pages_for_outlinks.py
```

### Configuration (Edit in file)

**Line 12-18:**
```python
SOURCE_DOMAINS = ["cryptonews.com.au", "wko.at", "ots.at", "easybank.at"]
TARGET_DOMAIN = "sebgroup.com"
ARCHIVE = "CC-MAIN-2025-47"
MAX_PAGES_PER_DOMAIN = 100
```

### Expected Runtime

- **Per domain:** 1-3 minutes
- **Total (4 domains):** 4-12 minutes

### Note

This pipeline directly fetches WARC files and parses HTML. If you get 0 results, the links may be in a different archive. Use `production_backlink_discovery.py` which tries multiple approaches.

---

## 4. Get Referring Pages (WAT Parser)

**File:** `/modules/linklater/pipelines/get_referring_pages.py`

**Status:** ❌ Failed (WAT file offset issue)

**Issue:** WARC index offsets don't map 1:1 to WAT files. WAT files have their own internal structure.

**Recommendation:** Use `production_backlink_discovery.py` instead, which uses GlobalLinks binaries that handle WAT files correctly.

### Execution (For reference only - will fail)

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/pipelines/get_referring_pages.py
```

### Why It Fails

1. Queries CC Index for WARC file locations
2. Tries to use WARC offsets to fetch from corresponding WAT file
3. **Error:** WAT files use different offsets than WARC files
4. Gets HTTP 404/416 errors

### Alternative

Use **GlobalLinks** instead:
```python
from modules.linklater.linkgraph.globallinks import GlobalLinksClient

client = GlobalLinksClient()
backlinks = await client.get_backlinks("sebgroup.com", limit=1000, archive="CC-MAIN-2025-47")
```

GlobalLinks uses precomputed WAT extractions, avoiding the offset mapping problem.

---

## Examples & Tests

### Examples (Investigation Scripts)

**Location:** `/modules/linklater/examples/`

#### `investigate_sebgroup.py` - Full Stack Investigation

**Purpose:** Complete SEB Group investigation using all LinkLater sources

**Execution:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/examples/investigate_sebgroup.py
```

**What it does:**
1. CC Web Graph backlinks
2. GlobalLinks backlinks
3. Majestic Fresh backlinks
4. Majestic Historic backlinks
5. Historical CC archives search (2008-2024)
6. Filters for Libyan keywords and specific TLDs (.ly, .ru, .is)

**Runtime:** 2-5 minutes

---

#### `full_content_scan.py` - Website Content Scanner

**Purpose:** Scan seb.se and sebgroup.com for Libyan keywords in actual page content

**Execution:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/examples/full_content_scan.py
```

**What it does:**
1. Scrapes homepages
2. Searches for 60+ Libyan keywords
3. Extracts entities (companies, persons)
4. Checks Wayback Machine
5. Checks Common Crawl index

**Runtime:** 1-3 minutes

---

### Tests (Integration Tests)

**Location:** `/modules/linklater/tests/`

#### `test_majestic_integration.py` - Majestic API Test

**Purpose:** Verify Majestic integration works correctly

**Execution:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/tests/test_majestic_integration.py
```

**What it tests:**
1. Fresh index - referring domains
2. Fresh index - backlink pages
3. Anchor text search for keywords
4. Country TLD filtering

**Expected output:** 10 referring domains, 10 backlink pages, keyword/TLD match status

---

#### `test_binary_extraction.py` - GlobalLinks Binary Test

**Purpose:** Verify GlobalLinks binaries are found and working

**Execution:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
python modules/linklater/tests/test_binary_extraction.py
```

**What it tests:**
1. Binary detection in multiple locations
2. Backlinks query functionality
3. Outlinks query functionality
4. Extract command with filters

---

## Quick Reference: Which Pipeline to Use?

| Scenario | Use This Pipeline | Reason |
|----------|-------------------|--------|
| **Production investigation** | `production_backlink_discovery.py` | Most complete, entity extraction, all sources |
| **Quick backlink check** | `automated_backlink_pipeline.py` | Faster, no entity extraction overhead |
| **Need entity extraction** | `production_backlink_discovery.py` | Only pipeline with entity/keyword snippets |
| **Historical research** | `production_backlink_discovery.py` | Includes Wayback fallback |
| **Testing Majestic** | `test_majestic_integration.py` | Focused test |
| **Testing GlobalLinks** | `test_binary_extraction.py` | Focused test |
| **Full SEB investigation** | `investigate_sebgroup.py` | Pre-configured for SEB Group + Libya |
| **Content scanning** | `full_content_scan.py` | Scans actual page content, not just links |

---

## Troubleshooting

### "Cannot connect to host localhost:8001"

**Problem:** CC Graph API not running

**Solution:**
```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend
source ../venv/bin/activate
PORT=8001 python -m uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

### "GlobalLinks binary not found"

**Problem:** GlobalLinks binaries not in expected locations

**Solution:**
```bash
# Check if binaries exist
ls /Users/attic/DRILL_SEARCH/drill-search-app/categorizer-filterer/globallinks/*/bin/outlinker

# If missing, download/compile GlobalLinks
cd /Users/attic/DRILL_SEARCH/drill-search-app/categorizer-filterer/globallinks
# [Follow GlobalLinks installation instructions]
```

### "Majestic API error"

**Problem:** Missing or invalid Majestic API key

**Solution:**
```bash
# Check .env file
grep MAJESTIC_API_KEY /Users/attic/DRILL_SEARCH/drill-search-app/.env

# Add if missing:
echo "MAJESTIC_API_KEY=your_key_here" >> /Users/attic/DRILL_SEARCH/drill-search-app/.env
```

### "Found 0 backlinks from CC Archive"

**Problem:** Target domain links not in specified archive

**Solutions:**
1. **Try different archive:** Change `archive="CC-MAIN-2025-47"` to `archive="CC-MAIN-2024-10"`
2. **Use production pipeline:** It tries Wayback as fallback
3. **Use GlobalLinks:** Queries precomputed indexes across all archives

---

## Environment Setup

**Required before running any pipeline:**

```bash
# 1. Navigate to python-backend
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend

# 2. Activate virtual environment
source ../venv/bin/activate

# 3. Verify environment
python -c "from modules.linklater.api import linklater; print('✅ LinkLater ready')"
```

**Verify `.env` has:**
```bash
MAJESTIC_API_KEY=<your_key>
ELASTICSEARCH_URL=http://localhost:9200
FASTAPI_URL=http://localhost:8001
```

---

## Output Locations

**Console Output:** All pipelines print to stdout by default

**File Output:** Some pipelines save to:
- `/modules/linklater/output/` (if implemented)
- Check individual pipeline code for specific output paths

**Elasticsearch:** Results can be indexed if ES integration is enabled in pipeline code

---

**Last Updated:** 2025-11-30
**Tested With:** sebgroup.com investigation
**Archive Version:** CC-MAIN-2025-47 (September-October-November 2025)
