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

# Load environment variables from project root .env
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
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
        Matches styling from company_profile_enhanced.html lines 70-110.

        Args:
            name: The entity name to wrap
            entity_type: "person" or "company" (auto-detected if None)

        Returns:
            HTML string with entity tag styling
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
        # Green capsule (#00ff88) with white text (#ffffff)
        html = f'<span class="entity-tag {entity_type}" data-entity-type="{entity_type}" data-entity-name="{escaped_name}">{name}</span>'

        return html

    def wrap_all_entity_names(self, entity: Dict) -> Dict:
        """
        Post-processor: Wrap all entity names in HTML after Haiku returns.
        Processes officers, shareholders, and beneficial_owners.
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

        # Load company entity template
        template_path = Path(__file__).parent / "entity_template.json"
        if template_path.exists():
            with open(template_path) as f:
                self.template = json.load(f)
        else:
            # Fallback minimal template
            self.template = {
                "name": {"value": "", "source": ""},
                "about": {},
                "officers": [],
                "ownership_structure": {},
                "raw_data": {},
                "_sources": [],
                "_contradictions": []
            }

        # Source badge mappings
        self.source_badges = {
            "opencorporates": "[OC]",
            "aleph": "[AL]",
            "occrp": "[AL]",
            "edgar": "[ED]",
            "sec": "[ED]",
            "openownership": "[OO]",
            "linkedin": "[LI]",
            "companies_house": "[CH]",
            "wikileaks": "[WL]",
            "opensanctions": "[OS]",
            "panama_papers": "[PP]",
            "paradise_papers": "[PD]",
            "icij": "[IC]"
        }

        # Accumulated results per company
        self.company_data_streams = {}

    async def process_streaming_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single streaming corporate search result

        HYBRID PROCESSING:
        1. Fast Path: Extract source badge, normalize data (instant)
        2. Smart Path: Claude Haiku 4.5 merge (parallel, comprehensive)

        Args:
            result: Raw result from OpenCorporates, OCCRP, EDGAR, etc.

        Returns:
            Updated company entity with this result merged in
        """
        # FAST PATH: Extract company identifier and source
        company_id = self._extract_company_id(result)
        source = result.get("source", "unknown").lower()
        badge = self.source_badges.get(source, "[??]")

        # Initialize or get existing accumulated data
        if company_id not in self.company_data_streams:
            self.company_data_streams[company_id] = {
                "results": [],
                "merged_entity": json.loads(json.dumps(self.template))  # Deep copy
            }

        # Add this result to accumulated results
        self.company_data_streams[company_id]["results"].append(result)

        # SMART PATH: Call Haiku 4.5 to intelligently merge
        updated_entity = await self._haiku_merge_result(
            self.company_data_streams[company_id]["merged_entity"],
            result,
            self.company_data_streams[company_id]["results"]
        )

        # Update stored entity
        self.company_data_streams[company_id]["merged_entity"] = updated_entity

        return updated_entity

    def _extract_company_id(self, result: Dict) -> str:
        """
        FAST PATH: Extract unique identifier from result.
        Use normalized company name as ID to ensure all results for the same company
        are merged together regardless of source.
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

    async def _haiku_merge_result(
        self,
        current_entity: Dict,
        new_result: Dict,
        all_results: List[Dict]
    ) -> Dict:
        """
        HYBRID PATH: Deterministic mapping FIRST, then Haiku validation/improvement

        STEP 1 (FAST): Deterministic field mapping
        - Maps all known fields from API → template instantly
        - No AI cost, no latency

        STEP 2 (SMART): Haiku 4.5 validation
        - Checks for missed fields
        - Deduplicates officers
        - Detects contradictions
        - Extracts hidden data
        - Ensures nothing lost

        Result: Fast + Smart + Nothing Lost
        """

        # STEP 1: DETERMINISTIC MAPPING (instant, free)
        source = new_result.get("source", "unknown").lower()
        badge = self.source_badges.get(source, "[??]")

        # Apply deterministic mapping first
        current_entity = self._deterministic_merge(current_entity, new_result, badge)

        # Prepare Haiku 4.5 prompt
        prompt = f"""You are a corporate data validator. A deterministic system has already mapped fields from raw API data to our template. Your task is to REVIEW and IMPROVE this mapping.

CURRENT ENTITY (after deterministic mapping):
{json.dumps(current_entity, indent=2)}

NEW RESULT THAT WAS JUST MAPPED:
Source: {source} {badge}
{json.dumps(new_result, indent=2)}

ALL RESULTS SO FAR (for context):
{json.dumps(all_results, indent=2)}

YOUR TASK - VALIDATE & IMPROVE:

1. CHECK COMPLETENESS: Did the deterministic mapper miss any important fields from the raw data?
   - Look for unmapped fields in the raw result that should be in the template
   - Add them with proper source badges

2. DEDUPLICATE & CONSOLIDATE: Are there duplicate or similar values across sources?
   - SAME DATA: "Apple Inc" from [OC] and "Apple Inc" from [AL] → consolidate to one value with "[OC] [AL]"
   - SIMILAR VERSIONS: "123 Main St" vs "123 Main Street, Suite 100" → choose most complete version, append both badges
   - Keep the most detailed/complete version of the data

3. DETECT CONTRADICTIONS: Do multiple sources give DIFFERENT values that can't be versions of each other?
   - Example: jurisdiction="us_ca" [OC] vs jurisdiction="us_de" [AL] ← CONTRADICTION!
   - When you find a contradiction:
     a) Add a "_contradictions" array to the entity if it doesn't exist
     b) Add entry: {{"field": "about.jurisdiction", "values": [{{"value": "us_ca", "source": "[OC]"}}, {{"value": "us_de", "source": "[AL]"}}], "highlight": "red"}}
     c) In the main field, keep BOTH values separated by " | " with their badges: "us_ca [OC] | us_de [AL]"

4. DEDUPLICATE OFFICERS: Are there duplicate officers with slight name variations?
   - "John Smith" vs "J. Smith" → merge to one officer with multiple source badges "[OC] [AL]"
   - Keep the most complete name variant
   - If same person has different roles in different sources, consolidate details

5. VALIDATE SOURCE BADGES: Every populated field must have its source badge
   - name.source should be "[OC]" or "[AL]" or "[OC] [AL]" (multiple sources)
   - about.registered_address.source should be "[OC]" or "[AL]" etc.
   - officers[].source should be "[OC]" or "[AL]" etc.

6. EXTRACT HIDDEN DATA: Look for data in nested fields that wasn't mapped
   - ownership info, compliance flags, relationships, etc.
   - Map to ownership_structure, compliance, or notes

6a. PARSE OWNERSHIP INTO ENTITIES: CRITICAL - Parse shareholders and beneficial_owners into structured entities
   - ownership_structure.shareholders is an ARRAY of entity objects, NOT a string
   - ownership_structure.beneficial_owners is an ARRAY of entity objects, NOT a string
   - NEVER use comma-separated strings like "John Smith, Jane Doe"
   - Parse each owner into a structured object:
     {
       "name": "Tamás Szabó",
       "entity_type": "person",
       "nationality": "Hungarian",
       "residence": "GB",
       "dob": "1987-11",
       "details": "",
       "source": "[AL]"
     }
   - For companies:
     {
       "name": "Srs Enterprises Holding Ltd",
       "entity_type": "company",
       "company_number": "12853383",
       "details": "GB company",
       "source": "[AL]"
     }
   - Extract nationality, residence, DOB, company numbers from parenthetical details
   - Example input: "Tamás Szabó (Hungarian national, GB resident, DOB 1987-11)"
   - Parse to: {"name": "Tamás Szabó", "entity_type": "person", "nationality": "Hungarian", "residence": "GB", "dob": "1987-11", "source": "[AL]"}

7. NOTHING LOST: All unmapped data goes to raw_data
   - Preserve everything from the source

8. VALIDATE STRING VALUES: NEVER use objects where strings are expected
   - If a field expects a string value (like "company_number", "jurisdiction", "address"), ONLY use actual string values
   - NEVER use objects, arrays, or nested structures for string fields
   - If you don't have a valid string value, use null or omit the field entirely
   - Example: "company_number": "12345" ✓ (correct)
   - Example: "company_number": {{"value": "12345"}} ✗ (WRONG - will display as [object Object])
   - Example: "jurisdiction": "GB" ✓ (correct)
   - Example: "jurisdiction": {{"code": "GB"}} ✗ (WRONG)

9. ENTITY TYPE IDENTIFICATION: For EVERY entity (officers, shareholders, beneficial_owners):
   - Analyze if the entity is a PERSON or a COMPANY
   - Detection rules:
     * COMPANY if name contains: Ltd, Limited, Inc, Corp, Corporation, GmbH, SA, SRL, LLC, LLP, PLC, AG, NV, BV, AB, AS, Oy, SpA, SPA, Sdn Bhd, Pty, Holdings, Group, Enterprises, Partners
     * PERSON if: No company suffix AND appears to be a human name (firstname + lastname pattern)
   - Add an "entity_type" field to each entity object:
     * officers[]: each officer should have "entity_type": "person" or "entity_type": "company"
     * ownership_structure.shareholders[]: each shareholder should have "entity_type": "person" or "entity_type": "company"
     * ownership_structure.beneficial_owners[]: each beneficial owner should have "entity_type": "person" or "entity_type": "company"
   - Do NOT add HTML tags - just the entity_type field
   - The deterministic post-processor will handle HTML wrapping based on this field

10. FINAL VALIDATION - REVIEW THE ENTIRE POPULATED ENTITY:
   - Check EVERY field has proper formatting (no [object Object], no undefined, no null strings)
   - Verify ALL entities have entity_type field set (officers, shareholders, beneficial_owners)
   - Ensure ALL populated fields have source badges ("[OC]", "[AL]", "[ED]", etc.)
   - Confirm contradictions are in "_contradictions" array AND main field shows both values with " | " separator
   - Validate all dates are in proper format (YYYY-MM-DD or similar)
   - Check all arrays contain proper objects (not comma-separated strings)
   - Ensure jurisdiction codes are normalized (GB not "Great Britain", US not "United States")
   - Verify phone numbers, emails, websites are properly formatted
   - Confirm all references between entities are consistent (no broken links)
   - Make sure NO data is lost - if you can't map it properly, put it in raw_data

CRITICAL: Return the COMPLETE entity JSON with "_contradictions" array if any contradictions found. Don't explain, just return valid JSON."""

        # Define entity schema as tool input schema (matches YOUR NEW template)
        entity_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "variations": {"type": "string"},
                        "alias": {"type": "string"},
                        "source": {"type": "string"}
                    }
                },
                "node_class": {"type": "string"},
                "type": {"type": "string"},
                "about": {
                    "type": "object",
                    "properties": {
                        "company_number": {"type": "string"},
                        "incorporation_date": {"type": "string"},
                        "jurisdiction": {"type": "string"},
                        "registered_address": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "comment": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "website": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "comment": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "contact_details": {
                            "type": "object",
                            "properties": {
                                "phone": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "comment": {"type": "string"},
                                        "source": {"type": "string"}
                                    }
                                },
                                "email": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "comment": {"type": "string"},
                                        "source": {"type": "string"}
                                    }
                                },
                                "source": {"type": "string"}
                            }
                        },
                        "source": {"type": "string"}
                    }
                },
                "officers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "name": {"type": "string"},
                            "details": {"type": "string"},
                            "source": {"type": "string"}
                        }
                    }
                },
                "officers_comment": {"type": "string"},
                "ownership_structure": {
                    "type": "object",
                    "properties": {
                        "shareholders": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "entity_type": {"type": "string"},
                                    "nationality": {"type": "string"},
                                    "residence": {"type": "string"},
                                    "dob": {"type": "string"},
                                    "company_number": {"type": "string"},
                                    "details": {"type": "string"},
                                    "source": {"type": "string"}
                                }
                            }
                        },
                        "beneficial_owners": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "entity_type": {"type": "string"},
                                    "nationality": {"type": "string"},
                                    "residence": {"type": "string"},
                                    "dob": {"type": "string"},
                                    "company_number": {"type": "string"},
                                    "details": {"type": "string"},
                                    "source": {"type": "string"}
                                }
                            }
                        },
                        "comment": {"type": "string"},
                        "source": {"type": "string"}
                    }
                },
                "financial_results": {"type": "string"},
                "filings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "date": {"type": "string"},
                            "details": {"type": "string"},
                            "source": {"type": "string"}
                        }
                    }
                },
                "assets": {
                    "type": "object",
                    "properties": {
                        "property": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "comment": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "vehicle": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "comment": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "other": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "comment": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "source": {"type": "string"}
                    }
                },
                "activity": {"type": "string"},
                "compliance": {
                    "type": "object",
                    "properties": {
                        "litigation": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"}
                            }
                        },
                        "regulatory": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "actions": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "reputation": {
                            "type": "object",
                            "properties": {
                                "overview": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "other": {
                            "type": "object",
                            "properties": {
                                "details": {"type": "string"},
                                "source": {"type": "string"}
                            }
                        },
                        "source": {"type": "string"}
                    }
                },
                "notes": {"type": "string"},
                "_contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "values": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "value": {"type": "string"},
                                        "source": {"type": "string"}
                                    }
                                }
                            },
                            "highlight": {"type": "string"}
                        }
                    }
                },
                "_sources": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "raw_data": {"type": "object"}
            }
        }

        try:
            # Use structured output with tools + tool_choice
            response = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4000,
                temperature=0.1,
                tools=[
                    {
                        "name": "merge_entity",
                        "description": "Merge new company data into existing entity profile",
                        "input_schema": entity_schema
                    }
                ],
                tool_choice={"type": "tool", "name": "merge_entity"},
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract from tool use - already valid JSON matching schema
            tool_use = next((block for block in response.content if block.type == "tool_use"), None)
            if tool_use:
                merged_entity = tool_use.input
                # POST-PROCESSING: Wrap all entity names in green capsule HTML
                merged_entity = self.wrap_all_entity_names(merged_entity)
                return merged_entity
            else:
                raise Exception("No tool_use block in response")

        except Exception as e:
            print(f"⚠️  Haiku merge error: {e}")
            print(f"   Falling back to deterministic merge")
            # Fallback to simple deterministic merge
            return self._simple_merge(current_entity, new_result, badge)

    def _deterministic_merge(self, entity: Dict, result: Dict, badge: str) -> Dict:
        """
        FAST PATH: Deterministic field mapping from raw API data to template
        Maps all known fields programmatically BEFORE Haiku validation

        This runs FIRST, then Haiku validates/fixes/fills gaps
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

            # IMPORTANT: Loop through ALL Aleph results!
            # Each result is from a different dataset (sanctions, leaks, PEP, etc.)
            # and contains DIFFERENT information that must ALL be merged!
            for aleph_entity in results_list:
                props = aleph_entity.get("properties", {})

                # Map name
                if not entity.get("name"):
                    entity["name"] = {}
                aleph_name = aleph_entity.get("caption") or (props.get("name", [""])[0])
                if not entity["name"].get("value"):
                    # First time - set value and source
                    entity["name"]["value"] = aleph_name
                    entity["name"]["source"] = badge
                else:
                    # Name exists - check if same, append badge
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

                # Map registered address with multiple source handling
                if props.get("address"):
                    if not entity["about"].get("registered_address"):
                        entity["about"]["registered_address"] = {}
                    if not entity["about"]["registered_address"].get("value"):
                        # First time - set value and source
                        entity["about"]["registered_address"]["value"] = props["address"][0]
                        entity["about"]["registered_address"]["source"] = badge
                    else:
                        # Address exists - check if same, append badge
                        # If different, Haiku will handle contradiction
                        existing = entity["about"]["registered_address"]["value"].strip().lower()
                        new_addr = props["address"][0].strip().lower()
                        if existing == new_addr or existing.replace(",", "").replace("  ", " ") == new_addr.replace(",", "").replace("  ", " "):
                            if badge not in entity["about"]["registered_address"]["source"]:
                                entity["about"]["registered_address"]["source"] += f" {badge}"

                # Map website with multiple source handling
                if props.get("website"):
                    if not entity["about"].get("website"):
                        entity["about"]["website"] = {}
                    if not entity["about"]["website"].get("value"):
                        # First time - set value and source
                        entity["about"]["website"]["value"] = props["website"][0]
                        entity["about"]["website"]["source"] = badge
                    else:
                        # Website exists - check if same, append badge
                        existing = entity["about"]["website"]["value"].strip().lower().rstrip("/")
                        new_website = props["website"][0].strip().lower().rstrip("/")
                        if existing == new_website:
                            if badge not in entity["about"]["website"]["source"]:
                                entity["about"]["website"]["source"] += f" {badge}"

                # Map contact details
                if not entity["about"].get("contact_details"):
                    entity["about"]["contact_details"] = {}

                # Map phone with multiple source handling
                if props.get("phone"):
                    if not entity["about"]["contact_details"].get("phone"):
                        entity["about"]["contact_details"]["phone"] = {}
                    if not entity["about"]["contact_details"]["phone"].get("value"):
                        # First time - set value and source
                        entity["about"]["contact_details"]["phone"]["value"] = props["phone"][0]
                        entity["about"]["contact_details"]["phone"]["source"] = badge
                    else:
                        # Phone exists - check if same (normalize for comparison)
                        existing = entity["about"]["contact_details"]["phone"]["value"].replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                        new_phone = props["phone"][0].replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                        if existing == new_phone:
                            if badge not in entity["about"]["contact_details"]["phone"]["source"]:
                                entity["about"]["contact_details"]["phone"]["source"] += f" {badge}"

                # Map email with multiple source handling
                if props.get("email"):
                    if not entity["about"]["contact_details"].get("email"):
                        entity["about"]["contact_details"]["email"] = {}
                    if not entity["about"]["contact_details"]["email"].get("value"):
                        # First time - set value and source
                        entity["about"]["contact_details"]["email"]["value"] = props["email"][0]
                        entity["about"]["contact_details"]["email"]["source"] = badge
                    else:
                        # Email exists - check if same
                        if entity["about"]["contact_details"]["email"]["value"].strip().lower() == props["email"][0].strip().lower():
                            if badge not in entity["about"]["contact_details"]["email"]["source"]:
                                entity["about"]["contact_details"]["email"]["source"] += f" {badge}"

                # Officers from Aleph (if fetched via _fetch_aleph_directors_by_entity_id)
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

    def _simple_merge(self, entity: Dict, result: Dict, badge: str) -> Dict:
        """
        FALLBACK: Calls deterministic merge when Haiku fails
        """
        return self._deterministic_merge(entity, result, badge)


# Example usage
if __name__ == "__main__":
    async def test_populator():
        """Test the populator with sample data"""

        populator = CorporateEntityPopulator()

        # Sample OpenCorporates result
        oc_result = {
            "ok": True,
            "source": "opencorporates",
            "companies": [{
                "name": "Apple Inc",
                "company_number": "C0806592",
                "jurisdiction_code": "us_ca",
                "current_status": "Active",
                "registered_address": "One Apple Park Way, Cupertino, CA 95014"
            }]
        }

        # Process first result
        print("=== Processing OpenCorporates Result ===")
        entity1 = await populator.process_streaming_result(oc_result)
        print(json.dumps(entity1, indent=2))

        # Sample EDGAR result (simulated)
        edgar_result = {
            "ok": True,
            "source": "edgar",
            "companies": [{
                "name": "Apple Inc.",
                "registered_address": "One Apple Park Way, Cupertino, California 95014"
            }]
        }

        # Process second result (should deduplicate/merge)
        print("\n=== Processing EDGAR Result ===")
        entity2 = await populator.process_streaming_result(edgar_result)
        print(json.dumps(entity2, indent=2))

        # Check for contradictions
        if entity2.get("_contradictions"):
            print(f"\n⚠️  Contradictions detected: {len(entity2['_contradictions'])}")
            for contradiction in entity2["_contradictions"]:
                print(f"   {contradiction}")

    asyncio.run(test_populator())
