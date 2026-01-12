#!/usr/bin/env python3
"""Check a sample document from ES."""
import requests
import json

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-scrapes"

# Get a random doc
resp = requests.get(f"{ES_HOST}/{ES_INDEX}/_search?size=1")
doc = resp.json()["hits"]["hits"][0]["_source"]

print("=== Sample Document ===")
print(f"Domain: {doc.get('domain', 'N/A')}")
print(f"URL: {doc.get('url', 'N/A')[:80]}")
print()
print("Field counts:")
print(f"  Persons: {len(doc.get('persons', []))}")
print(f"  Companies: {len(doc.get('companies', []))}")
print(f"  Titles: {len(doc.get('titles', []))}")
print(f"  Professions: {len(doc.get('professions', []))}")
print(f"  Industries: {len(doc.get('industries', []))}")
print(f"  Industry (primary): {doc.get('industry', 'N/A')}")
print(f"  Outlinks: {len(doc.get('outlinks', []))}")
print(f"  Themes: {len(doc.get('themes', []))}")

# Show samples
if doc.get("persons"):
    print("\nSample persons:")
    for p in doc["persons"][:3]:
        print(f"  - {p.get('name', '?')}")

if doc.get("companies"):
    print("\nSample companies:")
    for c in doc["companies"][:3]:
        print(f"  - {c.get('name', '?')}")

if doc.get("titles"):
    print("\nSample titles:")
    for t in doc["titles"][:3]:
        print(f"  - {t.get('name', '?')} (matched: {t.get('matched_term', '?')})")

if doc.get("industries"):
    print("\nSample industries:")
    for i in doc["industries"][:3]:
        print(f"  - {i.get('name', '?')} (matched: {i.get('matched_term', '?')})")

# Check aggregations for overall stats
print("\n=== Overall Field Coverage ===")
agg_query = {
    "size": 0,
    "aggs": {
        "total": {"value_count": {"field": "_id"}},
        "with_persons": {"filter": {"exists": {"field": "persons"}}},
        "with_companies": {"filter": {"exists": {"field": "companies"}}},
        "with_titles": {"filter": {"exists": {"field": "titles"}}},
        "with_industries": {"filter": {"exists": {"field": "industries"}}},
        "with_outlinks": {"filter": {"exists": {"field": "outlinks"}}},
    }
}
resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_search", json=agg_query)
aggs = resp.json().get("aggregations", {})
total = resp.json()["hits"]["total"]["value"]

print(f"Total docs: {total:,}")
print(f"Docs with persons: {aggs.get('with_persons', {}).get('doc_count', 0):,}")
print(f"Docs with companies: {aggs.get('with_companies', {}).get('doc_count', 0):,}")
print(f"Docs with titles: {aggs.get('with_titles', {}).get('doc_count', 0):,}")
print(f"Docs with industries: {aggs.get('with_industries', {}).get('doc_count', 0):,}")
print(f"Docs with outlinks: {aggs.get('with_outlinks', {}).get('doc_count', 0):,}")
