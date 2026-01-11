#!/usr/bin/env python3
"""
TORPEDO CLI - Unified Search with Source Templates

MCP-compatible flags. Output: JSON to stdout (default) or file.

Usage:
    # Process sources
    torpedo_cli.py process cr sources.json --jurisdiction UK,DE
    torpedo_cli.py process news sources/news.json --limit 100
    
    # Search
    torpedo_cli.py search cr "Acme Ltd" --jurisdiction UK
    torpedo_cli.py search news "corruption" --jurisdiction HR
    
    # Info
    torpedo_cli.py info --sources sources.json

All commands output JSON to stdout by default.
Use --output/-o to write to file instead.

IMPORTANT: UK NOT GB for United Kingdom!
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger("TORPEDO")

TORPEDO_ROOT = Path(__file__).parent
sys.path.insert(0, str(TORPEDO_ROOT.parents[2]))


def out(data, output_file=None):
    """Output JSON to stdout or file."""
    json_str = json.dumps(data, indent=2, default=str, ensure_ascii=False)
    if output_file:
        with open(output_file, 'w') as f:
            f.write(json_str)
        logger.info(f"Written to {output_file}")
    else:
        print(json_str)


async def cmd_process_cr(args):
    """Process corporate registry sources."""
    from modules.TORPEDO.PROCESSING.cr_processor import CRProcessor
    
    sources_path = Path(args.sources)
    if not sources_path.exists():
        out({"error": f"Sources file not found: {sources_path}"}, args.output)
        return 1
    
    with open(sources_path) as f:
        data = json.load(f)
    
    processor = CRProcessor(concurrent=args.concurrent)
    
    # Filter by jurisdiction if specified
    if args.jurisdiction:
        allowed = [j.strip().upper() for j in args.jurisdiction.split(',')]
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k.upper() in allowed}
    
    results = await processor.process(data, limit=args.limit)
    
    out({
        "command": "process_cr",
        "sources_file": str(sources_path),
        "jurisdiction_filter": args.jurisdiction,
        "results": results
    }, args.output)
    
    return 0


async def cmd_process_news(args):
    """Process news sources."""
    from modules.TORPEDO.PROCESSING.news_processor import NewsProcessor
    
    sources_path = Path(args.sources)
    if not sources_path.exists():
        out({"error": f"Sources file not found: {sources_path}"}, args.output)
        return 1
    
    with open(sources_path) as f:
        data = json.load(f)
    
    processor = NewsProcessor(concurrent=args.concurrent)
    results = await processor.process(data, limit=args.limit)
    
    out({
        "command": "process_news",
        "sources_file": str(sources_path),
        "results": results
    }, args.output)
    
    return 0


async def cmd_process_seekleech(args):
    """Find search templates for unknown domains."""
    from modules.TORPEDO.PROCESSING.SEEKLEECH.seekleech import Seekleech
    
    domains_path = Path(args.domains)
    if not domains_path.exists():
        out({"error": f"Domains file not found: {domains_path}"}, args.output)
        return 1
    
    # Load domains
    if domains_path.suffix == '.json':
        with open(domains_path) as f:
            domains = json.load(f)
    else:
        with open(domains_path) as f:
            domains = [l.strip() for l in f if l.strip()]
    
    if args.limit:
        domains = domains[:args.limit]
    
    seeker = Seekleech()
    results = await seeker.discover(domains)
    
    out({
        "command": "process_seekleech",
        "domains_file": str(domains_path),
        "domains_count": len(domains),
        "results": results
    }, args.output)
    
    return 0


async def cmd_search_cr(args):
    """Search corporate registries."""
    from modules.TORPEDO.EXECUTION.cr_searcher import CRSearcher
    
    searcher = CRSearcher()
    
    if args.sources:
        await searcher.load_sources(args.sources)
    
    results = await searcher.search(
        query=args.query,
        jurisdiction=args.jurisdiction,
        limit=args.limit
    )
    
    out({
        "command": "search_cr",
        "query": args.query,
        "jurisdiction": args.jurisdiction,
        "limit": args.limit,
        "results_count": len(results),
        "results": results
    }, args.output)
    
    return 0


async def cmd_search_news(args):
    """Search news sources."""
    from modules.TORPEDO.EXECUTION.news_searcher import NewsSearcher
    
    searcher = NewsSearcher()
    
    if args.sources:
        await searcher.load_sources(args.sources)
    
    results = await searcher.search(
        query=args.query,
        jurisdiction=args.jurisdiction,
        limit=args.limit
    )
    
    out({
        "command": "search_news",
        "query": args.query,
        "jurisdiction": args.jurisdiction,
        "limit": args.limit,
        "results_count": len(results),
        "results": results
    }, args.output)
    
    return 0


async def cmd_info(args):
    """Show info about sources or ES index."""
    result = {"command": "info"}
    
    if args.sources:
        sources_path = Path(args.sources)
        if sources_path.exists():
            with open(sources_path) as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                result["type"] = "jurisdiction_keyed"
                result["jurisdictions"] = list(data.keys())
                result["total_sources"] = sum(len(v) for v in data.values())
                result["by_jurisdiction"] = {k: len(v) for k, v in data.items()}
            else:
                result["type"] = "list"
                result["total_sources"] = len(data)
        else:
            result["error"] = f"File not found: {sources_path}"
    
    if args.es_index:
        try:
            from elasticsearch import Elasticsearch
            es = Elasticsearch(['http://localhost:9200'])
            stats = es.indices.stats(index=args.es_index)
            result["es_index"] = args.es_index
            result["doc_count"] = stats['indices'][args.es_index]['primaries']['docs']['count']
            result["size_bytes"] = stats['indices'][args.es_index]['primaries']['store']['size_in_bytes']
        except Exception as e:
            result["es_error"] = str(e)
    
    out(result, args.output)
    return 0


def main():
    p = argparse.ArgumentParser(
        description="TORPEDO CLI - Unified Search",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global options
    p.add_argument('-o', '--output', help='Output file (default: stdout)')
    p.add_argument('-v', '--verbose', action='store_true', help='Verbose logging')
    
    subparsers = p.add_subparsers(dest='command', help='Commands')
    
    # === PROCESS ===
    process_p = subparsers.add_parser('process', help='Process/classify sources')
    process_sub = process_p.add_subparsers(dest='process_type')
    
    # process cr
    p_cr = process_sub.add_parser('cr', help='Process corporate registry sources')
    p_cr.add_argument('sources', help='Sources JSON file')
    p_cr.add_argument('-o', '--output', help='Output file')
    p_cr.add_argument('-c', '--concurrent', type=int, default=20, help='Concurrent requests')
    p_cr.add_argument('-l', '--limit', type=int, help='Limit sources')
    p_cr.add_argument('-j', '--jurisdiction', help='Filter jurisdictions (comma-sep)')
    
    # process news
    p_news = process_sub.add_parser('news', help='Process news sources')
    p_news.add_argument('sources', help='Sources JSON file')
    p_news.add_argument('-o', '--output', help='Output file')
    p_news.add_argument('-c', '--concurrent', type=int, default=20, help='Concurrent requests')
    p_news.add_argument('-l', '--limit', type=int, help='Limit sources')
    p_news.add_argument('-j', '--jurisdiction', help='Filter jurisdictions')
    
    # process seekleech
    p_seek = process_sub.add_parser('seekleech', help='Find search templates')
    p_seek.add_argument('domains', help='Domains file (.txt or .json)')
    p_seek.add_argument('-o', '--output', help='Output file')
    p_seek.add_argument('-l', '--limit', type=int, help='Limit domains')
    
    # === SEARCH ===
    search_p = subparsers.add_parser('search', help='Search sources')
    search_sub = search_p.add_subparsers(dest='search_type')
    
    # search cr
    s_cr = search_sub.add_parser('cr', help='Search corporate registries')
    s_cr.add_argument('query', help='Search query')
    s_cr.add_argument('-j', '--jurisdiction', help='Jurisdiction (UK, DE, HR...)')
    s_cr.add_argument('-l', '--limit', type=int, default=100, help='Max results')
    s_cr.add_argument('-s', '--sources', help='Sources JSON file')
    s_cr.add_argument('-o', '--output', help='Output file')
    
    # search news
    s_news = search_sub.add_parser('news', help='Search news sources')
    s_news.add_argument('query', help='Search query')
    s_news.add_argument('-j', '--jurisdiction', help='Jurisdiction')
    s_news.add_argument('-l', '--limit', type=int, default=100, help='Max results')
    s_news.add_argument('-s', '--sources', help='Sources JSON file')
    s_news.add_argument('-o', '--output', help='Output file')
    
    # === INFO ===
    info_p = subparsers.add_parser('info', help='Show stats/info')
    info_p.add_argument('-s', '--sources', help='Sources JSON file')
    info_p.add_argument('-e', '--es-index', help='Elasticsearch index')
    info_p.add_argument('-o', '--output', help='Output file')
    
    args = p.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    if not args.command:
        p.print_help()
        return 1
    
    # Route commands
    if args.command == 'process':
        if args.process_type == 'cr':
            return asyncio.run(cmd_process_cr(args))
        elif args.process_type == 'news':
            return asyncio.run(cmd_process_news(args))
        elif args.process_type == 'seekleech':
            return asyncio.run(cmd_process_seekleech(args))
        else:
            process_p.print_help()
            return 1
    
    elif args.command == 'search':
        if args.search_type == 'cr':
            return asyncio.run(cmd_search_cr(args))
        elif args.search_type == 'news':
            return asyncio.run(cmd_search_news(args))
        else:
            search_p.print_help()
            return 1
    
    elif args.command == 'info':
        return asyncio.run(cmd_info(args))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
