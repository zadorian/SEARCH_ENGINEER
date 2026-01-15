#!/usr/bin/env python3
"""
Comprehensive Backlink Investigation: sebgroup.com
Full LinkLater Stack + Historical Common Crawl + Majestic
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.linklater.api import linklater


async def investigate_sebgroup():
    """Full backlink investigation using all LinkLater sources."""

    print("=" * 100)
    print("COMPREHENSIVE BACKLINK INVESTIGATION: sebgroup.com")
    print("=" * 100)
    print("\nFull LinkLater Stack:")
    print("  1. CC Web Graph (157M domains, 2.1B edges)")
    print("  2. GlobalLinks (4 Go binaries, 6B links/month)")
    print("  3. Majestic Fresh + Historic (with anchor texts)")
    print("  4. Historical Common Crawl Archives (2008-2024)")
    print("=" * 100)

    domain = "sebgroup.com"

    # Keywords to search for
    libyan_keywords = [
        'libya', 'libyan', 'tripoli', 'benghazi', 'gaddafi', 'qadhafi',
        'jamahiriya', 'lia', 'libyan investment', 'libyan authority',
        '.ly', 'libya.', 'libyan.'
    ]

    country_tlds = ['.ly', '.ru', '.is']

    print(f"\n🎯 Target: {domain}")
    print(f"🔍 Searching for: Libyan keywords + Russia/Iceland connections")
    print(f"📅 Timeframe: Historical archives back to 2008")
    print("=" * 100)

    # ========================================
    # PHASE 1: CC WEB GRAPH
    # ========================================
    print("\n" + "=" * 100)
    print("PHASE 1: CC WEB GRAPH (157M domains, 2.1B edges)")
    print("=" * 100)

    try:
        print(f"\n📊 Querying CC Web Graph for backlinks to {domain}...")
        cc_backlinks = await linklater.get_backlinks(domain, limit=500, use_globallinks=False)

        print(f"✅ Found {len(cc_backlinks)} backlinks from CC Web Graph")

        # Filter by country TLDs
        cc_filtered = [b for b in cc_backlinks if any(b.source.endswith(tld) for tld in country_tlds)]

        if cc_filtered:
            print(f"\n🚨 Found {len(cc_filtered)} backlinks from target TLDs:")
            for link in cc_filtered[:10]:
                print(f"   - {link.source} → {link.target} (TLD: {[t for t in country_tlds if link.source.endswith(t)][0]})")
        else:
            print(f"✅ No backlinks from .ly/.ru/.is domains in CC Graph")

    except Exception as e:
        print(f"⚠️  CC Web Graph: {e}")
        cc_backlinks = []

    # ========================================
    # PHASE 2: GLOBALLINKS
    # ========================================
    print("\n" + "=" * 100)
    print("PHASE 2: GLOBALLINKS (Common Crawl WAT Processing)")
    print("=" * 100)

    try:
        print(f"\n📊 Querying GlobalLinks for {domain}...")
        gl_backlinks = await linklater.get_backlinks(domain, limit=500, use_globallinks=True)

        # Filter out CC Graph results to get only GlobalLinks
        gl_only = [b for b in gl_backlinks if b.provider == 'globallinks']

        print(f"✅ Found {len(gl_only)} backlinks from GlobalLinks")

        # Filter by country TLDs
        gl_filtered = [b for b in gl_only if any(b.source.endswith(tld) for tld in country_tlds)]

        if gl_filtered:
            print(f"\n🚨 Found {len(gl_filtered)} backlinks from target TLDs:")
            for link in gl_filtered[:10]:
                print(f"   - {link.source} → {link.target}")
                if hasattr(link, 'anchor_text') and link.anchor_text:
                    print(f"     Anchor: \"{link.anchor_text}\"")
        else:
            print(f"✅ No backlinks from .ly/.ru/.is domains in GlobalLinks")

    except Exception as e:
        print(f"⚠️  GlobalLinks: {e}")
        gl_only = []

    # ========================================
    # PHASE 3: MAJESTIC FRESH (90 days)
    # ========================================
    print("\n" + "=" * 100)
    print("PHASE 3: MAJESTIC FRESH INDEX (Last 90 Days)")
    print("=" * 100)

    try:
        print(f"\n📊 Querying Majestic Fresh Index for {domain}...")

        # Get backlink pages with anchor text
        majestic_fresh = await linklater.get_majestic_backlinks(
            domain,
            mode="fresh",
            result_type="pages",
            max_results=1000
        )

        print(f"✅ Found {len(majestic_fresh)} backlink pages from Majestic Fresh")

        # Search anchor texts for Libyan keywords
        libyan_matches = [
            b for b in majestic_fresh
            if any(kw.lower() in b.get('anchor_text', '').lower() for kw in libyan_keywords)
        ]

        if libyan_matches:
            print(f"\n🚨 Found {len(libyan_matches)} backlinks with Libyan keywords in anchor text:")
            for match in libyan_matches[:20]:
                anchor = match.get('anchor_text', '')
                print(f"\n   Source: {match.get('source_domain')}")
                print(f"   Anchor: \"{anchor}\"")
                print(f"   Target: {match.get('target_url')}")
                print(f"   Trust Flow: {match.get('trust_flow')}")
        else:
            print(f"✅ No Libyan keywords found in Fresh anchor texts")

        # Filter by country TLDs
        tld_matches = [
            b for b in majestic_fresh
            if b.get('source_tld') in country_tlds
        ]

        if tld_matches:
            print(f"\n🚨 Found {len(tld_matches)} backlinks from target TLDs:")
            for match in tld_matches[:10]:
                print(f"   - {match.get('source_domain')} ({match.get('source_tld')})")
                print(f"     Anchor: \"{match.get('anchor_text', '')}\"")
        else:
            print(f"✅ No backlinks from .ly/.ru/.is domains in Majestic Fresh")

    except Exception as e:
        print(f"⚠️  Majestic Fresh: {e}")
        majestic_fresh = []
        libyan_matches = []
        tld_matches = []

    # ========================================
    # PHASE 4: MAJESTIC HISTORIC (5 years)
    # ========================================
    print("\n" + "=" * 100)
    print("PHASE 4: MAJESTIC HISTORIC INDEX (Last 5 Years)")
    print("=" * 100)

    try:
        print(f"\n📊 Querying Majestic Historic Index for {domain}...")

        # Get backlink pages with anchor text
        majestic_historic = await linklater.get_majestic_backlinks(
            domain,
            mode="historic",
            result_type="pages",
            max_results=1000
        )

        print(f"✅ Found {len(majestic_historic)} backlink pages from Majestic Historic")

        # Search anchor texts for Libyan keywords
        libyan_matches_historic = [
            b for b in majestic_historic
            if any(kw.lower() in b.get('anchor_text', '').lower() for kw in libyan_keywords)
        ]

        if libyan_matches_historic:
            print(f"\n🚨 Found {len(libyan_matches_historic)} historical backlinks with Libyan keywords:")
            for match in libyan_matches_historic[:20]:
                anchor = match.get('anchor_text', '')
                print(f"\n   Source: {match.get('source_domain')}")
                print(f"   Anchor: \"{anchor}\"")
                print(f"   Target: {match.get('target_url')}")
                print(f"   Trust Flow: {match.get('trust_flow')}")
        else:
            print(f"✅ No Libyan keywords found in Historic anchor texts")

        # Filter by country TLDs
        tld_matches_historic = [
            b for b in majestic_historic
            if b.get('source_tld') in country_tlds
        ]

        if tld_matches_historic:
            print(f"\n🚨 Found {len(tld_matches_historic)} historical backlinks from target TLDs:")
            for match in tld_matches_historic[:10]:
                print(f"   - {match.get('source_domain')} ({match.get('source_tld')})")
                print(f"     Anchor: \"{match.get('anchor_text', '')}\"")
        else:
            print(f"✅ No backlinks from .ly/.ru/.is domains in Majestic Historic")

    except Exception as e:
        print(f"⚠️  Majestic Historic: {e}")
        majestic_historic = []
        libyan_matches_historic = []
        tld_matches_historic = []

    # ========================================
    # PHASE 5: HISTORICAL COMMON CRAWL ARCHIVES
    # ========================================
    print("\n" + "=" * 100)
    print("PHASE 5: HISTORICAL COMMON CRAWL ARCHIVES (2008-2024)")
    print("=" * 100)

    print(f"\n📊 Searching historical CC archives for {domain}...")
    print("⏳ This will search through multiple archive snapshots...")

    try:
        # Search historical archives for Libyan keywords
        historical_matches = []

        print("\n🔍 Searching for Libyan keywords in archived content...")

        async for result in linklater.search_archives(
            domain=domain,
            keyword="libya OR libyan OR tripoli OR LIA",
            start_year=2008,
            end_year=2024
        ):
            historical_matches.append(result)
            if len(historical_matches) <= 10:
                print(f"   ✓ Found: {result.get('url', 'N/A')} ({result.get('timestamp', 'N/A')})")

        if historical_matches:
            print(f"\n🚨 Found {len(historical_matches)} archived pages with Libyan keywords!")
            print("\nTop 10 matches:")
            for i, match in enumerate(historical_matches[:10], 1):
                print(f"\n{i}. {match.get('url', 'N/A')}")
                print(f"   Timestamp: {match.get('timestamp', 'N/A')}")
                snippet = match.get('snippet', '')[:200]
                print(f"   Snippet: {snippet}...")
        else:
            print(f"✅ No Libyan keywords found in archived content")

    except Exception as e:
        print(f"⚠️  Historical Archive Search: {e}")
        historical_matches = []

    # ========================================
    # FINAL SUMMARY
    # ========================================
    print("\n" + "=" * 100)
    print("INVESTIGATION SUMMARY: sebgroup.com")
    print("=" * 100)

    total_backlinks = len(cc_backlinks) + len(gl_only) + len(majestic_fresh) + len(majestic_historic)
    total_libyan = len(libyan_matches) + len(libyan_matches_historic) + len(historical_matches)
    total_tld = len([b for b in cc_backlinks if any(b.source.endswith(t) for t in country_tlds)]) + \
                len([b for b in gl_only if any(b.source.endswith(t) for t in country_tlds)]) + \
                len(tld_matches) + len(tld_matches_historic)

    print(f"\n📊 Total Backlinks Found: {total_backlinks}")
    print(f"   - CC Web Graph: {len(cc_backlinks)}")
    print(f"   - GlobalLinks: {len(gl_only)}")
    print(f"   - Majestic Fresh: {len(majestic_fresh)}")
    print(f"   - Majestic Historic: {len(majestic_historic)}")

    print(f"\n🔍 Libyan Keyword Matches: {total_libyan}")
    print(f"   - Majestic Fresh Anchors: {len(libyan_matches)}")
    print(f"   - Majestic Historic Anchors: {len(libyan_matches_historic)}")
    print(f"   - Historical Archives: {len(historical_matches)}")

    print(f"\n🌍 Target Country TLD Matches (.ly/.ru/.is): {total_tld}")

    if total_libyan > 0 or total_tld > 0:
        print("\n🚨 CONNECTIONS FOUND!")
    else:
        print("\n✅ NO LIBYAN/RUSSIA/ICELAND CONNECTIONS FOUND")

    print("\n" + "=" * 100)
    print("INVESTIGATION COMPLETE")
    print("=" * 100)

    return {
        'total_backlinks': total_backlinks,
        'libyan_matches': total_libyan,
        'tld_matches': total_tld,
        'cc_graph': len(cc_backlinks),
        'globallinks': len(gl_only),
        'majestic_fresh': len(majestic_fresh),
        'majestic_historic': len(majestic_historic),
        'historical_archives': len(historical_matches)
    }


if __name__ == "__main__":
    result = asyncio.run(investigate_sebgroup())
    sys.exit(0)
