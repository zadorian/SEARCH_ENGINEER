#!/usr/bin/env python3
"""Fast regex-only entity extraction from existing content."""
import re
import sys
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan, bulk

es = Elasticsearch(["http://localhost:9200"])

PATTERNS = {
    "LEI": re.compile(r"\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b"),
    "UK_CRN": re.compile(r"\b(?:CRN|Company\s*(?:No|Number|Reg))[:\s]*([A-Z]{0,2}\d{6,8})\b", re.I),
    "IBAN": re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b"),
    "BTC": re.compile(r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"),
    "ETH": re.compile(r"\b(0x[a-fA-F0-9]{40})\b"),
    "IMO": re.compile(r"\bIMO[:\s]*(\d{7})\b", re.I),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.I),
    "PHONE": re.compile(r"(?:\+|00)[\d\s\-\(\)]{10,20}"),
}

# Company pattern
SUFFIXES = "ltd|llc|inc|corp|plc|gmbh|ag|sa|bv|nv|kft|zrt|doo|limited|corporation"
COMPANY_PATTERN = re.compile(rf"\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({SUFFIXES})\b", re.I)

def extract(content):
    if not content:
        return {}
    entities = {}
    for name, pat in PATTERNS.items():
        matches = pat.findall(content)
        if matches:
            entities[name] = list(set(matches))[:10]
    # Companies
    companies = []
    for m in COMPANY_PATTERN.finditer(content):
        companies.append(m.group(1).strip() + " " + m.group(2))
        if len(companies) >= 20:
            break
    if companies:
        entities["COMPANY"] = list(set(companies))
    return entities

count = es.count(index="submarine-linkedin", body={
    "query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}}
})["count"]
print(f"[START] {count} docs need processing", file=sys.stderr, flush=True)

actions = []
processed = 0
found = 0

for doc in scan(es, index="submarine-linkedin",
                query={"query": {"bool": {"must_not": {"exists": {"field": "entities.EMAIL"}}}}},
                scroll="10m", size=500):
    content = doc["_source"].get("content", "")
    entities = extract(content)
    
    if entities:
        found += 1
        actions.append({
            "_op_type": "update",
            "_index": "submarine-linkedin",
            "_id": doc["_id"],
            "doc": {"entities": entities}
        })
    
    processed += 1
    
    if len(actions) >= 500:
        success, _ = bulk(es, actions, raise_on_error=False, stats_only=True)
        print(f"[BATCH] processed={processed} updated={success} found={found}", file=sys.stderr, flush=True)
        actions = []

if actions:
    success, _ = bulk(es, actions, raise_on_error=False, stats_only=True)
    print(f"[FINAL] processed={processed} updated={success} found={found}", file=sys.stderr, flush=True)

print(f"[DONE] Total: {processed}, with entities: {found}")
