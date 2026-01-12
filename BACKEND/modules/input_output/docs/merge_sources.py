#!/usr/bin/env python3
"""
Merge registries.json + flows.json → sources.json
Clean, unified schema with NO cross-references.
"""

import json
from pathlib import Path
from collections import defaultdict

# Paths
OLD_MATRIX = Path(__file__).parent.parent / 'input_output' / 'matrix'
NEW_MATRIX = Path(__file__).parent / 'matrix'

REGISTRIES = OLD_MATRIX / 'registries.json'
FLOWS = OLD_MATRIX / 'flows.json'
MODULES_CORPORELLA = OLD_MATRIX / 'corporella.json'
MODULES_EYED = OLD_MATRIX / 'eyed.json'
MODULES_ALLDOM = OLD_MATRIX / 'alldom.json'
LEGEND = OLD_MATRIX / 'legend.json'
OUTPUT = NEW_MATRIX / 'sources.json'

def load_json(path):
    with open(path) as f:
        return json.load(f)

def resolve_legend_ids(id_list, legend):
    """Convert legend IDs to field names"""
    if not id_list:
        return []
    return [legend.get(str(id), f"unknown_{id}") for id in id_list]

def merge_sources():
    """Merge registries + flows + modules into unified sources.json"""

    registries = load_json(REGISTRIES)
    flows = load_json(FLOWS)
    corporella = load_json(MODULES_CORPORELLA)
    eyed = load_json(MODULES_EYED)
    alldom = load_json(MODULES_ALLDOM)
    legend = load_json(LEGEND)

    # Structure: { "jurisdiction_code": [ sources ] }
    unified = defaultdict(list)

    # === Process Registries (manual/wiki sources) ===
    for jurisdiction, entries in registries.items():
        for entry in entries:
            source = {
                "id": f"{entry['domain']}_{entry['type']}",
                "name": entry['name'],
                "jurisdiction": jurisdiction,
                "domain": entry.get('domain'),
                "url": entry.get('url'),
                "section": entry.get('section', 'misc'),
                "type": entry.get('type', 'unknown'),
                "access": entry.get('access', 'unknown'),
                "inputs": [],  # Registries don't specify structured inputs
                "outputs": entry.get('data_types', []),
                "notes": entry.get('description', ''),
                "flows": [],  # No structured flows for manual registries
                "metadata": {
                    "source": entry.get('source', 'wiki'),
                    "last_verified": None,
                    "reliability": "medium"  # Wiki-sourced
                }
            }
            unified[jurisdiction].append(source)

    # === Process Flows (ALEPH datasets with structured I/O) ===
    # flows is array of objects, each object has jurisdiction keys
    for flow_group in flows:
        if isinstance(flow_group, str):
            continue  # Skip any string entries
        for jurisdiction, flow_entries in flow_group.items():
            if not isinstance(flow_entries, list):
                continue
            for flow in flow_entries:
                # Group flows by source
                source_id = flow.get('source_id', 'unknown')
                source_label = flow.get('source_label', 'Unknown Source')

                # Check if source already exists
                existing = next(
                    (s for s in unified[jurisdiction] if s['id'] == f"aleph_{source_id}"),
                    None
                )

                flow_def = {
                    "input": flow.get('input_type'),
                    "output_schema": flow.get('output_schema'),
                    "output_fields": flow.get('output_columns_array', [])
                }

                if existing:
                    # Add flow to existing source
                    if flow_def not in existing['flows']:
                        existing['flows'].append(flow_def)
                    # Merge inputs/outputs
                    if flow.get('input_type') and flow['input_type'] not in existing['inputs']:
                        existing['inputs'].append(flow['input_type'])
                else:
                    # Create new source entry
                    source = {
                        "id": f"aleph_{source_id}",
                        "name": source_label,
                        "jurisdiction": jurisdiction,
                        "domain": "data.occrp.org",  # ALEPH domain
                        "url": f"https://data.occrp.org/datasets/{source_id}",
                        "section": "misc",  # ALEPH datasets are misc
                        "type": "dataset",
                        "access": "public",
                        "inputs": [flow.get('input_type')] if flow.get('input_type') else [],
                        "outputs": flow.get('output_columns_array', []),
                        "notes": f"ALEPH dataset: {source_label}",
                        "flows": [flow_def],
                        "metadata": {
                            "source": "aleph",
                            "source_id": source_id,
                            "last_verified": None,
                            "reliability": "high"  # ALEPH is vetted
                        }
                    }
                    unified[jurisdiction].append(source)

    # === Process Drill Search Modules (EYE-D, Corporella, AllDom) ===

    # EYE-D (OSINT platform)
    for module in eyed:
        primary_inputs = resolve_legend_ids(module.get('inputs', {}).get('primary', []), legend)
        secondary_inputs = resolve_legend_ids(module.get('inputs', {}).get('secondary', []), legend)
        all_inputs = primary_inputs + secondary_inputs
        outputs = resolve_legend_ids(module.get('outputs', []), legend)

        source = {
            "id": f"module_{module['module_name']}",
            "name": module.get('display_name', module['module_name']),
            "jurisdiction": "GLOBAL",  # Modules are global
            "domain": "localhost:8080",  # EYE-D service
            "url": f"http://localhost:8080",
            "section": "misc",
            "type": "osint",
            "access": "paywalled" if "Paywalled" in module.get('friction', '') else "public",
            "inputs": all_inputs,
            "outputs": outputs,
            "notes": module.get('description', ''),
            "flows": [],  # Module handles flows internally
            "metadata": {
                "source": "drill_module",
                "module_type": "osint",
                "location": module.get('location'),
                "reliability": "high"
            }
        }
        unified["GLOBAL"].append(source)

    # AllDom (domain intelligence)
    for module in alldom:
        primary_inputs = resolve_legend_ids(module.get('inputs', {}).get('primary', []), legend)
        outputs = resolve_legend_ids(module.get('outputs', []), legend)

        source = {
            "id": f"module_{module['module_name']}",
            "name": module.get('display_name', module['module_name']),
            "jurisdiction": "GLOBAL",
            "domain": "localhost",  # Local module
            "url": "http://localhost",
            "section": "misc",
            "type": "domain_intel",
            "access": "paywalled" if "Paywalled" in module.get('friction', '') else "public",
            "inputs": primary_inputs,
            "outputs": outputs,
            "notes": module.get('description', ''),
            "flows": [],
            "metadata": {
                "source": "drill_module",
                "module_type": "domain_intel",
                "location": module.get('location'),
                "reliability": "high"
            }
        }
        unified["GLOBAL"].append(source)

    # Corporella (corporate intelligence) - sample first entry to understand structure
    if corporella and len(corporella) > 0:
        # Corporella has different structure - country-specific flows
        for entry in corporella[:10]:  # Process sample entries for now
            if 'inputs' in entry and 'outputs' in entry:
                inputs = resolve_legend_ids(entry.get('inputs', {}).get('primary', []), legend)
                outputs = resolve_legend_ids(entry.get('outputs', []), legend)
                jurisdiction = entry.get('jurisdiction', 'GLOBAL')

                source = {
                    "id": f"module_corporella_{jurisdiction}",
                    "name": f"Corporella - {jurisdiction}",
                    "jurisdiction": jurisdiction,
                    "domain": "localhost:8000",
                    "url": "http://localhost:8000/api/corporella",
                    "section": "cr",
                    "type": "commercial_aggregator",
                    "access": "public",
                    "inputs": inputs,
                    "outputs": outputs,
                    "notes": "Corporate registry aggregator and enrichment",
                    "flows": [],
                    "metadata": {
                        "source": "drill_module",
                        "module_type": "corporate_intel",
                        "location": "python-backend/modules/corporella",
                        "reliability": "high"
                    }
                }
                unified[jurisdiction].append(source)

    # Sort entries within each jurisdiction
    for jurisdiction in unified:
        unified[jurisdiction].sort(key=lambda x: (x['section'], x['name']))

    # Convert to regular dict and save
    output_data = dict(unified)

    with open(OUTPUT, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Created {OUTPUT}")
    print(f"   Jurisdictions: {len(output_data)}")
    print(f"   Total sources: {sum(len(v) for v in output_data.values())}")

    # Stats
    registries_count = sum(1 for j in output_data.values() for s in j if s['metadata']['source'] == 'wiki')
    aleph_count = sum(1 for j in output_data.values() for s in j if s['metadata']['source'] == 'aleph')

    print(f"   Registry entries: {registries_count}")
    print(f"   ALEPH datasets: {aleph_count}")

if __name__ == '__main__':
    merge_sources()
