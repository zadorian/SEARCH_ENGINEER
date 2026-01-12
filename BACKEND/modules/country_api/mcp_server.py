#!/usr/bin/env python3
"""
Country API MCP Server

Unified interface for all country-specific registry APIs/CLIs.
Acts as a router to delegating execution to specific country modules.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("country-api-mcp")

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

from .router import CountryRouter

class CountryApiMCP:
    def __init__(self):
        self.server = Server("country-api")
        self.router = CountryRouter()
        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="execute_country_search",
                    description="Execute a search against a specific country's official registry API/CLI.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (can include prefix e.g. 'cde: Siemens')"
                            },
                            "jurisdiction": {
                                "type": "string",
                                "description": "ISO Country Code (e.g. DE, FR, NL, UK)"
                            }
                        },
                        "required": ["query", "jurisdiction"]
                    }
                ),
                Tool(
                    name="search_company",
                    description="Search for a company in a specific jurisdiction's official registry.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Company Name"},
                            "jurisdiction": {"type": "string", "description": "ISO Country Code"}
                        },
                        "required": ["name", "jurisdiction"]
                    }
                ),
                Tool(
                    name="search_person",
                    description="Search for a person in a specific jurisdiction's official registry.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Person Name"},
                            "jurisdiction": {"type": "string", "description": "ISO Country Code"}
                        },
                        "required": ["name", "jurisdiction"]
                    }
                ),
                Tool(
                    name="list_supported_countries",
                    description="List countries that have dedicated API integrations.",
                    inputSchema={"type": "object", "properties": {}}
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                if name == "execute_country_search":
                    result = await self.router.execute(arguments["query"], arguments["jurisdiction"])
                    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
                
                elif name == "search_company":
                    result = await self.router.search_company(arguments["name"], arguments["jurisdiction"])
                    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
                
                elif name == "search_person":
                    result = await self.router.search_person(arguments["name"], arguments["jurisdiction"])
                    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
                
                elif name == "list_supported_countries":
                    return [TextContent(type="text", text=json.dumps(list(self.router.registry.keys()), indent=2))]
                
                else:
                    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

            except Exception as e:
                logger.error(f"Tool {name} error: {e}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def run(self):
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())

def main():
    server = CountryApiMCP()
    asyncio.run(server.run())

if __name__ == "__main__":
    main()