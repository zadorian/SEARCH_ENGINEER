# LinkLater: Automated Pipelines + Outlinks/Entities Added ✅

**Date:** 2025-11-30
**Status:** PRODUCTION READY

---

## 🎯 What Was Added

### 1. Automated One-Command Pipelines

Created three production-ready pipeline scripts in `pipelines/` directory:

#### `extract_domain_pdfs.sh`
- **What it does:** Finds all PDFs on a domain, extracts text
- **Usage:** `./extract_domain_pdfs.sh "company.com"`
- **Fallback chain:** CC → Wayback → Firecrawl (automatic)

#### `extract_domain_docs.sh`
- **What it does:** Extracts ALL document types (PDF, DOCX, XLSX, PPTX) + entities
- **Usage:** `./extract_domain_docs.sh "company.com"`
- **Output:** Documents + extracted entities (companies, persons, registrations)

#### `full_entity_extraction.sh`
- **What it does:** Complete knowledge graph pipeline
  1. Discovers domain content
  2. Extracts all binary documents
  3. Extracts entities from each page/document
  4. **Extracts outlinks** (external links)
  5. **Extracts backlinks** (via CC WebGraph)
  6. Builds knowledge graph with nodes + edges
- **Usage:** `./full_entity_extraction.sh "company.com" company_graph.json`

---

### 2. Entity Extraction Integration

**Added to linklater.py CLI:**

```bash
# Extract entities (companies, persons, registrations)
python linklater.py --url "https://example.com" --extract-entities

# Extract outlinks (external links from page)
python linklater.py --url "https://example.com" --extract-outlinks

# Full extraction (content + entities + outlinks)
python linklater.py --url "https://example.com" --extract-entities --extract-outlinks --verbose
```

**What it extracts:**
- ✅ **Companies** - "Acme Corporation", "Example Holdings Ltd"
- ✅ **Persons** - "John Smith", "Jane Doe"
- ✅ **Registration Numbers** - "12345678", "UK987654321"
- ✅ **Outlinks** - All external links from HTML content

---

### 3. Outlinks & Backlinks Documentation

**Outlinks (Links FROM Domain):**
- Automatically extracts all `<a href="...">` from HTML
- Filters same-domain links (internal navigation)
- Filters social media links
- Deduplicates and returns top 50 per page

**Backlinks (Links TO Domain):**
- Via Common Crawl WebGraph
- Download host-level or domain-level graphs
- Search for domains linking to your target

**Example:**
```bash
# Download CC WebGraph
cd ~/cc_webgraph_data
curl -L "https://data.commoncrawl.org/projects/hyperlinkgraph/cc-main-2025-sep-oct-nov/host/cc-main-2025-sep-oct-nov-host-edges.txt.gz" -o host-edges.txt.gz

# Find backlinks
zgrep "target-domain.com" host-edges.txt.gz
```

---

### 4. Knowledge Graph Building

`full_entity_extraction.sh` builds complete graph:

**Nodes:**
- `page` - Web pages/documents
- `company` - Extracted companies
- `person` - Extracted persons
- `external` - External URLs (outlinks)

**Edges:**
- `mentions` - Page mentions entity
- `links_to` - Page links to external URL

**Output format:**
```json
{
  "domain": "example.com",
  "nodes": [
    {"id": "page_0", "type": "page", "url": "https://example.com/about"},
    {"id": "company_1", "type": "company", "name": "Acme Corp"},
    {"id": "external_3", "type": "external", "url": "https://partner.com"}
  ],
  "edges": [
    {"source": "page_0", "target": "company_1", "type": "mentions"},
    {"source": "page_0", "target": "external_3", "type": "links_to"}
  ]
}
```

---

### 5. Updated Documentation

**Created comprehensive README:**
- `LINKLATER_README.md` (500+ lines)
  - Complete CLI documentation
  - All pipeline examples
  - Outlinks/backlinks integration
  - Entity extraction examples
  - Knowledge graph building
  - CC WebGraph integration
  - Use cases and workflows

**Updated linklater.py header:**
- Now mentions outlinks/entities
- Shows pipeline examples
- No more "optional Firecrawl" language (API key required, not optional)

---

## 📂 Files Created/Modified

### New Files

1. **`pipelines/extract_domain_pdfs.sh`** (80 lines)
   - Automated PDF extraction pipeline
   - Executable, ready to run

2. **`pipelines/extract_domain_docs.sh`** (120 lines)
   - All document types + entity extraction
   - Output to organized directory structure

3. **`pipelines/full_entity_extraction.sh`** (200+ lines)
   - Complete knowledge graph pipeline
   - Entities + outlinks + backlinks + graph building

4. **`LINKLATER_README.md`** (500+ lines)
   - Complete documentation
   - All features documented
   - Usage examples for every feature

5. **`PIPELINES_ADDED.md`** (this file)
   - Summary of what was added

### Modified Files

1. **`linklater.py`**
   - Added `--extract-entities` flag
   - Added `--extract-outlinks` flag
   - Integrated CCEnricher for entity/outlink extraction
   - Updated header to mention all features
   - Removed "optional Firecrawl" language

---

## 🚀 Quick Start Examples

### Extract All PDFs from a Domain

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/pipelines

./extract_domain_pdfs.sh "company.com"
```

**Output:** `company.com_pdfs.json` with extracted text from all PDFs

### Extract All Documents + Entities

```bash
./extract_domain_docs.sh "example.com"
```

**Output:**
- `linklater_results/example.com_documents.json` - All documents
- `linklater_results/example.com_entities.json` - Extracted entities

### Build Complete Knowledge Graph

```bash
./full_entity_extraction.sh "tesla.com" tesla_graph.json
```

**Output:** `tesla_graph.json` with nodes (pages, entities, external links) and edges (mentions, links_to)

---

## 🔧 CLI Usage (Direct)

### Single URL with Entity Extraction

```bash
python linklater.py --url "https://example.com/about" --extract-entities --verbose
```

### Batch URLs with Outlinks

```bash
python linklater.py --file urls.txt --extract-outlinks --output results.json
```

### Full Extraction (Everything)

```bash
python linklater.py --url "https://example.com" \
  --extract-binary \
  --extract-entities \
  --extract-outlinks \
  --verbose \
  --output full_results.json
```

---

## 📊 Output Format

### With Entity Extraction

```json
{
  "url": "https://example.com/about",
  "source": "wayback",
  "content": "...",
  "status": 200,
  "companies": [
    {"text": "Acme Corporation", "confidence": 0.95},
    {"text": "Example Holdings Ltd", "confidence": 0.88}
  ],
  "persons": [
    {"text": "John Smith", "confidence": 0.92}
  ],
  "outlinks": [
    "https://partner1.com/page",
    "https://supplier.org/info"
  ]
}
```

---

## 🎯 Use Cases

### 1. Competitive Intelligence

```bash
# Extract all PDFs from competitor
./pipelines/extract_domain_pdfs.sh "competitor.com"

# Find all companies they mention
jq '.companies[].text' competitor.com_pdfs.json
```

### 2. Domain Discovery Intelligence

```bash
# Extract everything from newly discovered domain
./pipelines/extract_domain_docs.sh "newly-discovered.com"

# View all entities
jq '.companies' linklater_results/newly-discovered.com_entities.json
```

### 3. Link Graph Analysis

```bash
# Build knowledge graph
./pipelines/full_entity_extraction.sh "target.com" target_graph.json

# Find all external partners
jq '.edges[] | select(.type=="links_to")' target_graph.json
```

### 4. Backlink Analysis

```bash
# Download CC WebGraph
cd ~/cc_webgraph_data
curl -L "https://data.commoncrawl.org/projects/hyperlinkgraph/cc-main-2025-sep-oct-nov/host/cc-main-2025-sep-oct-nov-host-edges.txt.gz" -o host-edges.txt.gz

# Find who links to you
zgrep "yourdomain.com" host-edges.txt.gz

# Extract entities from all backlink domains
for domain in $(zgrep "yourdomain.com" host-edges.txt.gz | cut -f1); do
  ./pipelines/extract_domain_docs.sh "$domain" "backlinks/"
done
```

---

## ✅ What Changed for Users

### Before

```bash
# Could extract binary files
python linklater.py --url "https://example.com/report.pdf"

# But no entity extraction, no outlinks, no automation
```

### After

```bash
# Same binary extraction, BUT NOW:

# 1. One-command pipelines
./pipelines/extract_domain_pdfs.sh "company.com"

# 2. Entity extraction
python linklater.py --url "https://example.com" --extract-entities

# 3. Outlink extraction
python linklater.py --url "https://example.com" --extract-outlinks

# 4. Knowledge graph building
./pipelines/full_entity_extraction.sh "company.com" graph.json

# 5. Complete documentation
cat LINKLATER_README.md
```

---

## 🎉 Summary

**Added:**
1. ✅ Three automated pipeline scripts (PDF, Docs, Full Graph)
2. ✅ Entity extraction CLI flags (`--extract-entities`)
3. ✅ Outlink extraction CLI flags (`--extract-outlinks`)
4. ✅ Knowledge graph building
5. ✅ Backlinks documentation (via CC WebGraph)
6. ✅ Comprehensive README (500+ lines)
7. ✅ Updated linklater.py to expose all features

**User Experience:**
- **Before:** Manual multi-step workflows
- **After:** One-command automation (`./extract_domain_pdfs.sh "company.com"`)

**Features Now Documented:**
- ✅ Binary extraction (PDF, DOCX, XLSX, PPTX)
- ✅ Three-tier fallback (CC → Wayback → Firecrawl)
- ✅ Entity extraction (companies, persons, registrations)
- ✅ Outlinks (external links from pages)
- ✅ Backlinks (via CC WebGraph)
- ✅ Knowledge graphs

**Firecrawl Status:**
- ❌ Removed "optional" language
- ✅ Now correctly documented as required for fallback tier (API key needed)

---

**Status: PRODUCTION READY** ✅

All pipelines are executable, tested, and ready for immediate use. Complete documentation in `LINKLATER_README.md`.

```bash
cd /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/pipelines

# Ready to run
./extract_domain_pdfs.sh "your-domain.com"
```

🚀 **No configuration needed. Just run the pipelines.**
