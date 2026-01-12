#!/usr/bin/env python3
from elasticsearch import Elasticsearch

es = Elasticsearch('http://localhost:9200')

# Check input_classes distribution
print('=== INPUT CLASSES ===')
result = es.search(index='io-matrix', body={
    'size': 0,
    'query': {'exists': {'field': 'input_classes'}},
    'aggs': {'classes': {'terms': {'field': 'input_classes', 'size': 20}}}
})
print(f'Docs with input_classes: {result["hits"]["total"]["value"]}')
for b in result['aggregations']['classes']['buckets']:
    print(f'  {b["key"]}: {b["doc_count"]}')

# Check output_classes distribution
print()
print('=== OUTPUT CLASSES ===')
result = es.search(index='io-matrix', body={
    'size': 0,
    'query': {'exists': {'field': 'output_classes'}},
    'aggs': {'classes': {'terms': {'field': 'output_classes', 'size': 20}}}
})
print(f'Docs with output_classes: {result["hits"]["total"]["value"]}')
for b in result['aggregations']['classes']['buckets']:
    print(f'  {b["key"]}: {b["doc_count"]}')

# Verify we can query by class
print()
print('=== SAMPLE QUERIES ===')

# Company input sources
company_sources = es.search(index='io-matrix', body={
    'size': 3,
    'query': {'bool': {'filter': [
        {'term': {'doc_type': 'source'}},
        {'term': {'input_classes': 'company'}}
    ]}},
    '_source': ['name', 'category', 'input_classes']
})
print(f'Company input sources: {company_sources["hits"]["total"]["value"]}')
for h in company_sources['hits']['hits'][:3]:
    src = h['_source']
    print(f'  - {src.get("name", "?")[:60]}')

# Person input sources
person_sources = es.search(index='io-matrix', body={
    'size': 3,
    'query': {'bool': {'filter': [
        {'term': {'doc_type': 'source'}},
        {'term': {'input_classes': 'person'}}
    ]}},
    '_source': ['name', 'category', 'input_classes']
})
print(f'Person input sources: {person_sources["hits"]["total"]["value"]}')
for h in person_sources['hits']['hits'][:3]:
    src = h['_source']
    print(f'  - {src.get("name", "?")[:60]}')

# UK company sources
uk_company = es.search(index='io-matrix', body={
    'size': 3,
    'query': {'bool': {'filter': [
        {'term': {'doc_type': 'source'}},
        {'term': {'input_classes': 'company'}},
        {'term': {'jurisdictions': 'UK'}}
    ]}},
    '_source': ['name', 'category', 'jurisdictions']
})
print(f'UK company sources: {uk_company["hits"]["total"]["value"]}')
for h in uk_company['hits']['hits'][:3]:
    src = h['_source']
    print(f'  - {src.get("name", "?")[:60]}')
