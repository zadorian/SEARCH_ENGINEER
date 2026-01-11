import requests
from typing import Dict, List, Optional, Union
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path to ensure imports work correctly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class OpenCorporatesAPI:
    """Class to interact with the OpenCorporates API"""
    
    BASE_URL = "https://api.opencorporates.com/v0.4"
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the API client with an optional API key"""
        # Try to load the API key from environment or config
        self.api_key = api_key
        
        # If no API key was provided, try to get it from environment variables
        if not self.api_key:
            self.api_key = os.getenv("OPENCORPORATES_API_KEY")
            
        # If still no API key, continue without it (limited functionality)
        # Note: OpenCorporates allows some searches without API key
                
        # If still no API key, warn but continue (some functionality might be limited)
        if not self.api_key:
            print("Warning: No OpenCorporates API key found. Some functionality may be limited.")
            
        self.session = requests.Session()
        
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make a request to the OpenCorporates API"""
        if params is None:
            params = {}
            
        if self.api_key:
            params['api_token'] = self.api_key
            
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}")
            return {"error": str(e)}
        
    def search_companies(self, query: str, jurisdiction_code: Optional[str] = None, page: int = 1) -> dict:
        """Search for companies by name"""
        params = {
            'q': query,
            'page': page
        }
        
        if jurisdiction_code:
            params['jurisdiction_code'] = jurisdiction_code
            
        return self._make_request('companies/search', params)
        
    def search_officers(self, query: str, jurisdiction_code: Optional[str] = None, page: int = 1) -> dict:
        """Search for officers/directors by name"""
        params = {
            'q': query,
            'page': page
        }
        
        if jurisdiction_code:
            params['jurisdiction_code'] = jurisdiction_code
            
        return self._make_request('officers/search', params)
        
    def get_company_details(self, jurisdiction_code: str, company_number: str) -> dict:
        """Get detailed information about a company"""
        endpoint = f'companies/{jurisdiction_code}/{company_number}'
        return self._make_request(endpoint)
        
    def get_jurisdictions(self) -> dict:
        """Get a list of available jurisdictions"""
        return self._make_request('jurisdictions')
        
    def get_officer_details(self, jurisdiction_code: str, officer_id: str) -> dict:
        """Get detailed information about an officer/director"""
        endpoint = f'officers/{jurisdiction_code}/{officer_id}'
        return self._make_request(endpoint)

def format_company_info(company_data: dict, api: OpenCorporatesAPI = None) -> str:
    """Format company information for display"""
    if not company_data or 'company' not in company_data:
        return "No company data available"
        
    company = company_data['company']
    
    # Basic company information
    name = company.get('name', 'Not specified')
    jurisdiction = company.get('jurisdiction_code', 'Not specified').upper()
    company_number = company.get('company_number', 'Not specified')
    company_type = company.get('company_type', 'Not specified')
    incorporation_date = company.get('incorporation_date', 'Not specified')
    dissolution_date = company.get('dissolution_date', 'Not specified')
    status = company.get('current_status', 'Not specified')
    
    # Address information
    registered_address = "Not specified"
    if 'registered_address' in company:
        address_parts = []
        address = company['registered_address']
        for field in ['street_address', 'locality', 'region', 'postal_code', 'country']:
            if field in address and address[field]:
                address_parts.append(address[field])
        if address_parts:
            registered_address = ", ".join(address_parts)
    
    # Officer information
    officers_text = ""
    if 'officers' in company and company['officers']:
        officers_text = "\nOfficers/Directors:\n"
        for officer in company['officers']:
            officer_info = officer['officer']
            officers_text += f"  • {officer_info.get('name', 'Unknown')} - {officer_info.get('position', 'Unknown')}"
            if 'start_date' in officer_info:
                officers_text += f" (from {officer_info['start_date']})"
            if 'end_date' in officer_info:
                officers_text += f" (until {officer_info['end_date']})"
            officers_text += "\n"
    
    # Format the final output
    output = f"""
Company Name: {name}
Jurisdiction: {jurisdiction}
Company Number: {company_number}
Company Type: {company_type}
Status: {status}
Incorporation Date: {incorporation_date}
Dissolution Date: {dissolution_date if dissolution_date else 'N/A'}
Registered Address: {registered_address}
OpenCorporates URL: {company.get('opencorporates_url', 'Not available')}
{officers_text}
{'=' * 80}
"""
    return output

def main():
    """Interactive command line interface for OpenCorporates API"""
    api = OpenCorporatesAPI()
    
    # Check for command line arguments
    import argparse
    
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='OpenCorporates Search Tool')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--company', type=str, help='Search for company information')
    group.add_argument('--officer', type=str, help='Search for officer/director information')
    parser.add_argument('--jurisdiction', type=str, help='Jurisdiction code (e.g., us_de, gb)')
    parser.add_argument('--source-tag', type=str, help='Source tag for results categorization', default='O')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Get source tag for output
    source_tag = args.source_tag
    
    # Handle legacy positional argument (for backward compatibility)
    if len(sys.argv) > 1 and not any(flag in sys.argv for flag in ['--company', '--officer', '--jurisdiction']):
        # Legacy mode - first argument is assumed to be company name
        company_name = sys.argv[1]
        
        print(f"\nSearching for company: {company_name}")
        
        results = api.search_companies(query=company_name)
        
        if 'results' in results and 'companies' in results['results']:
            companies = results['results']['companies']
            total = results['results']['total_count']
            print(f"\nFound {total} companies matching '{company_name}'")
            print("=" * 80)
            print(f"CORPORATE DATA [{source_tag}]")
            print("=" * 80)
            
            for company in companies:
                print(format_company_info(company, api))
        else:
            print("No results found or error in search")
        
        return
    
    # If specific searches were requested via flags
    if args.company:
        company_name = args.company
        jurisdiction = args.jurisdiction
        
        print(f"\nSearching for company: {company_name}")
        if jurisdiction:
            print(f"Jurisdiction: {jurisdiction.upper()}")
        
        search_params = {'query': company_name}
        if jurisdiction:
            search_params['jurisdiction_code'] = jurisdiction
            
        results = api.search_companies(**search_params)
        
        if 'results' in results and 'companies' in results['results']:
            companies = results['results']['companies']
            total = results['results']['total_count']
            print(f"\nFound {total} companies matching '{company_name}'")
            print("=" * 80)
            print(f"CORPORATE DATA [{source_tag}]")
            print("=" * 80)
            
            for company in companies:
                print(format_company_info(company, api))
        else:
            print("No results found or error in search")
        
        return
        
    if args.officer:
        officer_name = args.officer
        jurisdiction = args.jurisdiction
        
        print(f"\nSearching for officer/director: {officer_name}")
        if jurisdiction:
            print(f"Jurisdiction: {jurisdiction.upper()}")
        
        search_params = {'query': officer_name}
        if jurisdiction:
            search_params['jurisdiction_code'] = jurisdiction
            
        results = api.search_officers(**search_params)
        
        if 'results' in results and 'officers' in results['results']:
            officers = results['results']['officers']
            total = results['results']['total_count']
            print(f"\nFound {total} officers matching '{officer_name}'")
            print("=" * 80)
            print(f"DIRECTORSHIPS [{source_tag}]")
            print("=" * 80)
            
            for officer in officers:
                info = officer['officer']
                company_name = info.get('company', {}).get('name') if info.get('company') else info.get('company_name', 'Not specified')
                print(f"""
Name: {info.get('name', 'Not specified')}
Position: {info.get('position', 'Not specified')}
Company: {company_name}
Company Number: {info.get('company', {}).get('company_number', 'Not specified') if info.get('company') else 'Not specified'}
Jurisdiction: {info.get('jurisdiction_code', 'Not specified').upper()}
Start Date: {info.get('start_date', 'Not specified')}
End Date: {info.get('end_date', 'Not specified')}
{'=' * 80}
                """)
        else:
            print("No officers found or error in search")
        
        return
    
    # If no search flags were provided, run interactive mode
    while True:
        print("\nOpenCorporates Search")
        print("1. Search Companies")
        print("2. Search Officers (Directors/Executives)")
        print("3. Get Company Details")
        print("4. List Jurisdictions")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ")
        
        if choice == '1':
            query = input("Enter company name to search: ")
            page = input("Enter page number (default 1): ") or 1
            results = api.search_companies(query=query, page=int(page))
            
            if 'results' in results and 'companies' in results['results']:
                companies = results['results']['companies']
                total = results['results']['total_count']
                print(f"\nFound {total} companies matching '{query}'")
                print("=" * 80)
                print(f"CORPORATE DATA [{source_tag}]")
                print("=" * 80)
                
                for company in companies:
                    print(format_company_info(company, api))
            else:
                print("No results found or error in search")
            
        elif choice == '2':
            query = input("Enter officer name to search: ")
            jurisdiction = input("Enter jurisdiction code (optional): ") or None
            results = api.search_officers(query=query, jurisdiction_code=jurisdiction)
            
            if 'results' in results and 'officers' in results['results']:
                officers = results['results']['officers']
                total = results['results']['total_count']
                print(f"\nFound {total} officers matching '{query}'")
                print("=" * 80)
                print(f"DIRECTORSHIPS [{source_tag}]")
                print("=" * 80)
                
                for officer in officers:
                    info = officer['officer']
                    company_name = info.get('company', {}).get('name') if info.get('company') else info.get('company_name', 'Not specified')
                    print(f"""
Name: {info.get('name', 'Not specified')}
Position: {info.get('position', 'Not specified')}
Company: {company_name}
Company Number: {info.get('company', {}).get('company_number', 'Not specified') if info.get('company') else 'Not specified'}
Jurisdiction: {info.get('jurisdiction_code', 'Not specified').upper()}
Start Date: {info.get('start_date', 'Not specified')}
End Date: {info.get('end_date', 'Not specified')}
{'=' * 80}
                    """)
            else:
                print("No results found or error in search")
            
        elif choice == '3':
            jurisdiction = input("Enter jurisdiction code (e.g., us_de): ")
            company_number = input("Enter company number: ")
            results = api.get_company_details(jurisdiction, company_number)
            
            if 'results' in results and 'company' in results['results']:
                company = results['results']
                print("=" * 80)
                print(f"CORPORATE DATA [{source_tag}]")
                print("=" * 80)
                print(format_company_info({'company': company['company']}, api))
            else:
                print("Company not found or error in search")
            
        elif choice == '4':
            results = api.get_jurisdictions()
            if 'results' in results and 'jurisdictions' in results['results']:
                jurisdictions = results['results']['jurisdictions']
                print("\nAvailable Jurisdictions:")
                print("=" * 80)
                for jurisdiction in jurisdictions:
                    info = jurisdiction['jurisdiction']
                    print(f"""
Code: {info['code']}
Name: {info['name']}
Type: {info.get('type', 'Not specified')}
{'=' * 80}
                    """)
            else:
                print("Error retrieving jurisdictions")
            
        elif choice == '5':
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")
        
        input("\nPress Enter to continue...") 

if __name__ == "__main__":
    import sys
    
    # If no command line arguments are provided, run in interactive mode
    if len(sys.argv) == 1:
        main()  # Run interactive mode
    else:
        # Process command line arguments via argparse if arguments are provided
        main()  # This will handle command line arguments through argparse 