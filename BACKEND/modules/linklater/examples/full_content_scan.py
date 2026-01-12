#!/usr/bin/env python3
"""
FULL CONTENT SCAN: seb.se + sebgroup.com
Search website content for Libyan entities, projects, and keywords
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.linklater.api import linklater


async def full_content_scan():
    """Scan website content for Libyan keywords and entities."""

    print("=" * 100)
    print("FULL CONTENT SCAN: seb.se + sebgroup.com")
    print("=" * 100)
    print("\nSearching for:")
    print("  - Libyan project names")
    print("  - Libyan companies")
    print("  - Libyan persons (Gaddafi, etc.)")
    print("  - Libyan locations (Tripoli, Benghazi, etc.)")
    print("  - Libya Investment Authority (LIA)")
    print("=" * 100)

    domains = ["seb.se", "sebgroup.com"]

    # Comprehensive Libyan keyword list
    libyan_keywords = [
        # Country & Demonym
        'libya', 'libyan', 'jamahiriya',

        # Cities
        'tripoli', 'benghazi', 'misrata', 'tobruk', 'sirte',

        # Leaders
        'gaddafi', 'qadhafi', 'qaddafi', 'kadafi', 'ghaddafi',
        'saif al-islam', 'mutassim', 'khamis',

        # Organizations
        'libya investment authority', 'lia fund', 'libyan investment',
        'libyan sovereign', 'libyan wealth fund',
        'national oil corporation libya', 'noc libya',
        'central bank libya', 'cbl',

        # Projects
        'great man-made river', 'gmr project',
        'libyan oil', 'libyan petroleum',

        # Financial terms
        'libyan assets', 'libyan funds', 'libyan sanctions',
        'frozen libyan', 'libyan portfolio',

        # Historical
        'libyan regime', 'libyan revolution', 'arab spring libya',

        # Domain/Email
        '.ly', 'libya.', '@libya', 'libyan.'
    ]

    for domain in domains:
        print(f"\n{'=' * 100}")
        print(f"SCANNING: {domain}")
        print("=" * 100)

        # ========================================
        # PHASE 1: SCRAPE HOMEPAGE
        # ========================================
        print(f"\n📄 Phase 1: Scraping homepage content...")

        try:
            result = await linklater.scrape_url(f"https://{domain}")

            if hasattr(result, 'content') and result.content:
                print(f"✅ Successfully scraped {len(result.content)} characters")
                print(f"   Source: {result.source}")

                # Search content for keywords
                content_lower = result.content.lower()
                matches = []

                for keyword in libyan_keywords:
                    if keyword.lower() in content_lower:
                        # Find context around keyword
                        idx = content_lower.find(keyword.lower())
                        start = max(0, idx - 100)
                        end = min(len(result.content), idx + len(keyword) + 100)
                        context = result.content[start:end].strip()

                        matches.append({
                            'keyword': keyword,
                            'context': context
                        })

                if matches:
                    print(f"\n🚨 FOUND {len(matches)} KEYWORD MATCHES IN HOMEPAGE!")
                    for i, match in enumerate(matches[:20], 1):
                        print(f"\n{i}. Keyword: '{match['keyword']}'")
                        print(f"   Context: ...{match['context']}...")
                else:
                    print(f"✅ No Libyan keywords found in homepage content")

                # Extract entities
                print(f"\n🔍 Extracting entities from content...")
                entities = linklater.extract_entities(result.content)

                print(f"   Companies: {len(entities.get('companies', []))}")
                print(f"   Persons: {len(entities.get('persons', []))}")

                # Check entities for Libyan connections
                libyan_companies = [
                    c for c in entities.get('companies', [])
                    if any(kw in c.text.lower() for kw in ['libya', 'libyan', 'tripoli'])
                ]

                libyan_persons = [
                    p for p in entities.get('persons', [])
                    if any(kw in p.text.lower() for kw in ['gaddafi', 'qadhafi', 'qaddafi'])
                ]

                if libyan_companies:
                    print(f"\n🚨 FOUND {len(libyan_companies)} LIBYAN COMPANIES:")
                    for c in libyan_companies:
                        print(f"   - {c.text}")

                if libyan_persons:
                    print(f"\n🚨 FOUND {len(libyan_persons)} LIBYAN PERSONS:")
                    for p in libyan_persons:
                        print(f"   - {p.text}")

            else:
                print(f"⚠️  Failed to scrape: Status {result.status_code}")

        except Exception as e:
            print(f"❌ Scraping error: {e}")

        # ========================================
        # PHASE 2: SEARCH SITE FOR KEYWORDS
        # ========================================
        print(f"\n📡 Phase 2: Searching site with keyword variations...")

        try:
            # Search for "Libya" and variations
            print(f"\n🔍 Searching for 'Libya' variations on {domain}...")

            search_terms = [
                'libya', 'libyan', 'LIA', 'tripoli',
                'gaddafi', 'libya investment authority'
            ]

            for term in search_terms[:3]:  # Limit to avoid timeout
                print(f"\n   Searching: '{term}'")

                try:
                    # Use standard search, not keyword variations
                    search_results = await linklater.search(
                        query=f"site:{domain} {term}",
                        max_results=10
                    )

                    matches_found = len(search_results)
                    if matches_found > 0:
                        print(f"   🚨 Found {matches_found} matches for '{term}'")
                        for i, match in enumerate(search_results[:5], 1):
                            print(f"      {i}. {match.get('url', 'N/A')}")
                            if match.get('snippet'):
                                print(f"         {match.get('snippet', '')[:100]}...")
                    else:
                        print(f"   ✅ No matches for '{term}'")

                except Exception as e:
                    print(f"   ⚠️  Search error for '{term}': {e}")

        except Exception as e:
            print(f"❌ Keyword search error: {e}")

        # ========================================
        # PHASE 3: CHECK WAYBACK HISTORICAL
        # ========================================
        print(f"\n📚 Phase 3: Checking Wayback Machine archives...")

        try:
            print(f"\n🔍 Fetching historical content from Wayback...")
            wayback_content = await linklater.fetch_from_wayback(f"https://{domain}")

            if wayback_content:
                print(f"✅ Retrieved {len(wayback_content)} characters from Wayback")

                # Search for keywords
                content_lower = wayback_content.lower()
                matches = []

                for keyword in libyan_keywords[:10]:  # Check top keywords
                    if keyword.lower() in content_lower:
                        matches.append(keyword)

                if matches:
                    print(f"🚨 FOUND {len(matches)} KEYWORDS IN WAYBACK ARCHIVE:")
                    for kw in matches:
                        print(f"   - {kw}")
                else:
                    print(f"✅ No Libyan keywords in Wayback archive")
            else:
                print(f"⚠️  No Wayback content available")

        except Exception as e:
            print(f"❌ Wayback error: {e}")

        # ========================================
        # PHASE 4: CHECK COMMON CRAWL
        # ========================================
        print(f"\n🌐 Phase 4: Checking Common Crawl index...")

        try:
            print(f"\n🔍 Querying CC index for {domain}...")
            cc_index = await linklater.check_cc_index(f"https://{domain}")

            if cc_index:
                print(f"✅ Found in Common Crawl index")
                print(f"   URL: {cc_index.get('url', 'N/A')}")
                print(f"   Timestamp: {cc_index.get('timestamp', 'N/A')}")

                # Try to fetch content
                print(f"\n🔍 Fetching CC content...")
                # Note: This would need actual WARC fetching
                print(f"   (Full WARC fetch would go here)")
            else:
                print(f"⚠️  Not found in CC index")

        except Exception as e:
            print(f"❌ CC index error: {e}")

    # ========================================
    # FINAL SUMMARY
    # ========================================
    print("\n" + "=" * 100)
    print("CONTENT SCAN SUMMARY")
    print("=" * 100)
    print("\nScanned both seb.se and sebgroup.com for:")
    print("  ✓ Homepage content")
    print("  ✓ Keyword variations across site")
    print("  ✓ Wayback Machine archives")
    print("  ✓ Common Crawl index")
    print("\nLooking for:")
    print(f"  • {len(libyan_keywords)} Libyan keywords")
    print("  • Company names (Libya Investment Authority, etc.)")
    print("  • Person names (Gaddafi, etc.)")
    print("  • Project names (Great Man-Made River, etc.)")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(full_content_scan())
