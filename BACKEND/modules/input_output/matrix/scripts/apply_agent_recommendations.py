#!/usr/bin/env python3
"""
Apply all agent recommendations to jurisdictions.json.

Consolidates changes from 12 parallel agents:
- Dead ends codification (batches 1-6)
- Invalid code cleanup
- US state standardization
- Proven methods standardization
- Observation codes application
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MATRIX_DIR = Path(__file__).parent.parent

# === STANDARD CATEGORIES ===
SOUGHT_CATEGORIES = {
    "beneficial_ownership", "financial_information", "entity_connections",
    "asset_information", "litigation_records", "sanctions_adverse",
    "directors_officers", "identity_verification", "corporate_structure",
    "regulatory_records", "insolvency_records", "employment_history",
    "licensing_records", "procurement_records", "policy_documents"
}

REASON_CATEGORIES = {
    "access_restricted", "no_records_found", "pending_action",
    "data_not_collected", "language_barrier", "technical_failure",
    "disclosure_not_required", "registry_limitation", "paywall",
    "offshore_opacity", "privacy_law", "scope_limitation"
}

# === INVALID CODES TO REMOVE ===
CODES_TO_DELETE = {
    "CIVIL_SOCIETY", "COMMERCIAL", "CORPORATE_REGISTRY", "COUNTRIES",
    "ASSET_REGISTRIES", "FURTHER_PUBLIC_RECORDS", "PUBLIC_RECORD",
    "TEST_COUNTRY_1", "PALESTINE_STATE", "REGULATORY", "KA", "KI", "LA",
    "PW", "UR"
}

# === CODES TO MERGE ===
MERGE_MAP = {
    "C_TE_D_IVOIRE": "CI",
    "CONGO": "CG",
    "DEMOCRATIC_REPUBLIC_OF_THE_CONGO": "CD",
    "TRINIDAD_AND_TOBAGO": "TT",
    "ANTIGUA_AND_BARBUDA": "AG",
    "MYANMAR_FORMERLY_BURMA": "MM",
    "SAINT_LUCIA": "LC",
    "SAO_TOME_AND_PRINCIPE": "ST",
    "UNKNOWN": "UNASSIGNED",
    "Unknown": "UNASSIGNED",
    "Global": "GLOBAL",
    "EMEA": "GLOBAL",
}

# === US STATE NORMALIZATION ===
US_STATE_MERGE = {
    "USA__ALABAMA": "US_AL",
    "USA__ALASKA": "US_AK",
    "USA__ARIZONA": "US_AZ",
    "USA__ARKANSAS": "US_AR",
    "USA__NEW_JERSEY": "US_NJ",
    "USA__NEW_YORK": "US_NY",
    "USA__WASHINGTON": "US_WA",
    "USA_FLORIDA": "US_FL",
    "USA_MICHIGAN": "US_MI",
    "USA_NEVADA": "US_NV",
    "USA_NEW_YORK": "US_NY",
    "USA_TEXAS": "US_TX",
}

# === PROVEN METHODS STANDARDIZATION ===
METHOD_RENAMES = {
    "corporate_registry_search": "REGISTRY_COMPANY",
    "CORPORATE_REGISTRY_SEARCH": "REGISTRY_COMPANY",
    "court_search": "LITIGATION_COURT",
    "COURT_SEARCH": "LITIGATION_COURT",
    "media_monitoring": "MEDIA_MONITORING",
    "MEDIA_SEARCH": "MEDIA_MONITORING",
    "osint": "OSINT_GENERAL",
    "humint": "HUMINT",
    "SOCIAL_MEDIA_MONITORING": "OSINT_SOCIAL",
    "social_media_analysis": "OSINT_SOCIAL",
    "corporate_filings_analysis": "REGISTRY_FILINGS",
    "CORPORATE_FILINGS_ANALYSIS": "REGISTRY_FILINGS",
    "regulatory_search": "REGULATORY_SEARCH",
    "property_search": "ASSET_PROPERTY",
    "PROPERTY_SEARCH": "ASSET_PROPERTY",
    "LAND_REGISTRY_SEARCH": "ASSET_PROPERTY",
    "bankruptcy_search": "LITIGATION_BANKRUPTCY",
    "BANKRUPTCY_SEARCH": "LITIGATION_BANKRUPTCY",
    "sanctions_screening": "COMPLIANCE_SANCTIONS",
    "SANCTIONS_SCREENING": "COMPLIANCE_SANCTIONS",
    "pep_screening": "COMPLIANCE_PEP",
    "archive_research": "ARCHIVE_RESEARCH",
    "domain_research": "OSINT_DOMAIN",
    "WEBSITE_ANALYSIS": "OSINT_DOMAIN",
    "DATA_BREACH_ANALYSIS": "BREACH_DATA",
}


def reclassify_sought(sought: str) -> str:
    """Reclassify 'other' sought categories."""
    sought_lower = sought.lower()

    patterns = {
        "beneficial_ownership": ["ownership", "shareholder", "ubo", "stake", "equity"],
        "financial_information": ["financial", "revenue", "transaction", "payment", "banking", "invoice", "credit"],
        "entity_connections": ["connection", "relationship", "link", "affiliation", "subsidiary"],
        "asset_information": ["asset", "property", "real estate", "vehicle", "aircraft"],
        "litigation_records": ["litigation", "court", "lawsuit", "criminal", "civil", "judgment"],
        "sanctions_adverse": ["sanction", "media", "adverse", "watchlist", "coverage"],
        "directors_officers": ["director", "officer", "executive", "management", "ceo"],
        "identity_verification": ["identity", "verification", "birth", "educational", "background"],
        "corporate_structure": ["corporate structure", "company", "website", "social media"],
        "regulatory_records": ["regulatory", "license", "permit", "audit", "tax"],
        "insolvency_records": ["insolvency", "bankruptcy"],
        "employment_history": ["employment", "career", "position", "departure"],
    }

    for category, keywords in patterns.items():
        if any(kw in sought_lower for kw in keywords):
            return category
    return "other"


def reclassify_reason(reason: str) -> str:
    """Reclassify 'other' reason categories."""
    reason_lower = reason.lower()

    patterns = {
        "access_restricted": ["not (publicly )?disclosed", "restricted", "private", "protected", "confidential", "not accessible", "privacy"],
        "no_records_found": ["no (records|results|information|evidence|matches)", "not found", "unable to", "could not"],
        "pending_action": ["ongoing", "pending", "current investigation", "time limit", "scope"],
        "disclosure_not_required": ["not required", "not mandated", "not obliged"],
        "registry_limitation": ["registry", "database", "portal", "search.*not.*available"],
        "language_barrier": ["language", "translation", "arabic", "cyrillic"],
        "technical_failure": ["website.*down", "offline", "technical"],
        "paywall": ["subscription", "paid", "payment required"],
        "offshore_opacity": ["offshore", "secrecy", "nominee"],
    }

    for category, keywords in patterns.items():
        for kw in keywords:
            if re.search(kw, reason_lower):
                return category
    return "other"


def clean_dead_ends(dead_ends: list) -> list:
    """Clean and deduplicate dead_ends."""
    seen_sought = set()
    cleaned = []

    for de in dead_ends:
        # Handle legacy string entries
        if isinstance(de, str):
            # Try to parse if it looks like a dict repr
            if de.startswith("{"):
                continue  # Skip malformed legacy entries
            # Convert simple string to dict
            de = {
                "sought": de,
                "sought_category": reclassify_sought(de),
                "reason": "Legacy entry",
                "reason_category": "other",
                "attempted_sources": [],
                "permanent": False,
            }

        sought = de.get("sought", "")

        # Skip if duplicate
        if sought in seen_sought:
            continue
        seen_sought.add(sought)

        # Skip malformed entries (sought contains JSON)
        if sought.startswith("{") or "'sought'" in sought:
            continue

        # Reclassify 'other' categories
        if de.get("sought_category") == "other":
            de["sought_category"] = reclassify_sought(sought)

        if de.get("reason_category") == "other":
            reason = de.get("reason", "")
            de["reason_category"] = reclassify_reason(reason)

        cleaned.append(de)

    return cleaned


def standardize_proven_methods(methods: dict) -> dict:
    """Standardize proven_methods names."""
    standardized = {}

    for method, data in methods.items():
        new_name = METHOD_RENAMES.get(method, method)

        if new_name in standardized:
            # Merge counts
            standardized[new_name]["count"] = standardized[new_name].get("count", 0) + data.get("count", 0)
            # Merge sources
            existing_sources = set(standardized[new_name].get("sample_sources", []))
            new_sources = data.get("sample_sources", [])
            standardized[new_name]["sample_sources"] = list(existing_sources | set(new_sources))[:5]
        else:
            standardized[new_name] = data

    return standardized


def merge_jurisdiction(target: dict, source: dict) -> dict:
    """Merge source jurisdiction data into target."""
    # Merge dead_ends
    target_de = target.get("dead_ends", [])
    source_de = source.get("dead_ends", [])
    existing_sought = {de.get("sought", "") for de in target_de if isinstance(de, dict)}

    for de in source_de:
        if isinstance(de, dict) and de.get("sought") not in existing_sought:
            target_de.append(de)
    target["dead_ends"] = target_de

    # Merge proven_methods
    target_pm = target.get("proven_methods", {})
    source_pm = source.get("proven_methods", {})
    for method, data in source_pm.items():
        if method not in target_pm:
            target_pm[method] = data
    target["proven_methods"] = target_pm

    # Merge wiki_sections (prefer non-empty)
    target_ws = target.get("wiki_sections", {})
    source_ws = source.get("wiki_sections", {})
    for section, data in source_ws.items():
        if section not in target_ws or not target_ws[section].get("content"):
            if data.get("content") or data.get("links"):
                target_ws[section] = data
    target["wiki_sections"] = target_ws

    # Merge source_domains
    target_sd = set(target.get("source_domains", []))
    source_sd = set(source.get("source_domains", []))
    target["source_domains"] = list(target_sd | source_sd)

    return target


def apply_recommendations():
    """Main function to apply all agent recommendations."""

    # Load jurisdictions.json
    jur_file = MATRIX_DIR / "jurisdictions.json"
    print(f"Loading {jur_file}...")
    with open(jur_file) as f:
        data = json.load(f)

    jurisdictions = data.get("jurisdictions", {})
    original_count = len(jurisdictions)
    print(f"  Found {original_count} jurisdictions")

    stats = {
        "deleted": 0,
        "merged": 0,
        "dead_ends_cleaned": 0,
        "methods_standardized": 0,
        "us_states_normalized": 0,
    }

    # Step 1: Delete invalid codes
    print("\n1. Deleting invalid codes...")
    for code in CODES_TO_DELETE:
        if code in jurisdictions:
            del jurisdictions[code]
            stats["deleted"] += 1
            print(f"  Deleted: {code}")

    # Step 2: Merge duplicates
    print("\n2. Merging duplicates...")
    for source_code, target_code in MERGE_MAP.items():
        if source_code in jurisdictions:
            source_data = jurisdictions[source_code]

            if target_code not in jurisdictions:
                jurisdictions[target_code] = {
                    "name": target_code,
                    "legal_notes": "",
                    "entity_types": [],
                    "id_formats": [],
                    "data_availability": {"accessible": [], "restricted": [], "unavailable": []},
                    "source_domains": [],
                    "dead_ends": [],
                }

            jurisdictions[target_code] = merge_jurisdiction(
                jurisdictions[target_code],
                source_data
            )
            del jurisdictions[source_code]
            stats["merged"] += 1
            print(f"  Merged: {source_code} → {target_code}")

    # Step 3: Normalize US states
    print("\n3. Normalizing US state codes...")
    for source_code, target_code in US_STATE_MERGE.items():
        if source_code in jurisdictions:
            source_data = jurisdictions[source_code]

            if target_code not in jurisdictions:
                jurisdictions[target_code] = {
                    "name": target_code,
                    "legal_notes": "",
                    "entity_types": [],
                    "id_formats": [],
                    "data_availability": {"accessible": [], "restricted": [], "unavailable": []},
                    "source_domains": [],
                    "dead_ends": [],
                }

            jurisdictions[target_code] = merge_jurisdiction(
                jurisdictions[target_code],
                source_data
            )
            del jurisdictions[source_code]
            stats["us_states_normalized"] += 1
            print(f"  Normalized: {source_code} → {target_code}")

    # Step 4: Clean dead_ends and standardize methods for all jurisdictions
    print("\n4. Cleaning dead_ends and standardizing methods...")
    for jur_code, jur_data in jurisdictions.items():
        # Clean dead_ends
        if "dead_ends" in jur_data:
            original = len(jur_data["dead_ends"])
            jur_data["dead_ends"] = clean_dead_ends(jur_data["dead_ends"])
            cleaned = original - len(jur_data["dead_ends"])
            if cleaned > 0:
                stats["dead_ends_cleaned"] += cleaned

        # Standardize proven_methods
        if "proven_methods" in jur_data:
            original_methods = set(jur_data["proven_methods"].keys())
            jur_data["proven_methods"] = standardize_proven_methods(jur_data["proven_methods"])
            new_methods = set(jur_data["proven_methods"].keys())
            if original_methods != new_methods:
                stats["methods_standardized"] += 1

    # Update metadata
    data["meta"]["cleanup_applied"] = True
    data["meta"]["cleanup_date"] = datetime.now().isoformat()
    data["meta"]["total_jurisdictions"] = len(jurisdictions)
    data["jurisdictions"] = jurisdictions

    # Write back
    print(f"\nWriting updated jurisdictions.json...")
    with open(jur_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Print stats
    print(f"\n=== CLEANUP STATS ===")
    print(f"Original jurisdictions: {original_count}")
    print(f"Final jurisdictions: {len(jurisdictions)}")
    print(f"Deleted invalid codes: {stats['deleted']}")
    print(f"Merged duplicates: {stats['merged']}")
    print(f"US states normalized: {stats['us_states_normalized']}")
    print(f"Dead ends cleaned: {stats['dead_ends_cleaned']}")
    print(f"Methods standardized: {stats['methods_standardized']}")


if __name__ == "__main__":
    apply_recommendations()
