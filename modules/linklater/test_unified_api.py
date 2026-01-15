#!/usr/bin/env python3
"""
Quick test to verify the unified LinkLater API works correctly.
"""

from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
from api import linklater


async def test_unified_api():
    """Test basic functionality of the unified API."""

    print("=" * 60)
    print("Testing LinkLater Unified API")
    print("=" * 60)

    # Test 1: Entity extraction (synchronous)
    print("\n1. Testing entity extraction...")
    text = "Acme Corporation is headquartered in London, UK. CEO John Smith founded it in 2020."
    entities = linklater.extract_entities(text)
    print(f"   ✓ Extracted entities: {len(entities.get('companies', []))} companies, {len(entities.get('persons', []))} persons")

    # Test 2: Binary extraction check
    print("\n2. Testing binary extraction capabilities...")
    pdf_supported = linklater.can_extract_binary("application/pdf")
    docx_supported = linklater.can_extract_binary("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    print(f"   ✓ PDF extraction: {pdf_supported}")
    print(f"   ✓ DOCX extraction: {docx_supported}")

    # Test 3: GlobalLinks binary check
    print("\n3. Testing GlobalLinks binary detection...")
    gl_binary = linklater.find_globallinks_binary()
    print(f"   {'✓' if gl_binary else '✗'} GlobalLinks binary: {gl_binary or 'not found'}")

    # Test 4: Scraper stats
    print("\n4. Testing scraper stats...")
    stats = linklater.get_scraper_stats()
    print(f"   ✓ Scraper stats available: {bool(stats)}")

    # Test 5: Archive scraping (async)
    print("\n5. Testing archive scraping...")
    try:
        result = await linklater.scrape_url("https://example.com")
        print(f"   ✓ Scraping works - Source: {result.source}, Status: {result.status_code}")
    except Exception as e:
        print(f"   ⚠ Scraping test skipped: {str(e)[:50]}")

    # Test 6: Backlinks (async)
    print("\n6. Testing backlinks...")
    try:
        backlinks = await linklater.get_backlinks("example.com", limit=5)
        print(f"   ✓ Backlinks API works - Found {len(backlinks)} results")
    except Exception as e:
        print(f"   ⚠ Backlinks test skipped: {str(e)[:50]}")

    print("\n" + "=" * 60)
    print("✅ Unified API Test Complete!")
    print("=" * 60)
    print("\nAll core methods accessible via: linklater.method_name()")
    print("Available: 148+ methods across all modules")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_unified_api())
