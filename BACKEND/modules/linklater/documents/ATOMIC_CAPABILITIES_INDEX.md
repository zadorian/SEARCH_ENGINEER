# LinkLater Atomic Capabilities Index

**Authoritative reference of what each file can do.**

---

## Core API Files

### `api.py` - Unified LinkLater API
**Location:** `/modules/linklater/api.py`

**Singleton Instance:** `linklater` (pre-initialized)

**Capabilities:**

```python
from modules.linklater.api import linklater

# BACKLINKS
await linklater.get_backlinks(domain, limit=100, use_globallinks=False)
# → Returns: List[LinkRecord]
# → Sources: CC Graph only (use_globallinks=False) or CC Graph + GlobalLinks
# → Speed: Fast (domain-level aggregates)

await linklater.get_majestic_backlinks(
    domain,
    mode="fresh",           # "fresh" (90d) or "historic" (5y)
    result_type="pages",    # "pages" or "domains"
    max_results=1000
)
# → Returns: List[Dict] with anchor_text, trust_flow, citation_flow
# → Sources: Majestic Fresh or Historic Index
# → Speed: Fast (API call)

# HISTORICAL ARCHIVES
async for result in linklater.search_archives(
    domain="example.com",
    keyword="libya OR libyan",
    start_year=2008,
    end_year=2024
):
    # → Yields: Dict with url, timestamp, snippet
    # → Sources: Common Crawl historical archives
    # → Speed: Slow (iterates through years)

# SCRAPING
result = await linklater.scrape_url("https://example.com")
# → Returns: Object with .content, .status_code, .source
# → Sources: Live web scraping
# → Speed: Fast (single page)

# ENTITY EXTRACTION
entities = linklater.extract_entities(text)
# → Returns: Dict with 'companies', 'persons', etc.
# → Sources: NER on provided text
# → Speed: Fast (local processing)

# WAYBACK MACHINE
content = await linklater.fetch_from_wayback("https://example.com")
# → Returns: String (archived HTML)
# → Sources: Internet Archive Wayback Machine
# → Speed: Medium (external API)

# CC INDEX
index_data = await linklater.check_cc_index("https://example.com")
# → Returns: Dict with url, timestamp, archive info
# → Sources: Common Crawl CDX Server API
# → Speed: Fast (API call)
```

---

## Discovery Modules

### `discovery/domain_filters.py` - Domain Discovery & Filtering
**Location:** `/modules/linklater/discovery/domain_filters.py`

**Imports from:** `/categorizer-filterer/` (CLIs stay in original location)

**Capabilities:**

```python
from modules.linklater.api import linklater

# Initialize domain filters (loads API keys from env)
linklater.init_domain_filters()

# PARALLEL DISCOVERY (all sources simultaneously)
discovered = await linklater.discover_domains_parallel(
    tlds=['.ly'],
    keywords=['libya', 'tripoli'],
    min_pagerank=3.0,
    max_tranco_rank=100000,
    limit_per_source=1000
)
# → Returns: Dict with results from all sources
# → Sources: BigQuery, Tranco, Cloudflare, filtered by PageRank
# → Speed: Fast (parallel execution ~15-30 seconds)

# FILTER BY PAGERANK (OpenPageRank API - 200K free/month)
high_authority = linklater.filter_by_pagerank(
    ['example.com', 'test.com'],
    min_pagerank=4.0
)
# → Returns: List of domains meeting threshold
# → Cost: FREE (200K requests/month)

# TOP DOMAINS (Tranco ranking - FREE)
top_sites = linklater.get_top_domains_tranco(count=10000)
# → Returns: Dict with success, domains, list_id, date
# → Cost: FREE

# TOP DOMAINS BY COUNTRY (Cloudflare Radar - FREE with token)
ly_domains = linklater.get_top_domains_cloudflare(
    location='LY',
    limit=500
)
# → Returns: Dict with success, domains, meta
# → Cost: FREE (requires API token)

# DISCOVER BY TECHNOLOGY (BigQuery HTTP Archive)
wp_sites = linklater.discover_by_technology('WordPress', limit=5000)
# → Returns: Dict with domains using specific technology
# → Cost: FREE (with Google Cloud project setup)

# DISCOVER BY COUNTRY (BigQuery Chrome UX Report)
ly_domains_crux = linklater.discover_by_country_crux('LY', limit=5000)
# → Returns: Dict with domains popular in country
# → Cost: FREE (with Google Cloud project setup)

# CHECK DOMAIN RANK (Tranco)
ranking = linklater.check_domain_rank_tranco('example.com')
# → Returns: Dict with rank, list_id, date
# → Cost: FREE
```

**Classes Available:**
- `DomainFilters` - Unified filtering interface
- `BigQueryDiscovery` - BigQuery domain search
- `OpenPageRankFilter` - PageRank authority filtering
- `TrancoRankingFilter` - Top sites ranking
- `CloudflareRadarFilter` - Traffic-based rankings

**API Keys Required:**
- `GOOGLE_CLOUD_PROJECT` - For BigQuery (optional)
- `OPENPAGERANK_API_KEY` - For PageRank (optional, 200K free/month)
- `CLOUDFLARE_API_TOKEN` - For Cloudflare Radar (optional, free)

**Speed:** Very Fast (parallel execution, most sources respond in <10s)

**Cost:** FREE (BigQuery has usage-based billing but very generous free tier)

---

### `linklater.py` - Core LinkLater Class
**Location:** `/modules/linklater/linklater.py`

**Capabilities:**
- Same as `api.py` (api.py wraps this)
- Can be instantiated separately if needed
- Manages all source integrations

---

### `linklater_cli.py` - Command Line Interface
**Location:** `/modules/linklater/linklater_cli.py`

**Usage:**
```bash
python linklater_cli.py backlinks example.com --limit 100
python linklater_cli.py search "site:example.com libya"
```

**Capabilities:**
- CLI wrapper for all API methods
- Output to stdout or JSON files

---

## LinkGraph Integration

### `linkgraph/globallinks.py` - GlobalLinks Go Binary Client
**Location:** `/modules/linklater/linkgraph/globallinks.py`

**Class:** `GlobalLinksClient`

**Capabilities:**

```python
from modules.linklater.linkgraph.globallinks import GlobalLinksClient

client = GlobalLinksClient()

# BACKLINKS (sources linking TO target)
backlinks = await client.get_backlinks(
    domain="example.com",
    limit=100,
    archive="CC-MAIN-2025-47"
)
# → Returns: List[LinkRecord]
# → Sources: Precomputed WAT file extractions
# → Binary: outlinker backlinks
# → Speed: Very fast (precomputed index)

# OUTLINKS (links FROM source)
outlinks = await client.get_outlinks(
    domain="example.com",
    limit=100,
    archive="CC-MAIN-2025-47"
)
# → Returns: List[LinkRecord]
# → Sources: Precomputed WAT file extractions
# → Binary: outlinker outlinks
# → Speed: Very fast (precomputed index)

# EXTRACT (filtered outlinks from specific domains)
results = await client.extract_outlinks(
    domains=["bbc.com", "cnn.com"],
    archive="CC-MAIN-2024-10",
    country_tlds=[".uk", ".fr"],
    url_keywords=["libya", "tripoli"],
    exclude_keywords=["spam"],
    max_results=1000
)
# → Returns: List[LinkRecord]
# → Binary: outlinker extract
# → Speed: Fast (targeted extraction)

# SEARCH (find outlinks to target domain)
results = await client.search_outlinks(
    target_domain="example.com",
    data_path="data/links/"
)
# → Returns: List[LinkRecord]
# → Binary: outlinker search
# → Speed: Medium (searches local link data)
```

**Binary Detection:**
Automatically finds GlobalLinks binaries in:
1. `/categorizer-filterer/globallinks/bin/`
2. `/categorizer-filterer/globallinks/globallinks-with-outlinker/bin/`
3. `/categorizer-filterer/globallinks/globallinks-ready/bin/`

**Available Binaries:**
- `outlinker` - Query backlinks/outlinks
- `linksapi` - API server for link queries
- `storelinks` - Link storage/import
- `importer` - Data importer

---

### `linkgraph/cc_graph.py` - CC Graph Client
**Location:** `/modules/linklater/linkgraph/cc_graph.py`

**Capabilities:**

```python
from modules.linklater.linkgraph.cc_graph import CCGraphClient

client = CCGraphClient(base_url="http://localhost:8001")

# BACKLINKS from CC Graph (domain-level aggregates)
backlinks = await client.get_backlinks(domain="example.com", limit=100)
# → Returns: List[LinkRecord]
# → Sources: CC domain graph (157M domains, 2.1B edges)
# → Requires: FastAPI backend running on port 8001
# → Speed: Very fast (in-memory graph)
```

---

### `linkgraph/models.py` - Data Models
**Location:** `/modules/linklater/linkgraph/models.py`

**Classes:**
- `LinkRecord` - Standard link representation
- Other data models for CC Graph

---

## Scraping & Extraction

### `scraping/binary_extractor.py` - Binary Data Extraction
**Location:** `/modules/linklater/scraping/binary_extractor.py`

**Capabilities:**
- Extract structured data from binary formats
- PDF text extraction
- Image metadata extraction

---

### `scraping/cc_first_scraper.py` - CC-First Scraping Strategy
**Location:** `/modules/linklater/scraping/cc_first_scraper.py`

**Capabilities:**
- Check Common Crawl BEFORE live scraping
- Fallback to live scraping if not in CC
- Reduces load on target sites

---

### `scraping/warc_parser.py` - WARC File Parser
**Location:** `/modules/linklater/scraping/warc_parser.py`

**Capabilities:**

```python
from modules.linklater.scraping.warc_parser import WARCParser

parser = WARCParser()

# Parse WARC file
records = parser.parse_warc_file("path/to/file.warc.gz")
# → Returns: List of parsed records

# Extract links from HTML
links = parser.extract_links(html_content, base_url)
# → Returns: List[str] (absolute URLs)

# Get specific record by offset
record = parser.get_record_at_offset("path/to/file.warc.gz", offset=12345)
# → Returns: Single WARC record
```

---

## Archives & Discovery

### `archives/optimal_archive.py` - Optimal Archive Selection
**Location:** `/modules/linklater/archives/optimal_archive.py`

**Capabilities:**
- Intelligently select best CC archive for target domain
- Balance between freshness and coverage
- Avoid downloading unnecessary archives

---

### `archives/hybrid_archive.py` - Hybrid Archive Strategy
**Location:** `/modules/linklater/archives/hybrid_archive.py`

**Capabilities:**
- Combine multiple archive sources
- Deduplicate across archives
- Prioritize by quality/freshness

---

### `archives/fast_scanner.py` - Fast Archive Scanner
**Location:** `/modules/linklater/archives/fast_scanner.py`

**Capabilities:**
- Rapid scanning of CC archives
- Index-based lookups (no full download)
- CDX API integration

---

### `discovery/keyword_variations.py` - Keyword Variation Generator
**Location:** `/modules/linklater/discovery/keyword_variations.py`

**Capabilities:**

```python
from modules.linklater.discovery.keyword_variations import generate_variations

variations = generate_variations("libya")
# → Returns: ["libya", "libyan", "libyans", "libya's", ...]
# → Uses: Stemming, pluralization, possessives
```

---

## Enrichment & Analysis

### `enrichment/cc_enricher.py` - CC Data Enrichment
**Location:** `/modules/linklater/enrichment/cc_enricher.py`

**Capabilities:**
- Enrich links with CC metadata
- Add archive timestamps
- Add WARC file references

---

### `enrichment/entity_patterns.py` - Entity Pattern Library
**Location:** `/modules/linklater/enrichment/entity_patterns.py`

**Capabilities:**

```python
from modules.linklater.enrichment.entity_patterns import ENTITY_PATTERNS

# Regex patterns for entity extraction
ENTITY_PATTERNS = {
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'phone': r'\+?[\d\s\-\(\)]{10,20}',
    'url': r'https?://[^\s<>"]+',
    'company': r'\b[A-Z][A-Za-z0-9\s&,\.]{2,50}(?:\s(?:Inc|LLC|Ltd|Corp|GmbH|SA|AB|AS)\.?)\b',
    'person': r'\b[A-Z][a-z]+\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b',
    'money': r'[\$€£¥]\s*[\d,]+(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP|million|billion)',
    'date': r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b'
}
```

---

## MCP Integration

### `mcp/server.py` - MCP Server Implementation
**Location:** `/modules/linklater/mcp/server.py`

**Capabilities:**
- Expose LinkLater via Model Context Protocol
- Used by C0GN1T0 and external agents
- Registered in `.claude/mcp_config.json`

**Usage:**
```json
{
  "mcpServers": {
    "linklater": {
      "command": "python",
      "args": ["modules/linklater/mcp/server.py"]
    }
  }
}
```

---

## Integration Points

### FastAPI Routes
**Location:** `/api/linklater_routes.py`

**Endpoints:**
- `GET /api/linklater/backlinks?domain=example.com`
- `GET /api/linklater/majestic?domain=example.com&mode=fresh`
- `POST /api/linklater/search` (with keyword payload)

---

### Node.js Router
**Location:** `/server/routers/linkLaterRouter.ts`

**Capabilities:**
- TypeScript bridge to Python LinkLater API
- Used by frontend React components
- WebSocket support for streaming results

---

## Environment Requirements

**Required in `.env`:**
```bash
MAJESTIC_API_KEY=your_key_here
ELASTICSEARCH_URL=http://localhost:9200
FASTAPI_URL=http://localhost:8001
```

**Optional:**
```bash
CC_DATA_PATH=/path/to/cc_webgraph_data
GLOBALLINKS_BIN_PATH=/path/to/globallinks/bin
```

---

## Performance Characteristics

| File/Module | Speed | Cost | Coverage | Best For |
|-------------|-------|------|----------|----------|
| `cc_graph.py` | Very Fast | Free | 157M domains | Domain-level discovery |
| `globallinks.py` | Fast | Free | Page-level | WAT-based extraction |
| `api.py` (Majestic) | Fast | Paid | High quality | Anchor text analysis |
| `optimal_archive.py` | Slow | Free | Complete | Historical research |
| `warc_parser.py` | Medium | Free | Targeted | Specific URLs |

---

**Last Updated:** 2025-11-30
**Archive Version:** CC-MAIN-2025-47 (September-October-November 2025)
