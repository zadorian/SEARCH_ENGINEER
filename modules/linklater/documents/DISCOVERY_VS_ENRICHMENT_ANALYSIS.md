# LinkLater: Discovery vs Enrichment Analysis

## Current State

### ENRICHMENT (Target Domain Known) ✅ COMPLETE

**Location:** `/modules/linklater/`

**Parallel Coverage:**

| Source | Parallel? | Speed | Cost | Purpose |
|--------|-----------|-------|------|---------|
| CC Graph | ✅ Yes | Very Fast | Free | Domain-level backlinks |
| GlobalLinks | ✅ Yes | Fast | Free | Page-level backlinks |
| Majestic Fresh | ✅ Yes | Fast | Paid | Recent quality backlinks |
| Majestic Historic | ✅ Yes | Fast | Paid | Historical backlinks |
| CC Archive | ❌ Sequential | Slow | Free | Deep WARC scanning |
| Wayback | ❌ Sequential | Medium | Free | Fallback archiving |

**Parallel Execution:** Phases 1 & 2 run in parallel (4 sources simultaneously)

**Usage:**
```python
from modules.linklater.api import linklater

# Known target: sebgroup.com
backlinks = await linklater.get_backlinks("sebgroup.com", limit=1000)
```

**Status:** ✅ COMPLETE in LinkLater

---

### DISCOVERY (No Target - Finding Domains) ✅ INTEGRATED

**Location:** `/modules/linklater/discovery/domain_filters.py` (IMPORTS FROM CATEGORIZER-FILTERER)

**Available CLI Tools:**

#### 1. Common Crawl Web Graph CLI ❌ NOT IN LINKLATER
**File:** `/modules/alldom/cc_inbound_domains_cli.py`

**Capabilities:**
- Fetch inbound domain-to-domain backlinks from CC Web Graph
- Filter by year/period
- Returns: target_domain, src_domain, weight, centrality, pagerank
- **Output:** CSV with domain relationships

**Discovery Use Case:**
```bash
python cc_inbound_domains_cli.py --target "*.ly" --year 2024
# → Discovers all domains linking to Libyan .ly domains
```

**Status:** ✅ Integrated into LinkLater discovery API

---

#### 2. Subdomain Discovery ⚠️ AVAILABLE BUT NOT YET IN LINKLATER
**File:** `/modules/alldom/sources/subdomain_discovery.py`

**Capabilities:**
- Multi-source subdomain enumeration (crt.sh, WhoisXML, Sublist3r)
- Runs in parallel (3 sources simultaneously)
- Free + Paid sources

**Discovery Use Case:**
```python
from alldom.sources.subdomain_discovery import SubdomainDiscovery

sd = SubdomainDiscovery()
async for subdomain in sd.discover_all("example.com"):
    # → Discovers: sub1.example.com, sub2.example.com, ...
```

**Status:** ❌ In alldom module, NOT integrated into LinkLater

---

#### 3. Multi-Source Discovery ❌ NOT IN LINKLATER
**File:** `/modules/alldom/legend/resources/multisource_discovery.py`

**Capabilities:**
- Aggregates multiple domain discovery sources
- Static domain resources

**Status:** ❌ In alldom module, NOT integrated into LinkLater

---

## Missing Integrations

### 1. BigQuery Domain Search ❌ NOT INTEGRATED

**What it would do:**
- Query BigQuery public datasets (CC index, domain databases)
- Filter domains by TLD, keyword, pagerank, etc.
- Discovery at scale (millions of domains)

**Example Usage (NOT IMPLEMENTED):**
```python
# Find all .ly domains with "bank" or "finance" keywords
domains = await linklater.discover_domains(
    tlds=[".ly"],
    keywords=["bank", "finance", "investment"],
    source="bigquery"
)
```

**Status:** ❌ NOT IMPLEMENTED

---

### 2. Majestic Domain Filtering ❌ NOT INTEGRATED

**What it would do:**
- Use Majestic API to discover domains by:
  - TopicalTrustFlow category
  - TrustFlow threshold
  - CitationFlow threshold
  - Referring domains count

**Example Usage (NOT IMPLEMENTED):**
```python
# Find high-authority finance domains linking to .ly TLDs
domains = await linklater.discover_domains(
    category="Finance",
    min_trust_flow=40,
    linking_to_tld=".ly",
    source="majestic"
)
```

**Status:** ❌ NOT IMPLEMENTED

---

### 3. Common Crawl Index Search ❌ PARTIALLY INTEGRATED

**Current:** `cc_index_cli.py` exists in alldom (NOT in LinkLater)

**What it does:**
- Query CC Index API for URL patterns
- Filter by status code, MIME type, etc.

**Example Usage (NOT FULLY INTEGRATED):**
```python
# Find all pages matching URL pattern
urls = await linklater.discover_urls(
    pattern="*.ly/*/about",
    archive="CC-MAIN-2025-47",
    source="cc_index"
)
```

**Status:** ⚠️ CLI exists in alldom, NOT in LinkLater API

---

## Proposed Integration

### Phase 1: Consolidate Existing Discovery Tools

**Move to LinkLater:**

1. **CC Inbound Domains CLI** → `/modules/linklater/discovery/cc_graph_discovery.py`
   ```python
   from modules.linklater.api import linklater
   
   # Discover domains linking to target TLD
   inbound = await linklater.discover_inbound_domains(
       tld=".ly",
       min_weight=10,
       archive="CC-MAIN-2025-47"
   )
   ```

2. **Subdomain Discovery** → `/modules/linklater/discovery/subdomain_discovery.py`
   ```python
   from modules.linklater.api import linklater
   
   # Discover subdomains
   subdomains = await linklater.discover_subdomains(
       domain="sebgroup.com",
       sources=["crtsh", "whoisxml", "sublist3r"]
   )
   ```

3. **CC Index Search** → `/modules/linklater/discovery/url_pattern_discovery.py`
   ```python
   from modules.linklater.api import linklater
   
   # Discover URLs by pattern
   urls = await linklater.discover_urls(
       pattern="*.ly/*/financial",
       archive="CC-MAIN-2025-47"
   )
   ```

---

### Phase 2: Add New Discovery Capabilities

**1. BigQuery Integration:**
```python
from modules.linklater.discovery.bigquery_discovery import BigQueryDiscovery

# Discover domains at scale
bq = BigQueryDiscovery()
domains = await bq.discover_domains(
    tlds=[".ly", ".ru", ".is"],
    keywords=["bank", "finance"],
    min_pagerank=0.01,
    limit=10000
)
```

**2. Majestic Category Discovery:**
```python
from modules.linklater.discovery.majestic_discovery import MajesticDiscovery

# Discover by TopicalTrustFlow category
maj = MajesticDiscovery()
domains = await maj.discover_by_category(
    category="Finance/Banking",
    min_trust_flow=40,
    limit=1000
)
```

**3. Hybrid Discovery (Parallel Multi-Source):**
```python
from modules.linklater.api import linklater

# Run ALL discovery sources in parallel
discovered = await linklater.discover_all(
    tlds=[".ly"],
    keywords=["libya", "tripoli"],
    sources=["cc_graph", "bigquery", "majestic", "crtsh"],
    min_quality_score=40
)
```

---

## Recommended File Structure

```
linklater/
├── discovery/              # NEW DIRECTORY
│   ├── __init__.py
│   ├── cc_graph_discovery.py       # CC Web Graph domain discovery
│   ├── subdomain_discovery.py      # Multi-source subdomain enum
│   ├── url_pattern_discovery.py    # CC Index URL pattern search
│   ├── bigquery_discovery.py       # BigQuery domain search (NEW)
│   ├── majestic_discovery.py       # Majestic category/TF discovery (NEW)
│   └── hybrid_discovery.py         # Parallel multi-source (NEW)
│
├── enrichment/             # EXISTING (rename for clarity)
│   ├── __init__.py
│   ├── backlink_enrichment.py      # Current get_backlinks()
│   └── content_enrichment.py       # Scraping, entity extraction
│
├── api.py                  # UPDATED
└── pipelines/              # EXISTING
```

---

## API Design

### Discovery Methods (NEW)

```python
from modules.linklater.api import linklater

# DISCOVERY METHODS (no target domain required)
# ================================================

# 1. Discover domains linking to TLD/pattern
inbound_domains = await linklater.discover_inbound_domains(
    tld=".ly",
    min_weight=10,
    archive="CC-MAIN-2025-47"
)

# 2. Discover subdomains
subdomains = await linklater.discover_subdomains(
    base_domain="sebgroup.com",
    sources=["crtsh", "whoisxml"]
)

# 3. Discover URLs by pattern
urls = await linklater.discover_urls(
    pattern="*.ly/*/about",
    archive="CC-MAIN-2025-47"
)

# 4. Discover domains by keywords (BigQuery)
keyword_domains = await linklater.discover_by_keywords(
    keywords=["libya", "tripoli", "benghazi"],
    tlds=[".ly", ".com"],
    source="bigquery",
    limit=10000
)

# 5. Discover domains by category (Majestic)
category_domains = await linklater.discover_by_category(
    category="Finance/Banking",
    min_trust_flow=40,
    source="majestic"
)

# 6. Hybrid discovery (ALL sources in parallel)
all_discovered = await linklater.discover_all(
    tlds=[".ly"],
    keywords=["libya"],
    categories=["Finance"],
    sources=["cc_graph", "bigquery", "majestic", "crtsh"],
    min_quality_score=40,
    parallel=True
)
```

### Enrichment Methods (EXISTING)

```python
# ENRICHMENT METHODS (target domain required)
# ===========================================

# Get backlinks (current implementation)
backlinks = await linklater.get_backlinks(
    domain="sebgroup.com",
    limit=1000,
    use_globallinks=True
)

# Get Majestic backlinks (current implementation)
majestic = await linklater.get_majestic_backlinks(
    domain="sebgroup.com",
    mode="fresh",
    result_type="pages"
)
```

---

## Parallelization Strategy

### Discovery (Parallel by Default)

```python
# Example: Discover .ly domains in parallel
async def discover_ly_domains():
    tasks = [
        linklater.discover_inbound_domains(tld=".ly", source="cc_graph"),
        linklater.discover_by_keywords(keywords=["libya"], tlds=[".ly"], source="bigquery"),
        linklater.discover_by_category(category="Finance", tld=".ly", source="majestic")
    ]
    results = await asyncio.gather(*tasks)  # Parallel execution
    return merge_and_deduplicate(results)
```

**Parallel Sources:**
- ✅ CC Graph
- ✅ BigQuery
- ✅ Majestic
- ✅ crt.sh (subdomain)
- ✅ WhoisXML (subdomain)
- ✅ Sublist3r (subdomain)

**Runtime:** ~10-30 seconds for 6 parallel sources

---

### Enrichment (Parallel Phases)

**Phase 1 (Parallel):**
- CC Graph backlinks
- GlobalLinks backlinks

**Phase 2 (Parallel):**
- Majestic Fresh backlinks
- Majestic Historic backlinks

**Total Runtime:** ~10-30 seconds for 4 parallel sources + sequential deep scans

---

## Implementation Priority

### HIGH PRIORITY (Add to LinkLater)

1. ✅ **Move CC Inbound Domains CLI to LinkLater** → `/discovery/cc_graph_discovery.py`
2. ✅ **Move Subdomain Discovery to LinkLater** → `/discovery/subdomain_discovery.py`
3. ✅ **Add Majestic Category Discovery** → `/discovery/majestic_discovery.py`

### MEDIUM PRIORITY

4. **Add BigQuery Integration** → `/discovery/bigquery_discovery.py`
5. **Add Hybrid Discovery Orchestrator** → `/discovery/hybrid_discovery.py`

### LOW PRIORITY

6. **Add Domain Filtering by Metadata** (pagerank, trustflow, etc.)
7. **Add Elastic caching for discovered domains**

---

## Usage Examples

### Example 1: Find All Finance Domains Linking to Libya

```python
from modules.linklater.api import linklater

# DISCOVERY: Find domains linking to .ly TLDs
inbound = await linklater.discover_inbound_domains(
    tld=".ly",
    min_weight=5,
    source="cc_graph"
)
# → Returns: ['bank.com', 'finance.co.uk', 'sebgroup.com', ...]

# ENRICHMENT: Get details on discovered domains
for domain in inbound[:10]:
    backlinks = await linklater.get_majestic_backlinks(
        domain=domain,
        mode="fresh",
        max_results=100
    )
    print(f"{domain}: {len(backlinks)} backlinks")
```

**Parallel Execution:** Discovery runs first (fast), then enrichment for top 10 domains (parallel batches)

---

### Example 2: Comprehensive Libya Investigation

```python
# Phase 1: DISCOVERY (find all relevant domains)
discovered_domains = await linklater.discover_all(
    tlds=[".ly"],
    keywords=["libya", "tripoli", "benghazi", "lia"],
    categories=["Finance", "Government"],
    sources=["cc_graph", "majestic", "bigquery"],
    parallel=True
)
# → Runs 3 sources in parallel, ~15 seconds
# → Returns: 500 discovered domains

# Phase 2: ENRICHMENT (get backlinks for discovered domains)
enriched = []
for domain in discovered_domains[:50]:  # Top 50
    backlinks = await linklater.get_backlinks(domain, limit=100)
    enriched.append({
        'domain': domain,
        'backlinks': backlinks
    })
# → Runs sequentially (50 domains), ~2 minutes
# → Or batch in parallel (10 domains/batch), ~30 seconds
```

---

## Summary

**Current State:**
- ✅ **Enrichment:** Complete in LinkLater (4 parallel sources)
- ✅ **Discovery:** Integrated in LinkLater (imports from categorizer-filterer)
- ✅ **BigQuery:** Integrated (domain search, technology, country filters)
- ✅ **OpenPageRank:** Integrated (domain authority filtering)
- ✅ **Tranco:** Integrated (top sites ranking)
- ✅ **Cloudflare Radar:** Integrated (traffic-based rankings)
- ⚠️ **Subdomain Discovery:** Available in alldom, not yet added to LinkLater
- ⚠️ **Majestic Discovery:** Not implemented (Majestic enrichment works)

**Completed Actions:**
1. ✅ **Created** `/modules/linklater/discovery/domain_filters.py`
2. ✅ **Imported** categorizer-filterer CLIs (BigQuery, OpenPageRank, Tranco, Cloudflare)
3. ✅ **Added** discovery methods to `linklater/api.py`
4. ✅ **Parallel discovery** orchestrator implemented
5. ✅ **CLI locations preserved** (CLIs stay in categorizer-filterer)

**Expected Outcome:**
- **Discovery + Enrichment** in one unified API
- **6+ parallel sources** for discovery
- **4 parallel sources** for enrichment
- **Clear separation:** Discovery (find domains) vs Enrichment (analyze known domain)
