# Search Architecture Refactoring Plan

**Date:** November 2, 2025  
**Status:** ACTIVE - Implementation in Progress  
**Goal:** Reorganize from legacy "search types" to **Targeted Searches** + **Macros** with 3-Level Matrix System

---

## 1. Core Architecture Principles

### **Terminology (NEW)**
- ❌ **DEPRECATED:** "Search Types"
- ✅ **NEW:** "Targeted Searches" (operator-based) + "Macros" (use-case combinations)

### **3-Level System (3L)**

**L1 - Native Support**
- Engines have native operator support
- No post-filtering needed
- Fastest, most accurate
- Example: Google for `site:` operator

**L2 - Native-Like (Creative)**
- Engines don't have native support BUT can approximate
- Requires post-filtering to remove false positives
- Good balance of speed and coverage
- Example: Using general search + filter for proximity on engines without AROUND()

**L3 - Brute + Filter**
- Run ALL available engines (brute search)
- Heavy post-filtering for criteria
- Maximum recall, slowest
- Fallback when L1/L2insufficient

**User Control:**
- Frontend selector: L1 (Fast) | L2 (Balanced) | L3 (Maximum Recall)
- Tradeoff: Speed ↔ Depth

---

## 2. New Folder Structure

```
iii. OBJECT/
├── targeted_searches/          # NEW - Operator-based searches
│   ├── __init__.py
│   ├── temporal/
│   │   ├── date.py            # Date range targeting
│   │   ├── age.py             # Domain/page age
│   │   └── event.py           # Event-based temporal
│   ├── geographical/
│   │   ├── site.py            # Domain targeting
│   │   ├── location.py        # Geographic location
│   │   └── address.py         # Physical address
│   ├── textual/
│   │   ├── intitle.py         # Title targeting
│   │   ├── inurl.py           # URL targeting
│   │   ├── inanchor.py        # Anchor text
│   │   └── author.py          # Author search
│   ├── format/
│   │   ├── filetype.py        # File type targeting
│   │   ├── image.py           # Image search
│   │   ├── video.py           # Video search
│   │   └── audio.py           # Audio search
│   ├── linguistic/
│   │   └── language.py        # Language targeting
│   ├── object/
│   │   ├── exact_phrase.py    # Exact phrase matching
│   │   ├── proximity.py       # Proximity search
│   │   ├── wildcards.py       # Wildcard operators
│   │   ├── or_search.py       # Boolean OR
│   │   └── not_search.py      # Boolean NOT/exclusion
│   └── category/
│       ├── news.py            # News search
│       ├── academic.py        # Academic search
│       ├── books.py           # Book search
│       ├── forum.py           # Forum search
│       ├── social_media.py    # Social platforms
│       └── corporate.py       # Corporate intelligence
│
├── macros/                     # NEW - Use-case combinations
│   ├── __init__.py
│   └── annual_report.py       # Annual report fetching (only macro for now)
│
└── Search_Types/              # LEGACY - To be migrated
    └── (60+ files to categorize and move)
```

---

## 3. Targeted Searches Audit

### **Files in Search_Types/ - Categorization**

#### **A. TEMPORAL (Targeted Searches)**
- ✅ `date.py` → `targeted_searches/temporal/date.py`
- ✅ `age.py` → `targeted_searches/temporal/age.py`
- ✅ `event.py` → `targeted_searches/temporal/event.py`

#### **B. GEOGRAPHICAL (Targeted Searches)**
- ✅ `site.py` → `targeted_searches/geographical/site.py`
- ✅ `location.py` → `targeted_searches/geographical/location.py`
- ✅ `location_improved.py` → Merge into `location.py`
- ✅ `address.py` → `targeted_searches/geographical/address.py`

#### **C. TEXTUAL (Targeted Searches)**
- ✅ `intitle.py` → `targeted_searches/textual/intitle.py`
- ✅ `inurl.py` → `targeted_searches/textual/inurl.py`
- ✅ `anchor.py` → `targeted_searches/textual/inanchor.py`
- ✅ `author_search.py` → `targeted_searches/textual/author.py`

#### **D. FORMAT (Targeted Searches)**
- ✅ `filetype.py` → `targeted_searches/format/filetype.py`
- ✅ `pdf.py` → Merge into `filetype.py` (wrapper)
- ✅ `image_search.py` → `targeted_searches/format/image.py`
- ✅ `video.py` → `targeted_searches/format/video.py`
- ✅ `audio.py` → `targeted_searches/format/audio.py`

#### **E. LINGUISTIC (Targeted Searches)**
- ✅ `language.py` → `targeted_searches/linguistic/language.py`

#### **F. OBJECT (Targeted Searches)**
- ✅ `exact_phrase.py` → `targeted_searches/object/exact_phrase.py`
- ✅ `proximity.py` → `targeted_searches/object/proximity.py`
- ✅ `proximity_lazy.py` → Merge into `proximity.py`
- ✅ `wildcards.py` → `targeted_searches/object/wildcards.py`
- ✅ `or_search.py` → `targeted_searches/object/or_search.py`
- ✅ `NOT.py` → `targeted_searches/object/not_search.py`

#### **G. CATEGORY (Targeted Searches)**
- ✅ `news.py` → `targeted_searches/category/news.py`
- ✅ `news_enhanced.py` → Merge into `news.py`
- ✅ `news_original.py` → Archive/delete
- ✅ `academic.py` → `targeted_searches/category/academic.py`
- ✅ `books.py` → `targeted_searches/category/books.py`
- ✅ `forum.py` → `targeted_searches/category/forum.py`
- ✅ `social_media.py` → `targeted_searches/category/social_media.py`
- ✅ `corporate_search.py` → `targeted_searches/category/corporate.py`
- ✅ `medical.py` → `targeted_searches/category/medical.py`
- ✅ `edu.py` → `targeted_searches/category/edu.py`
- ✅ `product.py` → `targeted_searches/category/product.py`
- ✅ `recruitment.py` → `targeted_searches/category/recruitment.py`
- ✅ `review.py` → `targeted_searches/category/review.py`
- ✅ `blog.py` → `targeted_searches/category/blog.py`
- ✅ `crypto.py` → `targeted_searches/category/crypto.py`
- ✅ `tor.py` → `targeted_searches/category/tor.py`

#### **H. DOMAIN INTELLIGENCE (Targeted Searches)**
- ✅ `domain_intel.py` → `targeted_searches/domain/domain_intel.py`
- ✅ `indom.py` → `targeted_searches/domain/indom.py`
- ✅ `alldom.py` → `targeted_searches/domain/alldom.py`
- ✅ `domain_fts5_search.py` → `targeted_searches/domain/domain_fts.py`

#### **I. SUBJECT (Targeted Searches)**
- ✅ `people.py` → `targeted_searches/subject/people.py`
- ✅ `person.py` → `targeted_searches/subject/person.py`
- ✅ `dataset.py` → `targeted_searches/subject/dataset.py`

#### **J. SUBJECT (Review Outcome)**
- ❌ `unified_company_intelligence.py` → Move to project-root temp folder `_TEMP_HOLD/unified_company_intelligence.py`
- ❌ `huggingface_search.py` → Move to project-root temp folder `_TEMP_HOLD/huggingface_search.py`
- ❌ `memory_search.py` → Move to project-root temp folder `_TEMP_HOLD/memory_search.py`
- ✅ `reverse_image.py` → `targeted_searches/format/reverse_image.py`

#### **K. INFRASTRUCTURE (Keep in Place)**
- 🔧 `base_engine.py` → Keep
- 🔧 `base_search_with_filtering.py` → Keep
- 🔧 `base_streamer.py` → Keep
- 🔧 `brute.py` → **CRITICAL - Refactor for L3 integration**
- 🔧 `capabilities.py` → Keep
- 🔧 `config.py` → Keep
- 🔧 `common.py` → Keep
- 🔧 `engine_imports.py` → Keep
- 🔧 `engine_wrapper.py` → Keep
- 🔧 `registry.py` → Keep
- 🔧 `settings.py` → Keep
- 🔧 `shared_session.py` → Keep

#### **L. UTILITIES (Keep in Place)**
- 🔧 `checkpoint_manager.py` → Keep
- 🔧 `progress_monitor.py` → Keep
- 🔧 `progress_indicator.py` → Keep
- 🔧 `parallel_executor.py` → Keep
- 🔧 `parallel_search_adapter.py` → Keep
- 🔧 `recall_optimizer.py` → Keep
- 🔧 `input_sanitizer.py` → Keep
- 🔧 `snippet_enrichment.py` → Keep
- 🔧 `engine_health_monitor.py` → Keep
- 🔧 `engine_status.py` → Keep
- 🔧 `lazy_engine_loader.py` → Keep

#### **M. LEGACY (Archive/Delete)**
- ❌ `legacy/` folder → Archive entire folder
- ❌ `news_original.py` → Archive
- ❌ `location/` subfolder → Merge into main targeted_searches

---

## 4. Targeted Search Template (3L Integration)

### **Standard Template for All Targeted Searches**

```python
#!/usr/bin/env python3
"""
[Operator Name] Targeted Search
3-Level Matrix Implementation
"""

from __future__ import annotations
from typing import List, Dict, Any, AsyncGenerator
from dataclasses import dataclass

from ROUTER.matrix_registry import get_engines
from ROUTER.engine_dispatcher import build_engines_from_codes
from iv.LOCATION.c.UNKNOWN_UNKNOWN["1"].OPEN-WEB.unified_engine import UnifiedEngine


@dataclass
class TargetedSearchConfig:
    """Configuration for targeted search execution"""
    level: str = "L1"  # L1, L2, or L3
    enable_post_filter: bool = True
    max_results: int = 100
    concurrency: int = 5


class [OperatorName]TargetedSearch:
    """
    [Operator] targeting with 3-level support
    
    L1: Engines with native [operator] support
    L2: Engines with creative workarounds + filtering
    L3: Brute search all engines + heavy filtering
    """
    
    def __init__(self, config: TargetedSearchConfig = None):
        self.config = config or TargetedSearchConfig()
        self.operator_type = "[operator_key]"  # e.g., "date", "site", "filetype"
    
    async def search(
        self,
        query: str,
        **operator_params  # operator-specific params
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute targeted search at configured level
        
        Args:
            query: Base search query
            **operator_params: Operator-specific parameters
        
        Yields:
            Search results matching criteria
        """
        
        # 1. Get engines for requested level
        engine_codes = get_engines(self.operator_type, level=self.config.level)
        
        if self.config.level == "L3":
            # L3: Use brute search (all engines)
            engine_codes = await self._get_all_engines()
        
        # 2. Build engine instances
        engines = build_engines_from_codes(engine_codes)
        
        # 3. Create unified engine
        unified = UnifiedEngine(list(engines.keys()))
        
        # 4. Execute search with operator-specific targeting
        async for result in unified.search_stream(
            query=query,
            **self._build_targeting_params(operator_params),
            concurrency=self.config.concurrency
        ):
            # 5. Apply post-filtering if needed
            if self._should_filter(result):
                if await self._passes_filter(result, operator_params):
                    yield self._enrich_result(result)
    
    def _should_filter(self, result: Dict) -> bool:
        """Determine if result needs filtering based on level"""
        return self.config.level in ("L2", "L3") and self.config.enable_post_filter
    
    async def _passes_filter(self, result: Dict, params: Dict) -> bool:
        """
        Apply operator-specific filtering logic
        Override in subclasses
        """
        return True
    
    def _build_targeting_params(self, params: Dict) -> Dict:
        """
        Convert operator params to engine targeting params
        Override in subclasses
        """
        return params
    
    def _enrich_result(self, result: Dict) -> Dict:
        """Add metadata about how result was found"""
        result['targeted_search'] = self.operator_type
        result['search_level'] = self.config.level
        return result
    
    async def _get_all_engines(self) -> List[str]:
        """Get all available engine codes for L3 brute search"""
        # Import all engine codes from registry
        from ROUTER.engine_dispatcher import CODE_TO_CLASS, OPEN_WEB_CODE_TO_CLASS
        return list(CODE_TO_CLASS.keys()) + list(OPEN_WEB_CODE_TO_CLASS.keys())


# API convenience functions
async def search_[operator](
    query: str,
    level: str = "L1",
    **params
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Convenience function for [operator] search
    
    Args:
        query: Search query
        level: "L1", "L2", or "L3"
        **params: Operator-specific parameters
    """
    config = TargetedSearchConfig(level=level)
    searcher = [OperatorName]TargetedSearch(config)
    async for result in searcher.search(query, **params):
        yield result
```

---

## 5. Macro Template (Annual Report Only)

### **Standard Template for Macros**

```python
#!/usr/bin/env python3
"""
[Use Case] Macro
Combines multiple targeted searches for specific use case
"""

from __future__ import annotations
from typing import List, Dict, Any, AsyncGenerator
import asyncio

from targeted_searches.temporal.date import search_date
from targeted_searches.format.filetype import search_filetype
from targeted_searches.geographical.site import search_site
from targeted_searches.textual.intitle import search_intitle


class AnnualReportMacro:
    """
    [Use Case Description]
    
    Combines:
    - Date targeting (fiscal year window)
    - Filetype (PDF)
    - Site targeting (company domain + SEC)
    - Title targeting ("annual report")
    """
    
    def __init__(self, level: str = "L1"):
        self.level = level
    
    async def execute(
        self,
        **macro_params
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute multi-operator macro
        
        Args:
            **macro_params: Use-case specific parameters
        
        Yields:
            Deduplicated results from all operators
        """
        
        seen_urls = set()
        
        # Execute targeted searches required for annual report retrieval
        tasks = [
            self._search_filetype(macro_params),
            self._search_site(macro_params),
            self._search_intitle(macro_params),
        ]
        
        # Stream results as they arrive, deduplicate
        for coro in asyncio.as_completed(tasks):
            async for result in await coro:
                url = result.get('url')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    result['macro'] = self.__class__.__name__
                    result['macro_level'] = self.level
                    yield result
    
    async def _search_filetype(self, params: Dict) -> AsyncGenerator:
        """Fetch annual-report PDFs"""
        async for result in search_filetype(
            query=params['query'],
            filetypes=['pdf'],
            level=self.level
        ):
            yield result

    async def _search_site(self, params: Dict) -> AsyncGenerator:
        """Limit to company/SEC domains"""
        async for result in search_site(
            query=params['query'],
            sites=params.get('sites', []),
            level=self.level
        ):
            yield result

    async def _search_intitle(self, params: Dict) -> AsyncGenerator:
        """Focus on annual report phrasing"""
        async for result in search_intitle(
            query=params['query'],
            terms=['annual report', params.get('fiscal_year', '')],
            level=self.level
        ):
            yield result
```

---

## 6. Integration Points

### **A. Matrix Registry Updates**

**File:** `ROUTER/matrix_registry.py`

**Required Changes:**
1. Ensure all targeted searches have L1/L2/L3 mappings
2. Add any missing operators
3. Validate engine code mappings

### **B. Brute Search Integration (L3)**

**File:** `iii.OBJECT/Search_Types/brute.py` → Refactor

**Changes:**
1. Brute becomes the L3 backend for ALL targeted searches
2. Accept operator-specific filters
3. Stream to unified result format

**New Interface:**
```python
async def brute_search_with_filter(
    query: str,
    operator_type: str,
    filter_func: callable,
    **targeting_params
) -> AsyncGenerator:
    """
    Execute brute search across all engines
    Apply operator-specific post-filtering
    """
    # Run all 60+ engines
    # Stream results through filter_func
    # Yield only passing results
```

### **C. Frontend Streaming (JSON + SQL)**

**All targeted searches and macros must:**

1. **Save to SQL** via `ResultStorage`
```python
from Indexer.result_storage import ResultStorage

storage = ResultStorage()
await storage.save_result(result, query_id, metadata)
```

2. **Save to JSON** for frontend grid
```python
import json
from pathlib import Path

def save_to_json(result: Dict, query_id: str):
    output_file = Path(f"results/{query_id}.jsonl")
    with output_file.open('a') as f:
        f.write(json.dumps(result) + '\n')
```

3. **Stream via WebSocket** (if real-time)
```python
# WebSocket streaming handled by WEBAPP layer
# Targeted searches just yield results
```

### **D. Frontend Level Selector**

**Location:** `WEBAPP/` frontend components

**Add UI Controls:**
```html
<select id="search-level">
  <option value="L1">L1 - Fast (Native Support)</option>
  <option value="L2">L2 - Balanced (Native-Like + Filter)</option>
  <option value="L3">L3 - Maximum Recall (Brute + Filter)</option>
</select>
```

**Pass to API:**
```javascript
const searchConfig = {
  level: document.getElementById('search-level').value,
  query: query,
  // ... other params
}
```

---

## 7. Migration Steps

### **Phase 1: Create New Structure (Week 1)**
1. Create `targeted_searches/` folder hierarchy
2. Create `macros/` folder
3. Set up templates

### **Phase 2: Migrate Targeted Searches (Week 2-3)**
1. Start with high-value operators (date, site, filetype, etc.)
2. Refactor to 3L template
3. Add post-filtering logic for L2/L3
4. Test with matrix routing

### **Phase 3: Refactor Brute (Week 4)**
1. Update brute.py for L3 integration
2. Add operator-specific filter support
3. Ensure streaming compatibility

### **Phase 4: Annual Report Macro (Week 5)**
1. Implement annual report macro using targeted searches
2. Ensure compatibility with level selector
3. Test end-to-end

### **Phase 5: Frontend Integration (Week 6)**
1. Add level selector
2. Update API endpoints
3. Ensure JSON + SQL saving
4. Test streaming to grid

### **Phase 6: Deprecate Legacy (Week 7)**
1. Archive `Search_Types/` folder
2. Update all imports
3. Documentation updates

---

## 8. Example Implementations

### **Example 1: Date Targeted Search (3L)**

```python
# targeted_searches/temporal/date.py

class DateTargetedSearch:
    """Date range targeting with 3-level support"""
    
    async def _passes_filter(self, result: Dict, params: Dict) -> bool:
        """L2/L3: Filter results by date range"""
        if 'date' not in result:
            return False  # No date info, exclude
        
        result_date = parse_date(result['date'])
        start_date = parse_date(params.get('start_date'))
        end_date = parse_date(params.get('end_date'))
        
        return start_date <= result_date <= end_date
```

### **Example 2: Annual Report Macro**

```python
# macros/annual_report.py

class AnnualReportMacro:
    """
    Fetch annual reports for a company
    
    Combines:
    - Date targeting (fiscal year)
    - Filetype (PDF)
    - Site targeting (company domain + SEC)
    - Intitle ("annual report")
    """
    
    async def execute(
        self,
        company_name: str,
        fiscal_year: int,
        company_domain: str = None
    ):
        # Build search variations
        queries = [
            f'"{company_name}" "annual report" {fiscal_year}',
            f'"{company_name}" "10-K" {fiscal_year}',
            f'"{company_name}" "form 10-K" {fiscal_year}',
        ]
        
        sites = ['sec.gov']
        if company_domain:
            sites.append(company_domain)
        
        # Execute multi-operator search
        async for result in search_filetype(
            query=queries[0],
            filetypes=['pdf'],
            level=self.level
        ):
            # Also search with site targeting
            async for r2 in search_site(
                query=queries[0],
                sites=sites,
                level=self.level
            ):
                yield r2
```

---

## 9. Success Criteria

✅ **All Search_Types/ files categorized and migrated**  
✅ **Every targeted search implements 3L template**  
✅ **Matrix routing works for all operators**  
✅ **Brute search integrated as L3 backend**  
✅ **Frontend level selector functional**  
✅ **All results stream to JSON + SQL**  
✅ **At least 3 macros implemented**  
✅ **Documentation complete**

---

## 10. Next Steps

**IMMEDIATE:**
1. ✅ Create folder structure
2. ✅ Start with critical operators (date, site, filetype)
3. ✅ Refactor brute.py for L3

**THIS WEEK:**
4. Migrate 10+ high-priority targeted searches
5. Create first macro (annual_report)
6. Update matrix_registry.py

**NEXT WEEK:**
7. Complete targeted search migrations
8. Frontend integration
9. End-to-end testing

---

**END OF REFACTORING PLAN**

