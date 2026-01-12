#!/usr/bin/env python3
"""
SerDavos - The Onion Knight
===========================

MCP server for dark web crawling, discovery, and search.
Named after Ser Davos Seaworth, the Onion Knight who smuggled
onions through blockades and navigated dangerous waters.

Tools:
- davos_discover: Search multiple onion search engines for URLs
- davos_scrape: Scrape selected results (3 | 1-6 | all | all -1,-3-5)
- davos_crawl: Crawl onion URLs and index to Elasticsearch
- davos_smuggle: Full pipeline (discover → crawl → index)
- davos_search: Search your crawled onion pages
- davos_engines: List available onion search engines
- davos_status: Get crawler status and stats
- davos_ahmia: Quick Ahmia search (no Tor needed)
- davos_graph: View/query discovery graph (search-to-domain relationships)

Discovery Graph:
All searches are logged with their results in a structured graph.
- Each .onion domain is a node
- Each search that found it is an edge (query + engine + timestamp)
- Persisted to discovery_graph.json
- Query by domain, search term, engine, or get top discovered sites

Usage:
    python mcp_server.py

Add to .mcp.json:
    "serdavos": {
        "command": "python3",
        "args": ["/path/to/linklater/tor/mcp_server.py"]
    }
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure pip-installed packages (e.g., mcp) take precedence over local LINKLATER modules
try:
    import site

    for _site in site.getsitepackages():
        if _site in sys.path:
            sys.path.remove(_site)
        sys.path.insert(0, _site)
except Exception:
    # If site is unavailable, continue with default sys.path
    pass

# Add parent modules to path (if not already via PYTHONPATH)
try:
    _parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
except NameError:
    pass  # Running in unusual context, rely on PYTHONPATH

from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import aiohttp

# Import our Tor modules
from modules.LINKLATER.scraping.tor import (
    TorCrawler,
    CrawlerConfig,
    CrawlerCallbacks,
    ScreenshotConfig,
    AhmiaDiscovery,
    OnionSearchDiscovery,
    ONION_SEARCH_ENGINES,
    search_tor_pages,
)

# Import ES backup manager for auto GDrive backup
try:
    from modules.LINKLATER.es_content_backup import get_backup_manager, ESBackupManager
    ES_BACKUP_AVAILABLE = True
except ImportError:
    ES_BACKUP_AVAILABLE = False
    ESBackupManager = None
    def get_backup_manager(*args, **kwargs):
        return None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("serdavos")

# Global state for tracking active crawls
ACTIVE_CRAWLS: Dict[str, Dict[str, Any]] = {}
CRAWL_RESULTS: Dict[str, Dict[str, Any]] = {}

# Store last discovery results for selection-based scraping
LAST_DISCOVERY: List[Dict[str, Any]] = []
LAST_QUERY: Optional[str] = None  # Store the query for screenshot folder naming


def parse_selection(selection: str, total: int) -> List[int]:
    """
    Parse flexible selection syntax into list of indices.

    Supported formats:
    - Single: "3"
    - Range: "1-6"
    - Multiple: "1, 2, 3"
    - Mixed: "1-6, 8, 10, 20-45"
    - All: "all"
    - All except Exception as e: "all -1, -3-5"

    Returns 0-indexed list of indices.
    """
    selection = selection.strip().lower()

    if not selection:
        return []

    # Handle "all" with optional exclusions
    if selection.startswith("all"):
        indices = set(range(total))

        # Check for exclusions after "all"
        remainder = selection[3:].strip()
        if remainder:
            # Parse exclusions (negative numbers or ranges)
            exclusions = set()
            parts = remainder.replace(",", " ").split()
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Remove leading minus if present
                if part.startswith("-"):
                    part = part[1:]
                if "-" in part:
                    # Range like "3-5"
                    try:
                        start, end = part.split("-", 1)
                        start = int(start.strip()) - 1  # Convert to 0-indexed
                        end = int(end.strip()) - 1
                        exclusions.update(range(start, end + 1))
                    except ValueError:
                        pass
                else:
                    # Single number
                    try:
                        exclusions.add(int(part) - 1)  # Convert to 0-indexed
                    except ValueError:
                        pass
            indices -= exclusions

        return sorted(list(indices))

    # Parse comma-separated items
    indices = set()
    parts = selection.replace(" ", "").split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "-" in part and not part.startswith("-"):
            # Range like "1-6"
            try:
                start, end = part.split("-", 1)
                start = int(start) - 1  # Convert to 0-indexed
                end = int(end) - 1
                indices.update(range(start, min(end + 1, total)))
            except ValueError:
                pass
        else:
            # Single number
            try:
                idx = int(part) - 1  # Convert to 0-indexed
                if 0 <= idx < total:
                    indices.add(idx)
            except ValueError:
                pass

    return sorted(list(indices))

# =============================================================================
# Elasticsearch Graph Indexer - Onion graph data in CYMONIDES-2 corpus
# =============================================================================

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")

# CYMONIDES MANDATE: Onion graph uses cymonides-2 with doc_type for filtering
# User decision: "the onion index should be a part of Cymonides-2 with different metadata"
C2_INDEX = "cymonides-2"
ONION_NODE_DOC_TYPE = "onion_node"
ONION_EDGE_DOC_TYPE = "onion_edge"

# Legacy names for backup manager compatibility (both point to C2)
ONION_GRAPH_NODES_INDEX = C2_INDEX
ONION_GRAPH_EDGES_INDEX = C2_INDEX

# Offline queue for when ES is down
OFFLINE_QUEUE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "es_offline_queue.jsonl"
)


class OnionGraphIndexer:
    """
    Indexes onion discovery graph data to Elasticsearch.
    Separate from main graph - uses dedicated indices.
    Includes offline queue for when ES is unavailable.
    """

    NODE_MAPPING = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "type": {"type": "keyword"},  # "query" or "onion"
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "domain": {"type": "keyword"},
                "query": {"type": "text"},
                "url": {"type": "keyword"},
                "title": {"type": "text"},
                "crawled": {"type": "boolean"},
                "crawled_pages": {"type": "integer"},
                "screenshots_taken": {"type": "integer"},
                "discovery_count": {"type": "integer"},
                "first_seen": {"type": "date"},
                "last_seen": {"type": "date"},
                "engines": {"type": "keyword"},  # List of engines that found this
                "metadata": {"type": "object", "enabled": False},
            }
        },
        "settings": {"number_of_shards": 1, "number_of_replicas": 0}
    }

    EDGE_MAPPING = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "from": {"type": "keyword"},
                "to": {"type": "keyword"},
                "type": {"type": "keyword"},  # "search_result" or "outlink"
                "engine": {"type": "keyword"},
                "keyword_match": {"type": "boolean"},
                "snippet": {"type": "text"},
                "created_at": {"type": "date"},
            }
        },
        "settings": {"number_of_shards": 1, "number_of_replicas": 0}
    }

    def __init__(self, gdrive_backup: bool = True):
        self.es_url = ES_URL
        self.auth = aiohttp.BasicAuth(ES_USER, ES_PASSWORD) if ES_PASSWORD else None
        self._indices_ready = False
        self._es_available = None  # None = unknown, True/False = known state

        # Initialize GDrive backup managers for nodes and edges
        self._backup_enabled = gdrive_backup and ES_BACKUP_AVAILABLE
        self._nodes_backup = None
        self._edges_backup = None
        if self._backup_enabled:
            self._nodes_backup = get_backup_manager(
                ONION_GRAPH_NODES_INDEX,
                gdrive_path="es_backups/tor",
                batch_size=100,  # Larger batches for small node records
            )
            self._edges_backup = get_backup_manager(
                ONION_GRAPH_EDGES_INDEX,
                gdrive_path="es_backups/tor",
                batch_size=500,  # Large batches for edge records
            )
            logger.info("[GDrive] Backup enabled for onion graph nodes and edges")

    async def _check_es_available(self) -> bool:
        """Check if ES is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.es_url}/_cluster/health",
                    auth=self.auth,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    self._es_available = resp.status == 200
                    return self._es_available
        except Exception as e:
            logger.warning(f"ES not available: {e}")
            self._es_available = False
            return False

    async def ensure_indices(self) -> bool:
        """
        Verify cymonides-2 index exists. CYMONIDES MANDATE: No separate indices.

        Onion graph data uses cymonides-2 with doc_type for filtering.
        The cymonides-2 index should already exist (created by main system).
        """
        if self._indices_ready:
            return True

        if not await self._check_es_available():
            return False

        try:
            async with aiohttp.ClientSession() as session:
                # Just verify cymonides-2 exists (should be created by main system)
                async with session.head(
                    f"{self.es_url}/{C2_INDEX}",
                    auth=self.auth
                ) as resp:
                    if resp.status == 404:
                        logger.warning(f"CYMONIDES-2 index ({C2_INDEX}) does not exist. Create it via main system.")
                        return False
                    logger.info(f"Using CYMONIDES-2 index ({C2_INDEX}) for onion graph data")

                self._indices_ready = True
                return True
        except Exception as e:
            logger.error(f"Failed to ensure index: {e}")
            return False

    async def index_node(self, node: Dict[str, Any]) -> bool:
        """Index a single node, queue if ES unavailable.

        CYMONIDES MANDATE: Nodes are indexed to cymonides-2 with doc_type for filtering.
        """
        if not await self.ensure_indices():
            self._queue_for_later("node", node)
            return False

        try:
            # CYMONIDES MANDATE: Add doc_type for filtering within cymonides-2
            node_with_type = {**node, "doc_type": ONION_NODE_DOC_TYPE}
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.es_url}/{C2_INDEX}/_doc/{node['id']}",
                    json=node_with_type,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status not in (200, 201):
                        logger.error(f"Failed to index node: {await resp.text()}")
                        self._queue_for_later("node", node)
                        return False

                    # Track node for GDrive backup
                    if self._backup_enabled and self._nodes_backup:
                        try:
                            await self._nodes_backup.track_document_async(node, doc_id=node['id'])
                        except Exception as backup_err:
                            logger.warning(f"[GDrive] Node backup tracking error: {backup_err}")

                    return True
        except Exception as e:
            logger.error(f"Failed to index node: {e}")
            self._queue_for_later("node", node)
            return False

    async def index_edge(self, edge: Dict[str, Any]) -> bool:
        """Index a single edge, queue if ES unavailable.

        CYMONIDES MANDATE: Edges are indexed to cymonides-2 with doc_type for filtering.
        """
        if not await self.ensure_indices():
            self._queue_for_later("edge", edge)
            return False

        try:
            edge_id = edge.get("id") or f"{edge['from']}_{edge['to']}_{edge.get('type', 'link')}"
            # CYMONIDES MANDATE: Add doc_type for filtering within cymonides-2
            edge_with_type = {**edge, "doc_type": ONION_EDGE_DOC_TYPE}
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.es_url}/{C2_INDEX}/_doc/{edge_id}",
                    json=edge_with_type,
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status not in (200, 201):
                        logger.error(f"Failed to index edge: {await resp.text()}")
                        self._queue_for_later("edge", edge)
                        return False

                    # Track edge for GDrive backup
                    if self._backup_enabled and self._edges_backup:
                        try:
                            await self._edges_backup.track_document_async(edge, doc_id=edge_id)
                        except Exception as backup_err:
                            logger.warning(f"[GDrive] Edge backup tracking error: {backup_err}")

                    return True
        except Exception as e:
            logger.error(f"Failed to index edge: {e}")
            self._queue_for_later("edge", edge)
            return False

    def _queue_for_later(self, doc_type: str, doc: Dict[str, Any]):
        """Add to offline queue for later sync."""
        try:
            entry = {"type": doc_type, "doc": doc, "queued_at": datetime.utcnow().isoformat()}
            with open(OFFLINE_QUEUE_PATH, 'a') as f:
                f.write(json.dumps(entry, default=str) + "\n")
            logger.info(f"Queued {doc_type} for later indexing")
        except Exception as e:
            logger.error(f"Failed to queue {doc_type}: {e}")

    async def process_offline_queue(self) -> Dict[str, int]:
        """Process any items in the offline queue."""
        if not os.path.exists(OFFLINE_QUEUE_PATH):
            return {"processed": 0, "failed": 0}

        if not await self._check_es_available():
            return {"processed": 0, "failed": 0, "reason": "ES unavailable"}

        processed = 0
        failed = 0
        remaining = []

        try:
            with open(OFFLINE_QUEUE_PATH, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        doc_type = entry.get("type")
                        doc = entry.get("doc")

                        if doc_type == "node":
                            success = await self.index_node(doc)
                        elif doc_type == "edge":
                            success = await self.index_edge(doc)
                        else:
                            success = False

                        if success:
                            processed += 1
                        else:
                            failed += 1
                            remaining.append(line)
                    except json.JSONDecodeError:
                        continue

            # Rewrite remaining items
            if remaining:
                with open(OFFLINE_QUEUE_PATH, 'w') as f:
                    f.writelines(remaining)
            else:
                os.remove(OFFLINE_QUEUE_PATH)

            logger.info(f"Processed offline queue: {processed} succeeded, {failed} failed")
            return {"processed": processed, "failed": failed}
        except Exception as e:
            logger.error(f"Failed to process offline queue: {e}")
            return {"processed": 0, "failed": 0, "error": str(e)}

    async def flush_backup(self) -> Dict[str, int]:
        """Flush any remaining documents in the backup buffers to GDrive."""
        result = {"nodes_flushed": 0, "edges_flushed": 0, "errors": []}

        if not self._backup_enabled:
            return result

        # Flush nodes backup
        if self._nodes_backup:
            try:
                await self._nodes_backup.flush()
                result["nodes_flushed"] = 1
                logger.info("[GDrive] Nodes backup flush completed")
            except Exception as e:
                result["errors"].append(f"nodes: {e}")
                logger.error(f"[GDrive] Nodes backup flush error: {e}")

        # Flush edges backup
        if self._edges_backup:
            try:
                await self._edges_backup.flush()
                result["edges_flushed"] = 1
                logger.info("[GDrive] Edges backup flush completed")
            except Exception as e:
                result["errors"].append(f"edges: {e}")
                logger.error(f"[GDrive] Edges backup flush error: {e}")

        return result

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics from ES indices.

        CYMONIDES MANDATE: Queries filter by doc_type within cymonides-2.
        """
        if not await self._check_es_available():
            return {"es_available": False}

        try:
            async with aiohttp.ClientSession() as session:
                # Count nodes (filter by doc_type)
                async with session.post(
                    f"{self.es_url}/{C2_INDEX}/_count",
                    json={"query": {"term": {"doc_type": ONION_NODE_DOC_TYPE}}},
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        node_count = (await resp.json()).get("count", 0)
                    else:
                        node_count = 0

                # Count edges (filter by doc_type)
                async with session.post(
                    f"{self.es_url}/{C2_INDEX}/_count",
                    json={"query": {"term": {"doc_type": ONION_EDGE_DOC_TYPE}}},
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        edge_count = (await resp.json()).get("count", 0)
                    else:
                        edge_count = 0

                # Count by node type (filter by doc_type first)
                async with session.post(
                    f"{self.es_url}/{C2_INDEX}/_search",
                    json={
                        "size": 0,
                        "query": {"term": {"doc_type": ONION_NODE_DOC_TYPE}},
                        "aggs": {
                            "by_type": {"terms": {"field": "type"}},
                            "crawled_count": {"filter": {"term": {"crawled": True}}},
                            "unique_domains": {"cardinality": {"field": "domain"}}
                        }
                    },
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        aggs = (await resp.json()).get("aggregations", {})
                        type_buckets = aggs.get("by_type", {}).get("buckets", [])
                        crawled_count = aggs.get("crawled_count", {}).get("doc_count", 0)
                        unique_domains = aggs.get("unique_domains", {}).get("value", 0)
                    else:
                        type_buckets = []
                        crawled_count = 0
                        unique_domains = 0

                return {
                    "es_available": True,
                    "total_nodes": node_count,
                    "total_edges": edge_count,
                    "query_nodes": next((b["doc_count"] for b in type_buckets if b["key"] == "query"), 0),
                    "onion_nodes": next((b["doc_count"] for b in type_buckets if b["key"] == "onion"), 0),
                    "crawled_sites": crawled_count,
                    "unique_domains": unique_domains,
                    "index": C2_INDEX,  # Show which index is being used
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"es_available": False, "error": str(e)}

    async def export_graph(self, max_nodes: int = 1000) -> Dict[str, Any]:
        """Export nodes and edges for visualization.

        CYMONIDES MANDATE: Queries filter by doc_type within cymonides-2.
        """
        if not await self._check_es_available():
            return {"nodes": [], "edges": [], "es_available": False}

        try:
            nodes = []
            edges = []

            async with aiohttp.ClientSession() as session:
                # Get nodes (filter by doc_type)
                async with session.post(
                    f"{self.es_url}/{C2_INDEX}/_search",
                    json={
                        "size": max_nodes,
                        "query": {"term": {"doc_type": ONION_NODE_DOC_TYPE}},
                        "sort": [{"last_seen": "desc"}]
                    },
                    auth=self.auth,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        hits = (await resp.json()).get("hits", {}).get("hits", [])
                        nodes = [h["_source"] for h in hits]

                # Get edges for these nodes (filter by doc_type)
                node_ids = [n["id"] for n in nodes]
                if node_ids:
                    async with session.post(
                        f"{self.es_url}/{C2_INDEX}/_search",
                        json={
                            "size": max_nodes * 2,
                            "query": {
                                "bool": {
                                    "must": [
                                        {"term": {"doc_type": ONION_EDGE_DOC_TYPE}}
                                    ],
                                    "should": [
                                        {"terms": {"from": node_ids}},
                                        {"terms": {"to": node_ids}}
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        },
                        auth=self.auth,
                        headers={"Content-Type": "application/json"}
                    ) as resp:
                        if resp.status == 200:
                            hits = (await resp.json()).get("hits", {}).get("hits", [])
                            edges = [h["_source"] for h in hits]

                return {"nodes": nodes, "edges": edges, "es_available": True, "index": C2_INDEX}
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
            return {"nodes": [], "edges": [], "error": str(e)}


# Global indexer instance
GRAPH_INDEXER = OnionGraphIndexer()

# Discovery graph - proper node/edge structure (in-memory + ES sync)
# Nodes: queries and onion sites
# Edges: search results (query->onion) and outlinks (onion->onion)
DISCOVERY_GRAPH: Dict[str, Any] = {
    "nodes": {},  # node_id -> {type, ...data}
    "edges": [],  # [{from, to, type, snippet, ...}]
}
SEARCH_LOG: List[Dict[str, Any]] = []  # Chronological log of all searches

# Graph storage path
GRAPH_STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "discovery_graph.json"
)
SEARCH_LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "search_log.jsonl"
)
EDGES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "edges.jsonl"
)


def load_discovery_graph():
    """Load existing graph from disk."""
    global DISCOVERY_GRAPH
    try:
        if os.path.exists(GRAPH_STORAGE_PATH):
            with open(GRAPH_STORAGE_PATH, 'r') as f:
                loaded = json.load(f)
                # Handle both old and new format
                if "nodes" in loaded and "edges" in loaded:
                    DISCOVERY_GRAPH = loaded
                else:
                    # Migrate old format
                    DISCOVERY_GRAPH = {"nodes": {}, "edges": []}
                    for domain, data in loaded.items():
                        node_id = f"onion:{domain}"
                        DISCOVERY_GRAPH["nodes"][node_id] = {
                            "type": "onion",
                            "domain": domain,
                            **{k: v for k, v in data.items() if k != "edges"}
                        }
            node_count = len(DISCOVERY_GRAPH.get("nodes", {}))
            edge_count = len(DISCOVERY_GRAPH.get("edges", []))
            logger.info(f"Loaded discovery graph: {node_count} nodes, {edge_count} edges")
    except Exception as e:
        logger.warning(f"Could not load discovery graph: {e}")
        DISCOVERY_GRAPH = {"nodes": {}, "edges": []}


def save_discovery_graph():
    """Save graph to disk."""
    try:
        with open(GRAPH_STORAGE_PATH, 'w') as f:
            json.dump(DISCOVERY_GRAPH, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Could not save discovery graph: {e}")


def save_edge(edge: Dict[str, Any]):
    """Append edge to edges.jsonl file."""
    try:
        with open(EDGES_PATH, 'a') as f:
            f.write(json.dumps(edge, default=str) + "\n")
    except Exception as e:
        logger.error(f"Could not write edge: {e}")


def log_search(query: str, engine: str, results: List[Dict], timestamp: str):
    """Log a search and its results to the search log."""
    entry = {
        "timestamp": timestamp,
        "query": query,
        "engine": engine,
        "result_count": len(results),
        "urls": [r.get("url") for r in results]
    }
    SEARCH_LOG.append(entry)

    # Append to JSONL file
    try:
        with open(SEARCH_LOG_PATH, 'a') as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.error(f"Could not write search log: {e}")


async def add_to_discovery_graph(query: str, engine: str, results: List[Dict], timestamp: str):
    """
    Add search results to the discovery graph.

    Creates:
    - Query node (the search itself)
    - Onion nodes (each discovered site)
    - Edges from query -> onion (with snippet from search results)

    Persists to both local JSON and ES (with offline queue fallback).
    """
    from urllib.parse import urlparse

    nodes = DISCOVERY_GRAPH["nodes"]
    edges = DISCOVERY_GRAPH["edges"]

    # Create/update query node
    query_id = f"query:{query.lower().strip()}"
    is_new_query = query_id not in nodes

    if is_new_query:
        nodes[query_id] = {
            "type": "query",
            "id": query_id,
            "query": query,
            "label": query,  # For ES/graph display
            "keywords": [k.strip() for k in query.lower().split() if len(k.strip()) > 2],
            "first_seen": timestamp,  # Consistent naming for ES
            "last_seen": timestamp,
            "first_searched": timestamp,
            "last_searched": timestamp,
            "search_count": 0,
            "engines_used": [],
        }

    query_node = nodes[query_id]
    query_node["last_searched"] = timestamp
    query_node["last_seen"] = timestamp
    query_node["search_count"] += 1
    if engine not in query_node["engines_used"]:
        query_node["engines_used"].append(engine)
    query_node["engines"] = query_node["engines_used"]  # ES field

    # Index query node to ES
    await GRAPH_INDEXER.index_node(query_node)

    for result in results:
        url = result.get("url", "")
        if not url:
            continue

        # Extract domain
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except Exception as e:
            continue

        if not domain.endswith('.onion'):
            continue

        # Create/update onion node
        onion_id = f"onion:{domain}"
        is_new_onion = onion_id not in nodes

        if is_new_onion:
            nodes[onion_id] = {
                "type": "onion",
                "id": onion_id,
                "domain": domain,
                "label": domain,  # For ES/graph display
                "first_seen": timestamp,
                "last_seen": timestamp,
                "urls": [],
                "titles": [],
                "discovery_count": 0,
                "crawled": False,
                "crawled_pages": 0,
                "screenshots_taken": 0,
            }

        onion_node = nodes[onion_id]
        onion_node["last_seen"] = timestamp
        onion_node["discovery_count"] += 1

        # Add URL if new
        if url not in onion_node["urls"]:
            onion_node["urls"].append(url)

        # Add title if available and new
        title = result.get("title", "")
        if title and title not in onion_node["titles"]:
            onion_node["titles"].append(title)
            onion_node["title"] = onion_node["titles"][0]  # Primary title for ES

        # Index onion node to ES
        await GRAPH_INDEXER.index_node(onion_node)

        # Create edge: query -> onion (search result)
        edge_id = f"{query_id}_{onion_id}_{engine}_{timestamp}"
        edge = {
            "id": edge_id,
            "from": query_id,
            "to": onion_id,
            "type": "search_result",
            "engine": engine,
            "url": url,
            "title": result.get("title", ""),
            "snippet": result.get("snippet", ""),
            "keyword_match": bool(result.get("kw")),
            "found_at": timestamp,
            "created_at": timestamp,
        }
        edges.append(edge)
        save_edge(edge)  # Also save to edges.jsonl

        # Index edge to ES
        await GRAPH_INDEXER.index_edge(edge)

    # Save full graph
    save_discovery_graph()


async def add_outlink_edge(from_domain: str, to_domain: str, context_snippet: str, found_on_url: str, timestamp: str):
    """
    Add an outlink edge: onion -> onion (discovered during crawling).

    Args:
        from_domain: Source .onion domain
        to_domain: Target .onion domain (the link)
        context_snippet: Text around the link on the page
        found_on_url: The specific URL where the link was found
        timestamp: When discovered

    Persists to both local JSON and ES (with offline queue fallback).
    """
    nodes = DISCOVERY_GRAPH["nodes"]
    edges = DISCOVERY_GRAPH["edges"]

    from_id = f"onion:{from_domain.lower()}"
    to_id = f"onion:{to_domain.lower()}"

    # Ensure both nodes exist
    for node_id, domain in [(from_id, from_domain), (to_id, to_domain)]:
        if node_id not in nodes:
            nodes[node_id] = {
                "type": "onion",
                "id": node_id,
                "domain": domain.lower(),
                "label": domain.lower(),  # For ES/graph display
                "first_seen": timestamp,
                "last_seen": timestamp,
                "urls": [],
                "titles": [],
                "discovery_count": 0,
                "crawled": False,
                "crawled_pages": 0,
                "screenshots_taken": 0,
            }
            # Index new node to ES
            await GRAPH_INDEXER.index_node(nodes[node_id])

    # Create edge: onion -> onion (outlink)
    edge_id = f"{from_id}_{to_id}_outlink_{timestamp}"
    edge = {
        "id": edge_id,
        "from": from_id,
        "to": to_id,
        "type": "outlink",
        "found_on_url": found_on_url,
        "snippet": context_snippet,
        "found_at": timestamp,
        "created_at": timestamp,
    }
    edges.append(edge)
    save_edge(edge)

    # Index edge to ES
    await GRAPH_INDEXER.index_edge(edge)

    save_discovery_graph()


def get_graph_stats() -> Dict[str, Any]:
    """Get statistics about the discovery graph (in-memory)."""
    nodes = DISCOVERY_GRAPH.get("nodes", {})
    edges = DISCOVERY_GRAPH.get("edges", [])

    if not nodes:
        return {"nodes": 0, "edges": 0, "queries": 0, "onions": 0}

    # Count node types
    query_nodes = [n for n in nodes.values() if n.get("type") == "query"]
    onion_nodes = [n for n in nodes.values() if n.get("type") == "onion"]

    # Count edge types
    search_edges = [e for e in edges if e.get("type") == "search_result"]
    outlink_edges = [e for e in edges if e.get("type") == "outlink"]

    # Get unique engines
    engines = set(e.get("engine", "") for e in search_edges if e.get("engine"))

    # Count unique domains
    unique_domains = len(set(n.get("domain") for n in onion_nodes if n.get("domain")))

    # Count crawled sites
    crawled_sites = len([n for n in onion_nodes if n.get("crawled")])

    return {
        "total_nodes": len(nodes),
        "query_nodes": len(query_nodes),
        "onion_nodes": len(onion_nodes),
        "total_edges": len(edges),
        "search_result_edges": len(search_edges),
        "outlink_edges": len(outlink_edges),
        "engines_used": list(engines),
        "unique_domains": unique_domains,
        "crawled_sites": crawled_sites,
        "recent_queries": [n.get("query") for n in query_nodes[-10:]],
    }


async def get_graph_stats_with_es() -> Dict[str, Any]:
    """Get statistics from both in-memory graph and ES."""
    # Get in-memory stats
    local_stats = get_graph_stats()

    # Try to get ES stats
    es_stats = await GRAPH_INDEXER.get_stats()

    # Combine, preferring ES when available
    if es_stats.get("es_available"):
        return {
            **local_stats,
            "es_available": True,
            "es_stats": es_stats,
            # Override with ES counts if available
            "total_nodes": es_stats.get("total_nodes", local_stats["total_nodes"]),
            "total_edges": es_stats.get("total_edges", local_stats["total_edges"]),
            "unique_domains": es_stats.get("unique_domains", local_stats["unique_domains"]),
            "crawled_sites": es_stats.get("crawled_sites", local_stats["crawled_sites"]),
        }
    else:
        return {
            **local_stats,
            "es_available": False,
        }


# Load graph on module import
load_discovery_graph()


def create_crawler_callbacks() -> CrawlerCallbacks:
    """Create crawler callbacks that hook into the discovery graph."""
    def on_outlink(from_domain: str, to_domain: str, context_snippet: str, found_on_url: str):
        """Callback invoked when an onion->onion link is discovered during crawling."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        # Schedule the async function to run in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(add_outlink_edge(from_domain, to_domain, context_snippet, found_on_url, timestamp))
        except RuntimeError:
            # No running loop, run synchronously in a new loop
            asyncio.run(add_outlink_edge(from_domain, to_domain, context_snippet, found_on_url, timestamp))

    return CrawlerCallbacks(on_outlink=on_outlink)

# Tor management
TOR_STARTED_BY_US = False


async def ensure_tor_running() -> Dict[str, Any]:
    """
    Ensure Tor is running. Start it if not.
    Returns status dict with 'running' bool and 'message'.
    """
    global TOR_STARTED_BY_US
    import subprocess
    import socket

    def is_tor_listening(port=9050):
        """Check if something is listening on the Tor SOCKS port."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception as e:
            return False

    # Check if Tor is already running
    if is_tor_listening(9050):
        return {"running": True, "message": "Tor already running on port 9050"}

    # Also check port 9150 (Tor Browser)
    if is_tor_listening(9150):
        return {"running": True, "port": 9150, "message": "Tor Browser running on port 9150"}

    # Try to start Tor
    logger.info("Tor not running, attempting to start...")

    # Try brew services first (macOS)
    try:
        result = subprocess.run(
            ["brew", "services", "start", "tor"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # Wait for Tor to be ready
            import time
            for _ in range(15):  # Wait up to 15 seconds
                time.sleep(1)
                if is_tor_listening(9050):
                    TOR_STARTED_BY_US = True
                    logger.info("Tor started successfully via brew")
                    return {"running": True, "started_by": "brew", "message": "Tor started via brew services"}
            return {"running": False, "message": "Tor started but not listening yet - try again in a few seconds"}
    except FileNotFoundError:
        pass  # brew not available
    except subprocess.TimeoutExpired:
        pass

    # Try starting tor directly
    try:
        subprocess.Popen(
            ["tor"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time
        for _ in range(15):
            time.sleep(1)
            if is_tor_listening(9050):
                TOR_STARTED_BY_US = True
                logger.info("Tor started successfully via direct command")
                return {"running": True, "started_by": "direct", "message": "Tor started directly"}
        return {"running": False, "message": "Tor process started but not listening - check logs"}
    except FileNotFoundError:
        return {"running": False, "message": "Tor not installed. Install with: brew install tor"}
    except Exception as e:
        return {"running": False, "message": f"Failed to start Tor: {e}"}


def get_tor_proxy() -> str:
    """Get the appropriate Tor proxy URL based on what's running."""
    import socket

    def is_listening(port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception as e:
            return False

    if is_listening(9050):
        return "socks5://127.0.0.1:9050"
    elif is_listening(9150):
        return "socks5://127.0.0.1:9150"
    else:
        return "socks5://127.0.0.1:9050"  # Default, will fail if Tor not running

# Create MCP server
server = Server("serdavos")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available SerDavos tools."""
    return [
        Tool(
            name="davos_discover",
            description="""Search multiple Tor/onion search engines to discover .onion URLs.

Searches up to 9 engines in parallel:
- Tor66, Ahmia (onion + clearnet), GDark, Candle
- DuckDuckGo Onion, Phobos, Excavator, Space, Fresh Onions

Returns discovered URLs grouped by engine, deduplicated.
Requires Tor SOCKS proxy running (default: 127.0.0.1:9050).

Use this to find onion sites related to a topic before crawling.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'cryptocurrency exchange', 'forum')"
                    },
                    "max_per_engine": {
                        "type": "integer",
                        "description": "Max results per engine (default: unlimited - engines self-limit)"
                    },
                    "engines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: specific engines to use (e.g., ['Tor66', 'Ahmia'])"
                    },
                    "include_clearnet_ahmia": {
                        "type": "boolean",
                        "description": "Also search Ahmia via clearnet (no Tor needed)",
                        "default": True
                    },
                    "tor_proxy": {
                        "type": "string",
                        "description": "Tor SOCKS proxy URL",
                        "default": "socks5://127.0.0.1:9050"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="davos_crawl",
            description="""Crawl onion URLs via Tor and index pages to Elasticsearch.

Features:
- Respects depth limits and per-domain page limits
- Extracts title, content, meta, outlinks
- Optional screenshots (triggered by keywords)
- Auto-zip and Google Drive upload for screenshots
- Resume from checkpoint
- Uses Ahmia's blocklist to skip illegal content

Pages are indexed to Elasticsearch for later searching.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "seed_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Onion URLs to crawl (e.g., ['http://example.onion/'])"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max link depth to follow (default: 2)",
                        "default": 2
                    },
                    "max_pages_per_domain": {
                        "type": "integer",
                        "description": "Max pages per domain (default: 100)",
                        "default": 100
                    },
                    "es_index": {
                        "type": "string",
                        "description": "Elasticsearch index name (default: onion-pages)",
                        "default": "onion-pages"
                    },
                    "screenshot": {
                        "type": "boolean",
                        "description": "Enable screenshots",
                        "default": False
                    },
                    "screenshot_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords that trigger screenshots"
                    },
                    "screenshot_zip_after": {
                        "type": "integer",
                        "description": "Create zip after N screenshots"
                    },
                    "screenshot_gdrive": {
                        "type": "boolean",
                        "description": "Upload screenshot zips to Google Drive",
                        "default": False
                    },
                    "tor_proxy": {
                        "type": "string",
                        "description": "Tor SOCKS proxy URL",
                        "default": "socks5://127.0.0.1:9050"
                    },
                    "run_async": {
                        "type": "boolean",
                        "description": "Run in background (returns job ID)",
                        "default": False
                    }
                },
                "required": ["seed_urls"]
            }
        ),
        Tool(
            name="davos_smuggle",
            description="""Full pipeline: discover URLs from search engines, then crawl them.

1. Searches all onion search engines for your query
2. Deduplicates and extracts unique domains
3. Crawls discovered URLs
4. Indexes pages to Elasticsearch
5. Optional: screenshots with auto-zip and GDrive upload

This is the main tool for exploring a topic on the dark web.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for discovery"
                    },
                    "max_discovery_results": {
                        "type": "integer",
                        "description": "Max URLs to discover per engine (default: 30)",
                        "default": 30
                    },
                    "max_seeds": {
                        "type": "integer",
                        "description": "Max seed URLs to crawl (default: 50)",
                        "default": 50
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Crawl depth from seeds (default: 2)",
                        "default": 2
                    },
                    "es_index": {
                        "type": "string",
                        "description": "Elasticsearch index",
                        "default": "onion-pages"
                    },
                    "screenshot": {
                        "type": "boolean",
                        "description": "Enable screenshots",
                        "default": False
                    },
                    "screenshot_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Screenshot trigger keywords"
                    },
                    "run_async": {
                        "type": "boolean",
                        "description": "Run in background",
                        "default": True
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="davos_search",
            description="""Search your crawled onion pages in Elasticsearch.

Full-text search across title, content, meta, and URL.
Returns matching pages with snippets and highlights.

Use this to find specific content in pages you've already crawled.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                        "default": 20
                    },
                    "es_index": {
                        "type": "string",
                        "description": "Elasticsearch index",
                        "default": "onion-pages"
                    },
                    "source_filter": {
                        "type": "string",
                        "description": "Filter by source (e.g., 'local_crawler', 'ahmia_import')"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="davos_engines",
            description="List available onion search engines for discovery.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="davos_status",
            description="""Get status of active/completed crawls.

Returns:
- Active crawl jobs
- Recent crawl results
- Elasticsearch index stats""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Optional: specific job ID to check"
                    }
                }
            }
        ),
        Tool(
            name="davos_ahmia",
            description="""Quick search via Ahmia clearnet (no Tor required).

Fast way to find onion URLs without needing Tor proxy running.
Ahmia filters illegal content by design.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default: 50)",
                        "default": 50
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="davos_scrape",
            description="""Scrape selected results from last discovery.

Selection syntax:
- Single: "3"
- Range: "1-6"
- Multiple: "1, 2, 3"
- Mixed: "1-6, 8, 10, 20-45"
- All: "all"
- All except Exception as e: "all -1, -3-5"

Crawls selected URLs and indexes to Elasticsearch.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "select": {
                        "type": "string",
                        "description": "Selection (e.g., '3', '1-6', '1,2,3', 'all', 'all -1,-3-5')"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Crawl depth (default: 1 for quick scrape)",
                        "default": 1
                    },
                    "screenshot": {
                        "type": "boolean",
                        "description": "Take screenshots",
                        "default": False
                    }
                },
                "required": ["select"]
            }
        ),
        Tool(
            name="davos_graph",
            description="""View and query the discovery graph (node/edge structure).

Graph Structure:
- NODES: query nodes (searches) and onion nodes (sites)
- EDGES: search_result (query→onion) and outlink (onion→onion)

Query Nodes (query:{search_term}):
- query, keywords, first_searched, search_count, engines_used

Onion Nodes (onion:{domain}):
- domain, urls, titles, first_seen, last_seen, discovery_count

Edges contain: from, to, type, snippet, engine (search_result) or found_on_url (outlink)

Use this to:
- See what searches found a specific domain (with snippets)
- See what domains were found by a query
- View link relationships between onion sites
- Get graph statistics (nodes, edges by type)
- Export the full graph + edges.jsonl""",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "View .onion domain node + all edges (search results, inbound/outbound links)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Find domains discovered by queries containing this term (with snippets)"
                    },
                    "engine": {
                        "type": "string",
                        "description": "Filter by search engine (e.g., 'Tor66', 'Ahmia')"
                    },
                    "stats_only": {
                        "type": "boolean",
                        "description": "Return only graph statistics (node/edge counts by type)",
                        "default": False
                    },
                    "export": {
                        "type": "boolean",
                        "description": "Export full graph JSON + paths to storage files",
                        "default": False
                    },
                    "top_domains": {
                        "type": "integer",
                        "description": "Return top N most-discovered domains with edge stats"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""

    try:
        if name == "davos_discover":
            result = await handle_discover(arguments)
        elif name == "davos_crawl":
            result = await handle_crawl(arguments)
        elif name == "davos_smuggle":
            result = await handle_discover_and_crawl(arguments)
        elif name == "davos_search":
            result = await handle_search(arguments)
        elif name == "davos_engines":
            result = await handle_list_engines(arguments)
        elif name == "davos_status":
            result = await handle_get_status(arguments)
        elif name == "davos_ahmia":
            result = await handle_ahmia_search(arguments)
        elif name == "davos_scrape":
            result = await handle_scrape(arguments)
        elif name == "davos_graph":
            result = await handle_graph(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "tool": name,
        }, indent=2))]


async def handle_discover(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_discover tool."""
    query = args["query"]
    max_per_engine = args.get("max_per_engine", 500)  # High default, let engines limit naturally
    engines = args.get("engines")
    include_clearnet = args.get("include_clearnet_ahmia", True)

    # Auto-start Tor if needed
    tor_status = await ensure_tor_running()
    if not tor_status.get("running"):
        return {
            "error": "Tor not available",
            "message": tor_status.get("message"),
            "suggestion": "Install Tor with: brew install tor && brew services start tor",
        }

    tor_proxy = get_tor_proxy()

    discovery = OnionSearchDiscovery(
        tor_proxy=tor_proxy,
        include_clearnet_ahmia=include_clearnet,
        engines=engines,
    )

    try:
        results = await discovery.search_all(query, max_per_engine=max_per_engine)
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Log each engine's results to the graph
        for engine_name, engine_results in results["engines"].items():
            if engine_results:
                log_search(query, engine_name, engine_results, timestamp)
                await add_to_discovery_graph(query, engine_name, engine_results, timestamp)

        # Engine code mapping (3-letter with 't' prefix for Tor engines)
        ENGINE_CODES = {
            "Tor66": "tT6",
            "Ahmia (Onion)": "tAO",
            "Ahmia (Clearnet)": "tAH",
            "GDark": "tGD",
            "Candle": "tCA",
            "DuckDuckGo Onion": "tDD",
            "Phobos": "tPH",
            "Excavator": "tEX",
            "Space": "tSP",
            "Fresh Onions": "tFO",
        }

        # Extract keywords from query for matching
        query_lower = query.lower()
        keywords = [k.strip() for k in query_lower.replace('"', '').split() if len(k.strip()) > 2]

        def has_keyword(result: Dict) -> bool:
            """Check if result contains any search keyword."""
            text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
            return any(kw in text for kw in keywords)

        # Build results and check for keyword presence
        global LAST_DISCOVERY, LAST_QUERY
        LAST_QUERY = query  # Store query for screenshot folder naming
        matches = []
        non_matches = []

        for r in results["unique_urls"]:
            engine = r.get("engine", "")
            code = ENGINE_CODES.get(engine, engine[:2].upper())
            has_kw = has_keyword(r)

            item = {
                "url": r.get("url"),
                "title": r.get("title", r.get("domain", "")),
                "snippet": r.get("snippet", ""),
                "src": f"[{code}]",
                "kw": has_kw,  # True if contains keyword
            }

            if has_kw:
                matches.append(item)
            else:
                non_matches.append(item)

        # Combine: matches first, then gap marker, then rest
        unified_results = []
        for i, item in enumerate(matches, 1):
            item["n"] = i
            item["match"] = "✓"
            unified_results.append(item)

        match_count = len(matches)

        # Add gap marker if there are both matches and non-matches
        if matches and non_matches:
            unified_results.append({
                "n": "---",
                "url": "--- RESULTS WITHOUT KEYWORD BELOW ---",
                "title": "",
                "snippet": "",
                "src": "",
                "kw": False,
                "match": "",
            })

        for i, item in enumerate(non_matches, match_count + 1):
            item["n"] = i
            item["match"] = ""
            unified_results.append(item)

        # Store for selection-based scraping (exclude gap marker)
        LAST_DISCOVERY = [r for r in unified_results if r.get("n") != "---"]

        return {
            "query": query,
            "keywords": keywords,
            "total": results["total"],
            "with_keyword": match_count,
            "without_keyword": len(non_matches),
            "results": unified_results,
            "engines": "tT6=Tor66, tAO=Ahmia(Onion), tAH=Ahmia, tGD=GDark, tCA=Candle, tDD=DDG, tPH=Phobos, tEX=Excavator, tSP=Space, tFO=FreshOnions",
            "select": "Use davos_scrape with: 3 | 1-6 | 1,2,3 | 1-6,8,10 | all | all -1,-3-5",
            "graph_stats": get_graph_stats(),
        }
    finally:
        await discovery.close()


async def handle_crawl(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_crawl tool."""
    seed_urls = args["seed_urls"]
    max_depth = args.get("max_depth", 2)
    max_pages = args.get("max_pages_per_domain", 100)
    es_index = args.get("es_index", "onion-pages")
    run_async = args.get("run_async", False)

    # Get search query for screenshot organization (optional, derived from seed URLs if not provided)
    search_query = args.get("search_query")
    if not search_query and seed_urls:
        # Derive from first seed URL's domain
        from urllib.parse import urlparse
        parsed = urlparse(seed_urls[0])
        search_query = parsed.netloc.split('.')[0] if parsed.netloc else "crawl"

    # Auto-start Tor if needed
    tor_status = await ensure_tor_running()
    if not tor_status.get("running"):
        return {
            "error": "Tor not available",
            "message": tor_status.get("message"),
            "suggestion": "Install Tor with: brew install tor && brew services start tor",
        }

    tor_proxy = get_tor_proxy()

    # Screenshot config - defaults to zip every 10 and upload to GDrive
    screenshot_config = None
    if args.get("screenshot"):
        screenshot_config = ScreenshotConfig(
            enabled=True,
            trigger_keywords=args.get("screenshot_keywords", []),
            zip_after=args.get("screenshot_zip_after", 10),  # Default: zip every 10
            gdrive_upload=args.get("screenshot_gdrive", True),  # Default: auto-upload
        )

    config = CrawlerConfig(
        tor_proxies=[tor_proxy],
        es_index=es_index,
        max_depth=max_depth,
        max_pages_per_domain=max_pages,
        screenshot_config=screenshot_config,
        search_query=search_query,  # For organizing screenshots by search query
    )

    # Create callbacks for graph tracking
    callbacks = create_crawler_callbacks()
    crawler = TorCrawler(seed_urls=seed_urls, config=config, callbacks=callbacks)

    if run_async:
        # Run in background
        job_id = f"crawl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        ACTIVE_CRAWLS[job_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "seed_urls": seed_urls,
            "config": {"max_depth": max_depth, "max_pages": max_pages},
        }

        async def run_crawl():
            try:
                stats = await crawler.run()
                CRAWL_RESULTS[job_id] = stats
                ACTIVE_CRAWLS[job_id]["status"] = "completed"
            except Exception as e:
                ACTIVE_CRAWLS[job_id]["status"] = "failed"
                ACTIVE_CRAWLS[job_id]["error"] = str(e)

        asyncio.create_task(run_crawl())

        return {
            "job_id": job_id,
            "status": "started",
            "seed_urls": len(seed_urls),
            "message": "Crawl started in background. Use tor_get_status to check progress.",
        }
    else:
        # Run synchronously
        stats = await crawler.run()
        return {
            "status": "completed",
            "stats": stats,
        }


async def handle_discover_and_crawl(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_smuggle tool."""
    query = args["query"]
    max_discovery = args.get("max_discovery_results", 30)
    max_seeds = args.get("max_seeds", 50)
    max_depth = args.get("max_depth", 2)
    es_index = args.get("es_index", "onion-pages")
    run_async = args.get("run_async", True)

    # Auto-start Tor if needed
    tor_status = await ensure_tor_running()
    if not tor_status.get("running"):
        return {
            "error": "Tor not available",
            "message": tor_status.get("message"),
            "suggestion": "Install Tor with: brew install tor && brew services start tor",
        }

    # Screenshot config - defaults to zip every 10 and upload to GDrive
    screenshot_config = None
    if args.get("screenshot"):
        screenshot_config = ScreenshotConfig(
            enabled=True,
            trigger_keywords=args.get("screenshot_keywords", []),
            zip_after=10,  # Zip every 10 screenshots
            gdrive_upload=True,  # Auto-upload to GDrive
        )

    config = CrawlerConfig(
        es_index=es_index,
        max_depth=max_depth,
        screenshot_config=screenshot_config,
        search_query=query,  # For organizing screenshots by search query
    )

    discovery = OnionSearchDiscovery()

    job_id = f"discover_crawl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    if run_async:
        ACTIVE_CRAWLS[job_id] = {
            "status": "discovering",
            "started_at": datetime.utcnow().isoformat(),
            "query": query,
        }

        async def run_pipeline():
            try:
                # Discover
                ACTIVE_CRAWLS[job_id]["status"] = "discovering"
                results = await discovery.search_all(query, max_per_engine=max_discovery)
                seeds = await discovery.get_seed_urls(query, max_seeds=max_seeds)

                # Log to discovery graph
                timestamp = datetime.utcnow().isoformat() + "Z"
                for engine_name, engine_results in results["engines"].items():
                    if engine_results:
                        log_search(query, engine_name, engine_results, timestamp)
                        await add_to_discovery_graph(query, engine_name, engine_results, timestamp)

                ACTIVE_CRAWLS[job_id]["discovered_urls"] = results["total"]
                ACTIVE_CRAWLS[job_id]["seeds"] = len(seeds)
                ACTIVE_CRAWLS[job_id]["graph_stats"] = get_graph_stats()
                ACTIVE_CRAWLS[job_id]["status"] = "crawling"

                # Crawl with graph callbacks
                callbacks = create_crawler_callbacks()
                crawler = TorCrawler(seed_urls=seeds, config=config, callbacks=callbacks)
                stats = await crawler.run()

                CRAWL_RESULTS[job_id] = {
                    "discovery": {"total": results["total"], "seeds": len(seeds)},
                    "crawl": stats,
                }
                ACTIVE_CRAWLS[job_id]["status"] = "completed"

            except Exception as e:
                ACTIVE_CRAWLS[job_id]["status"] = "failed"
                ACTIVE_CRAWLS[job_id]["error"] = str(e)
            finally:
                await discovery.close()

        asyncio.create_task(run_pipeline())

        return {
            "job_id": job_id,
            "status": "started",
            "query": query,
            "message": "Discovery + crawl pipeline started. Use tor_get_status to check progress.",
        }
    else:
        try:
            # Do discovery and log to graph
            search_results = await discovery.search_all(query, max_per_engine=max_discovery)
            seeds = await discovery.get_seed_urls(query, max_seeds=max_seeds)

            # Log to discovery graph
            timestamp = datetime.utcnow().isoformat() + "Z"
            for engine_name, engine_results in search_results["engines"].items():
                if engine_results:
                    log_search(query, engine_name, engine_results, timestamp)
                    await add_to_discovery_graph(query, engine_name, engine_results, timestamp)

            # Crawl with graph callbacks
            callbacks = create_crawler_callbacks()
            crawler = TorCrawler(seed_urls=seeds, config=config, callbacks=callbacks)
            crawl_stats = await crawler.run()

            return {
                "discovery": {
                    "query": query,
                    "total": search_results["total"],
                    "seeds": len(seeds),
                },
                "crawl": crawl_stats,
                "graph_stats": get_graph_stats(),
            }
        finally:
            await discovery.close()


async def handle_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tor_search tool."""
    query = args["query"]
    max_results = args.get("max_results", 20)
    es_index = args.get("es_index", "onion-pages")
    source_filter = args.get("source_filter")

    # Import the search function from brute module for full ES integration
    try:
        from modules.BRUTE.targeted_searches.special.tor import search_local_onion_index
        results = await search_local_onion_index(
            query,
            max_results=max_results,
            index=es_index,
            source_filter=source_filter,
        )
    except ImportError as e:
        logger.warning(f"Could not import search_local_onion_index: {e}, returning empty results")
        results = []

    return {
        "query": query,
        "total": len(results),
        "results": results,
    }


async def handle_list_engines(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tor_list_engines tool."""
    engines = OnionSearchDiscovery.list_engines()
    return {
        "total": len(engines),
        "engines": engines,
        "note": "All onion engines require Tor proxy. Ahmia (Clearnet) works without Tor.",
    }


async def handle_get_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_status tool."""
    job_id = args.get("job_id")

    # Check Tor status
    tor_status = await ensure_tor_running()

    if job_id:
        if job_id in ACTIVE_CRAWLS:
            status = ACTIVE_CRAWLS[job_id].copy()
            if job_id in CRAWL_RESULTS:
                status["results"] = CRAWL_RESULTS[job_id]
            status["tor"] = tor_status
            return status
        else:
            return {"error": f"Job not found: {job_id}", "tor": tor_status}

    return {
        "tor": tor_status,
        "tor_proxy": get_tor_proxy() if tor_status.get("running") else None,
        "active_crawls": ACTIVE_CRAWLS,
        "completed_results": list(CRAWL_RESULTS.keys()),
    }


async def handle_ahmia_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tor_ahmia_search tool (clearnet, no Tor needed)."""
    query = args["query"]
    max_results = args.get("max_results", 50)

    ahmia = AhmiaDiscovery()
    try:
        results = await ahmia.search(query, max_results=max_results)
        return {
            "query": query,
            "total": len(results),
            "urls": [r["url"] for r in results],
            "results": results[:20],  # First 20 with full details
        }
    finally:
        await ahmia.close()


async def handle_scrape(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_scrape tool - scrape selected discovery results."""
    selection = args["select"]
    max_depth = args.get("max_depth", 1)
    screenshot = args.get("screenshot", False)

    # Get search query for screenshot organization
    search_query = args.get("search_query") or LAST_QUERY or "scrape"

    if not LAST_DISCOVERY:
        return {
            "error": "No discovery results available",
            "hint": "Run davos_discover first to get results to scrape",
        }

    # Parse selection
    indices = parse_selection(selection, len(LAST_DISCOVERY))

    if not indices:
        return {
            "error": f"No valid indices from selection: {selection}",
            "available": f"1-{len(LAST_DISCOVERY)}",
            "syntax": "3 | 1-6 | 1,2,3 | 1-6,8,10 | all | all -1,-3-5",
        }

    # Get selected URLs
    selected = [LAST_DISCOVERY[i] for i in indices if i < len(LAST_DISCOVERY)]
    urls = [r["url"] for r in selected]

    if not urls:
        return {"error": "No URLs selected"}

    # Auto-start Tor
    tor_status = await ensure_tor_running()
    if not tor_status.get("running"):
        return {
            "error": "Tor not available",
            "message": tor_status.get("message"),
        }

    tor_proxy = get_tor_proxy()

    # Screenshot config - defaults to zip every 10 and upload to GDrive
    screenshot_config = None
    if screenshot:
        screenshot_config = ScreenshotConfig(
            enabled=True,
            zip_after=10,  # Zip every 10 screenshots
            gdrive_upload=True,  # Auto-upload to GDrive
        )

    config = CrawlerConfig(
        tor_proxies=[tor_proxy],
        es_index="onion-pages",
        max_depth=max_depth,
        max_pages_per_domain=50,
        screenshot_config=screenshot_config,
        search_query=search_query,  # For organizing screenshots by search query
    )

    # Create callbacks for graph tracking
    callbacks = create_crawler_callbacks()
    crawler = TorCrawler(seed_urls=urls, config=config, callbacks=callbacks)

    # Show what we're about to scrape
    scrape_preview = [
        {"n": r["n"], "url": r["url"], "title": r["title"][:50]}
        for r in selected[:10]
    ]

    # Run crawl
    try:
        stats = await crawler.run()
        return {
            "status": "completed",
            "selected": len(selected),
            "selection": selection,
            "preview": scrape_preview,
            "stats": stats,
        }
    except Exception as e:
        return {
            "error": str(e),
            "selected": len(selected),
            "preview": scrape_preview,
        }


async def handle_graph(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle davos_graph tool - view and query the discovery graph."""
    nodes = DISCOVERY_GRAPH.get("nodes", {})
    edges = DISCOVERY_GRAPH.get("edges", [])

    # Stats only - use ES-enhanced version
    if args.get("stats_only"):
        return await get_graph_stats_with_es()

    # Export full graph - include ES data if available
    if args.get("export"):
        es_export = await GRAPH_INDEXER.export_graph()
        return {
            "graph": DISCOVERY_GRAPH,
            "stats": await get_graph_stats_with_es(),
            "storage_path": GRAPH_STORAGE_PATH,
            "edges_path": EDGES_PATH,
            "es_export": es_export if es_export.get("es_available") else None,
            "es_indices": {
                "nodes": ONION_GRAPH_NODES_INDEX,
                "edges": ONION_GRAPH_EDGES_INDEX,
            },
        }

    # Top domains by discovery count
    top_n = args.get("top_domains")
    if top_n:
        # Filter to onion nodes only
        onion_nodes = [
            (node_id, node) for node_id, node in nodes.items()
            if node.get("type") == "onion"
        ]
        sorted_onions = sorted(
            onion_nodes,
            key=lambda x: x[1].get("discovery_count", 0),
            reverse=True
        )[:top_n]

        # Get edges for each top domain
        result_list = []
        for node_id, node in sorted_onions:
            # Find all edges pointing TO this onion (search results)
            incoming = [e for e in edges if e.get("to") == node_id and e.get("type") == "search_result"]
            # Find all edges going FROM this onion (outlinks)
            outgoing = [e for e in edges if e.get("from") == node_id and e.get("type") == "outlink"]

            result_list.append({
                "domain": node.get("domain"),
                "discovery_count": node.get("discovery_count", 0),
                "first_seen": node.get("first_seen"),
                "last_seen": node.get("last_seen"),
                "url_count": len(node.get("urls", [])),
                "search_edges": len(incoming),
                "outlink_edges": len(outgoing),
                "sample_titles": node.get("titles", [])[:3],
                "found_by_queries": list(set(
                    nodes.get(e.get("from"), {}).get("query", "")
                    for e in incoming
                ))[:5],
            })

        return {
            "top_domains": result_list,
            "stats": get_graph_stats(),
        }

    # View specific domain
    domain = args.get("domain")
    if domain:
        # Normalize domain (remove http://, trailing slashes, etc.)
        domain = domain.lower().strip()
        if domain.startswith("http://"):
            domain = domain[7:]
        if domain.startswith("https://"):
            domain = domain[8:]
        domain = domain.rstrip("/").split("/")[0]

        node_id = f"onion:{domain}"
        if node_id in nodes:
            node = nodes[node_id]

            # Find all edges for this domain
            incoming = [e for e in edges if e.get("to") == node_id]
            outgoing = [e for e in edges if e.get("from") == node_id]

            # Group incoming by type
            search_results = [e for e in incoming if e.get("type") == "search_result"]
            inbound_links = [e for e in incoming if e.get("type") == "outlink"]
            outbound_links = [e for e in outgoing if e.get("type") == "outlink"]

            return {
                "domain": domain,
                "node": node,
                "edge_summary": {
                    "search_results": len(search_results),
                    "inbound_links": len(inbound_links),
                    "outbound_links": len(outbound_links),
                    "unique_queries": list(set(
                        nodes.get(e.get("from"), {}).get("query", "")
                        for e in search_results
                    )),
                    "engines_found_by": list(set(e.get("engine") for e in search_results if e.get("engine"))),
                    "links_to": list(set(
                        nodes.get(e.get("to"), {}).get("domain", "")
                        for e in outbound_links
                    ))[:10],
                    "linked_from": list(set(
                        nodes.get(e.get("from"), {}).get("domain", "")
                        for e in inbound_links
                    ))[:10],
                },
                "sample_search_results": [
                    {"query": nodes.get(e.get("from"), {}).get("query", ""), "engine": e.get("engine"), "snippet": e.get("snippet", "")[:100]}
                    for e in search_results[:5]
                ],
            }
        else:
            # Try partial match
            matches = [
                nodes[nid].get("domain")
                for nid in nodes
                if nodes[nid].get("type") == "onion" and domain in nodes[nid].get("domain", "")
            ]
            if matches:
                return {
                    "error": f"Domain '{domain}' not found",
                    "partial_matches": matches[:10],
                }
            return {"error": f"Domain '{domain}' not found in graph"}

    # Find domains by query term
    search_query = args.get("query")
    engine_filter = args.get("engine")

    if search_query or engine_filter:
        # Find matching edges
        matching_edges = []
        for edge in edges:
            if edge.get("type") != "search_result":
                continue

            # Check query match (look at the source query node)
            from_node = nodes.get(edge.get("from"), {})
            query_text = from_node.get("query", "")
            query_match = not search_query or search_query.lower() in query_text.lower()

            # Check engine match
            engine_match = not engine_filter or edge.get("engine") == engine_filter

            if query_match and engine_match:
                matching_edges.append(edge)

        # Group by destination domain
        domains_found = {}
        for edge in matching_edges:
            to_node = nodes.get(edge.get("to"), {})
            domain = to_node.get("domain", "")
            if domain not in domains_found:
                domains_found[domain] = {
                    "domain": domain,
                    "edges": [],
                    "snippets": [],
                    "engines": set(),
                }
            domains_found[domain]["edges"].append(edge)
            if edge.get("snippet"):
                domains_found[domain]["snippets"].append(edge.get("snippet")[:150])
            domains_found[domain]["engines"].add(edge.get("engine", ""))

        # Convert sets to lists for JSON
        for d in domains_found.values():
            d["engines"] = list(d["engines"])
            d["edge_count"] = len(d["edges"])
            d["edges"] = d["edges"][:3]  # Limit to 3 sample edges
            d["snippets"] = d["snippets"][:3]  # Limit to 3 snippets

        return {
            "filter": {
                "query": search_query,
                "engine": engine_filter,
            },
            "match_count": len(domains_found),
            "domains": domains_found,
        }

    # Default: return stats and samples
    stats = await get_graph_stats_with_es()

    # Get sample query nodes
    query_nodes = [
        {"query": n.get("query"), "search_count": n.get("search_count", 0)}
        for n in nodes.values() if n.get("type") == "query"
    ][:5]

    # Get sample onion nodes
    onion_nodes = [
        {"domain": n.get("domain"), "discovery_count": n.get("discovery_count", 0)}
        for n in nodes.values() if n.get("type") == "onion"
    ][:5]

    # Get sample edges
    sample_edges = [
        {
            "type": e.get("type"),
            "from": e.get("from"),
            "to": e.get("to"),
            "snippet": (e.get("snippet") or "")[:80],
        }
        for e in edges[:5]
    ]

    return {
        "stats": stats,
        "sample_queries": query_nodes,
        "sample_domains": onion_nodes,
        "sample_edges": sample_edges,
        "es_indices": {
            "nodes": ONION_GRAPH_NODES_INDEX,
            "edges": ONION_GRAPH_EDGES_INDEX,
        },
        "hint": "Use 'domain', 'query', 'engine', 'top_domains', 'stats_only', or 'export' params to query the graph",
    }


async def main():
    """Run the MCP server."""
    logger.info("Starting SerDavos - The Onion Knight...")

    # Process any offline queue items on startup
    if os.path.exists(OFFLINE_QUEUE_PATH):
        logger.info("Found offline queue, attempting to process...")
        result = await GRAPH_INDEXER.process_offline_queue()
        logger.info(f"Offline queue processed: {result}")

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
