#!/usr/bin/env python3
"""
Test Majestic Integration in LinkLater Unified API
"""
from __future__ import annotations

if __name__ != "__main__":
    import pytest

    pytest.skip("LINKLATER test scripts are manual/integration; run directly", allow_module_level=True)

import asyncio
import sys
from pathlib import Path

# Add module to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.linklater.api import linklater


async def test_majestic_integration():
    """Test the new get_majestic_backlinks() method."""

    print("=" * 80)
    print("MAJESTIC INTEGRATION TEST - LinkLater Unified API")
    print("=" * 80)

    domain = "seb.se"
    print(f"\n🔍 Testing Majestic backlinks for: {domain}")
    print("-" * 80)

    try:
        # Test 1: Fresh index, referring domains
        print("\n1️⃣  Fresh Index - Referring Domains (limit 10)")
        print("-" * 40)

        domains = await linklater.get_majestic_backlinks(
            domain,
            mode="fresh",
            result_type="domains",
            max_results=10
        )

        print(f"✅ Found {len(domains)} referring domains")
        for i, d in enumerate(domains[:5], 1):
            print(f"   {i}. {d.get('source_domain')} (TF:{d.get('trust_flow')} CF:{d.get('citation_flow')})")

        if len(domains) > 5:
            print(f"   ... and {len(domains) - 5} more")

        # Test 2: Fresh index, backlink pages with anchor text
        print("\n2️⃣  Fresh Index - Backlink Pages (limit 10)")
        print("-" * 40)

        pages = await linklater.get_majestic_backlinks(
            domain,
            mode="fresh",
            result_type="pages",
            max_results=10
        )

        print(f"✅ Found {len(pages)} backlink pages")
        for i, p in enumerate(pages[:5], 1):
            anchor = p.get('anchor_text', '')[:50]
            print(f"   {i}. {p.get('source_domain')}")
            print(f"      Anchor: \"{anchor}\"")
            print(f"      TLD: {p.get('source_tld')}")

        if len(pages) > 5:
            print(f"   ... and {len(pages) - 5} more")

        # Test 3: Search anchor texts for keywords
        print("\n3️⃣  Anchor Text Search - Libyan Keywords")
        print("-" * 40)

        libyan_keywords = ['libya', 'libyan', 'tripoli', 'benghazi', '.ly', 'lia']

        matches = [
            p for p in pages
            if any(kw.lower() in p.get('anchor_text', '').lower() for kw in libyan_keywords)
        ]

        if matches:
            print(f"🚨 Found {len(matches)} matches!")
            for m in matches:
                print(f"   - {m.get('source_domain')}: \"{m.get('anchor_text')}\"")
        else:
            print("✅ No Libyan keywords found in anchor texts (expected)")

        # Test 4: Filter by country TLD
        print("\n4️⃣  Country TLD Filter - Libya/Russia/Iceland")
        print("-" * 40)

        target_tlds = ['.ly', '.ru', '.is']
        tld_matches = [
            p for p in pages
            if p.get('source_tld') in target_tlds
        ]

        if tld_matches:
            print(f"🚨 Found {len(tld_matches)} backlinks from target TLDs!")
            for m in tld_matches:
                print(f"   - {m.get('source_domain')} ({m.get('source_tld')})")
        else:
            print("✅ No backlinks from .ly/.ru/.is domains (expected)")

        print("\n" + "=" * 80)
        print("✅ MAJESTIC INTEGRATION TEST COMPLETE")
        print("=" * 80)
        print("\n📊 Summary:")
        print(f"   • Referring Domains: {len(domains)}")
        print(f"   • Backlink Pages: {len(pages)}")
        print(f"   • Libyan Keywords Found: {len(matches)}")
        print(f"   • Libya/Russia/Iceland TLDs: {len(tld_matches)}")
        print("\n✅ Majestic is now FULLY INTEGRATED into LinkLater!")
        print("   Usage: await linklater.get_majestic_backlinks(domain)")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(test_majestic_integration())
    sys.exit(0 if success else 1)
