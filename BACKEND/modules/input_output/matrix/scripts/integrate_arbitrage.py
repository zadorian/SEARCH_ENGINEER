#!/usr/bin/env python3
"""
Integrate mined_arbitrage.json into flows.json as ARBITRAGE_* flows.

Takes 859 cross-jurisdictional arbitrage patterns and adds them as special flows.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent
MINED_DIR = MATRIX_DIR.parent / "matrix_backup_20251125" / "mined"


def normalize_jurisdiction(jur: str) -> str:
    """Normalize jurisdiction code (GB -> UK, etc.)."""
    normalizations = {
        "GB": "UK",
        "GL": "GLOBAL",
    }
    return normalizations.get(jur.upper(), jur.upper())


def generate_flow_id(pattern: dict) -> str:
    """Generate a unique flow ID for an arbitrage pattern."""
    target = pattern.get("target_jurisdiction", "")
    source = pattern.get("source_jurisdiction", "")
    entity = pattern.get("target_entity", "")
    hash_input = f"{target}:{source}:{entity}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    return f"ARBITRAGE_{source}_TO_{target}_{short_hash}"


def map_arbitrage_type(arb_type: str) -> str:
    """Map arbitrage type to a standardized category."""
    type_mapping = {
        "regulatory_overlap": "REGULATORY",
        "foreign_filing": "FOREIGN_FILING",
        "subsidiary_disclosure": "SUBSIDIARY",
        "parent_company_disclosure": "PARENT_CO",
        "beneficial_ownership_disclosure": "UBO",
        "beneficial_ownership": "UBO",
        "treaty_access": "TREATY",
        "regulatory_oversight": "REGULATORY",
    }
    return type_mapping.get(arb_type, "OTHER")


def map_info_to_output_columns(info_obtained: list) -> list:
    """Map info_obtained to standardized output column names."""
    output_mapping = {
        "ownership_structure": "company_shareholders",
        "ownership structure": "company_shareholders",
        "beneficial_ownership": "company_ubo",
        "beneficial ownership": "company_ubo",
        "shareholder_information": "company_shareholders",
        "shareholding_percentages": "company_shareholder_percentage",
        "director_information": "company_directors",
        "director information": "company_directors",
        "directorship": "person_directorship",
        "directorships": "person_directorships",
        "ownership transfers": "company_ownership_changes",
        "regulatory approvals": "company_regulatory_status",
        "annual reports": "company_annual_reports",
        "financial information": "company_financials",
        "residential_address": "person_address",
        "residential_addresses": "person_address",
        "passport_number": "person_id_number",
        "corporate_connections": "entity_connections",
        "entity_affiliations": "entity_connections",
        "asset_ownership": "person_assets",
        "company_ownership": "company_shareholders",
        "parent company details": "company_parent",
        "ultimate parent company": "company_ultimate_parent",
        "ownership chain": "company_ownership_chain",
    }

    result = []
    for info in info_obtained:
        info_lower = info.lower().strip()
        mapped = output_mapping.get(info_lower)
        if mapped:
            result.append(mapped)
        else:
            # Create a generic column name from the info
            clean = info_lower.replace(" ", "_").replace("-", "_")
            result.append(clean)
    return list(set(result))


def integrate_arbitrage():
    """Main integration function."""

    # Load mined arbitrage
    arb_file = MINED_DIR / "mined_arbitrage.json"
    print(f"Loading {arb_file}...")
    with open(arb_file) as f:
        arb_data = json.load(f)

    patterns = arb_data.get("arbitrage_patterns", [])
    print(f"  Found {len(patterns)} arbitrage patterns")

    # Load flows.json
    flows_file = MATRIX_DIR / "flows.json"
    print(f"Loading {flows_file}...")
    with open(flows_file) as f:
        flows_data = json.load(f)

    flows = flows_data.get("flows", {})
    print(f"  Found {len(flows)} flow categories, {flows_data['meta'].get('total_flows', 0)} total flows")

    # Track stats
    stats = {
        "arbitrage_added": 0,
        "jurisdictions_updated": 0,
        "new_jurisdictions": 0,
        "by_type": defaultdict(int),
    }

    # Group patterns by SOURCE jurisdiction (where to look)
    # But also add to TARGET jurisdiction (what you're looking for)
    existing_ids = set()
    for jur, jur_flows in flows.items():
        for f in jur_flows:
            existing_ids.add(f.get("id", f.get("source_id", "")))

    for pattern in patterns:
        source_jur = normalize_jurisdiction(pattern.get("source_jurisdiction", ""))
        target_jur = normalize_jurisdiction(pattern.get("target_jurisdiction", ""))

        if not source_jur:
            continue

        flow_id = generate_flow_id(pattern)

        # Skip if already exists
        if flow_id in existing_ids:
            continue

        arb_type = pattern.get("arbitrage_type", "unknown")
        info_obtained = pattern.get("info_obtained", [])

        # Create the arbitrage flow
        arbitrage_flow = {
            "id": flow_id,
            "kind": "arbitrage",
            "arbitrage_type": map_arbitrage_type(arb_type),
            "arbitrage_subtype": arb_type,
            "source_jurisdiction": source_jur,
            "target_jurisdiction": target_jur,
            "target_entity": pattern.get("target_entity", ""),
            "source_registry": pattern.get("source_registry", ""),
            "info_obtainable": info_obtained,
            "output_columns": map_info_to_output_columns(info_obtained),
            "explanation": pattern.get("explanation", ""),
            "reliability": "high" if arb_type in ["regulatory_overlap", "foreign_filing"] else "medium",
            "input_type": "entity_name",  # Usually start with an entity name
            "output_schema": "CrossJurisdictionalIntel",
        }

        # Add to source jurisdiction flows (where you look)
        if source_jur not in flows:
            flows[source_jur] = []
            stats["new_jurisdictions"] += 1

        flows[source_jur].append(arbitrage_flow)
        existing_ids.add(flow_id)
        stats["arbitrage_added"] += 1
        stats["by_type"][arb_type] += 1

    # Count updated jurisdictions
    for jur in flows:
        if any(f.get("kind") == "arbitrage" for f in flows[jur]):
            stats["jurisdictions_updated"] += 1

    # Update metadata
    flows_data["meta"]["arbitrage_integrated"] = True
    flows_data["meta"]["arbitrage_count"] = stats["arbitrage_added"]
    flows_data["meta"]["total_flows"] += stats["arbitrage_added"]
    flows_data["meta"]["updated_at"] = datetime.now().isoformat()
    flows_data["flows"] = flows

    # Write back
    print(f"\nWriting updated flows.json...")
    with open(flows_file, "w") as f:
        json.dump(flows_data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== INTEGRATION STATS ===")
    print(f"Arbitrage flows added: {stats['arbitrage_added']}")
    print(f"Jurisdictions updated: {stats['jurisdictions_updated']}")
    print(f"New jurisdictions created: {stats['new_jurisdictions']}")

    print(f"\nBy arbitrage type:")
    for arb_type, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
        print(f"  {arb_type}: {count}")


if __name__ == "__main__":
    integrate_arbitrage()
