#!/usr/bin/env python3
"""
LINKLATER Syntax-Driven MCP Server

A SINGLE MCP tool that accepts DRILL/LINKLATER query syntax strings and routes
them through the QueryExecutor for unified operation.

This is the preferred interface for AI agents - ONE tool, infinite operations.
The syntax is the same everywhere: CLI, MCP, API.

Examples:
    "?bl:!soax.com"           → Fast backlinks (domains only, ~100ms)
    "bl?:!soax.com"           → Rich backlinks (full pages, ~30-60s)
    "ent?:2024! !soax.com"    → Historical entities from 2024 archives
    "p? c?:!company.com"      → Persons and companies from live domain
    "pdf!:!sebgroup.com"      → Find all PDFs on domain
    "\"bitcoin\" :tor"        → Search Tor engines for keyword
    "ol?:!domain.com"         → Outlinks from domain

MCP Protocol: JSON-RPC 2.0 over stdin/stdout
"""

import asyncio
import json
import sys
import traceback
from typing import Any, Dict
from pathlib import Path

# Add parent directories to path for imports
LINKLATER_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = LINKLATER_DIR.parent
BACKEND_DIR = MODULES_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(MODULES_DIR))

# Import QueryExecutor for routing
try:
    from modules.query_executor import QueryExecutor
    from modules.query_parser import parse_query
    QUERY_EXECUTOR_AVAILABLE = True
except ImportError:
    QUERY_EXECUTOR_AVAILABLE = False
    QueryExecutor = Any

# =============================================================================
# MCP TOOL DEFINITION
# =============================================================================

TOOLS = [
    {
        "name": "linklater_query",
        "description": """Execute any LINKLATER operation via query syntax.

This is a UNIFIED interface - one tool for ALL operations. The query syntax
determines what happens. Same syntax as CLI and API.

## Query Syntax Reference

**Format:** `OPERATORS : HISTORICAL_MODIFIER TARGET [CONTEXT_MODIFIER]`

**Canonical form:** `WHAT : WHERE`
- LEFT of colon = WHAT to do (operators)
- RIGHT of colon = WHERE to apply it (target domain/URL)

### Position Semantics (IMPORTANT!)

Position of `?` determines result type:
- `?op` (prefix) → Domain-level results, FAST (~100ms)
- `op?` (suffix) → Page-level results, RICH (~30-60s)

### Link Analysis

| Syntax | Result | Speed |
|--------|--------|-------|
| `?bl !domain` | Referring domains | Fast ~100ms |
| `bl? !domain` | Referring pages with anchor text | Rich ~30-60s |
| `?ol !domain` | Linked domains | Fast |
| `ol? !domain` | Linked pages | Rich |

### Entity Extraction

| Syntax | Result |
|--------|--------|
| `ent?:!domain` | ALL entities (persons, companies, emails, phones) |
| `p?:!domain` | Persons only |
| `c?:!domain` | Companies only |
| `e?:!domain` | Emails only |
| `t?:!domain` | Phone numbers only |
| `a?:!domain` | Addresses only |

### Historical (Archive) Queries

Add year modifier BEFORE target:
| Syntax | Result |
|--------|--------|
| `ent?:2024! !domain` | Entities from 2024 archives |
| `ent?:2020-2024! !domain` | Entities from 2020-2024 range |
| `bl?:<-! !domain` | All historical backlinks |

### Filetype Discovery

| Syntax | Result |
|--------|--------|
| `pdf!:!domain` | Find PDFs on domain |
| `doc!:!domain` | Find all documents (pdf, doc, xls, ppt) |
| `word!:!domain` | Find Word docs only |
| `xls!:!domain` | Find Excel files only |

### Tor/Onion Context

| Syntax | Result |
|--------|--------|
| `"keyword" :tor` | Search Tor engines |
| `ent?:!xyz.onion` | Extract entities from .onion URL |
| `p? :tor` | Search Tor index, filter by persons |

### Combining Operators

Multiple operators can be combined:
- `bl? p?:!domain` → Backlinks AND persons
- `?ol ent?:!domain` → Outlink domains AND entities
- `p? c? e?:2024! !domain` → Persons, companies, emails from 2024

### Examples

```
# Link Analysis
?bl:!soax.com               # Fast: referring domains (~100ms)
bl?:!soax.com               # Full: referring pages (~30-60s)

# Entity Extraction
ent?:!company.com           # All entities from live domain
p? c?:!company.com          # Persons and companies only

# Historical Research
ent?:2022! !domain.com      # Entities from 2022 archives
p?:2020-2024! !domain.com   # Persons from 2020-2024 range

# Document Discovery
pdf!:!sebgroup.com          # Find all PDFs

# Dark Web
"bitcoin" :tor              # Search Tor engines
ent?:!xyz.onion             # Extract entities from .onion
```

Returns structured JSON with:
- `query`: Original query string
- `target`: Parsed target domain/URL
- `results`: Operation results (varies by operator)
- `counts`: Result counts
- `method`: Execution method used
""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "LINKLATER query syntax string. Examples: '?bl !soax.com', 'ent?:2024! !domain.com', 'pdf!:!sebgroup.com'"
                }
            },
            "required": ["query"]
        }
    }
]

# =============================================================================
# QUERY EXECUTOR
# =============================================================================

_executor = None

def get_executor() -> QueryExecutor:
    """Get or create QueryExecutor singleton."""
    global _executor
    if _executor is None:
        _executor = QueryExecutor()
    return _executor


async def execute_linklater_query(query: str) -> Dict[str, Any]:
    """
    Execute a LINKLATER query string.

    Args:
        query: Query syntax string (e.g., "?bl !soax.com")

    Returns:
        Query results dict
    """
    if not QUERY_EXECUTOR_AVAILABLE:
        return {
            "error": "QueryExecutor not available",
            "message": "The query execution module could not be loaded"
        }

    if not query or not query.strip():
        return {
            "error": "Empty query",
            "message": "Please provide a query string"
        }

    # Parse query first to validate
    parsed = parse_query(query)
    if not parsed:
        return {
            "error": "Invalid query syntax",
            "query": query,
            "message": "Could not parse query. See tool description for syntax reference."
        }

    # Execute via QueryExecutor
    executor = get_executor()
    try:
        result = await executor.execute_async(query)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "query": query,
            "traceback": traceback.format_exc()
        }


# =============================================================================
# MCP TOOL HANDLER
# =============================================================================

async def handle_linklater_query(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle linklater_query tool invocation.

    Args:
        arguments: Tool arguments containing 'query' string

    Returns:
        Query results
    """
    query = arguments.get("query", "")
    return await execute_linklater_query(query)


# =============================================================================
# MCP PROTOCOL HANDLERS
# =============================================================================

async def handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP initialize request."""
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "linklater-syntax",
            "version": "1.0.0",
            "description": "LINKLATER syntax-driven query interface"
        },
        "capabilities": {
            "tools": {}
        }
    }


async def handle_tools_list(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tools/list request."""
    return {
        "tools": TOOLS
    }


async def handle_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tools/call request."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "linklater_query":
        result = await handle_linklater_query(arguments)

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

async def run_server():
    """Run the MCP server (JSON-RPC over stdin/stdout)."""
    print("[LINKLATER Syntax MCP] Starting server...", file=sys.stderr)
    print("[LINKLATER Syntax MCP] QueryExecutor available:", QUERY_EXECUTOR_AVAILABLE, file=sys.stderr)

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
                print(f"[LINKLATER Syntax MCP] JSON decode error: {e}", file=sys.stderr)
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
        print("[LINKLATER Syntax MCP] Shutting down...", file=sys.stderr)


# =============================================================================
# CONVENIENCE FUNCTIONS (for direct Python usage)
# =============================================================================

async def query(query_str: str) -> Dict[str, Any]:
    """
    Execute a LINKLATER query (for direct Python usage).

    This is the same function exposed via MCP, but callable directly.

    Args:
        query_str: Query syntax string

    Returns:
        Query results

    Example:
        >>> import asyncio
        >>> from linklater.mcp.syntax_server import query
        >>> result = asyncio.run(query("?bl !soax.com"))
    """
    return await execute_linklater_query(query_str)


def query_sync(query_str: str) -> Dict[str, Any]:
    """
    Execute a LINKLATER query synchronously.

    Args:
        query_str: Query syntax string

    Returns:
        Query results

    Example:
        >>> from linklater.mcp.syntax_server import query_sync
        >>> result = query_sync("?bl !soax.com")
    """
    return asyncio.run(execute_linklater_query(query_str))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Check for direct query mode (not MCP)
    if len(sys.argv) > 1 and sys.argv[1] != "--mcp":
        # Direct query execution
        query_str = " ".join(sys.argv[1:])
        result = query_sync(query_str)
        print(json.dumps(result, indent=2, default=str))
    else:
        # MCP server mode
        asyncio.run(run_server())
