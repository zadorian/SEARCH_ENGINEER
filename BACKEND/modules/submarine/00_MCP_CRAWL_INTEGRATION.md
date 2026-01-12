# SUBMARINE MCP Integration - Domain Crawling

**STATUS**: Ready to integrate optimized parallel crawler into MCP server

## Current MCP Server

**File**: 

**Current tools** (scraping only):
-  - Single URL scraping (JESTER)
-  - Multiple URLs
-  - Archive retrieval (BACKDRILL)
-  - CC index search

**Missing**: Domain crawling capability

---

## Required Addition: crawl_domains Tool

Add to :

### 1. Tool Definition (add to list_tools)

```python
Tool(
    name="crawl_domains",
    description="Launch optimized parallel crawler for domain list. Crawls full domains (not just front pages) with PACMAN entity extraction. Uses 19 workers processing 20 domains concurrently each (380 total concurrent).",
    inputSchema={
        "type": "object",
        "properties": {
            "domain_file": {
                "type": "string",
                "description": "Path to file with seed URLs (one per line). Can be local or absolute path."
            },
            "max_pages": {
                "type": "integer",
                "description": "Max pages per domain (default: 50). Higher = more comprehensive but slower.",
                "default": 50
            },
            "max_depth": {
                "type": "integer",
                "description": "Crawl depth - how many levels of internal links to follow (default: 2).",
                "default": 2
            },
            "es_index": {
                "type": "string",
                "description": "Elasticsearch index name (default: submarine-scrapes)",
                "default": "submarine-scrapes"
            }
        },
        "required": ["domain_file"]
    }
)
```

### 2. Tool Handler (add to call_tool)

```python
elif name == "crawl_domains":
    import subprocess
    import tempfile
    from pathlib import Path
    
    domain_file = arguments.get("domain_file")
    max_pages = arguments.get("max_pages", 50)
    max_depth = arguments.get("max_depth", 2)
    es_index = arguments.get("es_index", "submarine-scrapes")
    
    # Validate domain file
    domain_path = Path(domain_file)
    if not domain_path.exists():
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Domain file not found: {domain_file}",
                "status": "failed"
            }, indent=2)
        )]
    
    # Count domains
    with open(domain_path) as f:
        domain_count = sum(1 for line in f if line.strip().startswith('http'))
    
    # Launch crawler
    cmd = [
        "bash",
        "/data/SUBMARINE/launch_parallel_crawl.sh",
        str(domain_path),
        str(max_pages),
        str(max_depth)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 min timeout for launch only
        )
        
        # Calculate estimates
        workers = 19
        concurrent_per_worker = 20
        total_concurrent = workers * concurrent_per_worker
        avg_time_per_domain = 7  # seconds
        estimated_hours = (domain_count / total_concurrent * avg_time_per_domain) / 3600
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "launched" if result.returncode == 0 else "failed",
                "domains": domain_count,
                "workers": workers,
                "concurrent_per_worker": concurrent_per_worker,
                "total_concurrent": total_concurrent,
                "max_pages_per_domain": max_pages,
                "crawl_depth": max_depth,
                "es_index": es_index,
                "estimated_hours": round(estimated_hours, 1),
                "estimated_pages": domain_count * max_pages,
                "monitor_command": "./monitor_crawl.sh " + es_index,
                "check_progress": f"curl -s http://localhost:9200/{es_index}/_count | jq .count",
                "stdout": result.stdout[-500:],  # Last 500 chars
                "stderr": result.stderr[-500:] if result.returncode != 0 else None
            }, indent=2)
        )]
    except subprocess.TimeoutExpired:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Launch timeout (crawlers may still be starting)",
                "status": "unknown",
                "note": "Check screen -ls | grep crawler to verify"
            }, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "status": "failed"
            }, indent=2)
        )]
```

### 3. Monitor Tool (optional but recommended)

Add monitoring capability:

```python
Tool(
    name="crawl_status",
    description="Check status of running crawl operation. Shows active workers, document count, and progress.",
    inputSchema={
        "type": "object",
        "properties": {
            "es_index": {
                "type": "string",
                "description": "Elasticsearch index to check (default: submarine-scrapes)",
                "default": "submarine-scrapes"
            }
        }
    }
)
```

**Handler:**

```python
elif name == "crawl_status":
    import subprocess
    
    es_index = arguments.get("es_index", "submarine-scrapes")
    
    try:
        # Count active workers
        workers_result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        active_workers = len([
            line for line in workers_result.stdout.split('\n')
            if 'jester_crawler_pacman' in line and 'grep' not in line
        ])
        
        # Get document count from ES
        es_result = subprocess.run(
            ["curl", "-s", f"http://localhost:9200/{es_index}/_count"],
            capture_output=True,
            text=True
        )
        
        try:
            es_data = json.loads(es_result.stdout)
            doc_count = es_data.get("count", 0)
        except:
            doc_count = None
        
        # Get index size
        size_result = subprocess.run(
            ["curl", "-s", f"http://localhost:9200/_cat/indices/{es_index}?h=docs.count,store.size"],
            capture_output=True,
            text=True
        )
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "active_workers": active_workers,
                "documents_indexed": doc_count,
                "index_size": size_result.stdout.strip() if size_result.returncode == 0 else None,
                "status": "running" if active_workers > 0 else "idle",
                "es_index": es_index
            }, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2)
        )]
```

---

## Usage Examples

### Via MCP Client

```python
# Launch crawl
result = await mcp_client.call_tool(
    "crawl_domains",
    {
        "domain_file": "/tmp/linkedin_domains.txt",
        "max_pages": 50,
        "max_depth": 2
    }
)

# Check status
status = await mcp_client.call_tool(
    "crawl_status",
    {"es_index": "submarine-scrapes"}
)
```

### Via Claude Code

When user says:
- "Scrape these 2.8M domains"
- "Crawl all LinkedIn company websites"
- "Full domain crawl with entity extraction"

Claude should invoke the  tool via the submarine-remote MCP server.

---

## Integration Status

**Files ready:**
- ✅  - Optimized launcher
- ✅  - Parallel crawler (20× faster)
- ✅  - Monitoring script
- ✅  - Documentation

**To integrate:**
1. Add  tool to 
2. Add  tool (optional)
3. Test via MCP client
4. Document in 

---

## When to Use What

| Task | Tool | Why |
|------|------|-----|
| Single URL |  | Fast, uses JESTER tiers |
| 10-100 URLs |  | Concurrent scraping |
| 1000+ domains | **** | Optimized parallel crawler |
| Archive content |  | BACKDRILL |
| CC index search |  | Entity extraction |

---

## Performance Guarantees

When  is invoked:
- **Workers**: 19 (auto-configured)
- **Concurrent**: 20 domains per worker = 380 total
- **Speed**: 6-8 hours for 2.8M domains
- **Extraction**: Full PACMAN (EMAIL, PHONE, LEI, etc.)
- **Depth**: Follows internal links
- **Output**: Elasticsearch index with full content + entities

This is the **DEFAULT** for all large-scale domain scraping operations.
