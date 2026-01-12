#!/usr/bin/env python3
"""
LINKLATER CLI (MCP Entry Point)
===============================

Unified command-line wrapper around the CC-first stack:
- Domain-wide CC index discovery + CC-only scrape + entity extraction
- Single-URL CC-first scrape
- Keyword-variations URL search (Wayback + Common Crawl index)

Usage examples:
  # Domain-wide extract (entities only)
  python linklater_cli.py domain-extract --domain example.com --limit 200

  # Domain-wide extract including content
  python linklater_cli.py domain-extract --domain example.com --limit 100 --include-content

  # Single URL scrape (CC-first)
  python linklater_cli.py scrape --url https://example.com/page

  # Keyword variations search (Wayback + CC index)
  python linklater_cli.py kv-search --keyword "john smith" --max-results 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import List, Optional

from modules.cc_content.cc_first_scraper import CCFirstScraper
from modules.cc_content.entity_patterns import EntityExtractor
from modules.cc_content.keyword_variations import KeywordVariationsSearch


async def cmd_domain_extract(args: argparse.Namespace):
  # 1) discover URLs from CC index
  scraper = CCFirstScraper(cc_only=True, cc_collection=args.cc_collection or None)

  # Try multiple strategies to find URLs
  url_list = []
  strategies_tried = []

  # Strategy 1: Wildcard with current domain
  params = {
    'url': f'*.{args.domain}/*',
    'output': 'json',
    'limit': str(args.limit),
  }
  session = await scraper._get_session()
  async with session.get(scraper.cc_index_url, params=params) as resp:
    if resp.status == 200:
      text = await resp.text()
      for line in text.strip().split('\n'):
        try:
          rec = json.loads(line)
          if rec.get('url'):
            url_list.append(rec['url'])
        except Exception:
          continue

  strategies_tried.append(f"*.{args.domain}/* → {len(url_list)} URLs")

  # DIG DEEPER if no results found
  if not url_list:
    # Strategy 2: Try without wildcard (exact domain)
    params['url'] = f'{args.domain}/*'
    async with session.get(scraper.cc_index_url, params=params) as resp:
      if resp.status == 200:
        text = await resp.text()
        for line in text.strip().split('\n'):
          try:
            rec = json.loads(line)
            if rec.get('url') and rec['url'] not in url_list:
              url_list.append(rec['url'])
          except Exception:
            continue
    strategies_tried.append(f"{args.domain}/* → {len(url_list)} URLs")

    # Strategy 3: Try with www. if not present, or without if present
    if not url_list:
      alt_domain = f"www.{args.domain}" if not args.domain.startswith('www.') else args.domain[4:]
      params['url'] = f'*.{alt_domain}/*'
      async with session.get(scraper.cc_index_url, params=params) as resp:
        if resp.status == 200:
          text = await resp.text()
          for line in text.strip().split('\n'):
            try:
              rec = json.loads(line)
              if rec.get('url') and rec['url'] not in url_list:
                url_list.append(rec['url'])
            except Exception:
              continue
      strategies_tried.append(f"*.{alt_domain}/* → {len(url_list)} URLs")

    # Strategy 4: Try older CC collections (last 3 months)
    if not url_list:
      older_collections = [
        'CC-MAIN-2025-46',
        'CC-MAIN-2025-45',
        'CC-MAIN-2025-44'
      ]
      for collection in older_collections:
        old_index_url = f"{scraper.CC_INDEX_BASE}/{collection}-index"
        params['url'] = f'*.{args.domain}/*'
        try:
          async with session.get(old_index_url, params=params) as resp:
            if resp.status == 200:
              text = await resp.text()
              for line in text.strip().split('\n'):
                try:
                  rec = json.loads(line)
                  if rec.get('url') and rec['url'] not in url_list:
                    url_list.append(rec['url'])
                except Exception:
                  continue
          strategies_tried.append(f"{collection} *.{args.domain}/* → {len(url_list)} URLs")
          if url_list:
            break  # Found some, stop trying older collections
        except Exception as e:
          strategies_tried.append(f"{collection} → error: {str(e)[:50]}")
          continue

  if not url_list:
    result = {
      'success': True,
      'domain': args.domain,
      'discovered': 0,
      'results': {},
      'entities': {},
      'strategies_tried': strategies_tried,
      'message': 'No pages found in Common Crawl archives after trying multiple strategies'
    }
    print(json.dumps(result, indent=2))
    await scraper.close()
    return

  # 2) scrape CC-only
  scrape_results = await scraper.batch_scrape(url_list, max_concurrent=args.max_concurrent)
  await scraper.close()

  # 3) extract entities
  extractor = EntityExtractor(jurisdictions=args.jurisdictions)
  results_out = {}
  agg_entities = {k: [] for k in ['companies', 'registrations', 'persons', 'dates', 'financials']}

  for url in url_list:
    res = scrape_results.get(url)
    if not res or res.source == 'failed':
      results_out[url] = {'success': False, 'source': res.source if res else 'failed', 'error': res.error if res else 'not_found'}
      continue

    content = res.content or ''
    if len(content) > args.max_content_length:
      content = content[:args.max_content_length]

    ents = extractor.extract_all(content)
    results_out[url] = {
      'success': True,
      'source': res.source,
      'timestamp': res.timestamp,
      'content_length': len(content),
      'entities': {k: extractor.to_dict(v) for k, v in ents.items()},
    }
    if args.include_content:
      results_out[url]['content'] = content
    for k, v in ents.items():
      agg_entities[k].extend(extractor.to_dict(v))

  if args.pretty:
    # Render a compact, human-readable summary
    total = len(url_list)
    cc_hits = sum(1 for r in results_out.values() if r.get('source') == 'cc')
    print(f"LINKLATER: Domain extract for {args.domain}")
    print(f"- URLs discovered: {total}")
    print(f"- CC hits: {cc_hits}")
    if len(strategies_tried) > 1:
      print(f"- Search strategies tried: {len(strategies_tried)}")
      for strategy in strategies_tried:
        print(f"    {strategy}")
    print("- Top entities:")
    for etype, items in agg_entities.items():
      if not items:
        continue
      print(f"  {etype}:")
      for item in items[:5]:
        txt = item.get('text') or ''
        juris = item.get('jurisdiction')
        ctx = item.get('context') or ''
        print(f"    • {txt} ({juris}) — {ctx[:90]}{'…' if len(ctx)>90 else ''}")
    if not any(agg_entities.values()):
      print("  (none)")
    print("- Sample URLs:")
    for url, r in list(results_out.items())[:5]:
      print(f"  {url} [{r.get('source')}] len={r.get('content_length')}")
  else:
    print(json.dumps({
      'success': True,
      'domain': args.domain,
      'discovered': len(url_list),
      'strategies_tried': strategies_tried,
      'results': results_out,
      'entities': agg_entities,
    }, indent=2))


async def cmd_scrape(args: argparse.Namespace):
  scraper = CCFirstScraper(cc_only=args.cc_only)
  result = await scraper.get_content(args.url)
  await scraper.close()
  out = {
    'success': result.source != 'failed',
    'url': args.url,
    'source': result.source,
    'timestamp': result.timestamp,
    'status': result.status,
    'error': result.error,
    'content_length': len(result.content),
  }
  if args.include_content:
    out['content'] = result.content
  print(json.dumps(out, indent=2))


async def cmd_kv_search(args: argparse.Namespace):
  searcher = KeywordVariationsSearch(
    max_results_per_source=args.max_results,
    verify_snippets=args.verify_snippets,
  )
  result = await searcher.search(
    keyword=args.keyword,
    verify_snippets=args.verify_snippets,
    max_concurrent=args.max_concurrent,
  )
  await searcher.close()
  search_results = searcher.to_search_results(result, include_unverified=args.include_unverified)
  out = {
    'success': True,
    'keyword': result.keyword,
    'variations_searched': result.variations_searched,
    'total_matches': result.total_matches,
    'unique_urls': result.unique_urls,
    'wayback_hits': result.wayback_hits,
    'cc_hits': result.cc_hits,
    'verified_hits': result.verified_hits,
    'elapsed_seconds': result.elapsed_seconds,
    'results': search_results,
  }
  print(json.dumps(out, indent=2))


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(description="LINKLATER MCP CLI - CC-first discovery + keyword variations")
  sub = p.add_subparsers(dest='command', required=True)

  d = sub.add_parser('domain-extract', help='Discover domain URLs from CC index, scrape CC-only, extract entities')
  d.add_argument('--domain', required=True)
  d.add_argument('--limit', type=int, default=200)
  d.add_argument('--max-concurrent', type=int, default=10)
  d.add_argument('--include-content', action='store_true')
  d.add_argument('--max-content-length', type=int, default=60000)
  d.add_argument('--jurisdictions', nargs='*')
  d.add_argument('--cc-collection', help='Override CC index collection (e.g., CC-MAIN-2025-47)')
  d.add_argument('--pretty', action='store_true', help='Human-readable summary output')
  d.set_defaults(func=cmd_domain_extract)

  s = sub.add_parser('scrape', help='CC-first scrape a single URL')
  s.add_argument('--url', required=True)
  s.add_argument('--include-content', action='store_true')
  s.add_argument('--cc-only', action='store_true', help='Disable Firecrawl fallback')
  s.set_defaults(func=cmd_scrape)

  k = sub.add_parser('kv-search', help='Keyword variations search (Wayback + CC index)')
  k.add_argument('--keyword', required=True)
  k.add_argument('--max-results', type=int, default=100)
  k.add_argument('--max-concurrent', type=int, default=10)
  k.add_argument('--verify-snippets', action='store_true', help='Verify keyword in page content (CC fetch)')
  k.add_argument('--include-unverified', action='store_true', help='Include unverified URL matches')
  k.set_defaults(func=cmd_kv_search)

  return p


def main(argv: Optional[List[str]] = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)

  try:
    asyncio.run(args.func(args))
    return 0
  except KeyboardInterrupt:
    return 130


if __name__ == "__main__":
  raise SystemExit(main())
