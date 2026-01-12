#!/usr/bin/env python3
"""
BACKDRILL CLI - Unified Archive Search

MCP-compatible flags. Output: JSON to stdout.

Usage:
    backdrill_cli.py --fetch -u https://example.com
    backdrill_cli.py --fetch -u https://example.com --source wb_cdx
    backdrill_cli.py --batch --urls urls.txt
    backdrill_cli.py --cdx -u https://example.com --from 2020 --to 2023
    backdrill_cli.py --outlinks -u https://example.com
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.BACKDRILL.backdrill import Backdrill, ArchiveSource


def out(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    p = argparse.ArgumentParser(description="BACKDRILL CLI - Archive Search")
    
    # Input
    p.add_argument('--url', '-u', help='URL to fetch')
    p.add_argument('--urls', help='File with URLs')
    p.add_argument('--domain', '-d', help='Domain to search')
    
    # Operations
    p.add_argument('--fetch', '-f', action='store_true', help='Fetch URL from archives')
    p.add_argument('--batch', '-b', action='store_true', help='Batch fetch URLs')
    p.add_argument('--cdx', action='store_true', help='Get CDX index entries')
    p.add_argument('--outlinks', '-o', action='store_true', help='Extract outlinks from archived page')
    p.add_argument('--domain-search', action='store_true', help='Search domain in archives')
    
    # Options
    p.add_argument('--source', '-s', choices=['cc_index', 'cc_data', 'wb_cdx', 'wb_data', 'memento'],
                   help='Specific archive source')
    p.add_argument('--from', dest='from_date', help='Start date (YYYY or YYYYMMDD)')
    p.add_argument('--to', dest='to_date', help='End date (YYYY or YYYYMMDD)')
    p.add_argument('--limit', '-l', type=int, default=100, help='Max results')
    p.add_argument('--concurrent', '-c', type=int, default=50, help='Concurrent requests')
    
    args = p.parse_args()
    
    bd = Backdrill()
    
    try:
        if args.fetch and args.url:
            source = ArchiveSource(args.source) if args.source else None
            result = await bd.fetch(args.url, source=source)
            out({
                'url': args.url,
                'success': result.success,
                'source': result.source.value if result.source else None,
                'timestamp': result.timestamp,
                'status_code': result.status_code,
                'content_length': len(result.content or result.html or ''),
                'content_preview': (result.content or result.html or '')[:2000],
            })
            return
        
        if args.batch and args.urls:
            with open(args.urls) as f:
                urls = [l.strip() for l in f if l.strip()]
            
            results = await bd.fetch_batch(urls, concurrent=args.concurrent)
            out({
                'results': [{
                    'url': r.url,
                    'success': r.success,
                    'source': r.source.value if r.source else None,
                    'timestamp': r.timestamp,
                } for r in results]
            })
            return
        
        if args.cdx and args.url:
            entries = await bd.cdx_search(
                args.url,
                from_date=args.from_date,
                to_date=args.to_date,
                limit=args.limit
            )
            out({'entries': entries})
            return
        
        if args.outlinks and args.url:
            links = await bd.extract_outlinks(args.url)
            out({'outlinks': links})
            return
        
        if args.domain_search and args.domain:
            results = await bd.search_domain(
                args.domain,
                from_date=args.from_date,
                to_date=args.to_date,
                limit=args.limit
            )
            out({'results': results})
            return
        
        p.print_help()
    
    finally:
        await bd.close()


if __name__ == '__main__':
    asyncio.run(main())
