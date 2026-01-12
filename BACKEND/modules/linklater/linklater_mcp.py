#!/usr/bin/env python3
"""
LINKLATER MCP Server - Operator Syntax
=======================================

Single-tool MCP server that accepts LINKLATER operator syntax.

SYNTAX:
  SUBJECT : LOCATION

  `:` separates SUBJECT from LOCATION
  `!` determines scope: !domain = full domain, page! = specific page
  `?` position: before = domains only, after = pages with details

OPERATORS:
  ?bl :!domain.com     Referring domains
  bl? :!domain.com     Referring pages with anchor text
  ?ol :!domain.com     Outlinked domains
  ol? :!domain.com     Outlinked pages

  p? :!domain.com      Persons
  c? :!domain.com      Companies
  e? :!domain.com      Emails
  t? :!domain.com      Phones
  ent? :!domain.com    All entities

  whois?domain.com     WHOIS registration data

  keyword :<-domain    Search archives backwards
  2016! :!domain       Snapshots from 2016
  2013-2016! :!domain  Snapshots from range

  !domain.com          Scrape full domain
  page.com/path!       Scrape specific page

USAGE:
  Configure in claude_desktop_config.json:

  {
    "mcpServers": {
      "linklater": {
        "command": "python3",
        "args": ["/path/to/linklater_mcp.py"]
      }
    }
  }
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add module paths
LINKLATER_DIR = Path(__file__).resolve().parent
BACKEND_DIR = LINKLATER_DIR.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Import CLI components
try:
    from modules.LINKLATER.linklater_cli import OperatorParser, LinkLaterCLI
    CLI_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: CLI components not available: {e}", file=sys.stderr)
    CLI_AVAILABLE = False

# Initialize MCP server
app = Server("linklater")


SYNTAX_HELP = """
LINKLATER OPERATOR SYNTAX
=========================

The `:` separates SUBJECT from LOCATION
The `!` determines scope: before=domain, after=page
The `?` position: before=domains, after=pages with details

LINK ANALYSIS
-------------
?bl :!domain.com     Referring domains (who links here)
bl? :!domain.com     Referring pages with anchor text
?ol :!domain.com     Outlinked domains (who they link to)
ol? :!domain.com     Outlinked pages with anchor text

DOMAIN OPERATIONS
-----------------
!domain.com          Scrape full domain
?domain.com          Domain map (discover all URLs)
whois? :domain.com   WHOIS registration data
?age :domain.com     Domain age (WHOIS registration)
age? :url.com/page   Page age (first seen in archives)
meta? :url.com/file  EXIF/metadata extraction (exiftool)

ENTITY EXTRACTION
-----------------
p? :!domain.com      Persons
c? :!domain.com      Companies
e? :!domain.com      Emails
t? :!domain.com      Phones
a? :!domain.com      Addresses
u? :!domain.com      Usernames
ent? :!domain.com    All entities

ARCHIVE OPERATIONS
------------------
keyword :<-!domain       Search full domain archives backwards
keyword :<-domain/path!  Search specific page archives backwards
keyword :->!domain       Search archives forwards
2016! :!domain           Snapshots from 2016
2013-2016! :!domain      Snapshots from year range

NOTE: Archive keyword search REQUIRES ! scope indicator.

TRACKING CODE MINING
--------------------
ga? :!domain.com         Google Analytics codes (all archives)
ga? :2020! !domain.com   GA codes from 2020 only
ga? :2018-2022! !domain  GA codes from year range

(Finds: UA-XXXXXX-X, G-XXXXXXX, GTM-XXXXXX, AW-XXXXXX)

PAGE OPERATIONS
---------------
page.com/path!       Scrape specific page
:page.com/path       Scrape page + extract entities

EXAMPLES
--------
linklater("?bl :!sebgroup.com")         # Backlink domains
linklater("bl? :!example.com")          # Backlinks with anchors
linklater("whois? :example.com")        # WHOIS data
linklater("p? :!ksantex.com")           # Extract persons
linklater("ent? :!company.com")         # All entities
linklater("libya :<-!sebgroup.com")     # Archive search full domain
linklater("2020! :!example.com")        # 2020 snapshots
"""


def format_output(result: Dict[str, Any]) -> str:
    """Format result for human-readable output."""
    lines = [
        "=" * 70,
        f"LINKLATER: {result.get('operation', 'unknown')}",
        "=" * 70,
        ""
    ]

    if not result.get('success'):
        lines.append(f"ERROR: {result.get('error')}")
        return '\n'.join(lines)

    res = result.get('result', {})

    # Domain/URL info
    if 'domain' in res:
        lines.append(f"Domain: {res['domain']}")
    if 'url' in res:
        lines.append(f"URL: {res['url']}")
    if 'count' in res:
        lines.append(f"Count: {res['count']}")
    if 'counts' in res:
        lines.append(f"Counts: {res['counts']}")
    lines.append("")

    # Backlinks
    if 'backlinks' in res and res['backlinks']:
        lines.append("BACKLINKS:")
        lines.append("-" * 40)
        for item in res['backlinks'][:20]:
            if isinstance(item, dict):
                source = item.get('source', '')
                anchor = item.get('anchor_text', '')
                anchor_str = f"  [{anchor[:50]}]" if anchor else ""
                lines.append(f"  {source}{anchor_str}")
            else:
                lines.append(f"  {item}")
        if len(res['backlinks']) > 20:
            lines.append(f"  ... +{len(res['backlinks']) - 20} more")
        lines.append("")

    # Outlinks
    if 'outlinks' in res and res['outlinks']:
        lines.append("OUTLINKS:")
        lines.append("-" * 40)
        for item in res['outlinks'][:20]:
            if isinstance(item, dict):
                target = item.get('target', '')
                anchor = item.get('anchor_text', '')
                anchor_str = f"  [{anchor[:50]}]" if anchor else ""
                lines.append(f"  {target}{anchor_str}")
            else:
                lines.append(f"  {item}")
        if len(res['outlinks']) > 20:
            lines.append(f"  ... +{len(res['outlinks']) - 20} more")
        lines.append("")

    # Entities
    if 'entities' in res and res['entities']:
        lines.append("ENTITIES:")
        lines.append("-" * 40)
        for etype, items in res['entities'].items():
            if items:
                lines.append(f"  {etype}: {len(items)}")
                for item in items[:5]:
                    val = item.get('value', item) if isinstance(item, dict) else item
                    lines.append(f"    - {val}")
                if len(items) > 5:
                    lines.append(f"    ... +{len(items) - 5} more")
        lines.append("")

    # WHOIS
    if 'whois' in res and res['whois']:
        w = res['whois']
        lines.append("WHOIS:")
        lines.append("-" * 40)
        if w.get('registrar'):
            lines.append(f"  Registrar: {w['registrar']}")
        if w.get('created_date'):
            lines.append(f"  Created: {w['created_date']}")
        if w.get('expires_date'):
            lines.append(f"  Expires: {w['expires_date']}")
        if w.get('registrant_name'):
            lines.append(f"  Registrant: {w['registrant_name']}")
        if w.get('registrant_country'):
            lines.append(f"  Country: {w['registrant_country']}")
        lines.append("")

    # Archive results
    if 'results' in res and res['results']:
        lines.append(f"ARCHIVE RESULTS: {len(res['results'])}")
        lines.append("-" * 40)
        for item in res['results'][:10]:
            if isinstance(item, dict):
                ts = item.get('timestamp', '')[:8]
                url = item.get('url', '')[:60]
                lines.append(f"  [{ts}] {url}")
            else:
                lines.append(f"  {item}")
        if len(res['results']) > 10:
            lines.append(f"  ... +{len(res['results']) - 10} more")
        lines.append("")

    # Archive matches
    if 'matches' in res and res['matches']:
        lines.append(f"ARCHIVE MATCHES: {len(res['matches'])}")
        lines.append("-" * 40)
        for match in res['matches'][:10]:
            if isinstance(match, dict):
                ts = match.get('timestamp', '')[:8]
                snippet = match.get('snippet', '')[:60]
                lines.append(f"  [{ts}] ...{snippet}...")
            else:
                lines.append(f"  {match}")
        if len(res['matches']) > 10:
            lines.append(f"  ... +{len(res['matches']) - 10} more")
        lines.append("")

    # GA codes
    if 'ga_codes' in res and res['ga_codes']:
        lines.append(f"GOOGLE ANALYTICS CODES: {len(res['ga_codes'])}")
        lines.append("-" * 40)
        for ga in res['ga_codes'][:20]:
            code = ga.get('code', '')
            code_type = ga.get('type', '')
            first = ga.get('first_seen', '')[:8]
            last = ga.get('last_seen', '')[:8]
            count = ga.get('count', 0)
            lines.append(f"  {code} ({code_type})")
            lines.append(f"    First: {first}, Last: {last}, Found: {count}x")
        if len(res['ga_codes']) > 20:
            lines.append(f"  ... +{len(res['ga_codes']) - 20} more")
        lines.append("")

    # Age info
    if 'age_days' in res and res.get('age_days'):
        lines.append("AGE:")
        lines.append("-" * 40)
        if 'created_date' in res:
            lines.append(f"  Registered: {res.get('created_date', 'N/A')}")
        if 'first_seen' in res:
            lines.append(f"  First seen: {res.get('first_seen', 'N/A')}")
        lines.append(f"  Age: {res['age_days']} days ({res.get('age_years', 'N/A')} years)")
        if res.get('is_live') is not None:
            lines.append(f"  Status: {'LIVE' if res['is_live'] else 'DEAD'}")
        lines.append("")

    # Metadata/EXIF
    if 'investigation_fields' in res and res['investigation_fields']:
        lines.append("METADATA (Investigation Fields):")
        lines.append("-" * 40)
        for key, val in res['investigation_fields'].items():
            lines.append(f"  {key}: {val}")
        if res.get('has_gps'):
            lines.append("  ⚠️  GPS COORDINATES FOUND")
        if res.get('has_author'):
            lines.append("  ⚠️  AUTHOR/CREATOR INFO FOUND")
        lines.append("")

    lines.append("=" * 70)
    return '\n'.join(lines)


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="linklater",
            description="""Execute LINKLATER domain investigation via operator syntax.

SYNTAX: SUBJECT : LOCATION
  `:` separates subject from location
  `!` scope: before=domain, after=page
  `?` position: before=domains, after=pages

OPERATORS:
  ?bl :!domain    Backlink domains
  bl? :!domain    Backlink pages (with anchors)
  ?ol :!domain    Outlink domains
  ol? :!domain    Outlink pages
  p? :!domain     Persons
  c? :!domain     Companies
  ent? :!domain   All entities
  ga? :!domain    Google Analytics codes (historic)
  whois? :domain  WHOIS data
  ?age :domain    Domain age (WHOIS registration)
  age? :page      Page age (archive first-seen)
  meta? :url/file EXIF/metadata extraction
  keyword :<-!domain  Archive search (! required)
  2020! :!domain  Year snapshots
  !domain         Scrape domain

EXAMPLES:
  ?bl :!sebgroup.com
  bl? :!example.com
  whois? :example.com
  p? :!ksantex.com
  libya :<-!sebgroup.com
  ga? :!company.com
  ga? :2020! !company.com""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "LINKLATER operator query (e.g., '?bl :!domain.com')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 100)",
                        "default": 100
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json"],
                        "description": "Output format (default: text)",
                        "default": "text"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="linklater_help",
            description="Show LINKLATER operator syntax reference",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute LINKLATER tool."""

    if name == "linklater_help":
        return [TextContent(type="text", text=SYNTAX_HELP)]

    elif name == "linklater":
        query = arguments.get("query", "").strip()
        limit = arguments.get("limit", 100)
        output_format = arguments.get("format", "text")

        if not query:
            return [TextContent(type="text", text="ERROR: Query required. Example: ?bl :!domain.com")]

        if not CLI_AVAILABLE:
            return [TextContent(type="text", text="ERROR: CLI components not available. Check module imports.")]

        try:
            # Parse and execute
            operation, params = OperatorParser.parse(query)

            if operation == 'unknown':
                return [TextContent(
                    type="text",
                    text=f"ERROR: Unknown query syntax: {query}\n\nUse linklater_help for syntax reference."
                )]

            cli = LinkLaterCLI(limit=limit, output_format='json')
            result = await cli.execute(operation, params)

            # Format output
            if output_format == "json":
                return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
            else:
                return [TextContent(type="text", text=format_output(result))]

        except Exception as e:
            import traceback
            return [TextContent(
                type="text",
                text=f"ERROR: {str(e)}\n\n{traceback.format_exc()}"
            )]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    print("LINKLATER MCP Server starting...", file=sys.stderr)

    if not CLI_AVAILABLE:
        print("WARNING: CLI components not loaded. Some features may not work.", file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
