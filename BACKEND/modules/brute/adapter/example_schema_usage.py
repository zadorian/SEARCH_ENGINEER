#!/usr/bin/env python3
"""
CyMonides DrillSearchAdapter - Schema-Aware Example

Demonstrates:
1. Edge validation against edge_types.json
2. FTM (Follow The Money) conversion
3. Metadata schema validation
4. Valid edge discovery
"""

from drill_search_adapter import DrillSearchAdapter

def main():
    print("🧪 CyMonides Schema-Aware Features Demo\n")

    adapter = DrillSearchAdapter()

    # 1. Create entities
    print("📝 Creating entities...\n")

    company = adapter.index_node(
        label="Offshore Holdings Ltd",
        content="Shell company registered in British Virgin Islands",
        className="subject",
        typeName="company",
        metadata={
            "jurisdiction": "British Virgin Islands",
            "registration_number": "BVI123456",
            "status": "Active"
        }
    )
    print(f"   Created company: {company['id']}")

    person = adapter.index_node(
        label="John Anderson",
        content="Business owner and director",
        className="subject",
        typeName="person",
        metadata={
            "nationality": "UK",
            "birth_date": "1970-03-15"
        }
    )
    print(f"   Created person: {person['id']}")

    # 2. Create validated edge
    print("\n🔗 Creating validated edge...\n")

    edge = adapter.index_edge(
        from_node=person['id'],
        to_node=company['id'],
        relation="beneficial_owner_of",
        source_type="person",
        target_type="company",
        metadata={
            "share_pct": 85.0,
            "natures_of_control": ["ownership-of-shares-75-to-100-percent"]
        }
    )
    print(f"   ✅ Edge validated and created")

    # 3. Test edge validation with wrong types
    print("\n❌ Testing invalid edge...\n")

    try:
        # This should warn - person can't be beneficial_owner_of another person
        adapter.index_edge(
            from_node=person['id'],
            to_node=person['id'],  # Wrong target type
            relation="beneficial_owner_of",
            source_type="person",
            target_type="person",  # Should be company
            validate=True
        )
    except Exception:
        pass

    # 4. FTM Conversion
    print("\n🔄 Testing FTM conversion...\n")

    ftm_person = adapter.to_ftm(person)
    print(f"   Drill Search -> FTM:")
    print(f"   Schema: {ftm_person['schema']}")
    print(f"   Properties: {ftm_person['properties']}")

    # Convert back
    drill_person = adapter.from_ftm(ftm_person)
    print(f"\n   FTM -> Drill Search:")
    print(f"   Type: {drill_person['typeName']}")
    print(f"   FTM origin: {drill_person['metadata'].get('ftm_origin')}")

    # 5. List valid edges
    print("\n📋 Valid edges for 'company':\n")

    valid_edges = adapter.list_valid_edges_for_type('company', direction='outgoing')
    print(f"   Found {len(valid_edges)} outgoing edge types:")
    for edge_def in valid_edges[:10]:
        print(f"   - {edge_def['relationship_type']}: {edge_def['description'][:60]}...")

    # 6. Get metadata schema
    print("\n📄 Metadata schema for 'beneficial_owner_of':\n")

    schema = adapter.get_edge_metadata_schema('beneficial_owner_of')
    print(f"   Required fields: {schema.get('required', [])}")
    print(f"   Optional fields: {schema.get('optional', [])}")

    # 7. Semantic search
    print("\n🔍 Semantic search for 'offshore beneficial ownership':\n")

    results = adapter.search_semantic("offshore beneficial ownership", k=3)
    print(f"   Found {len(results)} results:")
    for i, result in enumerate(results):
        print(f"   {i+1}. [{result.get('score', 0):.3f}] {result.get('label', 'Untitled')}")

    print("\n✅ Demo complete!")
    print("\nKey features demonstrated:")
    print("  ✅ Edge validation against 69 edge types")
    print("  ✅ FTM schema conversion (10 entity types)")
    print("  ✅ Metadata schema checking")
    print("  ✅ Valid edge discovery")
    print("  ✅ Semantic search with embeddings")

if __name__ == "__main__":
    main()
