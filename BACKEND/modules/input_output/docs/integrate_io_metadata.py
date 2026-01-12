#!/usr/bin/env python3
"""
Integrate Structured I/O Metadata from wiki_io_extractions.json
================================================================

Enhances sources.json with structured input/output metadata including:
- Input types with confidence levels
- Output fields with source quotes
- Detailed notes and reliability scores

Author: Matrix Integration Pipeline
Date: 2025-11-22
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_IO = PROJECT_ROOT / 'input_output' / 'wiki_io_extractions.json'
SOURCES_IN = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'
SOURCES_OUT = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'

# Section mapping
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
    special_cases = {
        'UK': 'gb',
        'GB': 'gb',
        'USA': 'us',
        'US': 'us'
    }

    if code.upper() in special_cases:
        return special_cases[code.upper()]

    return code.lower()

def integrate_io_metadata():
    """Main integration function"""
    print("\n" + "="*70)
    print("STRUCTURED I/O METADATA INTEGRATION")
    print("="*70 + "\n")

    # Load data
    print("📖 Loading wiki_io_extractions.json...")
    wiki_io_data = load_json(WIKI_IO)
    if not wiki_io_data or 'results' not in wiki_io_data:
        print("❌ Invalid wiki_io data structure")
        return

    print("📖 Loading sources.json...")
    sources_data = load_json(SOURCES_IN)
    if not sources_data:
        print("❌ Invalid sources data")
        return

    wiki_results = wiki_io_data['results']
    print(f"✅ Loaded {len(wiki_results)} wiki jurisdictions with I/O metadata")
    print(f"✅ Loaded {len(sources_data)} source jurisdictions\n")

    # Statistics
    stats = {
        'jurisdictions_processed': 0,
        'sources_enhanced': 0,
        'sources_skipped': 0,
        'io_metadata_added': 0,
        'input_fields_added': 0,
        'output_fields_added': 0
    }

    # Process each jurisdiction in sources
    for jurisdiction_code, sources_list in sources_data.items():
        wiki_code = normalize_jurisdiction_code(jurisdiction_code)

        # Skip if no wiki data for this jurisdiction
        if wiki_code not in wiki_results:
            continue

        stats['jurisdictions_processed'] += 1
        wiki_jurisdiction = wiki_results[wiki_code]

        print(f"\n🌍 Processing {jurisdiction_code} ({len(sources_list)} sources)...")

        # Process each source
        for source in sources_list:
            source_section = source.get('section', '')

            # Map source section to wiki section
            wiki_section_name = SECTION_MAPPING.get(source_section)

            if not wiki_section_name:
                stats['sources_skipped'] += 1
                continue

            if wiki_section_name not in wiki_jurisdiction:
                stats['sources_skipped'] += 1
                continue

            wiki_section_data = wiki_jurisdiction[wiki_section_name]

            # Check if this section has I/O metadata
            if 'record' not in wiki_section_data:
                stats['sources_skipped'] += 1
                continue

            record = wiki_section_data['record']

            # Add structured input metadata
            if 'input' in record and record['input']:
                if 'input_metadata' not in source:
                    source['input_metadata'] = record['input']
                    stats['io_metadata_added'] += 1
                    stats['input_fields_added'] += len(record['input'])
                    print(f"   ✅ Added {len(record['input'])} input metadata entries to {source['id']}")

            # Add structured output metadata
            if 'output' in record and record['output']:
                if 'output_metadata' not in source:
                    source['output_metadata'] = record['output']
                    stats['io_metadata_added'] += 1
                    stats['output_fields_added'] += len(record['output'])
                    print(f"   ✅ Added {len(record['output'])} output metadata entries to {source['id']}")

            if 'input_metadata' in source or 'output_metadata' in source:
                stats['sources_enhanced'] += 1

    # Save enhanced sources
    print("\n💾 Saving enhanced sources.json...")
    save_json(sources_data, SOURCES_OUT)

    # Print statistics
    print("\n" + "="*70)
    print("INTEGRATION STATISTICS")
    print("="*70)
    print(f"Jurisdictions processed:   {stats['jurisdictions_processed']}")
    print(f"Sources enhanced:          {stats['sources_enhanced']}")
    print(f"Sources skipped:           {stats['sources_skipped']}")
    print(f"I/O metadata added:        {stats['io_metadata_added']}")
    print(f"Input fields added:        {stats['input_fields_added']}")
    print(f"Output fields added:       {stats['output_fields_added']}")
    print("="*70 + "\n")

    # Verification
    print("🔍 VERIFICATION:")
    print("   Checking for structured I/O metadata in AL sources...")

    if 'AL' in sources_data:
        for source in sources_data['AL']:
            if 'input_metadata' in source:
                print(f"\n   ✅ FOUND input_metadata in: {source['id']}")
                print(f"   📝 Sample: {source['input_metadata'][0]}")
                break
        else:
            print("   ⚠️  NO input_metadata found in AL sources")

    print("\n✅ I/O metadata integration complete!\n")

if __name__ == '__main__':
    integrate_io_metadata()
