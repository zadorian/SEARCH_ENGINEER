#!/usr/bin/env python3
"""
Phase 8: Integrate Breach Datasets from raidforums_master.json (MODULAR ADAPTATION)
Adds 23 breach datasets as searchable sources to the modular matrix structure.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_OUTPUT = PROJECT_ROOT / 'input_output'
RAIDFORUMS_FILE = PROJECT_ROOT / 'matrix' / 'input_output_archive' / 'raidforums_master.json'
MATRIX_DIR = INPUT_OUTPUT / 'matrix'
SOURCES_FILE = MATRIX_DIR / 'sources.json'
RULES_FILE = MATRIX_DIR / 'rules.json'
LOCAL_DB_FILE = MATRIX_DIR / 'local_databases.json'
LEGEND_FILE = MATRIX_DIR / 'legend.json'
FIELD_META_FILE = MATRIX_DIR / 'field_meta.json'

def load_json(path: Path) -> dict:
    """Load JSON file"""
    if not path.exists():
        print(f"Warning: File not found: {path}")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data: dict, path: Path):
    """Save JSON file"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")

def extract_fields_from_samples(samples: list) -> Set[str]:
    """Extract likely field names from breach data samples"""
    fields = set()

    for sample in samples:
        if 'preview' not in sample:
            continue

        for line in sample['preview'][:10]:  # Check first 10 lines
            # Common breach format: username:email:ip:password
            if ':' in line:
                parts = line.split(':')
                if len(parts) >= 3:
                    # Likely has email, password, maybe IP
                    if '@' in line:
                        fields.add('email')
                    # Check for IP pattern
                    if re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line):
                        fields.add('ip_address')
                    # Assume password field exists
                    fields.add('password')
                    fields.add('username')

    return fields

def create_breach_source(dataset_name: str, dataset_data: dict) -> dict:
    """Convert breach dataset to source format"""
    record = dataset_data['record']

    # Generate clean ID
    clean_name = re.sub(r'[^a-z0-9]+', '_', dataset_name.lower())
    clean_name = clean_name.strip('_')

    # Extract fields from samples
    detected_fields = extract_fields_from_samples(record.get('samples', []))
    if not detected_fields:
        # Default fields for breach datasets
        detected_fields = {'email', 'username', 'password', 'ip_address'}

    fields_list = sorted(list(detected_fields))

    source = {
        'id': f'breach_{clean_name}',
        'name': f'{dataset_name} Breach Dataset',
        'jurisdiction': 'GLOBAL',  # Breaches are global
        'domain': None,  # Local dataset
        'url': None,  # Local dataset
        'section': 'breaches',
        'type': 'breach_dataset',
        'access': 'offline',
        'inputs': fields_list.copy(),
        'outputs': fields_list.copy(),
        'notes': f'Breach dataset from {dataset_name}. Local dataset.',
        'flows': [],
        'metadata': {
            'source': 'raidforums',
            'dataset_root': record.get('dataset', ''),
            'file_count': len(record.get('files', [])),
            'classification': record.get('classification', {}),
            'last_verified': None,
            'reliability': 'high'  # Breach data is definitive
        },
        'breach_metadata': {
            'dataset': record.get('dataset'),
            'files': record.get('files', []),
            'sample_count': len(record.get('samples', []))
        }
    }

    return source

def integrate_breaches():
    """Add breach datasets to modular sources"""
    print("\n=== Phase 8: Integrating Breach Datasets (Modular) ===\n")

    # Load raidforums data
    print("Loading raidforums_master.json...")
    if not RAIDFORUMS_FILE.exists():
        print(f"Error: {RAIDFORUMS_FILE} not found.")
        return
        
    raidforums = load_json(RAIDFORUMS_FILE)
    datasets = raidforums.get('datasets', {})
    print(f"✓ Found {len(datasets)} breach datasets\n")

    # Load existing sources (if any, might be empty list or dict)
    print("Loading sources.json...")
    sources = load_json(SOURCES_FILE)
    
    # Ensure sources is a dict for grouping by jurisdiction
    if isinstance(sources, list):
        print("Warning: sources.json is a list. Converting to jurisdiction-based dict.")
        new_sources = {}
        for s in sources:
            jur = s.get('jurisdiction', 'GLOBAL')
            if jur not in new_sources:
                new_sources[jur] = []
            new_sources[jur].append(s)
        sources = new_sources
    
    if not sources:
        sources = {}

    total_sources_before = sum(len(v) if isinstance(v, list) else 0 for v in sources.values())
    print(f"✓ Loaded {len(sources)} jurisdictions, {total_sources_before} sources\n")

    # Create GLOBAL category for breach datasets
    if 'GLOBAL' not in sources:
        sources['GLOBAL'] = []

    # Convert breach datasets to sources
    print("Converting breach datasets to source format...")
    breach_sources = []
    for dataset_name, dataset_data in datasets.items():
        source = create_breach_source(dataset_name, dataset_data)
        
        # Check for duplicates
        exists = False
        for existing in sources['GLOBAL']:
            if existing.get('id') == source['id']:
                exists = True
                break
        
        if not exists:
            breach_sources.append(source)
            sources['GLOBAL'].append(source)

    print(f"✓ Added {len(breach_sources)} new breach datasets to GLOBAL category\n")

    # Save enhanced sources
    print("Saving enhanced sources.json...")
    save_json(sources, SOURCES_FILE)

    # Final summary
    total_sources_after = sum(len(v) if isinstance(v, list) else 0 for v in sources.values())

    print("\n=== Phase 8 Complete ===\n")
    print(f"Jurisdictions: {len(sources)}")
    print(f"Total sources before: {total_sources_before}")
    print(f"Total sources after: {total_sources_after}")
    print(f"Breach datasets added: {len(breach_sources)}")
    print()

if __name__ == '__main__':
    integrate_breaches()
