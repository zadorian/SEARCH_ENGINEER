#!/usr/bin/env python3
"""
BRUTE Search CLI - Wrapper for brute.py with simplified interface

TERMINOLOGY (see layers.py and tiers.py):

  TIERS = which engines to use
    t1 = fast engines (GO, BI, BR, DD, EX, CY)
    t2 = all standard engines
    t3 = all engines including slow
    t4 = all + LINKLATER (link analysis, requires scraping)

    No-scrape variants (add 0):
    t10 = fast + no scrape
    t20 = all + no scrape
    t30 = all+slow + no scrape
    (t40 invalid - link analysis requires scraping)

  LAYERS = search intensity (how hard) - see layers.py
    l1 = NATIVE (fast, clean)
    l2 = ENHANCED (workarounds, expansion)
    l3 = BRUTE (maximum recall)
    l4 = NUCLEAR (link expansion)

QUERY SYNTAX:
  Append "l1 t4" to query to set layer and tier inline.
  Examples:
    "john smith l1 t4" = native intensity + link analysis engines
    "acme corp l2 t20" = enhanced intensity + all engines + no scrape

Provides JSON output for MCP server integration.
"""

import argparse
import json
import sys
import asyncio
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from brute import BruteSearchEngine, ENGINE_PERFORMANCE
except ImportError:
    print("Error: Could not import brute.py", file=sys.stderr)
    sys.exit(1)


def tier_to_name(tier: int) -> str:
    """Map tier to engine group name.

    TIERS = which engines to use
      t1 = fast, t2 = all, t3 = all+slow, t4 = all+link
      t10, t20, t30 = same but no scraping

    See tiers.py for engine group definitions.
    """
    mapping = {
        1: 'fast',
        2: 'all',
        3: 'all+slow',
        4: 'all+link',
        10: 'fast (no scrape)',
        20: 'all (no scrape)',
        30: 'all+slow (no scrape)',
    }
    return mapping.get(tier, 'all')


def parse_layer_tier_from_query(query: str) -> tuple:
    """
    Parse layer and tier modifiers from query string.

    Syntax: "query text l1 t4" or "query text l2t30" or "query l1"

    Returns:
        (clean_query, layer, tier) - layer/tier are None if not specified

    Examples:
        "john smith l1 t4" -> ("john smith", 1, 4)
        "acme corp t20" -> ("acme corp", None, 20)  # no scrape
        "search query l3 t10" -> ("search query", 3, 10)
        "test t30" -> ("test", None, 30)  # all+slow, no scrape
    """
    import re

    clean_query = query.strip()
    layer = None
    tier = None

    # Match patterns like "l1", "l2", "t3", "t10", "t20", "t30", "l1 t4", "l2 t30"
    # At the end of the query
    # Support 1-2 digit tiers (t1-t4, t10, t20, t30)
    pattern = r'\s+([lt]\d{1,2})(?:\s+([lt]\d{1,2}))?\s*$'
    match = re.search(pattern, clean_query, re.I)

    if match:
        # Remove the matched part from query
        clean_query = clean_query[:match.start()].strip()

        # Parse the modifiers
        for group in [match.group(1), match.group(2)]:
            if group:
                modifier = group.lower()
                if modifier.startswith('l'):
                    layer = int(modifier[1:])
                elif modifier.startswith('t'):
                    tier = int(modifier[1:])

    return clean_query, layer, tier


def search(query: str, tier: int = None, layer: int = None, mode: str = 'broad', limit: int = 50) -> dict:
    """
    Run BRUTE search with simplified interface.

    Args:
        query: Search query (can include "l1 t4" at end)
        tier: 1=fast, 2=all, 3=all+slow, 4=all+link (which engines)
        layer: 1=native, 2=enhanced, 3=brute, 4=nuclear (intensity)
        mode: broad, news, filetype, site, etc.
        limit: Max results

    Returns:
        dict with query, tier, layer, results
    """
    # Parse layer/tier from query if present
    clean_query, query_layer, query_tier = parse_layer_tier_from_query(query)

    # Use parsed values if not explicitly provided
    if tier is None:
        tier = query_tier if query_tier else 2
    if layer is None:
        layer = query_layer if query_layer else 2

    query = clean_query
    tier_name = tier_to_name(tier)
    engines = ENGINE_PERFORMANCE.get(tier_name, [])

    # Apply mode-specific modifiers
    if mode == 'news':
        # Add news-specific engines
        query = f"{query}"  # Could add news operators
    elif mode == 'filetype':
        # Ensure filetype operator is in query
        if 'filetype:' not in query.lower():
            query = f"{query} filetype:pdf"
    elif mode == 'site':
        # Site search mode
        pass

    try:
        searcher = BruteSearchEngine(
            keyword=query,
            output_file=None,
            engines=engines,
            max_workers=10
        )

        results = searcher.search()

        # Format results for JSON output
        formatted_results = []
        for r in results[:limit]:
            formatted_results.append({
                'url': r.get('url', r.get('link', '')),
                'title': r.get('title', ''),
                'snippet': r.get('snippet', r.get('description', '')),
                'engine': r.get('source', r.get('engine', 'unknown')),
                'found_by': r.get('found_by', [r.get('source', 'unknown')])
            })

        return {
            'query': query,
            'tier': tier,
            'tier_name': tier_name,
            'mode': mode,
            'total_results': len(results),
            'results': formatted_results
        }

    except Exception as e:
        return {
            'error': str(e),
            'query': query,
            'tier': tier,
            'results': []
        }


def main():
    parser = argparse.ArgumentParser(description='BRUTE Search CLI')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--tier', type=int, default=2,
                       help='Engine tier: 1=fast, 2=all, 3=all+slow, 4=all+link; add 0 for no-scrape (10,20,30)')
    parser.add_argument('--limit', type=int, default=50,
                       help='Maximum results')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON format')

    # Mode flags (mutually exclusive for simplicity, but can be combined)
    parser.add_argument('--broad', action='store_true', help='Broad web search (default)')
    parser.add_argument('--news', action='store_true', help='News search mode')
    parser.add_argument('--filetype', action='store_true', help='Filetype search mode')
    parser.add_argument('--site', action='store_true', help='Site-specific search mode')
    parser.add_argument('--date', action='store_true', help='Date-filtered search')
    parser.add_argument('--title', action='store_true', help='Title search mode')
    parser.add_argument('--inurl', action='store_true', help='URL search mode')
    parser.add_argument('--link', action='store_true', help='Link search mode')
    parser.add_argument('--ip', action='store_true', help='IP search mode')
    parser.add_argument('--related', action='store_true', help='Related search mode')
    parser.add_argument('--feed', action='store_true', help='Feed search mode')
    parser.add_argument('--records', action='store_true', help='Records search mode')

    args = parser.parse_args()

    # Determine mode from flags
    mode = 'broad'
    for m in ['news', 'filetype', 'site', 'date', 'title', 'inurl', 'link', 'ip', 'related', 'feed', 'records']:
        if getattr(args, m, False):
            mode = m
            break

    result = search(args.query, args.tier, mode, args.limit)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        print(f"\n{'='*60}")
        print(f"BRUTE Search - Tier {args.tier} ({tier_to_name(args.tier)} engines)")
        print(f"{'='*60}")
        print(f"Query: {args.query}")
        print(f"Mode: {mode}")
        print(f"Results: {result.get('total_results', 0)}")
        print(f"{'='*60}\n")

        for i, r in enumerate(result.get('results', [])[:20], 1):
            print(f"{i}. {r.get('title', 'No title')[:70]}")
            print(f"   {r.get('url', '')}")
            print(f"   Source: {r.get('engine', 'unknown')}")
            print()


if __name__ == '__main__':
    main()
