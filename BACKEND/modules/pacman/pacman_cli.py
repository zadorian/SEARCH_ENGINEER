#!/usr/bin/env python3
"""
PACMAN CLI - Pattern and Content Analysis Module

MCP-compatible flags for all operations.
All output is JSON to stdout.

Usage:
    pacman_cli.py --extract -c "John Smith is CEO of Acme Ltd"
    pacman_cli.py --persons -c "..."
    pacman_cli.py --companies -c "..."
    pacman_cli.py --classify-url -u https://companieshouse.gov.uk/company/123
    pacman_cli.py --red-flags -c "money laundering sanctions"
    pacman_cli.py --links -u https://example.com --html "<a href=..."
    pacman_cli.py --full -c "..." -u https://example.com
    pacman_cli.py --tiered --urls urls.txt
    pacman_cli.py --blitz --domains domains.txt
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

# sys.path configured in PYTHONPATH

from PACMAN.patterns import ALL_PATTERNS
from PACMAN.entity_extractors import extract_fast, extract_persons, extract_companies
from PACMAN.classifiers import classify_url, classify_content, scan_content, has_red_flags
from PACMAN.link_extractors import extract_links
from PACMAN.batch_runners import TieredRunner, BlitzRunner


def out(data):
    print(json.dumps(data, indent=2, default=str))


def get_content(args) -> Optional[str]:
    if args.content:
        return args.content
    if args.file:
        with open(args.file) as f:
            return f.read()
    if args.stdin:
        return sys.stdin.read()
    return None


async def main():
    p = argparse.ArgumentParser(description="PACMAN CLI")
    
    # Input
    p.add_argument('--content', '-c', help='Content string')
    p.add_argument('--file', '-f', help='File path')
    p.add_argument('--stdin', action='store_true', help='Read stdin')
    p.add_argument('--url', '-u', help='URL context')
    p.add_argument('--html', help='HTML for link extraction')
    
    # Operations
    p.add_argument('--extract', '-e', action='store_true', help='Extract entities')
    p.add_argument('--persons', '-p', action='store_true', help='Extract persons')
    p.add_argument('--companies', '-C', action='store_true', help='Extract companies')
    p.add_argument('--classify-url', action='store_true', help='Classify URL tier')
    p.add_argument('--classify-content', action='store_true', help='Classify content tier')
    p.add_argument('--red-flags', '-r', action='store_true', help='Scan red flags')
    p.add_argument('--has-red-flags', action='store_true', help='Check any red flags')
    p.add_argument('--links', '-l', action='store_true', help='Extract links')
    p.add_argument('--full', action='store_true', help='Full extraction')
    
    # Batch
    p.add_argument('--tiered', action='store_true', help='Tiered batch')
    p.add_argument('--blitz', action='store_true', help='Blitz batch')
    p.add_argument('--urls', help='URLs file')
    p.add_argument('--domains', help='Domains file')
    
    # Options
    p.add_argument('--max', '-m', type=int, default=30, help='Max results')
    p.add_argument('--patterns', action='store_true', help='List patterns')
    
    args = p.parse_args()
    
    if args.patterns:
        out({'patterns': list(ALL_PATTERNS.keys())})
        return
    
    if args.extract:
        content = get_content(args)
        if not content:
            sys.exit("Error: --extract needs --content/-c")
        out({'entities': extract_fast(content)})
        return
    
    if args.persons:
        content = get_content(args)
        if not content:
            sys.exit("Error: --persons needs --content/-c")
        out({'persons': extract_persons(content, args.max)})
        return
    
    if args.companies:
        content = get_content(args)
        if not content:
            sys.exit("Error: --companies needs --content/-c")
        out({'companies': extract_companies(content, args.max)})
        return
    
    if args.classify_url:
        if not args.url:
            sys.exit("Error: --classify-url needs --url/-u")
        r = classify_url(args.url)
        out({'url': args.url, 'tier': r.tier.value, 'confidence': r.confidence, 'reasons': r.reasons})
        return
    
    if args.classify_content:
        content = get_content(args)
        if not content:
            sys.exit("Error: --classify-content needs --content/-c")
        r = classify_content(content, args.url or '')
        out({'tier': r.tier.value, 'confidence': r.confidence, 'reasons': r.reasons})
        return
    
    if args.red_flags:
        content = get_content(args)
        if not content:
            sys.exit("Error: --red-flags needs --content/-c")
        hits = scan_content(content)
        out({'red_flags': [{'pattern': h.pattern, 'category': h.category.value, 'context': h.context} for h in hits]})
        return
    
    if args.has_red_flags:
        content = get_content(args)
        if not content:
            sys.exit("Error: --has-red-flags needs --content/-c")
        out({'has_red_flags': has_red_flags(content)})
        return
    
    if args.links:
        html = args.html or get_content(args)
        if not html or not args.url:
            sys.exit("Error: --links needs --url and --html/--content")
        links = extract_links(html, args.url)
        out({'links': [{'url': l.url, 'type': l.link_type.value, 'anchor': l.anchor_text} for l in links]})
        return
    
    if args.full:
        content = get_content(args)
        if not content:
            sys.exit("Error: --full needs --content/-c")
        out({
            'url': args.url or '',
            'entities': extract_fast(content),
            'persons': extract_persons(content, args.max),
            'companies': extract_companies(content, args.max),
            'tier': classify_content(content, args.url or '').tier.value,
            'red_flags': [h.pattern for h in scan_content(content)]
        })
        return
    
    if args.tiered:
        if not args.urls:
            sys.exit("Error: --tiered needs --urls")
        with open(args.urls) as f:
            urls = [l.strip() for l in f if l.strip()]
        runner = TieredRunner()
        results = []
        async for r in runner.run(urls):
            results.append({'url': r.url, 'status': r.status, 'entities': r.entities, 'tier': r.tier})
        await runner.close()
        out({'results': results})
        return
    
    if args.blitz:
        if not args.domains:
            sys.exit("Error: --blitz needs --domains")
        with open(args.domains) as f:
            domains = [l.strip() for l in f if l.strip()]
        runner = BlitzRunner()
        results = []
        async for r in runner.run(domains):
            results.append({'domain': r.url, 'status': r.status, 'entities': r.entities})
        await runner.close()
        out({'results': results})
        return
    
    p.print_help()


if __name__ == '__main__':
    asyncio.run(main())
