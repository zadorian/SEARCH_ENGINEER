#!/usr/bin/env python3
"""Extract entities with proper progress tracking."""
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

# Get total count
total = es.count(index="submarine-linkedin", body={
    "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}}
})["count"]

ts = time.strftime("%H:%M:%S")
print(f"[{ts}] Total: {total} docs to process", flush=True)

processed = 0
updated = 0
start_time = time.time()

# Use scroll with moderate batch size
scroll = es.search(
    index="submarine-linkedin",
    body={
        "size": 500,
        "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}},
        "_source": ["content"]
    },
    scroll="10m"
)

scroll_id = scroll["_scroll_id"]
hits = scroll["hits"]["hits"]

while hits:
    bulk_body = []
    for hit in hits:
        content = hit["_source"].get("content", "")
        entities = extract(content)
        if entities:
            bulk_body.append({"update": {"_index": "submarine-linkedin", "_id": hit["_id"]}})
            bulk_body.append({"doc": {"entities": entities}})

    if bulk_body:
        result = es.bulk(body=bulk_body, refresh=False)
        updated += len([i for i in result["items"] if i.get("update", {}).get("result") == "updated"])

    processed += len(hits)

    elapsed = time.time() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    eta = (total - processed) / rate if rate > 0 else 0

    ts = time.strftime("%H:%M:%S")
    pct = 100 * processed // total
    eta_min = eta / 60
    print(f"[{ts}] {processed}/{total} ({pct}%) updated={updated} rate={rate:.0f}/s ETA={eta_min:.1f}min", flush=True)

    # Get next batch
    scroll = es.scroll(scroll_id=scroll_id, scroll="10m")
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]

es.clear_scroll(scroll_id=scroll_id)

elapsed = time.time() - start_time
ts = time.strftime("%H:%M:%S")
print(f"[{ts}] DONE: processed={processed} updated={updated} time={elapsed/60:.1f}min")
