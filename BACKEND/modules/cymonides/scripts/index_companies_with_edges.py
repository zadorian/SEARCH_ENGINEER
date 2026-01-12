#!/usr/bin/env python3
"""
Index Company Datasets WITH Graph Edges
Creates companies, extracts officers/directors, creates person nodes, and builds edges.
Follows the master_entity_edges_matrix.json schema.
"""

import os
import sys
import json
import csv
import asyncio
import logging
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

# Add parent directory to path
CURRENT_DIR = Path(__file__).parent
MCP_ROOT = CURRENT_DIR.parent
sys.path.insert(0, str(MCP_ROOT))

from brute.services.elastic_service import get_elastic_service
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Database
DB_URL = os.getenv("DATABASE_URL", "postgresql://attic@localhost:5432/search_engineer_db")

# Dataset paths
GERMAN_CR_PATH = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/Search-Engineer.02.backup/iv. LOCATION/a. KNOWN_UNKNOWN/SOURCE_CATEGORY/PUBLIC-RECORDS/LOCAL/CORPORATE-REGISTRY/DE/de_CR.jsonl"
CCOD_PATH = "/Users/attic/Dropbox/My Mac (Spyborgs-MacBook-Pro.local)/Desktop/data_cr/CCOD_FULL_2025_08.csv"


def generate_node_id(value: str, node_type: str) -> str:
    """Generate consistent node ID from value and type"""
    hash_input = f"{node_type}:{value.lower().strip()}"
    return hashlib.md5(hash_input.encode()).hexdigest()


def get_or_create_node_class_type(conn, class_name: str, type_name: str) -> tuple:
    """Get or create nodeClass and nodeType IDs"""
    cur = conn.cursor()

    # Get or create class
    cur.execute('SELECT id FROM "nodeClasses" WHERE name = %s', (class_name,))
    class_row = cur.fetchone()
    if class_row:
        class_id = class_row[0]
    else:
        cur.execute('INSERT INTO "nodeClasses" (name, "displayLabel") VALUES (%s, %s) RETURNING id',
                    (class_name, class_name.title()))
        class_id = cur.fetchone()[0]

    # Get or create type
    cur.execute('SELECT id FROM "nodeTypes" WHERE name = %s', (type_name,))
    type_row = cur.fetchone()
    if type_row:
        type_id = type_row[0]
    else:
        cur.execute('INSERT INTO "nodeTypes" ("classId", name, "displayLabel", "enforceUniqueness") VALUES (%s, %s, %s, false) RETURNING id',
                    (class_id, type_name, type_name.replace('_', ' ').title()))
        type_id = cur.fetchone()[0]

    return class_id, type_id


def create_node_in_postgres(conn, node_id: str, label: str, class_name: str, type_name: str,
                             canonical_value: str, metadata: dict, project_id: str = "crde"):
    """Create node in PostgreSQL"""
    cur = conn.cursor()

    class_id, type_id = get_or_create_node_class_type(conn, class_name, type_name)

    # Create value hash
    value_hash = hashlib.sha256(f"{canonical_value}:{type_id}".encode()).hexdigest()

    # Insert node (userId can be NULL for dataset imports)
    # Use ON CONFLICT on id (primary key) to handle duplicates within same run
    cur.execute("""
        INSERT INTO nodes (id, label, "classId", "typeId", "canonicalValue", "valueHash",
                          "projectId", "userId", status, metadata, "createdAt", "updatedAt")
        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, 'active', %s, NOW(), NOW())
        ON CONFLICT (id)
        DO UPDATE SET metadata = EXCLUDED.metadata, "updatedAt" = NOW()
        RETURNING id
    """, (node_id, label, class_id, type_id, canonical_value, value_hash, project_id, json.dumps(metadata)))

    conn.commit()
    return node_id


def create_edge_in_postgres(conn, from_node_id: str, to_node_id: str, relation: str, metadata: dict = None):
    """Create edge in PostgreSQL"""
    cur = conn.cursor()

    edge_id = str(uuid.uuid4()).replace('-', '')

    cur.execute("""
        INSERT INTO edges (id, "fromNodeId", "toNodeId", relation, metadata, "createdAt", "updatedAt")
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT DO NOTHING
    """, (edge_id, from_node_id, to_node_id, relation, json.dumps(metadata or {})))

    conn.commit()
    return edge_id


def get_or_create_source_node(conn, project_id: str = "crde"):
    """Get or create the Unternehmensregister source node"""
    source_name = "Unternehmensregister"
    source_id = generate_node_id(source_name, 'source')

    source_metadata = {
        "identifier": source_name,
        "alias": "crde",
        "type": "public_records",
        "name": "Unternehmensregister",
        "full_name": "Handelsregister (German Company Registry)",
        "country": "DE",
        "description": "Official German company registry (Handelsregister)",
        "url": "https://www.handelsregister.de",
        "data_type": "corporate_registry",
        "jurisdiction": "Germany"
    }

    create_node_in_postgres(
        conn, source_id, source_name, "source", "public_records",
        source_name, source_metadata, project_id
    )

    return source_id


def get_or_create_project_node(conn, project_id: str = "crde"):
    """Get or create the German CR dataset/project node"""
    project_name = "German Company Registry Dataset"
    project_node_id = generate_node_id(project_name, 'datasets')

    project_metadata = {
        "identifier": project_id,
        "name": "German Company Registry Dataset",
        "alias": "crde",
        "description": "Complete dataset of German company registrations from Handelsregister",
        "dataset_type": "corporate_registry",
        "country": "DE",
        "record_count": "~5 million companies",
        "source": "Unternehmensregister / Handelsregister"
    }

    create_node_in_postgres(
        conn, project_node_id, project_name, "narrative", "datasets",
        project_name, project_metadata, project_id
    )

    return project_node_id


async def index_german_companies_with_edges(limit: Optional[int] = None, skip: int = 0):
    """
    Index German companies WITH officer/director relationships.
    Creates: Company nodes + Person nodes + Edges
    """
    elastic = get_elastic_service()
    await elastic.initialize()

    conn = psycopg2.connect(DB_URL)

    logger.info(f"Indexing German CR with edges from: {GERMAN_CR_PATH}")

    if not os.path.exists(GERMAN_CR_PATH):
        logger.error(f"File not found: {GERMAN_CR_PATH}")
        return

    # Create parent nodes once
    source_node_id = get_or_create_source_node(conn, "crde")
    project_node_id = get_or_create_project_node(conn, "crde")
    logger.info(f"Source node: {source_node_id}, Project node: {project_node_id}")

    elastic_batch = []
    count = 0
    line_num = 0
    total_people = 0
    total_addresses = 0
    total_locations = 0

    with open(GERMAN_CR_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1

            # Skip first N lines
            if line_num <= skip:
                continue

            if limit and count >= limit:
                break

            try:
                # Rollback any pending failed transaction
                conn.rollback()

                company = json.loads(line.strip())
                company_name = company.get('name', 'Unknown')
                company_number = company.get('company_number', '')

                # Generate company node ID
                company_id = generate_node_id(company_number or company_name, 'company')

                # Extract registered address
                registered_address = company.get('registered_address', '').strip()
                all_attrs = company.get('all_attributes', {})

                # Create company node in PostgreSQL - STORE ALL GERMAN CR DATA
                company_metadata = {
                    # Primary identifier (company number)
                    "identifier": company_number,

                    # Additional identifiers (multiple possible)
                    "identifiers": {
                        "company_number": company_number,
                        "native_company_number": all_attrs.get('native_company_number'),
                        "register_nummer": all_attrs.get('_registerNummer'),
                        "register_art": all_attrs.get('_registerArt')
                    },

                    # Source information
                    "source": "handelsregister",
                    "source_database": "German Company Registry (Handelsregister)",
                    "country": "DE",

                    # Company details
                    "company_number": company_number,
                    "native_company_number": all_attrs.get('native_company_number'),
                    "register_art": all_attrs.get('_registerArt'),
                    "register_nummer": all_attrs.get('_registerNummer'),

                    # Status and jurisdiction
                    "current_status": company.get('current_status'),
                    "jurisdiction_code": company.get('jurisdiction_code'),

                    # Location details
                    "federal_state": all_attrs.get('federal_state'),
                    "registered_office": all_attrs.get('registered_office'),
                    "registered_address": registered_address,
                    "registrar": all_attrs.get('registrar'),

                    # Additional data
                    "additional_data": all_attrs.get('additional_data'),

                    # Metadata
                    "retrieved_at": company.get('retrieved_at'),

                    # Raw data for reference
                    "raw_all_attributes": all_attrs
                }

                create_node_in_postgres(
                    conn, company_id, company_name, "entity", "company",
                    company_number or company_name, company_metadata, "crde"
                )

                # Create edges to parent nodes (source + project)
                create_edge_in_postgres(conn, company_id, source_node_id, "discovered_from", {
                    "confidence": 1.0,
                    "source": "handelsregister"
                })
                create_edge_in_postgres(conn, company_id, project_node_id, "belongs_to_project", {
                    "project_id": "crde"
                })

                # Create ADDRESS node + edge if address exists
                if registered_address:
                    total_addresses += 1
                    address_id = generate_node_id(registered_address, 'address')
                    address_metadata = {
                        # Primary identifier (address string)
                        "identifier": registered_address,

                        # Source information
                        "source": "handelsregister",
                        "source_database": "German Company Registry (Handelsregister)",

                        # Address details
                        "address_type": "registered_office",
                        "country": "DE"
                    }

                    create_node_in_postgres(
                        conn, address_id, registered_address, "entity", "address",
                        registered_address, address_metadata, "crde"
                    )

                    # Create edges to parent nodes
                    create_edge_in_postgres(conn, address_id, source_node_id, "discovered_from", {
                        "confidence": 1.0,
                        "source": "handelsregister"
                    })
                    create_edge_in_postgres(conn, address_id, project_node_id, "belongs_to_project", {
                        "project_id": "crde"
                    })

                    # Index address to Elasticsearch
                    elastic_batch.append({
                        "id": address_id,
                        "label": registered_address,
                        "url": registered_address,
                        "class": "entity",
                        "type": "address",
                        "projectId": "crde",
                        "metadata": address_metadata,
                        "timestamp": datetime.now().isoformat(),
                        "query": "",
                        "content": registered_address
                    })

                    # Create edge: company -> has_address -> address
                    create_edge_in_postgres(conn, company_id, address_id, "has_address", {
                        "address_type": "registered_office",
                        "confidence": 1.0,
                        "source": "handelsregister"
                    })

                # Index company to Elasticsearch
                content = f"{company_name} {company_number} {company.get('registered_office', '')} {company.get('federal_state', '')}"
                elastic_batch.append({
                    "id": company_id,
                    "label": company_name,
                    "url": f"https://www.handelsregister.de/{company_number}",
                    "class": "entity",
                    "type": "company",
                    "projectId": "crde",
                    "metadata": company_metadata,
                    "timestamp": datetime.now().isoformat(),
                    "query": "",
                    "content": content
                })

                # Extract and create person nodes + edges for officers
                officers = company.get('officers', [])
                if isinstance(officers, list):
                    for officer in officers:
                        if isinstance(officer, dict):
                            officer_name = officer.get('name', '').strip()
                            if not officer_name:
                                continue

                            total_people += 1
                            # Create person node - STORE ALL OFFICER DATA
                            person_id = generate_node_id(officer_name, 'person')
                            other_attrs = officer.get('other_attributes', {})
                            person_metadata = {
                                # Primary identifier (full name)
                                "identifier": officer_name,

                                # Additional identifiers
                                "identifiers": {
                                    "full_name": officer_name,
                                    "firstname": other_attrs.get('firstname'),
                                    "lastname": other_attrs.get('lastname')
                                },

                                # Source information
                                "source": "handelsregister_officers",
                                "source_database": "German Company Registry (Handelsregister)",

                                # Officer details
                                "position": officer.get('position'),
                                "type": officer.get('type'),
                                "start_date": officer.get('start_date'),
                                "end_date": officer.get('end_date'),

                                # Personal details
                                "firstname": other_attrs.get('firstname'),
                                "lastname": other_attrs.get('lastname'),
                                "city": other_attrs.get('city'),
                                "flag": other_attrs.get('flag'),

                                # Raw data
                                "raw_other_attributes": other_attrs
                            }

                            create_node_in_postgres(
                                conn, person_id, officer_name, "entity", "person",
                                officer_name, person_metadata, "crde"
                            )

                            # Create edges to parent nodes
                            create_edge_in_postgres(conn, person_id, source_node_id, "discovered_from", {
                                "confidence": 1.0,
                                "source": "handelsregister"
                            })
                            create_edge_in_postgres(conn, person_id, project_node_id, "belongs_to_project", {
                                "project_id": "crde"
                            })

                            # Index person to Elasticsearch
                            elastic_batch.append({
                                "id": person_id,
                                "label": officer_name,
                                "url": officer_name,
                                "class": "entity",
                                "type": "person",
                                "projectId": "crde",
                                "metadata": person_metadata,
                                "timestamp": datetime.now().isoformat(),
                                "query": "",
                                "content": officer_name
                            })

                            # Create LOCATION node for city + resides_at edge
                            city = other_attrs.get('city', '').strip()
                            if city:
                                total_locations += 1
                                location_id = generate_node_id(city, 'location')
                                location_metadata = {
                                    # Primary identifier (city name)
                                    "identifier": city,

                                    # Source information
                                    "source": "handelsregister_officers",
                                    "source_database": "German Company Registry (Handelsregister)",

                                    # Location details
                                    "country": "DE",
                                    "location_type": "city"
                                }

                                create_node_in_postgres(
                                    conn, location_id, city, "entity", "location",
                                    city, location_metadata, "crde"
                                )

                                # Create edges to parent nodes
                                create_edge_in_postgres(conn, location_id, source_node_id, "discovered_from", {
                                    "confidence": 1.0,
                                    "source": "handelsregister"
                                })
                                create_edge_in_postgres(conn, location_id, project_node_id, "belongs_to_project", {
                                    "project_id": "crde"
                                })

                                # Index location to Elasticsearch
                                elastic_batch.append({
                                    "id": location_id,
                                    "label": city,
                                    "url": city,
                                    "class": "entity",
                                    "type": "location",
                                    "projectId": "crde",
                                    "metadata": location_metadata,
                                    "timestamp": datetime.now().isoformat(),
                                    "query": "",
                                    "content": city
                                })

                                # Create edge: person -> resides_at -> location
                                create_edge_in_postgres(conn, person_id, location_id, "resides_at", {
                                    "confidence": 0.9,
                                    "source": "handelsregister"
                                })

                            # Create edge: person -> company (type depends on position)
                            # Shareholders/Partners: "Persönlich haftender Gesellschafter"
                            # Directors/Officers: "Geschäftsführer", "Prokurist", etc.
                            position = officer.get('position', '').lower()
                            if 'gesellschafter' in position or 'partner' in position:
                                edge_type = "partner_of"
                            else:
                                edge_type = "director_of"

                            edge_metadata = {
                                "position": officer.get('position'),
                                "start_date": officer.get('start_date'),
                                "confidence": 1.0,
                                "source": "handelsregister"
                            }

                            create_edge_in_postgres(conn, person_id, company_id, edge_type, edge_metadata)

                count += 1

                # Batch index to Elasticsearch
                if len(elastic_batch) >= 1000:
                    await elastic.index_batch(elastic_batch)
                    logger.info(f"Indexed {count} companies + {total_people} people + {total_addresses} addresses + {total_locations} locations...")
                    elastic_batch = []

            except Exception as e:
                logger.error(f"Error processing company {count}: {e}")
                continue

    # Index remaining batch
    if elastic_batch:
        await elastic.index_batch(elastic_batch)

    logger.info(f"Complete! Indexed {count} companies + {total_people} people + {total_addresses} addresses + {total_locations} locations + edges")

    # Cleanup
    await elastic.close()
    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit companies for testing')
    parser.add_argument('--skip', type=int, default=0, help='Skip first N companies')
    args = parser.parse_args()

    asyncio.run(index_german_companies_with_edges(limit=args.limit, skip=args.skip))
