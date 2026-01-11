import requests
from typing import Dict, List, Optional
import json
from dataclasses import dataclass
from datetime import datetime
import difflib
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CompanyMatch:
    name: str
    registration_number: str
    jurisdiction: str
    address: str
    incorporation_date: Optional[str]
    source: str
    raw_data: Dict
    confidence_score: float = 1.0

class UnifiedCompanySearch:
    def __init__(self, opencorporates_api_key: str, occrp_api_key: str):
        self.opencorporates_api_key = opencorporates_api_key
        self.occrp_api_key = occrp_api_key
        self.opencorporates_base_url = "https://api.opencorporates.com/v0.4"
        self.occrp_base_url = "https://data.occrp.org/api/2/entities"

    def search_opencorporates(self, query: str, jurisdiction: str = None) -> List[CompanyMatch]:
        """
        Search OpenCorporates API for companies with detailed debugging
        """
        try:
            params = {
                'q': query,
                'api_token': self.opencorporates_api_key,
                'per_page': 100
            }
            
            if jurisdiction:
                params['jurisdiction_code'] = jurisdiction

            logger.info(f"Searching OpenCorporates for: {query}")
            logger.info(f"Request URL: {self.opencorporates_base_url}/companies/search")
            logger.info(f"Parameters: {params}")

            response = requests.get(
                f"{self.opencorporates_base_url}/companies/search",
                params=params
            )
            logger.info(f"OpenCorporates Status Code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"OpenCorporates Error: {response.text}")
                return []

            data = response.json()
            
            # Log the raw response for debugging
            logger.debug(f"OpenCorporates Raw Response: {json.dumps(data, indent=2)}")

            total_results = data.get('results', {}).get('total_count', 0)
            logger.info(f"OpenCorporates found {total_results} results")

            matches = []
            for company in data.get('results', {}).get('companies', []):
                company_data = company.get('company', {})
                
                match = CompanyMatch(
                    name=company_data.get('name', ''),
                    registration_number=company_data.get('company_number', ''),
                    jurisdiction=company_data.get('jurisdiction_code', ''),
                    address=company_data.get('registered_address_in_full', ''),
                    incorporation_date=company_data.get('incorporation_date'),
                    source='OpenCorporates',
                    raw_data=company_data
                )
                matches.append(match)
                logger.info(f"Found OpenCorporates match: {match.name}")

            return matches

        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching OpenCorporates: {str(e)}")
            return []

    def search_occrp(self, query: str) -> List[CompanyMatch]:
        """
        Search OCCRP API for companies with detailed debugging
        """
        try:
            headers = {
                'Authorization': f'ApiKey {self.occrp_api_key}'
            }
            
            params = {
                'q': query,
                'filter:schema': 'Company',
                'limit': 100
            }
            
            logger.info(f"Searching OCCRP for: {query}")
            logger.info(f"Request URL: {self.occrp_base_url}")
            logger.info(f"Parameters: {params}")

            response = requests.get(
                self.occrp_base_url,
                headers=headers,
                params=params
            )
            
            logger.info(f"OCCRP Status Code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"OCCRP Error: {response.text}")
                return []

            data = response.json()
            
            # Log the raw response for debugging
            logger.debug(f"OCCRP Raw Response: {json.dumps(data, indent=2)}")

            total_results = len(data.get('results', []))
            logger.info(f"OCCRP found {total_results} results")

            matches = []
            for result in data.get('results', []):
                properties = result.get('properties', {})
                
                # Handle both list and single value formats
                def get_property(prop_name):
                    value = properties.get(prop_name, '')
                    if isinstance(value, list):
                        return value[0] if value else ''
                    return value

                match = CompanyMatch(
                    name=get_property('name'),
                    registration_number=get_property('registrationNumber'),
                    jurisdiction=get_property('jurisdiction'),
                    address=get_property('address'),
                    incorporation_date=get_property('incorporationDate'),
                    source='OCCRP',
                    raw_data=result
                )
                matches.append(match)
                logger.info(f"Found OCCRP match: {match.name}")

            return matches

        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching OCCRP: {str(e)}")
            return []

    def calculate_similarity_score(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using difflib
        """
        if not str1 or not str2:
            return 0.0
        return difflib.SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def merge_results(self, oc_results: List[CompanyMatch], occrp_results: List[CompanyMatch]) -> List[Dict]:
        """
        Merge results from both sources, removing duplicates and grouping similar entries
        """
        merged = []
        processed = set()

        # Process all results
        all_results = oc_results + occrp_results
        
        for company in all_results:
            if company.name in processed:
                continue
                
            group = {
                'primary_match': company,
                'similar_matches': [],
                'confidence_score': 1.0
            }
            
            # Find similar companies
            for other in all_results:
                if other.name == company.name:
                    continue
                    
                similarity = self.calculate_similarity_score(company.name, other.name)
                if similarity > 0.8:  # 80% similarity threshold
                    other.confidence_score = similarity
                    group['similar_matches'].append(other)
                    processed.add(other.name)
            
            merged.append(group)
            processed.add(company.name)

        return merged

    def search(self, query: str, jurisdiction: str = None) -> Dict:
        """
        Perform unified search with additional search strategies
        """
        logger.info(f"Starting unified search for: {query}")
        
        # Try exact name search
        logger.info("Attempting exact name search...")
        oc_results = self.search_opencorporates(query, jurisdiction)
        occrp_results = self.search_occrp(query)

        # If no results, try with wildcards
        if not oc_results and not occrp_results:
            logger.info("No results found with exact name, trying with wildcards...")
            oc_results = self.search_opencorporates(f"{query}*", jurisdiction)
            occrp_results = self.search_occrp(f"{query}*")

        # If still no results, try tokenized search
        if not oc_results and not occrp_results:
            logger.info("No results found with wildcards, trying tokenized search...")
            tokens = query.split()
            if len(tokens) > 1:
                for i in range(len(tokens)):
                    partial_query = " ".join(tokens[i:])
                    logger.info(f"Trying partial query: {partial_query}")
                    oc_partial = self.search_opencorporates(partial_query, jurisdiction)
                    occrp_partial = self.search_occrp(partial_query)
                    
                    oc_results.extend(oc_partial)
                    occrp_results.extend(occrp_partial)

        # Merge results
        merged_results = self.merge_results(oc_results, occrp_results)

        results = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'total_results': len(merged_results),
            'results': merged_results,
            'sources': {
                'opencorporates_count': len(oc_results),
                'occrp_count': len(occrp_results)
            },
            'debug_info': {
                'jurisdiction_used': jurisdiction,
                'search_strategies_tried': [
                    'exact_name',
                    'wildcard_search',
                    'tokenized_search'
                ]
            }
        }

        logger.info(f"Search completed. Found {len(merged_results)} merged results")
        return results

def print_results(results: Dict):
    """
    Pretty print the search results
    """
    print(f"\nSearch Query: {results['query']}")
    print(f"Search Time: {results['timestamp']}")
    print(f"Total Results: {results['total_results']}")
    print("\n=== Search Results ===\n")

    for i, group in enumerate(results['results'], 1):
        print(f"\nResult Group {i}:")
        print("\nPrimary Match:")
        primary = group['primary_match']
        print(f"  Source: {primary.source}")
        print(f"  Name: {primary.name}")
        print(f"  Registration: {primary.registration_number}")
        print(f"  Jurisdiction: {primary.jurisdiction}")
        print(f"  Address: {primary.address}")
        print(f"  Incorporation Date: {primary.incorporation_date}")
        print("  " + "-"*40)

        if group['similar_matches']:
            print("\n  Similar Matches:")
            for match in group['similar_matches']:
                print(f"    Source: {match.source}")
                print(f"    Name: {match.name}")
                print(f"    Registration: {match.registration_number}")
                print(f"    Jurisdiction: {match.jurisdiction}")
                print(f"    Address: {match.address}")
                print(f"    Incorporation Date: {match.incorporation_date}")
                print(f"    Confidence Score: {match.confidence_score:.2f}")
                print("    " + "-"*40)

    print("\n=== Source Statistics ===")
    print(f"OpenCorporates Results: {results['sources']['opencorporates_count']}")
    print(f"OCCRP Results: {results['sources']['occrp_count']}")

def test_search(searcher, company_name: str):
    """
    Test search with multiple strategies
    """
    print(f"\nTesting search for: {company_name}")
    
    # Try different variations
    variations = [
        company_name,
        company_name.upper(),
        company_name.lower(),
        # Remove common company suffixes
        company_name.replace(" LIMITED", "").replace(" LTD", ""),
        # Add wildcards
        f"{company_name}*",
        # Try with quotes
        f'"{company_name}"'
    ]

    # Try different jurisdictions if needed
    jurisdictions = [None, 'gb', 'us', 'de']  # Add more as needed

    for variation in variations:
        for jurisdiction in jurisdictions:
            print(f"\nTrying variation: '{variation}' with jurisdiction: {jurisdiction}")
            results = searcher.search(variation, jurisdiction)
            if results['total_results'] > 0:
                print(f"Found {results['total_results']} results!")
                print_results(results)
                return
            else:
                print("No results found for this variation")

def save_to_json(results: Dict, company_name: str):
    """
    Save search results to a JSON file with a consistent name
    """
    # Use a fixed filename
    filename = "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/#R&D/Script_Library/Python Library/Woosh/latest_company_search.json"
    
    # Convert CompanyMatch objects to dictionaries
    json_results = results.copy()
    for group in json_results['results']:
        group['primary_match'] = vars(group['primary_match'])
        group['similar_matches'] = [vars(match) for match in group['similar_matches']]
    
    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(json_results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

# Example usage
if __name__ == "__main__":
    # Get company name from command line arguments
    if len(sys.argv) > 1:
        company_name = " ".join(sys.argv[1:])  # Join all arguments after script name
    else:
        company_name = "Sastre Consulting"  # Default fallback
        
    print(f"\nSearching for: {company_name}")
    
    searcher = UnifiedCompanySearch(
        opencorporates_api_key="UvjlNXuBiIeNymveADRR",
        occrp_api_key="1c0971afa4804c2aafabb125c79b275e"
    )
    
    # Perform the search
    results = searcher.search(company_name)
    
    # Print results to console
    print_results(results)
    
    # Save results to JSON file
    save_to_json(results, company_name)
