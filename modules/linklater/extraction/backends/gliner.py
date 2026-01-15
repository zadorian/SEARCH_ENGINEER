"""
GLiNER Backend - Local Zero-Shot NER Model

Uses GLiNER (Generalist and Lightweight Model for Named Entity Recognition)
for fast, local entity extraction without API costs.

Model: urchade/gliner_medium-v2.1 (can use small-v2.1 for speed)

Best for:
- Bulk extraction where API costs would be prohibitive
- Privacy-sensitive content (no data leaves local machine)
- Offline operation
- Good accuracy for persons/organizations

Usage:
    from linklater.extraction.backends.gliner import GLiNERBackend

    backend = GLiNERBackend()
    result = backend.extract(html, url)
    # Returns: {"persons": [...], "companies": [...], "addresses": [...]}
"""

import re
import logging
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger(__name__)

# Optional GLiNER import
try:
    from gliner import GLiNER
    GLINER_AVAILABLE = True
except ImportError:
    GLINER_AVAILABLE = False
    logger.warning("GLiNER not installed: pip install gliner")

# Optional phonenumbers for phone extraction
try:
    import phonenumbers
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False


# ============================================================================
# NAME DICTIONARIES (for regex fallback and validation)
# ============================================================================

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
    "Carlos", "Juan", "José", "Miguel", "Pedro", "Luis", "Fernando",
    "Ivan", "Dmitri", "Sergei", "Vladimir", "Alexei", "Nikolai", "Boris",
    "Mohammed", "Ahmed", "Ali", "Hassan", "Omar", "Khalid", "Abdullah",
}

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
    "Martin", "Bernard", "Dubois", "Robert", "Richard", "Petit",
    "Durand", "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel",
    # Russian
    "Ivanov", "Smirnov", "Kuznetsov", "Popov", "Sokolov", "Lebedev", "Kozlov",
}

COMPANY_SUFFIXES: Set[str] = {
    "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation",
    "plc", "llp", "lp", "co", "company",
    "gmbh", "ag", "kg", "ohg", "ug", "gbr", "ev",
    "sa", "sarl", "sas", "sasu", "snc", "sci", "eurl",
    "spa", "srl", "sas", "sapa",
    "sl", "sau", "scl",
    "bv", "nv", "vof", "cv",
    "ab", "as", "asa", "oy", "oyj", "a/s",
    "pte", "pty", "bhd", "sdn", "kk", "jsc", "ooo", "zao", "pao",
}


# ============================================================================
# SINGLETON MODEL LOADING
# ============================================================================

_gliner_model = None
_gliner_loading = False


def get_gliner_model(model_name: str = "urchade/gliner_medium-v2.1"):
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
        logger.info(f"Loading GLiNER model ({model_name})...")
        _gliner_model = GLiNER.from_pretrained(model_name)
        logger.info("GLiNER model loaded successfully")
        return _gliner_model
    except Exception as e:
        logger.error(f"Failed to load GLiNER model: {e}")
        return None
    finally:
        _gliner_loading = False


# ============================================================================
# GLINER BACKEND CLASS
# ============================================================================

class GLiNERBackend:
    """
    Entity extraction backend using GLiNER (local model).

    Uses REGEX-FIRST approach: finds candidate snippets via regex,
    then runs GLiNER only on those snippets for efficiency.
    """

    # Entity labels for GLiNER
    GLINER_LABELS = ["person name", "organization", "company", "address", "location", "phone number", "date"]

    # Regex patterns for REGEX-FIRST candidate detection
    DATE_SIGNALS = [
        # ISO format: 2024-01-15
        r'\b\d{4}-\d{1,2}-\d{1,2}\b',
        # US format: 01/15/2024, 1/15/24
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        # EU format: 15.01.2024, 15-01-2024
        r'\b\d{1,2}[.\-]\d{1,2}[.\-]\d{2,4}\b',
        # Long format: January 15, 2024
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        # Medium format: Jan 15, 2024
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}',
        # Day Month Year: 15 January 2024
        r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
        # Month Year: January 2024
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
        # Quarter: Q1 2024, 1Q2024
        r'Q[1-4]\s*\d{4}|\d{4}\s*Q[1-4]',
        # Year only (near context words)
        r'(?:in|during|since|from|until|by)\s+\d{4}\b',
    ]

    PERSON_SIGNALS = [
        r'(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder|Owner|Partner|Chief|Head of|VP|Vice President|Chairman|Executive)\s+[A-Z][a-z]+',
        r'[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*,\s*(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder)',
        r'(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+[A-Z][a-z]+\s+[A-Z][a-z]+',
        r'[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?:\s+(?:said|announced|stated|explained|noted))',
    ]

    COMPANY_SIGNALS = [
        r'[A-Z][A-Za-z\s&]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company|Group|Holdings|Partners|Associates|Solutions|Technologies|Services|Consulting)',
        r'(?:partnership with|acquired by|subsidiary of|invested in)\s+[A-Z][A-Za-z\s&]+',
    ]

    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

    def __init__(
        self,
        model_name: str = "urchade/gliner_medium-v2.1",
        threshold: float = 0.5,
        snippet_chars: int = 100,
        max_snippets: int = 30,
        fallback_chars: int = 2000,
    ):
        """
        Initialize GLiNER backend.

        Args:
            model_name: GLiNER model to use (small for speed, medium for accuracy)
            threshold: Confidence threshold for predictions
            snippet_chars: Characters before/after for context snippets
            max_snippets: Maximum snippets to process per page
        """
        self.model_name = model_name
        self.threshold = threshold
        self.snippet_chars = snippet_chars
        self.max_snippets = max_snippets
        self.fallback_chars = fallback_chars
        self._model = None

    def _get_model(self):
        """Lazy load GLiNER model."""
        if self._model is None:
            self._model = get_gliner_model(self.model_name)
        return self._model

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags, scripts, styles."""
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _get_snippet(self, text: str, start: int, end: int) -> str:
        """Extract snippet with context."""
        snippet_start = max(0, start - self.snippet_chars)
        snippet_end = min(len(text), end + self.snippet_chars)

        # Extend to word boundaries
        while snippet_start > 0 and text[snippet_start] not in ' \n\t':
            snippet_start -= 1
        while snippet_end < len(text) and text[snippet_end] not in ' \n\t':
            snippet_end += 1

        snippet = text[snippet_start:snippet_end].strip()

        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    def _extract_candidate_snippets(self, text: str, include_dates: bool = True) -> List[str]:
        """
        REGEX-FIRST: Extract candidate snippets containing likely entities.

        This dramatically reduces the text GLiNER needs to process.
        """
        all_signals = self.PERSON_SIGNALS + self.COMPANY_SIGNALS
        if include_dates:
            all_signals = all_signals + self.DATE_SIGNALS
        snippets = []
        seen = set()

        for pattern in all_signals:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = max(0, match.start() - 200)
                end = min(len(text), match.end() + 300)
                snippet = text[start:end]

                # Deduplicate by hash
                snippet_hash = hash(snippet[:100])
                if snippet_hash not in seen:
                    seen.add(snippet_hash)
                    snippets.append(snippet)

                if len(snippets) >= self.max_snippets:
                    break
            if len(snippets) >= self.max_snippets:
                break

        return snippets

    def _fallback_snippets(self, text: str) -> List[str]:
        """Fallback snippets when no regex signals match (non-English text, sparse pages)."""
        if not text:
            return []
        if len(text) <= self.fallback_chars:
            return [text]

        head = text[:self.fallback_chars]
        tail = text[-self.fallback_chars:]
        if head == tail:
            return [head]
        return [head, tail]

    def _extract_with_gliner(self, text: str, include_dates: bool = True) -> Dict[str, Any]:
        """
        Extract entities using GLiNER model.

        Returns dict with persons, companies, addresses, phone_candidates, dates.
        """
        model = self._get_model()
        if not model:
            return {"persons": [], "companies": [], "addresses": [], "phone_candidates": [], "dates": []}

        # Use REGEX-FIRST approach
        snippets = self._extract_candidate_snippets(text, include_dates=include_dates)
        if not snippets:
            snippets = self._fallback_snippets(text)

        seen_persons = set()
        seen_companies = set()
        seen_phones = set()
        seen_dates = set()
        persons = []
        companies = []
        addresses = []
        phone_candidates = []
        dates = []

        for snippet in snippets:
            try:
                entities = model.predict_entities(
                    snippet,
                    self.GLINER_LABELS,
                    threshold=self.threshold
                )

                for entity in entities:
                    entity_text = entity.get('text', '').strip()
                    entity_type = entity.get('label', '').lower()
                    confidence = entity.get('score', 0.5)

                    if not entity_text or len(entity_text) < 2:
                        continue

                    if entity_type in ('person', 'person name'):
                        # Validate: should have space (first + last name)
                        if ' ' in entity_text and entity_text not in seen_persons:
                            seen_persons.add(entity_text)
                            persons.append({
                                "value": entity_text,
                                "confidence": confidence,
                                "method": "gliner"
                            })

                    elif entity_type in ('organization', 'company'):
                        if entity_text not in seen_companies:
                            seen_companies.add(entity_text)
                            companies.append({
                                "value": entity_text,
                                "confidence": confidence,
                                "method": "gliner"
                            })

                    elif entity_type in ('address', 'location'):
                        addresses.append({
                            "value": entity_text,
                            "confidence": confidence,
                            "method": "gliner"
                        })

                    elif entity_type == 'phone number':
                        # Store as candidate - will be validated with phonenumbers
                        if entity_text not in seen_phones:
                            seen_phones.add(entity_text)
                            phone_candidates.append({
                                "value": entity_text,
                                "confidence": confidence,
                                "method": "gliner"
                            })

                    elif entity_type == 'date':
                        # Parse date to structured format
                        if entity_text not in seen_dates:
                            seen_dates.add(entity_text)
                            parsed = self._parse_date_text(entity_text)
                            if parsed:
                                dates.append({
                                    "value": entity_text,
                                    "parsed": parsed,
                                    "confidence": confidence,
                                    "method": "gliner"
                                })

            except Exception as e:
                logger.debug(f"GLiNER snippet extraction failed: {e}")
                continue

        return {
            "persons": persons,
            "companies": companies,
            "addresses": addresses,
            "phone_candidates": phone_candidates,
            "dates": dates
        }

    def _extract_emails(self, text: str) -> List[Dict[str, Any]]:
        """Extract emails using regex (more reliable than NER)."""
        seen = set()
        emails = []

        for match in self.EMAIL_PATTERN.finditer(text.lower()):
            email = match.group()
            # Filter false positives
            if any(fp in email for fp in ['example.com', 'test.com', 'localhost', '.png', '.jpg']):
                continue
            if email not in seen:
                seen.add(email)
                emails.append({
                    "value": email,
                    "confidence": 0.95,
                    "method": "regex"
                })

        return emails

    def _extract_phones(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract phones using GLiNER + phonenumbers validation.

        Flow:
        1. GLiNER extracts phone candidates from text
        2. phonenumbers library validates and normalizes
        """
        phones = []
        seen = set()

        # Method 1: Use phonenumbers to find phone numbers directly (most reliable)
        if PHONENUMBERS_AVAILABLE:
            try:
                # Try common regions
                for region in [None, "US", "GB", "DE", "FR", "NL", "CH", "AT"]:
                    for match in phonenumbers.PhoneNumberMatcher(text, region):
                        try:
                            number = match.number
                            if phonenumbers.is_valid_number(number):
                                formatted = phonenumbers.format_number(
                                    number,
                                    phonenumbers.PhoneNumberFormat.E164
                                )
                                if formatted not in seen:
                                    seen.add(formatted)
                                    phones.append({
                                        "value": formatted,
                                        "raw": match.raw_string,
                                        "confidence": 0.95,
                                        "method": "phonenumbers"
                                    })
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"phonenumbers extraction failed: {e}")

        # Method 2: GLiNER extraction as supplement (already done in _extract_with_gliner)
        # The GLiNER results for "phone number" label are handled separately
        # and can be validated with phonenumbers

        return phones

    def _validate_phone_candidate(self, candidate: str) -> Optional[Dict[str, Any]]:
        """Validate a phone candidate extracted by GLiNER using phonenumbers."""
        if not PHONENUMBERS_AVAILABLE:
            return None

        try:
            # Try parsing without region first
            for region in [None, "US", "GB", "DE", "FR"]:
                try:
                    parsed = phonenumbers.parse(candidate, region)
                    if phonenumbers.is_valid_number(parsed):
                        formatted = phonenumbers.format_number(
                            parsed,
                            phonenumbers.PhoneNumberFormat.E164
                        )
                        return {
                            "value": formatted,
                            "raw": candidate,
                            "confidence": 0.85,
                            "method": "gliner+phonenumbers"
                        }
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _parse_date_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse date text into structured format with year/month/day components.

        Returns hierarchical date info for TemporalManager integration:
        - year (always present if valid)
        - month (if available)
        - day (if available)
        - iso_date (normalized format)
        - resolution (year/month/day)
        """
        from datetime import datetime
        import calendar

        text = text.strip()

        # Month name mappings
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
            'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9,
            'oct': 10, 'nov': 11, 'dec': 12,
        }

        year, month, day = None, None, None

        try:
            # Try ISO format: YYYY-MM-DD
            iso_match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', text)
            if iso_match:
                year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))

            # Try US format: MM/DD/YYYY
            elif re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', text):
                parts = text.split('/')
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])

            # Try EU format: DD.MM.YYYY or DD-MM-YYYY
            elif re.match(r'^\d{1,2}[.\-]\d{1,2}[.\-]\d{4}$', text):
                parts = re.split(r'[.\-]', text)
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])

            # Try long format: January 15, 2024 or January 15 2024
            elif re.match(r'^[A-Za-z]+\s+\d{1,2},?\s+\d{4}$', text, re.IGNORECASE):
                parts = re.split(r'[\s,]+', text)
                month_str = parts[0].lower()
                if month_str in month_names:
                    month = month_names[month_str]
                    day = int(parts[1])
                    year = int(parts[2])

            # Try: 15 January 2024
            elif re.match(r'^\d{1,2}\s+[A-Za-z]+\s+\d{4}$', text, re.IGNORECASE):
                parts = text.split()
                day = int(parts[0])
                month_str = parts[1].lower()
                if month_str in month_names:
                    month = month_names[month_str]
                year = int(parts[2])

            # Try month-year: January 2024
            elif re.match(r'^[A-Za-z]+\s+\d{4}$', text, re.IGNORECASE):
                parts = text.split()
                month_str = parts[0].lower()
                if month_str in month_names:
                    month = month_names[month_str]
                year = int(parts[1])

            # Try quarter: Q1 2024 or 2024 Q1
            elif re.match(r'^Q[1-4]\s*\d{4}$', text, re.IGNORECASE):
                q = int(text[1])
                year = int(re.search(r'\d{4}', text).group())
                month = (q - 1) * 3 + 1  # Q1=Jan, Q2=Apr, Q3=Jul, Q4=Oct

            # Try year only: 2024
            elif re.match(r'^\d{4}$', text):
                year = int(text)

            # Validate parsed values
            if year and (year < 1900 or year > 2100):
                return None
            if month and (month < 1 or month > 12):
                return None
            if day and month and year:
                # Validate day for month
                max_day = calendar.monthrange(year, month)[1]
                if day < 1 or day > max_day:
                    return None

            if year:
                # Determine resolution
                if day:
                    resolution = "day"
                    iso_date = f"{year:04d}-{month:02d}-{day:02d}"
                elif month:
                    resolution = "month"
                    iso_date = f"{year:04d}-{month:02d}"
                else:
                    resolution = "year"
                    iso_date = f"{year:04d}"

                return {
                    "year": year,
                    "month": month,
                    "day": day,
                    "iso_date": iso_date,
                    "resolution": resolution
                }

        except Exception as e:
            logger.debug(f"Date parsing failed for '{text}': {e}")

        return None

    def extract(
        self,
        html: str,
        url: str = "",
        include_emails: bool = True,
        include_phones: bool = True,
        include_dates: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract entities from HTML content.

        Args:
            html: Raw HTML content
            url: Source URL (for logging)
            include_emails: Whether to extract emails via regex
            include_phones: Whether to extract phones via phonenumbers
            include_dates: Whether to extract dates

        Returns:
            Dict with persons, companies, addresses, emails, phones, dates

            dates format:
            [{"value": "January 15, 2024", "parsed": {"year": 2024, "month": 1, "day": 15,
              "iso_date": "2024-01-15", "resolution": "day"}, "confidence": 0.8, "method": "gliner"}]
        """
        text = self._strip_html(html)

        # GLiNER extraction (includes dates if requested)
        result = self._extract_with_gliner(text, include_dates=include_dates)

        # Add emails if requested
        if include_emails:
            result["emails"] = self._extract_emails(text)

        # Extract and validate phones
        if include_phones:
            phones = []
            seen_phones = set()

            # Method 1: Direct phonenumbers extraction (most reliable)
            direct_phones = self._extract_phones(text)
            for phone in direct_phones:
                if phone["value"] not in seen_phones:
                    seen_phones.add(phone["value"])
                    phones.append(phone)

            # Method 2: Validate GLiNER phone candidates with phonenumbers
            for candidate in result.get("phone_candidates", []):
                validated = self._validate_phone_candidate(candidate["value"])
                if validated and validated["value"] not in seen_phones:
                    seen_phones.add(validated["value"])
                    phones.append(validated)

            result["phones"] = phones

        # Remove internal phone_candidates from output
        result.pop("phone_candidates", None)

        result["method"] = "gliner"
        result["url"] = url

        return result


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_backend = None


def get_backend() -> GLiNERBackend:
    """Get singleton backend instance."""
    global _backend
    if _backend is None:
        _backend = GLiNERBackend()
    return _backend


def extract(html: str, url: str = "") -> Dict[str, Any]:
    """
    Quick extraction using default GLiNER backend.

    Args:
        html: HTML content
        url: Source URL

    Returns:
        Dict with persons, companies, addresses, emails
    """
    backend = get_backend()
    return backend.extract(html, url)


# For unified interface compatibility
def extract_entities(html: str, url: str = "", **kwargs) -> Dict[str, Any]:
    """Unified interface for entity extraction."""
    return extract(html, url)
