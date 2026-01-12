# LinkLater Module Consolidation Plan

**Goal:** Single unified module for ALL discovery/archive/graph capabilities

## Current Structure (After Initial Move):

```
python-backend/modules/linklater/
├── __init__.py                    # Master exports
├── archives/
│   ├── optimal_archive.py         # ✅ MOVED from rapid_backdrill/
│   ├── hybrid_archive.py          # ✅ MOVED from rapid_backdrill/
│   └── (TODO: wayback, archive.org engines)
├── discovery/
│   └── keyword_variations.py      # ✅ MOVED from cc_content/
├── enrichment/
│   └── cc_enricher.py             # ✅ MOVED from cc_content/
├── scraping/
│   └── cc_first_scraper.py        # ✅ MOVED from cc_content/
└── graph/
    └── (TODO: graph queries, link extraction)
```

## Files to Consolidate INTO linklater:

### From `cc_content/` (3 files - 2 already moved):
- [x] `keyword_variations.py` → `linklater/discovery/`
- [x] `cc_enricher.py` → `linklater/enrichment/`
- [x] `cc_first_scraper.py` → `linklater/scraping/`

### From `rapid_backdrill/` (2 files - DONE):
- [x] `optimal_archive.py` → `linklater/archives/`
- [x] `hybrid_archive.py` → `linklater/archives/`

### From `scripts/` (Select best, DELETE rest):
**Keep these (move to linklater):**
- [ ] `waybackbacksearch.py` → `linklater/archives/wayback.py`
- [ ] `commoncrawl.py` → `linklater/archives/commoncrawl.py`

**DELETE these (redundant):**
- [ ] `parallel_archived_scraping.py` (duplicate of alldom backup)
- [ ] `archive_browser.py` (duplicate)
- [ ] `archived_page_fetcher.py` (duplicate)
- [ ] `archived_scraping.py` (old version)
- [ ] `optimal_archive_search.py` (superseded by rapid_backdrill version)
- [ ] `rapid_archive_search.py` (superseded)
- [ ] `archive.py` (old version)

### From `modules/brute/engines/`:
**Keep but reference (DON'T move - part of Brute module):**
- `archiveorg.py` - Brute Search engine integration
- `annas_archive.py` - Anna's Archive integration

### From `modules/alldom/`:
**Keep source module (DON'T move):**
- `sources/web_archives.py` - AllDom source integration

### From `categorizer-filterer/globallinks/`:
**Graph capabilities to move:**
- [ ] `commoncrawl_agent.py` → `linklater/graph/cc_agent.py`
- [ ] Link extraction logic → `linklater/graph/link_extractor.py`

### From `search/`:
- [ ] DELETE `hybrid_archive.py` (duplicate of rapid_backdrill version)

---

## Duplicates to DELETE:

### 1. `modules/alldom/_archive_duplicates_backup/` - DELETE ENTIRE FOLDER
```bash
rm -rf python-backend/modules/alldom/_archive_duplicates_backup/
```

### 2. `scripts/` - DELETE 7 files:
```bash
cd python-backend/scripts/
rm parallel_archived_scraping.py archive_browser.py archived_page_fetcher.py
rm archived_scraping.py optimal_archive_search.py rapid_archive_search.py archive.py
```

### 3. `search/` - DELETE 1 file:
```bash
rm python-backend/search/hybrid_archive.py
```

### 4. `rapid_backdrill/` - DELETE after moving best versions:
```bash
rm -rf python-backend/rapid_backdrill/
```

---

## __init__.py Files to Create:

### `linklater/__init__.py` - Master module (DONE ✅)

### `linklater/archives/__init__.py`:
```python
from .optimal_archive import OptimalArchiveSearch
from .hybrid_archive import HybridArchiveSearch
from .wayback import WaybackScanner
from .commoncrawl import CCArchiveScanner
```

### `linklater/discovery/__init__.py`:
```python
from .keyword_variations import KeywordVariationsSearch
```

### `linklater/enrichment/__init__.py`:
```python
from .cc_enricher import CCEnricher
```

### `linklater/scraping/__init__.py`:
```python
from .cc_first_scraper import CCFirstScraper
```

### `linklater/graph/__init__.py`:
```python
from .cc_agent import CCAgent
from .link_extractor import LinkExtractor
from .graph_query import GraphQuery
```

---

## API Routes Update:

### BEFORE:
```python
# Multiple scattered imports
from cc_content.keyword_variations import KeywordVariationsSearch
from cc_content.cc_enricher import CCEnricher
from rapid_backdrill.optimal_archive import OptimalArchiveSearch
```

### AFTER:
```python
# Single unified import
from linklater import (
    KeywordVariationsSearch,
    CCEnricher,
    OptimalArchiveSearch,
    HybridArchiveSearch,
    CCFirstScraper
)
```

---

## archive_advanced_routes.py - FIX EXTERNAL PATHS:

**BEFORE (lines 23-29):**
```python
c0gn1t0_standalone = Path(__file__).resolve().parents[4] / "C0GN1T0-STANDALONE" / ...
archive_search = Path(__file__).resolve().parents[4] / "Development" / ...
linkdata = Path(__file__).resolve().parents[4] / "Development" / ...
```

**AFTER:**
```python
# Use linklater module (no external paths)
from linklater import (
    KeywordVariationsSearch,
    CCEnricher,
    OptimalArchiveSearch
)
```

**ACTION:** Either DELETE `archive_advanced_routes.py` entirely OR rewrite to use linklater

---

## Final Structure:

```
python-backend/
├── modules/
│   ├── linklater/                 # ✅ THE ONLY DISCOVERY/ARCHIVE MODULE
│   │   ├── __init__.py
│   │   ├── archives/
│   │   ├── discovery/
│   │   ├── enrichment/
│   │   ├── scraping/
│   │   └── graph/
│   ├── brute/                     # Keep - Different purpose (meta-search)
│   ├── corporella/                # Keep - Company intelligence
│   ├── eyed/                      # Keep - Entity extraction
│   ├── alldom/                    # Keep - Domain intelligence
│   └── ai_engines/                # Keep - AI search engines
├── api/
│   ├── linklater_routes.py        # ✅ THE ONLY ARCHIVE/DISCOVERY ROUTES
│   └── (DELETE archive_advanced_routes.py)
├── scripts/                       # Keep only 2 files (wayback, cc)
└── (DELETE rapid_backdrill/, search/)
```

---

## Benefits:

1. ✅ **Single source of truth** - All archive/discovery code in one place
2. ✅ **No duplicates** - Each capability exists once
3. ✅ **Clear organization** - Logical subfolder structure
4. ✅ **Easy imports** - `from linklater import X`
5. ✅ **No external paths** - Everything self-contained in project
6. ✅ **Maintainable** - Future additions go to clear locations

---

## Execution Order:

1. [x] Create linklater structure
2. [x] Move core files (cc_content, rapid_backdrill)
3. [ ] Move select scripts (wayback, commoncrawl)
4. [ ] Move graph capabilities
5. [ ] Create all __init__.py files
6. [ ] Delete duplicates (alldom backup, scripts, search)
7. [ ] Update linklater_routes.py imports
8. [ ] Delete/rewrite archive_advanced_routes.py
9. [ ] Test all endpoints
10. [ ] Delete old folders (rapid_backdrill, search)

---

**Status:** PHASE 1 COMPLETE - Core files moved, structure created
**Next:** Move graph capabilities and delete duplicates
