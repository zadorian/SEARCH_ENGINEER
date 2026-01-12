#!/usr/bin/env python3
"""
JESTER TIERED + PACMAN - Maximum parallel scraping with extraction
"""

import asyncio
import json
import sys
import re
import time
import argparse
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, List, Set

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
COLLY_BIN = Path("/data/SUBMARINE/bin/colly_crawler_linux")
ROD_BIN = Path("/data/SUBMARINE/bin/rod_crawler_linux")

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-linkedin"

CONCURRENT_A = 500
CONCURRENT_B = 100
CONCURRENT_C = 50
BATCH_SIZE = 10000
ES_BULK_SIZE = 500

# === PACMAN FAST PATTERNS (compiled once) ===
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

# Person name pattern (Unicode-aware)
NAME_PATTERN = re.compile(
    r'\b([A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+(?:\s+[A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+){1,2})\b',
    re.UNICODE
)

# Words that are NOT person names
NAME_EXCLUSIONS: Set[str] = {
    'the', 'this', 'that', 'these', 'those', 'monday', 'tuesday', 'wednesday',
    'thursday', 'friday', 'saturday', 'sunday', 'january', 'february', 'march',
    'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november',
    'december', 'american', 'british', 'german', 'french', 'spanish', 'italian',
    'russian', 'chinese', 'japanese', 'korean', 'indian', 'brazilian', 'mexican',
    'canadian', 'australian', 'dutch', 'polish', 'hungarian', 'czech', 'swedish',
    'norwegian', 'danish', 'finnish', 'turkish', 'greek', 'portuguese', 'belgian',
    'swiss', 'austrian', 'european', 'asian', 'african', 'international', 'global',
    'national', 'regional', 'local', 'general', 'special', 'senior', 'junior',
    'managing', 'executive', 'financial', 'technical', 'annual', 'quarterly',
    'case', 'docket', 'file', 'claim', 'appeal', 'court', 'tribunal', 'matter',
    'company', 'corporation', 'limited', 'incorporated', 'holding', 'group',
    'total', 'amount', 'value', 'payment', 'pursuant', 'subject', 'exhibit',
    'dear', 'please', 'thank', 'thanks', 'sincerely', 'regards', 'best',
    'news', 'home', 'about', 'contact', 'services', 'products', 'privacy', 'terms',
    'click', 'read', 'more', 'learn', 'view', 'download', 'subscribe', 'share',
}

# Company legal suffixes
COMPANY_SUFFIXES: Set[str] = {
    'ltd', 'llc', 'inc', 'corp', 'plc', 'gmbh', 'ag', 'kg', 'ohg', 'ug',
    'sa', 'sas', 'sarl', 'srl', 'sl', 'bv', 'nv', 'ab', 'as', 'oy', 'oyj',
    'sp', 'kft', 'zrt', 'nyrt', 'bt', 'doo', 'dd', 'ad', 'ood', 'eood',
    'jsc', 'pjsc', 'ojsc', 'co', 'limited', 'corporation', 'incorporated',
}

# Build company pattern
_suffix_pattern = '|'.join(re.escape(s) for s in COMPANY_SUFFIXES)
COMPANY_PATTERN = re.compile(
    rf'\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({_suffix_pattern})\b',
    re.I
)

# URL classification
CORPORATE_KEYWORDS = {'annual-report', '10-k', '10k', 'prospectus', 'proxy', 'filing',
                      'investor', 'financial', 'quarterly', 'earnings', 'disclosure'}
REGISTRY_DOMAINS = {'sec.gov', 'companieshouse.gov.uk', 'e-cegjegyzek.hu', 'handelsregister.de',
                    'infogreffe.fr', 'opencorporates.com', 'proff.no', 'proff.se'}
FREE_HOSTING = {'blogspot.com', 'wordpress.com', 'medium.com', 'wix.com', 'weebly.com',
                'tumblr.com', 'github.io', 'netlify.app', 'vercel.app'}

# === STATS ===
stats = {"a_success": 0, "a_fail": 0, "b_success": 0, "b_fail": 0,
         "c_success": 0, "c_fail": 0, "indexed": 0, "total": 0,
         "entities_extracted": 0}

# ES client
es_client = None

# CLI args
args = None


def extract_persons(text: str) -> List[str]:
    """Extract person names using names-dataset + pattern."""
    if not HAS_NAMES or not text:
        return []

    results = []
    seen = set()

    for match in NAME_PATTERN.finditer(text):
        candidate = match.group(1)
        words = candidate.split()

        # Skip if any word is in exclusions
        if any(w.lower() in NAME_EXCLUSIONS for w in words):
            continue

        # First word must be a known first name (O(1) lookup)
        result = _nd.search(words[0])
        if result and result.get('first_name'):
            if candidate.lower() not in seen:
                seen.add(candidate.lower())
                results.append(candidate)
                if len(results) >= 20:  # Limit
                    break

    return results


def extract_companies(text: str) -> List[str]:
    """Extract company names (name + designation)."""
    if not text:
        return []

    results = []
    seen = set()

    for match in COMPANY_PATTERN.finditer(text):
        company_name = match.group(1).strip()
        designation = match.group(2)
        full_name = f"{company_name} {designation}"

        if len(company_name) < 2 or full_name.lower() in seen:
            continue
        seen.add(full_name.lower())
        results.append(full_name)
        if len(results) >= 20:  # Limit
            break

    return results


def extract_fast(content: str) -> Dict[str, List[str]]:
    """Fast PACMAN extraction - runs inline."""
    if not content:
        return {}

    entities = {}

    # Regex patterns
    for name, pattern in FAST_PATTERNS.items():
        matches = pattern.findall(content)
        if matches:
            # Dedupe and limit
            unique = list(set(matches))[:10]
            if unique:
                entities[name] = unique

    # Person names (needs names-dataset)
    persons = extract_persons(content)
    if persons:
        entities['PERSON'] = persons

    # Company names
    companies = extract_companies(content)
    if companies:
        entities['COMPANY'] = companies

    return entities


def classify_url(url: str, domain: str) -> int:
    """Fast tier classification based on URL/domain."""
    url_lower = url.lower()
    domain_lower = domain.lower()

    # Tier 1: Corporate/registry
    if any(kw in url_lower for kw in CORPORATE_KEYWORDS):
        return 1
    if any(domain_lower.endswith(rd) for rd in REGISTRY_DOMAINS):
        return 1

    # Tier 3: Free hosting
    if any(domain_lower.endswith(fh) for fh in FREE_HOSTING):
        return 3

    # Default: Tier 2
    return 2


async def init_es():
    global es_client
    es_client = AsyncElasticsearch([ES_HOST])

    # Create index if not exists
    if not await es_client.indices.exists(index=ES_INDEX):
        await es_client.indices.create(index=ES_INDEX, body={
            "settings": {"number_of_shards": 3, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "domain": {"type": "keyword"},
                    "url": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "status": {"type": "integer"},
                    "content": {"type": "text"},
                    "content_length": {"type": "integer"},
                    "latency_ms": {"type": "integer"},
                    "tier": {"type": "integer"},
                    "entities": {"type": "object", "enabled": True},
                    "indexed_at": {"type": "date"}
                }
            }
        })
        print(f"[ES] Created index {ES_INDEX}", file=sys.stderr)


async def index_results(results: list):
    """Bulk index results to ES."""
    if not results:
        return

    actions = []
    for r in results:
        domain = urlparse(r.get("url", r.get("input_url", ""))).netloc
        doc = {
            "domain": domain,
            "url": r.get("url", ""),
            "input_url": r.get("input_url", ""),
            "source": r.get("source", ""),
            "status": r.get("status", 0),
            "content": r.get("content", "")[:50000] if r.get("content") else "",
            "content_length": r.get("content_length", 0),
            "latency_ms": r.get("latency_ms", 0),
            "indexed_at": datetime.utcnow().isoformat()
        }

        # Add entities if extraction is enabled
        if not args.no_extract and r.get("entities"):
            doc["entities"] = r["entities"]
            doc["tier"] = r.get("tier", 2)

        actions.append({
            "_index": ES_INDEX,
            "_id": f"jester_{domain}",
            "_source": doc
        })

    try:
        success, failed = await async_bulk(es_client, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        if failed:
            print(f"[ES] {failed} failed to index", file=sys.stderr)
    except Exception as e:
        print(f"[ES] Bulk error: {e}", file=sys.stderr)


def process_result(result: dict, url: str) -> dict:
    """Add PACMAN extraction to scrape result."""
    if args.no_extract or not result.get("content"):
        return result

    # Extract entities
    entities = extract_fast(result["content"])
    if entities:
        result["entities"] = entities
        stats["entities_extracted"] += 1

    # Classify URL
    domain = urlparse(result.get("url", url)).netloc
    result["tier"] = classify_url(result.get("url", url), domain)

    return result


async def tier_a_batch(urls: list) -> tuple[list, list]:
    """TIER A: httpx"""
    successes = []
    failed = []

    limits = httpx.Limits(max_connections=CONCURRENT_A, max_keepalive_connections=200)
    async with httpx.AsyncClient(timeout=10, limits=limits, follow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; JESTER/1.0)"}) as client:
        sem = asyncio.Semaphore(CONCURRENT_A)

        async def fetch(url):
            async with sem:
                try:
                    start = time.time()
                    r = await client.get(url)
                    latency = int((time.time() - start) * 1000)
                    if r.status_code == 200 and len(r.text) > 50:
                        stats["a_success"] += 1
                        result = {"url": str(r.url), "input_url": url, "source": "jester_a",
                                "status": r.status_code, "content": r.text,
                                "content_length": len(r.text), "latency_ms": latency}
                        return process_result(result, url)
                except:
                    pass
                stats["a_fail"] += 1
                return None

        results = await asyncio.gather(*[fetch(u) for u in urls], return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, dict) and r:
                successes.append(r)
                log = {"url": r["url"], "source": r["source"], "len": r["content_length"]}
                if r.get("entities"):
                    log["entities"] = sum(len(v) for v in r["entities"].values())
                print(json.dumps(log), flush=True)
            else:
                failed.append(urls[i])

    return successes, failed


async def tier_b_batch(urls: list) -> tuple[list, list]:
    """TIER B: colly"""
    if not COLLY_BIN.exists() or not urls:
        return [], urls

    successes = []
    failed = []
    sem = asyncio.Semaphore(CONCURRENT_B)

    async def crawl_one(url):
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(COLLY_BIN), "test", url,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
                for line in stdout.decode().strip().split('\n'):
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        if data.get("status_code") == 200 and data.get("content"):
                            stats["b_success"] += 1
                            result = {"url": data.get("url", url), "input_url": url, "source": "jester_b",
                                    "status": 200, "content": data["content"],
                                    "content_length": len(data["content"]), "latency_ms": data.get("latency_ms", 0)}
                            return process_result(result, url)
                    except: pass
            except: pass
            stats["b_fail"] += 1
            return None

    results = await asyncio.gather(*[crawl_one(u) for u in urls], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, dict) and r:
            successes.append(r)
            log = {"url": r["url"], "source": r["source"], "len": r["content_length"]}
            if r.get("entities"):
                log["entities"] = sum(len(v) for v in r["entities"].values())
            print(json.dumps(log), flush=True)
        else:
            failed.append(urls[i])
    return successes, failed


async def tier_c_batch(urls: list) -> tuple[list, list]:
    """TIER C: rod (JS)"""
    if not ROD_BIN.exists() or not urls:
        return [], urls

    successes = []
    failed = []
    sem = asyncio.Semaphore(CONCURRENT_C)

    async def crawl_one(url):
        async with sem:
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(ROD_BIN), "test", url,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=45)
                for line in stdout.decode().strip().split('\n'):
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        content = data.get("content") or data.get("html", "")
                        if content:
                            stats["c_success"] += 1
                            result = {"url": data.get("url", url), "input_url": url, "source": "jester_c",
                                    "status": 200, "content": content,
                                    "content_length": len(content), "latency_ms": data.get("latency_ms", 0)}
                            return process_result(result, url)
                    except: pass
            except: pass
            stats["c_fail"] += 1
            return None

    results = await asyncio.gather(*[crawl_one(u) for u in urls], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, dict) and r:
            successes.append(r)
            log = {"url": r["url"], "source": r["source"], "len": r["content_length"]}
            if r.get("entities"):
                log["entities"] = sum(len(v) for v in r["entities"].values())
            print(json.dumps(log), flush=True)
        else:
            failed.append(urls[i])
    return successes, failed


async def process_batch(batch_urls: list, batch_num: int, total_batches: int):
    """Process one batch through all tiers + index to ES."""
    print(f"[BATCH {batch_num}/{total_batches}] {len(batch_urls)} URLs", file=sys.stderr)

    all_results = []

    # Tier A
    successes_a, failed_a = await tier_a_batch(batch_urls)
    all_results.extend(successes_a)

    # Tier B (failed from A)
    if failed_a:
        successes_b, failed_b = await tier_b_batch(failed_a)
        all_results.extend(successes_b)
    else:
        failed_b = []

    # Tier C (failed from B)
    if failed_b:
        successes_c, failed_c = await tier_c_batch(failed_b)
        all_results.extend(successes_c)
    else:
        failed_c = []

    # Index ALL results from this batch to ES
    if all_results:
        await index_results(all_results)

    return len(failed_c)


async def main(input_file: str):
    start = time.time()

    # Init ES
    await init_es()

    print(f"[JESTER+PACMAN] Reading {input_file}...", file=sys.stderr)
    print(f"[PACMAN] Extraction: {'DISABLED' if args.no_extract else 'ENABLED'}", file=sys.stderr)

    with open(input_file) as f:
        urls = [line.strip() for line in f if line.strip()]

    stats["total"] = len(urls)
    total_batches = (len(urls) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"[JESTER] {len(urls)} URLs in {total_batches} batches @ {BATCH_SIZE}/batch", file=sys.stderr)
    print(f"[ES] Indexing to {ES_INDEX}", file=sys.stderr)

    total_failed = 0
    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        failed = await process_batch(batch, batch_num, total_batches)
        total_failed += failed

        # Progress
        done = min(i + BATCH_SIZE, len(urls))
        elapsed = time.time() - start
        rate = done / max(elapsed, 0.1)
        eta = (len(urls) - done) / max(rate, 0.1)
        entities_str = f" | Entities:{stats['entities_extracted']}" if not args.no_extract else ""
        print(f"[PROGRESS] {done}/{len(urls)} ({done*100/len(urls):.1f}%) | {rate:.0f}/s | ETA: {eta/60:.0f}m | A:{stats['a_success']} B:{stats['b_success']} C:{stats['c_success']} | ES:{stats['indexed']}{entities_str}", file=sys.stderr)

    await es_client.close()

    elapsed = time.time() - start
    total_success = stats["a_success"] + stats["b_success"] + stats["c_success"]
    print(f"\n[DONE] {total_success}/{stats['total']} scraped, {stats['indexed']} indexed in {elapsed/60:.1f}m ({stats['total']/elapsed:.0f}/s)", file=sys.stderr)
    print(f"  A: {stats['a_success']} | B: {stats['b_success']} | C: {stats['c_success']} | Failed: {total_failed}", file=sys.stderr)
    if not args.no_extract:
        print(f"  Entities extracted: {stats['entities_extracted']} pages", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JESTER TIERED + PACMAN")
    parser.add_argument("input_file", help="File with URLs (one per line)")
    parser.add_argument("--no-extract", action="store_true", help="Disable PACMAN extraction")
    parser.add_argument("--pacman-full", action="store_true", help="Enable full PACMAN (tripwires + domain sets)")
    args = parser.parse_args()

    if args.pacman_full:
        print("[PACMAN] Full mode not yet implemented (tripwires require ~2GB RAM)", file=sys.stderr)

    asyncio.run(main(args.input_file))
