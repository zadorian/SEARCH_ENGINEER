# INDOM Implementation TODO

**Status:** PLANNED - Not yet implemented on Sastre
**Target Location:** `/data/brute/targeted_searches/domain/indom.py`
**Priority:** MEDIUM
**Date Added:** 2026-01-07

---

## What INDOM Does

**InDOM** (Inbound Domain Search) = Keyword-based domain discovery.

**Example:** Searching "tesla" finds tesla.com, teslashop.com, teslamotors.com, etc.

**Use Case:** Discover all domains containing specific keywords/brand names.

---

## Current Status

Sastre has:
- ✅ `/data/brute/targeted_searches/domain/indom.py` (279 lines) - **WRAPPER ONLY**
- ❌ Missing: Actual InDOM multi-source implementation

The current `indom.py` is a thin wrapper that imports:
- `InDOMSearch` (from specialist_sources/url_dom_search/indom)
- `DomainFTS5Search` (from domain_fts5_search)
- `ATLAS` domain list

**Problem:** These underlying modules don't exist on Sastre.

---

## What Needs to be Implemented

### 1. Multi-Source Domain Discovery

**Local has:** `/BACKEND/modules/DomScan/AllDomain_Mapper/backend/indom/search.py` (23KB)

**Features:**
- **7 Data Sources:**
  - Google Custom Search API
  - Bing Search API
  - Brave Search API
  - WhoisXML API (reverse domain search)
  - Wayback Machine (domain archives)
  - CommonCrawl (domain index)
  - Ahrefs API (domain database)

- **Performance Optimizations:**
  - Async/await with connection pooling
  - 100 concurrent connections
  - 10 connections per host
  - Early termination when enough results found
  - DNS caching

- **Smart Features:**
  - Domain variation generation (TLDs, extensions)
  - Language-specific search (18 languages)
  - Market code targeting (12 Bing markets)
  - Spam filtering
  - Keyword validation

### 2. Configuration System

**Local has:** `/BACKEND/modules/DomScan/AllDomain_Mapper/backend/indom/config.py` (4.8KB)

**Features:**
- API key auto-detection (enable sources only if keys available)
- Source availability checking
- Performance settings (timeouts, limits, concurrency)
- Domain variation rules
- Country TLD lists (40+ countries)

### 3. Spam Filtering

**Local has:** `/BACKEND/modules/DomScan/AllDomain_Mapper/backend/indom/spam_filter.py` (3.2KB)

**Features:**
- Spam domain detection
- Blacklist filtering
- Pattern-based spam identification

---

## Integration Plan

### Phase 1: Core Implementation (Week 1)
1. Port `search.py` from Local to Sastre
2. Port `config.py` from Local to Sastre
3. Port `spam_filter.py` from Local to Sastre
4. Update `/data/brute/targeted_searches/domain/indom.py` to use new implementation

### Phase 2: API Integration (Week 2)
1. Verify API keys in Sastre's `.env`:
   - `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`
   - `BING_API_KEY`
   - `BRAVE_API_KEY`
   - `WHOISXML_API_KEY`
   - `AHREFS_API_KEY`
2. Test each source individually
3. Implement graceful degradation (disable sources with missing keys)

### Phase 3: Testing & Optimization (Week 3)
1. Test keyword searches across all sources
2. Benchmark performance (target: <10s for 100+ results)
3. Tune concurrency limits
4. Test spam filtering effectiveness

### Phase 4: Integration with BRUTE (Week 4)
1. Register INDOM as targeted search type in BRUTE
2. Add to BRUTE's search type registry
3. Update BRUTE CLI to support `indom:keyword` syntax
4. Add BRUTE web interface support

---

## File Locations

### Local (Reference):
```
/Users/attic/01. DRILL_SEARCH/drill-search-app/BACKEND/modules/DomScan/AllDomain_Mapper/backend/indom/
├── __init__.py (241 bytes)
├── config.py (4.8KB) - API keys, sources, performance settings
├── search.py (23KB) - Multi-source async discovery
└── spam_filter.py (3.2KB) - Domain filtering
```

### Sastre (Target):
```
/data/brute/targeted_searches/domain/
├── indom.py (279 lines) - Current wrapper
└── (NEW) indom/
    ├── __init__.py
    ├── config.py - Port from Local
    ├── search.py - Port from Local
    └── spam_filter.py - Port from Local
```

---

## Dependencies

**Python Packages:**
- `aiohttp` - Async HTTP client
- `tenacity` - Retry logic
- Already available: `re`, `logging`, `asyncio`, `urllib.parse`

**API Keys Required:**
- Google Custom Search (optional but recommended)
- Bing Search (optional but recommended)
- Brave Search (optional but recommended)
- WhoisXML (optional)
- Ahrefs (optional)

**Fallback:** Wayback and CommonCrawl always available (no API keys needed)

---

## Expected Outcome

After implementation:
- ✅ `brute indom:tesla` discovers all domains containing "tesla"
- ✅ Multi-source parallel discovery (7 sources)
- ✅ Spam filtering removes junk domains
- ✅ Fast performance (~5-10s for 100+ results)
- ✅ Graceful degradation when API keys missing
- ✅ Integration with BRUTE's existing infrastructure

---

## Notes

- This is a **targeted search type**, not a general ALLDOM operator
- INDOM is keyword-based discovery, different from ALLDOM's domain mapping
- Local's implementation is production-ready and proven
- Estimated effort: 2-3 weeks for full implementation and testing

---

**Author:** Claude (via comparison analysis)
**Last Updated:** 2026-01-07
