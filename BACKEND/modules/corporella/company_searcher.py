import requests
from typing import List, Dict

ALEPH_BASE_URL = "https://aleph.occrp.org/api/2/entities"

def get_company_directorships(person_id: str, headers: dict) -> List[Dict]:
    """Get all companies where the person is a director"""
    params = {
        'filter:entities': person_id,
        'filter:schemata': ['Directorship', 'Company', 'Organization'],
        'include': ['properties', 'entities', 'schema'],
        'expand': 'true',
        'limit': 50
    }
    
    try:
        response = requests.get(ALEPH_BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        results = response.json().get('results', [])
        
        directorships = []
        for result in results:
            if result.get('schema') in ['Company', 'Organization']:
                # Direct company relationship
                directorships.append({
                    'company': result,
                    'properties': {
                        'role': ['Director']
                    }
                })
            elif result.get('schema') == 'Directorship':
                # Through directorship schema
                props = result.get('properties', {})
                # Get the organization details from the entities array
                org_id = props.get('organization', [None])[0]
                if org_id:
                    for entity in result.get('entities', []):
                        if entity.get('id') == org_id:
                            directorships.append({
                                'company': entity,
                                'properties': props
                            })
                            break
        
        return directorships
        
    except Exception as e:
        print(f"Error fetching directorships: {e}")
        return []

def search_entities(query, limit=100):
    # Define the API endpoint for searching entities
    search_url = ALEPH_BASE_URL

    # Your API key
    api_key = "1c0971afa4804c2aafabb125c79b275e"

    # Set up the request headers
    headers = {
        'Authorization': f'ApiKey {api_key}',
        'Accept': 'application/json'
    }

    offset = 0
    total_results = []

    while True:
        # Set up the query parameters
        params = {
            'q': query,
            'filter:schema': 'Person',
            'limit': limit,
            'offset': offset,
            'include': ['properties', 'relationships', 'entities', 'schema'],
            'expand': 'true'
        }

        try:
            # Make the GET request with timeouts
            response = requests.get(search_url, headers=headers, params=params, timeout=(3.05, 27))
            response.raise_for_status()
            
            search_results = response.json()
            results = search_results.get('results', [])
            
            for person in results:
                print("\n" + "="*80)
                print(f"Person: {person.get('properties', {}).get('name', ['Unknown'])[0]}")
                print("="*80)
                
                # Print basic person properties
                properties = person.get('properties', {})
                for prop, value in properties.items():
                    if isinstance(value, list):
                        print(f"{prop}: {', '.join(str(x) for x in value)}")
                    else:
                        print(f"{prop}: {value}")
                
                # Get and print directorships
                directorships = get_company_directorships(person['id'], headers)
                if directorships:
                    print("\n🏢 Director of:")
                    for directorship in directorships:
                        company = directorship.get('company', {})
                        props = directorship.get('properties', {})
                        
                        # Handle case where company is a list
                        if isinstance(company, list):
                            company = company[0] if company else {}
                        
                        # Get company name, handling both string and list cases
                        company_name = company.get('properties', {}).get('name', [])
                        if isinstance(company_name, list):
                            company_name = company_name[0] if company_name else 'Unknown Company'
                        
                        print(f"\nCompany: {company_name}")
                        
                        # Get role information
                        role = props.get('role', ['Director'])
                        if isinstance(role, str):
                            role = [role]
                        print(f"Role: {role}")
                        
                        # Print dates if available
                        if props.get('startDate'):
                            start_dates = props.get('startDate')
                            if isinstance(start_dates, str):
                                start_dates = [start_dates]
                            print(f"Start Date: {start_dates}")
                        if props.get('endDate'):
                            end_dates = props.get('endDate')
                            if isinstance(end_dates, str):
                                end_dates = [end_dates]
                            print(f"End Date: {end_dates}")

                        # Print additional company details if available
                        if company and isinstance(company, dict):
                            print("\nCompany Details:")
                            for key, value in company.get('properties', {}).items():
                                if value:  # Only print if value exists
                                    print(f"  {key}: {value}")
                
                print("\nSource Information:")
                collection = person.get('collection', {})
                print(f"Collection: {collection.get('label', 'N/A')}")
                print(f"Publisher: {collection.get('publisher', 'N/A')}")
                print(f"Category: {collection.get('category', 'N/A')}")
                print(f"Summary: {collection.get('summary', 'N/A')}")
                
                print("\nMetadata:")
                print(f"ID: {person.get('id', 'N/A')}")
                print(f"Created At: {person.get('created_at', 'N/A')}")
                print(f"Updated At: {person.get('updated_at', 'N/A')}")
                print(f"Score: {person.get('score', 'N/A')}")
            
            if 'next' not in search_results.get('links', {}):
                break
            offset += limit
            
        except requests.exceptions.Timeout:
            print("Request timed out. The server is taking too long to respond.")
            break
        except requests.exceptions.ConnectionError:
            print("Failed to connect to the server. Please check your internet connection.")
            break
        except requests.exceptions.HTTPError as err:
            print(f"HTTP Error occurred: {err}")
            break
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            break

if __name__ == "__main__":
    query = input("Enter your search query: ")
    search_entities(query)
