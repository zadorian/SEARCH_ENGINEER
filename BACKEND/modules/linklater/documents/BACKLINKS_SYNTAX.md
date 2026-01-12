# LinkLater Backlinks Discovery - Syntax Guide

## Overview

LinkLater provides deterministic backlink discovery with 4 query modes using intuitive syntax:

```
?bl  = Fast (domains only)
bl?  = Rich (pages with enrichment)

!domain  = Target is a domain
domain!  = Target is a specific URL
```

---

## The 4 Query Modes

### 1. `?bl !domain` - Referring Domains Only (FAST)

**Speed:** ~100ms
**Data:** Domain list with link weights
**Sources:** CC Domain Graph ES + Tor Bridges

```python
from linklater.backlinks import get_backlinks_domains

# Get domains linking to soax.com
result = await get_backlinks_domains("soax.com")

# Result structure:
# {
#   "target": "soax.com",
#   "target_type": "domain",
#   "domains": [
#     {"source": "example.com", "weight": 47},
#     {"source": "test.com", "weight": 23},
#     ...
#   ],
#   "summary": {
#     "total": 52,
#     "sources": {"cc_graph": 52, "tor_bridges": 0}
#   },
#   "execution_time_ms": 553.18
# }
```

**CLI:**
```bash
python3 backlinks.py "?bl" "!soax.com"
```

---

### 2. `bl? !domain` - Referring Pages with Enrichment (RICH)

**Speed:** ~30-60s
**Data:** Page URLs + anchor text + Trust/Citation Flow
**Sources:** CC Graph ES → GlobalLinks → Majestic → Tor

```python
from linklater.backlinks import get_backlinks_pages

# Get pages linking to soax.com with anchor text
result = await get_backlinks_pages("soax.com", top_domains=20)

# Result structure:
# {
#   "target": "soax.com",
#   "target_type": "domain",
#   "pages": [
#     {
#       "source": "https://example.com/article.html",
#       "target": "https://soax.com",
#       "anchor_text": "SOAX proxy service",
#       "provider": "globallinks"
#     },
#     {
#       "source": "https://test.com/review",
#       "target": "https://soax.com",
#       "anchor_text": "residential proxies",
#       "trust_flow": 45,
#       "citation_flow": 38,
#       "provider": "majestic"
#     },
#     ...
#   ],
#   "summary": {
#     "total": 237,
#     "sources": {
#       "cc_graph": 52,
#       "globallinks": 189,
#       "majestic": 48,
#       "tor_bridges": 0
#     }
#   },
#   "execution_time_ms": 31245.67
# }
```

**CLI:**
```bash
python3 backlinks.py "bl?" "!soax.com"
```

---

### 3. `?bl domain!` - Referring Domains to Specific URL (FAST)

**Speed:** ~100ms
**Use Case:** Find who links to a specific page

```python
# Get domains linking to soax.com/pricing
result = await get_backlinks_domains("soax.com/pricing")

# Target type will be "url" instead of "domain"
```

**CLI:**
```bash
python3 backlinks.py "?bl" "soax.com/pricing!"
```

---

### 4. `bl? domain!` - Referring Pages to Specific URL (RICH)

**Speed:** ~30-60s
**Use Case:** Full enrichment for specific URL backlinks

```python
# Get pages linking to soax.com/pricing with anchor text
result = await get_backlinks_pages("soax.com/pricing", top_domains=20)
```

**CLI:**
```bash
python3 backlinks.py "bl?" "soax.com/pricing!"
```

---

## Pipeline Details

### Fast Path (?bl) - Domains Only

```
1. CC Domain Graph ES (100ms)
   → Query: domains linking TO target
   → Returns: 1000 domains with link weights

2. Tor Bridges (100ms)
   → Query: .onion domains linking to target
   → Returns: Dark web sources

3. Deduplicate and return
```

### Rich Path (bl?) - Pages with Enrichment

```
1. CC Domain Graph ES (100ms)
   → Get referring domains

2. Sort by Weight (instant)
   → Take top 20 domains by link weight

3. GlobalLinks Extraction (5-30s per domain)
   → For each top domain:
     - Download Common Crawl WAT files
     - Extract page URLs linking to target
     - Get anchor text and context
   → Parallel processing

4. Majestic API (5s)
   → Get Trust Flow / Citation Flow scores
   → Fresh backlinks (90 days)
   → Anchor text enrichment

5. Tor Bridges (100ms)
   → Add dark web sources

6. Combine, deduplicate, return
```

---

## Configuration Options

### For `get_backlinks_domains()` (?bl)

```python
result = await get_backlinks_domains(
    target="soax.com",
    limit=1000,              # Max results (default: 1000)
    min_weight=1,            # Minimum link weight (default: 1)
    include_tor=True         # Include Tor bridges (default: True)
)
```

### For `get_backlinks_pages()` (bl?)

```python
result = await get_backlinks_pages(
    target="soax.com",
    limit=100,               # Max total results (default: 100)
    top_domains=20,          # How many top domains to enrich (default: 20)
    include_majestic=True,   # Use Majestic API (default: True)
    include_anchor_text=True, # Extract anchor text (default: True)
    include_tor=True,        # Include Tor bridges (default: True)
    archive="CC-MAIN-2024-10" # Common Crawl archive (default: latest)
)
```

---

## MCP Server Usage

The MCP server exposes the same syntax to AI assistants:

```json
{
  "name": "linklater_backlinks",
  "arguments": {
    "syntax": "?bl",
    "target": "!soax.com",
    "limit": 100
  }
}
```

Or:

```json
{
  "name": "linklater_backlinks",
  "arguments": {
    "syntax": "bl?",
    "target": "!soax.com",
    "top_domains": 20,
    "include_majestic": true
  }
}
```

---

## Data Sources

### CC Domain Graph ES
- **Size:** 435M edges, 100M domains
- **Speed:** ~100ms per query
- **Data:** Domain-to-domain relationships with weights
- **Index:** `cymonides_cc_domain_edges`, `cymonides_cc_domain_vertices`

### GlobalLinks (Go Binary)
- **Location:** `categorizer-filterer/globallinks/globallinks-with-outlinker/bin/outlinker`
- **Speed:** 5-30s per domain extraction
- **Data:** Page URLs, anchor text, link context from Common Crawl WAT files
- **Archives:** All CC archives available (monthly releases)

### Majestic API
- **Requires:** MAJESTIC_API_KEY environment variable
- **Speed:** ~5s per query
- **Data:** Trust Flow, Citation Flow, fresh + historic backlinks
- **Modes:** Fresh (90 days) or Historic (5 years)

### Tor Bridges
- **Index:** `tor-bridges`
- **Speed:** ~100ms per query
- **Data:** .onion → clearnet links extracted by TorCrawler

---

## Test Results

### Test: `?bl !soax.com`
```
✅ SUCCESS
Execution time: 553ms
Results: 52 referring domains
Sources: CC Graph (52), Tor Bridges (0)
```

Sample domains found:
- adverank.ai
- crayo.ai
- thewebscraping.club
- scrapingproxies.best
- (and 48 more...)

---

## Architecture

### Deterministic Python Core
- **File:** `backlinks.py`
- **Class:** `BacklinkDiscovery`
- **Functions:** `get_referring_domains()`, `get_referring_pages()`

### Thin MCP Wrapper
- **File:** `mcp_server.py`
- **Purpose:** Expose syntax to AI assistants
- **Protocol:** JSON-RPC over stdio

### Direct Python Usage

```python
# Import
from linklater.backlinks import backlinks

# Use unified function with syntax
result = await backlinks("?bl", "!soax.com")
result = await backlinks("bl?", "!soax.com", top_domains=20)

# Or use specific functions
from linklater.backlinks import get_backlinks_domains, get_backlinks_pages

domains = await get_backlinks_domains("soax.com")
pages = await get_backlinks_pages("soax.com", top_domains=20)
```

---

## Performance Targets

| Query Mode | Speed | Data Volume | Use Case |
|------------|-------|-------------|----------|
| `?bl !domain` | 100ms | 1000 domains | Quick overview, domain discovery |
| `bl? !domain` | 30-60s | 100-500 pages | SEO analysis, anchor text research |
| `?bl domain!` | 100ms | Filtered domains | URL-specific backlink analysis |
| `bl? domain!` | 30-60s | Filtered pages | Deep URL backlink intel |

---

## Error Handling

All functions return structured errors:

```python
{
  "error": "Invalid syntax: xyz. Must be '?bl' or 'bl?'",
  "target": "soax.com",
  "execution_time_ms": 5.23
}
```

---

## Extended Syntax (2025-12-06)

### Topic Filtering: `bl[topic]?`

Filter backlinks by topic category:

```bash
bl[news]? example.com      # News/media backlinks only
bl[tech]? example.com      # Technology backlinks only
bl[business]? example.com  # Business backlinks only
```

**How it works:**
- **Majestic:** Uses native `FilterTopic` parameter (562 categories)
- **CC/Linklater:** Results processed through categorizer pipeline (100M+ domain taxonomy)

**Available topic categories:**
| Category ID | Label | Keywords |
|-------------|-------|----------|
| `news_media` | News & Media | news, journalism, newspaper, magazine |
| `tech` | Technology | tech, programming, software, ai, coding |
| `business` | Business | business, corporate, finance, startup |
| `shopping` | Shopping & E-commerce | shopping, ecommerce, store, retail |
| `entertainment` | Arts & Entertainment | entertainment, movies, music, games |
| `research` | Research & Academic | research, academic, science, library |
| `health` | Health & Medical | health, medical, medicine, wellness |
| `sports` | Sports | sports, football, soccer, basketball |
| `education` | Education | education, school, learning, university |
| `public_records` | Public Records | court, registry, regulatory, bankruptcy |
| `social` | Social Media & Forums | social media, forum, community |
| `regional` | Regional & Local | regional, local, travel, tourism |
| `society` | Society & Culture | society, law, government, politics |

---

### Filetype Filtering: `bl[filetype]?`

Filter backlinks by URL extension:

```bash
bl[pdf]? example.com       # PDF backlinks only
bl[doc]? example.com       # Word doc backlinks only
bl[xls]? example.com       # Excel backlinks only
bl[pdf!]? example.com      # PDF only (exclusive mode)
```

**Supported filetypes:**
- Documents: `pdf`, `doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`, `csv`, `txt`, `rtf`, `odt`
- Data: `xml`, `json`
- Web: `html`, `htm`
- Archives: `zip`, `rar`, `gz`
- Media: `mp3`, `mp4`, `avi`, `mov`, `jpg`, `jpeg`, `png`, `gif`, `svg`, `webp`

---

### Streaming Endpoint

**Endpoint:** `GET /api/backlinks/stream`

Results stream in real-time as they arrive from each source:

```
1. Majestic results → stream immediately (fast, native topic filter)
2. CC/Linklater → fetch → categorize → filter → stream
```

**SSE Events:**
| Event | Data |
|-------|------|
| `source_start` | `{ source: "majestic" }` |
| `backlink` | Individual result object |
| `categorizing` | `{ source: "linklater", count: 150 }` |
| `source_complete` | `{ source: "majestic", count: 75 }` |
| `complete` | Final summary with totals |

---

## Next Steps

1. ✅ Test `?bl !domain` (DONE - 553ms, 52 results)
2. ⏳ Test `bl? !domain` (TODO - full enrichment)
3. ⏳ Test URL variants (`?bl domain!`, `bl? domain!`)
4. ⏳ Register MCP server in `.claude/mcp_config.json`
5. ⏳ Add to LinkLater unified API (`api.py`)
6. ✅ Topic filtering (`bl[news]?`) - DONE 2025-12-06
7. ✅ Filetype filtering (`bl[pdf]?`) - DONE 2025-12-06
8. ✅ Streaming endpoint - DONE 2025-12-06

---

**The emphasis is on deterministic Python functions, not MCP.**
The MCP server just exposes the syntax to AI.
