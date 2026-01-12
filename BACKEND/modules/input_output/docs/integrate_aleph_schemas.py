#!/usr/bin/env python3
"""
Integrate ALEPH Field Schemas
==============================

Enhances ALEPH sources with detailed field schemas showing exactly
what fields each collection returns for Company and Person entities.

Input:
- outputs_company_by_country_dataset.csv
- outputs_person_by_country_dataset.csv
- inputs_company_by_country_dataset.csv (optional)

Output:
- sources.json with enhanced ALEPH field schemas

Author: Matrix Integration Pipeline
Date: 2025-11-22
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_DIR = Path("/Users/attic/cmpany-kisgombov/country-kisgomboc/ROUTER/input_output")

COMPANY_OUTPUT = ROUTER_DIR / "outputs_company_by_country_dataset.csv"
PERSON_OUTPUT = ROUTER_DIR / "outputs_person_by_country_dataset.csv"
COMPANY_INPUT = ROUTER_DIR / "inputs_company_by_country_dataset.csv"

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

def load_csv_schemas(csv_path: Path) -> Dict[str, List[Dict]]:
    """Load field schemas from CSV and group by collection_id"""
    schemas = defaultdict(list)

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                collection_id = row['collection_id']
                schemas[collection_id].append({
                    'field': row['field'],
                    'types': row['types'],
                    'formats': row['formats'],
                    'examples': row['examples'][:200] if row['examples'] else ''  # Truncate long examples
                })
    except FileNotFoundError:
        print(f"⚠️  File not found: {csv_path}")

    return schemas

def integrate_aleph_schemas():
    """Main integration function"""
    print("\n" + "="*70)
    print("ALEPH FIELD SCHEMAS INTEGRATION")
    print("="*70 + "\n")

    # Load CSV schemas
    print("📖 Loading ALEPH field schemas...")
    company_schemas = load_csv_schemas(COMPANY_OUTPUT)
    person_schemas = load_csv_schemas(PERSON_OUTPUT)

    print(f"✅ Loaded company schemas for {len(company_schemas)} collections")
    print(f"✅ Loaded person schemas for {len(person_schemas)} collections")

    # Load sources
    print("📖 Loading sources.json...")
    sources_data = load_json(SOURCES_IN)
    if not sources_data:
        print("❌ Invalid sources data")
        return

    print(f"✅ Loaded {len(sources_data)} source jurisdictions\n")

    # Statistics
    stats = {
        'aleph_sources_found': 0,
        'company_schemas_added': 0,
        'person_schemas_added': 0,
        'total_fields_documented': 0
    }

    # Process each jurisdiction
    for jurisdiction_code, sources_list in sources_data.items():
        for source in sources_list:
            source_id = source.get('id', '')

            # Check if this is an ALEPH source
            if not source_id.startswith('aleph_'):
                continue

            stats['aleph_sources_found'] += 1

            # Extract collection ID
            try:
                collection_id = source_id.replace('aleph_', '')

                # Add company schema if available
                if collection_id in company_schemas:
                    source['company_fields'] = company_schemas[collection_id]
                    stats['company_schemas_added'] += 1
                    stats['total_fields_documented'] += len(company_schemas[collection_id])
                    print(f"   ✅ Added {len(company_schemas[collection_id])} company fields to {source_id}")

                # Add person schema if available
                if collection_id in person_schemas:
                    source['person_fields'] = person_schemas[collection_id]
                    stats['person_schemas_added'] += 1
                    stats['total_fields_documented'] += len(person_schemas[collection_id])
                    print(f"   ✅ Added {len(person_schemas[collection_id])} person fields to {source_id}")

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
    print(f"Company schemas added:          {stats['company_schemas_added']}")
    print(f"Person schemas added:           {stats['person_schemas_added']}")
    print(f"Total fields documented:        {stats['total_fields_documented']}")
    print("="*70 + "\n")

    # Verification
    print("🔍 VERIFICATION:")
    print("   Checking for field schemas in ALEPH sources...")

    for jurisdiction_code, sources_list in sources_data.items():
        for source in sources_list:
            if source.get('id', '').startswith('aleph_') and 'company_fields' in source:
                print(f"\n   ✅ Sample: {source['id']}")
                print(f"   📝 Company fields: {len(source.get('company_fields', []))}")
                print(f"   📝 Person fields: {len(source.get('person_fields', []))}")
                if source.get('company_fields'):
                    print(f"   📝 Sample field: {source['company_fields'][0]['field']} ({source['company_fields'][0]['types']})")
                break
        else:
            continue
        break

    print("\n✅ ALEPH field schemas integration complete!\n")

if __name__ == '__main__':
    integrate_aleph_schemas()
