#!/usr/bin/env python3
"""
IO MCP Server v2 - Elasticsearch-Powered Investigation Routing

THE SINGLE ENTRY POINT for Investigation Operations via MCP.

Uses Elasticsearch index (io-matrix) for fast querying of:
- 11,809+ sources with inputs, outputs, jurisdictions
- 433+ field codes with entity types and edges
- 16 execution modules with capabilities
- Jurisdiction capabilities and operators
- Chain rules for multi-hop routing

QUERY TOOLS:
  - io_search: Full-text search across all IO data
  - io_find_sources: Find sources by input/output/jurisdiction/category
  - io_find_route: Find path from input to desired output
  - io_get_capabilities: What outputs can I get from this input?
  - io_field_lookup: Lookup field code details
  - io_jurisdiction_info: Get jurisdiction capabilities and operators

EXECUTION TOOLS:
  - io_execute: Run investigation (p:, c:, e:, t:, d: prefixes)
  - io_jurisdiction_cli: Run jurisdiction-specific CLI (cuk:, puk:, etc.)

TORPEDO TOOLS:
  - torpedo_search_cr: Corporate registry search via TORPEDO
  - torpedo_search_news: News search via TORPEDO templates

Usage:
  python io_mcp_v2.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("io-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Paths
MATRIX_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MATRIX_DIR.parent.parent
BACKEND_MODULES = PROJECT_ROOT / "BACKEND" / "modules"
JURISDICTIONAL = Path("/data/JURISDICTIONAL")

sys.path.insert(0, str(MATRIX_DIR))
sys.path.insert(0, str(BACKEND_MODULES))
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(Path("/data/.env"))
except ImportError:
    pass

# Elasticsearch
from elasticsearch import Elasticsearch
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
INDEX_NAME = "io-matrix"

# Import IO execution components
IO_EXECUTOR_AVAILABLE = False
IOExecutor = None
parse_prefix = None
detect_entity_type = None
try:
    from io_cli import IORouter, IOExecutor, parse_prefix, detect_entity_type
    IO_EXECUTOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"IOExecutor not available: {e}")
    # Fallback: try just parse_prefix
    try:
        from io_cli import parse_prefix, detect_entity_type
    except ImportError:
        pass

# Import TORPEDO
TORPEDO_AVAILABLE = False
try:
    from TORPEDO.EXECUTION.cr_searcher import CRSearcher
    from TORPEDO.EXECUTION.news_searcher import NewsSearcher
    from TORPEDO.paths import corporate_registries_sources_path, news_sources_path
    TORPEDO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"TORPEDO not available: {e}")

# Import jurisdiction CLIs dynamically
def get_jurisdiction_cli(jurisdiction: str):
    """Dynamically import and return jurisdiction CLI."""
    jur_upper = jurisdiction.upper()
    jur_lower = jurisdiction.lower()

    cli_paths = [
        JURISDICTIONAL / jur_upper / f"{jur_lower}_cli.py",
        JURISDICTIONAL / jur_upper / f"{jur_lower}_unified_cli.py",
    ]

    for cli_path in cli_paths:
        if cli_path.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{jur_lower}_cli", cli_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Look for CLI class
                for cls_name in [f"{jur_upper}CLI", f"{jur_upper}UnifiedCLI", "CLI"]:
                    if hasattr(module, cls_name):
                        return getattr(module, cls_name)
            except Exception as e:
                logger.warning(f"Failed to load {cli_path}: {e}")

    return None


class IOMCP:
    """IO MCP Server v2 - Elasticsearch-Powered"""

    def __init__(self):
        self.server = Server("io-matrix")
        self.es = Elasticsearch(ES_HOST)

        # Initialize IO executor with router
        self.executor = None
        if IO_EXECUTOR_AVAILABLE:
            try:
                router = IORouter()
                self.executor = IOExecutor(router)
            except Exception as e:
                logger.warning(f"Failed to init IOExecutor: {e}")

        self.torpedo_cr = None
        self.torpedo_news = None
        self._register_handlers()

    async def _init_torpedo(self):
        """Lazy init TORPEDO searchers."""
        if TORPEDO_AVAILABLE and not self.torpedo_cr:
            try:
                self.torpedo_cr = CRSearcher()
                await self.torpedo_cr.load_sources()
                self.torpedo_news = NewsSearcher()
                await self.torpedo_news.load_sources()
            except Exception as e:
                logger.warning(f"Failed to init TORPEDO: {e}")

    def _search_index(self, query: Dict, size: int = 100) -> List[Dict]:
        """Execute search against io-matrix index."""
        try:
            result = self.es.search(index=INDEX_NAME, body=query, size=size)
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.error(f"ES search error: {e}")
            return []

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                # =============================================================
                # QUERY TOOLS (Elasticsearch-powered)
                # =============================================================
                Tool(
                    name="io_search",
                    description="""Full-text search across all IO Matrix data.

Searches sources, fields, modules, jurisdictions, and chain rules.
Returns matching documents with relevance scores.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "doc_type": {
                                "type": "string",
                                "enum": ["source", "field", "module", "jurisdiction", "chain_rule", "all"],
                                "default": "all",
                                "description": "Filter by document type"
                            },
                            "limit": {"type": "integer", "default": 50, "description": "Max results"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="io_find_sources",
                    description="""Find sources by input/output/jurisdiction/category.

Filter sources that can process specific entity types or produce specific outputs.
Essential for route planning and capability discovery.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_class": {
                                "type": "string",
                                "enum": ["person", "company", "domain", "email", "phone", "address", "document", "event"],
                                "description": "Input entity class"
                            },
                            "output_class": {
                                "type": "string",
                                "enum": ["person", "company", "domain", "email", "phone", "address", "document", "event"],
                                "description": "Output entity class"
                            },
                            "jurisdiction": {"type": "string", "description": "Jurisdiction code (UK, US, DE, etc.)"},
                            "category": {
                                "type": "string",
                                "enum": ["news", "corporate", "government", "social", "financial", "legal", "academic"],
                                "description": "Source category"
                            },
                            "source_type": {
                                "type": "string",
                                "enum": ["api", "registry", "scrape", "aggregator"],
                                "description": "Source type"
                            },
                            "limit": {"type": "integer", "default": 50}
                        }
                    }
                ),
                Tool(
                    name="io_find_route",
                    description="""Find route from input to desired output.

Uses graph traversal to find multi-hop paths through sources.
Returns possible routes with sources at each step.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "have": {"type": "string", "description": "What you have (e.g., 'email', 'company_name')"},
                            "want": {"type": "string", "description": "What you want (e.g., 'phone', 'officers')"},
                            "jurisdiction": {"type": "string", "description": "Optional jurisdiction filter"},
                            "max_hops": {"type": "integer", "default": 3, "description": "Max intermediate steps"}
                        },
                        "required": ["have", "want"]
                    }
                ),
                Tool(
                    name="io_get_capabilities",
                    description="""Get all possible outputs from a given input type.

'I have an email - what can I get from it?'
Returns all reachable outputs and the sources that provide them.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input_type": {"type": "string", "description": "Input type (email, domain, company_name, etc.)"},
                            "jurisdiction": {"type": "string", "description": "Optional jurisdiction filter"}
                        },
                        "required": ["input_type"]
                    }
                ),
                Tool(
                    name="io_field_lookup",
                    description="""Lookup field code details.

Get information about what a field code means, its entity class, and relationships.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "code": {"type": "integer", "description": "Field code number"},
                            "name": {"type": "string", "description": "Or search by field name"}
                        }
                    }
                ),
                Tool(
                    name="io_jurisdiction_info",
                    description="""Get jurisdiction capabilities and available operators.

Returns: supported operators (cuk:, puk:, etc.), available sources, and capabilities.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jurisdiction": {"type": "string", "description": "Jurisdiction code (UK, US, DE, HR, etc.)"}
                        },
                        "required": ["jurisdiction"]
                    }
                ),
                Tool(
                    name="io_list_modules",
                    description="List all execution modules with their capabilities.",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="io_stats",
                    description="Get IO Matrix statistics: source counts, jurisdictions, categories.",
                    inputSchema={"type": "object", "properties": {}}
                ),

                # =============================================================
                # EXECUTION TOOLS
                # =============================================================
                Tool(
                    name="io_execute",
                    description="""Execute investigation using prefix operators.

Prefixes:
  p: = person     c: = company    e: = email
  t: = phone      d: = domain     u: = username

Examples:
  'p: John Smith'
  'c: Acme Corp' --jurisdiction UK
  'e: john@acme.com'""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Query with prefix (p:, c:, e:, t:, d:)"},
                            "jurisdiction": {"type": "string", "description": "Optional jurisdiction filter"},
                            "dry_run": {"type": "boolean", "default": False, "description": "Show plan only"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="io_jurisdiction_cli",
                    description="""Run jurisdiction-specific CLI command.

Operators by jurisdiction:
  UK: cuk:, puk:, reguk:, lituk:, assuk:, newsuk:
  DE: cde:, pde:, regde:, litde:
  HR: chr:, phr:, lithr:
  (etc. for all 20+ jurisdictions)

Example: 'cuk: Barclays' for UK company search.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Query with jurisdiction operator"},
                            "jurisdiction": {"type": "string", "description": "Jurisdiction code (auto-detected from operator)"}
                        },
                        "required": ["query"]
                    }
                ),

                # =============================================================
                # TORPEDO TOOLS
                # =============================================================
                Tool(
                    name="torpedo_search_cr",
                    description="""Search corporate registries via TORPEDO templates.

Uses classified source templates to search company registries.
Supports 200+ corporate registry sources across jurisdictions.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Company name to search"},
                            "jurisdiction": {"type": "string", "default": "GLOBAL", "description": "Jurisdiction code (UK, DE, HR, etc.)"},
                            "max_sources": {"type": "integer", "default": 5, "description": "Max templates to execute"},
                            "limit": {"type": "integer", "default": 5, "description": "Alias for max_sources"},
                            "use_brightdata": {"type": "boolean", "default": False, "description": "Force BrightData proxy"},
                            "include_html": {"type": "boolean", "default": False, "description": "Include raw HTML in results"},
                            "html_max_chars": {"type": "integer", "default": 2000, "description": "Truncate HTML to this many chars (0 = no truncation)"},
                            "sources_path": {"type": "string", "description": "Optional corporate_registries.json override"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="torpedo_search_news",
                    description="""Search news sources via TORPEDO templates.

Uses classified news source templates.
Supports 1000+ news sources across jurisdictions.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "jurisdiction": {"type": "string", "default": "GLOBAL", "description": "Jurisdiction filter (optional)"},
                            "max_sources": {"type": "integer", "default": 5, "description": "Max sources to query"},
                            "limit": {"type": "integer", "default": 5, "description": "Alias for max_sources"},
                            "max_pages": {"type": "integer", "default": 1, "description": "Max pages per source"},
                            "min_reliability": {"type": "number", "default": 0.0},
                            "extract": {"type": "boolean", "default": True},
                            "source_type": {"type": "string", "description": "Optional subtype filter"},
                            "region": {"type": "string", "description": "Optional region filter"},
                            "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                            "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                            "date_filter_only": {"type": "boolean", "default": False},
                            "scrape_method_filter": {"type": "string", "description": "Only use sources with this scrape_method"},
                            "require_recipe": {"type": "boolean", "default": False},
                            "sources_path": {"type": "string", "description": "Optional news.json override"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="torpedo_list_jurisdictions",
                    description="List TORPEDO jurisdictions available in templates JSON (news or corporate registries).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_type": {"type": "string", "enum": ["news", "cr"], "default": "news"},
                            "sources_path": {"type": "string", "description": "Optional JSON file override"}
                        }
                    }
                ),
                Tool(
                    name="torpedo_list_sources",
                    description="Search/browse TORPEDO templates (news or corporate registries) without executing them.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source_type": {"type": "string", "enum": ["news", "cr"], "default": "news"},
                            "jurisdiction": {"type": "string", "description": "Filter by jurisdiction"},
                            "query": {"type": "string", "description": "Substring filter for name/domain/template"},
                            "limit": {"type": "integer", "default": 50},
                            "sources_path": {"type": "string", "description": "Optional JSON file override"},
                            "require_recipe": {"type": "boolean", "default": False, "description": "News-only: require extraction recipe"},
                            "min_reliability": {"type": "number", "default": 0.0, "description": "News-only: minimum reliability (0-1)"}
                        }
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                # =============================================================
                # QUERY TOOLS
                # =============================================================
                if name == "io_search":
                    query_text = arguments["query"]
                    doc_type = arguments.get("doc_type", "all")
                    limit = arguments.get("limit", 50)

                    es_query = {
                        "query": {
                            "bool": {
                                "must": [
                                    {"multi_match": {
                                        "query": query_text,
                                        "fields": ["name^3", "description^2", "all_text", "domain"]
                                    }}
                                ]
                            }
                        }
                    }

                    if doc_type != "all":
                        es_query["query"]["bool"]["filter"] = [{"term": {"doc_type": doc_type}}]

                    results = self._search_index(es_query, limit)
                    return [TextContent(type="text", text=json.dumps({
                        "total": len(results),
                        "results": results
                    }, indent=2))]

                elif name == "io_find_sources":
                    filters = []

                    filters.append({"term": {"doc_type": "source"}})

                    if arguments.get("input_class"):
                        filters.append({"term": {"input_classes": arguments["input_class"]}})
                    if arguments.get("output_class"):
                        filters.append({"term": {"output_classes": arguments["output_class"]}})
                    if arguments.get("jurisdiction"):
                        filters.append({"term": {"jurisdictions": arguments["jurisdiction"].upper()}})
                    if arguments.get("category"):
                        filters.append({"term": {"category": arguments["category"]}})
                    if arguments.get("source_type"):
                        filters.append({"term": {"source_type": arguments["source_type"]}})

                    es_query = {"query": {"bool": {"filter": filters}}}
                    results = self._search_index(es_query, arguments.get("limit", 50))

                    return [TextContent(type="text", text=json.dumps({
                        "total": len(results),
                        "sources": [{
                            "name": r.get("name"),
                            "domain": r.get("domain"),
                            "category": r.get("category"),
                            "jurisdiction": r.get("jurisdiction"),
                            "inputs": r.get("input_classes"),
                            "outputs": r.get("output_classes")
                        } for r in results]
                    }, indent=2))]

                elif name == "io_find_route":
                    have = arguments["have"]
                    want = arguments["want"]
                    jur = arguments.get("jurisdiction")

                    # Find sources that accept 'have' as input
                    input_filter = [
                        {"term": {"doc_type": "source"}},
                        {"term": {"input_classes": have}}
                    ]
                    if jur:
                        input_filter.append({"term": {"jurisdictions": jur.upper()}})

                    input_sources = self._search_index({"query": {"bool": {"filter": input_filter}}}, 100)

                    # Find sources that produce 'want' as output
                    output_filter = [
                        {"term": {"doc_type": "source"}},
                        {"term": {"output_classes": want}}
                    ]
                    if jur:
                        output_filter.append({"term": {"jurisdictions": jur.upper()}})

                    output_sources = self._search_index({"query": {"bool": {"filter": output_filter}}}, 100)

                    # Find direct routes (sources that do both)
                    direct = [s for s in input_sources if want in s.get("output_classes", [])]

                    return [TextContent(type="text", text=json.dumps({
                        "have": have,
                        "want": want,
                        "direct_routes": len(direct),
                        "direct_sources": [{"name": s.get("name"), "domain": s.get("domain")} for s in direct[:10]],
                        "sources_accepting_input": len(input_sources),
                        "sources_producing_output": len(output_sources)
                    }, indent=2))]

                elif name == "io_get_capabilities":
                    input_type = arguments["input_type"]
                    jur = arguments.get("jurisdiction")

                    filters = [
                        {"term": {"doc_type": "source"}},
                        {"term": {"input_classes": input_type}}
                    ]
                    if jur:
                        filters.append({"term": {"jurisdictions": jur.upper()}})

                    sources = self._search_index({"query": {"bool": {"filter": filters}}}, 500)

                    # Aggregate outputs
                    output_counts = {}
                    for s in sources:
                        for out in s.get("output_classes", []):
                            output_counts[out] = output_counts.get(out, 0) + 1

                    return [TextContent(type="text", text=json.dumps({
                        "input": input_type,
                        "jurisdiction": jur,
                        "total_sources": len(sources),
                        "possible_outputs": sorted(output_counts.items(), key=lambda x: -x[1]),
                        "sample_sources": [{"name": s.get("name"), "outputs": s.get("output_classes")} for s in sources[:10]]
                    }, indent=2))]

                elif name == "io_field_lookup":
                    code = arguments.get("code")
                    field_name = arguments.get("name")

                    if code:
                        results = self._search_index({
                            "query": {"bool": {"filter": [
                                {"term": {"doc_type": "field"}},
                                {"term": {"code": code}}
                            ]}}
                        }, 1)
                    elif field_name:
                        results = self._search_index({
                            "query": {"bool": {"must": [
                                {"term": {"doc_type": "field"}},
                                {"match": {"name": field_name}}
                            ]}}
                        }, 10)
                    else:
                        return [TextContent(type="text", text=json.dumps({"error": "Provide code or name"}))]

                    return [TextContent(type="text", text=json.dumps({"fields": results}, indent=2))]

                elif name == "io_jurisdiction_info":
                    jur = arguments["jurisdiction"].upper()

                    # Get jurisdiction doc
                    jur_docs = self._search_index({
                        "query": {"bool": {"filter": [
                            {"term": {"doc_type": "jurisdiction"}},
                            {"term": {"jurisdiction": jur}}
                        ]}}
                    }, 1)

                    # Get sources for jurisdiction
                    sources = self._search_index({
                        "query": {"bool": {"filter": [
                            {"term": {"doc_type": "source"}},
                            {"term": {"jurisdictions": jur}}
                        ]}}
                    }, 100)

                    # Aggregate by category
                    categories = {}
                    for s in sources:
                        cat = s.get("category", "other")
                        categories[cat] = categories.get(cat, 0) + 1

                    return [TextContent(type="text", text=json.dumps({
                        "jurisdiction": jur,
                        "info": jur_docs[0] if jur_docs else {},
                        "total_sources": len(sources),
                        "by_category": categories,
                        "operators": jur_docs[0].get("operators", []) if jur_docs else [],
                        "sample_sources": [s.get("name") for s in sources[:20]]
                    }, indent=2))]

                elif name == "io_list_modules":
                    modules = self._search_index({
                        "query": {"term": {"doc_type": "module"}}
                    }, 50)

                    return [TextContent(type="text", text=json.dumps({
                        "modules": [{
                            "name": m.get("module_name"),
                            "description": m.get("description"),
                            "capabilities": m.get("capabilities")
                        } for m in modules]
                    }, indent=2))]

                elif name == "io_stats":
                    # Get counts by doc_type
                    agg = self.es.search(index=INDEX_NAME, body={
                        "size": 0,
                        "aggs": {
                            "by_type": {"terms": {"field": "doc_type", "size": 10}},
                            "by_category": {"terms": {"field": "category", "size": 20}},
                            "by_jurisdiction": {"terms": {"field": "jurisdictions", "size": 50}}
                        }
                    })

                    return [TextContent(type="text", text=json.dumps({
                        "by_type": {b["key"]: b["doc_count"] for b in agg["aggregations"]["by_type"]["buckets"]},
                        "by_category": {b["key"]: b["doc_count"] for b in agg["aggregations"]["by_category"]["buckets"]},
                        "top_jurisdictions": {b["key"]: b["doc_count"] for b in agg["aggregations"]["by_jurisdiction"]["buckets"][:20]}
                    }, indent=2))]

                # =============================================================
                # EXECUTION TOOLS
                # =============================================================
                elif name == "io_execute":
                    if not self.executor:
                        return [TextContent(type="text", text=json.dumps({"error": "IOExecutor not available"}))]

                    query = arguments["query"]
                    jur = arguments.get("jurisdiction")
                    dry_run = arguments.get("dry_run", False)

                    if dry_run:
                        # Just show what would happen
                        prefix, value = parse_prefix(query)
                        entity_type = detect_entity_type(value) if not prefix else prefix
                        return [TextContent(type="text", text=json.dumps({
                            "dry_run": True,
                            "query": query,
                            "detected_prefix": prefix,
                            "entity_type": entity_type,
                            "jurisdiction": jur
                        }, indent=2))]

                    result = await self.executor.execute(query, jurisdiction=jur)
                    return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

                elif name == "io_jurisdiction_cli":
                    query = arguments["query"]

                    # Detect jurisdiction from operator (e.g., cuk: -> UK)
                    import re
                    match = re.match(r'^([a-z]+)([a-z]{2}):(.+)$', query.strip(), re.I)
                    if match:
                        jur = match.group(2).upper()
                    else:
                        jur = arguments.get("jurisdiction", "").upper()

                    if not jur:
                        return [TextContent(type="text", text=json.dumps({
                            "error": "Could not detect jurisdiction from query. Use format: cuk: CompanyName"
                        }))]

                    cli_class = get_jurisdiction_cli(jur)
                    if not cli_class:
                        return [TextContent(type="text", text=json.dumps({
                            "error": f"No CLI available for jurisdiction: {jur}"
                        }))]

                    try:
                        cli = cli_class()
                        result = await cli.execute(query)
                        return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
                    except Exception as e:
                        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

                # =============================================================
                # TORPEDO TOOLS
                # =============================================================
                elif name == "torpedo_search_cr":
                    if not TORPEDO_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO not available"}))]

                    sources_path = arguments.get("sources_path")
                    cr = None
                    if sources_path:
                        cr = CRSearcher()
                        await cr.load_sources(sources_path)
                    else:
                        await self._init_torpedo()
                        if not self.torpedo_cr:
                            return [TextContent(type="text", text=json.dumps({"error": "TORPEDO CR not available"}))]
                        cr = self.torpedo_cr

                    if not cr:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO CR not available"}))]

                    query = arguments["query"]
                    jur = (arguments.get("jurisdiction") or "GLOBAL").upper()
                    if jur == "GB":
                        jur = "UK"

                    max_sources = arguments.get("max_sources")
                    if max_sources is None:
                        max_sources = arguments.get("limit", 5)
                    max_sources = int(max_sources)

                    result = await cr.search(
                        query=query,
                        jurisdiction=jur,
                        max_sources=max_sources,
                        use_brightdata=bool(arguments.get("use_brightdata", False))
                    )

                    include_html = bool(arguments.get("include_html", False))
                    html_max_chars = int(arguments.get("html_max_chars", 2000))

                    if not include_html and isinstance(result, dict):
                        for r in result.get("results", []) or []:
                            if isinstance(r, dict):
                                r.pop("html", None)
                    elif include_html and html_max_chars > 0 and isinstance(result, dict):
                        for r in result.get("results", []) or []:
                            if isinstance(r, dict) and isinstance(r.get("html"), str):
                                r["html"] = r["html"][:html_max_chars]

                    return [TextContent(type="text", text=json.dumps({
                        "query": query,
                        "jurisdiction": jur,
                        "results": result
                    }, default=str, indent=2))]

                elif name == "torpedo_search_news":
                    if not TORPEDO_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO not available"}))]

                    sources_path = arguments.get("sources_path")
                    news = None
                    if sources_path:
                        news = NewsSearcher()
                        await news.load_sources(sources_path)
                    else:
                        await self._init_torpedo()
                        if not self.torpedo_news:
                            return [TextContent(type="text", text=json.dumps({"error": "TORPEDO News not available"}))]
                        news = self.torpedo_news

                    if not news:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO News not available"}))]

                    query = arguments["query"]
                    jur = (arguments.get("jurisdiction") or "GLOBAL").upper()
                    if jur == "GB":
                        jur = "UK"

                    max_sources = arguments.get("max_sources")
                    if max_sources is None:
                        max_sources = arguments.get("limit", 5)
                    max_sources = int(max_sources)

                    result = await news.search(
                        query=query,
                        jurisdiction=jur,
                        max_sources=max_sources,
                        max_pages=int(arguments.get("max_pages", 1)),
                        min_reliability=float(arguments.get("min_reliability", 0.0)),
                        extract=bool(arguments.get("extract", True)),
                        source_type=arguments.get("source_type"),
                        region=arguments.get("region"),
                        date_from=arguments.get("date_from"),
                        date_to=arguments.get("date_to"),
                        date_filter_only=bool(arguments.get("date_filter_only", False)),
                        scrape_method_filter=arguments.get("scrape_method_filter"),
                        require_recipe=bool(arguments.get("require_recipe", False)),
                    )

                    return [TextContent(type="text", text=json.dumps({
                        "query": query,
                        "jurisdiction": jur,
                        "results": result
                    }, default=str, indent=2))]

                elif name == "torpedo_list_jurisdictions":
                    if not TORPEDO_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO not available"}))]

                    source_type = arguments.get("source_type", "news")
                    sources_path = arguments.get("sources_path")
                    if sources_path:
                        path = Path(sources_path)
                    else:
                        path = news_sources_path() if source_type == "news" else corporate_registries_sources_path()

                    if not path.exists():
                        return [TextContent(type="text", text=json.dumps({"error": f"Sources file not found: {path}"}))]

                    data = json.load(open(path, encoding="utf-8"))
                    if not isinstance(data, dict):
                        return [TextContent(type="text", text=json.dumps({"error": f"Unsupported sources format in {path}"}))]

                    jurs = sorted({("UK" if k.upper() == "GB" else k.upper()) for k in data.keys()})
                    counts = {("UK" if k.upper() == "GB" else k.upper()): len(v) for k, v in data.items() if isinstance(v, list)}

                    return [TextContent(type="text", text=json.dumps({
                        "source_type": source_type,
                        "sources_path": str(path),
                        "jurisdictions": jurs,
                        "counts": counts
                    }, indent=2, default=str, ensure_ascii=False))]

                elif name == "torpedo_list_sources":
                    if not TORPEDO_AVAILABLE:
                        return [TextContent(type="text", text=json.dumps({"error": "TORPEDO not available"}))]

                    source_type = arguments.get("source_type", "news")
                    jurisdiction = (arguments.get("jurisdiction") or "").upper()
                    if jurisdiction == "GB":
                        jurisdiction = "UK"

                    query = (arguments.get("query") or "").strip().lower()
                    limit = int(arguments.get("limit", 50))
                    require_recipe = bool(arguments.get("require_recipe", False))
                    min_reliability = float(arguments.get("min_reliability", 0.0))

                    sources_path = arguments.get("sources_path")
                    if sources_path:
                        path = Path(sources_path)
                    else:
                        path = news_sources_path() if source_type == "news" else corporate_registries_sources_path()

                    if not path.exists():
                        return [TextContent(type="text", text=json.dumps({"error": f"Sources file not found: {path}"}))]

                    data = json.load(open(path, encoding="utf-8"))
                    if not isinstance(data, dict):
                        return [TextContent(type="text", text=json.dumps({"error": f"Unsupported sources format in {path}"}))]

                    out = []
                    for jur_key, sources_list in data.items():
                        jur_key_norm = jur_key.upper()
                        if jur_key_norm == "GB":
                            jur_key_norm = "UK"
                        if jurisdiction and jur_key_norm != jurisdiction:
                            continue
                        if not isinstance(sources_list, list):
                            continue

                        for s in sources_list:
                            if not isinstance(s, dict):
                                continue

                            if source_type == "news":
                                if float(s.get("reliability", 0.0) or 0.0) < min_reliability:
                                    continue
                                if require_recipe and not s.get("search_recipe"):
                                    continue

                            hay = " ".join([
                                str(s.get("name", "")),
                                str(s.get("domain", "")),
                                str(s.get("url", "")),
                                str(s.get("search_template") or s.get("search_url") or ""),
                            ]).lower()
                            if query and query not in hay:
                                continue

                            out.append({
                                "id": s.get("id"),
                                "name": s.get("name"),
                                "domain": s.get("domain"),
                                "jurisdiction": (s.get("jurisdiction") or jur_key_norm),
                                "template": s.get("search_template") or s.get("search_url"),
                                "scrape_method": s.get("scrape_method"),
                                "http_latency": s.get("http_latency"),
                                "needs_js": s.get("needs_js"),
                                "reliability": s.get("reliability"),
                                "has_recipe": bool(s.get("search_recipe")),
                                "category": s.get("category"),
                                "type": s.get("type"),
                            })

                            if len(out) >= limit:
                                break
                        if len(out) >= limit:
                            break

                    return [TextContent(type="text", text=json.dumps({
                        "source_type": source_type,
                        "sources_path": str(path),
                        "jurisdiction": jurisdiction or None,
                        "query": query or None,
                        "returned": len(out),
                        "sources": out
                    }, indent=2, default=str, ensure_ascii=False))]

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
    server = IOMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
