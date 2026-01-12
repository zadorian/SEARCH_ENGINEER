# Common Crawl PDF & File Type Filtering Integration Plan

**Date:** 2025-12-02
**Purpose:** Integrate CC file type filtering to efficiently discover PDFs (esp. annual reports) without downloading full CC dataset
**Target:** Swedish bank annual reports & financial documents

---

## I. Current Architecture Analysis

### Existing Components

**1. CC Index Client** (`archives/cc_index_client.py`)
- ✅ Already queries CC Index API
- ✅ Supports MIME type filtering: `filter_mime=["application/pdf"]`
- ✅ Domain/URL pattern matching
- ✅ Streaming for large result sets
- ⚠️ Limited to index metadata (doesn't download content)

**2. CC-First Scraper** (`scraping/cc_first_scraper.py`)
- ✅ Fetches WARC/WAT files with byte-range requests
- ✅ Parallel racing (CC + Wayback)
- ✅ Entity extraction integration
- ⚠️ Designed for HTML, not PDFs

**3. Binary Extractor** (`scraping/binary_extractor.py`)
- ✅ PDF text extraction (PyMuPDF)
- ✅ Office docs (DOCX, XLSX, PPTX)
- ⚠️ Processes already-downloaded files

**4. Drill Pipeline** (`drill/linkpipeline.py`)
- ✅ Orchestrates discovery → scrape → index
- ✅ Queue-based parallel processing
- ⚠️ No file type awareness yet

---

## II. Integration Options

### Option A: **Index-First Query Filter** (RECOMMENDED)
**Approach:** Query CC Index API with MIME filters, discover PDF URLs, fetch metadata only

**Workflow:**
```
Query CC Index → Filter PDFs → Extract metadata → Score relevance → Fetch top candidates
```

**Implementation:**
```python
# New: linklater/discovery/cc_pdf_discovery.py

class CCPDFDiscovery:
    """Discover PDFs in Common Crawl by file type."""

    async def find_pdfs_by_domain(
        self,
        domain: str,
        keywords: List[str] = ["annual report", "årsredovisning"],
        archives: List[str] = ["CC-MAIN-2024-*"],
        min_size_kb: int = 100,  # Skip tiny PDFs
        max_size_mb: int = 50    # Skip huge PDFs
    ) -> List[PDFCandidate]:
        """
        Find PDF candidates without downloading full files.

        Process:
        1. Query CC Index with mime filter: application/pdf
        2. Filter by URL patterns (annual-report, ar2024, etc.)
        3. Filter by file size (avoid tiny/huge)
        4. Return ranked candidates
        """

    async def find_annual_reports(
        self,
        companies: List[str],  # ["SEB", "Swedbank", ...]
        years: List[int] = [2023, 2024]
    ) -> List[AnnualReport]:
        """
        Specialized annual report discovery.

        URL patterns:
        - /annual-report-2024.pdf
        - /ar2024.pdf
        - /investor-relations/reports/
        - /arsredovisning-2024.pdf (Swedish)
        """
```

**Advantages:**
- ✅ Zero CC data download needed
- ✅ Fast (index queries: ~100-500ms)
- ✅ Precise targeting via MIME + URL patterns
- ✅ Scalable (query millions of records)

**Disadvantages:**
- ⚠️ Depends on accurate CC MIME classification
- ⚠️ URL-based filtering may miss some reports

**Estimated Performance:**
- 1M domain records → 10-50K PDFs → 100-500 candidates
- Query time: 2-10 seconds
- Zero bandwidth cost

---

### Option B: **WAT File Streaming Filter**
**Approach:** Stream WAT files (metadata archives) and filter by file type headers

**Workflow:**
```
Query CC Index → Get WAT locations → Stream WAT → Filter PDFs → Extract metadata
```

**Implementation:**
```python
# Enhancement: scraping/warc_parser.py

class WATStreamFilter:
    """Stream WAT files and filter by content type."""

    async def stream_wat_for_pdfs(
        self,
        wat_url: str,
        filters: WATFilters
    ) -> AsyncIterator[PDFRecord]:
        """
        Stream WAT file and yield PDF records.

        WAT structure (JSON):
        {
          "Envelope": {
            "WARC-Header-Metadata": {
              "WARC-Type": "response",
              "Content-Type": "application/pdf"
            },
            "Payload-Metadata": {
              "HTTP-Response-Metadata": {
                "Headers": {
                  "Content-Type": "application/pdf",
                  "Content-Length": "2048576"
                }
              }
            }
          }
        }
        """
```

**Advantages:**
- ✅ More comprehensive than index (includes HTTP headers)
- ✅ Can extract title/metadata from PDF headers
- ✅ Still avoids downloading full PDFs

**Disadvantages:**
- ⚠️ Requires downloading WAT files (~500MB-2GB each)
- ⚠️ Slower than index queries
- ⚠️ More bandwidth usage

**Estimated Performance:**
- 1 WAT file: 500MB-2GB
- Processing time: 30-60 seconds per WAT
- Typical domain: 5-20 WAT files

---

### Option C: **Hybrid: Index Query + Selective WAT Verification**
**Approach:** Use index for initial discovery, verify promising candidates with WAT metadata

**Workflow:**
```
Index query → Top 1000 candidates → WAT metadata fetch → Re-rank → Download top 50
```

**Implementation:**
```python
# New: linklater/discovery/cc_hybrid_discovery.py

class CCHybridDiscovery:
    """Hybrid index + WAT verification."""

    async def discover_pdfs_verified(
        self,
        domain: str,
        keywords: List[str],
        verify_top_n: int = 100
    ) -> List[VerifiedPDFCandidate]:
        """
        1. Query index: Get 1000 PDF candidates
        2. Rank by URL patterns
        3. Fetch WAT metadata for top 100
        4. Verify file size, content-type headers
        5. Return verified top candidates
        """
```

**Advantages:**
- ✅ Best precision (verification step)
- ✅ Reasonable bandwidth (selective WAT fetches)
- ✅ Can extract PDF title/author from metadata

**Disadvantages:**
- ⚠️ More complex
- ⚠️ Slower than index-only

**Estimated Performance:**
- Initial query: 2-5 seconds
- WAT verification (100 URLs): 10-30 seconds
- Total: 15-35 seconds

---

## III. Annual Report Specialization

### URL Pattern Recognition

```python
ANNUAL_REPORT_PATTERNS = {
    'english': [
        r'/annual[_-]?report[_-]?\d{4}\.pdf',
        r'/ar\d{4}\.pdf',
        r'/investor[_-]?relations/.*report.*\.pdf',
        r'/financial[_-]?statements[_-]?\d{4}\.pdf',
    ],
    'swedish': [
        r'/årsredovisning[_-]?\d{4}\.pdf',
        r'/arsredovisning[_-]?\d{4}\.pdf',
        r'/bokslutskommunike[_-]?\d{4}\.pdf',
    ],
    'generic': [
        r'/\d{4}[_-]?annual\.pdf',
        r'/reports/\d{4}/.*\.pdf',
    ]
}

# Domain-specific paths
BANK_IR_PATHS = [
    '/investor-relations/',
    '/investerare/',
    '/offentliggoranden/',  # Swedish: disclosures
    '/finansiell-information/',
]
```

### Swedish Bank Targets

```python
SWEDISH_BANKS = {
    'SEB': {
        'domains': ['sebgroup.com', 'seb.se'],
        'ir_paths': ['/investor-relations/', '/investerare/'],
    },
    'Swedbank': {
        'domains': ['swedbank.com', 'swedbank.se'],
        'ir_paths': ['/investor-relations/', '/investerare/'],
    },
    'Handelsbanken': {
        'domains': ['handelsbanken.com', 'handelsbanken.se'],
        'ir_paths': ['/ir/', '/investor-relations/'],
    },
    'Nordea': {
        'domains': ['nordea.com'],
        'ir_paths': ['/investor-relations/'],
    },
}
```

---

## IV. Implementation Phases

### Phase 1: Core PDF Discovery (Week 1)
**File:** `linklater/discovery/cc_pdf_discovery.py`

```python
class CCPDFDiscovery:
    def __init__(self, cc_index_client: CCIndexClient):
        self.index = cc_index_client

    async def find_pdfs(
        self,
        domain: str,
        archive: str = "CC-MAIN-2024-10",
        url_patterns: Optional[List[str]] = None,
        min_size: int = 102400,  # 100KB
        max_size: int = 52428800  # 50MB
    ):
        # Query with MIME filter
        records = await self.index.query_domain(
            domain=domain,
            archive=archive,
            filter_mime=["application/pdf"],
            limit=10000
        )

        # Filter by size
        candidates = [
            r for r in records
            if min_size <= r.length <= max_size
        ]

        # Filter by URL patterns
        if url_patterns:
            candidates = filter_by_patterns(candidates, url_patterns)

        return candidates
```

**Testing:**
```python
# Test on SEB
discovery = CCPDFDiscovery(CCIndexClient())
pdfs = await discovery.find_pdfs(
    domain="sebgroup.com",
    url_patterns=ANNUAL_REPORT_PATTERNS['english'],
    archive="CC-MAIN-2024-22"  # Latest
)

print(f"Found {len(pdfs)} annual report candidates")
```

---

### Phase 2: Annual Report Specialization (Week 1-2)
**File:** `linklater/discovery/annual_report_hunter.py`

```python
class AnnualReportHunter:
    """Specialized annual report discovery."""

    async def find_bank_annual_reports(
        self,
        banks: List[str] = list(SWEDISH_BANKS.keys()),
        years: List[int] = [2023, 2024],
        archives: Optional[List[str]] = None
    ) -> Dict[str, List[AnnualReport]]:
        """
        Comprehensive bank annual report discovery.

        Returns:
        {
          'SEB': [
            AnnualReport(
              url='https://sebgroup.com/ir/annual-report-2024.pdf',
              year=2024,
              archive='CC-MAIN-2024-22',
              size_mb=5.2,
              timestamp='20240315...',
              confidence=0.95
            )
          ],
          ...
        }
        """
```

---

### Phase 3: Integration with Drill Pipeline (Week 2)
**File:** `linklater/drill/linkpipeline.py` (enhancement)

```python
class LinkPipeline:
    # Add new stage
    async def pdf_discovery_stage(
        self,
        domains: List[str],
        pdf_filters: PDFFilters
    ):
        """
        PDF discovery stage in pipeline.

        Workflow:
        1. Query CC Index for PDFs
        2. Filter by patterns
        3. Queue for download
        4. Extract text
        5. Index content
        """
```

---

### Phase 4: PDF Processing & Indexing (Week 2-3)
**File:** `linklater/scraping/pdf_processor.py`

```python
class PDFProcessor:
    """Download and process PDF candidates."""

    async def fetch_and_extract(
        self,
        pdf_record: CCIndexRecord
    ) -> ProcessedPDF:
        """
        1. Fetch PDF from CC WARC (byte-range request)
        2. Extract text (PyMuPDF)
        3. Extract metadata (title, author, date)
        4. Extract entities (companies, dates, numbers)
        5. Return processed result
        """

    async def batch_process(
        self,
        candidates: List[CCIndexRecord],
        max_concurrent: int = 10
    ) -> List[ProcessedPDF]:
        """Parallel PDF processing."""
```

---

## V. Efficiency Optimizations

### 1. **Query Pagination**
```python
# Stream large result sets without memory explosion
async for record in cc_client.stream_query_results(
    url="*.sebgroup.com/*",
    archive="CC-MAIN-2024-22",
    match_type="domain"
):
    if is_pdf(record) and matches_pattern(record.url):
        yield record
```

### 2. **Archive Selection**
```python
# Query multiple archives efficiently
async def query_multiple_archives(
    domain: str,
    archives: List[str]  # ["CC-MAIN-2024-22", "CC-MAIN-2024-18", ...]
) -> Dict[str, List[CCIndexRecord]]:
    """Parallel queries across archives."""
    tasks = [
        query_archive(domain, archive)
        for archive in archives
    ]
    results = await asyncio.gather(*tasks)
    return dict(zip(archives, results))
```

### 3. **Deduplication**
```python
# Many PDFs appear in multiple archives
def deduplicate_by_digest(
    records: List[CCIndexRecord]
) -> List[CCIndexRecord]:
    """Keep only latest version of each PDF by digest."""
    seen = {}
    for record in sorted(records, key=lambda r: r.timestamp, reverse=True):
        if record.digest not in seen:
            seen[record.digest] = record
    return list(seen.values())
```

### 4. **Smart Ranking**
```python
def rank_annual_report_candidates(
    records: List[CCIndexRecord]
) -> List[ScoredCandidate]:
    """
    Score candidates by:
    - URL pattern match strength (40%)
    - File size appropriateness (20%)
    - Recency (20%)
    - Domain authority (20%)
    """
    scores = []
    for record in records:
        score = (
            pattern_score(record.url) * 0.4 +
            size_score(record.length) * 0.2 +
            recency_score(record.timestamp) * 0.2 +
            domain_score(record.url) * 0.2
        )
        scores.append((score, record))

    return sorted(scores, key=lambda x: x[0], reverse=True)
```

---

## VI. Cost & Performance Analysis

### Option A: Index-First (Recommended)

**Bandwidth:**
- Index queries: ~50KB per query
- 100 queries: ~5MB total
- PDF downloads (top 50): ~250MB
- **Total: ~255MB**

**Time:**
- Index queries: 2-10 seconds
- Ranking: 1-2 seconds
- PDF downloads: 30-60 seconds
- **Total: ~45-75 seconds**

**Coverage:**
- Expected recall: 85-90% of available reports
- Precision: 70-80% (some false positives)

---

### Option B: WAT Streaming

**Bandwidth:**
- WAT files for domain: ~2-10GB
- PDF downloads (top 50): ~250MB
- **Total: ~2.25-10.25GB**

**Time:**
- WAT downloads: 1-5 minutes
- WAT parsing: 30-120 seconds
- PDF downloads: 30-60 seconds
- **Total: ~2-7 minutes**

**Coverage:**
- Expected recall: 95%+ (more comprehensive)
- Precision: 80-85% (better verification)

---

### Option C: Hybrid

**Bandwidth:**
- Index queries: ~5MB
- Selective WAT fetches (100 URLs): ~50-200MB
- PDF downloads (top 50): ~250MB
- **Total: ~305-455MB**

**Time:**
- Index queries: 2-10 seconds
- WAT verification: 10-30 seconds
- PDF downloads: 30-60 seconds
- **Total: ~45-100 seconds**

**Coverage:**
- Expected recall: 90-95%
- Precision: 85-90% (best)

---

## VII. Recommended Approach

### **Phase 1: Start with Option A (Index-First)**

**Rationale:**
- Fastest time to value
- Minimal bandwidth
- Easy to implement
- Good enough for most use cases

**Implementation:**
```python
# 1. Add CC PDF Discovery module
# linklater/discovery/cc_pdf_discovery.py

# 2. Integrate into existing discovery pipeline
# linklater/discovery/unified_discovery.py

# 3. Add PDF processing to scraping chain
# linklater/scraping/pdf_processor.py

# 4. Index PDFs with drill pipeline
# linklater/drill/linkpipeline.py
```

### **Phase 2: Add Option C (Hybrid) for critical targets**

**Use hybrid for:**
- High-value targets (major banks)
- Historical compliance (need complete archives)
- Verification (before relying on data)

---

## VIII. Sample Usage

```python
from linklater.discovery import CCPDFDiscovery, AnnualReportHunter

# Simple: Find all PDFs for domain
discovery = CCPDFDiscovery()
pdfs = await discovery.find_pdfs(
    domain="sebgroup.com",
    archive="CC-MAIN-2024-22"
)

# Specialized: Find annual reports
hunter = AnnualReportHunter()
reports = await hunter.find_bank_annual_reports(
    banks=["SEB", "Swedbank"],
    years=[2023, 2024]
)

# Results:
{
  'SEB': [
    AnnualReport(
      url='https://sebgroup.com/siteassets/ir/annual-reports/2024/seb-annual-report-2024.pdf',
      year=2024,
      size_mb=12.3,
      confidence=0.96
    )
  ],
  'Swedbank': [...]
}

# Process top candidates
processor = PDFProcessor()
processed = await processor.batch_process(
    candidates=reports['SEB'][:10]
)

# Index content
for pdf in processed:
    await drill_indexer.index_document(pdf)
```

---

## IX. Next Steps

1. **Implement `cc_pdf_discovery.py`** (Option A core)
2. **Test on Swedish banks** (SEB, Swedbank, Handelsbanken)
3. **Integrate with drill pipeline**
4. **Add annual report patterns**
5. **Benchmark performance**
6. **(Optional) Add hybrid verification for critical targets**

---

## X. Success Metrics

**Coverage:**
- ✅ Find 90%+ of available annual reports
- ✅ Cover 2020-2024 (5 years)

**Speed:**
- ✅ Initial discovery: <2 minutes
- ✅ Full processing: <10 minutes per bank

**Precision:**
- ✅ 80%+ of candidates are actual annual reports
- ✅ <5% duplicate detections

**Bandwidth:**
- ✅ <500MB per bank discovery
- ✅ Scalable to 100+ banks

---

**Status:** Ready for implementation
**Recommended:** Start with Option A, expand to Option C as needed
