"""
LINKLATER Entity Extraction Module

Unified entity extraction with pluggable backends:
- Gemini 2.0 Flash (default, fast cloud API)
- GPT-5-nano (OpenAI cloud)
- GLiNER (local model)
- Regex patterns (no API, fallback)

Schema.org extraction (no LLM needed):
- JSON-LD structured data
- Organization, Person, LocalBusiness, Product, Event schemas
- High-confidence machine-readable facts

Relationship extraction (Layer 4):
- Claude Haiku 4.5 for edges between entities
- Comprehensive edge schema (25+ relationship types)
- officer_of, director_of, shareholder_of, family_of, etc.

Usage:
    from linklater.extraction import extract_entities, extract_schemas

    # LLM-based entity extraction
    entities = await extract_entities(
        html="<html>...",
        url="https://example.com",
        backend="auto"  # or "gemini", "gpt", "gliner", "regex"
    )

    # With relationship extraction (Layer 4)
    entities = await extract_entities(
        html="<html>...",
        url="https://example.com",
        extract_relationships=True  # Uses Haiku 4.5
    )
    # Returns: {"persons": [...], "companies": [...], "edges": [...]}

    # Schema.org extraction (fast, no API)
    schemas = extract_schemas(html, url="https://example.com")
    # Returns: {"organizations": [...], "persons": [...], "has_schema": True}
"""

from typing import Dict, List, Optional, Any

# Safe imports with fallbacks
try:
    from .entity_extractor import extract_entities, EntityExtractor
except ImportError:
    extract_entities = EntityExtractor = None

try:
    from .models import Entity, Edge, ExtractionResult, VALID_EDGES, VALID_RELATIONS
except ImportError:
    Entity = Edge = ExtractionResult = None
    VALID_EDGES = VALID_RELATIONS = None

try:
    from .schema_extractor import (
        extract_schemas,
        extract_schemas_from_pages,
        has_schema_markup,
        SchemaEntity,
        SchemaExtractionResult,
    )
except ImportError:
    extract_schemas = extract_schemas_from_pages = has_schema_markup = None
    SchemaEntity = SchemaExtractionResult = None

# Haiku backend for full entity + relationship extraction
try:
    from .backends.haiku import (
        HaikuBackend,
        HaikuRelationshipBackend,  # Backwards compat alias
        extract_all as haiku_extract_all,
        extract_relationships,
    )
except ImportError:
    HaikuBackend = HaikuRelationshipBackend = None
    haiku_extract_all = extract_relationships = None

# Ontology for relationship types
try:
    from .ontology import (
        get_ontology,
        get_valid_relations,
        get_valid_edges,
        generate_prompt_section,
    )
except ImportError:
    get_ontology = get_valid_relations = get_valid_edges = generate_prompt_section = None

__all__ = [
    # Entity extraction (LLM-based)
    "extract_entities",
    "EntityExtractor",
    "Entity",
    "ExtractionResult",
    # Haiku backend (primary for person/company/relationships)
    "HaikuBackend",
    "HaikuRelationshipBackend",  # Backwards compat
    "haiku_extract_all",
    "extract_relationships",
    # Edge types
    "Edge",
    "VALID_EDGES",
    "VALID_RELATIONS",
    # Ontology
    "get_ontology",
    "get_valid_relations",
    "get_valid_edges",
    "generate_prompt_section",
    # Schema.org extraction
    "extract_schemas",
    "extract_schemas_from_pages",
    "has_schema_markup",
    "SchemaEntity",
    "SchemaExtractionResult",
]
