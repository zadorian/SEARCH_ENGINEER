# LinkLater - MASTER DOCUMENTATION

**The Complete Archive Intelligence & Link Graph System**

---

## 🎯 What Is LinkLater?

LinkLater is the **unified archive intelligence and link graph system** for Drill Search, providing:

1. **CC Web Graph** - 157M domains, 2.1B edges in Elasticsearch for instant backlink/outlink lookups
2. **GlobalLinks** - Precomputed CC link relationships via Go binaries
3. **Archive Scanning** - Wayback (80 concurrent) + Common Crawl (70 concurrent) + Firecrawl (100)
4. **Binary Extraction** - PDF, DOCX, XLSX, PPTX text extraction from archives
5. **Entity Extraction** - Companies, persons, registrations from documents
6. **Link Hopping** - Navigate site-to-site via backlink/outlink graphs
7. **Keyword Search** - Find keywords across archive snapshots with variations
8. **Multi-tier fallback** - CC → Wayback → Firecrawl automatic fallback chain

---

## 📂 Complete Architecture

```
drill-search-app/
├── python-backend/
│   ├── modules/linklater/                 # Core Python module
│   │   ├── archives/                      # Archive scanners
│   │   │   ├── fast_scanner.py            # Wayback scanner (80 concurrent)
│   │   │   ├── optimal_archive.py         # Speed-optimized archive search
│   │   │   └── hybrid_archive.py          # Hybrid archive strategy
│   │   ├── discovery/                     # Discovery engines
│   │   │   └── keyword_variations.py      # Keyword variation search
│   │   ├── enrichment/                    # Content enrichment
│   │   │   ├── cc_enricher.py             # CC enricher with entities/outlinks
│   │   │   └── entity_patterns.py         # Entity extraction patterns
│   │   ├── scraping/                      # Scraping engines
│   │   │   ├── cc_first_scraper.py        # CC-first scraper with fallback
│   │   │   ├── warc_parser.py             # WARC file parser
│   │   │   └── binary_extractor.py        # PDF/DOCX/XLSX/PPTX extraction
│   │   ├── graph/                         # (Future graph modules)
│   │   ├── pipelines/                     # Automated pipelines
│   │   │   ├── extract_domain_pdfs.sh     # Extract all PDFs from domain
│   │   │   ├── extract_domain_docs.sh     # Extract all docs + entities
│   │   │   └── full_entity_extraction.sh  # Full graph pipeline
│   │   ├── tests/                         # Test suite
│   │   │   └── test_binary_extraction.py
│   │   ├── linklater.py                   # CLI interface
│   │   └── linklater_cli.py               # Original CLI
│   ├── api/
│   │   └── linklater_routes.py            # FastAPI routes
│   ├── mcp_servers/
│   │   └── linklater_mcp.py               # Python MCP server
│   └── modules/brute/
│       └── linklater_priority_scraper.py  # Priority scraping
├── server/
│   ├── services/
│   │   ├── linklater.ts                   # TypeScript LinkLater class (3870 lines)
│   │   └── linklaterPersistence.ts        # Elasticsearch persistence
│   ├── mcp/
│   │   └── linklater-server.ts            # TypeScript MCP server
│   └── routers/
│       └── linkLaterRouter.ts             # API routes
├── client/src/components/location/
│   ├── LinkLaterConsole.tsx               # Console UI
│   ├── LinkLaterGraph.tsx                 # Graph visualization
│   └── DomainProfilePanel.tsx             # Domain profiles
├── scripts/
│   └── linklater_domain_spider.py         # Domain spider script
└── categorizer-filterer/globallinks/
    └── bin/outlinker                      # GlobalLinks Go binary
```

---

## 🚀 Quick Start

### 1. Automated Pipelines (Easiest)

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/pipelines

# Extract all PDFs from a domain
./extract_domain_pdfs.sh "company.com"

# Extract all documents (PDF, DOCX, XLSX, PPTX) + entities
./extract_domain_docs.sh "company.com"

# Full knowledge graph (documents + entities + outlinks + backlinks)
./full_entity_extraction.sh "company.com" company_graph.json
```

### 2. CLI Usage

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend

# Single URL with binary extraction
python modules/linklater/linklater.py --url "https://example.com/report.pdf"

# Batch URLs with entity extraction
python modules/linklater/linklater.py \
  --file urls.txt \
  --extract-entities \
  --extract-outlinks \
  --output results.json

# Full extraction (everything)
python modules/linklater/linklater.py \
  --url "https://example.com" \
  --extract-binary \
  --extract-entities \
  --extract-outlinks \
  --verbose
```

### 3. MCP Server (Claude Code Integration)

**Python MCP Server:**
```json
{
  "mcpServers": {
    "linklater": {
      "command": "python3",
      "args": ["/path/to/drill-search-app/python-backend/mcp_servers/linklater_mcp.py"]
    }
  }
}
```

**TypeScript MCP Server:**
```json
{
  "mcpServers": {
    "linklater": {
      "command": "npx",
      "args": ["tsx", "/path/to/drill-search-app/server/mcp/linklater-server.ts"]
    }
  }
}
```

---

## 📊 Core Capabilities

### 1. Archive Scraping (CC → Wayback → Firecrawl)

**Three-tier automatic fallback:**

```python
from modules.linklater.scraping.cc_first_scraper import CCFirstScraper

scraper = CCFirstScraper(extract_binary=True)
result = await scraper.get_content("https://example.com/report.pdf")

# Automatically tries:
# 1. Common Crawl → Found PDF, extracted text ✓
# OR
# 2. Wayback Machine → Found PDF, extracted text ✓
# OR
# 3. Firecrawl → Live scrape ✓
```

**Supported file types:**
- ✅ PDF (.pdf) - pypdf + pdfplumber
- ✅ Word (.docx) - python-docx
- ✅ Excel (.xlsx) - openpyxl
- ✅ PowerPoint (.pptx) - python-pptx
- ✅ Archives (.zip, .tar, .gz)

### 2. Entity Extraction

```python
from modules.linklater.enrichment.cc_enricher import CCEnricher

enricher = CCEnricher(extract_entities=True, extract_outlinks=True)
result = await enricher.enrich_single("https://example.com")

# result.companies - List of companies mentioned
# result.persons - List of persons mentioned
# result.registrations - Registration numbers
# result.outlinks - External links from page
```

### 3. Backlinks & Outlinks (CC Web Graph)

**Via Elasticsearch (157M domains, 2.1B edges):**

```python
# Get backlinks (who links TO a domain)
POST /api/cc/inbound-backlinks
{
  "targets": ["example.com"],
  "period": "latest",
  "min_weight": 1,
  "limit": 100
}

# Get outlinks (what a domain links TO)
POST /api/cc/outbound-outlinks
{
  "sources": ["example.com"],
  "period": "latest",
  "limit": 100
}
```

**Via GlobalLinks (Go binary):**

```bash
# Direct binary usage
./categorizer-filterer/globallinks/bin/outlinker extract example.com
```

### 4. Link Hopping (Graph Traversal)

```typescript
import linklater from '@/server/services/linklater';

// Navigate 2 hops through link graph
const graph = await linklater.queryGraphNeighbors({
  startDomain: 'example.com',
  hops: 2,
  direction: 'bidirectional',  // inbound, outbound, or bidirectional
  maxNeighborsPerHop: 100
});

// graph.nodes - All discovered domains
// graph.edges - Link relationships
```

### 5. Keyword Variations Search

```typescript
// Find all variations of "portofino"
for await (const match of linklater.searchKeywordVariations({
  keywords: ['portofino', 'john smith'],
  verifySnippets: true
})) {
  console.log(`${match.source}: ${match.url}`);
  console.log(`  Matched variation: ${match.variationMatched}`);
}
```

**Generates variations:**
- Misspellings (phonetic, keyboard proximity)
- Swapped words
- Different separators (-, _, space)
- Case variations

### 6. Category Search

```typescript
// Search specific website categories
for await (const result of linklater.searchCategories({
  query: 'annual report',
  categories: ['news', 'registry', 'financial'],
  maxPerCategory: 50
})) {
  console.log(`[${result.category}] ${result.title}`);
}
```

**200+ categories:**
- News sites
- Corporate registries
- Government databases
- Academic repositories
- Financial databases
- Court records

---

## 🔧 MCP Tools Available

### Python MCP Server (`linklater_mcp.py`)

1. **`get_backlinks`** - Get domains linking TO a target domain
2. **`get_outlinks`** - Get domains a target domain links TO
3. **`hop_links`** - Navigate site-to-site through links
4. **`search_archives`** - Search archive snapshots for keywords
5. **`scrape_url`** - Scrape URL content (CC-first → Firecrawl fallback)
6. **`extract_entities`** - Extract companies, people, registrations
7. **`enrich_urls`** - Full enrichment: scrape + entities + links + keywords
8. **`batch_domain_extract`** - Process multiple domains from file

### TypeScript MCP Server (`linklater-server.ts`)

1. **`linklater_enrich_batch`** - Enrich URLs with archive content, entities, keywords, links
2. **`linklater_get_backlinks`** - Get backlinks for domain (CC Graph + GlobalLinks)
3. **`linklater_get_outlinks`** - Get outlinks for domain
4. **`linklater_search_archives`** - Search archive snapshots
5. **`linklater_hop_links`** - Navigate via link graph
6. **`linklater_scrape_live`** - Scrape current content via Firecrawl
7. **`linklater_scrape_batch`** - Batch scrape multiple URLs
8. **`linklater_extract_entities`** - Extract entities from text
9. **`linklater_corpus_search`** - Search Elasticsearch corpus
10. **`linklater_corpus_stats`** - Get corpus statistics
11. **`linklater_corpus_get`** - Get document by URL
12. **`linklater_corpus_delete`** - Delete document from corpus
13. **`linklater_corpus_by_domain`** - Get all documents for domain

---

## 🎯 Use Cases

### 1. Domain Intelligence Report

```bash
# Complete domain analysis
./pipelines/full_entity_extraction.sh "target.com" target_graph.json

# Outputs:
# - All pages discovered
# - All binary documents extracted
# - All entities (companies, persons, registrations)
# - All outlinks (external links)
# - All backlinks (from CC WebGraph)
# - Knowledge graph (nodes + edges)
```

### 2. Competitive Intelligence

```bash
# Extract all PDFs from competitor
./pipelines/extract_domain_pdfs.sh "competitor.com"

# Find all mentioned companies
jq '.companies[].text' competitor.com_pdfs.json

# Find who links to them
curl -X POST 'http://localhost:8001/api/cc/inbound-backlinks' \
  -d '{"targets": ["competitor.com"], "limit": 1000}'
```

### 3. Link Network Analysis

```bash
# Download CC WebGraph
cd ~/cc_webgraph_data
curl -L "https://data.commoncrawl.org/projects/hyperlinkgraph/cc-main-2025-sep-oct-nov/host/cc-main-2025-sep-oct-nov-host-edges.txt.gz" -o host-edges.txt.gz

# Find all backlinks
zgrep "target-domain.com" host-edges.txt.gz

# Extract entities from all backlink domains
for domain in $(zgrep "target-domain.com" host-edges.txt.gz | cut -f1); do
  ./pipelines/extract_domain_docs.sh "$domain" "backlinks_analysis/"
done
```

### 4. Maximum Recall Document Search

```bash
# Find ALL documents matching pattern
python modules/linklater/linklater.py \
  --url "*.example.com/*.pdf" \
  --extract-binary \
  --extract-entities \
  --concurrent 100 \
  --output all_pdfs.json
```

### 5. Historical Domain Analysis

```typescript
// Find all snapshots of a domain
const snapshots = await linklater.searchArchives({
  domain: 'example.com',
  keyword: 'annual report',
  startDate: new Date('2020-01-01'),
  endDate: new Date('2025-01-01')
});

// Extract entities from each snapshot
for (const snapshot of snapshots) {
  const content = await linklater.scrapeURL(snapshot.url);
  const entities = await linklater.extractEntities(content.text);
  // Track entity changes over time
}
```

---

## 📈 Performance Characteristics

| Operation | Latency | Concurrency | Notes |
|-----------|---------|-------------|-------|
| **CC index lookup** | 50-100ms | Unlimited | CDX API |
| **CC WARC fetch** | 200-300ms | 70 concurrent | S3 retrieval |
| **Wayback lookup** | 150-250ms | 80 concurrent | Availability API |
| **Wayback fetch** | 300-500ms | 80 concurrent | Snapshot retrieval |
| **Firecrawl scrape** | 2-5s | 100 concurrent | Live web |
| **PDF extraction** | +150ms | Parallel | pypdf/pdfplumber |
| **DOCX extraction** | +100ms | Parallel | python-docx |
| **Entity extraction** | +50-100ms | Parallel | Regex patterns |
| **Outlink extraction** | +10-20ms | Parallel | HTML parsing |
| **CC Graph query** | <100ms | High | Elasticsearch |
| **GlobalLinks query** | 50-200ms | Medium | Go binary |

**Cache benefits:** LRU cache means repeated URLs = 0ms

---

## 🔗 Integration Points

### With FileType Search

```python
# FileType search finds PDFs
from modules.brute.targeted_searches.filetypes.filetype import FiletypeSearcher

results = FiletypeSearcher().search("annual report", "pdf")

# LinkLater extracts text from found PDFs
for result in results:
    scraped = await scraper.get_content(result['url'])
    # scraped.content = extracted PDF text
```

### With InDOM Search

```python
# InDOM discovers domain
from modules.brute.targeted_searches.domain.indom import IndomSearcher

domains = IndomSearcher().search("tesla")

# LinkLater extracts all documents + entities from domain
for domain in domains:
    await enricher.enrich_batch([{'url': f"https://{domain}"}])
```

### With Matrix Router

```typescript
// LinkLater feeds into Elasticsearch
import { indexLinklaterDocument } from '@/server/services/linklaterPersistence';

const result = await linklater.enrichBatch(urls);

// Auto-indexes to Elasticsearch
for (const doc of result.enrichedResults) {
  await indexLinklaterDocument(doc);
}

// Matrix router can then query Elasticsearch
```

---

## 🛠️ Configuration

### Environment Variables

```bash
# Required for Firecrawl fallback tier
FIRECRAWL_API_KEY=sk-...

# Optional overrides
LINKLATER_CACHE_DIR=/path/to/cache
LINKLATER_CC_CONCURRENT=70
LINKLATER_WAYBACK_CONCURRENT=80
LINKLATER_FIRECRAWL_CONCURRENT=100
```

### CLI Flags

```
--url URL                    Single URL to scrape
--file FILE                  File with URLs (one per line)
--extract-binary            Extract text from PDF/DOCX/etc [default: True]
--no-binary                 Disable binary extraction (HTML only)
--extract-entities          Extract entities (companies, persons, registrations)
--extract-outlinks          Extract outlinks (external links from pages)
--cc-only                   Common Crawl only (no Wayback/Firecrawl)
--format {json,markdown,text} Output format
--concurrent N              Max concurrent requests
--verbose                   Verbose output with progress
--stats                     Print statistics
--output FILE               Output file
```

---

## 📚 Documentation Files

- **`MASTER_README.md`** (this file) - Complete system documentation
- **`LINKLATER_README.md`** - CLI & pipelines documentation
- **`PIPELINES_ADDED.md`** - Automated pipeline documentation
- **`IMPLEMENTATION_COMPLETE.md`** - Binary extraction implementation
- **`WAYBACK_FALLBACK_ADDED.md`** - Wayback integration documentation
- **`BINARY_EXTRACTION_INTEGRATION.md`** - Binary extraction technical details
- **`CONSOLIDATION_PLAN.md`** - Module consolidation plan
- **`/docs/LINKLATER_CONSOLIDATION_COMPLETE.md`** - Consolidation completion report
- **`/docs/LINKLATER_TIER1_INTEGRATION_COMPLETE.md`** - Tier 1 methods integration
- **`/docs/LINKLATER_CAPABILITY_AUDIT.md`** - Complete capability inventory (50-60 methods)

---

## 🚨 Known Limitations

1. **Binary formats:**
   - .doc (old Word) - requires antiword CLI
   - .xls (old Excel) - requires xlrd
   - .ppt (old PowerPoint) - not supported

2. **Common Crawl:**
   - 5MB file truncation limit
   - Monthly archive updates
   - Not real-time

3. **OCR:**
   - Scanned PDFs (images) require tesseract integration

4. **Backlinks:**
   - CC WebGraph updated monthly (not real-time)
   - Manual download required for bulk analysis

---

## 🎯 Future Enhancements

### Tier 2 (Company Intelligence) - 6 methods
1. `searchCompany()` - Multi-registry search
2. `mapDomainToCompany()` - Domain attribution
3. `searchEdgar()` - SEC filings
4. `checkSanctions()` - Risk screening
5. `findRelatedViaGA()` - Google Analytics attribution
6. `searchUKCompany()` - Companies House integration

### Tier 3 (AI & Search) - 4 methods
1. `optimaSearch()` - Optima AI
2. `youSearch()` - You.com
3. `grokSearch()` - Grok/X
4. `analyzeOSINT()` - AI synthesis

### Tier 4 (Utilities)
1. OCR integration (tesseract)
2. Legacy format support (.doc, .xls, .ppt)
3. Real-time backlink tracking
4. Graph visualization enhancements

---

## ✅ Status Summary

**Current Capabilities:**
- ✅ Binary file extraction (PDF, DOCX, XLSX, PPTX)
- ✅ Three-tier fallback (CC → Wayback → Firecrawl)
- ✅ Entity extraction (companies, persons, registrations)
- ✅ Outlink extraction
- ✅ Backlink queries (CC Graph + GlobalLinks)
- ✅ Keyword variation search
- ✅ Category search
- ✅ Graph traversal
- ✅ Archive scanning
- ✅ Automated pipelines
- ✅ Two MCP servers (Python & TypeScript)
- ✅ Elasticsearch persistence
- ✅ React UI components

**Total Methods Available:**
- Core LinkLater: 15+ methods
- Tier 1 integrated: 6 methods
- MCP tools: 13+ tools
- Automated pipelines: 3 scripts
- **Estimated total when complete: 50-60 methods**

**Production Status:** ✅ **PRODUCTION READY**

---

## 🔍 Quick Reference

### Common Commands

```bash
# Extract all PDFs from domain
./pipelines/extract_domain_pdfs.sh "company.com"

# Extract all documents + entities
./pipelines/extract_domain_docs.sh "company.com"

# Full knowledge graph
./pipelines/full_entity_extraction.sh "company.com" graph.json

# CLI single URL
python modules/linklater/linklater.py --url "https://example.com/doc.pdf"

# CLI batch with entities
python modules/linklater/linklater.py --file urls.txt --extract-entities --extract-outlinks

# Get backlinks via API
curl -X POST 'http://localhost:8001/api/cc/inbound-backlinks' -d '{"targets": ["example.com"]}'

# Get outlinks via API
curl -X POST 'http://localhost:8001/api/cc/outbound-outlinks' -d '{"sources": ["example.com"]}'
```

### Common Imports

```python
# Python
from modules.linklater.scraping.cc_first_scraper import CCFirstScraper
from modules.linklater.enrichment.cc_enricher import CCEnricher
from modules.linklater.discovery.keyword_variations import KeywordVariationsSearch
```

```typescript
// TypeScript
import linklater from '@/server/services/linklater';
import { indexLinklaterDocument } from '@/server/services/linklaterPersistence';
```

---

**END OF MASTER DOCUMENTATION**

For specific topics, see the specialized documentation files listed above.
