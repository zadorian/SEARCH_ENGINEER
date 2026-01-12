#!/usr/bin/env python3
"""FAST extraction - strips HTML first, then extracts entities"""
import re
import sys
import time
from elasticsearch import Elasticsearch

print("[INIT] Starting FAST extraction (HTML stripping enabled)...", flush=True)
es = Elasticsearch(["http://localhost:9200"], request_timeout=30)

# Simple HTML stripper (faster than BeautifulSoup)
HTML_TAG = re.compile(r'<[^>]+>')
def strip_html(html):
    """Strip HTML tags - FAST"""
    return HTML_TAG.sub(' ', html)

# Patterns
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I)
PHONE = re.compile(r"(?:\+|00)[\d\s\-\(\)]{10,20}")
SUFFIXES = "ltd|llc|inc|corp|plc|gmbh|ag|sa|bv|nv|kft|zrt|doo|limited|corporation"
COMPANY = re.compile(rf"\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({SUFFIXES})\b", re.I)

def extract(content):
    """Extract entities from HTML content (with stripping)"""
    if not content:
        return {}
    
    # CRITICAL: Strip HTML FIRST (10x speedup)
    text = strip_html(content)[:50000]  # Only first 50K after stripping
    
    entities = {}

    emails = list(set(EMAIL.findall(text)))[:10]
    if emails:
        entities["EMAIL"] = emails

    phones = list(set(PHONE.findall(text)))[:10]
    if phones:
        entities["PHONE"] = phones

    companies = []
    for m in COMPANY.finditer(text):
        companies.append(m.group(1).strip() + " " + m.group(2))
        if len(companies) >= 10:
            break
    if companies:
        entities["COMPANY"] = list(set(companies))

    return entities

TEST_LIMIT = 1000

ts = time.strftime("%H:%M:%S")
print(f"[{ts}] Processing first {TEST_LIMIT} LinkedIn docs", flush=True)

processed = 0
updated = 0
start_time = time.time()

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

print(f"[{ts}] Got first batch: {len(hits)} hits - processing...", flush=True)

while hits and processed < TEST_LIMIT:
    bulk_body = []
    
    for hit in hits:
        if processed >= TEST_LIMIT:
            break
            
        content = hit["_source"].get("content", "")
        entities = extract(content)
        
        if entities:
            bulk_body.append({"update": {"_index": "submarine-linkedin", "_id": hit["_id"]}})
            bulk_body.append({"doc": {"entities": entities}})
        
        processed += 1

    if bulk_body:
        es.bulk(body=bulk_body, refresh=False)
        updated += len(bulk_body) // 2

    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    pct = 100 * processed // TEST_LIMIT
    
    print(f"[{time.strftime('%H:%M:%S')}] {processed}/{TEST_LIMIT} ({pct}%) | updated={updated} | rate={rate:.0f}/s | {elapsed:.1f}s elapsed", flush=True)
    
    if processed >= TEST_LIMIT:
        break

    scroll = es.scroll(scroll_id=scroll_id, scroll="5m")
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]

es.clear_scroll(scroll_id=scroll_id)

elapsed = time.time() - start_time
print(f"\n[{time.strftime('%H:%M:%S')}] COMPLETE: {processed} processed, {updated} updated in {elapsed:.1f}s ({processed/elapsed:.0f}/s)", flush=True)
