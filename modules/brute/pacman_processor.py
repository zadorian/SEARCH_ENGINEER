"""
BRUTE → JESTER → PACMAN Processing Pipeline

As results stream in from brute:
1. Queue URLs for scraping via JESTER (tiered: A→B→C→D)
2. Process scraped content through PACMAN extractors
3. Attach extracted entities to results for filtering/display

Extracted entities:
- Persons (names, roles)
- Companies (names, registration numbers)
- Locations/Jurisdictions (countries, cities, ISO codes)
- Temporal (dates, periods, eras)
- Identifiers (LEI, IBAN, SWIFT, VAT, crypto)
- Contacts (emails, phones)
- Red flags (tripwire detection)
"""

import asyncio
import logging
import queue
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# JESTER Import (Scraping)
# ─────────────────────────────────────────────────────────────────
try:
    from modules.jester import Jester
    JESTER_AVAILABLE = True
except ImportError:
    logger.warning("JESTER not available - scraping disabled")
    JESTER_AVAILABLE = False
    Jester = None

# ─────────────────────────────────────────────────────────────────
# PACMAN Imports (Entity Extraction)
# ─────────────────────────────────────────────────────────────────
try:
    from modules.pacman.entity_extractors.locations import extract_all_locations
    from modules.pacman.entity_extractors.persons import extract_persons
    from modules.pacman.entity_extractors.companies import extract_companies, SUFFIXES as COMPANY_SUFFIXES
    from modules.pacman.temporal_hierarchy import derive_temporal_hierarchy, extract_periods_from_text
    from modules.pacman.patterns.identifiers import ALL_IDENTIFIERS
    from modules.pacman.patterns.contacts import ALL_CONTACTS
    from modules.pacman.patterns.crypto import ALL_CRYPTO
    from modules.pacman.patterns.company_numbers import ALL_COMPANY_NUMBERS
    PACMAN_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PACMAN not fully available: {e}")
    PACMAN_AVAILABLE = False
    ALL_COMPANY_NUMBERS = {}
    COMPANY_SUFFIXES = set()

# Semantic concept detection (ownership, compliance red flags, sectors)
_domain_embedder = None
SEMANTIC_AVAILABLE = False

try:
    from modules.pacman.embeddings.domain_embedder import DomainEmbedder
    SEMANTIC_AVAILABLE = True
except ImportError:
    logger.debug("DomainEmbedder not available - semantic detection disabled")


@dataclass
class ExtractedEntities:
    """All entities extracted from a result's content."""
    url: str

    # Core entities
    persons: List[Dict] = field(default_factory=list)
    companies: List[Dict] = field(default_factory=list)
    locations: List[Dict] = field(default_factory=list)

    # Temporal
    dates: List[Dict] = field(default_factory=list)
    periods: List[tuple] = field(default_factory=list)
    temporal_focus: Optional[str] = None  # historical, current, future

    # Company designations (legal suffixes grouped by type)
    company_designations: Dict[str, List[str]] = field(default_factory=dict)  # GMBH: [companies], LTD: [companies], etc.

    # Identifiers
    identifiers: Dict[str, List[str]] = field(default_factory=dict)  # LEI, IBAN, SWIFT, VAT
    company_numbers: Dict[str, List[str]] = field(default_factory=dict)  # UK_CRN, DE_HRB, NL_KVK, etc.
    crypto_addresses: Dict[str, List[str]] = field(default_factory=dict)  # BTC, ETH, etc.

    # Contacts
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)

    # Red flags
    red_flags: List[Dict] = field(default_factory=list)

    # Semantic concepts (via embedding similarity)
    semantic_concepts: List[Dict] = field(default_factory=list)  # beneficial_ownership, sanctions_exposure, etc.
    concept_categories: Dict[str, int] = field(default_factory=dict)  # ownership: 2, compliance_red_flag: 3

    # Metadata
    scrape_success: bool = False
    scrape_method: str = ""
    content_length: int = 0
    extraction_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'persons': self.persons,
            'companies': self.companies,
            'company_designations': self.company_designations,
            'locations': self.locations,
            'dates': self.dates,
            'periods': self.periods,
            'temporal_focus': self.temporal_focus,
            'identifiers': self.identifiers,
            'company_numbers': self.company_numbers,
            'crypto_addresses': self.crypto_addresses,
            'emails': self.emails,
            'phones': self.phones,
            'red_flags': self.red_flags,
            'semantic_concepts': self.semantic_concepts,
            'concept_categories': self.concept_categories,
            'scrape_success': self.scrape_success,
            'scrape_method': self.scrape_method,
            'content_length': self.content_length,
        }

    def has_entities(self) -> bool:
        """Check if any entities were extracted."""
        return bool(
            self.persons or self.companies or self.locations or
            self.identifiers or self.company_numbers or self.company_designations or
            self.emails or self.phones or self.crypto_addresses
        )


class PacmanProcessor:
    """
    Processes BRUTE results through JESTER (scrape) + PACMAN (extract).

    Runs as background threads that:
    1. Take URLs from scrape queue
    2. Scrape via JESTER
    3. Extract entities via PACMAN
    4. Callback with extracted entities
    """

    def __init__(
        self,
        max_concurrent_scrapes: int = 20,
        max_queue_size: int = 1000,
        on_extraction_complete: Optional[Callable[[str, ExtractedEntities], None]] = None
    ):
        self.max_concurrent_scrapes = max_concurrent_scrapes
        self.on_extraction_complete = on_extraction_complete

        # Queues
        self.scrape_queue = queue.Queue(maxsize=max_queue_size)
        self.results: Dict[str, ExtractedEntities] = {}

        # State
        self._stop = False
        self._workers: List[threading.Thread] = []
        self._lock = threading.Lock()

        # Stats
        self.stats = {
            'queued': 0,
            'scraped': 0,
            'failed': 0,
            'extracted': 0,
        }

        # Initialize JESTER if available
        self.jester = None
        if JESTER_AVAILABLE:
            try:
                self.jester = Jester()
                logger.info("JESTER initialized for scraping")
            except Exception as e:
                logger.error(f"Failed to init JESTER: {e}")

    def start(self, num_workers: int = None):
        """Start background worker threads."""
        if num_workers is None:
            num_workers = min(self.max_concurrent_scrapes, 10)

        self._stop = False

        for i in range(num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"pacman-worker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)

        logger.info(f"PacmanProcessor started with {num_workers} workers")

    def stop(self):
        """Stop all workers."""
        self._stop = True
        for worker in self._workers:
            worker.join(timeout=5)
        self._workers = []
        logger.info("PacmanProcessor stopped")

    def queue_url(self, url: str, title: str = "", snippet: str = "", metadata: Dict = None):
        """Add URL to processing queue."""
        try:
            self.scrape_queue.put({
                'url': url,
                'title': title,
                'snippet': snippet,
                'metadata': metadata or {},
                'queued_at': datetime.now()
            }, timeout=1)

            with self._lock:
                self.stats['queued'] += 1

        except queue.Full:
            logger.warning(f"Scrape queue full, skipping {url}")

    def _worker_loop(self):
        """Worker thread: scrape → extract → callback."""
        while not self._stop:
            try:
                item = self.scrape_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            url = item['url']

            try:
                # Scrape via JESTER
                content = self._scrape_url(url)

                if content:
                    with self._lock:
                        self.stats['scraped'] += 1

                    # Extract entities via PACMAN
                    entities = self._extract_entities(url, content, item)

                    with self._lock:
                        self.results[url] = entities
                        self.stats['extracted'] += 1

                    # Callback
                    if self.on_extraction_complete:
                        self.on_extraction_complete(url, entities)
                else:
                    with self._lock:
                        self.stats['failed'] += 1

            except Exception as e:
                logger.warning(f"Processing failed for {url}: {e}")
                with self._lock:
                    self.stats['failed'] += 1

    def _scrape_url(self, url: str) -> Optional[str]:
        """Scrape URL via JESTER (sync wrapper for async)."""
        if not self.jester:
            return None

        try:
            # Run async scrape in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.jester.scrape(url))
                if result and result.text:
                    return result.text
                elif result and result.html:
                    # Extract text from HTML
                    return self._html_to_text(result.html)
            finally:
                loop.close()
        except Exception as e:
            logger.debug(f"Scrape failed for {url}: {e}")

        return None

    def _html_to_text(self, html: str) -> str:
        """Extract text from HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
                tag.decompose()
            return ' '.join(soup.get_text(separator=' ', strip=True).split())
        except:
            import re
            return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())

    def _extract_entities(self, url: str, content: str, item: Dict) -> ExtractedEntities:
        """Run all PACMAN extractors on content."""
        start_time = datetime.now()

        entities = ExtractedEntities(
            url=url,
            scrape_success=True,
            content_length=len(content)
        )

        if not PACMAN_AVAILABLE:
            return entities

        # Combine snippet + scraped content for richer extraction
        full_text = f"{item.get('title', '')} {item.get('snippet', '')} {content}"

        try:
            # Locations/Jurisdictions
            entities.locations = extract_all_locations(full_text, max_results=50)
        except Exception as e:
            logger.debug(f"Location extraction failed: {e}")

        try:
            # Persons
            entities.persons = extract_persons(full_text, max_results=50)
        except Exception as e:
            logger.debug(f"Person extraction failed: {e}")

        try:
            # Companies
            entities.companies = extract_companies(full_text, max_results=50)
            # Group by designation (legal suffix)
            for company in entities.companies:
                suffix = company.get('suffix')
                if suffix:
                    suffix_upper = suffix.upper()
                    if suffix_upper not in entities.company_designations:
                        entities.company_designations[suffix_upper] = []
                    entities.company_designations[suffix_upper].append(company.get('name', ''))
        except Exception as e:
            logger.debug(f"Company extraction failed: {e}")

        try:
            # Temporal
            temporal = derive_temporal_hierarchy(text=full_text)
            if temporal.content_years:
                entities.dates = [{'year': y} for y in temporal.content_years]
            entities.temporal_focus = temporal.temporal_focus
            entities.periods = extract_periods_from_text(full_text)
        except Exception as e:
            logger.debug(f"Temporal extraction failed: {e}")

        try:
            # Identifiers (LEI, IBAN, SWIFT, VAT)
            for id_type, pattern in ALL_IDENTIFIERS.items():
                matches = pattern.findall(full_text)
                if matches:
                    entities.identifiers[id_type] = list(set(matches))[:20]
        except Exception as e:
            logger.debug(f"Identifier extraction failed: {e}")

        try:
            # Company registration numbers (UK_CRN, DE_HRB, NL_KVK, etc.)
            for crn_type, pattern in ALL_COMPANY_NUMBERS.items():
                matches = pattern.findall(full_text)
                if matches:
                    # Some patterns return tuples, flatten them
                    flat_matches = []
                    for m in matches:
                        if isinstance(m, tuple):
                            flat_matches.append(' '.join(str(x) for x in m if x))
                        else:
                            flat_matches.append(str(m))
                    entities.company_numbers[crn_type] = list(set(flat_matches))[:10]
        except Exception as e:
            logger.debug(f"Company number extraction failed: {e}")

        try:
            # Contacts (email, phone)
            for contact_type, pattern in ALL_CONTACTS.items():
                matches = pattern.findall(full_text)
                if contact_type == 'EMAIL':
                    entities.emails = list(set(matches))[:20]
                elif 'PHONE' in contact_type and matches:
                    entities.phones.extend(matches)
            entities.phones = list(set(entities.phones))[:20]
        except Exception as e:
            logger.debug(f"Contact extraction failed: {e}")

        try:
            # Crypto addresses
            for crypto_type, pattern in ALL_CRYPTO.items():
                matches = pattern.findall(full_text)
                if matches:
                    entities.crypto_addresses[crypto_type] = list(set(matches))[:10]
        except Exception as e:
            logger.debug(f"Crypto extraction failed: {e}")

        # Semantic concept detection (ownership, compliance red flags, sectors)
        # This is expensive (embedding), so only run if content is substantial
        if SEMANTIC_AVAILABLE and len(full_text) > 500:
            try:
                global _domain_embedder
                if _domain_embedder is None:
                    _domain_embedder = DomainEmbedder()

                # Run async detect_concepts in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    concept_result = loop.run_until_complete(
                        _domain_embedder.detect_concepts(full_text[:8000])
                    )
                    entities.semantic_concepts = concept_result.get('detected', [])
                    entities.concept_categories = concept_result.get('categories', {})
                finally:
                    loop.close()
            except Exception as e:
                logger.debug(f"Semantic concept detection failed: {e}")

        entities.extraction_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return entities

    def get_entities(self, url: str) -> Optional[ExtractedEntities]:
        """Get extracted entities for a URL (if processed)."""
        return self.results.get(url)

    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        with self._lock:
            return dict(self.stats)


# ─────────────────────────────────────────────────────────────────
# Integration with BRUTE
# ─────────────────────────────────────────────────────────────────

_processor: Optional[PacmanProcessor] = None

def get_processor() -> PacmanProcessor:
    """Get singleton processor instance."""
    global _processor
    if _processor is None:
        _processor = PacmanProcessor()
        _processor.start()
    return _processor


def process_brute_result(result: Dict[str, Any]) -> None:
    """
    Queue a BRUTE result for PACMAN processing.

    Called from brute's _result_writer_thread for each new result.
    """
    processor = get_processor()
    processor.queue_url(
        url=result.get('url', ''),
        title=result.get('title', ''),
        snippet=result.get('aggregated_snippet', result.get('snippet', '')),
        metadata={
            'engine': result.get('engine', ''),
            'sources': result.get('sources', []),
        }
    )


def get_result_entities(url: str) -> Optional[Dict[str, Any]]:
    """
    Get extracted entities for a URL.

    Returns None if not yet processed.
    """
    processor = get_processor()
    entities = processor.get_entities(url)
    return entities.to_dict() if entities else None


# ─────────────────────────────────────────────────────────────────
# Entity-Based Filtering
# ─────────────────────────────────────────────────────────────────

def filter_by_location(results: List[Dict], iso_codes: List[str]) -> List[Dict]:
    """Filter results to those mentioning specific jurisdictions."""
    processor = get_processor()
    filtered = []

    iso_codes_upper = [c.upper() for c in iso_codes]

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities:
            result_isos = [loc.get('iso_code', '') for loc in entities.locations]
            if any(iso in iso_codes_upper for iso in result_isos):
                filtered.append(result)

    return filtered


def filter_by_person(results: List[Dict], name_pattern: str) -> List[Dict]:
    """Filter results mentioning a person name."""
    processor = get_processor()
    filtered = []
    name_lower = name_pattern.lower()

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities:
            for person in entities.persons:
                if name_lower in person.get('name', '').lower():
                    filtered.append(result)
                    break

    return filtered


def filter_by_company(results: List[Dict], company_pattern: str) -> List[Dict]:
    """Filter results mentioning a company name."""
    processor = get_processor()
    filtered = []
    pattern_lower = company_pattern.lower()

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities:
            for company in entities.companies:
                if pattern_lower in company.get('name', '').lower():
                    filtered.append(result)
                    break

    return filtered


def filter_by_date_range(results: List[Dict], start_year: int, end_year: int) -> List[Dict]:
    """Filter results discussing a specific time period."""
    processor = get_processor()
    filtered = []

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities:
            for date in entities.dates:
                year = date.get('year')
                if year and start_year <= year <= end_year:
                    filtered.append(result)
                    break

    return filtered


def filter_has_identifiers(results: List[Dict], id_types: List[str] = None) -> List[Dict]:
    """Filter results containing financial identifiers (LEI, IBAN, etc.)."""
    processor = get_processor()
    filtered = []

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities and entities.identifiers:
            if id_types:
                if any(t in entities.identifiers for t in id_types):
                    filtered.append(result)
            else:
                filtered.append(result)

    return filtered


def filter_has_company_numbers(results: List[Dict], crn_types: List[str] = None) -> List[Dict]:
    """Filter results containing company registration numbers (UK_CRN, DE_HRB, etc.)."""
    processor = get_processor()
    filtered = []

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities and entities.company_numbers:
            if crn_types:
                if any(t in entities.company_numbers for t in crn_types):
                    filtered.append(result)
            else:
                filtered.append(result)

    return filtered


def filter_by_semantic_concept(results: List[Dict], concept_ids: List[str] = None, categories: List[str] = None) -> List[Dict]:
    """
    Filter results by semantic concepts detected via embedding similarity.

    Args:
        results: Results to filter
        concept_ids: Specific concept IDs (e.g., ['beneficial_ownership', 'sanctions_exposure'])
        categories: Concept categories (e.g., ['compliance_red_flag', 'ownership'])

    Concepts include: beneficial_ownership, corporate_layering, sanctions_exposure,
                      money_laundering, shell_company, pep_connections, etc.
    """
    processor = get_processor()
    filtered = []

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities and entities.semantic_concepts:
            # Filter by concept IDs
            if concept_ids:
                result_concepts = [c.get('id') for c in entities.semantic_concepts]
                if any(cid in result_concepts for cid in concept_ids):
                    filtered.append(result)
            # Filter by categories
            elif categories:
                if any(cat in entities.concept_categories for cat in categories):
                    filtered.append(result)
            else:
                # Any semantic concepts detected
                filtered.append(result)

    return filtered


def filter_by_red_flag_category(results: List[Dict], min_red_flags: int = 1) -> List[Dict]:
    """Filter results with compliance red flags detected semantically."""
    processor = get_processor()
    filtered = []

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities and entities.concept_categories:
            red_flag_count = entities.concept_categories.get('compliance_red_flag', 0)
            if red_flag_count >= min_red_flags:
                filtered.append(result)

    return filtered


def filter_by_designation(results: List[Dict], designations: List[str] = None) -> List[Dict]:
    """
    Filter results by company legal designation (suffix).

    Args:
        results: Results to filter
        designations: List of designations to match (e.g., ['GMBH', 'AG', 'LTD', 'LLC'])
                      If None, returns any result with company designations

    Designations include: LTD, LLC, INC, CORP, PLC, GMBH, AG, KG, SA, SARL, SAS,
                          BV, NV, SRL, SPA, AB, AS, OY, etc.
    """
    processor = get_processor()
    filtered = []

    if designations:
        designations_upper = [d.upper() for d in designations]

    for result in results:
        entities = processor.get_entities(result.get('url', ''))
        if entities and entities.company_designations:
            if designations:
                if any(d in entities.company_designations for d in designations_upper):
                    filtered.append(result)
            else:
                # Any designation found
                filtered.append(result)

    return filtered
