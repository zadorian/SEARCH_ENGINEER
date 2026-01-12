#!/usr/bin/env python3
"""
Integrate mined_dead_ends.json into jurisdictions.json

Takes 2,196 dead_end patterns, classifies them, and adds to jurisdictions.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent
MINED_DIR = MATRIX_DIR.parent / "matrix_backup_20251125" / "mined"

# === REASON CATEGORIES ===
REASON_PATTERNS = {
    "access_restricted": [
        r"not (publicly )?disclosed",
        r"not (publicly )?available",
        r"confidential",
        r"private",
        r"restricted",
        r"not required (to|by)",
        r"privacy",
        r"not mandated",
        r"protected",
        r"sealed",
        r"not accessible",
        r"prohibit",
        r"classified",
        r"not obliged",
    ],
    "no_records_found": [
        r"no (relevant )?results",
        r"no (instances|matches|records|evidence|profile|information|mention)",
        r"not found",
        r"unable to (find|locate|identify|determine|confirm|verify)",
        r"could not be (found|located|identified|confirmed|verified)",
        r"limited (media|coverage|information|disclosure)",
        r"minimal (media|profile|coverage)",
        r"no media",
        r"no apparent",
    ],
    "pending_action": [
        r"ongoing",
        r"current investigation",
        r"pending",
        r"time limit",
        r"scope limit",
        r"outside scope",
        r"beyond scope",
        r"engagement limit",
        r"investigation stage",
    ],
    "data_not_collected": [
        r"not collected",
        r"no registry",
        r"does not maintain",
        r"not tracked",
        r"not recorded",
        r"dissolved before",
        r"no system",
    ],
    "language_barrier": [
        r"language",
        r"translation",
        r"non-English",
        r"Arabic",
        r"Cyrillic",
        r"Chinese",
        r"requires translation",
    ],
    "technical_failure": [
        r"poor quality",
        r"technical",
        r"website (down|unavailable)",
        r"system (error|unavailable)",
    ],
}

# === SOUGHT CATEGORIES ===
SOUGHT_PATTERNS = {
    "beneficial_ownership": [
        r"beneficial owner",
        r"UBO",
        r"ultimate (owner|controlling)",
        r"ownership (structure|percentage|details|stake|share)",
        r"shareholder",
        r"equity",
        r"stake",
        r"controlling interest",
        r"owner.*identity",
    ],
    "financial_information": [
        r"financial",
        r"revenue",
        r"profit",
        r"loss",
        r"balance sheet",
        r"accounts",
        r"credit",
        r"transaction",
        r"payment",
        r"price",
        r"capital",
        r"fund",
        r"banking",
        r"invoice",
    ],
    "entity_connections": [
        r"connection",
        r"relationship",
        r"link",
        r"association",
        r"affiliation",
        r"subsidiary",
        r"parent company",
        r"group structure",
    ],
    "asset_information": [
        r"asset",
        r"property",
        r"real estate",
        r"land",
        r"vehicle",
        r"yacht",
        r"aircraft",
    ],
    "litigation_records": [
        r"litigation",
        r"lawsuit",
        r"court",
        r"legal (action|proceeding)",
        r"judgment",
        r"criminal",
        r"civil",
        r"case",
        r"prosecution",
        r"investigation records",
    ],
    "sanctions_adverse": [
        r"sanction",
        r"watchlist",
        r"adverse",
        r"PEP",
        r"politically exposed",
        r"OFAC",
        r"media mention",
    ],
    "directors_officers": [
        r"director",
        r"officer",
        r"executive",
        r"management",
        r"board",
        r"CEO",
        r"CFO",
        r"representative",
    ],
    "identity_verification": [
        r"identity",
        r"verification",
        r"face",
        r"photo",
        r"background",
        r"educational",
        r"qualification",
    ],
    "corporate_structure": [
        r"corporate structure",
        r"group structure",
        r"all subsidiar",
        r"company structure",
        r"organizational",
    ],
    "regulatory_records": [
        r"regulator",
        r"license",
        r"permit",
        r"compliance",
        r"regulatory",
    ],
}


def categorize_reason(reason: str) -> str:
    """Classify reason text into a category."""
    reason_lower = reason.lower()
    for category, patterns in REASON_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, reason_lower):
                return category
    return "other"


def categorize_sought(sought: str) -> str:
    """Classify sought text into a category."""
    sought_lower = sought.lower()
    for category, patterns in SOUGHT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, sought_lower):
                return category
    return "other"


def normalize_jurisdiction(jur: str) -> str:
    """Normalize jurisdiction code (GB -> UK, etc.)."""
    normalizations = {
        "GB": "UK",
        "GL": "GLOBAL",  # GL sometimes used for GLOBAL
    }
    return normalizations.get(jur.upper(), jur.upper())


def is_permanent(reason: str, reason_cat: str) -> bool:
    """Determine if this dead end is permanent or temporary."""
    if reason_cat == "pending_action":
        return False
    if reason_cat == "technical_failure":
        return False
    if "ongoing" in reason.lower() or "current stage" in reason.lower():
        return False
    # Most access_restricted and no_records_found are permanent structural issues
    return reason_cat in ["access_restricted", "data_not_collected"]


def generate_workaround(dead_end: dict) -> str:
    """Generate a workaround suggestion based on the dead end."""
    sought = dead_end.get("sought", "").lower()
    reason = dead_end.get("reason", "").lower()
    jurisdiction = dead_end.get("jurisdiction", "")

    if "ownership" in sought:
        return "Check if entity operates in jurisdictions with stricter disclosure (UK, EU)"
    if "financial" in sought or "transaction" in sought:
        return "Look for related party disclosures in associated entities' filings"
    if "connection" in sought or "relationship" in sought:
        return "Use network analysis on known entities to infer relationships"
    if "media" in reason or "limited coverage" in reason:
        return "Try native language media sources or specialized industry publications"
    if "private" in reason or "not disclosed" in reason:
        return "Check historical filings before privacy changes; look for regulatory submissions"
    return ""


def integrate_dead_ends():
    """Main integration function."""

    # Load mined dead_ends
    mined_file = MINED_DIR / "mined_dead_ends.json"
    print(f"Loading {mined_file}...")
    with open(mined_file) as f:
        mined_data = json.load(f)

    dead_ends = mined_data.get("dead_ends", [])
    print(f"  Found {len(dead_ends)} dead_end patterns")

    # Load jurisdictions.json
    jur_file = MATRIX_DIR / "jurisdictions.json"
    print(f"Loading {jur_file}...")
    with open(jur_file) as f:
        jur_data = json.load(f)

    jurisdictions = jur_data.get("jurisdictions", {})
    print(f"  Found {len(jurisdictions)} jurisdictions")

    # Group dead_ends by jurisdiction
    grouped = defaultdict(list)
    for de in dead_ends:
        jur = normalize_jurisdiction(de.get("jurisdiction", "UNKNOWN"))

        # Classify
        sought = de.get("sought", "")
        reason = de.get("reason", "")
        sought_cat = categorize_sought(sought)
        reason_cat = categorize_reason(reason)

        structured_de = {
            "sought": sought,
            "sought_category": sought_cat,
            "reason": reason,
            "reason_category": reason_cat,
            "attempted_sources": de.get("attempted_sources", []),
            "permanent": is_permanent(reason, reason_cat),
        }

        # Add workaround if we can generate one
        workaround = generate_workaround(de)
        if workaround:
            structured_de["workaround"] = workaround

        grouped[jur].append(structured_de)

    print(f"\nGrouped into {len(grouped)} jurisdictions")

    # Stats
    stats = {
        "jurisdictions_updated": 0,
        "dead_ends_added": 0,
        "new_jurisdictions": 0,
        "reason_categories": defaultdict(int),
        "sought_categories": defaultdict(int),
    }

    # Merge into jurisdictions
    for jur, des in grouped.items():
        if jur not in jurisdictions:
            # Create new jurisdiction entry
            jurisdictions[jur] = {
                "name": jur,
                "legal_notes": "",
                "entity_types": [],
                "id_formats": [],
                "data_availability": {"accessible": [], "restricted": [], "unavailable": []},
                "source_domains": [],
                "dead_ends": [],
            }
            stats["new_jurisdictions"] += 1

        # Merge dead_ends (avoid duplicates)
        existing = jurisdictions[jur].get("dead_ends", [])
        # Handle case where existing entries might be strings (legacy format)
        # Convert any string entries to proper dict format
        existing_sought = set()
        new_existing = []
        for d in existing:
            if isinstance(d, dict):
                existing_sought.add(d.get("sought", ""))
                new_existing.append(d)
            elif isinstance(d, str):
                # Convert legacy string to dict
                existing_sought.add(d)
                new_existing.append({
                    "sought": d,
                    "sought_category": categorize_sought(d),
                    "reason": "Legacy entry - reason not recorded",
                    "reason_category": "other",
                    "attempted_sources": [],
                    "permanent": False,
                })
        existing = new_existing

        for de in des:
            if de["sought"] not in existing_sought:
                existing.append(de)
                stats["dead_ends_added"] += 1
                stats["reason_categories"][de["reason_category"]] += 1
                stats["sought_categories"][de["sought_category"]] += 1

        jurisdictions[jur]["dead_ends"] = existing
        if des:
            stats["jurisdictions_updated"] += 1

    # Update metadata
    jur_data["meta"]["dead_ends_integrated"] = True
    jur_data["meta"]["dead_ends_count"] = stats["dead_ends_added"]
    jur_data["meta"]["updated_at"] = datetime.now().isoformat()
    jur_data["jurisdictions"] = jurisdictions

    # Write back
    print(f"\nWriting updated jurisdictions.json...")
    with open(jur_file, "w") as f:
        json.dump(jur_data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== INTEGRATION STATS ===")
    print(f"Dead ends added: {stats['dead_ends_added']}")
    print(f"Jurisdictions updated: {stats['jurisdictions_updated']}")
    print(f"New jurisdictions created: {stats['new_jurisdictions']}")

    print(f"\nReason categories:")
    for cat, count in sorted(stats["reason_categories"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"\nSought categories:")
    for cat, count in sorted(stats["sought_categories"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    integrate_dead_ends()
