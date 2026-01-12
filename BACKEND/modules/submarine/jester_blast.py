#!/usr/bin/env python3
"""
JESTER BLAST - Maximum concurrency URL scraper
No tiers, no fallbacks, just speed.

Usage:
    python3 jester_blast.py urls.txt > results.ndjson
    cat urls.txt | python3 jester_blast.py > results.ndjson
    awk '{print "https://"$0}' domains.txt | python3 jester_blast.py > results.ndjson
"""

import asyncio
import httpx
import json
import sys
import time
from urllib.parse import urlparse

CONCURRENT = 500
TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; JESTER/1.0)"

stats = {"total": 0, "success": 0, "failed": 0, "start": 0}

async def scrape(client: httpx.AsyncClient, url: str) -> dict:
    """Scrape single URL, return result dict."""
    try:
        start = time.time()
        r = await client.get(url, follow_redirects=True)
        latency = int((time.time() - start) * 1000)
        
        domain = urlparse(str(r.url)).netloc
        content = r.text
        
        return {
            "url": str(r.url),
            "input_url": url,
            "domain": domain,
            "status": r.status_code,
            "content_length": len(content),
            "latency_ms": latency,
            "content": content
        }
    except Exception as e:
        return {
            "url": url,
            "input_url": url,
            "domain": urlparse(url).netloc,
            "status": 0,
            "error": str(e)[:100]
        }

async def main(urls: list[str]):
    """Process all URLs with maximum concurrency."""
    stats["total"] = len(urls)
    stats["start"] = time.time()
    
    limits = httpx.Limits(
        max_connections=CONCURRENT,
        max_keepalive_connections=CONCURRENT // 2
    )
    
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        limits=limits,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True
    ) as client:
        
        sem = asyncio.Semaphore(CONCURRENT)
        
        async def bounded_scrape(url: str):
            async with sem:
                result = await scrape(client, url)
                
                # Update stats
                if result.get("status", 0) == 200:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                
                # Stream result immediately
                print(json.dumps(result), flush=True)
                
                # Progress to stderr every 100
                done = stats["success"] + stats["failed"]
                if done % 100 == 0:
                    elapsed = time.time() - stats["start"]
                    rate = done / max(elapsed, 0.1)
                    print(f"\r[{done}/{stats['total']}] {rate:.1f}/s ✓{stats['success']} ✗{stats['failed']}", 
                          file=sys.stderr, end="", flush=True)
        
        # Launch all tasks
        tasks = [bounded_scrape(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Final stats
    elapsed = time.time() - stats["start"]
    print(f"\n\nDone: {stats['total']} URLs in {elapsed:.1f}s ({stats['total']/max(elapsed,0.1):.1f}/s)", 
          file=sys.stderr)
    print(f"Success: {stats['success']} | Failed: {stats['failed']}", file=sys.stderr)

if __name__ == "__main__":
    # Read URLs from file or stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        urls = [line.strip() for line in sys.stdin if line.strip()]
    
    if not urls:
        print("Usage: python3 jester_blast.py urls.txt", file=sys.stderr)
        print("   or: cat urls.txt | python3 jester_blast.py", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting JESTER BLAST: {len(urls)} URLs @ {CONCURRENT} concurrent", file=sys.stderr)
    asyncio.run(main(urls))
