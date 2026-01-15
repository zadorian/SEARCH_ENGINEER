#!/usr/bin/env python3
"""
CATEGORY-SPECIFIC BANGS MODULE
Automatically searches category-specific sources when a dominant category is detected in results.

Categories:
- Crypto (CoinDesk, TheBlock, etc.)
- Tech (TechCrunch, GitHub, etc.)
- Finance (Bloomberg, WSJ, etc.)
- Academic (Arxiv, etc.)
- Legal (Justia, etc.)
- Social (Reddit, Twitter, etc.)
"""

import asyncio
import aiohttp
import time
import os
import json
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus, urlparse
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Load environment for API keys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY BANG DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_BANGS: Dict[str, Dict[str, str]] = {
    'crypto': {
        'coindesk': 'https://www.coindesk.com/search?s={q}',
        'cointelegraph': 'https://cointelegraph.com/search?query={q}',
        'theblock': 'https://www.theblock.co/search?query={q}',
        'decrypt': 'https://decrypt.co/search?q={q}',
        'cryptoslate': 'https://decrypt.co/search?q={q}',
        'blockworks': 'https://www.blockworks.co/search?q={q}',
    },
    'tech': {
        'techcrunch': 'https://techcrunch.com/search/{q}',
        'verge': 'https://www.theverge.com/search?q={q}',
        'wired': 'https://www.wired.com/search/?q={q}',
        'arstechnica': 'https://arstechnica.com/search/?query={q}',
        'engadget': 'https://www.engadget.com/search/?q={q}',
        'venturebeat': 'https://www.venturebeat.com/?s={q}',
        'hackernews': 'https://hn.algolia.com/?q={q}',
        'github': 'https://github.com/search?q={q}&type=repositories',
        'stackoverflow': 'https://stackoverflow.com/search?q={q}',
    },
    'finance': {
        'bloomberg': 'https://www.bloomberg.com/search?query={q}',
        'wsj': 'https://www.wsj.com/search?query={q}',
        'ft': 'https://www.ft.com/search?q={q}',
        'cnbc': 'https://www.cnbc.com/search/?query={q}',
        'forbes': 'https://www.forbes.com/search/?q={q}',
        'businessinsider': 'https://www.businessinsider.com/s?q={q}',
        'marketwatch': 'https://www.marketwatch.com/search?q={q}',
        'yahoo_finance': 'https://finance.yahoo.com/lookup?s={q}',
    },
    'academic': {
        'arxiv': 'https://arxiv.org/search/?query={q}&searchtype=all',
        'google_scholar': 'https://scholar.google.com/scholar?q={q}',
        'semantic_scholar': 'https://www.semanticscholar.org/search?q={q}',
        'researchgate': 'https://www.researchgate.net/search/publication?q={q}',
        'pubmed': 'https://pubmed.ncbi.nlm.nih.gov/?term={q}',
    },
    'legal': {
        'justia': 'https://www.justia.com/search?q={q}',
        'findlaw': 'https://lp.findlaw.com/scripts/search_results.pl?query={q}',
        'cornell_lii': 'https://www.law.cornell.edu/search/results?q={q}',
        'oyez': 'https://www.oyez.org/search/{q}',
    },
    'video': {
        'youtube': 'https://www.youtube.com/results?search_query={q}',
        'vimeo': 'https://vimeo.com/search?q={q}',
        'dailymotion': 'https://www.dailymotion.com/search/{q}',
        'twitch': 'https://www.twitch.tv/search?term={q}',
    },
    'social': {
        'reddit': 'https://www.reddit.com/search/?q={q}',
        'twitter': 'https://twitter.com/search?q={q}&f=live',
        'linkedin': 'https://www.linkedin.com/search/results/all/?keywords={q}',
        'mastodon': 'https://mastodon.social/tags/{q}',
        'bluesky': 'https://bsky.app/search?q={q}',
        'quora': 'https://www.quora.com/search?q={q}',
    },
    'investigative': {
        'bellingcat': 'https://www.bellingcat.com/?s={q}',
        'icij': 'https://www.icij.org/?s={q}',
        'occrp': 'https://www.occrp.org/en/search?q={q}',
        'propublica': 'https://www.propublica.org/search?q={q}',
        'intercept': 'https://www.theintercept.com/search/?q={q}',
    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

async def detect_dominant_category_llm(results: List[Dict[str, Any]]) -> Optional[str]:
    """
    Use LLM to detect category from result titles/urls.
    Strategy: Try Free OpenRouter models first (Gemini -> Llama -> Mistral), fallback to OpenAI.
    """
    # Extract minimal context to save tokens
    samples = [
        f"{r.get('title', '')} ({r.get('url', '')})" 
        for r in results[:15] # Analyze top 15
    ]
    
    categories = list(CATEGORY_BANGS.keys())
    
    prompt = f"""Analyze these search results and determine if they strongly belong to one of these categories: {', '.join(categories)}.
If they strongly match a single category, return ONLY the category name.
If they are mixed or generic, return "none".

Results:
{json.dumps(samples, indent=2)}"""

    # Define candidates in priority order
    candidates = []
    
    if OPENROUTER_API_KEY:
        candidates.append({
            'model': 'google/gemini-2.0-flash-exp:free', # Priority 1: Speed & Quality
            'key': OPENROUTER_API_KEY,
            'url': 'https://openrouter.ai/api/v1/chat/completions'
        })
        candidates.append({
            'model': 'meta-llama/llama-3.3-70b-instruct:free',
            'key': OPENROUTER_API_KEY,
            'url': 'https://openrouter.ai/api/v1/chat/completions'
        })
        candidates.append({
            'model': 'mistralai/mistral-small-24b-instruct-2501:free',
            'key': OPENROUTER_API_KEY,
            'url': 'https://openrouter.ai/api/v1/chat/completions'
        })

    if OPENAI_API_KEY:
        candidates.append({
            'model': 'gpt-5-nano', 
            'key': OPENAI_API_KEY,
            'url': 'https://api.openai.com/v1/chat/completions'
        })

    if not candidates:
        return None

    async with aiohttp.ClientSession() as session:
        for candidate in candidates:
            try:
                async with session.post(
                    candidate['url'],
                    headers={
                        'Authorization': f'Bearer {candidate["key"]}',
                        'Content-Type': 'application/json',
                        'HTTP-Referer': 'https://drill-search.app', 
                        'X-Title': 'Drill Search',
                    },
                    json={
                        'model': candidate['model'],
                        'messages': [{'role': 'user', 'content': prompt}],
                        'max_tokens': 10,
                        'temperature': 0.0,
                    },
                    timeout=aiohttp.ClientTimeout(total=8.0)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip().lower()
                        
                        # Clean up response
                        content = content.replace('category:', '').replace('"', '').strip()
                        
                        if content in CATEGORY_BANGS:
                            return content
                        
                        if content == 'none':
                            return None
                            
                    elif resp.status == 429:
                        # Rate limited, try next candidate silently
                        continue
                    else:
                        continue
                        
            except Exception as e:
                continue

    return None

async def detect_dominant_category(results: List[Dict[str, Any]], min_ratio: float = 0.20) -> Optional[str]:
    """
    Detect if a category dominates the result set.
    Prioritizes LLM analysis, falls back to keyword matching.
    """
    if not results:
        return None

    # 1. Try LLM first (smarter)
    llm_category = await detect_dominant_category_llm(results)
    if llm_category:
        return llm_category

    # 2. Fallback: Keyword counting
    category_counts: Dict[str, int] = {}
    total = len(results)
    
    # Keywords for fallback URL matching
    url_keywords = {
        'crypto': ['coin', 'token', 'btc', 'eth', 'ledger', 'blockchain', 'wallet'],
        'tech': ['github', 'stack', 'code', 'software', 'dev', 'api', 'linux'],
        'finance': ['market', 'stock', 'trade', 'invest', 'bank', 'economy', 'money'],
        'academic': ['edu', 'university', 'journal', 'research', 'science', 'doi', 'pdf'],
        'legal': ['law', 'court', 'attorney', 'legal', 'statute', 'case'],
        'video': ['youtube', 'vimeo', 'watch', 'stream', 'tv'],
    }

    for res in results:
        # Check explicit category field
        cat = res.get('category')
        if cat and cat in CATEGORY_BANGS:
            category_counts[cat] = category_counts.get(cat, 0) + 1
            continue
            
        # Check URL keywords
        url = res.get('url', '').lower()
        for cat_key, keywords in url_keywords.items():
            if any(k in url for k in keywords):
                category_counts[cat_key] = category_counts.get(cat_key, 0) + 1
                break

    # Check thresholds
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        if count / total >= min_ratio:
            return cat
            
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# SEARCH LOGIC (Reusing auto_bang_search components)
# ═══════════════════════════════════════════════════════════════════════════════

# Import utilities from auto_bang_search to avoid code duplication
from .auto_bang_search import clean_html_to_text, extract_snippets, extract_title, check_bang

async def scan_category_bangs(
    query: str,
    category: str,
    timeout: float = 4.0,
    max_concurrent: int = 30,
) -> List[Dict[str, Any]]:
    """Scan category-specific bangs in parallel"""
    bangs = CATEGORY_BANGS.get(category)
    if not bangs:
        return []

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
            check_bang(session, name, url_template, query, keywords, timeout, f'category_{category}')
            for name, url_template in bangs.items()
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]

async def category_burst(
    query: str,
    category: str,
    timeout: float = 4.0,
) -> Dict[str, Any]:
    """
    Run a category burst search.
    """
    start_time = time.time()
    
    results = await scan_category_bangs(query, category, timeout)
    
    return {
        'query': query,
        'category': category,
        'timestamp': datetime.utcnow().isoformat(),
        'results': results,
        'total_matches': len(results),
        'total_sources': len(CATEGORY_BANGS.get(category, {})),
        'elapsed_seconds': round(time.time() - start_time, 2)
    }

def normalize_category_result(result: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Convert category result to standard search result format"""
    return {
        'url': result['url'],
        'title': result.get('title', result['domain']),
        'snippet': result['snippets'][0] if result.get('snippets') else '',
        'snippets': result.get('snippets', []),
        'domain': result['domain'],
        'source': f"category_bang:{result['source_type'].replace('category_', '')}:{result['bang']}",
        'engine': f"BANG_{result['bang'].upper()}",
        'category': result['source_type'].replace('category_', ''),
        'bang_source': result['bang'],
        'matched_keywords': result.get('matched_keywords', []),
        'fetched_at': result.get('fetched_at'),
        'response_ms': result.get('response_ms'),
        'needs_scrape': True,
        'scrape_priority': 'high',
    }

# CLI Test
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Category Bang Search')
    parser.add_argument('query', help='Search query')
    parser.add_argument('category', help='Category (crypto, tech, finance, etc)')
    args = parser.parse_args()
    
    print(f"Searching {args.category} for '{args.query}'...")
    results = asyncio.run(category_burst(args.query, args.category))
    print(f"Found {results['total_matches']} matches in {results['elapsed_seconds']}s")
    for r in results['results']:
        print(f"- {r['bang']}: {r['title']} ({r['url']})")