#!/usr/bin/env python3
"""
PACMAN Bridge for SUBMARINE

Connects SUBMARINE's WARC content fetcher to PACMAN's entity extraction pipeline.

Extracts:
- Persons (names via pattern + first-name validation)
- Companies (legal suffixes, business words)
- Identifiers (LEI, IBAN, SWIFT, VAT, etc.)
- Contacts (email, phone)
- Crypto addresses (BTC, ETH, etc.)

Uses tiered extraction:
1. Fast regex-only extraction (~5ms)
2. GLiNER NER model (if available)
3. AI backends (Haiku/GPT for validation)
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Add PACMAN to path
import sys
sys.path.insert(0, "/data")

# Try to import PACMAN components
PACMAN_AVAILABLE = False
try:
    from PACMAN.entity_extractors.fast import extract_fast
    from PACMAN.entity_extractors.persons import extract_persons
    from PACMAN.entity_extractors.companies import extract_companies
    from PACMAN.patterns.identifiers import ALL_IDENTIFIERS
    from PACMAN.patterns.contacts import ALL_CONTACTS
    from PACMAN.patterns.crypto import ALL_CRYPTO
    PACMAN_AVAILABLE = True
    logger.info("PACMAN extraction modules loaded")
except ImportError as e:
    logger.warning(f"PACMAN not available: {e}")

# Fallback patterns if PACMAN not available
FALLBACK_PATTERNS = {
    "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "PHONE": re.compile(r'(?:\+|00)[\d\s\-\(\)]{10,20}'),
    "URL": re.compile(r'https?://[^\s<>"\']+'),
}


@dataclass
class ExtractedEntity:
    """A single extracted entity."""
    value: str
    entity_type: str
    confidence: float
    source: str  # Which extractor found it
    context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Results from extracting a single document."""
    url: str
    domain: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    raw_counts: Dict[str, int] = field(default_factory=dict)
    _seen: set = field(default_factory=set, repr=False)

    def add(self, entity: ExtractedEntity) -> bool:
        """
        Add entity with deduplication.

        Returns True if entity was added, False if duplicate.
        """
        # Dedupe key: (normalized_value, type)
        key = (entity.value.lower().strip(), entity.entity_type)
        if key in self._seen:
            return False

        self._seen.add(key)
        self.entities.append(entity)
        self.raw_counts[entity.entity_type] = self.raw_counts.get(entity.entity_type, 0) + 1
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "domain": self.domain,
            "entity_count": len(self.entities),
            "counts_by_type": self.raw_counts,
            "entities": [
                {
                    "value": e.value,
                    "type": e.entity_type,
                    "confidence": e.confidence,
                    "source": e.source,
                }
                for e in self.entities
            ],
        }


class PACMANExtractor:
    """
    PACMAN-powered entity extractor.

    Usage:
        extractor = PACMANExtractor()
        result = extractor.extract(content, url="https://example.com/page")

        # Or extract from SUBMARINE DiveResult
        result = extractor.extract_from_dive_result(dive_result)
    """

    def __init__(self, use_ai: bool = False):
        """
        Initialize extractor.

        Args:
            use_ai: Enable AI-powered extraction (slower, more accurate)
        """
        self.use_ai = use_ai
        self.pacman_available = PACMAN_AVAILABLE

    def extract(
        self,
        content: str,
        url: str = "",
        domain: str = "",
    ) -> ExtractionResult:
        """
        Extract entities from text content.

        Uses PACMAN extractors if available, falls back to regex.
        """
        result = ExtractionResult(url=url, domain=domain or self._get_domain(url))

        if not content:
            return result

        # Clean HTML if present
        text = self._strip_html(content)

        if self.pacman_available:
            # Use PACMAN extractors
            self._extract_with_pacman(text, result)
        else:
            # Fallback to simple patterns
            self._extract_fallback(text, result)

        return result

    def _extract_with_pacman(self, text: str, result: ExtractionResult):
        """Extract using PACMAN modules."""

        # 1. Fast pattern extraction (identifiers, contacts, crypto)
        try:
            fast_entities = extract_fast(text)
            for entity_type, values in fast_entities.items():
                for val in values:
                    result.add(ExtractedEntity(
                        value=val,
                        entity_type=entity_type,
                        confidence=0.9,
                        source="pacman_fast",
                    ))
        except Exception as e:
            logger.warning(f"PACMAN fast extraction failed: {e}")

        # 2. Person extraction
        try:
            persons = extract_persons(text, max_results=30)
            for p in persons:
                result.add(ExtractedEntity(
                    value=p["name"],
                    entity_type="PERSON",
                    confidence=p["confidence"],
                    source=f"pacman_person_{p['source']}",
                ))
        except Exception as e:
            logger.warning(f"PACMAN person extraction failed: {e}")

        # 3. Company extraction
        try:
            companies = extract_companies(text, max_results=20)
            for c in companies:
                result.add(ExtractedEntity(
                    value=c["name"],
                    entity_type="COMPANY",
                    confidence=c["confidence"],
                    source=f"pacman_company_{c['source']}",
                    metadata={"suffix": c.get("suffix"), "crn": c.get("crn")},
                ))
        except Exception as e:
            logger.warning(f"PACMAN company extraction failed: {e}")

    def _extract_fallback(self, text: str, result: ExtractionResult):
        """Fallback extraction using simple patterns."""
        for pattern_name, pattern in FALLBACK_PATTERNS.items():
            matches = pattern.findall(text)
            for match in set(matches)[:50]:  # Limit and dedupe
                result.add(ExtractedEntity(
                    value=match,
                    entity_type=pattern_name,
                    confidence=0.7,
                    source="fallback_regex",
                ))

    def _strip_html(self, content: str) -> str:
        """Remove HTML tags from content."""
        # Simple HTML stripping
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url if "://" in url else f"https://{url}")
            return parsed.netloc
        except:
            return ""


def extract_from_content(
    content: str,
    url: str = "",
    domain: str = "",
) -> ExtractionResult:
    """
    Quick extraction function.

    Usage:
        result = extract_from_content(html_content, url="https://example.com")
        print(f"Found {len(result.entities)} entities")
    """
    extractor = PACMANExtractor()
    return extractor.extract(content, url=url, domain=domain)


async def extract_from_results(
    results: List["DiveResult"],
    callback=None,
) -> List[ExtractionResult]:
    """
    Extract entities from multiple DiveResults.

    Args:
        results: List of DiveResult from DeepDiver
        callback: Optional callback for progress updates

    Returns:
        List of ExtractionResult
    """
    extractor = PACMANExtractor()
    extractions = []

    for i, dive_result in enumerate(results):
        extraction = extractor.extract(
            content=dive_result.content,
            url=dive_result.url,
            domain=dive_result.domain,
        )
        extractions.append(extraction)

        if callback:
            callback(i + 1, len(results), extraction)

    return extractions


# Import DiveResult type hint
try:
    from deep_dive.diver import DiveResult
except ImportError:
    DiveResult = Any


# Test
if __name__ == "__main__":
    test_content = """
    <html>
    <body>
    <h1>Company Profile</h1>
    <p>John Smith, CEO of Acme Corporation Ltd, can be reached at john.smith@acme.com
    or by phone at +1-555-123-4567.</p>
    <p>The company is registered with LEI 529900T8BM49AURSDO55 and
    VAT number GB123456789.</p>
    <p>Wire transfers can be sent to IBAN GB82 WEST 1234 5698 7654 32.</p>
    <p>Bitcoin donations: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa</p>
    </body>
    </html>
    """

    result = extract_from_content(test_content, url="https://example.com/about")

    print(f"URL: {result.url}")
    print(f"Total entities: {len(result.entities)}")
    print(f"By type: {result.raw_counts}")
    print("\nEntities:")
    for e in result.entities:
        print(f"  [{e.entity_type}] {e.value} (conf: {e.confidence:.2f}, src: {e.source})")
