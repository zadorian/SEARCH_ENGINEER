#!/usr/bin/env python3
"""
Source Migration Script for I/O Matrix

Converts source files from string-based inputs/outputs to numeric codes from codes.json.
Splits outputs into entities, relationships, and attributes.

Usage:
    python migrate_sources.py                    # Dry run, show changes
    python migrate_sources.py --execute          # Apply changes
    python migrate_sources.py --source news.json # Migrate single file
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import argparse

# Paths
MATRIX_DIR = Path(__file__).parent
CODES_PATH = MATRIX_DIR / "codes.json"
RELATIONSHIPS_PATH = MATRIX_DIR / "relationship.json"
SOURCES_DIR = MATRIX_DIR / "sources"

# Category mapping from old names to codes
CATEGORY_MAP = {
    "corporate_registries": "cr",
    "corporate_registry": "cr",
    "regulators": "reg",
    "regulator": "reg",
    "litigation": "lit",
    "sanctions": "sanc",
    "news": "news",
    "social_media": "social",
    "assets": "at",
    "asset_tracing": "at",
    "government": "gov",
    "finance": "finance",
    "legal": "legal",
    "leaks": "leak",
    "osint": "osint",
    "tracking": "osint",
    "geospatial": "geo",
    "education": "edu",
    "health": "hea",
    "ecommerce": "ecom",
    "lifestyle": "life",
    "media": "media",
    "multimedia": "media",
    "tech": "tech",
    "science": "sci",
    "reference": "ref",
    "libraries": "lib",
    "library": "lib",
    "grey_literature": "grey",
    "creative": "crea",
    "recruitment": "rec",
    "search_engine": "search",
    "mapping_tools": "map",
    "weather": "wea",
    "misc": "misc",
    "miscellaneous": "misc",
    "uncategorized": "misc",
}

# Files to merge
FILE_MERGES = {
    "multimedia.json": "media.json",
    "asset_tracing.json": "assets.json",
    "library.json": "libraries.json",
    "miscellaneous.json": "misc.json",
    "uncategorized.json": "misc.json",
    "tracking.json": "osint.json",
}


class SourceMigrator:
    """Migrates source files from string-based to code-based format."""

    def __init__(self):
        self.codes = self._load_codes()
        self.relationships = self._load_relationships()
        self.name_to_code = self._build_name_to_code_map()
        self.output_to_relationship = self._build_output_to_relationship_map()
        self.stats = {
            "sources_processed": 0,
            "inputs_converted": 0,
            "outputs_converted": 0,
            "unmapped_inputs": set(),
            "unmapped_outputs": set(),
        }

    def _load_codes(self) -> Dict:
        """Load codes.json (codes are nested under 'codes' key)."""
        with open(CODES_PATH) as f:
            data = json.load(f)
            return data.get("codes", data)  # Handle nested structure

    def _load_relationships(self) -> Dict:
        """Load relationship.json."""
        with open(RELATIONSHIPS_PATH) as f:
            return json.load(f)

    def _build_name_to_code_map(self) -> Dict[str, int]:
        """Build mapping from field name to code number."""
        mapping = {}
        for code_str, info in self.codes.items():
            if code_str == "meta":
                continue
            try:
                code = int(code_str)
                name = info.get("name", "")
                if name:
                    # Map exact name
                    mapping[name] = code
                    # Map common variations
                    mapping[name.lower()] = code
                    mapping[name.replace("_", " ")] = code
            except ValueError:
                continue

        # Add common aliases
        self._add_common_aliases(mapping)
        return mapping

    def _add_common_aliases(self, mapping: Dict[str, int]):
        """Add common string aliases that map to codes."""
        aliases = {
            # Input aliases
            "company_name": 13,
            "company name": 13,
            "company": 13,
            "organization_name": 13,
            "organization name": 13,
            "establishment_name": 13,
            "ministry_name": 13,
            "government_agency_name": 13,

            "person_name": 7,
            "person name": 7,
            "person": 7,
            "individual": 7,
            "name": 7,

            "email": 1,
            "email_address": 1,
            "email address": 1,

            "phone": 2,
            "phone_number": 2,
            "phone number": 2,
            "telephone": 2,

            "address": 11,
            "postal_address": 11,
            "physical_address": 11,

            "company_reg_id": 14,
            "company_registration_number": 14,
            "registration_number": 14,
            "reg_number": 14,
            "company_number": 14,
            "crn": 14,

            "domain": 6,
            "domain_url": 6,
            "website": 6,

            "ip_address": 8,
            "ip": 8,

            "username": 3,
            "handle": 3,

            "url": 5,

            "vat_id": 15,
            "vat_number": 15,
            "tax_id": 15,
            "tax_identification": 15,

            "lei": 16,
            "legal_entity_identifier": 16,

            # Output aliases - Entity producing
            "directors": 59,
            "company_officers": 59,
            "officers": 59,
            "director_positions": 59,
            "director_appointments": 59,
            "board_members": 59,
            "management_team": 59,
            "executives": 59,
            "key_personnel": 59,

            "beneficial_owners": 67,
            "beneficial_owner": 67,
            "ubos": 67,
            "controlling_persons": 67,

            "shareholders": 72,
            "company_shareholders": 72,
            "shareholdings": 72,
            "company_shareholdings": 72,
            "shareholding_structure": 72,
            "shareholder_history": 72,

            "subsidiaries": 73,
            "subsidiary_companies": 73,
            "subsidiary_information": 73,
            "controlled_companies": 73,
            "group_companies": 73,

            "affiliated_companies": 13,
            "affiliated_entities": 13,
            "corporate_affiliations": 13,

            "registered_address": 11,
            "legal_address": 11,
            "business_address": 11,
            "head_office_address": 11,
            "registration_address": 11,

            "contact_information": 1,  # Usually produces email

            # Attribute aliases
            "incorporation_date": 50,
            "establishment_date": 50,
            "registration_date": 50,
            "formation_date": 50,

            "company_status": 51,
            "activity_status": 51,
            "business_status": 51,
            "trading_status": 51,
            "liquidation_status": 51,

            "company_type": 52,
            "legal_form": 52,
            "entity_type": 52,

            "share_capital": 53,
            "authorized_capital": 53,
            "paid_up_capital": 53,

            "sic_code": 54,
            "nace_code": 54,
            "industry_code": 54,
            "business_classification": 54,

            # Document/metadata outputs (no node creation)
            "annual_accounts": 80,
            "financial_statements": 80,
            "annual_filings": 80,
            "annual_reports": 80,

            "court_cases": 81,
            "court_decisions": 81,
            "court_judgments": 81,
            "court_proceedings": 81,
            "litigation_history": 81,
            "litigation_records": 81,
            "legal_proceedings": 81,

            "bankruptcy_filings": 82,
            "insolvency_records": 82,
            "insolvency_proceedings": 82,

            "charges": 83,
            "mortgages": 83,
            "security_interests": 83,

            "gazette_notices": 84,
            "official_announcements": 84,

            "adverse_media": 85,
            "news_articles": 85,

            # Sanctions
            "sanctions_match": 101,
            "sanctions_screening": 101,
            "pep_status": 102,
            "politically_exposed": 102,
        }
        mapping.update(aliases)

    def _build_output_to_relationship_map(self) -> Dict[str, str]:
        """Build mapping from output string to relationship name."""
        return {
            # Officer relationships
            "directors": "officer_of",
            "company_officers": "officer_of",
            "officers": "officer_of",
            "director_positions": "officer_of",
            "director_appointments": "officer_of",
            "board_members": "officer_of",
            "directorships": "officer_of",
            "directorship_history": "officer_of",
            "management_team": "officer_of",
            "executives": "officer_of",

            # Beneficial owner relationships
            "beneficial_owners": "beneficial_owner_of",
            "ubos": "beneficial_owner_of",
            "controlling_persons": "beneficial_owner_of",

            # Shareholder relationships
            "shareholders": "shareholder_of",
            "company_shareholders": "shareholder_of",
            "shareholdings": "shareholder_of",
            "company_shareholdings": "shareholder_of",
            "shareholding_structure": "shareholder_of",
            "shareholder_history": "shareholder_of",
            "ownership_structure": "shareholder_of",
            "ownership_percentages": "shareholder_of",
            "corporate_ownership": "shareholder_of",

            # Subsidiary relationships
            "subsidiaries": "subsidiary_of",
            "subsidiary_companies": "subsidiary_of",
            "subsidiary_information": "subsidiary_of",
            "subsidiary_presence": "subsidiary_of",
            "controlled_companies": "subsidiary_of",
            "group_companies": "subsidiary_of",
            "corporate_structure": "subsidiary_of",

            # Address relationships
            "registered_address": "has_address",
            "legal_address": "has_address",
            "business_address": "has_address",
            "head_office_address": "has_address",
            "registration_address": "has_address",
            "property_ownership": "owner_of",
            "property_owners": "owner_of",

            # Employment/affiliated relationships
            "employment_history": "employed_by",
            "career_history": "employed_by",
            "professional_background": "employed_by",
            "position_history": "employed_by",

            "affiliated_companies": "affiliated_with",
            "affiliated_entities": "affiliated_with",
            "corporate_affiliations": "affiliated_with",
            "business_relationships": "affiliated_with",
            "corporate_relationships": "affiliated_with",

            # Family
            "family_connections": "related_to",
            "family_members": "related_to",
            "family_relationships": "related_to",

            # Litigation
            "court_cases": "party_to",
            "litigation_history": "party_to",
            "litigation_records": "party_to",
            "legal_proceedings": "party_to",
        }

    def _get_relationship_code(self, rel_name: str) -> Optional[int]:
        """Get the reified code for a relationship name."""
        rel_info = self.relationships.get("relationships", {}).get(rel_name, {})
        return rel_info.get("reified_code")

    def convert_input(self, input_str: str) -> Optional[int]:
        """Convert input string to code."""
        code = self.name_to_code.get(input_str.lower())
        if code:
            self.stats["inputs_converted"] += 1
        else:
            self.stats["unmapped_inputs"].add(input_str)
        return code

    def convert_output(self, output_str: str) -> Tuple[Optional[int], Optional[int], str]:
        """
        Convert output string to (entity_code, relationship_code, output_type).

        Returns:
            (entity_code, relationship_code, output_type)
            output_type is one of: 'entity', 'relationship', 'attribute', 'document'
        """
        output_lower = output_str.lower()
        entity_code = self.name_to_code.get(output_lower)

        # Check if this output produces a relationship
        rel_name = self.output_to_relationship.get(output_lower)
        rel_code = self._get_relationship_code(rel_name) if rel_name else None

        if entity_code:
            self.stats["outputs_converted"] += 1
            # Determine output type from codes.json
            code_info = self.codes.get(str(entity_code), {})
            output_type = code_info.get("type", "unknown")
            if output_type == "nexus":
                output_type = "relationship"
            elif output_type == "entity":
                output_type = "entity"
            elif output_type == "attribute":
                output_type = "attribute"
            else:
                output_type = "attribute"  # Default to attribute

            return entity_code, rel_code, output_type
        else:
            self.stats["unmapped_outputs"].add(output_str)
            return None, rel_code, "unknown"

    def migrate_source(self, source: Dict) -> Dict:
        """Migrate a single source entry."""
        self.stats["sources_processed"] += 1

        migrated = {
            "id": source.get("id", ""),
            "name": source.get("name", ""),
        }

        # Handle jurisdiction
        jurisdictions = source.get("jurisdictions", [])
        primary_jurisdiction = source.get("jurisdiction_primary", "")
        if primary_jurisdiction:
            migrated["jurisdiction"] = primary_jurisdiction
        elif jurisdictions:
            migrated["jurisdiction"] = jurisdictions[0] if len(jurisdictions) == 1 else "GLOBAL"

        # Handle category
        old_category = source.get("category", "")
        migrated["category"] = CATEGORY_MAP.get(old_category, old_category)

        # URL
        if source.get("url"):
            migrated["url"] = source["url"]

        # Module hierarchy (placeholder - would need more info)
        # For now, infer from existing handlers
        migrated["module"] = {
            "primary": "direct",
            "secondary": {
                "handler": "corporella",
                "aggregators": []
            }
        }

        # Convert inputs
        old_inputs = source.get("inputs", [])
        new_inputs = []
        for inp in old_inputs:
            code = self.convert_input(inp)
            if code and code not in new_inputs:
                new_inputs.append(code)
        migrated["inputs"] = sorted(new_inputs)

        # Convert outputs
        old_outputs = source.get("outputs", [])
        entities = []
        relationships = []
        attributes = []

        for out in old_outputs:
            entity_code, rel_code, out_type = self.convert_output(out)

            if entity_code:
                if out_type == "entity":
                    if entity_code not in entities:
                        entities.append(entity_code)
                elif out_type == "attribute":
                    if entity_code not in attributes:
                        attributes.append(entity_code)

            if rel_code and rel_code not in relationships:
                relationships.append(rel_code)

        migrated["outputs"] = {
            "entities": sorted(entities),
            "relationships": sorted(relationships),
        }
        if attributes:
            migrated["outputs"]["attributes"] = sorted(attributes)

        # Copy other fields
        if source.get("friction"):
            migrated["friction"] = source["friction"]
        if source.get("has_api") is not None:
            migrated["has_api"] = source["has_api"]

        # Preserve capabilities in legacy format for now
        if source.get("capabilities"):
            migrated["_legacy_capabilities"] = source["capabilities"]

        return migrated

    def migrate_file(self, filepath: Path) -> Tuple[Dict, List[Dict]]:
        """Migrate an entire source file."""
        with open(filepath) as f:
            data = json.load(f)

        sources = data.get("sources", [])
        migrated_sources = [self.migrate_source(s) for s in sources]

        # Create new meta
        old_meta = data.get("meta", {})
        old_category = old_meta.get("category", filepath.stem)

        new_meta = {
            "category": CATEGORY_MAP.get(old_category, old_category),
            "count": len(migrated_sources),
            "migrated_at": datetime.utcnow().isoformat(),
            "version": "2.0",
            "format": "code-based",
        }

        return new_meta, migrated_sources

    def print_stats(self):
        """Print migration statistics."""
        print("\n" + "="*60)
        print("MIGRATION STATISTICS")
        print("="*60)
        print(f"Sources processed: {self.stats['sources_processed']}")
        print(f"Inputs converted: {self.stats['inputs_converted']}")
        print(f"Outputs converted: {self.stats['outputs_converted']}")
        print(f"Unmapped inputs: {len(self.stats['unmapped_inputs'])}")
        print(f"Unmapped outputs: {len(self.stats['unmapped_outputs'])}")

        if self.stats["unmapped_inputs"]:
            print("\nUnmapped inputs (sample):")
            for inp in sorted(self.stats["unmapped_inputs"])[:20]:
                print(f"  - {inp}")

        if self.stats["unmapped_outputs"]:
            print("\nUnmapped outputs (sample):")
            for out in sorted(self.stats["unmapped_outputs"])[:20]:
                print(f"  - {out}")


def main():
    parser = argparse.ArgumentParser(description="Migrate source files to code-based format")
    parser.add_argument("--execute", action="store_true", help="Apply changes (default is dry run)")
    parser.add_argument("--source", type=str, help="Migrate single source file")
    args = parser.parse_args()

    migrator = SourceMigrator()

    if args.source:
        # Migrate single file
        filepath = SOURCES_DIR / args.source
        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)

        new_meta, migrated_sources = migrator.migrate_file(filepath)

        if args.execute:
            output_path = filepath.with_suffix(".v2.json")
            with open(output_path, "w") as f:
                json.dump({"meta": new_meta, "sources": migrated_sources}, f, indent=2)
            print(f"Migrated to: {output_path}")
        else:
            print(json.dumps({"meta": new_meta, "sources": migrated_sources[:3]}, indent=2))
            print(f"\n... and {len(migrated_sources) - 3} more sources")
    else:
        # Migrate all files
        source_files = sorted(SOURCES_DIR.glob("*.json"))

        for filepath in source_files:
            if filepath.name in ["manifest.json", "source_schema.json"]:
                continue
            if filepath.name.endswith(".v2.json"):
                continue

            print(f"\nProcessing: {filepath.name}")
            try:
                new_meta, migrated_sources = migrator.migrate_file(filepath)

                if args.execute:
                    output_path = filepath.with_suffix(".v2.json")
                    with open(output_path, "w") as f:
                        json.dump({"meta": new_meta, "sources": migrated_sources}, f, indent=2)
                    print(f"  -> Migrated {len(migrated_sources)} sources")
                else:
                    print(f"  -> Would migrate {len(migrated_sources)} sources")
            except Exception as e:
                print(f"  -> Error: {e}")

    migrator.print_stats()


if __name__ == "__main__":
    main()
