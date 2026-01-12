#!/usr/bin/env python3
"""FAST extraction: emails + phones for ALL 135K LinkedIn docs"""
import re
import time
from elasticsearch import Elasticsearch

print("[INIT] Full LinkedIn extraction (emails + phones only)...", flush=True)
es = Elasticsearch(["http://localhost:9200"], request_timeout=30)

# HTML stripper
HTML_TAG = re.compile(r'<[^>]+>')

# Patterns (skip complex COMPANY pattern)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I)
PHONE = re.compile(r"(?:\+|00)[\d\s\-\(\)]{10,20}")

processed = 0
updated = 0
start_time = time.time()

print(f"[{time.strftime('%H:%M:%S')}] Starting scroll...", flush=True)

scroll = es.search(
    index="submarine-linkedin",
    body={
        "size": 500,  # Larger batches since we're fast now
        "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}},
        "_source": ["content"]
    },
    scroll="10m"
)

scroll_id = scroll["_scroll_id"]
hits = scroll["hits"]["hits"]

print(f"[{time.strftime('%H:%M:%S')}] Got {len(hits)} hits - processing...", flush=True)

while hits:
    bulk_body = []
    
    for hit in hits:
        content = hit["_source"].get("content", "")
        text = HTML_TAG.sub(' ', content)[:20000]
        
        entities = {}
        
        # Extract emails
        emails = list(set(EMAIL.findall(text)))[:10]
        if emails:
            entities["EMAIL"] = emails
        
        # Extract phones
        phones = list(set(PHONE.findall(text)))[:10]
        if phones:
            entities["PHONE"] = phones
        
        if entities:
            bulk_body.append({"update": {"_index": "submarine-linkedin", "_id": hit["_id"]}})
            bulk_body.append({"doc": {"entities": entities}})
        
        processed += 1

    if bulk_body:
        es.bulk(body=bulk_body, refresh=False)
        updated += len(bulk_body) // 2

    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    
    # Report every 10K
    if processed % 10000 == 0:
        eta = (135144 - processed) / rate if rate > 0 else 0
        print(f"[{time.strftime('%H:%M:%S')}] {processed:,}/135,144 | {updated:,} updated | {rate:.0f}/s | ETA: {eta/60:.1f}min", flush=True)

    scroll = es.scroll(scroll_id=scroll_id, scroll="10m")
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]

es.clear_scroll(scroll_id=scroll_id)

elapsed = time.time() - start_time
print(f"\n[DONE] {processed:,} docs in {elapsed:.0f}s ({processed/elapsed:.0f}/s) | {updated:,} updated", flush=True)
