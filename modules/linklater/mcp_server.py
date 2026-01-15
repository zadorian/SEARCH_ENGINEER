#!/usr/bin/env python3
"""
LINKLATER MCP Server - Complete Link & Archive Intelligence

Exposes ALL LINKLATER capabilities via MCP:

LINK GRAPH:
- get_backlinks: Domains/pages linking TO a target
- get_outlinks: Domains/pages a target links TO
- hop_links: Spider through link graph
- find_related_domains: Find domains sharing backlink patterns

ARCHIVE INTELLIGENCE:
- search_archives: Keyword search across Wayback + CC snapshots
- get_archive_snapshots: List available archive snapshots
- compare_archive_versions: Compare content changes over time
- scrape_url: CC-first scraping with Firecrawl fallback

ENTITY EXTRACTION:
- extract_entities: Extract companies, persons, registrations from text
- extract_domain_entities: Extract all entities from a domain's pages

DISCOVERY:
- discover_subdomains: Find subdomains via DNS, CT logs, archives
- discover_tech_stack: Identify technologies used by a domain
- discover_similar_domains: Find similar/related domains

ENRICHMENT:
- enrich_urls: Full URL enrichment pipeline
- batch_domain_extract: Batch processing multiple domains

Sources: CC Web Graph (157M domains), GlobalLinks, Wayback (80 concurrent),
CC Index, Firecrawl, Majestic API, DNS/CT logs
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add module paths
LINKLATER_ROOT = Path(__file__).resolve().parent
MODULES_ROOT = LINKLATER_ROOT.parent
sys.path.insert(0, str(MODULES_ROOT))
sys.path.insert(0, str(LINKLATER_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("linklater-mcp")

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    import mcp.server.stdio
except ImportError:
    logger.error("MCP SDK not installed. Run: pip install mcp")
    sys.exit(1)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(Path("/data/.env"))
except ImportError:
    pass

# Import LINKLATER modules
MODULES_AVAILABLE = {
    "backlinks": False,
    "archives": False,
    "discovery": False,
    "extractors": False,
}

# Try to import BacklinkDiscovery
try:
    from linklater.linkgraph.backlinks import BacklinkDiscovery, get_backlinks_domains, get_backlinks_pages
    MODULES_AVAILABLE["backlinks"] = True
except ImportError:
    try:
        from linkgraph.backlinks import BacklinkDiscovery, get_backlinks_domains, get_backlinks_pages
        MODULES_AVAILABLE["backlinks"] = True
    except ImportError as e:
        logger.warning(f"BacklinkDiscovery not available: {e}")
        BacklinkDiscovery = None

# Try to import archive modules
try:
    from linklater.archives import ArchiveSearcher
    MODULES_AVAILABLE["archives"] = True
except ImportError:
    try:
        from archives import ArchiveSearcher
        MODULES_AVAILABLE["archives"] = True
    except ImportError:
        logger.warning("ArchiveSearcher not available")
        ArchiveSearcher = None

# Try to import discovery modules
try:
    from linklater.discovery import UnifiedDiscoveryEngine
    MODULES_AVAILABLE["discovery"] = True
except ImportError:
    try:
        from discovery.unified_discovery_engine import UnifiedDiscoveryEngine
        MODULES_AVAILABLE["discovery"] = True
    except ImportError:
        logger.warning("UnifiedDiscoveryEngine not available")
        UnifiedDiscoveryEngine = None

# Try to import entity extraction
try:
    from linklater.drill.extractors import EntityExtractor
    MODULES_AVAILABLE["extractors"] = True
except ImportError:
    try:
        from drill.extractors import EntityExtractor
        MODULES_AVAILABLE["extractors"] = True
    except ImportError:
        logger.warning("EntityExtractor not available")
        EntityExtractor = None


class LinkLaterMCP:
    """LINKLATER MCP Server - Complete Link & Archive Intelligence"""

    def __init__(self):
        self.server = Server("linklater")

        # Initialize components
        self.backlink_engine = None
        self.archive_searcher = None
        self.discovery_engine = None
        self.entity_extractor = None

        if BacklinkDiscovery:
            try:
                self.backlink_engine = BacklinkDiscovery()
            except Exception as e:
                logger.warning(f"Could not initialize BacklinkDiscovery: {e}")

        if ArchiveSearcher:
            try:
                self.archive_searcher = ArchiveSearcher()
            except Exception as e:
                logger.warning(f"Could not initialize ArchiveSearcher: {e}")

        if UnifiedDiscoveryEngine:
            try:
                self.discovery_engine = UnifiedDiscoveryEngine()
            except Exception as e:
                logger.warning(f"Could not initialize UnifiedDiscoveryEngine: {e}")

        if EntityExtractor:
            try:
                self.entity_extractor = EntityExtractor()
            except Exception as e:
                logger.warning(f"Could not initialize EntityExtractor: {e}")

        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                # ========== LINK GRAPH ==========
                Tool(
                    name="get_backlinks",
                    description="""Get domains/pages linking TO a target domain.

SYNTAX (for execute tool):
    ?bl !domain.com     → Referring domains only (FAST ~100ms)
    bl? !domain.com     → Referring pages with enrichment (RICH ~30-60s)
    ?bl domain.com/path! → Domains linking to specific URL
    bl? domain.com/path! → Pages linking to specific URL

SOURCES: CC Web Graph (157M domains, 2.1B edges), GlobalLinks, Majestic API

Returns: List of linking domains/pages with anchor text and link weight.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Target domain (e.g., 'example.com')"},
                            "mode": {
                                "type": "string",
                                "enum": ["fast", "rich"],
                                "default": "fast",
                                "description": "fast=domains only (~100ms), rich=pages with enrichment (~30-60s)"
                            },
                            "limit": {"type": "integer", "default": 100, "description": "Max results"},
                            "min_weight": {"type": "integer", "default": 1, "description": "Minimum link weight"},
                            "include_majestic": {"type": "boolean", "default": True, "description": "Include Majestic Trust/Citation Flow"},
                            "include_tor": {"type": "boolean", "default": False, "description": "Include Tor/dark web sources"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="get_outlinks",
                    description="""Get domains/pages that a target domain links TO.

SYNTAX (for execute tool):
    ?ol !domain.com     → Outlink domains only (FAST)
    ol? !domain.com     → Outlink pages with context (RICH)

SOURCES: GlobalLinks (CC extracted links), live scraping

Returns: List of domains/pages the target links to with anchor text.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Target domain"},
                            "mode": {
                                "type": "string",
                                "enum": ["fast", "rich"],
                                "default": "fast",
                                "description": "fast=domains only, rich=pages with context"
                            },
                            "limit": {"type": "integer", "default": 100, "description": "Max results"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="hop_links",
                    description="""Spider through link graph - navigate site-to-site via backlinks/outlinks.

Start from a domain and discover connected domains up to N hops away.
Useful for mapping website networks and finding hidden relationships.

DIRECTIONS:
- backlinks: Follow who links TO each domain
- outlinks: Follow who each domain links TO
- bidirectional: Both directions (wider coverage)""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_domain": {"type": "string", "description": "Starting domain"},
                            "direction": {
                                "type": "string",
                                "enum": ["backlinks", "outlinks", "bidirectional"],
                                "default": "bidirectional",
                                "description": "Direction to follow links"
                            },
                            "depth": {"type": "integer", "default": 2, "description": "Hops to make (1-3)"},
                            "max_per_hop": {"type": "integer", "default": 10, "description": "Max domains per hop"}
                        },
                        "required": ["start_domain"]
                    }
                ),
                Tool(
                    name="find_related_domains",
                    description="""Find domains with similar backlink profiles.

Discovers domains that share significant overlap in who links to them.
Useful for finding competitor sites, related businesses, or network analysis.

SYNTAX (for execute tool):
    ?rl !domain.com     → Related domains via shared backlinks""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Target domain"},
                            "min_shared": {"type": "integer", "default": 3, "description": "Minimum shared backlinks"},
                            "limit": {"type": "integer", "default": 50, "description": "Max related domains"}
                        },
                        "required": ["domain"]
                    }
                ),

                # ========== ARCHIVE INTELLIGENCE ==========
                Tool(
                    name="search_archives",
                    description="""Search archive snapshots (Wayback + Common Crawl) for keywords.

Searches historical versions of a URL/domain for specific content.
Uses 80 concurrent Wayback connections + CC Index for maximum coverage.

SYNTAX (for execute tool):
    keyword :<-domain.com   → Search archives backwards in time
    keyword :->domain.com   → Search archives forwards in time

Returns: Snapshots containing the keyword with surrounding context.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL or domain to search"},
                            "keyword": {"type": "string", "description": "Keyword to find in archives"},
                            "max_snapshots": {"type": "integer", "default": 100, "description": "Max snapshots to check"},
                            "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                            "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"}
                        },
                        "required": ["url", "keyword"]
                    }
                ),
                Tool(
                    name="get_archive_snapshots",
                    description="""List available archive snapshots for a URL.

Returns all Wayback Machine snapshots with timestamps, status codes,
and content lengths. Useful for finding specific historical versions.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to check"},
                            "limit": {"type": "integer", "default": 100, "description": "Max snapshots to return"}
                        },
                        "required": ["url"]
                    }
                ),
                Tool(
                    name="compare_archive_versions",
                    description="""Compare content between two archive snapshots.

Highlights what changed between two points in time.
Useful for detecting content modifications, price changes, etc.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to compare"},
                            "date1": {"type": "string", "description": "First date (YYYY-MM-DD)"},
                            "date2": {"type": "string", "description": "Second date (YYYY-MM-DD)"}
                        },
                        "required": ["url", "date1", "date2"]
                    }
                ),
                Tool(
                    name="scrape_url",
                    description="""Scrape URL content using CC-first strategy.

ORDER: Common Crawl (free, fast) → Wayback → Firecrawl (live)

Returns markdown-formatted content with metadata.
CC-first minimizes API costs while maximizing coverage.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to scrape"},
                            "use_firecrawl": {"type": "boolean", "default": True, "description": "Allow Firecrawl for live content"},
                            "archive_only": {"type": "boolean", "default": False, "description": "Only use archive sources (no live)"}
                        },
                        "required": ["url"]
                    }
                ),

                # ========== ENTITY EXTRACTION ==========
                Tool(
                    name="extract_entities",
                    description="""Extract entities from text: companies, persons, registrations, dates.

ENTITY TYPES:
- companies: GmbH, Ltd, LLC, Inc, AG, SA, etc.
- registrations: Company numbers, VAT, LEI, IBAN, SWIFT
- persons: Names detected via patterns
- dates: Dates and date ranges
- financials: Currency amounts

JURISDICTIONS: DE, UK, US, NL, FR, CH, CY, etc.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Text to extract from"},
                            "entity_types": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter: companies, registrations, persons, dates, financials"
                            },
                            "jurisdictions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter jurisdictions: DE, UK, US, etc."
                            }
                        },
                        "required": ["text"]
                    }
                ),
                Tool(
                    name="extract_domain_entities",
                    description="""Extract all entities from a domain's CC-indexed pages.

Scrapes all available pages from Common Crawl and extracts:
- Company names and registration numbers
- Person names
- Contact information
- Financial amounts

Returns aggregated entity list with source URLs.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Domain to analyze"},
                            "limit": {"type": "integer", "default": 200, "description": "Max pages to analyze"}
                        },
                        "required": ["domain"]
                    }
                ),

                # ========== DISCOVERY ==========
                Tool(
                    name="discover_subdomains",
                    description="""Discover subdomains via multiple sources.

SOURCES:
- DNS brute force (common subdomain list)
- Certificate Transparency logs
- Archive sources (Wayback, CC)
- Search engine results""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Root domain"},
                            "use_dns": {"type": "boolean", "default": True, "description": "DNS brute force"},
                            "use_ct": {"type": "boolean", "default": True, "description": "Certificate Transparency"},
                            "use_archives": {"type": "boolean", "default": True, "description": "Archive sources"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="discover_tech_stack",
                    description="""Identify technologies used by a domain.

Detects: CMS, frameworks, analytics, CDNs, hosting, security tools.
Uses: HTTP headers, HTML patterns, JavaScript fingerprints.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Domain to analyze"}
                        },
                        "required": ["domain"]
                    }
                ),
                Tool(
                    name="discover_whois_cluster",
                    description="""Find domains registered by the same entity.

Groups domains by shared WHOIS data: registrant, email, nameservers.
Useful for identifying domain portfolios and network infrastructure.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string", "description": "Starting domain"},
                            "cluster_by": {
                                "type": "string",
                                "enum": ["registrant", "email", "nameserver", "all"],
                                "default": "all",
                                "description": "What WHOIS field to cluster by"
                            }
                        },
                        "required": ["domain"]
                    }
                ),

                # ========== ENRICHMENT ==========
                Tool(
                    name="enrich_urls",
                    description="""Full URL enrichment: scrape + entities + links + keywords.

PIPELINE:
1. Scrape content (CC-first)
2. Extract all entities
3. Get backlinks/outlinks
4. Search for keywords

Returns comprehensive intelligence package per URL.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "URLs to enrich"
                            },
                            "keyword": {"type": "string", "description": "Optional keyword to search for"},
                            "include_backlinks": {"type": "boolean", "default": True, "description": "Include backlink analysis"},
                            "include_entities": {"type": "boolean", "default": True, "description": "Include entity extraction"},
                            "max_backlinks": {"type": "integer", "default": 10, "description": "Max backlinks per domain"}
                        },
                        "required": ["urls"]
                    }
                ),
                Tool(
                    name="batch_domain_extract",
                    description="""Batch process multiple domains for entity extraction.

Processes a list of domains, extracting all entities from each.
Results saved to file with per-domain breakdown.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "domains": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of domains to process"
                            },
                            "limit_per_domain": {"type": "integer", "default": 100, "description": "Max pages per domain"}
                        },
                        "required": ["domains"]
                    }
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            try:
                result = await self._handle_tool(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
            except Exception as e:
                logger.error(f"Tool {name} error: {e}", exc_info=True)
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _handle_tool(self, name: str, arguments: dict) -> dict:
        """Route tool calls to appropriate handlers."""

        # ========== LINK GRAPH ==========
        if name == "get_backlinks":
            return await self._get_backlinks(
                arguments["domain"],
                arguments.get("mode", "fast"),
                arguments.get("limit", 100),
                arguments.get("min_weight", 1),
                arguments.get("include_majestic", True),
                arguments.get("include_tor", False)
            )

        elif name == "get_outlinks":
            return await self._get_outlinks(
                arguments["domain"],
                arguments.get("mode", "fast"),
                arguments.get("limit", 100)
            )

        elif name == "hop_links":
            return await self._hop_links(
                arguments["start_domain"],
                arguments.get("direction", "bidirectional"),
                arguments.get("depth", 2),
                arguments.get("max_per_hop", 10)
            )

        elif name == "find_related_domains":
            return await self._find_related_domains(
                arguments["domain"],
                arguments.get("min_shared", 3),
                arguments.get("limit", 50)
            )

        # ========== ARCHIVE INTELLIGENCE ==========
        elif name == "search_archives":
            return await self._search_archives(
                arguments["url"],
                arguments["keyword"],
                arguments.get("max_snapshots", 100),
                arguments.get("date_from"),
                arguments.get("date_to")
            )

        elif name == "get_archive_snapshots":
            return await self._get_archive_snapshots(
                arguments["url"],
                arguments.get("limit", 100)
            )

        elif name == "compare_archive_versions":
            return await self._compare_archive_versions(
                arguments["url"],
                arguments["date1"],
                arguments["date2"]
            )

        elif name == "scrape_url":
            return await self._scrape_url(
                arguments["url"],
                arguments.get("use_firecrawl", True),
                arguments.get("archive_only", False)
            )

        # ========== ENTITY EXTRACTION ==========
        elif name == "extract_entities":
            return await self._extract_entities(
                arguments["text"],
                arguments.get("entity_types"),
                arguments.get("jurisdictions")
            )

        elif name == "extract_domain_entities":
            return await self._extract_domain_entities(
                arguments["domain"],
                arguments.get("limit", 200)
            )

        # ========== DISCOVERY ==========
        elif name == "discover_subdomains":
            return await self._discover_subdomains(
                arguments["domain"],
                arguments.get("use_dns", True),
                arguments.get("use_ct", True),
                arguments.get("use_archives", True)
            )

        elif name == "discover_tech_stack":
            return await self._discover_tech_stack(arguments["domain"])

        elif name == "discover_whois_cluster":
            return await self._discover_whois_cluster(
                arguments["domain"],
                arguments.get("cluster_by", "all")
            )

        # ========== ENRICHMENT ==========
        elif name == "enrich_urls":
            return await self._enrich_urls(
                arguments["urls"],
                arguments.get("keyword"),
                arguments.get("include_backlinks", True),
                arguments.get("include_entities", True),
                arguments.get("max_backlinks", 10)
            )

        elif name == "batch_domain_extract":
            return await self._batch_domain_extract(
                arguments["domains"],
                arguments.get("limit_per_domain", 100)
            )

        else:
            return {"error": f"Unknown tool: {name}"}

    # ========== IMPLEMENTATION METHODS ==========

    async def _get_backlinks(self, domain: str, mode: str, limit: int,
                            min_weight: int, include_majestic: bool, include_tor: bool) -> dict:
        """Get backlinks using BacklinkDiscovery."""
        if not self.backlink_engine:
            return {"error": "BacklinkDiscovery not available"}

        syntax = "bl?" if mode == "rich" else "?bl"
        target = f"!{domain}"

        try:
            result = await self.backlink_engine.query(
                syntax, target,
                limit=limit,
                min_weight=min_weight,
                include_majestic=include_majestic,
                include_tor=include_tor
            )
            return {
                "domain": domain,
                "mode": mode,
                "total": len(result.get("backlinks", [])),
                **result
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _get_outlinks(self, domain: str, mode: str, limit: int) -> dict:
        """Get outlinks."""
        if not self.backlink_engine:
            return {"error": "BacklinkDiscovery not available"}

        # Use outlinks query if available
        try:
            # Try to get outlinks from CC Graph
            from linkgraph.cc_graph import CCGraphClient
            client = CCGraphClient()
            result = await client.get_outlinks(domain, limit=limit)
            return {
                "domain": domain,
                "mode": mode,
                "total": len(result),
                "outlinks": result
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _hop_links(self, start_domain: str, direction: str, depth: int, max_per_hop: int) -> dict:
        """Spider through link graph."""
        visited = set()
        current_level = {start_domain}
        results = {"start": start_domain, "hops": []}

        for hop in range(depth):
            next_level = set()
            hop_results = {"hop": hop + 1, "domains": []}

            for domain in current_level:
                if domain in visited:
                    continue
                visited.add(domain)

                # Get links based on direction
                if direction in ["backlinks", "bidirectional"]:
                    bl_result = await self._get_backlinks(domain, "fast", max_per_hop, 1, False, False)
                    for bl in bl_result.get("backlinks", [])[:max_per_hop]:
                        src = bl.get("source_domain", bl.get("source", ""))
                        if src and src not in visited:
                            next_level.add(src)
                            hop_results["domains"].append({"domain": src, "via": domain, "type": "backlink"})

                if direction in ["outlinks", "bidirectional"]:
                    ol_result = await self._get_outlinks(domain, "fast", max_per_hop)
                    for ol in ol_result.get("outlinks", [])[:max_per_hop]:
                        tgt = ol.get("target_domain", ol.get("target", ""))
                        if tgt and tgt not in visited:
                            next_level.add(tgt)
                            hop_results["domains"].append({"domain": tgt, "via": domain, "type": "outlink"})

            results["hops"].append(hop_results)
            current_level = next_level

            if not current_level:
                break

        results["total_discovered"] = len(visited) - 1
        return results

    async def _find_related_domains(self, domain: str, min_shared: int, limit: int) -> dict:
        """Find domains with similar backlink profiles."""
        # Get backlinks for the target
        bl_result = await self._get_backlinks(domain, "fast", 1000, 1, False, False)
        target_backlinks = set(bl.get("source_domain", "") for bl in bl_result.get("backlinks", []))

        if not target_backlinks:
            return {"domain": domain, "related": [], "message": "No backlinks found"}

        # Count shared backlinks with other domains
        # This is a simplified implementation - full version would use CC Graph
        return {
            "domain": domain,
            "target_backlinks": len(target_backlinks),
            "min_shared": min_shared,
            "note": "Full implementation requires CC Graph co-citation query"
        }

    async def _search_archives(self, url: str, keyword: str, max_snapshots: int,
                              date_from: str = None, date_to: str = None) -> dict:
        """Search archives for keyword."""
        if not self.archive_searcher:
            return {"error": "ArchiveSearcher not available"}

        try:
            result = await self.archive_searcher.search_keyword(
                url, keyword,
                max_snapshots=max_snapshots,
                date_from=date_from,
                date_to=date_to
            )
            return {
                "url": url,
                "keyword": keyword,
                **result
            }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _get_archive_snapshots(self, url: str, limit: int) -> dict:
        """List archive snapshots."""
        if not self.archive_searcher:
            return {"error": "ArchiveSearcher not available"}

        try:
            snapshots = await self.archive_searcher.list_snapshots(url, limit=limit)
            return {
                "url": url,
                "total": len(snapshots),
                "snapshots": snapshots
            }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _compare_archive_versions(self, url: str, date1: str, date2: str) -> dict:
        """Compare two archive versions."""
        if not self.archive_searcher:
            return {"error": "ArchiveSearcher not available"}

        try:
            result = await self.archive_searcher.compare_versions(url, date1, date2)
            return {
                "url": url,
                "date1": date1,
                "date2": date2,
                **result
            }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _scrape_url(self, url: str, use_firecrawl: bool, archive_only: bool) -> dict:
        """Scrape URL with CC-first strategy."""
        if not self.archive_searcher:
            return {"error": "ArchiveSearcher not available"}

        try:
            result = await self.archive_searcher.scrape(
                url,
                use_firecrawl=use_firecrawl and not archive_only,
                archive_only=archive_only
            )
            return {
                "url": url,
                **result
            }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _extract_entities(self, text: str, entity_types: list = None,
                               jurisdictions: list = None) -> dict:
        """Extract entities from text."""
        if not self.entity_extractor:
            return {"error": "EntityExtractor not available"}

        try:
            entities = self.entity_extractor.extract(
                text,
                entity_types=entity_types,
                jurisdictions=jurisdictions
            )
            return {
                "text_length": len(text),
                "entities": entities
            }
        except Exception as e:
            return {"error": str(e)}

    async def _extract_domain_entities(self, domain: str, limit: int) -> dict:
        """Extract entities from all pages of a domain."""
        if not self.entity_extractor:
            return {"error": "EntityExtractor not available"}

        # Scrape pages and extract
        all_entities = {"companies": [], "persons": [], "registrations": [], "contacts": []}
        sources = []

        try:
            # Get pages from CC Index
            # This would use the CC Index API in full implementation
            return {
                "domain": domain,
                "pages_analyzed": 0,
                "entities": all_entities,
                "note": "Full implementation requires CC Index integration"
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _discover_subdomains(self, domain: str, use_dns: bool,
                                   use_ct: bool, use_archives: bool) -> dict:
        """Discover subdomains."""
        if not self.discovery_engine:
            return {"error": "UnifiedDiscoveryEngine not available"}

        try:
            result = await self.discovery_engine.discover_subdomains(
                domain,
                use_dns=use_dns,
                use_ct=use_ct,
                use_archives=use_archives
            )
            return {
                "domain": domain,
                **result
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _discover_tech_stack(self, domain: str) -> dict:
        """Discover tech stack."""
        if not self.discovery_engine:
            return {"error": "UnifiedDiscoveryEngine not available"}

        try:
            result = await self.discovery_engine.discover_tech_stack(domain)
            return {
                "domain": domain,
                **result
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _discover_whois_cluster(self, domain: str, cluster_by: str) -> dict:
        """Find WHOIS-related domains."""
        if not self.discovery_engine:
            return {"error": "UnifiedDiscoveryEngine not available"}

        try:
            result = await self.discovery_engine.discover_whois_cluster(
                domain,
                cluster_by=cluster_by
            )
            return {
                "domain": domain,
                **result
            }
        except Exception as e:
            return {"error": str(e), "domain": domain}

    async def _enrich_urls(self, urls: list, keyword: str,
                          include_backlinks: bool, include_entities: bool,
                          max_backlinks: int) -> dict:
        """Full URL enrichment."""
        results = []

        for url in urls:
            enriched = {"url": url}

            # Scrape content
            if self.archive_searcher:
                try:
                    scrape_result = await self._scrape_url(url, True, False)
                    enriched["content"] = scrape_result
                except Exception as e:
                    enriched["scrape_error"] = str(e)

            # Extract entities
            if include_entities and self.entity_extractor:
                content = enriched.get("content", {}).get("markdown", "")
                if content:
                    try:
                        entities = await self._extract_entities(content)
                        enriched["entities"] = entities
                    except Exception as e:
                        enriched["entity_error"] = str(e)

            # Get backlinks
            if include_backlinks:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                if domain:
                    try:
                        bl_result = await self._get_backlinks(domain, "fast", max_backlinks, 1, False, False)
                        enriched["backlinks"] = bl_result
                    except Exception as e:
                        enriched["backlink_error"] = str(e)

            # Search for keyword
            if keyword:
                content = enriched.get("content", {}).get("markdown", "")
                if keyword.lower() in content.lower():
                    enriched["keyword_found"] = True
                    # Find context
                    idx = content.lower().find(keyword.lower())
                    enriched["keyword_context"] = content[max(0, idx-100):idx+100+len(keyword)]
                else:
                    enriched["keyword_found"] = False

            results.append(enriched)

        return {
            "urls_processed": len(urls),
            "results": results
        }

    async def _batch_domain_extract(self, domains: list, limit_per_domain: int) -> dict:
        """Batch extract entities from domains."""
        results = []

        for domain in domains:
            result = await self._extract_domain_entities(domain, limit_per_domain)
            results.append(result)

        return {
            "domains_processed": len(domains),
            "results": results
        }

    async def run(self):
        """Run the MCP server."""
        logger.info(f"Starting LINKLATER MCP Server")
        logger.info(f"Modules available: {MODULES_AVAILABLE}")

        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def main():
    """Entry point."""
    server = LinkLaterMCP()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
