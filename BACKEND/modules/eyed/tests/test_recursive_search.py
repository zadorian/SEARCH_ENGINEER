#!/usr/bin/env python3
"""
Test script for EYE-D Recursive Search with Priority Queues

This demonstrates the VERIFIED-first recursive search strategy.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from unified_osint import UnifiedSearcher


async def test_recursive_search():
    """Test recursive search with a sample entity"""

    print("=" * 80)
    print("EYE-D RECURSIVE SEARCH TEST")
    print("=" * 80)
    print()

    # Initialize searcher
    searcher = UnifiedSearcher()

    # Check if C1Bridge is available
    if not searcher.c1_bridge:
        print("❌ C1Bridge not available. Cannot test recursive search.")
        print("   Make sure Elasticsearch is running and c1_bridge.py is properly configured.")
        return

    # Test entity (you can change this to any email, phone, or username)
    test_query = "test@example.com"  # Change this to a real entity for testing
    project_id = "test_project_001"  # Change this to your project ID
    max_depth = 2  # Limit depth for testing

    print(f"Test Configuration:")
    print(f"  Query: {test_query}")
    print(f"  Project ID: {project_id}")
    print(f"  Max Depth: {max_depth}")
    print()

    # Run recursive search
    try:
        summary = await searcher.search_with_recursion(
            initial_query=test_query,
            project_id=project_id,
            max_depth=max_depth
        )

        print("\n" + "=" * 80)
        print("RECURSIVE SEARCH SUMMARY")
        print("=" * 80)
        print(f"Total Searches: {summary.get('total_searches', 0)}")
        print(f"VERIFIED Searches: {summary.get('verified_searches', 0)}")
        print(f"UNVERIFIED Searches: {summary.get('unverified_searches', 0)}")
        print(f"Final Depth: {summary.get('final_depth', 0)}")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during recursive search: {e}")
        import traceback
        traceback.print_exc()


async def test_priority_queues():
    """Test priority queue building"""

    print("=" * 80)
    print("PRIORITY QUEUE TEST")
    print("=" * 80)
    print()

    searcher = UnifiedSearcher()

    if not searcher.c1_bridge:
        print("❌ C1Bridge not available. Cannot test priority queues.")
        return

    project_id = "test_project_001"  # Change this to your project ID

    print(f"Building priority queues for project: {project_id}\n")

    try:
        verified_queue, unverified_queue = searcher.c1_bridge.get_priority_queues(project_id)

        print(f"✓ VERIFIED Queue: {len(verified_queue)} entities")
        if verified_queue:
            print(f"  First 5: {verified_queue[:5]}")

        print(f"\n✓ UNVERIFIED Queue: {len(unverified_queue)} entities")
        if unverified_queue:
            print(f"  First 5: {[f'{val} ({tag})' for val, tag in unverified_queue[:5]]}")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Error building priority queues: {e}")
        import traceback
        traceback.print_exc()


async def test_tag_increment():
    """Test sequence tag incrementing"""

    print("=" * 80)
    print("TAG INCREMENT TEST")
    print("=" * 80)
    print()

    searcher = UnifiedSearcher()

    if not searcher.c1_bridge:
        print("❌ C1Bridge not available. Cannot test tag increment.")
        return

    print("Testing tag increment logic:\n")

    test_cases = [
        ("john_smith", "email@address.com_1", "email@address.com_2"),
        ("phone_number", "john_smith_2", "john_smith_3"),
        ("username", "phone_number_3", "phone_number_4"),
    ]

    for entity, current_tag, expected in test_cases:
        result = searcher.c1_bridge.increment_sequence_tag(entity, current_tag)
        status = "✓" if result == expected else "✗"
        print(f"{status} {current_tag} → {result} (expected: {expected})")

    print("\n" + "=" * 80)


async def main():
    """Main test runner"""

    print("\n")
    print("█" * 80)
    print("  EYE-D RECURSIVE SEARCH - TEST SUITE")
    print("█" * 80)
    print()

    # Test 1: Tag Increment
    await test_tag_increment()
    print()

    # Test 2: Priority Queues
    await test_priority_queues()
    print()

    # Test 3: Full Recursive Search
    print("NOTE: For full recursive search test, you need:")
    print("  1. Elasticsearch running with cymonides-1 index")
    print("  2. A project with tagged entities")
    print("  3. Update test_query and project_id in the script")
    print()

    response = input("Do you want to run the full recursive search test? (y/n): ")
    if response.lower() == 'y':
        await test_recursive_search()
    else:
        print("Skipping full recursive search test.")

    print("\n")
    print("█" * 80)
    print("  TEST SUITE COMPLETE")
    print("█" * 80)
    print()


if __name__ == "__main__":
    asyncio.run(main())
