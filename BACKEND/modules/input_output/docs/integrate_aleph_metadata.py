#!/usr/bin/env python3
"""
Integrate ALEPH Collection Metadata
====================================

Enhances ALEPH sources in sources.json with detailed metadata from aleph_matrix_processed.json:
- Collection IDs and labels
- Example input/output values from real ALEPH records
- Access requirements (paywall, ID required, etc.)
- Source type classification

Author: Matrix Integration Pipeline
Date: 2025-11-22
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEPH_MATRIX = Path("/Users/attic/cmpany-kisgombov/country-kisgomboc/_TEMP_WIKIMAN-PRO/aleph_matrix_processed.json")
SOURCES_IN = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'
SOURCES_OUT = PROJECT_ROOT / 'input_output2' / 'matrix' / 'sources.json'

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
    """Convert jurisdiction code to lowercase"""
    return code.lower()

def integrate_aleph_metadata():
    """Main integration function"""
    print("\n" + "="*70)
    print("ALEPH COLLECTION METADATA INTEGRATION")
    print("="*70 + "\n")

    # Load data
    print("📖 Loading aleph_matrix_processed.json...")
    aleph_data = load_json(ALEPH_MATRIX)
    if not aleph_data or 'results' not in aleph_data:
        print("❌ Invalid ALEPH data structure")
        return

    print("📖 Loading sources.json...")
    sources_data = load_json(SOURCES_IN)
    if not sources_data:
        print("❌ Invalid sources data")
        return

    aleph_results = aleph_data['results']
    print(f"✅ Loaded {len(aleph_results)} ALEPH jurisdictions")
    print(f"✅ Loaded {len(sources_data)} source jurisdictions\n")

    # Statistics
    stats = {
        'aleph_sources_found': 0,
        'aleph_sources_enhanced': 0,
        'collection_metadata_added': 0,
        'example_data_added': 0,
        'access_requirements_added': 0
    }

    # Build ALEPH lookup by collection_id
    print("🔨 Building ALEPH collection lookup...")
    aleph_lookup = {}
    for jurisdiction_code, jurisdiction_data in aleph_results.items():
        if 'aleph_matrix' in jurisdiction_data:
            records = jurisdiction_data['aleph_matrix']['records']
            for record in records:
                coll_id = record.get('collection_id')
                if coll_id and coll_id not in aleph_lookup:
                    aleph_lookup[coll_id] = record

    print(f"✅ Built lookup for {len(aleph_lookup)} unique ALEPH collections\n")

    # Process each jurisdiction
    for jurisdiction_code, sources_list in sources_data.items():
        for source in sources_list:
            source_id = source.get('id', '')

            # Check if this is an ALEPH source
            if not source_id.startswith('aleph_'):
                continue

            stats['aleph_sources_found'] += 1

            # Extract collection ID from source ID (e.g., "aleph_776" → "776")
            try:
                collection_id = source_id.replace('aleph_', '')

                # Find matching ALEPH record
                if collection_id not in aleph_lookup:
                    print(f"   ⚠️  No ALEPH data for collection {collection_id}")
                    continue

                aleph_record = aleph_lookup[collection_id]

                # Add collection metadata
                if 'collection_label' in aleph_record:
                    source['collection_id'] = collection_id
                    source['collection_label'] = aleph_record['collection_label']
                    stats['collection_metadata_added'] += 1

                # Add example input/output data
                if 'input' in aleph_record and aleph_record['input']:
                    if 'aleph_examples' not in source:
                        source['aleph_examples'] = {
                            'inputs': aleph_record['input'],
                            'outputs': aleph_record.get('output', [])
                        }
                        stats['example_data_added'] += 1

                # Add access requirements
                if 'access_requirements' in aleph_record:
                    source['access_requirements'] = aleph_record['access_requirements']
                    stats['access_requirements_added'] += 1

                # Add source type
                if 'source_type' in aleph_record:
                    source['source_type_aleph'] = aleph_record['source_type']

                # Add coverage notes
                if 'coverage' in aleph_record:
                    if 'aleph_coverage' not in source:
                        source['aleph_coverage'] = aleph_record['coverage']

                stats['aleph_sources_enhanced'] += 1
                print(f"   ✅ Enhanced {source_id} with ALEPH collection {collection_id}: {aleph_record.get('collection_label', 'N/A')}")

            except Exception as e:
                print(f"   ❌ Error processing {source_id}: {e}")
                continue

    # Save enhanced sources
    print("\n💾 Saving enhanced sources.json...")
    save_json(sources_data, SOURCES_OUT)

    # Print statistics
    print("\n" + "="*70)
    print("INTEGRATION STATISTICS")
    print("="*70)
    print(f"ALEPH sources found:            {stats['aleph_sources_found']}")
    print(f"ALEPH sources enhanced:         {stats['aleph_sources_enhanced']}")
    print(f"Collection metadata added:      {stats['collection_metadata_added']}")
    print(f"Example data added:             {stats['example_data_added']}")
    print(f"Access requirements added:      {stats['access_requirements_added']}")
    print("="*70 + "\n")

    # Verification
    print("🔍 VERIFICATION:")
    print("   Checking for ALEPH collection labels...")

    aleph_with_labels = 0
    for jurisdiction_code, sources_list in sources_data.items():
        for source in sources_list:
            if source.get('id', '').startswith('aleph_') and source.get('collection_label'):
                aleph_with_labels += 1
                if aleph_with_labels == 1:
                    print(f"\n   ✅ Sample: {source['id']}")
                    print(f"   📝 Collection: {source['collection_label']}")
                    print(f"   📝 Has examples: {('aleph_examples' in source)}")
                    print(f"   📝 Has access requirements: {('access_requirements' in source)}")

    print(f"\n   Total ALEPH sources with collection labels: {aleph_with_labels}/{stats['aleph_sources_found']}")
    print("\n✅ ALEPH metadata integration complete!\n")

if __name__ == '__main__':
    integrate_aleph_metadata()
