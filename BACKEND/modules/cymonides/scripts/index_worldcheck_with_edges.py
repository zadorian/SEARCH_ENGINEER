#!/usr/bin/env python3
"""
WorldCheck Dataset Indexer with Full Graph Structure
Indexes 5.4M WorldCheck records to Drill Search with complete entity relationships
"""

import asyncio
import json
import logging
import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path
CURRENT_DIR = Path(__file__).parent
MCP_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from brute.services.elastic_service import get_elastic_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'search_engineer_db',
    'user': 'attic'
}

WORLDCHECK_FILE = "/Volumes/My Book/DOWNLOADS/Free - world-check.com (10.2022).txt"
PROJECT_ID = "worldcheck"


def generate_node_id(value: str, node_type: str) -> str:
    """Generate consistent node ID from value and type"""
    combined = f"{value.lower().strip()}_{node_type}"
    return hashlib.md5(combined.encode()).hexdigest()


def get_or_create_node_class_type(conn, class_name: str, type_name: str):
    """Get or create nodeClass and nodeType, return their IDs"""
    cur = conn.cursor()

    # Get or create nodeClass
    cur.execute('SELECT id FROM "nodeClasses" WHERE name = %s', (class_name,))
    result = cur.fetchone()
    if result:
        class_id = result[0]
    else:
        cur.execute('INSERT INTO "nodeClasses" (name, "displayLabel", "createdAt", "updatedAt") VALUES (%s, %s, NOW(), NOW()) RETURNING id',
                   (class_name, class_name.replace('_', ' ').title()))
        class_id = cur.fetchone()[0]
        conn.commit()

    # Get or create nodeType
    cur.execute('SELECT id FROM "nodeTypes" WHERE name = %s AND "classId" = %s', (type_name, class_id))
    result = cur.fetchone()
    if result:
        type_id = result[0]
    else:
        cur.execute('INSERT INTO "nodeTypes" ("classId", name, "displayLabel", "enforceUniqueness") VALUES (%s, %s, %s, false) RETURNING id',
                   (class_id, type_name, type_name.replace('_', ' ').title()))
        type_id = cur.fetchone()[0]
        conn.commit()

    cur.close()
    return class_id, type_id


def create_node_in_postgres(conn, node_id: str, label: str, class_name: str, type_name: str,
                             canonical_value: str, metadata: dict, project_id: str = "worldcheck"):
    """Create node in PostgreSQL"""
    cur = conn.cursor()

    class_id, type_id = get_or_create_node_class_type(conn, class_name, type_name)

    # Create valueHash
    value_hash = hashlib.md5(canonical_value.lower().encode()).hexdigest()

    # Insert or update node
    cur.execute('''
        INSERT INTO nodes (id, label, "classId", "typeId", "valueHash", "canonicalValue", metadata, "projectId", "createdAt", "updatedAt")
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (id)
        DO UPDATE SET metadata = EXCLUDED.metadata, "updatedAt" = NOW()
    ''', (node_id, label, class_id, type_id, value_hash, canonical_value, json.dumps(metadata), project_id))

    conn.commit()
    cur.close()


def create_edge_in_postgres(conn, from_id: str, to_id: str, relation: str, metadata: dict = None):
    """Create edge in PostgreSQL"""
    cur = conn.cursor()

    edge_id = hashlib.md5(f"{from_id}_{to_id}_{relation}".encode()).hexdigest()

    cur.execute('''
        INSERT INTO edges (id, "fromNodeId", "toNodeId", relation, metadata, "createdAt", "updatedAt")
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (id)
        DO UPDATE SET metadata = EXCLUDED.metadata, "updatedAt" = NOW()
    ''', (edge_id, from_id, to_id, relation, json.dumps(metadata or {})))

    conn.commit()
    cur.close()


def get_or_create_source_node(conn, project_id: str = "worldcheck"):
    """Get or create the World-Check source node"""
    source_name = "World-Check"
    source_id = generate_node_id(source_name, 'source')

    source_metadata = {
        "identifier": source_name,
        "alias": "worldcheck",
        "type": "red_flag",
        "name": "World-Check",
        "full_name": "Refinitiv World-Check",
        "description": "Global sanctions, PEP, and adverse media screening database",
        "url": "https://www.refinitiv.com/en/products/world-check-kyc-screening",
        "data_type": "sanctions_pep_adverse_media",
        "provider": "Refinitiv",
        "version": "October 2022"
    }

    create_node_in_postgres(
        conn, source_id, source_name, "source", "red_flag",
        source_name, source_metadata, project_id
    )

    return source_id


def get_or_create_project_node(conn, project_id: str = "worldcheck"):
    """Get or create the WorldCheck dataset/project node"""
    project_name = "World-Check Dataset"
    project_node_id = generate_node_id(project_name, 'datasets')

    project_metadata = {
        "identifier": project_id,
        "name": "World-Check Dataset",
        "alias": "worldcheck",
        "description": "Global database of sanctions, PEPs, and adverse media (October 2022 snapshot)",
        "dataset_type": "sanctions_pep_adverse_media",
        "record_count": "~5.4 million entities",
        "source": "Refinitiv World-Check",
        "snapshot_date": "2022-10-06"
    }

    create_node_in_postgres(
        conn, project_node_id, project_name, "narrative", "datasets",
        project_name, project_metadata, project_id
    )

    return project_node_id


async def index_worldcheck(limit: int = None, skip: int = 0):
    """Index WorldCheck dataset with full graph structure"""
    conn = psycopg2.connect(**DB_CONFIG)
    elastic = get_elastic_service()
    await elastic.initialize()

    logger.info(f"Indexing WorldCheck from: {WORLDCHECK_FILE}")

    # Get or create parent nodes
    source_node_id = get_or_create_source_node(conn)
    project_node_id = get_or_create_project_node(conn)
    logger.info(f"Source node: {source_node_id}, Project node: {project_node_id}")

    count = 0
    line_num = 0
    total_people = 0
    total_organizations = 0
    total_locations = 0
    elastic_batch = []

    with open(WORLDCHECK_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1

            # Skip first N lines
            if line_num <= skip:
                continue

            if limit and count >= limit:
                break

            try:
                # Parse JSONL - malformed format: "field":value...},"EXTRA_DATA":{...}
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Split on },"EXTRA_DATA":{
                if '},"EXTRA_DATA":{' not in line_stripped:
                    continue

                parts = line_stripped.split('},"EXTRA_DATA":{', 1)

                # Parse basic data (add opening brace)
                basic_json = '{' + parts[0] + '}'
                basic_data = json.loads(basic_json)

                # Parse extra data (wrap in object and close braces)
                extra_json = '{"EXTRA_DATA":{' + parts[1] + '}}'
                extra_data = json.loads(extra_json)['EXTRA_DATA']

                entry_id = basic_data.get('entry_id')
                entity_type = extra_data.get('entity_type', '')

                # Determine primary entity
                if entity_type == 'Person':
                    # Create person node
                    first_name = basic_data.get('first_name', '')
                    last_name = basic_data.get('last_name', '')
                    primary_name = basic_data.get('primary_name', f"{first_name} {last_name}".strip())

                    if not primary_name or primary_name == 'None':
                        primary_name = f"{first_name} {last_name}".strip()

                    person_id = generate_node_id(f"{primary_name}_{entry_id}", 'person')

                    # Build identifiers
                    identifiers = {
                        "entry_id": entry_id,
                        "primary_name": primary_name,
                        "first_name": first_name,
                        "last_name": last_name
                    }

                    # Add other IDs
                    other_ids = extra_data.get('other_identification_numbers', [])
                    for id_obj in other_ids:
                        id_type = id_obj.get('name', '').lower().replace(' ', '_')
                        id_number = id_obj.get('number', '')
                        if id_type and id_number:
                            identifiers[id_type] = id_number

                    person_metadata = {
                        "identifier": str(entry_id),
                        "identifiers": identifiers,
                        "source": "world-check",
                        "entity_type": "Person",
                        "category": extra_data.get('category', ''),
                        "sub_category": extra_data.get('sub_category', ''),
                        "first_name": first_name,
                        "last_name": last_name,
                        "primary_name": primary_name,
                        "alternative_names": basic_data.get('alternative_names', []),
                        "date_of_birth": basic_data.get('date_of_birth', ''),
                        "additional_dobs": extra_data.get('additional_dobs', []),
                        "gender": basic_data.get('gender', ''),
                        "nationality": basic_data.get('nationality', []),
                        "place_of_birth": basic_data.get('place_of_birth', []),
                        "country": basic_data.get('country', ''),
                        "position": extra_data.get('position', []),
                        "company": basic_data.get('company', []),
                        "linked_to": extra_data.get('linked_to', []),
                        "further_info": extra_data.get('further_info', ''),
                        "keywords": extra_data.get('keywords', []),
                        "ext_sources": extra_data.get('ext_sources', []),
                        "status": extra_data.get('status', ''),
                        "pure_adverse_media": extra_data.get('pure_adverse_media', ''),
                        "country_code": extra_data.get('country_code', ''),
                        "sourceDate": extra_data.get('sourceDate', ''),
                        "sourceUpdateDate": extra_data.get('sourceUpdateDate', ''),
                        "mat_ch_date": extra_data.get('mat_ch_date', ''),
                        "modified_date": extra_data.get('modified_date', '')
                    }

                    create_node_in_postgres(
                        conn, person_id, primary_name, "entity", "person",
                        primary_name, person_metadata, PROJECT_ID
                    )

                    # Edges to parent nodes
                    create_edge_in_postgres(conn, person_id, source_node_id, "discovered_from", {
                        "confidence": 1.0,
                        "source": "world-check"
                    })
                    create_edge_in_postgres(conn, person_id, project_node_id, "belongs_to_project", {
                        "project_id": PROJECT_ID
                    })

                    # Index to Elasticsearch
                    content = f"{primary_name} {first_name} {last_name} {' '.join(basic_data.get('alternative_names', []))} {extra_data.get('category', '')} {extra_data.get('further_info', '')}"
                    elastic_batch.append({
                        "id": person_id,
                        "label": primary_name,
                        "url": f"https://world-check.com/{entry_id}",
                        "class": "entity",
                        "type": "person",
                        "projectId": PROJECT_ID,
                        "metadata": person_metadata,
                        "timestamp": datetime.now().isoformat(),
                        "query": "",
                        "content": content[:5000]
                    })

                    total_people += 1

                elif entity_type == 'Organization':
                    # Create organization node
                    org_name = basic_data.get('last_name', basic_data.get('primary_name', ''))

                    if not org_name or org_name == 'None':
                        org_name = basic_data.get('primary_name', f"Org_{entry_id}")

                    org_id = generate_node_id(f"{org_name}_{entry_id}", 'company')

                    # Build identifiers
                    identifiers = {
                        "entry_id": entry_id,
                        "primary_name": org_name
                    }

                    org_metadata = {
                        "identifier": str(entry_id),
                        "identifiers": identifiers,
                        "source": "world-check",
                        "entity_type": "Organization",
                        "category": extra_data.get('category', ''),
                        "sub_category": extra_data.get('sub_category', ''),
                        "name": org_name,
                        "alternative_names": basic_data.get('alternative_names', []),
                        "nationality": basic_data.get('nationality', []),
                        "country": basic_data.get('country', ''),
                        "linked_to": extra_data.get('linked_to', []),
                        "further_info": extra_data.get('further_info', ''),
                        "keywords": extra_data.get('keywords', []),
                        "ext_sources": extra_data.get('ext_sources', []),
                        "status": extra_data.get('status', ''),
                        "pure_adverse_media": extra_data.get('pure_adverse_media', ''),
                        "country_code": extra_data.get('country_code', ''),
                        "sourceDate": extra_data.get('sourceDate', ''),
                        "sourceUpdateDate": extra_data.get('sourceUpdateDate', ''),
                        "mat_ch_date": extra_data.get('mat_ch_date', ''),
                        "modified_date": extra_data.get('modified_date', '')
                    }

                    create_node_in_postgres(
                        conn, org_id, org_name, "entity", "company",
                        org_name, org_metadata, PROJECT_ID
                    )

                    # Edges to parent nodes
                    create_edge_in_postgres(conn, org_id, source_node_id, "discovered_from", {
                        "confidence": 1.0,
                        "source": "world-check"
                    })
                    create_edge_in_postgres(conn, org_id, project_node_id, "belongs_to_project", {
                        "project_id": PROJECT_ID
                    })

                    # Index to Elasticsearch
                    content = f"{org_name} {' '.join(basic_data.get('alternative_names', []))} {extra_data.get('category', '')} {extra_data.get('further_info', '')}"
                    elastic_batch.append({
                        "id": org_id,
                        "label": org_name,
                        "url": f"https://world-check.com/{entry_id}",
                        "class": "entity",
                        "type": "company",
                        "projectId": PROJECT_ID,
                        "metadata": org_metadata,
                        "timestamp": datetime.now().isoformat(),
                        "query": "",
                        "content": content[:5000]
                    })

                    total_organizations += 1

                # Process addresses (create location nodes)
                addresses = basic_data.get('address', [])
                for addr in addresses:
                    if not addr:
                        continue

                    country = addr.get('country', '')
                    city = addr.get('city', '')
                    state = addr.get('state', '')

                    if country:
                        # Create location node for country
                        loc_id = generate_node_id(country, 'location')
                        loc_metadata = {
                            "identifier": country,
                            "country": country,
                            "city": city,
                            "state": state,
                            "source": "world-check"
                        }

                        create_node_in_postgres(
                            conn, loc_id, country, "entity", "location",
                            country, loc_metadata, PROJECT_ID
                        )

                        # Edges to parent nodes
                        create_edge_in_postgres(conn, loc_id, source_node_id, "discovered_from", {
                            "confidence": 1.0,
                            "source": "world-check"
                        })
                        create_edge_in_postgres(conn, loc_id, project_node_id, "belongs_to_project", {
                            "project_id": PROJECT_ID
                        })

                        # Index to Elasticsearch
                        elastic_batch.append({
                            "id": loc_id,
                            "label": country,
                            "url": "",
                            "class": "entity",
                            "type": "location",
                            "projectId": PROJECT_ID,
                            "metadata": loc_metadata,
                            "timestamp": datetime.now().isoformat(),
                            "query": "",
                            "content": f"{country} {city} {state}"
                        })

                        # Edge: entity -> resides_at -> location
                        entity_id = person_id if entity_type == 'Person' else org_id
                        create_edge_in_postgres(conn, entity_id, loc_id, "resides_at", {
                            "city": city,
                            "state": state,
                            "confidence": 1.0,
                            "source": "world-check"
                        })

                        total_locations += 1

                count += 1

                # Batch index to Elasticsearch
                if len(elastic_batch) >= 1000:
                    await elastic.index_batch(elastic_batch)
                    logger.info(f"Indexed {count} records ({total_people} people + {total_organizations} orgs + {total_locations} locations)...")
                    elastic_batch = []

            except Exception as e:
                logger.error(f"Error processing record {count}: {e}")
                continue

    # Index remaining batch
    if elastic_batch:
        await elastic.index_batch(elastic_batch)

    logger.info(f"Complete! Indexed {count} records ({total_people} people + {total_organizations} organizations + {total_locations} locations + edges)")

    # Cleanup
    await elastic.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Index WorldCheck to Drill Search')
    parser.add_argument('--limit', type=int, help='Limit number of records to index')
    parser.add_argument('--skip', type=int, default=0, help='Skip first N records')
    args = parser.parse_args()

    asyncio.run(index_worldcheck(limit=args.limit, skip=args.skip))
