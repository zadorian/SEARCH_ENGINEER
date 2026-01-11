"""
DRILL Entity Extractors

Entity extraction for investigation crawling using GLiNER (zero-shot NER).
Extracts entities with surrounding context snippets.

Primary: GLiNER (ML-based, accurate)
Fallback: Regex (fast, no ML dependencies)

Extracts:
- Companies (organizations)
- Persons (names with proper boundaries)
- Emails (regex + validation)
- Phone numbers (phonenumbers library)
- Addresses (GLiNER)
- Outlinks (HTML parsing)
- Investigation keywords (shareholder, subsidiary, etc.)
"""

import re
import logging
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from pathlib import Path
import json

logger = logging.getLogger(__name__)

# Optional imports - graceful fallback if not available
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False
    logger.warning("GLiNER not installed, using regex fallback")

try:
    import phonenumbers
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False
    logger.warning("phonenumbers not installed, using regex for phones")

# ============================================================================
# NAME DICTIONARIES (loaded once at module level)
# ============================================================================

# Common first names (expandable)
FIRST_NAMES: Set[str] = {
    # English
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan", "Jacob",
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Dorothy", "Carol",
    "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura",
    # European
    "Hans", "Klaus", "Peter", "Franz", "Wolfgang", "Heinrich", "Friedrich",
    "Pierre", "Jean", "Jacques", "Michel", "François", "Louis", "Henri",
    "Giovanni", "Giuseppe", "Francesco", "Antonio", "Marco", "Alessandro",
    "Carlos", "Juan", "José", "Miguel", "Pedro", "Luis", "Fernando", "Antonio",
    "Ivan", "Dmitri", "Sergei", "Vladimir", "Alexei", "Nikolai", "Boris",
    "Mohammed", "Ahmed", "Ali", "Hassan", "Omar", "Khalid", "Abdullah",
    # More international
    "Wei", "Ming", "Jian", "Hong", "Hui", "Xiao", "Chen", "Wang", "Li", "Zhang",
    "Yuki", "Takeshi", "Hiroshi", "Kenji", "Akira", "Satoshi", "Kazuki",
}

# Common last names (expandable)
LAST_NAMES: Set[str] = {
    # English/American
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    # German
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
    # French
    "Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit",
    "Durand", "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel",
    # Italian
    "Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo",
    "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "DeLuca",
    # Spanish
    "García", "Rodríguez", "Martínez", "López", "González", "Hernández",
    "Pérez", "Sánchez", "Ramírez", "Torres", "Flores", "Rivera", "Gómez",
    # Russian
    "Ivanov", "Smirnov", "Kuznetsov", "Popov", "Sokolov", "Lebedev", "Kozlov",
    "Novikov", "Morozov", "Petrov", "Volkov", "Solovyov", "Vasiliev",
    # Chinese (romanized)
    "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou",
    # Arabic
    "Khan", "Ali", "Hassan", "Hussein", "Ahmed", "Mohammed", "Ibrahim", "Rashid",
}

# Company suffixes by jurisdiction
COMPANY_SUFFIXES: Set[str] = {
    # English
    "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation",
    "plc", "llp", "lp", "co", "company",
    # German
    "gmbh", "ag", "kg", "ohg", "ug", "gbr", "ev",
    # French
    "sa", "sarl", "sas", "sasu", "snc", "sci", "eurl",
    # Italian
    "spa", "srl", "snc", "sas", "sapa",
    # Spanish
    "sl", "sa", "slu", "sau", "scl",
    # Dutch/Belgian
    "bv", "nv", "vof", "cv",
    # Nordic
    "ab", "as", "asa", "oy", "oyj", "a/s",
    # Other
    "pte", "pty", "bhd", "sdn", "kk", "jsc", "ooo", "zao", "pao",
}

# Investigation keywords
INVESTIGATION_KEYWORDS: Set[str] = {
    # Corporate structure
    "shareholder", "shareholders", "shareholding",
    "subsidiary", "subsidiaries",
    "parent company", "holding company", "holding",
    "affiliate", "affiliates", "affiliated",
    "beneficial owner", "beneficial ownership", "ubo",
    "director", "directors", "board of directors",
    "officer", "officers", "executive",
    "ceo", "cfo", "coo", "chairman", "president",
    # Financial
    "revenue", "turnover", "profit", "loss", "assets",
    "investment", "investor", "invested",
    "loan", "debt", "credit", "financing",
    "dividend", "capital", "equity",
    # Legal
    "registered", "registration", "incorporated",
    "jurisdiction", "offshore", "onshore",
    "litigation", "lawsuit", "legal action",
    "sanction", "sanctioned", "blacklist",
    "investigation", "investigated", "probe",
    "fraud", "corruption", "bribery", "money laundering",
    # Corporate actions
    "merger", "acquisition", "takeover",
    "joint venture", "partnership",
    "liquidation", "bankruptcy", "insolvency",
    "dissolution", "struck off", "dormant",
}


@dataclass
class EntityWithContext:
    """An entity with surrounding context/snippet."""
    value: str
    entity_type: str  # 'company', 'person', 'email', 'phone', 'keyword'
    snippet: str  # Surrounding text context
    position: int = 0  # Character position in text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "type": self.entity_type,
            "snippet": self.snippet,
            "position": self.position,
        }


@dataclass
class ExtractedEntities:
    """Container for extracted entities from a page."""
    url: str
    companies: List[str] = field(default_factory=list)
    persons: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    outlinks: List[str] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    keywords_found: List[str] = field(default_factory=list)
    raw_text_length: int = 0
    # NEW: Entities with context snippets
    entities_with_context: List[EntityWithContext] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "companies": self.companies,
            "persons": self.persons,
            "emails": self.emails,
            "phones": self.phones,
            "outlinks": self.outlinks,
            "internal_links": self.internal_links,
            "keywords_found": self.keywords_found,
            "raw_text_length": self.raw_text_length,
            "entities_with_context": [e.to_dict() for e in self.entities_with_context],
        }

    @property
    def total_entities(self) -> int:
        return (
            len(self.companies) + len(self.persons) +
            len(self.emails) + len(self.phones)
        )


# ============================================================================
# GLiNER SINGLETON (loaded once, reused across all extractors)
# ============================================================================

_gliner_model = None
_gliner_loading = False

def get_gliner_model():
    """Get or load the GLiNER model (singleton pattern)."""
    global _gliner_model, _gliner_loading

    if not GLINER_AVAILABLE:
        return None

    if _gliner_model is not None:
        return _gliner_model

    if _gliner_loading:
        return None  # Avoid concurrent loading

    _gliner_loading = True
    try:
        logger.info("Loading GLiNER model (urchade/gliner_medium-v2.1)...")
        _gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        logger.info("GLiNER model loaded successfully")
        return _gliner_model
    except Exception as e:
        logger.error(f"Failed to load GLiNER model: {e}")
        return None
    finally:
        _gliner_loading = False


class EntityExtractor:
    """
    Entity extraction using GLiNER (primary) with regex fallback.
    Extracts entities with surrounding context snippets.
    """

    # Entity labels for GLiNER (person names, not usernames/emails)
    GLINER_LABELS = ["person name", "organization", "company", "address", "location"]

    # Regex patterns (fallback)
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )

    PHONE_PATTERN = re.compile(
        r'(?:\+|00)?[\d\s\-\.\(\)]{10,20}'
    )

    # More specific phone patterns by region
    PHONE_PATTERNS = [
        re.compile(r'\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}'),  # International
        re.compile(r'\(\d{3}\)[\s\-]?\d{3}[\s\-]?\d{4}'),  # US format
        re.compile(r'\d{3}[\s\-\.]\d{3}[\s\-\.]\d{4}'),  # US alt
        re.compile(r'\+44[\s\-]?\d{4}[\s\-]?\d{6}'),  # UK
        re.compile(r'\+49[\s\-]?\d{3,4}[\s\-]?\d{6,8}'),  # Germany
    ]

    # Person name pattern (Capitalized First Last) - fallback
    PERSON_PATTERN = re.compile(
        r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    )

    # Company pattern (words followed by suffix) - fallback
    COMPANY_SUFFIX_PATTERN = re.compile(
        r'\b((?:[A-Z][a-zA-Z0-9&\'\-]*\s+){1,5})(' +
        '|'.join(re.escape(s) for s in COMPANY_SUFFIXES) +
        r')\.?\b',
        re.IGNORECASE
    )

    # URL pattern for outlinks
    URL_PATTERN = re.compile(
        r'href=["\']?(https?://[^"\'\s>]+)["\']?',
        re.IGNORECASE
    )

    def __init__(
        self,
        first_names: Optional[Set[str]] = None,
        last_names: Optional[Set[str]] = None,
        custom_keywords: Optional[Set[str]] = None,
        snippet_chars: int = 100,  # Characters before/after entity for context
        use_gliner: bool = True,  # Use GLiNER if available
        gliner_threshold: float = 0.5,  # GLiNER confidence threshold
    ):
        """
        Initialize extractor.

        Args:
            first_names: Custom first name set (for regex fallback)
            last_names: Custom last name set (for regex fallback)
            custom_keywords: Additional investigation keywords
            snippet_chars: Characters before/after entity to include in snippet
            use_gliner: Whether to use GLiNER (default True)
            gliner_threshold: Confidence threshold for GLiNER predictions
        """
        self.first_names = first_names or FIRST_NAMES
        self.last_names = last_names or LAST_NAMES
        self.keywords = INVESTIGATION_KEYWORDS.copy()
        if custom_keywords:
            self.keywords.update(custom_keywords)
        self.snippet_chars = snippet_chars
        self.use_gliner = use_gliner
        self.gliner_threshold = gliner_threshold

        # Lowercase versions for matching (regex fallback)
        self.first_names_lower = {n.lower() for n in self.first_names}
        self.last_names_lower = {n.lower() for n in self.last_names}
        self.keywords_lower = {k.lower() for k in self.keywords}

        # GLiNER model (lazy loaded)
        self._gliner = None

    def _get_gliner(self):
        """Get GLiNER model (lazy loading)."""
        if self._gliner is None and self.use_gliner:
            self._gliner = get_gliner_model()
        return self._gliner

    def extract(
        self,
        html: str,
        url: str,
        base_url: Optional[str] = None,
        include_snippets: bool = True,
    ) -> ExtractedEntities:
        """
        Extract all entities from HTML content.

        Args:
            html: Raw HTML content
            url: Source URL
            base_url: Base URL for resolving relative links
            include_snippets: Whether to extract context snippets (default True)

        Returns:
            ExtractedEntities with all found entities
        """
        # Strip HTML tags for text extraction
        text = self._strip_html(html)

        result = ExtractedEntities(url=url, raw_text_length=len(text))

        # Try GLiNER first for persons/companies/addresses
        gliner = self._get_gliner()
        if gliner is not None:
            gliner_entities = self._extract_with_gliner(text, gliner)
            result.persons = gliner_entities.get('persons', [])
            result.companies = gliner_entities.get('companies', [])
            person_contexts = gliner_entities.get('person_contexts', [])
            company_contexts = gliner_entities.get('company_contexts', [])
            address_contexts = gliner_entities.get('address_contexts', [])
        else:
            # Fallback to regex
            result.persons, person_contexts = self._extract_persons_with_context(text)
            result.companies, company_contexts = self._extract_companies_with_context(text)
            address_contexts = []

        # Always use specialized extraction for emails/phones (more reliable than NER)
        result.emails, email_contexts = self._extract_emails_with_context(text)
        result.phones, phone_contexts = self._extract_phones_with_context(text)
        result.keywords_found, keyword_contexts = self._extract_keywords_with_context(text)

        # Combine all entities with context
        if include_snippets:
            result.entities_with_context = (
                email_contexts + phone_contexts + person_contexts +
                company_contexts + address_contexts + keyword_contexts
            )

        # Extract links from HTML (not stripped text)
        outlinks, internal = self._extract_links(html, url, base_url)
        result.outlinks = outlinks
        result.internal_links = internal

        return result

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags, scripts, styles. Fast regex-based."""
        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove all tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode common entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _get_snippet(self, text: str, start: int, end: int) -> str:
        """Extract snippet with context before and after the match."""
        snippet_start = max(0, start - self.snippet_chars)
        snippet_end = min(len(text), end + self.snippet_chars)

        # Extend to word boundaries
        while snippet_start > 0 and text[snippet_start] not in ' \n\t':
            snippet_start -= 1
        while snippet_end < len(text) and text[snippet_end] not in ' \n\t':
            snippet_end += 1

        snippet = text[snippet_start:snippet_end].strip()

        # Add ellipsis if truncated
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    def _extract_with_gliner(self, text: str, model) -> Dict[str, Any]:
        """
        Extract entities using GLiNER model.

        Returns dict with:
        - persons: List[str]
        - companies: List[str]
        - person_contexts: List[EntityWithContext]
        - company_contexts: List[EntityWithContext]
        - address_contexts: List[EntityWithContext]
        """
        result = {
            'persons': [],
            'companies': [],
            'person_contexts': [],
            'company_contexts': [],
            'address_contexts': [],
        }

        if not text.strip():
            return result

        try:
            # GLiNER has text length limits, chunk if needed
            max_len = 10000
            if len(text) > max_len:
                # Process in chunks
                chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            else:
                chunks = [text]

            seen_persons = set()
            seen_companies = set()

            for chunk_idx, chunk in enumerate(chunks):
                offset = chunk_idx * max_len

                # Call GLiNER
                entities = model.predict_entities(
                    chunk,
                    self.GLINER_LABELS,
                    threshold=self.gliner_threshold
                )

                for entity in entities:
                    entity_text = entity.get('text', '').strip()
                    entity_type = entity.get('label', '').lower()
                    start = entity.get('start', 0) + offset
                    end = entity.get('end', 0) + offset

                    if not entity_text or len(entity_text) < 2:
                        continue

                    # Get snippet from original text
                    snippet = self._get_snippet(text, start, end)

                    if entity_type in ('person', 'person name'):
                        if entity_text not in seen_persons:
                            seen_persons.add(entity_text)
                            result['persons'].append(entity_text)
                            result['person_contexts'].append(EntityWithContext(
                                value=entity_text,
                                entity_type='person',
                                snippet=snippet,
                                position=start,
                            ))

                    elif entity_type in ('organization', 'company'):
                        if entity_text not in seen_companies:
                            seen_companies.add(entity_text)
                            result['companies'].append(entity_text)
                            result['company_contexts'].append(EntityWithContext(
                                value=entity_text,
                                entity_type='company',
                                snippet=snippet,
                                position=start,
                            ))

                    elif entity_type in ('address', 'location'):
                        result['address_contexts'].append(EntityWithContext(
                            value=entity_text,
                            entity_type='address',
                            snippet=snippet,
                            position=start,
                        ))

            result['persons'] = sorted(result['persons'])
            result['companies'] = sorted(result['companies'])

        except Exception as e:
            logger.error(f"GLiNER extraction failed: {e}")
            # Return empty results, caller will fallback to regex

        return result

    def _extract_emails(self, text: str) -> List[str]:
        """Extract unique email addresses (legacy, no context)."""
        emails, _ = self._extract_emails_with_context(text)
        return emails

    def _extract_emails_with_context(self, text: str) -> tuple[List[str], List[EntityWithContext]]:
        """Extract unique email addresses with surrounding context."""
        seen = set()
        emails = []
        contexts = []

        for match in self.EMAIL_PATTERN.finditer(text.lower()):
            email = match.group()
            # Filter out common false positives
            if any(fp in email for fp in ['example.com', 'test.com', 'localhost', '.png', '.jpg', '.gif']):
                continue
            if email not in seen:
                seen.add(email)
                emails.append(email)
                snippet = self._get_snippet(text, match.start(), match.end())
                contexts.append(EntityWithContext(
                    value=email,
                    entity_type='email',
                    snippet=snippet,
                    position=match.start(),
                ))

        return sorted(emails), contexts

    def _extract_phones(self, text: str) -> List[str]:
        """Extract unique phone numbers (legacy, no context)."""
        phones, _ = self._extract_phones_with_context(text)
        return phones

    def _extract_phones_with_context(self, text: str) -> Tuple[List[str], List[EntityWithContext]]:
        """Extract phone numbers with context using phonenumbers library + regex fallback."""
        seen = set()
        phones = []
        contexts = []

        if PHONENUMBERS_AVAILABLE:
            # Use phonenumbers library for accurate extraction
            try:
                for match in phonenumbers.PhoneNumberMatcher(text, None):  # None = detect country
                    phone_str = match.raw_string
                    normalized = phonenumbers.format_number(
                        match.number,
                        phonenumbers.PhoneNumberFormat.E164
                    )

                    if normalized not in seen:
                        seen.add(normalized)
                        phones.append(phone_str)
                        snippet = self._get_snippet(text, match.start, match.end)
                        contexts.append(EntityWithContext(
                            value=phone_str,
                            entity_type='phone',
                            snippet=snippet,
                            position=match.start,
                        ))
            except Exception as e:
                logger.warning(f"phonenumbers extraction failed: {e}, using regex fallback")
                # Fall through to regex

        # Regex fallback or supplement
        if not phones:
            for pattern in self.PHONE_PATTERNS:
                for match in pattern.finditer(text):
                    phone_str = match.group().strip()
                    normalized = re.sub(r'[\s\-\.\(\)]', '', phone_str)
                    if len(normalized) >= 10 and normalized not in seen:
                        seen.add(normalized)
                        phones.append(phone_str)
                        snippet = self._get_snippet(text, match.start(), match.end())
                        contexts.append(EntityWithContext(
                            value=phone_str,
                            entity_type='phone',
                            snippet=snippet,
                            position=match.start(),
                        ))

        return sorted(phones), contexts

    def _extract_persons(self, text: str) -> List[str]:
        """Extract person names (legacy, no context)."""
        persons, _ = self._extract_persons_with_context(text)
        return persons

    def _extract_persons_with_context(self, text: str) -> Tuple[List[str], List[EntityWithContext]]:
        """
        Extract person names with context using regex (fallback for GLiNER).
        """
        seen = set()
        persons = []
        contexts = []

        for match in self.PERSON_PATTERN.finditer(text):
            first = match.group(1)
            last_parts = match.group(2).split()
            last = last_parts[-1] if last_parts else ""

            first_lower = first.lower()
            last_lower = last.lower()

            # Accept if either first OR last name is in dictionary
            if first_lower in self.first_names_lower or last_lower in self.last_names_lower:
                full_name = f"{first} {match.group(2)}"
                # Filter out common false positives
                if not self._is_false_positive_name(full_name) and full_name not in seen:
                    seen.add(full_name)
                    persons.append(full_name)
                    snippet = self._get_snippet(text, match.start(), match.end())
                    contexts.append(EntityWithContext(
                        value=full_name,
                        entity_type='person',
                        snippet=snippet,
                        position=match.start(),
                    ))

        return sorted(persons), contexts

    def _is_false_positive_name(self, name: str) -> bool:
        """Filter out common false positive person names."""
        false_positives = {
            "New York", "Los Angeles", "San Francisco", "San Diego", "Las Vegas",
            "United States", "United Kingdom", "New Zealand", "South Africa",
            "North America", "South America", "Privacy Policy", "Terms Service",
            "Read More", "Learn More", "Click Here", "Contact Us",
        }
        return name in false_positives or len(name) < 5

    def _extract_companies(self, text: str) -> List[str]:
        """Extract company names (legacy, no context)."""
        companies, _ = self._extract_companies_with_context(text)
        return companies

    def _extract_companies_with_context(self, text: str) -> Tuple[List[str], List[EntityWithContext]]:
        """Extract company names with context (fallback for GLiNER)."""
        seen = set()
        companies = []
        contexts = []

        for match in self.COMPANY_SUFFIX_PATTERN.finditer(text):
            company_name = match.group(0).strip()
            company_name = re.sub(r'\s+', ' ', company_name)

            if len(company_name) > 5 and company_name not in seen:
                seen.add(company_name)
                companies.append(company_name)
                snippet = self._get_snippet(text, match.start(), match.end())
                contexts.append(EntityWithContext(
                    value=company_name,
                    entity_type='company',
                    snippet=snippet,
                    position=match.start(),
                ))

        return sorted(companies), contexts

    def _extract_keywords(self, text: str) -> List[str]:
        """Find investigation keywords (legacy, no context)."""
        keywords, _ = self._extract_keywords_with_context(text)
        return keywords

    def _extract_keywords_with_context(self, text: str) -> Tuple[List[str], List[EntityWithContext]]:
        """Find investigation keywords with context snippets."""
        text_lower = text.lower()
        found = []
        contexts = []

        for keyword in self.keywords:
            keyword_lower = keyword.lower()
            # Find all occurrences
            start = 0
            while True:
                pos = text_lower.find(keyword_lower, start)
                if pos == -1:
                    break
                if keyword not in found:
                    found.append(keyword)
                snippet = self._get_snippet(text, pos, pos + len(keyword))
                contexts.append(EntityWithContext(
                    value=keyword,
                    entity_type='keyword',
                    snippet=snippet,
                    position=pos,
                ))
                start = pos + 1

        return sorted(found), contexts

    def _extract_links(
        self,
        html: str,
        url: str,
        base_url: Optional[str] = None,
    ) -> tuple[List[str], List[str]]:
        """
        Extract outlinks and internal links from HTML.

        Returns:
            Tuple of (outlinks, internal_links)
        """
        base = base_url or url
        parsed_base = urlparse(base)
        base_domain = parsed_base.netloc.lower()

        outlinks = set()
        internal = set()

        # Find all href links
        for match in self.URL_PATTERN.finditer(html):
            link = match.group(1)

            # Skip non-http links
            if not link.startswith(('http://', 'https://')):
                continue

            # Skip common non-content links
            if any(skip in link.lower() for skip in [
                'javascript:', 'mailto:', 'tel:', '#',
                '.css', '.js', '.png', '.jpg', '.gif', '.ico',
                'facebook.com/sharer', 'twitter.com/intent',
                'linkedin.com/share', 'pinterest.com/pin',
            ]):
                continue

            try:
                parsed = urlparse(link)
                link_domain = parsed.netloc.lower()

                if link_domain == base_domain or link_domain.endswith('.' + base_domain):
                    internal.add(link)
                else:
                    outlinks.add(link)
            except Exception:
                continue

        return sorted(outlinks), sorted(internal)

    def load_names_from_file(self, filepath: Path, name_type: str = "first") -> int:
        """
        Load additional names from a file (one name per line).

        Args:
            filepath: Path to names file
            name_type: "first" or "last"

        Returns:
            Number of names loaded
        """
        if not filepath.exists():
            return 0

        with open(filepath, 'r', encoding='utf-8') as f:
            names = {line.strip() for line in f if line.strip()}

        if name_type == "first":
            self.first_names.update(names)
            self.first_names_lower.update(n.lower() for n in names)
        else:
            self.last_names.update(names)
            self.last_names_lower.update(n.lower() for n in names)

        return len(names)

    def add_keywords(self, keywords: List[str]) -> int:
        """
        Add investigation keywords dynamically.

        Used by GlobalLinks intelligence to inject anchor-derived keywords.

        Args:
            keywords: List of keywords to add

        Returns:
            Number of new keywords added
        """
        new_count = 0
        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            if keyword_lower and keyword_lower not in self.keywords_lower:
                self.keywords.add(keyword)
                self.keywords_lower.add(keyword_lower)
                new_count += 1
        return new_count

    def add_company_names(self, names: List[str]) -> int:
        """
        Add known company names to watch for.

        Used by GlobalLinks intelligence when anchor texts contain company names.

        Args:
            names: List of company names

        Returns:
            Number added
        """
        # Create a pattern that will match these exact names
        # Store them for exact matching
        if not hasattr(self, 'known_companies'):
            self.known_companies = set()

        new_count = 0
        for name in names:
            if name and name not in self.known_companies:
                self.known_companies.add(name)
                new_count += 1
        return new_count

    def add_person_names(self, names: List[str]) -> int:
        """
        Add known person names to watch for.

        Used by GlobalLinks intelligence when anchor texts contain person names.

        Args:
            names: List of person names (e.g., "John Smith")

        Returns:
            Number added
        """
        if not hasattr(self, 'known_persons'):
            self.known_persons = set()

        new_count = 0
        for name in names:
            if name and name not in self.known_persons:
                self.known_persons.add(name)
                new_count += 1
        return new_count


# Convenience function
def extract_entities(html: str, url: str, base_url: Optional[str] = None) -> ExtractedEntities:
    """Quick extraction using default extractor."""
    extractor = EntityExtractor()
    return extractor.extract(html, url, base_url)


def extract_and_store_entities(
    html: str,
    url: str,
    base_url: Optional[str] = None,
    project_id: Optional[str] = None,
    store_to_es: bool = True,
) -> Dict[str, Any]:
    """
    Extract entities from HTML and optionally store to Elasticsearch.

    This is the primary function for DRILL entity extraction with storage.
    Combines extraction (via EntityExtractor) with storage (via DrillIndexer).

    Args:
        html: HTML content to extract from
        url: URL of the page
        base_url: Optional base URL for resolving relative links
        project_id: Optional project identifier for grouping
        store_to_es: Whether to store to Elasticsearch (default True)

    Returns:
        Dict with:
        - extracted: ExtractedEntities object (as dict)
        - storage: Storage result if store_to_es=True, else None
        - total_entities: Total count of entities found
    """
    from urllib.parse import urlparse

    # Extract entities
    extractor = EntityExtractor()
    extracted = extractor.extract(html, url, base_url)

    result = {
        "extracted": extracted.to_dict(),
        "total_entities": extracted.total_entities,
        "storage": None,
    }

    # Store to Elasticsearch if enabled
    if store_to_es and extracted.total_entities > 0:
        try:
            from .indexer import DrillIndexer

            indexer = DrillIndexer()
            indexer.ensure_indices()

            # Get domain from URL
            parsed = urlparse(url)
            domain = parsed.netloc

            storage_result = indexer.index_entities_from_extraction(
                source_url=url,
                source_domain=domain,
                companies=extracted.companies,
                persons=extracted.persons,
                emails=extracted.emails,
                phones=extracted.phones,
                project_id=project_id,
            )
            result["storage"] = storage_result

        except Exception as e:
            result["storage"] = {"error": str(e)}

    return result


async def batch_extract_and_store(
    pages: List[Dict[str, str]],
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Batch extract and store entities from multiple pages.

    Args:
        pages: List of dicts with 'url' and 'html' keys
        project_id: Optional project identifier

    Returns:
        Aggregated results with totals
    """
    from urllib.parse import urlparse
    from .indexer import DrillIndexer

    extractor = EntityExtractor()
    indexer = DrillIndexer()
    indexer.ensure_indices()

    all_entities = []
    extraction_results = []

    for page in pages:
        url = page.get("url", "")
        html = page.get("html", "")

        if not url or not html:
            continue

        # Extract
        extracted = extractor.extract(html, url)
        extraction_results.append(extracted.to_dict())

        # Prepare for bulk storage
        parsed = urlparse(url)
        domain = parsed.netloc

        for company in extracted.companies:
            all_entities.append({
                "entity_type": "company",
                "entity_value": company,
                "source_url": url,
                "source_domain": domain,
                "project_id": project_id,
            })

        for person in extracted.persons:
            all_entities.append({
                "entity_type": "person",
                "entity_value": person,
                "source_url": url,
                "source_domain": domain,
                "project_id": project_id,
            })

        for email in extracted.emails:
            all_entities.append({
                "entity_type": "email",
                "entity_value": email,
                "source_url": url,
                "source_domain": domain,
                "project_id": project_id,
            })

        for phone in extracted.phones:
            all_entities.append({
                "entity_type": "phone",
                "entity_value": phone,
                "source_url": url,
                "source_domain": domain,
                "project_id": project_id,
            })

    # Bulk store
    storage_result = {"success": 0, "errors": 0}
    if all_entities:
        storage_result = indexer.bulk_index_entities(all_entities)

    return {
        "pages_processed": len(pages),
        "total_entities": len(all_entities),
        "companies": sum(len(e.get("companies", [])) for e in extraction_results),
        "persons": sum(len(e.get("persons", [])) for e in extraction_results),
        "emails": sum(len(e.get("emails", [])) for e in extraction_results),
        "phones": sum(len(e.get("phones", [])) for e in extraction_results),
        "storage": storage_result,
    }
