"""
Unified Entity Extractor

CORRECT EXTRACTION ARCHITECTURE:
- Email: Regex extraction (fast, reliable)
- Phone: GLiNER + phonenumbers (local, validated)
- Person/Company/Relationships: Haiku 4.5 extracts FROM SCRATCH

Schema.org JSON-LD is also used when available (free, fast, high confidence).

Usage:
    from linklater.extraction import extract_entities

    # Full extraction (recommended)
    entities = await extract_entities(
        html="<html>...",
        url="https://example.com",
    )
    # Returns: {"persons": [...], "companies": [...], "emails": [...], "phones": [...], "edges": [...]}

    # Legacy mode (uses old backend system)
    entities = await extract_entities(
        html="<html>...",
        url="https://example.com",
        use_legacy_flow=True,
        backend="gemini"  # or "gpt", "gliner", "regex"
    )
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, Set
from .models import Entity, Edge, ExtractionResult

# Schema extraction (first pass - free, fast)
from .schema_extractor import extract_schemas, has_schema_markup, SchemaEntity

# Centralized logging
from ..config import get_logger
logger = get_logger(__name__)

# Available backends (lazy loaded)
_backends = {}
_relationship_backend = None


def _get_backend(name: str):
    """Get or create a backend instance."""
    if name not in _backends:
        if name == "gemini":
            from .backends.gemini import GeminiBackend
            _backends[name] = GeminiBackend()
        elif name == "regex":
            from .backends.regex import RegexBackend
            _backends[name] = RegexBackend()
        elif name == "gpt":
            try:
                from .backends.gpt import GPTBackend
                _backends[name] = GPTBackend()
            except ImportError:
                return None
        elif name == "gliner":
            try:
                from .backends.gliner import GLiNERBackend
                _backends[name] = GLiNERBackend()
            except ImportError:
                return None
    return _backends.get(name)


def _select_backend(backend: str = "auto") -> str:
    """Select best available backend."""
    if backend != "auto":
        return backend

    # Priority: gemini > gpt > regex (gliner is slow to load)
    for name in ["gemini", "gpt", "regex"]:
        if _get_backend(name) is not None:
            return name

    return "regex"  # Fallback


def _get_relationship_backend():
    """Get or create the Haiku relationship backend (Layer 4) - LEGACY."""
    global _relationship_backend
    if _relationship_backend is None:
        try:
            from .backends.haiku import HaikuBackend
            _relationship_backend = HaikuBackend()
            logger.info("Haiku relationship backend loaded")
        except ImportError as e:
            logger.warning(f"Haiku backend not available: {e}")
        except Exception as e:
            logger.error(f"Failed to load Haiku backend: {e}")
    return _relationship_backend


# Haiku backend for full extraction (persons + companies + relationships)
_haiku_backend = None


def _get_haiku_backend():
    """Get or create the Haiku backend for full entity + relationship extraction."""
    global _haiku_backend
    if _haiku_backend is None:
        try:
            from .backends.haiku import HaikuBackend
            _haiku_backend = HaikuBackend()
            logger.info("Haiku backend loaded for full extraction")
        except ImportError as e:
            logger.warning(f"Haiku backend not available: {e}")
        except Exception as e:
            logger.error(f"Failed to load Haiku backend: {e}")
    return _haiku_backend


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text for relationship extraction."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator=' ', strip=True)
    except Exception:
        # Fallback: basic tag removal
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        return ' '.join(text.split())


def _schema_to_entities(schema_result, url: str) -> ExtractionResult:
    """
    Convert Schema.org extraction result to Entity models.

    Schema entities get confidence=1.0 (machine-readable, high trust).
    """
    result = ExtractionResult()

    # Organizations → companies
    for org in schema_result.organizations:
        if org.name:
            result.companies.append(Entity(
                value=org.name,
                type="company",
                archive_urls=[url] if url else [],
                confidence=1.0,  # Schema = high confidence
            ))

    # Local businesses → companies
    for biz in schema_result.local_businesses:
        if biz.name:
            result.companies.append(Entity(
                value=biz.name,
                type="company",
                archive_urls=[url] if url else [],
                confidence=1.0,
            ))
            # Also extract phone/email if present
            if biz.telephone:
                result.phones.append(Entity(
                    value=biz.telephone,
                    type="phone",
                    archive_urls=[url] if url else [],
                    confidence=1.0,
                ))
            if biz.email:
                result.emails.append(Entity(
                    value=biz.email,
                    type="email",
                    archive_urls=[url] if url else [],
                    confidence=1.0,
                ))

    # Persons
    for person in schema_result.persons:
        if person.name:
            result.persons.append(Entity(
                value=person.name,
                type="person",
                archive_urls=[url] if url else [],
                confidence=1.0,
            ))
            # Also extract email/phone if present
            if person.email:
                result.emails.append(Entity(
                    value=person.email,
                    type="email",
                    archive_urls=[url] if url else [],
                    confidence=1.0,
                ))
            if person.telephone:
                result.phones.append(Entity(
                    value=person.telephone,
                    type="phone",
                    archive_urls=[url] if url else [],
                    confidence=1.0,
                ))

    return result


def _merge_results(
    schema_result: ExtractionResult,
    backend_result: ExtractionResult,
) -> ExtractionResult:
    """
    Merge schema and backend results, deduplicating by value.

    Schema entities take priority (higher confidence).
    """
    merged = ExtractionResult()

    # Track seen values to avoid duplicates
    seen_persons: Set[str] = set()
    seen_companies: Set[str] = set()
    seen_emails: Set[str] = set()
    seen_phones: Set[str] = set()

    # Add schema entities first (they have higher confidence)
    for p in schema_result.persons:
        key = p.value.lower().strip()
        if key not in seen_persons:
            seen_persons.add(key)
            merged.persons.append(p)

    for c in schema_result.companies:
        key = c.value.lower().strip()
        if key not in seen_companies:
            seen_companies.add(key)
            merged.companies.append(c)

    for e in schema_result.emails:
        key = e.value.lower().strip()
        if key not in seen_emails:
            seen_emails.add(key)
            merged.emails.append(e)

    for ph in schema_result.phones:
        # Normalize phone for comparison
        key = ''.join(c for c in ph.value if c.isdigit())
        if key not in seen_phones:
            seen_phones.add(key)
            merged.phones.append(ph)

    # Add backend entities (only if not already seen)
    for p in backend_result.persons:
        key = p.value.lower().strip()
        if key not in seen_persons:
            seen_persons.add(key)
            merged.persons.append(p)

    for c in backend_result.companies:
        key = c.value.lower().strip()
        if key not in seen_companies:
            seen_companies.add(key)
            merged.companies.append(c)

    for e in backend_result.emails:
        key = e.value.lower().strip()
        if key not in seen_emails:
            seen_emails.add(key)
            merged.emails.append(e)

    for ph in backend_result.phones:
        key = ''.join(c for c in ph.value if c.isdigit())
        if key not in seen_phones:
            seen_phones.add(key)
            merged.phones.append(ph)

    return merged


async def extract_entities(
    html: str,
    url: str = "",
    backend: str = "auto",
    entity_types: List[str] = None,
    skip_schema: bool = False,
    extract_relationships: bool = True,  # Default to True for correct flow
    use_legacy_flow: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Extract entities from HTML content using the CORRECT architecture:

    CORRECT FLOW (default):
    1. Schema.org JSON-LD (free, fast, confidence=1.0) - for any entities
    2. Regex for emails (fast, reliable)
    3. GLiNER + phonenumbers for phones (local, validated)
    4. Haiku 4.5 for persons + companies + relationships FROM SCRATCH

    LEGACY FLOW (use_legacy_flow=True):
    1. Schema.org
    2. Selected backend (gemini/gpt/gliner/regex) for all entities
    3. Haiku for relationships only (if extract_relationships=True)

    Args:
        html: HTML content to extract from
        url: Source URL (for provenance tracking)
        backend: "auto", "gemini", "gpt", "gliner", or "regex" (legacy only)
        entity_types: Types to extract (legacy only)
        skip_schema: Skip schema extraction
        extract_relationships: Extract relationships (default True)
        use_legacy_flow: Use old extraction flow (default False)

    Returns:
        Dictionary with entity lists: {"persons": [...], "companies": [...], "edges": [...]}
    """
    if use_legacy_flow:
        return await _extract_entities_legacy(
            html, url, backend, entity_types, skip_schema, extract_relationships
        )

    # =========================================================================
    # CORRECT EXTRACTION FLOW
    # =========================================================================
    start = time.time()
    result = ExtractionResult()

    # Convert HTML to plain text once
    text = _html_to_text(html)

    # LAYER 1: Schema.org extraction (free, fast, high confidence)
    if not skip_schema and has_schema_markup(html):
        try:
            schema_result = extract_schemas(html, url)
            if schema_result.total_entities > 0:
                schema_entities = _schema_to_entities(schema_result, url)
                # Add schema entities to result
                result.persons.extend(schema_entities.persons)
                result.companies.extend(schema_entities.companies)
                result.emails.extend(schema_entities.emails)
                result.phones.extend(schema_entities.phones)
                logger.debug(f"Schema extracted {schema_entities.total_entities} entities from {url}")
        except Exception as e:
            logger.debug(f"Schema extraction failed: {e}")

    # LAYER 2: Regex for emails (fast, reliable)
    try:
        regex_backend = _get_backend("regex")
        if regex_backend:
            regex_result = await regex_backend.extract(html, url, ["email"])
            # Add emails not already found
            seen_emails = {e.value.lower() for e in result.emails}
            for email in regex_result.emails:
                if email.value.lower() not in seen_emails:
                    seen_emails.add(email.value.lower())
                    result.emails.append(email)
    except Exception as e:
        logger.debug(f"Regex email extraction failed: {e}")

    # LAYER 3: GLiNER + phonenumbers for phones (local, validated)
    try:
        gliner_backend = _get_backend("gliner")
        if gliner_backend:
            gliner_result = gliner_backend.extract(html, url, include_emails=False, include_phones=True)
            # Add phones not already found
            seen_phones = {p.value for p in result.phones}
            for phone in gliner_result.get("phones", []):
                phone_val = phone.get("value", "")
                if phone_val and phone_val not in seen_phones:
                    seen_phones.add(phone_val)
                    result.phones.append(Entity(
                        value=phone_val,
                        type="phone",
                        archive_urls=[url] if url else [],
                        confidence=phone.get("confidence", 0.9),
                    ))
    except Exception as e:
        logger.debug(f"GLiNER phone extraction failed: {e}")

    # LAYER 4: Haiku for persons + companies + relationships + ET3 FROM SCRATCH
    haiku_backend = _get_haiku_backend()
    if haiku_backend and len(text) > 50:
        try:
            haiku_result = await haiku_backend.extract_all(text, url)

            # Add persons not already found
            seen_persons = {p.value.lower() for p in result.persons}
            for person in haiku_result.get("persons", []):
                if person.value.lower() not in seen_persons:
                    seen_persons.add(person.value.lower())
                    result.persons.append(person)

            # Add companies not already found
            seen_companies = {c.value.lower() for c in result.companies}
            for company in haiku_result.get("companies", []):
                if company.value.lower() not in seen_companies:
                    seen_companies.add(company.value.lower())
                    result.companies.append(company)

            # Add all edges
            result.edges = haiku_result.get("edges", [])
            result.relationship_backend = "haiku-4.5"

            # ET3: Add themes, phenomena, events
            result.themes = haiku_result.get("themes", [])
            result.phenomena = haiku_result.get("phenomena", [])
            result.events = haiku_result.get("events", [])

            logger.debug(
                f"Haiku extracted {len(result.persons)} persons, {len(result.companies)} companies, "
                f"{len(result.edges)} edges, {len(result.themes)} themes, "
                f"{len(result.phenomena)} phenomena, {len(result.events)} events from {url}"
            )

        except Exception as e:
            logger.warning(f"Haiku extraction failed: {e}")
            # Fallback to legacy flow for persons/companies
            try:
                selected = _select_backend(backend)
                extractor = _get_backend(selected)
                if extractor:
                    fallback_result = await extractor.extract(html, url, ["person", "company"])
                    seen_persons = {p.value.lower() for p in result.persons}
                    seen_companies = {c.value.lower() for c in result.companies}
                    for p in fallback_result.persons:
                        if p.value.lower() not in seen_persons:
                            result.persons.append(p)
                    for c in fallback_result.companies:
                        if c.value.lower() not in seen_companies:
                            result.companies.append(c)
            except Exception:
                pass

    result.backend_used = "correct_flow"
    result.processing_time = time.time() - start
    return result.to_dict()


async def _extract_entities_legacy(
    html: str,
    url: str = "",
    backend: str = "auto",
    entity_types: List[str] = None,
    skip_schema: bool = False,
    extract_relationships: bool = False,
) -> Dict[str, List[Dict]]:
    """
    LEGACY extraction flow - kept for backwards compatibility.

    Uses selected backend for all entity types, then Haiku for relationships only.
    """
    if entity_types is None:
        entity_types = ["person", "company", "email", "phone"]

    start = time.time()
    schema_entities = ExtractionResult()

    # LAYER 1: Schema.org extraction (free, fast, high confidence)
    if not skip_schema and has_schema_markup(html):
        try:
            schema_result = extract_schemas(html, url)
            if schema_result.total_entities > 0:
                schema_entities = _schema_to_entities(schema_result, url)
                logger.debug(f"Schema extracted {schema_entities.total_entities} entities from {url}")
        except Exception as e:
            logger.debug(f"Schema extraction failed: {e}")

    # LAYER 2: Backend extraction (fills gaps)
    selected = _select_backend(backend)
    extractor = _get_backend(selected)

    backend_entities = ExtractionResult()
    if extractor is not None:
        try:
            backend_entities = await extractor.extract(html, url, entity_types)
        except Exception as e:
            logger.warning(f"Error with {selected}: {e}")
            # Fallback to regex
            if selected != "regex":
                regex_backend = _get_backend("regex")
                if regex_backend:
                    backend_entities = await regex_backend.extract(html, url, entity_types)
                    selected = "regex"

    # LAYER 3: Merge results (schema takes priority)
    if schema_entities.total_entities > 0:
        result = _merge_results(schema_entities, backend_entities)
        result.backend_used = f"schema+{selected}"
    else:
        result = backend_entities
        result.backend_used = selected

    # LAYER 4: Relationship extraction (optional, uses Haiku)
    if extract_relationships and result.total_entities >= 2:
        relationship_backend = _get_relationship_backend()
        if relationship_backend:
            try:
                # Get all entities as a flat list
                all_entities = result.persons + result.companies + result.emails + result.phones

                # Convert HTML to plain text for relationship extraction
                text = _html_to_text(html)

                # Extract relationships
                edges = await relationship_backend.extract_relationships(
                    text=text,
                    entities=all_entities,
                    url=url
                )

                result.edges = edges
                result.relationship_backend = "haiku-4.5"
                logger.debug(f"Extracted {len(edges)} relationships from {url}")

            except Exception as e:
                logger.warning(f"Relationship extraction failed: {e}")

    result.processing_time = time.time() - start
    return result.to_dict()


class EntityExtractor:
    """
    Entity extractor class for batch operations with layered extraction.

    Extraction order:
    1. Schema.org JSON-LD (free, fast, confidence=1.0)
    2. Selected backend fills gaps
    3. Results merged
    4. [Optional] Haiku extracts relationships (Layer 4)

    Usage:
        extractor = EntityExtractor(backend="gemini")
        for html in pages:
            result = await extractor.extract(html, url)

        # With relationship extraction
        extractor = EntityExtractor(backend="gemini", use_relationships=True)
        result = await extractor.extract(html, url)
        print(result.edges)  # Relationships found
    """

    def __init__(
        self,
        backend: str = "auto",
        use_schema: bool = True,
        use_relationships: bool = False
    ):
        self.backend = _select_backend(backend)
        self._extractor = _get_backend(self.backend)
        self.use_schema = use_schema
        self.use_relationships = use_relationships
        self._relationship_backend = None

        # Lazy load relationship backend if needed
        if use_relationships:
            self._relationship_backend = _get_relationship_backend()

    async def extract(
        self,
        html: str,
        url: str = "",
        entity_types: List[str] = None,
        extract_relationships: bool = None
    ) -> ExtractionResult:
        """
        Extract entities from HTML using layered approach.

        Args:
            html: HTML content
            url: Source URL
            entity_types: Types to extract
            extract_relationships: Override instance setting for this call

        Returns:
            ExtractionResult with entities and optionally edges
        """
        if entity_types is None:
            entity_types = ["person", "company", "email", "phone"]

        # Use instance setting unless overridden
        do_relationships = extract_relationships if extract_relationships is not None else self.use_relationships

        schema_entities = ExtractionResult()

        # LAYER 1: Schema.org (if enabled)
        if self.use_schema and has_schema_markup(html):
            try:
                schema_result = extract_schemas(html, url)
                if schema_result.total_entities > 0:
                    schema_entities = _schema_to_entities(schema_result, url)
            except Exception:
                pass

        # LAYER 2: Backend extraction
        backend_entities = ExtractionResult()
        if self._extractor is not None:
            try:
                backend_entities = await self._extractor.extract(html, url, entity_types)
            except Exception:
                pass

        # LAYER 3: Merge
        if schema_entities.total_entities > 0:
            result = _merge_results(schema_entities, backend_entities)
            result.backend_used = f"schema+{self.backend}"
        else:
            result = backend_entities
            result.backend_used = self.backend

        # LAYER 4: Relationship extraction (optional)
        if do_relationships and result.total_entities >= 2:
            rel_backend = self._relationship_backend or _get_relationship_backend()
            if rel_backend:
                try:
                    all_entities = result.persons + result.companies + result.emails + result.phones
                    text = _html_to_text(html)
                    edges = await rel_backend.extract_relationships(text, all_entities, url)
                    result.edges = edges
                    result.relationship_backend = "haiku-4.5"
                except Exception:
                    pass

        return result

    async def extract_batch(
        self,
        pages: List[Dict[str, str]],  # [{"html": "...", "url": "..."}]
        entity_types: List[str] = None,
        extract_relationships: bool = None
    ) -> List[ExtractionResult]:
        """Extract entities from multiple pages in parallel."""
        tasks = [
            self.extract(
                page["html"],
                page.get("url", ""),
                entity_types,
                extract_relationships
            )
            for page in pages
        ]
        return await asyncio.gather(*tasks)
