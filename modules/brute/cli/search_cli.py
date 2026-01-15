#!/usr/bin/env python3
"""
Unified Search CLI - The Command Center for Search Engineer MCP
Explicit mode selection for professional investigative control with L1/L2/L3 depth.
"""

import argparse
import asyncio
import sys
import re
from pathlib import Path
import logging

# Add module paths
BRUTE_DIR = Path(__file__).resolve().parents[1]
MODULES_DIR = BRUTE_DIR.parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# Import Searchers
from brute.infrastructure.streaming_search import StreamingSearchEngine
from brute.targeted_searches.news.news import NewsSearcher
from brute.targeted_searches.filetypes.filetype import FileTypeSearcher
from brute.targeted_searches.domain.site import SiteSearch
from brute.targeted_searches.content.title import TitleSearcher
from brute.targeted_searches.temporal.temporal import DateSearchRouter
from brute.targeted_searches.content.inurl import InURLSearch
from brute.targeted_searches.content.intext import InTextSearcher
from brute.targeted_searches.domain.ip import IPSearcher
from brute.targeted_searches.domain.link import LinkSearcher
from brute.targeted_searches.special.script import ScriptSearcher
from brute.targeted_searches.domain.related import RelatedSearcher
from brute.targeted_searches.special.public_records import PublicRecordsSearcher
from brute.targeted_searches.special.feed import FeedSearcher
from brute.targeted_searches.location.geo import LocationSearcher
from brute.targeted_searches.content.language import LanguageSearcher

# Configure Logging
logging.basicConfig(level=logging.ERROR, format='%(message)s')
logger = logging.getLogger("SearchCLI")

async def main():
    parser = argparse.ArgumentParser(description="Unified Search Engine CLI - Professional Investigative Tool")
    parser.add_argument("query", help="Search query")
    
    # Depth Level Control (L1/L2/L3)
    parser.add_argument("--level", "-l", type=int, choices=[1, 2, 3], default=2, 
                        help="Search depth level: 1=Native, 2=Native+Tricks (Default), 3=Native+Tricks+Brute")

    # Mode flags (Mutually exclusive group)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--broad", action="store_true", help="Broad search across all engines (Uses L1/L2/L3 logic)")
    mode_group.add_argument("--news", action="store_true", help="News search (NewsAPI, GDELT, Bangs)")
    mode_group.add_argument("--filetype", action="store_true", help="Filetype search (requires 'filetype:ext' in query)")
    mode_group.add_argument("--site", action="store_true", help="Site search (requires 'site:domain' in query)")
    mode_group.add_argument("--date", action="store_true", help="Date search (requires date operator)")
    mode_group.add_argument("--title", action="store_true", help="Title search (requires 'intitle:' operator)")
    mode_group.add_argument("--inurl", action="store_true", help="URL search (requires 'inurl:' operator)")
    mode_group.add_argument("--intext", action="store_true", help="Text search (requires 'intext:' operator)")
    mode_group.add_argument("--link", action="store_true", help="Link search (requires 'link:' operator)")
    mode_group.add_argument("--ip", action="store_true", help="IP search (requires 'ip:' operator)")
    mode_group.add_argument("--related", action="store_true", help="Related search (requires 'related:' operator)")
    mode_group.add_argument("--feed", action="store_true", help="Feed search (requires 'feed:' operator)")
    mode_group.add_argument("--script", action="store_true", help="Script search (requires 'script:' operator)")
    mode_group.add_argument("--records", action="store_true", help="Public Records search (FOI/Transparency)")
    
    parser.add_argument("--limit", type=int, default=50, help="Max results")
    parser.add_argument("--news-mode", choices=["global", "national"], help="News mode override")
    parser.add_argument("--news-country", help="ISO-2 country code for national news")
    parser.add_argument("--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    if not args.json:
        print(f"\n🚀 Query: {args.query} (Level {args.level})")
        print("="*60)

    results = []
    
    try:
        if args.broad:
            # Use Streaming Engine for broad/mixed queries
            # It handles L1/L2 expansion internally for all types!
            searcher = StreamingSearchEngine(engines=[], query=args.query, level=args.level)

            if not args.json:
                print(f"{'{SOURCE}':<10} | { '{CATEGORY}':<15} | { 'TITLE'}")
                print("-" * 60)

            async for event in searcher.stream_results():
                if event['type'] == 'results':
                    for res in event['data']:
                        if not args.json:
                            print(f"{event['engine']:<10} | {res.get('category','uncategorized')[:15]:<15} | {res.get('title', '')[:50]}")

            results = searcher.get_all_results()
            
        elif args.news:
            searcher = NewsSearcher()
            # NewsSearcher doesn't support level explicitly yet, but we can adapt it
            # For now, standard search
            data = await searcher.search(
                args.query,
                max_results=args.limit,
                mode=args.news_mode,
                country=args.news_country,
            )
            results = data.get('results', [])
            for r in results:
                print(f"[{r.get('source', '?')}] {r.get('title')}")
                
        elif args.filetype:
            clean_query = args.query.replace('!', '')
            if 'filetype:' not in clean_query:
                parts = clean_query.split()
                ext = parts[-1]
                base = " ".join(parts[:-1])
                clean_query = f"{base} filetype:{ext}!" 
            
            searcher = FileTypeSearcher()
            # Pass level via recall_config logic or explicit param?
            # For now, standard search
            await searcher.search_filetype(clean_query, clean_query.split()[-1], args.limit)
            
        elif args.site:
            searcher = SiteSearch()
            match = re.search(r'site:([^\s]+)', args.query)
            pattern = match.group(1) if match else ""
            base = args.query.replace(match.group(0), '').strip() if match else args.query
            
            if pattern:
                res = await searcher.search_with_filtering(base, pattern, args.limit)
                for engine, items in res.items():
                    for item in items:
                        print(f"[{engine}] {item.get('url')}")
                        
        elif args.date:
            searcher = DateSearchRouter()
            searcher.search(args.query)
            
        elif args.title:
            searcher = TitleSearcher()
            await searcher.search_title(args.query, args.limit)
            
        elif args.records:
            searcher = PublicRecordsSearcher()
            await searcher.search(args.query, args.limit)
            
        elif args.inurl:
            searcher = InURLSearch()
            match = re.search(r'inurl:([^\s]+)', args.query)
            keyword = match.group(1) if match else args.query
            res = await searcher.search_urls(keyword, args.limit)
            for engine, urls in res.items():
                print(f"\n{engine}:")
                for url in urls:
                    print(f"  {url}")
        elif args.intext:
            searcher = InTextSearcher()
            data = await searcher.search(args.query, args.limit)
            results = data.get("results", [])
            for r in results:
                print(f"[{r.get('source', '?')}] {r.get('title')}") 

        elif args.link:
            searcher = LinkSearcher()
            await searcher.search(args.query, args.limit)

        elif args.ip:
            searcher = IPSearcher()
            await searcher.search(args.query, args.limit)

        elif args.related:
            searcher = RelatedSearcher()
            await searcher.search(args.query, args.limit)

        elif args.feed:
            searcher = FeedSearcher()
            await searcher.search(args.query, args.limit)

        elif args.script:
            searcher = ScriptSearcher()
            await searcher.search(args.query, args.limit)
            
        else:
            print("Unknown mode selected.")

    except Exception as e:
        logger.error(f"Search failed: {e}")
        import traceback
        traceback.print_exc()

    # Output results as JSON if requested
    if args.json:
        import json
        output = {
            'query': args.query,
            'level': args.level,
            'results': results,
            'total': len(results)
        }
        print(json.dumps(output, indent=2))
    else:
        print("\n✅ Search Complete.")

if __name__ == "__main__":
    asyncio.run(main())
