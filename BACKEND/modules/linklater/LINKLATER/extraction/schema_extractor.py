"""
Schema.org Extractor

Extracts JSON-LD structured data from HTML.
Works with any HTML source: CC, Wayback, Drill (Go or Python), Firecrawl.

Usage:
    from linklater.extraction import extract_schemas

    schemas = extract_schemas(html, url="https://example.com")
    # Returns: {
    #     "organizations": [...],
    #     "persons": [...],
    #     "local_businesses": [...],
    #     "products": [...],
    #     "events": [...],
    #     "raw_schemas": [...]  # All parsed JSON-LD blocks
    # }
"""

import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from bs4 import BeautifulSoup

# Centralized logging
from ..config import get_logger
logger = get_logger(__name__)


# Schema.org type mappings to our entity model
SCHEMA_TYPE_MAP = {
    # Organizations
    "Organization": "organization",
    "Corporation": "organization",
    "LocalBusiness": "local_business",
    "Restaurant": "local_business",
    "Store": "local_business",
    "Hotel": "local_business",
    "MedicalBusiness": "local_business",
    "LegalService": "local_business",
    "FinancialService": "local_business",
    "GovernmentOrganization": "organization",
    "NGO": "organization",
    "EducationalOrganization": "organization",
    "SportsOrganization": "organization",
    # People
    "Person": "person",
    # Products
    "Product": "product",
    "SoftwareApplication": "product",
    "WebApplication": "product",
    "MobileApplication": "product",
    # Events
    "Event": "event",
    "BusinessEvent": "event",
    "SocialEvent": "event",
    # Content
    "Article": "article",
    "NewsArticle": "article",
    "BlogPosting": "article",
    "WebPage": "webpage",
    "WebSite": "website",
    # Other valuable types
    "JobPosting": "job",
    "Review": "review",
    "BreadcrumbList": "breadcrumb",
}


@dataclass
class SchemaEntity:
    """Extracted Schema.org entity."""
    schema_type: str  # Original @type from JSON-LD
    entity_type: str  # Normalized type (organization, person, etc.)
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

    # Organization fields
    founders: List[str] = field(default_factory=list)
    employees: List[str] = field(default_factory=list)
    address: Optional[Dict[str, str]] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    same_as: List[str] = field(default_factory=list)  # Social profiles, other URLs
    parent_organization: Optional[str] = None

    # Person fields
    job_title: Optional[str] = None
    works_for: Optional[str] = None

    # Product fields
    brand: Optional[str] = None
    price: Optional[str] = None

    # Provenance
    source_url: str = ""
    confidence: float = 1.0  # Schema.org = high confidence

    # Raw data for anything we didn't parse
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "schema_type": self.schema_type,
            "entity_type": self.entity_type,
            "name": self.name,
            "url": self.url,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }

        # Add non-empty fields
        if self.description:
            result["description"] = self.description[:500]  # Truncate
        if self.founders:
            result["founders"] = self.founders
        if self.employees:
            result["employees"] = self.employees[:20]  # Limit
        if self.address:
            result["address"] = self.address
        if self.telephone:
            result["telephone"] = self.telephone
        if self.email:
            result["email"] = self.email
        if self.same_as:
            result["same_as"] = self.same_as
        if self.parent_organization:
            result["parent_organization"] = self.parent_organization
        if self.job_title:
            result["job_title"] = self.job_title
        if self.works_for:
            result["works_for"] = self.works_for
        if self.brand:
            result["brand"] = self.brand
        if self.price:
            result["price"] = self.price

        return result


@dataclass
class SchemaExtractionResult:
    """Result from schema extraction."""
    organizations: List[SchemaEntity] = field(default_factory=list)
    persons: List[SchemaEntity] = field(default_factory=list)
    local_businesses: List[SchemaEntity] = field(default_factory=list)
    products: List[SchemaEntity] = field(default_factory=list)
    events: List[SchemaEntity] = field(default_factory=list)
    articles: List[SchemaEntity] = field(default_factory=list)
    jobs: List[SchemaEntity] = field(default_factory=list)
    other: List[SchemaEntity] = field(default_factory=list)

    raw_schemas: List[Dict] = field(default_factory=list)  # All parsed JSON-LD
    source_url: str = ""
    has_schema: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "organizations": [e.to_dict() for e in self.organizations],
            "persons": [e.to_dict() for e in self.persons],
            "local_businesses": [e.to_dict() for e in self.local_businesses],
            "products": [e.to_dict() for e in self.products],
            "events": [e.to_dict() for e in self.events],
            "articles": [e.to_dict() for e in self.articles],
            "jobs": [e.to_dict() for e in self.jobs],
            "other": [e.to_dict() for e in self.other],
            "raw_schemas": self.raw_schemas,
            "source_url": self.source_url,
            "has_schema": self.has_schema,
            "total_entities": self.total_entities,
        }

    @property
    def total_entities(self) -> int:
        """Total count of all extracted entities."""
        return (
            len(self.organizations) +
            len(self.persons) +
            len(self.local_businesses) +
            len(self.products) +
            len(self.events) +
            len(self.articles) +
            len(self.jobs) +
            len(self.other)
        )


def _extract_json_ld(html: str) -> List[Dict]:
    """Extract all JSON-LD blocks from HTML."""
    schemas = []

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find all JSON-LD script tags
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                text = script.string
                if not text:
                    continue

                # Clean up common issues
                text = text.strip()

                # Parse JSON
                data = json.loads(text)

                # Handle @graph arrays
                if isinstance(data, dict) and "@graph" in data:
                    for item in data["@graph"]:
                        if isinstance(item, dict):
                            schemas.append(item)
                elif isinstance(data, list):
                    schemas.extend([d for d in data if isinstance(d, dict)])
                elif isinstance(data, dict):
                    schemas.append(data)

            except json.JSONDecodeError as e:
                logger.debug(f"JSON-LD parse error: {e}")
                continue

    except Exception as e:
        logger.warning(f"HTML parsing error: {e}")

    return schemas


def _get_string(data: Dict, *keys: str) -> Optional[str]:
    """Safely get a string value from nested dict."""
    for key in keys:
        val = data.get(key)
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            # Handle nested objects like {"@type": "Text", "name": "..."}
            return val.get("name") or val.get("@value")
    return None


def _get_list(data: Dict, key: str) -> List[str]:
    """Safely get a list of strings from dict."""
    val = data.get(key, [])
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        result = []
        for item in val:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("@value")
                if name:
                    result.append(name)
        return result
    return []


def _parse_address(data: Dict) -> Optional[Dict[str, str]]:
    """Parse PostalAddress schema."""
    addr = data.get("address")
    if not addr:
        return None

    if isinstance(addr, str):
        return {"formatted": addr}

    if isinstance(addr, dict):
        return {
            "street": addr.get("streetAddress"),
            "city": addr.get("addressLocality"),
            "region": addr.get("addressRegion"),
            "postal_code": addr.get("postalCode"),
            "country": addr.get("addressCountry"),
        }

    return None


def _parse_schema_entity(schema: Dict, source_url: str) -> Optional[SchemaEntity]:
    """Parse a single JSON-LD schema into SchemaEntity."""
    schema_type = schema.get("@type")

    # Handle array types (use first)
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else None

    if not schema_type:
        return None

    # Get normalized entity type
    entity_type = SCHEMA_TYPE_MAP.get(schema_type, "other")

    entity = SchemaEntity(
        schema_type=schema_type,
        entity_type=entity_type,
        name=_get_string(schema, "name", "legalName"),
        url=_get_string(schema, "url", "mainEntityOfPage"),
        description=_get_string(schema, "description"),
        source_url=source_url,
        raw_data=schema,
    )

    # Organization-specific fields
    if entity_type in ("organization", "local_business"):
        entity.telephone = _get_string(schema, "telephone")
        entity.email = _get_string(schema, "email")
        entity.same_as = _get_list(schema, "sameAs")
        entity.address = _parse_address(schema)

        # Founders
        founders = schema.get("founder", [])
        if isinstance(founders, dict):
            founders = [founders]
        entity.founders = [
            f.get("name") for f in founders
            if isinstance(f, dict) and f.get("name")
        ]

        # Parent org
        parent = schema.get("parentOrganization")
        if isinstance(parent, dict):
            entity.parent_organization = parent.get("name")
        elif isinstance(parent, str):
            entity.parent_organization = parent

    # Person-specific fields
    elif entity_type == "person":
        entity.job_title = _get_string(schema, "jobTitle")
        entity.email = _get_string(schema, "email")
        entity.telephone = _get_string(schema, "telephone")
        entity.same_as = _get_list(schema, "sameAs")

        works_for = schema.get("worksFor")
        if isinstance(works_for, dict):
            entity.works_for = works_for.get("name")
        elif isinstance(works_for, str):
            entity.works_for = works_for

    # Product-specific fields
    elif entity_type == "product":
        brand = schema.get("brand")
        if isinstance(brand, dict):
            entity.brand = brand.get("name")
        elif isinstance(brand, str):
            entity.brand = brand

        offers = schema.get("offers")
        if isinstance(offers, dict):
            entity.price = offers.get("price")
        elif isinstance(offers, list) and offers:
            entity.price = offers[0].get("price") if isinstance(offers[0], dict) else None

    return entity


def extract_schemas(html: str, url: str = "") -> SchemaExtractionResult:
    """
    Extract Schema.org JSON-LD from HTML.

    Args:
        html: HTML content (from any source: CC, Wayback, Drill, Firecrawl)
        url: Source URL for provenance

    Returns:
        SchemaExtractionResult with categorized entities
    """
    result = SchemaExtractionResult(source_url=url)

    # Extract all JSON-LD blocks
    schemas = _extract_json_ld(html)
    result.raw_schemas = schemas
    result.has_schema = len(schemas) > 0

    if not schemas:
        return result

    # Parse each schema
    for schema in schemas:
        entity = _parse_schema_entity(schema, url)
        if not entity:
            continue

        # Categorize by entity type
        if entity.entity_type == "organization":
            result.organizations.append(entity)
        elif entity.entity_type == "person":
            result.persons.append(entity)
        elif entity.entity_type == "local_business":
            result.local_businesses.append(entity)
        elif entity.entity_type == "product":
            result.products.append(entity)
        elif entity.entity_type == "event":
            result.events.append(entity)
        elif entity.entity_type == "article":
            result.articles.append(entity)
        elif entity.entity_type == "job":
            result.jobs.append(entity)
        else:
            result.other.append(entity)

    logger.debug(f"Extracted {result.total_entities} schema entities from {url}")

    return result


def extract_schemas_from_pages(
    pages: List[Dict[str, str]]  # [{"html": "...", "url": "..."}]
) -> List[SchemaExtractionResult]:
    """
    Extract schemas from multiple pages.

    Args:
        pages: List of {"html": str, "url": str} dicts

    Returns:
        List of SchemaExtractionResult
    """
    return [
        extract_schemas(page["html"], page.get("url", ""))
        for page in pages
    ]


# Convenience function for checking if page has schema
def has_schema_markup(html: str) -> bool:
    """Quick check if HTML contains JSON-LD schema markup."""
    return 'application/ld+json' in html


__all__ = [
    "extract_schemas",
    "extract_schemas_from_pages",
    "has_schema_markup",
    "SchemaEntity",
    "SchemaExtractionResult",
]
