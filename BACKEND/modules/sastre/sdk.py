"""
SASTRE Agent SDK v2 - Official Claude Agent SDK Integration

Migrated from raw anthropic API to official claude-agent-sdk.
Uses @tool decorators, create_sdk_mcp_server, and ClaudeSDKClient.

AGENTS (4):
- orchestrator: Coordinates investigation loop
- investigator: Discovery & enrichment via syntax
- writer: Document streaming (watchers)
- disambiguator: Collision resolution (FUSE/REPEL/BINARY_STAR)

TOOLS (5):
- execute: Universal query router
- assess: Grid state assessment (4 perspectives)
- get_watchers: Active document sections
- stream_finding: Write to document
- resolve: Apply disambiguation decision

Plus:
- create_watcher: Create a new watcher/section
- toggle_auto_scribe: Toggle EDITH auto-scribe mode
- EDITH tools: rewrite/answer/edit/template/read_url
- TORPEDO tools: search/process/template
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Add SASTRE to path for local imports
_sastre_dir = Path(__file__).resolve().parent
_repo_root = _sastre_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Add TORPEDO backend path
_torpedo_backend = Path("/data/SEARCH_ENGINEER/nexus/BACKEND")
if _torpedo_backend.exists():
    sys.path.insert(0, str(_torpedo_backend))

# Official Claude Agent SDK imports
from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)

# Local imports
try:
    from modules.syntax.executor import execute as unified_execute
    from .tools.query_lab_tools import build_fused_query_handler
    from .template_loader import compose_report_template, get_writing_style
except ImportError:
    # Fallback if running as script
    from modules.syntax.executor import execute as unified_execute
    from modules.sastre.tools.query_lab_tools import build_fused_query_handler
    from modules.sastre.template_loader import compose_report_template, get_writing_style

# Optional: EYE-D OSINT bridge (direct, no MCP required)
try:
    from .bridges.eyed_osint import EyedOsintBridge, EyedOsintError
    EYED_OSINT_AVAILABLE = True
except Exception:  # pragma: no cover
    EyedOsintBridge = None  # type: ignore[assignment]
    EyedOsintError = Exception  # type: ignore[assignment]
    EYED_OSINT_AVAILABLE = False

# Import Aggregator Agents
try:
    from SEARCH_ENGINEER.BACKEND.modules.biographer.agent import BiographerAgent
    from SEARCH_ENGINEER.BACKEND.modules.alldom.agent import AlldomAgent
    from SUBMARINE.agent import SubmarineAgent
    AGGREGATORS_AVAILABLE = True
except ImportError:
    AGGREGATORS_AVAILABLE = False

# Optional mined context
try:
    from .mined_context import get_writer_context
    MINED_CONTEXT_AVAILABLE = True
except ImportError:
    MINED_CONTEXT_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sastre-v2")


# Agent and Tool classes for backward compatibility with agents/*.py
@dataclass
class Agent:
    """Agent definition for subagent modules."""
    name: str
    model: str
    system_prompt: str
    tools: List[Any] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    model: str
    system_prompt: str
    mcp_server: Any = None
    allowed_tools: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)


@dataclass
class Tool:
    """Tool definition for agents."""
    name: str
    description: str
    handler: Optional[Any] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)



# =============================================================================
# CONFIGURATION
# =============================================================================

CYMONIDES_API = os.getenv("CYMONIDES_API", "http://localhost:3001/api/graph")
WATCHER_API = os.getenv("WATCHER_API", "http://localhost:3001/api/graph/watchers")

_WATCHER_BRIDGE = None


def _get_watcher_bridge():
    """Load WatcherBridge from SASTRE/bridges.py (file, not package) and cache an instance."""
    global _WATCHER_BRIDGE
    if _WATCHER_BRIDGE is not None:
        return _WATCHER_BRIDGE

    import importlib.util

    bridges_file = Path(__file__).resolve().parent / "bridges.py"
    spec = importlib.util.spec_from_file_location("_sastre_bridges_file", bridges_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load WatcherBridge from {bridges_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bridge_cls = getattr(module, "WatcherBridge", None)
    if bridge_cls is None:
        raise RuntimeError(f"WatcherBridge not found in {bridges_file}")
    _WATCHER_BRIDGE = bridge_cls()
    return _WATCHER_BRIDGE


def _build_mcp_env() -> Dict[str, str]:
    """Build a stable environment for spawned MCP stdio servers."""
    extra_paths = [
        "/data",
        "/data/CLASSES",
        "/data/CLASSES/NARRATIVE",  # EDITH home
        "/data/SEARCH_ENGINEER/BACKEND",
        "/data/SEARCH_ENGINEER/BACKEND/modules",
        "/data/SEARCH_ENGINEER/nexus/BACKEND",
        "/data/SEARCH_ENGINEER/nexus/BACKEND/modules",
    ]
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = ":".join([p for p in extra_paths + ([existing] if existing else []) if p])

    env: Dict[str, str] = {"PYTHONPATH": pythonpath}
    passthrough = [
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "BING_API_KEY",
        "ELASTICSEARCH_URL",
        "NODE_API_BASE_URL",
        "CYMONIDES_API",
        "WATCHER_API",
        "FIRECRAWL_API_KEY",
        "BRIGHTDATA_API_KEY",
    ]
    for key in passthrough:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _build_brute_env() -> Dict[str, str]:
    """Build an environment for running BRUTE without `modules` import collisions.

    BRUTE's core code imports `modules.brute...` and relies on the repo-root
    namespace package (`/data/modules` symlink). Some backends ship a *regular*
    `modules` package (with `__init__.py`) that can shadow this namespace when
    present on PYTHONPATH. For BRUTE subprocess calls we intentionally keep the
    path minimal.
    """
    extra_paths = [
        "/data",
        "/data/CLASSES",
    ]
    pythonpath = ":".join([p for p in extra_paths if p])

    env: Dict[str, str] = {"PYTHONPATH": pythonpath}
    passthrough = [
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "BING_API_KEY",
        "ELASTICSEARCH_URL",
        "NODE_API_BASE_URL",
        "CYMONIDES_API",
        "WATCHER_API",
        "FIRECRAWL_API_KEY",
        "BRIGHTDATA_API_KEY",
    ]
    for key in passthrough:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _external_mcp_servers() -> Dict[str, Any]:
    """External (stdio) MCP servers available in this repo."""
    env = _build_mcp_env()

    def stdio_server(script_path: str, *, key: str) -> Optional[Dict[str, Any]]:
        path = Path(script_path)
        if not path.exists():
            return None
        return {
            "type": "stdio",
            "command": "python3",
            "args": [str(path)],
            "env": env,
        }

    servers: Dict[str, Any] = {}
    candidates = [
        ("submarine", "/data/SUBMARINE/mcp_server.py"),
        ("brute", "/data/BRUTE/brute_mcp_server.py"),
        ("linklater", "/data/LINKLATER/mcp_server.py"),
        ("cymonides", "/data/CYMONIDES/mcp_server.py"),
        ("torpedo_mcp", "/data/TORPEDO/mcp_server.py"),
        ("matrix", "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/io_mcp_v2.py"),
        ("edith_templates", "/data/CLASSES/NARRATIVE/EDITH/templates/edith_mcp.py"),
        ("eyed", "/data/EYE-D/mcp_server.py"),
        ("corporella", "/data/CORPORELLA/mcp_server.py"),
        ("corporella_gdrive", "/data/CORPORELLA/gdrive_mcp_server.py"),
        ("corporella_archive_gdrive", "/data/corporella_archive/gdrive_mcp_server.py"),
        ("socialite", "/data/SOCIALITE/mcp_server.py"),
    ]

    for key, path in candidates:
        cfg = stdio_server(path, key=key)
        if cfg:
            servers[key] = cfg

    return servers


def get_orchestrator_mcp_servers() -> Dict[str, Any]:
    """MCP server surface for the chief SASTRE orchestrator."""
    servers: Dict[str, Any] = {
        # In-process SDK MCP servers (fast, shared state)
        "orchestrator": orchestrator_server,
        "nexus": nexus_server,  # NEXUS replaces investigator
        "writer": writer_server,
        "disambiguator": disambiguator_server,
        "edith": edith_server,
        "torpedo": torpedo_server,
    }

    enable_external = os.getenv("SASTRE_ENABLE_EXTERNAL_MCPS", "1").strip().lower() not in {"0", "false", "no"}
    if enable_external:
        servers.update(_external_mcp_servers())
    return servers


# =============================================================================
# HTTP HELPERS
# =============================================================================

async def _http_get(url: str, params: Dict = None) -> Dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status >= 400:
                return {"error": f"HTTP {resp.status}"}
            return await resp.json()


async def _http_post(url: str, data: Dict) -> Dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status >= 400:
                return {"error": f"HTTP {resp.status}"}
            return await resp.json()


# =============================================================================
# TOOLS - Using @tool decorator (Official SDK Pattern)
# =============================================================================

_CYMONIDES_BRIDGE = None

def _get_cymonides_bridge():
    """Load CymonidesBridge from SASTRE/bridges.py."""
    global _CYMONIDES_BRIDGE
    if _CYMONIDES_BRIDGE is not None:
        return _CYMONIDES_BRIDGE

    import importlib.util
    bridges_file = Path(__file__).resolve().parent / "bridges.py"
    spec = importlib.util.spec_from_file_location("_sastre_bridges_file", bridges_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bridge_cls = getattr(module, "CymonidesBridge", None)
    if bridge_cls is None:
        raise RuntimeError("CymonidesBridge not found")
    _CYMONIDES_BRIDGE = bridge_cls()
    return _CYMONIDES_BRIDGE


@tool(
    "process_finding",
    "Process a finding: create Kernel Node, link source/tags, and stream to document.",
    {
        "watcher_id": str,
        "kernel": str,
        "quote": str,
        "source_url": str,
        "analysis": str,
        "tags": List[str],
        "reasoning": str
    }
)
async def process_finding_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Process finding with graph integration."""
    try:
        cymonides = _get_cymonides_bridge()
        watcher = _get_watcher_bridge()
        
        watcher_id = args["watcher_id"]
        kernel = args["kernel"]
        quote = args["quote"]
        source_url = args["source_url"]
        tags = args.get("tags", [])
        
        # 1. Create Kernel Node
        kernel_node_id = await cymonides._remote_client.create_node(
            project_id="default",  # Should get from watcher context
            label=kernel[:50],     # Short label
            node_type="narrative",
            node_class="kernel",
            properties={
                "content": kernel,
                "quote": quote,
                "analysis": args.get("analysis", ""),
                "reasoning": args.get("reasoning", "")
            }
        )
        
        # 2. Resolve Source Node & Link
        # (Simplified: Just assume we link to a Source node if we can find/create it)
        # For now, we skip explicit Source Node creation to save time, relying on the property
        
        # 3. Link Tags
        for tag in tags:
            # Create/Get Tag Node
            tag_id = await cymonides._remote_client.create_node(
                project_id="default",
                label=tag,
                node_type="tag",
                node_class="meta"
            )
            # Link Kernel -> Tag
            await cymonides._remote_client.create_edge(
                project_id="default",
                from_node=kernel_node_id,
                to_node=tag_id,
                relation="TAGGED"
            )

        # 4. Stream to Document
        # Fetch watcher to get doc ID
        w = await watcher.get(watcher_id)
        doc_id = w.get("parentDocumentId")
        header = w.get("name")
        
        if doc_id and header:
            # Format text for document
            text = f"{kernel}\n> \"{quote}\"\n"
            if tags:
                text += f"[{', '.join(tags)}]\n"
            
            await watcher.stream_finding_to_section(
                document_id=doc_id,
                section_title=header,
                finding_text=text,
                source_url=source_url
            )
            
        return {"content": [{"type": "text", "text": json.dumps({
            "success": True,
            "kernel_id": kernel_node_id,
            "tags": tags
        })}]}

    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "execute",
    "Execute any investigation query using operator syntax. Supports IO prefixes, link analysis, entity extraction, and archive queries.",
    {"query": str, "project_id": str}
)
async def execute_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute query via unified executor."""
    query = args["query"]
    project_id = args.get("project_id", "default")
    logger.info(f"Execute: {query}")

    try:
        result = await unified_execute(query, project_id)
        return {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "is_error": True
        }


@tool(
    "query_lab_build",
    "Build a fused query from intent and knowns. Use for complex logic.",
    {
        "intent": str,
        "ku_quadrant": str,
        "subject_name": str,
        "location_domain": str,
        "location_jurisdiction": str,
        "expected_terms": List[str],
    }
)
async def query_lab_build_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Build fused query via Query Lab."""
    try:
        result = build_fused_query_handler(
            intent=args.get("intent", ""),
            ku_quadrant=args.get("ku_quadrant", ""),
            subject_name=args.get("subject_name", ""),
            location_domain=args.get("location_domain", ""),
            location_jurisdiction=args.get("location_jurisdiction", ""),
            expected_terms=args.get("expected_terms", []),
        )
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "assess",
    "Get four-centric grid assessment: NARRATIVE, SUBJECT, LOCATION, NEXUS. Use to identify gaps.",
    {"project_id": str, "mode": str}
)
async def assess_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get grid assessment from Cymonides."""
    project_id = args["project_id"]
    mode = args.get("mode", "all")

    mode_to_class = {
        "narrative": "narrative",
        "subject": "entity",
        "location": "source",
        "nexus": None,
    }

    def build_params(m: str) -> Dict:
        params = {"projectId": project_id, "limit": 100}
        if mode_to_class.get(m):
            params["primaryClassName"] = mode_to_class[m]
        return params

    try:
        if mode == "all":
            results = {}
            for m in ["narrative", "subject", "location", "nexus"]:
                results[m] = await _http_get(f"{CYMONIDES_API}/rotate", build_params(m))
            return {"content": [{"type": "text", "text": json.dumps(results, default=str)}]}

        result = await _http_get(f"{CYMONIDES_API}/rotate", build_params(mode))
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "get_watchers",
    "Get active watchers (document sections waiting for content).",
    {"project_id": str}
)
async def get_watchers_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get active watchers."""
    project_id = args["project_id"]

    try:
        watcher = _get_watcher_bridge()
        watchers = await watcher.list_active(project_id)
        return {"content": [{"type": "text", "text": json.dumps({"watchers": watchers}, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "create_watcher",
    "Create a new watcher for a topic, entity, or event.",
    {"project_id": str, "type": str, "query": str, "label": str}
)
async def create_watcher_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new watcher."""
    project_id = args["project_id"]
    watcher_type = args.get("type", "generic") # generic, entity, topic, event
    query = args["query"]
    label = args.get("label", query)

    try:
        watcher = _get_watcher_bridge()

        watcher_type_norm = str(watcher_type or "generic").strip().lower()
        if watcher_type_norm in ("generic", "watcher", "basic"):
            result = await watcher.create(name=label, project_id=project_id, query=query)
        elif watcher_type_norm in ("entity", "entities"):
            result = await watcher.create_entity_watcher(
                project_id=project_id,
                label=label,
                monitored_names=[query],
            )
        elif watcher_type_norm in ("topic", "topics"):
            result = await watcher.create_topic_watcher(
                project_id=project_id,
                label=label,
                monitored_topic=query,
            )
        elif watcher_type_norm in ("event", "events"):
            result = await watcher.create_event_watcher(
                project_id=project_id,
                monitored_event=query,
                label=label,
            )
        else:
            result = await watcher.create(name=label, project_id=project_id, query=query)

        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "activate_headers",
    "Convert all headers in a document into active watchers. Supports context injection via context{...} and trigger filters via {IF: \"...\"}.",
    {"document_id": str}
)
async def activate_headers_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Convert headers to watchers with context and trigger parsing."""
    document_id = args["document_id"]
    
    try:
        # Load document content via EdithBService
        try:
            from EDITH.edith_b.service import EdithBService
            edith_service = EdithBService()
            doc = edith_service.store.fetch_one("SELECT * FROM documents WHERE id = ?", [document_id])
            if not doc:
                return {"content": [{"type": "text", "text": f"Error: Document {document_id} not found"}]}
            content = doc.get("markdown") or ""
            project_id = doc.get("project_id") or "default"
        except ImportError:
             return {"content": [{"type": "text", "text": "Error: EDITH service not available"}]}

        watcher_bridge = _get_watcher_bridge()
        created_watchers = []
        
        lines = content.split('\n')
        current_block = []
        
        async def process_block(block):
            if not block:
                return
            
            # 1. Detect Header
            # Support optional \w or /w suffix for explicit watcher marking
            header_match = re.match(r"^(#{1,6})\s+(.+?)(\s*[\\/]w)?$", header_line)
            if not header_match:
                return
            
            header_title = header_match.group(2).strip()
            # If explicit marker (\w) is present, we definitely create.
            # If not, we still create (default behavior of this tool), but stripping ensures clean names.
            
            # Scan block for directives
            trigger = None
            context_ids = []
            
            for line in block[1:]:
                line = line.strip()
                # Trigger: {IF: "pattern"}
                trig_match = re.match(r"^\{IF:\s*[\"'](.+?)[\"']\}$", line, re.IGNORECASE)
                if trig_match:
                    trigger = trig_match.group(1)
                
                # Context: context{id1, id2}
                ctx_match = re.match(r"^context\{(.+?)\}$", line, re.IGNORECASE)
                if ctx_match:
                    parts = [p.strip() for p in re.split(r"[,|]", ctx_match.group(1))]
                    for part in parts:
                        tid = part.split(":", 1)[1].strip() if ":" in part else part
                        if tid: context_ids.append(tid)

            # Create Watcher
            w = await watcher_bridge.create(
                name=header_title,
                project_id=project_id,
                query=header_title,
                parent_document_id=document_id,
                trigger=trigger
            )
            
            if w and not w.get("error"):
                wid = w.get("id") or w.get("watcherId")
                # Add Context
                added = []
                if wid:
                    for cid in context_ids:
                        try:
                            await watcher_bridge.add_context(wid, cid)
                            added.append(cid)
                        except Exception:
                            pass
                w["_context_added"] = added
                w["_trigger"] = trigger
                created_watchers.append(w)

        # Loop lines
        for line in lines:
            if re.match(r"^(#{1,6})\s+", line):
                # New header found, process previous block
                if current_block:
                    await process_block(current_block)
                current_block = [line]
            else:
                if current_block:
                    current_block.append(line)
        
        # Process last block
        if current_block:
            await process_block(current_block)

        return {
            "content": [{
                "type": "text", 
                "text": json.dumps({
                    "success": True, 
                    "watchers_created": len(created_watchers),
                    "watchers": created_watchers
                }, default=str)
            }]
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        return {
            "content": [{
                "type": "text", 
                "text": json.dumps({
                    "success": True, 
                    "watchers_created": len(created_watchers),
                    "watchers": created_watchers
                }, default=str)
            }]
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "watcher_update_status",
    "Update the status of a watcher (active, paused, archived).",
    {"watcher_id": str, "status": str}
)
async def watcher_update_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update watcher status."""
    try:
        watcher = _get_watcher_bridge()
        result = await watcher.update_status(args["watcher_id"], args["status"])
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "watcher_toggle",
    "Toggle a watcher on/off (active/paused).",
    {"watcher_id": str}
)
async def watcher_toggle_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle watcher status."""
    try:
        watcher = _get_watcher_bridge()
        result = await watcher.toggle(args["watcher_id"])
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "watcher_delete",
    "Delete a watcher permanently.",
    {"watcher_id": str}
)
async def watcher_delete_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete watcher."""
    try:
        watcher = _get_watcher_bridge()
        result = await watcher.delete(args["watcher_id"])
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "stream_finding",
    "Stream a finding to a document section via its watcher.",
    {"watcher_id": str, "content": str, "source_url": str}
)
async def stream_finding_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Stream finding to document section."""
    watcher_id = args["watcher_id"]
    content = args["content"]
    source_url = args.get("source_url")

    try:
        watcher = _get_watcher_bridge()

        watcher_obj = await watcher.get(watcher_id)
        if watcher_obj is None:
            watcher_obj = await watcher.get_watcher(watcher_id)

        if watcher_obj is None:
            return {
                "content": [{"type": "text", "text": f"Error: watcher not found ({watcher_id})"}],
                "is_error": True,
            }

        section_title = (
            watcher_obj.get("header")
            or watcher_obj.get("name")
            or watcher_obj.get("label")
            or watcher_obj.get("title")
        )
        document_id = (
            watcher_obj.get("parentDocumentId")
            or watcher_obj.get("parent_document_id")
            or watcher_obj.get("documentId")
            or watcher_obj.get("document_id")
            or watcher_obj.get("noteId")
            or watcher_obj.get("note_id")
        )

        if not section_title or not document_id:
            return {
                "content": [{"type": "text", "text": json.dumps({
                    "error": "Watcher missing document linkage",
                    "watcher_id": watcher_id,
                    "keys": sorted(list(watcher_obj.keys())),
                    "watcher": watcher_obj,
                }, default=str)}],
                "is_error": True,
            }

        ok = await watcher.stream_finding_to_section(
            document_id=document_id,
            section_title=section_title,
            finding_text=content,
            source_url=source_url,
        )

        return {"content": [{"type": "text", "text": json.dumps({
            "success": bool(ok),
            "watcher_id": watcher_id,
            "document_id": document_id,
            "section_title": section_title,
        }, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "pacman_watch_register",
    "Register a temporary PACMAN watcher spec (targets + order) for SUBMARINE missions.",
    {
        "watcher_id": str,
        "submarine_order": str,
        "domain_count": int,
        "ttl_seconds": int,
        "targets": List[Dict[str, Any]],
        "registry_path": str,
    },
)
async def pacman_watch_register_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    watcher_id = str(args["watcher_id"]).strip()
    submarine_order = str(args.get("submarine_order") or "").strip()
    domain_count = args.get("domain_count")
    ttl_seconds = args.get("ttl_seconds")
    registry_path = str(args.get("registry_path") or "").strip()
    targets_raw = args.get("targets") or []

    try:
        from PACMAN.watcher_registry import (
            DEFAULT_REGISTRY_PATH,
            ExtractionTarget,
            WatcherSpec,
            default_targets,
            register_watcher,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: PACMAN watcher registry unavailable: {e}"}], "is_error": True}

    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH

    targets: List[ExtractionTarget] = []
    for t in targets_raw:
        if isinstance(t, str):
            targets.append(ExtractionTarget(name=t))
            continue
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        targets.append(
            ExtractionTarget(
                name=name,
                mode=str(t.get("mode") or "builtin"),
                pattern=t.get("pattern"),
                flags=str(t.get("flags") or "i"),
                group=int(t.get("group") or 0),
                max_hits=int(t.get("max_hits") or 20),
                instruction=t.get("instruction"),
            )
        )

    if not targets:
        targets = default_targets()

    spec = WatcherSpec(
        watcher_id=watcher_id,
        submarine_order=submarine_order,
        domain_count=int(domain_count) if domain_count is not None else None,
        ttl_seconds=int(ttl_seconds) if ttl_seconds is not None else 6 * 60 * 60,
        targets=targets,
    )

    try:
        register_watcher(spec, path)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: failed to register watcher: {e}"}], "is_error": True}

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "success": True,
                        "watcher_id": watcher_id,
                        "registry_path": str(path),
                        "targets": [t.__dict__ for t in targets],
                    },
                    indent=2,
                    default=str,
                ),
            }
        ]
    }


@tool(
    "pacman_watch_get",
    "Get a PACMAN watcher spec by watcher_id.",
    {"watcher_id": str, "registry_path": str},
)
async def pacman_watch_get_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    watcher_id = str(args["watcher_id"]).strip()
    registry_path = str(args.get("registry_path") or "").strip()

    try:
        from PACMAN.watcher_registry import DEFAULT_REGISTRY_PATH, get_watcher
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: PACMAN watcher registry unavailable: {e}"}], "is_error": True}

    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
    spec = get_watcher(watcher_id, path)
    return {"content": [{"type": "text", "text": json.dumps({"watcher": spec.__dict__ if spec else None}, indent=2, default=str)}]}


@tool(
    "pacman_watch_unregister",
    "Unregister a PACMAN watcher spec (cleanup after a mission).",
    {"watcher_id": str, "registry_path": str},
)
async def pacman_watch_unregister_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    watcher_id = str(args["watcher_id"]).strip()
    registry_path = str(args.get("registry_path") or "").strip()

    try:
        from PACMAN.watcher_registry import DEFAULT_REGISTRY_PATH, unregister_watcher
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: PACMAN watcher registry unavailable: {e}"}], "is_error": True}

    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
    try:
        unregister_watcher(watcher_id, path)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: failed to unregister watcher: {e}"}], "is_error": True}
    return {"content": [{"type": "text", "text": json.dumps({"success": True, "watcher_id": watcher_id, "registry_path": str(path)}, indent=2)}]}


@tool(
    "pacman_watch_extract",
    "Run PACMAN extraction for a registered watcher spec against provided content.",
    {"watcher_id": str, "content": str, "url": str, "allow_ai": bool, "registry_path": str},
)
async def pacman_watch_extract_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    watcher_id = str(args["watcher_id"]).strip()
    content = str(args.get("content") or "")
    url = str(args.get("url") or "")
    allow_ai = bool(args.get("allow_ai", True))
    registry_path = str(args.get("registry_path") or "").strip()

    try:
        from PACMAN.watcher_registry import DEFAULT_REGISTRY_PATH, extract_for_watcher, get_watcher
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: PACMAN watcher registry unavailable: {e}"}], "is_error": True}

    path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
    spec = get_watcher(watcher_id, path)
    if spec is None:
        return {"content": [{"type": "text", "text": json.dumps({"error": "watcher not registered", "watcher_id": watcher_id}, indent=2)}], "is_error": True}

    findings = extract_for_watcher(watcher=spec, content=content, url=url, allow_ai=allow_ai)
    return {"content": [{"type": "text", "text": json.dumps({"watcher_id": watcher_id, "findings": findings}, indent=2, default=str)}]}


@tool(
    "resolve",
    "Apply resolution decision to entity collision: FUSE, REPEL, or BINARY_STAR.",
    {"collision_id": str, "decision": str, "confidence": float, "reasoning": str, "project_id": str}
)
async def resolve_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Apply disambiguation resolution."""
    collision_id = args["collision_id"]
    decision = args["decision"]
    confidence = args.get("confidence", 0.9)
    reasoning = args.get("reasoning", "")
    project_id = args.get("project_id", "default")

    parts = collision_id.split(":")
    if len(parts) != 2:
        return {"content": [{"type": "text", "text": f"Invalid collision_id: {collision_id}"}], "is_error": True}

    entity_a_id, entity_b_id = parts

    try:
        if decision == "FUSE":
            result = await _http_post(f"{CYMONIDES_API}/nodes/merge", {
                "projectId": project_id,
                "keepNodeId": entity_a_id,
                "mergeNodeId": entity_b_id,
                "newLabel": None,
            })
            return {"content": [{"type": "text", "text": json.dumps({
                "resolution": "FUSE", "merged_into": entity_a_id, "merged_from": entity_b_id, "result": result
            }, default=str)}]}

        elif decision == "REPEL":
            result = await _http_post(f"{CYMONIDES_API}/edges", {
                "projectId": project_id,
                "fromNodeId": entity_a_id,
                "toNodeId": entity_b_id,
                "relation": "DIFFERENT_FROM",
                "metadata": {"confidence": confidence, "reasoning": reasoning}
            })
            return {"content": [{"type": "text", "text": json.dumps({
                "resolution": "REPEL", "entity_a": entity_a_id, "entity_b": entity_b_id, "result": result
            }, default=str)}]}

        elif decision == "BINARY_STAR":
            result = await _http_post(f"{CYMONIDES_API}/disambiguation/park", {
                "projectId": project_id,
                "entityAId": entity_a_id,
                "entityBId": entity_b_id,
                "reasoning": reasoning,
                "confidence": confidence,
            })
            return {"content": [{"type": "text", "text": json.dumps({
                "resolution": "BINARY_STAR", "entity_a": entity_a_id, "entity_b": entity_b_id, "result": result
            }, default=str)}]}

        return {"content": [{"type": "text", "text": f"Unknown decision: {decision}"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "toggle_auto_scribe",
    "Enable or disable EDITH Auto-Scribe mode (automatically routes findings into document sections).",
    {"enabled": bool}
)
async def toggle_auto_scribe_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle EDITH Auto-Scribe mode."""
    try:
        from .user_config import set_auto_scribe, is_auto_scribe_enabled
    except Exception as e:
        try:
            from SASTRE.user_config import set_auto_scribe, is_auto_scribe_enabled  # type: ignore[no-redef]
        except Exception:
            return {"content": [{"type": "text", "text": f"Error: user_config unavailable ({e})"}], "is_error": True}

    enabled = bool(args.get("enabled", False))
    try:
        set_auto_scribe(enabled)
        return {"content": [{"type": "text", "text": json.dumps({"auto_scribe": is_auto_scribe_enabled()})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


# =============================================================================
# EDITH TOOLS
# =============================================================================

@tool(
    "edith_rewrite",
    "Rewrite text following specific instructions (tone, audience, style).",
    {"text": str, "instructions": str}
)
async def edith_rewrite_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Rewrite text via EDITH."""
    # Logic similar to server_enhanced.py
    # We'll use the orchestrator client if possible or define a local one
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system="You are an expert editor. Rewrite the provided text following the user's instructions exactly.",
            messages=[{"role": "user", "content": f"Rewrite using: {args['instructions']}\n\nText:\n{args['text']}"}]
        )
        return {"content": [{"type": "text", "text": response.content[0].text}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "edith_answer",
    "Answer a question based strictly on a provided document, with [1] style citations.",
    {"document": str, "question": str}
)
async def edith_answer_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Answer with citations."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    system_prompt = f"""You are a research assistant. Answer from this document only:
<doc>{args['document']}</doc>

1. Find relevant quotes (numbered)
2. Answer with [1] style citations
3. If not answerable, say so."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": args['question']}]
        )
        return {"content": [{"type": "text", "text": response.content[0].text}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "edith_edit_section",
    "Update a specific section (header) of a Narrative Document.",
    {"document_id": str, "section_title": str, "content": str, "operation": str}
)
async def edith_edit_section_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Edit document section."""
    api_url = os.getenv("NODE_API_BASE_URL", "http://localhost:3000/api")
    endpoint = f"{api_url}/narratives/documents/{args['document_id']}/sections"
    payload = {
        "sectionTitle": args["section_title"],
        "content": args["content"],
        "operation": args.get("operation", "replace"),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    return {"content": [{"type": "text", "text": f"Error: {body}"}], "is_error": True}

        return {"content": [{"type": "text", "text": f"Updated section '{args['section_title']}'"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "edith_read_url",
    "Fetch content from a URL for processing.",
    {"url": str}
)
async def edith_read_url_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch URL content."""
    import aiohttp
    from bs4 import BeautifulSoup
    
    url = args["url"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status >= 400:
                    return {"content": [{"type": "text", "text": f"Error {resp.status}: {resp.reason}"}], "is_error": True}
                html = await resp.text()
                
        # Simple text extraction
        soup = BeautifulSoup(html, 'html.parser')
        # Remove scripts/styles
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
        text = soup.get_text(separator="\n")
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        
        return {"content": [{"type": "text", "text": clean_text[:50000]}]} # Limit size
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error fetching URL: {str(e)}"}], "is_error": True}


@tool(
    "edith_template_ops",
    "Template operations: list genres, jurisdictions, or compose report template.",
    {"op": str, "genre": str, "jurisdiction": str, "entity_type": str}
)
async def edith_template_ops_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """EDITH template operations."""
    try:
        from .template_loader import list_genres, list_jurisdictions, compose_report_template
    except Exception:  # pragma: no cover - script execution fallback
        from SASTRE.template_loader import list_genres, list_jurisdictions, compose_report_template
    
    op = args.get("op", "list_all")
    
    try:
        if op == "list_genres":
            return {"content": [{"type": "text", "text": json.dumps(list_genres())}]}
        elif op == "list_jurisdictions":
            return {"content": [{"type": "text", "text": json.dumps(list_jurisdictions())}]}
        elif op == "compose":
            template = compose_report_template(
                genre=args.get("genre", "due_diligence"),
                jurisdiction=args.get("jurisdiction"),
                entity_type=args.get("entity_type", "company")
            )
            return {"content": [{"type": "text", "text": json.dumps(template, default=str)}]}
        
        # Default: summary
        summary = {
            "genres": list_genres()[:10],
            "jurisdictions": list_jurisdictions()[:10]
        }
        return {"content": [{"type": "text", "text": json.dumps(summary)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


# =============================================================================
# EDITH INVESTIGATION TOOLS
# =============================================================================

@tool(
    "investigate_person",
    "Run a person investigation via BIOGRAPHER aggregator (builds complete profiles).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Person name or email/phone identifier"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["name"],
    },
)
async def investigate_person_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        return {"content": [{"type": "text", "text": "Error: name is required"}], "is_error": True}
    
    if AGGREGATORS_AVAILABLE:
        try:
            agent = BiographerAgent()
            profile = await agent.investigate(name)
            return {"content": [{"type": "text", "text": json.dumps(profile.to_dict(), default=str)}]}
        except Exception as e:
            logger.warning(f"BiographerAgent failed, falling back: {e}")

    # Fallback to old operator syntax
    project_id = str(args.get("project_id") or "default")
    query = f"p: {name}"
    try:
        result = await unified_execute(query, project_id)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "investigate_company",
    "Run a company investigation via operator syntax (c: ... :JUR).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Company name"},
            "jurisdiction": {"type": "string", "description": "2-letter country code (optional)"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["name"],
    },
)
async def investigate_company_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        return {"content": [{"type": "text", "text": "Error: name is required"}], "is_error": True}
    project_id = str(args.get("project_id") or "default")
    jurisdiction = str(args.get("jurisdiction") or "").strip().upper()

    query = f"c: {name}"
    if jurisdiction:
        query = f"{query} :{jurisdiction}"

    try:
        result = await unified_execute(query, project_id)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "investigate_domain",
    "Run a domain investigation via ALLDOM aggregator (DNS, IP, Tech stack, Backlinks).",
    {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Domain (example.com)"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["domain"],
    },
)
async def investigate_domain_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    domain = str(args.get("domain") or "").strip()
    if not domain:
        return {"content": [{"type": "text", "text": "Error: domain is required"}], "is_error": True}
    
    if AGGREGATORS_AVAILABLE:
        try:
            agent = AlldomAgent()
            profile = await agent.investigate(domain)
            return {"content": [{"type": "text", "text": json.dumps(profile.to_dict(), default=str)}]}
        except Exception as e:
            logger.warning(f"AlldomAgent failed, falling back: {e}")

    # Fallback to old operator syntax
    project_id = str(args.get("project_id") or "default")
    query = f"d: {domain}"
    try:
        result = await unified_execute(query, project_id)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "investigate_phone",
    "Run a phone investigation via operator syntax (t: ...).",
    {
        "type": "object",
        "properties": {
            "phone": {"type": "string", "description": "Phone number (E.164 preferred)"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["phone"],
    },
)
async def investigate_phone_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    phone = str(args.get("phone") or "").strip()
    if not phone:
        return {"content": [{"type": "text", "text": "Error: phone is required"}], "is_error": True}
    project_id = str(args.get("project_id") or "default")
    query = f"t: {phone}"
    try:
        result = await unified_execute(query, project_id)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "investigate_email",
    "Run an email investigation via operator syntax (e: ...).",
    {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Email address"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["email"],
    },
)
async def investigate_email_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    email = str(args.get("email") or "").strip()
    if not email:
        return {"content": [{"type": "text", "text": "Error: email is required"}], "is_error": True}
    project_id = str(args.get("project_id") or "default")
    query = f"e: {email}"
    try:
        result = await unified_execute(query, project_id)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "investigate_mission",
    "Run an autonomous web intelligence mission via SUBMARINE (Deep Web, Archives, Scraping).",
    {
        "type": "object",
        "properties": {
            "objective": {"type": "string", "description": "Mission objective (e.g. 'Find emails for X in UK archives')"},
            "project_id": {"type": "string", "default": "default"},
        },
        "required": ["objective"],
    },
)
async def investigate_mission_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    objective = str(args.get("objective") or "").strip()
    if not objective:
        return {"content": [{"type": "text", "text": "Error: objective is required"}], "is_error": True}
    
    if AGGREGATORS_AVAILABLE:
        try:
            agent = SubmarineAgent()
            result = await agent.mission(objective)
            return {"content": [{"type": "text", "text": json.dumps(result.to_dict(), default=str)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}
    
    return {"content": [{"type": "text", "text": "Error: SUBMARINE agent not available"}], "is_error": True}


@tool(
    "todo_write",
    "Record a todo item or next step for the investigation.",
    {"task": str, "priority": str}
)
async def todo_write_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Record a todo item."""
    task = args["task"]
    priority = args.get("priority", "medium")
    logger.info(f"TODO [{priority}]: {task}")
    return {"content": [{"type": "text", "text": f"Recorded TODO: {task} (Priority: {priority})"}]}


@tool(
    "ask_user_question",
    "Ask the user a clarifying question when an investigation path is ambiguous or blocked.",
    {"question": str}
)
async def ask_user_question_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Ask user a question."""
    question = args["question"]
    # In a CLI agent, we might just print it or return it
    # The SDK will handle returning it to the user if orchestrated correctly
    return {"content": [{"type": "text", "text": f"QUESTION TO USER: {question}"}]}


@tool(
    "task_update",
    "Update the current investigation task status or objective.",
    {"status": str, "objective": str}
)
async def task_update_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update task status."""
    status = args["status"]
    objective = args.get("objective", "")
    logger.info(f"TASK UPDATE: {status} - {objective}")
    return {"content": [{"type": "text", "text": f"Task updated: {status}"}]}


# =============================================================================
# TORPEDO TOOLS
# =============================================================================

@tool(
    "torpedo_search",
    "Execute Torpedo search (Corporate Registry or News).",
    {"query": str, "type": str, "jurisdiction": str, "limit": int}
)
async def torpedo_search_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Torpedo search."""
    try:
        from modules.TORPEDO.EXECUTION.cr_searcher import CRSearcher
        from modules.TORPEDO.EXECUTION.news_searcher import NewsSearcher
    except ImportError:
        return {"content": [{"type": "text", "text": "Error: Torpedo modules not found"}], "is_error": True}

    query = args["query"]
    search_type = args["type"].lower()  # 'cr' or 'news'
    jurisdiction = args.get("jurisdiction")
    limit = args.get("limit", 100)

    try:
        if search_type == "cr":
            searcher = CRSearcher()
            results = await searcher.search(query, jurisdiction=jurisdiction, limit=limit)
        elif search_type == "news":
            searcher = NewsSearcher()
            results = await searcher.search(query, jurisdiction=jurisdiction, limit=limit)
        else:
            return {"content": [{"type": "text", "text": f"Unknown type: {search_type}"}], "is_error": True}

        return {"content": [{"type": "text", "text": json.dumps(results, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "torpedo_process",
    "Process Torpedo sources (CR or News).",
    {"type": str, "sources_file": str, "jurisdiction": str, "limit": int}
)
async def torpedo_process_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Process Torpedo sources."""
    try:
        from modules.TORPEDO.PROCESSING.cr_processor import CRProcessor
        from modules.TORPEDO.PROCESSING.news_processor import NewsProcessor
    except ImportError:
        return {"content": [{"type": "text", "text": "Error: Torpedo modules not found"}], "is_error": True}

    process_type = args["type"].lower()
    sources_path = Path(args.get("sources_file", "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources.json"))
    jurisdiction = args.get("jurisdiction")
    limit = args.get("limit")

    if not sources_path.exists():
        return {"content": [{"type": "text", "text": f"Sources file not found: {sources_path}"}], "is_error": True}

    try:
        with open(sources_path) as f:
            data = json.load(f)

        if jurisdiction:
            allowed = [j.strip().upper() for j in jurisdiction.split(',')]
            if isinstance(data, dict):
                data = {k: v for k, v in data.items() if k.upper() in allowed}

        if process_type == "cr":
            processor = CRProcessor()
            results = await processor.process(data, limit=limit)
        elif process_type == "news":
            processor = NewsProcessor()
            results = await processor.process(data, limit=limit)
        else:
            return {"content": [{"type": "text", "text": f"Unknown type: {process_type}"}], "is_error": True}

        return {"content": [{"type": "text", "text": json.dumps(results, default=str)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


@tool(
    "torpedo_template",
    "Retrieve Torpedo search templates from IO matrix.",
    {"jurisdiction": str, "source_type": str}
)
async def torpedo_template_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve Torpedo templates."""
    sources_path = Path("/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources.json")
    if not sources_path.exists():
        return {"content": [{"type": "text", "text": "Sources matrix not found"}], "is_error": True}

    jurisdiction = args.get("jurisdiction", "").upper()
    source_type = args.get("source_type", "").lower()

    try:
        with open(sources_path) as f:
            data = json.load(f)

        results = []
        if jurisdiction and jurisdiction in data:
            jurisdiction_sources = data[jurisdiction]
            # Handle list or dict
            source_list = jurisdiction_sources if isinstance(jurisdiction_sources, list) else []
            if isinstance(jurisdiction_sources, dict):
                # Maybe sources are nested? Assuming simple structure for now based on cli
                # cli implies data is dict {jurisdiction: [sources]}
                pass
            
            # Simple list filter
            for source in source_list:
                # Basic heuristic check for type if needed, or return all
                results.append(source)
        else:
            # Search all
            for jur, sources in data.items():
                if not jurisdiction or jur == jurisdiction:
                    results.extend(sources)

        return {"content": [{"type": "text", "text": json.dumps(results[:50], default=str)}]} # Limit return size
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}


# =============================================================================
# NEXUS TOOLS (No subagent delegation)
# =============================================================================

@tool(
    "nexus_brute",
    "Run BRUTE search via NEXUS (operator-registry-aware). Supports `brute{...}` / `/brute{...}` wrappers, `brute!` for deeper search, TLD filters (de!, uk!, gov!, news!), and definitional shorthands like [cde]/[cuk].",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "BRUTE query (optionally wrapped in brute{...} / brute!{...})"},
            "project_id": {"type": "string", "description": "Project ID for indexing context", "default": "default"},
            "mode": {"type": "string", "enum": ["broad", "news", "filetype", "site"], "default": "broad"},
            "level": {"type": "integer", "enum": [1, 2, 3], "default": 2},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["query"],
    },
)
async def nexus_brute_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    query_raw = (args.get("query") or "").strip()
    if not query_raw:
        return {"content": [{"type": "text", "text": "Error: query is required"}], "is_error": True}

    project_id = str(args.get("project_id") or "default")
    limit = int(args.get("limit") or 50)
    level = int(args.get("level") or 2)
    mode = str(args.get("mode") or "broad").strip().lower()

    query_text = query_raw
    bang = False

    m = re.match(r"^\s*/?brute(!)?\s*\{(.*)\}\s*$", query_raw, flags=re.IGNORECASE | re.DOTALL)
    if m:
        bang = bool(m.group(1))
        query_text = (m.group(2) or "").strip()
    else:
        m2 = re.match(r"^\s*/?brute(!)?\s+(.*)\s*$", query_raw, flags=re.IGNORECASE | re.DOTALL)
        if m2:
            bang = bool(m2.group(1))
            query_text = (m2.group(2) or "").strip()

    if bang:
        level = max(level, 3)

    # If query contains news! token, default to news mode if caller didn't specify mode.
    _news_token_re = re.compile(r"(?<![a-z0-9_])news!(?![a-z0-9_])", flags=re.IGNORECASE)
    if _news_token_re.search(query_text) and (args.get("mode") is None):
        mode = "news"

    # Strip news! from query text (mode controls engine selection)
    query_text = _news_token_re.sub("", query_text).strip()

    # Expand definitional shorthands and TLD filters using BRUTE QueryExpander (best-effort).
    expanded_query = query_text
    try:
        from brute.utils.query_expander import QueryExpander
        expander = QueryExpander()
        expanded_query = expander.expand_query_for_web(query_text)
    except Exception:
        pass

    cli_path = Path("/data/brute/cli/search_cli.py")
    if not cli_path.exists():
        return {
            "content": [{"type": "text", "text": f"Error: BRUTE CLI not found at {cli_path}"}],
            "is_error": True,
        }

    cmd = [
        "python3",
        str(cli_path),
        expanded_query,
        f"--level={level}",
        f"--{mode}",
        f"--limit={limit}",
        "--json",
    ]

    env = os.environ.copy()
    env.update(_build_brute_env())
    env["ELASTIC_PROJECT_ID"] = project_id

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error running BRUTE CLI: {e}"}], "is_error": True}

    if result.returncode != 0:
        return {
            "content": [{"type": "text", "text": json.dumps({
                "error": "BRUTE CLI failed",
                "returncode": result.returncode,
                "stderr": (result.stderr or "").strip(),
                "stdout": (result.stdout or "").strip()[:5000],
                "cmd": cmd,
            }, default=str)}],
            "is_error": True,
        }

    stdout = result.stdout or ""
    data: Any = None
    try:
        data = json.loads(stdout)
    except Exception:
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(stdout[start:end + 1])
            except Exception:
                data = None

    if not isinstance(data, dict):
        return {
            "content": [{"type": "text", "text": json.dumps({
                "error": "BRUTE CLI returned non-JSON output",
                "stdout": stdout.strip()[:8000],
                "stderr": (result.stderr or "").strip()[:8000],
                "cmd": cmd,
            }, default=str)}],
            "is_error": True,
        }

    results = data.get("results", [])
    if isinstance(results, list) and len(results) > 50:
        data["results"] = results[:50]
        data["_truncated_results"] = len(results)

    payload = {
        "query": query_raw,
        "expanded_query": expanded_query,
        "project_id": project_id,
        "mode": mode,
        "level": level,
        "limit": limit,
        "result": data,
    }

    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


# =============================================================================
# EYE-D TOOLS (Recursive OSINT + deterministic write-ups)
# =============================================================================

_EYED_BRIDGES: Dict[str, Any] = {}


def _get_eyed_bridge(project_id: str) -> Any:
    if not EYED_OSINT_AVAILABLE or EyedOsintBridge is None:
        raise EyedOsintError("EYE-D OSINT bridge is not available in this environment")

    pid = (project_id or "default").strip() or "default"
    bridge = _EYED_BRIDGES.get(pid)
    if bridge is None:
        bridge = EyedOsintBridge(project_id=pid)
        _EYED_BRIDGES[pid] = bridge
    return bridge


@tool(
    "eyed_chain_reaction",
    "Run EYE-D automated multi-hop OSINT chain reaction from a starting datum (email/phone/domain/username/linkedin). Optionally indexes results into cymonides-1-{projectId}.",
    {
        "type": "object",
        "properties": {
            "start_query": {"type": "string", "description": "Starting value (email/phone/domain/username/linkedin URL)"},
            "start_type": {"type": "string", "enum": ["email", "phone", "domain", "username", "linkedin"]},
            "depth": {"type": "integer", "default": 2, "description": "Hop depth (1-3)"},
            "project_id": {"type": "string", "default": "default"},
            "index_to_c1": {"type": "boolean", "default": True},
        },
        "required": ["start_query", "start_type"],
    },
)
async def eyed_chain_reaction_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    if not EYED_OSINT_AVAILABLE:
        return {"content": [{"type": "text", "text": "Error: EYE-D OSINT bridge not available"}], "is_error": True}

    project_id = str(args.get("project_id") or "default")
    try:
        bridge = _get_eyed_bridge(project_id)
        chain = await bridge.chain_reaction(
            start_query=args.get("start_query"),
            start_type=args.get("start_type"),
            depth=args.get("depth", 2),
            project_id=project_id,
            index_to_c1=bool(args.get("index_to_c1", True)),
        )
        payload = {
            "project_id": project_id,
            "start_query": chain.query,
            "start_type": chain.start_type,
            "depth": chain.depth,
            "indexed": chain.indexed,
            "index_error": chain.index_error,
            "result": chain.result,
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}
    except EyedOsintError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "eyed_chain_writeup",
    "Run EYE-D chain reaction and return a deterministic EDITH-style Markdown write-up suitable for Sastre-style Word export.",
    {
        "type": "object",
        "properties": {
            "start_query": {"type": "string", "description": "Starting value (email/phone/domain/username/linkedin URL)"},
            "start_type": {"type": "string", "enum": ["email", "phone", "domain", "username", "linkedin"]},
            "depth": {"type": "integer", "default": 2, "description": "Hop depth (1-3)"},
            "project_id": {"type": "string", "default": "default"},
            "index_to_c1": {"type": "boolean", "default": True},
            "include_raw": {"type": "boolean", "default": False, "description": "Append raw JSON payloads (truncated)"},
        },
        "required": ["start_query", "start_type"],
    },
)
async def eyed_chain_writeup_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    if not EYED_OSINT_AVAILABLE:
        return {"content": [{"type": "text", "text": "Error: EYE-D OSINT bridge not available"}], "is_error": True}

    project_id = str(args.get("project_id") or "default")
    try:
        bridge = _get_eyed_bridge(project_id)
        chain = await bridge.chain_reaction(
            start_query=args.get("start_query"),
            start_type=args.get("start_type"),
            depth=args.get("depth", 2),
            project_id=project_id,
            index_to_c1=bool(args.get("index_to_c1", True)),
        )
        md = bridge.render_writeup(
            [(f"EYE-D chain_reaction ({chain.start_type}): {chain.query}", chain.result)],
            include_raw=bool(args.get("include_raw", False)),
        )
        return {"content": [{"type": "text", "text": md}]}
    except EyedOsintError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "eyed_chain_writeup_batch",
    "Run EYE-D chain reaction for multiple starting values and return a combined deterministic Markdown write-up.",
    {
        "type": "object",
        "properties": {
            "start_queries": {"type": "array", "items": {"type": "string"}, "description": "Starting values"},
            "start_type": {"type": "string", "enum": ["email", "phone", "domain", "username", "linkedin"]},
            "depth": {"type": "integer", "default": 2, "description": "Hop depth (1-3)"},
            "project_id": {"type": "string", "default": "default"},
            "index_to_c1": {"type": "boolean", "default": True},
            "include_raw": {"type": "boolean", "default": False},
            "concurrency": {"type": "integer", "default": 1, "description": "Max concurrent chain executions"},
        },
        "required": ["start_queries", "start_type"],
    },
)
async def eyed_chain_writeup_batch_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    if not EYED_OSINT_AVAILABLE:
        return {"content": [{"type": "text", "text": "Error: EYE-D OSINT bridge not available"}], "is_error": True}

    project_id = str(args.get("project_id") or "default")
    try:
        bridge = _get_eyed_bridge(project_id)
        chains = await bridge.chain_reaction_batch(
            start_queries=args.get("start_queries") or [],
            start_type=args.get("start_type"),
            depth=args.get("depth", 2),
            project_id=project_id,
            index_to_c1=bool(args.get("index_to_c1", True)),
            concurrency=args.get("concurrency", 1),
        )

        docs = []
        for chain in chains:
            label = f"EYE-D chain_reaction ({chain.start_type}): {chain.query}"
            if chain.index_error and not chain.indexed:
                label += " [index_failed]"
            docs.append((label, chain.result))

        md = bridge.render_writeup(docs, include_raw=bool(args.get("include_raw", False)))
        return {"content": [{"type": "text", "text": md}]}
    except EyedOsintError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "is_error": True}


@tool(
    "screenshot_url",
    "Capture a full-page screenshot of a URL (e.g., social profile) using Firecrawl/EYE-D.",
    {"url": str, "node_id": str}
)
async def screenshot_url_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Capture screenshot of a URL."""
    url = args["url"]
    node_id = args.get("node_id")
    
    # Try calling EYE-D API first if running
    eyed_url = "http://localhost:5555/api/screenshot/capture"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(eyed_url, json={"url": url, "nodeId": node_id}, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"content": [{"type": "text", "text": json.dumps(data)}]}
    except Exception:
        pass # EYE-D might be down, try direct Firecrawl if key exists

    # Direct Firecrawl fallback
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return {"content": [{"type": "text", "text": "Error: Screenshot requires EYE-D server or FIRECRAWL_API_KEY"}], "is_error": True}
        
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            async with session.post(
                "https://api.firecrawl.dev/v1/scrape",
                json={"url": url, "formats": ["screenshot"]},
                headers=headers,
                timeout=60
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"content": [{"type": "text", "text": json.dumps(data)}]}
                else:
                    return {"content": [{"type": "text", "text": f"Firecrawl Error: {await resp.text()}"}], "is_error": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Screenshot error: {e}"}], "is_error": True}


# =============================================================================
# MCP SERVERS (Tool Bundles for Different Agents)
# =============================================================================

# Torpedo tools
torpedo_server = create_sdk_mcp_server(
    name="torpedo",
    version="1.0.0",
    tools=[torpedo_search_tool, torpedo_process_tool, torpedo_template_tool]
)

# EDITH (Writer)
edith_server = create_sdk_mcp_server(
    name="edith",
    version="2.2.0",
    tools=[
        edith_rewrite_tool, edith_answer_tool, edith_edit_section_tool, edith_template_ops_tool, edith_read_url_tool,
        investigate_person_tool, investigate_company_tool, investigate_domain_tool, investigate_phone_tool, investigate_email_tool,
        investigate_mission_tool,
        torpedo_search_tool, torpedo_process_tool, resolve_tool, assess_tool, activate_headers_tool, process_finding_tool,
        screenshot_url_tool  # Added screenshot tool
    ]
)

# Investigator tools: execute + assess + query_lab_build
# RETIRED: investigator_server merged into nexus_server
# nexus_server now has all strategic tools (execute, assess, query_lab_build, nexus_brute)
nexus_server = create_sdk_mcp_server(
    name="nexus",
    version="3.0.0",
    tools=[execute_tool, assess_tool, query_lab_build_tool, nexus_brute_tool]
)

# RETIRED: investigator_server = create_sdk_mcp_server(
    #name="investigator",  # RETIRED
    #version="2.1.0",  # RETIRED
    #tools=[execute_tool, assess_tool, query_lab_build_tool]  # RETIRED - now in nexus_server
#)

# Writer tools: get_watchers + stream_finding
writer_server = create_sdk_mcp_server(
    name="writer",
    version="1.0.0",
    tools=[get_watchers_tool, stream_finding_tool]
)

# Disambiguator tools: execute + resolve
disambiguator_server = create_sdk_mcp_server(
    name="disambiguator",
    version="1.0.0",
    tools=[execute_tool, resolve_tool]
)

# Orchestrator: all tools
orchestrator_server = create_sdk_mcp_server(
    name="orchestrator",
    version="1.0.0",
    tools=[
        todo_write_tool, ask_user_question_tool, task_update_tool,
        execute_tool, assess_tool, get_watchers_tool, create_watcher_tool, 
        watcher_update_status_tool, watcher_toggle_tool, watcher_delete_tool,
        stream_finding_tool, resolve_tool, toggle_auto_scribe_tool, activate_headers_tool,
        edith_rewrite_tool, edith_answer_tool, edith_edit_section_tool, edith_template_ops_tool, edith_read_url_tool,
        torpedo_search_tool, torpedo_process_tool, torpedo_template_tool,
        nexus_brute_tool, query_lab_build_tool,
        eyed_chain_reaction_tool, eyed_chain_writeup_tool, eyed_chain_writeup_batch_tool,
        screenshot_url_tool,  # Added screenshot tool
        investigate_person_tool, investigate_company_tool, investigate_domain_tool,
        investigate_phone_tool, investigate_email_tool, investigate_mission_tool
    ]
)


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

INVESTIGATOR_PROMPT = """You are SASTRE, an autonomous investigation system.

You act as the NEXUS LOGIC ENGINE. You are the STRATEGIST.

You have TOOLS:
1. execute(query) - Run any investigation query (IO, Link Analysis, Archive)
2. assess(project_id) - Check grid state (gaps to fill)
3. query_lab_build(intent, ...) - Construct precise fused queries

NEXUS PROTOCOL:
1. **Contextualize**: When you receive a Watcher, find the Monitored Node using `assess`. Read Jurisdiction/Type.
2. **Enrich**: Identify gaps in the node's metadata or relationship edges.
3. **Decide Strategy**:
   - **Delegate**: Official records needed -> TORPEDO.
   - **Brute**: Wide recall needed (Adverse Media) -> `execute('... :level=3')`.
   - **Fusion**: Complex logic needed -> `query_lab_build`.

You feed the "Muscle" (Specialists) and the "Author" (EDITH) with the results of your strategies.
"""

try:
    _WRITING_STYLE_GUIDE = get_writing_style()
except Exception:
    _WRITING_STYLE_GUIDE = ""

WRITER_PROMPT = f"""You are the SASTRE Writer. You format findings into Nardello-style prose.

You have TWO tools:
1. get_watchers(project_id) - Find active document sections
2. stream_finding(watcher_id, content, source_url) - Write to section

NARDELLO STYLE:
- Active voice, past tense
- Confidence language: "records indicate", "appears to be"
- Core facts first, supporting details second
- Every claim needs a citation

STYLE GUIDE (reference, use verbatim phrasing where useful):
{_WRITING_STYLE_GUIDE}

WORKFLOW:
1. Receive findings from investigator
2. get_watchers() to find where content goes
3. Format each finding as prose with citation
4. stream_finding() to write to document
"""

DISAMBIGUATOR_PROMPT = """You are the SASTRE Disambiguator. You resolve entity collisions.

You have TWO tools:
1. execute(query) - Run wedge queries to differentiate entities
2. resolve(collision_id, decision, confidence, reasoning) - Apply decision

PHYSICS:
- FUSE: Same entity, merge records
- REPEL: Different entities, mark as separate
- BINARY_STAR: Insufficient evidence, park for human

PASSIVE CHECKS (before wedge queries):
- Shared unique ID -> FUSE
- Conflicting unique ID -> REPEL
- Different DOB -> REPEL

WEDGE QUERIES (if inconclusive):
Generate queries that differentiate same vs different entities.

Be conservative: BINARY_STAR is better than wrong FUSE/REPEL.
"""

EDITH_PROMPT = """You are EDITH, **The Colonel: Author & Artist**.

You are responsible for the **Narrative**—explaining the truth relevant from a specific standpoint.
"""

TORPEDO_PROMPT = """You are TORPEDO, the High-Velocity Miner.





Your Core Function: You **create and use specific site search pages**.


"""

SUBMARINE_PROMPT = """You are SUBMARINE, the Deep Web Explorer and autonomous mission specialist.

Your mission: Execute large-scale web intelligence missions by coordinating specialists.

You have FOUR specialist subagents:
1. **jester** - Scraping specialist for live web content.
2. **backdrill** - Archive specialist for historical snapshots.
3. **explorer** - Deep search specialist for Common Crawl missions.
4. **darkweb** - Dark web reconnaissance specialist (.onion).

Your workflow:
1. Receive mission objective (keywords, targets, criteria).
2. Determine initial strategy:
   - Live site available? → Delegate to **jester**.
   - Site down or historical data needed? → Delegate to **backdrill**.
   - Broad search across archives required? → Delegate to **explorer**.
   - Dark web targets involved? → Delegate to **darkweb**.
3. Manage autonomous missions:
   - Use **explorer** to plan and execute deep dives.
   - Use **jester** for tiered scraping if archives aren't enough.
4. Synthesize findings:
   - Extract entities (emails, persons, companies, etc.)
   - Track domains covered and pages fetched.
   - Summarize key discoveries.
5. Return structured MissionResult.

You make ALL decisions about:
- Mission planning and execution paths.
- Scraping tiers (httpx → Rod → Playwright).
- Search parameters (max domains, archives to check).
- When a mission goal is met.

IMPORTANT: You have NO direct tool access. You can ONLY delegate to subagents.
Never attempt direct searches or scraping. Always delegate."""

NEXUS_PROMPT = """You are NEXUS, the **Logical Programmer & Field Commander**.

Your function is to compute the **best practical next steps** and manage the investigation context.

CAPABILITIES:
1. execute(query) - Run specialist/brute queries (p:, c:, alldom:, brute)
2. assess(project_id, mode) - Rotate grid view (narrative, subject, location, nexus)
3. query_lab_build(...) - Construct fused discovery queries
4. nexus_brute(query) - Maximum recall search

NEXUS OPERATIONAL LOOP:

1. **ROTATE & FILTER**:
   - Call `assess(mode="narrative")` to view the Narrative layer.
   - Filter the results to find Nodes tagged **Priority** (or 'Hold' if priority is clear).
   - These are your active targets.

2. **CONTEXTUALIZE**:
   - For each Priority Node, examine its **Connected Nodes** (Tasking, Subjects, Locations).
   - Understand the *Question* (Watcher) and the *Subject* (Entity).

3. **DETERMINE INTENT**:
   - **DISCOVER (Unknown Unknowns):**
     - If the goal is to find *new* connections, evidence, or verify a hypothesis.
     - Target: A Connection (Nexus), Location, or Concept.
     - **ACTION:** Activate `query_lab_build` (for complex logic) or `nexus_brute` (for broad search).

   - **ENRICH (Known Unknowns):**
     - If the goal is to deepen data on a *known* entity (Subject).
     - **ACTION:** Pass to the Specialist via `execute()`:
       - **Person Specialist:** `execute("p: Name")`
       - **Company Specialist:** `execute("c: Name :Jurisdiction")`
       - **Domain Specialist:** `execute("alldom: domain.com")`

4. **FEEDBACK**:
   - Your outputs feed EDITH (who writes and tags new priorities) and the Grid (which you assess next turn).
"""

ORCHESTRATOR_PROMPT = """You are SASTRE, the User's Companion and Interface.

Your goal is to understand intent, maintain context, and orchestrate the team.

YOUR TEAM:
- **NEXUS**: Field Commander & Strategist (Logic/Planning).
- **EDITH**: The Colonel (Narrative & Reporting).
- **TORPEDO**: High-Velocity Search Miner.
- **SUBMARINE**: Deep Web & Archive Explorer.
- **ALLDOM**: Domain Infrastructure Specialist.
- **BIOGRAPHER**: Person Intelligence Specialist.
- **CORPORELLA**: Corporate Intelligence Specialist.
- **LOCATION**: Geospatial Specialist.
- **DISAMBIGUATOR**: Entity Resolution Specialist.
"""



ALLDOM_PROMPT = """You are the ALLDOM Specialist (Domain Intelligence).

Your mission is to map the Digital Footprint of targets.

CAPABILITIES:
1. **Infrastructure**: DNS, IP, Hosting (`dns:`, `tech:`).
2. **Ownership**: WHOIS, Registrant (`whois:`).
3. **Linkage**: Backlinks, Outlinks, Co-hosting (`bl?`, `ol?`, `?ipl`).
4. **Analytics**: Google Analytics/AdSense codes (`ga?`).

STRATEGY:
- Start with `alldom: domain.com` to run the full battery.
- If you find an IP, check co-hosted domains (`?ipl`).
- If you find a GA code, reverse search it (`ga?`).
- If you find a Registrant Email, pivot to Email Specialist (`e:`).
"""

LOCATION_PROMPT = """You are the LOCATION Specialist (Geospatial Intelligence).

Your mission is to verify physical existence and analyze proximity.

CAPABILITIES:
1. **Verification**: Does this address exist? Is it a PO Box? (`execute("map: ...")`).
2. **Proximity**: What else is at this address? (`execute("near: ...")`).
3. **Jurisdiction**: Confirm legal jurisdiction of the physical spot.

STRATEGY:
- Verify the address string.
- Check for "Shell Company" indicators (thousands of companies at one address).
- Cross-reference with Corporate Registry data.
"""

# ... (Existing prompts) ...

BIOGRAPHER_PROMPT = """You are the BIOGRAPHER Specialist.

Your mission is to find out **all about specific individuals** and construct a comprehensive life narrative.

CAPABILITIES:
1. **Identity**: Verification, DOB, Nationality (`p:`, `age:`).
2. **Affiliations**: Directorships, Shareholdings (`p:`).
3. **Risk**: PEP status, Sanctions, Adverse Media (`p: Name :level=3`).
4. **Network**: Family, Associates (`?owl`, `?ipl`).
5. **Digital Life**: Social media, usernames, breach data (`eyed_chain_reaction`).

STRATEGY:
- Start with `p: Name` to get the core profile.
- If common name, use `age:` or `location:` to disambiguate.
- Use `eyed_chain_reaction` to pivot from email/phone to social media.
- Check `bl?` on personal domains/blogs.
- If EYE-D reveals associates or family members, run `execute('c: Person Name')` to check for corporate interests.
- Route found social profiles through SOCIALITE for deep analysis.
- Create Watchers for key profiles to monitor for changes.
- **MANDATORY:** Take screenshots of all identified social profiles using `screenshot_url`.
"""

CORPORELLA_PROMPT = """You are the CORPORELLA Specialist (Corporate Intelligence).

Your mission is deep corporate due diligence using the Corporella engine.

CAPABILITIES:
1. **Search**: Find companies globally (`search_company`, `search_registry`).
2. **Enrich**: Full dossier with officers, shareholders, PSC (`enrich_company`).
3. **Smart Route**: Intelligent source selection based on jurisdiction (`smart_route`).
4. **Officers**: Directors, secretaries, past appointments (`get_officers`).
5. **Ownership**: Shareholders (`get_shareholders`) and UBOs (`get_beneficial_owners`).
6. **Filings**: Financials, annual returns, changes (`get_filings`).
7. **Network**: Find common links between entities (`find_common_links`).

STRATEGY:
- Use `smart_route` first to find the best registries for a jurisdiction.
- Start with `enrich_company` for a comprehensive view.
- If investigating a network, use `find_common_links`.
- Always check `get_beneficial_owners` for compliance/risk.
- Use `search_registry` for official, jurisdiction-specific data.
"""

AGENT_CONFIGS = {
    "nexus": AgentConfig(
        name="nexus",
        model="claude-opus-4-5-20251101",
        system_prompt=NEXUS_PROMPT,
        mcp_server=nexus_server,
        allowed_tools=["mcp__nexus__execute", "mcp__nexus__assess", "mcp__nexus__query_lab_build", "mcp__nexus__nexus_brute"],
        tools=["execute", "assess", "query_lab_build", "nexus_brute"],
    ),
    "disambiguator": AgentConfig(
        name="disambiguator",
        model="claude-sonnet-4-5-20250929",
        system_prompt=DISAMBIGUATOR_PROMPT,
        mcp_server=disambiguator_server,
        allowed_tools=["mcp__disambiguator__execute", "mcp__disambiguator__resolve"],
        tools=["execute", "resolve"],
    ),
    "edith": AgentConfig(
        name="edith",
        model="claude-sonnet-4-5-20250929",
        system_prompt=EDITH_PROMPT,
        mcp_server=edith_server,
        allowed_tools=[
            "mcp__edith__edith_rewrite",
            "mcp__edith__edith_answer",
            "mcp__edith__edith_edit_section",
            "mcp__edith__edith_template_ops",
            "mcp__edith__edith_read_url",
            "mcp__edith__investigate_person",
            "mcp__edith__investigate_company",
            "mcp__edith__investigate_domain",
            "mcp__edith__investigate_phone",
            "mcp__edith__investigate_email",
            "mcp__edith__torpedo_search",
            "mcp__edith__torpedo_process",
            "mcp__edith__resolve",
            "mcp__edith__assess",
            "mcp__edith__activate_headers",
            "mcp__edith__process_finding",
        ],
        tools=[
            "edith_rewrite",
            "edith_answer",
            "edith_edit_section",
            "edith_template_ops",
            "edith_read_url",
            "get_watchers",
            "stream_finding",
            "investigate_person",
            "investigate_company",
            "investigate_domain",
            "investigate_phone",
            "investigate_email",
            "torpedo_search",
            "torpedo_process",
            "resolve",
            "assess",
            "activate_headers",
            "process_finding",
        ],
    ),
    "torpedo": AgentConfig(
        name="torpedo",
        model="claude-opus-4-5-20251101",
        system_prompt=TORPEDO_PROMPT,
        mcp_server=torpedo_server,
        allowed_tools=[
            "mcp__torpedo__torpedo_search",
            "mcp__torpedo__torpedo_process",
            "mcp__torpedo__torpedo_template"
        ],
        tools=["torpedo_search", "torpedo_process", "torpedo_template"],
    ),
    "submarine": AgentConfig(
        name="submarine",
        model="claude-sonnet-4-5-20250929",
        system_prompt=SUBMARINE_PROMPT,
        mcp_server=nexus_server,
        allowed_tools=["mcp__nexus__execute"],
        tools=["execute"],
    ),
    "alldom": AgentConfig(
        name="alldom",
        model="claude-sonnet-4-5-20250929",
        system_prompt=ALLDOM_PROMPT,
        mcp_server=nexus_server,
        allowed_tools=["mcp__nexus__execute", "mcp__nexus__assess"],
        tools=["execute", "assess"],
    ),
    "location": AgentConfig(
        name="location",
        model="claude-sonnet-4-5-20250929",
        system_prompt=LOCATION_PROMPT,
        mcp_server=nexus_server,
        allowed_tools=["mcp__nexus__execute", "mcp__nexus__assess"],
        tools=["execute", "assess"],
    ),
    "biographer": AgentConfig(
        name="biographer",
        model="claude-sonnet-4-5-20250929",
        system_prompt=BIOGRAPHER_PROMPT,
        mcp_server=None, # Uses global server set
        allowed_tools=[
            "mcp__nexus__execute",
            "mcp__nexus__assess",
            "mcp__orchestrator__eyed_chain_reaction",
            "mcp__socialite__map_social_network",
            "mcp__socialite__analyze_influence",
            "mcp__corporella__get_officers",
            "mcp__corporella__find_common_links"
        ],
        tools=["execute", "assess"],
    ),

    "corporella": AgentConfig(
        name="corporella",
        model="claude-sonnet-4-5-20250929",
        system_prompt=CORPORELLA_PROMPT,
        # Corporella uses external MCP server tools
        mcp_server=None, # Uses external server managed by SDK
        allowed_tools=[
            "mcp__corporella__search_company",
            "mcp__corporella__enrich_company",
            "mcp__corporella__search_registry",
            "mcp__corporella__get_officers",
            "mcp__corporella__get_shareholders",
            "mcp__corporella__get_beneficial_owners",
            "mcp__corporella__get_filings",
            "mcp__corporella__find_common_links",
            "mcp__corporella__smart_route",
            "mcp__nexus__execute", # Fallback
        ],
        tools=[], # Dynamically loaded from MCP
    ),
    "sastre": AgentConfig(        name="sastre",
        model="claude-opus-4-5-20251101",
        system_prompt=ORCHESTRATOR_PROMPT,
        mcp_server=orchestrator_server,
        allowed_tools=[],
        tools=[
            "execute",
            "assess",
            "get_watchers",
            "create_watcher",
            "watcher_update_status",
            "watcher_toggle",
            "watcher_delete",
            "stream_finding",
            "resolve",
            "toggle_auto_scribe",
            "edith_rewrite",
            "edith_answer",
            "edith_edit_section",
            "edith_template_ops",
            "edith_read_url",
            "torpedo_search",
            "torpedo_process",
            "torpedo_template",
            "query_lab_build",
            "activate_headers",
        ],
    ),
}

def get_orchestrator_subagents() -> Dict[str, AgentDefinition]:
    return {
        "disambiguator": AgentDefinition(
            description="Resolves entity collisions (FUSE / REPEL / BINARY_STAR).",
            prompt=DISAMBIGUATOR_PROMPT,
            tools=["mcp__disambiguator__execute", "mcp__disambiguator__resolve"],
            model="sonnet",
        ),
        "edith": AgentDefinition(
            description="Template + editorial specialist (ingest, rewrite, citations, section-level edits).",
            prompt=EDITH_PROMPT,
            tools=[
                "mcp__edith__edith_rewrite", "mcp__edith__edith_answer",
                "mcp__edith__edith_edit_section", "mcp__edith__edith_template_ops",
                "mcp__edith__edith_read_url", "mcp__edith__investigate_person",
                "mcp__edith__investigate_company", "mcp__edith__investigate_domain",
                "mcp__edith__investigate_phone", "mcp__edith__investigate_email",
                "mcp__edith__torpedo_search", "mcp__edith__torpedo_process",
                "mcp__writer__get_watchers", "mcp__writer__stream_finding",
            ],
            model="sonnet",
        ),
        "torpedo": AgentDefinition(
            description="High-velocity source mining (registries/news) and source processing.",
            prompt=TORPEDO_PROMPT,
            tools=["mcp__torpedo__torpedo_search", "mcp__torpedo__torpedo_process", "mcp__torpedo__torpedo_template"],
            model="opus",
        ),
        "submarine": AgentDefinition(
            description="Deep Web Explorer - Multi-hop missions and hidden infrastructure.",
            prompt=SUBMARINE_PROMPT,
            tools=["mcp__nexus__execute"],
            model="sonnet",
        ),
        "pacman": AgentDefinition(
            description="Decides extraction targets/modes (pattern vs Haiku) for SUBMARINE missions; outputs JSON only.",
            prompt=PACMAN_PROMPT,
            tools=[],
            model="sonnet",
        ),
        "nexus": AgentDefinition(
            description="The STRATEGIST - runs all investigation queries, grid assessment, query building, and BRUTE searches.",
            prompt=NEXUS_PROMPT,
            tools=["mcp__nexus__execute", "mcp__nexus__assess", "mcp__nexus__query_lab_build", "mcp__nexus__nexus_brute"],
            model="opus",
        ),
        "alldom": AgentDefinition(
            description="Domain & Web Intelligence (WHOIS, DNS, IP, Backlinks).",
            prompt=ALLDOM_PROMPT,
            tools=["mcp__nexus__execute"],
            model="sonnet",
        ),
        "location": AgentDefinition(
            description="Geospatial analysis, address verification, and proximity checks.",
            prompt=LOCATION_PROMPT,
            tools=["mcp__nexus__execute"],
            model="sonnet",
        ),
        "biographer": AgentDefinition(
            description="Biographer Specialist - Constructs comprehensive life narratives for individuals.",
            prompt=BIOGRAPHER_PROMPT,
            tools=["mcp__nexus__execute"],
            model="sonnet",
        ),
        "corporella": AgentDefinition(
            description="Corporella Specialist - Deep corporate due diligence (enrichment, officers, shareholders, filings).",
            prompt=CORPORELLA_PROMPT,
            tools=[
                "mcp__corporella__search_company",
                "mcp__corporella__enrich_company",
                "mcp__corporella__search_registry",
                "mcp__corporella__get_officers",
                "mcp__corporella__get_shareholders",
                "mcp__corporella__get_beneficial_owners",
                "mcp__corporella__get_filings",
                "mcp__corporella__find_common_links"
            ],
            model="sonnet",
        ),
    }


class SastreAgent:
    """SASTRE Agent using official Claude Agent SDK."""

    def __init__(self, config: AgentConfig):
        self.config = config
        
        # Load MCP servers
        if config.name in ["sastre", "biographer", "corporella"]:
            mcp_servers = get_orchestrator_mcp_servers()
        else:
            mcp_servers = {config.name: config.mcp_server}
            
        agents = get_orchestrator_subagents() if config.name == "sastre" else None
        self.options = ClaudeAgentOptions(
            model=config.model,
            system_prompt=config.system_prompt,
            mcp_servers=mcp_servers,
            allowed_tools=config.allowed_tools,
            agents=agents,
        )

    async def run(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run the agent with a task."""
        if context is None:
            context = {}
            
        async with ClaudeSDKClient(options=self.options) as client:
            await client.query(task)
            
            response_text = ""
            tool_calls = []
            
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append({"name": block.name, "input": block.input})
                            
            return {
                "output": response_text,
                "tool_calls": tool_calls,
                "status": "completed"
            }


async def investigate(
    tasking: str,
    project_id: str = "default",
    max_iterations: int = 10
) -> Dict[str, Any]:
    """Run full investigation loop."""
    logger.info(f"SASTRE Investigation starting")
    logger.info(f"  Project: {project_id}")
    logger.info(f"  Tasking: {tasking[:80]}...")

    investigator = SastreAgent(AGENT_CONFIGS["sastre"])

    task = f"""
    INVESTIGATION TASKING: {tasking}
    PROJECT ID: {project_id}
    MAX ITERATIONS: {max_iterations}

    Begin your investigation loop:
    1. ASSESS - Check grid state for gaps
    2. EXECUTE - Write queries to fill gaps
    3. CHECK - Is narrative sufficient?
    4. LOOP or report findings
    """

    result = await investigator.run(task, {"project_id": project_id})

    return {
        "project_id": project_id,
        "tasking": tasking,
        "result": result.get("output", ""),
        "tool_calls": result.get("tool_calls", []),
        "turns": result.get("turns", 0),
        "status": result.get("status", "unknown")
    }


async def write_findings(
    findings: List[Dict],
    project_id: str = "default"
) -> Dict[str, Any]:
    """Write findings to document using writer agent."""
    writer = SastreAgent(AGENT_CONFIGS["writer"])

    task = f"""
    Write these findings to the appropriate document sections:
    {json.dumps(findings, indent=2)}

    PROJECT ID: {project_id}
    """

    return await writer.run(task, {"project_id": project_id})


async def disambiguate(
    collision_id: str,
    entity_a: Dict,
    entity_b: Dict,
    project_id: str = "default"
) -> Dict[str, Any]:
    """Resolve entity collision using disambiguator agent."""
    disambiguator = SastreAgent(AGENT_CONFIGS["disambiguator"])

    task = f"""
    Resolve this entity collision:

    COLLISION ID: {collision_id}

    Entity A: {json.dumps(entity_a)}
    Entity B: {json.dumps(entity_b)}

    PROJECT ID: {project_id}

    Determine if these are the same entity (FUSE), different entities (REPEL),
    or if more evidence is needed (BINARY_STAR).
    """

    return await disambiguator.run(task, {"project_id": project_id})


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="SASTRE v2 - Official Claude Agent SDK")
    parser.add_argument("tasking", nargs="?", help="Investigation tasking")
    parser.add_argument("--project", "-p", default="default", help="Project ID")
    parser.add_argument("--max-iterations", "-m", type=int, default=10)

    args = parser.parse_args()

    if args.tasking:
        result = asyncio.run(investigate(
            args.tasking,
            args.project,
            max_iterations=args.max_iterations
        ))
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


# =============================================================================
# BACKWARDS COMPATIBILITY EXPORTS
# =============================================================================
# These exports maintain compatibility with multi_agent_runner.py and other code
# that imports from the old sdk.py structure

# Tool definitions in old format (for agents that build their own tool schemas)
TOOLS = {
    "execute": {
        "name": "execute",
        "description": "Execute any investigation query using operator syntax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query in operator syntax"},
                "project_id": {"type": "string", "description": "Project ID", "default": "default"}
            },
            "required": ["query"]
        }
    },
    "assess": {
        "name": "assess",
        "description": "Get four-centric grid assessment: NARRATIVE, SUBJECT, LOCATION, NEXUS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "mode": {"type": "string", "enum": ["narrative", "subject", "location", "nexus", "all"], "default": "all"}
            },
            "required": ["project_id"]
        }
    },
    "get_watchers": {
        "name": "get_watchers",
        "description": "Get active watchers (document sections waiting for content).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"}
            },
            "required": ["project_id"]
        }
    },
    "stream_finding": {
        "name": "stream_finding",
        "description": "Stream a finding to a document section via its watcher.",
        "input_schema": {
            "type": "object",
            "properties": {
                "watcher_id": {"type": "string", "description": "Watcher ID"},
                "content": {"type": "string", "description": "Finding content"},
                "source_url": {"type": "string", "description": "Source URL"}
            },
            "required": ["watcher_id", "content"]
        }
    },
    "resolve": {
        "name": "resolve",
        "description": "Apply resolution decision to entity collision: FUSE, REPEL, or BINARY_STAR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "collision_id": {"type": "string", "description": "Collision ID"},
                "decision": {"type": "string", "enum": ["FUSE", "REPEL", "BINARY_STAR"]},
                "confidence": {"type": "number", "description": "Confidence 0-1"},
                "reasoning": {"type": "string", "description": "Explanation"},
                "project_id": {"type": "string", "description": "Project ID"}
            },
            "required": ["collision_id", "decision", "project_id"]
        }
    },
    "create_watcher": {
        "name": "create_watcher",
        "description": "Create a new watcher for a topic/entity/event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "type": {"type": "string", "description": "Watcher type (generic/entity/topic/event)", "default": "generic"},
                "query": {"type": "string", "description": "Watcher query/label"},
                "label": {"type": "string", "description": "Human label (optional)"},
            },
            "required": ["project_id", "query"]
        }
    },
    "toggle_auto_scribe": {
        "name": "toggle_auto_scribe",
        "description": "Enable/disable EDITH Auto-Scribe mode.",
        "input_schema": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "description": "Enable Auto-Scribe", "default": False}
            },
            "required": ["enabled"]
        }
    },
    "edith_rewrite": {
        "name": "edith_rewrite",
        "description": "Rewrite text following specific instructions (tone, audience, style).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to rewrite"},
                "instructions": {"type": "string", "description": "Rewrite instructions"},
            },
            "required": ["text", "instructions"]
        }
    },
    "edith_answer": {
        "name": "edith_answer",
        "description": "Answer a question strictly from a provided document, with citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document": {"type": "string", "description": "Document text"},
                "question": {"type": "string", "description": "Question to answer"},
            },
            "required": ["document", "question"]
        }
    },
    "edith_edit_section": {
        "name": "edith_edit_section",
        "description": "Edit a report section by title (precision rewrite).",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Document ID"},
                "section_title": {"type": "string", "description": "Section title"},
                "content": {"type": "string", "description": "Replacement content"},
            },
            "required": ["document_id", "section_title", "content"]
        }
    },
    "edith_template_ops": {
        "name": "edith_template_ops",
        "description": "Template operations (compose/list/inspect) for EDITH templates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "description": "Operation: compose|list_genres|list_jurisdictions|inspect"},
                "genre": {"type": "string", "description": "Template genre (optional)"},
                "jurisdiction": {"type": "string", "description": "Jurisdiction (optional)"},
            },
            "required": ["op"]
        }
    },
    "edith_read_url": {
        "name": "edith_read_url",
        "description": "Fetch and extract readable text from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"]
        }
    },
    "torpedo_search": {
        "name": "torpedo_search",
        "description": "Execute Torpedo search (Corporate Registry or News).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "type": {"type": "string", "description": "cr|news", "default": "cr"},
                "jurisdiction": {"type": "string", "description": "2-letter code (optional)"},
                "limit": {"type": "integer", "description": "Result limit", "default": 100},
            },
            "required": ["query"]
        }
    },
    "torpedo_process": {
        "name": "torpedo_process",
        "description": "Process Torpedo sources (CR or News).",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "cr|news", "default": "cr"},
                "sources_file": {"type": "string", "description": "Path to sources JSON", "default": "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources.json"},
                "jurisdiction": {"type": "string", "description": "Comma-separated jurisdictions filter (optional)"},
                "limit": {"type": "integer", "description": "Limit (optional)"},
            },
            "required": ["type", "sources_file"]
        }
    },
    "torpedo_template": {
        "name": "torpedo_template",
        "description": "Retrieve Torpedo templates from the sources matrix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string", "description": "2-letter code"},
                "source_type": {"type": "string", "description": "Source type (cr/news/etc)"},
            },
            "required": ["jurisdiction", "source_type"]
        }
    },
}


# Sync wrappers for tool handlers (for code that expects sync functions)
def _extract_tool_text(result: Dict[str, Any]) -> str:
    try:
        content = result.get("content", [])
        if not content:
            return ""
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("text", ""))
        return str(first)
    except Exception:
        return ""


def _parse_tool_text(text: str) -> Any:
    if text is None:
        return {"text": ""}
    try:
        return json.loads(text)
    except Exception:
        return {"text": text}


async def _call_tool(tool_fn, args: Dict[str, Any]) -> Any:
    handler = getattr(tool_fn, "handler", None)
    if callable(handler):
        result = await handler(args)
    else:
        result = await tool_fn(args)
    return _parse_tool_text(_extract_tool_text(result))


async def handle_execute(query: str, project_id: str = "default") -> Dict:
    return await _call_tool(execute_tool, {"query": query, "project_id": project_id})


async def handle_assess(project_id: str, mode: str = "all") -> Dict:
    return await _call_tool(assess_tool, {"project_id": project_id, "mode": mode})


async def handle_get_watchers(project_id: str) -> Dict:
    return await _call_tool(get_watchers_tool, {"project_id": project_id})


async def handle_create_watcher(project_id: str, query: str, label: str = "", type: str = "generic") -> Dict:
    return await _call_tool(create_watcher_tool, {"project_id": project_id, "query": query, "label": label, "type": type})


async def handle_stream_finding(watcher_id: str, content: str, source_url: str = None) -> Dict:
    return await _call_tool(stream_finding_tool, {"watcher_id": watcher_id, "content": content, "source_url": source_url})


async def handle_resolve(collision_id: str, decision: str, confidence: float = 0.9, reasoning: str = "", project_id: str = "default") -> Dict:
    return await _call_tool(resolve_tool, {
        "collision_id": collision_id, "decision": decision,
        "confidence": confidence, "reasoning": reasoning, "project_id": project_id
    })


async def handle_toggle_auto_scribe(enabled: bool) -> Dict:
    return await _call_tool(toggle_auto_scribe_tool, {"enabled": enabled})


async def handle_edith_rewrite(text: str, instructions: str) -> Dict:
    return await _call_tool(edith_rewrite_tool, {"text": text, "instructions": instructions})


async def handle_edith_answer(document: str, question: str) -> Dict:
    return await _call_tool(edith_answer_tool, {"document": document, "question": question})


async def handle_edith_edit_section(document_id: str, section_title: str, content: str) -> Dict:
    return await _call_tool(edith_edit_section_tool, {"document_id": document_id, "section_title": section_title, "content": content})


async def handle_edith_template_ops(op: str, genre: str = None, jurisdiction: str = None) -> Dict:
    args: Dict[str, Any] = {"op": op}
    if genre:
        args["genre"] = genre
    if jurisdiction:
        args["jurisdiction"] = jurisdiction
    return await _call_tool(edith_template_ops_tool, args)


async def handle_read_url(url: str) -> Dict:
    return await _call_tool(edith_read_url_tool, {"url": url})


async def handle_torpedo_search(query: str, type: str = "cr", jurisdiction: str = None, limit: int = 100) -> Dict:
    return await _call_tool(torpedo_search_tool, {"query": query, "type": type, "jurisdiction": jurisdiction, "limit": limit})


async def handle_torpedo_process(type: str = "cr", sources_file: str = "/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix/sources.json", jurisdiction: str = None, limit: int = None) -> Dict:
    return await _call_tool(torpedo_process_tool, {"type": type, "sources_file": sources_file, "jurisdiction": jurisdiction, "limit": limit})


async def handle_torpedo_template(jurisdiction: str, source_type: str) -> Dict:
    return await _call_tool(torpedo_template_tool, {"jurisdiction": jurisdiction, "source_type": source_type})


async def handle_query_lab_build(intent: str, **kwargs) -> Dict:
    args = {"intent": intent}
    args.update(kwargs)
    return await _call_tool(query_lab_build_tool, args)


# Tool handlers dict (for code that dispatches by name)
TOOL_HANDLERS = {
    "execute": handle_execute,
    "assess": handle_assess,
    "get_watchers": handle_get_watchers,
    "create_watcher": handle_create_watcher,
    "stream_finding": handle_stream_finding,
    "resolve": handle_resolve,
    "toggle_auto_scribe": handle_toggle_auto_scribe,
    "edith_rewrite": handle_edith_rewrite,
    "edith_answer": handle_edith_answer,
    "edith_edit_section": handle_edith_edit_section,
    "edith_template_ops": handle_edith_template_ops,
    "edith_read_url": handle_read_url,
    "torpedo_search": handle_torpedo_search,
    "torpedo_process": handle_torpedo_process,
    "torpedo_template": handle_torpedo_template,
    "query_lab_build": handle_query_lab_build,
}
