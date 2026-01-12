#!/usr/bin/env python3
"""
IO MCP Server - Model Context Protocol server for the Input/Output Matrix

THE SINGLE ENTRY POINT for Investigation Operations via MCP.

Exposes both ROUTING and EXECUTION capabilities via MCP tools.
Full feature parity with io_cli.py.

Usage:
  python io_mcp.py

EXECUTION Tools (NEW):
  - io_execute: Run full investigation pipeline (p:, c:, e:, t:, d:)
  - io_list_modules: List available execution modules
  - io_module_info: Get details about a specific module

ROUTING Tools:
  - io_find_capabilities: Find what outputs are possible given an input field
  - io_find_route: Find path from input field to desired output
  - io_get_sources: Get sources that can transform input to output
  - io_get_graph: Get graph data for visualization
  - io_generate_viz: Generate interactive HTML visualization
  - io_expand_node: Chain reaction - expand a node to show its sources and outputs
  - io_search_fields: Search or list field codes
  - io_get_stats: Get matrix statistics
"""

import json
import asyncio
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP package not installed. Install with: pip install mcp")
    exit(1)

# Import from io_cli to avoid code duplication
from io_cli import IORouter, IOExecutor, generate_viz_html, classify_node_type, parse_prefix, detect_entity_type

# Matrix data directory
MATRIX_DIR = Path(__file__).parent

# Initialize router
router = IORouter()

# Create MCP server
server = Server("io-matrix")


@server.list_tools()
async def list_tools():
    """List available tools"""
    return [
        # =========================================================================
        # EXECUTION TOOLS (NEW) - Run actual investigations
        # =========================================================================
        Tool(
            name="io_execute",
            description="""**PRIMARY TOOL** - Execute a full investigation pipeline on an entity.

Use prefix operators to specify entity type:
- p: = person (e.g., "p: John Smith")
- c: = company (e.g., "c: Acme Corp")
- e: = email (e.g., "e: john@acme.com")
- t: = phone (e.g., "t: +1-555-1234")
- d: = domain (e.g., "d: acme.com")

The investigation runs multiple modules: EYE-D, Corporella, OpenSanctions, WHOIS, etc.
Results can be auto-indexed to Elasticsearch.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query with prefix (e.g., 'p: John Smith', 'c: Acme Corp', 'e: john@acme.com')"
                    },
                    "jurisdiction": {
                        "type": "string",
                        "description": "Optional jurisdiction filter (e.g., 'US', 'UK', 'DE')"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show execution plan without running",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="io_list_modules",
            description="List all available execution modules with their capabilities (EYE-D, Corporella, OpenSanctions, etc.)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="io_module_info",
            description="Get detailed information about a specific execution module",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Module name (e.g., 'eye-d', 'corporella', 'opensanctions')"
                    }
                },
                "required": ["module_name"]
            }
        ),
        # =========================================================================
        # ROUTING TOOLS - Lookup capabilities and paths
        # =========================================================================
        Tool(
            name="io_find_capabilities",
            description="Find what outputs are possible given an input field. Use field names like 'email', 'domain', 'company_name', 'person_name', etc. Returns available transformations and data sources. **IMPORTANT: After calling this, ALWAYS call io_generate_viz to show the user the interactive graph!**",
            inputSchema={
                "type": "object",
                "properties": {
                    "have_field": {
                        "type": "string",
                        "description": "The input field you have (e.g., 'email', 'domain', 'company_name', 'person_name')"
                    }
                },
                "required": ["have_field"]
            }
        ),
        Tool(
            name="io_find_route",
            description="Find the shortest path from an input field to a desired output field. Useful for planning multi-step data enrichment. **IMPORTANT: After calling this, ALWAYS call io_generate_viz to show the user the interactive graph!**",
            inputSchema={
                "type": "object",
                "properties": {
                    "have_field": {
                        "type": "string",
                        "description": "The input field you have"
                    },
                    "want_field": {
                        "type": "string",
                        "description": "The output field you want to obtain"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum path length to search (default: 3)",
                        "default": 3
                    }
                },
                "required": ["have_field", "want_field"]
            }
        ),
        Tool(
            name="io_get_sources",
            description="Get all data sources that can directly transform an input field to an output field. Returns source names and their capabilities.",
            inputSchema={
                "type": "object",
                "properties": {
                    "have_field": {
                        "type": "string",
                        "description": "The input field"
                    },
                    "want_field": {
                        "type": "string",
                        "description": "The desired output field"
                    }
                },
                "required": ["have_field", "want_field"]
            }
        ),
        Tool(
            name="io_get_graph",
            description="Get graph data centered on a field, showing connected sources and outputs. Useful for understanding data flow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "center_field": {
                        "type": "string",
                        "description": "The field to center the graph on"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many levels deep to explore (default: 1)",
                        "default": 1
                    },
                    "max_sources": {
                        "type": "integer",
                        "description": "Maximum sources per node to include (default: 30)",
                        "default": 30
                    }
                },
                "required": ["center_field"]
            }
        ),
        Tool(
            name="io_generate_viz",
            description="**MANDATORY** - Generate and open an interactive HTML visualization of the I/O matrix. Opens in browser automatically. YOU MUST CALL THIS after ANY io_find_capabilities, io_find_route, or io_get_graph call to show the user the visual graph. This is the PRIMARY output method.",
            inputSchema={
                "type": "object",
                "properties": {
                    "center_field": {
                        "type": "string",
                        "description": "The field to center the visualization on"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many levels deep to explore (default: 1)",
                        "default": 1
                    },
                    "max_sources": {
                        "type": "integer",
                        "description": "Maximum sources per node (default: 30)",
                        "default": 30
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Whether to open in browser (default: true)",
                        "default": True
                    }
                },
                "required": ["center_field"]
            }
        ),
        Tool(
            name="io_expand_node",
            description="Chain reaction: Get expansion data for a node - its sources and their outputs. For interactive exploration.",
            inputSchema={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "The field to expand"
                    },
                    "max_sources": {
                        "type": "integer",
                        "description": "Maximum sources to return (default: 10)",
                        "default": 10
                    },
                    "max_outputs_per_source": {
                        "type": "integer",
                        "description": "Maximum outputs per source (default: 10)",
                        "default": 10
                    }
                },
                "required": ["field"]
            }
        ),
        Tool(
            name="io_search_fields",
            description="Search for field codes by name, or list all available fields in the matrix.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (leave empty to list all)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 50)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="io_get_stats",
            description="Get statistics about the I/O matrix: field count, rule count, source count.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="io_list_entity_types",
            description="List all entity/field type categories available in the matrix (person, company, domain, etc.)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


def expand_node(field: str, max_sources: int = 10, max_outputs: int = 10) -> Dict[str, Any]:
    """Get expansion data for chain reaction"""
    code = router.resolve_code(field)
    if code is None:
        return {"error": f"Unknown field: {field}"}

    sources_for_node = {}
    for rule in router.rules:
        requires = rule.get("requires_any", rule.get("inputs", []))
        returns = rule.get("returns", rule.get("outputs", []))
        if code in requires:
            label = rule.get("label", rule.get("source", ""))
            if label.startswith("BLOCKED") or label.startswith("'''") or len(label) < 3:
                continue
            if label not in sources_for_node:
                sources_for_node[label] = set()
            for out in returns:
                sources_for_node[label].add(out)

    # Sort by output count and limit
    sorted_sources = sorted(sources_for_node.items(), key=lambda x: -len(x[1]))[:max_sources]

    result_sources = []
    for label, outputs in sorted_sources:
        output_list = [
            {"code": o, "name": router.get_field_name(o)}
            for o in list(outputs)[:max_outputs]
        ]
        result_sources.append({
            "source": label,
            "outputs": output_list,
            "total_outputs": len(outputs)
        })

    return {
        "field": router.get_field_name(code),
        "field_code": code,
        "sources": result_sources,
        "total_sources": len(sources_for_node)
    }


def list_entity_types() -> Dict[str, Any]:
    """List all entity type categories"""
    categories = {
        "person": [],
        "company": [],
        "domain": [],
        "address": [],
        "contact": [],
        "document": [],
        "financial": [],
        "legal": [],
        "other": []
    }

    for code, name in router.legend.items():
        name_lower = name.lower()
        if "person" in name_lower:
            categories["person"].append({"code": int(code), "name": name})
        elif "company" in name_lower or "corporate" in name_lower:
            categories["company"].append({"code": int(code), "name": name})
        elif "domain" in name_lower or "url" in name_lower or "website" in name_lower:
            categories["domain"].append({"code": int(code), "name": name})
        elif "address" in name_lower or "location" in name_lower:
            categories["address"].append({"code": int(code), "name": name})
        elif "email" in name_lower or "phone" in name_lower or "contact" in name_lower:
            categories["contact"].append({"code": int(code), "name": name})
        elif "document" in name_lower or "filing" in name_lower or "report" in name_lower:
            categories["document"].append({"code": int(code), "name": name})
        elif "financial" in name_lower or "revenue" in name_lower or "profit" in name_lower:
            categories["financial"].append({"code": int(code), "name": name})
        elif "legal" in name_lower or "court" in name_lower or "litigation" in name_lower:
            categories["legal"].append({"code": int(code), "name": name})
        else:
            categories["other"].append({"code": int(code), "name": name})

    # Sort each category and add counts
    result = {}
    for cat, fields in categories.items():
        if fields:
            result[cat] = {
                "count": len(fields),
                "fields": sorted(fields, key=lambda x: x["name"])[:20]  # Limit to 20 per category
            }

    return result


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls"""
    try:
        # =====================================================================
        # EXECUTION HANDLERS (NEW)
        # =====================================================================
        if name == "io_execute":
            query = arguments["query"]
            entity_type, value, parsed_jurisdiction = parse_prefix(query)
            # Use argument jurisdiction if provided, otherwise use parsed jurisdiction
            jurisdiction = arguments.get("jurisdiction") or parsed_jurisdiction

            # Auto-detect if no prefix
            if entity_type is None:
                entity_type = detect_entity_type(value)
                if entity_type is None:
                    result = {
                        "error": "No prefix specified and cannot auto-detect entity type",
                        "hint": "Use prefixes: p: (person), c: (company), e: (email), t: (phone), d: (domain)",
                        "example": f"p: {value}"
                    }
                else:
                    # Run with auto-detected type
                    executor = IOExecutor(router, dry_run=arguments.get("dry_run", False))
                    result = await executor.execute(entity_type, value, jurisdiction)
                    result["auto_detected_type"] = entity_type
            else:
                # Run with prefix-specified type
                executor = IOExecutor(router, dry_run=arguments.get("dry_run", False))
                result = await executor.execute(entity_type, value, jurisdiction)

        elif name == "io_list_modules":
            result = {
                "modules": {
                    "EYE-D": {
                        "description": "OSINT lookup for persons, emails, phones",
                        "entity_types": ["person", "email", "phone"],
                        "status": "active"
                    },
                    "Corporella": {
                        "description": "Corporate registry lookups and company intelligence",
                        "entity_types": ["company"],
                        "status": "active"
                    },
                    "OpenSanctions": {
                        "description": "PEP and sanctions screening",
                        "entity_types": ["person", "company"],
                        "api_key_required": "OPENSANCTIONS_API_KEY",
                        "status": "active"
                    },
                    "OpenCorporates": {
                        "description": "Global company registry data",
                        "entity_types": ["company"],
                        "api_key_required": "OPENCORPORATES_API_KEY (optional)",
                        "status": "active"
                    },
                    "WHOIS": {
                        "description": "Domain registration lookup via ALLDOM (WhoisXML API)",
                        "entity_types": ["domain"],
                        "capabilities": ["current_whois", "whois_history", "reverse_whois", "domain_clustering"],
                        "source": "alldom.bridges.whois",
                        "status": "active"
                    },
                    "LINKLATER": {
                        "description": "Web enrichment and entity extraction",
                        "entity_types": ["person", "company", "domain"],
                        "status": "pending integration"
                    }
                }
            }

        elif name == "io_module_info":
            module_name = arguments["module_name"].lower()
            module_details = {
                "eye-d": {
                    "name": "EYE-D",
                    "description": "Unified OSINT search module",
                    "capabilities": [
                        "Person search: social profiles, breach data, public records",
                        "Email search: reverse lookup, breach checks, associated accounts",
                        "Phone search: carrier info, reverse lookup"
                    ],
                    "methods": ["search_person()", "search_email()", "search_phone()"],
                    "location": "BACKEND/modules/EYE-D/unified_osint.py"
                },
                "corporella": {
                    "name": "Corporella",
                    "description": "Corporate intelligence and registry lookup",
                    "capabilities": [
                        "Company search across multiple registries",
                        "Neural search for company matching",
                        "News aggregation for companies"
                    ],
                    "methods": ["search_company()"],
                    "location": "BACKEND/modules/corporella/exa_company_search.py"
                },
                "opensanctions": {
                    "name": "OpenSanctions",
                    "description": "PEP and sanctions screening via OpenSanctions API",
                    "capabilities": [
                        "Person sanctions check",
                        "Company sanctions check",
                        "PEP (Politically Exposed Person) screening"
                    ],
                    "api_endpoint": "https://api.opensanctions.org/match/default",
                    "api_key": "OPENSANCTIONS_API_KEY"
                },
                "whois": {
                    "name": "WHOIS (ALLDOM)",
                    "description": "Domain WHOIS intelligence via ALLDOM bridge (WhoisXML API)",
                    "capabilities": [
                        "Current WHOIS lookup: registrant info, nameservers, dates",
                        "Historic WHOIS: all ownership changes over time",
                        "Reverse WHOIS: find domains by registrant name/email/org",
                        "Nameserver clustering: find domains sharing nameservers",
                        "Domain clustering: full registrant network discovery",
                        "Entity extraction: persons, companies, emails, addresses from WHOIS"
                    ],
                    "methods": ["lookup()", "history()", "reverse()", "cluster()", "entities()"],
                    "location": "BACKEND/modules/alldom/bridges/whois.py",
                    "api_key": "WHOIS_API_KEY or WHOISXMLAPI_KEY"
                }
            }
            result = module_details.get(module_name, {"error": f"Unknown module: {arguments['module_name']}"})

        # =====================================================================
        # ROUTING HANDLERS (EXISTING)
        # =====================================================================
        elif name == "io_find_capabilities":
            result = router.find_capabilities(arguments["have_field"])

        elif name == "io_find_route":
            result = router.find_route(
                arguments["have_field"],
                arguments["want_field"],
                arguments.get("max_depth", 3)
            )

        elif name == "io_get_sources":
            result = router.get_sources_for_transform(
                arguments["have_field"],
                arguments["want_field"]
            )

        elif name == "io_get_graph":
            result = router.get_graph_data(
                arguments["center_field"],
                arguments.get("depth", 1),
                arguments.get("max_sources", 30)
            )

        elif name == "io_generate_viz":
            graph_data = router.get_graph_data(
                arguments["center_field"],
                arguments.get("depth", 1),
                arguments.get("max_sources", 30)
            )
            if "error" in graph_data:
                result = graph_data
            else:
                html = generate_viz_html(graph_data, router)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(html)
                    filepath = f.name

                if arguments.get("open_browser", True):
                    webbrowser.open(f'file://{filepath}')

                result = {
                    "success": True,
                    "filepath": filepath,
                    "center": graph_data["center"],
                    "node_count": graph_data["node_count"],
                    "edge_count": graph_data["edge_count"],
                    "message": f"Visualization opened in browser. {graph_data['node_count']} nodes, {graph_data['edge_count']} edges."
                }

        elif name == "io_expand_node":
            result = expand_node(
                arguments["field"],
                arguments.get("max_sources", 10),
                arguments.get("max_outputs_per_source", 10)
            )

        elif name == "io_search_fields":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 50)
            if query:
                results = router.search_legend(query)[:limit]
            else:
                results = [{"code": int(k), "name": v} for k, v in router.legend.items()][:limit]
            result = {"fields": results, "count": len(results)}

        elif name == "io_get_stats":
            result = router.get_stats()

        elif name == "io_list_entity_types":
            result = list_entity_types()

        else:
            result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    """Run the MCP server"""
    import sys
    print("Starting IO Matrix MCP Server...", file=sys.stderr)
    print(f"Matrix directory: {MATRIX_DIR}", file=sys.stderr)
    print(f"Loaded {len(router.legend)} fields, {len(router.rules)} rules", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
