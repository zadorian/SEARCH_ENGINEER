#!/usr/bin/env python3
"""
LINKLATER MCP Server - UNIFIED Archive & Link Intelligence

ALL ARCHIVE AND LINK OPERATIONS IN ONE PLACE:
1. CC Web Graph (Elasticsearch) - 157M domains, 2.1B edges instant backlink/outlink lookups
2. GlobalLinks (Go binaries) - precomputed CC link relationships
3. Hybrid Archive Scanning - Wayback (80 concurrent) + CC (70 concurrent) + Firecrawl (100)
4. Firecrawl Live - current content scraping
5. Rapid Keyword Search - find keywords across archive snapshots
6. Entity Extraction - companies, registrations, persons, dates
7. Link Hopping - navigate site-to-site via backlinks/outlinks

MCP Tools:
- get_backlinks: Get domains linking TO a target domain
- get_outlinks: Get domains a target domain links TO
- hop_links: Navigate site-to-site through links (spider)
- search_archives: Search archive snapshots for keywords
- scrape_url: Scrape URL content (CC-first → Firecrawl fallback)
- extract_entities: Extract companies, people, registrations from text
- enrich_urls: Full enrichment: scrape + entities + links + keywords
- batch_domain_extract: Process multiple domains from file
"""

import asyncio
import json
import sys
import os
import aiohttp
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python-backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# Results directory
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Python API URL (internal)
PYTHON_API_BASE = os.getenv('PYTHON_API_URL', 'http://localhost:8000')

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError as e:
    print(f"ERROR: mcp package not installed in BACKEND/modules/LINKLATER/mcp/server.py. Error: {e}", file=sys.stderr)
    # sys.exit(1) # Don't exit, let it crash or continue if possible
    raise

# Initialize MCP server
app = Server("linklater")

# GlobalLinks binary path resolution
GLOBALLINKS_CANDIDATES = [
    PROJECT_ROOT / "categorizer-filterer/globallinks/bin/outlinker",
    PROJECT_ROOT / "categorizer-filterer/globallinks/globallinks-with-outlinker/bin/outlinker",
    PROJECT_ROOT / "categorizer-filterer/globallinks/globallinks-ready/bin/outlinker",
]


def find_globallinks_binary() -> Optional[Path]:
    """Find the GlobalLinks binary if available."""
    for candidate in GLOBALLINKS_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


@dataclass
class LinkRecord:
    source: str
    target: str
    weight: Optional[int] = None
    anchor_text: Optional[str] = None
    provider: str = "unknown"


async def get_backlinks_from_cc_graph(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get backlinks from CC Web Graph (Elasticsearch)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PYTHON_API_BASE}/api/cc/inbound-backlinks",
                json={
                    "targets": [domain],
                    "period": "latest",
                    "min_weight": 1,
                    "limit": limit,
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [
                        LinkRecord(
                            source=r.get("src_domain", ""),
                            target=r.get("target_domain", ""),
                            weight=r.get("weight"),
                            provider="cc_graph"
                        )
                        for r in data.get("records", [])
                    ]
    except Exception as e:
        print(f"[Linklater] CC Graph backlinks error: {e}", file=sys.stderr)
    return []


async def get_backlinks_from_globallinks_targeted(
    domain: str,
    source_domains: List[str],
    limit: int = 100
) -> List[LinkRecord]:
    """
    Get page-level backlinks using CC Index API (targeted "sniper" mode).

    This is MUCH faster than the Go binary because it:
    1. Uses CC Index API to find exact WAT file locations
    2. Fetches only the specific records needed with HTTP Range headers
    3. Only searches domains we know link to the target

    Args:
        domain: Target domain to find backlinks TO
        source_domains: List of domains that link to target (from CC Graph)
        limit: Max results

    Returns:
        List of LinkRecord objects with page-level URLs
    """
    try:
        # Import the CC Index backlinks module
        from linkgraph.cc_index_backlinks import get_backlinks_targeted

        backlinks = await get_backlinks_targeted(
            target_domain=domain,
            source_domains=source_domains[:20],  # Limit source domains to check
            archive="CC-MAIN-2024-10",
            max_pages_per_source=10,
            max_results=limit
        )

        return [
            LinkRecord(
                source=bl.source_url,
                target=bl.target_url,
                anchor_text=bl.anchor_text,
                provider="globallinks_targeted"
            )
            for bl in backlinks
        ]
    except Exception as e:
        print(f"[Linklater] GlobalLinks targeted error: {e}", file=sys.stderr)
        return []


async def get_backlinks_from_globallinks(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get backlinks from GlobalLinks Go binary (legacy - slow, scans all WAT files)."""
    binary_path = find_globallinks_binary()
    if not binary_path:
        return []

    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary_path),
            "backlinks",
            f"--target-domain={domain}",
            "--archive=latest",
            f"--limit={limit}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(binary_path.parent)
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)

        records = []
        for line in stdout.decode().strip().split('\n'):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
                records.append(LinkRecord(
                    source=parsed.get("source", ""),
                    target=parsed.get("target", ""),
                    anchor_text=parsed.get("anchorText"),
                    provider="globallinks"
                ))
            except json.JSONDecodeError:
                parts = line.split()
                if len(parts) >= 2:
                    records.append(LinkRecord(
                        source=parts[0],
                        target=parts[1],
                        anchor_text=" ".join(parts[2:]) if len(parts) > 2 else None,
                        provider="globallinks"
                    ))
        return records
    except Exception as e:
        print(f"[Linklater] GlobalLinks backlinks error: {e}", file=sys.stderr)
    return []


async def get_outlinks_from_globallinks(domain: str, limit: int = 100) -> List[LinkRecord]:
    """Get outlinks from GlobalLinks Go binary."""
    binary_path = find_globallinks_binary()
    if not binary_path:
        return []

    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary_path),
            "outlinks",
            f"--target-domain={domain}",
            "--archive=latest",
            f"--limit={limit}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(binary_path.parent)
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)

        records = []
        for line in stdout.decode().strip().split('\n'):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
                records.append(LinkRecord(
                    source=parsed.get("source", ""),
                    target=parsed.get("target", ""),
                    anchor_text=parsed.get("anchorText"),
                    provider="globallinks"
                ))
            except json.JSONDecodeError:
                parts = line.split()
                if len(parts) >= 2:
                    records.append(LinkRecord(
                        source=parts[0],
                        target=parts[1],
                        provider="globallinks"
                    ))
        return records
    except Exception as e:
        print(f"[Linklater] GlobalLinks outlinks error: {e}", file=sys.stderr)
    return []


@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available LINKLATER tools"""
    return [
        # ========== BACKLINKS / OUTLINKS ==========
        Tool(
            name="get_backlinks",
            description="Get domains that link TO a target domain. Uses CC Web Graph (157M domains) + GlobalLinks for comprehensive coverage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Target domain (e.g., 'example.com')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max backlinks to return (default: 100)",
                        "default": 100
                    },
                    "use_cc_graph": {
                        "type": "boolean",
                        "description": "Use CC Web Graph on Elasticsearch (default: true)",
                        "default": True
                    },
                    "use_globallinks": {
                        "type": "boolean",
                        "description": "Use GlobalLinks Go binary (default: true)",
                        "default": True
                    }
                },
                "required": ["domain"]
            }
        ),
        Tool(
            name="get_outlinks",
            description="Get domains that a target domain links TO. Uses GlobalLinks for CC Web Graph link relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Target domain (e.g., 'example.com')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max outlinks to return (default: 100)",
                        "default": 100
                    }
                },
                "required": ["domain"]
            }
        ),
        Tool(
            name="hop_links",
            description="Navigate site-to-site through backlinks/outlinks. Spider from a starting domain to discover connected domains.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_domain": {
                        "type": "string",
                        "description": "Starting domain to hop from"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["backlinks", "outlinks", "bidirectional"],
                        "description": "Direction to hop (default: bidirectional)",
                        "default": "bidirectional"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many hops to make (default: 2)",
                        "default": 2
                    },
                    "max_per_hop": {
                        "type": "integer",
                        "description": "Max domains to follow per hop (default: 10)",
                        "default": 10
                    }
                },
                "required": ["start_domain"]
            }
        ),

        # ========== ARCHIVE SEARCH ==========
        Tool(
            name="search_archives",
            description="Search archive snapshots (Wayback + Common Crawl) for a keyword on a URL. Returns snippets where keyword was found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL or domain to search archives for"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Keyword to search for in archive snapshots"
                    },
                    "max_snapshots": {
                        "type": "integer",
                        "description": "Max snapshots to check (default: 100)",
                        "default": 100
                    }
                },
                "required": ["url", "keyword"]
            }
        ),

        # ========== SCRAPING ==========
        Tool(
            name="scrape_url",
            description="Scrape URL content using CC-first strategy: Common Crawl (free, fast) → Wayback → Firecrawl (live). Returns markdown content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to scrape"
                    },
                    "use_firecrawl": {
                        "type": "boolean",
                        "description": "Allow Firecrawl fallback for live content (default: true)",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),

        # ========== ENTITY EXTRACTION ==========
        Tool(
            name="extract_entities",
            description="Extract entities from text: companies (GmbH, Ltd, LLC...), registration numbers, persons, dates, financials.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to extract entities from"
                    },
                    "entity_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter entity types: companies, registrations, persons, dates, financials"
                    },
                    "jurisdictions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter jurisdictions: DE, UK, US, NL, FR, etc."
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="extract_domain_entities",
            description="Extract all entities from a domain by scraping its CC-indexed pages. Returns companies, people, registrations found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain to extract entities from (e.g., 'example.com')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max pages to analyze (default: 200)",
                        "default": 200
                    }
                },
                "required": ["domain"]
            }
        ),

        # ========== FULL ENRICHMENT ==========
        Tool(
            name="enrich_urls",
            description="Full URL enrichment: scrape (CC-first) + entity extraction + keyword search + backlinks. Returns comprehensive intelligence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs to enrich"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword to search for in content"
                    },
                    "include_backlinks": {
                        "type": "boolean",
                        "description": "Include backlinks for each domain (default: true)",
                        "default": True
                    },
                    "max_backlinks": {
                        "type": "integer",
                        "description": "Max backlinks per domain (default: 10)",
                        "default": 10
                    }
                },
                "required": ["urls"]
            }
        ),

        # ========== BATCH OPERATIONS ==========
        Tool(
            name="batch_domain_extract",
            description="Process multiple domains from a file. Extracts entities from all CC-indexed pages for each domain.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domains_file": {
                        "type": "string",
                        "description": "Path to file containing domain list (one per line)"
                    },
                    "limit_per_domain": {
                        "type": "integer",
                        "description": "Max pages per domain (default: 100)",
                        "default": 100
                    }
                },
                "required": ["domains_file"]
            }
        ),

        # ========== KEYWORD SEARCH ==========
        Tool(
            name="keyword_variations_search",
            description="Search archives for keyword variations. Generates query variations automatically and searches Wayback + CC index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Base keyword to search for"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional: Restrict search to specific domain"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default: 100)",
                        "default": 100
                    }
                },
                "required": ["keyword"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute LINKLATER tool"""

    try:
        # ========== BACKLINKS ==========
        if name == "get_backlinks":
            domain = arguments["domain"]
            limit = arguments.get("limit", 100)
            use_cc_graph = arguments.get("use_cc_graph", True)
            use_globallinks = arguments.get("use_globallinks", True)

            all_records: List[LinkRecord] = []

            # Step 1: Get domain-level backlinks from CC Graph (fast)
            cc_graph_records = []
            if use_cc_graph:
                cc_graph_records = await get_backlinks_from_cc_graph(domain, limit)
                all_records.extend(cc_graph_records)

            # Step 2: Get page-level backlinks using targeted CC Index approach
            # Use domains from CC Graph as source_domains (MUCH faster than blind scanning)
            if use_globallinks and cc_graph_records:
                source_domains = [r.source for r in cc_graph_records if r.source]
                if source_domains:
                    try:
                        targeted_records = await get_backlinks_from_globallinks_targeted(
                            domain=domain,
                            source_domains=source_domains,
                            limit=limit
                        )
                        all_records.extend(targeted_records)
                    except Exception as e:
                        print(f"[Linklater] Targeted backlinks error: {e}", file=sys.stderr)

            # Legacy fallback if no CC Graph results (will be slow/timeout)
            if use_globallinks and not cc_graph_records:
                legacy_records = await get_backlinks_from_globallinks(domain, limit)
                all_records.extend(legacy_records)

            # Deduplicate by source domain
            seen = set()
            deduped = []
            for r in all_records:
                if r.source not in seen:
                    seen.add(r.source)
                    deduped.append(r)

            # Format output
            lines = [
                "=" * 80,
                f"LINKLATER: BACKLINKS FOR {domain}",
                f"Found: {len(deduped)} unique linking domains",
                "=" * 80,
                "",
            ]

            if deduped:
                lines.append("Domains linking to this target:")
                for i, r in enumerate(deduped[:limit], 1):
                    weight_str = f" (weight: {r.weight})" if r.weight else ""
                    anchor_str = f" [{r.anchor_text[:50]}...]" if r.anchor_text and len(r.anchor_text) > 50 else (f" [{r.anchor_text}]" if r.anchor_text else "")
                    lines.append(f"  {i}. {r.source}{weight_str}{anchor_str} [{r.provider}]")
            else:
                lines.append("No backlinks found.")

            lines.append("")
            lines.append("=" * 80)

            return [TextContent(type="text", text="\n".join(lines))]

        # ========== OUTLINKS ==========
        elif name == "get_outlinks":
            domain = arguments["domain"]
            limit = arguments.get("limit", 100)

            records = await get_outlinks_from_globallinks(domain, limit)

            lines = [
                "=" * 80,
                f"LINKLATER: OUTLINKS FROM {domain}",
                f"Found: {len(records)} domains linked to",
                "=" * 80,
                "",
            ]

            if records:
                lines.append("Domains this target links TO:")
                for i, r in enumerate(records[:limit], 1):
                    anchor_str = f" [{r.anchor_text}]" if r.anchor_text else ""
                    lines.append(f"  {i}. {r.target}{anchor_str}")
            else:
                lines.append("No outlinks found.")

            lines.append("")
            lines.append("=" * 80)

            return [TextContent(type="text", text="\n".join(lines))]

        # ========== LINK HOPPING ==========
        elif name == "hop_links":
            start_domain = arguments["start_domain"]
            direction = arguments.get("direction", "bidirectional")
            depth = min(arguments.get("depth", 2), 3)  # Cap at 3 to avoid explosion
            max_per_hop = arguments.get("max_per_hop", 10)

            visited = set()
            visited.add(start_domain)

            current_level = [start_domain]
            all_hops = {0: [start_domain]}

            for hop in range(1, depth + 1):
                next_level = []
                for domain in current_level:
                    links = []
                    if direction in ["backlinks", "bidirectional"]:
                        backlinks = await get_backlinks_from_globallinks(domain, max_per_hop)
                        links.extend([r.source for r in backlinks])
                    if direction in ["outlinks", "bidirectional"]:
                        outlinks = await get_outlinks_from_globallinks(domain, max_per_hop)
                        links.extend([r.target for r in outlinks])

                    for link in links:
                        if link and link not in visited:
                            visited.add(link)
                            next_level.append(link)
                            if len(next_level) >= max_per_hop * len(current_level):
                                break

                all_hops[hop] = next_level[:max_per_hop * 5]  # Cap total per level
                current_level = next_level[:max_per_hop * 2]  # Limit expansion

            lines = [
                "=" * 80,
                f"LINKLATER: LINK HOPPING from {start_domain}",
                f"Direction: {direction}, Depth: {depth}",
                f"Total domains discovered: {len(visited)}",
                "=" * 80,
                "",
            ]

            for hop, domains in all_hops.items():
                if hop == 0:
                    lines.append(f"START: {start_domain}")
                else:
                    lines.append(f"\nHOP {hop} ({len(domains)} domains):")
                    for d in domains[:20]:
                        lines.append(f"  → {d}")
                    if len(domains) > 20:
                        lines.append(f"  ... and {len(domains) - 20} more")

            lines.append("")
            lines.append("=" * 80)

            return [TextContent(type="text", text="\n".join(lines))]

        # ========== ARCHIVE SEARCH ==========
        elif name == "search_archives":
            url = arguments["url"]
            keyword = arguments["keyword"]
            max_snapshots = arguments.get("max_snapshots", 100)

            # Call Python API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PYTHON_API_BASE}/api/archive/search",
                    json={
                        "url": url,
                        "keywords": [keyword],
                        "max_snapshots": max_snapshots,
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lines = [
                            "=" * 80,
                            f"LINKLATER: ARCHIVE SEARCH",
                            f"URL: {url}",
                            f"Keyword: {keyword}",
                            "=" * 80,
                            "",
                        ]

                        if data.get("found"):
                            lines.append(f"✅ FOUND in {data.get('total_snapshots', 0)} snapshots")
                            if data.get("snippets"):
                                lines.append("\nSnippets:")
                                for i, snippet in enumerate(data["snippets"][:5], 1):
                                    lines.append(f"  {i}. ...{snippet}...")
                        else:
                            lines.append("❌ Keyword not found in archive snapshots")

                        return [TextContent(type="text", text="\n".join(lines))]
                    else:
                        return [TextContent(type="text", text=f"Archive search failed: HTTP {resp.status}")]

        # ========== SCRAPE URL ==========
        elif name == "scrape_url":
            url = arguments["url"]
            use_firecrawl = arguments.get("use_firecrawl", True)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PYTHON_API_BASE}/api/scrape/cc-first",
                    json={"url": url, "allow_firecrawl": use_firecrawl},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lines = [
                            "=" * 80,
                            f"LINKLATER: SCRAPE RESULT",
                            f"URL: {url}",
                            f"Source: {data.get('source', 'unknown')}",
                            f"Timestamp: {data.get('timestamp', 'N/A')}",
                            f"Content Length: {len(data.get('content', ''))} chars",
                            "=" * 80,
                            "",
                        ]

                        content = data.get("content", "")
                        if content:
                            lines.append("Content Preview (first 2000 chars):")
                            lines.append("-" * 40)
                            lines.append(content[:2000])
                            if len(content) > 2000:
                                lines.append(f"\n... [{len(content) - 2000} more chars]")
                        else:
                            lines.append("(No content retrieved)")

                        return [TextContent(type="text", text="\n".join(lines))]
                    else:
                        return [TextContent(type="text", text=f"Scrape failed: HTTP {resp.status}")]

        # ========== EXTRACT ENTITIES ==========
        elif name == "extract_entities":
            text = arguments["text"]
            entity_types = arguments.get("entity_types")
            jurisdictions = arguments.get("jurisdictions")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PYTHON_API_BASE}/api/extract/entities",
                    json={
                        "text": text,
                        "entity_types": entity_types,
                        "jurisdictions": jurisdictions,
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        entities = data.get("entities", {})

                        lines = [
                            "=" * 80,
                            "LINKLATER: ENTITY EXTRACTION",
                            f"Total entities: {data.get('total_entities', 0)}",
                            "=" * 80,
                            "",
                        ]

                        for etype, items in entities.items():
                            if items:
                                lines.append(f"\n{etype.upper()} ({len(items)}):")
                                for item in items[:20]:
                                    text_val = item.get("text", str(item))
                                    conf = item.get("confidence", "")
                                    conf_str = f" [{conf:.0%}]" if conf else ""
                                    lines.append(f"  • {text_val}{conf_str}")

                        return [TextContent(type="text", text="\n".join(lines))]
                    else:
                        return [TextContent(type="text", text=f"Entity extraction failed: HTTP {resp.status}")]

        # ========== EXTRACT DOMAIN ENTITIES ==========
        elif name == "extract_domain_entities":
            domain = arguments["domain"]
            limit = arguments.get("limit", 200)

            # Use the existing CLI logic via API
            from modules.cc_content.linklater_cli import cmd_domain_extract
            import argparse
            from io import StringIO

            args = argparse.Namespace(
                domain=domain,
                limit=limit,
                max_concurrent=10,
                include_content=False,
                max_content_length=60000,
                jurisdictions=None,
                cc_collection=None,
                pretty=False
            )

            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            try:
                await cmd_domain_extract(args)
                output_text = captured_output.getvalue()
            finally:
                sys.stdout = old_stdout

            try:
                cli_results = json.loads(output_text)
            except json.JSONDecodeError:
                return [TextContent(type="text", text=f"Error parsing results:\n{output_text[:500]}")]

            # Format nice output
            lines = [
                "=" * 80,
                f"LINKLATER: DOMAIN ENTITY EXTRACTION",
                f"Domain: {domain}",
                f"Pages discovered: {cli_results.get('discovered', 0)}",
                "=" * 80,
                "",
            ]

            entities = cli_results.get("entities", {})
            for etype, items in entities.items():
                if items:
                    lines.append(f"\n{etype.upper()} ({len(items)}):")
                    for item in items[:30]:
                        text_val = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                        lines.append(f"  • {text_val}")

            if cli_results.get("strategies_tried"):
                lines.append("\n\nSearch strategies tried:")
                for strategy in cli_results["strategies_tried"]:
                    lines.append(f"  • {strategy}")

            return [TextContent(type="text", text="\n".join(lines))]

        # ========== ENRICH URLS ==========
        elif name == "enrich_urls":
            urls = arguments["urls"]
            keyword = arguments.get("keyword")
            include_backlinks = arguments.get("include_backlinks", True)
            max_backlinks = arguments.get("max_backlinks", 10)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PYTHON_API_BASE}/api/scrape/cc-first/extract-batch",
                    json={
                        "urls": urls,
                        "keyword": keyword,
                        "max_outlinks": 20,
                        "allow_firecrawl": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        return [TextContent(type="text", text=f"Enrichment failed: HTTP {resp.status}")]

                    data = await resp.json()

            # Add backlinks if requested
            if include_backlinks:
                domains = set()
                for url in urls:
                    try:
                        from urllib.parse import urlparse
                        domain = urlparse(url).hostname
                        if domain:
                            domains.add(domain.replace("www.", ""))
                    except Exception as e:

                        print(f"[LINKLATER] Error: {e}")

                        pass

                domain_backlinks = {}
                for domain in domains:
                    backlinks = await get_backlinks_from_cc_graph(domain, max_backlinks)
                    if not backlinks:
                        backlinks = await get_backlinks_from_globallinks(domain, max_backlinks)
                    domain_backlinks[domain] = [r.source for r in backlinks]

            lines = [
                "=" * 80,
                "LINKLATER: URL ENRICHMENT",
                f"URLs processed: {len(urls)}",
                f"Keyword: {keyword or '(none)'}",
                "=" * 80,
                "",
            ]

            results = data.get("results", {})
            for url, result in results.items():
                lines.append(f"\n📄 {url}")
                lines.append(f"   Source: {result.get('source', 'unknown')}")
                lines.append(f"   Content: {result.get('content_length', 0)} chars")

                if result.get("keyword_hits"):
                    lines.append(f"   ✅ Keyword hits: {result['keyword_hits']}")

                entities = result.get("entities", {})
                if entities:
                    counts = [f"{k}: {len(v)}" for k, v in entities.items() if v]
                    if counts:
                        lines.append(f"   Entities: {', '.join(counts)}")

                if include_backlinks:
                    try:
                        from urllib.parse import urlparse
                        domain = urlparse(url).hostname.replace("www.", "")
                        if domain in domain_backlinks:
                            bl = domain_backlinks[domain]
                            lines.append(f"   Backlinks: {len(bl)} domains ({', '.join(bl[:3])}{'...' if len(bl) > 3 else ''})")
                    except Exception as e:

                        print(f"[LINKLATER] Error: {e}")

                        pass

            return [TextContent(type="text", text="\n".join(lines))]

        # ========== BATCH DOMAIN EXTRACT ==========
        elif name == "batch_domain_extract":
            domains_file = arguments["domains_file"]
            limit_per_domain = arguments.get("limit_per_domain", 100)

            domains_path = Path(domains_file)
            if not domains_path.exists():
                return [TextContent(type="text", text=f"❌ File not found: {domains_file}")]

            domains = [line.strip() for line in domains_path.read_text().splitlines() if line.strip()]
            if not domains:
                return [TextContent(type="text", text=f"❌ No domains found in {domains_file}")]

            lines = [
                "=" * 80,
                f"LINKLATER: BATCH DOMAIN EXTRACTION",
                f"Domains: {len(domains)}",
                "=" * 80,
            ]

            for idx, domain in enumerate(domains, 1):
                lines.append(f"\n[{idx}/{len(domains)}] {domain}")
                try:
                    # Call extract_domain_entities for each
                    from modules.cc_content.linklater_cli import cmd_domain_extract
                    import argparse
                    from io import StringIO

                    args = argparse.Namespace(
                        domain=domain,
                        limit=limit_per_domain,
                        max_concurrent=10,
                        include_content=False,
                        max_content_length=60000,
                        jurisdictions=None,
                        cc_collection=None,
                        pretty=False
                    )

                    old_stdout = sys.stdout
                    sys.stdout = captured_output = StringIO()
                    try:
                        await cmd_domain_extract(args)
                        output_text = captured_output.getvalue()
                    finally:
                        sys.stdout = old_stdout

                    try:
                        result = json.loads(output_text)
                        pages = result.get("discovered", 0)
                        entities = result.get("entities", {})
                        entity_counts = [f"{k}: {len(v)}" for k, v in entities.items() if v]
                        lines.append(f"   ✅ {pages} pages, {', '.join(entity_counts) if entity_counts else 'no entities'}")
                    except Exception as e:
                        lines.append(f"   ⚠️ Parse error")
                except Exception as e:
                    lines.append(f"   ❌ Error: {str(e)[:50]}")

            lines.append("\n" + "=" * 80)
            return [TextContent(type="text", text="\n".join(lines))]

        # ========== KEYWORD VARIATIONS SEARCH ==========
        elif name == "keyword_variations_search":
            keyword = arguments["keyword"]
            domain = arguments.get("domain")
            max_results = arguments.get("max_results", 100)

            from modules.cc_content.keyword_variations import KeywordVariationsSearch

            searcher = KeywordVariationsSearch(max_results_per_source=max_results)
            result = await searcher.search(keyword=keyword, max_concurrent=10)
            await searcher.close()

            search_results = searcher.to_search_results(result)

            lines = [
                "=" * 80,
                "LINKLATER: KEYWORD VARIATIONS SEARCH",
                f"Keyword: {keyword}",
                f"Variations searched: {result.variations_searched}",
                f"Total matches: {result.total_matches}",
                f"Unique URLs: {result.unique_urls}",
                "=" * 80,
                "",
            ]

            if search_results:
                lines.append("Results:")
                for i, r in enumerate(search_results[:30], 1):
                    lines.append(f"  {i}. {r.get('url', 'unknown')}")
                    if r.get("title"):
                        lines.append(f"      {r['title'][:80]}")

            return [TextContent(type="text", text="\n".join(lines))]

        else:
            return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]

    except Exception as e:
        import traceback
        return [TextContent(
            type="text",
            text=f"❌ ERROR: {str(e)}\n\n{traceback.format_exc()}"
        )]


async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
