"""
Companies House API Integration for WIKIMAN-PRO
Provides UK company registry search with PSC (beneficial ownership) data
"""

import requests
import os
import base64
from typing import Optional, Dict, List, Any

class CompaniesHouseAPI:
    """
    UK Companies House API client
    Searches official UK company registry and retrieves:
    - Company details
    - Officers (directors, secretaries)
    - PSC data (Persons with Significant Control / beneficial owners)
    - Filing history
    """
    
    def __init__(self, ch_api_key: str = None):
        """
        Initialize with Companies House API key
        
        Args:
            ch_api_key: Companies House API key (or from CH_API_KEY env var)
        """
        self.ch_api_key = (
            ch_api_key
            or os.environ.get('COMPANIES_HOUSE_API_KEY', '')
            or os.environ.get('CH_API_KEY', '')
        )
        self.base_url = "https://api.company-information.service.gov.uk"
        self.session = requests.Session()
        
        if self.ch_api_key:
            # Properly encode the API key for Basic Auth
            auth = base64.b64encode(f"{self.ch_api_key}:".encode('utf-8')).decode('utf-8')
            self.session.headers.update({'Authorization': f'Basic {auth}'})
    
    def test_api_key(self) -> bool:
        """Test if the API key is valid"""
        if not self.ch_api_key:
            return False
            
        url = f"{self.base_url}/search/companies"
        params = {'q': 'test'}
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False
    
    def search_company(self, company_name: str, items_per_page: int = 20) -> Optional[List[Dict]]:
        """
        Search for a company by name
        
        Args:
            company_name: Company name to search
            items_per_page: Results per page (default 20)
            
        Returns:
            List of company matches or None
        """
        if not self.ch_api_key:
            return None
            
        try:
            url = f"{self.base_url}/search/companies"
            params = {
                'q': company_name,
                'items_per_page': items_per_page
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            search_results = response.json()
            
            if search_results.get('items'):
                return search_results['items']
                
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"Companies House search error: {e}")
            return None
    
    def get_company_details(self, company_number: str) -> Optional[Dict]:
        """
        Get detailed information about a specific company
        
        Args:
            company_number: UK company registration number
            
        Returns:
            Company details dict or None
        """
        if not self.ch_api_key:
            return None
            
        endpoint = f"{self.base_url}/company/{company_number}"
        try:
            response = self.session.get(endpoint, timeout=10)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Companies House details error: {e}")
        
        return None
    
    def get_company_officers(self, company_number: str) -> List[Dict]:
        """
        Get officers (directors, secretaries) for a company
        
        Args:
            company_number: UK company registration number
            
        Returns:
            List of officers
        """
        if not self.ch_api_key:
            return []
            
        endpoint = f"{self.base_url}/company/{company_number}/officers"
        try:
            response = self.session.get(endpoint, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Companies House officers error: {e}")
        
        return []
    
    def get_psc_data(self, company_number: str) -> List[Dict]:
        """
        Get PSC (Persons with Significant Control) data - beneficial owners
        
        Args:
            company_number: UK company registration number
            
        Returns:
            List of PSCs (beneficial owners)
        """
        if not self.ch_api_key:
            return []
            
        endpoint = f"{self.base_url}/company/{company_number}/persons-with-significant-control"
        try:
            response = self.session.get(endpoint, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Companies House PSC error: {e}")
        
        return []
    
    def get_filing_history(self, company_number: str, category: str = None,
                          items_per_page: int = 25) -> Optional[Dict]:
        """
        Get filing history for a company

        Args:
            company_number: UK company registration number
            category: Optional filing category filter
            items_per_page: Results per page

        Returns:
            Filing history dict or None
        """
        if not self.ch_api_key:
            return None

        try:
            url = f"{self.base_url}/company/{company_number}/filing-history"
            params = {
                'items_per_page': items_per_page,
                'start_index': 0
            }
            if category:
                params['category'] = category

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Companies House filing history error: {e}")
            return None

    def search_officers(self, officer_name: str) -> Optional[Dict]:
        """
        Search for officers by name

        Args:
            officer_name: Name of the officer to search for

        Returns:
            Search results with officer details
        """
        if not self.ch_api_key:
            return None

        try:
            url = f"{self.base_url}/search/officers"
            params = {'q': officer_name}

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Companies House officer search error: {e}")
            return None

    def get_officer_appointments(self, officer_id: str, items_per_page: int = 50) -> Optional[Dict]:
        """
        Get all appointments for a specific officer

        Args:
            officer_id: The officer ID from Companies House
            items_per_page: Number of items per page

        Returns:
            List of appointments with company details
        """
        if not self.ch_api_key:
            return None

        try:
            url = f"{self.base_url}/officers/{officer_id}/appointments"
            params = {'items_per_page': items_per_page}

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Companies House officer appointments error: {e}")
            return None


def search_uk_company(company_name: str, include_psc: bool = True, 
                     include_officers: bool = True) -> Dict[str, Any]:
    """
    Convenience function to search UK company with all data
    
    Args:
        company_name: Company name to search
        include_psc: Include PSC (beneficial ownership) data
        include_officers: Include officers data
        
    Returns:
        Dict with search results and enriched data
    """
    ch = CompaniesHouseAPI()
    
    if not ch.ch_api_key:
        return {
            'ok': False,
            'error': 'Companies House API key not configured (set COMPANIES_HOUSE_API_KEY env var)'
        }
    
    # Search for company
    companies = ch.search_company(company_name)
    
    if not companies:
        return {
            'ok': False,
            'error': 'No companies found'
        }
    
    # Enrich first result with full data
    top_company = companies[0]
    company_number = top_company.get('company_number')
    
    result = {
        'ok': True,
        'search_results': companies,
        'top_match': top_company
    }
    
    if company_number:
        # Get detailed data
        result['company_details'] = ch.get_company_details(company_number)
        
        if include_officers:
            result['officers'] = ch.get_company_officers(company_number)
        
        if include_psc:
            result['psc'] = ch.get_psc_data(company_number)
    
    return result


if __name__ == "__main__":
    # Test the Companies House API
    print("Testing Companies House API...")
    
    ch = CompaniesHouseAPI()
    
    if ch.test_api_key():
        print("✅ API key valid")
        
        # Test search
        results = search_uk_company("BP plc", include_psc=True, include_officers=True)
        
        if results.get('ok'):
            print(f"✅ Found {len(results['search_results'])} companies")
            print(f"   Top match: {results['top_match'].get('title')}")
            print(f"   Officers: {len(results.get('officers', []))}")
            print(f"   PSCs: {len(results.get('psc', []))}")
        else:
            print(f"❌ Search failed: {results.get('error')}")
    else:
        print("❌ API key invalid or not set")
        print("   Set COMPANIES_HOUSE_API_KEY environment variable (CH_API_KEY alias also supported)")
