#!/usr/bin/env python3
"""
Dynamic Flow Router - Maps inputs to outputs and template slots
Enables bidirectional action generation based on what data we have or need
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class FlowMapping:
    """Represents a data flow between input and output"""
    input_type: str          # e.g., "company_number", "tax_id", "person_id"
    input_format: str        # e.g., "GB########", "CNPJ", "NIK"
    jurisdiction: str        # e.g., "GB", "BR", "ID"
    output_slots: List[str]  # Template slots this can fill
    fetcher: str            # Which fetcher to use
    description: str        # Human-readable description


class DynamicFlowRouter:
    """
    Routes between:
    1. What we HAVE (inputs) → What we can GET (outputs)
    2. What we NEED (empty slots) → What inputs would FILL them
    """

    def __init__(self):
        self.flow_mappings = self._initialize_flow_mappings()
        self.slot_to_input_map = self._build_reverse_map()

    def _initialize_flow_mappings(self) -> List[FlowMapping]:
        """Define all known input→output flows"""
        return [
            # UK Companies House
            FlowMapping(
                input_type="company_number",
                input_format=r"^[A-Z]{2}\d{6}$|^\d{8}$",
                jurisdiction="GB",
                output_slots=[
                    "officers",
                    "about.registered_address",
                    "about.incorporation_date",
                    "compliance.regulatory.filings",
                    "ownership.beneficial_owners"
                ],
                fetcher="uk_companies_house",
                description="Fetch UK company data from Companies House"
            ),

            # Brazil CNPJ
            FlowMapping(
                input_type="cnpj",
                input_format=r"^\d{14}$",
                jurisdiction="BR",
                output_slots=[
                    "name.value",
                    "about.company_number",
                    "about.registered_address",
                    "about.jurisdiction",
                    "compliance.regulatory.status"
                ],
                fetcher="brazil_receita_federal",
                description="Fetch Brazilian company from Receita Federal"
            ),

            # Indonesia NIK (for person lookups)
            FlowMapping(
                input_type="nik",
                input_format=r"^\d{16}$",
                jurisdiction="ID",
                output_slots=[
                    "officers",  # If person is an officer
                    "ownership.beneficial_owners"  # If person is an owner
                ],
                fetcher="indonesia_person_lookup",
                description="Lookup Indonesian person by NIK"
            ),

            # US EIN/CIK for EDGAR
            FlowMapping(
                input_type="cik",
                input_format=r"^\d{10}$",
                jurisdiction="US",
                output_slots=[
                    "compliance.regulatory.filings",
                    "financials.revenue",
                    "financials.assets",
                    "officers",
                    "ownership.major_shareholders"
                ],
                fetcher="sec_edgar",
                description="Fetch SEC filings from EDGAR"
            ),

            # EU VAT Number
            FlowMapping(
                input_type="vat_number",
                input_format=r"^[A-Z]{2}\d+",
                jurisdiction="EU",
                output_slots=[
                    "name.value",
                    "about.vat_number",
                    "about.registered_address",
                    "compliance.tax.status"
                ],
                fetcher="eu_vies",
                description="Validate EU VAT number via VIES"
            ),

            # Generic company name search
            FlowMapping(
                input_type="company_name",
                input_format=r".+",
                jurisdiction="GLOBAL",
                output_slots=[
                    "about.company_number",
                    "about.jurisdiction",
                    "about.registered_address",
                    "officers",
                    "ownership.beneficial_owners"
                ],
                fetcher="opencorporates",
                description="Search OpenCorporates by company name"
            ),

            # Person name for director/officer searches
            FlowMapping(
                input_type="person_name",
                input_format=r".+",
                jurisdiction="GLOBAL",
                output_slots=[
                    "person.directorships",
                    "person.beneficial_ownerships",
                    "person.sanctions_status"
                ],
                fetcher="occrp_aleph",
                description="Search OCCRP Aleph for person"
            ),

            # LEI (Legal Entity Identifier)
            FlowMapping(
                input_type="lei",
                input_format=r"^[A-Z0-9]{20}$",
                jurisdiction="GLOBAL",
                output_slots=[
                    "name.value",
                    "about.lei",
                    "about.registered_address",
                    "ownership.direct_parent",
                    "ownership.ultimate_parent"
                ],
                fetcher="gleif",
                description="Fetch entity data from GLEIF"
            ),

            # Domain name for company discovery
            FlowMapping(
                input_type="domain",
                input_format=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                jurisdiction="GLOBAL",
                output_slots=[
                    "name.value",
                    "about.website",
                    "contact.emails",
                    "contact.phones",
                    "locations.headquarters"
                ],
                fetcher="domain_intel",
                description="Discover company from domain"
            )
        ]

    def _build_reverse_map(self) -> Dict[str, List[FlowMapping]]:
        """Build slot → input mappings for reverse lookup"""
        slot_map = {}
        for flow in self.flow_mappings:
            for slot in flow.output_slots:
                if slot not in slot_map:
                    slot_map[slot] = []
                slot_map[slot].append(flow)
        return slot_map

    def detect_input_type(self, value: str) -> List[Dict[str, Any]]:
        """
        Detect what type of input we have and what we can fetch with it
        Returns list of possible actions
        """
        from .id_decoder import decode_id

        actions = []
        value = value.strip()

        # First try ID decoder for national IDs
        decoded_id = decode_id(value)
        if decoded_id.get("valid"):
            # We have a valid national ID
            id_type = decoded_id.get("id_type", "").lower()
            country = decoded_id.get("country", "")

            # Map ID types to our flow system
            if "cnpj" in id_type:
                actions.append({
                    "action": "fetch_brazil_company",
                    "input_type": "cnpj",
                    "value": value,
                    "jurisdiction": "BR",
                    "decoded_info": decoded_id.get("decoded_info", {}),
                    "description": f"Fetch Brazilian company data for CNPJ {decoded_id['decoded_info'].get('formatted', value)}"
                })
            elif "cpf" in id_type:
                actions.append({
                    "action": "fetch_brazil_person",
                    "input_type": "cpf",
                    "value": value,
                    "jurisdiction": "BR",
                    "decoded_info": decoded_id.get("decoded_info", {}),
                    "description": f"Lookup Brazilian person with CPF {decoded_id['decoded_info'].get('formatted', value)}"
                })
            elif "nik" in id_type:
                decoded_info = decoded_id.get("decoded_info", {})
                actions.append({
                    "action": "fetch_indonesia_person",
                    "input_type": "nik",
                    "value": value,
                    "jurisdiction": "ID",
                    "decoded_info": decoded_info,
                    "description": f"Lookup Indonesian person (DOB: {decoded_info.get('date_of_birth', 'Unknown')}, {decoded_info.get('gender', 'Unknown')})"
                })

        # Check against our flow patterns
        for flow in self.flow_mappings:
            if re.match(flow.input_format, value, re.IGNORECASE):
                # Skip if we already have this from ID decoder
                if any(a["input_type"] == flow.input_type for a in actions):
                    continue

                actions.append({
                    "action": f"fetch_{flow.fetcher}",
                    "input_type": flow.input_type,
                    "value": value,
                    "jurisdiction": flow.jurisdiction,
                    "output_slots": flow.output_slots,
                    "description": flow.description
                })

        return actions

    def get_inputs_for_slot(self, slot_path: str, jurisdiction: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Given an empty slot, determine what inputs could fill it
        Returns list of possible input requirements
        """
        inputs = []

        # Get all flows that can fill this slot
        matching_flows = self.slot_to_input_map.get(slot_path, [])

        for flow in matching_flows:
            # Filter by jurisdiction if specified
            if jurisdiction and flow.jurisdiction not in ["GLOBAL", jurisdiction]:
                continue

            inputs.append({
                "input_type": flow.input_type,
                "input_format": flow.input_format,
                "jurisdiction": flow.jurisdiction,
                "fetcher": flow.fetcher,
                "description": f"Provide {flow.input_type} to {flow.description}",
                "example": self._get_example_for_input(flow.input_type)
            })

        return inputs

    def _get_example_for_input(self, input_type: str) -> str:
        """Provide example values for different input types"""
        examples = {
            "company_number": "12345678 (UK)",
            "cnpj": "11.222.333/0001-81",
            "cpf": "123.456.789-00",
            "nik": "3527091604810001",
            "cik": "0000320193 (Apple)",
            "vat_number": "GB123456789",
            "lei": "549300GFG0M4RJCTJE92",
            "company_name": "Apple Inc",
            "person_name": "Tim Cook",
            "domain": "apple.com"
        }
        return examples.get(input_type, "")

    def analyze_entity(self, entity: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Analyze an entire entity to find:
        1. All detected inputs (IDs, numbers) that can fetch more data
        2. All empty slots that could be filled

        Returns: {
            "available_actions": [...],  # What we CAN fetch
            "fillable_slots": [...]      # What we NEED
        }
        """
        available_actions = []
        fillable_slots = []

        # Scan entity for potential inputs
        potential_inputs = self._extract_potential_inputs(entity)
        for input_value in potential_inputs:
            actions = self.detect_input_type(input_value)
            available_actions.extend(actions)

        # Find empty slots
        empty_slots = self._find_empty_slots(entity)
        jurisdiction = entity.get("about", {}).get("jurisdiction")

        for slot_path in empty_slots:
            inputs = self.get_inputs_for_slot(slot_path, jurisdiction)
            if inputs:
                fillable_slots.append({
                    "slot_path": slot_path,
                    "possible_inputs": inputs
                })

        return {
            "available_actions": available_actions,
            "fillable_slots": fillable_slots
        }

    def _extract_potential_inputs(self, entity: Dict[str, Any], path: str = "") -> List[str]:
        """Recursively extract all potential input values from entity"""
        inputs = []

        if isinstance(entity, dict):
            for key, value in entity.items():
                new_path = f"{path}.{key}" if path else key

                # Check if this looks like an ID field
                if any(id_key in key.lower() for id_key in ["number", "id", "code", "vat", "lei", "ein", "cik"]):
                    if isinstance(value, str) and value:
                        inputs.append(value)
                    elif isinstance(value, dict) and "value" in value:
                        inputs.append(value["value"])

                # Recurse
                if isinstance(value, (dict, list)):
                    inputs.extend(self._extract_potential_inputs(value, new_path))

        elif isinstance(entity, list):
            for item in entity:
                inputs.extend(self._extract_potential_inputs(item, path))

        return inputs

    def _find_empty_slots(self, entity: Dict[str, Any], path: str = "") -> List[str]:
        """Find all empty or missing slots in the entity"""
        empty = []

        # Define expected slots for a complete profile
        expected_slots = {
            "name.value",
            "about.company_number",
            "about.jurisdiction",
            "about.registered_address",
            "officers",
            "ownership.beneficial_owners",
            "compliance.regulatory.filings",
            "financials.revenue"
        }

        for slot in expected_slots:
            value = self._get_nested_value(entity, slot)
            if not value or (isinstance(value, list) and len(value) == 0):
                empty.append(slot)

        return empty

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dict using dot notation"""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return None
            else:
                return None

        return current


# Singleton instance
flow_router = DynamicFlowRouter()