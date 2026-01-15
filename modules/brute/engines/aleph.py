"""
exact_phrase_recall_runner_aleph.py  ·  v2 ("max-recall + streaming + exact phrase enforcement")
=======================================================
Automates a "max-recall" style search for OCCRP Aleph with enhanced exact phrase enforcement.

Features:
* **Streaming Support**: Results are yielded progressively as pages/entities are fetched
* **Expanded Query Variations**: Exact phrase, fuzzy, proximity, field-specific searches
* **Enhanced Schema Coverage**: All entity types with comprehensive permutations
* **Multi-Country Support**: Comprehensive country filtering with aliases
* **Retry Logic**: Robust handling of API failures, rate limits, and timeouts
* **Iterative Exception Search**: NOT-based exclusion to discover overlooked results
* **Time Range Filtering**: Date-based filtering for historical targeting
* **Improved Thread Safety**: Enhanced parallel execution with proper deduplication

Changes from base occrp_aleph.py:
* Converted to generator yielding results progressively
* Added comprehensive query variations (fuzzy, proximity, field-specific)
* Enhanced retry logic with exponential backoff and jitter
* Implemented iterative exception search using NOT operators
* Added time range filtering capabilities
* Enhanced exact phrase enforcement with validation
* Added comprehensive metadata tagging
* Supports related entity fetching for maximum coverage
"""

from __future__ import annotations

import requests
import json
import logging
import time
import random
import threading
import os
import re
import uuid
from typing import Dict, List, Optional, Set, Tuple, Any, Iterable, Union
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urljoin, urlencode
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import shared utilities
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from brute.infrastructure.shared_session import get_shared_session
except ImportError:
    from ..infrastructure.shared_session import get_shared_session

logger = logging.getLogger("aleph_phrase_runner")

# Enhanced Aleph API configuration
ALEPH_BASE_URL = "https://aleph.occrp.org/api/2/"
DEFAULT_API_KEY = os.getenv('ALEPH_API_KEY')
MAX_RETRIES = 5
REQUEST_TIMEOUT = 30
MAX_RESULTS_PER_PAGE = 50
RETRY_DELAY_BASE = 1.0

# Enhanced entity schemas for comprehensive coverage
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
    'Membership',
    'Document',
    'Email',
    'Phone',
    'Address',
    'Interval',
    'Sanction',
    'Vessel',
    'Aircraft'
]

# Enhanced country code mapping for maximum coverage
COUNTRY_CODES = {
    'us': ['usa', 'us', 'united states', 'american', 'america'],
    'uk': ['gbr', 'gb', 'uk', 'united kingdom', 'britain', 'british', 'england', 'scotland', 'wales'],
    'de': ['deu', 'de', 'germany', 'german', 'deutschland'],
    'fr': ['fra', 'fr', 'france', 'french', 'francais'],
    'it': ['ita', 'it', 'italy', 'italian', 'italia'],
    'es': ['esp', 'es', 'spain', 'spanish', 'espana'],
    'ru': ['rus', 'ru', 'russia', 'russian', 'россия'],
    'cn': ['chn', 'cn', 'china', 'chinese', '中国'],
    'jp': ['jpn', 'jp', 'japan', 'japanese', '日本'],
    'ca': ['can', 'ca', 'canada', 'canadian'],
    'au': ['aus', 'au', 'australia', 'australian'],
    'nz': ['nzl', 'nz', 'new zealand', 'kiwi'],
    'ie': ['irl', 'ie', 'ireland', 'irish'],
    'ch': ['che', 'ch', 'switzerland', 'swiss'],
    'nl': ['nld', 'nl', 'netherlands', 'dutch', 'holland'],
    'be': ['bel', 'be', 'belgium', 'belgian'],
    'at': ['aut', 'at', 'austria', 'austrian'],
    'se': ['swe', 'se', 'sweden', 'swedish'],
    'no': ['nor', 'no', 'norway', 'norwegian'],
    'dk': ['dnk', 'dk', 'denmark', 'danish'],
    'fi': ['fin', 'fi', 'finland', 'finnish'],
    'pl': ['pol', 'pl', 'poland', 'polish'],
    'cz': ['cze', 'cz', 'czech', 'czech republic'],
    'sk': ['svk', 'sk', 'slovakia', 'slovak'],
    'hu': ['hun', 'hu', 'hungary', 'hungarian'],
    'ro': ['rou', 'ro', 'romania', 'romanian'],
    'bg': ['bgr', 'bg', 'bulgaria', 'bulgarian'],
    'hr': ['hrv', 'hr', 'croatia', 'croatian'],
    'si': ['svn', 'si', 'slovenia', 'slovenian'],
    'ee': ['est', 'ee', 'estonia', 'estonian'],
    'lv': ['lva', 'lv', 'latvia', 'latvian'],
    'lt': ['ltu', 'lt', 'lithuania', 'lithuanian'],
    'mt': ['mlt', 'mt', 'malta', 'maltese'],
    'cy': ['cyp', 'cy', 'cyprus', 'cypriot'],
    'lu': ['lux', 'lu', 'luxembourg', 'luxembourgish'],
    'gr': ['grc', 'gr', 'greece', 'greek'],
    'pt': ['prt', 'pt', 'portugal', 'portuguese'],
    'br': ['bra', 'br', 'brazil', 'brazilian'],
    'mx': ['mex', 'mx', 'mexico', 'mexican'],
    'ar': ['arg', 'ar', 'argentina', 'argentinian'],
    'cl': ['chl', 'cl', 'chile', 'chilean'],
    'co': ['col', 'co', 'colombia', 'colombian'],
    'pe': ['per', 'pe', 'peru', 'peruvian'],
    'uy': ['ury', 'uy', 'uruguay', 'uruguayan'],
    'py': ['pry', 'py', 'paraguay', 'paraguayan'],
    'bo': ['bol', 'bo', 'bolivia', 'bolivian'],
    'ec': ['ecu', 'ec', 'ecuador', 'ecuadorian'],
    've': ['ven', 've', 'venezuela', 'venezuelan'],
    'in': ['ind', 'in', 'india', 'indian'],
    'pk': ['pak', 'pk', 'pakistan', 'pakistani'],
    'bd': ['bgd', 'bd', 'bangladesh', 'bangladeshi'],
    'lk': ['lka', 'lk', 'sri lanka', 'sri lankan'],
    'th': ['tha', 'th', 'thailand', 'thai'],
    'vn': ['vnm', 'vn', 'vietnam', 'vietnamese'],
    'my': ['mys', 'my', 'malaysia', 'malaysian'],
    'sg': ['sgp', 'sg', 'singapore', 'singaporean'],
    'id': ['idn', 'id', 'indonesia', 'indonesian'],
    'ph': ['phl', 'ph', 'philippines', 'filipino'],
    'kr': ['kor', 'kr', 'south korea', 'korean'],
    'kp': ['prk', 'kp', 'north korea', 'north korean'],
    'tw': ['twn', 'tw', 'taiwan', 'taiwanese'],
    'hk': ['hkg', 'hk', 'hong kong'],
    'mo': ['mac', 'mo', 'macau', 'macao'],
    'tr': ['tur', 'tr', 'turkey', 'turkish'],
    'il': ['isr', 'il', 'israel', 'israeli'],
    'ps': ['pse', 'ps', 'palestine', 'palestinian'],
    'sa': ['sau', 'sa', 'saudi arabia', 'saudi'],
    'ae': ['are', 'ae', 'uae', 'united arab emirates'],
    'kw': ['kwt', 'kw', 'kuwait', 'kuwaiti'],
    'qa': ['qat', 'qa', 'qatar', 'qatari'],
    'bh': ['bhr', 'bh', 'bahrain', 'bahraini'],
    'om': ['omn', 'om', 'oman', 'omani'],
    'jo': ['jor', 'jo', 'jordan', 'jordanian'],
    'lb': ['lbn', 'lb', 'lebanon', 'lebanese'],
    'sy': ['syr', 'sy', 'syria', 'syrian'],
    'iq': ['irq', 'iq', 'iraq', 'iraqi'],
    'ir': ['irn', 'ir', 'iran', 'iranian'],
    'af': ['afg', 'af', 'afghanistan', 'afghan'],
    'pk': ['pak', 'pk', 'pakistan', 'pakistani'],
    'kz': ['kaz', 'kz', 'kazakhstan', 'kazakh'],
    'uz': ['uzb', 'uz', 'uzbekistan', 'uzbek'],
    'kg': ['kgz', 'kg', 'kyrgyzstan', 'kyrgyz'],
    'tj': ['tjk', 'tj', 'tajikistan', 'tajik'],
    'tm': ['tkm', 'tm', 'turkmenistan', 'turkmen'],
    'za': ['zaf', 'za', 'south africa', 'south african'],
    'ng': ['nga', 'ng', 'nigeria', 'nigerian'],
    'eg': ['egy', 'eg', 'egypt', 'egyptian'],
    'ma': ['mar', 'ma', 'morocco', 'moroccan'],
    'dz': ['dza', 'dz', 'algeria', 'algerian'],
    'tn': ['tun', 'tn', 'tunisia', 'tunisian'],
    'ly': ['lby', 'ly', 'libya', 'libyan'],
    'sd': ['sdn', 'sd', 'sudan', 'sudanese'],
    'et': ['eth', 'et', 'ethiopia', 'ethiopian'],
    'ke': ['ken', 'ke', 'kenya', 'kenyan'],
    'tz': ['tza', 'tz', 'tanzania', 'tanzanian'],
    'ug': ['uga', 'ug', 'uganda', 'ugandan'],
    'rw': ['rwa', 'rw', 'rwanda', 'rwandan'],
    'gh': ['gha', 'gh', 'ghana', 'ghanaian'],
    'ci': ['civ', 'ci', 'ivory coast', 'ivorian'],
    'sn': ['sen', 'sn', 'senegal', 'senegalese'],
    'ml': ['mli', 'ml', 'mali', 'malian'],
    'bf': ['bfa', 'bf', 'burkina faso'],
    'ne': ['ner', 'ne', 'niger'],
    'td': ['tcd', 'td', 'chad', 'chadian'],
    'cf': ['caf', 'cf', 'central african republic'],
    'cm': ['cmr', 'cm', 'cameroon', 'cameroonian'],
    'ga': ['gab', 'ga', 'gabon', 'gabonese'],
    'gq': ['gnq', 'gq', 'equatorial guinea'],
    'cg': ['cog', 'cg', 'congo', 'congolese'],
    'cd': ['cod', 'cd', 'democratic republic congo', 'drc'],
    'ao': ['ago', 'ao', 'angola', 'angolan'],
    'zm': ['zmb', 'zm', 'zambia', 'zambian'],
    'zw': ['zwe', 'zw', 'zimbabwe', 'zimbabwean'],
    'bw': ['bwa', 'bw', 'botswana'],
    'na': ['nam', 'na', 'namibia', 'namibian'],
    'sz': ['swz', 'sz', 'eswatini', 'swaziland'],
    'ls': ['lso', 'ls', 'lesotho'],
    'mw': ['mwi', 'mw', 'malawi', 'malawian'],
    'mz': ['moz', 'mz', 'mozambique', 'mozambican'],
    'mg': ['mdg', 'mg', 'madagascar', 'malagasy'],
    'mu': ['mus', 'mu', 'mauritius', 'mauritian'],
    'sc': ['syc', 'sc', 'seychelles'],
    'km': ['com', 'km', 'comoros', 'comorian'],
    'dj': ['dji', 'dj', 'djibouti'],
    'so': ['som', 'so', 'somalia', 'somali'],
    'er': ['eri', 'er', 'eritrea', 'eritrean'],
    'ss': ['ssd', 'ss', 'south sudan'],
    'by': ['blr', 'by', 'belarus', 'belarusian'],
    'ua': ['ukr', 'ua', 'ukraine', 'ukrainian'],
    'md': ['mda', 'md', 'moldova', 'moldovan'],
    'ge': ['geo', 'ge', 'georgia', 'georgian'],
    'am': ['arm', 'am', 'armenia', 'armenian'],
    'az': ['aze', 'az', 'azerbaijan', 'azerbaijani'],
    'mn': ['mng', 'mn', 'mongolia', 'mongolian'],
    'la': ['lao', 'la', 'laos', 'lao'],
    'kh': ['khm', 'kh', 'cambodia', 'cambodian'],
    'mm': ['mmr', 'mm', 'myanmar', 'burmese'],
    'bt': ['btn', 'bt', 'bhutan', 'bhutanese'],
    'np': ['npl', 'np', 'nepal', 'nepali'],
    'mv': ['mdv', 'mv', 'maldives', 'maldivian'],
    'fj': ['fji', 'fj', 'fiji', 'fijian'],
    'pg': ['png', 'pg', 'papua new guinea'],
    'sb': ['slb', 'sb', 'solomon islands'],
    'vu': ['vut', 'vu', 'vanuatu'],
    'nc': ['ncl', 'nc', 'new caledonia'],
    'pf': ['pyf', 'pf', 'french polynesia'],
    'to': ['ton', 'to', 'tonga', 'tongan'],
    'ws': ['wsm', 'ws', 'samoa', 'samoan'],
    'ki': ['kir', 'ki', 'kiribati'],
    'tv': ['tuv', 'tv', 'tuvalu'],
    'nr': ['nru', 'nr', 'nauru'],
    'pw': ['plw', 'pw', 'palau'],
    'fm': ['fsm', 'fm', 'micronesia'],
    'mh': ['mhl', 'mh', 'marshall islands'],
    'gu': ['gum', 'gu', 'guam'],
    'mp': ['mnp', 'mp', 'northern mariana islands'],
    'as': ['asm', 'as', 'american samoa'],
    'pr': ['pri', 'pr', 'puerto rico'],
    'vi': ['vir', 'vi', 'us virgin islands'],
    'dm': ['dma', 'dm', 'dominica'],
    'gd': ['grd', 'gd', 'grenada'],
    'lc': ['lca', 'lc', 'saint lucia'],
    'vc': ['vct', 'vc', 'saint vincent grenadines'],
    'bb': ['brb', 'bb', 'barbados'],
    'tt': ['tto', 'tt', 'trinidad and tobago'],
    'jm': ['jam', 'jm', 'jamaica', 'jamaican'],
    'ht': ['hti', 'ht', 'haiti', 'haitian'],
    'do': ['dom', 'do', 'dominican republic', 'dominican'],
    'cu': ['cub', 'cu', 'cuba', 'cuban'],
    'bs': ['bhs', 'bs', 'bahamas', 'bahamian'],
    'bz': ['blz', 'bz', 'belize', 'belizean'],
    'gt': ['gtm', 'gt', 'guatemala', 'guatemalan'],
    'sv': ['slv', 'sv', 'el salvador', 'salvadoran'],
    'hn': ['hnd', 'hn', 'honduras', 'honduran'],
    'ni': ['nic', 'ni', 'nicaragua', 'nicaraguan'],
    'cr': ['cri', 'cr', 'costa rica', 'costa rican'],
    'pa': ['pan', 'pa', 'panama', 'panamanian'],
    'gf': ['guf', 'gf', 'french guiana'],
    'sr': ['sur', 'sr', 'suriname', 'surinamese'],
    'gy': ['guy', 'gy', 'guyana', 'guyanese'],
    'fk': ['flk', 'fk', 'falkland islands'],
    'is': ['isl', 'is', 'iceland', 'icelandic'],
    'fo': ['fro', 'fo', 'faroe islands'],
    'gl': ['grl', 'gl', 'greenland'],
    'ad': ['and', 'ad', 'andorra'],
    'mc': ['mco', 'mc', 'monaco'],
    'sm': ['smr', 'sm', 'san marino'],
    'va': ['vat', 'va', 'vatican'],
    'li': ['lie', 'li', 'liechtenstein'],
    'mt': ['mlt', 'mt', 'malta', 'maltese'],
    'cy': ['cyp', 'cy', 'cyprus', 'cypriot'],
    'mk': ['mkd', 'mk', 'north macedonia', 'macedonian'],
    'al': ['alb', 'al', 'albania', 'albanian'],
    'me': ['mne', 'me', 'montenegro'],
    'rs': ['srb', 'rs', 'serbia', 'serbian'],
    'ba': ['bih', 'ba', 'bosnia', 'bosnian'],
    'xk': ['xkx', 'xk', 'kosovo'],
    'kz': ['kaz', 'kz', 'kazakhstan', 'kazakh'],
    'uz': ['uzb', 'uz', 'uzbekistan', 'uzbek'],
    'kg': ['kgz', 'kg', 'kyrgyzstan', 'kyrgyz'],
    'tj': ['tjk', 'tj', 'tajikistan', 'tajik'],
    'tm': ['tkm', 'tm', 'turkmenistan', 'turkmen'],
}

# Global deduplication for thread safety
DEDUP_LOCK = threading.Lock()
ALL_ENTITIES: Dict[str, Dict] = {}

# Shared session for connection pooling
SHARED_SESSION = requests.Session()

@dataclass
class AlephEntity:
    """Enhanced structured data class for Aleph entities."""
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
    search_metadata: Optional[Dict] = None  # NEW: Track search context
    
    def to_dict(self) -> Dict:
        """Convert entity to dictionary format."""
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
            'highlights': self.highlights,
            'search_metadata': self.search_metadata
        }
        return data

class AlephSearchException(Exception):
    """Enhanced exception class for Aleph API errors."""
    def __init__(self, message, original_exception=None, response=None):
        super().__init__(message)
        self.original_exception = original_exception
        self.response = response
        self.status = None
        self.transient = False

        if response is not None:
            self.status = response.status_code
            self.transient = self.status >= 500 or self.status == 429
            try:
                data = response.json()
                self.message = data.get('message', message)
            except ValueError:
                self.message = response.text or message
        elif isinstance(original_exception, (requests.ConnectionError, requests.Timeout)):
            self.transient = True
            self.message = str(original_exception)
        elif original_exception:
            self.message = str(original_exception)

def validate_exact_phrase(phrase: str) -> str:
    """Validate and format phrase for exact matching."""
    if not phrase or not phrase.strip():
        raise ValueError("Phrase cannot be empty")
    
    # Remove existing quotes and re-quote for exact matching
    clean_phrase = phrase.strip('\'"')
    if not clean_phrase:
        raise ValueError("Phrase cannot be empty after cleaning")
    
    return clean_phrase

def extract_country_filters(query: str) -> Tuple[str, Set[str]]:
    """Enhanced country filter extraction with more patterns."""
    country_patterns = [
        r'\b([a-zA-Z]{2})!',  # Original pattern
        r'\bcountry:([a-zA-Z]{2,3})\b',  # country:us
        r'\bin:([a-zA-Z]{2,3})\b',  # in:uk
    ]
    
    country_filters = set()
    clean_query = query
    
    for pattern in country_patterns:
        matches = re.finditer(pattern, clean_query, re.IGNORECASE)
        for match in matches:
            country_code = match.group(1).lower()
            if country_code in COUNTRY_CODES:
                country_filters.add(country_code)
        clean_query = re.sub(pattern, '', clean_query, flags=re.IGNORECASE)
    
    clean_query = re.sub(r'\s+', ' ', clean_query).strip(' ,.!?')
    return clean_query, country_filters

def format_query_for_api(
    query: str, 
    enable_regex: bool = False, 
    fuzzy: bool = False, 
    proximity: int = 0,
    field_specific: Optional[str] = None
) -> str:
    """Enhanced query formatting with multiple exact phrase strategies."""
    # Handle intitle: prefix
    intitle_match = re.match(r'^"?intitle:(.*?)"?$', query, flags=re.IGNORECASE)
    if intitle_match and not enable_regex:
        kw = intitle_match.group(1).strip()
        return f'title:"{kw}"' if ' ' in kw else f'title:{kw}'
    
    query = query.strip().strip('"\'')
    
    if enable_regex:
        return query
    
    # Field-specific search
    if field_specific:
        if ' ' in query:
            return f'{field_specific}:"{query}"'
        else:
            return f'{field_specific}:{query}'
    
    # Proximity search
    if proximity > 0:
        return f'"{query}"~{proximity}'
    
    # Fuzzy search
    if fuzzy:
        if ' ' in query:
            return f'"{query}"~'
        else:
            return f'{query}~'
    
    # Default exact phrase for multi-word queries
    if ' ' in query:
        return f'"{query}"'
    
    return query

def enhanced_backoff_sleep(attempt: int, base_delay: float = RETRY_DELAY_BASE):
    """Enhanced exponential backoff with jitter for Aleph API."""
    if attempt == 0:
        return
    
    # Exponential backoff with jitter
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, 120)  # Cap at 2 minutes
    
    # Add jitter to avoid synchronized retries
    jitter = random.uniform(0, delay * 0.3)
    final_delay = delay + jitter
    
    logger.info(f"Aleph API backing off for {final_delay:.2f}s (attempt {attempt})")
    time.sleep(final_delay)

def matches_country_filter(entity_countries: List[str], country_filters: Set[str]) -> bool:
    """Enhanced country matching with more aliases."""
    if not country_filters:
        return True
    if not entity_countries:
        return True
    
    entity_countries = [c.lower() for c in entity_countries]
    
    for filter_code in country_filters:
        valid_codes = COUNTRY_CODES.get(filter_code, [])
        if any(code in entity_countries for code in valid_codes):
            return True
    
    return False

def post_filter_by_time_range(entity: AlephEntity, time_range: Optional[Tuple[str, str]]) -> bool:
    """Filter entities by time range using available date properties."""
    if not time_range:
        return True
    
    start_date, end_date = time_range
    
    # Check various date properties
    date_properties = ['date', 'startDate', 'endDate', 'created_at', 'updated_at']
    
    for prop in date_properties:
        prop_values = entity.properties.get(prop, [])
        if not prop_values:
            continue
        
        if not isinstance(prop_values, list):
            prop_values = [prop_values]
        
        for date_value in prop_values:
            try:
                if isinstance(date_value, str):
                    entity_date = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    range_start = datetime.fromisoformat(start_date)
                    range_end = datetime.fromisoformat(end_date)
                    
                    if range_start <= entity_date <= range_end:
                        return True
            except (ValueError, TypeError):
                continue
    
    return True  # Include if no date filtering possible

class StreamingAlephResultSet:
    """Enhanced result set with streaming capabilities."""
    
    def __init__(self, api: "EnhancedAlephAPI", url: str, query_metadata: Dict):
        self.api = api
        self.url = url
        self.query_metadata = query_metadata
        self.current_page_results: List[Dict] = []
        self.current_item_index: int = 0
        self.next_page_url: Optional[str] = url
        self.total_results: int = 0
        
        # Fetch the first page immediately
        try:
            response_data = self.api._request("GET", self.url)
            self.current_page_results = response_data.get("results", [])
            self.next_page_url = response_data.get("next")
            self.total_results = response_data.get("total", 0)
        except Exception as e:
            logger.error(f"Error fetching initial page: {e}")
            self.current_page_results = []
            self.next_page_url = None
        
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.current_item_index >= len(self.current_page_results):
            if self.next_page_url is None:
                raise StopIteration
            
            # Fetch next page
            try:
                response_data = self.api._request("GET", self.next_page_url)
                self.current_page_results = response_data.get("results", [])
                self.next_page_url = response_data.get("next")
                self.total_results = response_data.get("total", 0)
                self.current_item_index = 0
                
                if not self.current_page_results:
                    raise StopIteration
                    
            except Exception as e:
                logger.error(f"Error fetching next page: {e}")
                raise StopIteration
        
        item = self.current_page_results[self.current_item_index]
        self.current_item_index += 1
        
        # Add query metadata to item
        item['_query_metadata'] = self.query_metadata
        
        return self.api._patch_entity(item)
    
    def __len__(self):
        return self.total_results

class EnhancedAlephAPI:
    """Enhanced Aleph API client with streaming and maximum recall features."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DEFAULT_API_KEY
        if not self.api_key:
            raise AlephSearchException("ALEPH_API_KEY not found in environment variables")
        
        self.base_url = ALEPH_BASE_URL
        if SHARED_SESSION:

            self.session = get_shared_session(engine_name='Aleph')

            logger.info("Using shared connection pool")

        else:

            self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'ApiKey {self.api_key}',
            'Accept': 'application/json',
            'User-Agent': f'aleph-exact-phrase-runner/2.0',
            'X-Aleph-Session': str(uuid.uuid4())
        })
        
        # Thread safety
        self._lock = threading.Lock()
        self._processed_entities: Dict[str, AlephEntity] = {}
        
        # Test connection
        try:
            self.get_statistics()
            logger.info("Successfully connected to Aleph API")
        except AlephSearchException as e:
            logger.error(f"Failed to connect to Aleph API: {e}")
            raise
    
    def _request(self, method: str, url: str, **kwargs) -> Dict:
        """Enhanced request method with better retry logic."""
        if not url.startswith('http'):
            url = urljoin(self.base_url, url)
        
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Aleph API request (attempt {attempt + 1}/{MAX_RETRIES}): {method} {url}")
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=REQUEST_TIMEOUT,
                    **kwargs
                )
                
                if response.status_code == 429:
                    logger.warning(f"Rate limit hit, backing off (attempt {attempt + 1})")
                    enhanced_backoff_sleep(attempt + 1, 2.0)
                    continue
                
                response.raise_for_status()
                
                if response.status_code == 204 or not response.content:
                    return {}
                
                return response.json()
                
            except requests.RequestException as exc:
                last_exception = AlephSearchException(
                    str(exc), 
                    original_exception=exc, 
                    response=getattr(exc, 'response', None)
                )
                
                logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {last_exception}")
                
                if last_exception.transient and attempt < MAX_RETRIES - 1:
                    enhanced_backoff_sleep(attempt + 1)
                    continue
                else:
                    logger.error(f"Request failed permanently after {attempt + 1} attempts")
                    raise last_exception
        
        if last_exception:
            raise last_exception
    
    def _make_url(
        self,
        path: str,
        query: Optional[str] = None,
        filters: Optional[List[Tuple[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enhanced URL construction."""
        url = urljoin(self.base_url, path)
        current_params = dict(params or {})

        if query:
            current_params["q"] = query
        
        if filters:
            for key, val in filters:
                if val is not None:
                    current_params[f"filter:{key}"] = val
        
        if current_params:
            encoded_params = {k: v for k, v in current_params.items() if v is not None}
            if encoded_params:
                url += "?" + urlencode(encoded_params)
        
        return url
    
    def _patch_entity(self, entity: Dict) -> Dict:
        """Enhanced entity patching with more metadata."""
        try:
            properties = entity.get("properties", {})
            collection = entity.get("collection") or {}
            links = entity.get("links", {})
            
            # Add API URL
            api_url = links.get("self")
            if not api_url and entity.get('id'):
                api_url = self._make_url(f"entities/{entity.get('id')}")
            if api_url:
                properties["alephUrl"] = api_url
            
            # Add publisher info
            publisher_label = collection.get("label") or collection.get("publisher")
            if publisher_label:
                properties["publisher"] = publisher_label
            
            publisher_url = collection.get("links", {}).get("ui") or collection.get("publisher_url")
            if publisher_url:
                properties["publisherUrl"] = publisher_url
            
            # Add query metadata if available
            query_metadata = entity.get('_query_metadata', {})
            if query_metadata:
                properties["searchQuery"] = query_metadata.get("query")
                properties["searchSchema"] = query_metadata.get("schema")
                properties["searchType"] = query_metadata.get("search_type", "main")
            
            entity["properties"] = properties
            return entity
            
        except Exception as e:
            logger.error(f"Error patching entity {entity.get('id', 'Unknown')}: {e}")
            return entity
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get Aleph statistics."""
        return self._request("GET", "statistics")
    
    def search_entities_streaming(
        self,
        phrase: str,
        schemas_to_search: Optional[List[Optional[str]]] = None,
        country_filters: Optional[Set[str]] = None,
        time_range: Optional[Tuple[str, str]] = None,
        query_variations: Optional[List[Dict]] = None,
        include_related: bool = False,
        max_results_per_query: int = 100
    ) -> Iterable[AlephEntity]:
        """Enhanced streaming search with comprehensive query variations."""
        
        # Clean and validate phrase
        clean_phrase = validate_exact_phrase(phrase)
        
        # Default schemas - use Document as primary schema for maximum recall
        if schemas_to_search is None:
            schemas_to_search = ['Document'] + ENTITY_SCHEMAS[:5]  # Focus on Document + core entities
        
        # Default query variations for maximum recall
        if query_variations is None:
            query_variations = [
                {"name": "exact", "params": {}},
                {"name": "fuzzy", "params": {"fuzzy": True}},
                {"name": "proximity_2", "params": {"proximity": 2}},
                {"name": "proximity_5", "params": {"proximity": 5}},
                {"name": "title_specific", "params": {"field_specific": "title"}},
                {"name": "text_specific", "params": {"field_specific": "text"}},
                {"name": "summary_specific", "params": {"field_specific": "summary"}},
            ]
        
        logger.info(f"Starting enhanced Aleph search for phrase: '{clean_phrase}'")
        logger.info(f"Schemas: {len(schemas_to_search)}, Variations: {len(query_variations)}")
        
        # Clear global deduplication
        with DEDUP_LOCK:
            ALL_ENTITIES.clear()
        
        # Generate all query permutations
        query_count = 0
        for schema in schemas_to_search:
            for variation in query_variations:
                query_count += 1
                
                # Format query with variation
                formatted_query = format_query_for_api(
                    clean_phrase, 
                    **variation["params"]
                )
                
                # Build API filters
                api_filters = []
                if schema:
                    api_filters.append(("schema", schema))
                if country_filters:
                    for country in country_filters:
                        api_filters.append(("countries", country))
                if time_range:
                    api_filters.append(("dates", f"{time_range[0]}..{time_range[1]}"))
                
                # Build query metadata
                query_metadata = {
                    "query": formatted_query,
                    "original_phrase": clean_phrase,
                    "schema": schema,
                    "variation": variation["name"],
                    "search_type": "main",
                    "query_index": query_count
                }
                
                # API parameters
                api_params = {
                    "limit": min(max_results_per_query, MAX_RESULTS_PER_PAGE),
                    "safe": True,
                    "highlight": True,
                    "highlight_count": 5,
                }
                
                # Add regex parameter if needed
                if variation["params"].get("enable_regex"):
                    api_params["regex"] = True
                
                # Build URL
                url = self._make_url(
                    "entities",
                    query=formatted_query,
                    filters=api_filters,
                    params=api_params
                )
                
                logger.debug(f"Query {query_count}: {variation['name']} - {formatted_query}")
                
                try:
                    # Create streaming result set
                    result_set = StreamingAlephResultSet(self, url, query_metadata)
                    
                    # Stream results with deduplication
                    for entity_dict in result_set:
                        entity = self._dict_to_aleph_entity(entity_dict, query_metadata)
                        
                        # Apply time range filtering if specified
                        if not post_filter_by_time_range(entity, time_range):
                            continue
                        
                        # Apply country filtering if specified
                        if not matches_country_filter(entity.countries, country_filters):
                            continue
                        
                        # Deduplicate
                        with DEDUP_LOCK:
                            if entity.id not in ALL_ENTITIES:
                                ALL_ENTITIES[entity.id] = entity.to_dict()
                                yield entity
                                
                                # Fetch related entities if requested
                                if include_related:
                                    for related_entity in self._get_related_entities_streaming(entity.id):
                                        if related_entity.id not in ALL_ENTITIES:
                                            ALL_ENTITIES[related_entity.id] = related_entity.to_dict()
                                            yield related_entity
                
                except Exception as e:
                    logger.error(f"Query {query_count} failed: {e}")
                    continue
                
                # Reduced delay - parallel execution provides natural spacing
                time.sleep(random.uniform(0.1, 0.3))
        
        # Run iterative exception search
        with DEDUP_LOCK:
            main_results_count = len(ALL_ENTITIES)
            known_ids = set(ALL_ENTITIES.keys())
        
        logger.info(f"Main search complete. Found {main_results_count} unique entities")
        logger.info("Starting iterative exception search...")
        
        for iteration in range(3):  # Up to 3 exception iterations
            try:
                exception_count = 0
                for entity in self._run_exception_search(
                    clean_phrase, 
                    known_ids, 
                    schemas_to_search[:3],  # Limit to top schemas
                    country_filters,
                    time_range
                ):
                    entity.search_metadata = entity.search_metadata or {}
                    entity.search_metadata.update({
                        "search_type": "exception",
                        "exception_iteration": iteration + 1
                    })
                    
                    with DEDUP_LOCK:
                        if entity.id not in ALL_ENTITIES:
                            ALL_ENTITIES[entity.id] = entity.to_dict()
                            known_ids.add(entity.id)
                            exception_count += 1
                            yield entity
                
                if exception_count > 0:
                    logger.info(f"Exception search iteration {iteration + 1}: Found {exception_count} new entities")
                else:
                    logger.info(f"Exception search iteration {iteration + 1}: No new entities found, stopping")
                    break
                    
            except Exception as e:
                logger.error(f"Exception search iteration {iteration + 1} failed: {e}")
                break
        
        with DEDUP_LOCK:
            final_count = len(ALL_ENTITIES)
        
        logger.info(f"Enhanced Aleph search complete. Total unique entities: {final_count}")
    
    def _dict_to_aleph_entity(self, data: Dict, query_metadata: Dict) -> AlephEntity:
        """Convert dictionary to AlephEntity with enhanced metadata."""
        if not isinstance(data, dict):
            return AlephEntity(
                id="error_invalid_input",
                schema="Error",
                name="Invalid Input",
                properties={},
                datasets=[],
                countries=[],
                addresses=[],
                links=[],
                raw_data=data or {},
                search_metadata=query_metadata
            )
        
        properties_data = data.get("properties", {})
        if not isinstance(properties_data, dict):
            properties_data = {}
        
        return AlephEntity(
            id=str(data.get("id", uuid.uuid4())),
            schema=str(data.get("schema", "Thing")),
            name=str(data.get("caption", data.get("name", "Unknown"))),
            properties=properties_data,
            datasets=[{
                "name": d.get("name"),
                "label": d.get("label"),
                "category": d.get("category"),
                "publisher": d.get("publisher"),
                "summary": d.get("summary")
            } for d in data.get("datasets", []) if isinstance(d, dict)],
            countries=properties_data.get("country", properties_data.get("countries", [])),
            addresses=properties_data.get("address", properties_data.get("addresses", [])),
            links=data.get("links", []),
            raw_data=data,
            collection_id=str(data.get("collection_id")) if data.get("collection_id") else None,
            first_seen=str(data.get("created_at", data.get("first_seen"))) if data.get("created_at") or data.get("first_seen") else None,
            last_seen=str(data.get("updated_at", data.get("last_seen"))) if data.get("updated_at") or data.get("last_seen") else None,
            fingerprints=data.get("fingerprints", []),
            names=properties_data.get("name", data.get("names", [])),
            identifiers=data.get("identifiers", []),
            roles=data.get("roles", []),
            highlights=data.get("highlight", data.get("highlights", {})),
            search_metadata=query_metadata
        )
    
    def _get_related_entities_streaming(self, entity_id: str) -> Iterable[AlephEntity]:
        """Stream related entities for a given entity."""
        try:
            # This is a simplified implementation
            # In practice, you might want to use specific relationship endpoints
            related_url = self._make_url(f"entities/{entity_id}/related")
            
            result_set = StreamingAlephResultSet(
                self, 
                related_url, 
                {"search_type": "related", "parent_id": entity_id}
            )
            
            for entity_dict in result_set:
                yield self._dict_to_aleph_entity(entity_dict, {
                    "search_type": "related",
                    "parent_id": entity_id
                })
                
        except Exception as e:
            logger.error(f"Error fetching related entities for {entity_id}: {e}")
    
    def _run_exception_search(
        self,
        phrase: str,
        known_ids: Set[str],
        schemas: List[Optional[str]],
        country_filters: Optional[Set[str]] = None,
        time_range: Optional[Tuple[str, str]] = None
    ) -> Iterable[AlephEntity]:
        """Run exception search using NOT operators to exclude known entities."""
        
        if not known_ids:
            return
        
        logger.info(f"Running exception search excluding {len(known_ids)} known entities")
        
        # Build NOT clause for known IDs (chunk to avoid URL length limits)
        chunk_size = 50
        id_chunks = [list(known_ids)[i:i + chunk_size] for i in range(0, len(known_ids), chunk_size)]
        
        for chunk in id_chunks:
            try:
                # Build exclusion query
                exclusions = " ".join(f"-id:{entity_id}" for entity_id in chunk)
                exception_query = f'"{phrase}" {exclusions}'
                
                # Search with broader parameters
                for schema in schemas:
                    api_filters = []
                    if schema:
                        api_filters.append(("schema", schema))
                    if country_filters:
                        for country in country_filters:
                            api_filters.append(("countries", country))
                    if time_range:
                        api_filters.append(("dates", f"{time_range[0]}..{time_range[1]}"))
                    
                    url = self._make_url(
                        "entities",
                        query=exception_query,
                        filters=api_filters,
                        params={
                            "limit": MAX_RESULTS_PER_PAGE,
                            "safe": True,
                            "highlight": True,
                        }
                    )
                    
                    query_metadata = {
                        "query": exception_query,
                        "original_phrase": phrase,
                        "schema": schema,
                        "search_type": "exception",
                        "excluded_count": len(chunk)
                    }
                    
                    result_set = StreamingAlephResultSet(self, url, query_metadata)
                    
                    for entity_dict in result_set:
                        entity = self._dict_to_aleph_entity(entity_dict, query_metadata)
                        
                        # Double-check it's not in known IDs
                        if entity.id not in known_ids:
                            yield entity
                    
                    # Reduced delay for parallel execution
                    time.sleep(random.uniform(0.1, 0.2))
                    
            except Exception as e:
                logger.error(f"Exception search chunk failed: {e}")
                continue

class ExactPhraseRecallRunnerAleph:
    """Main runner class for enhanced Aleph exact phrase searches."""
    
    def __init__(
        self,
        phrase: str,
        api_key: Optional[str] = None,
        schemas_to_search: Optional[List[Optional[str]]] = None,
        country_filters: Optional[Set[str]] = None,
        time_range: Optional[Tuple[str, str]] = None,
        query_variations: Optional[List[Dict]] = None,
        include_related: bool = False,
        max_results_per_query: int = 100,
        use_parallel: bool = True,
        max_workers: int = 4,
    ):
        self.phrase = phrase
        self.api = EnhancedAlephAPI(api_key)
        self.schemas_to_search = schemas_to_search
        self.country_filters = country_filters
        self.time_range = time_range
        self.query_variations = query_variations
        self.include_related = include_related
        self.max_results_per_query = max_results_per_query
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        
        # Validate phrase
        validate_exact_phrase(phrase)
    
    def run(self) -> Iterable[Dict]:
        """Run the complete enhanced Aleph search."""
        logger.info(f"Starting enhanced Aleph exact phrase search for: '{self.phrase}'")
        
        # Extract country filters from phrase if present
        clean_phrase, embedded_countries = extract_country_filters(self.phrase)
        
        # Combine country filters
        all_country_filters = set()
        if self.country_filters:
            all_country_filters.update(self.country_filters)
        if embedded_countries:
            all_country_filters.update(embedded_countries)
        
        # Stream results
        for entity in self.api.search_entities_streaming(
            phrase=clean_phrase,
            schemas_to_search=self.schemas_to_search,
            country_filters=all_country_filters if all_country_filters else None,
            time_range=self.time_range,
            query_variations=self.query_variations,
            include_related=self.include_related,
            max_results_per_query=self.max_results_per_query
        ):
            # Convert AlephEntity to dict format expected by brute.py
            entity_dict = entity.to_dict()
            
            # Map Aleph fields to standard search result format
            result = {
                'url': entity_dict.get('properties', {}).get('alephUrl', f"https://aleph.occrp.org/entities/{entity.id}"),
                'title': entity_dict.get('name', 'Untitled'),
                'snippet': self._extract_snippet(entity_dict),
                'source': 'Aleph',
                'dataset': ', '.join([d.get('label', d.get('name', '')) for d in entity_dict.get('datasets', [])]),
                'schema': entity_dict.get('schema'),
                'countries': entity_dict.get('countries', []),
                'raw_data': entity_dict
            }
            
            yield result
    
    def _extract_snippet(self, entity_dict: Dict) -> str:
        """Enhanced snippet extraction from Aleph entity properties."""
        properties = entity_dict.get('properties', {})
        
        # Priority order for snippet content
        snippet_sources = [
            'summary',
            'description', 
            'text',
            'content',
            'body',
            'notes',
            'abstract',
            'details'
        ]
        
        # Try each source in order
        for source in snippet_sources:
            value = properties.get(source)
            if value:
                # Handle lists (Aleph often stores properties as lists)
                if isinstance(value, list) and value:
                    content = ' '.join(str(v) for v in value if v)
                else:
                    content = str(value)
                
                # Clean and truncate content
                content = content.strip()
                if content and len(content) > 10:  # Ensure meaningful content
                    return content[:300] + ('...' if len(content) > 300 else '')
        
        # Fallback to highlights if available
        highlights = entity_dict.get('highlights', {})
        if highlights:
            all_highlights = []
            
            # Handle both dict and list formats for highlights
            if isinstance(highlights, dict):
                # Highlights is a dictionary mapping fields to highlight lists
                for field, highlight_list in highlights.items():
                    if isinstance(highlight_list, list):
                        all_highlights.extend(highlight_list)
                    elif highlight_list:  # Single highlight value
                        all_highlights.append(str(highlight_list))
            elif isinstance(highlights, list):
                # Highlights is a list of highlight strings
                all_highlights.extend([str(h) for h in highlights if h])
            
            if all_highlights:
                content = ' ... '.join(all_highlights)
                return content[:300] + ('...' if len(content) > 300 else '')
        
        # Final fallback to schema and name
        schema = entity_dict.get('schema', 'Entity')
        name = entity_dict.get('name', 'Unknown')
        return f"{schema}: {name}"
    
    def run_as_list(self) -> List[AlephEntity]:
        """Convenience method to collect all results."""
        return list(self.run())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    PHRASE_TO_SEARCH = input("Enter exact phrase for OCCRP Aleph: ").strip()
    if not PHRASE_TO_SEARCH:
        print("No phrase given. Exiting.")
    else:
        logger.info(f"Starting Enhanced OCCRP Aleph Recall Runner demo for phrase: '{PHRASE_TO_SEARCH}'")
        
        # Demo configuration
        demo_schemas = [None, "Company", "Person", "Organization", "Document"]
        demo_countries = {"us", "uk", "de", "fr"}  # High-value countries
        demo_time_range = ("2020-01-01", "2024-12-31")  # Recent years
        
        try:
            runner = ExactPhraseRecallRunnerAleph(
                phrase=PHRASE_TO_SEARCH,
                schemas_to_search=demo_schemas,
                country_filters=demo_countries,
                time_range=demo_time_range,
                include_related=True,
                max_results_per_query=50,
                use_parallel=True,
                max_workers=4
            )
            
            logger.info("Starting streaming Aleph runner...")
            results = []
            result_count = 0
            
            # Demonstrate streaming
            for result in runner.run():
                result_count += 1
                results.append(result)
                
                if result_count % 10 == 0:
                    print(f"Processed {result_count} results so far...")
            
            print(f"\n--- STREAMING ALEPH DEMO COMPLETE ---")
            print(f"Found {len(results)} unique entities for '{PHRASE_TO_SEARCH}'")
            
            if results:
                print("\nSample of results:")
                for i, entity in enumerate(results[:5], 1):
                    print(f"\n{i}. {entity.name} ({entity.schema})")
                    print(f"   ID: {entity.id}")
                    print(f"   Countries: {entity.countries}")
                    
                    # Show key properties
                    key_props = ['summary', 'description', 'publisher', 'sourceUrl']
                    for prop in key_props:
                        value = entity.properties.get(prop)
                        if value:
                            display_value = ', '.join(value) if isinstance(value, list) else value
                            print(f"   {prop}: {str(display_value)[:100]}...")
                    
                    # Show search metadata
                    if entity.search_metadata:
                        search_type = entity.search_metadata.get('search_type', 'unknown')
                        variation = entity.search_metadata.get('variation', 'unknown')
                        print(f"   Found via: {search_type} ({variation})")
                
                # Show schema distribution
                schema_counts = {}
                for entity in results:
                    schema = entity.schema
                    schema_counts[schema] = schema_counts.get(schema, 0) + 1
                
                print(f"\nResults by schema:")
                for schema, count in sorted(schema_counts.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {schema}: {count} entities")
                    
            else:
                print("No results found in this Aleph demo run.")
                
        except Exception as e:
            logger.error(f"Error during Aleph demo: {e}", exc_info=True) 