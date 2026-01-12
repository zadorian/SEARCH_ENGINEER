#!/usr/bin/env python3
"""
LinkLater MCP Server

Minimal wrapper that exposes backlink discovery syntax to AI.
The REAL implementation is in backlinks.py - this just provides the interface.

Syntax:
    ?bl !domain   → Referring domains only (FAST)
    bl? !domain   → Referring pages with enrichment (RICH)
    ?bl domain!   → Referring domains to specific URL
    bl? domain!   → Referring pages to specific URL
"""

import asyncio
import json
import sys
from typing import Any, Dict

# Add repo root to path for imports
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    # Deployed layout on this server
    from LINKLATER.backlinks import BacklinkDiscovery
except ImportError:
    # Alternate package layout
    from linklater.backlinks import BacklinkDiscovery


# MCP Server State
discovery_engine = None


def initialize():
    """Initialize the backlink discovery engine."""
    global discovery_engine
    discovery_engine = BacklinkDiscovery()


async def cleanup():
    """Cleanup resources."""
    global discovery_engine
    if discovery_engine:
        await discovery_engine.close()


# =============================================================================
# MCP TOOL DEFINITIONS
# =============================================================================

TOOLS = [
    {
        "name": "linklater_backlinks",
        "description": """Get backlinks using LinkLater syntax.

Syntax:
  ?bl !domain   → Referring domains only (FAST - 100ms)
  bl? !domain   → Referring pages with full enrichment (RICH - 30-60s)
  ?bl domain!   → Referring domains to specific URL
  bl? domain!   → Referring pages to specific URL

Examples:
  ?bl !soax.com              # Fast: domains linking to soax.com
  bl? !soax.com              # Rich: pages linking to soax.com with anchor text
  ?bl soax.com/pricing!      # Domains linking to specific URL
  bl? soax.com/pricing!      # Pages linking to specific URL with anchor text

The 'bl?' mode includes:
- CC Domain Graph (domain discovery)
- GlobalLinks (page-level extraction with anchor text)
- Majestic API (Trust/Citation Flow, fresh backlinks)
- Tor Bridges (dark web sources)
""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "syntax": {
                    "type": "string",
                    "enum": ["?bl", "bl?"],
                    "description": "Query mode: '?bl' for domains only (fast), 'bl?' for pages with enrichment (rich)"
                },
                "target": {
                    "type": "string",
                    "description": "Target domain or URL. Use '!domain' or 'domain!' format. Examples: '!soax.com', 'soax.com/pricing!'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 100 for pages, 1000 for domains)",
                    "default": 100
                },
                "top_domains": {
                    "type": "integer",
                    "description": "For 'bl?' mode: how many top domains to enrich with GlobalLinks (default: 20)",
                    "default": 20
                },
                "include_majestic": {
                    "type": "boolean",
                    "description": "For 'bl?' mode: include Majestic API data (requires API key, default: true)",
                    "default": True
                },
                "include_tor": {
                    "type": "boolean",
                    "description": "Include Tor bridge data (dark web sources, default: true)",
                    "default": True
                },
                "min_weight": {
                    "type": "integer",
                    "description": "For '?bl' mode: minimum link weight (default: 1)",
                    "default": 1
                }
            },
            "required": ["syntax", "target"]
        }
    }
]


# =============================================================================
# MCP TOOL HANDLERS
# =============================================================================

async def handle_linklater_backlinks(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle backlinks query.

    Args:
        arguments: Tool arguments from MCP

    Returns:
        Query results
    """
    syntax = arguments.get("syntax")
    target = arguments.get("target")

    # Validate
    if syntax not in ("?bl", "bl?"):
        return {
            "error": f"Invalid syntax: {syntax}. Must be '?bl' or 'bl?'"
        }

    if not target:
        return {
            "error": "Target is required. Use '!domain' or 'domain!' format."
        }

    # Extract optional parameters
    kwargs = {}
    if "limit" in arguments:
        kwargs["limit"] = arguments["limit"]
    if "top_domains" in arguments:
        kwargs["top_domains"] = arguments["top_domains"]
    if "include_majestic" in arguments:
        kwargs["include_majestic"] = arguments["include_majestic"]
    if "include_tor" in arguments:
        kwargs["include_tor"] = arguments["include_tor"]
    if "min_weight" in arguments:
        kwargs["min_weight"] = arguments["min_weight"]

    # Execute query
    try:
        result = await discovery_engine.query(syntax, target, **kwargs)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "traceback": __import__("traceback").format_exc()
        }


# =============================================================================
# MCP PROTOCOL HANDLERS
# =============================================================================

async def handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle initialize request."""
    initialize()
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "linklater",
            "version": "1.0.0"
        },
        "capabilities": {
            "tools": {}
        }
    }


async def handle_tools_list(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/list request."""
    return {
        "tools": TOOLS
    }


async def handle_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/call request."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "linklater_backlinks":
        result = await handle_linklater_backlinks(arguments)

        # Format as MCP response
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, default=str)
                }
            ]
        }
    else:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"error": f"Unknown tool: {tool_name}"})
                }
            ],
            "isError": True
        }


# =============================================================================
# MCP SERVER MAIN LOOP
# =============================================================================

async def main():
    """Main MCP server loop."""
    print("[LinkLater MCP] Starting server...", file=sys.stderr)

    try:
        while True:
            # Read JSON-RPC message from stdin
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )

            if not line:
                break

            try:
                message = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[LinkLater MCP] JSON decode error: {e}", file=sys.stderr)
                continue

            # Route request
            method = message.get("method")
            params = message.get("params", {})
            msg_id = message.get("id")

            response = None

            if method == "initialize":
                response = await handle_initialize(params)
            elif method == "tools/list":
                response = await handle_tools_list(params)
            elif method == "tools/call":
                response = await handle_tools_call(params)
            elif method == "ping":
                response = {}
            else:
                response = {
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            # Send response
            if msg_id is not None:
                output = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": response
                }
                print(json.dumps(output), flush=True)

    except KeyboardInterrupt:
        print("[LinkLater MCP] Shutting down...", file=sys.stderr)
    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
