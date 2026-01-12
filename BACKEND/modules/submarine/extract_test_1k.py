#!/usr/bin/env python3
"""Extract entities from first 1,000 LinkedIn profiles - TEST RUN"""
import re
import sys
import time
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://localhost:9200"])

# Patterns
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I)
PHONE = re.compile(r"(?:\+|00)[\d\s\-\(\)]{10,20}")
SUFFIXES = "ltd|llc|inc|corp|plc|gmbh|ag|sa|bv|nv|kft|zrt|doo|limited|corporation"
COMPANY = re.compile(rf"\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({SUFFIXES})\b", re.I)

def extract(content):
    if not content:
        return {}
    c = content[:100000]
    entities = {}

    emails = list(set(EMAIL.findall(c)))[:10]
    if emails:
        entities["EMAIL"] = emails

    phones = list(set(PHONE.findall(c)))[:10]
    if phones:
        entities["PHONE"] = phones

    companies = []
    for m in COMPANY.finditer(c):
        companies.append(m.group(1).strip() + " " + m.group(2))
        if len(companies) >= 10:
            break
    if companies:
        entities["COMPANY"] = list(set(companies))

    return entities

# TEST: Only process 1000 docs
TEST_LIMIT = 1000

ts = time.strftime("%H:%M:%S")
print(f"[{ts}] TEST MODE: Processing first {TEST_LIMIT} docs only", flush=True)

processed = 0
updated = 0
start_time = time.time()

# Use scroll with small batch size for testing
scroll = es.search(
    index="submarine-linkedin",
    body={
        "size": 100,  # Smaller batches for testing
        "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}},
        "_source": ["content"]
    },
    scroll="5m"
)

scroll_id = scroll["_scroll_id"]
hits = scroll["hits"]["hits"]

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
        result = es.bulk(body=bulk_body, refresh=False)
        updated += len([i for i in result["items"] if i.get("update", {}).get("result") == "updated"])

    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0

    ts = time.strftime("%H:%M:%S")
    pct = 100 * processed // TEST_LIMIT
    print(f"[{ts}] {processed}/{TEST_LIMIT} ({pct}%) updated={updated} rate={rate:.0f}/s", flush=True)
    
    if processed >= TEST_LIMIT:
        break

    # Get next batch
    scroll = es.scroll(scroll_id=scroll_id, scroll="5m")
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]

es.clear_scroll(scroll_id=scroll_id)

elapsed = time.time() - start_time
ts = time.strftime("%H:%M:%S")
print(f"[{ts}] TEST COMPLETE: processed={processed} updated={updated} time={elapsed:.1f}s rate={processed/elapsed:.0f}/s")
print(f"[{ts}] SUCCESS: Test run completed successfully!")
