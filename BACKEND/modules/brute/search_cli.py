#!/usr/bin/env python3
"""
BRUTE Search CLI - Wrapper for brute.py with simplified interface

Maps level-based interface to brute.py tier system:
  Level 1 = fast tier (native engines only)
  Level 2 = medium tier (native + tricks)
  Level 3 = all tier (brute force - all engines)

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


def level_to_tier(level: int) -> str:
    """Map level (1-3) to tier name."""
    mapping = {
        1: 'fast',
        2: 'medium',
        3: 'all'
    }
    return mapping.get(level, 'medium')


def search(query: str, level: int = 2, mode: str = 'broad', limit: int = 50) -> dict:
    """
    Run BRUTE search with simplified interface.

    Args:
        query: Search query
        level: 1=fast, 2=medium, 3=all
        mode: broad, news, filetype, site, etc.
        limit: Max results

    Returns:
        dict with query, level, results
    """
    tier = level_to_tier(level)
    engines = ENGINE_PERFORMANCE.get(tier, [])

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
            'level': level,
            'tier': tier,
            'mode': mode,
            'total_results': len(results),
            'results': formatted_results
        }

    except Exception as e:
        return {
            'error': str(e),
            'query': query,
            'level': level,
            'results': []
        }


def main():
    parser = argparse.ArgumentParser(description='BRUTE Search CLI')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--level', type=int, choices=[1, 2, 3], default=2,
                       help='Search depth: 1=fast, 2=medium, 3=all')
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

    result = search(args.query, args.level, mode, args.limit)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        print(f"\n{'='*60}")
        print(f"BRUTE Search - Level {args.level} ({level_to_tier(args.level)} tier)")
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
