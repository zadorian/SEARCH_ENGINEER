#!/usr/bin/env python3
"""
JESTER TIERED - Maximum parallel scraping with A→B→C + ES indexing
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

import httpx
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

COLLY_BIN = Path("/data/SUBMARINE/bin/colly_crawler_linux")
ROD_BIN = Path("/data/SUBMARINE/bin/rod_crawler_linux")

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-linkedin"

CONCURRENT_A = 500
CONCURRENT_B = 100
CONCURRENT_C = 50
BATCH_SIZE = 10000
ES_BULK_SIZE = 500

stats = {"a_success": 0, "a_fail": 0, "b_success": 0, "b_fail": 0, "c_success": 0, "c_fail": 0, "indexed": 0, "total": 0}

# ES client
es_client = None

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
        actions.append({
            "_index": ES_INDEX,
            "_id": f"jester_{domain}",
            "_source": {
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
        })
    
    try:
        success, failed = await async_bulk(es_client, actions, raise_on_error=False, stats_only=True)
        stats["indexed"] += success
        if failed:
            print(f"[ES] {failed} failed to index", file=sys.stderr)
    except Exception as e:
        print(f"[ES] Bulk error: {e}", file=sys.stderr)

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
                        return {"url": str(r.url), "input_url": url, "source": "jester_a",
                                "status": r.status_code, "content": r.text, 
                                "content_length": len(r.text), "latency_ms": latency}
                except:
                    pass
                stats["a_fail"] += 1
                return None
        
        results = await asyncio.gather(*[fetch(u) for u in urls], return_exceptions=True)
        
        for i, r in enumerate(results):
            if isinstance(r, dict) and r:
                successes.append(r)
                print(json.dumps({"url": r["url"], "source": r["source"], "len": r["content_length"]}), flush=True)
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
                            return {"url": data.get("url", url), "input_url": url, "source": "jester_b",
                                    "status": 200, "content": data["content"],
                                    "content_length": len(data["content"]), "latency_ms": data.get("latency_ms", 0)}
                    except: pass
            except: pass
            stats["b_fail"] += 1
            return None
    
    results = await asyncio.gather(*[crawl_one(u) for u in urls], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, dict) and r:
            successes.append(r)
            print(json.dumps({"url": r["url"], "source": r["source"], "len": r["content_length"]}), flush=True)
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
                            return {"url": data.get("url", url), "input_url": url, "source": "jester_c",
                                    "status": 200, "content": content,
                                    "content_length": len(content), "latency_ms": data.get("latency_ms", 0)}
                    except: pass
            except: pass
            stats["c_fail"] += 1
            return None
    
    results = await asyncio.gather(*[crawl_one(u) for u in urls], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, dict) and r:
            successes.append(r)
            print(json.dumps({"url": r["url"], "source": r["source"], "len": r["content_length"]}), flush=True)
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
    
    print(f"[JESTER] Reading {input_file}...", file=sys.stderr)
    
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
        print(f"[PROGRESS] {done}/{len(urls)} ({done*100/len(urls):.1f}%) | {rate:.0f}/s | ETA: {eta/60:.0f}m | A:{stats['a_success']} B:{stats['b_success']} C:{stats['c_success']} | ES:{stats['indexed']}", file=sys.stderr)
    
    await es_client.close()
    
    elapsed = time.time() - start
    total_success = stats["a_success"] + stats["b_success"] + stats["c_success"]
    print(f"\n[DONE] {total_success}/{stats['total']} scraped, {stats['indexed']} indexed in {elapsed/60:.1f}m ({stats['total']/elapsed:.0f}/s)", file=sys.stderr)
    print(f"  A: {stats['a_success']} | B: {stats['b_success']} | C: {stats['c_success']} | Failed: {total_failed}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: jester_tiered.py urls.txt", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
