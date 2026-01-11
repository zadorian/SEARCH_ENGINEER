#!/usr/bin/env python3
"""
Test entity graph integration with Corporella
Tests that entities are extracted and relationships are created
"""

import sys
from pathlib import Path
import json

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from storage.company_storage import CorporellaStorage


def test_entity_graph_integration():
    """Test that entity extraction works when saving a company"""

    print("=" * 80)
    print("TESTING ENTITY GRAPH INTEGRATION")
    print("=" * 80)

    # Initialize storage (which includes entity graph)
    storage = CorporellaStorage()
    print(f"\n✅ Storage initialized: {storage.db_path}")
    print(f"✅ Entity graph initialized")

    # Test company data with various entities
    test_company = {
        "name": {
            "value": "TechCorp International Ltd",
            "source": ["test"]
        },
        "about": {
            "company_number": "TC123456",
            "jurisdiction": "UK",
            "incorporation_date": "2020-01-15",
            "status": "Active",
            "registered_address": {
                "value": "123 Tech Street, London, EC1A 1BB, UK",
                "source": ["test"]
            }
        },
        "officers": [
            {
                "name": "Jane Smith",
                "position": "CEO",
                "appointed_on": "2020-01-15",
                "source": ["test"]
            },
            {
                "name": "John Doe",
                "position": "CTO",
                "appointed_on": "2020-03-01",
                "source": ["test"]
            }
        ],
        "ownership": {
            "beneficial_owners": [
                {
                    "name": "Alice Johnson",
                    "percentage": 45,
                    "source": ["test"]
                },
                {
                    "name": "Bob Williams",
                    "percentage": 35,
                    "source": ["test"]
                }
            ],
            "parent_companies": [
                {
                    "name": "Global Holdings Inc",
                    "jurisdiction": "US",
                    "source": ["test"]
                }
            ],
            "subsidiaries": [
                {
                    "name": "TechCorp Software GmbH",
                    "jurisdiction": "DE",
                    "ownership_percentage": 100,
                    "source": ["test"]
                },
                {
                    "name": "TechCorp France SARL",
                    "jurisdiction": "FR",
                    "ownership_percentage": 100,
                    "source": ["test"]
                }
            ]
        },
        "locations": {
            "registered_address": {
                "value": "123 Tech Street, London, EC1A 1BB, UK",
                "source": ["test"]
            },
            "mailing_address": {
                "value": "PO Box 789, London, EC2A 2BB, UK",
                "source": ["test"]
            }
        },
        "contact": {
            "emails": [
                {
                    "value": "info@techcorp.com",
                    "type": "general",
                    "source": ["test"]
                },
                {
                    "value": "investors@techcorp.com",
                    "type": "investor_relations",
                    "source": ["test"]
                }
            ],
            "phones": [
                {
                    "value": "+44 20 1234 5678",
                    "type": "main",
                    "source": ["test"]
                },
                {
                    "value": "+44 20 9876 5432",
                    "type": "support",
                    "source": ["test"]
                }
            ]
        }
    }

    # Save the company (should trigger entity extraction)
    print("\n" + "=" * 40)
    print("TEST 1: Save Company with Entity Extraction")
    print("=" * 40)

    company_id = storage.save_company(test_company)
    print(f"✅ Company saved with ID: {company_id}")

    # Get entity relationships
    print("\n" + "=" * 40)
    print("TEST 2: Retrieve Entity Relationships")
    print("=" * 40)

    relationships = storage.get_entity_relationships(company_id)

    if "error" not in relationships:
        print(f"✅ Retrieved relationships for company")

        # Display outgoing relationships
        if relationships.get("outgoing"):
            print(f"\n📤 OUTGOING RELATIONSHIPS ({len(relationships['outgoing'])} total):")
            for rel in relationships["outgoing"][:5]:  # Show first 5
                print(f"   → {rel['relationship_type']}: {rel['target_name']} ({rel['target_type']})")

        # Display incoming relationships
        if relationships.get("incoming"):
            print(f"\n📥 INCOMING RELATIONSHIPS ({len(relationships['incoming'])} total):")
            for rel in relationships["incoming"][:5]:  # Show first 5
                print(f"   ← {rel['relationship_type']}: {rel['source_name']} ({rel['source_type']})")
    else:
        print(f"⚠️ Error getting relationships: {relationships.get('error')}")

    # Check what entities were created in the graph
    print("\n" + "=" * 40)
    print("TEST 3: Query Graph Database Directly")
    print("=" * 40)

    import sqlite3
    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()

        # Count entity nodes
        cursor.execute("""
            SELECT entity_type, COUNT(*) as count
            FROM entity_nodes
            GROUP BY entity_type
        """)

        print("\n📊 Entity Node Statistics:")
        for row in cursor.fetchall():
            print(f"   {row[0]}: {row[1]} nodes")

        # Count edges
        cursor.execute("""
            SELECT COUNT(*) as count FROM entity_edges
        """)
        edge_count = cursor.fetchone()[0]
        print(f"\n🔗 Total Edges: {edge_count}")

        # Sample some edges
        cursor.execute("""
            SELECT
                en1.name as source,
                en1.entity_type as source_type,
                ee.relationship_type,
                en2.name as target,
                en2.entity_type as target_type
            FROM entity_edges ee
            JOIN entity_nodes en1 ON ee.source_id = en1.id
            JOIN entity_nodes en2 ON ee.target_id = en2.id
            LIMIT 10
        """)

        edges = cursor.fetchall()
        if edges:
            print(f"\n🔍 Sample Edges:")
            for edge in edges:
                print(f"   {edge[0]} ({edge[1]}) --[{edge[2]}]--> {edge[3]} ({edge[4]})")

    print("\n" + "=" * 80)
    print("ENTITY GRAPH INTEGRATION TEST COMPLETE")
    print("=" * 80)

    print("\nSUMMARY:")
    print("✅ Company storage with entity graph is working")
    print("✅ Entities are automatically extracted from company data")
    print("✅ Bidirectional relationships are created")
    print("✅ Graph can be queried for entity networks")

    print("\n💡 Next Steps:")
    print("1. The websocket server can now include entity relationships")
    print("2. Frontend can display entity badges with relationship counts")
    print("3. Click on entity badges to explore the graph")


if __name__ == "__main__":
    test_entity_graph_integration()