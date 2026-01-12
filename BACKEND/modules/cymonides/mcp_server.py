#!/usr/bin/env python3
"""
Cymonides MCP Server - 3-Tier Elasticsearch Index Management

Provides unified access to the Cymonides index hierarchy:
- C-1: Project node graph indices (cymonides-1-{projectId})
- C-2: Website contents from BRUTE search (cymonides-2)
- C-3: Common Crawl domain graph (cymonides_cc_domain_*)

Tools:
- Project management (create, list, delete, switch)
- Node operations (create, update, query nodes in C-1)
- Content search (C-2 website content)
- Graph queries (C-3 domain relationships)
- Unified search (across all tiers)

Usage:
    python mcp_server.py
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Add paths
CYMONIDES_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CYMONIDES_ROOT))
sys.path.insert(0, str(CYMONIDES_ROOT.parent))
sys.path.insert(0, "/data/CLASSES")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cymonides-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(CYMONIDES_ROOT.parent / "SASTRE" / ".env")
except ImportError:
    pass

# Elasticsearch
from elasticsearch import Elasticsearch

ES_HOST = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

# Index patterns
C1_PATTERN = "cymonides-1-"  # Project indices
C2_INDEX = "cymonides-2"      # Website contents
C3_VERTICES = "cymonides_cc_domain_vertices"  # CC domain vertices
C3_EDGES = "cymonides_cc_domain_edges"        # CC domain edges

# Import PROJECT module
try:
    from NARRATIVE.PROJECT import (
        create_project, delete_project, reset_project,
        get_project, get_active_project, set_active_project,
        list_projects, get_node_count, ensure_default_project,
        get_project_index, create_project_index, delete_project_index,
        list_project_indices,
    )
    PROJECT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PROJECT module not available: {e}")
    PROJECT_AVAILABLE = False

# Import Cymonides unified search
try:
    from cymonides_unified import CymonidesUnifiedSearch
    UNIFIED_AVAILABLE = True
except ImportError as e:
    logger.warning(f"CymonidesUnifiedSearch not available: {e}")
    UNIFIED_AVAILABLE = False

# Import Indexer toolkit
try:
    from indexer.mcp_tools import get_indexer_tools, create_indexer_handler, INDEXER_TOOLS
    INDEXER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Indexer toolkit not available: {e}")
    INDEXER_AVAILABLE = False


class CymonidesMCP:
    """Cymonides MCP Server - 3-Tier Index Management"""

    def __init__(self):
        self.server = Server("cymonides")
        self.es = Elasticsearch(ES_HOST)
        self.unified = CymonidesUnifiedSearch() if UNIFIED_AVAILABLE else None
        # Initialize indexer handler
        self.indexer_handler = create_indexer_handler(self.es) if INDEXER_AVAILABLE else None

        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            tools = [
                # === PROJECT MANAGEMENT (C-1) ===
                Tool(
                    name="project_create",
                    description="Create a new investigation project. Creates cymonides-1-{projectId} index.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Project name"},
                            "user_id": {"type": "integer", "default": 1, "description": "User ID"}
                        },
                        "required": ["name"]
                    }
                ),
                Tool(
                    name="project_list",
                    description="List all projects for a user.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "integer", "default": 1}
                        }
                    }
                ),
                Tool(
                    name="project_delete",
                    description="Delete a project and its index.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "Project ID to delete"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["project_id"]
                    }
                ),
                Tool(
                    name="project_reset",
                    description="Reset a project (delete all nodes but keep project).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["project_id"]
                    }
                ),
                Tool(
                    name="project_activate",
                    description="Set active project for a user.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["project_id"]
                    }
                ),

                # === NODE OPERATIONS (C-1) ===
                Tool(
                    name="node_create",
                    description="Create a node in the active project's graph.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "Project ID (or uses active)"},
                            "node_class": {"type": "string", "enum": ["entity", "narrative", "source", "query"]},
                            "node_type": {"type": "string", "description": "e.g., person, company, document, domain"},
                            "label": {"type": "string", "description": "Display label"},
                            "properties": {"type": "object", "description": "Additional properties"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["node_class", "node_type", "label"]
                    }
                ),
                Tool(
                    name="node_search",
                    description="Search nodes in a project's graph.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string", "description": "Project ID (or uses active)"},
                            "query": {"type": "string", "description": "Search query"},
                            "node_class": {"type": "string", "description": "Filter by class"},
                            "node_type": {"type": "string", "description": "Filter by type"},
                            "limit": {"type": "integer", "default": 50},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="node_get",
                    description="Get a specific node by ID.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "string"},
                            "node_id": {"type": "string"},
                            "user_id": {"type": "integer", "default": 1}
                        },
                        "required": ["node_id"]
                    }
                ),

                # === CONTENT SEARCH (C-2) ===
                Tool(
                    name="content_search",
                    description="Search website contents indexed from BRUTE (C-2). Full-text search on scraped pages.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "domain": {"type": "string", "description": "Filter by domain"},
                            "content_type": {"type": "string", "description": "Filter by content type"},
                            "limit": {"type": "integer", "default": 50}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="content_by_url",
                    description="Get content for a specific URL from C-2.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to retrieve"}
                        },
                        "required": ["url"]
                    }
                ),

                # === GRAPH QUERIES (C-3) ===
                Tool(
                    name="domain_lookup",
                    description="Lookup a domain in the Common Crawl graph (C-3).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Domain to lookup"},
                            "include_edges": {"type": "boolean", "default": False, "description": "Include linked domains"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="domain_links",
                    description="Get domains linked to/from a domain (C-3 edges).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string"},
                            "direction": {"type": "string", "enum": ["outbound", "inbound", "both"], "default": "both"},
                            "limit": {"type": "integer", "default": 100}
                        },
                        "required": ["domain"]
                    }
                ),

                # === UNIFIED SEARCH ===
                Tool(
                    name="search_all",
                    description="Search across all Cymonides tiers (C-1, C-2, C-3). Supports definitional, filters, rank, authority.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query with operators"},
                            "tiers": {"type": "array", "items": {"type": "string"}, "description": "Tiers to search: c1, c2, c3"},
                            "project_id": {"type": "string", "description": "C-1 project (if searching C-1)"},
                            "limit": {"type": "integer", "default": 50}
                        },
                        "required": ["query"]
                    }
                ),

                # === INGESTION & STRUCTURE ===
                Tool(
                    name="assess_structure",
                    description="Analyze content to determine structure, schema, and target index (C1/C2/C3).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Content snippet or full text"},
                            "source_type": {"type": "string", "description": "Origin (report, web, document)"},
                            "metadata": {"type": "object", "description": "Known metadata"}
                        },
                        "required": ["content"]
                    }
                ),
                Tool(
                    name="content_ingest",
                    description="Ingest content into specific index with defined structure.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "index": {"type": "string", "description": "Target index (e.g., cymonides-2)"},
                            "document": {"type": "object", "description": "Structured document to index"},
                            "id": {"type": "string", "description": "Optional explicit ID"}
                        },
                        "required": ["index", "document"]
                    }
                ),

                # === INDEX STATS ===
                Tool(
                    name="index_stats",
                    description="Get statistics for Cymonides indices.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tier": {"type": "string", "enum": ["c1", "c2", "c3", "all"], "default": "all"}
                        }
                    }
                ),
                # === INDEXER TOOLKIT ===
                # (Tools added dynamically below)
            ]
            
            # Add indexer tools if available
            if INDEXER_AVAILABLE:
                for tool_def in INDEXER_TOOLS:
                    tools.append(Tool(
                        name=tool_def["name"],
                        description=tool_def["description"],
                        inputSchema=tool_def["inputSchema"]
                    ))
            
            return tools


        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                result = await self._handle_tool(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
            except Exception as e:
                logger.error(f"Tool {name} error: {e}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _handle_tool(self, name: str, args: Dict) -> Any:
        """Route tool calls to handlers."""
        user_id = args.get("user_id", 1)

        
        # === INDEXER TOOLKIT ===
        if name.startswith("indexer_") and INDEXER_AVAILABLE and self.indexer_handler:
            return await self.indexer_handler.handle(name, args)

# === INGESTION & STRUCTURE ===
        if name == "assess_structure":
            content = args["content"]
            source_type = args.get("source_type", "unknown")
            
            # Simple Heuristics
            target_index = C2_INDEX # Default to content store
            schema_hint = "unstructured"
            
            # C1 Detection (Entity/Graph data)
            if isinstance(content, str) and (content.startswith("{") or "node_type" in content):
                target_index = f"{C1_PATTERN}active" # Placeholder
                schema_hint = "graph_node"
            elif source_type in ["report", "article", "web"]:
                target_index = C2_INDEX
                schema_hint = "content_document"
            
            return {
                "recommended_index": target_index,
                "schema_hint": schema_hint,
                "detected_type": source_type,
                "confidence": 0.8
            }

        elif name == "content_ingest":
            index = args["index"]
            doc = args["document"]
            doc_id = args.get("id")
            
            # Add timestamp if missing
            if "created_at" not in doc:
                doc["created_at"] = datetime.utcnow().isoformat()
                
            try:
                resp = self.es.index(index=index, document=doc, id=doc_id)
                return {
                    "success": True, 
                    "id": resp["_id"], 
                    "index": resp["_index"],
                    "result": resp["result"]
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # === PROJECT MANAGEMENT ===
        if name == "project_create":
            if not PROJECT_AVAILABLE:
                return {"error": "PROJECT module not available"}
            project = create_project(user_id, args["name"])
            return {"success": True, "project": project}

        elif name == "project_list":
            if not PROJECT_AVAILABLE:
                return {"error": "PROJECT module not available"}
            projects = list_projects(user_id)
            return {"projects": projects}

        elif name == "project_delete":
            if not PROJECT_AVAILABLE:
                return {"error": "PROJECT module not available"}
            delete_project(user_id, args["project_id"])
            return {"success": True, "deleted": args["project_id"]}

        elif name == "project_reset":
            if not PROJECT_AVAILABLE:
                return {"error": "PROJECT module not available"}
            reset_project(user_id, args["project_id"])
            return {"success": True, "reset": args["project_id"]}

        elif name == "project_activate":
            if not PROJECT_AVAILABLE:
                return {"error": "PROJECT module not available"}
            set_active_project(user_id, args["project_id"])
            return {"success": True, "active": args["project_id"]}

        # === NODE OPERATIONS ===
        elif name == "node_create":
            project_id = args.get("project_id")
            if not project_id and PROJECT_AVAILABLE:
                active = get_active_project(user_id)
                project_id = active.get("id") if active else None
            if not project_id:
                return {"error": "No project specified or active"}

            index = f"{C1_PATTERN}{project_id}"
            now = datetime.utcnow().isoformat()
            node_id = str(uuid.uuid4())
            label = args["label"]
            node = {
                # Canonical C-1 fields (see CLASSES/NARRATIVE/PROJECT/index_setup.py)
                "id": node_id,
                "className": args["node_class"],
                "typeName": args["node_type"],
                "label": label,
                "canonicalValue": str(label or "").upper(),
                "snippet": "",
                "userId": user_id,
                "projectId": project_id,
                "metadata": {},
                "properties": args.get("properties", {}),
                "embedded_edges": [],
                "createdAt": now,
                "updatedAt": now,
            }
            resp = self.es.index(index=index, id=node_id, document=node, refresh=True)
            node["id"] = resp["_id"]
            return {"success": True, "node": node, "index": index}

        elif name == "node_search":
            project_id = args.get("project_id")
            if not project_id and PROJECT_AVAILABLE:
                active = get_active_project(user_id)
                project_id = active.get("id") if active else None
            if not project_id:
                return {"error": "No project specified or active"}

            index = f"{C1_PATTERN}{project_id}"
            query_body = {
                "bool": {
                    "must": [{
                        "multi_match": {
                            "query": args["query"],
                            "fields": ["label^3", "canonicalValue^2", "snippet", "properties.*", "metadata.*"]
                        }
                    }]
                }
            }
            if args.get("node_class"):
                query_body["bool"]["filter"] = query_body["bool"].get("filter", [])
                query_body["bool"]["filter"].append({"term": {"className": args["node_class"]}})
            if args.get("node_type"):
                query_body["bool"]["filter"] = query_body["bool"].get("filter", [])
                query_body["bool"]["filter"].append({"term": {"typeName": args["node_type"]}})

            resp = self.es.search(index=index, query=query_body, size=args.get("limit", 50))
            nodes = [{"id": h["_id"], "score": h.get("_score"), **h["_source"]} for h in resp["hits"]["hits"]]
            return {"total": resp["hits"]["total"]["value"], "nodes": nodes}

        elif name == "node_get":
            project_id = args.get("project_id")
            if not project_id and PROJECT_AVAILABLE:
                active = get_active_project(user_id)
                project_id = active.get("id") if active else None
            if not project_id:
                return {"error": "No project specified or active"}

            index = f"{C1_PATTERN}{project_id}"
            try:
                resp = self.es.get(index=index, id=args["node_id"])
                return {"node": {"id": resp["_id"], **resp["_source"]}}
            except Exception:
                return {"error": "Node not found"}

        # === CONTENT SEARCH (C-2) ===
        elif name == "content_search":
            query_body = {"bool": {"must": [{"multi_match": {"query": args["query"], "fields": ["content", "title^2", "url"]}}]}}
            if args.get("domain"):
                query_body["bool"]["filter"] = [{"term": {"domain": args["domain"]}}]
            if args.get("content_type"):
                query_body["bool"]["filter"] = query_body["bool"].get("filter", [])
                query_body["bool"]["filter"].append({"term": {"content_type": args["content_type"]}})

            resp = self.es.search(index=C2_INDEX, query=query_body, size=args.get("limit", 50))
            results = [{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]
            return {"total": resp["hits"]["total"]["value"], "results": results}

        elif name == "content_by_url":
            url = args["url"]
            resp = self.es.search(
                index=C2_INDEX,
                query={
                    "bool": {
                        "should": [
                            {"term": {"url.keyword": url}},
                            {"term": {"source_url.keyword": url}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                size=1,
            )
            if resp["hits"]["hits"]:
                h = resp["hits"]["hits"][0]
                return {"found": True, "content": {"id": h["_id"], **h["_source"]}}
            return {"found": False}

        # === GRAPH QUERIES (C-3) ===
        elif name == "domain_lookup":
            resp = self.es.search(index=C3_VERTICES, query={"term": {"domain.keyword": args["domain"]}}, size=1)
            if not resp["hits"]["hits"]:
                return {"found": False}
            vertex = resp["hits"]["hits"][0]["_source"]
            result = {"found": True, "domain": vertex}

            if args.get("include_edges"):
                edges_resp = self.es.search(
                    index=C3_EDGES,
                    query={"bool": {"should": [
                        {"term": {"source.keyword": args["domain"]}},
                        {"term": {"target.keyword": args["domain"]}}
                    ]}},
                    size=100
                )
                result["edges"] = [h["_source"] for h in edges_resp["hits"]["hits"]]
            return result

        elif name == "domain_links":
            domain = args["domain"]
            direction = args.get("direction", "both")
            limit = args.get("limit", 100)

            query_clauses = []
            if direction in ["outbound", "both"]:
                query_clauses.append({"term": {"source.keyword": domain}})
            if direction in ["inbound", "both"]:
                query_clauses.append({"term": {"target.keyword": domain}})

            resp = self.es.search(
                index=C3_EDGES,
                query={"bool": {"should": query_clauses}},
                size=limit
            )
            edges = [h["_source"] for h in resp["hits"]["hits"]]

            # Extract unique domains
            linked = set()
            for e in edges:
                if e.get("source") != domain:
                    linked.add(e["source"])
                if e.get("target") != domain:
                    linked.add(e["target"])

            return {"domain": domain, "edge_count": len(edges), "linked_domains": list(linked)[:limit], "edges": edges}

        # === UNIFIED SEARCH ===
        elif name == "search_all":
            query = args["query"]
            limit = int(args.get("limit", 50) or 50)
            tiers = [t.lower() for t in (args.get("tiers") or ["c1", "c2", "c3"]) if isinstance(t, str)]
            tiers = tiers or ["c1", "c2", "c3"]

            start_time = time.time()
            by_tier: Dict[str, Any] = {}
            combined: List[Dict[str, Any]] = []

            # --- C-1 (project graph) ---
            if "c1" in tiers:
                project_id = args.get("project_id")
                if not project_id and PROJECT_AVAILABLE:
                    active = get_active_project(user_id)
                    project_id = active.get("id") if active else None

                if project_id:
                    index = f"{C1_PATTERN}{project_id}"
                    c1_query = {
                        "bool": {
                            "must": [{
                                "multi_match": {
                                    "query": query,
                                    "fields": ["label^3", "canonicalValue^2", "snippet", "properties.*", "metadata.*"]
                                }
                            }]
                        }
                    }
                    resp = self.es.search(index=index, query=c1_query, size=limit)
                    hits = resp.get("hits", {}).get("hits", [])
                    c1_results = [{
                        "tier": "c1",
                        "index": index,
                        "id": h["_id"],
                        "score": h.get("_score"),
                        "doc": h.get("_source", {}),
                    } for h in hits]
                    by_tier["c1"] = {"total": resp["hits"]["total"]["value"], "results": c1_results}
                    combined.extend(c1_results)
                else:
                    by_tier["c1"] = {"error": "No project specified or active", "results": []}

            # --- C-2 (content corpus) ---
            if "c2" in tiers:
                c2_query = {
                    "bool": {
                        "must": [{
                            "multi_match": {
                                "query": query,
                                "fields": ["content", "raw_content", "title^2", "label^2", "snippet", "url", "source_url", "domain", "source_domain"],
                            }
                        }]
                    }
                }
                resp = self.es.search(index=C2_INDEX, query=c2_query, size=limit)
                hits = resp.get("hits", {}).get("hits", [])
                c2_results = [{
                    "tier": "c2",
                    "index": C2_INDEX,
                    "id": h["_id"],
                    "score": h.get("_score"),
                    "doc": h.get("_source", {}),
                } for h in hits]
                by_tier["c2"] = {"total": resp["hits"]["total"]["value"], "results": c2_results}
                combined.extend(c2_results)

            # --- C-3 (domain graph) ---
            if "c3" in tiers:
                # Heuristic: if query looks like a domain, prioritize exact/wildcard on domain.keyword
                q = query.strip().lower()
                looks_like_domain = "." in q and " " not in q and len(q) <= 255
                c3_should = []
                if looks_like_domain:
                    c3_should.extend([
                        {"term": {"domain.keyword": q}},
                        {"wildcard": {"domain.keyword": f"*{q}*"}},
                    ])
                c3_should.append({"match": {"domain": {"query": query}}})

                resp = self.es.search(
                    index=C3_VERTICES,
                    query={"bool": {"should": c3_should, "minimum_should_match": 1}},
                    size=min(limit, 50),
                )
                hits = resp.get("hits", {}).get("hits", [])
                c3_results = [{
                    "tier": "c3",
                    "index": C3_VERTICES,
                    "id": h["_id"],
                    "score": h.get("_score"),
                    "doc": h.get("_source", {}),
                } for h in hits]
                by_tier["c3"] = {"total": resp["hits"]["total"]["value"], "results": c3_results}
                combined.extend(c3_results)

                # Also include operator/unified search results when available (rank/authority/location/etc.)
                if UNIFIED_AVAILABLE and self.unified:
                    try:
                        u = self.unified.search(query, limit=limit)
                        unified_results = [{
                            "tier": "unified",
                            "index": r.get("source_index"),
                            "id": r.get("id"),
                            "score": r.get("score"),
                            "doc": r,
                        } for r in (u.results or [])]
                        by_tier["unified"] = {
                            "total": u.total,
                            "results": unified_results,
                            "sources_queried": u.sources_queried,
                            "timing_ms": u.timing_ms,
                        }
                        combined.extend(unified_results)
                    except Exception as e:
                        by_tier["unified"] = {"error": str(e), "results": []}

            timing_ms = round((time.time() - start_time) * 1000, 2)
            return {
                "query": query,
                "tiers": tiers,
                "total": len(combined),
                "results": combined[:limit],
                "by_tier": by_tier,
                "timing_ms": timing_ms,
            }

        # === INDEX STATS ===
        elif name == "index_stats":
            tier = args.get("tier", "all")
            stats = {}

            if tier in ["c1", "all"]:
                c1_indices = list_project_indices() if PROJECT_AVAILABLE else []
                c1_docs = 0
                for idx in c1_indices:
                    try:
                        count = self.es.count(index=idx)["count"]
                        c1_docs += count
                    except Exception:
                        pass
                stats["c1"] = {"indices": len(c1_indices), "total_docs": c1_docs, "indices_list": c1_indices}

            if tier in ["c2", "all"]:
                try:
                    c2_count = self.es.count(index=C2_INDEX)["count"]
                    stats["c2"] = {"docs": c2_count}
                except Exception:
                    stats["c2"] = {"error": "index not found"}

            if tier in ["c3", "all"]:
                try:
                    vertices = self.es.count(index=C3_VERTICES)["count"]
                    edges = self.es.count(index=C3_EDGES)["count"]
                    stats["c3"] = {"vertices": vertices, "edges": edges}
                except Exception:
                    stats["c3"] = {"error": "indices not found"}

            return stats

        return {"error": f"Unknown tool: {name}"}

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
    server = CymonidesMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
