#!/usr/bin/env python3
"""
LINKLATER Syntax-Driven MCP Server

SINGLE TOOL that routes ALL operations via query syntax.

Instead of multiple discrete tools like:
  - get_backlinks(domain="soax.com")
  - extract_entities(domain="soax.com")

Use ONE tool with query syntax:
  - linklater_query(query="?bl !soax.com")     → backlinks (domains)
  - linklater_query(query="bl? !soax.com")     → backlinks (pages)
  - linklater_query(query="ent?:2024! !soax.com") → entities from 2024 archives

QUERY SYNTAX REFERENCE:
=======================

OPERATORS (combine multiple with spaces):
  ?bl      - backlinks (referring domains)
  bl?      - backlinks (referring pages)
  ?ol      - outlinks (linked domains)
  ol?      - outlinks (linked pages)
  p?       - persons
  c?       - companies
  t?       - telephones
  e?       - emails
  a?       - addresses
  ent?     - all entities

FILETYPE DISCOVERY (find files on a domain):
  pdf!     - PDF files only
  doc!     - ALL documents (pdf, doc, docx, xls, xlsx, ppt, pptx, etc.)
  word!    - Word documents only (doc, docx, odt, rtf)
  xls!     - Excel spreadsheets (xls, xlsx, ods, csv)
  ppt!     - PowerPoint presentations (ppt, pptx, odp)
  file!    - All document types (alias for doc!)

TARGET (! position determines granularity):
  !domain.com     - domain level
  url.com/page!   - page level
  !xyz.onion      - .onion URL (auto-detects Tor context)

TOR/ONION CONTEXT MODIFIERS (AFTER target):
  :tor            - search via Tor search engines + local ES index
  :onion          - alias for :tor

  The :tor modifier searches both:
  1. Local Elasticsearch 'onion-pages' index (if available)
  2. External Tor engines (Ahmia, Tor66, GDark, Candle, Phobos, etc.)

  Entity filtering with :tor extracts entities using GLiNER.

HISTORICAL MODIFIERS (before target):
  2024! !domain.com         - single year
  2020-2024! !domain.com    - year range
  <-2012! !domain.com       - from now back to 2012

EXAMPLES:
  "?bl:!soax.com"               → referring domains to soax.com (~100ms)
  "bl?:!soax.com"               → referring pages to soax.com (~30-60s)
  "ent?:!soax.com"              → all entities from current pages
  "ent?:2024! !soax.com"        → entities from 2024 archives
  "p? c?:2022-2024! !soax.com"  → persons + companies from 2022-2024
  "?ol:!example.com"            → domains that example.com links to

  # Filetype discovery examples:
  "pdf! :!sebgroup.com"         → find all PDFs on sebgroup.com
  "doc! :!company.com"          → find ALL documents (pdf, docx, xlsx, pptx, etc.)
  "word! :!domain.com"          → find Word documents only (doc, docx)
  "xls! :!bank.com"             → find Excel spreadsheets (xls, xlsx, csv)

  # Tor/Onion examples:
  "bitcoin :tor"              → keyword search on Tor engines + ES
  "marketplace :onion"        → same (alias)
  "e?:!search :tor"           → Tor pages with emails matching "search"
  "c?:!bank :tor"             → Tor pages about "bank" with companies
  "ent?:!xyz.onion"           → extract all entities from .onion URL
  "ol?:!xyz.onion"            → outlinks from .onion URL

ARCHITECTURE:
  MCP Client → linklater_query(query) → QueryExecutor.execute_async()
                                           ↓
                                    ┌──────┴──────┐
                                    │ query_parser │
                                    └──────┬──────┘
                                           ↓
              ┌────────────┬────────────┬────────────┐
              │ backlinks  │ extraction │ scraping   │
              │ linkgraph/ │ extraction/│ scraping/  │
              └────────────┴────────────┴────────────┘
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add module paths
LINKLATER_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = LINKLATER_DIR.parent
BACKEND_DIR = MODULES_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(MODULES_DIR))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Import QueryExecutor for routing
try:
    from modules.query_executor import QueryExecutor, execute_async
    from modules.query_parser import parse_query
    QUERY_EXECUTOR_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: QueryExecutor not available: {e}", file=sys.stderr)
    QUERY_EXECUTOR_AVAILABLE = False

# Initialize MCP server
app = Server("linklater-syntax")


def format_results(query: str, results: Dict[str, Any]) -> str:
    """Format query results for human-readable output."""
    lines = [
        "=" * 80,
        f"LINKLATER QUERY: {query}",
        "=" * 80,
        "",
        f"Target: {results.get('target', 'N/A')} ({results.get('target_type', 'N/A')})",
        f"Historical: {results.get('historical', 'current')}",
        f"Method: {results.get('method', 'N/A')}",
        "",
    ]

    # Show counts summary
    counts = results.get("counts", {})
    if counts:
        lines.append("COUNTS:")
        for key, value in counts.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    # Show snapshots if historical
    snapshots = results.get("snapshots", [])
    if snapshots:
        lines.append(f"SNAPSHOTS ANALYZED: {len(snapshots)}")
        for s in snapshots[:5]:
            ts = s.get("timestamp", "")
            url = s.get("url", "")
            source = s.get("source", "")
            lines.append(f"  [{ts[:8]}] {url[:60]}... ({source})")
        if len(snapshots) > 5:
            lines.append(f"  ... and {len(snapshots) - 5} more")
        lines.append("")

    # Show results by type
    result_data = results.get("results", {})

    # Backlinks
    if "backlinks" in result_data:
        backlinks = result_data["backlinks"]
        lines.append(f"BACKLINKS ({len(backlinks)} found):")
        lines.append("-" * 40)
        for bl in backlinks[:20]:
            if isinstance(bl, dict):
                domain = bl.get("domain", bl.get("url", ""))
                count = bl.get("count", bl.get("found_in_snapshots", ""))
                count_str = f" (x{count})" if count else ""
                lines.append(f"  → {domain}{count_str}")
            else:
                lines.append(f"  → {bl}")
        if len(backlinks) > 20:
            lines.append(f"  ... and {len(backlinks) - 20} more")
        lines.append("")

    # Outlinks
    if "outlinks" in result_data:
        outlinks = result_data["outlinks"]
        lines.append(f"OUTLINKS ({len(outlinks)} found):")
        lines.append("-" * 40)
        for ol in outlinks[:20]:
            if isinstance(ol, dict):
                domain = ol.get("domain", ol.get("url", ""))
                count = ol.get("url_count", ol.get("link_count", ""))
                count_str = f" ({count} links)" if count else ""
                lines.append(f"  → {domain}{count_str}")
            else:
                lines.append(f"  → {ol}")
        if len(outlinks) > 20:
            lines.append(f"  ... and {len(outlinks) - 20} more")
        lines.append("")

    # Onion URLs (from Tor discovery)
    if "onion_urls" in result_data:
        onion_urls = result_data["onion_urls"]
        lines.append(f"ONION URLS ({len(onion_urls)} found):")
        lines.append("-" * 40)
        for url_info in onion_urls[:30]:
            if isinstance(url_info, dict):
                url = url_info.get("url", "")
                title = url_info.get("title", "")[:50]
                snippet = url_info.get("snippet", "")[:60]
                lines.append(f"  → {url}")
                if title:
                    lines.append(f"    Title: {title}")
                if snippet:
                    lines.append(f"    Snippet: {snippet}...")
            else:
                lines.append(f"  → {url_info}")
        if len(onion_urls) > 30:
            lines.append(f"  ... and {len(onion_urls) - 30} more")
        lines.append("")

    # Entities
    if "entities" in result_data:
        entities = result_data["entities"]
        lines.append("ENTITIES:")
        lines.append("-" * 40)

        for entity_type, ent_list in entities.items():
            if not ent_list:
                continue

            lines.append(f"\n  {entity_type.upper()} ({len(ent_list)} found):")

            for ent in ent_list[:15]:
                if isinstance(ent, dict):
                    value = ent.get("value", "")
                    found_in = ent.get("found_in_snapshots", 1)
                    confidence = ent.get("confidence", "")

                    # Build info string
                    info_parts = []
                    if found_in and found_in > 1:
                        info_parts.append(f"x{found_in}")
                    if confidence and isinstance(confidence, (int, float)):
                        info_parts.append(f"{confidence:.0%}")

                    info_str = f" ({', '.join(info_parts)})" if info_parts else ""
                    lines.append(f"    • {value}{info_str}")

                    # Show archive URL if available (for historical queries)
                    archive_urls = ent.get("archive_urls", [])
                    if archive_urls:
                        lines.append(f"      └─ {archive_urls[0]}")

                    # Show snippet if available
                    snippets = ent.get("snippets", [])
                    if snippets and snippets[0].get("text"):
                        snippet_text = snippets[0]["text"][:80]
                        lines.append(f"      └─ \"{snippet_text}...\"")
                else:
                    lines.append(f"    • {ent}")

            if len(ent_list) > 15:
                lines.append(f"    ... and {len(ent_list) - 15} more")

    # Error handling
    if "error" in results:
        lines.append("")
        lines.append(f"ERROR: {results['error']}")

    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools - just ONE unified tool"""
    return [
        Tool(
            name="linklater_query",
            description="""Execute ANY LINKLATER operation via query syntax.

QUERY SYNTAX:
  OPERATOR(s) : TARGET

OPERATORS (combine multiple):
  ?bl      - backlinks (referring DOMAINS) - FAST ~100ms
  bl?      - backlinks (referring PAGES) - slower ~30-60s
  ?ol      - outlinks (linked domains)
  ol?      - outlinks (linked pages)
  p?       - persons
  c?       - companies
  t?       - telephones/phones
  e?       - emails
  a?       - addresses
  ent?     - ALL entities
  tor?     - Tor/dark web discovery (searches 9+ onion engines)
  onion?   - alias for Tor discovery
  pdf!     - find PDF files on domain
  doc!     - find ALL documents (pdf, docx, xlsx, pptx, etc.)
  word!    - find Word documents only (doc, docx)
  xls!     - find Excel spreadsheets (xls, xlsx, csv)
  ppt!     - find PowerPoint presentations
  file!    - find all document types (alias for doc!)

TARGET (! = granularity):
  !domain.com     - domain level
  url.com/page!   - page level

HISTORICAL (archive search - NOT for Tor):
  2024! !domain.com         - single year
  2020-2024! !domain.com    - year range
  <-2015! !domain.com       - back to 2015

EXAMPLES:
  "?bl:!soax.com"               → Fast backlinks (domains only)
  "bl?:!soax.com"               → Rich backlinks (with pages)
  "ent?:!soax.com"              → All entities (current)
  "ent?:2024! !soax.com"        → Historical entities from 2024
  "p? c?:2022-2024! !soax.com"  → Persons + companies 2022-2024
  "?ol:!example.com"            → Outlink domains
  "tor?:!drugs"                 → Search dark web for "drugs"
  "tor? ent?:!marketplace"      → Dark web + entity extraction""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "LINKLATER query syntax (e.g., '?bl:!soax.com', 'ent?:2024! !domain.com')"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Output format (default: text for human-readable, json for raw data)",
                        "default": "text"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="linklater_syntax_help",
            description="Show LINKLATER query syntax reference",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute LINKLATER tool"""

    if name == "linklater_syntax_help":
        help_text = """
LINKLATER QUERY SYNTAX REFERENCE
================================

OPERATORS (combine with spaces before :)
----------------------------------------
  ?bl      Backlinks - referring DOMAINS (fast, ~100ms)
  bl?      Backlinks - referring PAGES (slower, ~30-60s)
  ?ol      Outlinks - linked DOMAINS
  ol?      Outlinks - linked PAGES

  p?       Persons (names)
  c?       Companies (organizations)
  t?       Telephones/phones
  e?       Emails
  a?       Addresses
  ent?     ALL entity types

  tor?     Tor/dark web discovery (searches 9+ onion engines)
  onion?   Alias for Tor discovery

FILETYPE DISCOVERY (find files on domains):
  pdf!     PDF files only
  doc!     ALL documents (pdf, docx, xlsx, pptx, etc.)
  word!    Word documents only (doc, docx, odt, rtf)
  xls!     Excel spreadsheets (xls, xlsx, ods, csv)
  ppt!     PowerPoint presentations (ppt, pptx, odp)
  file!    All document types (alias for doc!)

TARGET SYNTAX (after :)
-----------------------
  !domain.com       Domain-level (everything on domain)
  url.com/page!     Page-level (specific page only)
  !keyword          For Tor queries, search term

HISTORICAL MODIFIERS (before target) - NOT for Tor
--------------------------------------------------
  2024! !domain.com          Single year archives
  2020-2024! !domain.com     Year range
  <-2015! !domain.com        From now back to 2015

EXAMPLES
--------
Fast backlinks (domains only):
  ?bl:!soax.com

Rich backlinks (with source pages):
  bl?:!soax.com

Current entities from domain:
  ent?:!soax.com

Historical entities from 2024:
  ent?:2024! !soax.com

Persons + companies from 2022-2024:
  p? c?:2022-2024! !soax.com

Outlink domains:
  ?ol:!example.com

Backlinks + entities combined:
  bl? ent?:!domain.com

DARK WEB / TOR EXAMPLES
-----------------------
Search dark web for keyword:
  tor?:!marketplace

Dark web search + entity extraction:
  tor? ent?:!drugs

Dark web search + specific entities:
  tor? p? c?:!fraud

TIPS
----
• Use ?bl (domain-level) for fast results (~100ms)
• Use bl? (page-level) when you need source URLs (~30-60s)
• Historical queries scan Wayback + Common Crawl archives
• Entity extraction uses Gemini + GPT-5-nano in parallel
• Results include archive URLs for provenance
• Tor queries search: Ahmia, Tor66, GDark, Candle, Phobos, etc.
• Combine tor? with entity operators for extraction from results
"""
        return [TextContent(type="text", text=help_text)]

    elif name == "linklater_query":
        query = arguments.get("query", "").strip()
        output_format = arguments.get("format", "text")

        if not query:
            return [TextContent(type="text", text="ERROR: Query string required. Try: ?bl:!soax.com")]

        if not QUERY_EXECUTOR_AVAILABLE:
            return [TextContent(type="text", text="ERROR: QueryExecutor not available. Check module imports.")]

        # Validate query syntax
        parsed = parse_query(query)
        if not parsed:
            return [TextContent(type="text", text=f"""ERROR: Invalid query syntax: {query}

Valid format: OPERATOR(s):TARGET

Examples:
  ?bl:!soax.com           (backlinks - domains)
  bl?:!soax.com           (backlinks - pages)
  ent?:2024! !soax.com    (entities from 2024)
  p? c?:!domain.com       (persons + companies)

Use linklater_syntax_help for full reference.""")]

        try:
            # Execute query via QueryExecutor
            executor = QueryExecutor()
            results = await executor.execute_async(query)

            # Clean up
            await executor.historical_fetcher.close()

            # Format output
            if output_format == "json":
                return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]
            else:
                formatted = format_results(query, results)
                return [TextContent(type="text", text=formatted)]

        except Exception as e:
            import traceback
            return [TextContent(
                type="text",
                text=f"ERROR executing query: {str(e)}\n\n{traceback.format_exc()}"
            )]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
