# LINKLATER Similar Content - Implementation Complete

**Date:** 2026-01-07
**Status:** ✅ IMPLEMENTED - Similar content now in LINKLATER

---

## What Was Changed

### ❌ REMOVED: Standalone similar.py bridge
- **Was:** `/data/ALLDOM/bridges/similar.py` (2.1KB) - standalone bridge
- **Reason:** Similar content is a LINKING operation, belongs in LINKLATER

### ✅ ADDED: Similar content in LINKLATER

**File:** `/data/LINKLATER/discovery/similar_discovery.py` (9.7KB)

**Features:**
- **Exa API integration** - LLM embedding-based similarity
- **CLINK integration** - Entity-based related sites (uses `/data/CLASSES/NEXUS/clink.py`)
- **Two methods with fallback:**
  - `find_similar_exa()` - Primary method via Exa
  - `find_similar_clink()` - Fallback via entity matching
- **Unified interface:** `find_similar()`, `find_similar_all()`

**Classes:**
```python
@dataclass
class SimilarSite:
    url: str
    domain: str
    title: str = ""
    score: float = 0.0  # Similarity score
    source: str = ""     # "exa" or "clink"
    metadata: Dict[str, Any] = None

class SimilarContentDiscovery:
    async def find_similar_exa()     # Exa API method
    async def find_similar_clink()   # CLINK entity method
    async def find_similar()         # Unified with fallback
    async def find_similar_all()     # All methods in parallel
```

---

## LINKLATER Architecture

LINKLATER now handles ALL link-related operations:

| Operation | Operator | Bridge Method | Implementation |
|-----------|----------|---------------|----------------|
| **Backlinks** | `bl?`, `?bl` | `linklater.backlinks()` | `/data/LINKLATER/linkgraph/backlinks.py` |
| **Outlinks** | `ol?`, `!ol` | `linklater.outlinks()` | `/data/LINKLATER/linkgraph/` |
| **Similar Content** | `similar:` | `linklater.similar()` | `/data/LINKLATER/discovery/similar_discovery.py` |

---

## ALLDOM Integration

### Updated Files:

**1. `/data/ALLDOM/alldom.py`**
Added operator route:
```python
OPERATOR_ROUTES = {
    # ...
    "similar:": ("linklater", "similar"),
    # ...
}
```

**2. `/data/ALLDOM/bridges/linklater.py`**
Added similar content methods:
```python
async def similar(url: str, limit: int = 20, method: str = "exa", **kwargs)
async def similar_all(url: str, limit: int = 20, **kwargs)
async def related_sites(domain_or_url: str, limit: int = 20, **kwargs)  # Alias
```

**3. `/data/ALLDOM/bridges/__init__.py`**
Removed `similar` from exports (now in linklater)

**4. `/data/LINKLATER/discovery/__init__.py`**
Added exports:
```python
from .similar_discovery import SimilarContentDiscovery, find_similar, find_similar_all
```

---

## CLINK Integration

LINKLATER's similar content uses **CLINK** (`/data/CLASSES/NEXUS/clink.py`) as a fallback method.

**CLINK (Chain Link Entity Discovery):**
- Extracts entities from target URL
- Searches for sites mentioning same entities
- Uses BRUTE's fast_search for multi-engine discovery
- Returns sites ranked by entity overlap

**Flow:**
```
Target URL → JESTER scrape → Extract entities → CLINK search → Related sites
```

**Example:**
```python
# Target: https://anthropic.com
# Entities: ["Claude", "Anthropic", "AI Safety", "Dario Amodei"]
# CLINK finds: Sites mentioning Claude + Anthropic + AI Safety
# Result: Related AI safety research sites, news articles, etc.
```

---

## Usage Examples

### Via ALLDOM Operator:
```python
from modules.ALLDOM import AllDom

ad = AllDom()
result = await ad.execute("similar:https://anthropic.com")
# Returns: List of similar sites with scores
```

### Direct LINKLATER Usage:
```python
from modules.LINKLATER.discovery import find_similar

# Exa method (default)
sites = await find_similar("https://anthropic.com", limit=20)

# CLINK method
sites = await find_similar("https://anthropic.com", prefer_method="clink")

# All methods in parallel
results = await find_similar_all("https://anthropic.com")
# Returns: {"exa": [...], "clink": [...]}
```

### CLI:
```bash
# Via LINKLATER discovery
python3 /data/LINKLATER/discovery/similar_discovery.py https://anthropic.com 20

# Via ALLDOM (when integrated)
python3 /data/ALLDOM/alldom.py similar:https://anthropic.com
```

---

## Operator Summary - Final State

| Operator | Bridge | Method | Location |
|----------|--------|--------|----------|
| `bl?`, `?bl` | linklater | backlinks() | /data/LINKLATER/linkgraph/ |
| `ol?`, `!ol` | linklater | outlinks() | /data/LINKLATER/linkgraph/ |
| `similar:` | linklater | similar() | /data/LINKLATER/discovery/ |
| `keyword:` | keyword | search_keyword() | /data/ALLDOM/bridges/ |
| `?:` | ai_qa | ask_question() | /data/ALLDOM/bridges/ |
| `ga!` | macros | ga() | /data/ALLDOM/bridges/ (existing) |

---

## Testing

### Test Similar Content:
```bash
# Test Exa method
python3 -c "
import asyncio
from modules.LINKLATER.discovery import find_similar
print(asyncio.run(find_similar('https://anthropic.com', limit=10)))
"

# Test CLINK method
python3 -c "
import asyncio
from modules.LINKLATER.discovery import find_similar
print(asyncio.run(find_similar('https://anthropic.com', prefer_method='clink')))
"

# Test all methods
python3 -c "
import asyncio
from modules.LINKLATER.discovery import find_similar_all
print(asyncio.run(find_similar_all('https://anthropic.com')))
"
```

### Test via ALLDOM:
```bash
python3 -c "
import asyncio
from modules.ALLDOM import AllDom
ad = AllDom()
print(asyncio.run(ad.execute('similar:https://anthropic.com')))
"
```

---

## Dependencies

All dependencies already exist on Sastre:
- ✅ `modules.brute.engines.exa.ExaEngine` - Exa API
- ✅ `CLASSES.NEXUS.clink.CLINK` - Entity-based discovery
- ✅ `modules.JESTER` - Scraping
- ✅ `modules.alldom.utils.entity_extraction` - Entity extraction

**No new packages required.**

---

## Files Modified/Created

**Created:**
- `/data/LINKLATER/discovery/similar_discovery.py` (9.7KB)

**Modified:**
- `/data/LINKLATER/discovery/__init__.py` - Added similar exports
- `/data/ALLDOM/bridges/linklater.py` - Added similar() methods
- `/data/ALLDOM/alldom.py` - Added `similar:` route
- `/data/ALLDOM/bridges/__init__.py` - Removed standalone similar

**Removed:**
- `/data/ALLDOM/bridges/similar.py` - Moved to LINKLATER

---

## Architecture Rationale

**Why LINKLATER?**

LINKLATER is Sastre's **"related site module"** - it handles all operations that discover relationships between sites:

1. **Backlinks** - Sites linking TO target
2. **Outlinks** - Sites linked FROM target
3. **Similar content** - Sites LIKE target

All three are link/relationship operations → All belong in LINKLATER.

**Not standalone bridges** - They're part of the unified LINKLATER discovery system.

---

**Implementation by:** Claude
**Verified:** 2026-01-07 21:15 UTC
