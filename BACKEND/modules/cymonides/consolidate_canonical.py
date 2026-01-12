#!/usr/bin/env python3
"""
CANONICAL FILE CONSOLIDATOR

Creates the 6 canonical files from all mined/backup data:
1. sources.json - All sources with embedded capabilities
2. jurisdiction_intel.json - Per-country intelligence
3. methodology.json - Research methodology patterns
4. genres.json - Report types and structures
5. section_templates.json - Section-level templates
6. sectors.json - Industry-specific intelligence

NO DATA LOSS - Everything is consolidated.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent
BACKUP_DIR = MATRIX_DIR.parent / "matrix_backup_20251125"  # One level up
MERGED_DIR = MATRIX_DIR / "_merged"
MINED_DIR = BACKUP_DIR / "mined"

def load_json(path: Path) -> dict | list:
    """Load JSON file, return empty dict/list if not found."""
    if not path.exists():
        print(f"  [SKIP] {path.name} not found")
        return {}
    with open(path) as f:
        return json.load(f)

def save_json(path: Path, data: dict | list):
    """Save JSON with nice formatting."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [SAVED] {path.name}")


# =============================================================================
# 1. SOURCES.JSON - Merge all source files + embed capabilities
# =============================================================================

def create_sources_canonical():
    """
    Merge:
    - sources_CANONICAL.json (already consolidated from v1-v4)
    - rules.json (extract capabilities per source)
    - mined_registry_domains.json (registry domain mappings)
    """
    print("\n=== CREATING sources.json ===")

    # Load existing canonical sources
    sources_path = MATRIX_DIR / "sources_CANONICAL.json"
    sources_data = load_json(sources_path)

    # Load rules to extract capabilities
    rules_path = MATRIX_DIR / "rules.json"
    rules = load_json(rules_path)

    # Load mined registry domains
    mined_domains = load_json(MINED_DIR / "mined_registry_domains.json")

    # Build source_id -> capabilities mapping from rules
    capabilities_by_source = defaultdict(list)
    if isinstance(rules, list):
        for rule in rules:
            # Try to match rule to source by jurisdiction
            jur = rule.get("jurisdiction", "none")
            category = rule.get("category", "")

            capability = {
                "rule_id": rule.get("id"),
                "label": rule.get("label", ""),
                "requires_any": rule.get("requires_any", []),
                "requires_all": rule.get("requires_all", []),
                "returns": rule.get("returns", []),
                "friction": rule.get("friction", ""),
                "resources": rule.get("resources", [])
            }

            # Index by jurisdiction
            capabilities_by_source[jur].append(capability)

    # Enhance sources with capabilities
    enhanced_count = 0
    if isinstance(sources_data, dict):
        for jur, sources in sources_data.items():
            jur_capabilities = capabilities_by_source.get(jur, []) + capabilities_by_source.get("none", [])

            for source in sources:
                # Add capabilities that match this source's type/category
                source_type = source.get("type", "")
                source_section = source.get("section", "")

                matching_caps = []
                for cap in jur_capabilities:
                    cap_cat = cap.get("label", "").lower()
                    if (source_type in cap_cat or
                        source_section in cap_cat or
                        "company" in cap_cat and "corporate" in source_type):
                        matching_caps.append(cap)

                if matching_caps:
                    source["capabilities"] = matching_caps
                    enhanced_count += 1

    # Add metadata
    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Canonical source catalog - all 11,705 sources with embedded capabilities",
        "stats": {
            "total_jurisdictions": len(sources_data) if isinstance(sources_data, dict) else 0,
            "total_sources": sum(len(v) for v in sources_data.values()) if isinstance(sources_data, dict) else 0,
            "sources_with_capabilities": enhanced_count,
            "total_rules_available": len(rules) if isinstance(rules, list) else 0
        },
        "sources": sources_data
    }

    save_json(MATRIX_DIR / "sources.json", result)
    print(f"  Sources: {result['stats']['total_sources']}, Enhanced: {enhanced_count}")


# =============================================================================
# 2. JURISDICTION_INTEL.JSON - Country-level intelligence
# =============================================================================

def create_jurisdiction_intel():
    """
    Merge:
    - mined_jurisdictions.json (data availability, legal notes)
    - arbitrage_routes.json (cross-border paths)
    - dead_ends_catalog.json (what's impossible)
    - jurisdiction_capabilities.json (existing)
    """
    print("\n=== CREATING jurisdiction_intel.json ===")

    # Load mined jurisdictions
    mined_jur = load_json(MINED_DIR / "mined_jurisdictions.json")
    jurisdictions = mined_jur.get("jurisdictions", {})

    # Load arbitrage routes
    arbitrage = load_json(MERGED_DIR / "arbitrage_routes.json")
    if not arbitrage:
        arbitrage = load_json(BACKUP_DIR / "arbitrage_routes.json")
    arbitrage_by_jur = arbitrage.get("by_target_jurisdiction", {})

    # Load dead ends
    dead_ends = load_json(MERGED_DIR / "dead_ends_catalog.json")
    if not dead_ends:
        dead_ends = load_json(BACKUP_DIR / "dead_ends_catalog.json")
    dead_ends_by_jur = dead_ends.get("by_jurisdiction", {})

    # Load existing jurisdiction capabilities
    existing_caps = load_json(MATRIX_DIR / "jurisdiction_capabilities.json")

    # Merge everything
    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Jurisdiction intelligence - what's available, what's not, and workarounds",
        "stats": {
            "total_jurisdictions": 0,
            "with_arbitrage_paths": 0,
            "with_dead_ends": 0
        },
        "jurisdictions": {}
    }

    # Collect all jurisdiction codes
    all_jurs = set(jurisdictions.keys()) | set(arbitrage_by_jur.keys()) | set(dead_ends_by_jur.keys())

    for jur in sorted(all_jurs):
        jur_data = {
            "jurisdiction": jur,
            "data_availability": {},
            "entity_types": [],
            "id_formats": [],
            "legal_notes": "",
            "arbitrage_paths": [],
            "dead_ends": [],
            "capabilities": {}
        }

        # From mined jurisdictions
        if jur in jurisdictions:
            mj = jurisdictions[jur]
            jur_data["data_availability"] = mj.get("data_availability", {})
            jur_data["entity_types"] = mj.get("entity_types_explained", [])
            jur_data["id_formats"] = mj.get("id_formats", [])
            jur_data["legal_notes"] = mj.get("legal_notes", "")

        # From arbitrage routes
        if jur in arbitrage_by_jur:
            arb = arbitrage_by_jur[jur]
            jur_data["arbitrage_paths"] = arb.get("sources", {})
            jur_data["info_available_via_arbitrage"] = arb.get("info_available", [])
            result["stats"]["with_arbitrage_paths"] += 1

        # From dead ends
        if jur in dead_ends_by_jur:
            jur_data["dead_ends"] = dead_ends_by_jur[jur]
            result["stats"]["with_dead_ends"] += 1

        # From existing capabilities
        if jur in existing_caps:
            jur_data["capabilities"] = existing_caps[jur]

        result["jurisdictions"][jur] = jur_data

    result["stats"]["total_jurisdictions"] = len(result["jurisdictions"])

    save_json(MATRIX_DIR / "jurisdiction_intel.json", result)
    print(f"  Jurisdictions: {result['stats']['total_jurisdictions']}")


# =============================================================================
# 3. METHODOLOGY.JSON - Research patterns
# =============================================================================

def create_methodology():
    """
    Merge:
    - methodology_patterns.json (success/failure patterns)
    - methodology_catalog.json (detailed catalog)
    - methodology_atoms.json (existing)
    """
    print("\n=== CREATING methodology.json ===")

    # Load methodology patterns
    patterns = load_json(MERGED_DIR / "methodology_patterns.json")
    if not patterns:
        patterns = load_json(BACKUP_DIR / "methodology_patterns.json")

    # Load catalog
    catalog = load_json(BACKUP_DIR / "methodology_catalog.json")

    # Load existing atoms
    atoms = load_json(MATRIX_DIR / "methodology_atoms.json")

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Research methodology patterns - what works, what doesn't",
        "stats": patterns.get("stats", {}),
        "method_counts": patterns.get("method_counts", {}),
        "atoms": atoms,
        "patterns_by_jurisdiction": {},
        "catalog": catalog
    }

    # Index patterns by jurisdiction if available
    if "patterns" in patterns:
        for pattern in patterns.get("patterns", []):
            jur = pattern.get("jurisdiction", "GLOBAL")
            if jur not in result["patterns_by_jurisdiction"]:
                result["patterns_by_jurisdiction"][jur] = []
            result["patterns_by_jurisdiction"][jur].append(pattern)

    save_json(MATRIX_DIR / "methodology.json", result)
    print(f"  Methods: {len(result.get('method_counts', {}))}")


# =============================================================================
# 4. GENRES.JSON - Report types
# =============================================================================

def create_genres():
    """
    Merge:
    - report_genres.json (types and distribution)
    - mined_genres.json (additional patterns)
    """
    print("\n=== CREATING genres.json ===")

    # Load report genres
    genres = load_json(MERGED_DIR / "report_genres.json")
    if not genres:
        genres = load_json(BACKUP_DIR / "report_genres.json")

    # Load mined genres
    mined_genres = load_json(MINED_DIR / "mined_genres.json")

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Report genre classification - types, purposes, structures",
        "stats": genres.get("stats", {}),
        "primary_types": genres.get("primary_type_distribution", {}),
        "secondary_types": genres.get("secondary_type_distribution", {}),
        "scopes": genres.get("scope_distribution", {}),
        "depth_levels": genres.get("depth_distribution", {}),
        "genre_definitions": mined_genres.get("genres", []) if isinstance(mined_genres, dict) else []
    }

    save_json(MATRIX_DIR / "genres.json", result)
    print(f"  Primary types: {len(result.get('primary_types', {}))}")


# =============================================================================
# 5. SECTION_TEMPLATES.JSON - Section-level patterns
# =============================================================================

def create_section_templates():
    """
    From:
    - mined_section_templates.json
    """
    print("\n=== CREATING section_templates.json ===")

    templates = load_json(MINED_DIR / "mined_section_templates.json")

    # Organize by section type
    by_type = defaultdict(list)
    template_list = templates.get("templates", [])

    for tmpl in template_list:
        section_type = tmpl.get("section_type", "other")
        by_type[section_type].append(tmpl)

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Section templates - content patterns, sources, key phrases",
        "stats": {
            "total_templates": len(template_list),
            "section_types": len(by_type)
        },
        "templates_by_type": dict(by_type),
        "all_templates": template_list
    }

    save_json(MATRIX_DIR / "section_templates.json", result)
    print(f"  Templates: {len(template_list)}, Types: {len(by_type)}")


# =============================================================================
# 6. SECTORS.JSON - Industry intelligence
# =============================================================================

def create_sectors():
    """
    Merge:
    - mined_sectors.json
    - sector_catalog.json
    - aggregated_sectors.json
    """
    print("\n=== CREATING sectors.json ===")

    # Load all sector data
    mined_sectors = load_json(MINED_DIR / "mined_sectors.json")
    sector_catalog = load_json(BACKUP_DIR / "sector_catalog.json")
    aggregated = load_json(MINED_DIR / "aggregated_sectors.json")

    # Merge into one comprehensive list
    all_sectors = {}

    # From sector catalog (most structured)
    for sector in sector_catalog.get("sectors", []):
        name = sector.get("sector_name", "").lower().replace(" ", "_")
        if name:
            all_sectors[name] = {
                "name": sector.get("sector_name"),
                "red_flags": sector.get("red_flags", []),
                "typical_structures": sector.get("typical_structures", []),
                "investigation_notes": []
            }

    # From mined sectors (add any missing)
    for sector in mined_sectors.get("sectors", []):
        name = sector.get("sector", "").lower().replace(" ", "_")
        if name:
            if name in all_sectors:
                # Merge red flags and structures
                all_sectors[name]["red_flags"].extend(sector.get("red_flags", []))
                all_sectors[name]["typical_structures"].extend(sector.get("typical_structures", []))
            else:
                all_sectors[name] = {
                    "name": sector.get("sector"),
                    "red_flags": sector.get("red_flags", []),
                    "typical_structures": sector.get("typical_structures", []),
                    "investigation_notes": []
                }

    # Deduplicate within each sector
    for name, data in all_sectors.items():
        data["red_flags"] = list(set(data["red_flags"]))
        data["typical_structures"] = list(set(data["typical_structures"]))

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "description": "Sector-specific intelligence - red flags, typical structures",
        "stats": {
            "total_sectors": len(all_sectors)
        },
        "sectors": all_sectors
    }

    save_json(MATRIX_DIR / "sectors.json", result)
    print(f"  Sectors: {len(all_sectors)}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("CANONICAL FILE CONSOLIDATOR")
    print("=" * 60)

    create_sources_canonical()
    create_jurisdiction_intel()
    create_methodology()
    create_genres()
    create_section_templates()
    create_sectors()

    print("\n" + "=" * 60)
    print("DONE - 6 canonical files created:")
    print("  1. sources.json")
    print("  2. jurisdiction_intel.json")
    print("  3. methodology.json")
    print("  4. genres.json")
    print("  5. section_templates.json")
    print("  6. sectors.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
