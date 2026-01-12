#!/usr/bin/env python3
"""
German CR - ELASTICSEARCH ONLY
No PostgreSQL, no graph database, just fast Elasticsearch indexing
"""
import asyncio
import json
import logging
import hashlib
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).parent
MCP_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from brute.services.elastic_service import get_elastic_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GERMAN_CR_PATH = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02.backup/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/CORPORATE-REGISTRY/DE/de_CR.jsonl"
PROJECT_ID = "crde"

def generate_id(value: str, entity_type: str) -> str:
    """Generate consistent ID"""
    return hashlib.md5(f"{value.lower().strip()}_{entity_type}".encode()).hexdigest()

async def index_german_cr(limit: int = None, skip: int = 0):
    """Index German CR to Elasticsearch ONLY"""
    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info(f"Indexing German CR (skip={skip}, limit={limit})")

    batch = []
    count = 0
    line_num = 0

    with open(GERMAN_CR_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1
            if line_num <= skip:
                continue
            if limit and count >= limit:
                break

            try:
                company = json.loads(line.strip())
                company_name = company.get('name', 'Unknown')
                company_number = company.get('company_number', '')

                # Company document
                company_id = generate_id(company_number or company_name, 'company')
                batch.append({
                    "id": company_id,
                    "label": company_name,
                    "class": "entity",
                    "type": "company",
                    "projectId": PROJECT_ID,
                    "metadata": {
                        "identifier": company_number,
                        "source": "handelsregister",
                        **company
                    },
                    "content": f"{company_name} {company_number} {company.get('registered_office', '')}",
                    "timestamp": datetime.now().isoformat()
                })

                # Index officers as separate person documents + edge documents
                for officer in company.get('officers', []):
                    officer_name = officer.get('name', '').strip()
                    if not officer_name:
                        continue

                    person_id = generate_id(officer_name, 'person')

                    # Person document
                    batch.append({
                        "id": person_id,
                        "label": officer_name,
                        "class": "entity",
                        "type": "person",
                        "projectId": PROJECT_ID,
                        "metadata": {
                            "identifier": officer_name,
                            "source": "handelsregister",
                            **officer
                        },
                        "content": officer_name,
                        "timestamp": datetime.now().isoformat()
                    })

                    # Edge document
                    position = officer.get('position', '').lower()
                    edge_type = "partner_of" if 'gesellschafter' in position else "director_of"
                    edge_id = generate_id(f"{person_id}_{company_id}_{edge_type}", 'edge')

                    batch.append({
                        "id": edge_id,
                        "class": "edge",
                        "type": edge_type,
                        "from_id": person_id,
                        "to_id": company_id,
                        "from_type": "person",
                        "to_type": "company",
                        "projectId": PROJECT_ID,
                        "metadata": {
                            "position": officer.get('position'),
                            "start_date": officer.get('start_date'),
                            "source": "handelsregister"
                        },
                        "content": f"{officer_name} {edge_type} {company_name}",
                        "timestamp": datetime.now().isoformat()
                    })

                count += 1

                if len(batch) >= 1000:
                    await elastic.index_batch(batch)
                    logger.info(f"Indexed {count} companies...")
                    batch = []

            except Exception as e:
                logger.error(f"Error processing line {line_num}: {e}")
                continue

    if batch:
        await elastic.index_batch(batch)

    logger.info(f"Complete! Indexed {count} companies")
    await elastic.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--skip', type=int, default=0)
    args = parser.parse_args()

    asyncio.run(index_german_cr(limit=args.limit, skip=args.skip))
