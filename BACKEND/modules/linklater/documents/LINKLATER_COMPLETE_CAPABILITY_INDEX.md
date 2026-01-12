# LinkLater Complete Capability Index

> **Last Updated:** December 2025
> **Total Files:** 59 Python files across 12 subdirectories
> **Unified API:** `api.py` with 148+ methods accessible via `linklater` singleton

---

## Overview

LinkLater is a comprehensive web intelligence module that combines:
- **Link Graph Intelligence** (GlobalLinks, CC Web Graph, Majestic)
- **Archive Intelligence** (Wayback, Common Crawl, temporal analysis)
- **Web Crawling** (3-tier hybrid crawler, Tor crawler)
- **Entity Extraction** (companies, persons, emails, phones)
- **Discovery** (subdomains, WHOIS clustering, news/GDELT)
- **Alerting** (category-based link pattern alerts)

---

## Architecture

```
linklater/
├── drill/                 # Core crawler + link processing (10 files)
├── tor/                   # Tor/onion crawler (4 files)
├── scraping/              # Content scraping (3 files)
├── archives/              # Archive sources (6 files)
├── linkgraph/             # Link graph sources (4 files)
├── discovery/             # Domain discovery (8 files)
├── alerts/                # Link alerting (2 files)
├── enrichment/            # Link enrichment (3 files)
├── pipelines/             # Automated pipelines (5 files)
├── mcp/                   # MCP server interface (1 file)
├── api.py                 # Unified API (817 lines)
├── temporal.py            # URL timeline analysis
├── linklater.py           # Legacy entry point
└── linklater_cli.py       # CLI interface
```

---

## 1. DRILL Crawler System (`drill/`)

### 1.1 Core Crawler (`crawler.py`, `go_bridge.py`, `discovery.py`)

**3-Tier Hybrid Architecture:**
| Tier | Tool | Speed | Use Case |
|------|------|-------|----------|
| 1 | Go/Colly | Fast | Static HTML, bulk crawling |
| 2 | Go/Rod | Medium | JavaScript-rendered pages |
| 3 | Python/Playwright | Slow | Complex JS, fallback |

**Key Classes:**
- `GoBridge` - Python-Go interprocess communication via JSON pipes
- `DrillCrawler` - Orchestrates 3-tier crawler with automatic fallback
- `DiscoveryEngine` - URL discovery from multiple sources

**Capabilities:**
- Automatic Tier 1→2→3 fallback on JavaScript detection
- Link extraction (same-site, external, robots.txt)
- Sitemap parsing and crawl frontier management
- Screenshot capture on tier escalation
- Configurable depth, filters, and rate limiting

### 1.2 Link Processing (`link_processor.py`)

**Features:**
- URL normalization and canonicalization
- Anchor text extraction and cleaning
- Domain categorization (offshore, government, russia_cis, china_hk, financial)
- Link quality scoring

### 1.3 JavaScript Detection (`js_detector.py`)

**Detection Patterns:**
- SPA frameworks (React, Vue, Angular)
- Dynamic loading indicators
- Empty body detection
- Script-heavy pages

### 1.4 Entity Extraction (`extractors.py`)

**`EntityExtractor` Class (509 lines):**

| Entity Type | Method | Detection |
|-------------|--------|-----------|
| Companies | Regex + suffix matching | `Ltd`, `Inc`, `GmbH`, etc. |
| Persons | Name dictionaries | First + Last name patterns |
| Emails | Regex | Standard email pattern |
| Phones | Regex | International formats |
| Outlinks | HTML parsing | All `<a href>` links |
| Keywords | Investigation terms | Money laundering, fraud, etc. |

**Output:** `ExtractedEntities` dataclass with all extracted data.

### 1.5 Link Pipeline (`linkpipeline.py`, 894 lines)

**`DrillLinkPipeline` Class:**

Deep integration with GlobalLinks for link graph extraction:

```python
pipeline = DrillLinkPipeline()

# Extract and index links with enrichments
result = await pipeline.extract_and_index(
    domain="example.com",
    archive="CC-MAIN-2024-10",
    enrich_temporal=True  # Add first_seen/last_seen dates
)

# Query links by age
old_links = await pipeline.query_links_by_age(
    source_domain="example.com",
    min_age_days=365,
    first_seen_before="2023-01-01"
)

# Calculate link velocity
velocity = await pipeline.calculate_link_velocity(
    source_domain="example.com",
    period_days=30
)
```

**Features:**
- GlobalLinks → Elasticsearch indexing
- Entity extraction on anchor texts
- Sentence embeddings for semantic anchor search
- Domain categorization (offshore, government, etc.)
- Temporal enrichment (first_seen, last_seen)
- Link velocity tracking

**ES Index Schema (`drill_enriched_links`):**
- source_url, source_domain
- target_url, target_domain, target_tld
- anchor_text, anchor_embedding
- anchor_entities (companies, persons)
- target_category
- first_seen, last_seen, link_age_days

### 1.6 Archive Freshness (`archive_freshness.py`, 531 lines)

**`ArchiveFreshnessChecker` Class:**

Check archives before crawling to avoid redundant work:

```python
checker = ArchiveFreshnessChecker()

# Check single URL
freshness = await checker.check_freshness(url, check_cc=True, check_wayback=True)

# Filter URLs for crawling (skip those with recent archives)
to_crawl, skipped = await filter_for_crawling(urls, recent_days=90)
```

**Skip Policies:**
- `ALWAYS_SKIP` - Never re-crawl if archive exists
- `SKIP_IF_RECENT` - Skip if within threshold days
- `NEVER_SKIP` - Always crawl
- `REPORT_ONLY` - User decides

### 1.7 GlobalLinks Intelligence (`globallinks_intel.py`, 537 lines)

**`GlobalLinksIntelligence` Class:**

Pre-flight intelligence gathering before crawling:

```python
intel = GlobalLinksIntelligence()

# Gather intelligence about a domain
report = await intel.gather_intelligence(
    domain="example.com",
    archive="CC-MAIN-2024-10",
    deep_analysis=True
)
# Returns: DomainIntelligence with:
#   - backlink_count
#   - anchor_keywords
#   - categories
#   - suggested_max_depth
#   - suggested_extraction_focus
```

### 1.8 Indexer (`indexer.py`)

**`DrillIndexer` Class:**

Elasticsearch indexing for crawled content:
- Page content indexing
- Entity indexing (separate index)
- Link relationship indexing
- Full-text search support

### 1.9 Embedder (`embedder.py`)

**`SentenceEmbedder` Class:**

Generate embeddings for semantic search:
- Uses `sentence-transformers/all-MiniLM-L6-v2`
- Batch embedding for performance
- Vector similarity search support

---

## 2. Tor Crawler (`tor/`)

### 2.1 Tor Crawler (`tor_crawler.py`, ~1000 lines)

**Colly-Inspired Architecture:**

```python
from linklater.tor.tor_crawler import TorCrawler, CrawlerCallbacks, DomainRule

# Define callbacks
callbacks = CrawlerCallbacks(
    on_request=lambda url, depth: print(f"Fetching: {url}"),
    on_scraped=lambda page: save_to_db(page),
    on_blocked=lambda url, reason: log_blocked(url, reason),
)

# Domain-specific rules
rules = [
    DomainRule(r".*market.*\.onion", delay=2.0, max_concurrent=1),
    DomainRule(r".*forum.*\.onion", delay=0.3, max_concurrent=5),
]

# Initialize crawler
crawler = TorCrawler(
    seed_urls=["http://example.onion/"],
    es_url="http://localhost:9200",
    es_index="onion-pages",
    callbacks=callbacks,
    domain_rules=rules,
)
crawler.run()
```

**Features:**
- SOCKS5 proxy via Tor
- Elasticsearch indexing (Ahmia-compatible schema)
- Blocklist support
- Per-domain rate limiting
- Pluggable storage backends (Memory, SQLite, Redis)
- Checkpoint persistence for crash recovery

### 2.2 Tor Ingest (`tor_ingest.py`, `tor_ingest_manager.py`)

Manage bulk ingestion of Tor crawl results into Elasticsearch.

### 2.3 Ahmia Importer (`ahmia_importer.py`)

Import data from Ahmia's public dark web index.

---

## 3. Content Scraping (`scraping/`)

### 3.1 CC-First Scraper (`cc_first_scraper.py`, 617 lines)

**3-Source Fallback Chain:**

```python
scraper = CCFirstScraper()

# Single URL (auto-fallback: CC → Wayback → Firecrawl)
result = await scraper.get_content("https://example.com")
# result.source = 'cc' | 'wayback' | 'firecrawl' | 'failed'

# Batch scraping with high concurrency
results = await scraper.batch_scrape(urls, max_concurrent=50)

# Stats
print(scraper.get_stats())
# {cc_hits: 75, wayback_hits: 20, firecrawl_hits: 3, failures: 2, archive_hit_rate: "95.0%"}
```

**Performance:**
- CC/Wayback: 100-300ms vs Firecrawl: 2-5s
- ~85% archive hit rate (free sources)
- LRU cache for index lookups

### 3.2 WARC Parser (`warc_parser.py`)

**`WARCParser` Class:**

Extract content from Common Crawl WARC records:
- HTML extraction from gzipped WARC
- Binary content extraction (PDF, DOCX)
- Metadata extraction (URL, timestamp, status, content-type)
- HTML to markdown conversion

### 3.3 Binary Extractor (`binary_extractor.py`, 545 lines)

**`BinaryTextExtractor` Class:**

Extract searchable text from binary files in archives:

| Format | Library | Support |
|--------|---------|---------|
| PDF | pypdf / pdfplumber | ✅ Full |
| DOCX | python-docx | ✅ Full |
| XLSX | openpyxl | ✅ Full |
| PPTX | python-pptx | ✅ Full |
| DOC/XLS/PPT | - | ❌ Legacy |
| ZIP/TAR | builtin | ✅ Listing only |

---

## 4. Archives (`archives/`)

### 4.1 CC Index Client (`cc_index_client.py`, 471 lines)

**`CCIndexClient` Class:**

Query Common Crawl Index API:

```python
client = CCIndexClient()

# Query for URL
records = await client.query_url(
    "https://example.com/page.html",
    archive="CC-MAIN-2025-47"
)

# Query for domain (all pages)
records = await client.query_domain("example.com", limit=1000)

# Get WAT file locations
wat_files = await client.get_wat_files_for_domain("example.com")

# Stream large result sets
async for record in client.stream_query_results("*.example.com/*"):
    process(record)
```

**`CCIndexRecord` Fields:**
- url, mime, status, digest
- offset, length, filename (WARC location)
- timestamp, charset, languages

### 4.2 Snapshot Differ (`snapshot_differ.py`, 418 lines)

**`SnapshotDiffer` Class:**

Detect content changes between archive snapshots:

```python
differ = SnapshotDiffer()

# Find all content change events (FAST - digest comparison only)
events = await differ.find_change_events(url, start_year=2015)
# Returns: List of ChangeEvent with timestamps when content changed

# Deep comparison of two snapshots
diff = await differ.compare_snapshots(url, ts1="20230115", ts2="20240601")
# Returns: DiffReport with:
#   - text_added, text_removed
#   - links_added, links_removed
#   - entities_added, entities_removed
```

### 4.3 Hybrid Archive Searcher (`hybrid_archive.py`)

**`HybridArchiveSearcher` Class:**

Coordinate fast snapshot sampling with exhaustive archive sweep:

```python
searcher = HybridArchiveSearcher()

# Stream hybrid search (fast + deep)
async for event in searcher.stream_search(url, keywords, direction="backwards"):
    if event["type"] == "result":
        print(f"Found: {event['keyword']} at {event['timestamp']}")

# Collect all results
summary = await searcher.collect_all(url, keywords)
# Returns: {keyword: {first: date, last: date, hits: [...]}}
```

### 4.4 Fast Scanner (`fast_scanner.py`)

**`FastWaybackScanner` Class:**

Fast Wayback CDX-based keyword scanning without fetching content.

### 4.5 Optimal Archive (`optimal_archive.py`)

**`OptimalArchiveSearcher` Class:**

Exhaustive multi-year archive search with smart year selection.

---

## 5. Link Graph Sources (`linkgraph/`)

### 5.1 GlobalLinks Client (`globallinks.py`)

**`GlobalLinksClient` Class:**

Interface to GlobalLinks Go binary for high-performance link extraction:

```python
client = GlobalLinksClient()

# Get outlinks from a domain
outlinks = await client.get_outlinks("example.com", archive="CC-MAIN-2024-10")

# Search anchors
results = await client.search_anchors("company name", archive="CC-MAIN-2024-10")
```

**GlobalLinks Architecture:**
- Go binary (`linksapi`) for performance
- Processes CC WAT files directly
- Extracts links with anchor texts
- 1M+ links/second throughput

### 5.2 CC Web Graph (`cc_graph.py`)

**`CCGraphClient` Class:**

Query CC Web Graph (157M domains, 2.1B edges) via Elasticsearch:

```python
client = CCGraphClient()

# Get backlinks (domains linking TO this domain)
backlinks = await client.get_backlinks("example.com", limit=100)

# Get outlinks (domains this domain links TO)
outlinks = await client.get_outlinks("example.com", limit=100)
```

### 5.3 Majestic Integration (via `api.py`)

```python
from linklater import linklater

# Get backlinks from Majestic (Fresh + Historic)
backlinks = await linklater.get_majestic_backlinks(
    domain="example.com",
    mode="fresh",  # or "historic"
    result_type="pages",  # or "domains"
    max_results=100
)
# Returns: List with anchor_text, trust_flow, citation_flow
```

---

## 6. Discovery (`discovery/`)

### 6.1 Unified Discovery (`unified_discovery.py`, 748 lines)

**`UnifiedDiscovery` Class:**

Single interface for all discovery methods:

```python
discovery = UnifiedDiscovery()

# Check capabilities
caps = discovery.get_capabilities()

# Subdomain discovery (crt.sh, WhoisXML, Sublist3r)
response = await discovery.discover_subdomains("example.com")

# WHOIS clustering
response = await discovery.cluster_by_whois("example.com")

# Reverse WHOIS
response = await discovery.reverse_whois("John Doe", search_type="registrant")

# News search (NewsAPI, GDELT, DDG)
response = await discovery.search_news("company name")

# GDELT direct
response = await discovery.search_gdelt("company name", timespan="1m")

# PageRank scores
scores = await discovery.get_pagerank(["domain1.com", "domain2.com"])

# Tranco ranking
rank = await discovery.get_tranco_rank("example.com")
```

### 6.2 Domain Filters (`domain_filters.py`)

**Available Filters:**
- `BigQueryDiscovery` - CrUX, HTTP Archive queries
- `OpenPageRankFilter` - Domain authority scoring
- `TrancoRankingFilter` - Top 1M sites ranking
- `CloudflareRadarFilter` - Traffic data

### 6.3 Other Discovery Modules

- `ga_tracker.py` - Google Analytics tracker ID discovery
- `outlink_extractor.py` - Extract outlinks from HTML
- `entity_extractor.py` - Extract entities from content
- `keyword_variations.py` - Generate keyword variations

---

## 7. Alerts (`alerts/`)

### 7.1 Link Alerts (`link_alerts.py`, 462 lines)

**`LinkAlertService` Class:**

Category-based alerting for suspicious link patterns:

```python
service = LinkAlertService()

# Check for new alerts
alerts = await service.check_for_alerts("example.com", since_hours=24)

# Get stored alerts
alerts = await service.get_alerts(severity="high")

# Get alert statistics
stats = await service.get_alert_stats(source_domain="example.com")
```

**Alert Rules:**

| Rule | Category | Severity | Description |
|------|----------|----------|-------------|
| `new_offshore` | offshore | high | New link to offshore jurisdiction |
| `new_russia_cis` | russia_cis | medium | New link to Russia/CIS region |
| `new_government` | government | low | New link to government domain |
| `velocity_spike` | - | medium | Link velocity 3x above baseline |

**Offshore TLDs:** `.ky`, `.vg`, `.pa`, `.bs`, `.je`, `.gg`, `.im`, `.lu`, `.li`, `.mc`
**Russia/CIS TLDs:** `.ru`, `.su`, `.by`, `.kz`, `.ua`, `.uz`, `.az`

---

## 8. Enrichment (`enrichment/`)

### 8.1 Entity Timeline (`entity_timeline.py`)

**`EntityTimelineTracker` Class:**

Track when entities first appeared in domain content:

```python
tracker = EntityTimelineTracker()

# Track entity appearances
appearances = await tracker.track_entity_appearances(
    domain="example.com",
    years=[2022, 2023, 2024]
)

# Get timeline for specific entity
timeline = await tracker.get_entity_timeline("Company Name")

# Find new entities since date
new_entities = await tracker.find_new_entities(
    domain="example.com",
    since_date="2024-01-01"
)
```

### 8.2 CC Enricher (`cc_enricher.py`)

Enrich records with Common Crawl data.

### 8.3 Entity Patterns (`entity_patterns.py`)

Advanced entity pattern matching.

---

## 9. Pipelines (`pipelines/`)

### 9.1 Automated Backlink Pipeline (`automated_backlink_pipeline.py`)

**`AutomatedBacklinkPipeline` Class:**

Full automated backlink discovery:

```python
pipeline = AutomatedBacklinkPipeline(target_domain="example.com")

# Run full pipeline
results = await pipeline.run(max_results=100)

# Pipeline phases:
# 1. CC Index lookup (find WARC locations)
# 2. GlobalLinks extraction (WAT processing)
# 3. Majestic backlinks (Fresh + Historic, parallel)
# 4. Combine and deduplicate
# 5. Analysis (top domains, anchor texts, TrustFlow)
```

### 9.2 Production Backlink Discovery (`production_backlink_discovery.py`)

Production-ready pipeline with error handling and logging.

### 9.3 Other Pipelines

- `get_referring_pages.py` - Get pages linking to a URL
- `scan_pages_for_outlinks.py` - Scan pages for outbound links

---

## 10. Temporal Analysis (`temporal.py`, 406 lines)

**`TemporalAnalyzer` Class:**

URL timeline intelligence:

```python
analyzer = TemporalAnalyzer()

# Get complete timeline for URL
timeline = await analyzer.get_url_timeline(url, check_live=True)
# Returns: URLTimeline with:
#   - first_seen_wayback, last_seen_wayback
#   - first_seen_commoncrawl, last_seen_commoncrawl
#   - is_live

# Get first seen date
first_seen = timeline.get_first_seen()  # Earliest across all archives

# Get age in days
age = timeline.age_days()

# Batch timelines
timelines = await analyzer.get_url_timelines_batch(urls, max_concurrent=20)
```

---

## 11. Unified API (`api.py`, 817 lines)

**`LinkLater` Class:**

Single entry point for all 148+ methods:

```python
from linklater import linklater

# Scraping
content, source = await linklater.scrape_url(url)

# Backlinks (multi-source)
backlinks = await linklater.get_backlinks(domain, use_globallinks=True)

# Majestic
majestic_data = await linklater.get_majestic_backlinks(domain, mode="fresh")

# Entity extraction
entities = linklater.extract_entities(text)

# Discovery
subdomains = await linklater.discover_subdomains(domain)
whois_cluster = await linklater.cluster_by_whois(domain)

# Temporal
timeline = await linklater.get_url_timeline(url)

# Alerts
alerts = await linklater.check_for_alerts(domain)
```

---

## 12. MCP Server (`mcp/server.py`, 978 lines)

Full MCP (Model Context Protocol) server exposing all LinkLater capabilities:

**Available Tools:**
- `scrape_url` - Scrape with CC-first fallback
- `get_backlinks` - Multi-source backlinks
- `extract_entities` - Entity extraction
- `discover_subdomains` - Subdomain enumeration
- `search_news` - News search
- `check_alerts` - Link pattern alerts
- ... and 30+ more tools

---

## External Data Sources

| Source | Type | Cost | Coverage |
|--------|------|------|----------|
| Common Crawl | Archive | FREE | 3B+ pages |
| Wayback Machine | Archive | FREE | 800B+ pages |
| GlobalLinks | Link Graph | FREE | CC WAT extraction |
| CC Web Graph | Link Graph | FREE | 157M domains, 2.1B edges |
| Majestic | Link Graph | PAID | Fresh + Historic indexes |
| Firecrawl | Scraper | PAID | Live content fallback |
| crt.sh | Discovery | FREE | Certificate Transparency |
| WhoisXML | Discovery | PAID | WHOIS, reverse WHOIS |
| GDELT | News | FREE | Global news database |
| OpenPageRank | Authority | FREE | PageRank scores |
| Tranco | Ranking | FREE | Top 1M sites |
| BigQuery | Analytics | PAID | CrUX, HTTP Archive |

---

## Performance Characteristics

| Operation | Speed | Notes |
|-----------|-------|-------|
| CC Index lookup | 100-300ms | LRU cached |
| Wayback fetch | 200-500ms | - |
| Firecrawl | 2-5s | Paid fallback |
| GlobalLinks query | 50-200ms | Via Go binary |
| Entity extraction | 10-50ms | Regex-based |
| Batch scrape (100 URLs) | ~8s | With racing |
| Full backlink pipeline | 30-60s | All sources |

---

## Quick Start

```python
from linklater import linklater

async def investigate_domain(domain: str):
    # 1. Get backlinks from all sources
    backlinks = await linklater.get_backlinks(domain, limit=100)

    # 2. Check for suspicious patterns
    alerts = await linklater.check_for_alerts(domain, since_hours=24)

    # 3. Discover related domains
    whois_cluster = await linklater.cluster_by_whois(domain)
    subdomains = await linklater.discover_subdomains(domain)

    # 4. Get temporal intelligence
    for bl in backlinks[:10]:
        timeline = await linklater.get_url_timeline(bl.source)
        print(f"{bl.source}: first seen {timeline.get_first_seen()}")

    return {
        "backlinks": len(backlinks),
        "alerts": len(alerts),
        "related_domains": len(whois_cluster.results),
        "subdomains": len(subdomains.results),
    }
```

---

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `api.py` | 817 | Unified API |
| `mcp/server.py` | 978 | MCP interface |
| `drill/linkpipeline.py` | 894 | Link pipeline |
| `drill/crawler.py` | ~800 | 3-tier crawler |
| `discovery/unified_discovery.py` | 748 | Discovery |
| `scraping/cc_first_scraper.py` | 617 | CC-first scraper |
| `scraping/binary_extractor.py` | 545 | Binary extraction |
| `drill/archive_freshness.py` | 531 | Archive freshness |
| `drill/globallinks_intel.py` | 537 | Pre-flight intel |
| `drill/extractors.py` | 509 | Entity extraction |
| `archives/cc_index_client.py` | 471 | CC Index API |
| `alerts/link_alerts.py` | 462 | Link alerts |
| `archives/snapshot_differ.py` | 418 | Snapshot diff |
| `temporal.py` | 406 | Temporal analysis |
| `tor/tor_crawler.py` | ~1000 | Tor crawler |

---

*This document was generated from a comprehensive audit of the LinkLater module.*
