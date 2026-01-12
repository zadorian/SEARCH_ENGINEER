"""
EXIF Entity Extractor - Extract person names from metadata using Claude Haiku.

Collects all metadata from a domain scan and uses AI to:
1. Identify person names from Author/Creator fields
2. Extract company names
3. Parse software/tools used
4. Identify locations from GPS coordinates
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """Entity extracted from metadata."""
    value: str
    entity_type: str  # person, company, software, location
    confidence: float
    source_urls: List[str] = field(default_factory=list)
    metadata_field: Optional[str] = None
    context: Optional[str] = None


@dataclass
class DateInfo:
    """Date information from file metadata."""
    date_str: str
    date_type: str  # creation, modified, original
    source_url: str
    parsed_year: Optional[int] = None
    parsed_date: Optional[str] = None  # ISO format


@dataclass
class EntityExtractionResult:
    """Result of entity extraction from metadata."""
    domain: str
    persons: List[ExtractedEntity] = field(default_factory=list)
    companies: List[ExtractedEntity] = field(default_factory=list)
    software: List[ExtractedEntity] = field(default_factory=list)
    locations: List[ExtractedEntity] = field(default_factory=list)
    dates: List[DateInfo] = field(default_factory=list)
    raw_ai_response: Optional[str] = None

    # Date aggregates
    earliest_creation: Optional[str] = None
    latest_modification: Optional[str] = None
    date_range: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "persons": [{"name": e.value, "confidence": e.confidence, "sources": e.source_urls} for e in self.persons],
            "companies": [{"name": e.value, "confidence": e.confidence, "sources": e.source_urls} for e in self.companies],
            "software": [{"name": e.value, "confidence": e.confidence, "sources": e.source_urls} for e in self.software],
            "locations": [{"coords": e.value, "confidence": e.confidence, "context": e.context} for e in self.locations],
            "dates": {
                "all": [{"date": d.date_str, "type": d.date_type, "source": d.source_url, "year": d.parsed_year} for d in self.dates],
                "earliest_creation": self.earliest_creation,
                "latest_modification": self.latest_modification,
                "date_range": self.date_range,
            },
        }

    def all_entities(self) -> List[ExtractedEntity]:
        return self.persons + self.companies + self.software + self.locations


async def extract_persons_from_metadata(
    scan_result: Any,
    use_ai: bool = True
) -> EntityExtractionResult:
    """
    Extract person names and entities from metadata scan results.

    Uses Claude Haiku to analyze Author/Creator fields and identify real people.

    Args:
        scan_result: ScanResult from MetadataScanner
        use_ai: Whether to use AI for extraction (default True)

    Returns:
        EntityExtractionResult with extracted entities
    """
    domain = scan_result.domain if hasattr(scan_result, "domain") else "unknown"
    result = EntityExtractionResult(domain=domain)

    # Collect all metadata fields
    authors: Dict[str, List[str]] = {}  # author -> [source_urls]
    companies: Dict[str, List[str]] = {}
    software_list: Dict[str, List[str]] = {}
    creation_dates: List[DateInfo] = []
    modification_dates: List[DateInfo] = []

    for meta in scan_result.results:
        url = meta.url

        # Authors
        if meta.author:
            author = meta.author.strip()
            if author and len(author) > 1:
                authors.setdefault(author, []).append(url)

        # Companies
        if meta.company:
            company = meta.company.strip()
            if company and len(company) > 1:
                companies.setdefault(company, []).append(url)

        # Software
        if meta.software:
            sw = meta.software.strip()
            if sw and len(sw) > 1:
                software_list.setdefault(sw, []).append(url)

        # GPS locations
        if meta.gps_lat and meta.gps_lon:
            result.locations.append(ExtractedEntity(
                value=f"{meta.gps_lat},{meta.gps_lon}",
                entity_type="location",
                confidence=1.0,
                source_urls=[url],
                context=f"GPS from {url}"
            ))

        # Creation dates
        if hasattr(meta, "create_date") and meta.create_date:
            parsed = _parse_date(meta.create_date)
            creation_dates.append(DateInfo(
                date_str=meta.create_date,
                date_type="creation",
                source_url=url,
                parsed_year=parsed.get("year"),
                parsed_date=parsed.get("iso")
            ))

        # Modification dates
        if hasattr(meta, "modify_date") and meta.modify_date:
            parsed = _parse_date(meta.modify_date)
            modification_dates.append(DateInfo(
                date_str=meta.modify_date,
                date_type="modified",
                source_url=url,
                parsed_year=parsed.get("year"),
                parsed_date=parsed.get("iso")
            ))

        # Original date (from EXIF DateTimeOriginal - when photo was taken)
        if hasattr(meta, "original_date") and meta.original_date:
            parsed = _parse_date(meta.original_date)
            creation_dates.append(DateInfo(
                date_str=meta.original_date,
                date_type="original",
                source_url=url,
                parsed_year=parsed.get("year"),
                parsed_date=parsed.get("iso")
            ))

    # First pass: Extract obvious person names with regex patterns
    obvious_persons = _extract_obvious_persons(authors)
    for person, sources in obvious_persons.items():
        result.persons.append(ExtractedEntity(
            value=person,
            entity_type="person",
            confidence=0.9,
            source_urls=sources,
            metadata_field="Author"
        ))

    # Add obvious companies
    for company, sources in companies.items():
        if _is_likely_company(company):
            result.companies.append(ExtractedEntity(
                value=company,
                entity_type="company",
                confidence=0.8,
                source_urls=sources,
                metadata_field="Company"
            ))

    # Add software
    for sw, sources in software_list.items():
        result.software.append(ExtractedEntity(
            value=sw,
            entity_type="software",
            confidence=0.9,
            source_urls=sources,
            metadata_field="Software"
        ))

    # Use AI to identify additional persons from ambiguous author fields
    if use_ai and authors:
        ai_entities = await _ai_extract_persons(
            list(authors.keys()),
            list(companies.keys()),
            domain
        )
        if ai_entities:
            result.raw_ai_response = ai_entities.get("raw")

            # Add AI-identified persons
            for person_data in ai_entities.get("persons", []):
                name = person_data.get("name", "").strip()
                if name and not _entity_exists(result.persons, name):
                    result.persons.append(ExtractedEntity(
                        value=name,
                        entity_type="person",
                        confidence=person_data.get("confidence", 0.7),
                        source_urls=authors.get(name, []),
                        metadata_field="Author",
                        context=person_data.get("reasoning")
                    ))

            # Add AI-identified companies
            for company_data in ai_entities.get("companies", []):
                name = company_data.get("name", "").strip()
                if name and not _entity_exists(result.companies, name):
                    result.companies.append(ExtractedEntity(
                        value=name,
                        entity_type="company",
                        confidence=company_data.get("confidence", 0.7),
                        source_urls=companies.get(name, []) or authors.get(name, []),
                        context=company_data.get("reasoning")
                    ))

    # Dedupe
    result.persons = _dedupe_entities(result.persons)
    result.companies = _dedupe_entities(result.companies)
    result.software = _dedupe_entities(result.software)
    result.locations = _dedupe_entities(result.locations)

    # Aggregate dates
    result.dates = creation_dates + modification_dates

    # Calculate date aggregates
    if creation_dates:
        # Find earliest creation date
        creation_isos = [d.parsed_date for d in creation_dates if d.parsed_date]
        if creation_isos:
            result.earliest_creation = min(creation_isos)

    if modification_dates:
        # Find latest modification date
        mod_isos = [d.parsed_date for d in modification_dates if d.parsed_date]
        if mod_isos:
            result.latest_modification = max(mod_isos)

    # Calculate date range (earliest to latest across all dates)
    all_isos = [d.parsed_date for d in result.dates if d.parsed_date]
    if all_isos:
        earliest = min(all_isos)
        latest = max(all_isos)
        if earliest != latest:
            result.date_range = f"{earliest} to {latest}"
        else:
            result.date_range = earliest

    logger.info(
        f"Extracted {len(result.persons)} persons, {len(result.companies)} companies, "
        f"{len(result.software)} software, {len(result.locations)} locations, "
        f"{len(result.dates)} dates"
    )

    return result


def _extract_obvious_persons(authors: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Extract obvious person names using patterns.

    Patterns for real names:
    - Two or more capitalized words
    - Contains common first names
    - Not all caps
    - Not a company name pattern
    """
    persons = {}

    # Common first names (partial list for pattern matching)
    COMMON_FIRST_NAMES = {
        "john", "james", "michael", "david", "robert", "william", "richard",
        "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara",
        "peter", "paul", "mark", "steven", "andrew", "daniel", "matthew",
        "hans", "klaus", "wolfgang", "franz", "pierre", "jean", "giuseppe",
        "marco", "carlos", "jose", "maria", "anna", "sarah", "emma", "lisa",
    }

    for author, urls in authors.items():
        # Skip if too short
        if len(author) < 3:
            continue

        # Skip if all caps (likely acronym or company)
        if author.isupper():
            continue

        # Skip common software/company patterns
        if _is_likely_software(author) or _is_likely_company(author):
            continue

        # Check if looks like a person name
        words = author.split()

        # Two or three words, each capitalized
        if 2 <= len(words) <= 4:
            if all(w[0].isupper() for w in words if len(w) > 1):
                # Check for common first name
                first = words[0].lower()
                if first in COMMON_FIRST_NAMES:
                    persons[author] = urls
                    continue

                # Check if second word is also capitalized (Last, First format)
                if len(words) >= 2 and words[1][0].isupper():
                    persons[author] = urls

    return persons


def _is_likely_company(text: str) -> bool:
    """Check if text is likely a company name."""
    text_lower = text.lower()

    company_indicators = [
        " inc", " llc", " ltd", " corp", " gmbh", " ag", " sa", " nv",
        " plc", " co.", " company", " group", " holdings", " partners",
        " solutions", " systems", " technologies", " software", " consulting",
        "microsoft", "adobe", "google", "apple", "oracle", "ibm",
    ]

    return any(ind in text_lower for ind in company_indicators)


def _is_likely_software(text: str) -> bool:
    """Check if text is likely software/tool name."""
    text_lower = text.lower()

    software_indicators = [
        "adobe", "microsoft", "photoshop", "illustrator", "acrobat",
        "word", "excel", "powerpoint", "libreoffice", "openoffice",
        "scanner", "camera", "iphone", "android", "canon", "nikon",
        "preview", "pdf", "version", "build", " v.", " v1", " v2",
    ]

    return any(ind in text_lower for ind in software_indicators)


def _parse_date(date_str: str) -> Dict[str, Any]:
    """
    Parse various date formats and extract year and ISO date.

    Handles formats:
    - EXIF: "2023:05:15 10:30:00"
    - ISO: "2023-05-15T10:30:00"
    - PDF: "D:20230515103000"
    - Various: "May 15, 2023", "15/05/2023", etc.

    Returns:
        Dict with "year" (int) and "iso" (str in YYYY-MM-DD format)
    """
    from datetime import datetime

    if not date_str:
        return {}

    date_str = str(date_str).strip()

    # Common date patterns to try
    patterns = [
        # EXIF format
        ("%Y:%m:%d %H:%M:%S", None),
        ("%Y:%m:%d", None),
        # ISO formats
        ("%Y-%m-%dT%H:%M:%S", None),
        ("%Y-%m-%dT%H:%M:%SZ", None),
        ("%Y-%m-%d %H:%M:%S", None),
        ("%Y-%m-%d", None),
        # US formats
        ("%m/%d/%Y %H:%M:%S", None),
        ("%m/%d/%Y", None),
        # European formats
        ("%d/%m/%Y %H:%M:%S", None),
        ("%d/%m/%Y", None),
        ("%d.%m.%Y", None),
        # Written formats
        ("%B %d, %Y", None),
        ("%b %d, %Y", None),
        ("%d %B %Y", None),
        ("%d %b %Y", None),
    ]

    # Handle PDF date format: D:20230515103000
    if date_str.startswith("D:"):
        date_str = date_str[2:]
        # Remove timezone if present
        if "+" in date_str:
            date_str = date_str.split("+")[0]
        if "-" in date_str and len(date_str) > 8:
            # Could be timezone offset
            pass
        patterns = [
            ("%Y%m%d%H%M%S", None),
            ("%Y%m%d", None),
        ] + patterns

    # Try each pattern
    for pattern, _ in patterns:
        try:
            dt = datetime.strptime(date_str[:len(datetime.strptime("2000-01-01", "%Y-%m-%d").strftime(pattern))], pattern)
        except (ValueError, TypeError):
            try:
                dt = datetime.strptime(date_str, pattern)
            except (ValueError, TypeError):
                continue

        return {
            "year": dt.year,
            "iso": dt.strftime("%Y-%m-%d")
        }

    # Fallback: try to extract year with regex
    year_match = re.search(r'(19|20)\d{2}', date_str)
    if year_match:
        return {"year": int(year_match.group()), "iso": None}

    return {}


def _entity_exists(entities: List[ExtractedEntity], name: str) -> bool:
    """Check if entity already exists (case-insensitive)."""
    name_lower = name.lower()
    return any(e.value.lower() == name_lower for e in entities)


def _dedupe_entities(entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
    """Deduplicate entities by name, keeping highest confidence."""
    seen: Dict[str, ExtractedEntity] = {}

    for entity in entities:
        key = entity.value.lower()
        if key not in seen or entity.confidence > seen[key].confidence:
            # Merge source URLs
            if key in seen:
                entity.source_urls = list(set(entity.source_urls + seen[key].source_urls))
            seen[key] = entity

    return list(seen.values())


async def _ai_extract_persons(
    authors: List[str],
    companies: List[str],
    domain: str
) -> Optional[Dict]:
    """
    Use Claude Haiku to identify person names from author fields.

    Returns:
        Dict with "persons" and "companies" lists, each with name/confidence/reasoning
    """
    if not authors:
        return None

    # Build prompt
    prompt = f"""Analyze these metadata Author/Creator fields from files on {domain}.

AUTHOR FIELDS:
{chr(10).join(f"- {a}" for a in authors[:100])}

COMPANY FIELDS (for reference):
{chr(10).join(f"- {c}" for c in companies[:50]) if companies else "None found"}

TASK: Identify which Author fields are REAL PERSON NAMES vs software/companies/usernames.

For each entry, determine:
1. Is it a real person's name? (First Last, or Last, First format)
2. Is it a company/organization?
3. Is it software/tool name?
4. Is it a username/handle?

Return JSON:
{{
  "persons": [
    {{"name": "John Smith", "confidence": 0.95, "reasoning": "Standard Western name format"}}
  ],
  "companies": [
    {{"name": "Acme Corp", "confidence": 0.9, "reasoning": "Contains 'Corp' suffix"}}
  ]
}}

Only include entries with confidence > 0.6. Focus on REAL PERSON NAMES.
Return ONLY valid JSON, no other text."""

    try:
        # Try to use brain.py
        from modules.brain import ask_ai

        response = await ask_ai(
            prompt,
            model="claude-haiku-4-5-20251001",  # Fast and cheap
            max_tokens=2000
        )

        # Parse JSON from response
        if response:
            # Find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                result["raw"] = response
                return result

    except ImportError:
        logger.debug("brain.py not available, trying direct API")

        # Fallback: Try Anthropic API directly
        try:
            import anthropic

            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            if response.content:
                text = response.content[0].text
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    result = json.loads(json_match.group())
                    result["raw"] = text
                    return result

        except Exception as e:
            logger.error(f"Anthropic API failed: {e}")

    except Exception as e:
        logger.error(f"AI extraction failed: {e}")

    return None


async def extract_and_save_entities(
    scan_result: Any,
    save_to_elastic: bool = True
) -> EntityExtractionResult:
    """
    Extract entities and optionally save to Elasticsearch.

    Args:
        scan_result: ScanResult from MetadataScanner
        save_to_elastic: Whether to save entities to ES

    Returns:
        EntityExtractionResult
    """
    result = await extract_persons_from_metadata(scan_result)

    if save_to_elastic and (result.persons or result.companies):
        try:
            await _save_to_elasticsearch(result)
        except Exception as e:
            logger.error(f"Failed to save to Elasticsearch: {e}")

    return result


async def _save_to_elasticsearch(result: EntityExtractionResult):
    """Save extracted entities to Elasticsearch."""
    try:
        from elasticsearch import AsyncElasticsearch
        import os

        es_host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        es = AsyncElasticsearch([es_host])

        try:
            # Save each person entity
            for person in result.persons:
                doc = {
                    "entity_type": "person",
                    "name": person.value,
                    "confidence": person.confidence,
                    "source_domain": result.domain,
                    "source_urls": person.source_urls,
                    "extraction_method": "exif_metadata",
                    "metadata_field": person.metadata_field,
                }

                await es.index(
                    index="entities-exif",
                    document=doc
                )

            # Save each company entity
            for company in result.companies:
                doc = {
                    "entity_type": "company",
                    "name": company.value,
                    "confidence": company.confidence,
                    "source_domain": result.domain,
                    "source_urls": company.source_urls,
                    "extraction_method": "exif_metadata",
                }

                await es.index(
                    index="entities-exif",
                    document=doc
                )

            logger.info(f"Saved {len(result.persons)} persons and {len(result.companies)} companies to ES")

        finally:
            await es.close()

    except ImportError:
        logger.warning("elasticsearch package not installed")
    except Exception as e:
        logger.error(f"ES save failed: {e}")
