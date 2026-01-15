# GlobalLinks Integration with Elasticsearch CC Web Graph

## Executive Summary

**ES CC Graph + GlobalLinks = Complete Link Intelligence**

- **ES holds the map** (435M domain edges, 421M host edges)
- **GlobalLinks fetches the terrain** (actual page content from Common Crawl)

The ES graph tells us WHICH domains to investigate, GlobalLinks downloads the actual content.

---

## The Data We Have in Elasticsearch

### Domain-Level Graph (cc_domain_edges, cc_domain_vertices)
```
Size: 435,770,000 edges + 100,662,487 vertices
Granularity: domain → domain
Example: "nytimes.com" → "example.com"
Data: Weight/frequency, no page URLs or anchor text
Query Speed: Milliseconds
```

### Host-Level Graph (cc_web_graph_host_edges, cc_host_vertices)
```
Size: 421,203,112 edges + 235,648,112 vertices
Granularity: host → host (subdomain level)
Example: "blog.nytimes.com" → "shop.example.com"
Data: Weight/frequency, no page URLs or anchor text
Query Speed: Milliseconds
```

**What ES Gives Us:**
- Fast graph traversal (Who links to X? 2-hop neighbors? Centrality?)
- Domain/host level relationships
- Link weight/frequency

**What ES Does NOT Give Us:**
- Actual page URLs (only domain/host)
- Anchor text
- Link context
- Country-specific filtering at page level

---

## What GlobalLinks Provides

**Location:** `categorizer-filterer/globallinks/globallinks-with-outlinker/bin/`

### Three Go Binaries:

#### 1. `outlinker extract`
Downloads and parses Common Crawl WAT files to extract outlinks FROM specific domains.

```bash
./outlinker extract \
  --domains=nytimes.com \
  --archive=CC-MAIN-2024-10 \
  --country-tlds=.uk \
  --url-keywords=example.com \
  --max-results=1000 \
  --format=json
```

**Output:**
```json
{
  "source": "https://www.nytimes.com/2024/03/article.html",
  "target": "https://www.example.com/page.html",
  "anchorText": "Read more at Example",
  "context": "...surrounding text..."
}
```

#### 2. `outlinker search`
Searches pre-extracted link data (cached locally in `data/links/`).

```bash
./outlinker search \
  --target-domain=example.com \
  --input=data/links/
```

Used when we've already extracted links from high-value domains.

#### 3. `linksapi`
API server for link queries (alternative to direct binary calls).

---

## The Correct Integration Workflow

### Scenario 1: "Who links to my company?"

```python
# STEP 1: Fast graph query (ES) - Get domain list
from linklater.linkgraph import CCGraphClient

cc = CCGraphClient()
backlinks = await cc.get_backlinks("example.com", limit=1000)
# Returns in ~100ms: ["nytimes.com", "bbc.com", "guardian.com", ...]
# Data: Domain names + link weight

# STEP 2: Enrich top results with GlobalLinks
from linklater.linkgraph import GlobalLinksClient

gl = GlobalLinksClient()

# Sort by weight, take top 20
top_domains = sorted(backlinks, key=lambda x: x.weight, reverse=True)[:20]

for link in top_domains:
    # Extract actual page links from this domain
    pages = await gl.extract_outlinks(
        domains=[link.source],
        url_keywords=["example.com"],
        archive="CC-MAIN-2024-10"
    )
    # Now we have: full URLs, anchor text, context
    for page in pages:
        print(f"{page.source} → {page.target}")
        print(f"Anchor: {page.anchor_text}")
```

**Result:**
- ES tells us "nytimes.com links to you with weight 47"
- GlobalLinks shows "these 12 specific NYT articles link with these anchor texts"

---

### Scenario 2: "Find UK media coverage"

```python
# STEP 1: ES graph - Find all backlinks
backlinks = await cc.get_backlinks("company.com", limit=5000)

# STEP 2: Filter by UK domains (domain-level filter)
uk_domains = [bl.source for bl in backlinks if bl.source.endswith(".uk")]

# STEP 3: GlobalLinks - Get UK page-level links
uk_pages = await gl.extract_outlinks(
    domains=uk_domains[:50],  # Top 50 UK domains
    country_tlds=[".uk"],
    url_keywords=["company.com"],
    max_results=500
)

# Result: Actual UK news articles with anchor text and context
```

---

### Scenario 3: "Graph traversal + content"

```python
# Multi-hop: Find who links to NYT, then who links to THOSE domains

# STEP 1: ES 2-hop query (fast)
tier1 = await cc.get_backlinks("nytimes.com", limit=100)
tier2_queries = [cc.get_backlinks(t1.source, limit=10) for t1 in tier1]
tier2 = await asyncio.gather(*tier2_queries)

# STEP 2: For interesting patterns, get content via GlobalLinks
interesting_domains = analyze_tier2(tier2)  # Your filtering logic

for domain in interesting_domains:
    content = await gl.extract_outlinks(
        domains=[domain],
        archive="CC-MAIN-2024-10"
    )
```

---

## Performance Strategy

### When to Use ES Only (Fast Path)
```python
# Just need domain-level relationships
backlinks = await cc.get_backlinks("example.com", limit=1000)
# 100ms response, 1000 domain names
```

### When to Use ES + GlobalLinks (Rich Path)
```python
# Need anchor text, page URLs, or country filtering
domains = await cc.get_backlinks("example.com", limit=100)
enriched = await gl.extract_from_domains(domains[:20])
# 5-30s response, 20 domains with full page context
```

### Caching Strategy
```python
# For high-value domains, cache GlobalLinks extractions locally
high_value = ["nytimes.com", "bbc.com", "reuters.com"]

for domain in high_value:
    # Extract once, store in data/links/
    await gl.extract_outlinks(
        domains=[domain],
        archive="CC-MAIN-2024-10"
    )

# Future queries use cached data (fast)
await gl.search_outlinks(
    target_domain="example.com",
    data_path="data/links/"  # Uses local cache
)
```

---

## Code Location

### Python Integration
```
python-backend/modules/linklater/linkgraph/
├── __init__.py          # Public API
├── globallinks.py       # GlobalLinksClient (subprocess wrapper)
├── cc_graph.py          # CCGraphClient (ES query wrapper)
├── models.py            # LinkRecord data model
└── ARCHITECTURE.md      # This document
```

### MCP Integration
```python
# MCP tools available:
await mcp__linklater__get_backlinks({
    "domain": "example.com",
    "provider": "cc_graph",  # Fast ES query
    "limit": 1000
})

await mcp__linklater__enrich_urls({
    "urls": [...],
    "provider": "globallinks",  # Rich content
    "include_anchor_text": True
})
```

---

## Data Flow Diagram

```
USER QUERY: "Who links to example.com?"
    ↓
┌─────────────────────────────────────┐
│ 1. CCGraphClient.get_backlinks()   │
│    Queries: cc_domain_edges (ES)   │
│    Returns: 1000 domains in 100ms  │
│    Data: ["nytimes.com", ...]      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. Filter/Sort by weight           │
│    Take top 20 domains             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. GlobalLinksClient.extract()     │
│    Downloads: CC WAT files (S3)    │
│    Returns: Full page URLs in 30s  │
│    Data: URLs + anchor text        │
└─────────────────────────────────────┘
    ↓
RESULT: "NYT article X links with anchor 'Company raises $50M'"
```

---

## Why Both Are Needed

| Question | ES CC Graph | GlobalLinks |
|----------|------------|-------------|
| "What domains link to X?" | ✅ Perfect | ❌ Too slow |
| "What pages link to X?" | ❌ No page URLs | ✅ Full URLs |
| "What's the anchor text?" | ❌ Not stored | ✅ Extracted |
| "2-hop graph traversal?" | ✅ Fast | ❌ Impractical |
| "Filter by .uk domains?" | ⚠️ Manual | ✅ Built-in |
| "Get context around link?" | ❌ No content | ✅ Yes |

**The Principle:** ES is the index, GlobalLinks is the retrieval system.

---

## Common Crawl Archive Selection

GlobalLinks queries specific CC archives:

```python
# Latest archive
archive = "CC-MAIN-2024-10"  # October 2024 crawl

# Multiple archives for temporal analysis
archives = ["CC-MAIN-2024-10", "CC-MAIN-2024-04", "CC-MAIN-2023-10"]
for arc in archives:
    links = await gl.extract_outlinks(domains=["example.com"], archive=arc)
```

**ES graph is rebuilt quarterly** when new CC releases come out.
**GlobalLinks can query any archive** on-demand from S3.

---

## Summary

1. **ES CC Graph = Fast structural queries** (Who's connected? Graph metrics?)
2. **GlobalLinks = Slow content retrieval** (What's the actual link? Anchor text?)
3. **Correct workflow:** ES finds domains → GlobalLinks enriches top results
4. **Cache strategy:** Store GlobalLinks extractions for high-value domains
5. **Performance:** ES for bulk, GlobalLinks for detail

**The ES graph is the map. GlobalLinks is the ground survey crew.**
