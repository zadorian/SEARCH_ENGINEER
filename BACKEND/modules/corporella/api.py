"""
Corporella Unified API for RuleExecutor

SINGLE ENTRY POINT for corporate intelligence operations.
Used by chains and rules to get company data, officers, beneficial owners, shareholders.

Usage:
    from BACKEND.modules.corporella.api import corporella

    # Get company profile
    profile = await corporella.get_company_profile("Podravka d.d.", jurisdiction="HR")

    # Get officers
    officers = await corporella.get_officers("Tesla Inc")

    # Get officer appointments for a person
    appointments = await corporella.get_officer_appointments("Elon Musk")

    # Get beneficial owners
    owners = await corporella.get_beneficial_owners("Example Ltd", jurisdiction="GB")

    # Get shareholders
    shareholders = await corporella.get_shareholders("Apple Inc")
"""

import os
import sys
import asyncio
import logging
import requests
import base64
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)

logger = logging.getLogger(__name__)

# API Keys from environment (loaded from project root .env)
OPENCORPORATES_API_KEY = os.getenv('OPENCORPORATES_API_KEY')
COMPANIES_HOUSE_API_KEY = os.getenv('CH_API_KEY') or os.getenv('COMPANIES_HOUSE_API_KEY')
OCCRP_API_KEY = os.getenv('OCCRP_API_KEY')
OPENSANCTIONS_API_KEY = os.getenv('OPENSANCTIONS_API_KEY')


@dataclass
class Officer:
    """Officer/director of a company"""
    name: str
    role: str
    appointed_on: Optional[str] = None
    resigned_on: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    occupation: Optional[str] = None
    company_name: Optional[str] = None
    company_number: Optional[str] = None


@dataclass
class BeneficialOwner:
    """Beneficial owner (PSC) of a company"""
    name: str
    natures_of_control: List[str]
    notified_on: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    ownership_percentage: Optional[float] = None
    kind: Optional[str] = None  # individual, corporate, legal-person


@dataclass
class CompanyProfile:
    """Basic company profile"""
    name: str
    company_number: Optional[str] = None
    jurisdiction: Optional[str] = None
    status: Optional[str] = None
    incorporation_date: Optional[str] = None
    address: Optional[str] = None
    company_type: Optional[str] = None
    sic_codes: Optional[List[str]] = None
    officers: Optional[List[Officer]] = None
    beneficial_owners: Optional[List[BeneficialOwner]] = None


class CorporellaAPI:
    """
    Unified API for corporate intelligence.
    Aggregates data from multiple sources:
    - OpenCorporates (global)
    - UK Companies House (GB)
    - OCCRP Aleph (investigative)
    - OpenSanctions (compliance)
    - GLEIF (Legal Entity Identifiers - global, free API)

    GLEIF Features:
    - LEI codes (20-char unique identifiers)
    - Parent/subsidiary relationships
    - Previous company names
    - BIC/SWIFT codes
    - Cross-border ownership chains
    """

    def __init__(self):
        self._session = None

    def _get_ch_headers(self) -> Dict[str, str]:
        """Get Companies House authorization headers"""
        auth = base64.b64encode(f"{COMPANIES_HOUSE_API_KEY}:".encode('utf-8')).decode('utf-8')
        return {'Authorization': f'Basic {auth}'}

    # =========================================================================
    # COMPANY PROFILE
    # =========================================================================

    async def get_company_profile(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get basic company profile from best available source.

        Args:
            company_name: Company name to search
            jurisdiction: Optional 2-letter country code (e.g., 'GB', 'HR', 'US')

        Returns:
            Dict with company profile data
        """
        # --- NEXUS VALIDATION (Pattern Check) ---
        if jurisdiction:
            try:
                from modules.NEXUS.nexus_logic import NexusLogic
                nexus = NexusLogic()
                # Use RestrainedTemplate for fast pattern matching
                templates = nexus.get_logic("restrained_template")
                
                # Guess concept from jurisdiction (e.g. "GB" -> "[UK Company]")
                # We need a mapping or just construct it. RestrainedTemplate has shorthands.
                # Let's try to find patterns for this jurisdiction.
                # This is a bit hacky without a direct "get patterns for geo" method, 
                # but we can try generating for "[{geo} Company]"
                
                # Mapping iso code to concept name if possible, or relying on RestrainedTemplate's smarts
                geo_map = {"GB": "UK", "UK": "UK", "DE": "German", "US": "US", "FR": "French"}
                geo_name = geo_map.get(jurisdiction.upper(), jurisdiction)
                concept = f"[{geo_name} Company]"
                
                # We use generate() which returns a KeywordResult with 'patterns'
                # Note: This is async
                keyword_result = await templates.generate(concept)
                
                if keyword_result.patterns:
                    # Check if company name contains any of the patterns
                    matches = [p for p in keyword_result.patterns if p.lower() in company_name.lower()]
                    if not matches and len(keyword_result.patterns) > 1:
                        # Don't warn if only 1 pattern (likely just the concept name itself)
                        logger.warning(f"NEXUS VALIDATION: '{company_name}' does not match typical patterns for {jurisdiction} ({keyword_result.patterns})")
                        # We could flag this in the result
            except Exception as e:
                # Fail open - don't block execution
                logger.debug(f"NEXUS validation skipped: {e}")
        # ---------------------------------------

        result = {
            'company_name': company_name,
            'jurisdiction': jurisdiction,
            'sources': [],
            'profiles': []
        }

        # Route to best source based on jurisdiction
        if jurisdiction == 'GB':
            ch_result = await self._get_profile_companies_house(company_name)
            if ch_result:
                result['profiles'].extend(ch_result)
                result['sources'].append('companies_house')

        # Always check OpenCorporates (global coverage)
        oc_result = await self._get_profile_opencorporates(company_name, jurisdiction)
        if oc_result:
            result['profiles'].extend(oc_result)
            result['sources'].append('opencorporates')

        # Check OCCRP Aleph for investigative data
        aleph_result = await self._get_profile_aleph(company_name)
        if aleph_result:
            result['profiles'].extend(aleph_result)
            result['sources'].append('occrp_aleph')

        # Check GLEIF for LEI data (global coverage, no API key needed)
        gleif_result = await self._get_profile_gleif(company_name, jurisdiction)
        if gleif_result:
            result['profiles'].extend(gleif_result)
            result['sources'].append('gleif')

        return result

    async def _get_profile_opencorporates(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None
    ) -> List[Dict]:
        """Get company profiles from OpenCorporates"""
        try:
            url = "https://api.opencorporates.com/v0.4/companies/search"
            params = {
                'q': company_name,
                'api_token': OPENCORPORATES_API_KEY,
                'per_page': 10
            }
            if jurisdiction:
                params['jurisdiction_code'] = jurisdiction.lower()

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                profiles = []
                for company in data.get('results', {}).get('companies', []):
                    co = company.get('company', {})
                    profiles.append({
                        'source': 'opencorporates',
                        'name': co.get('name'),
                        'company_number': co.get('company_number'),
                        'jurisdiction': co.get('jurisdiction_code'),
                        'status': co.get('current_status'),
                        'incorporation_date': co.get('incorporation_date'),
                        'address': co.get('registered_address_in_full'),
                        'company_type': co.get('company_type'),
                        'opencorporates_url': co.get('opencorporates_url')
                    })
                return profiles
        except Exception as e:
            logger.error(f"OpenCorporates error: {e}")
        return []

    async def _get_profile_companies_house(self, company_name: str) -> List[Dict]:
        """Get company profiles from UK Companies House"""
        try:
            url = "https://api.company-information.service.gov.uk/search/companies"
            params = {'q': company_name, 'items_per_page': 10}

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=self._get_ch_headers(), params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                profiles = []
                for item in data.get('items', []):
                    profiles.append({
                        'source': 'companies_house',
                        'name': item.get('title'),
                        'company_number': item.get('company_number'),
                        'jurisdiction': 'GB',
                        'status': item.get('company_status'),
                        'incorporation_date': item.get('date_of_creation'),
                        'address': item.get('address', {}),
                        'company_type': item.get('company_type')
                    })
                return profiles
        except Exception as e:
            logger.error(f"Companies House error: {e}")
        return []

    async def _get_profile_aleph(self, company_name: str) -> List[Dict]:
        """Get company profiles from OCCRP Aleph"""
        try:
            url = "https://aleph.occrp.org/api/2/entities"
            headers = {'Authorization': f'ApiKey {OCCRP_API_KEY}'}
            params = {'q': company_name, 'filter:schema': 'Company', 'limit': 10}

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=headers, params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                profiles = []
                for result in data.get('results', []):
                    props = result.get('properties', {})
                    profiles.append({
                        'source': 'occrp_aleph',
                        'name': self._get_prop(props, 'name'),
                        'aleph_id': result.get('id'),
                        'countries': self._get_prop(props, 'country'),
                        'dates': self._get_prop(props, 'date'),
                        'aliases': self._get_prop(props, 'alias'),
                        'topics': self._get_prop(props, 'topics'),
                        'collection': result.get('collection', {}).get('label')
                    })
                return profiles
        except Exception as e:
            logger.error(f"OCCRP Aleph error: {e}")
        return []

    async def _get_profile_gleif(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None
    ) -> List[Dict]:
        """
        Get company profiles from GLEIF (Global Legal Entity Identifier Foundation).

        GLEIF provides LEI codes - unique identifiers for legal entities worldwide.
        No API key required - free public API.
        """
        try:
            url = "https://api.gleif.org/api/v1/lei-records"
            params = {
                'filter[entity.legalName]': company_name,
                'page[size]': 20
            }
            if jurisdiction:
                params['filter[entity.jurisdiction]'] = jurisdiction.upper()

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                profiles = []
                for record in data.get('data', []):
                    attrs = record.get('attributes', {})
                    entity = attrs.get('entity', {})
                    registration = attrs.get('registration', {})
                    legal_address = entity.get('legalAddress', {})
                    hq_address = entity.get('headquartersAddress', {})

                    # Extract previous names
                    other_names = entity.get('otherNames', [])
                    previous_names = [n.get('name') for n in other_names if n.get('type') == 'PREVIOUS_LEGAL_NAME']

                    # Format address
                    address_lines = legal_address.get('addressLines', [])
                    address_str = ', '.join(address_lines) if address_lines else ''
                    if legal_address.get('city'):
                        address_str += f", {legal_address.get('city')}"
                    if legal_address.get('postalCode'):
                        address_str += f" {legal_address.get('postalCode')}"
                    if legal_address.get('country'):
                        address_str += f", {legal_address.get('country')}"

                    profiles.append({
                        'source': 'gleif',
                        'lei': attrs.get('lei') or record.get('id'),
                        'name': entity.get('legalName', {}).get('name') if isinstance(entity.get('legalName'), dict) else entity.get('legalName'),
                        'previous_names': previous_names,
                        'jurisdiction': entity.get('jurisdiction'),
                        'legal_form': entity.get('legalForm', {}).get('id'),
                        'status': entity.get('status'),
                        'creation_date': entity.get('creationDate'),
                        'registration_status': registration.get('status'),
                        'initial_registration': registration.get('initialRegistrationDate'),
                        'last_update': registration.get('lastUpdateDate'),
                        'address': address_str,
                        'headquarters_address': hq_address,
                        'registered_at': entity.get('registeredAt', {}).get('id'),
                        'registered_as': entity.get('registeredAs'),  # Company number in local registry
                        'bic': attrs.get('bic'),  # BIC/SWIFT code
                        'ocid': attrs.get('ocid'),  # OpenCorporates ID
                        'gleif_url': f"https://search.gleif.org/#/record/{attrs.get('lei') or record.get('id')}"
                    })
                return profiles
        except Exception as e:
            logger.error(f"GLEIF error: {e}")
        return []

    async def _get_gleif_relationships(self, lei: str) -> Dict[str, Any]:
        """
        Get parent/subsidiary relationships for a company from GLEIF.

        Args:
            lei: Legal Entity Identifier (20-char alphanumeric)

        Returns:
            Dict with direct_parent, ultimate_parent, and subsidiaries
        """
        result = {
            'lei': lei,
            'direct_parent': None,
            'ultimate_parent': None,
            'subsidiaries': []
        }

        try:
            # Get direct parent
            url = f"https://api.gleif.org/api/v1/lei-records/{lei}/direct-parent"
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, timeout=10)
            )
            if response.status_code == 200:
                data = response.json().get('data', {})
                if data:
                    attrs = data.get('attributes', {})
                    entity = attrs.get('entity', {})
                    result['direct_parent'] = {
                        'lei': data.get('id'),
                        'name': entity.get('legalName', {}).get('name') if isinstance(entity.get('legalName'), dict) else entity.get('legalName'),
                        'jurisdiction': entity.get('jurisdiction')
                    }

            # Get ultimate parent
            url = f"https://api.gleif.org/api/v1/lei-records/{lei}/ultimate-parent"
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, timeout=10)
            )
            if response.status_code == 200:
                data = response.json().get('data', {})
                if data:
                    attrs = data.get('attributes', {})
                    entity = attrs.get('entity', {})
                    result['ultimate_parent'] = {
                        'lei': data.get('id'),
                        'name': entity.get('legalName', {}).get('name') if isinstance(entity.get('legalName'), dict) else entity.get('legalName'),
                        'jurisdiction': entity.get('jurisdiction')
                    }

            # Get direct children (subsidiaries)
            url = f"https://api.gleif.org/api/v1/lei-records/{lei}/direct-children"
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, timeout=10)
            )
            if response.status_code == 200:
                data = response.json().get('data', [])
                for child in data[:20]:  # Limit to 20 subsidiaries
                    attrs = child.get('attributes', {})
                    entity = attrs.get('entity', {})
                    result['subsidiaries'].append({
                        'lei': child.get('id'),
                        'name': entity.get('legalName', {}).get('name') if isinstance(entity.get('legalName'), dict) else entity.get('legalName'),
                        'jurisdiction': entity.get('jurisdiction'),
                        'status': entity.get('status')
                    })

        except Exception as e:
            logger.error(f"GLEIF relationships error: {e}")

        return result

    async def get_lei(self, company_name: str, jurisdiction: Optional[str] = None) -> Optional[str]:
        """
        Get the LEI (Legal Entity Identifier) for a company.

        Args:
            company_name: Company name to search
            jurisdiction: Optional jurisdiction code

        Returns:
            LEI code if found, None otherwise
        """
        profiles = await self._get_profile_gleif(company_name, jurisdiction)
        if profiles:
            return profiles[0].get('lei')
        return None

    async def get_company_ownership(self, company_name: str, jurisdiction: Optional[str] = None) -> Dict[str, Any]:
        """
        Get complete ownership structure from GLEIF.

        Args:
            company_name: Company name to search
            jurisdiction: Optional jurisdiction code

        Returns:
            Dict with company info, LEI, parent companies, and subsidiaries
        """
        result = {
            'company_name': company_name,
            'jurisdiction': jurisdiction,
            'lei': None,
            'company': None,
            'direct_parent': None,
            'ultimate_parent': None,
            'subsidiaries': [],
            'source': 'gleif'
        }

        # First find the company
        profiles = await self._get_profile_gleif(company_name, jurisdiction)
        if profiles:
            result['company'] = profiles[0]
            result['lei'] = profiles[0].get('lei')

            # Then get relationships
            if result['lei']:
                relationships = await self._get_gleif_relationships(result['lei'])
                result['direct_parent'] = relationships.get('direct_parent')
                result['ultimate_parent'] = relationships.get('ultimate_parent')
                result['subsidiaries'] = relationships.get('subsidiaries', [])

        return result

    def _get_prop(self, props: Dict, key: str) -> Any:
        """Get property value, handling lists"""
        val = props.get(key, [])
        if isinstance(val, list):
            return val[0] if len(val) == 1 else val
        return val

    # =========================================================================
    # OFFICERS
    # =========================================================================

    async def get_officers(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None,
        company_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get officers/directors for a company.

        Args:
            company_name: Company name
            jurisdiction: Optional 2-letter country code
            company_number: Optional company registration number (more precise)

        Returns:
            Dict with officers list
        """
        result = {
            'company_name': company_name,
            'jurisdiction': jurisdiction,
            'sources': [],
            'officers': []
        }

        # If we have a UK company number, go direct to Companies House
        if company_number and (jurisdiction == 'GB' or not jurisdiction):
            ch_officers = await self._get_officers_companies_house_by_number(company_number)
            if ch_officers:
                result['officers'].extend(ch_officers)
                result['sources'].append('companies_house')
                return result

        # Otherwise search by name
        if jurisdiction == 'GB' or not jurisdiction:
            # First find company, then get officers
            ch_companies = await self._get_profile_companies_house(company_name)
            for co in ch_companies[:3]:  # Check top 3 matches
                company_num = co.get('company_number')
                if company_num:
                    officers = await self._get_officers_companies_house_by_number(company_num)
                    for off in officers:
                        off['company_name'] = co.get('name')
                        off['company_number'] = company_num
                    result['officers'].extend(officers)
            if result['officers']:
                result['sources'].append('companies_house')

        # Check OpenCorporates for global coverage
        oc_officers = await self._get_officers_opencorporates(company_name, jurisdiction)
        if oc_officers:
            result['officers'].extend(oc_officers)
            if 'opencorporates' not in result['sources']:
                result['sources'].append('opencorporates')

        return result

    async def _get_officers_companies_house_by_number(self, company_number: str) -> List[Dict]:
        """Get officers from UK Companies House by company number"""
        try:
            url = f"https://api.company-information.service.gov.uk/company/{company_number}/officers"

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=self._get_ch_headers(), timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                officers = []
                for item in data.get('items', []):
                    officers.append({
                        'source': 'companies_house',
                        'name': item.get('name'),
                        'role': item.get('officer_role'),
                        'appointed_on': item.get('appointed_on'),
                        'resigned_on': item.get('resigned_on'),
                        'nationality': item.get('nationality'),
                        'country_of_residence': item.get('country_of_residence'),
                        'occupation': item.get('occupation'),
                        'date_of_birth': item.get('date_of_birth', {})
                    })
                return officers
        except Exception as e:
            logger.error(f"Companies House officers error: {e}")
        return []

    async def _get_officers_opencorporates(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None
    ) -> List[Dict]:
        """Get officers from OpenCorporates"""
        try:
            # First search for company
            url = "https://api.opencorporates.com/v0.4/companies/search"
            params = {
                'q': company_name,
                'api_token': OPENCORPORATES_API_KEY,
                'per_page': 5
            }
            if jurisdiction:
                params['jurisdiction_code'] = jurisdiction.lower()

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, params=params, timeout=15)
            )

            if response.status_code != 200:
                return []

            data = response.json()
            companies = data.get('results', {}).get('companies', [])

            officers = []
            for company in companies[:3]:  # Check top 3
                co = company.get('company', {})
                company_url = co.get('opencorporates_url')
                if not company_url:
                    continue

                # Get officers from company detail endpoint
                # OpenCorporates includes officers in company detail
                detail_url = company_url.replace('https://opencorporates.com', 'https://api.opencorporates.com/v0.4')
                detail_response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: requests.get(f"{detail_url}?api_token={OPENCORPORATES_API_KEY}", timeout=15)
                )

                if detail_response.status_code == 200:
                    detail_data = detail_response.json()
                    company_detail = detail_data.get('results', {}).get('company', {})
                    for officer in company_detail.get('officers', []):
                        off = officer.get('officer', {})
                        officers.append({
                            'source': 'opencorporates',
                            'name': off.get('name'),
                            'role': off.get('position'),
                            'appointed_on': off.get('start_date'),
                            'resigned_on': off.get('end_date'),
                            'company_name': co.get('name'),
                            'company_number': co.get('company_number'),
                            'jurisdiction': co.get('jurisdiction_code')
                        })

            return officers
        except Exception as e:
            logger.error(f"OpenCorporates officers error: {e}")
        return []

    # =========================================================================
    # OFFICER APPOINTMENTS (Reverse - person to companies)
    # =========================================================================

    async def get_officer_appointments(
        self,
        person_name: str,
        jurisdiction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all companies where a person is/was an officer.

        Args:
            person_name: Name of the person
            jurisdiction: Optional 2-letter country code

        Returns:
            Dict with list of appointments
        """
        result = {
            'person_name': person_name,
            'jurisdiction': jurisdiction,
            'sources': [],
            'appointments': []
        }

        # UK Companies House officer search
        if jurisdiction == 'GB' or not jurisdiction:
            ch_appointments = await self._get_appointments_companies_house(person_name)
            if ch_appointments:
                result['appointments'].extend(ch_appointments)
                result['sources'].append('companies_house')

        # OpenCorporates officer search
        oc_appointments = await self._get_appointments_opencorporates(person_name, jurisdiction)
        if oc_appointments:
            result['appointments'].extend(oc_appointments)
            if 'opencorporates' not in result['sources']:
                result['sources'].append('opencorporates')

        return result

    async def _get_appointments_companies_house(self, person_name: str) -> List[Dict]:
        """Search for officer appointments in UK Companies House"""
        try:
            url = "https://api.company-information.service.gov.uk/search/officers"
            params = {'q': person_name, 'items_per_page': 30}

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=self._get_ch_headers(), params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                appointments = []
                for item in data.get('items', []):
                    for appt in item.get('items', [item]):  # Handle nested format
                        appointments.append({
                            'source': 'companies_house',
                            'person_name': item.get('title'),
                            'company_name': appt.get('appointed_to', {}).get('company_name'),
                            'company_number': appt.get('appointed_to', {}).get('company_number'),
                            'role': appt.get('officer_role'),
                            'appointed_on': appt.get('appointed_on'),
                            'resigned_on': appt.get('resigned_on'),
                            'date_of_birth': item.get('date_of_birth', {})
                        })
                return appointments
        except Exception as e:
            logger.error(f"Companies House appointments error: {e}")
        return []

    async def _get_appointments_opencorporates(
        self,
        person_name: str,
        jurisdiction: Optional[str] = None
    ) -> List[Dict]:
        """Search for officer appointments in OpenCorporates"""
        try:
            url = "https://api.opencorporates.com/v0.4/officers/search"
            params = {
                'q': person_name,
                'api_token': OPENCORPORATES_API_KEY,
                'per_page': 30
            }
            if jurisdiction:
                params['jurisdiction_code'] = jurisdiction.lower()

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                appointments = []
                for result in data.get('results', {}).get('officers', []):
                    off = result.get('officer', {})
                    company = off.get('company', {})
                    appointments.append({
                        'source': 'opencorporates',
                        'person_name': off.get('name'),
                        'company_name': company.get('name'),
                        'company_number': company.get('company_number'),
                        'jurisdiction': company.get('jurisdiction_code'),
                        'role': off.get('position'),
                        'appointed_on': off.get('start_date'),
                        'resigned_on': off.get('end_date')
                    })
                return appointments
        except Exception as e:
            logger.error(f"OpenCorporates appointments error: {e}")
        return []

    # =========================================================================
    # BENEFICIAL OWNERS (PSC)
    # =========================================================================

    async def get_beneficial_owners(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None,
        company_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get beneficial owners (Persons with Significant Control).

        Args:
            company_name: Company name
            jurisdiction: Optional 2-letter country code
            company_number: Optional company registration number

        Returns:
            Dict with beneficial owners list
        """
        result = {
            'company_name': company_name,
            'jurisdiction': jurisdiction,
            'sources': [],
            'beneficial_owners': []
        }

        # UK Companies House PSC (most detailed)
        if jurisdiction == 'GB' or not jurisdiction:
            if company_number:
                psc = await self._get_psc_companies_house_by_number(company_number)
                if psc:
                    result['beneficial_owners'].extend(psc)
                    result['sources'].append('companies_house')
            else:
                # Search by name first
                ch_companies = await self._get_profile_companies_house(company_name)
                for co in ch_companies[:3]:
                    company_num = co.get('company_number')
                    if company_num:
                        psc = await self._get_psc_companies_house_by_number(company_num)
                        for p in psc:
                            p['company_name'] = co.get('name')
                            p['company_number'] = company_num
                        result['beneficial_owners'].extend(psc)
                if result['beneficial_owners']:
                    result['sources'].append('companies_house')

        # Check OpenSanctions for sanctioned beneficial owners
        sanctions_bo = await self._get_beneficial_owners_sanctions(company_name)
        if sanctions_bo:
            result['beneficial_owners'].extend(sanctions_bo)
            result['sources'].append('opensanctions')

        return result

    async def _get_psc_companies_house_by_number(self, company_number: str) -> List[Dict]:
        """Get Persons with Significant Control from UK Companies House"""
        try:
            url = f"https://api.company-information.service.gov.uk/company/{company_number}/persons-with-significant-control"

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=self._get_ch_headers(), timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                owners = []
                for item in data.get('items', []):
                    owners.append({
                        'source': 'companies_house',
                        'name': item.get('name'),
                        'kind': item.get('kind'),  # individual, corporate, legal-person
                        'natures_of_control': item.get('natures_of_control', []),
                        'notified_on': item.get('notified_on'),
                        'nationality': item.get('nationality'),
                        'country_of_residence': item.get('country_of_residence'),
                        'date_of_birth': item.get('date_of_birth', {}),
                        'identification': item.get('identification', {})
                    })
                return owners
        except Exception as e:
            logger.error(f"Companies House PSC error: {e}")
        return []

    async def _get_beneficial_owners_sanctions(self, company_name: str) -> List[Dict]:
        """Check OpenSanctions for beneficial owners of sanctioned entities"""
        try:
            url = "https://api.opensanctions.org/search/default"
            headers = {'Authorization': f'Bearer {OPENSANCTIONS_API_KEY}'}
            params = {'q': company_name, 'schema': 'Company', 'limit': 10}

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=headers, params=params, timeout=15)
            )

            if response.status_code == 200:
                data = response.json()
                owners = []
                for result in data.get('results', []):
                    props = result.get('properties', {})
                    # Look for ownership relationships
                    for owner_id in props.get('ownershipOwner', []):
                        owners.append({
                            'source': 'opensanctions',
                            'name': owner_id,
                            'kind': 'sanctioned_owner',
                            'company_sanctioned': result.get('caption'),
                            'datasets': result.get('datasets', [])
                        })
                return owners
        except Exception as e:
            logger.error(f"OpenSanctions beneficial owners error: {e}")
        return []

    # =========================================================================
    # SHAREHOLDERS
    # =========================================================================

    async def get_shareholders(
        self,
        company_name: str,
        jurisdiction: Optional[str] = None,
        company_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get shareholders of a company.

        Note: Direct shareholder data is limited. This combines:
        - PSC data (beneficial owners often are major shareholders)
        - OpenCorporates control relationships

        Args:
            company_name: Company name
            jurisdiction: Optional 2-letter country code
            company_number: Optional company registration number

        Returns:
            Dict with shareholders list
        """
        result = {
            'company_name': company_name,
            'jurisdiction': jurisdiction,
            'sources': [],
            'shareholders': []
        }

        # PSC data often includes major shareholders
        bo_result = await self.get_beneficial_owners(company_name, jurisdiction, company_number)
        for bo in bo_result.get('beneficial_owners', []):
            # Convert PSC to shareholder format
            natures = bo.get('natures_of_control', [])
            ownership_pct = None
            for nature in natures:
                if 'ownership' in nature.lower():
                    # Parse percentage from nature of control
                    if '75%' in nature:
                        ownership_pct = 75.0
                    elif '50%' in nature:
                        ownership_pct = 50.0
                    elif '25%' in nature:
                        ownership_pct = 25.0

            result['shareholders'].append({
                'source': bo.get('source'),
                'name': bo.get('name'),
                'ownership_percentage': ownership_pct,
                'kind': bo.get('kind'),
                'natures_of_control': natures,
                'company_name': bo.get('company_name'),
                'company_number': bo.get('company_number')
            })

        if bo_result.get('sources'):
            result['sources'] = bo_result['sources']

        return result


# Singleton instance
_corporella_instance = None

def get_corporella() -> CorporellaAPI:
    """Get the singleton CorporellaAPI instance"""
    global _corporella_instance
    if _corporella_instance is None:
        _corporella_instance = CorporellaAPI()
    return _corporella_instance

# Convenience alias
corporella = get_corporella()


# =========================================================================
# CONVENIENCE FUNCTIONS (for direct import)
# =========================================================================

async def get_company_profile(company_name: str, jurisdiction: Optional[str] = None) -> Dict:
    """Get company profile"""
    return await get_corporella().get_company_profile(company_name, jurisdiction)

async def get_officers(company_name: str, jurisdiction: Optional[str] = None) -> Dict:
    """Get company officers"""
    return await get_corporella().get_officers(company_name, jurisdiction)

async def get_officer_appointments(person_name: str, jurisdiction: Optional[str] = None) -> Dict:
    """Get officer appointments for a person"""
    return await get_corporella().get_officer_appointments(person_name, jurisdiction)

async def get_beneficial_owners(company_name: str, jurisdiction: Optional[str] = None) -> Dict:
    """Get beneficial owners"""
    return await get_corporella().get_beneficial_owners(company_name, jurisdiction)

async def get_shareholders(company_name: str, jurisdiction: Optional[str] = None) -> Dict:
    """Get shareholders"""
    return await get_corporella().get_shareholders(company_name, jurisdiction)


# =========================================================================
# CLI TEST
# =========================================================================

async def _test():
    """Test the API"""
    api = get_corporella()

    print("=" * 60)
    print("CORPORELLA API TEST")
    print("=" * 60)

    # Test company profile
    print("\n1. Testing get_company_profile('Tesla Inc')...")
    profile = await api.get_company_profile("Tesla Inc")
    print(f"   Sources: {profile.get('sources')}")
    print(f"   Profiles found: {len(profile.get('profiles', []))}")

    # Test officers
    print("\n2. Testing get_officers('Tesco PLC', jurisdiction='GB')...")
    officers = await api.get_officers("Tesco PLC", jurisdiction="GB")
    print(f"   Sources: {officers.get('sources')}")
    print(f"   Officers found: {len(officers.get('officers', []))}")
    if officers.get('officers'):
        print(f"   First officer: {officers['officers'][0].get('name')}")

    # Test officer appointments
    print("\n3. Testing get_officer_appointments('John Smith')...")
    appointments = await api.get_officer_appointments("John Smith")
    print(f"   Sources: {appointments.get('sources')}")
    print(f"   Appointments found: {len(appointments.get('appointments', []))}")

    # Test beneficial owners
    print("\n4. Testing get_beneficial_owners('Barclays PLC', jurisdiction='GB')...")
    owners = await api.get_beneficial_owners("Barclays PLC", jurisdiction="GB")
    print(f"   Sources: {owners.get('sources')}")
    print(f"   Beneficial owners found: {len(owners.get('beneficial_owners', []))}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_test())
