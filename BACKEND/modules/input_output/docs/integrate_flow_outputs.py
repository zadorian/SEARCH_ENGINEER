#!/usr/bin/env python3
"""
Phase 7: Integrate Flow Output Mappings
Adds route-specific output column mappings from flows/*.csv
Shows exactly what fields each input type returns
"""

import json
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_OUTPUT = PROJECT_ROOT / 'input_output'
FLOWS_DIR = INPUT_OUTPUT / 'flows'
OUTPUT_DIR = PROJECT_ROOT / 'input_output2' / 'matrix'
SOURCES_FILE = OUTPUT_DIR / 'sources.json'

def load_json(path: Path) -> dict:
    """Load JSON file"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data: dict, path: Path):
    """Save JSON file"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

def load_flow_mappings(flows_dir: Path) -> Dict[str, List[Dict]]:
    """Load all flow CSV files and organize by collection_id"""
    flows = defaultdict(list)

    csv_files = list(flows_dir.glob('*.csv'))
    # Exclude entity_flow (that's for modules, not ALEPH)
    csv_files = [f for f in csv_files if f.name != 'entity_flow_20250823_013733.csv']

    print(f"Loading {len(csv_files)} flow CSV files...")

    for csv_file in csv_files:
        country = csv_file.stem.upper()
        # Convert GB to UK
        if country == 'GB':
            country = 'UK'

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                source_id = row['source_id'].strip()
                input_type = row['input_type'].strip()
                output_schema = row['output_schema'].strip()
                output_columns = row['output_columns'].strip()

                # Parse output_columns (semicolon-separated)
                columns = [c.strip() for c in output_columns.split(';') if c.strip()]

                flow_entry = {
                    'input_type': input_type,
                    'output_schema': output_schema,
                    'output_columns': columns,
                    'country': country
                }

                flows[source_id].append(flow_entry)

    total_flows = sum(len(v) for v in flows.values())
    print(f"✓ Loaded {total_flows} flow definitions for {len(flows)} sources")

    return flows

def integrate_flows():
    """Add flow output mappings to sources"""
    print("\n=== Phase 7: Integrating Flow Output Mappings ===\n")

    # Load existing sources
    print("Loading sources.json...")
    sources = load_json(SOURCES_FILE)
    print(f"✓ Loaded {len(sources)} countries\n")

    # Load flow mappings
    flows = load_flow_mappings(FLOWS_DIR)
    print()

    # Track stats
    sources_enhanced = 0
    total_flow_entries = 0
    sources_processed = 0

    # Enhance sources with flow mappings
    print("Adding flow output mappings to sources...")

    for country_code, country_sources in sources.items():
        if not isinstance(country_sources, list):
            continue

        for source in country_sources:
            sources_processed += 1

            # Check if this source has flows
            # Try both collection_id and source_id matching
            collection_id = source.get('collection_id', '')
            source_id = source.get('id', '')

            # For ALEPH sources, collection_id is the key
            matched_flows = None
            if collection_id and collection_id in flows:
                matched_flows = flows[collection_id]
            # Also check by extracting ID from source_id (e.g., aleph_809 -> 809)
            elif source_id.startswith('aleph_'):
                aleph_id = source_id.replace('aleph_', '')
                if aleph_id in flows:
                    matched_flows = flows[aleph_id]
            # For non-ALEPH sources, match by source_id directly
            elif source_id in flows:
                matched_flows = flows[source_id]

            if matched_flows:
                source['flow_mappings'] = matched_flows
                sources_enhanced += 1
                total_flow_entries += len(matched_flows)

    print(f"✓ Enhanced {sources_enhanced} sources with flow mappings")
    print(f"  - Total flow entries added: {total_flow_entries}")
    print(f"  - Sources processed: {sources_processed}")
    print()

    # Save enhanced sources
    print("Saving enhanced sources.json...")
    save_json(sources, SOURCES_FILE)

    # Print summary
    print("\n=== Phase 7 Complete ===\n")
    print(f"Countries: {len(sources)}")
    print(f"Total sources: {sources_processed}")
    print(f"Sources with flow mappings: {sources_enhanced}")
    print(f"Total flow entries: {total_flow_entries}")
    print()

    # Show example
    example_sources = []
    for country_sources in sources.values():
        if isinstance(country_sources, list):
            example_sources.extend([s for s in country_sources if 'flow_mappings' in s])

    if example_sources:
        example = example_sources[0]
        print("Example source with flow mappings:")
        print(f"  ID: {example['id']}")
        print(f"  Name: {example['name']}")
        print(f"  Flow mappings: {len(example['flow_mappings'])} routes")
        if example['flow_mappings']:
            first_flow = example['flow_mappings'][0]
            print(f"    Sample: {first_flow['input_type']} → {first_flow['output_schema']}")
            print(f"           Returns: {len(first_flow['output_columns'])} fields")
            print(f"           Fields: {', '.join(first_flow['output_columns'][:5])}...")

if __name__ == '__main__':
    integrate_flows()
