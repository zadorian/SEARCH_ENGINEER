#!/usr/bin/env python3
"""
BRUTE Search MCP Server
Maximum Recall Search with Auto-Indexing to Elasticsearch + Optional Firecrawl Scraping

Wraps the search_cli.py (L1/L2/L3 depth system) as an MCP server.
Results automatically indexed to Elasticsearch for immediate use in Drill Search.

With --scrape flag: Uses Firecrawl to fetch full content (1900 URLs in parallel batches of 100).
Indexes complete markdown (.md) files instead of search snippets.

Usage in Claude Code:
  "Search for 'John Doe' using BRUTE level 3"
  "Run news search for 'crypto regulation' with scraping enabled"
  "BRUTE search 'annual reports filetype:pdf' level 3 and scrape the results"
"""

import asyncio
import json
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import tempfile
import webbrowser
from urllib.parse import quote
import time
import hashlib
from datetime import datetime
from urllib.parse import urlparse

# MCP SDK
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Firecrawl service for scraping
try:
    from modules.fact_assembler.firecrawl_service import FirecrawlService
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    print("⚠️  Firecrawl service not available - scraping disabled")

# Import Elasticsearch service for indexing scraped content
try:
    from brute.services.elastic_service import get_elastic_service
    ELASTIC_AVAILABLE = True
except ImportError:
    ELASTIC_AVAILABLE = False
    print("⚠️  Elasticsearch service not available - scraped content won't be indexed")

# Static system context so indexed docs are visible to the grid (matches server fallback user)
SYSTEM_USER_ID = int(os.getenv("ELASTIC_USER_ID", "1"))
SYSTEM_PROJECT_ID = os.getenv("ELASTIC_PROJECT_ID") or None
DEFAULT_PROJECT_ID = os.getenv("BRUTE_PROJECT_ID_FALLBACK", "default")
WATCHER_FETCH_LIMIT = int(os.getenv("BRUTE_WATCHER_LIMIT", "50"))
WATCHER_CONTEXT_LIMIT = int(os.getenv("BRUTE_WATCHER_CONTEXT_LIMIT", "200"))
WATCHER_CACHE_TTL = int(os.getenv("BRUTE_WATCHER_CACHE_TTL", "60"))

_watcher_cache: Dict[str, Any] = {
    "project_id": None,
    "timestamp": 0.0,
    "watchers": [],
}


def _get_project_id() -> str:
    return SYSTEM_PROJECT_ID or DEFAULT_PROJECT_ID


def _result_node_id(url: str) -> str:
    return f"search_{hashlib.sha256(url.encode('utf-8')).hexdigest()}"


def _query_node_id(query: str, now_ts: float) -> str:
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]
    return f"query_{query_hash}_{int(now_ts * 1000)}"


def _safe_label(value: str, fallback: str) -> str:
    if not value:
        return fallback
    return value[:200]


def _extract_node_id(source: Dict[str, Any], fallback: Optional[str] = None) -> Optional[str]:
    for key in ("id", "nodeId", "node_id", "watcherId", "entityId", "target_id"):
        value = source.get(key)
        if value:
            return str(value)
    return fallback


def _extract_context_ids(embedded_edges: Any) -> List[str]:
    if not isinstance(embedded_edges, list):
        return []
    context_ids = []
    for edge in embedded_edges:
        if not isinstance(edge, dict):
            continue
        target_id = edge.get("target_id") or edge.get("targetId")
        if target_id:
            context_ids.append(str(target_id))
    return list(dict.fromkeys(context_ids))


async def _fetch_active_watchers(elastic_service, project_id: str) -> List[Dict[str, Any]]:
    now_ts = time.time()
    cache_hit = (
        _watcher_cache["project_id"] == project_id
        and now_ts - _watcher_cache["timestamp"] < WATCHER_CACHE_TTL
    )
    if cache_hit:
        return _watcher_cache["watchers"]

    query = {
        "size": WATCHER_FETCH_LIMIT,
        "query": {
            "bool": {
                "must": [
                    {"term": {"projectId": project_id}},
                    {
                        "bool": {
                            "should": [
                                {"term": {"typeName.keyword": "watcher"}},
                                {"term": {"type.keyword": "watcher"}},
                                {"term": {"typeName": "watcher"}},
                                {"term": {"type": "watcher"}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                ],
                "filter": [
                    {
                        "bool": {
                            "should": [
                                {"term": {"status.keyword": "active"}},
                                {"term": {"status": "active"}},
                                {"bool": {"must_not": [{"exists": {"field": "status"}}]}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                ],
            }
        },
        "_source": [
            "id",
            "label",
            "name",
            "title",
            "status",
            "embedded_edges",
            "metadata",
        ],
    }

    watchers: List[Dict[str, Any]] = []
    try:
        response = await elastic_service.search(query)
        hits = response.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            watcher_id = _extract_node_id(source, hit.get("_id"))
            if not watcher_id:
                continue
            label = (
                source.get("label")
                or source.get("name")
                or source.get("title")
                or watcher_id
            )
            context_ids = _extract_context_ids(source.get("embedded_edges", []))
            if WATCHER_CONTEXT_LIMIT and len(context_ids) > WATCHER_CONTEXT_LIMIT:
                context_ids = context_ids[:WATCHER_CONTEXT_LIMIT]
            watchers.append(
                {
                    "id": watcher_id,
                    "label": label,
                    "status": source.get("status"),
                    "context_ids": context_ids,
                }
            )
    except Exception:
        watchers = []

    _watcher_cache["project_id"] = project_id
    _watcher_cache["timestamp"] = now_ts
    _watcher_cache["watchers"] = watchers

    return watchers

# Server instance
server = Server("brute-search")

# Store last search results for URL selection (simple in-memory cache)
last_search_results = {
    'urls': [],
    'results': [],
    'query': '',
    'timestamp': 0,
    'query_node_id': ''
}

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available BRUTE search tools"""
    return [
        types.Tool(
            name="brute_search",
            description="Maximum recall search across 40+ engines with auto-indexing. Level 1=Native, 2=Tricks, 3=Brute Force. Returns search results with URLs for optional scraping.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports operators: site:, filetype:, intitle:, inurl:, etc.)"
                    },
                    "level": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "Search depth: 1=Native engines only, 2=Native+Tricks (default), 3=Native+Tricks+Brute Force",
                        "default": 2
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["broad", "news", "filetype", "site", "date", "title", "inurl", "link", "ip", "related", "feed", "records"],
                        "description": "Search mode (broad=general web search, news=news-specific, etc.)",
                        "default": "broad"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="brute_scrape_urls",
            description="Scrape full content from selected URLs using Firecrawl (batches of 100 in parallel). Use after brute_search to get full markdown content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to scrape (from search results)"
                    },
                    "query_context": {
                        "type": "string",
                        "description": "Original search query (for metadata)",
                        "default": ""
                    }
                },
                "required": ["urls"]
            }
        ),
        types.Tool(
            name="brute_news_search",
            description="Specialized news search with auto-indexing (NewsAPI, GDELT, Bangs)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "News search query"
                    },
                    "level": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "default": 2
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="brute_filetype_search",
            description="Search for specific file types (PDF, DOC, XLS, etc.) with auto-indexing",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (must include 'filetype:ext' operator, e.g., 'financial report filetype:pdf')"
                    },
                    "level": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "default": 2
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="brute_site_search",
            description="Search within specific domains/sites with auto-indexing",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (must include 'site:domain' operator, e.g., 'corruption site:nytimes.com')"
                    },
                    "level": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "default": 2
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Dict[str, Any] | None
) -> List[types.TextContent]:
    """Execute BRUTE search or scraping tool"""

    if not arguments:
        raise ValueError("Missing arguments")

    # Handle scraping separately
    if name == "brute_scrape_urls":
        return await handle_scrape_urls(arguments)

    # Handle search tools
    query = arguments.get("query")
    level = arguments.get("level", 2)
    limit = arguments.get("limit", 50)

    if not query:
        raise ValueError("Query is required")

    # Map tool name to CLI mode
    mode_map = {
        "brute_search": arguments.get("mode", "broad"),
        "brute_news_search": "news",
        "brute_filetype_search": "filetype",
        "brute_site_search": "site"
    }

    mode = mode_map.get(name, "broad")

    # Build CLI command using brute.py directly
    brute_dir = Path(__file__).parent
    brute_script = brute_dir / "brute.py"

    # Map level to tier
    tier_map = {1: 'fast', 2: 'medium', 3: 'all'}
    tier = tier_map.get(level, 'medium')

    cmd = [
        "python3",
        str(brute_script),
        query,
        f"--tier={tier}",
        "--format=json",
    ]

    # Set environment for proper module imports
    env = os.environ.copy()
    env['PYTHONPATH'] = str(brute_dir.parent)

    try:
        # Run search CLI
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env,
            cwd=str(brute_dir)
        )

        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            return [types.TextContent(
                type="text",
                text=f"❌ Search failed: {error_msg}"
            )]

        # Parse JSON output
        output = result.stdout

        try:
            search_data = json.loads(output)
            results = search_data.get('results', [])
            result_count = len(results)

            # Extract URLs for scraping
            urls = [r.get('url') for r in results if r.get('url')]
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            result_count = 0
            urls = []
            search_data = {}

        # Format response with URLs for user to review
        response = f"""✅ BRUTE Search Complete (Level {level})

Query: {query}
Mode: {mode}
Results: {result_count} indexed to Elasticsearch

📊 Results automatically indexed to `search_nodes` for immediate use in Drill Search.

"""

        # Show top URLs for scraping consideration
        if urls and len(urls) > 0:
            response += f"🔗 **{len(urls)} URLs available for scraping**\n\n"

            # Show first 10 URLs as preview
            preview_count = min(10, len(urls))
            for i, url in enumerate(urls[:preview_count], 1):
                # Get title if available
                result = next((r for r in results if r.get('url') == url), {})
                title = result.get('title', 'No title')[:60]
                response += f"{i}. {title}\n   {url}\n\n"

            if len(urls) > preview_count:
                response += f"... and {len(urls) - preview_count} more URLs\n\n"

            response += f"""
💡 **To scrape these URLs:**

Option 1 - Scrape all {len(urls)} URLs:
   "Scrape all URLs from the search"

Option 2 - Scrape specific URLs:
   "Scrape URLs 1, 3, 5-10 from the search"

Option 3 - Scrape by pattern:
   "Scrape all PDF URLs from the search"
   "Scrape URLs from nytimes.com"

I'll use the brute_scrape_urls tool to fetch full content (batches of 100 parallel).
"""

        response += "\n🔍 Use Cymonides or Graph Explorer to query the indexed snippets."

        # Store URLs for potential scraping and generate HTML selector
        import time
        last_search_results['urls'] = urls
        last_search_results['results'] = results
        last_search_results['query'] = query
        last_search_results['level'] = level
        last_search_results['timestamp'] = time.time()

        # Ensure results are indexed to Elastic so they appear in the grid
        await index_search_results(results, query, level=level, mode=mode)

        # Generate HTML selector and open in browser
        if urls and len(urls) > 0:
            html_path = generate_url_selector_html(search_data)
            webbrowser.open(f'file://{html_path}')
            response += f"\n\n🌐 **URL selector opened in your browser!**\n"
            response += f"Select URLs and click 'Scrape Selected URLs' to fetch full content.\n"

        return [types.TextContent(
            type="text",
            text=response
        )]

    except subprocess.TimeoutExpired:
        return [types.TextContent(
            type="text",
            text=f"❌ Search timeout after 5 minutes. Try reducing scope or using a more specific query."
        )]
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ Error: {str(e)}"
        )]

def generate_url_selector_html(search_data: Dict[str, Any]) -> str:
    """Generate HTML file for URL selection and open in browser"""

    # Read template
    template_path = Path(__file__).parent / "templates" / "url_selector.html"

    try:
        with open(template_path, 'r') as f:
            html_template = f.read()
    except FileNotFoundError:
        # Fallback: create simple inline HTML if template not found
        print(f"Warning: Template not found at {template_path}")
        return ""

    # Encode search data as URL parameter
    data_json = json.dumps(search_data)
    data_param = quote(data_json)

    # Create temporary HTML file with data
    temp_dir = tempfile.gettempdir()
    html_file = Path(temp_dir) / f"brute_search_results_{int(time.time())}.html"

    # Replace placeholder or append data script
    html_with_data = html_template.replace(
        'window.onload = loadData;',
        f"""
        // Embedded data (fallback if URL param fails)
        const embeddedData = {data_json};

        function loadData() {{
            const params = new URLSearchParams(window.location.search);
            const dataParam = params.get('data');

            let data = embeddedData; // Use embedded as fallback

            if (dataParam) {{
                try {{
                    data = JSON.parse(decodeURIComponent(dataParam));
                }} catch (e) {{
                    console.warn('Failed to parse URL data, using embedded:', e);
                }}
            }}

            searchData = data;
            allUrls = searchData.results || [];

            document.getElementById('search-query').textContent = searchData.query || 'Unknown';
            document.getElementById('search-level').textContent = searchData.level || '2';
            document.getElementById('total-urls').textContent = allUrls.length;

            renderUrls();
        }}

        window.onload = loadData;
        """
    )

    # Write HTML file
    with open(html_file, 'w') as f:
        f.write(html_with_data)

    return str(html_file)


async def index_search_results(
    results: List[Dict[str, Any]],
    query: str,
    level: Optional[int] = None,
    mode: Optional[str] = None,
):
    """Index search results plus a query node linked to results and watchers."""
    if not ELASTIC_AVAILABLE:
        return

    elastic_service = get_elastic_service()
    project_id = _get_project_id()
    if getattr(elastic_service, "project_id", None) != project_id:
        elastic_service.set_project_id(project_id)

    docs: List[Dict[str, Any]] = []
    now = datetime.utcnow().isoformat()
    now_ts = time.time()

    edges: List[Dict[str, Any]] = []
    edge_keys = set()

    def add_edge(
        target_id: Optional[str],
        relation: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not target_id:
            return
        key = (target_id, relation)
        if key in edge_keys:
            return
        edge = {
            "target_id": target_id,
            "relation": relation,
            "verification_status": "UNVERIFIED",
            "connection_reason": reason,
        }
        if metadata:
            edge["metadata"] = metadata
        edges.append(edge)
        edge_keys.add(key)

    for idx, res in enumerate(results or []):
        url = res.get("url") or res.get("link")
        if not url:
            continue

        engines = res.get("found_by") or res.get("sources") or (
            [res["engine"]] if res.get("engine") else []
        )
        engine_list = engines if isinstance(engines, list) else [engines]
        primary_engine = engine_list[0] if engine_list else None
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ""

        result_id = _result_node_id(url)
        docs.append(
            {
                "id": result_id,
                "label": _safe_label(res.get("title") or url, url),
                "content": res.get("snippet") or res.get("description") or "",
                "className": "source",
                "typeName": "search_result",
                "urls": [url],
                "domains": [domain] if domain else [],
                "metadata": {
                    "search_query": query,
                    "search_engines": engine_list,
                    "source": "brute_mcp",
                    "found_at": now,
                },
                "userId": SYSTEM_USER_ID,
                "projectId": project_id,
                "lastSeen": now,
                "createdAt": now,
                "updatedAt": now,
            }
        )

        add_edge(
            result_id,
            "has_result",
            "brute_search_result",
            metadata={
                "created_at": now,
                "source_system": "brute_mcp",
                "engine": primary_engine,
                "engines": engine_list,
                "rank": idx + 1,
                "query_type": mode or "broad",
                "url": url,
            },
        )

    watchers = await _fetch_active_watchers(elastic_service, project_id)
    for watcher in watchers:
        watcher_id = watcher.get("id")
        if not watcher_id:
            continue
        watcher_label = watcher.get("label") or watcher_id
        add_edge(
            watcher_id,
            "active_watcher",
            "active_watcher",
            metadata={
                "watcher_label": watcher_label,
                "watcher_status": watcher.get("status"),
            },
        )
        for context_id in watcher.get("context_ids", []):
            add_edge(
                context_id,
                "watcher_context",
                "watcher_context",
                metadata={
                    "watcher_id": watcher_id,
                    "watcher_label": watcher_label,
                },
            )

    query_id = _query_node_id(query, now_ts)
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    query_node = {
        "id": query_id,
        "label": _safe_label(query, "query"),
        "canonicalValue": query,
        "query": query,
        "className": "nexus",
        "typeName": "query",
        "node_class": "NEXUS",
        "type": "query",
        "metadata": {
            "search_query": query,
            "search_mode": mode,
            "search_level": level,
            "source": "brute_mcp",
            "executed_at": now,
            "query_hash": query_hash,
            "result_count": len(results or []),
            "watcher_count": len(watchers),
        },
        "embedded_edges": edges,
        "userId": SYSTEM_USER_ID,
        "projectId": project_id,
        "lastSeen": now,
        "createdAt": now,
        "updatedAt": now,
    }
    docs.append(query_node)

    last_search_results["query_node_id"] = query_id

    if docs:
        await elastic_service.index_batch(docs)

async def handle_scrape_urls(arguments: Dict[str, Any]) -> List[types.TextContent]:
    """Handle URL scraping requests"""

    if not FIRECRAWL_AVAILABLE:
        return [types.TextContent(
            type="text",
            text="❌ Firecrawl service not available. Install dependencies first."
        )]

    urls = arguments.get("urls", [])
    query_context = arguments.get("query_context", last_search_results.get('query', ''))

    if not urls:
        return [types.TextContent(
            type="text",
            text="❌ No URLs provided. Please specify URLs to scrape."
        )]

    response = f"🔥 Scraping {len(urls)} URLs with Firecrawl...\n\n"

    try:
        firecrawl = FirecrawlService()

        response += f"   📄 Processing {len(urls)} URLs in batches of 100...\n"
        scraped_results = firecrawl.scrape_urls(urls, use_cache=True)

        successful_scrapes = sum(1 for _, content, _ in scraped_results if content)
        total_chars = sum(len(content) if content else 0 for _, content, _ in scraped_results)

        response += f"   ✅ Scraped: {successful_scrapes}/{len(urls)} URLs\n"
        response += f"   📝 Total content: {total_chars:,} characters\n\n"

        # Index scraped content to Elasticsearch
        if ELASTIC_AVAILABLE and scraped_results:
            try:
                docs_to_index = []
                now = datetime.utcnow().isoformat()
                for url, markdown_content, metadata in scraped_results:
                    if markdown_content:
                        # Find matching result from stored search results
                        original_result = next(
                            (r for r in last_search_results['results'] if r.get('url') == url),
                            {}
                        )

                        doc = {
                            'id': f"scrape_{hashlib.sha256(url.encode('utf-8')).hexdigest()}",
                            'url': url,
                            'label': original_result.get('title', metadata.get('title', url))[:200],
                            'title': original_result.get('title', metadata.get('title', url)),
                            'content': markdown_content,
                            'snippet': markdown_content[:500] + '...' if len(markdown_content) > 500 else markdown_content,
                            'metadata': {
                                'source': 'brute_scrape',
                                'query': query_context,
                                'scraped_at': now,
                                **metadata
                            },
                            'className': 'source',
                            'typeName': 'scraped_content',
                            'urls': [url],
                            'domains': [urlparse(url).netloc] if url else [],
                            'userId': SYSTEM_USER_ID,
                            'projectId': SYSTEM_PROJECT_ID,
                            'lastSeen': now,
                            'createdAt': now,
                            'updatedAt': now,
                        }
                        docs_to_index.append(doc)

                if docs_to_index:
                    elastic_service = get_elastic_service()
                    indexed = await elastic_service.index_batch(docs_to_index)

                    if indexed:
                        response += f"   💾 {len(docs_to_index)} markdown files indexed to Elasticsearch\n"
                        response += f"\n✅ Full content is now searchable in Cymonides!"
                    else:
                        response += f"   ⚠️  Indexing to Elasticsearch failed\n"
            except Exception as index_error:
                response += f"   ⚠️  Indexing error: {str(index_error)}\n"
        else:
            response += f"   💾 Markdown files scraped (Elasticsearch not available)\n"

        return [types.TextContent(type="text", text=response)]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ Scraping error: {str(e)}"
        )]

async def main():
    """Run BRUTE Search MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="brute-search",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
