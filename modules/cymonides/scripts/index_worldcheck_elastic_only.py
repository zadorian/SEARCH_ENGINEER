#!/usr/bin/env python3
"""
WorldCheck - ELASTICSEARCH ONLY
No PostgreSQL, just fast Elasticsearch indexing
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

WORLDCHECK_FILE = "/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt"
PROJECT_ID = "worldcheck"

def generate_id(value: str, entity_type: str) -> str:
    """Generate consistent ID"""
    return hashlib.md5(f"{value.lower().strip()}_{entity_type}".encode()).hexdigest()

async def index_worldcheck(limit: int = None, skip: int = 0):
    """Index WorldCheck to Elasticsearch ONLY"""
    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info(f"Indexing WorldCheck (skip={skip}, limit={limit})")

    batch = []
    count = 0
    line_num = 0

    with open(WORLDCHECK_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1
            if line_num <= skip:
                continue
            if limit and count >= limit:
                break

            try:
                line_stripped = line.strip()
                if not line_stripped or '},"EXTRA_DATA":{' not in line_stripped:
                    continue

                # Parse malformed JSON
                parts = line_stripped.split('},"EXTRA_DATA":{', 1)
                basic_data = json.loads('{' + parts[0] + '}')
                extra_data = json.loads('{"EXTRA_DATA":{' + parts[1] + '}}')['EXTRA_DATA']

                entry_id = basic_data.get('entry_id')
                entity_type = extra_data.get('entity_type', '')

                if entity_type == 'Person':
                    first_name = basic_data.get('first_name', '')
                    last_name = basic_data.get('last_name', '')
                    primary_name = basic_data.get('primary_name', f"{first_name} {last_name}".strip())
                    if primary_name == 'None':
                        primary_name = f"{first_name} {last_name}".strip()

                    person_id = generate_id(f"{primary_name}_{entry_id}", 'person')

                    batch.append({
                        "id": person_id,
                        "label": primary_name,
                        "class": "entity",
                        "type": "person",
                        "projectId": PROJECT_ID,
                        "metadata": {
                            "identifier": str(entry_id),
                            "source": "world-check",
                            "category": extra_data.get('category', ''),
                            "sub_category": extra_data.get('sub_category', ''),
                            **basic_data,
                            **extra_data
                        },
                        "content": f"{primary_name} {extra_data.get('category', '')} {extra_data.get('further_info', '')}"[:5000],
                        "timestamp": datetime.now().isoformat()
                    })

                elif entity_type == 'Organization':
                    org_name = basic_data.get('last_name', basic_data.get('primary_name', ''))
                    if org_name == 'None':
                        org_name = f"Org_{entry_id}"

                    org_id = generate_id(f"{org_name}_{entry_id}", 'company')

                    batch.append({
                        "id": org_id,
                        "label": org_name,
                        "class": "entity",
                        "type": "company",
                        "projectId": PROJECT_ID,
                        "metadata": {
                            "identifier": str(entry_id),
                            "source": "world-check",
                            "category": extra_data.get('category', ''),
                            **basic_data,
                            **extra_data
                        },
                        "content": f"{org_name} {extra_data.get('category', '')}"[:5000],
                        "timestamp": datetime.now().isoformat()
                    })

                count += 1

                if len(batch) >= 1000:
                    await elastic.index_batch(batch)
                    logger.info(f"Indexed {count} records...")
                    batch = []

            except Exception as e:
                logger.error(f"Error processing line {line_num}: {e}")
                continue

    if batch:
        await elastic.index_batch(batch)

    logger.info(f"Complete! Indexed {count} records")
    await elastic.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--skip', type=int, default=0)
    args = parser.parse_args()

    asyncio.run(index_worldcheck(limit=args.limit, skip=args.skip))
