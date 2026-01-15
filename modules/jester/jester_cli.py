#!/usr/bin/env python3
"""
JESTER CLI - Unified Scraping System

MCP-compatible flags. Output: JSON to stdout.

Usage:
    jester_cli.py --scrape -u https://example.com
    jester_cli.py --scrape -u https://example.com --method jester_a
    jester_cli.py --batch --urls urls.txt
    jester_cli.py --extract -u https://example.com
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.jester.scraper import Jester, JesterMethod, JesterConfig


def out(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    p = argparse.ArgumentParser(description="JESTER CLI - Unified Scraper")
    
    # Input
    p.add_argument('--url', '-u', help='URL to scrape')
    p.add_argument('--urls', help='File with URLs (one per line)')
    p.add_argument('--file', '-f', help='Output file (optional)')
    
    # Operations
    p.add_argument('--scrape', '-s', action='store_true', help='Scrape URL')
    p.add_argument('--batch', '-b', action='store_true', help='Batch scrape URLs')
    p.add_argument('--extract', '-e', action='store_true', help='Scrape and extract entities')
    
    # Options
    p.add_argument('--method', '-m', choices=['jester_a', 'jester_b', 'jester_c', 'jester_d', 'firecrawl'],
                   help='Force specific method')
    p.add_argument('--timeout', '-t', type=int, default=30, help='Timeout seconds')
    p.add_argument('--concurrent', '-c', type=int, default=50, help='Concurrent requests')
    p.add_argument('--html-only', action='store_true', help='Return HTML only, no metadata')
    
    args = p.parse_args()
    
    config = JesterConfig()
    if args.timeout:
        config.timeout_a = args.timeout
        config.timeout_b = args.timeout
    
    jester = Jester(config)
    
    try:
        if args.scrape and args.url:
            if args.method:
                method_map = {
                    'jester_a': jester.scrape_a,
                    'jester_b': jester.scrape_b,
                    'jester_c': jester.scrape_c,
                    'jester_d': jester.scrape_d,
                }
                fn = method_map.get(args.method)
                if fn:
                    result = await fn(args.url)
                else:
                    result = await jester.scrape(args.url)
            else:
                result = await jester.scrape(args.url)
            
            if args.html_only:
                print(result.html if hasattr(result, 'html') else result)
            else:
                out({
                    'url': args.url,
                    'html': result.html[:5000] if hasattr(result, 'html') else str(result)[:5000],
                    'method': result.method.value if hasattr(result, 'method') else 'unknown',
                    'latency_ms': result.latency_ms if hasattr(result, 'latency_ms') else 0,
                    'status_code': result.status_code if hasattr(result, 'status_code') else 0,
                    'content_length': len(result.html) if hasattr(result, 'html') else 0,
                })
            return
        
        if args.batch and args.urls:
            with open(args.urls) as f:
                urls = [l.strip() for l in f if l.strip()]
            
            results = await jester.scrape_batch(urls, max_concurrent=args.concurrent)
            out({
                'results': [{
                    'url': r.url,
                    'method': r.method.value,
                    'status_code': r.status_code,
                    'content_length': len(r.html) if r.html else 0,
                    'error': r.error
                } for r in results]
            })
            return
        
        if args.extract and args.url:
            result = await jester.scrape(args.url)
            # Import PACMAN for extraction
            try:
                sys.path.insert(0, "/data")
                from PACMAN.entity_extractors import extract_fast
                entities = extract_fast(result.html if hasattr(result, 'html') else str(result))
            except ImportError:
                entities = {}
            
            out({
                'url': args.url,
                'method': result.method.value if hasattr(result, 'method') else 'unknown',
                'entities': entities,
            })
            return
        
        p.print_help()
    
    finally:
        await jester.close()


if __name__ == '__main__':
    asyncio.run(main())
