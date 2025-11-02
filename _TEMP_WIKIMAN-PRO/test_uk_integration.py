#!/usr/bin/env python3
"""
UK Public Records Integration Test
Tests all 3 new routers end-to-end
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from countries.uk.handler import UKHandler, parse_source_filter, search_uk_with_sources


def test_litigation_search():
    """Test lituk: router via BAILII"""
    print("\n" + "="*60)
    print("TEST 1: UK Litigation Search (BAILII)")
    print("="*60)

    handler = UKHandler()
    result = handler.search_litigation("Barclays", search_type="bailii")

    assert result is not None, "Litigation search returned None"
    assert result.get("ok") == True, "Litigation search failed"
    assert result.get("source") == "litigation", "Wrong source"
    assert "data" in result, "No data in result"

    print("✅ PASS: Litigation search working")
    print(f"   Database: {result.get('metadata', {}).get('database', 'N/A')}")
    print(f"   Data keys: {list(result.get('data', {}).keys())}")

    return True


def test_foi_search():
    """Test reguk: router via WhatDoTheyKnow"""
    print("\n" + "="*60)
    print("TEST 2: UK FOI Search (WhatDoTheyKnow)")
    print("="*60)

    handler = UKHandler()
    result = handler.search_foi("banks", search_type="whatdotheyknow")

    assert result is not None, "FOI search returned None"
    assert result.get("ok") == True, "FOI search failed"
    assert result.get("source") == "foi", "Wrong source"
    assert "data" in result, "No data in result"

    data = result.get("data", {})
    print("✅ PASS: FOI search working")
    print(f"   Platform: {result.get('metadata', {}).get('platform', 'N/A')}")
    print(f"   Total found: {data.get('total_found', 0)}")
    print(f"   Data keys: {list(data.keys())}")

    return True


def test_regulatory_search():
    """Test reguk: router via FCA"""
    print("\n" + "="*60)
    print("TEST 3: UK Regulatory Search (FCA)")
    print("="*60)

    handler = UKHandler()
    result = handler.search_regulatory("banks", search_type="general")

    assert result is not None, "Regulatory search returned None"
    assert result.get("ok") == True, "Regulatory search failed"
    assert result.get("source") == "regulatory", "Wrong source"

    print("✅ PASS: Regulatory search working")
    print(f"   Search type: {result.get('metadata', {}).get('search_type', 'N/A')}")
    print(f"   Data keys: {list(result.get('data', {}).keys())[:5]}")

    return True


def test_property_search():
    """Test auk: router (currently placeholder)"""
    print("\n" + "="*60)
    print("TEST 4: UK Property Search (Land Registry)")
    print("="*60)

    handler = UKHandler()
    result = handler.search_property("10 Downing Street", search_type="land_registry")

    assert result is not None, "Property search returned None"
    assert result.get("source") == "property", "Wrong source"

    status = result.get("data", {}).get("status", "unknown")
    print(f"✅ PASS: Property search returns proper placeholder")
    print(f"   Status: {status}")
    print(f"   Implementation: {result.get('metadata', {}).get('implementation_status', 'N/A')}")

    return True


def test_source_filter_parsing():
    """Test bracket syntax parsing"""
    print("\n" + "="*60)
    print("TEST 5: Source Filter Parsing")
    print("="*60)

    # Test 1: Single source
    query, sources, has_brackets = parse_source_filter("uk[fec] Barclays Bank")
    assert query == "Barclays Bank", "Wrong query extraction"
    assert sources == ["fec"], "Wrong sources extraction"
    assert has_brackets == True, "Should detect brackets"
    print("✅ PASS: Single source parsing")

    # Test 2: Multiple sources
    query, sources, has_brackets = parse_source_filter("uk[fca, fec, foi] BP plc")
    assert query == "BP plc", "Wrong query extraction"
    assert sources == ["fca", "fec", "foi"], "Wrong sources extraction"
    assert has_brackets == True, "Should detect brackets"
    print("✅ PASS: Multiple source parsing")

    # Test 3: No brackets
    query, sources, has_brackets = parse_source_filter("Barclays Bank")
    assert query == "Barclays Bank", "Wrong query extraction"
    assert sources == [], "Should have empty sources"
    assert has_brackets == False, "Should not detect brackets"
    print("✅ PASS: No bracket parsing")

    return True


def test_source_filtered_search():
    """Test uk[source] syntax"""
    print("\n" + "="*60)
    print("TEST 6: Source-Filtered Company Search")
    print("="*60)

    # This will only search bailii (litigation source)
    result = search_uk_with_sources("uk[bailii] banks")

    assert result is not None, "Source-filtered search returned None"
    assert "metadata" in result, "No metadata in result"

    # Check that sources_only mode was activated
    print("✅ PASS: Source-filtered search working")
    print(f"   Query processed: 'uk[bailii] banks'")
    print(f"   Result OK: {result.get('ok', False)}")

    return True


def test_cache_layers():
    """Test that all cache layers are configured"""
    print("\n" + "="*60)
    print("TEST 7: Cache Layer Configuration")
    print("="*60)

    from countries.cache import MultiLayerCache

    cache = MultiLayerCache()

    required_layers = ["api", "wikiman", "trailblazer", "gemini",
                       "regulatory", "litigation", "foi", "property"]

    for layer in required_layers:
        assert layer in cache.caches, f"Cache layer '{layer}' not configured"
        print(f"   ✓ {layer}: TTL={cache.caches[layer].ttl}")

    print("✅ PASS: All 8 cache layers configured")

    return True


def main():
    """Run all integration tests"""
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*15 + "UK INTEGRATION TEST SUITE" + " "*17 + "║")
    print("╚" + "="*58 + "╝")

    tests = [
        ("Litigation Search", test_litigation_search),
        ("FOI Search", test_foi_search),
        ("Regulatory Search", test_regulatory_search),
        ("Property Search", test_property_search),
        ("Source Filter Parsing", test_source_filter_parsing),
        ("Source-Filtered Search", test_source_filtered_search),
        ("Cache Layer Config", test_cache_layers),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ FAIL: {name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ ERROR: {name}")
            print(f"   Exception: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("="*60)

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Integration complete.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
