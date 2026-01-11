import requests
import json
from typing import Dict, List, Optional, Set, Tuple, Any, Generator, Mapping, Iterable
from datetime import datetime
from pathlib import Path
import os
from dataclasses import dataclass
import time
import re
import logging
from logging.handlers import RotatingFileHandler
import uuid
from urllib.parse import urljoin, urlencode
from itertools import count
import click

# Constants
VERSION = "3.0.0"
ALEPH_API_KEY = "1c0971afa4804c2aafabb125c79b275e"
ALEPH_BASE_URL = "https://aleph.occrp.org/api/2/"
MAX_RETRIES = 5
RETRY_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RESULTS_PER_PAGE = 50

# Set up logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "aleph_search.log"

logger = logging.getLogger("aleph_search")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Country code mapping (add more as needed)
COUNTRY_CODES = {
    'uk': ['gbr', 'gb', 'uk', 'united kingdom', 'britain', 'british', 'england', 'scotland', 'wales', 'northern ireland'],
    'fr': ['fra', 'fr', 'france', 'french'],
    'de': ['deu', 'de', 'germany', 'german'],
    'es': ['esp', 'es', 'spain', 'spanish'],
    'it': ['ita', 'it', 'italy', 'italian'],
    'us': ['usa', 'us', 'united states', 'american'],
    'ca': ['can', 'ca', 'canada', 'canadian'],
    'au': ['aus', 'au', 'australia', 'australian'],
    'nz': ['nzl', 'nz', 'new zealand'],
    'ie': ['irl', 'ie', 'ireland', 'irish'],
    'ch': ['che', 'ch', 'switzerland', 'swiss'],
    # Add more country mappings as needed
}

# Expanded schema types
ENTITY_SCHEMAS = [
    'Company',
    'Person',
    'Organization',
    'LegalEntity',
    'Asset',
    'Event',
    'Contract',
    'Payment',
    'BankAccount',
    'Vehicle',
    'RealEstate',
    'Directorship',
    'Ownership',
    'Membership'
]

def extract_country_filters(query: str) -> Tuple[str, Set[str]]:
    """Extract country filters from query and normalize them"""
    country_pattern = r'\b([a-zA-Z]{2})!'  # Allow both upper and lower case
    country_filters = set()
    
    # Find all country codes with ! operator
    matches = re.finditer(country_pattern, query)  # Remove .lower() to match original case
    for match in matches:
        country_code = match.group(1).lower()  # Convert to lowercase for comparison
        if country_code in COUNTRY_CODES:
            country_filters.add(country_code)
    
    # Remove country filters from query and clean up
    clean_query = re.sub(country_pattern, '', query)
    # Remove any trailing/leading punctuation and normalize spaces
    clean_query = re.sub(r'\s+', ' ', clean_query).strip(' ,.!?')
    return clean_query, country_filters

def format_query_for_api(query: str, enable_regex: bool = False) -> str:
    """Format a query string for the Aleph API with enhanced options"""
    # Remove any existing quotes
    query = query.strip().strip('"\'')
    
    if enable_regex:
        return query  # Return as-is for regex queries
    
    # For multi-word queries, wrap in quotes to ensure exact phrase matching
    if ' ' in query:
        return f'"{query}"'
    
    return query

def matches_country_filter(entity_countries: List[str], country_filters: Set[str]) -> bool:
    """Check if entity matches any of the country filters"""
    if not country_filters:
        return True
        
    if not entity_countries:
        print("  • No country information available")
        return True  # If no country info, include it
        
    entity_countries = [c.lower() for c in entity_countries]
    print(f"  • Checking countries: {entity_countries}")
    
    for filter_code in country_filters:
        valid_codes = COUNTRY_CODES.get(filter_code, [])
        print(f"  • Looking for matches with {filter_code}: {valid_codes}")
        if any(code in entity_countries for code in valid_codes):
            print("  • ✓ Match found!")
            return True
        
    print("  • ✗ No country matches found")
    return False

@dataclass
class AlephEntity:
    """Structured data class for Aleph entities following FollowTheMoney schema specifications"""
    id: str
    schema: str
    name: str
    properties: Dict
    datasets: List[Dict]
    countries: List[str]
    addresses: List[str]
    links: List[Dict]
    raw_data: Dict
    collection_id: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    fingerprints: Optional[List[str]] = None
    names: Optional[List[str]] = None
    identifiers: Optional[List[str]] = None
    roles: Optional[List[Dict]] = None
    highlights: Optional[Dict[str, List[str]]] = None
    edge_spec: Optional[Dict] = None
    temporal_extent: Optional[Dict] = None
    featured_props: Optional[List[str]] = None
    caption_props: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        """Convert entity to dictionary format following FollowTheMoney SchemaToDict spec"""
        data = {
            'id': self.id,
            'schema': self.schema,
            'name': self.name,
            'properties': self.properties,
            'datasets': self.datasets,
            'countries': self.countries,
            'addresses': self.addresses,
            'links': self.links,
            'collection_id': self.collection_id,
            'created_at': self.first_seen,
            'updated_at': self.last_seen,
            'fingerprints': self.fingerprints,
            'names': self.names,
            'identifiers': self.identifiers,
            'roles': self.roles,
            'highlights': self.highlights
        }
        
        # Add edge specification if available
        if self.edge_spec:
            data['edge'] = {
                'source': self.edge_spec.get('source'),
                'target': self.edge_spec.get('target'),
                'caption': self.edge_spec.get('caption', []),
                'label': self.edge_spec.get('label'),
                'directed': self.edge_spec.get('directed', True)
            }
            
        # Add temporal extent if available
        if self.temporal_extent:
            data['temporalExtent'] = {
                'start': self.temporal_extent.get('start', []),
                'end': self.temporal_extent.get('end', [])
            }
            
        # Add featured and caption properties
        if self.featured_props:
            data['featured'] = self.featured_props
        if self.caption_props:
            data['caption'] = self.caption_props
            
        return data

    def get_property(self, prop_name: str, default: Any = None) -> Any:
        """Safely get a property value following FollowTheMoney property access pattern"""
        if prop_name in (self.featured_props or []):
            # Featured properties get priority
            return self.properties.get(prop_name, default)
        elif prop_name in (self.caption_props or []):
            # Caption properties come next
            return self.properties.get(prop_name, default)
        return self.properties.get(prop_name, default)

    def get_temporal_properties(self) -> Tuple[List[str], List[str]]:
        """Get temporal start and end properties following FollowTheMoney temporal spec"""
        if not self.temporal_extent:
            return [], []
        return (
            self.temporal_extent.get('start', []),
            self.temporal_extent.get('end', [])
        )

    def get_edge_properties(self) -> Optional[Dict]:
        """Get edge properties following FollowTheMoney EdgeSpec"""
        if not self.edge_spec:
            return None
        return {
            'source': self.edge_spec.get('source'),
            'target': self.edge_spec.get('target'),
            'caption': self.edge_spec.get('caption', []),
            'label': self.edge_spec.get('label'),
            'directed': self.edge_spec.get('directed', True)
        }

class AlephSearchException(Exception):
    """Custom exception class for Aleph API errors"""
    def __init__(self, exc):
        self.exc = exc
        self.response = None
        self.status = None
        self.transient = isinstance(exc, (requests.ConnectionError, requests.Timeout))
        self.message = str(exc)
        
        if hasattr(exc, 'response') and exc.response is not None:
            self.response = exc.response
            self.status = exc.response.status_code
            self.transient = exc.response.status_code >= 500
            try:
                data = exc.response.json()
                self.message = data.get('message')
            except Exception:
                self.message = exc.response.text
    
    def __str__(self):
        return self.message

def backoff(exc: AlephSearchException, attempt: int):
    """Implement exponential backoff"""
    sleep_time = min(2 ** attempt, 120)  # Cap at 120 seconds
    logger.warning(f"Request failed (attempt {attempt}), retrying in {sleep_time}s... Error: {exc}")
    time.sleep(sleep_time)

class APIResultSet:
    def __init__(self, api: "AlephAPI", url: str):
        self.api = api
        self.url = url
        self.current = 0
        self.result = self.api._request("GET", self.url)

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= self.result.get("limit"):
            next_url = self.result.get("next")
            if next_url is None:
                raise StopIteration
            self.result = self.api._request("GET", next_url)
            self.current = 0
        try:
            item = self.result.get("results", [])[self.index]
        except IndexError:
            raise StopIteration
        self.current += 1
        return self._patch(item)

    next = __next__

    def _patch(self, item):
        return item

    @property
    def index(self):
        return self.current - self.result.get("offset", 0)

    def __len__(self):
        return self.result.get("total", 0)

    def __repr__(self):
        return "<APIResultSet(%r, %r)>" % (self.url, len(self))

class EntityResultSet(APIResultSet):
    def __init__(self, api: "AlephAPI", url: str, publisher: bool = False):
        super().__init__(api, url)
        self.publisher = publisher
    
    def _patch(self, item: Dict) -> Dict:
        """Override _patch to add publisher info"""
        return self.api._patch_entity(item, self.publisher)

    def __iter__(self):
        return self

    def __next__(self):
        if self.current >= len(self.result.get("results", [])):
            next_url = self.result.get("next")
            if next_url is None:
                raise StopIteration
            self.result = self.api._request("GET", next_url)
            self.current = 0
        
        item = self.result.get("results", [])[self.current]
        self.current += 1
        return self._patch(item)

class AlephAPI:
    def __init__(self):
        """Initialize Aleph API client with enhanced configuration"""
        if not ALEPH_BASE_URL:
            raise AlephSearchException("No host environment variable found")
            
        self.base_url = ALEPH_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'ApiKey {ALEPH_API_KEY}',
            'Accept': 'application/json',
            'User-Agent': f'alephclient/{VERSION}',
            'X-Aleph-Session': str(uuid.uuid4())
        })
        
        # Test connection
        logger.info("Testing Aleph API connection...")
        try:
            self.get_statistics()
            logger.info("✓ Successfully connected to Aleph API")
        except AlephSearchException as e:
            logger.error(f"❌ Failed to connect to Aleph API: {str(e)}")
            raise

    def _patch_entity(self, entity: Dict, publisher: bool = True) -> Dict:
        """Add extra properties from context to the entity"""
        try:
            properties = entity.get("properties", {})
            collection = entity.get("collection") or {}
            
            # Add API URL
            links = entity.get("links", {})
            api_url = links.get("self")
            if api_url is None:
                api_url = f"entities/{entity.get('id')}"
                api_url = self._make_url(api_url)
            properties["alephUrl"] = api_url

            if publisher:
                # Add publisher information
                publisher_label = collection.get("label")
                publisher_label = collection.get("publisher", publisher_label)
                if publisher_label:
                    properties["publisher"] = publisher_label

                publisher_url = collection.get("links", {}).get("ui")
                publisher_url = collection.get("publisher_url", publisher_url)
                if publisher_url:
                    properties["publisherUrl"] = publisher_url

            entity["properties"] = properties
            return entity
        except Exception as e:
            logger.error(f"Error patching entity: {str(e)}")
            return entity

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about available data"""
        return self._request("GET", "statistics")

    def _request(self, method: str, url: str, **kwargs) -> Dict:
        """Single point to make HTTP requests with proper error handling"""
        try:
            if not url.startswith('http'):
                url = urljoin(self.base_url, url)
                
            response = self.session.request(
                method=method,
                url=url,
                timeout=REQUEST_TIMEOUT,
                **kwargs
            )
            response.raise_for_status()
            return response.json() if len(response.text) else {}
        except requests.RequestException as exc:
            raise AlephSearchException(exc)

    def _make_url(
        self,
        path: str,
        query: Optional[str] = None,
        filters: Optional[List] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Construct the target URL from given args"""
        url = urljoin(self.base_url, path)
        params = params or {}
        params_list = list(params.items())
        
        if query:
            params_list.append(("q", query))
            
        if filters:
            for key, val in filters:
                if val is not None:
                    params_list.append(("filter:" + key, val))
                    
        if params_list:
            params_filter = [(k, v) for k, v in params_list if v is not None]
            url = url + "?" + urlencode(params_filter)
            
        return url

    def search_entities(
        self,
        query: str,
        schema: Optional[str] = None,
        country_filters: Optional[Set[str]] = None,
        enable_regex: bool = False,
        publisher: bool = True,
        params: Optional[Mapping[str, Any]] = None,
        include_related: bool = True
    ) -> EntityResultSet:
        """Search for entities using Aleph's pagination pattern with related entities"""
        filters_list: List = []
        
        # Handle schema filtering differently
        if schema is not None:
            if schema == 'Company':
                # When searching for companies, include persons too
                filters_list.append(("schema", "Company,Person"))
            else:
                filters_list.append(("schema", schema))
        else:
            # If no schema specified, search for both companies and persons
            filters_list.append(("schema", "Company,Person"))
            
        if country_filters:
            for country in country_filters:
                filters_list.append(("countries", country))

        search_params = {
            "limit": MAX_RESULTS_PER_PAGE,
            "safe": True,
            "highlight": True,
            "highlight_count": 5,
            "prefix_field": "name",
            "include_relationships": include_related
        }
        if params:
            search_params.update(params)
        if enable_regex:
            search_params["regex"] = True

        url = self._make_url(
            "entities", 
            query=query, 
            filters=filters_list, 
            params=search_params
        )
        return EntityResultSet(self, url, publisher=publisher)

    def get_related_entities(self, entity_id: str, schema_type: Optional[str] = None) -> List[Dict]:
        """Fetch entities related to the given entity ID using UK Companies House specific endpoints"""
        try:
            # First get the entity details
            entity_url = self._make_url(f"entities/{entity_id}")
            entity_data = self._request("GET", entity_url)
            entity_schema = entity_data.get('schema')
            
            if entity_schema != 'Company':
                logger.info(f"Entity {entity_id} is not a company (schema: {entity_schema})")
                return []
            
            # Get the company number from the entity
            company_number = None
            for reg_num in entity_data.get('properties', {}).get('registrationNumber', []):
                if reg_num:  # Use the first non-empty registration number
                    company_number = reg_num
                    break
            
            if not company_number:
                logger.error("No company registration number found")
                return []
            
            # Search for officers using the company number
            params = {
                "limit": MAX_RESULTS_PER_PAGE,
                "filter:properties.company.registration_number": company_number,
                "schema": "Directorship"
            }
            
            url = self._make_url("entities", params=params)
            response = self._request("GET", url)
            results = response.get('results', [])
            
            # Process the directorships to extract related people
            related_entities = []
            for directorship in results:
                props = directorship.get('properties', {})
                
                # Get the director details
                director = props.get('director', {})
                if isinstance(director, dict) and director.get('id'):
                    try:
                        # Get full person details
                        person_url = self._make_url(f"entities/{director['id']}")
                        person_data = self._request("GET", person_url)
                        if person_data:
                            # Add relationship metadata
                            person_data['role'] = props.get('role', 'Director')
                            person_data['schema'] = 'Person'
                            
                            # Add temporal extent
                            if props.get('startDate'):
                                person_data['temporal_start'] = props['startDate']
                            if props.get('endDate'):
                                person_data['temporal_end'] = props['endDate']
                            
                            # Add position and status
                            if props.get('position') or props.get('status'):
                                person_data['edge_properties'] = {
                                    'position': props.get('position'),
                                    'status': props.get('status')
                                }
                            
                            related_entities.append(person_data)
                            logger.info(f"Found director: {person_data.get('name')} ({person_data.get('role')})")
                    except Exception as e:
                        logger.error(f"Failed to fetch director details: {str(e)}")
                        continue
            
            # Also search for ownership records
            params['schema'] = 'Ownership'
            url = self._make_url("entities", params=params)
            response = self._request("GET", url)
            results = response.get('results', [])
            
            # Process ownerships to extract owners
            for ownership in results:
                props = ownership.get('properties', {})
                owner = props.get('owner', {})
                
                if isinstance(owner, dict) and owner.get('id'):
                    try:
                        # Get full person details
                        person_url = self._make_url(f"entities/{owner['id']}")
                        person_data = self._request("GET", person_url)
                        if person_data:
                            # Add relationship metadata
                            person_data['role'] = 'Owner'
                            person_data['schema'] = 'Person'
                            
                            # Add ownership details
                            if props.get('percentage'):
                                person_data['edge_properties'] = {
                                    'ownership_percentage': props['percentage']
                                }
                            
                            # Add temporal extent
                            if props.get('startDate'):
                                person_data['temporal_start'] = props['startDate']
                            if props.get('endDate'):
                                person_data['temporal_end'] = props['endDate']
                            
                            related_entities.append(person_data)
                            logger.info(f"Found owner: {person_data.get('name')} ({person_data.get('role')})")
                    except Exception as e:
                        logger.error(f"Failed to fetch owner details: {str(e)}")
                        continue
            
            return related_entities
            
        except Exception as e:
            logger.error(f"Failed to fetch related entities: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response content: {e.response.text}")
            return []

    def write_entities(
        self,
        collection_id: str,
        entities: Iterable,
        chunk_size: int = 1000,
        **kwargs
    ) -> None:
        """Create entities in bulk via the API"""
        chunk = []
        for entity in entities:
            if hasattr(entity, "to_dict"):
                entity = entity.to_dict()
            chunk.append(entity)
            if len(chunk) >= chunk_size:
                self._bulk_chunk(collection_id, chunk, **kwargs)
                chunk = []
        if chunk:
            self._bulk_chunk(collection_id, chunk, **kwargs)

    def _bulk_chunk(self, collection_id: str, chunk: List[Dict], **kwargs) -> None:
        """Process a chunk of entities for bulk upload"""
        url = self._make_url(f"collections/{collection_id}/ingest")
        self._request("POST", url, json={"entities": chunk}, **kwargs)

    def get_collection_by_foreign_id(self, foreign_id: str) -> Optional[Dict]:
        """Get collection details by foreign ID"""
        try:
            params = {"filter:foreign_id": foreign_id}
            url = self._make_url("collections", params=params)
            results = self._request("GET", url)
            if results.get("results"):
                return results["results"][0]
            return None
        except Exception as e:
            logger.error(f"Failed to get collection: {str(e)}")
            return None

    def _get_collection_id(self, foreign_id: str) -> Optional[str]:
        """Get collection ID from foreign ID"""
        collection = self.get_collection_by_foreign_id(foreign_id)
        if collection is None:
            logger.error(f"Collection not found: {foreign_id}")
            return None
        return collection.get("id")

    def _get_filename(self, entity: Dict) -> str:
        """Get filename from entity following Aleph's pattern"""
        filenames = entity.get("properties", {}).get("fileName", [])
        if filenames:
            return max(filenames, key=len)
        return entity.get("id")

def print_entity_details(entity: AlephEntity):
    """Print formatted entity details to terminal with enhanced relationship display"""
    print(f"\n{'='*80}")
    print(f"📌 Entity: {entity.name}")
    print(f"{'='*80}")
    
    # Basic entity info
    print(f"Type: {entity.schema}")
    print(f"ID: {entity.id}")
    if entity.collection_id:
        print(f"Collection: {entity.collection_id}")
    
    # For Person entities
    if entity.schema == 'Person':
        props = entity.properties
        if props.get('firstName'):
            print(f"First Name: {props['firstName'][0]}")
        if props.get('lastName'):
            print(f"Last Name: {props['lastName'][0]}")
        if props.get('birthDate'):
            print(f"Birth Date: {props['birthDate'][0]}")
        if props.get('idNumber'):
            print(f"ID Number: {props['idNumber'][0]}")
        if props.get('address'):
            print(f"Address: {props['address'][0]}")
        if props.get('country'):
            print(f"Country: {props['country'][0].upper()}")
            
    # For Directorship entities
    elif entity.schema == 'Directorship':
        props = entity.properties
        if props.get('organization'):
            company = props['organization'][0]
            company_props = company.get('properties', {})
            print("\n🏢 Company Details:")
            print(f"Name: {company_props.get('name', ['Unknown'])[0]}")
            print(f"Registration: {company_props.get('registrationNumber', ['Unknown'])[0]}")
            print(f"Status: {', '.join(company_props.get('status', ['Unknown']))}")
            print(f"Incorporated: {company_props.get('incorporationDate', ['Unknown'])[0]}")
            if company_props.get('dissolutionDate'):
                print(f"Dissolved: {company_props.get('dissolutionDate')[0]}")
            print(f"Address: {company_props.get('address', ['Unknown'])[0]}")
            print(f"Jurisdiction: {company_props.get('jurisdiction', ['Unknown'])[0].upper()}")
            
        if props.get('role'):
            print(f"\nRole: {props['role'][0].title()}")
        if props.get('startDate'):
            print(f"Start Date: {props['startDate'][0]}")
            
    print(f"\nSource: {entity.collection_id}")
    if entity.first_seen:
        print(f"First seen: {entity.first_seen}")
    if entity.last_seen:
        print(f"Last seen: {entity.last_seen}")
    print(f"{'='*80}\n")

def save_results(data: List[AlephEntity], query: str):
    """Save search results and print to terminal"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(f"aleph_data/{query.replace(' ', '_')}_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n🔍 Search Results:")
    print(f"{'='*80}")
    print(f"Query: {query}")
    
    # Deduplicate entities by ID
    unique_entities = {}
    for entity in data:
        if entity.id not in unique_entities:
            unique_entities[entity.id] = entity
    
    data = list(unique_entities.values())
    print(f"Total entities found: {len(data)}")
    print(f"{'='*80}\n")
    
    # Group entities by schema
    entities_by_schema = {}
    for entity in data:
        if entity.schema not in entities_by_schema:
            entities_by_schema[entity.schema] = []
        entities_by_schema[entity.schema].append(entity)
    
    # Print persons first, then their directorships
    if 'Person' in entities_by_schema:
        for person in entities_by_schema['Person']:
            print_entity_details(person)
            # Print associated directorships
            if 'Directorship' in entities_by_schema:
                related_directorships = [
                    d for d in entities_by_schema['Directorship']
                    if d.properties.get('director', [{}])[0].get('id') == person.id
                ]
                for directorship in related_directorships:
                    print_entity_details(directorship)
    
    # Save to files
    for entity in data:
        entity_file = output_dir / f"{entity.schema.lower()}_{entity.id}.json"
        with open(entity_file, 'w', encoding='utf-8') as f:
            json.dump(entity.to_dict(), f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved in: {output_dir}")
    print("\nEntity counts by type:")
    for schema, entities in entities_by_schema.items():
        print(f"  • {schema}: {len(entities)}")

def dict_to_aleph_entity(data: Dict) -> AlephEntity:
    """Convert a dictionary to an AlephEntity object following FollowTheMoney schema"""
    # Extract edge specification if present
    edge_spec = None
    if 'edge' in data:
        edge_spec = {
            'source': data['edge'].get('source'),
            'target': data['edge'].get('target'),
            'caption': data['edge'].get('caption', []),
            'label': data['edge'].get('label'),
            'directed': data['edge'].get('directed', True)
        }
    
    # Extract temporal extent if present
    temporal_extent = None
    if 'temporalExtent' in data:
        temporal_extent = {
            'start': data['temporalExtent'].get('start', []),
            'end': data['temporalExtent'].get('end', [])
        }
    
    return AlephEntity(
        id=data.get("id"),
        schema=data.get("schema"),
        name=data.get("caption", data.get("name", "Unknown")),
        properties=data.get("properties", {}),
        datasets=[{
            "name": d.get("name"),
            "label": d.get("label"),
            "category": d.get("category"),
            "publisher": d.get("publisher"),
            "summary": d.get("summary")
        } for d in data.get("datasets", [])],
        countries=data.get("properties", {}).get("countries", []),
        addresses=data.get("properties", {}).get("addresses", []),
        links=data.get("relationships", []),
        raw_data=data,
        collection_id=data.get("collection_id"),
        first_seen=data.get("created_at"),
        last_seen=data.get("updated_at"),
        fingerprints=data.get("fingerprints", []),
        names=data.get("names", []),
        identifiers=data.get("identifiers", []),
        roles=data.get("roles", []),
        highlights=data.get("highlight", data.get("highlights", [])),
        edge_spec=edge_spec,
        temporal_extent=temporal_extent,
        featured_props=data.get("featured", []),
        caption_props=data.get("caption", [])
    )

def main():
    """Main entry point with improved error handling"""
    api = None
    try:
        query = input("\nEnter search term (use XX! for country filters, e.g. 'Siemens Ltd de!'): ").strip()
        if not query:
            logger.warning("No input provided")
            return

        # Extract country filters from query
        clean_query, country_filters = extract_country_filters(query)
        logger.info(f"\nProcessing search:")
        logger.info(f"• Clean search term: {clean_query}")
        if country_filters:
            logger.info(f"• Country filters: {', '.join(country_filters)}")
            for country in country_filters:
                logger.info(f"  - {country}: {COUNTRY_CODES.get(country, [])}")
        else:
            logger.info("• No country filters applied - showing all results")
        
        api = AlephAPI()
        all_entities = []
        
        try:
            stats = api.get_statistics()
            logger.info(f"\n📊 Aleph Statistics:")
            logger.info(f"• Total entities: {stats.get('entities', 0):,}")
            logger.info(f"• Total collections: {stats.get('collections', 0):,}")
            logger.info(f"• Total datasets: {stats.get('datasets', 0):,}")
        except AlephSearchException as e:
            logger.warning(f"Could not fetch statistics: {e.message}")
        
        logger.info(f"\n🔎 Starting comprehensive search")
        
        # First search for companies and persons together
        try:
            logger.info("\nSearching for Companies and Persons...")
            result_set = api.search_entities(
                clean_query, 
                None,  # This will search for both Company and Person
                country_filters,
                include_related=True
            )
            
            if result_set:
                total = len(result_set)
                logger.info(f"Found {total} entities")
                
                for entity_dict in result_set:
                    entity = dict_to_aleph_entity(entity_dict)
                    
                    # Fetch related people if this is a company
                    if entity.schema == 'Company':
                        try:
                            logger.info(f"\nFetching related people for company: {entity.name}")
                            related = api.get_related_entities(entity.id, 'Person')
                            if related:
                                # Add relationship information to the links
                                for rel in related:
                                    rel['type'] = rel.pop('role', 'Unknown')  # Convert role to type for consistency
                                    logger.info(f"Found related person: {rel.get('name')} ({rel.get('type')})")
                                entity.links.extend(related)
                                logger.info(f"Added {len(related)} related people to {entity.name}")
                            else:
                                logger.info("No related people found for this company")
                        except Exception as e:
                            logger.error(f"Error fetching related entities for {entity.name}: {str(e)}")
                            logger.error(f"Response content: {getattr(e, 'response', {}).get('content', 'No response content')}")
                    
                    all_entities.append(entity)
        
        except AlephSearchException as e:
            logger.error(f"Error searching for entities: {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error during search: {str(e)}")
        
        # Then search for other entity types if needed
        other_schemas = [s for s in ENTITY_SCHEMAS if s not in ['Company', 'Person']]
        for schema in other_schemas:
            try:
                logger.info(f"\nSearching for {schema} entities...")
                result_set = api.search_entities(
                    clean_query, 
                    schema, 
                    country_filters,
                    include_related=True
                )
                
                if result_set:
                    total = len(result_set)
                    logger.info(f"Found {total} {schema} entities")
                    for entity_dict in result_set:
                        all_entities.append(dict_to_aleph_entity(entity_dict))
                        
            except AlephSearchException as e:
                logger.error(f"Error searching for {schema} entities: {e.message}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error searching for {schema} entities: {str(e)}")
                continue
        
        if all_entities:
            logger.info(f"\n✨ Found total of {len(all_entities)} matching entities")
            save_results(all_entities, clean_query)
        else:
            logger.warning("\n❌ No matching results found")
            
    except KeyboardInterrupt:
        logger.info("\nSearch interrupted by user")
        raise click.Abort()
    except AlephSearchException as e:
        logger.error(f"Search failed: {e.message}")
        raise click.ClickException(e.message)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise click.ClickException(str(e))
    finally:
        if api and api.session:
            api.session.close()
            logger.info("Cleaned up API session")

if __name__ == "__main__":
    main() 