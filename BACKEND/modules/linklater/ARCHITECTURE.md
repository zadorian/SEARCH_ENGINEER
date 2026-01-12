# LINKLATER Architecture

**Web investigation, link analysis, and archive research system.**

Last updated: 2026-01-06

---

## Overview

LINKLATER is a comprehensive link intelligence platform combining:
- **Majestic API** for backlink discovery
- **WHOIS** for domain clustering and registration analysis
- **CommonCrawl** for historical content scanning
- **Multi-tier scraping** (httpx → Colly → Rod → Playwright)
- **Entity extraction** (GLiNER, GPT, Gemini, Haiku, Regex)

---

## Module Structure (159 Python files)

```
LINKLATER/
├── api.py                 # Main API interface (58KB)
├── cli.py                 # Command-line interface
├── backlinks.py          # Backlink discovery wrapper
├── graph_index.py        # Link graph indexing
│
├── discovery/            # Domain/link discovery
│   ├── majestic_discovery.py   # ✅ Majestic API (backlinks, trust flow)
│   ├── whois_discovery.py      # ✅ WHOIS lookup & clustering
│   ├── tech_discovery.py       # Technology stack detection
│   ├── filetype_discovery.py   # PDF/DOC/XLS file finding
│   └── unified_discovery_engine.py
│
├── scraping/             # Multi-tier scraping system
│   ├── web/
│   │   ├── crawler.py         # Drill/DrillConfig
│   │   ├── go_bridge.py       # GoBridge for Colly/Rod
│   │   └── go/
│   │       ├── bin/           # Compiled Go binaries
│   │       │   ├── colly_crawler   # JESTER_B (500 concurrent)
│   │       │   ├── rod_crawler     # JESTER_C (JS rendering)
│   │       │   └── cclinks         # CommonCrawl links
│   │       └── cmd/           # Go source code
│   ├── historical/            # Archive.org/Wayback
│   └── tor/                   # Tor hidden services
│
├── extraction/           # Entity extraction backends
│   ├── backends/
│   │   ├── gpt.py            # OpenAI GPT extraction
│   │   ├── gemini.py         # Google Gemini extraction
│   │   ├── haiku.py          # Claude Haiku extraction
│   │   ├── gliner.py         # Local GLiNER NER
│   │   └── regex.py          # Fast regex patterns
│   ├── entity_extractor.py   # Main extractor
│   ├── universal_extractor.py
│   └── ontology.py           # Entity type definitions
│
├── archives/             # Historical content access
│   ├── cc_index_client.py    # CommonCrawl CDX API
│   ├── hybrid_archive.py     # CC + Wayback combined
│   ├── optimal_archive.py    # Smart archive selection
│   ├── fast_scanner.py       # High-speed scanning
│   └── snapshot_differ.py    # Temporal diff analysis
│
├── enrichment/           # Content enrichment
│   ├── cc_enricher.py        # CommonCrawl enrichment
│   ├── entity_patterns.py    # Pattern matching
│   ├── entity_timeline.py    # Temporal analysis
│   ├── query_variations.py   # Query expansion
│   └── universal_enricher.py
│
├── linkgraph/            # Graph operations
│   ├── backlinks.py          # Backlink graph
│   └── globallinks.py        # Global link database
│
├── mapping/              # Domain mapping
│   ├── domain_filters.py     # Domain categorization
│   └── keyword_variations.py # Search variations
│
├── mcp/                  # MCP server integration
├── mcp_internal/         # Internal MCP tools
│
├── pipelines/            # Processing pipelines
├── scoring/              # Relevance scoring
├── search/               # Search operations
├── temporal/             # Time-based analysis
├── alerts/               # Link change alerts
├── watchers/             # Automated monitoring
└── utils/                # Utilities
```

---

## Core Components

### 1. Discovery Engine

```
┌─────────────────────────────────────────────────────────────┐
│                    UNIFIED DISCOVERY                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐ │
│  │ Majestic │   │   WHOIS   │   │   Tech   │   │Filetype │ │
│  │ Backlinks│   │ Clustering│   │ Discovery│   │ Scanner │ │
│  └────┬─────┘   └─────┬─────┘   └────┬─────┘   └────┬────┘ │
│       │               │              │              │       │
│       └───────────────┴──────────────┴──────────────┘       │
│                           │                                 │
│                    ┌──────▼──────┐                         │
│                    │ Link Graph  │                         │
│                    │   Index     │                         │
│                    └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### 2. Majestic Integration

```python
from LINKLATER.discovery.majestic_discovery import (
    get_backlink_data,      # Trust/citation flow, counts
    get_related_sites,      # Similar domains
    get_ref_domains,        # Referring domains
    get_topics              # Topic classification
)

# Get backlinks for a domain
result = await get_backlink_data("github.com")
# Returns: MajesticDiscoveryResponse with BacklinkResult[]
#   - source_url, target_url, anchor_text
#   - trust_flow, citation_flow
#   - first_seen, source_domain
```

### 3. WHOIS Discovery

```python
from LINKLATER.discovery.whois_discovery import (
    whois_lookup,           # Single domain lookup
    cluster_domains_by_whois # Group by registrant
)

# Lookup domain registration
record = await whois_lookup("example.com")
# Returns: WhoisRecord with:
#   - registrar, created_date, expiry_date
#   - registrant_name, registrant_org
#   - nameservers

# Cluster related domains
clusters = await cluster_domains_by_whois(["a.com", "b.com", "c.com"])
# Groups domains by registrant/org/nameserver similarity
```

### 4. Multi-Tier Scraping

```
┌───────────────────────────────────────────────────────────────────┐
│                      SCRAPING TIERS                               │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Tier A (httpx)     Tier B (Colly)    Tier C (Rod)    Tier D     │
│  ┌──────────┐       ┌──────────┐      ┌──────────┐   ┌─────────┐ │
│  │  Python  │ FAIL  │    Go    │ FAIL │ Go + JS  │   │Playwright│ │
│  │  async   │──────▶│  static  │─────▶│  render  │──▶│ fallback│ │
│  │ ~60% ok  │       │ 500 conc │      │ 100 conc │   │   50    │ │
│  └──────────┘       └──────────┘      └──────────┘   └─────────┘ │
│                                                                   │
│  Cost: FREE         Cost: FREE        Cost: FREE     Cost: FREE  │
└───────────────────────────────────────────────────────────────────┘
```

### 5. Entity Extraction

```
┌───────────────────────────────────────────────────────────────────┐
│                    EXTRACTION BACKENDS                            │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │  Regex  │  │ GLiNER  │  │   GPT   │  │ Gemini  │  │  Haiku  │ │
│  │  ~5ms   │  │  ~100ms │  │  ~800ms │  │  ~600ms │  │  ~400ms │ │
│  │  FREE   │  │  FREE   │  │  $0.002 │  │  $0.001 │  │  $0.001 │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘ │
│       │            │            │            │            │       │
│       └────────────┴────────────┴────────────┴────────────┘       │
│                               │                                   │
│                      ┌────────▼────────┐                         │
│                      │ Universal       │                         │
│                      │ Extractor       │                         │
│                      └─────────────────┘                         │
│                               │                                   │
│                ┌──────────────┴──────────────┐                   │
│                │     Entity Types:           │                   │
│                │ • person • company • email  │                   │
│                │ • phone  • address • LEI    │                   │
│                │ • IBAN   • crypto  • URL    │                   │
│                └─────────────────────────────┘                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## API Usage

### Main API

```python
import sys
sys.path.insert(0, "/data")

from LINKLATER import api

# Or import specific functions:
from LINKLATER.discovery.majestic_discovery import get_backlink_data
from LINKLATER.discovery.whois_discovery import whois_lookup
from LINKLATER.scraping.web.go_bridge import GoBridge
```

### Full Investigation Flow

```python
from LINKLATER.discovery import majestic_discovery, whois_discovery
from LINKLATER.archives import hybrid_archive
from LINKLATER.extraction import entity_extractor

async def investigate_domain(domain: str):
    # 1. Get backlink profile
    backlinks = await majestic_discovery.get_backlink_data(domain)
    
    # 2. Get WHOIS data
    whois = await whois_discovery.whois_lookup(domain)
    
    # 3. Find related domains
    related = await majestic_discovery.get_related_sites(domain)
    
    # 4. Get historical snapshots
    snapshots = await hybrid_archive.get_snapshots(domain)
    
    # 5. Extract entities from content
    entities = await entity_extractor.extract(content)
    
    return {
        "backlinks": backlinks,
        "whois": whois,
        "related": related,
        "history": snapshots,
        "entities": entities
    }
```

---

## Environment Variables

Required API keys (stored in /etc/environment):

| Variable | Service | Purpose |
|----------|---------|---------|
| `MAJESTIC_API_KEY` | Majestic.com | Backlink data |
| `WHOIS_API_KEY` | WhoisXMLAPI | WHOIS lookups |
| `OPENAI_API_KEY` | OpenAI | GPT extraction |
| `ANTHROPIC_API_KEY` | Anthropic | Haiku extraction |
| `GOOGLE_API_KEY` | Google | Gemini extraction |

---

## Go Binaries

Located in `/data/LINKLATER/scraping/web/go/bin/`:

| Binary | Purpose | Concurrency |
|--------|---------|-------------|
| `colly_crawler` | Static HTML scraping (JESTER_B) | 500 |
| `rod_crawler` | JS rendering (JESTER_C) | 100 |
| `cclinks` | CommonCrawl link extraction | 1000 |

---

## Integration Points

### With JESTER (via bridge)

```python
# JESTER uses LINKLATER scraping tiers:
from LINKLATER.scraping.web.go_bridge import GoBridge

bridge = GoBridge()
result = await bridge.scrape_colly(url)  # JESTER_B
result = await bridge.scrape_rod(url)    # JESTER_C
```

### With PACMAN (entity extraction)

```python
# PACMAN can use LINKLATER extractors:
from LINKLATER.extraction.backends.regex import RegexBackend
from LINKLATER.extraction.backends.gliner import GLiNERBackend
```

### With CYMONIDES (via bridge)

```python
# For corpus search across extracted entities:
from LINKLATER.cymonides_bridge import search_entities
```

---

## Status

- ✅ Majestic API (backlinks, trust flow, related sites)
- ✅ WHOIS discovery (lookup, clustering)
- ✅ Multi-tier scraping (httpx, Colly, Rod)
- ✅ Entity extraction (5 backends)
- ✅ CommonCrawl integration
- ✅ Archive hybrid search
- ⏳ Tech discovery (needs API keys)
- ⏳ Filetype discovery (operational)
