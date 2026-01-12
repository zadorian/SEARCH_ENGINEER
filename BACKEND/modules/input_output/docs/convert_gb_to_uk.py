#!/usr/bin/env python3
"""
Convert all GB country codes to UK throughout sources.json
UK = United Kingdom in our system
"""

import json
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
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

def convert_gb_to_uk():
    """Convert all GB codes to UK"""
    print("\n=== Converting GB to UK ===\n")

    # Load sources
    print("Loading sources.json...")
    sources = load_json(SOURCES_FILE)
    print(f"✓ Loaded {len(sources)} countries\n")

    # Track changes
    gb_sources_count = len(sources.get('GB', []))
    uk_sources_count = len(sources.get('UK', []))
    jurisdiction_changes = 0
    field_changes = 0

    print(f"Current state:")
    print(f"  - GB sources: {gb_sources_count}")
    print(f"  - UK sources: {uk_sources_count}\n")

    # Merge GB sources into UK
    if 'GB' in sources:
        print("Merging GB sources into UK...")
        if 'UK' not in sources:
            sources['UK'] = []

        # Add all GB sources to UK
        sources['UK'].extend(sources['GB'])

        # Change jurisdiction field in former GB sources
        for source in sources['GB']:
            if source.get('jurisdiction') == 'GB':
                source['jurisdiction'] = 'UK'
                jurisdiction_changes += 1

        # Remove GB key
        del sources['GB']
        print(f"✓ Merged {gb_sources_count} GB sources into UK\n")

    # Change all GB jurisdictions to UK across all countries
    print("Updating jurisdiction codes...")
    for country_code, country_sources in sources.items():
        if not isinstance(country_sources, list):
            continue

        for source in country_sources:
            # Change jurisdiction field
            if source.get('jurisdiction') == 'GB':
                source['jurisdiction'] = 'UK'
                jurisdiction_changes += 1

            # Change any GB country codes in metadata
            if isinstance(source.get('wiki_links'), list):
                for link in source['wiki_links']:
                    if link.get('country') == 'GB':
                        link['country'] = 'UK'
                        field_changes += 1

            # Change GB in any text fields that reference country codes
            for field in ['notes', 'classification']:
                if isinstance(source.get(field), str):
                    if 'GB' in source[field] and 'United Kingdom' in source[field]:
                        source[field] = source[field].replace('GB', 'UK')
                        field_changes += 1

            # Fix company_inputs and person_inputs country codes
            for input_list_key in ['company_inputs', 'person_inputs']:
                if isinstance(source.get(input_list_key), list):
                    for input_entry in source[input_list_key]:
                        if input_entry.get('country') == 'gb':
                            input_entry['country'] = 'uk'
                            field_changes += 1

    print(f"✓ Changed {jurisdiction_changes} jurisdiction codes from GB to UK")
    print(f"✓ Changed {field_changes} field values from GB to UK\n")

    # Save updated sources
    print("Saving updated sources.json...")
    save_json(sources, SOURCES_FILE)

    # Final summary
    new_uk_count = len(sources.get('UK', []))
    print(f"\n=== Conversion Complete ===\n")
    print(f"Final state:")
    print(f"  - GB sources: 0 (removed)")
    print(f"  - UK sources: {new_uk_count}")
    print(f"  - Total changes: {jurisdiction_changes + field_changes}")
    print()

if __name__ == '__main__':
    convert_gb_to_uk()
