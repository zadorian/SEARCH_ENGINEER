#!/usr/bin/env python3
"""
Semantic Search for Domains

Search domains_unified using vector similarity.
Uses StandardEmbedder for consistent 1024D e5-large embeddings.

Usage:
    python3 semantic_search.py "AI research companies" --limit 20
    python3 semantic_search.py "fintech startups" --country US --limit 10
"""

import sys
sys.path.insert(0, '/data')

import argparse
import logging
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
from shared.embedders import encode_query

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
ES_HOST = 'http://localhost:9200'
INDEX_NAME = 'domains_unified'
FIELD_NAME = 'content_vector_e5'


def semantic_search(
    es: Elasticsearch,
    query_text: str,
    limit: int = 20,
    filters: Dict = None
) -> List[Dict[str, Any]]:
    """
    Perform semantic search using vector similarity.
    
    Args:
        es: Elasticsearch client
        query_text: Search query text
        limit: Number of results
        filters: Optional filters (country, industry, etc.)
    
    Returns:
        List of matching domains with scores
    """
    
    # Generate query vector
    logger.info(f"Encoding query: '{query_text}'")
    query_vector = encode_query(query_text)
    logger.info(f"Query vector: {len(query_vector)}D")
    
    # Build ES query
    base_query = filters or {"match_all": {}}
    
    es_query = {
        "size": limit,
        "query": {
            "script_score": {
                "query": base_query,
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'content_vector_e5') + 1.0",
                    "params": {"query_vector": query_vector}
                }
            }
        }
    }
    
    # Execute search
    response = es.search(index=INDEX_NAME, body=es_query)
    
    # Format results
    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        results.append({
            'domain': source.get('domain'),
            'company_name': source.get('company_name'),
            'description': source.get('company_description'),
            'score': hit['_score'],
            'country': source.get('country'),
            'categories': source.get('categories', [])
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Semantic search for domains')
    parser.add_argument('query', type=str, help='Search query')
    parser.add_argument('--limit', type=int, default=20, help='Number of results')
    parser.add_argument('--country', type=str, help='Filter by country code')
    parser.add_argument('--industry', type=str, help='Filter by industry')
    args = parser.parse_args()
    
    # Connect
    es = Elasticsearch([ES_HOST])
    
    # Build filters
    filters = None
    if args.country or args.industry:
        must = []
        if args.country:
            must.append({"term": {"country": args.country}})
        if args.industry:
            must.append({"match": {"industry": args.industry}})
        filters = {"bool": {"must": must}}
    
    # Search
    logger.info(f"Searching for: '{args.query}'")
    results = semantic_search(es, args.query, args.limit, filters)
    
    # Display results
    print(f"\n{'='*80}")
    print(f"SEMANTIC SEARCH: '{args.query}'")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['domain']} (score: {result['score']:.4f})")
        if result['company_name']:
            print(f"   Company: {result['company_name']}")
        if result['description']:
            desc = result['description'][:200]
            print(f"   Description: {desc}...")
        if result['country']:
            print(f"   Country: {result['country']}")
        print()
    
    print(f"Found {len(results)} results\n")


if __name__ == '__main__':
    main()
