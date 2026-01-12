# LinkLater & Drill Search: External Resources Index

**Complete index of all external APIs, services, and data sources used.**

---

## Data Sources & APIs

### 1. Common Crawl
**Cost:** FREE
**Coverage:** Web-scale (petabytes)

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **CC Web Graph** | Domain-level link relationships (157M domains, 2.1B edges) | HTTP API via Python | `/modules/linklater/linkgraph/cc_graph.py` |
| **GlobalLinks Binaries** | WAT file extraction (6B links/month) | Go binaries via subprocess | `/modules/linklater/linkgraph/globallinks.py` |
| **CC Index API** | URL discovery and WARC file locations | HTTPS REST API | `/modules/alldom/cc_index_cli.py` |
| **CC Archives (WARC)** | Raw web content from archives | S3 bucket download (gzip) | `/modules/linklater/scraping/warc_parser.py` |

**Base URLs:**
- Index: `https://index.commoncrawl.org/`
- Data: `https://data.commoncrawl.org/`
- Web Graph: `https://data.commoncrawl.org/projects/hyperlinkgraph/`

**Archives Used:**
- Primary: `CC-MAIN-2025-47` (Sep-Oct-Nov 2025)
- Historical: `CC-MAIN-2024-10`, `CC-MAIN-2021-04`, etc.

**API Keys:** None required (public data)

---

### 2. Internet Archive Wayback Machine
**Cost:** FREE
**Coverage:** 866B+ archived pages since 1996

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Wayback CDX Server** | Find archived URL snapshots | HTTPS REST API | `/modules/linklater/api.py` (fetch_from_wayback) |
| **Wayback Availability API** | Check if URL archived | HTTPS REST API | Used as fallback in pipelines |

**Base URLs:**
- CDX: `https://web.archive.org/cdx/search/cdx`
- Availability: `https://archive.org/wayback/available`

**API Keys:** None required (public)

**Rate Limits:** Soft limit ~10 req/sec

---

### 3. Majestic SEO
**Cost:** PAID (API subscription required)
**Coverage:** 1.2T+ URLs, 11T+ links

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Fresh Index** | Recent backlinks (90 days) | HTTPS REST API | `/modules/linklater/api.py` (get_majestic_backlinks) |
| **Historic Index** | Historical backlinks (5 years) | HTTPS REST API | `/modules/linklater/api.py` (get_majestic_backlinks) |
| **TopicalTrustFlow** | Category classification | HTTPS REST API | Not yet integrated |
| **Domain Metrics** | TrustFlow, CitationFlow, Referring Domains | HTTPS REST API | Included in backlink responses |

**Base URL:** `https://api.majestic.com/api/json`

**API Key Location:** `.env` → `MAJESTIC_API_KEY`

**Rate Limits:**
- Fresh: 10,000 queries/month (standard plan)
- Historic: 2,000 queries/month (standard plan)

**Used In:**
- `/modules/linklater/api.py:322` - get_majestic_backlinks()
- `/modules/linklater/pipelines/production_backlink_discovery.py` - Phases 2

---

### 4. Firecrawl
**Cost:** PAID (API subscription)
**Coverage:** Live web scraping with JS rendering

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Scrape API** | Headless browser scraping | HTTPS REST API | `/modules/brute/scraper/firecrawl_client.py` |
| **Crawl API** | Multi-page crawling | HTTPS REST API | `/modules/alldom/providers/firecrawl.py` |
| **Screenshot API** | Visual content capture | HTTPS REST API | Part of scrape response |

**Base URL:** `https://api.firecrawl.dev/v0`

**API Key Location:** `.env` → `FIRECRAWL_API_KEY`

**Used In:**
- `/modules/alldom/providers/firecrawl.py`
- `/modules/brute/services/scrape_service.py`
- `/modules/fact_assembler/` (optional scraping)

**Rate Limits:** Depends on plan (typically 100-10,000 req/month)

---

### 5. WhoisXML API
**Cost:** PAID (API subscription)
**Coverage:** WHOIS records, DNS data, subdomain discovery

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **WHOIS Lookup** | Domain registration data | HTTPS REST API | `/modules/alldom/sources/subdomain_discovery.py` |
| **Reverse WHOIS** | Find domains by owner | HTTPS REST API | Not yet integrated |
| **DNS Lookup** | DNS records | HTTPS REST API | Used in subdomain discovery |

**Base URL:** `https://www.whoisxmlapi.com/whoisserver/`

**API Key Location:** `.env` → `WHOISXML_API_KEY`

**Used In:**
- `/modules/alldom/sources/subdomain_discovery.py:discover_whoisxml()`

---

### 6. crt.sh (Certificate Transparency)
**Cost:** FREE
**Coverage:** All SSL/TLS certificates issued

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **CT Log Search** | Subdomain discovery via certificates | HTTPS REST API (JSON) | `/modules/alldom/sources/subdomain_discovery.py` |

**Base URL:** `https://crt.sh/`

**API Keys:** None required (public)

**Used In:**
- `/modules/alldom/sources/subdomain_discovery.py:discover_crtsh()`

**Rate Limits:** None documented (soft limit ~10 req/sec recommended)

---

### 7. OpenCorporates
**Cost:** FREE (basic) / PAID (pro)
**Coverage:** 250M+ companies from 140+ jurisdictions

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Company Search** | Find companies by name/number | HTTPS REST API | `/modules/corporella/` |
| **Officer Search** | Find company officers | HTTPS REST API | `/modules/corporella/` |
| **Network Mapping** | Corporate networks | HTTPS REST API | `/modules/fact_assembler/` (viz) |

**Base URL:** `https://api.opencorporates.com/v0.4/`

**API Key Location:** `.env` → `OPENCORPORATES_API_KEY`

**Used In:**
- `/modules/corporella/` (company lookups)
- `/modules/fact_assembler/opcorpvis*.html` (visualizations)

**Rate Limits:**
- Free: 500 req/day
- Pro: Higher limits

---

### 8. Ahrefs
**Cost:** PAID (expensive, $99+/month)
**Coverage:** 14T+ links, 441M+ domains

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Backlinks** | High-quality backlink data | HTTPS REST API | `/modules/alldom/sources/ahrefs_backlinks.py` |
| **Domain Metrics** | Domain Rating, URL Rating | HTTPS REST API | Not actively used |

**Base URL:** `https://apiv2.ahrefs.com/`

**API Key Location:** `.env` → `AHREFS_API_KEY`

**Used In:**
- `/modules/alldom/sources/ahrefs_backlinks.py`

**Status:** ⚠️ Module exists but NOT integrated into LinkLater (in alldom)

---

### 9. WorldCheck (Refinitiv)
**Cost:** PAID (enterprise)
**Coverage:** Sanctions, PEPs, adverse media

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Entity Screening** | Check sanctions/PEPs/watch lists | HTTPS REST API | `/modules/brute/scripts/index_worldcheck*.py` |

**Base URL:** Enterprise endpoint (varies by customer)

**API Key Location:** `.env` → `WORLDCHECK_API_KEY`

**Used In:**
- `/modules/brute/scripts/index_worldcheck_elastic_only.py`
- `/modules/brute/scripts/index_worldcheck_with_edges.py`

**Status:** ⚠️ Indexing scripts exist, not actively queried in LinkLater

---

### 10. SerpAPI
**Cost:** PAID ($50+/month for 5K searches)
**Coverage:** Google, Bing, Yahoo, Yandex, Baidu search results

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Google Search** | Real-time search results | HTTPS REST API | `/modules/brute/` |
| **Image Search** | Google Images API | HTTPS REST API | `/modules/brute/` |
| **News Search** | Google News API | HTTPS REST API | `/modules/brute/` |

**Base URL:** `https://serpapi.com/search`

**API Key Location:** `.env` → `SERPAPI_API_KEY`

**Used In:**
- `/modules/brute/engines/` (various search engines)
- `/modules/brute/brute.py` (search aggregation)

**Rate Limits:** Depends on plan (typically 5,000-100,000 searches/month)

---

### 11. Aleph (OCCRP)
**Cost:** FREE
**Coverage:** Investigative journalism datasets, leaks, corporate records

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Document Search** | Search leaked documents | HTTPS REST API | `/modules/corporella/corporella_claude/` |
| **Entity Search** | Find companies/persons in datasets | HTTPS REST API | `/modules/corporella/` |

**Base URL:** `https://aleph.occrp.org/api/2/`

**API Keys:** None required (public datasets)

**Used In:**
- `/modules/corporella/corporella_claude/ALEPH_INTEGRATION_COMPLETE.md`

**Rate Limits:** Soft limit ~10 req/sec

---

### 12. BigQuery (Google Cloud)
**Cost:** PAID (query-based, typically $5/TB scanned)
**Coverage:** Common Crawl datasets, public web data

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **CC Index Queries** | Query CC Index via SQL | BigQuery API | Not yet integrated |
| **Public Datasets** | Various web/domain datasets | BigQuery API | Not yet integrated |

**Base URL:** `https://bigquery.googleapis.com/bigquery/v2/`

**API Key Location:** `.env` → `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS`

**Status:** ❌ NOT IMPLEMENTED (proposed for LinkLater discovery)

---

### 13. EDGAR (SEC)
**Cost:** FREE
**Coverage:** US public company filings

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Company Search** | Find US companies by CIK | HTTPS REST API | `/modules/corporella/` |
| **Filing Search** | Find 10-K, 10-Q, 8-K filings | HTTPS REST API | `/modules/corporella/` |

**Base URL:** `https://www.sec.gov/cgi-bin/browse-edgar`

**API Keys:** None required (rate limit: declare user-agent)

**Used In:**
- `/modules/corporella/EDGAR_USAGE_GUIDE.md`

**Rate Limits:** 10 req/sec (declare user-agent header)

---

### 14. Sublist3r
**Cost:** FREE (open source)
**Coverage:** Multi-source subdomain enumeration

| Resource | Purpose | Access Method | Location |
|----------|---------|---------------|----------|
| **Subdomain Discovery** | Aggregate from multiple search engines | Python subprocess | `/modules/alldom/sources/subdomain_discovery.py` |

**Installation:** `pip install sublist3r`

**Used In:**
- `/modules/alldom/sources/subdomain_discovery.py:discover_sublist3r()`

**Status:** Requires local installation

---

## Environment Variables Required

**Create/update:** `/Users/attic/DRILL_SEARCH/drill-search-app/.env`

```bash
# === PAID APIs (Required for full functionality) ===
MAJESTIC_API_KEY=your_majestic_key_here
FIRECRAWL_API_KEY=your_firecrawl_key_here
WHOISXML_API_KEY=your_whoisxml_key_here
SERPAPI_API_KEY=your_serpapi_key_here
AHREFS_API_KEY=your_ahrefs_key_here           # Optional (not integrated)
OPENCORPORATES_API_KEY=your_opencorporates_key  # Optional (free tier available)
WORLDCHECK_API_KEY=your_worldcheck_key         # Optional (enterprise only)

# === Google Cloud (Optional, for BigQuery) ===
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# === Internal Services ===
ELASTICSEARCH_URL=http://localhost:9200
FASTAPI_URL=http://localhost:8001

# === Free APIs (No keys required) ===
# - Common Crawl (no auth)
# - Wayback Machine (no auth)
# - crt.sh (no auth)
# - EDGAR (no auth, just declare user-agent)
# - Aleph/OCCRP (no auth)
```

---

## Integration Status by Module

| External Resource | LinkLater | alldom | brute | fact_assembler | corporella | eyed |
|-------------------|-----------|--------|-------|----------------|------------|------|
| **Common Crawl** | ✅ Full | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **Wayback Machine** | ✅ Full | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **Majestic** | ✅ Full | ⚠️ Partial | ❌ No | ❌ No | ❌ No | ❌ No |
| **Firecrawl** | ✅ Wrapper | ✅ Full | ✅ Full | ✅ Full | ❌ No | ❌ No |
| **WhoisXML** | ✅ Wrapper | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **crt.sh** | ✅ Wrapper | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **OpenCorporates** | ❌ No | ❌ No | ❌ No | ✅ Full | ✅ Full | ❌ No |
| **Ahrefs** | ❌ No | ⚠️ Exists | ❌ No | ❌ No | ❌ No | ❌ No |
| **WorldCheck** | ❌ No | ❌ No | ⚠️ Scripts | ❌ No | ❌ No | ❌ No |
| **SerpAPI** | ❌ No | ❌ No | ✅ Full | ❌ No | ❌ No | ❌ No |
| **Aleph (OCCRP)** | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Full | ❌ No |
| **EDGAR (SEC)** | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Full | ❌ No |
| **Sublist3r** | ✅ Wrapper | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **BigQuery** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **GDELT** | ✅ Wrapper | ❌ No | ✅ Full | ❌ No | ❌ No | ❌ No |
| **NewsAPI** | ✅ Wrapper | ❌ No | ✅ Full | ❌ No | ❌ No | ❌ No |
| **OpenPageRank** | ✅ Wrapper | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |
| **Tranco** | ✅ Wrapper | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No |

**Legend:**
- ✅ Full = Fully integrated and actively used
- ✅ Wrapper = Accessible via UnifiedDiscovery wrapper (no code duplication)
- ⚠️ Partial = Integration exists but not fully utilized
- ❌ No = Not integrated

---

## Cost Analysis

### FREE Resources (No API key required)
1. ✅ Common Crawl (Web Graph, Archives, Index)
2. ✅ Internet Archive Wayback Machine
3. ✅ crt.sh (Certificate Transparency)
4. ✅ Aleph/OCCRP
5. ✅ EDGAR (SEC filings)
6. ✅ Sublist3r (open source)

**Total Free Coverage:** ~90% of backlink discovery functionality

---

### PAID Resources (API key required)

| Service | Cost/Month | Primary Use | Critical? |
|---------|------------|-------------|-----------|
| Majestic | $99.99+ | High-quality backlinks with anchor text | ⭐ HIGH |
| Firecrawl | $49-199 | JS rendering, modern sites | MEDIUM |
| WhoisXML | $30-300 | Subdomain discovery | LOW |
| SerpAPI | $50-250 | Real-time search results | MEDIUM |
| OpenCorporates | FREE-$500 | Corporate records | LOW (free tier OK) |
| Ahrefs | $99-999 | Backlinks (alternative to Majestic) | LOW (Majestic preferred) |
| WorldCheck | Enterprise | Sanctions screening | LOW (niche) |
| BigQuery | Usage-based | Large-scale domain queries | LOW (not implemented) |

**Recommended Minimum:**
- ✅ Majestic ($99/mo) - Essential for quality backlinks
- ✅ Common Crawl (FREE) - Primary data source
- ✅ Wayback Machine (FREE) - Fallback archiving

**Total Minimum Cost:** $99/month (Majestic only)

---

## Data Sources by Use Case

### Backlink Discovery
- **Primary:** Common Crawl (FREE)
- **Quality Enhancement:** Majestic (PAID)
- **Historical Fallback:** Wayback Machine (FREE)
- **Alternative (unused):** Ahrefs (PAID)

### Subdomain Discovery
- **Free:** crt.sh
- **Paid:** WhoisXML API
- **Open Source:** Sublist3r

### Corporate Intelligence
- **Company Records:** OpenCorporates, EDGAR
- **Leaked Documents:** Aleph/OCCRP
- **Sanctions:** WorldCheck (enterprise)

### Content Scraping
- **Modern Sites:** Firecrawl (PAID, JS rendering)
- **Static Sites:** Common Crawl Archives (FREE)
- **Live Fallback:** Wayback Machine (FREE)

### Search Results
- **Real-time:** SerpAPI (PAID)
- **Archived:** Common Crawl (FREE)

---

## Proposed Additions for LinkLater

### HIGH PRIORITY (Free/Cheap)
1. **Move alldom discovery CLIs to LinkLater** → `/modules/linklater/discovery/`
   - crt.sh subdomain discovery
   - CC Index search
   - WhoisXML subdomain discovery

### MEDIUM PRIORITY (Implementation effort)
2. **Add Majestic TopicalTrustFlow** → Category-based domain discovery
3. **Add BigQuery CC Index queries** → Large-scale domain filtering

### LOW PRIORITY (Expensive/Niche)
4. **Ahrefs integration** → Alternative to Majestic (if needed)
5. **WorldCheck integration** → Sanctions screening (niche use case)

---

---

## LinkLater Internal Capabilities (DRILL System)

### Crawling System (`drill/`)

| Component | File | Description |
|-----------|------|-------------|
| **3-Tier Crawler** | `crawler.py` | Go/Colly → Go/Rod → Python/Playwright |
| **Go Bridge** | `go_bridge.py` | Python-Go interprocess communication |
| **Discovery** | `discovery.py` | URL discovery from multiple sources |
| **Link Processor** | `link_processor.py` | URL normalization, categorization |
| **JS Detector** | `js_detector.py` | SPA/dynamic content detection |
| **Entity Extractor** | `extractors.py` | Companies, persons, emails, phones |
| **Link Pipeline** | `linkpipeline.py` | GlobalLinks → ES with enrichments |
| **Archive Freshness** | `archive_freshness.py` | CC/Wayback freshness checking |
| **GlobalLinks Intel** | `globallinks_intel.py` | Pre-flight domain intelligence |

### Scraping (`scraping/`)

| Component | File | Description |
|-----------|------|-------------|
| **CC-First Scraper** | `cc_first_scraper.py` | CC → Wayback → Firecrawl fallback |
| **WARC Parser** | `warc_parser.py` | Extract content from WARC records |
| **Binary Extractor** | `binary_extractor.py` | PDF/DOCX/XLSX text extraction |

### Archives (`archives/`)

| Component | File | Description |
|-----------|------|-------------|
| **CC Index Client** | `cc_index_client.py` | Query CC Index API |
| **Snapshot Differ** | `snapshot_differ.py` | Detect archive changes |
| **Hybrid Archive** | `hybrid_archive.py` | Fast + deep archive search |
| **Fast Scanner** | `fast_scanner.py` | CDX-based keyword scanning |
| **Optimal Archive** | `optimal_archive.py` | Multi-year exhaustive search |

### Link Graph (`linkgraph/`)

| Component | File | Description |
|-----------|------|-------------|
| **GlobalLinks** | `globallinks.py` | Go binary client for WAT extraction |
| **CC Graph** | `cc_graph.py` | CC Web Graph ES client |

### Discovery (`discovery/`)

| Component | File | Description |
|-----------|------|-------------|
| **Unified Discovery** | `unified_discovery.py` | Single interface for all methods |
| **Domain Filters** | `domain_filters.py` | BigQuery, PageRank, Tranco, CF |
| **GA Tracker** | `ga_tracker.py` | Google Analytics tracker discovery |
| **Outlink Extractor** | `outlink_extractor.py` | Extract outlinks from HTML |

### Alerts (`alerts/`)

| Component | File | Description |
|-----------|------|-------------|
| **Link Alerts** | `link_alerts.py` | Category-based pattern alerting |

### Tor (`tor/`)

| Component | File | Description |
|-----------|------|-------------|
| **Tor Crawler** | `tor_crawler.py` | Colly-style onion crawler |
| **Tor Ingest** | `tor_ingest.py` | Ingest management |
| **Ahmia Importer** | `ahmia_importer.py` | Import from Ahmia |

### Temporal

| Component | File | Description |
|-----------|------|-------------|
| **Temporal Analyzer** | `temporal.py` | URL timeline (first_seen/last_seen) |

### Unified API

| Component | File | Description |
|-----------|------|-------------|
| **LinkLater API** | `api.py` | 148+ methods via singleton |
| **MCP Server** | `mcp/server.py` | MCP interface (30+ tools) |

---

## Full Capability Matrix

| Capability | Primary Source | Fallback | Cost |
|------------|---------------|----------|------|
| **Backlink Discovery** | GlobalLinks + CC Graph | Majestic | FREE/PAID |
| **Content Archiving** | Common Crawl | Wayback | FREE |
| **Live Scraping** | CC-First | Firecrawl | FREE/PAID |
| **Entity Extraction** | DRILL extractors | - | FREE |
| **Subdomain Discovery** | crt.sh | WhoisXML | FREE/PAID |
| **WHOIS Clustering** | WhoisXML | - | PAID |
| **News Search** | GDELT + NewsAPI | DuckDuckGo | FREE |
| **Domain Authority** | OpenPageRank | Tranco | FREE |
| **Temporal Analysis** | Wayback CDX | CC Index | FREE |
| **Category Alerting** | DRILL alerts | - | FREE |
| **Tor Crawling** | DRILL Tor crawler | - | FREE |
| **Binary Extraction** | DRILL binary_extractor | - | FREE |

---

**Last Updated:** 2025-12-02
**Total External Resources:** 14
**Free Resources:** 6 (43%)
**Paid Resources:** 8 (57%)
**Fully Integrated in LinkLater:** 12+ (CC, Wayback, Majestic, GlobalLinks, crt.sh, WhoisXML, GDELT, NewsAPI, OpenPageRank, Tranco, Firecrawl, Aleph)
