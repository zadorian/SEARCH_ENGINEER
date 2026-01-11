"""
Gap-Aware Smart Router

DEFAULT BEHAVIOR: If a field is blank/null in the company JSON, we're looking for it.

This router analyzes the current entity profile and automatically determines
what data is missing, then routes searches to fill those gaps.
"""

from typing import Dict, List, Optional, Set
from smart_router import (
    SmartRouter, UserInput, TargetType, SearchTask,
    InputType, OutputSchema
)
import json
from utils import decode_id


class EntityGapAnalyzer:
    """
    Analyzes an entity template to identify missing fields
    and maps them to the data we need to fetch
    """

    # Map entity fields to target types
    FIELD_TO_TARGET = {
        # Ownership structure
        'ownership_structure.beneficial_owners': TargetType.BENEFICIAL_OWNERSHIP,
        'ownership_structure.shareholders': TargetType.BENEFICIAL_OWNERSHIP,
        'ownership_structure.ownership_percentage': TargetType.BENEFICIAL_OWNERSHIP,

        # Compliance & regulatory
        'compliance.regulatory': TargetType.REGULATORY_CHECK,
        'compliance.sanctions': TargetType.SANCTIONS_CHECK,

        # Officers
        'officers': TargetType.COMPANY_PROFILE,  # Directors included in company profile

        # Basic company info
        'about.company_number': TargetType.COMPANY_PROFILE,
        'about.lei': TargetType.COMPANY_PROFILE,
        'about.founded_year': TargetType.COMPANY_PROFILE,
        'about.jurisdiction': TargetType.COMPANY_PROFILE,
        'about.registered_address': TargetType.COMPANY_PROFILE,
        'about.website': TargetType.COMPANY_PROFILE,
        'about.industry': TargetType.COMPANY_PROFILE,

        # Financial
        'financial_results': TargetType.COMPANY_PROFILE,

        # Filings
        'filings': TargetType.COMPANY_PROFILE,
    }

    def __init__(self, entity_template_path: str = "entity_template.json"):
        """Load the entity template"""
        with open(entity_template_path, 'r') as f:
            self.template = json.load(f)

    def analyze_gaps(self, current_entity: Dict) -> Set[TargetType]:
        """
        Compare current entity against template to find missing fields
        Returns set of TargetTypes we need to fetch
        """
        gaps = set()

        # Check ownership structure
        if self._is_empty(current_entity.get('ownership_structure', {}).get('beneficial_owners')):
            gaps.add(TargetType.BENEFICIAL_OWNERSHIP)

        # Check regulatory/compliance
        if self._is_empty(current_entity.get('compliance', {}).get('regulatory')):
            gaps.add(TargetType.REGULATORY_CHECK)

        if self._is_empty(current_entity.get('compliance', {}).get('sanctions', {}).get('details')):
            gaps.add(TargetType.SANCTIONS_CHECK)

        # Check officers
        if self._is_empty(current_entity.get('officers')):
            gaps.add(TargetType.COMPANY_PROFILE)

        # Check basic company info
        about = current_entity.get('about', {})
        if self._is_empty(about.get('company_number')) or \
           self._is_empty(about.get('jurisdiction')) or \
           self._is_empty(about.get('registered_address', {}).get('value')):
            gaps.add(TargetType.COMPANY_PROFILE)

        # If no specific gaps, default to company profile
        if not gaps:
            gaps.add(TargetType.COMPANY_PROFILE)

        return gaps

    def _is_empty(self, value) -> bool:
        """Check if a value is empty/null/blank"""
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, list):
            return len(value) == 0
        if isinstance(value, dict):
            # Check if all values in dict are empty
            return all(self._is_empty(v) for v in value.values())
        return False

    def get_missing_fields(self, current_entity: Dict) -> Dict[str, List[str]]:
        """
        Returns detailed list of missing fields grouped by category
        """
        missing = {
            'ownership': [],
            'regulatory': [],
            'officers': [],
            'company_info': [],
            'financial': []
        }

        # Check ownership
        ownership = current_entity.get('ownership_structure', {})
        if self._is_empty(ownership.get('beneficial_owners')):
            missing['ownership'].append('beneficial_owners')
        if self._is_empty(ownership.get('shareholders')):
            missing['ownership'].append('shareholders')

        # Check regulatory
        compliance = current_entity.get('compliance', {})
        if self._is_empty(compliance.get('regulatory')):
            missing['regulatory'].append('regulatory_status')
        if self._is_empty(compliance.get('sanctions')):
            missing['regulatory'].append('sanctions_check')

        # Check officers
        if self._is_empty(current_entity.get('officers')):
            missing['officers'].append('directors')
            missing['officers'].append('officers')

        # Check company info
        about = current_entity.get('about', {})
        if self._is_empty(about.get('company_number')):
            missing['company_info'].append('company_number')
        if self._is_empty(about.get('jurisdiction')):
            missing['company_info'].append('jurisdiction')
        if self._is_empty(about.get('registered_address')):
            missing['company_info'].append('registered_address')
        if self._is_empty(about.get('website')):
            missing['company_info'].append('website')

        # Check financial
        if self._is_empty(current_entity.get('financial_results')):
            missing['financial'].append('revenue')
            missing['financial'].append('assets')

        return missing


class GapAwareRouter:
    """
    Smart router that automatically determines what to fetch based on
    what's missing from the current entity profile
    """

    def __init__(self, entity_template_path: str = "entity_template.json"):
        self.router = SmartRouter()
        self.gap_analyzer = EntityGapAnalyzer(entity_template_path)

    def route_from_entity(
        self,
        current_entity: Dict,
        available_inputs: Optional[Dict] = None
    ) -> List[SearchTask]:
        """
        Analyze entity gaps and route searches to fill them

        Args:
            current_entity: Current entity profile (with some fields filled)
            available_inputs: Optional dict of available search inputs
                             If not provided, extracts from current_entity

        Returns:
            List of SearchTask prioritized to fill gaps
        """
        # Analyze what's missing
        target_gaps = self.gap_analyzer.analyze_gaps(current_entity)
        missing_fields = self.gap_analyzer.get_missing_fields(current_entity)

        # Extract available inputs
        if available_inputs is None:
            available_inputs = self._extract_inputs_from_entity(current_entity)

        # Route for each gap
        all_tasks = []
        for target in target_gaps:
            user_input = UserInput(
                company_name=available_inputs.get('company_name'),
                company_id=available_inputs.get('company_id'),
                person_name=available_inputs.get('person_name'),
                person_id=available_inputs.get('person_id'),
                person_dob=available_inputs.get('person_dob'),
                country=available_inputs.get('country'),
                countries=available_inputs.get('countries'),
                target=target
            )

            tasks = self.router.route(user_input)
            all_tasks.extend(tasks)

        # Deduplicate tasks (same collection + input)
        unique_tasks = self._deduplicate_tasks(all_tasks)

        return unique_tasks

    def _extract_inputs_from_entity(self, entity: Dict) -> Dict:
        """
        Extract searchable inputs from existing entity data

        ENHANCED: Now uses ID decoder to extract DOB/gender from person_id
        """
        inputs = {}

        # Company inputs
        name = entity.get('name', {})
        if isinstance(name, dict):
            inputs['company_name'] = name.get('value', '')
        else:
            inputs['company_name'] = entity.get('name', '')

        about = entity.get('about', {})
        inputs['company_id'] = about.get('company_number', '')
        inputs['country'] = about.get('jurisdiction', '')

        # Person inputs (if searching for officers)
        officers = entity.get('officers', [])
        if officers and len(officers) > 0:
            inputs['person_name'] = officers[0].get('name', '')

            # NEW: If person_id is available, decode it to get DOB and gender
            person_id = officers[0].get('person_id', '')
            if person_id:
                try:
                    decoded = decode_id(person_id)
                    if decoded.get('valid'):
                        decoded_info = decoded.get('decoded_info', {})

                        # Extract DOB if not already present
                        if not inputs.get('person_dob') and decoded_info.get('date_of_birth'):
                            inputs['person_dob'] = decoded_info['date_of_birth']

                        # Extract gender if available
                        if decoded_info.get('gender'):
                            inputs['person_gender'] = decoded_info['gender']

                        # Extract location if available and country not set
                        if not inputs.get('country') and decoded.get('country'):
                            inputs['country'] = decoded['country']

                except Exception as e:
                    # Silently ignore ID decoding errors - not critical
                    pass

        return inputs

    def _deduplicate_tasks(self, tasks: List[SearchTask]) -> List[SearchTask]:
        """Remove duplicate search tasks"""
        seen = set()
        unique = []

        for task in tasks:
            # Create unique key from collection + input_type + query
            key = (task.country, task.collection_id, task.input_type.value, task.query_value)
            if key not in seen:
                seen.add(key)
                unique.append(task)

        # Re-sort by priority
        unique.sort(key=lambda t: t.priority)
        return unique

    def route_with_gaps_report(
        self,
        current_entity: Dict,
        available_inputs: Optional[Dict] = None
    ) -> Dict:
        """
        Route searches AND return detailed gap analysis

        Returns:
            {
                'missing_fields': {...},  # Detailed gaps by category
                'targets': [...],         # TargetTypes we'll fetch
                'search_tasks': [...],    # Prioritized SearchTasks
                'summary': str            # Human-readable summary
            }
        """
        missing_fields = self.gap_analyzer.get_missing_fields(current_entity)
        target_gaps = self.gap_analyzer.analyze_gaps(current_entity)

        if available_inputs is None:
            available_inputs = self._extract_inputs_from_entity(current_entity)

        tasks = self.route_from_entity(current_entity, available_inputs)

        # Generate summary
        summary_parts = []
        if missing_fields['ownership']:
            summary_parts.append(f"Ownership data missing: {', '.join(missing_fields['ownership'])}")
        if missing_fields['regulatory']:
            summary_parts.append(f"Regulatory data missing: {', '.join(missing_fields['regulatory'])}")
        if missing_fields['officers']:
            summary_parts.append(f"Officers data missing: {', '.join(missing_fields['officers'])}")
        if missing_fields['company_info']:
            summary_parts.append(f"Company info missing: {', '.join(missing_fields['company_info'])}")

        summary = " | ".join(summary_parts) if summary_parts else "Profile complete"

        return {
            'missing_fields': missing_fields,
            'targets': [t.value for t in target_gaps],
            'search_tasks': tasks,
            'summary': summary,
            'total_searches': len(tasks)
        }


# Example usage
if __name__ == "__main__":
    router = GapAwareRouter()

    # Example 1: Empty entity - fetch everything
    print("=== Example 1: Empty Entity (Fetch Everything) ===")
    empty_entity = {
        "name": {"value": "Revolut Ltd"},
        "about": {"jurisdiction": "GB"},
        "ownership_structure": {},
        "officers": [],
        "compliance": {}
    }

    report = router.route_with_gaps_report(empty_entity)
    print(f"Missing fields: {report['missing_fields']}")
    print(f"Targets: {report['targets']}")
    print(f"Summary: {report['summary']}")
    print(f"Total searches: {report['total_searches']}")
    print("\nSearch Tasks:")
    for task in report['search_tasks'][:5]:  # Show first 5
        print(f"  Priority {task.priority}: {task.collection_name} - {task.input_type.value}")

    # Example 2: Partial entity - only fetch what's missing
    print("\n=== Example 2: Partial Entity (Only Fetch Missing Ownership) ===")
    partial_entity = {
        "name": {"value": "Revolut Ltd"},
        "about": {
            "company_number": "08804411",
            "jurisdiction": "GB",
            "registered_address": {"value": "7 Westferry Circus, London E14 4HD"},
            "founded_year": "2015"
        },
        "officers": [
            {"name": "Nikolay Storonsky", "position": "Director"}
        ],
        "ownership_structure": {},  # MISSING!
        "compliance": {
            "regulatory": {"summary": "Authorized by FCA"},
            "sanctions": {}  # MISSING!
        }
    }

    report = router.route_with_gaps_report(partial_entity)
    print(f"Missing fields: {report['missing_fields']}")
    print(f"Targets: {report['targets']}")
    print(f"Summary: {report['summary']}")
    print(f"Total searches: {report['total_searches']}")
    print("\nSearch Tasks:")
    for task in report['search_tasks']:
        print(f"  Priority {task.priority}: {task.collection_name} - {task.input_type.value}")

    # Example 3: Complete entity - nothing to fetch
    print("\n=== Example 3: Complete Entity (Nothing Missing) ===")
    complete_entity = {
        "name": {"value": "Revolut Ltd"},
        "about": {
            "company_number": "08804411",
            "jurisdiction": "GB",
            "registered_address": {"value": "7 Westferry Circus, London E14 4HD"},
            "founded_year": "2015"
        },
        "officers": [
            {"name": "Nikolay Storonsky", "position": "Director"}
        ],
        "ownership_structure": {
            "beneficial_owners": [
                {"name": "Nikolay Storonsky", "percentage": "58.4%"}
            ]
        },
        "compliance": {
            "regulatory": {"summary": "Authorized by FCA"},
            "sanctions": {"listed": False}
        }
    }

    report = router.route_with_gaps_report(complete_entity)
    print(f"Missing fields: {report['missing_fields']}")
    print(f"Summary: {report['summary']}")
    print(f"Total searches: {report['total_searches']}")
