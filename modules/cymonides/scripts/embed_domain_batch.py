#!/usr/bin/env python3
"""
Batch Embed Domains from Elasticsearch

Adds 1024D e5-large embeddings to domains in domains_unified index.
Uses StandardEmbedder for consistent, free embeddings.

Usage:
    python3 embed_domain_batch.py --limit 1000 --batch-size 32
    python3 embed_domain_batch.py --query '{"exists": {"field": "company_description"}}'
"""

import sys
sys.path.insert(0, '/data')

import argparse
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
from elasticsearch import Elasticsearch
from shared.embedders import get_embedder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Config
ES_HOST = 'http://localhost:9200'
INDEX_NAME = 'domains_unified'
FIELD_NAME = 'content_vector_e5'


def extract_content(doc: Dict) -> str:
    """Extract meaningful text from domain document."""
    parts = []
    
    # Company info
    if doc.get('company_name'):
        parts.append(doc['company_name'])
    if doc.get('company_description'):
        parts.append(doc['company_description'])
    
    # Domain
    if doc.get('domain'):
        parts.append(doc['domain'])
    
    # Categories
    if doc.get('categories'):
        cats = doc['categories'] if isinstance(doc['categories'], list) else [doc['categories']]
        parts.extend(cats)
    
    return ' '.join(parts)


def embed_batch(es: Elasticsearch, embedder, docs: List[Dict], batch_size: int = 32):
    """Embed a batch of documents and update Elasticsearch."""
    
    if not docs:
        return 0
    
    # Extract texts
    texts = [extract_content(doc['_source']) for doc in docs]
    
    # Generate embeddings
    logger.info(f"Generating embeddings for {len(texts)} documents...")
    embeddings = embedder.encode_batch_passages(
        texts=texts,
        batch_size=batch_size,
        show_progress=True
    )
    
    # Bulk update
    bulk_ops = []
    for doc, embedding in zip(docs, embeddings):
        bulk_ops.append({
            "update": {
                "_index": INDEX_NAME,
                "_id": doc['_id']
            }
        })
        bulk_ops.append({
            "doc": {
                FIELD_NAME: embedding,
                "vector_generated_at": datetime.utcnow().isoformat()
            }
        })
    
    if bulk_ops:
        response = es.bulk(operations=bulk_ops)
        if response.get('errors'):
            logger.error(f"Bulk update had errors: {response}")
        else:
            logger.info(f"✅ Updated {len(docs)} documents")
    
    return len(docs)


def main():
    parser = argparse.ArgumentParser(description='Batch embed domains')
    parser.add_argument('--limit', type=int, default=1000, help='Max documents to process')
    parser.add_argument('--batch-size', type=int, default=32, help='Embedding batch size')
    parser.add_argument('--query', type=str, help='ES query JSON (default: docs with company_description)')
    args = parser.parse_args()
    
    # Connect
    es = Elasticsearch([ES_HOST])
    embedder = get_embedder()
    
    logger.info(f"Embedder loaded: {embedder.dimensions}D")
    logger.info(f"Target index: {INDEX_NAME}")
    
    # Default query: only domains with content
    if args.query:
        query = json.loads(args.query)
    else:
        query = {
            "bool": {
                "should": [
                    {"exists": {"field": "company_description"}},
                    {"exists": {"field": "company_name"}}
                ],
                "must_not": [
                    {"exists": {"field": FIELD_NAME}}  # Skip already embedded
                ]
            }
        }
    
    logger.info(f"Query: {json.dumps(query, indent=2)}")
    
    # Scroll through documents
    total_processed = 0
    scroll = '5m'
    
    response = es.search(
        index=INDEX_NAME,
        query=query,
        size=args.batch_size,
        scroll=scroll
    )
    
    scroll_id = response['_scroll_id']
    docs = response['hits']['hits']
    
    while docs and total_processed < args.limit:
        # Process batch
        processed = embed_batch(es, embedder, docs, args.batch_size)
        total_processed += processed
        
        if total_processed >= args.limit:
            break
        
        # Get next batch
        response = es.scroll(scroll_id=scroll_id, scroll=scroll)
        scroll_id = response['_scroll_id']
        docs = response['hits']['hits']
    
    # Clean up scroll
    es.clear_scroll(scroll_id=scroll_id)
    
    logger.info(f"✅ Complete! Processed {total_processed} documents")


if __name__ == '__main__':
    main()
