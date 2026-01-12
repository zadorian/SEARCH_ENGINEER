#!/usr/bin/env python3
"""
Script to update local_databases.json with breach data definitions dynamically.
Adapts logic from the Archive's integrate_breach_data.py but targets the modular file structure.
"""

import json
from pathlib import Path
from datetime import datetime

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MATRIX_DIR = PROJECT_ROOT / 'input_output' / 'matrix'
LOCAL_DB_FILE = MATRIX_DIR / 'local_databases.json'
RULES_FILE = MATRIX_DIR / 'rules.json'
LEGEND_FILE = MATRIX_DIR / 'legend.json'
FIELD_META_FILE = MATRIX_DIR / 'field_meta.json'

# Helper to load/save JSON
def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"Warning: {path} does not exist.")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data: dict, path: Path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {path}")

def update_local_databases():
    print("\n=== Updating local_databases.json with Breach Data Defs ===\n")
    
    databases = load_json(LOCAL_DB_FILE)
    
    # Define the breach database capability (matches Archive definition)
    breach_db_def = {
        "description": "Country-specific breach data from RaidForums and other sources. Contains breach URLs, thread names, and metadata organized by jurisdiction.",
        "countries": [
            "ge", "jp", "br", "tr", "sg", "mx", "global", "it", "in", "ph",
            "hk", "uk", "th", "cn", "id", "ua", "pt", "ae", "by", "es",
            "ca", "de", "pe", "az", "fr", "us", "ru"
        ],
        "inputs": [
            "person_country",
            "company_country",
            "domain_url",
            "email"
        ],
        "outputs": [
            "breach_source_url",
            "breach_thread_name",
            "breach_date",
            "breach_status",
            "breach_comment",
            "breach_country"
        ],
        "sources": [
            "BREACH_EXPOSURE_LOOKUP",
            "BREACH_BY_COUNTRY"
        ],
        "metadata": {
            "source": "C0GN1T0-STANDALONE/search-engineer-mcp/Indexer/data_sources/breaches",
            "integrated_at": datetime.now().isoformat()
        }
    }

    # Update or add
    databases["breach_data.db"] = breach_db_def
    print(f"✓ Updated definition for breach_data.db in {LOCAL_DB_FILE}")
    
    save_json(databases, LOCAL_DB_FILE)

def update_rules():
    print("\n=== Updating rules.json with Breach Routing Rules ===\n")
    
    rules = load_json(RULES_FILE)
    if not isinstance(rules, list):
        print("Error: rules.json is not a list.")
        return

    breach_rule = {
        "id": "BREACH_BY_COUNTRY",
        "label": "Country-specific breach data lookup",
        "requires_any": [36, 48],  # person_country (36) or company_country (48) - IDs from Archive
        "requires_all": [],
        "returns": [
            146, 147, 148, 149, 150  # IDs from Archive logic
        ],
        "friction": "Open",
        "jurisdiction": "required",
        "notes": "Routes to country-specific breach databases.",
        "resources": [
            {
                "type": "database",
                "name": "breach_data.db",
                "query": "SELECT * FROM breaches WHERE country = ? ORDER BY date DESC"
            }
        ]
    }

    # Check if rule exists
    existing = False
    for i, r in enumerate(rules):
        if r.get('id') == 'BREACH_BY_COUNTRY':
            rules[i] = breach_rule
            existing = True
            print("✓ Updated existing BREACH_BY_COUNTRY rule")
            break
    
    if not existing:
        rules.append(breach_rule)
        print("✓ Added new BREACH_BY_COUNTRY rule")

    save_json(rules, RULES_FILE)

def update_field_metadata():
    print("\n=== Updating field_meta.json and legend.json ===\n")
    
    legend = load_json(LEGEND_FILE)
    field_meta = load_json(FIELD_META_FILE)

    # Fields to ensure exist (IDs based on Archive logic)
    new_fields = {
        "146": "breach_source_url",
        "147": "breach_thread_name",
        "148": "breach_date",
        "149": "breach_status",
        "150": "breach_comment",
        "151": "breach_country"
    }

    # Update Legend
    for fid, fname in new_fields.items():
        if fid not in legend:
            legend[fid] = fname
            print(f"  + Added to Legend: {fid} -> {fname}")

    # Update Field Meta
    breach_field_meta = {
        "breach_source_url": {
            "name": "breach_source_url",
            "group": 4,
            "role": "output",
            "datatype": "url",
            "cardinality": "single",
            "pii": False,
            "description": "Source URL of breach data (often archived)"
        },
        "breach_thread_name": {
            "name": "breach_thread_name",
            "group": 4,
            "role": "output",
            "datatype": "string",
            "cardinality": "single",
            "pii": False,
            "description": "Name/title of breach thread or discussion"
        },
        "breach_date": {
            "name": "breach_date",
            "group": 4,
            "role": "output",
            "datatype": "datetime",
            "cardinality": "single",
            "pii": False,
            "description": "Date of breach occurrence or disclosure"
        },
        "breach_status": {
            "name": "breach_status",
            "group": 4,
            "role": "output",
            "datatype": "string",
            "cardinality": "single",
            "pii": False,
            "description": "HTTP status or availability status of breach source"
        },
        "breach_comment": {
            "name": "breach_comment",
            "group": 4,
            "role": "output",
            "datatype": "string",
            "cardinality": "single",
            "pii": False,
            "description": "Commentary or description of breach context"
        },
        "breach_country": {
            "name": "breach_country",
            "group": 4,
            "role": "input|output",
            "datatype": "string",
            "cardinality": "single",
            "pii": False,
            "description": "Country/jurisdiction associated with breach"
        }
    }

    for fname, meta in breach_field_meta.items():
        if fname not in field_meta:
            field_meta[fname] = meta
            print(f"  + Added to Field Meta: {fname}")

    save_json(legend, LEGEND_FILE)
    save_json(field_meta, FIELD_META_FILE)

if __name__ == "__main__":
    update_local_databases()
    update_rules()
    update_field_metadata()
    print("\n=== Modular Update Complete ===\n")

