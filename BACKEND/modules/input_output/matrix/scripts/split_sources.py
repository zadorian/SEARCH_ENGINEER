#!/usr/bin/env python3
"""
Split sources_OLD.json into canonical files.

sources_OLD.json (85MB, 11,705 sources) →
  - sources.json (core identity by domain)
  - templates.json (search recipes by domain)
  - intel.json (research wisdom by domain)
  - methodologies.json (performance stats by domain)
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

MATRIX_DIR = Path(__file__).parent.parent
LEGACY_DIR = MATRIX_DIR / "_archive" / "legacy"

# Field categorization
SOURCES_FIELDS = {
    "id", "name", "domain", "jurisdiction", "url",
    "section", "type", "access", "inputs", "outputs", "flows"
}

TEMPLATES_FIELDS = {
    "search_template", "search_params", "search_input_codes",
    "search_input_type", "search_placeholder", "searchable",
    "lookup_template", "lookup_params", "lookup_input_codes", "lookup_input_type",
    "output_schema", "input_schema", "seekleech_templates",
    "name_search_template", "name_search_input_codes", "name_search_params"
}

INTEL_FIELDS = {
    "notes", "wiki_context", "wiki_links", "thematic_tags",
    "related_entity_types", "arbitrage_opportunities",
    "exposes_related_entities", "classification"
}

METHODOLOGY_FIELDS = {
    "methodology", "reliability", "scrape_method", "http_latency",
    "capabilities", "language", "requires_translation", "enhanced_at"
}

# Skip these derived/redundant fields
SKIP_FIELDS = {
    "_sourceJurisdiction",  # Duplicate of jurisdiction
    "metadata",             # Usually empty or redundant
    "input_metadata",       # Low usage, embed in templates if needed
    "output_metadata",      # Low usage
}


def normalize_domain(source: dict) -> str:
    """Get normalized domain as ID."""
    domain = source.get("domain", "")
    if not domain:
        # Fallback to extracting from URL
        url = source.get("url", "")
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
    return domain.lower().strip()


def extract_fields(source: dict, fields: set) -> dict:
    """Extract only specified fields that have values."""
    result = {}
    for field in fields:
        if field in source:
            value = source[field]
            # Skip empty values
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and len(value) == 0:
                continue
            result[field] = value
    return result


def split_sources():
    """Main split function."""

    # Load sources_OLD.json
    old_file = LEGACY_DIR / "sources_OLD.json"
    if not old_file.exists():
        print(f"ERROR: {old_file} not found")
        return

    print(f"Loading {old_file}...")
    with open(old_file, "r") as f:
        data = json.load(f)

    sources_data = data.get("sources", {})

    # Output dictionaries keyed by domain
    sources_out = {}
    templates_out = {}
    intel_out = {}
    methodologies_out = {}

    # Stats
    stats = {
        "total_sources": 0,
        "sources_with_templates": 0,
        "sources_with_intel": 0,
        "sources_with_methodology": 0,
        "duplicate_domains": 0,
    }

    # Process all sources
    for jur_code, jur_sources in sources_data.items():
        if not isinstance(jur_sources, list):
            continue

        for source in jur_sources:
            if not isinstance(source, dict):
                continue

            stats["total_sources"] += 1
            domain = normalize_domain(source)

            if not domain:
                continue

            # Track duplicates (same domain in multiple jurisdictions)
            if domain in sources_out:
                stats["duplicate_domains"] += 1
                # Merge or skip? For now, prefer first occurrence
                continue

            # Extract into canonical files
            core = extract_fields(source, SOURCES_FIELDS)
            if core:
                core["id"] = domain  # Use domain as ID
                sources_out[domain] = core

            templates = extract_fields(source, TEMPLATES_FIELDS)
            if templates:
                templates["id"] = domain
                templates_out[domain] = templates
                stats["sources_with_templates"] += 1

            intel = extract_fields(source, INTEL_FIELDS)
            if intel:
                intel["id"] = domain
                intel_out[domain] = intel
                stats["sources_with_intel"] += 1

            methodology = extract_fields(source, METHODOLOGY_FIELDS)
            if methodology:
                methodology["id"] = domain
                methodologies_out[domain] = methodology
                stats["sources_with_methodology"] += 1

    # Write output files
    timestamp = datetime.now().isoformat()

    def write_canonical(filename: str, data: dict, description: str):
        output = {
            "meta": {
                "generated_at": timestamp,
                "description": description,
                "total_entries": len(data),
                "source_file": "sources_OLD.json"
            },
            "entries": data
        }
        outpath = MATRIX_DIR / filename
        with open(outpath, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"  Written: {filename} ({len(data)} entries)")

    print("\nWriting canonical files...")

    # Note: sources.json already exists with different structure
    # We'll write to sources_core.json for review, then decide on merge
    write_canonical(
        "sources_core.json",
        sources_out,
        "Core source identity - keyed by domain"
    )

    write_canonical(
        "templates.json",
        templates_out,
        "Search recipes - how to search and extract from each source"
    )

    write_canonical(
        "intel.json",
        intel_out,
        "Research wisdom - notes, tips, wiki context by source"
    )

    write_canonical(
        "methodologies.json",
        methodologies_out,
        "Performance stats - reliability, latency, capabilities by source"
    )

    print(f"\nStats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    split_sources()
