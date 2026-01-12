#!/usr/bin/env python3
"""
Integrate Wiki Comments into Sources
=====================================

Merges rich human-curated comments from wiki_sections_processed.json
into sources.json, preserving all existing data.

Author: Matrix Integration Pipeline
Date: 2025-11-22
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_SECTIONS = PROJECT_ROOT / 'input_output' / 'wiki_sections_processed.json'
SOURCES_IN = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'
SOURCES_OUT = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'

# Section mapping: source section code → wiki section name
SECTION_MAPPING = {
    'cr': 'corporate_registry',
    'lit': 'litigation',
    'reg': 'regulatory',
    'at': 'asset_registries',
    'lic': 'licensing',
    'pol': 'political',
    'pr': 'further_public_records',
    'media': 'media',
    'misc': 'breaches'
}

def load_json(file_path: Path) -> Dict:
    """Load JSON file with error handling"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error in {file_path}: {e}")
        return {}

def save_json(data: Dict, file_path: Path):
    """Save JSON file with pretty formatting"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved: {file_path}")

def normalize_jurisdiction_code(code: str) -> str:
    """Convert jurisdiction code to wiki format (lowercase)"""
    # Handle special cases
    special_cases = {
        'UK': 'gb',
        'GB': 'gb',
        'USA': 'us',
        'US': 'us'
    }

    if code.upper() in special_cases:
        return special_cases[code.upper()]

    return code.lower()

def clean_wiki_content(content: str) -> str:
    """Clean wiki content for better readability"""
    if not content or not content.strip():
        return ""

    # Remove excessive newlines
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    cleaned = '\n\n'.join(lines)

    return cleaned

def integrate_wiki_comments():
    """Main integration function"""
    print("\n" + "="*70)
    print("WIKI COMMENTS INTEGRATION")
    print("="*70 + "\n")

    # Load data
    print("📖 Loading wiki_sections_processed.json...")
    wiki_data = load_json(WIKI_SECTIONS)
    if not wiki_data or 'jurisdictions' not in wiki_data:
        print("❌ Invalid wiki data structure")
        return

    print("📖 Loading sources.json...")
    sources_data = load_json(SOURCES_IN)
    if not sources_data:
        print("❌ Invalid sources data")
        return

    wiki_jurisdictions = wiki_data['jurisdictions']
    print(f"✅ Loaded {len(wiki_jurisdictions)} wiki jurisdictions")
    print(f"✅ Loaded {len(sources_data)} source jurisdictions\n")

    # Statistics
    stats = {
        'jurisdictions_processed': 0,
        'sources_enhanced': 0,
        'sources_skipped': 0,
        'wiki_content_added': 0,
        'wiki_links_added': 0
    }

    # Process each jurisdiction in sources
    for jurisdiction_code, sources_list in sources_data.items():
        wiki_code = normalize_jurisdiction_code(jurisdiction_code)

        # Skip if no wiki data for this jurisdiction
        if wiki_code not in wiki_jurisdictions:
            print(f"⚠️  No wiki data for jurisdiction: {jurisdiction_code} (looking for '{wiki_code}')")
            continue

        stats['jurisdictions_processed'] += 1
        wiki_jurisdiction = wiki_jurisdictions[wiki_code]
        wiki_sections = wiki_jurisdiction.get('sections', {})

        print(f"\n🌍 Processing {jurisdiction_code} ({len(sources_list)} sources)...")

        # Process each source
        for source in sources_list:
            source_section = source.get('section', '')

            # Map source section to wiki section
            wiki_section_name = SECTION_MAPPING.get(source_section)

            if not wiki_section_name:
                stats['sources_skipped'] += 1
                continue

            if wiki_section_name not in wiki_sections:
                stats['sources_skipped'] += 1
                continue

            wiki_section_data = wiki_sections[wiki_section_name]
            wiki_content = wiki_section_data.get('content', '')
            wiki_links = wiki_section_data.get('links', [])

            # Skip if no wiki content
            if not wiki_content or not wiki_content.strip():
                stats['sources_skipped'] += 1
                continue

            # Clean content
            cleaned_content = clean_wiki_content(wiki_content)

            # Add wiki content to source
            # Create a new field 'wiki_context' to preserve original notes
            if 'wiki_context' not in source:
                source['wiki_context'] = cleaned_content
                stats['wiki_content_added'] += 1
                stats['sources_enhanced'] += 1
                print(f"   ✅ Enhanced {source['id']} with wiki context ({len(cleaned_content)} chars)")

            # Add wiki links if not already present
            if wiki_links and 'wiki_links' not in source:
                source['wiki_links'] = wiki_links
                stats['wiki_links_added'] += 1

    # Save enhanced sources
    print("\n💾 Saving enhanced sources.json...")
    save_json(sources_data, SOURCES_OUT)

    # Print statistics
    print("\n" + "="*70)
    print("INTEGRATION STATISTICS")
    print("="*70)
    print(f"Jurisdictions processed:  {stats['jurisdictions_processed']}")
    print(f"Sources enhanced:         {stats['sources_enhanced']}")
    print(f"Sources skipped:          {stats['sources_skipped']}")
    print(f"Wiki content added:       {stats['wiki_content_added']}")
    print(f"Wiki links added:         {stats['wiki_links_added']}")
    print("="*70 + "\n")

    # Verification
    print("🔍 VERIFICATION:")
    print("   Checking for 'Albania is a pineapple'...")

    # Check if Albania content is now in sources
    if 'AL' in sources_data:
        for source in sources_data['AL']:
            if 'wiki_context' in source and 'pineapple' in source['wiki_context']:
                print(f"   ✅ FOUND in source: {source['id']}")
                print(f"   📝 Preview: {source['wiki_context'][:100]}...")
                break
        else:
            print("   ⚠️  NOT FOUND in AL sources")

    print("\n✅ Integration complete!\n")

if __name__ == '__main__':
    integrate_wiki_comments()
