import requests
import json
from typing import Dict, Any, List
import time

class CompanySearcher:
    def __init__(self):
        self.occrp_api_key = "d130af08b5ab43b3825d99e7c92a1b5a"  # Your OCCRP API key
        self.occrp_base_url = "https://aleph.occrp.org/api/2/"

    def search_occrp(self, company_name: str) -> Dict[str, Any]:
        """Search OCCRP Aleph database for company information."""
        try:
            # Format the search query properly
            params = {
                'q': company_name,
                'filter:schema': 'Company',  # Specify we want company results
                'limit': 10,
                'api_key': self.occrp_api_key
            }
            
            headers = {
                'Authorization': f'ApiKey {self.occrp_api_key}'
            }
            
            # Make the request
            response = requests.get(
                f"{self.occrp_base_url}search",
                params=params,
                headers=headers
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching OCCRP: {str(e)}")
            if hasattr(e.response, 'text'):
                print(f"Response text: {e.response.text}")
            return None

    def format_results(self, results: Dict[str, Any]) -> str:
        """Format search results into readable text."""
        if not results or 'results' not in results:
            return "No results found"
            
        formatted = "\nSearch Results:\n" + "="*50 + "\n"
        
        for item in results.get('results', []):
            formatted += f"\nCompany Name: {item.get('name', 'N/A')}\n"
            formatted += f"Jurisdiction: {item.get('jurisdiction', 'N/A')}\n"
            formatted += f"Registration: {item.get('registration_number', 'N/A')}\n"
            formatted += f"Source: {item.get('source', 'N/A')}\n"
            formatted += "-"*50 + "\n"
            
        return formatted

def main():
    print("\nCompany Search Tool")
    print("==================\n")
    
    searcher = CompanySearcher()
    
    while True:
        query = input("Enter company name to search (or 'exit' to quit):\n> ").strip()
        
        if query.lower() == 'exit':
            break
            
        print(f"\nSearching for: {query}")
        try:
            results = searcher.search_occrp(query)
            if results:
                print(searcher.format_results(results))
            else:
                print("No results found")
                
        except Exception as e:
            print(f"Error in company search execution: {str(e)}")
            
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()
