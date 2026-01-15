#!/usr/bin/env python3
"""
Test all LinkLater backlink pipelines
Majestic confirmed working - test the rest
"""
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
import sys
from pathlib import Path

# Add parent modules directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Test domain - USE REAL DOMAIN
TEST_DOMAIN = "soax.com"

async def test_cc_graph():
    """Test 1: CC Web Graph (Elasticsearch)"""
    print("\n" + "="*60)
    print("TEST 1: CC Web Graph (Elasticsearch - SHOULD BE INSTANT)")
    print("="*60)
    try:
        from linklater.linkgraph.cc_graph_es import CCGraphESClient
        client = CCGraphESClient()

        # Test stats first
        stats = await client.get_stats()
        print(f"   ES Index stats: {stats.get('edges_count', 0):,} edges")

        # Test backlinks
        results = await client.get_backlinks(TEST_DOMAIN, limit=10)
        await client.close()

        print(f"✅ SUCCESS: Got {len(results)} backlinks")
        if results:
            print(f"   Sample: {results[0].source} → {results[0].target} (weight: {results[0].weight})")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_globallinks():
    """Test 2: GlobalLinks"""
    print("\n" + "="*60)
    print("TEST 2: GlobalLinks (Page-Level)")
    print("="*60)
    try:
        from linklater.linkgraph import GlobalLinksClient
        client = GlobalLinksClient()

        # Check binary
        if not client.outlinker:
            print(f"❌ FAILED: outlinker binary not found")
            print(f"   Expected locations:")
            print(f"   - categorizer-filterer/globallinks/globallinks-with-outlinker/bin/outlinker")
            print(f"   - globallinks/bin/outlinker")
            return False

        print(f"   ✅ Binary found: {client.outlinker}")

        # Test get_outlinks (extracts from CC archives)
        print("   Testing extract_outlinks...")
        results = await client.get_outlinks(TEST_DOMAIN, limit=5, archive="CC-MAIN-2024-10")
        print(f"✅ SUCCESS: Got {len(results)} outlinks")
        if results:
            print(f"   Sample: {results[0].source} → {results[0].target}")
            if results[0].anchor_text:
                print(f"   Anchor: {results[0].anchor_text}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_tor_bridges():
    """Test 3: Tor Bridges"""
    print("\n" + "="*60)
    print("TEST 3: Tor Bridges (Onion↔Clearnet)")
    print("="*60)
    try:
        from linklater.linkgraph import TorBridgesClient
        client = TorBridgesClient()

        # Test stats first
        stats = await client.get_bridge_stats()
        print(f"   Index stats: {stats}")

        if stats.get('total_bridges', 0) == 0:
            print(f"⚠️  WARNING: tor-bridges index is empty")
            return False

        # Test reverse lookup
        results = await client.get_bridges_to_clearnet(TEST_DOMAIN, limit=5)
        print(f"✅ SUCCESS: Got {len(results)} bridges")
        if results:
            print(f"   Sample: {results[0].source} → {results[0].target}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_go_bridge():
    """Test 4: Go Bridge / LinksAPI"""
    print("\n" + "="*60)
    print("TEST 4: Go Bridge (Local DB)")
    print("="*60)
    try:
        from linklater.drill.go_bridge import GoBridge
        bridge = GoBridge()

        if not bridge.is_available("linksapi"):
            print(f"⚠️  WARNING: linksapi binary not found")
            return False

        print(f"   ✅ Binary found, testing query...")
        results = await bridge.query_backlinks(TEST_DOMAIN, limit=10)
        print(f"✅ SUCCESS: Got {len(results)} results")
        if results:
            print(f"   Sample: {results[0]}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_production_pipeline():
    """Test 5: Production Pipeline (Combined)"""
    print("\n" + "="*60)
    print("TEST 5: Production Pipeline (CC Graph + GlobalLinks)")
    print("="*60)
    try:
        from linklater.pipelines.production_backlink_discovery import ProductionBacklinkPipeline

        pipeline = ProductionBacklinkPipeline(
            target_domain=TEST_DOMAIN,
            max_backlinks_per_source=20
        )

        results = await pipeline.discover_backlinks(
            max_results=50,
            include_majestic=False,  # Skip Majestic (already tested)
            include_cc_scan=False     # Skip deep scan (slow)
        )

        print(f"✅ SUCCESS: Combined pipeline completed")
        print(f"   CC Graph: {len(results.get('cc_graph', []))} results")
        print(f"   GlobalLinks: {len(results.get('globallinks', []))} results")
        print(f"   Combined: {len(results.get('combined', []))} unique")
        print(f"   Summary: {results.get('summary', {})}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_automated_pipeline():
    """Test 6: Automated Pipeline (Advanced)"""
    print("\n" + "="*60)
    print("TEST 6: Automated Pipeline (Entities + PDFs)")
    print("="*60)
    try:
        from linklater.pipelines.automated_backlink_pipeline import AutomatedBacklinkPipeline

        pipeline = AutomatedBacklinkPipeline(
            target_domain=TEST_DOMAIN,
            extract_entities=True,
            max_entity_pages=5,  # Small test
            entity_method="gpt5nano",
            discover_pdfs=False,  # Skip PDF discovery for speed
        )

        results = await pipeline.run()

        print(f"✅ SUCCESS: Automated pipeline completed")
        print(f"   Backlinks: {len(results.get('backlinks', []))}")
        print(f"   Entities: {results.get('entities', {})}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("="*60)
    print("LINKLATER BACKLINK PIPELINE TEST SUITE")
    print("="*60)
    print(f"Test domain: {TEST_DOMAIN}")
    print(f"Majestic: ✅ Already confirmed working")

    tests = [
        ("CC Graph", test_cc_graph),
        ("GlobalLinks", test_globallinks),
        ("Tor Bridges", test_tor_bridges),
        ("Go Bridge", test_go_bridge),
        ("Production Pipeline", test_production_pipeline),
        ("Automated Pipeline", test_automated_pipeline),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = await test_func()
        except Exception as e:
            print(f"❌ FATAL ERROR in {name}: {e}")
            results[name] = False

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("Majestic:            ✅ WORKING (confirmed)")
    for name, passed in results.items():
        status = "✅ WORKING" if passed else "❌ FAILED"
        print(f"{name:20s} {status}")

    total = len(results) + 1  # +1 for Majestic
    passed = sum(results.values()) + 1  # +1 for Majestic
    print(f"\nTotal: {passed}/{total} pipelines working")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
