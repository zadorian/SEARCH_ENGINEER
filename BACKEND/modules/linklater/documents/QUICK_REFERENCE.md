# LinkLater Quick Reference

## Installation
```python
from modules.linklater.api import linklater
```

## Archive Scraping
```python
# Single URL (CC → Wayback → Firecrawl)
result = await linklater.scrape_url("https://example.com/doc.pdf")

# Batch
results = await linklater.scrape_batch(["url1", "url2"])

# Check CC index
cdx = await linklater.check_cc_index("https://example.com")
```

## Entity Extraction
```python
# All entities
entities = linklater.extract_entities(text)
# Returns: {'companies': [...], 'persons': [...], 'registrations': [...]}

# Specific types
companies = linklater.extract_companies(text)
persons = linklater.extract_persons(text)
registrations = linklater.extract_registrations(text)
```

## Backlinks & Outlinks
```python
# Basic (CC Graph + GlobalLinks)
backlinks = await linklater.get_backlinks("example.com", limit=100)
outlinks = await linklater.get_outlinks("example.com", limit=100)

# Majestic (Premium - Fresh + Historic)
backlinks = await linklater.get_majestic_backlinks(
    "example.com",
    mode="fresh",        # or "historic" (5 years)
    result_type="pages"  # or "domains"
)

# Search anchor texts in Majestic backlinks
libyan_links = [
    b for b in backlinks
    if any(kw in b.get('anchor_text', '').lower()
           for kw in ['libya', 'libyan', 'tripoli'])
]

# Advanced filtering (GlobalLinks only)
outlinks = await linklater.extract_domain_outlinks(
    domains=["bbc.com"],
    archive="CC-MAIN-2024-10",
    country_tlds=[".gov.uk"],
    url_keywords=["parliament"],
    exclude_keywords=["spam"]
)

# Search local data
results = await linklater.search_domain_in_links("bbc.com", "data/links/")
```

## Binary Extraction
```python
# Check support
supported = linklater.can_extract_binary("application/pdf")

# Extract text
result = linklater.extract_text_from_binary(pdf_bytes, "application/pdf")
if result.success:
    print(result.text)
```

## Content Enrichment
```python
# Single URL
enriched = await linklater.enrich_url("https://example.com")

# Batch
results = await linklater.enrich_batch([
    {"url": "url1", "title": "Title 1"},
    {"url": "url2", "title": "Title 2"}
])
```

## Keyword Variations
```python
# Search with variations
async for match in linklater.search_keyword_variations(
    keywords=["company name"],
    domain="example.com"
):
    print(f"{match.variation} at {match.url}")

# Generate variations
variations = linklater.generate_variations("keyword")
variations_llm = await linklater.generate_variations_llm("keyword")
```

## Archive Search
```python
# Historical search
async for result in linklater.search_archives(
    domain="example.com",
    keyword="annual report",
    start_year=2020,
    end_year=2024
):
    print(result)
```

## WARC Parsing
```python
# Extract HTML
html = linklater.extract_html_from_warc(warc_bytes)

# Convert to markdown
markdown = linklater.html_to_markdown(html)

# Extract binary
binary_data, mime_type = linklater.extract_binary_from_warc(warc_bytes)
```

## Binary Detection
```python
# Find GlobalLinks binaries
outlinker = linklater.find_globallinks_binary("outlinker")
linksapi = linklater.find_globallinks_binary("linksapi")
storelinks = linklater.find_globallinks_binary("storelinks")
importer = linklater.find_globallinks_binary("importer")
```

## Statistics
```python
# Get scraper stats
stats = linklater.get_scraper_stats()
# Returns: {'cc_hits': N, 'wayback_hits': N, 'firecrawl_hits': N}

# Reset stats
linklater.reset_scraper_stats()
```

## Data Sources

### CC Web Graph
- 157M domains, 2.1B edges
- Elasticsearch-backed
- Fast HTTP API

### GlobalLinks
- 4 Go binaries (outlinker, linksapi, storelinks, importer)
- ~6 billion backlinks/month
- 300K pages/minute processing
- Advanced filtering (country TLDs, keywords)
- Anchor text extraction

### Majestic (INTEGRATED ✅)
- Premium backlink intelligence
- Fresh Index (90 days)
- Historic Index (5+ years)
- Anchor text extraction
- Trust Flow / Citation Flow metrics
- Referring domains + backlink pages

### Common Crawl
- 3-tier fallback (CC → Wayback → Firecrawl)
- Binary extraction (PDF, DOCX, XLSX, PPTX)
- Historical archives

## Link Record Format
```python
@dataclass
class LinkRecord:
    source: str          # Source domain
    target: str          # Target domain
    weight: int          # Link weight (optional)
    anchor_text: str     # Anchor text (optional)
    provider: str        # cc_graph, globallinks, etc.
```

## Performance Tips

1. **Use batch methods** for multiple URLs
2. **Enable GlobalLinks** for maximum coverage: `use_globallinks=True`
3. **Filter early** with country_tlds and keywords
4. **Cache results** - scraper has built-in stats tracking
5. **Limit results** appropriately (default: 100)

## Common Patterns

### Comprehensive Link Analysis
```python
# Get both backlinks and outlinks
backlinks = await linklater.get_backlinks("example.com", limit=100)
outlinks = await linklater.get_outlinks("example.com", limit=100)

# Analyze
print(f"Backlinks: {len(backlinks)}")
print(f"Outlinks: {len(outlinks)}")
```

### Targeted Domain Research
```python
# Extract UK government links from news sites
links = await linklater.extract_domain_outlinks(
    domains=["bbc.com", "guardian.com"],
    country_tlds=[".gov.uk"],
    url_keywords=["parliament", "minister"],
    archive="CC-MAIN-2024-10"
)
```

### Document Processing Pipeline
```python
# 1. Scrape
result = await linklater.scrape_url("https://example.com/report.pdf")

# 2. Extract binary
if result.content:
    extracted = linklater.extract_text_from_binary(
        result.content.encode(),
        "application/pdf"
    )

    # 3. Extract entities
    if extracted.success:
        entities = linklater.extract_entities(extracted.text)
        print(entities)
```

### Archive Deep Dive
```python
# Search historical archives for specific content
async for match in linklater.search_archives(
    domain="example.com",
    keyword="quarterly report",
    start_year=2018,
    end_year=2024
):
    # Process each historical snapshot
    print(f"Found: {match.url} ({match.timestamp})")
```

## Error Handling
```python
try:
    result = await linklater.scrape_url(url)
    if result.status_code == 200:
        # Process
        pass
except Exception as e:
    print(f"Error: {e}")
```

## Module Structure
```
modules/linklater/
├── api.py              # ← Import from here
├── linkgraph/          # CC Graph + GlobalLinks
├── mcp/                # MCP server
├── scraping/           # Archive scraping
├── enrichment/         # Entity extraction
├── discovery/          # Keyword variations
├── archives/           # Historical search
└── pipelines/          # Workflows
```

---

**One import. 150+ methods. Everything you need.**

```python
from modules.linklater.api import linklater
```
