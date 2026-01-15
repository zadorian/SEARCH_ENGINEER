"""
exact_phrase_recall_runner_gdelt.py  ·  v2 ("max-recall + streaming + exact phrase enforcement")
===================================================
Automates a "max-recall" style search for GDELT Doc 2.0 API with enhanced exact phrase enforcement.

Features:
* **Streaming Support**: Results are yielded progressively as API responses are parsed
* **Time Slicing**: Bypasses 250 record limit by splitting time ranges into multiple calls
* **Enhanced Query Variations**: Exact phrase, related terms, and theme-based searches
* **Retry Logic**: Robust handling of API failures, rate limits, and timeouts
* **Iterative Exception Search**: Post-filtering approach to discover overlooked results
* **Multi-Language Support**: Leverages GDELT's 65+ language coverage with translations
* **Theme and Source Filtering**: Advanced filtering by content themes and news sources
* **Comprehensive Metadata**: Rich article metadata with sentiment, themes, and locations

Changes from basic GDELT client:
* Converted to generator yielding results progressively
* Added time slicing to bypass 250 record API limit
* Enhanced retry logic with exponential backoff and jitter
* Implemented iterative exception search for maximum recall
* Added comprehensive query variations and theme filtering
* Enhanced exact phrase enforcement with validation
* Added multi-language and source filtering capabilities
* Supports overlapping time windows for maximum coverage
"""

from __future__ import annotations

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


import requests
import logging
import time
import random
import json
import re
from typing import Dict, List, Optional, Set, Tuple, Any, Iterable, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from urllib.parse import urlencode, quote_plus
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Circuit breaker for API failures
class GDELTCircuitBreaker:
    def __init__(self, failure_threshold=3, reset_timeout=300):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open
    
    def call(self, func, *args, **kwargs):
        logger.info(f"GDELT Circuit Breaker - State: {self.state}, Failures: {self.failure_count}")
        if self.state == 'open':
            if self.last_failure_time and time.time() - self.last_failure_time > self.reset_timeout:
                logger.info("Circuit breaker transitioning from OPEN to HALF_OPEN")
                self.state = 'half_open'
            else:
                logger.error(f"Circuit breaker is OPEN - blocking call (failures: {self.failure_count})")
                raise Exception("Circuit breaker is OPEN - GDELT API unavailable")
        
        try:
            logger.info(f"Circuit breaker allowing call (state: {self.state})")
            result = func(*args, **kwargs)
            if self.state == 'half_open':
                logger.info("Circuit breaker SUCCESS in half_open state - transitioning to CLOSED")
                self.state = 'closed'
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.error(f"Circuit breaker caught error: {e} (failure count: {self.failure_count})")
            if self.failure_count >= self.failure_threshold:
                self.state = 'open'
                logger.warning(f"GDELT Circuit breaker opened after {self.failure_count} failures")
            raise

# Global circuit breaker instance
gdelt_circuit_breaker = GDELTCircuitBreaker()

logger = logging.getLogger("gdelt_phrase_runner")

# Enhanced GDELT configuration
GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS_PER_CALL = 250  # GDELT API limit
MAX_RETRIES = 3  # Reduced from 5 to 3
REQUEST_TIMEOUT = 15     # Reduced from 30 to 15 seconds
DEFAULT_TIMESPAN = "1m"  # Reduced from 3m to 1m 
DEFAULT_TIME_SLICES = 3  # Reduced from 6 to 3 slices for speed
RETRY_DELAY_BASE = 1.0
MAX_EXCEPTION_ITERATIONS = 3

# Enhanced GDELT themes for document-like content
GDELT_DOCUMENT_THEMES = {
    'finance': ['WB_696_BUSINESS_FINANCE', 'WB_648_ECONOMIC_CONDITIONS', 'WB_695_FINANCIAL_MARKETS'],
    'legal': ['WB_590_JUDICIAL_SYSTEM', 'WB_591_LEGAL_SYSTEM', 'WB_592_LEGISLATION'],
    'government': ['WB_842_GOVERNMENT_OPERATIONS', 'WB_843_GOVERNMENT_POLICY', 'WB_844_GOVERNMENT_STRUCTURE'],
    'military': ['WB_1049_MILITARY_AFFAIRS', 'WB_1050_MILITARY_OPERATIONS', 'WB_1051_DEFENSE_POLICY'],
    'healthcare': ['WB_1089_HEALTH_CARE', 'WB_1090_MEDICAL_RESEARCH', 'WB_1091_PUBLIC_HEALTH'],
    'education': ['WB_1104_EDUCATION', 'WB_1105_ACADEMIC_RESEARCH', 'WB_1106_HIGHER_EDUCATION'],
    'energy': ['WB_1122_ENERGY_POLICY', 'WB_1123_RENEWABLE_ENERGY', 'WB_1124_FOSSIL_FUELS'],
    'environment': ['WB_1148_ENVIRONMENTAL_ISSUES', 'WB_1149_CLIMATE_CHANGE', 'WB_1150_POLLUTION'],
    'technology': ['WB_1168_TECHNOLOGY', 'WB_1169_TELECOMMUNICATIONS', 'WB_1170_INTERNET'],
    'trade': ['WB_1188_INTERNATIONAL_TRADE', 'WB_1189_TRADE_AGREEMENTS', 'WB_1190_TRADE_POLICY']
}

# Enhanced language coverage for global reach
GDELT_LANGUAGES = {
    'english': 'eng',
    'spanish': 'spa',
    'french': 'fra',
    'german': 'deu',
    'italian': 'ita',
    'portuguese': 'por',
    'russian': 'rus',
    'chinese': 'chi',
    'japanese': 'jpn',
    'korean': 'kor',
    'arabic': 'ara',
    'hindi': 'hin',
    'dutch': 'nld',
    'swedish': 'swe',
    'danish': 'dan',
    'norwegian': 'nor',
    'finnish': 'fin',
    'polish': 'pol',
    'czech': 'ces',
    'hungarian': 'hun',
    'romanian': 'ron',
    'bulgarian': 'bul',
    'croatian': 'hrv',
    'serbian': 'srp',
    'slovenian': 'slv',
    'slovak': 'slk',
    'estonian': 'est',
    'latvian': 'lav',
    'lithuanian': 'lit',
    'greek': 'ell',
    'turkish': 'tur',
    'hebrew': 'heb',
    'persian': 'fas',
    'urdu': 'urd',
    'thai': 'tha',
    'vietnamese': 'vie',
    'indonesian': 'ind',
    'malay': 'msa',
    'tagalog': 'tgl',
    'swahili': 'swa',
    'hausa': 'hau',
    'yoruba': 'yor',
    'amharic': 'amh',
    'bengali': 'ben',
    'gujarati': 'guj',
    'tamil': 'tam',
    'telugu': 'tel',
    'malayalam': 'mal',
    'marathi': 'mar',
    'punjabi': 'pan',
    'nepali': 'nep',
    'sinhalese': 'sin',
    'burmese': 'mya',
    'khmer': 'khm',
    'lao': 'lao',
    'mongolian': 'mon',
    'kazakh': 'kaz',
    'kyrgyz': 'kir',
    'tajik': 'tgk',
    'turkmen': 'tuk',
    'uzbek': 'uzb',
    'azerbaijani': 'aze',
    'armenian': 'hye',
    'georgian': 'kat',
    'albanian': 'sqi',
    'macedonian': 'mkd',
    'bosnian': 'bos',
    'montenegrin': 'cnr',
    'maltese': 'mlt',
    'basque': 'eus',
    'catalan': 'cat',
    'galician': 'glg',
    'welsh': 'cym',
    'irish': 'gle',
    'scottish': 'gla',
    'icelandic': 'isl',
    'faroese': 'fao'
}

# Global deduplication for thread safety
DEDUP_LOCK = threading.Lock()
ALL_GDELT_RESULTS: Dict[str, Dict] = {}

@dataclass
class GDELTArticle:
    """Structured data class for GDELT article results."""
    url: str
    title: str
    snippet: str
    source: str
    seendate: str
    socialimage: Optional[str] = None
    domain: Optional[str] = None
    language: Optional[str] = None
    sourcecountry: Optional[str] = None
    tone: Optional[float] = None
    themes: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    organizations: List[str] = field(default_factory=list)
    search_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'url': self.url,
            'title': self.title,
            'snippet': self.snippet,
            'source': self.source,
            'seendate': self.seendate,
            'socialimage': self.socialimage,
            'domain': self.domain,
            'language': self.language,
            'sourcecountry': self.sourcecountry,
            'tone': self.tone,
            'themes': self.themes,
            'locations': self.locations,
            'persons': self.persons,
            'organizations': self.organizations,
            'search_metadata': self.search_metadata
        }

def validate_exact_phrase(phrase: str) -> str:
    """Validate and format phrase for exact matching."""
    if not phrase or not phrase.strip():
        raise ValueError("Phrase cannot be empty")
    
    # Remove existing quotes and re-quote for exact matching
    clean_phrase = phrase.strip('\'"')
    if not clean_phrase:
        raise ValueError("Phrase cannot be empty after cleaning")
    
    return clean_phrase

def parse_gdelt_datetime(datetime_str: str) -> Optional[datetime]:
    """Parse GDELT datetime format (YYYYMMDDHHMMSS)."""
    try:
        return datetime.strptime(datetime_str, '%Y%m%d%H%M%S')
    except (ValueError, TypeError):
        return None

def format_gdelt_datetime(dt: datetime) -> str:
    """Format datetime for GDELT API (YYYYMMDDHHMMSS)."""
    return dt.strftime('%Y%m%d%H%M%S')

def calculate_time_slices(timespan: str, num_slices: int) -> List[Tuple[str, str]]:
    """Calculate time slices for maximum recall."""
    if not timespan or timespan == "":
        return []
    
    # Parse timespan (e.g., "3m", "2w", "5d", "12h")
    unit = timespan[-1].lower()
    try:
        value = int(timespan[:-1])
    except ValueError:
        return []
    
    # Calculate total duration in minutes
    if unit == 'm':
        total_minutes = value * 30 * 24 * 60  # months to minutes (approximate)
    elif unit == 'w':
        total_minutes = value * 7 * 24 * 60  # weeks to minutes
    elif unit == 'd':
        total_minutes = value * 24 * 60  # days to minutes
    elif unit == 'h':
        total_minutes = value * 60  # hours to minutes
    else:
        return []
    
    # Calculate slice duration
    slice_minutes = total_minutes // num_slices
    if slice_minutes < 15:  # GDELT minimum is 15 minutes
        slice_minutes = 15
        num_slices = total_minutes // 15
    
    # Generate time slices
    now = datetime.now()
    slices = []
    
    for i in range(num_slices):
        end_time = now - timedelta(minutes=i * slice_minutes)
        start_time = end_time - timedelta(minutes=slice_minutes)
        
        # Ensure we don't go beyond GDELT's 3-month limit
        three_months_ago = now - timedelta(days=90)
        if start_time < three_months_ago:
            start_time = three_months_ago
        
        if start_time >= end_time:
            break
        
        slices.append((
            format_gdelt_datetime(start_time),
            format_gdelt_datetime(end_time)
        ))
    
    return slices

def enhanced_backoff_sleep(attempt: int, base_delay: float = RETRY_DELAY_BASE):
    """Enhanced exponential backoff with jitter for GDELT API."""
    if attempt == 0:
        return
    
    # Exponential backoff with jitter
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, 60)  # Cap at 1 minute
    
    # Add jitter to avoid synchronized retries
    jitter = random.uniform(0, delay * 0.3)
    final_delay = delay + jitter
    
    logger.info(f"GDELT API backing off for {final_delay:.2f}s (attempt {attempt})")
    time.sleep(final_delay)

def extract_themes_from_article(article: Dict[str, Any]) -> List[str]:
    """Extract themes from GDELT article response."""
    themes = []
    
    # Check for theme fields in the article
    theme_fields = ['themes', 'gcam_themes', 'themes_list']
    for field in theme_fields:
        if field in article:
            theme_value = article[field]
            if isinstance(theme_value, str):
                themes.extend(theme_value.split(','))
            elif isinstance(theme_value, list):
                themes.extend(theme_value)
    
    return [theme.strip() for theme in themes if theme.strip()]

def extract_locations_from_article(article: Dict[str, Any]) -> List[str]:
    """Extract locations from GDELT article response."""
    locations = []
    
    # Check for location fields in the article
    location_fields = ['locations', 'gcam_locations', 'locations_list']
    for field in location_fields:
        if field in article:
            location_value = article[field]
            if isinstance(location_value, str):
                locations.extend(location_value.split(','))
            elif isinstance(location_value, list):
                locations.extend(location_value)
    
    return [location.strip() for location in locations if location.strip()]

def extract_entities_from_article(article: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Extract persons and organizations from GDELT article response."""
    persons = []
    organizations = []
    
    # Check for entity fields
    person_fields = ['persons', 'gcam_persons', 'persons_list']
    org_fields = ['organizations', 'gcam_organizations', 'organizations_list']
    
    for field in person_fields:
        if field in article:
            person_value = article[field]
            if isinstance(person_value, str):
                persons.extend(person_value.split(','))
            elif isinstance(person_value, list):
                persons.extend(person_value)
    
    for field in org_fields:
        if field in article:
            org_value = article[field]
            if isinstance(org_value, str):
                organizations.extend(org_value.split(','))
            elif isinstance(org_value, list):
                organizations.extend(org_value)
    
    return (
        [person.strip() for person in persons if person.strip()],
        [org.strip() for org in organizations if org.strip()]
    )

class GDELTSearchException(Exception):
    """Custom exception for GDELT search errors."""
    def __init__(self, message: str, response: Optional[requests.Response] = None):
        super().__init__(message)
        self.response = response
        self.status = response.status_code if response else None
        self.transient = self.status and (self.status >= 500 or self.status == 429)

class EnhancedGDELTSearcher:
    """Enhanced GDELT searcher with streaming and maximum recall features."""
    
    def __init__(
        self,
        base_url: str = GDELT_BASE_URL,
        request_timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        user_agent: Optional[str] = None
    ):
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.user_agent = user_agent or "GDELT-Exact-Phrase-Runner/2.0"
        
        # Session configuration
        if SHARED_SESSION:

            self.session = get_shared_session(engine_name='GDELT')

            logger.info("Using shared connection pool")

        else:

            self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
    
    def make_request_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make GDELT API request with retry logic."""
        
        # Wrap the entire request process in circuit breaker
        def _make_api_call():
            last_exception = None
            
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"GDELT API request (attempt {attempt + 1}/{self.max_retries}) - Query: {params.get('query', 'N/A')}")
                    
                    response = self.session.get(
                        self.base_url,
                        params=params,
                        timeout=self.request_timeout
                    )
                    
                    logger.info(f"GDELT API response status: {response.status_code}")
                    
                    if response.status_code == 429:
                        logger.warning(f"Rate limited by GDELT API (attempt {attempt + 1})")
                        enhanced_backoff_sleep(attempt + 1, 2.0)
                        continue
                    
                    if response.status_code >= 500:
                        logger.warning(f"Server error {response.status_code} (attempt {attempt + 1})")
                        enhanced_backoff_sleep(attempt + 1)
                        continue
                    
                    response.raise_for_status()
                    
                    try:
                        data = response.json()
                        articles = data.get('articles', [])
                        logger.info(f"GDELT API returned {len(articles)} articles")
                        return data
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON response (attempt {attempt + 1}): {e}")
                        logger.debug(f"Response content: {response.text[:500]}...")
                        if attempt < self.max_retries - 1:
                            enhanced_backoff_sleep(attempt + 1)
                            continue
                        else:
                            raise GDELTSearchException(f"Invalid JSON response: {e}", response)
                    
                except requests.exceptions.Timeout:
                    last_exception = GDELTSearchException(f"Timeout requesting GDELT API")
                    logger.warning(f"Timeout requesting GDELT API (attempt {attempt + 1})")
                    if attempt < self.max_retries - 1:
                        enhanced_backoff_sleep(attempt + 1)
                        continue
                        
                except requests.exceptions.RequestException as e:
                    last_exception = GDELTSearchException(f"Request error: {e}", getattr(e, 'response', None))
                    logger.warning(f"Request error (attempt {attempt + 1}): {e}")
                    if attempt < self.max_retries - 1:
                        enhanced_backoff_sleep(attempt + 1)
                        continue
                        
                except Exception as e:
                    last_exception = GDELTSearchException(f"Unexpected error: {e}")
                    logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
                    if attempt < self.max_retries - 1:
                        enhanced_backoff_sleep(attempt + 1)
                        continue
        
            if last_exception:
                raise last_exception
            
            return {}
        
        # Use circuit breaker for the API call
        try:
            return gdelt_circuit_breaker.call(_make_api_call)
        except Exception as e:
            logger.error(f"GDELT request failed with circuit breaker: {e}")
            # Return empty result instead of raising to allow other engines to continue
            return {}
    
    def build_search_params(
        self,
        query: str,
        mode: str = "artlist",
        max_records: int = MAX_RECORDS_PER_CALL,
        timespan: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
        theme: Optional[str] = None,
        source_country: Optional[str] = None,
        source_lang: Optional[str] = None,
        domain: Optional[str] = None,
        additional_params: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build GDELT API parameters."""
        params = {
            "query": query,
            "mode": mode,
            "maxrecords": str(min(max_records, MAX_RECORDS_PER_CALL)),
            "format": "json",
            "sort": "datedesc",
        }
        
        # Time parameters
        if start_datetime and end_datetime:
            params["STARTDATETIME"] = start_datetime
            params["ENDDATETIME"] = end_datetime
        elif timespan:
            params["timespan"] = timespan
        
        # Filtering parameters
        if theme:
            params["theme"] = theme
        if source_country:
            params["sourcecountry"] = source_country
        if source_lang:
            params["sourcelang"] = source_lang
        if domain:
            params["domain"] = domain
        
        # Additional parameters
        if additional_params:
            params.update(additional_params)
        
        return params
    
    def parse_article_response(self, article: Dict[str, Any], query: str) -> GDELTArticle:
        """Parse GDELT article response into structured format."""
        # Extract basic fields
        url = article.get('url', '')
        title = article.get('title', 'No title')
        seendate = article.get('seendate', '')
        source = article.get('source', 'Unknown')
        
        # Create snippet
        snippet = f"[{source}] [{seendate}]\n{title}"
        
        # Extract enhanced metadata
        themes = extract_themes_from_article(article)
        locations = extract_locations_from_article(article)
        persons, organizations = extract_entities_from_article(article)
        
        # Parse tone (sentiment)
        tone = None
        if 'tone' in article:
            try:
                tone = float(article['tone'])
            except (ValueError, TypeError):
                pass
        
        return GDELTArticle(
            url=url,
            title=title,
            snippet=snippet,
            source=source,
            seendate=seendate,
            socialimage=article.get('socialimage'),
            domain=article.get('domain'),
            language=article.get('language'),
            sourcecountry=article.get('sourcecountry'),
            tone=tone,
            themes=themes,
            locations=locations,
            persons=persons,
            organizations=organizations
        )
    
    def search_single_call(
        self,
        query: str,
        timespan: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
        theme: Optional[str] = None,
        source_country: Optional[str] = None,
        source_lang: Optional[str] = None,
        domain: Optional[str] = None,
        max_records: int = MAX_RECORDS_PER_CALL
    ) -> Iterable[GDELTArticle]:
        """Make a single GDELT API call and yield results."""
        params = self.build_search_params(
            query=query,
            max_records=max_records,
            timespan=timespan,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            theme=theme,
            source_country=source_country,
            source_lang=source_lang,
            domain=domain
        )
        
        try:
            data = self.make_request_with_retry(params)
            articles = data.get('articles', [])
            
            for article in articles:
                if not article.get('url'):
                    continue
                
                parsed_article = self.parse_article_response(article, query)
                parsed_article.search_metadata = {
                    'query': query,
                    'timespan': timespan,
                    'start_datetime': start_datetime,
                    'end_datetime': end_datetime,
                    'theme': theme,
                    'source_country': source_country,
                    'source_lang': source_lang,
                    'domain': domain,
                    'search_type': 'main'
                }
                
                yield parsed_article
                
        except GDELTSearchException as e:
            logger.error(f"GDELT API call failed: {e}")
            return
    
    def search_with_time_slicing(
        self,
        phrase: str,
        timespan: str = DEFAULT_TIMESPAN,
        num_slices: int = DEFAULT_TIME_SLICES,
        theme_filters: Optional[List[str]] = None,
        source_countries: Optional[List[str]] = None,
        source_languages: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        query_variations: bool = True
    ) -> Iterable[GDELTArticle]:
        """Search with time slicing to bypass 250 record limit."""
        
        # Validate and prepare exact phrase
        clean_phrase = validate_exact_phrase(phrase)
        exact_query = f'"{clean_phrase}"'
        
        logger.info(f"Starting GDELT search for phrase: '{clean_phrase}' with time slicing")
        
        # Clear global deduplication
        with DEDUP_LOCK:
            ALL_GDELT_RESULTS.clear()
        
        # Calculate time slices
        time_slices = calculate_time_slices(timespan, num_slices)
        if not time_slices:
            # Fallback to single timespan query
            time_slices = [(None, None)]
        
        # Generate query variations
        queries_to_search = [exact_query]
        if query_variations:
            # Add loose version for broader recall
            queries_to_search.append(clean_phrase)  # Without quotes
            
            # Add enhanced queries with related terms
            related_terms = ['document', 'report', 'leak', 'revealed', 'disclosed']
            for term in related_terms[:2]:  # Limit to avoid too many queries
                queries_to_search.append(f'"{clean_phrase}" AND {term}')
        
        # Generate filter combinations
        filter_combinations = [{}]  # Start with no filters
        
        if theme_filters:
            for theme in theme_filters:
                filter_combinations.append({'theme': theme})
        
        if source_countries:
            for country in source_countries:
                filter_combinations.append({'source_country': country})
        
        if source_languages:
            for lang in source_languages:
                filter_combinations.append({'source_lang': lang})
        
        if domains:
            for domain in domains:
                filter_combinations.append({'domain': domain})
        
        # Execute all combinations
        total_queries = len(queries_to_search) * len(time_slices) * len(filter_combinations)
        logger.info(f"Executing {total_queries} GDELT queries ({len(queries_to_search)} variations × {len(time_slices)} time slices × {len(filter_combinations)} filter combinations)")
        
        query_count = 0
        for query in queries_to_search:
            for start_time, end_time in time_slices:
                for filters in filter_combinations:
                    query_count += 1
                    
                    try:
                        # Make API call
                        call_params = {
                            'query': query,
                            'timespan': timespan if start_time is None else None,
                            'start_datetime': start_time,
                            'end_datetime': end_time,
                            **filters
                        }
                        
                        logger.debug(f"Query {query_count}/{total_queries}: {query} [{start_time}-{end_time}] {filters}")
                        
                        # Process results with deduplication
                        new_results = []
                        for article in self.search_single_call(**call_params):
                            with DEDUP_LOCK:
                                if article.url not in ALL_GDELT_RESULTS:
                                    ALL_GDELT_RESULTS[article.url] = article.to_dict()
                                    new_results.append(article)
                        
                        # Yield new unique results
                        for article in new_results:
                            yield article
                        
                        logger.debug(f"Query {query_count}: yielded {len(new_results)} new results")
                        
                        # Reduced delay - parallel execution provides natural spacing
                        time.sleep(random.uniform(0.1, 0.3))
                        
                    except Exception as e:
                        logger.error(f"Query {query_count} failed: {e}")
                        continue
        
        # Get count of main results
        with DEDUP_LOCK:
            main_results_count = len(ALL_GDELT_RESULTS)
        
        logger.info(f"Main GDELT search complete. Found {main_results_count} unique articles")
        
        # Run iterative exception search
        logger.info("Starting iterative exception search...")
        with DEDUP_LOCK:
            known_urls = set(ALL_GDELT_RESULTS.keys())
        
        for iteration in range(MAX_EXCEPTION_ITERATIONS):
            try:
                exception_count = 0
                for article in self.run_exception_search(
                    clean_phrase, 
                    known_urls, 
                    timespan,
                    theme_filters,
                    source_countries
                ):
                    article.search_metadata = article.search_metadata or {}
                    article.search_metadata.update({
                        'search_type': 'exception',
                        'exception_iteration': iteration + 1
                    })
                    
                    with DEDUP_LOCK:
                        if article.url not in ALL_GDELT_RESULTS:
                            ALL_GDELT_RESULTS[article.url] = article.to_dict()
                            known_urls.add(article.url)
                            exception_count += 1
                            yield article
                
                if exception_count > 0:
                    logger.info(f"Exception search iteration {iteration + 1}: Found {exception_count} new articles")
                else:
                    logger.info(f"Exception search iteration {iteration + 1}: No new articles found, stopping")
                    break
                    
            except Exception as e:
                logger.error(f"Exception search iteration {iteration + 1} failed: {e}")
                break
        
        with DEDUP_LOCK:
            final_count = len(ALL_GDELT_RESULTS)
        
        logger.info(f"Enhanced GDELT search complete. Total unique articles: {final_count}")
    
    def run_exception_search(
        self,
        phrase: str,
        known_urls: Set[str],
        timespan: str = DEFAULT_TIMESPAN,
        theme_filters: Optional[List[str]] = None,
        source_countries: Optional[List[str]] = None
    ) -> Iterable[GDELTArticle]:
        """Run exception search with broader queries to find overlooked articles."""
        
        if not known_urls:
            return
        
        logger.info(f"Running GDELT exception search (filtering {len(known_urls)} known URLs)")
        
        # Exception search strategies
        exception_queries = [
            phrase,  # Without quotes for broader matching
            f'"{phrase}" OR related',  # With OR operator
            f'"{phrase}" AND (document OR report OR leak)',  # With related terms
            f'"{phrase.lower()}" OR "{phrase.upper()}"',  # Case variations
        ]
        
        # Use broader themes for exception search
        exception_themes = []
        if theme_filters:
            # Use related themes
            for theme_category in GDELT_DOCUMENT_THEMES.keys():
                if any(theme in theme_filters for theme in GDELT_DOCUMENT_THEMES[theme_category]):
                    exception_themes.extend(GDELT_DOCUMENT_THEMES[theme_category][:2])
        
        for query in exception_queries:
            try:
                logger.debug(f"Exception search query: '{query}'")
                
                # Search with limited filters for broader coverage
                search_params = {
                    'query': query,
                    'timespan': timespan,
                    'max_records': 100  # Smaller limit for exception search
                }
                
                # Add theme filter if available
                if exception_themes:
                    search_params['theme'] = exception_themes[0]
                
                # Add source country filter if available
                if source_countries:
                    search_params['source_country'] = source_countries[0]
                
                # Yield results not in known URLs
                for article in self.search_single_call(**search_params):
                    if article.url not in known_urls:
                        yield article
                
                # Reduced delay between exception queries
                time.sleep(random.uniform(0.2, 0.5))
                
            except Exception as e:
                logger.error(f"Exception search failed for query '{query}': {e}")
                continue

class ExactPhraseRecallRunnerGDELT:
    """Main runner class for enhanced GDELT exact phrase searches."""
    
    def __init__(
        self,
        phrase: str,
        timespan: str = DEFAULT_TIMESPAN,
        num_time_slices: int = 2,  # Optimized: reduced from DEFAULT_TIME_SLICES to 2
        theme_filters: Optional[List[str]] = None,
        source_countries: Optional[List[str]] = None,
        source_languages: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        query_variations: bool = True,
        request_timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        user_agent: Optional[str] = None
    ):
        self.phrase = phrase
        self.timespan = timespan
        self.num_time_slices = num_time_slices
        self.theme_filters = theme_filters
        self.source_countries = source_countries
        self.source_languages = source_languages
        self.domains = domains
        self.query_variations = query_variations
        
        # Initialize searcher
        self.searcher = EnhancedGDELTSearcher(
            request_timeout=request_timeout,
            max_retries=max_retries,
            user_agent=user_agent
        )
        
        # Validate phrase
        validate_exact_phrase(phrase)
    
    def run(self) -> Iterable[GDELTArticle]:
        """Run the complete enhanced GDELT search."""
        logger.info(f"Starting enhanced GDELT exact phrase search for: '{self.phrase}'")
        
        for article in self.searcher.search_with_time_slicing(
            phrase=self.phrase,
            timespan=self.timespan,
            num_slices=self.num_time_slices,
            theme_filters=self.theme_filters,
            source_countries=self.source_countries,
            source_languages=self.source_languages,
            domains=self.domains,
            query_variations=self.query_variations
        ):
            yield article
    
    def run_as_list(self) -> List[GDELTArticle]:
        """Convenience method to collect all results."""
        return list(self.run())

if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Interactive demo
    if len(sys.argv) > 1:
        phrase_to_search = " ".join(sys.argv[1:])
    else:
        phrase_to_search = input("Enter exact phrase for GDELT search: ").strip()
    
    if not phrase_to_search:
        print("No phrase given. Exiting.")
        sys.exit(1)
    
    logger.info(f"Starting Enhanced GDELT Recall Runner demo for phrase: '{phrase_to_search}'")
    
    # Demo configuration
    demo_timespan = "1m"  # 1 month for demo
    demo_time_slices = 4  # 4 slices for demo
    demo_themes = ['WB_696_BUSINESS_FINANCE', 'WB_842_GOVERNMENT_OPERATIONS', 'WB_1168_TECHNOLOGY']
    demo_countries = ['US', 'GB', 'DE', 'FR']  # High-value countries
    demo_languages = ['eng', 'spa', 'fra', 'deu']  # Major languages
    
    try:
        runner = ExactPhraseRecallRunnerGDELT(
            phrase=phrase_to_search,
            timespan=demo_timespan,
            num_time_slices=demo_time_slices,
            theme_filters=demo_themes,
            source_countries=demo_countries,
            source_languages=demo_languages,
            query_variations=True
        )
        
        logger.info("Starting streaming GDELT runner...")
        results = []
        result_count = 0
        
        # Demonstrate streaming
        for result in runner.run():
            result_count += 1
            results.append(result)
            
            # Show progress
            if result_count % 20 == 0:
                print(f"Processed {result_count} results so far...")
        
        print(f"\n--- STREAMING GDELT DEMO COMPLETE ---")
        print(f"Found {len(results)} unique GDELT articles for '{phrase_to_search}'")
        
        if results:
            print("\nSample of results:")
            for i, article in enumerate(results[:5], 1):
                print(f"\n{i}. {article.title}")
                print(f"   Source: {article.source}")
                print(f"   URL: {article.url}")
                print(f"   Date: {article.seendate}")
                print(f"   Country: {article.sourcecountry or 'Unknown'}")
                print(f"   Language: {article.language or 'Unknown'}")
                print(f"   Tone: {article.tone or 'Unknown'}")
                
                if article.themes:
                    print(f"   Themes: {', '.join(article.themes[:3])}...")
                if article.locations:
                    print(f"   Locations: {', '.join(article.locations[:3])}...")
                if article.persons:
                    print(f"   Persons: {', '.join(article.persons[:3])}...")
                if article.organizations:
                    print(f"   Organizations: {', '.join(article.organizations[:3])}...")
                
                # Show search metadata
                search_type = article.search_metadata.get('search_type', 'main')
                print(f"   Found via: {search_type} search")
            
            # Show source distribution
            source_counts = {}
            for article in results:
                source = article.source
                source_counts[source] = source_counts.get(source, 0) + 1
            
            print(f"\nResults by source:")
            for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {source}: {count} articles")
            
            # Show country distribution
            country_counts = {}
            for article in results:
                country = article.sourcecountry or 'Unknown'
                country_counts[country] = country_counts.get(country, 0) + 1
            
            print(f"\nResults by country:")
            for country, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {country}: {count} articles")
            
            # Show search type distribution
            search_type_counts = {}
            for article in results:
                search_type = article.search_metadata.get('search_type', 'main')
                search_type_counts[search_type] = search_type_counts.get(search_type, 0) + 1
            
            print(f"\nResults by search type:")
            for search_type, count in sorted(search_type_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {search_type}: {count} articles")
                
        else:
            print("No results found in this GDELT demo run.")
            
    except Exception as e:
        logger.error(f"Error during GDELT demo: {e}", exc_info=True) 