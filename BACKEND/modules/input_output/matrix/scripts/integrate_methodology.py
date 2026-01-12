#!/usr/bin/env python3
"""
Integrate mined_methodology.json into jurisdictions.json.

Takes 6,126 methodology patterns and adds them as proven methods per jurisdiction.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent
ARCHIVE_DIR = MATRIX_DIR / "_archive" / "legacy" / "mined"


def normalize_jurisdiction(jur: str) -> str:
    """Normalize jurisdiction code."""
    normalizations = {
        "GB": "UK",
        "GL": "GLOBAL",
    }
    return normalizations.get(jur.upper(), jur.upper())


def normalize_method(method: str) -> str:
    """Normalize method names."""
    method_mapping = {
        "corporate_registry_search": "REGISTRY_COMPANY",
        "court_search": "LITIGATION_COURT",
        "media_monitoring": "MEDIA_MONITORING",
        "osint": "OSINT_GENERAL",
        "humint": "HUMINT",
        "social_media_analysis": "OSINT_SOCIAL",
        "corporate_filings_analysis": "REGISTRY_FILINGS",
        "regulatory_search": "REGULATORY_SEARCH",
        "property_search": "ASSET_PROPERTY",
        "asset_search": "ASSET_SEARCH",
        "sanctions_screening": "COMPLIANCE_SANCTIONS",
        "pep_screening": "COMPLIANCE_PEP",
        "litigation_search": "LITIGATION_SEARCH",
        "archive_research": "ARCHIVE_RESEARCH",
        "domain_research": "DOMAIN_INTEL",
    }
    return method_mapping.get(method.lower(), method.upper())


def integrate_methodology():
    """Main integration function."""

    # Load methodology patterns
    meth_file = ARCHIVE_DIR / "mined_methodology.json"
    print(f"Loading {meth_file}...")
    with open(meth_file) as f:
        meth_data = json.load(f)

    patterns = meth_data.get("patterns", [])
    print(f"  Found {len(patterns)} methodology patterns")

    # Load jurisdictions.json
    jur_file = MATRIX_DIR / "jurisdictions.json"
    print(f"Loading {jur_file}...")
    with open(jur_file) as f:
        jur_data = json.load(f)

    jurisdictions = jur_data.get("jurisdictions", {})
    print(f"  Found {len(jurisdictions)} jurisdictions")

    # Group patterns by jurisdiction
    grouped = defaultdict(lambda: defaultdict(list))
    stats = {
        "patterns_processed": 0,
        "jurisdictions_updated": 0,
        "methods": defaultdict(int),
        "friction": defaultdict(int),
    }

    for p in patterns:
        jur = normalize_jurisdiction(p.get("jurisdiction", "GLOBAL"))
        method = normalize_method(p.get("method", "unknown"))
        success = p.get("success", True)
        friction = p.get("friction", "unknown")

        if success:
            grouped[jur][method].append({
                "source": p.get("source_used", ""),
                "description": p.get("description", ""),
                "friction": friction,
            })
            stats["methods"][method] += 1
            stats["friction"][friction] += 1
            stats["patterns_processed"] += 1

    print(f"\nGrouped into {len(grouped)} jurisdictions")

    # Merge into jurisdictions
    for jur, methods in grouped.items():
        if jur not in jurisdictions:
            jurisdictions[jur] = {
                "name": jur,
                "legal_notes": "",
                "entity_types": [],
                "id_formats": [],
                "data_availability": {"accessible": [], "restricted": [], "unavailable": []},
                "source_domains": [],
                "dead_ends": [],
            }

        # Add methodology section
        existing_meth = jurisdictions[jur].get("proven_methods", {})

        for method, examples in methods.items():
            if method not in existing_meth:
                existing_meth[method] = {
                    "count": len(examples),
                    "friction_profile": {},
                    "sample_sources": [],
                }

            # Update count
            existing_meth[method]["count"] += len(examples)

            # Update friction profile
            for ex in examples:
                f = ex.get("friction", "unknown")
                existing_meth[method]["friction_profile"][f] = \
                    existing_meth[method]["friction_profile"].get(f, 0) + 1

            # Add sample sources (limit to 5)
            sources = [ex.get("source", "") for ex in examples if ex.get("source")]
            existing = existing_meth[method].get("sample_sources", [])
            new_sources = [s for s in sources if s and s not in existing][:5 - len(existing)]
            existing_meth[method]["sample_sources"] = existing + new_sources

        jurisdictions[jur]["proven_methods"] = existing_meth
        stats["jurisdictions_updated"] += 1

    # Update metadata
    jur_data["meta"]["methodology_integrated"] = True
    jur_data["meta"]["methodology_count"] = stats["patterns_processed"]
    jur_data["meta"]["updated_at"] = datetime.now().isoformat()
    jur_data["jurisdictions"] = jurisdictions

    # Write back
    print(f"\nWriting updated jurisdictions.json...")
    with open(jur_file, "w") as f:
        json.dump(jur_data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== INTEGRATION STATS ===")
    print(f"Patterns processed: {stats['patterns_processed']}")
    print(f"Jurisdictions updated: {stats['jurisdictions_updated']}")

    print(f"\nTop methods:")
    for method, count in sorted(stats["methods"].items(), key=lambda x: -x[1])[:15]:
        print(f"  {method}: {count}")

    print(f"\nFriction distribution:")
    for friction, count in sorted(stats["friction"].items(), key=lambda x: -x[1]):
        print(f"  {friction}: {count}")


if __name__ == "__main__":
    integrate_methodology()
