#!/usr/bin/env python3
"""
Complete Audit: Check EVERY file in input_output/ against sources.json
Identify what's integrated and what's missing
"""

import json
from pathlib import Path
from typing import Dict, Set

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_OUTPUT = PROJECT_ROOT / 'input_output'
OUTPUT_DIR = PROJECT_ROOT / 'input_output2' / 'matrix'
SOURCES_FILE = OUTPUT_DIR / 'sources.json'

def load_json(path: Path) -> dict:
    """Load JSON file"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"   ERROR loading {path.name}: {e}")
        return None

def get_all_files(directory: Path) -> list:
    """Get all files recursively, excluding hidden and common excludes"""
    files = []
    excludes = {'.DS_Store', '__pycache__', 'node_modules', '.git'}

    for item in directory.rglob('*'):
        if item.is_file():
            # Skip if in excluded directories
            if any(ex in item.parts for ex in excludes):
                continue
            # Skip if hidden file
            if item.name.startswith('.'):
                continue
            files.append(item)

    return sorted(files)

def check_file_integration(file_path: Path, sources: dict) -> dict:
    """Check if file's data is in sources.json"""
    result = {
        'file': file_path.name,
        'path': str(file_path.relative_to(INPUT_OUTPUT)),
        'size': file_path.stat().st_size,
        'type': file_path.suffix,
        'integrated': 'UNKNOWN',
        'details': ''
    }

    # Known integrated files
    integrated_files = {
        'wiki_registries.json': 'Phase 1 - Base sources',
        'wiki_sections_processed.json': 'Phase 2 - Wiki context',
        'wiki_io_extractions.json': 'Phase 3 - Structured I/O',
        'aleph_matrix_processed.json': 'Phase 4 - ALEPH metadata',
        'inputs_company_by_country_dataset.csv': 'Phase 6 - Company inputs',
        'inputs_person_by_country_dataset.csv': 'Phase 6 - Person inputs',
    }

    # Flows integrated
    if file_path.parent.name == 'flows' and file_path.suffix == '.csv':
        if file_path.name != 'entity_flow_20250823_013733.csv':
            result['integrated'] = 'YES'
            result['details'] = 'Phase 7 - Flow output mappings'
            return result
        else:
            result['integrated'] = 'MODULES'
            result['details'] = 'Module flows (not registry flows)'
            return result

    # Check by filename
    if file_path.name in integrated_files:
        result['integrated'] = 'YES'
        result['details'] = integrated_files[file_path.name]
        return result

    # Matrix files - check if preserved
    if file_path.parent.name == 'matrix':
        preserved = {
            'ftm_schema_mapping.json': 'Preserved as-is',
            'entity_class_type_matrix.json': 'Preserved as-is',
            'database_capabilities.json': 'Preserved as-is',
            'graph_schema.json': 'Preserved as-is',
            'edge_types.json': 'Preserved as-is',
            'legend.json': 'Extracted from investigations_routing_spec',
            'rules.json': 'Extracted from investigations_routing_spec',
            'field_meta.json': 'Extracted from investigations_routing_spec',
        }

        if file_path.name in preserved:
            result['integrated'] = 'PRESERVED'
            result['details'] = preserved[file_path.name]
            return result

        # Integrated into sources
        if file_path.name in ['registries.json', 'flows.json', 'corporella.json', 'eyed.json', 'alldom.json']:
            result['integrated'] = 'YES'
            result['details'] = 'Phase 1 - Merged into sources.json'
            return result

        # Delete candidates
        delete_files = {
            'company_bang_urls.json': 'DELETE - DuckDuckGo bangs (user rejected)',
            'datasets.json': 'DELETE - Redundant with flows.json',
            'index.json': 'DELETE - Just pointers',
            'metadata.json': 'DELETE - Auto-generated',
            'meta_description.json': 'DELETE - Fragment',
            'meta_friction_order.json': 'DELETE - Fragment',
            'meta_generated_at.json': 'DELETE - Fragment',
            'meta_last_updated.json': 'DELETE - Fragment',
            'meta_spec_version.json': 'DELETE - Fragment',
        }

        if file_path.name in delete_files:
            result['integrated'] = 'DELETE'
            result['details'] = delete_files[file_path.name]
            return result

        # Template files
        if 'template' in file_path.name.lower() or file_path.name in [
            'node_templates.json', 'additional_specs.json', 'code_snippets.json',
            'documentation.json', 'project_docs.json', 'readme_graph.json'
        ]:
            result['integrated'] = 'TEMPLATE'
            result['details'] = 'Template/documentation file'
            return result

    # Large master files
    master_files = {
        'master_matrix.json': 'SUPERSEDED - Legacy version (2.3 MB)',
        'master_input_output_matrix.json': 'SUPERSEDED - Legacy version (3.6 MB)',
        'master_input_output_matrix_with_breaches.json': 'DELETE - Duplicate (3.5 MB)',
        'wiki_master_schema.json': 'SOURCE - Already integrated in Phases 2-6',
        'investigations_routing_spec.json': 'SOURCE - Extracted to legend/rules/field_meta',
        'investigation_io_rules_v1_1.json': 'DELETE - Duplicate of routing_spec',
        'investigation_io_rules_v1_1 copy.json': 'DELETE - Backup copy',
        'wiki_io_extractions_backup_af.json': 'DELETE - Backup',
        'raidforums_master.json': 'SEPARATE - Breach data (27 MB, keep separate)',
        'database_capabilities.json': 'PRESERVED - Copied to input_output2/matrix/',
    }

    if file_path.name in master_files:
        status = 'SOURCE' if 'SOURCE' in master_files[file_path.name] else 'DELETE' if 'DELETE' in master_files[file_path.name] else 'PRESERVED' if 'PRESERVED' in master_files[file_path.name] else 'REVIEW'
        result['integrated'] = status
        result['details'] = master_files[file_path.name]
        return result

    # Unknown file
    result['integrated'] = 'UNKNOWN'
    result['details'] = 'Needs manual review'

    return result

def audit_all():
    """Audit ALL files in input_output/"""
    print("\n=== COMPLETE FILE AUDIT ===\n")
    print("Scanning input_output/ directory...\n")

    all_files = get_all_files(INPUT_OUTPUT)
    print(f"Found {len(all_files)} files\n")

    # Load sources for reference
    sources = load_json(SOURCES_FILE)

    # Categorize files
    categories = {
        'YES': [],
        'PRESERVED': [],
        'MODULES': [],
        'SOURCE': [],
        'TEMPLATE': [],
        'DELETE': [],
        'SEPARATE': [],
        'SUPERSEDED': [],
        'UNKNOWN': []
    }

    for file_path in all_files:
        result = check_file_integration(file_path, sources)
        status = result['integrated']
        if status in categories:
            categories[status].append(result)
        else:
            categories['UNKNOWN'].append(result)

    # Print results
    print("=" * 80)
    print("INTEGRATION STATUS BY CATEGORY")
    print("=" * 80)

    for category in ['YES', 'PRESERVED', 'MODULES', 'SOURCE', 'TEMPLATE', 'DELETE', 'SEPARATE', 'SUPERSEDED', 'UNKNOWN']:
        files = categories[category]
        if not files:
            continue

        print(f"\n{category} ({len(files)} files)")
        print("-" * 80)

        for item in files:
            size_mb = item['size'] / 1024 / 1024
            if size_mb > 1:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_kb = item['size'] / 1024
                size_str = f"{size_kb:.0f} KB"

            print(f"  {item['file']:<50} {size_str:>10}")
            print(f"    → {item['details']}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files scanned: {len(all_files)}")
    print(f"Integrated (YES): {len(categories['YES'])}")
    print(f"Preserved separately: {len(categories['PRESERVED'])}")
    print(f"Module files: {len(categories['MODULES'])}")
    print(f"Source files (already integrated): {len(categories['SOURCE'])}")
    print(f"Template/docs: {len(categories['TEMPLATE'])}")
    print(f"Ready to delete: {len(categories['DELETE'])}")
    print(f"Keep separate: {len(categories['SEPARATE'])}")
    print(f"Superseded/legacy: {len(categories['SUPERSEDED'])}")
    print(f"Unknown/needs review: {len(categories['UNKNOWN'])}")

    # Critical check - any data files not integrated?
    critical = []
    for item in categories['UNKNOWN']:
        if item['type'] in ['.json', '.csv'] and 'template' not in item['file'].lower():
            critical.append(item)

    if critical:
        print("\n" + "=" * 80)
        print("⚠️  CRITICAL: UNKNOWN DATA FILES THAT NEED REVIEW")
        print("=" * 80)
        for item in critical:
            print(f"  {item['path']}")
    else:
        print("\n✅ All data files accounted for!")

if __name__ == '__main__':
    audit_all()
