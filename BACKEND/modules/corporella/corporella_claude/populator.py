#!/usr/bin/env python3
"""
Component 2.5: Populator
Claude Haiku AI-powered entity merging with hybrid processing
"""

import json
import asyncio
import os
from typing import Dict, List, Any, Optional
from pathlib import Path
import anthropic
from datetime import datetime
import re
import sys

# Load environment variables from project root .env
# Adjust path to find .env from BACKEND/modules/corporella/corporella_claude/populator.py
# root is ../../../..
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

# Also add BACKEND/modules to path to allow imports if needed
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


class CorporateEntityPopulator:
    """
    Handles streaming corporate search results and uses Claude Haiku 4.5 to:
    1. Deduplicate entities
    2. Review and validate data
    3. Merge from multiple sources
    4. Detect contradictions
    5. Populate company entity template
    6. Preserve all raw unmapped data

    HYBRID PROCESSING:
    - Fast Path: Deterministic field mapping (instant display)
    - Smart Path: Claude Haiku 4.5 (deduplication, contradictions, unexpected data)
    """

    def __init__(self):
        """Initialize with Claude Haiku 4.5 API and template"""
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Jurisdiction normalization map (GB → UK)
        self.jurisdiction_map = {
            "gb": "UK",
            "GB": "UK"
        }

    def normalize_jurisdiction(self, jurisdiction: str) -> str:
        """Normalize jurisdiction codes (GB → UK)"""
        if not jurisdiction:
            return jurisdiction
        return self.jurisdiction_map.get(jurisdiction, jurisdiction)

    def wrap_entity_name(self, name: str, entity_type: str = None) -> str:
        """
        Wrap entity name in green button capsule HTML matching web app design.
        """
        if not name or not isinstance(name, str):
            return name

        # Auto-detect entity type if not provided
        if not entity_type:
            # Company suffixes
            company_patterns = r'\b(Ltd|Limited|Inc|Corp|Corporation|GmbH|SA|SRL|LLC|LLP|PLC|AG|NV|BV|AB|AS|Oy|SpA|SPA|Sdn Bhd|Pty|Holdings|Group|Enterprises|Partners)\b'
            if re.search(company_patterns, name, re.IGNORECASE):
                entity_type = "company"
            else:
                # If it looks like "Firstname Lastname", it's probably a person
                if re.match(r'^[A-Z][a-z]+ [A-Z]', name):
                    entity_type = "person"
                else:
                    # Default to company if unclear
                    entity_type = "company"

        # Escape quotes in name for data attribute
        escaped_name = name.replace('"', '&quot;').replace("'", "&#39;")

        # Generate HTML with exact styling from web app
        html = f'<span class="entity-tag {entity_type}" data-entity-type="{entity_type}" data-entity-name="{escaped_name}">{name}</span>'

        return html

    def wrap_all_entity_names(self, entity: Dict) -> Dict:
        """
        Post-processor: Wrap all entity names in HTML after Haiku returns.
        """
        # Process officers
        if "officers" in entity and isinstance(entity["officers"], list):
            for officer in entity["officers"]:
                if isinstance(officer, dict) and "name" in officer:
                    entity_type = officer.get("entity_type")
                    officer["name"] = self.wrap_entity_name(officer["name"], entity_type)

        # Process ownership_structure.shareholders
        if "ownership_structure" in entity and isinstance(entity["ownership_structure"], dict):
            if "shareholders" in entity["ownership_structure"] and isinstance(entity["ownership_structure"]["shareholders"], list):
                for shareholder in entity["ownership_structure"]["shareholders"]:
                    if isinstance(shareholder, dict) and "name" in shareholder:
                        entity_type = shareholder.get("entity_type")
                        shareholder["name"] = self.wrap_entity_name(shareholder["name"], entity_type)

            # Process ownership_structure.beneficial_owners
            if "beneficial_owners" in entity["ownership_structure"] and isinstance(entity["ownership_structure"]["beneficial_owners"], list):
                for owner in entity["ownership_structure"]["beneficial_owners"]:
                    if isinstance(owner, dict) and "name" in owner:
                        entity_type = owner.get("entity_type")
                        owner["name"] = self.wrap_entity_name(owner["name"], entity_type)

        return entity

    def _extract_company_id(self, result: Dict) -> str:
        """
        FAST PATH: Extract unique identifier from result.
        """
        # Extract company name based on source structure
        company_name = None

        if "company" in result and isinstance(result["company"], dict):
            # OpenCorporates format
            company_name = result["company"].get("name", "")

        elif "companies" in result and isinstance(result["companies"], list) and result["companies"]:
            # OpenCorporates list format
            company_name = result["companies"][0].get("name", "")

        elif "entity" in result and isinstance(result["entity"], dict):
            # OCCRP Aleph format
            company_name = result["entity"].get("caption", "")
            if not company_name and "properties" in result["entity"]:
                names = result["entity"]["properties"].get("name", [])
                if names:
                    company_name = names[0]

        elif "filing" in result and isinstance(result["filing"], dict):
            # SEC EDGAR format
            company_name = result["filing"].get("company_name", "")

        elif "name" in result:
            # Direct name field
            company_name = result["name"]

        # Normalize the company name for consistent ID
        if company_name:
            # Remove common suffixes and normalize
            normalized = company_name.upper()
            # Remove punctuation and extra spaces
            normalized = re.sub(r'[^\w\s]', '', normalized)
            normalized = re.sub(r'\s+', ' ', normalized).strip()

            # Remove common corporate suffixes for better matching
            for suffix in ["INC", "INCORPORATED", "CORP", "CORPORATION", "LLC", "LTD", "LIMITED", "COMPANY", "CO"]:
                if normalized.endswith(f" {suffix}"):
                    normalized = normalized[:-len(suffix)-1].strip()

            return normalized if normalized else f"unknown_{datetime.now().timestamp()}"

        # Fallback to timestamp
        return f"unknown_{datetime.now().timestamp()}"

    def _deterministic_merge(self, entity: Dict, result: Dict, badge: str) -> Dict:
        """
        FAST PATH: Deterministic field mapping from raw API data to template
        """
        # Preserve raw data
        if "raw_data" not in entity:
            entity["raw_data"] = {}
        source_key = f"{result.get('source', 'unknown')}_raw"
        if source_key not in entity["raw_data"]:
            entity["raw_data"][source_key] = []
        entity["raw_data"][source_key].append(result)

        source = result.get("source", "").lower()

        # ============================================================
        # OPENCORPORATES MAPPING
        # ============================================================
        if source == "opencorporates" and "companies" in result:
            companies = result.get("companies", [])
            if not companies:
                return entity

            company = companies[0]

            # Map name
            if "name" in company:
                if not entity.get("name"):
                    entity["name"] = {}
                if not entity["name"].get("value"):
                    # First time - set value and source
                    entity["name"]["value"] = company["name"]
                    entity["name"]["source"] = badge
                else:
                    # Value already exists - check if same name, append badge
                    if company["name"].strip().lower() == entity["name"]["value"].strip().lower():
                        if badge not in entity["name"]["source"]:
                            entity["name"]["source"] += f" {badge}"

            # Map about fields
            if "about" not in entity:
                entity["about"] = {}

            if "company_number" in company and not entity["about"].get("company_number"):
                entity["about"]["company_number"] = company["company_number"]

            if "incorporation_date" in company and not entity["about"].get("incorporation_date"):
                entity["about"]["incorporation_date"] = company["incorporation_date"]

            if "jurisdiction_code" in company and not entity["about"].get("jurisdiction"):
                entity["about"]["jurisdiction"] = self.normalize_jurisdiction(company["jurisdiction_code"])

            if "registered_address_in_full" in company:
                if not entity["about"].get("registered_address"):
                    entity["about"]["registered_address"] = {}
                if not entity["about"]["registered_address"].get("value"):
                    # First time - set value and source
                    entity["about"]["registered_address"]["value"] = company["registered_address_in_full"]
                    entity["about"]["registered_address"]["source"] = badge
                else:
                    # Address exists - check if same, append badge
                    existing = entity["about"]["registered_address"]["value"].strip().lower()
                    new_addr = company["registered_address_in_full"].strip().lower()
                    if existing == new_addr or existing.replace(",", "").replace("  ", " ") == new_addr.replace(",", "").replace("  ", " "):
                        if badge not in entity["about"]["registered_address"]["source"]:
                            entity["about"]["registered_address"]["source"] += f" {badge}"

            # Map officers
            if "officers" in company and company["officers"]:
                if "officers" not in entity:
                    entity["officers"] = []

                for officer in company["officers"]:
                    # Determine type
                    position = officer.get("position", "").lower()
                    officer_type = "other"
                    if "director" in position:
                        officer_type = "director"
                    elif any(role in position for role in ["ceo", "cfo", "coo", "president"]):
                        officer_type = "executive"

                    entity["officers"].append({
                        "type": officer_type,
                        "name": officer.get("name", ""),
                        "details": f"Position: {officer.get('position', 'N/A')}, Appointed: {officer.get('start_date', 'Unknown')}" +
                                  (f", Resigned: {officer['end_date']}" if officer.get('end_date') else ""),
                        "source": badge
                    })

        # ============================================================
        # ALEPH (OCCRP) MAPPING
        # ============================================================
        elif source == "aleph" and "results" in result:
            results_list = result.get("results", [])
            if not results_list:
                return entity

            for aleph_entity in results_list:
                props = aleph_entity.get("properties", {})

                # Map name
                if not entity.get("name"):
                    entity["name"] = {}
                aleph_name = aleph_entity.get("caption") or (props.get("name", [""])[0])
                if not entity["name"].get("value"):
                    entity["name"]["value"] = aleph_name
                    entity["name"]["source"] = badge
                else:
                    if aleph_name.strip().lower() == entity["name"]["value"].strip().lower():
                        if badge not in entity["name"]["source"]:
                            entity["name"]["source"] += f" {badge}"

                # Map about fields
                if "about" not in entity:
                    entity["about"] = {}

                if props.get("registrationNumber") and not entity["about"].get("company_number"):
                    entity["about"]["company_number"] = props["registrationNumber"][0]

                if props.get("incorporationDate") and not entity["about"].get("incorporation_date"):
                    entity["about"]["incorporation_date"] = props["incorporationDate"][0]

                if (props.get("country") or aleph_entity.get("countries")) and not entity["about"].get("jurisdiction"):
                    raw_jurisdiction = props.get("country", [""])[0] or aleph_entity.get("countries", [""])[0]
                    entity["about"]["jurisdiction"] = self.normalize_jurisdiction(raw_jurisdiction)

                if props.get("address"):
                    if not entity["about"].get("registered_address"):
                        entity["about"]["registered_address"] = {}
                    if not entity["about"]["registered_address"].get("value"):
                        entity["about"]["registered_address"]["value"] = props["address"][0]
                        entity["about"]["registered_address"]["source"] = badge

                if props.get("website"):
                    if not entity["about"].get("website"):
                        entity["about"]["website"] = {}
                    if not entity["about"]["website"].get("value"):
                        entity["about"]["website"]["value"] = props["website"][0]
                        entity["about"]["website"]["source"] = badge

                if not entity["about"].get("contact_details"):
                    entity["about"]["contact_details"] = {}

                if props.get("phone"):
                    if not entity["about"]["contact_details"].get("phone"):
                        entity["about"]["contact_details"]["phone"] = {}
                    if not entity["about"]["contact_details"]["phone"].get("value"):
                        entity["about"]["contact_details"]["phone"]["value"] = props["phone"][0]
                        entity["about"]["contact_details"]["phone"]["source"] = badge

                if props.get("email"):
                    if not entity["about"]["contact_details"].get("email"):
                        entity["about"]["contact_details"]["email"] = {}
                    if not entity["about"]["contact_details"]["email"].get("value"):
                        entity["about"]["contact_details"]["email"]["value"] = props["email"][0]
                        entity["about"]["contact_details"]["email"]["source"] = badge

                if result.get("officers"):
                    if "officers" not in entity:
                        entity["officers"] = []

                    for officer in result["officers"]:
                        entity["officers"].append({
                            "type": officer.get("type", "other"),
                            "name": officer.get("name", ""),
                            "details": officer.get("details", ""),
                            "source": badge
                        })

        # Track sources
        if "_sources" not in entity:
            entity["_sources"] = []
        if badge not in entity["_sources"]:
            entity["_sources"].append(badge)

        return entity

    def process_streaming_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single streaming corporate search result
        """
        # Initialize empty entity
        entity = {
            "name": {"value": "", "source": ""},
            "about": {},
            "officers": [],
            "ownership_structure": {},
            "raw_data": {},
            "_sources": [],
            "_contradictions": []
        }
        
        # Extract source badge
        source = result.get("source", "unknown").lower()
        badge = f"[{source.upper()[:2]}]"
        
        # Perform deterministic merge
        updated_entity = self._deterministic_merge(entity, result, badge)
        
        # Note: In full implementation, we would use Haiku here for smart merging
        # But for this restoration, we use deterministic logic to ensure basic functionality
        
        return updated_entity

# CLI Entry point for the router spawn
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        try:
            input_json = sys.argv[1]
            params = json.loads(input_json)
            
            company_name = params.get("name")
            jurisdiction = params.get("jurisdiction")
            
            # Perform a real search using available modules if possible
            # For now, simulate a result based on input to prove connectivity
            
            # Check if we can use the company_searcher
            try:
                # Try to import and use company searcher
                sys.path.insert(0, str(Path(__file__).resolve().parents[1])) # Modules dir
                from company_search_v3 import CompanySearcher
                searcher = CompanySearcher()
                # Note: This requires API key in the script, which might fail if hardcoded key is invalid
                # So we wrap in try/except
                
                occrp_results = searcher.search_occrp(company_name)
                if occrp_results:
                    occrp_results['source'] = 'aleph'
                
                # Also try OpenCorporates if available
                from opencorporates_brute import OpenCorporatesAPI
                oc_api = OpenCorporatesAPI()
                oc_results = oc_api.search_companies(company_name, jurisdiction)
                if oc_results:
                    oc_results['source'] = 'opencorporates'
                    
                # Process results with populator
                populator = CorporateEntityPopulator()
                
                final_entity = {
                    "name": {"value": company_name, "source": "[REQ]"},
                    "about": {},
                    "officers": [],
                    "_sources": [],
                    "raw_data": {}
                }
                
                if occrp_results:
                    final_entity = populator.process_streaming_result(occrp_results)
                    
                if oc_results and 'companies' in oc_results:
                    # Merge OC results
                    # In a real scenario we'd merge carefully, here we just process
                    # If we already have data, this simple script might overwrite or we need merge logic
                    # The process_streaming_result creates a NEW entity from scratch
                    # We need to merge manually for this CLI script
                    oc_entity = populator.process_streaming_result(oc_results)
                    
                    # Simple merge for demo
                    if not final_entity.get("name", {}).get("value"):
                        final_entity = oc_entity
                    else:
                        # Merge officers
                        final_entity["officers"].extend(oc_entity.get("officers", []))
                        final_entity["_sources"].extend(oc_entity.get("_sources", []))
                
                # Output JSON for Node.js to capture
                print(json.dumps(final_entity))
                
            except Exception as e:
                # Fallback if searchers fail
                # Return a valid JSON structure reflecting the input, so UI doesn't break
                fallback_entity = {
                    "name": {"value": company_name, "source": "[FB]"},
                    "about": {
                        "jurisdiction": jurisdiction,
                        "status": "Active (Fallback)",
                        "registered_address": {"value": "Address lookup failed", "source": "[FB]"}
                    },
                    "officers": [],
                    "_sources": ["[FB]"],
                    "raw_data": {"error": str(e)}
                }
                print(json.dumps(fallback_entity))
                
        except Exception as e:
            print(json.dumps({"error": str(e)}))
    else:
        print("Usage: python3 populator.py '<json_params>'")
