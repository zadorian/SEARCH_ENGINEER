#!/usr/bin/env python3
"""
ALLDOM MCP Server - Unified Domain Intelligence

Exposes the AllDom orchestrator to AI agents via MCP.
Allows running any domain operator (bl?, whois:, etc.) or full scans.

Usage:
  python3 ALLDOM/mcp_server.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("alldom-mcp")

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

try:
    from ALLDOM.alldom import AllDom, AllDomResult
except ImportError:
    logger.error("Failed to import AllDom. Ensure ALLDOM module is in python path.")
    sys.exit(1)


class AllDomMCP:
    """ALLDOM MCP Server."""

    def __init__(self):
        self.server = Server("alldom")
        self.alldom = AllDom()
        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="alldom_execute",
                    description="""Execute a single domain operator against a target.

Supported Operators:
- Link Analysis: bl? (backlinks), ol? (outlinks), bl! (backlink domains)
- Archive: <-! (fetch), wb: (Wayback), cc: (CommonCrawl)
- Discovery: map! (discover), sub! (subdomains), sitemap:
- WHOIS/DNS: whois:, dns:
- Macros: age!, ga!, tech!
- Entities: @ent?, @p? (persons), @c? (companies), @e? (emails)
- Metadata: meta?, exif?, docs?, dates?

Example:
  alldom_execute(operator="bl?", target="example.com")
  alldom_execute(operator="whois:", target="example.com")""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "operator": {
                                "type": "string",
                                "description": "Operator string (e.g., 'bl?', 'whois:', 'sub!')"
                            },
                            "target": {
                                "type": "string",
                                "description": "Domain or URL to analyze"
                            },
                            "params": {
                                "type": "object",
                                "description": "Optional parameters for the operator",
                                "default": {}
                            }
                        },
                        "required": ["operator", "target"]
                    }
                ),
                Tool(
                    name="alldom_scan",
                    description="""Run a comprehensive domain scan using multiple operators.

Depth Levels:
- fast: whois, age, map (basic checks)
- full: whois, age, ga, tech, map, sub, sitemap, backlinks, outlinks
- custom: provide specific list of operators""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "Target domain"
                            },
                            "depth": {
                                "type": "string",
                                "enum": ["fast", "full"],
                                "default": "fast",
                                "description": "Scan depth"
                            },
                            "operators": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Custom list of operators to run (overrides depth)"
                            }
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="alldom_list_operators",
                    description="List all available AllDom operators and their descriptions.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="alldom_status",
                    description="Check status of AllDom bridges and modules.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                if name == "alldom_status":
                    # Initialize to check bridges
                    await self.alldom._ensure_bridges()
                    return [TextContent(type="text", text=json.dumps({
                        "status": "operational",
                        "loaded_bridges": list(self.alldom._bridges.keys())
                    }, indent=2))]

                elif name == "alldom_list_operators":
                    ops = self.alldom.list_operators()
                    return [TextContent(type="text", text=json.dumps({
                        "count": len(ops),
                        "operators": ops
                    }, indent=2))]

                elif name == "alldom_execute":
                    operator = arguments["operator"]
                    target = arguments["target"]
                    params = arguments.get("params", {})
                    
                    result = await self.alldom.execute(operator, target, **params)
                    
                    return [TextContent(type="text", text=json.dumps({
                        "operator": result.operator,
                        "target": result.target,
                        "success": result.success,
                        "source": result.source,
                        "error": result.error,
                        "data": result.data,
                        "metadata": result.metadata
                    }, indent=2, default=str))]

                elif name == "alldom_scan":
                    domain = arguments["domain"]
                    depth = arguments.get("depth", "fast")
                    operators = arguments.get("operators")
                    
                    results = await self.alldom.scan(domain, depth=depth, operators=operators)
                    
                    # Convert Dataclasses to dicts for JSON serialization
                    serializable_results = {}
                    for op, res in results.items():
                        serializable_results[op] = {
                            "success": res.success,
                            "error": res.error,
                            "source": res.source,
                            "data_preview": str(res.data)[:100] if res.data else None
                        }
                        
                        # Include full data if it's small or structured, otherwise truncate/summarize
                        # For now, just dumping it with default=str handles most things
                        serializable_results[op]["data"] = res.data

                    return [TextContent(type="text", text=json.dumps({
                        "domain": domain,
                        "depth": depth,
                        "operators_run": list(results.keys()),
                        "results": serializable_results
                    }, indent=2, default=str))]

                else:
                    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

            except Exception as e:
                logger.error(f"Tool {name} error: {e}")
                return [TextContent(type="text", text=json.dumps({
                    "error": str(e),
                    "type": type(e).__name__
                }))]

    async def run(self):
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    server = AllDomMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
