#!/usr/bin/env python3
"""
AUTO BANG SEARCH MODULE
Automatically runs news + social bang searches for exact phrase queries.
Integrates with main search flow and LinkLater for priority scraping.

This module:
1. Detects exact phrase queries without filetype filters
2. Runs parallel bang scans (news + social)
3. Bulk scrapes incoming pages with cleaner extraction
4. Queues results for LinkLater priority processing
5. Returns normalized results for grid display

Usage:
    from auto_bang_search import auto_bang_search
    results = await auto_bang_search("Portofino Technologies", query_id="abc123")
"""

import asyncio
import aiohttp
import json
import re
import time
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import quote_plus, urlparse, unquote
from pathlib import Path
from html import unescape
from datetime import datetime
import hashlib

# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY NEWS BANGS - Curated high-quality sources
# ═══════════════════════════════════════════════════════════════════════════════

NEWS_BANGS = {
    # Wire Services & Aggregators
    'google_news': 'https://news.google.com/search?q={q}',
    'reuters': 'https://www.reuters.com/site-search/?query={q}',
    'ap': 'https://apnews.com/search?q={q}',
    'bbc': 'https://www.bbc.co.uk/search?q={q}',

    # US Major
    'nyt': 'https://www.nytimes.com/search?query={q}',
    'wapo': 'https://www.washingtonpost.com/search/?query={q}',
    'wsj': 'https://www.wsj.com/search?query={q}',
    'bloomberg': 'https://www.bloomberg.com/search?query={q}',
    'ft': 'https://www.ft.com/search?q={q}',

    # UK
    'guardian': 'https://www.theguardian.com/search?q={q}',
    'telegraph': 'https://www.telegraph.co.uk/search/?q={q}',

    # European
    'spiegel': 'https://www.spiegel.de/suche/?suchbegriff={q}',
    'lemonde': 'https://www.lemonde.fr/recherche/?search_keywords={q}',
    'corriere': 'https://www.corriere.it/ricerca/?q={q}',
    'elpais': 'https://elpais.com/buscador/?qt={q}',
    'nzz': 'https://www.nzz.ch/suche?q={q}',

    # Business
    'cnbc': 'https://www.cnbc.com/search/?query={q}',
    'forbes': 'https://www.forbes.com/search/?q={q}',
    'businessinsider': 'https://www.businessinsider.com/s?q={q}',

    # Tech
    'techcrunch': 'https://techcrunch.com/search/{q}',
    'verge': 'https://www.theverge.com/search?q={q}',
    'wired': 'https://www.wired.com/search/?q={q}',

    # Crypto
    'coindesk': 'https://www.coindesk.com/search?s={q}',
    'cointelegraph': 'https://cointelegraph.com/search?query={q}',
    'theblock': 'https://www.theblock.co/search?query={q}',

    # Investigative
    'icij': 'https://www.icij.org/?s={q}',
    'occrp': 'https://www.occrp.org/en/search?q={q}',
    'bellingcat': 'https://www.bellingcat.com/?s={q}',
}

# ═══════════════════════════════════════════════════════════════════════════════
# PRIORITY SOCIAL BANGS - Curated social sources
# ═══════════════════════════════════════════════════════════════════════════════

SOCIAL_BANGS = {
    # Twitter/X
    'twitter': 'https://twitter.com/search?q={q}&f=live',
    'nitter': 'https://nitter.net/search?q={q}',

    # Reddit
    'reddit': 'https://www.reddit.com/search/?q={q}',
    'reddit_new': 'https://www.reddit.com/search/?q={q}&sort=new',

    # LinkedIn
    'linkedin': 'https://www.linkedin.com/search/results/all/?keywords={q}',
    'linkedin_posts': 'https://www.linkedin.com/search/results/content/?keywords={q}',

    # YouTube
    'youtube': 'https://www.youtube.com/results?search_query={q}',

    # Hacker News
    'hackernews': 'https://hn.algolia.com/?q={q}',

    # GitHub
    'github': 'https://github.com/search?q={q}&type=repositories',

    # Mastodon/Fediverse
    'bluesky': 'https://bsky.app/search?q={q}',
    'mastodon': 'https://mastodon.social/tags/{q}',

    # Discord
    'disboard': 'https://disboard.org/search?keyword={q}',

    # Telegram
    'tgstat': 'https://tgstat.com/search?q={q}',

    # Business/Professional
    'crunchbase': 'https://www.crunchbase.com/textsearch?q={q}',
    'angellist': 'https://wellfound.com/search?q={q}',
    'glassdoor': 'https://www.glassdoor.com/Search/results.htm?keyword={q}',

    # Forums
    'quora': 'https://www.quora.com/search?q={q}',
    'stackoverflow': 'https://stackoverflow.com/search?q={q}',
}


# ═══════════════════════════════════════════════════════════════════════════════
# SNIPPET EXTRACTION (cleaned up)
# ═══════════════════════════════════════════════════════════════════════════════

def clean_html_to_text(html: str) -> str:
    """Strip HTML to clean text for snippet extraction"""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = unquote(text)

    # Remove CSS/JS artifacts
    text = re.sub(r'\{[^}]+\}', ' ', text)
    text = re.sub(r'https?://[^\s<>"]+', ' ', text)
    text = re.sub(r'\\u[0-9a-fA-F]{4}', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def extract_snippets(html: str, keywords: List[str], max_snippets: int = 3, context_chars: int = 150) -> List[str]:
    """Extract clean text snippets around keyword matches"""
    text = clean_html_to_text(html)
    text_lower = text.lower()

    snippets = []
    garbage = ['webkit', 'keyframes', 'function(', 'window.', 'document.',
               'var(--', 'rgba(', '===', 'return ', 'const ', 'null,']

    for kw in keywords:
        kw_lower = kw.lower()
        start = 0
        while len(snippets) < max_snippets:
            pos = text_lower.find(kw_lower, start)
            if pos == -1:
                break

            snippet_start = max(0, pos - context_chars)
            snippet_end = min(len(text), pos + len(kw) + context_chars)
            snippet = text[snippet_start:snippet_end].strip()

            # Skip garbage
            if any(x in snippet.lower() for x in garbage):
                start = pos + len(kw)
                continue

            # Skip high special-char ratio
            special_ratio = sum(1 for c in snippet if c in '{}[]()=;:,\\') / max(len(snippet), 1)
            if special_ratio > 0.1:
                start = pos + len(kw)
                continue

            if snippet_start > 0:
                snippet = '...' + snippet
            if snippet_end < len(text):
                snippet = snippet + '...'

            if snippet not in snippets and len(snippet) > 40:
                snippets.append(snippet)

            start = pos + len(kw)

        if len(snippets) >= max_snippets:
            break

    return snippets


def extract_title(html: str) -> Optional[str]:
    """Extract page title from HTML"""
    # Try og:title first
    og_match = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og_match:
        return unescape(og_match.group(1))

    # Try <title> tag
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        return unescape(title_match.group(1)).strip()

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC BANG SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

async def check_bang(
    session: aiohttp.ClientSession,
    name: str,
    url_template: str,
    query: str,
    keywords: List[str],
    timeout: float,
    source_type: str,
) -> Optional[Dict[str, Any]]:
    """Check a single bang source for keyword matches"""
    url = url_template.replace('{q}', quote_plus(query))
    domain = urlparse(url).netloc.replace('www.', '')

    try:
        start_time = time.time()
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True
        ) as resp:
            if resp.status not in [200, 301, 302]:
                return None

            chunk = await resp.content.read(100000)  # 100KB
            html = chunk.decode('utf-8', errors='ignore')
            elapsed_ms = int((time.time() - start_time) * 1000)

            # Check for keyword matches
            html_lower = html.lower()
            matches = [kw for kw in keywords if kw.lower() in html_lower]

            if not matches:
                return None

            # Extract metadata
            title = extract_title(html) or f"{name} - {query}"
            snippets = extract_snippets(html, keywords)

            return {
                'bang': name,
                'url': url,
                'domain': domain,
                'title': title,
                'source_type': source_type,  # 'news' or 'social'
                'matched_keywords': matches,
                'snippets': snippets,
                'size_bytes': len(chunk),
                'response_ms': elapsed_ms,
                'fetched_at': datetime.utcnow().isoformat(),
            }

    except Exception as e:
        return None


async def scan_bangs(
    query: str,
    bangs: Dict[str, str],
    source_type: str,
    timeout: float = 4.0,
    max_concurrent: int = 50,
) -> List[Dict[str, Any]]:
    """Scan a set of bangs in parallel"""

    # Build keyword list - exact phrase
    clean = query.replace('"', '').replace("'", '')
    keywords = [clean]

    connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=3)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = [
            check_bang(session, name, url_template, query, keywords, timeout, source_type)
            for name, url_template in bangs.items()
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN AUTO-BANG SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_bang_search(
    query: str,
    query_id: Optional[str] = None,
    include_news: bool = True,
    include_social: bool = True,
    timeout: float = 4.0,
    on_result: Optional[Callable[[Dict], None]] = None,
) -> Dict[str, Any]:
    """
    Automatically run news + social bang searches for exact phrase queries.

    Args:
        query: The search query (exact phrase)
        query_id: Optional query ID for persistence
        include_news: Whether to include news bangs
        include_social: Whether to include social bangs
        timeout: Request timeout per source
        on_result: Optional callback for streaming results

    Returns:
        Dict with 'news' and 'social' result lists plus metadata
    """
    start_time = time.time()

    results = {
        'query': query,
        'query_id': query_id or hashlib.md5(query.encode()).hexdigest()[:12],
        'timestamp': datetime.utcnow().isoformat(),
        'news': [],
        'social': [],
        'total_sources': 0,
        'total_matches': 0,
        'elapsed_seconds': 0,
    }

    tasks = []

    if include_news:
        tasks.append(('news', scan_bangs(query, NEWS_BANGS, 'news', timeout)))

    if include_social:
        tasks.append(('social', scan_bangs(query, SOCIAL_BANGS, 'social', timeout)))

    # Run both in parallel
    if tasks:
        gathered = await asyncio.gather(*[t[1] for t in tasks])
        for i, (source_type, _) in enumerate(tasks):
            results[source_type] = gathered[i]
            results['total_matches'] += len(gathered[i])

            # Call streaming callback if provided
            if on_result:
                for r in gathered[i]:
                    on_result(r)

    results['total_sources'] = (len(NEWS_BANGS) if include_news else 0) + (len(SOCIAL_BANGS) if include_social else 0)
    results['elapsed_seconds'] = round(time.time() - start_time, 2)

    return results


def normalize_bang_result_to_search_result(bang_result: Dict[str, Any], query: str) -> Dict[str, Any]:
    """
    Convert a bang result to the standard search result format for grid display.
    """
    return {
        'url': bang_result['url'],
        'title': bang_result.get('title', bang_result['domain']),
        'snippet': bang_result['snippets'][0] if bang_result.get('snippets') else '',
        'snippets': bang_result.get('snippets', []),
        'domain': bang_result['domain'],
        'source': f"bang:{bang_result['bang']}",
        'engine': bang_result['bang'],
        'category': 'news' if bang_result['source_type'] == 'news' else 'social',
        'bang_source_type': bang_result['source_type'],
        'matched_keywords': bang_result.get('matched_keywords', []),
        'fetched_at': bang_result.get('fetched_at'),
        'response_ms': bang_result.get('response_ms'),
        # Mark for LinkLater priority processing
        'needs_scrape': True,
        'scrape_priority': 'high',
    }


def get_urls_for_linklater(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract URLs from bang results for LinkLater priority queue.
    Returns list of {url, priority, source_type, bang} for queue insertion.
    """
    urls = []

    for source_type in ['news', 'social']:
        for r in results.get(source_type, []):
            urls.append({
                'url': r['url'],
                'priority': 'high',
                'source_type': source_type,
                'bang': r['bang'],
                'domain': r['domain'],
                'query': results.get('query', ''),
                'query_id': results.get('query_id', ''),
            })

    return urls


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Auto Bang Search - News + Social')
    parser.add_argument('query', help='Search query (exact phrase)')
    parser.add_argument('--no-news', action='store_true', help='Skip news bangs')
    parser.add_argument('--no-social', action='store_true', help='Skip social bangs')
    parser.add_argument('--timeout', '-t', type=float, default=4.0, help='Timeout per source')
    parser.add_argument('--json', '-j', help='Save results to JSON file')
    args = parser.parse_args()

    print(f"\n🔍 AUTO BANG SEARCH: \"{args.query}\"")
    print(f"   News: {'✓' if not args.no_news else '✗'} ({len(NEWS_BANGS)} sources)")
    print(f"   Social: {'✓' if not args.no_social else '✗'} ({len(SOCIAL_BANGS)} sources)")
    print()

    results = asyncio.run(auto_bang_search(
        args.query,
        include_news=not args.no_news,
        include_social=not args.no_social,
        timeout=args.timeout,
    ))

    print(f"⚡ Completed in {results['elapsed_seconds']}s")
    print(f"✅ {results['total_matches']} matches from {results['total_sources']} sources\n")

    # Display results
    for source_type in ['news', 'social']:
        items = results.get(source_type, [])
        if items:
            emoji = '📰' if source_type == 'news' else '📱'
            print(f"{emoji} {source_type.upper()} ({len(items)} matches):")
            for r in items[:10]:  # Show top 10
                print(f"   {r['bang']:18} → {r['domain']} ({r['response_ms']}ms)")
                for snippet in r['snippets'][:1]:
                    print(f"      💬 {snippet[:120]}...")
            if len(items) > 10:
                print(f"   ... and {len(items) - 10} more")
            print()

    # Save JSON
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"💾 Saved to {args.json}")

    # Show LinkLater URLs
    linklater_urls = get_urls_for_linklater(results)
    print(f"\n📋 {len(linklater_urls)} URLs ready for LinkLater priority queue")

    return results


if __name__ == '__main__':
    main()
