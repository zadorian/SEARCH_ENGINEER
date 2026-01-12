#!/usr/bin/env python3
"""
Bulk Index Company Datasets into Drill Search Elasticsearch
Indexes German CR, CCOD, and other company datasets into the search_nodes index.
"""

import os
import sys
import json
import csv
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path
CURRENT_DIR = Path(__file__).parent
MCP_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from brute.services.elastic_service import get_elastic_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Dataset paths
GERMAN_CR_PATH = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02.backup/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/CORPORATE-REGISTRY/DE/de_CR.jsonl"
CCOD_PATH = "/Users/attic/Dropbox/My Mac (Spyborgs-MacBook-Pro.local)/Desktop/data_cr/CCOD_FULL_2025_08.csv"


def normalize_label(text: str) -> str:
    """Normalize text for content field (searchable)"""
    if not text:
        return ""
    return text.replace(",", " ").replace("  ", " ").strip()


async def index_german_companies(batch_size: int = 1000, limit: Optional[int] = None):
    """
    Index German Company Register (Handelsregister) into Elasticsearch.

    Args:
        batch_size: Number of documents per batch
        limit: Optional limit for testing (e.g., 10000)
    """
    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info(f"Indexing German CR from: {GERMAN_CR_PATH}")

    if not os.path.exists(GERMAN_CR_PATH):
        logger.error(f"File not found: {GERMAN_CR_PATH}")
        return

    batch = []
    count = 0

    with open(GERMAN_CR_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if limit and count >= limit:
                break

            try:
                company = json.loads(line.strip())

                # Build searchable content
                content_parts = [
                    company.get('name', ''),
                    company.get('company_number', ''),
                    company.get('registered_office', ''),
                    company.get('federal_state', ''),
                    company.get('jurisdiction_code', ''),
                ]
                content = normalize_label(' '.join(filter(None, content_parts)))

                # Create Elasticsearch document
                doc = {
                    "id": f"de_cr_{company.get('company_number', count)}",
                    "label": company.get('name', 'Unknown'),
                    "url": f"https://www.handelsregister.de/{company.get('company_number', '')}",
                    "class": "entity",
                    "type": "company",
                    "projectId": "german_cr",
                    "metadata": {
                        "company_number": company.get('company_number'),
                        "jurisdiction": company.get('jurisdiction_code'),
                        "federal_state": company.get('federal_state'),
                        "status": company.get('current_status'),
                        "native_company_number": company.get('native_company_number'),
                        "registered_office": company.get('registered_office'),
                        "register_art": company.get('_registerArt'),
                        "register_nummer": company.get('_registerNummer'),
                        "officers": company.get('officers'),
                        "source": "handelsregister",
                        "country": "DE"
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "query": "",
                    "content": content
                }

                batch.append(doc)
                count += 1

                if len(batch) >= batch_size:
                    await elastic.index_batch(batch)
                    logger.info(f"Indexed {count} German companies...")
                    batch = []

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error at line {count}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing company {count}: {e}")
                continue

    # Index remaining batch
    if batch:
        await elastic.index_batch(batch)
        logger.info(f"Indexed final batch. Total: {count} German companies")

    logger.info(f"German CR indexing complete. Total companies: {count}")


async def index_ccod_properties(batch_size: int = 1000, limit: Optional[int] = None):
    """
    Index UK CCOD (Corporate & Commercial Ownership Database) into Elasticsearch.

    Args:
        batch_size: Number of documents per batch
        limit: Optional limit for testing
    """
    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info(f"Indexing CCOD from: {CCOD_PATH}")

    if not os.path.exists(CCOD_PATH):
        logger.error(f"File not found: {CCOD_PATH}")
        return

    batch = []
    count = 0

    with open(CCOD_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            if limit and count >= limit:
                break

            try:
                # Build searchable content
                content_parts = [
                    row.get('Property Address', ''),
                    row.get('Proprietor Name (1)', ''),
                    row.get('Company Registration No. (1)', ''),
                    row.get('District', ''),
                    row.get('County', ''),
                    row.get('Postcode', ''),
                ]
                content = normalize_label(' '.join(filter(None, content_parts)))

                # Create URL slug from address
                address = row.get('Property Address', '').lower()
                url_slug = address.replace(' ', '-').replace(',', '')[:100]

                # Create Elasticsearch document
                doc = {
                    "id": f"ccod_{row.get('Title Number', count)}",
                    "label": row.get('Proprietor Name (1)', 'Unknown'),
                    "url": url_slug or row.get('Title Number', ''),
                    "class": "property",
                    "type": "uk_property",
                    "projectId": "ccod_2025",
                    "metadata": {
                        "title_number": row.get('Title Number'),
                        "tenure": row.get('Tenure'),
                        "property_address": row.get('Property Address'),
                        "district": row.get('District'),
                        "county": row.get('County'),
                        "postcode": row.get('Postcode'),
                        "proprietor_name": row.get('Proprietor Name (1)'),
                        "company_number": row.get('Company Registration No. (1)'),
                        "proprietor_category": row.get('Proprietor Category (1)'),
                        "date_registered": row.get('Date Proprietor Added'),
                        "source": "ccod",
                        "country": "UK"
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "query": "",
                    "content": content
                }

                batch.append(doc)
                count += 1

                if len(batch) >= batch_size:
                    await elastic.index_batch(batch)
                    logger.info(f"Indexed {count} CCOD properties...")
                    batch = []

            except Exception as e:
                logger.error(f"Error processing CCOD row {count}: {e}")
                continue

    # Index remaining batch
    if batch:
        await elastic.index_batch(batch)
        logger.info(f"Indexed final batch. Total: {count} CCOD properties")

    logger.info(f"CCOD indexing complete. Total properties: {count}")


async def index_all_datasets(german_limit: Optional[int] = None, ccod_limit: Optional[int] = None):
    """
    Index all company datasets.

    Args:
        german_limit: Limit German companies (for testing, e.g., 10000)
        ccod_limit: Limit CCOD properties (for testing, e.g., 10000)
    """
    logger.info("Starting bulk company dataset indexing...")

    # Index German companies
    await index_german_companies(limit=german_limit)

    # Index CCOD properties
    await index_ccod_properties(limit=ccod_limit)

    logger.info("All datasets indexed successfully!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Bulk index company datasets into Elasticsearch')
    parser.add_argument('--dataset', choices=['german', 'ccod', 'all'], default='all',
                        help='Which dataset to index')
    parser.add_argument('--limit', type=int, help='Limit number of records (for testing)')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for indexing')

    args = parser.parse_args()

    if args.dataset == 'german':
        asyncio.run(index_german_companies(batch_size=args.batch_size, limit=args.limit))
    elif args.dataset == 'ccod':
        asyncio.run(index_ccod_properties(batch_size=args.batch_size, limit=args.limit))
    else:
        asyncio.run(index_all_datasets(german_limit=args.limit, ccod_limit=args.limit))
