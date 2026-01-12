#!/usr/bin/env python3
"""
BACKDRILL MCP Server - Archive Intelligence & Version Comparison

THE EXPERT on all things archive search, URL mapping, and domain versioning.

Tools:
  URL MAPPING:
  - backdrill_map_domain: Map all URLs for a domain across archives
  - backdrill_url_count: Quick count of archived URLs per source

  VERSION COMPARISON:
  - backdrill_domain_evolution: Track how a domain changed over time
  - backdrill_compare_periods: Compare domain at two time points
  - backdrill_page_history: Get version history for a specific URL
  - backdrill_find_content_change: Find when content appeared/disappeared

  C3 ENTITY QUERIES (Pre-indexed CommonCrawl):
  - backdrill_c3_orgs: Search WDC organization entities (9.6M)
  - backdrill_c3_persons: Search WDC person entities (6.8M)
  - backdrill_c3_webgraph: Search web graph edges (421M)
  - backdrill_c3_domains: Search unified domains (180M)
  - backdrill_c3_pdfs: Search indexed PDFs (67K+)

  STATUS:
  - backdrill_status: Get BACKDRILL system status

Usage:
  python mcp_server.py

SASTRE Integration:
  Add to .claude/settings.json mcp_servers:
  {
    "backdrill": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "modules.backdrill.mcp_server"],
      "cwd": "/data/SEARCH_ENGINEER/BACKEND"
    }
  }
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("backdrill-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Add module paths
BACKDRILL_ROOT = Path(__file__).resolve().parent
BACKEND_MODULES = Path("/data/SEARCH_ENGINEER/BACKEND/modules")
sys.path.insert(0, str(BACKDRILL_ROOT))
sys.path.insert(0, str(BACKEND_MODULES))
sys.path.insert(0, "/data/SEARCH_ENGINEER/BACKEND")
sys.path.insert(0, "/data")

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(Path("/data/.env"))
except ImportError:
    pass


# Import BACKDRILL components
MAPPER_AVAILABLE = False
DIFFER_AVAILABLE = False
C3_AVAILABLE = False

try:
    from modules.backdrill.mapper import BackdrillMapper, MappedURL, DomainMap
    MAPPER_AVAILABLE = True
    logger.info("BackdrillMapper loaded successfully")
except ImportError as e:
    logger.warning(f"BackdrillMapper not available: {e}")

try:
    from modules.backdrill.differ import (
        DomainDiffer,
        DomainEvolution,
        PeriodComparison,
        PageHistory,
        ContentAppearance,
    )
    DIFFER_AVAILABLE = True
    logger.info("DomainDiffer loaded successfully")
except ImportError as e:
    logger.warning(f"DomainDiffer not available: {e}")

try:
    from modules.backdrill.c3_bridge import C3Bridge
    C3_AVAILABLE = True
    logger.info("C3Bridge loaded successfully")
except ImportError as e:
    logger.warning(f"C3Bridge not available: {e}")


class BackdrillMCP:
    """BACKDRILL MCP Server - Archive Intelligence & Version Comparison"""

    def __init__(self):
        self.server = Server("backdrill")
        self._mapper: Optional[BackdrillMapper] = None
        self._differ: Optional[DomainDiffer] = None
        self._c3: Optional[C3Bridge] = None
        self._register_handlers()

    async def _ensure_mapper(self) -> Optional[BackdrillMapper]:
        """Lazy-load mapper."""
        if not MAPPER_AVAILABLE:
            return None
        if self._mapper is None:
            self._mapper = BackdrillMapper()
            await self._mapper._ensure_clients()
        return self._mapper

    async def _ensure_differ(self) -> Optional[DomainDiffer]:
        """Lazy-load differ."""
        if not DIFFER_AVAILABLE:
            return None
        if self._differ is None:
            self._differ = DomainDiffer()
            await self._differ._ensure_clients()
        return self._differ

    async def _ensure_c3(self) -> Optional[C3Bridge]:
        """Lazy-load C3 bridge."""
        if not C3_AVAILABLE:
            return None
        if self._c3 is None:
            self._c3 = C3Bridge()
        return self._c3

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            tools = []

            # =================================================================
            # URL MAPPING TOOLS
            # =================================================================
            if MAPPER_AVAILABLE:
                tools.extend([
                    Tool(
                        name="backdrill_map_domain",
                        description="""Map all URLs for a domain across archive sources.

Discovers all archived URLs by querying:
- Wayback Machine CDX API
- CommonCrawl Index API
- Memento TimeMap (40+ archives, optional)

Returns: URL list with timestamps, sources, and statistics by year.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain (e.g., 'example.com')"},
                                "start_date": {"type": "string", "description": "Optional start date (YYYY-MM-DD)"},
                                "end_date": {"type": "string", "description": "Optional end date (YYYY-MM-DD)"},
                                "mime_filter": {"type": "string", "description": "Filter by MIME type (e.g., 'text/html')"},
                                "limit_per_source": {"type": "integer", "default": 1000, "description": "Max URLs per source"},
                            },
                            "required": ["domain"]
                        }
                    ),
                    Tool(
                        name="backdrill_url_count",
                        description="""Quick count of archived URLs per source (no full fetch).

Fast way to estimate archive coverage before full mapping.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"}
                            },
                            "required": ["domain"]
                        }
                    ),
                    Tool(
                        name="backdrill_snapshots",
                        description="""Get all snapshots/versions of a specific URL.

Returns all archived versions with timestamps and archive URLs.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "Target URL"},
                                "limit": {"type": "integer", "default": 100, "description": "Max snapshots"}
                            },
                            "required": ["url"]
                        }
                    ),
                ])

            # =================================================================
            # VERSION COMPARISON TOOLS
            # =================================================================
            if DIFFER_AVAILABLE:
                tools.extend([
                    Tool(
                        name="backdrill_domain_evolution",
                        description="""Analyze how a domain evolved over time.

Groups URLs by year and tracks:
- Pages added each year
- Pages removed each year
- Total URL counts per period

Essential for understanding domain history.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"},
                                "start_year": {"type": "integer", "description": "Optional start year filter"},
                                "end_year": {"type": "integer", "description": "Optional end year filter"},
                            },
                            "required": ["domain"]
                        }
                    ),
                    Tool(
                        name="backdrill_compare_periods",
                        description="""Compare a domain at two different time periods.

Shows:
- URLs added between periods
- URLs removed between periods
- URLs that existed in both
- Content changes for common URLs (optional)

Perfect for understanding what changed between two dates.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"},
                                "period1": {"type": "string", "description": "First date (YYYY-MM-DD or YYYY)"},
                                "period2": {"type": "string", "description": "Second date (YYYY-MM-DD or YYYY)"},
                                "fetch_content": {"type": "boolean", "default": False, "description": "Compare content of common URLs"},
                            },
                            "required": ["domain", "period1", "period2"]
                        }
                    ),
                    Tool(
                        name="backdrill_page_history",
                        description="""Get complete history of a single page.

Returns all versions with:
- Timestamps
- Sources (wayback, commoncrawl, memento)
- Content changes between versions

Track how a specific page evolved.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "Target URL"},
                                "max_versions": {"type": "integer", "default": 50, "description": "Max versions to retrieve"},
                            },
                            "required": ["url"]
                        }
                    ),
                    Tool(
                        name="backdrill_find_content_change",
                        description="""Find when specific content appeared or disappeared from a domain.

Searches through archived versions to find:
- When text first appeared ('appeared')
- When text was removed ('disappeared')

Essential for tracking when information changed.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"},
                                "search_text": {"type": "string", "description": "Text to search for"},
                                "change_type": {
                                    "type": "string",
                                    "enum": ["appeared", "disappeared"],
                                    "default": "appeared",
                                    "description": "Type of change to find"
                                },
                                "max_pages": {"type": "integer", "default": 100, "description": "Max pages to check"},
                            },
                            "required": ["domain", "search_text"]
                        }
                    ),
                    Tool(
                        name="backdrill_domain_snapshot",
                        description="""Get a snapshot of what a domain looked like at a specific date.

Returns URLs and structure as it appeared at that time.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"},
                                "target_date": {"type": "string", "description": "Date (YYYY-MM-DD)"},
                            },
                            "required": ["domain", "target_date"]
                        }
                    ),
                ])

            # =================================================================
            # C3 ENTITY QUERY TOOLS (Pre-indexed CommonCrawl)
            # =================================================================
            if C3_AVAILABLE:
                tools.extend([
                    Tool(
                        name="backdrill_c3_orgs",
                        description="""Search WDC organization entities (9.6M docs, 2023).

Pre-indexed organization data from Web Data Commons CommonCrawl extraction.
Search by company name, legal name, or description.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query (company name, etc.)"},
                                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="backdrill_c3_persons",
                        description="""Search WDC person entities (6.8M docs, 2023).

Pre-indexed person data from Web Data Commons CommonCrawl extraction.
Search by name, job title, or description.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query (person name)"},
                                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="backdrill_c3_webgraph",
                        description="""Search CC web graph for domain edges (421M edges, 2024).

Find backlinks (who links TO this domain) or outlinks (who this domain links TO).
Essential for link analysis and domain relationships.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string", "description": "Target domain"},
                                "direction": {
                                    "type": "string",
                                    "enum": ["inbound", "outbound", "both"],
                                    "default": "both",
                                    "description": "Edge direction"
                                },
                                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            },
                            "required": ["domain"]
                        }
                    ),
                    Tool(
                        name="backdrill_c3_domains",
                        description="""Search unified domains index (180M domains, 2020-2024).

Multi-year aggregated domain data.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Domain name or pattern"},
                                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="backdrill_c3_pdfs",
                        description="""Search CC PDF collection (67K+ PDFs, 2025).

Find PDF documents indexed from CommonCrawl.
Filter by jurisdiction for country-specific documents.""",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query (title, content)"},
                                "jurisdiction": {"type": "string", "description": "Optional 2-letter country code (e.g., 'DE', 'UK')"},
                                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="backdrill_c3_indices",
                        description="""List all available C3 indices with metadata.

Shows index names, document counts, sizes, and data years.""",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                ])

            # Always available: status tool
            tools.append(
                Tool(
                    name="backdrill_status",
                    description="Get BACKDRILL system status and available components.",
                    inputSchema={"type": "object", "properties": {}}
                )
            )

            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                # =============================================================
                # URL MAPPING TOOLS
                # =============================================================
                if name == "backdrill_map_domain":
                    mapper = await self._ensure_mapper()
                    if not mapper:
                        return [TextContent(type="text", text=json.dumps({"error": "BackdrillMapper not available"}))]

                    domain = arguments["domain"]
                    domain_map = await mapper.map_domain(
                        domain,
                        start_date=arguments.get("start_date"),
                        end_date=arguments.get("end_date"),
                        mime_filter=arguments.get("mime_filter"),
                        limit_per_source=arguments.get("limit_per_source", 1000),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "domain": domain_map.domain,
                        "total_urls": domain_map.total_urls,
                        "unique_urls": domain_map.unique_urls,
                        "by_source": domain_map.by_source,
                        "by_year": domain_map.by_year,
                        "earliest": domain_map.earliest,
                        "latest": domain_map.latest,
                        "duration_ms": domain_map.duration_ms,
                        "sample_urls": [{"url": u.url, "source": u.source, "timestamp": u.timestamp}
                                       for u in domain_map.urls[:50]],
                    }, indent=2))]

                elif name == "backdrill_url_count":
                    mapper = await self._ensure_mapper()
                    if not mapper:
                        return [TextContent(type="text", text=json.dumps({"error": "BackdrillMapper not available"}))]

                    domain = arguments["domain"]
                    counts = await mapper.get_url_count(domain)

                    return [TextContent(type="text", text=json.dumps({
                        "domain": domain,
                        "counts": counts
                    }, indent=2))]

                elif name == "backdrill_snapshots":
                    mapper = await self._ensure_mapper()
                    if not mapper:
                        return [TextContent(type="text", text=json.dumps({"error": "BackdrillMapper not available"}))]

                    url = arguments["url"]
                    limit = arguments.get("limit", 100)
                    snapshots = await mapper.get_snapshots(url, limit=limit)

                    return [TextContent(type="text", text=json.dumps({
                        "url": url,
                        "total": len(snapshots),
                        "snapshots": [{"url": s.url, "source": s.source, "timestamp": s.timestamp,
                                      "archive_url": s.archive_url} for s in snapshots]
                    }, indent=2))]

                # =============================================================
                # VERSION COMPARISON TOOLS
                # =============================================================
                elif name == "backdrill_domain_evolution":
                    differ = await self._ensure_differ()
                    if not differ:
                        return [TextContent(type="text", text=json.dumps({"error": "DomainDiffer not available"}))]

                    domain = arguments["domain"]
                    evolution = await differ.domain_evolution(
                        domain,
                        start_year=arguments.get("start_year"),
                        end_year=arguments.get("end_year"),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "domain": evolution.domain,
                        "total_unique_urls": evolution.total_unique_urls,
                        "earliest_snapshot": evolution.earliest,
                        "latest_snapshot": evolution.latest,
                        "periods": evolution.periods[:20],
                        "pages_added_count": len(evolution.pages_added),
                        "pages_removed_count": len(evolution.pages_removed),
                        "sample_pages_added": [{"url": p.url, "timestamp": p.timestamp} for p in evolution.pages_added[:20]],
                        "sample_pages_removed": [{"url": p.url, "timestamp": p.timestamp} for p in evolution.pages_removed[:20]],
                    }, indent=2))]

                elif name == "backdrill_compare_periods":
                    differ = await self._ensure_differ()
                    if not differ:
                        return [TextContent(type="text", text=json.dumps({"error": "DomainDiffer not available"}))]

                    domain = arguments["domain"]
                    comparison = await differ.compare_periods(
                        domain,
                        period1=arguments["period1"],
                        period2=arguments["period2"],
                        fetch_content=arguments.get("fetch_content", False),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "domain": comparison.domain,
                        "period1": comparison.period1,
                        "period2": comparison.period2,
                        "urls_in_period1": len(comparison.urls_period1),
                        "urls_in_period2": len(comparison.urls_period2),
                        "urls_added": len(comparison.urls_added),
                        "urls_removed": len(comparison.urls_removed),
                        "urls_common": len(comparison.urls_common),
                        "sample_added": list(comparison.urls_added)[:30],
                        "sample_removed": list(comparison.urls_removed)[:30],
                        "content_changes": [{"url": c.url, "change_type": c.change_type, "similarity": c.similarity}
                                           for c in comparison.content_changed[:20]],
                    }, indent=2))]

                elif name == "backdrill_page_history":
                    differ = await self._ensure_differ()
                    if not differ:
                        return [TextContent(type="text", text=json.dumps({"error": "DomainDiffer not available"}))]

                    url = arguments["url"]
                    history = await differ.page_history(
                        url,
                        max_versions=arguments.get("max_versions", 50),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "url": history.url,
                        "total_versions": history.total_versions,
                        "unique_versions": history.unique_versions,
                        "first_seen": history.first_seen,
                        "last_seen": history.last_seen,
                        "versions": [{"timestamp": v.timestamp, "source": v.source, "archive_url": v.archive_url}
                                    for v in history.versions[:30]],
                        "changes_detected": len(history.changes),
                    }, indent=2))]

                elif name == "backdrill_find_content_change":
                    differ = await self._ensure_differ()
                    if not differ:
                        return [TextContent(type="text", text=json.dumps({"error": "DomainDiffer not available"}))]

                    domain = arguments["domain"]
                    appearance = await differ.find_content_change(
                        domain,
                        search_text=arguments["search_text"],
                        change_type=arguments.get("change_type", "appeared"),
                        max_pages=arguments.get("max_pages", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "search_text": appearance.search_text,
                        "domain": appearance.domain,
                        "change_type": appearance.change_type,
                        "found": appearance.found,
                        "url": appearance.url,
                        "timestamp": appearance.timestamp,
                        "surrounding_text": appearance.surrounding_text[:500] if appearance.surrounding_text else None,
                    }, indent=2))]

                elif name == "backdrill_domain_snapshot":
                    differ = await self._ensure_differ()
                    if not differ:
                        return [TextContent(type="text", text=json.dumps({"error": "DomainDiffer not available"}))]

                    domain = arguments["domain"]
                    snapshot = await differ.get_domain_snapshot(
                        domain,
                        target_date=arguments["target_date"],
                    )

                    return [TextContent(type="text", text=json.dumps(snapshot, indent=2))]

                # =============================================================
                # C3 ENTITY QUERY TOOLS
                # =============================================================
                elif name == "backdrill_c3_orgs":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    results = await c3.search_wdc_orgs(
                        arguments["query"],
                        limit=arguments.get("limit", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "query": arguments["query"],
                        "total": len(results),
                        "index_year": 2023,
                        "results": results[:50],
                    }, indent=2))]

                elif name == "backdrill_c3_persons":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    results = await c3.search_wdc_persons(
                        arguments["query"],
                        limit=arguments.get("limit", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "query": arguments["query"],
                        "total": len(results),
                        "index_year": 2023,
                        "results": results[:50],
                    }, indent=2))]

                elif name == "backdrill_c3_webgraph":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    results = await c3.search_webgraph(
                        arguments["domain"],
                        direction=arguments.get("direction", "both"),
                        limit=arguments.get("limit", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "domain": arguments["domain"],
                        "direction": arguments.get("direction", "both"),
                        "total": len(results),
                        "index_year": 2024,
                        "edges": results[:50],
                    }, indent=2))]

                elif name == "backdrill_c3_domains":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    results = await c3.search_domains(
                        arguments["query"],
                        limit=arguments.get("limit", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "query": arguments["query"],
                        "total": len(results),
                        "index_years": "2020-2024",
                        "results": results[:50],
                    }, indent=2))]

                elif name == "backdrill_c3_pdfs":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    results = await c3.search_cc_pdfs(
                        arguments["query"],
                        jurisdiction=arguments.get("jurisdiction"),
                        limit=arguments.get("limit", 100),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "query": arguments["query"],
                        "jurisdiction": arguments.get("jurisdiction"),
                        "total": len(results),
                        "index_year": 2025,
                        "results": results[:50],
                    }, indent=2))]

                elif name == "backdrill_c3_indices":
                    c3 = await self._ensure_c3()
                    if not c3:
                        return [TextContent(type="text", text=json.dumps({"error": "C3Bridge not available"}))]

                    indices = c3.list_indices()

                    return [TextContent(type="text", text=json.dumps({
                        "indices": indices,
                    }, indent=2))]

                # =============================================================
                # STATUS TOOL
                # =============================================================
                elif name == "backdrill_status":
                    return [TextContent(type="text", text=json.dumps({
                        "status": "operational",
                        "components": {
                            "mapper": MAPPER_AVAILABLE,
                            "differ": DIFFER_AVAILABLE,
                            "c3_bridge": C3_AVAILABLE,
                        },
                        "mapper_sources": ["wayback", "commoncrawl", "memento"] if MAPPER_AVAILABLE else [],
                        "c3_indices": list(C3Bridge.INDEX_METADATA.keys()) if C3_AVAILABLE else [],
                    }, indent=2))]

                else:
                    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

            except Exception as e:
                logger.error(f"Tool {name} error: {e}")
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }))]

    async def run(self):
        """Run the MCP server."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Entry point."""
    server = BackdrillMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
