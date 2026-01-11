#!/usr/bin/env python3
"""
EYE-D MCP Server - OSINT Intelligence

Exposes OSINT search capabilities via MCP:
- Email breach & enrichment
- Phone number lookup
- Username discovery
- LinkedIn profile enrichment
- Domain WHOIS
- IP geolocation
- People search
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add EYE-D to path
EYED_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EYED_ROOT))
# NOTE: LINKLATER contains a local `mcp/` package which can shadow the real
# `mcp` SDK if added with high precedence. Keep it low-priority.
_linklater_root = EYED_ROOT.parent / "LINKLATER"
if _linklater_root.exists():
    sys.path.append(str(_linklater_root))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("eyed-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(EYED_ROOT.parent / "SASTRE" / ".env")
except ImportError:
    pass

# Import EYE-D searcher
try:
    from unified_osint import UnifiedSearcher
    UNIFIED_AVAILABLE = True
except ImportError as e:
    logger.warning(f"UnifiedSearcher not available: {e}")
    UNIFIED_AVAILABLE = False
    UnifiedSearcher = None

# Import Bridge
try:
    from c1_bridge import C1Bridge
    BRIDGE_AVAILABLE = True
except ImportError:
    logger.warning("C1Bridge not available")
    BRIDGE_AVAILABLE = False


class EyeDMCP:
    """EYE-D MCP Server - OSINT Intelligence"""

    def __init__(self):
        self.server = Server("eyed")
        self.searcher = UnifiedSearcher() if UNIFIED_AVAILABLE else None
        self.bridge = C1Bridge(project_id="eyed") if BRIDGE_AVAILABLE else None
        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="search_email",
                    description="Search for email in breach databases, enrich with contact info. Returns breaches, related accounts, associated entities.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "description": "Email address to search"}
                        },
                        "required": ["email"]
                    }
                ),
                Tool(
                    name="search_phone",
                    description="Search phone number for owner info, carrier, associated accounts. Supports international formats.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "phone": {"type": "string", "description": "Phone number (any format)"}
                        },
                        "required": ["phone"]
                    }
                ),
                Tool(
                    name="search_username",
                    description="Search username across platforms and breach databases. Mode: 'discovery' (broad) or 'breach' (focused).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "username": {"type": "string", "description": "Username to search"},
                            "mode": {"type": "string", "enum": ["discovery", "breach"], "default": "discovery"}
                        },
                        "required": ["username"]
                    }
                ),
                Tool(
                    name="search_linkedin",
                    description="Enrich LinkedIn profile with contact info, work history, connections.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "linkedin_url": {"type": "string", "description": "LinkedIn profile URL"}
                        },
                        "required": ["linkedin_url"]
                    }
                ),
                Tool(
                    name="search_whois",
                    description="WHOIS lookup for domain. Returns registrant, contacts, nameservers, history.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Domain name to lookup"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="search_ip",
                    description="IP geolocation and intelligence. Returns location, ISP, hosting info.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "ip_address": {"type": "string", "description": "IP address to lookup"}
                        },
                        "required": ["ip_address"]
                    }
                ),
                Tool(
                    name="search_people",
                    description="People search by name. Returns matching profiles, contact info, associations.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Person name to search"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="chain_reaction",
                    description="Automated OSINT chain: start from one data point, follow connections. Builds entity graph.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_query": {"type": "string", "description": "Starting data point (email, phone, domain, etc.)"},
                            "start_type": {"type": "string", "enum": ["email", "phone", "domain", "username", "linkedin"], "description": "Type of starting data"},
                            "depth": {"type": "integer", "default": 2, "description": "How many hops to follow (1-3)"}
                        },
                        "required": ["start_query", "start_type"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            if not self.searcher:
                return [TextContent(type="text", text=json.dumps({"error": "UnifiedSearcher not available"}))]

            try:
                if name == "search_email":
                    result = await self.searcher.search_email(arguments["email"])
                elif name == "search_phone":
                    result = await self.searcher.search_phone(arguments["phone"])
                elif name == "search_username":
                    result = await self.searcher.search_username(
                        arguments["username"],
                        mode=arguments.get("mode", "discovery")
                    )
                elif name == "search_linkedin":
                    result = await self.searcher.search_linkedin(arguments["linkedin_url"])
                elif name == "search_whois":
                    result = await self.searcher.search_whois(arguments["domain"])
                elif name == "search_ip":
                    result = await self.searcher.search_ip(arguments["ip_address"])
                elif name == "search_people":
                    result = await self.searcher.search_people(arguments["query"])
                elif name == "chain_reaction":
                    result = await self.searcher.run_chain_reaction(
                        arguments["start_query"],
                        arguments["start_type"],
                        depth=arguments.get("depth", 2)
                    )
                else:
                    result = {"error": f"Unknown tool: {name}"}

                # Index results to Cymonides via Bridge
                if self.bridge:
                    try:
                        if name == "chain_reaction":
                            # For chains, index each step individually to preserve A->B->C topology
                            count = 0
                            for step_result in result.get("results", []):
                                self.bridge.index_eyed_results(step_result)
                                count += 1
                            logger.info(f"Indexed {count} chain reaction steps to Cymonides")
                        else:
                            # Single search
                            self.bridge.index_eyed_results(result)
                            logger.info(f"Indexed search result to Cymonides")
                    except Exception as e:
                        logger.error(f"Failed to index results: {e}")

                return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

            except Exception as e:
                logger.error(f"Tool {name} error: {e}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

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
    server = EyeDMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
