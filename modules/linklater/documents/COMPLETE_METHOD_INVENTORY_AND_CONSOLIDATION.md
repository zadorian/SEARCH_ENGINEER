# LinkLater: Complete Method Inventory & Consolidation Plan

**Date:** 2025-11-30
**Goal:** Consolidate ALL LinkLater functionality into `/modules/linklater/` with unified API: `linklater.method_name()`

---

## 📋 COMPLETE METHOD INVENTORY (130+ Methods)

### Section 1: ALREADY IN `/modules/linklater/` ✅

#### A. **scraping/** - Archive Scraping & Binary Extraction

**File:** `/python-backend/modules/linklater/scraping/cc_first_scraper.py`
```
1. CCFirstScraper.__init__()
2. CCFirstScraper.check_cc_index(url)                 # Check CC CDX API
3. CCFirstScraper.fetch_from_cc(location)             # Fetch from CC WARC
4. CCFirstScraper.fetch_from_wayback(url)             # Fetch from Wayback
5. CCFirstScraper.fetch_from_firecrawl(url)           # Fetch from Firecrawl
6. CCFirstScraper.get_content(url)                    # Main method (3-tier fallback)
7. CCFirstScraper.batch_scrape(urls, max_concurrent)  # Batch scraping
8. CCFirstScraper.get_stats()                         # Get scraping statistics
9. CCFirstScraper.reset_stats()                       # Reset statistics
10. scrape_url(url, firecrawl_key)                    # Standalone function
11. scrape_urls(urls, firecrawl_key)                  # Standalone batch function
```

**File:** `/python-backend/modules/linklater/scraping/warc_parser.py`
```
12. WARCParser.extract_html(warc_data)                # Extract HTML from WARC
13. WARCParser.extract_metadata(warc_data)            # Extract WARC metadata
14. WARCParser.extract_binary(warc_data)              # Extract binary from WARC
15. html_to_markdown(html)                            # HTML → Markdown conversion
```

**File:** `/python-backend/modules/linklater/scraping/binary_extractor.py`
```
16. BinaryTextExtractor.__init__()
17. BinaryTextExtractor.can_extract(mime_type)        # Check if MIME type supported
18. BinaryTextExtractor.extract_text(data, mime, filename)  # Main extraction dispatcher
19. BinaryTextExtractor._extract_pdf(data, mime)      # PDF extraction (pypdf + pdfplumber)
20. BinaryTextExtractor._extract_pdf_pypdf(data)      # PDF via pypdf
21. BinaryTextExtractor._extract_pdf_pdfplumber(data) # PDF via pdfplumber
22. BinaryTextExtractor._extract_docx(data, mime)     # Word DOCX extraction
23. BinaryTextExtractor._extract_doc(data, mime)      # Old Word DOC (antiword)
24. BinaryTextExtractor._extract_xlsx(data, mime)     # Excel XLSX extraction
25. BinaryTextExtractor._extract_xls(data, mime)      # Old Excel XLS (xlrd)
26. BinaryTextExtractor._extract_pptx(data, mime)     # PowerPoint PPTX extraction
27. BinaryTextExtractor._extract_ppt(data, mime)      # Old PowerPoint PPT
28. BinaryTextExtractor._extract_zip_listing(data, mime)  # ZIP file listing
29. BinaryTextExtractor._extract_tar_listing(data, mime)  # TAR file listing
30. BinaryTextExtractor._extract_gzip_listing(data, mime) # GZIP file listing
31. extract_text_from_bytes(data, mime, filename)     # Standalone function
```

#### B. **enrichment/** - Entity Extraction & Content Enrichment

**File:** `/python-backend/modules/linklater/enrichment/cc_enricher.py`
```
32. CCEnricher.__init__(extract_entities, extract_outlinks, ...)
33. CCEnricher.enrich_single(url, title, snippet)     # Enrich single URL
34. CCEnricher.enrich_batch(items)                    # Batch enrichment
35. CCEnricher.enrich_search_results(results)         # Enrich search results
36. CCEnricher.get_priority_domains(country)          # Get priority domains by country
37. CCEnricher._extract_outlinks(content, base_url)   # Extract external links from HTML
38. CCEnricher._is_directory_url(url)                 # Check if URL is directory
39. CCEnricher._get_domain(url)                       # Extract domain from URL
40. CCEnricher._is_news_site(url)                     # Check if news site
41. CCEnricher._is_registry_site(url)                 # Check if registry site
42. CCEnricher._load_registries()                     # Load registry data
```

**File:** `/python-backend/modules/linklater/enrichment/entity_patterns.py`
```
43. EntityExtractor.__init__(jurisdictions)
44. EntityExtractor._compile_patterns()               # Compile regex patterns
45. EntityExtractor.extract_companies(text)           # Extract company names
46. EntityExtractor.extract_registrations(text)       # Extract registration numbers
47. EntityExtractor.extract_persons(text)             # Extract person names
48. EntityExtractor.extract_dates(text)               # Extract dates
49. EntityExtractor.extract_financials(text)          # Extract financial data
50. EntityExtractor.extract_all(text)                 # Extract all entity types
51. EntityExtractor.extract_with_custom_pattern(text, pattern, name)  # Custom regex
52. EntityExtractor.to_dict(entities)                 # Convert to dict
53. extract_companies(text, jurisdictions)            # Standalone function
54. extract_all_entities(text)                        # Standalone function
```

#### C. **discovery/** - Keyword Variations & Archive Search

**File:** `/python-backend/modules/linklater/discovery/keyword_variations.py`
```
55. KeywordVariationsSearch.__init__(firecrawl_key, max_concurrent)
56. KeywordVariationsSearch.generate_variations(keyword)  # Heuristic variations
57. KeywordVariationsSearch.generate_variations_llm(keyword)  # LLM-based variations
58. KeywordVariationsSearch.search_wayback(variation, domain, url)  # Wayback search
59. KeywordVariationsSearch.search_wayback_domain_url(variation, domain, url)  # Domain-specific
60. KeywordVariationsSearch.search_cc_index(variation, domain, url)  # CC index search
61. KeywordVariationsSearch.verify_snippet(url, variation)  # Verify keyword in snippet
62. KeywordVariationsSearch.search(keywords, domain, url, verify_snippets)  # Main search
63. KeywordVariationsSearch.to_search_results(variation_result, query)  # Convert to search format
```

#### D. **archives/** - Archive Scanning Strategies

**File:** `/python-backend/modules/linklater/archives/optimal_archive.py`
```
64. OptimalArchiveSearcher.__init__(keywords, domain, start_year, end_year, ...)
65. OptimalArchiveSearcher.search_keywords_streaming(domain, keywords, ...)  # Stream search
66. OptimalArchiveSearcher._fetch_years_parallel(domain, keywords, ...)  # Parallel year fetching
67. OptimalArchiveSearcher._fetch_year(year, domain, keywords, ...)  # Fetch single year
68. OptimalArchiveSearcher._fetch_wayback_year(year, domain, keywords)  # Wayback year search
69. OptimalArchiveSearcher._get_wayback_snapshots(domain, year)  # Get Wayback snapshots
70. OptimalArchiveSearcher._fetch_wayback_snapshot(snapshot, keyword)  # Fetch single snapshot
71. OptimalArchiveSearcher._fetch_commoncrawl_year(year, domain, keywords)  # CC year search
72. OptimalArchiveSearcher._get_commoncrawl_crawls(session)  # Get CC crawl list
73. OptimalArchiveSearcher._search_commoncrawl_index(session, crawl, domain)  # Search CC index
74. OptimalArchiveSearcher._fetch_commoncrawl_content(session, location, keyword)  # Fetch CC content
75. OptimalArchiveSearcher._extract_snippet(text, keyword, context_chars)  # Extract snippet
```

**File:** `/python-backend/modules/linklater/archives/hybrid_archive.py`
```
76. HybridArchiveSearcher methods (TBD - need to inventory)
```

**File:** `/python-backend/modules/linklater/archives/fast_scanner.py`
```
77-80. Fast scanner methods (TBD - need to inventory)
```

#### E. **CLI & Entry Points**

**File:** `/python-backend/modules/linklater/linklater.py`
```
81. LinkLaterCLI.__init__(args)
82. LinkLaterCLI.scrape_single(url)                   # CLI single URL scrape
83. LinkLaterCLI.scrape_batch(urls)                   # CLI batch scrape
84. LinkLaterCLI._format_result(result)               # Format result
85. LinkLaterCLI._print_stats()                       # Print statistics
86. LinkLaterCLI.output_results(results)              # Output results
87. LinkLaterCLI.run()                                # Main CLI execution
88. main()                                            # CLI entry point
```

---

### Section 2: MOVE INTO `/modules/linklater/` (External Python Files)

#### F. **MCP Server** → MOVE TO `/modules/linklater/mcp/server.py`

**Current location:** `/python-backend/mcp_servers/linklater_mcp.py`
```
89. find_globallinks_binary()                         # Find GlobalLinks Go binary
90. get_backlinks_from_cc_graph(domain, limit)        # CC Graph backlinks
91. get_backlinks_from_globallinks(domain, limit)     # GlobalLinks backlinks
92. get_outlinks_from_globallinks(domain, limit)      # GlobalLinks outlinks
93. list_tools()                                      # MCP list_tools handler
94. call_tool(name, arguments)                        # MCP call_tool handler
95. main()                                            # MCP server entry point
```

#### G. **FastAPI Routes** → MOVE TO `/modules/linklater/api/routes.py`

**Current location:** `/python-backend/api/linklater_routes.py`
```
96. search_keyword_variations(request)                # POST /linklater/keyword-variations
97. enrich_results(request)                           # POST /linklater/enrich
98. search_categories(request)                        # POST /linklater/search-categories
99. extract_cc_links(request)                         # POST /linklater/extract-cc-links
100. map_to_vertices(request)                         # POST /linklater/map-vertices
101. query_graph(request)                             # POST /linklater/query-graph
```

#### H. **Priority Scraper** → MOVE TO `/modules/linklater/brute/priority_scraper.py`

**Current location:** `/python-backend/modules/brute/linklater_priority_scraper.py`
```
102. scrape_bang_results_priority(query, bangs, ...)  # Priority scraping for bangs
103. normalize_priority_result_to_search_result(result, query)  # Result normalization
```

#### I. **Domain Spider Script** → MOVE TO `/modules/linklater/scripts/domain_spider.py`

**Current location:** `/scripts/linklater_domain_spider.py`
```
104. extract_outlinks(html, base_url, max_links)      # Extract outlinks from HTML
105. discover_cc_urls(domain, limit, collections)     # Discover URLs via CC
106. discover_wayback_urls(domain, limit)             # Discover URLs via Wayback
107. fetch_wayback_content(url)                       # Fetch Wayback content
108. process_domain(domain, args)                     # Process single domain
109. parse_domains(domains_file, inline)              # Parse domain list
110. main_async(args)                                 # Async main
111. main(argv)                                       # Script entry point
112. build_parser()                                   # Argparse builder
```

---

### Section 3: PORT FROM TypeScript (Create Python Implementations)

#### J. **TypeScript LinkLater Class** → PORT TO `/modules/linklater/graph/` and `/modules/linklater/discovery/`

**Current location:** `/server/services/linklater.ts` (TypeScript - 3870 lines)

**Archive & Scraping Methods:**
```
113. enrichBatch(items)                               # Batch enrichment with archive content
114. getBacklinks(domain, limit)                      # Get backlinks (CC Graph + GlobalLinks)
115. getOutlinks(domain, limit)                       # Get outlinks (CC Graph + GlobalLinks)
116. searchArchives(domain, keyword, startDate, endDate)  # Search archive snapshots
117. searchCCIndex(url, collections)                  # Search CC CDX index
118. searchByFiletype(domain, filetype, limit)        # Search by file type
119. getMimeTypesForDomain(domain)                    # Get MIME types for domain
120. findAllUrls(domain, limit)                       # Find all URLs for domain
121. searchUrlsForKeyword(domain, keyword)            # Search URLs for keyword
122. hopLinks(startDomain, hops, direction, maxPerHop)  # Link hopping (graph traversal)
123. scrapeLive(url, options)                         # Live Firecrawl scraping
124. scrapeBatch(urls, options)                       # Batch scraping
125. extractEntities(text)                            # Entity extraction
```

**Graph & Link Intelligence:**
```
126. searchBacklinkArchives(domains, linkType)        # Search archives of backlink domains
127. queryESForLinkingDomains(target, linkType)       # Elasticsearch link queries
128. identifyWATFilesFromDomains(domains)             # Identify WAT files
129. processWATFilesWithProgress(watFiles)            # Process WAT files
130. mapToVertices(domains)                           # Domain → vertex ID mapping
131. queryGraphNeighbors(startDomain, hops, direction, maxPerHop)  # Multi-hop graph traversal
```

**Domain Discovery:**
```
132. mapDomain(domain, options)                       # Map domain structure
133. crawlDomain(domain, options)                     # Crawl domain via Firecrawl
134. discoverSubdomainsCrtSh(domain)                  # crt.sh subdomain discovery
135. discoverSubdomainsWhoisXML(domain)               # WhoisXML subdomain discovery
136. discoverSubdomains(domain)                       # Combined subdomain discovery
137. parseSitemaps(domain)                            # Parse XML sitemaps
138. discoverViaGoogle(domain)                        # Google search engine discovery
139. discoverViaBrave(domain)                         # Brave search engine discovery
140. discoverViaBing(domain)                          # Bing search engine discovery
141. discoverViaSearchEngines(domain)                 # Combined search engine discovery
142. discoverAllUrls(domain)                          # All discovery methods combined
143. discoverBacklinks(options)                       # Backlink discovery
```

**Tier 1 Methods (Already in TypeScript, need Python ports):**
```
144. searchKeywordVariations(keywords, verifySnippets)  # Keyword variation search
145. enrichSearchResults(results, enrichWithBacklinks)  # CC enrichment
146. searchCategories(query, categories, maxPerCategory)  # Category-specific search
147. extractCCLinks(domain, collections, limit)       # Direct CC WAT link extraction
148. livePatternScan(pattern, domains, concurrent)    # Live pattern scanning
```

---

## 🎯 CONSOLIDATION PLAN

### Phase 1: Create Unified Python API

**Create:** `/modules/linklater/api.py` - **Main unified API entry point**

```python
"""
LinkLater Unified Python API

Single entry point for ALL LinkLater functionality.
All methods callable via: linklater.method_name()

Usage:
    from modules.linklater.api import linklater

    # Archive scraping
    result = await linklater.scrape_url("https://example.com/doc.pdf")

    # Entity extraction
    entities = linklater.extract_entities(text)

    # Backlinks
    backlinks = await linklater.get_backlinks("example.com")

    # Keyword variations
    results = await linklater.search_keyword_variations(["keyword"])
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from .scraping.cc_first_scraper import CCFirstScraper, scrape_url, scrape_urls
from .enrichment.cc_enricher import CCEnricher
from .enrichment.entity_patterns import EntityExtractor, extract_companies, extract_all_entities
from .discovery.keyword_variations import KeywordVariationsSearch
from .archives.optimal_archive import OptimalArchiveSearcher
from .scraping.binary_extractor import BinaryTextExtractor, extract_text_from_bytes
from .scraping.warc_parser import WARCParser, html_to_markdown


class LinkLater:
    """
    Unified LinkLater API

    All 148+ methods accessible via single instance.
    """

    def __init__(self):
        # Initialize all sub-modules
        self.scraper = CCFirstScraper(extract_binary=True)
        self.enricher = CCEnricher(extract_entities=True, extract_outlinks=True)
        self.entity_extractor = EntityExtractor()
        self.keyword_search = KeywordVariationsSearch()
        self.archive_search = OptimalArchiveSearcher()
        self.binary_extractor = BinaryTextExtractor()
        self.warc_parser = WARCParser()

    # ========================================
    # SECTION 1: ARCHIVE SCRAPING (Methods 1-31)
    # ========================================

    async def scrape_url(self, url: str, **kwargs):
        """1-6. Scrape single URL with 3-tier fallback (CC → Wayback → Firecrawl)."""
        return await self.scraper.get_content(url)

    async def scrape_batch(self, urls: List[str], **kwargs):
        """7. Batch scrape multiple URLs."""
        return await self.scraper.batch_scrape(urls, **kwargs)

    async def check_cc_index(self, url: str):
        """2. Check if URL exists in CC index."""
        return await self.scraper.check_cc_index(url)

    async def fetch_from_wayback(self, url: str):
        """4. Fetch content from Wayback Machine."""
        return await self.scraper.fetch_from_wayback(url)

    async def fetch_from_firecrawl(self, url: str):
        """5. Fetch content from Firecrawl (live scraping)."""
        return await self.scraper.fetch_from_firecrawl(url)

    def get_scraper_stats(self):
        """8. Get scraping statistics."""
        return self.scraper.get_stats()

    def extract_html_from_warc(self, warc_data: bytes):
        """12. Extract HTML from WARC data."""
        return self.warc_parser.extract_html(warc_data)

    def extract_binary_from_warc(self, warc_data: bytes):
        """14. Extract binary from WARC data."""
        return self.warc_parser.extract_binary(warc_data)

    def html_to_markdown(self, html: str):
        """15. Convert HTML to Markdown."""
        return html_to_markdown(html)

    def can_extract_binary(self, mime_type: str):
        """17. Check if MIME type is supported for binary extraction."""
        return self.binary_extractor.can_extract(mime_type)

    def extract_text_from_binary(self, data: bytes, mime_type: str, filename: str = ""):
        """18-30. Extract text from binary files (PDF, DOCX, XLSX, PPTX, etc)."""
        return self.binary_extractor.extract_text(data, mime_type, filename)

    # ========================================
    # SECTION 2: ENTITY EXTRACTION (Methods 32-54)
    # ========================================

    def extract_entities(self, text: str) -> Dict[str, List]:
        """50. Extract all entity types from text."""
        return self.entity_extractor.extract_all(text)

    def extract_companies(self, text: str):
        """45. Extract company names."""
        return self.entity_extractor.extract_companies(text)

    def extract_persons(self, text: str):
        """47. Extract person names."""
        return self.entity_extractor.extract_persons(text)

    def extract_registrations(self, text: str):
        """46. Extract registration numbers."""
        return self.entity_extractor.extract_registrations(text)

    def extract_dates(self, text: str):
        """48. Extract dates."""
        return self.entity_extractor.extract_dates(text)

    def extract_financials(self, text: str):
        """49. Extract financial data."""
        return self.entity_extractor.extract_financials(text)

    # ========================================
    # SECTION 3: ENRICHMENT (Methods 32-42)
    # ========================================

    async def enrich_url(self, url: str, title: str = "", snippet: str = ""):
        """33. Enrich single URL with entities and outlinks."""
        return await self.enricher.enrich_single(url, title, snippet)

    async def enrich_batch(self, items: List[Dict]):
        """34. Batch enrich URLs."""
        return await self.enricher.enrich_batch(items)

    async def enrich_search_results(self, results: List[Dict]):
        """35. Enrich search results."""
        return await self.enricher.enrich_search_results(results)

    def extract_outlinks(self, html: str, base_url: str):
        """37. Extract outlinks from HTML."""
        return self.enricher._extract_outlinks(html, base_url)

    def get_priority_domains(self, country: Optional[str] = None):
        """36. Get priority domains by country."""
        return self.enricher.get_priority_domains(country)

    # ========================================
    # SECTION 4: KEYWORD VARIATIONS (Methods 55-63)
    # ========================================

    async def search_keyword_variations(self, keywords: List[str], **kwargs):
        """62. Search with keyword variations."""
        return await self.keyword_search.search(keywords, **kwargs)

    def generate_variations(self, keyword: str):
        """56. Generate keyword variations (heuristic)."""
        return self.keyword_search.generate_variations(keyword)

    async def generate_variations_llm(self, keyword: str):
        """57. Generate keyword variations (LLM)."""
        return await self.keyword_search.generate_variations_llm(keyword)

    async def search_wayback(self, variation: str, domain: str = None, url: str = None):
        """58. Search Wayback for keyword variation."""
        return await self.keyword_search.search_wayback(variation, domain, url)

    async def search_cc_index(self, variation: str, domain: str = None, url: str = None):
        """60. Search CC index for keyword variation."""
        return await self.keyword_search.search_cc_index(variation, domain, url)

    # ========================================
    # SECTION 5: ARCHIVE SEARCH (Methods 64-75)
    # ========================================

    async def search_archives(self, domain: str, keyword: str, **kwargs):
        """65. Search archive snapshots for keyword."""
        async for result in self.archive_search.search_keywords_streaming(
            domain=domain,
            keywords=[keyword],
            **kwargs
        ):
            yield result

    # ========================================
    # SECTION 6: BACKLINKS & OUTLINKS (Methods 89-92, 113-115)
    # TODO: Implement after moving MCP server code
    # ========================================

    async def get_backlinks(self, domain: str, limit: int = 100):
        """90, 114. Get backlinks (domains linking TO this domain)."""
        # TODO: Integrate from mcp/server.py
        raise NotImplementedError("Will be implemented in Phase 2")

    async def get_outlinks(self, domain: str, limit: int = 100):
        """92, 115. Get outlinks (domains this domain links TO)."""
        # TODO: Integrate from mcp/server.py
        raise NotImplementedError("Will be implemented in Phase 2")

    # ========================================
    # SECTION 7: GRAPH TRAVERSAL (Methods 122, 127-131)
    # TODO: Port from TypeScript
    # ========================================

    async def hop_links(self, start_domain: str, hops: int = 2, **kwargs):
        """122. Navigate through link graph (multi-hop traversal)."""
        # TODO: Port from TypeScript linklater.ts
        raise NotImplementedError("Will be ported from TypeScript in Phase 3")

    async def query_graph_neighbors(self, start_domain: str, hops: int, **kwargs):
        """131. Multi-hop graph traversal."""
        # TODO: Port from TypeScript linklater.ts
        raise NotImplementedError("Will be ported from TypeScript in Phase 3")

    # ========================================
    # SECTION 8: DOMAIN DISCOVERY (Methods 132-143)
    # TODO: Port from TypeScript
    # ========================================

    async def discover_subdomains(self, domain: str):
        """136. Discover subdomains via crt.sh, WhoisXML, etc."""
        # TODO: Port from TypeScript linklater.ts
        raise NotImplementedError("Will be ported from TypeScript in Phase 3")

    async def discover_urls(self, domain: str):
        """142. Discover all URLs via sitemaps, search engines, etc."""
        # TODO: Port from TypeScript linklater.ts
        raise NotImplementedError("Will be ported from TypeScript in Phase 3")

    async def map_domain(self, domain: str):
        """132. Map complete domain structure."""
        # TODO: Port from TypeScript linklater.ts
        raise NotImplementedError("Will be ported from TypeScript in Phase 3")

    # ========================================
    # (50+ more methods to add in phases 2-3)
    # ========================================


# Singleton instance for easy import
linklater = LinkLater()
```

---

### Phase 2: Move External Python Files

#### Step 1: Move MCP Server
```bash
mkdir -p /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/mcp
cp /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/mcp_servers/linklater_mcp.py \
   /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/mcp/server.py
```

Update `mcp/server.py` to use unified API:
```python
from ..api import linklater  # Use unified API
```

#### Step 2: Move API Routes
```bash
mkdir -p /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/api
cp /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/api/linklater_routes.py \
   /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/api/routes.py
```

Update `api/routes.py` to use unified API:
```python
from ..api import linklater  # Use unified API
```

#### Step 3: Move Priority Scraper
```bash
mkdir -p /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/brute
cp /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/brute/linklater_priority_scraper.py \
   /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/brute/priority_scraper.py
```

#### Step 4: Move Domain Spider
```bash
mkdir -p /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/scripts
cp /Users/attic/DRILL_SEARCH/drill-search-app/scripts/linklater_domain_spider.py \
   /Users/attic/DRILL_SEARCH/drill-search-app/python-backend/modules/linklater/scripts/domain_spider.py
```

---

### Phase 3: Port TypeScript Methods to Python

**Create new modules:**

1. `/modules/linklater/graph/cc_graph.py` - CC Graph queries (methods 114-115, 127-131)
2. `/modules/linklater/graph/traversal.py` - Graph traversal (methods 122, 131)
3. `/modules/linklater/discovery/domain_discovery.py` - Domain/subdomain discovery (methods 132-143)
4. `/modules/linklater/scraping/live_scraper.py` - Live Firecrawl scraping (methods 123-124)

---

## 📁 Final Structure

```
/modules/linklater/
├── api.py                          # 🆕 UNIFIED API - Main entry point (148+ methods)
├── linklater.py                    # CLI interface (methods 81-88)
├── scraping/
│   ├── cc_first_scraper.py         # Methods 1-11
│   ├── warc_parser.py              # Methods 12-15
│   ├── binary_extractor.py         # Methods 16-31
│   └── live_scraper.py             # 🆕 Methods 123-124 (from TypeScript)
├── enrichment/
│   ├── cc_enricher.py              # Methods 32-42
│   └── entity_patterns.py          # Methods 43-54
├── discovery/
│   ├── keyword_variations.py       # Methods 55-63
│   └── domain_discovery.py         # 🆕 Methods 132-143 (from TypeScript)
├── archives/
│   ├── optimal_archive.py          # Methods 64-75
│   ├── hybrid_archive.py           # Methods 76
│   └── fast_scanner.py             # Methods 77-80
├── graph/                          # 🆕 Graph operations
│   ├── cc_graph.py                 # 🆕 Methods 114-115, 127-130 (from TypeScript)
│   └── traversal.py                # 🆕 Methods 122, 131 (from TypeScript)
├── mcp/                            # 🆕 MCP server (moved)
│   └── server.py                   # Methods 89-95 (from /mcp_servers/)
├── api/                            # 🆕 FastAPI routes (moved)
│   └── routes.py                   # Methods 96-101 (from /api/)
├── brute/                          # 🆕 Brute search integration (moved)
│   └── priority_scraper.py         # Methods 102-103 (from /modules/brute/)
├── scripts/                        # 🆕 Utility scripts (moved)
│   └── domain_spider.py            # Methods 104-112 (from /scripts/)
└── pipelines/                      # Automated pipelines (already exist)
    ├── extract_domain_pdfs.sh
    ├── extract_domain_docs.sh
    └── full_entity_extraction.sh
```

---

## ✅ Usage After Consolidation

### Python (Simple - Main Goal)
```python
from modules.linklater.api import linklater

# Archive scraping
result = await linklater.scrape_url("https://example.com/doc.pdf")

# Entity extraction
entities = linklater.extract_entities(text)

# Backlinks (after Phase 2)
backlinks = await linklater.get_backlinks("example.com")

# Keyword variations
async for match in linklater.search_keyword_variations(["portofino"]):
    print(match)

# Domain discovery (after Phase 3)
subdomains = await linklater.discover_subdomains("example.com")
```

### CLI (Unchanged)
```bash
python modules/linklater/linklater.py --url "https://example.com" --extract-entities
```

### MCP Server (Updated path)
```bash
python modules/linklater/mcp/server.py
```

### FastAPI (Updated imports only)
```python
from modules.linklater.api.routes import router
app.include_router(router)
```

---

## 🎯 Migration Checklist

### Phase 1: Unified API
- [ ] Create `/modules/linklater/api.py` with methods 1-80 integrated
- [ ] Add placeholder methods for 89-148 (NotImplementedError)
- [ ] Test all currently implemented methods work

### Phase 2: Move External Python Files
- [ ] Move MCP server → `/modules/linklater/mcp/server.py`
- [ ] Move API routes → `/modules/linklater/api/routes.py`
- [ ] Move priority scraper → `/modules/linklater/brute/priority_scraper.py`
- [ ] Move domain spider → `/modules/linklater/scripts/domain_spider.py`
- [ ] Integrate methods 89-112 into `api.py`
- [ ] Update MCP server config path
- [ ] Update FastAPI main.py imports

### Phase 3: Port TypeScript Methods
- [ ] Create `/modules/linklater/graph/cc_graph.py`
- [ ] Create `/modules/linklater/graph/traversal.py`
- [ ] Create `/modules/linklater/discovery/domain_discovery.py`
- [ ] Create `/modules/linklater/scraping/live_scraper.py`
- [ ] Port methods 113-148 from TypeScript
- [ ] Integrate into `api.py`
- [ ] Update TypeScript to call Python for these methods (if needed)

### Phase 4: Testing & Documentation
- [ ] Test all 148+ methods via `linklater.method_name()`
- [ ] Update MASTER_README.md with unified API docs
- [ ] Update all import paths in codebase
- [ ] Update MCP server docs
- [ ] Delete old file locations (after confirming working)

---

## 📊 Final Count

**Total Methods: 148+**
- Currently in `/modules/linklater/`: 80 methods
- External Python (to move): 28 methods
- TypeScript (to port): 40+ methods

**All callable via:**
```python
from modules.linklater.api import linklater
result = await linklater.method_name()
```

**Status:** READY TO IMPLEMENT
