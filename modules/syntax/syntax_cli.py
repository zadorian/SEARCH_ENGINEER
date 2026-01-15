#!/usr/bin/env python3
"""
SASTRE SYNTAX CLI - Primary Entry Point for OSINT Platform

Execute any SASTRE syntax query from command line.
This is the PRIMARY interface for sastre_ai and all AI agents.

Usage:
    python syntax_cli.py execute "p: John Smith"
    python syntax_cli.py execute "e: john@example.com t2 l3"
    python syntax_cli.py execute "bl? example.com"
    python syntax_cli.py execute "brute: \"Project Nighthawk\" t3"
    python syntax_cli.py parse "p: John Smith"
    python syntax_cli.py operators
    python syntax_cli.py operators --category DISCOVER
    python syntax_cli.py help

Syntax Quick Reference:
    p: <name>           Person search (EYE-D)
    e: <email>          Email search (EYE-D)
    t: <phone>          Phone search (EYE-D)
    c: <company>        Company search (EYE-D/CORPORELLA)
    ent: <target>       Full entity OSINT chain
    bl? <domain>        Backlinks (LINKLATER)
    ol? <domain>        Outlinks (LINKLATER)
    "exact phrase"      Exact phrase search (BRUTE)

Module Prefixes:
    brute: <query>      Multi-engine search
    linklater: <cmd>    Link analysis
    corporella: <cmd>   Corporate intelligence
    optics: <entity>    Media footprint analysis
    socialite: <handle> Social media
    submarine: <url>    Web scraping
    pacman: <content>   Entity extraction
    torpedo: <company>  Registry scraping
    stories: <entity>   Narrative generation

Tier Modifiers (which engines):
    t1  - Fast (6 engines)
    t2  - Standard (12 engines) [default]
    t3  - Deep (15 engines)
    t4  - Full (19 engines + link analysis)
    t10/t20/t30 - No-scrape variants

Layer Modifiers (intensity):
    l1  - Native (30s, 50 results)
    l2  - Enhanced (60s, 100 results) [default]
    l3  - Brute (120s, 200 results)
    l4  - Nuclear (300s, recursive)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add module paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from syntax.executor import UnifiedExecutor as SyntaxExecutor
from syntax.parser import SyntaxParser


def cmd_execute(args):
    """Execute a syntax query."""
    async def run():
        executor = SyntaxExecutor()

        try:
            result = await executor.execute(
                query=args.query,
                project_id=args.project or "default"
            )

            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                # Pretty print result
                print(f"\n=== Syntax Execution: {args.query} ===\n")

                if result.get("error"):
                    print(f"ERROR: {result['error']}")
                    return

                if result.get("operator"):
                    print(f"Operator: {result['operator']}")
                if result.get("module"):
                    print(f"Module: {result['module']}")
                if result.get("tier"):
                    print(f"Tier: {result['tier']}")
                if result.get("layer"):
                    print(f"Layer: {result['layer']}")

                # Print results
                if result.get("results"):
                    results = result["results"]
                    if isinstance(results, list):
                        print(f"\nResults ({len(results)} items):")
                        for i, item in enumerate(results[:20], 1):
                            if isinstance(item, dict):
                                title = item.get("title") or item.get("name") or item.get("url", "")
                                print(f"  {i}. {title[:80]}")
                            else:
                                print(f"  {i}. {str(item)[:80]}")
                    elif isinstance(results, dict):
                        print(f"\nResults:")
                        print(json.dumps(results, indent=2, default=str)[:2000])
                    else:
                        print(f"\nResults: {results}")

                if result.get("count"):
                    print(f"\nTotal: {result['count']}")

        except Exception as e:
            if args.json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}")

    asyncio.run(run())


def cmd_parse(args):
    """Parse a syntax query without executing."""
    parser = SyntaxParser()

    try:
        parsed = parser.parse(args.query)

        if args.json:
            print(json.dumps(parsed, indent=2, default=str))
        else:
            print(f"\n=== Parsed Syntax: {args.query} ===\n")
            print(f"Operator: {parsed.get('operator', 'N/A')}")
            print(f"Target: {parsed.get('target', 'N/A')}")
            print(f"Module: {parsed.get('module', 'auto')}")
            print(f"Tier: {parsed.get('tier', 't2')}")
            print(f"Layer: {parsed.get('layer', 'l2')}")

            if parsed.get("modifiers"):
                print(f"Modifiers: {parsed['modifiers']}")
            if parsed.get("flags"):
                print(f"Flags: {parsed['flags']}")

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"Parse error: {e}")


def cmd_operators(args):
    """List available operators."""
    # Load operators from registry
    operators_file = Path(__file__).parent / "operators.json"

    if not operators_file.exists():
        print("Operators registry not found")
        return

    with open(operators_file) as f:
        operators = json.load(f)

    # Filter by category if specified
    if args.category:
        cat = args.category.upper()
        operators = {
            k: v for k, v in operators.items()
            if v.get("dimensions", {}).get("why", "").upper() == cat
        }

    if args.json:
        print(json.dumps(operators, indent=2))
    else:
        print("\n=== SASTRE Syntax Operators ===\n")

        # Group by category
        categories = {}
        for op_id, op in operators.items():
            cat = op.get("dimensions", {}).get("why", "OTHER")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((op_id, op))

        for cat in sorted(categories.keys()):
            print(f"\n--- {cat} ---")
            for op_id, op in sorted(categories[cat]):
                desc = op.get("description", "")[:60]
                print(f"  {op_id}: {desc}")

                # Show examples
                examples = op.get("examples", [])
                if examples and args.examples:
                    for ex in examples[:2]:
                        print(f"    > {ex.get('query', '')}")


def cmd_modules(args):
    """List available modules."""
    modules = {
        "brute": {
            "description": "Multi-engine federated search",
            "prefix": "brute:",
            "operators": ["BRUTE_SEARCH", "EXACT_PHRASE"]
        },
        "linklater": {
            "description": "Link analysis and web investigation",
            "prefix": "linklater:, bl?, ol?",
            "operators": ["BACKLINKS", "OUTLINKS", "WHOIS", "TECHSTACK"]
        },
        "corporella": {
            "description": "Corporate intelligence",
            "prefix": "corporella:, c:",
            "operators": ["GLEIF", "EDGAR", "COMPANIES_HOUSE", "OPENCORPORATES"]
        },
        "eyed": {
            "description": "OSINT investigation",
            "prefix": "p:, e:, t:, c:, ent:",
            "operators": ["PERSON", "EMAIL", "PHONE", "COMPANY", "ENTITY"]
        },
        "optics": {
            "description": "Media footprint & reputation",
            "prefix": "optics:",
            "operators": ["ANALYZE", "QUICK", "TIER", "MISMATCHES"]
        },
        "socialite": {
            "description": "Social media intelligence",
            "prefix": "socialite:, social:, sm:",
            "operators": ["TWITTER", "INSTAGRAM", "LINKEDIN", "FACEBOOK"]
        },
        "submarine": {
            "description": "Web scraping",
            "prefix": "submarine:",
            "operators": ["SCRAPE", "BATCH", "ARCHIVE"]
        },
        "pacman": {
            "description": "Entity extraction",
            "prefix": "pacman:",
            "operators": ["EXTRACT", "CLASSIFY", "RED_FLAGS"]
        },
        "torpedo": {
            "description": "Corporate registry scrapers",
            "prefix": "torpedo:",
            "operators": ["UK", "US", "DE", "AT", "BE", "SE", "DK"]
        },
        "stories": {
            "description": "Narrative generation",
            "prefix": "stories:, narrative:",
            "operators": ["DETECT", "ARC", "FACADE", "GENERATE"]
        }
    }

    if args.json:
        print(json.dumps(modules, indent=2))
    else:
        print("\n=== SASTRE Modules ===\n")
        for name, info in sorted(modules.items()):
            print(f"{name.upper()}")
            print(f"  Description: {info['description']}")
            print(f"  Prefixes: {info['prefix']}")
            print(f"  Operators: {', '.join(info['operators'])}")
            print()


def cmd_tiers(args):
    """Show tier definitions."""
    tiers = {
        "t1": {
            "name": "Fast",
            "engines": 6,
            "description": "Quick results from fastest engines",
            "engines_list": ["Google", "Bing", "DuckDuckGo", "Brave", "Yandex", "Baidu"]
        },
        "t2": {
            "name": "Standard",
            "engines": 12,
            "description": "Balanced search across main engines [DEFAULT]",
            "engines_list": ["t1 + WhoisXML", "Ahrefs", "CommonCrawl", "Wayback", "GDELT", "News"]
        },
        "t3": {
            "name": "Deep",
            "engines": 15,
            "description": "Extended search with specialized sources",
            "engines_list": ["t2 + Academic", "Court records", "Patents"]
        },
        "t4": {
            "name": "Full",
            "engines": 19,
            "description": "Complete search with link analysis",
            "engines_list": ["t3 + All archives", "Link analysis", "Social"]
        },
        "t10": {"name": "Fast No-Scrape", "engines": 6, "description": "t1 without scraping"},
        "t20": {"name": "Standard No-Scrape", "engines": 12, "description": "t2 without scraping"},
        "t30": {"name": "Deep No-Scrape", "engines": 15, "description": "t3 without scraping"}
    }

    if args.json:
        print(json.dumps(tiers, indent=2))
    else:
        print("\n=== SASTRE Tiers (Which Engines) ===\n")
        for tier_id, info in tiers.items():
            print(f"{tier_id}: {info['name']} ({info['engines']} engines)")
            print(f"  {info['description']}")
            if info.get('engines_list'):
                print(f"  Engines: {', '.join(info['engines_list'][:5])}...")
            print()


def cmd_layers(args):
    """Show layer definitions."""
    layers = {
        "l1": {
            "name": "Native",
            "timeout": 30,
            "max_results": 50,
            "description": "Quick, shallow search"
        },
        "l2": {
            "name": "Enhanced",
            "timeout": 60,
            "max_results": 100,
            "description": "Standard depth [DEFAULT]"
        },
        "l3": {
            "name": "Brute",
            "timeout": 120,
            "max_results": 200,
            "description": "Deep, thorough search"
        },
        "l4": {
            "name": "Nuclear",
            "timeout": 300,
            "max_results": 500,
            "description": "Recursive, exhaustive search"
        }
    }

    if args.json:
        print(json.dumps(layers, indent=2))
    else:
        print("\n=== SASTRE Layers (Intensity) ===\n")
        for layer_id, info in layers.items():
            print(f"{layer_id}: {info['name']}")
            print(f"  Timeout: {info['timeout']}s")
            print(f"  Max results: {info['max_results']}")
            print(f"  {info['description']}")
            print()


def cmd_help(args):
    """Show syntax help."""
    print(__doc__)


def main():
    parser = argparse.ArgumentParser(
        description="SASTRE SYNTAX CLI - Primary Entry Point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python syntax_cli.py execute "p: John Smith"
  python syntax_cli.py execute "bl? example.com" --json
  python syntax_cli.py execute "brute: corruption t3 l3" --project myproject
  python syntax_cli.py parse "e: john@test.com t2"
  python syntax_cli.py operators --category DISCOVER
  python syntax_cli.py modules
  python syntax_cli.py tiers
  python syntax_cli.py layers
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # execute
    p_exec = subparsers.add_parser("execute", help="Execute syntax query")
    p_exec.add_argument("query", help="Syntax query to execute")
    p_exec.add_argument("--project", "-P", help="Project ID")
    p_exec.add_argument("--json", action="store_true", help="JSON output")
    p_exec.set_defaults(func=cmd_execute)

    # parse
    p_parse = subparsers.add_parser("parse", help="Parse syntax without executing")
    p_parse.add_argument("query", help="Syntax query to parse")
    p_parse.add_argument("--json", action="store_true", help="JSON output")
    p_parse.set_defaults(func=cmd_parse)

    # operators
    p_ops = subparsers.add_parser("operators", help="List operators")
    p_ops.add_argument("--category", "-c", help="Filter by category (DISCOVER, MAP, MODIFIER)")
    p_ops.add_argument("--examples", "-e", action="store_true", help="Show examples")
    p_ops.add_argument("--json", action="store_true", help="JSON output")
    p_ops.set_defaults(func=cmd_operators)

    # modules
    p_mods = subparsers.add_parser("modules", help="List modules")
    p_mods.add_argument("--json", action="store_true", help="JSON output")
    p_mods.set_defaults(func=cmd_modules)

    # tiers
    p_tiers = subparsers.add_parser("tiers", help="Show tier definitions")
    p_tiers.add_argument("--json", action="store_true", help="JSON output")
    p_tiers.set_defaults(func=cmd_tiers)

    # layers
    p_layers = subparsers.add_parser("layers", help="Show layer definitions")
    p_layers.add_argument("--json", action="store_true", help="JSON output")
    p_layers.set_defaults(func=cmd_layers)

    # help
    p_help = subparsers.add_parser("help", help="Show syntax help")
    p_help.set_defaults(func=cmd_help)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
