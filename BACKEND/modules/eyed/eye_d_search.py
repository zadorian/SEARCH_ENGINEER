#!/usr/bin/env python3
"""
EYE-D OSINT Search Integration for Search_Engineer
Handles email, phone, LinkedIn, username, and WHOIS searches
"""

import sys
import os
import json
import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import EYE-D modules
sys.path.insert(0, str(Path(__file__).parent.parent / "EYE-D"))

# Import LINKLATER for C1Bridge
sys.path.insert(0, str(Path(__file__).parent.parent / "LINKLATER"))

try:
    from unified_osint import UnifiedSearcher
    EYE_D_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import EYE-D unified_osint module: {e}")
    EYE_D_AVAILABLE = False

# Import C1 Bridge
try:
    from c1_bridge import C1Bridge
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import C1Bridge: {e}")
    BRIDGE_AVAILABLE = False


class EyeDSearchHandler:
    """Handles EYE-D OSINT searches and stores results"""
    
    def __init__(self, project_id: str = "eyed"):
        self.osint_client = UnifiedSearcher() if EYE_D_AVAILABLE else None
        self.project_id = project_id
        self.bridge = C1Bridge(project_id=project_id) if BRIDGE_AVAILABLE else None
        
    def extract_query_value(self, query: str, search_type: str) -> str:
        """Extract the actual value from the query (remove ? and other markers)"""
        if search_type == 'whois':
            # Extract domain from whois!:domain.com pattern
            match = re.match(r'^whois!\s*:\s*(.+)$', query)
            if match:
                return match.group(1).strip()
            return query
        else:
            # Remove trailing ? for other types
            return query.rstrip('?').strip()
    
    async def search_email(self, email: str) -> Dict[str, Any]:
        """Search for email address across all EYE-D sources"""
        print(f"📧 Searching for email: {email}")
        
        results = {
            'query': email,
            'query_type': 'EYE-D',
            'subtype': 'email',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results
        
        try:
            # Use UnifiedSearcher's search method
            osint_results = self.osint_client.search(email)
            
            # Process results - UnifiedSearcher returns a dict with various sources
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    result_entry = {
                        'source': source,
                        'data': data,
                        'entity_type': 'email',
                        'entity_value': email
                    }
                    results['results'].append(result_entry)
                    
                    # Extract additional entities found
                    entities = self._extract_entities_from_data(data)
                    results['entities'].extend(entities)
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for email {email}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching email: {e}")
        
        return results
    
    async def search_phone(self, phone: str) -> Dict[str, Any]:
        """Search for phone number across all EYE-D sources"""
        print(f"📱 Searching for phone: {phone}")
        
        results = {
            'query': phone,
            'query_type': 'EYE-D',
            'subtype': 'phone',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results
        
        try:
            # Normalize phone number (basic normalization)
            normalized_phone = re.sub(r'[^\d+]', '', phone)
            
            # Use UnifiedSearcher's search method
            osint_results = self.osint_client.search(normalized_phone)
            
            # Process results
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    result_entry = {
                        'source': source,
                        'data': data,
                        'entity_type': 'phone',
                        'entity_value': phone
                    }
                    results['results'].append(result_entry)
                    
                    # Extract additional entities
                    entities = self._extract_entities_from_data(data)
                    results['entities'].extend(entities)
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for phone {phone}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching phone: {e}")
        
        return results
    
    async def search_linkedin(self, linkedin_url: str) -> Dict[str, Any]:
        """Search and enrich LinkedIn profile (includes company database search)"""
        print(f"💼 Searching LinkedIn profile: {linkedin_url}")

        results = {
            'query': linkedin_url,
            'query_type': 'EYE-D',
            'subtype': 'linkedin',
            'results': [],
            'entities': [],
            'company_data': None,  # NEW: LinkedIn company dataset match
            'timestamp': datetime.now().isoformat()
        }

        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results

        try:
            # Use UnifiedSearcher's search method with the full LinkedIn URL
            osint_results = self.osint_client.search(linkedin_url)

            # Process OSINT results
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    result_entry = {
                        'source': source,
                        'data': data,
                        'entity_type': 'linkedin',
                        'entity_value': linkedin_url
                    }
                    results['results'].append(result_entry)

                    # Extract entities
                    entities = self._extract_entities_from_data(data)
                    results['entities'].extend(entities)

            # NEW: Search LinkedIn companies dataset if this is a company LinkedIn URL
            if '/company/' in linkedin_url:
                try:
                    company_data = await self._search_linkedin_companies_index(linkedin_url)
                    if company_data:
                        results['company_data'] = company_data
                        print(f"✅ Found company data from LinkedIn dataset: {company_data.get('company_name')}")

                        # Add as enrichment to results
                        results['results'].append({
                            'source': 'linkedin_company_database',
                            'data': company_data,
                            'entity_type': 'company',
                            'entity_value': company_data.get('company_name')
                        })
                except Exception as e:
                    print(f"⚠️  LinkedIn company dataset search failed: {e}")

            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for LinkedIn profile")

        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching LinkedIn: {e}")

        return results
    
    async def search_whois(self, domain: str) -> Dict[str, Any]:
        """Search WHOIS information for domain"""
        print(f"🌐 Searching WHOIS for domain: {domain}")
        
        results = {
            'query': domain,
            'query_type': 'EYE-D',
            'subtype': 'whois',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results
        
        try:
            # Use UnifiedSearcher's search method for domain
            osint_results = self.osint_client.search(domain)
            
            # Process results - look for whois data in the results
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    # Store all results but specially handle whois data
                    if 'whois' in source.lower() or source == 'whoisxmlapi_history':
                        result_entry = {
                            'source': source,
                            'data': data,
                            'entity_type': 'domain',
                            'entity_value': domain
                        }
                        results['results'].append(result_entry)
                        
                        # Extract entities from WHOIS data
                        entities = self._extract_entities_from_whois(data) if 'whois' in source.lower() else self._extract_entities_from_data(data)
                        results['entities'].extend(entities)
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for domain {domain}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching WHOIS: {e}")
        
        return results
    
    async def search_username(self, username: str) -> Dict[str, Any]:
        """Search for username across breach databases"""
        print(f"👤 Searching for username: {username}")
        
        results = {
            'query': username,
            'query_type': 'EYE-D',
            'subtype': 'username',
            'results': [],
            'entities': [],
            'timestamp': datetime.now().isoformat()
        }
        
        if not self.osint_client:
            results['error'] = "EYE-D module not available"
            return results
        
        try:
            # Use UnifiedSearcher's search method
            osint_results = self.osint_client.search(username)
            
            # Process results
            for source, data in osint_results.items():
                if data and not (isinstance(data, dict) and data.get('error')):
                    # Focus on breach-related sources
                    if any(breach_src in source.lower() for breach_src in ['dehashed', 'osint', 'breach']):
                        result_entry = {
                            'source': source,
                            'data': data,
                            'entity_type': 'username',
                            'entity_value': username
                        }
                        results['results'].append(result_entry)
                        
                        # Extract entities
                        entities = self._extract_entities_from_data(data)
                        results['entities'].extend(entities)
            
            results['total_results'] = len(results['results'])
            print(f"✅ Found {results['total_results']} results for username {username}")
            
        except Exception as e:
            results['error'] = str(e)
            print(f"❌ Error searching username: {e}")
        
        return results
    
    def _extract_entities_from_data(self, data: Any) -> List[Dict[str, str]]:
        """Extract entities using the existing entity extraction system for consistency"""
        entities = []
        
        # Convert data to text for the existing entity extractor
        text_content = str(data)
        
        try:
            # Use the existing entity extraction system
            from domain_search.entity_extractor import EntityExtractor
            
            # Initialize with a mock websocket since we don't need real-time updates here
            class MockWebSocket:
                async def send_json(self, data):
                    pass
            
            extractor = EntityExtractor(MockWebSocket(), self.storage.db_path if self.storage else "search_results.db")
            
            # Extract all entity types
            import asyncio
            from contextlib import asynccontextmanager
            
            @asynccontextmanager
            async def null_context():
                yield
            
            # Run the entity extraction asynchronously
            loop = asyncio.get_event_loop() if asyncio._get_running_loop() else asyncio.new_event_loop()
            if not loop.is_running():
                asyncio.set_event_loop(loop)
            
            # Use the AI-powered entity extraction
            entity_types = ["PERSON", "ORGANIZATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION"]
            prompt = extractor._build_extraction_prompt(entity_types, text_content)
            
            # For now, fallback to simple pattern matching to avoid async complexity
            # This will be enhanced later with full AI integration
            entities.extend(self._fallback_entity_extraction(data))
            
        except Exception as e:
            print(f"Error using existing entity extractor: {e}")
            # Fallback to original extraction
            entities.extend(self._fallback_entity_extraction(data))
        
        return entities
    
    def _fallback_entity_extraction(self, data: Any) -> List[Dict[str, str]]:
        """Fallback entity extraction for when the AI system is not available"""
        entities = []
        
        if isinstance(data, dict):
            # Look for common fields
            if 'email' in data:
                entities.append({'type': 'EMAIL_ADDRESS', 'value': data['email']})
            if 'emails' in data and isinstance(data['emails'], list):
                for email in data['emails']:
                    entities.append({'type': 'EMAIL_ADDRESS', 'value': email})
            
            if 'phone' in data:
                entities.append({'type': 'PHONE_NUMBER', 'value': data['phone']})
            if 'phones' in data and isinstance(data['phones'], list):
                for phone in data['phones']:
                    entities.append({'type': 'PHONE_NUMBER', 'value': phone})
            
            if 'username' in data:
                entities.append({'type': 'PERSON', 'value': data['username']})
            if 'usernames' in data and isinstance(data['usernames'], list):
                for username in data['usernames']:
                    entities.append({'type': 'PERSON', 'value': username})
            
            # Look for organization/company names
            if 'company' in data:
                entities.append({'type': 'ORGANIZATION', 'value': data['company']})
            if 'organization' in data:
                entities.append({'type': 'ORGANIZATION', 'value': data['organization']})
            
            # Recursively check nested data
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    entities.extend(self._fallback_entity_extraction(value))
        
        elif isinstance(data, list):
            for item in data:
                entities.extend(self._fallback_entity_extraction(item))
        
        return entities
    
    def _extract_entities_from_whois(self, whois_data: Dict) -> List[Dict[str, str]]:
        """Extract entities from WHOIS data"""
        entities = []
        
        # Extract registrant information
        if 'registrant' in whois_data:
            reg = whois_data['registrant']
            if 'email' in reg:
                entities.append({'type': 'email', 'value': reg['email']})
            if 'phone' in reg:
                entities.append({'type': 'phone', 'value': reg['phone']})
            if 'name' in reg:
                entities.append({'type': 'person', 'value': reg['name']})
            if 'organization' in reg:
                entities.append({'type': 'organization', 'value': reg['organization']})
        
        # Extract admin/tech contact info
        for contact_type in ['admin', 'tech', 'billing']:
            if contact_type in whois_data:
                contact = whois_data[contact_type]
                if 'email' in contact:
                    entities.append({'type': 'email', 'value': contact['email']})
                if 'phone' in contact:
                    entities.append({'type': 'phone', 'value': contact['phone']})
        
        return entities

    async def _search_linkedin_companies_index(self, linkedin_url: str) -> Optional[Dict[str, Any]]:
        """
        Search the LinkedIn companies dataset (3M+ records)
        Returns company data if found: company_name, domain, website_url, industry
        """
        import os
        import aiohttp

        ES_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
        LINKEDIN_COMPANIES_INDEX = 'linkedin_companies'

        # Extract LinkedIn company ID from URL
        # https://www.linkedin.com/company/microsoft/ → microsoft
        linkedin_id = None
        if '/company/' in linkedin_url:
            parts = linkedin_url.split('/company/')
            if len(parts) > 1:
                linkedin_id = parts[1].strip('/').split('?')[0].split('#')[0]

        if not linkedin_id:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                query = {
                    "query": {
                        "bool": {
                            "should": [
                                # Exact match on LinkedIn URL
                                {
                                    "term": {
                                        "linkedin_url.keyword": linkedin_url
                                    }
                                },
                                # Match on extracted LinkedIn ID
                                {
                                    "wildcard": {
                                        "linkedin_url.keyword": f"*linkedin.com/company/{linkedin_id}*"
                                    }
                                },
                                # Fuzzy match on LinkedIn ID
                                {
                                    "match": {
                                        "linkedin_company_id": {
                                            "query": linkedin_id,
                                            "fuzziness": "AUTO"
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 1,
                    "_source": ["company_name", "domain", "linkedin_url", "website_url", "industry", "linkedin_company_id"]
                }

                async with session.post(
                    f"{ES_URL}/{LINKEDIN_COMPANIES_INDEX}/_search",
                    json=query,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('hits', {}).get('hits'):
                            hit = result['hits']['hits'][0]
                            return hit['_source']
                    elif response.status == 404:
                        # Index doesn't exist yet
                        print(f"⚠️  LinkedIn companies index not found. Run linkedin_company_importer.py to create it.")
                    else:
                        print(f"⚠️  LinkedIn companies search returned status {response.status}")

                    return None

        except Exception as e:
            print(f"❌ Error searching LinkedIn companies index: {e}")
            return None

    def store_results(self, results: Dict[str, Any]) -> None:
        """Store results using C1Bridge to Cymonides-1"""
        if not self.bridge:
            print("⚠️ C1Bridge not available - results not persisted")
            return
        
        try:
            print(f"💾 Indexing results to Cymonides-1 (Project: {self.project_id})...")
            stats = self.bridge.index_eyed_results(results)
            print(f"✅ Indexed {stats.get('total_nodes', 0)} nodes (Entities: {stats.get('total_nodes', 0)})")
            
        except Exception as e:
            print(f"❌ Error storing results: {e}")
            import traceback
            traceback.print_exc()
    
    def display_results(self, results: Dict[str, Any]) -> None:
        """Display results in a formatted way"""
        print("\n" + "="*60)
        print(f"🔍 EYE-D OSINT Search Results")
        print(f"📝 Query: {results['query']}")
        print(f"🎯 Type: {results['subtype']}")
        print(f"⏰ Timestamp: {results['timestamp']}")
        print("="*60 + "\n")
        
        if results.get('error'):
            print(f"❌ Error: {results['error']}")
            return
        
        # Display main results
        print(f"📊 Found {results.get('total_results', 0)} results\n")
        
        for i, result in enumerate(results.get('results', []), 1):
            print(f"{i}. Source: {result['source']}")
            print(f"   Type: {result['entity_type']}")
            print(f"   Value: {result['entity_value']}")
            
            # Display key data points
            data = result.get('data', {})
            if isinstance(data, dict):
                # Show first few key-value pairs
                for j, (key, value) in enumerate(data.items()):
                    if j >= 5:  # Limit display
                        print(f"   ... and {len(data) - 5} more fields")
                        break
                    print(f"   {key}: {str(value)[:100]}")
            print()
        
        # Display extracted entities
        if results.get('entities'):
            print(f"\n📌 Extracted Entities ({len(results['entities'])})")
            entity_types = {}
            for entity in results['entities']:
                entity_type = entity['type']
                if entity_type not in entity_types:
                    entity_types[entity_type] = []
                entity_types[entity_type].append(entity['value'])
            
            for entity_type, values in entity_types.items():
                print(f"\n   {entity_type.title()}s:")
                for value in values[:10]:  # Limit display
                    print(f"   - {value}")
                if len(values) > 10:
                    print(f"   ... and {len(values) - 10} more")


async def main():
    """Main entry point for EYE-D search"""
    if len(sys.argv) < 3:
        print("Usage: python eye_d_search.py <query> <search_type>")
        print("Search types: email, phone, linkedin, whois, username")
        sys.exit(1)
    
    query = sys.argv[1]
    search_type = sys.argv[2].lower()
    
    if not EYE_D_AVAILABLE:
        print("❌ Error: EYE-D module is not available")
        print("Please ensure the EYE-D directory is in the correct location")
        sys.exit(1)
    
    handler = EyeDSearchHandler()
    
    # Extract actual query value
    query_value = handler.extract_query_value(query, search_type)
    
    # Route to appropriate search method
    if search_type == 'email':
        results = await handler.search_email(query_value)
    elif search_type == 'phone':
        results = await handler.search_phone(query_value)
    elif search_type == 'linkedin':
        results = await handler.search_linkedin(query_value)
    elif search_type == 'whois':
        results = await handler.search_whois(query_value)
    elif search_type == 'username':
        results = await handler.search_username(query_value)
    else:
        print(f"❌ Unknown search type: {search_type}")
        sys.exit(1)
    
    # Display results
    handler.display_results(results)
    
    # Store results
    handler.store_results(results)


if __name__ == "__main__":
    asyncio.run(main())