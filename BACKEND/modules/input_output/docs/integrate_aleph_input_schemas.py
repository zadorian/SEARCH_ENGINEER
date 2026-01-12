#!/usr/bin/env python3
"""
Phase 6: Integrate ALEPH Input Schemas
Adds detailed input descriptions to ALEPH sources from:
- inputs_company_by_country_dataset.csv
- inputs_person_by_country_dataset.csv
"""

import json
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_OUTPUT = PROJECT_ROOT / 'input_output'
OUTPUT_DIR = PROJECT_ROOT / 'input_output2' / 'matrix'
SOURCES_FILE = OUTPUT_DIR / 'sources.json'

COMPANY_INPUTS_CSV = INPUT_OUTPUT / 'inputs_company_by_country_dataset.csv'
PERSON_INPUTS_CSV = INPUT_OUTPUT / 'inputs_person_by_country_dataset.csv'

def load_json(path: Path) -> dict:
    """Load JSON file"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data: dict, path: Path):
    """Save JSON file"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

def load_input_schemas(csv_path: Path, schema_type: str) -> Dict[str, List[Dict]]:
    """Load input schemas from CSV and group by collection_id"""
    schemas = defaultdict(list)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            collection_id = row['collection_id'].strip()

            # Create input schema entry
            input_entry = {
                'input_key': row['input_key'].strip(),
                'input_desc': row['input_desc'].strip(),
                'country': row['country'].strip() if row['country'].strip() else None
            }

            schemas[collection_id].append(input_entry)

    print(f"✓ Loaded {sum(len(v) for v in schemas.values())} {schema_type} input entries from {len(schemas)} collections")
    return schemas

def integrate_input_schemas():
    """Add input schemas to ALEPH sources"""
    print("\n=== Phase 6: Integrating ALEPH Input Schemas ===\n")

    # Load existing sources
    print("Loading sources.json...")
    sources = load_json(SOURCES_FILE)
    print(f"✓ Loaded {len(sources)} sources\n")

    # Load input schemas
    print("Loading input schema CSV files...")
    company_inputs = load_input_schemas(COMPANY_INPUTS_CSV, "company")
    person_inputs = load_input_schemas(PERSON_INPUTS_CSV, "person")
    print()

    # Track stats
    sources_enhanced = 0
    company_input_count = 0
    person_input_count = 0
    total_sources = 0

    # Enhance sources with input schemas
    print("Adding input schemas to ALEPH sources...")

    # sources.json is organized by country code
    for country_code, country_sources in sources.items():
        if not isinstance(country_sources, list):
            continue

        for source in country_sources:
            total_sources += 1

            # Only process ALEPH sources
            if not source.get('id', '').startswith('aleph_'):
                continue

            collection_id = source.get('collection_id')
            if not collection_id:
                continue

            # Add company inputs if available
            if collection_id in company_inputs:
                source['company_inputs'] = company_inputs[collection_id]
                company_input_count += len(company_inputs[collection_id])
                sources_enhanced += 1

            # Add person inputs if available
            if collection_id in person_inputs:
                source['person_inputs'] = person_inputs[collection_id]
                person_input_count += len(person_inputs[collection_id])
                if 'company_inputs' not in source:
                    sources_enhanced += 1

    print(f"✓ Enhanced {sources_enhanced} ALEPH sources")
    print(f"  - Company inputs added: {company_input_count} entries")
    print(f"  - Person inputs added: {person_input_count} entries")
    print()

    # Save enhanced sources
    print("Saving enhanced sources.json...")
    save_json(sources, SOURCES_FILE)

    # Print summary
    print("\n=== Phase 6 Complete ===\n")
    print(f"Countries: {len(sources)}")
    print(f"Total sources: {total_sources}")
    print(f"ALEPH sources with input schemas: {sources_enhanced}")
    print(f"Total input definitions: {company_input_count + person_input_count}")
    print()

    # Show example
    aleph_sources = []
    for country_sources in sources.values():
        if isinstance(country_sources, list):
            aleph_sources.extend([s for s in country_sources if s.get('id', '').startswith('aleph_')])

    if aleph_sources:
        example = next((s for s in aleph_sources if 'company_inputs' in s or 'person_inputs' in s), None)
        if example:
            print("Example enhanced source:")
            print(f"  ID: {example['id']}")
            print(f"  Name: {example['name']}")
            if 'company_inputs' in example:
                print(f"  Company inputs: {len(example['company_inputs'])} types")
                print(f"    Sample: {example['company_inputs'][0]['input_key']} - {example['company_inputs'][0]['input_desc'][:80]}...")
            if 'person_inputs' in example:
                print(f"  Person inputs: {len(example['person_inputs'])} types")
                print(f"    Sample: {example['person_inputs'][0]['input_key']} - {example['person_inputs'][0]['input_desc'][:80]}...")

    return sources

if __name__ == '__main__':
    integrate_input_schemas()
