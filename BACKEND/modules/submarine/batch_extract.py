#!/usr/bin/env python3
"""Extract entities in small batches using search_after."""
import re
import sys
from elasticsearch import Elasticsearch

es = Elasticsearch(["http://localhost:9200"])

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I)
PHONE = re.compile(r"(?:\+|00)[\d\s\-\(\)]{10,20}")
IBAN = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b")
SUFFIXES = "ltd|llc|inc|corp|plc|gmbh|ag|sa|bv|nv|kft|zrt|doo|limited|corporation"
COMPANY = re.compile(rf"\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({SUFFIXES})\b", re.I)

def extract(content):
    if not content or len(content) < 50:
        return {}
    entities = {}
    c = content[:100000]
    
    emails = list(set(EMAIL.findall(c)))[:10]
    if emails:
        entities["EMAIL"] = emails
    
    phones = list(set(PHONE.findall(c)))[:10]
    if phones:
        entities["PHONE"] = phones
    
    ibans = list(set(IBAN.findall(c)))[:5]
    if ibans:
        entities["IBAN"] = ibans
    
    companies = []
    for m in COMPANY.finditer(c):
        companies.append(m.group(1).strip() + " " + m.group(2))
        if len(companies) >= 10:
            break
    if companies:
        entities["COMPANY"] = list(set(companies))
    
    return entities

# Process in batches using scroll (simpler)
BATCH_SIZE = 200
processed = 0
updated = 0

print("[START] Processing submarine-linkedin", file=sys.stderr, flush=True)

# Use scroll API with source filter to reduce memory
resp = es.search(
    index="submarine-linkedin",
    body={
        "size": BATCH_SIZE,
        "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}},
        "_source": ["content"]
    },
    scroll="5m"
)

scroll_id = resp["_scroll_id"]
hits = resp["hits"]["hits"]
total = resp["hits"]["total"]["value"]
print(f"[TOTAL] {total} docs to process", file=sys.stderr, flush=True)

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
    
    if processed % 1000 == 0:
        print(f"[PROGRESS] processed={processed}/{total} updated={updated}", file=sys.stderr, flush=True)
    
    # Get next batch
    resp = es.scroll(scroll_id=scroll_id, scroll="5m")
    scroll_id = resp["_scroll_id"]
    hits = resp["hits"]["hits"]

# Clear scroll
es.clear_scroll(scroll_id=scroll_id)

print(f"[DONE] processed={processed} updated={updated}")
