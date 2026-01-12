#!/usr/bin/env python3
"""Check overall extraction stats."""
import requests

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-scrapes"

# Get total count
resp = requests.get(f"{ES_HOST}/{ES_INDEX}/_count")
total = resp.json().get("count", 0)
print(f"Total docs in index: {total:,}")

# Check for docs with various fields using simple count queries
fields = ["persons", "companies", "titles", "professions", "industries", "industry", "outlinks", "themes"]

for field in fields:
    query = {"query": {"exists": {"field": field}}}
    resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_count", json=query)
    count = resp.json().get("count", 0)
    pct = (count / total * 100) if total > 0 else 0
    print(f"  {field}: {count:,} ({pct:.1f}%)")

# Get sample doc with persons
print("\n=== Sample doc WITH persons ===")
query = {
    "query": {"exists": {"field": "persons"}},
    "size": 1,
    "_source": ["domain", "persons", "companies", "titles", "industries"]
}
resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_search", json=query)
hits = resp.json().get("hits", {}).get("hits", [])
if hits:
    doc = hits[0]["_source"]
    print(f"Domain: {doc.get('domain')}")
    print(f"Persons ({len(doc.get('persons', []))}):")
    for p in doc.get("persons", [])[:3]:
        print(f"  - {p.get('name', '?')} (conf={p.get('confidence', 0):.2f})")
    print(f"Companies ({len(doc.get('companies', []))}):")
    for c in doc.get("companies", [])[:3]:
        print(f"  - {c.get('name', '?')} ({c.get('suffix', 'N/A')})")

# Get sample doc with companies
print("\n=== Sample doc WITH companies ===")
query = {
    "query": {"exists": {"field": "companies"}},
    "size": 1,
    "_source": ["domain", "persons", "companies"]
}
resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_search", json=query)
hits = resp.json().get("hits", {}).get("hits", [])
if hits:
    doc = hits[0]["_source"]
    print(f"Domain: {doc.get('domain')}")
    print(f"Companies ({len(doc.get('companies', []))}):")
    for c in doc.get("companies", [])[:5]:
        print(f"  - {c.get('name', '?')} ({c.get('suffix', 'N/A')})")
