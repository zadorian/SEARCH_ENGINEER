#!/usr/bin/env python3
"""
Corporella Claude - Example Usage
Demonstrates how to use all 4 components together
"""

import asyncio
import json
from finder import CompanyFinder
from fetcher import GlobalCompanyFetcher
from populator import CorporateEntityPopulator


async def example_1_simple_search():
    """
    Example 1: Simple company search using Finder only
    """
    print("\n" + "="*60)
    print("EXAMPLE 1: Simple Search with Finder")
    print("="*60)

    finder = CompanyFinder()

    # Search by company name
    print("\n1. Searching for 'Apple Inc'...")
    results = finder.search_by_name("Apple Inc", jurisdiction="us_ca")

    if results["ok"]:
        print(f"   ✓ Found {results['total_count']} companies")
        for i, company in enumerate(results['companies'][:3], 1):
            print(f"\n   {i}. {company['name']}")
            print(f"      Number: {company['company_number']}")
            print(f"      Status: {company['current_status']}")
            print(f"      Jurisdiction: {company['jurisdiction_code']}")
    else:
        print(f"   ✗ Error: {results['error']}")


async def example_2_parallel_search():
    """
    Example 2: Parallel multi-source search using Fetcher
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: Parallel Multi-Source Search")
    print("="*60)

    fetcher = GlobalCompanyFetcher()

    print("\n2. Searching across all sources for 'Apple Inc'...")
    results = await fetcher.parallel_search("Apple Inc", country_code="us")

    print(f"\n   ✓ Completed in {results['processing_time']:.2f}s")
    print(f"   ✓ Retrieved data from {len(results['sources_used'])} sources:")

    for source in results['sources_used']:
        exec_time = results['execution_times'].get(source, 0)
        print(f"      - {source} ({exec_time:.2f}s)")

    if results['errors']:
        print(f"\n   ⚠️  {len(results['errors'])} sources had errors:")
        for error in results['errors']:
            print(f"      - {error['source']}: {error['error']}")

    # Show raw results summary
    print(f"\n   Raw Results:")
    for result in results['raw_results']:
        source = result.get('source', 'unknown')
        if source == "opencorporates" and result.get('companies'):
            print(f"\n   OpenCorporates:")
            for company in result['companies'][:2]:
                print(f"      - {company.get('name')}")
                print(f"        Number: {company.get('company_number')}")


async def example_3_ai_merging():
    """
    Example 3: AI-powered entity merging with Claude Haiku 4.5
    """
    print("\n" + "="*60)
    print("EXAMPLE 3: AI-Powered Entity Merging (Hybrid Processing)")
    print("="*60)

    fetcher = GlobalCompanyFetcher()
    populator = CorporateEntityPopulator()

    print("\n3. Fetching data and merging with Claude Haiku 4.5...")

    # Get raw results
    results = await fetcher.parallel_search("Apple Inc", country_code="us")

    print(f"\n   FAST PATH: Raw results retrieved in {results['processing_time']:.2f}s")
    print(f"              User sees data immediately")

    print(f"\n   SMART PATH: Processing with Claude Haiku 4.5...")

    # Process each result with Haiku
    merged_entity = None
    for i, raw_result in enumerate(results['raw_results'], 1):
        source = raw_result.get('source')
        print(f"      {i}. Merging {source} data...")

        merged_entity = await populator.process_streaming_result(raw_result)

    # Show final merged entity
    print(f"\n   ✓ Final merged entity:")
    if merged_entity:
        name = merged_entity.get('name', {})
        if isinstance(name, dict):
            print(f"      Name: {name.get('value', 'N/A')}")
        else:
            print(f"      Name: {name}")

        about = merged_entity.get('about', {})
        print(f"      Jurisdiction: {about.get('jurisdiction', 'N/A')}")
        print(f"      Company Number: {about.get('company_number', 'N/A')}")

        sources = merged_entity.get('_sources', [])
        print(f"      Sources: {', '.join(sources)}")

        # Check for contradictions
        contradictions = merged_entity.get('_contradictions', [])
        if contradictions:
            print(f"\n      ⚠️  {len(contradictions)} contradictions detected:")
            for contradiction in contradictions:
                print(f"          - {contradiction}")


async def example_4_complete_workflow():
    """
    Example 4: Complete workflow showing all components
    """
    print("\n" + "="*60)
    print("EXAMPLE 4: Complete Workflow (All Components)")
    print("="*60)

    print("\n4. Complete company intelligence workflow...")

    # Step 1: Quick validation
    print("\n   Step 1: Quick validation with Finder")
    finder = CompanyFinder()
    quick_check = finder.search_by_name("Microsoft", per_page=1)

    if not quick_check["ok"] or quick_check["total_count"] == 0:
        print("      ✗ Company not found")
        return

    print(f"      ✓ Found {quick_check['total_count']} matches")

    # Step 2: Parallel fetch
    print("\n   Step 2: Parallel fetch from all sources")
    fetcher = GlobalCompanyFetcher()
    results = await fetcher.parallel_search("Microsoft Corporation")

    print(f"      ✓ Fetched from {len(results['sources_used'])} sources")

    # Step 3: AI merging
    print("\n   Step 3: AI-powered merging with Claude Haiku 4.5")
    populator = CorporateEntityPopulator()

    merged_entity = None
    for raw_result in results['raw_results']:
        merged_entity = await populator.process_streaming_result(raw_result)

    print(f"      ✓ Entity merged and deduplicated")

    # Step 4: Display final profile
    print("\n   Step 4: Final company profile")
    if merged_entity:
        print("\n      " + "="*50)
        print(json.dumps(merged_entity, indent=6))
        print("      " + "="*50)


async def main():
    """
    Run all examples
    """
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "    CORPORELLA CLAUDE - USAGE EXAMPLES".center(58) + "║")
    print("║" + "    Ultimate Global Company Search".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")

    try:
        # Run examples sequentially
        await example_1_simple_search()

        input("\n\nPress Enter to continue to Example 2...")
        await example_2_parallel_search()

        input("\n\nPress Enter to continue to Example 3...")
        await example_3_ai_merging()

        input("\n\nPress Enter to continue to Example 4...")
        await example_4_complete_workflow()

    except KeyboardInterrupt:
        print("\n\n✗ Examples interrupted")
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n\n" + "="*60)
    print("Examples complete!")
    print("\nNext steps:")
    print("1. Start WebSocket server: python websocket_server.py")
    print("2. Open client.html in your browser")
    print("3. Start searching for companies!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
