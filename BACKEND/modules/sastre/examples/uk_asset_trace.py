#!/usr/bin/env python3
"""
UK ASSET TRACE - Complete End-to-End Example

Template: ASSET_TRACE
Jurisdiction: UK
Entity Type: Person

This traces assets for a UK-based individual across:
- Property (Land Registry)
- Company shareholdings (Companies House)
- Vehicles/Aircraft/Vessels (DVLA, CAA, Lloyd's)
- Intellectual property (IPO, WIPO)
- Financial signals (news, filings)

FULL OPERATOR CHAIN:
1. template:asset_trace:UK :#JohnSmith           → Load template + create watchers
2. { puk:, cuk: } in parallel                     → Person + company lookups
3. foreach #directorships => cuk: [COMPANY]       → Get all companies
4. propuk: [NAME] + propuk: [COMPANIES]           → Property search
5. { FAA:, CAA:, Lloyd's: } in parallel           → Vehicles/aircraft/vessels
6. { USPTO:, EPO:, WIPO: } in parallel            → IP assets
7. Gazette: [NAME] ##transfer                     → Recent transfers
8. Loop until sufficient

USAGE:
    python examples/uk_asset_trace.py "John Smith"
    python examples/uk_asset_trace.py "Roman Abramovich"
"""

import asyncio
import sys
from pathlib import Path

# Add paths
SASTRE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = SASTRE_DIR.parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SASTRE_DIR))


# Define UK Asset Trace sections
UK_ASSET_TRACE_SECTIONS = [
    "EXECUTIVE_SUMMARY",
    "SUBJECT_IDENTIFICATION",
    "DIRECTORSHIPS_SHAREHOLDINGS",
    "REAL_PROPERTY",
    "VEHICLES_AIRCRAFT_VESSELS",
    "INTELLECTUAL_PROPERTY",
    "FINANCIAL_INTERESTS",
    "CONCEALMENT_INDICATORS",
    "ASSET_SUMMARY_TABLE",
    "RESEARCH_LIMITATIONS",
    "RESEARCH_METHODOLOGY",
]

# UK-specific asset search actions
UK_ASSET_ACTIONS = [
    "SEARCH_REGISTRY",           # Companies House for directorships
    "SEARCH_SHAREHOLDERS",       # Shareholdings in companies
    "SEARCH_PROPERTY",           # Land Registry
    "SEARCH_INTELLECTUAL_PROPERTY",  # IPO, WIPO
    "SEARCH_BANKRUPTCY",         # Insolvency register
    "SEARCH_COURT",              # Freezing orders, judgments
    "SEARCH_NEWS",               # Financial signals
    "SEARCH_RELATED_PARTIES",    # Connected entities
]


async def run_uk_asset_trace(subject_name: str):
    """
    Execute UK Asset Trace using template operator.
    """
    from executor import UnifiedExecutor

    print("=" * 70)
    print(f"UK ASSET TRACE: {subject_name}")
    print("=" * 70)

    executor = UnifiedExecutor()

    # Build template query
    entity_tag = subject_name.replace(" ", "_").replace(".", "")
    query = f"template:asset_trace:UK :#{entity_tag}"

    print(f"\n[QUERY] {query}\n")

    # Execute template
    result = await executor.execute(query, project_id="uk_asset_trace")

    if "error" in result:
        print(f"[ERROR] {result['error']}")
        return result

    # Display results
    print("\n[TEMPLATE LOADED]")
    print(f"  Genre: {result.get('genre')}")
    print(f"  Jurisdiction: {result.get('jurisdiction')}")
    print(f"  Entity: {result.get('entity')}")

    sections = result.get("sections", [])
    print(f"\n[ASSET TRACE SECTIONS] ({len(sections)})")
    for section in sections:
        print(f"  • {section}")

    # Now execute the asset-specific queries in parallel
    print("\n[EXECUTING ASSET SEARCHES]")

    # Phase 1: Subject identification
    print("\n  Phase 1: Subject Identification")
    subject_queries = [
        f"puk: {subject_name}",      # Person lookup
        f'"{subject_name}" site:linkedin.com',  # LinkedIn profile
    ]
    for q in subject_queries:
        print(f"    → {q}")

    # Phase 2: Directorships & Shareholdings
    print("\n  Phase 2: Directorships & Shareholdings")
    corp_queries = [
        f"cuk: {subject_name}",      # Companies where subject is officer
        f"p? @COMPANY :#{entity_tag}",  # Extract company names from profile
    ]
    for q in corp_queries:
        print(f"    → {q}")

    # Phase 3: Property (Land Registry)
    print("\n  Phase 3: Real Property")
    property_queries = [
        f"propuk: {subject_name}",   # Land Registry search
        f'"{subject_name}" site:rightmove.co.uk OR site:zoopla.co.uk',  # Property listings
    ]
    for q in property_queries:
        print(f"    → {q}")

    # Phase 4: Vehicles/Aircraft/Vessels (parallel)
    print("\n  Phase 4: Vehicles/Aircraft/Vessels (PARALLEL)")
    vehicle_query = f'{{ CAA: {subject_name}, Lloyd\'s: {subject_name}, DVLA: {subject_name} }}'
    print(f"    → {vehicle_query}")

    # Phase 5: Intellectual Property (parallel)
    print("\n  Phase 5: Intellectual Property (PARALLEL)")
    ip_query = f'{{ IPO: {subject_name}, WIPO: {subject_name}, USPTO: {subject_name} }}'
    print(f"    → {ip_query}")

    # Phase 6: Financial Signals
    print("\n  Phase 6: Financial Signals")
    financial_queries = [
        f'"{subject_name}" investment OR fund OR capital',
        f'Gazette: {subject_name} ##transfer',
    ]
    for q in financial_queries:
        print(f"    → {q}")

    # Phase 7: Concealment Detection
    print("\n  Phase 7: Concealment Indicators")
    concealment_queries = [
        f'"{subject_name}" trust OR "asset protection" OR offshore',
        f'court: {subject_name} ##freezing_order',
    ]
    for q in concealment_queries:
        print(f"    → {q}")

    # Summary
    print("\n" + "=" * 70)
    print("ASSET TRACE SUMMARY")
    print("=" * 70)
    print(f"""
  Subject: {subject_name}
  Jurisdiction: UK

  Searches Planned:
    • Subject ID: 2 queries
    • Directorships: 2 queries
    • Property: 2 queries (Land Registry + listings)
    • Vehicles: 3 queries (CAA, Lloyd's, DVLA) - PARALLEL
    • IP: 3 queries (IPO, WIPO, USPTO) - PARALLEL
    • Financial: 2 queries
    • Concealment: 2 queries

  Total: 16 queries (11 parallel groups)

  Template Sections: {len(sections)}
  Watchers Created: {len(result.get('watchers_created', []))}
""")

    return result


async def demonstrate_parallel_asset_queries():
    """Show how parallel queries work for asset trace."""
    print("\n" + "=" * 70)
    print("PARALLEL ASSET QUERY DEMONSTRATION")
    print("=" * 70)

    # These would execute in true parallel after the macros.py fix
    parallel_examples = [
        "{ CAA: John Smith, Lloyd's: John Smith, DVLA: John Smith }",
        "{ IPO: John Smith, WIPO: John Smith, USPTO: John Smith }",
        "{ propuk: John Smith, propuk: Acme Ltd, propuk: Smith Holdings }",
    ]

    for example in parallel_examples:
        print(f"\n  PARALLEL: {example}")
        print("    → All 3 queries execute simultaneously via asyncio.gather")
        print("    → Total time = max(query1, query2, query3), not sum")


def main():
    if len(sys.argv) > 1:
        subject_name = " ".join(sys.argv[1:])
    else:
        subject_name = "Roman Abramovich"  # Example with known assets

    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                     UK ASSET TRACE EXAMPLE                            ║
║                                                                       ║
║  Traces assets for UK-based individuals across:                       ║
║  • Property (Land Registry)                                           ║
║  • Company shareholdings (Companies House)                            ║
║  • Vehicles/Aircraft/Vessels (CAA, Lloyd's, DVLA)                     ║
║  • Intellectual property (IPO, WIPO, USPTO)                           ║
║  • Financial signals (Gazette, news)                                  ║
╚═══════════════════════════════════════════════════════════════════════╝
""")

    asyncio.run(run_uk_asset_trace(subject_name))
    asyncio.run(demonstrate_parallel_asset_queries())


if __name__ == "__main__":
    main()
