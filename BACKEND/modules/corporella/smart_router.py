"""
Smart Router - Input/Output Matrix for Intelligent Source Selection

This router decides which data sources to query based on:
1. What we're searching for (company, person, ownership, regulatory)
2. What data we have (name, ID, DOB, country)
3. Available collections per country

The router returns a prioritized list of search tasks to execute.
"""

from typing import Dict, List, Optional, Literal
from dataclasses import dataclass
from enum import Enum


class TargetType(Enum):
    """What the user wants to find"""
    COMPANY_PROFILE = "company_profile"
    BENEFICIAL_OWNERSHIP = "ownership"
    PERSON_DUE_DILIGENCE = "person_dd"
    REGULATORY_CHECK = "regulatory"
    SANCTIONS_CHECK = "sanctions"
    POLITICAL_EXPOSURE = "political_exposure"
    GENERIC_SEARCH = "generic"


class InputType(Enum):
    """Available input types from flow data"""
    COMPANY_NAME = "company_name"
    COMPANY_ID = "company_id"
    PERSON_NAME = "person_name"
    PERSON_ID = "person_id"
    PERSON_DOB = "person_dob"
    GENERIC_QUERY = "generic_query"


class OutputSchema(Enum):
    """Expected output schemas"""
    COMPANY = "Company"
    PERSON = "Person"
    ENTITY = "Entity"


@dataclass
class SearchTask:
    """A specific search to execute"""
    country: str
    collection_id: str
    collection_name: str
    input_type: InputType
    query_value: str
    expected_schema: OutputSchema
    filters: Dict[str, any]
    priority: int  # Lower = execute first


@dataclass
class UserInput:
    """What the user provides"""
    # Primary inputs
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    person_name: Optional[str] = None
    person_id: Optional[str] = None

    # Enhanced inputs
    person_dob: Optional[str] = None
    country: Optional[str] = None  # ISO 2-letter code
    countries: Optional[List[str]] = None  # Multi-country search

    # Target
    target: TargetType = TargetType.GENERIC_SEARCH


class CollectionRegistry:
    """
    Registry of available collections per country
    Built from flow data files
    """

    # Collection metadata from flow data
    COLLECTIONS = {
        'GB': {
            '809': {
                'name': 'UK Companies House',
                'inputs': ['company_name', 'company_id', 'person_name', 'person_id'],
                'outputs': {
                    'company_name': 'Company',
                    'company_id': 'Company',
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['directors', 'full_registry']
            },
            '2053': {
                'name': 'UK People with Significant Control',
                'inputs': ['company_name', 'company_id', 'person_name', 'person_id'],
                'outputs': {
                    'company_name': 'Company',
                    'company_id': 'Company',
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['beneficial_ownership', 'company_owner_person', 'company_owner_company']
            },
            '2302': {
                'name': 'UK Disqualified Directors',
                'inputs': ['person_name', 'person_id'],
                'outputs': {
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['person_dob', 'disqualifications']
            },
            '1303': {
                'name': 'HM Treasury Sanctions List',
                'inputs': ['person_name', 'person_id'],
                'outputs': {
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['sanctions', 'person_dob', 'person_nationality']
            },
            '153': {
                'name': 'UK Parliamentary Inquiries',
                'inputs': ['person_name', 'person_id'],
                'outputs': {
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['political_exposure']
            },
            'fca_register': {
                'name': 'FCA Register',
                'inputs': ['company_name', 'company_id', 'person_name', 'person_id'],
                'outputs': {
                    'company_name': 'Company',
                    'company_id': 'Company',
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': ['regulatory', 'fca_permissions', 'fca_disciplinary_history']
            }
        },
        'DE': {
            '1027': {
                'name': 'German companies registry (OpenCorporates, 2019)',
                'inputs': ['company_name'],
                'outputs': {
                    'company_name': 'Company'
                },
                'features': ['opencorporates']
            }
        },
        'MX': {
            '506': {
                'name': 'Personas de Interes (2014)',
                'inputs': ['company_name', 'company_id', 'person_name', 'person_id'],
                'outputs': {
                    'company_name': 'Company',
                    'company_id': 'Company',
                    'person_name': 'Person',
                    'person_id': 'Person'
                },
                'features': []
            }
        }
        # TODO: Add SK, PT, SI, GG, KE, MU, AZ when flow data is loaded
    }


class SmartRouter:
    """
    Routes searches to appropriate collections based on inputs and target
    """

    def __init__(self):
        self.registry = CollectionRegistry()

    def route(self, user_input: UserInput) -> List[SearchTask]:
        """
        Main routing logic

        Returns prioritized list of SearchTasks to execute
        """
        tasks = []

        # Determine countries to search
        countries = self._get_countries(user_input)

        for country in countries:
            country_tasks = self._route_for_country(country, user_input)
            tasks.extend(country_tasks)

        # Sort by priority (lower = execute first)
        tasks.sort(key=lambda t: t.priority)

        return tasks

    def _get_countries(self, user_input: UserInput) -> List[str]:
        """Determine which countries to search"""
        if user_input.countries:
            return user_input.countries
        elif user_input.country:
            return [user_input.country]
        else:
            # No country specified - use all available
            return list(self.registry.COLLECTIONS.keys())

    def _route_for_country(self, country: str, user_input: UserInput) -> List[SearchTask]:
        """Route within a specific country"""
        tasks = []

        collections = self.registry.COLLECTIONS.get(country, {})
        if not collections:
            return tasks

        # Route based on target type
        if user_input.target == TargetType.COMPANY_PROFILE:
            tasks = self._route_company_profile(country, collections, user_input)

        elif user_input.target == TargetType.BENEFICIAL_OWNERSHIP:
            tasks = self._route_ownership(country, collections, user_input)

        elif user_input.target == TargetType.PERSON_DUE_DILIGENCE:
            tasks = self._route_person_dd(country, collections, user_input)

        elif user_input.target == TargetType.REGULATORY_CHECK:
            tasks = self._route_regulatory(country, collections, user_input)

        elif user_input.target == TargetType.SANCTIONS_CHECK:
            tasks = self._route_sanctions(country, collections, user_input)

        elif user_input.target == TargetType.POLITICAL_EXPOSURE:
            tasks = self._route_political(country, collections, user_input)

        else:  # GENERIC_SEARCH
            tasks = self._route_generic(country, collections, user_input)

        return tasks

    def _route_company_profile(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for full company profile"""
        tasks = []

        # Priority 1: Direct company ID lookup
        if user_input.company_id:
            for coll_id, coll_data in collections.items():
                if 'company_id' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_ID,
                        query_value=user_input.company_id,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=1
                    ))

        # Priority 2: Company name search
        elif user_input.company_name:
            for coll_id, coll_data in collections.items():
                if 'company_name' in coll_data['inputs']:
                    # Companies House gets priority 2, others get 3
                    priority = 2 if 'Companies House' in coll_data['name'] else 3

                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_NAME,
                        query_value=user_input.company_name,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=priority
                    ))

        return tasks

    def _route_ownership(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for beneficial ownership search"""
        tasks = []

        # Look for PSC/ownership collections
        for coll_id, coll_data in collections.items():
            if 'beneficial_ownership' in coll_data.get('features', []):

                # Use company_id if available (priority 1)
                if user_input.company_id and 'company_id' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_ID,
                        query_value=user_input.company_id,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=1
                    ))

                # Otherwise use company_name (priority 2)
                elif user_input.company_name and 'company_name' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_NAME,
                        query_value=user_input.company_name,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=2
                    ))

        # Also get base company info (priority 3)
        base_tasks = self._route_company_profile(country, collections, user_input)
        for task in base_tasks:
            task.priority = 3  # Lower priority than PSC
        tasks.extend(base_tasks)

        return tasks

    def _route_person_dd(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for person due diligence"""
        tasks = []

        # Check all person-related collections
        person_collections = [
            ('sanctions', 1),  # Highest priority
            ('disqualifications', 2),
            ('political_exposure', 3),
            ('directors', 4)  # Lowest priority
        ]

        for feature, priority in person_collections:
            for coll_id, coll_data in collections.items():
                if feature in coll_data.get('features', []):

                    # Use person_id if available
                    if user_input.person_id and 'person_id' in coll_data['inputs']:
                        tasks.append(SearchTask(
                            country=country,
                            collection_id=coll_id,
                            collection_name=coll_data['name'],
                            input_type=InputType.PERSON_ID,
                            query_value=user_input.person_id,
                            expected_schema=OutputSchema.PERSON,
                            filters={'schema': 'Person'},
                            priority=priority
                        ))

                    # Otherwise use person_name
                    elif user_input.person_name and 'person_name' in coll_data['inputs']:
                        filters = {'schema': 'Person'}
                        # Add DOB filter if available and collection supports it
                        if user_input.person_dob and 'person_dob' in coll_data.get('features', []):
                            filters['person_dob'] = user_input.person_dob

                        tasks.append(SearchTask(
                            country=country,
                            collection_id=coll_id,
                            collection_name=coll_data['name'],
                            input_type=InputType.PERSON_NAME,
                            query_value=user_input.person_name,
                            expected_schema=OutputSchema.PERSON,
                            filters=filters,
                            priority=priority
                        ))

        return tasks

    def _route_regulatory(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for regulatory checks"""
        tasks = []

        for coll_id, coll_data in collections.items():
            if 'regulatory' in coll_data.get('features', []):

                if user_input.company_id and 'company_id' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_ID,
                        query_value=user_input.company_id,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=1
                    ))

                elif user_input.company_name and 'company_name' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.COMPANY_NAME,
                        query_value=user_input.company_name,
                        expected_schema=OutputSchema.COMPANY,
                        filters={'schema': 'Company'},
                        priority=1
                    ))

        return tasks

    def _route_sanctions(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for sanctions screening"""
        tasks = []

        for coll_id, coll_data in collections.items():
            if 'sanctions' in coll_data.get('features', []):

                if user_input.person_id and 'person_id' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.PERSON_ID,
                        query_value=user_input.person_id,
                        expected_schema=OutputSchema.PERSON,
                        filters={'schema': 'Person'},
                        priority=1
                    ))

                elif user_input.person_name and 'person_name' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.PERSON_NAME,
                        query_value=user_input.person_name,
                        expected_schema=OutputSchema.PERSON,
                        filters={'schema': 'Person'},
                        priority=1
                    ))

        return tasks

    def _route_political(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Route for political exposure check"""
        tasks = []

        for coll_id, coll_data in collections.items():
            if 'political_exposure' in coll_data.get('features', []):

                if user_input.person_name and 'person_name' in coll_data['inputs']:
                    tasks.append(SearchTask(
                        country=country,
                        collection_id=coll_id,
                        collection_name=coll_data['name'],
                        input_type=InputType.PERSON_NAME,
                        query_value=user_input.person_name,
                        expected_schema=OutputSchema.PERSON,
                        filters={'schema': 'Person'},
                        priority=1
                    ))

        return tasks

    def _route_generic(self, country: str, collections: dict, user_input: UserInput) -> List[SearchTask]:
        """Fallback: search all relevant collections"""
        tasks = []

        # Try company searches
        if user_input.company_name or user_input.company_id:
            tasks.extend(self._route_company_profile(country, collections, user_input))

        # Try person searches
        if user_input.person_name or user_input.person_id:
            tasks.extend(self._route_person_dd(country, collections, user_input))

        return tasks


# Example usage
if __name__ == "__main__":
    router = SmartRouter()

    # Example 1: UK Company with ownership
    print("=== Example 1: UK Company Ownership ===")
    user_input = UserInput(
        company_name="Revolut Ltd",
        country="GB",
        target=TargetType.BENEFICIAL_OWNERSHIP
    )
    tasks = router.route(user_input)
    for task in tasks:
        print(f"Priority {task.priority}: {task.collection_name} - {task.input_type.value} = '{task.query_value}'")

    print("\n=== Example 2: Person Due Diligence with DOB ===")
    user_input = UserInput(
        person_name="John Smith",
        person_dob="1985-03-15",
        country="GB",
        target=TargetType.PERSON_DUE_DILIGENCE
    )
    tasks = router.route(user_input)
    for task in tasks:
        print(f"Priority {task.priority}: {task.collection_name} - {task.input_type.value} = '{task.query_value}'")

    print("\n=== Example 3: FCA Regulatory Check ===")
    user_input = UserInput(
        company_name="Barclays Bank",
        country="GB",
        target=TargetType.REGULATORY_CHECK
    )
    tasks = router.route(user_input)
    for task in tasks:
        print(f"Priority {task.priority}: {task.collection_name} - {task.input_type.value} = '{task.query_value}'")

    print("\n=== Example 4: Cross-Border Search ===")
    user_input = UserInput(
        company_name="Deutsche Bank",
        countries=["DE", "GB"],
        target=TargetType.COMPANY_PROFILE
    )
    tasks = router.route(user_input)
    for task in tasks:
        print(f"Priority {task.priority}: [{task.country}] {task.collection_name} - {task.input_type.value}")
