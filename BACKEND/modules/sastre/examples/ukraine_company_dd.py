#!/usr/bin/env python3
"""
UKRAINE COMPANY DUE DILIGENCE - Complete End-to-End Example

Template: COMPANY_DD
Jurisdiction: UA (Ukraine)
Entity Type: Company

This demonstrates Ukraine-specific DD across:
- EDR (Unified State Register / Єдиний державний реєстр)
- Court decisions (судові рішення)
- Sanctions lists (NSDC, EU, OFAC)
- Property registry (державний реєстр речових прав)
- Beneficial ownership (бенефіціарні власники)

UKRAINE-SPECIFIC OPERATORS:
1. cua: [COMPANY]                → EDR company lookup
2. pua: [PERSON]                 → Ukrainian person search
3. court_ua: [NAME]              → Court registry search
4. sanction: [NAME] ##UA         → NSDC sanctions check
5. propua: [NAME]                → Property registry
6. { a, b, c } in parallel       → True parallel via asyncio.gather

SOURCES:
- data.gov.ua                    → Open data portal
- court.gov.ua                   → Court decisions
- edr.data.gov.ua                → Company registry
- youcontrol.com.ua              → Commercial aggregator
- opendatabot.ua                 → Alternative data provider

USAGE:
    python examples/ukraine_company_dd.py "Нафтогаз України"
    python examples/ukraine_company_dd.py "Приватбанк"
    python examples/ukraine_company_dd.py "Burisma Holdings"
"""

import asyncio
import sys
from pathlib import Path

# Add paths
SASTRE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = SASTRE_DIR.parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SASTRE_DIR))


# Ukraine-specific DD sections
UA_COMPANY_DD_SECTIONS = [
    "EXECUTIVE_SUMMARY",
    "COMPANY_IDENTIFICATION",         # ЄДРПОУ code, registration
    "OWNERSHIP_STRUCTURE",            # Beneficial owners (бенефіціари)
    "DIRECTORS_OFFICERS",             # Керівництво
    "RELATED_PARTIES",                # Пов'язані особи
    "LITIGATION_HISTORY",             # Судові справи
    "SANCTIONS_SCREENING",            # NSDC, EU, OFAC, UN
    "FINANCIAL_CONDITION",            # Financial statements
    "PROPERTY_ASSETS",                # Real property, vehicles
    "REGULATORY_COMPLIANCE",          # Licenses, permits
    "MEDIA_ADVERSE_FINDINGS",         # Ukrainian + international media
    "WAR_RELATED_RISKS",              # Post-2022 considerations
    "RESEARCH_LIMITATIONS",
]

# Ukraine-specific actions
UA_ACTIONS = [
    "SEARCH_EDR",                     # Unified State Register
    "SEARCH_BENEFICIAL_OWNERS",       # UBO registry
    "SEARCH_COURTS",                  # Court decisions
    "SEARCH_SANCTIONS",               # NSDC + international
    "SEARCH_PROPERTY",                # Property registry
    "SEARCH_LICENSES",                # Regulatory permits
    "SEARCH_PROCUREMENT",             # ProZorro (public procurement)
    "SEARCH_MEDIA",                   # Ukrainian news sources
    "SEARCH_ARCHIVE",                 # web.archive.org for historical
]


async def run_ukraine_company_dd(company_name: str):
    """
    Execute Ukraine Company DD using template operator.
    """
    from executor import UnifiedExecutor

    print("=" * 70)
    print(f"UKRAINE COMPANY DUE DILIGENCE: {company_name}")
    print("=" * 70)

    executor = UnifiedExecutor()

    # Build template query
    entity_tag = company_name.replace(" ", "_").replace(".", "").replace("'", "")
    query = f"template:company_dd:UA :#{entity_tag}"

    print(f"\n[QUERY] {query}\n")

    # Execute template
    result = await executor.execute(query, project_id="ukraine_dd")

    if "error" in result:
        print(f"[ERROR] {result['error']}")
        return result

    # Display results
    print("\n[TEMPLATE LOADED]")
    print(f"  Genre: {result.get('genre')}")
    print(f"  Jurisdiction: {result.get('jurisdiction')}")
    print(f"  Entity: {result.get('entity')}")

    sections = result.get("sections", [])
    print(f"\n[DD SECTIONS] ({len(sections)})")
    for section in sections:
        print(f"  • {section}")

    # Now show the Ukraine-specific query chain
    print("\n[EXECUTING UKRAINE-SPECIFIC SEARCHES]")

    # Phase 1: Company Identification (EDR)
    print("\n  Phase 1: Company Identification (EDR)")
    id_queries = [
        f"cua: {company_name}",                     # EDR lookup
        f'site:edr.data.gov.ua "{company_name}"',   # Direct EDR search
        f'site:youcontrol.com.ua "{company_name}"', # Commercial aggregator
    ]
    for q in id_queries:
        print(f"    → {q}")

    # Phase 2: Beneficial Ownership
    print("\n  Phase 2: Beneficial Ownership (Бенефіціари)")
    ubo_queries = [
        f"ubo_ua: {company_name}",                  # UBO registry
        f'site:data.gov.ua beneficiary "{company_name}"',
    ]
    for q in ubo_queries:
        print(f"    → {q}")

    # Phase 3: Directors & Officers
    print("\n  Phase 3: Directors & Officers (Керівництво)")
    officer_query = f"p? @OFFICERS :#{entity_tag}"  # Extract from EDR result
    print(f"    → {officer_query}")

    # Phase 4: Litigation (Courts - PARALLEL)
    print("\n  Phase 4: Litigation (Судові справи) - PARALLEL")
    court_query = f'{{ court_ua: {company_name}, reyestr.court.gov.ua: "{company_name}" }}'
    print(f"    → {court_query}")

    # Phase 5: Sanctions Screening (PARALLEL)
    print("\n  Phase 5: Sanctions Screening - PARALLEL")
    sanctions_query = f'''{{
        sanction: {company_name} ##UA,
        sanction: {company_name} ##EU,
        sanction: {company_name} ##OFAC,
        sanction: {company_name} ##UN
    }}'''
    print(f"    → NSDC, EU, OFAC, UN in parallel")

    # Phase 6: Property & Assets
    print("\n  Phase 6: Property & Assets (Майно)")
    property_queries = [
        f"propua: {company_name}",                  # Property registry
        f'site:kap.minjust.gov.ua "{company_name}"', # Encumbrances registry
    ]
    for q in property_queries:
        print(f"    → {q}")

    # Phase 7: Procurement (ProZorro)
    print("\n  Phase 7: Public Procurement (ProZorro)")
    prozorro_query = f'site:prozorro.gov.ua "{company_name}"'
    print(f"    → {prozorro_query}")

    # Phase 8: Media & Adverse
    print("\n  Phase 8: Media Screening (PARALLEL)")
    media_query = f'''{{
        "{company_name}" site:pravda.com.ua,
        "{company_name}" site:liga.net,
        "{company_name}" corruption OR scandal OR investigation
    }}'''
    print(f"    → Ukrainian media + adverse terms")

    # Phase 9: War-Related Risks (post-2022)
    print("\n  Phase 9: War-Related Risk Assessment")
    war_queries = [
        f'"{company_name}" occupied territory OR Crimea OR Donbas',
        f'"{company_name}" Russia sanctions evasion',
        f'"{company_name}" site:war.sanctions.com',
    ]
    for q in war_queries:
        print(f"    → {q}")

    # Phase 10: Historical (Wayback)
    print("\n  Phase 10: Historical Archive Search")
    archive_query = f'"{company_name}":?youcontrol.com.ua'  # Wayback for historical
    print(f"    → {archive_query}")

    # Summary
    print("\n" + "=" * 70)
    print("UKRAINE DD SUMMARY")
    print("=" * 70)
    print(f"""
  Subject: {company_name}
  Jurisdiction: UA (Ukraine)

  Searches Planned:
    • EDR Identification: 3 queries
    • Beneficial Ownership: 2 queries
    • Directors/Officers: 1 query (extraction)
    • Court Decisions: 2 queries - PARALLEL
    • Sanctions: 4 queries (NSDC, EU, OFAC, UN) - PARALLEL
    • Property: 2 queries
    • ProZorro: 1 query
    • Media: 3 queries - PARALLEL
    • War Risks: 3 queries
    • Archive: 1 query

  Total: 22 queries (12 parallel groups)

  Template Sections: {len(sections)}
  Ukraine Sources Used:
    • data.gov.ua (Open Data)
    • edr.data.gov.ua (EDR)
    • reyestr.court.gov.ua (Courts)
    • prozorro.gov.ua (Procurement)
    • youcontrol.com.ua (Commercial)
    • pravda.com.ua, liga.net (Media)
""")

    return result


async def demonstrate_ukraine_operators():
    """Show Ukraine-specific operators."""
    print("\n" + "=" * 70)
    print("UKRAINE-SPECIFIC OPERATORS")
    print("=" * 70)

    operators = [
        ("cua:", "Company lookup in EDR (Unified State Register)"),
        ("pua:", "Person search in Ukrainian registries"),
        ("court_ua:", "Court decision search (reyestr.court.gov.ua)"),
        ("sanction: ##UA", "NSDC sanctions list check"),
        ("propua:", "Property registry search"),
        ("ubo_ua:", "Beneficial ownership registry"),
        ("prozorro:", "Public procurement search"),
    ]

    for op, desc in operators:
        print(f"\n  {op}")
        print(f"    → {desc}")

    print("\n  PARALLEL EXECUTION:")
    print("    { cua: Company, court_ua: Company, sanction: Company ##UA }")
    print("    → All 3 execute simultaneously via asyncio.gather")


def main():
    if len(sys.argv) > 1:
        company_name = " ".join(sys.argv[1:])
    else:
        company_name = "Нафтогаз України"  # Naftogaz - major state company

    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                   UKRAINE COMPANY DD EXAMPLE                          ║
║                                                                       ║
║  Investigates Ukrainian companies across:                             ║
║  • EDR (Unified State Register / ЄДРПОУ)                              ║
║  • Court decisions (reyestr.court.gov.ua)                             ║
║  • Sanctions (NSDC, EU, OFAC, UN)                                     ║
║  • Property registry                                                  ║
║  • ProZorro (public procurement)                                      ║
║  • War-related risk assessment                                        ║
╚═══════════════════════════════════════════════════════════════════════╝
""")

    asyncio.run(run_ukraine_company_dd(company_name))
    asyncio.run(demonstrate_ukraine_operators())


if __name__ == "__main__":
    main()
