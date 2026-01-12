#!/usr/bin/env python3
"""
JESTER CRAWLER + PACMAN - Full domain crawling with entity extraction

Unlike jester_tiered_pacman.py (which scrapes individual URLs), this CRAWLS domains:
1. Start with seed URLs (homepages)
2. Extract internal_links from each page (via colly/rod)
3. Queue and crawl new URLs up to depth/limit
4. Extract entities with PACMAN on all pages

Usage:
    python3 jester_crawler_pacman.py seeds.txt --max-pages 100 --max-depth 3
    python3 jester_crawler_pacman.py seeds.txt --crawl-all  # No limits (dangerous!)
"""

import asyncio
import json
import sys
import re
import time
import argparse
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from collections import deque

import httpx
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

# === PACMAN: names-dataset for person extraction ===
try:
    from names_dataset import NameDataset
    _nd = NameDataset()
    HAS_NAMES = True
    print("[PACMAN] names-dataset loaded (730k+ first names)", file=sys.stderr)
except ImportError:
    _nd = None
    HAS_NAMES = False
    print("[PACMAN] names-dataset not available", file=sys.stderr)

# === CONFIG ===
COLLY_BIN = Path("/data/submarine/bin/colly_crawler_linux")
ROD_BIN = Path("/data/submarine/bin/rod_crawler_linux")

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-crawl"

CONCURRENT_A = 200  # Lower for crawling (more URLs queued)
CONCURRENT_B = 50
CONCURRENT_C = 25

# === PACMAN FAST PATTERNS ===
FAST_PATTERNS = {
    'LEI': re.compile(r'\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b'),
    'UK_CRN': re.compile(r'\b(?:CRN|Company\s*(?:No|Number|Reg))[:\s]*([A-Z]{0,2}\d{6,8})\b', re.I),
    'IBAN': re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b'),
    'BTC': re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b'),
    'ETH': re.compile(r'\b(0x[a-fA-F0-9]{40})\b'),
    'IMO': re.compile(r'\bIMO[:\s]*(\d{7})\b', re.I),
    'EMAIL': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.I),
    'PHONE': re.compile(r'(?:\+|00)[\d\s\-\(\)]{10,20}'),
}

NAME_PATTERN = re.compile(
    r'\b([A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+(?:\s+[A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+){1,2})\b'
)

NAME_EXCLUSIONS = {
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december',
    'american', 'british', 'german', 'french', 'italian', 'spanish', 'russian',
    'company', 'limited', 'incorporated', 'corporation', 'association',
    'terms', 'conditions', 'privacy', 'policy', 'copyright', 'reserved',
    'contact', 'about', 'services', 'products', 'home', 'news', 'blog',
    'read', 'more', 'learn', 'click', 'here', 'view', 'see', 'get', 'find'
}

COMPANY_SUFFIXES = {
    'Ltd', 'LLC', 'Inc', 'Corp', 'GmbH', 'AG', 'SA', 'BV', 'Kft', 'NV', 'PLC',
    'Limited', 'Incorporated', 'Corporation', 'Company', 'Co', 'LLP', 'LP'
}

COMPANY_PATTERN = re.compile(
    rf'\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({"|".join(COMPANY_SUFFIXES)})\b'
)

# === URL Filtering ===
SKIP_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js',
                   '.zip', '.tar', '.gz', '.mp4', '.mp3', '.avi', '.mov'}
SKIP_PATHS = {'wp-content', 'wp-includes', 'cdn-cgi', 'static', 'assets'}


def extract_persons(text: str) -> List[str]:
    """Extract person names using names-dataset + pattern."""
    if not HAS_NAMES or not text:
        return []

    results = []
    for match in NAME_PATTERN.finditer(text[:50000]):
        candidate = match.group(1)
        words = candidate.split()
        if any(w.lower() in NAME_EXCLUSIONS for w in words):
            continue
        if len(words) < 2:
            continue

        result = _nd.search(words[0])
        if result and result.get('first_name'):
            results.append(candidate)

    return list(set(results))[:20]


def extract_companies(text: str) -> List[str]:
    """Extract company names (name + designation)."""
    if not text:
        return []

    results = []
    for match in COMPANY_PATTERN.finditer(text[:50000]):
        company = (match.group(1).strip() + ' ' + match.group(2)).strip()
        if len(company) > 3:
            results.append(company)

    return list(set(results))[:20]


def extract_fast(content: str) -> Dict[str, List[str]]:
    """Fast PACMAN extraction - runs inline."""
    if not content:
        return {}

    entities = {}
    for name, pattern in FAST_PATTERNS.items():
        matches = pattern.findall(content[:100000])
        if matches:
            entities[name] = list(set(matches))[:20]

    persons = extract_persons(content)
    if persons:
        entities['PERSON'] = persons

    companies = extract_companies(content)
    if companies:
        entities['COMPANY'] = companies

    return entities


def should_crawl_url(url: str, base_domain: str) -> bool:
    """Filter URLs worth crawling."""
    try:
        parsed = urlparse(url)

        # Must be same domain
        url_domain = parsed.netloc.lower().replace('www.', '')
        if url_domain != base_domain:
            return False

        # Skip unwanted extensions
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False

        # Skip unwanted paths
        if any(skip in path for skip in SKIP_PATHS):
            return False

        # Skip anchors and queries that are typically not content
        if '#' in url and parsed.fragment:
            return False

        return True
    except:
        return False


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    try:
        parsed = urlparse(url)
        # Remove trailing slash, fragment, and common query params
        path = parsed.path.rstrip('/')
        if not path:
            path = '/'
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    except:
        return url


class DomainCrawler:
    """Crawls a single domain with tiered scraping."""

    def __init__(self, seed_url: str, max_pages: int = 100, max_depth: int = 3):
        self.seed_url = seed_url
        parsed = urlparse(seed_url)
        self.base_domain = parsed.netloc.lower().replace('www.', '')
        self.max_pages = max_pages
        self.max_depth = max_depth

        # URL tracking
        self.seen_urls: Set[str] = set()
        self.queue: deque = deque()  # (url, depth)
        self.results: List[dict] = []

        # Stats
        self.stats = {'a': 0, 'b': 0, 'c': 0, 'failed': 0}

    def add_url(self, url: str, depth: int):
        """Add URL to queue if not seen and within limits."""
        normalized = normalize_url(url)
        if normalized in self.seen_urls:
            return
        if len(self.seen_urls) >= self.max_pages:
            return
        if depth > self.max_depth:
            return
        if not should_crawl_url(url, self.base_domain):
            return

        self.seen_urls.add(normalized)
        self.queue.append((url, depth))

    async def scrape_tier_a(self, client: httpx.AsyncClient, url: str) -> Optional[dict]:
        """Tier A: httpx GET."""
        try:
            start = time.time()
            r = await client.get(url)
            latency = int((time.time() - start) * 1000)

            if r.status_code == 200 and len(r.text) > 100:
                self.stats['a'] += 1
                return {
                    'url': str(r.url),
                    'input_url': url,
                    'source': 'crawler_a',
                    'status': r.status_code,
                    'content': r.text,
                    'content_length': len(r.text),
                    'latency_ms': latency,
                    'internal_links': [],  # httpx doesn't extract links, but B/C do
                }
        except:
            pass
        return None

    async def scrape_tier_b(self, url: str) -> Optional[dict]:
        """Tier B: colly (with link extraction!)."""
        if not COLLY_BIN.exists():
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                str(COLLY_BIN), "test", url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)

            # Skip debug lines (🔍 Testing...) and find JSON
            output = stdout.decode()
            # Find the JSON object - it starts with { and spans multiple lines
            json_start = output.find('{')
            if json_start >= 0:
                json_str = output[json_start:]
                data = json.loads(json_str)
                if data.get('status_code') == 200 and data.get('content'):
                    self.stats['b'] += 1
                    return {
                        'url': data.get('url', url),
                        'input_url': url,
                        'source': 'crawler_b',
                        'status': 200,
                        'content': data['content'],
                        'content_length': len(data['content']),
                        'latency_ms': data.get('latency_ms', 0),
                        'internal_links': data.get('internal_links', []),
                        'outlinks': data.get('outlinks', []),
                    }
        except Exception as e:
            pass
        return None

    async def scrape_tier_c(self, url: str) -> Optional[dict]:
        """Tier C: rod (JS rendering with link extraction!)."""
        if not ROD_BIN.exists():
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                str(ROD_BIN), "test", url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=45)

            # Find JSON in output (may have debug lines before it)
            output = stdout.decode()
            json_start = output.find('{')
            if json_start >= 0:
                json_str = output[json_start:]
                data = json.loads(json_str)
                content = data.get('content') or data.get('html', '')
                if content:
                    self.stats['c'] += 1
                    return {
                        'url': data.get('url', url),
                        'input_url': url,
                        'source': 'crawler_c',
                        'status': 200,
                        'content': content,
                        'content_length': len(content),
                        'latency_ms': data.get('latency_ms', 0),
                        'internal_links': data.get('internal_links', []),
                        'outlinks': data.get('outlinks', []),
                    }
        except:
            pass
        return None

    async def scrape_url(self, client: httpx.AsyncClient, url: str, depth: int) -> Optional[dict]:
        """Scrape URL with B→A→C fallback (B first for link extraction!)."""
        result = None

        # For crawling, prefer colly (Tier B) FIRST - it extracts internal_links!
        if depth < self.max_depth:
            result = await self.scrape_tier_b(url)

        # Fallback to httpx (Tier A) if colly fails or at max depth
        if not result:
            result = await self.scrape_tier_a(client, url)
            # Try colly anyway to get links if A succeeded
            if result and depth < self.max_depth:
                result_b = await self.scrape_tier_b(url)
                if result_b and result_b.get('internal_links'):
                    result['internal_links'] = result_b['internal_links']
                    result['outlinks'] = result_b.get('outlinks', [])

        # If both fail, try C (JS rendering)
        if not result:
            result = await self.scrape_tier_c(url)

        if not result:
            self.stats['failed'] += 1
            return None

        result['depth'] = depth
        result['domain'] = self.base_domain

        # Extract entities with PACMAN
        result['entities'] = extract_fast(result.get('content', ''))

        return result

    async def crawl(self) -> List[dict]:
        """Main crawl loop."""
        # Start with seed URL
        self.add_url(self.seed_url, 0)

        limits = httpx.Limits(max_connections=CONCURRENT_A, max_keepalive_connections=50)
        async with httpx.AsyncClient(
            timeout=15, limits=limits, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JESTER-Crawler/1.0)"}
        ) as client:

            sem = asyncio.Semaphore(CONCURRENT_A)

            while self.queue:
                # Process in batches
                batch = []
                while self.queue and len(batch) < 50:
                    batch.append(self.queue.popleft())

                async def process_one(url_depth):
                    url, depth = url_depth
                    async with sem:
                        return await self.scrape_url(client, url, depth)

                results = await asyncio.gather(*[process_one(ud) for ud in batch], return_exceptions=True)

                for r in results:
                    if isinstance(r, dict) and r:
                        self.results.append(r)

                        # Queue internal links for crawling
                        current_depth = r.get('depth', 0)
                        for link in r.get('internal_links', []):
                            self.add_url(link, current_depth + 1)

                        # Output progress
                        entities = r.get('entities', {})
                        entity_counts = {k: len(v) for k, v in entities.items() if v}
                        print(json.dumps({
                            'url': r['url'],
                            'depth': current_depth,
                            'source': r['source'],
                            'len': r['content_length'],
                            'internal_links': len(r.get('internal_links', [])),
                            'entities': entity_counts
                        }), flush=True)

                # Progress to stderr
                print(f"[CRAWL] {self.base_domain}: {len(self.results)}/{len(self.seen_urls)} pages | "
                      f"Queue: {len(self.queue)} | A:{self.stats['a']} B:{self.stats['b']} C:{self.stats['c']}",
                      file=sys.stderr, end='\r')

        print(file=sys.stderr)  # Newline after progress
        return self.results


async def index_results(es: AsyncElasticsearch, results: List[dict], index: str):
    """Bulk index results to Elasticsearch."""
    if not results:
        return 0

    actions = []
    for r in results:
        doc_id = f"crawl_{r['domain']}_{urlparse(r['url']).path.replace('/', '_')[:100]}"
        actions.append({
            "_index": index,
            "_id": doc_id,
            "_source": {
                "domain": r.get('domain', ''),
                "url": r.get('url', ''),
                "input_url": r.get('input_url', ''),
                "source": r.get('source', ''),
                "depth": r.get('depth', 0),
                "status": r.get('status', 0),
                "content": r.get('content', '')[:50000],
                "content_length": r.get('content_length', 0),
                "latency_ms": r.get('latency_ms', 0),
                "internal_links_count": len(r.get('internal_links', [])),
                "outlinks_count": len(r.get('outlinks', [])),
                "entities": r.get('entities', {}),
                "crawled_at": datetime.utcnow().isoformat()
            }
        })

    try:
        success, failed = await async_bulk(es, actions, raise_on_error=False, stats_only=True)
        return success
    except Exception as e:
        print(f"[ES] Bulk error: {e}", file=sys.stderr)
        return 0


async def main():
    parser = argparse.ArgumentParser(description='JESTER Crawler + PACMAN')
    parser.add_argument('input_file', help='File with seed URLs (one per line)')
    parser.add_argument('--max-pages', type=int, default=100, help='Max pages per domain (default: 100)')
    parser.add_argument('--max-depth', type=int, default=3, help='Max crawl depth (default: 3)')
    parser.add_argument('--es-index', default=ES_INDEX, help=f'Elasticsearch index (default: {ES_INDEX})')
    parser.add_argument('--no-index', action='store_true', help='Skip Elasticsearch indexing')
    args = parser.parse_args()

    start_time = time.time()

    # Read seed URLs
    with open(args.input_file) as f:
        seeds = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]

    print(f"[CRAWLER] {len(seeds)} seed URLs, max {args.max_pages} pages/domain, depth {args.max_depth}",
          file=sys.stderr)

    # Init ES
    es = None
    if not args.no_index:
        es = AsyncElasticsearch([ES_HOST])
        if not await es.indices.exists(index=args.es_index):
            await es.indices.create(index=args.es_index, body={
                "settings": {"number_of_shards": 3, "number_of_replicas": 0},
                "mappings": {
                    "properties": {
                        "domain": {"type": "keyword"},
                        "url": {"type": "keyword"},
                        "source": {"type": "keyword"},
                        "depth": {"type": "integer"},
                        "status": {"type": "integer"},
                        "content": {"type": "text"},
                        "content_length": {"type": "integer"},
                        "internal_links_count": {"type": "integer"},
                        "outlinks_count": {"type": "integer"},
                        "entities": {"type": "object"},
                        "crawled_at": {"type": "date"}
                    }
                }
            })

    # Crawl each domain
    total_pages = 0
    total_indexed = 0

    for i, seed in enumerate(seeds):
        print(f"\n[{i+1}/{len(seeds)}] Crawling {seed}...", file=sys.stderr)

        crawler = DomainCrawler(seed, max_pages=args.max_pages, max_depth=args.max_depth)
        results = await crawler.crawl()
        total_pages += len(results)

        # Index results
        if es and results:
            indexed = await index_results(es, results, args.es_index)
            total_indexed += indexed
            print(f"[ES] Indexed {indexed}/{len(results)} pages from {crawler.base_domain}", file=sys.stderr)

    if es:
        await es.close()

    elapsed = time.time() - start_time
    print(f"\n[DONE] Crawled {total_pages} pages from {len(seeds)} domains in {elapsed/60:.1f}m", file=sys.stderr)
    print(f"[ES] Total indexed: {total_indexed}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
