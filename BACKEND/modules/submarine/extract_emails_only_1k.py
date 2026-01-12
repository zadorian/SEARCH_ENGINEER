#!/usr/bin/env python3
"""ULTRA-FAST test: Extract ONLY emails from 1000 docs"""
import re
import time
from elasticsearch import Elasticsearch

print("[INIT] Email-only extraction test...", flush=True)
es = Elasticsearch(["http://localhost:9200"], request_timeout=30)

# HTML stripper
HTML_TAG = re.compile(r'<[^>]+>')

# ONLY email pattern (simplest)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I)

TEST_LIMIT = 1000
processed = 0
updated = 0
start_time = time.time()

print(f"[{time.strftime('%H:%M:%S')}] Starting scroll...", flush=True)

scroll = es.search(
    index="submarine-linkedin",
    body={
        "size": 100,
        "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}},
        "_source": ["content"]
    },
    scroll="5m"
)

scroll_id = scroll["_scroll_id"]
hits = scroll["hits"]["hits"]

print(f"[{time.strftime('%H:%M:%S')}] Got {len(hits)} hits", flush=True)

while hits and processed < TEST_LIMIT:
    bulk_body = []
    
    for hit in hits:
        if processed >= TEST_LIMIT:
            break
        
        # Strip HTML and find emails
        content = hit["_source"].get("content", "")
        text = HTML_TAG.sub(' ', content)[:20000]  # Only 20K chars
        emails = list(set(EMAIL.findall(text)))[:10]
        
        if emails:
            bulk_body.append({"update": {"_index": "submarine-linkedin", "_id": hit["_id"]}})
            bulk_body.append({"doc": {"entities": {"EMAIL": emails}}})
        
        processed += 1

    if bulk_body:
        es.bulk(body=bulk_body, refresh=False)
        updated += len(bulk_body) // 2

    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    
    print(f"[{time.strftime('%H:%M:%S')}] {processed}/{TEST_LIMIT} | {updated} updated | {rate:.1f}/s", flush=True)
    
    if processed >= TEST_LIMIT:
        break

    scroll = es.scroll(scroll_id=scroll_id, scroll="5m")
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]

es.clear_scroll(scroll_id=scroll_id)

elapsed = time.time() - start_time
print(f"\n[DONE] {processed} docs in {elapsed:.1f}s ({processed/elapsed:.1f}/s) | {updated} with emails", flush=True)
