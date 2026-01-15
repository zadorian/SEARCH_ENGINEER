# LinkGraph Architecture: ES CC Graph + GlobalLinks Integration

## The Correct Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ ELASTICSEARCH CC WEB GRAPH                                      │
│                                                                 │
│ • cc_domain_edges: 435M domain-to-domain relationships         │
│ • cc_web_graph_host_edges: 421M host-to-host relationships     │
│ • cc_domain_vertices: 100M domains                             │
│ • cc_host_vertices: 235M hosts                                 │
│                                                                 │
│ Purpose: FAST graph queries (Who links to X? Who does X link?) │
│ Speed: Milliseconds for graph traversal                        │
│ Data: Domain/host level only, no page content                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    Results feed into ↓
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ GLOBALLINKS (Go Binaries + Common Crawl WAT Files)            │
│                                                                 │
│ • Outlinker: Extract outlinks from specific domains            │
│ • LinksAPI: API server for link queries                        │
│ • StoreLinks: Store extracted links locally                    │
│                                                                 │
│ Purpose: Get CONTENT from Common Crawl WAT files               │
│ Speed: Seconds to minutes (downloads from S3)                  │
│ Data: Page-level (URLs, anchor text, context)                 │
└─────────────────────────────────────────────────────────────────┘
```

## Why We Need Both

### ES CC Graph (Fast, Structural)
- **Query:** "What domains link to bbc.com?"
- **Result:** List of 50,000 domains in milliseconds
- **Limitation:** Domain-level only, no page URLs or anchor text

### GlobalLinks (Slow, Rich)
- **Query:** "Extract actual links from nytimes.com pages"
- **Result:** Full URLs, anchor text, link context from WAT files
- **Limitation:** Must download/process actual crawl data (slower)

## The Optimal Workflow

### Use Case 1: Backlink Discovery

```python
# Step 1: Fast graph query to find linking domains (ES)
cc_client = CCGraphClient()
linking_domains = await cc_client.get_backlinks("example.com", limit=1000)
# Returns: ["nytimes.com", "bbc.com", "guardian.com", ...]
# Speed: <1 second

# Step 2: Extract actual page links from those domains (GlobalLinks)
gl_client = GlobalLinksClient()
for domain in linking_domains[:10]:  # Top 10 by weight
    links = await gl_client.extract_outlinks(
        domains=[domain],
        url_keywords=["example.com"],
        archive="CC-MAIN-2024-10"
    )
    # Returns: Full LinkRecord with URLs, anchor text, context
    # Speed: ~5 seconds per domain
```

### Use Case 2: Country-Specific Links

```python
# Step 1: Get domains linking to target (ES)
all_backlinks = await cc_client.get_backlinks("company.com", limit=5000)

# Step 2: Filter by country TLD and get content (GlobalLinks)
uk_links = await gl_client.extract_outlinks(
    domains=[bl.source for bl in all_backlinks],
    country_tlds=[".uk"],
    url_keywords=["company.com"],
    max_results=100
)
# Returns: Only UK pages linking to company.com with full context
```

### Use Case 3: Anchor Text Analysis

```python
# ES gives us: "These 100 domains link to target.com"
domains = await cc_client.get_backlinks("target.com", limit=100)

# GlobalLinks gives us: "Here's HOW they link (anchor text)"
for domain in domains:
    links = await gl_client.extract_outlinks(
        domains=[domain],
        url_keywords=["target.com"]
    )
    for link in links:
        print(f"{link.source} → {link.target}")
        print(f"Anchor: {link.anchor_text}")
```

## Implementation: Unified Query Method

```python
async def get_backlinks_with_context(
    domain: str,
    limit: int = 100,
    include_anchor_text: bool = True,
    country_filter: Optional[List[str]] = None
) -> List[LinkRecord]:
    """
    Unified backlink query using ES + GlobalLinks.

    Args:
        domain: Target domain
        limit: Max results
        include_anchor_text: If True, fetch from GlobalLinks (slower)
        country_filter: Filter by country TLDs (requires GlobalLinks)

    Returns:
        List of LinkRecord with full context
    """
    # Phase 1: Fast graph query (ES)
    cc_client = CCGraphClient()
    graph_results = await cc_client.get_backlinks(domain, limit=limit*2)

    if not include_anchor_text and not country_filter:
        # Return graph results immediately (fast path)
        return graph_results[:limit]

    # Phase 2: Enrich with GlobalLinks content
    gl_client = GlobalLinksClient()
    enriched = []

    # Process top results by weight
    sorted_results = sorted(graph_results, key=lambda x: x.weight or 0, reverse=True)

    for result in sorted_results[:limit]:
        links = await gl_client.extract_outlinks(
            domains=[result.source],
            url_keywords=[domain],
            country_tlds=country_filter,
            max_results=10
        )
        enriched.extend(links)

    return enriched[:limit]
```

## Data Storage Strategy

### ES CC Graph (Read-Only)
- **Source:** Pre-indexed from CC Web Graph dataset
- **Update:** Quarterly when new CC releases come out
- **Size:** ~60GB total
- **Purpose:** Fast structural queries

### GlobalLinks Local Cache (`data/links/`)
- **Source:** Extracted on-demand from CC WAT files
- **Update:** As needed for specific domains
- **Size:** Variable (only cache what we use)
- **Purpose:** Rich link context for specific investigations

### When to Cache GlobalLinks Data

```python
# If we query the same domain repeatedly, cache it
if domain in high_value_targets:
    # Extract once, store in data/links/
    await gl_client.extract_outlinks(
        domains=[domain],
        archive="CC-MAIN-2024-10"
    )
    # Future queries use local cache via search command
    await gl_client.search_outlinks(
        target_domain=domain,
        data_path="data/links/"
    )
```

## Performance Characteristics

| Operation                | ES CC Graph | GlobalLinks | Combined      |
| ------------------------ | ----------- | ----------- | ------------- |
| Find 1K backlinks        | 100ms       | N/A         | 100ms         |
| Get anchor text          | N/A         | 5-30s       | 5-30s         |
| Country filtering        | Manual      | Built-in    | ES + GL       |
| Graph traversal (2-hop)  | 200ms       | Minutes     | 200ms + GL    |
| Full link context        | No          | Yes         | ES finds, GL enriches |

## Summary

**ES CC Graph:**
- The source of truth for WHICH domains are connected
- Fast structural queries (graph traversal, centrality, paths)
- Domain/host level granularity

**GlobalLinks:**
- Downloads actual page content from Common Crawl
- Provides URL-level links, anchor text, context
- Filters by country TLD, keywords, patterns

**Correct Usage:**
1. Query ES graph to find relevant domains (fast)
2. Use those results to target GlobalLinks extraction (precise)
3. Cache frequently-queried extractions locally

**The ES graph tells us WHERE to look, GlobalLinks tells us WHAT we'll find there.**
