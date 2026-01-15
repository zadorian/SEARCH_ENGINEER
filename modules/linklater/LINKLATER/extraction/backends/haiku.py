"""
Claude Haiku 4.5 Backend for Entity + Relationship Extraction

Primary extraction backend for high-value entities (persons, companies) and relationships.
Dynamically loads valid relationship types from input_output/ontology/relationships.json.

Architecture:
- Email/Phone: Handled by regex/GLiNER + GPT-5-nano validation (NOT Haiku)
- Person/Company/Relationships: Haiku extracts FROM SCRATCH with full context

This backend does TWO things:
1. Extract persons and companies from text (full NER)
2. Extract relationships between discovered entities

Usage:
    from linklater.extraction.backends.haiku import HaikuBackend

    backend = HaikuBackend()
    result = await backend.extract_all(
        text="...",
        url="https://..."
    )
    # Returns: {"persons": [...], "companies": [...], "edges": [...]}
"""

import os
import re
import json
import asyncio
from typing import List, Optional, Dict, Any, Set
from pathlib import Path

# Load env
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

from ..models import (
    Entity, Edge, Theme, Phenomenon, Event,
    THEME_CATEGORIES, PHENOMENON_CATEGORIES
)
from ..ontology import get_ontology, generate_prompt_section

# Centralized logging
from ...config import get_logger
logger = get_logger(__name__)


# =============================================================================
# FULL EXTRACTION PROMPT - PERSONS + COMPANIES + RELATIONSHIPS + ET3
# =============================================================================
# Haiku extracts EVERYTHING from scratch in a single pass

FULL_EXTRACTION_SYSTEM = """You are an expert entity, relationship, and event analyst. Extract ALL persons and companies from the text, identify relationships between them, AND extract themes, phenomena, and events.

Return ONLY valid JSON:
{
  "persons": [
    {
      "value": "Full Name",
      "role": "CEO|Director|Manager|etc (if mentioned)",
      "confidence": 0.0-1.0
    }
  ],
  "companies": [
    {
      "value": "Company Full Name",
      "jurisdiction": "Country code if mentioned",
      "confidence": 0.0-1.0
    }
  ],
  "edges": [
    {
      "source_type": "person|company",
      "source_value": "Exact entity name from above",
      "relation": "RELATIONSHIP_TYPE",
      "target_type": "person|company",
      "target_value": "Exact entity name from above",
      "confidence": 0.0-1.0,
      "evidence": "Quote or brief explanation"
    }
  ],
  "themes": [
    {
      "category": "professional|financial|legal_regulatory|reputational|personal|criminal|political|controversy",
      "label": "Human-readable theme description",
      "confidence": 0.0-1.0,
      "evidence": "Quote supporting this theme"
    }
  ],
  "phenomena": [
    {
      "category": "corporate|career|legal|financial|recognition|crisis",
      "phenomenon_type": "ipo|acquisition|merger|hiring|departure|lawsuit_filed|etc",
      "label": "Human-readable description",
      "confidence": 0.0-1.0,
      "evidence": "Quote or brief explanation"
    }
  ],
  "events": [
    {
      "label": "Short event description (e.g., 'Acme Corp IPO on NYSE')",
      "phenomenon_type": "The phenomenon type from above",
      "phenomenon_category": "The category from above",
      "primary_entity": "Main entity name involved",
      "primary_entity_type": "person|company",
      "related_entities": ["Other entity names involved"],
      "date": "YYYY-MM-DD or YYYY-MM or YYYY (if mentioned)",
      "date_precision": "exact|month|year|approximate",
      "location_geographic": "City, Country (if mentioned)",
      "location_institutional": "NYSE, SEC, Delaware Court, etc (if mentioned)",
      "themes": ["theme categories that apply"],
      "confidence": 0.0-1.0,
      "evidence": "Quote describing the event"
    }
  ]
}

{relationship_types_section}

THEME CATEGORIES:
- professional: Career, roles, appointments, industry expertise
- financial: Deals, investments, funding, revenue, assets
- legal_regulatory: Lawsuits, compliance, regulatory actions
- reputational: Awards, recognition, reputation, public image
- personal: Family, philanthropy, personal life, lifestyle
- criminal: Investigations, charges, arrests, convictions
- political: Government roles, lobbying, political connections
- controversy: Scandals, disputes, criticism, adverse coverage

PHENOMENON TYPES:
- corporate: ipo, acquisition, merger, spinoff, bankruptcy, restructuring, funding_round
- career: hiring, departure, promotion, appointment, resignation, retirement, termination
- legal: lawsuit_filed, lawsuit_settled, investigation_opened, charges_filed, conviction, acquittal, regulatory_action
- financial: deal_closed, investment_made, asset_sale, dividend_announced, earnings_reported
- recognition: award_received, ranking_listed, certification_granted, honor_bestowed
- crisis: scandal_broke, controversy_emerged, recall_issued, incident_occurred

Rules:
1. Extract ALL persons mentioned by name (first + last name required)
2. Extract ALL companies/organizations mentioned
3. For relationships, only include those with clear evidence
4. Direction matters: "person officer_of company" NOT "company has_officer person"
5. DO NOT extract emails or phone numbers - those are handled separately
6. Include evidence quotes for all extractions
7. Events are specific occurrences: phenomenon + entity + location/time
8. Multiple themes can apply to the same text
9. Only create events when there's a clear phenomenon with an entity involved"""


# =============================================================================
# RELATIONSHIP-ONLY PROMPT (for when entities are pre-extracted)
# =============================================================================

RELATIONSHIP_SYSTEM_BASE = """You are an expert relationship analyst. Given extracted entities, identify relationships between them.

Return ONLY valid JSON:
{
  "edges": [
    {
      "source_type": "person|company|...",
      "source_value": "Exact entity name",
      "relation": "RELATIONSHIP_TYPE",
      "target_type": "person|company|...",
      "target_value": "Exact entity name",
      "confidence": 0.0-1.0,
      "evidence": "Quote or brief explanation from the text"
    }
  ]
}

{relationship_types_section}

Rules:
1. Only include relationships with clear evidence in the text
2. Use exact entity names from the provided list
3. Direction matters: "person officer_of company" NOT "company has_officer person"
4. Include evidence quote for each relationship"""


def build_full_extraction_prompt(entity_types: Set[str] = None) -> str:
    """
    Build the system prompt for full entity + relationship extraction.

    Args:
        entity_types: Set of entity types to extract relationships for.
                      Defaults to {"person", "company"} for full extraction.
    """
    if entity_types is None:
        entity_types = {"person", "company"}

    # Generate the relationship types section from ontology
    rel_section = generate_prompt_section(
        entity_types,
        exclude_contact_edges=True  # has_email/phone/address handled by regex
    )

    return FULL_EXTRACTION_SYSTEM.format(relationship_types_section=rel_section)


def build_system_prompt(entity_types: Set[str]) -> str:
    """
    Build the system prompt with relationship types filtered for the given entity types.

    Args:
        entity_types: Set of entity types present in the current extraction,
                      e.g., {"person", "company"}

    Returns:
        Complete system prompt with dynamically filtered relationship types
    """
    # Generate the relationship types section from ontology
    rel_section = generate_prompt_section(
        entity_types,
        exclude_contact_edges=True  # has_email/phone/address handled by regex
    )

    return RELATIONSHIP_SYSTEM_BASE.format(relationship_types_section=rel_section)


class HaikuBackend:
    """
    Claude Haiku 4.5 backend for full entity + relationship extraction.

    This is the PRIMARY backend for extracting persons, companies, and their relationships.
    Emails and phones are NOT handled here - use regex/GLiNER + nano validation for those.
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        self.model = "claude-haiku-4-5-20251001"  # Fast/cheap extraction
        self.ontology = get_ontology()  # Load relationship ontology
        self._init_client()

    def _init_client(self):
        """Initialize Anthropic client."""
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set - Haiku extraction disabled")
            return

        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info(f"Haiku backend ready with {len(self.ontology.get_all_relations())} relationship types from ontology")
        except ImportError:
            logger.warning("anthropic package not installed")
        except Exception as e:
            logger.error(f"Anthropic init failed: {e}")

    def _get_entity_types(self, entities: List[Entity]) -> Set[str]:
        """Extract unique entity types from entity list."""
        return {e.type.lower() for e in entities if e.type}

    def _build_prompt(self, text: str, entities: List[Entity]) -> str:
        """Build relationship extraction prompt."""
        # Format entity list
        entity_list = "\n".join([
            f"- {e.type}: \"{e.value}\""
            for e in entities
        ])

        # Truncate text to avoid token limits
        truncated = text[:10000] if len(text) > 10000 else text

        return f"""Entities found:
{entity_list}

Source text:
{truncated}

Identify relationships between these entities."""

    async def extract_relationships(
        self,
        text: str,
        entities: List[Entity],
        url: str = ""
    ) -> List[Edge]:
        """
        Extract relationships between entities from text.

        The system prompt is dynamically generated based on the entity types
        present, filtering relationship types to only those valid for the
        given entity type combinations.

        Args:
            text: Source text (plain text, not HTML)
            entities: List of Entity objects to find relationships between
            url: Source URL for provenance

        Returns:
            List of Edge objects representing relationships
        """
        if not self.client:
            return []

        # Need at least 2 entities to have relationships
        if len(entities) < 2:
            return []

        # Get entity types and build dynamic system prompt
        entity_types = self._get_entity_types(entities)
        system_prompt = build_system_prompt(entity_types)

        # Get valid relations for these entity types (for validation)
        valid_edges = self.ontology.get_relationships_for_entity_types(
            entity_types,
            exclude_contact_edges=True
        )
        valid_relations = {e["relation"].lower() for e in valid_edges}

        logger.debug(f"Entity types: {entity_types}, valid relations: {len(valid_relations)}")

        prompt = self._build_prompt(text, entities)

        try:
            # Run synchronously in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
            )

            content = response.content[0].text

            # Handle markdown-wrapped JSON
            if "```" in content:
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if json_match:
                    content = json_match.group(1).strip()
                elif content.startswith("```"):
                    lines = content.split("\n", 1)
                    if len(lines) > 1:
                        content = lines[1].strip()

            # Find JSON start if not at beginning
            if content and not content.strip().startswith("{"):
                json_start = content.find("{")
                if json_start >= 0:
                    content = content[json_start:]

            if not content:
                return []

            parsed = json.loads(content)
            edges_data = parsed.get("edges", [])

            # Build entity value set for validation (lowercase for comparison)
            entity_values = {e.value.lower() for e in entities}

            # Parse and validate edges
            edges = []
            for edge_data in edges_data:
                source_val = edge_data.get("source_value", "").strip()
                target_val = edge_data.get("target_value", "").strip()
                relation = edge_data.get("relation", "").lower()
                source_type = edge_data.get("source_type", "").lower()
                target_type = edge_data.get("target_type", "").lower()

                # Validate relation is valid for these entity types
                if relation not in valid_relations:
                    logger.debug(f"Invalid relation '{relation}' for entity types {entity_types} - skipping")
                    continue

                # Validate the specific edge combination is valid
                if not self.ontology.is_valid_edge(source_type, relation, target_type):
                    logger.debug(f"Invalid edge {source_type}->{relation}->{target_type} - skipping")
                    continue

                # Validate entities exist in our entity list
                if source_val.lower() not in entity_values:
                    logger.debug(f"Source entity '{source_val}' not found - skipping")
                    continue
                if target_val.lower() not in entity_values:
                    logger.debug(f"Target entity '{target_val}' not found - skipping")
                    continue

                edge = Edge(
                    source_type=source_type,
                    source_value=source_val,
                    relation=relation,
                    target_type=target_type,
                    target_value=target_val,
                    confidence=edge_data.get("confidence", 0.8),
                    evidence=edge_data.get("evidence", ""),
                    source_url=url,
                )
                edges.append(edge)

            logger.info(f"Extracted {len(edges)} valid relationships from {url or 'text'}")
            return edges

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error in relationship extraction: {e}")
            return []
        except Exception as e:
            logger.warning(f"Relationship extraction error: {e}")
            return []

    async def extract_all(
        self,
        text: str,
        url: str = ""
    ) -> Dict[str, Any]:
        """
        Extract persons, companies, relationships, AND ET3 (themes/phenomena/events) in one pass.

        This is the PRIMARY extraction method for high-value entities and events.
        Does NOT extract emails/phones - use regex/GLiNER for those.

        Args:
            text: Source text (plain text, not HTML)
            url: Source URL for provenance

        Returns:
            Dict with persons, companies, edges, themes, phenomena, events lists
        """
        empty_result = {
            "persons": [], "companies": [], "edges": [],
            "themes": [], "phenomena": [], "events": [],
            "backend": "haiku-4.5"
        }

        if not self.client:
            return empty_result

        if not text or len(text.strip()) < 50:
            return empty_result

        # Build system prompt with full relationship ontology for person/company
        system_prompt = build_full_extraction_prompt({"person", "company"})

        # Truncate text to avoid token limits
        truncated = text[:15000] if len(text) > 15000 else text

        prompt = f"""Extract all persons, companies, relationships, themes, phenomena, and events from this text.

Source text:
{truncated}

Remember:
- Extract ALL persons with first AND last names
- Extract ALL companies/organizations
- Identify relationships between them using the allowed types
- Identify themes (what the text is ABOUT)
- Identify phenomena (what TYPE of events occurred)
- Construct events (phenomenon + entity + location/time)
- DO NOT extract emails or phone numbers"""

        try:
            # Run synchronously in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=self.model,
                    max_tokens=12000,  # Increased for ET3
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
            )

            content = response.content[0].text

            # Handle markdown-wrapped JSON
            if "```" in content:
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if json_match:
                    content = json_match.group(1).strip()
                elif content.startswith("```"):
                    lines = content.split("\n", 1)
                    if len(lines) > 1:
                        content = lines[1].strip()

            # Find JSON start if not at beginning
            if content and not content.strip().startswith("{"):
                json_start = content.find("{")
                if json_start >= 0:
                    content = content[json_start:]

            if not content:
                return empty_result

            parsed = json.loads(content)

            # Parse persons
            persons = []
            for p in parsed.get("persons", []):
                value = p.get("value", "").strip()
                if value and " " in value:  # Must have first + last name
                    persons.append(Entity(
                        value=value,
                        type="person",
                        archive_urls=[url] if url else [],
                        confidence=p.get("confidence", 0.85),
                    ))

            # Parse companies
            companies = []
            for c in parsed.get("companies", []):
                value = c.get("value", "").strip()
                if value and len(value) > 2:
                    companies.append(Entity(
                        value=value,
                        type="company",
                        archive_urls=[url] if url else [],
                        confidence=c.get("confidence", 0.85),
                    ))

            # Build entity value set for edge validation
            entity_values = {e.value.lower() for e in persons + companies}

            # Get valid relations for person/company
            valid_edges = self.ontology.get_relationships_for_entity_types(
                {"person", "company"},
                exclude_contact_edges=True
            )
            valid_relations = {e["relation"].lower() for e in valid_edges}

            # Parse and validate edges
            edges = []
            for edge_data in parsed.get("edges", []):
                source_val = edge_data.get("source_value", "").strip()
                target_val = edge_data.get("target_value", "").strip()
                relation = edge_data.get("relation", "").lower()
                source_type = edge_data.get("source_type", "").lower()
                target_type = edge_data.get("target_type", "").lower()

                # Validate relation
                if relation not in valid_relations:
                    logger.debug(f"Invalid relation '{relation}' - skipping")
                    continue

                # Validate edge combination
                if not self.ontology.is_valid_edge(source_type, relation, target_type):
                    logger.debug(f"Invalid edge {source_type}->{relation}->{target_type} - skipping")
                    continue

                # Validate entities exist
                if source_val.lower() not in entity_values:
                    logger.debug(f"Source entity '{source_val}' not found - skipping")
                    continue
                if target_val.lower() not in entity_values:
                    logger.debug(f"Target entity '{target_val}' not found - skipping")
                    continue

                edge = Edge(
                    source_type=source_type,
                    source_value=source_val,
                    relation=relation,
                    target_type=target_type,
                    target_value=target_val,
                    confidence=edge_data.get("confidence", 0.8),
                    evidence=edge_data.get("evidence", ""),
                    source_url=url,
                )
                edges.append(edge)

            # =========================================================
            # ET3: Parse Themes, Phenomena, Events
            # =========================================================

            # Parse themes
            themes = []
            valid_theme_categories = set(THEME_CATEGORIES.keys())
            for t in parsed.get("themes", []):
                category = t.get("category", "").lower()
                if category in valid_theme_categories:
                    themes.append(Theme(
                        category=category,
                        label=t.get("label", category.replace("_", " ").title()),
                        confidence=t.get("confidence", 0.8),
                        evidence=t.get("evidence", ""),
                        source_url=url,
                    ))

            # Parse phenomena
            phenomena = []
            valid_phenomenon_types = set()
            for cat, types in PHENOMENON_CATEGORIES.items():
                valid_phenomenon_types.update(types)

            for p in parsed.get("phenomena", []):
                ptype = p.get("phenomenon_type", "").lower()
                category = p.get("category", "").lower()
                if ptype in valid_phenomenon_types:
                    phenomena.append(Phenomenon(
                        category=category,
                        phenomenon_type=ptype,
                        label=p.get("label", ptype.replace("_", " ").title()),
                        confidence=p.get("confidence", 0.8),
                        evidence=p.get("evidence", ""),
                        source_url=url,
                    ))

            # Parse events
            events = []
            import hashlib
            for idx, e in enumerate(parsed.get("events", [])):
                label = e.get("label", "").strip()
                primary_entity = e.get("primary_entity", "").strip()
                ptype = e.get("phenomenon_type", "").lower()

                if label and primary_entity:
                    # Generate event ID from components
                    event_hash = hashlib.md5(
                        f"{label}:{primary_entity}:{e.get('date', '')}".encode()
                    ).hexdigest()[:12]
                    event_id = f"evt_{event_hash}"

                    events.append(Event(
                        event_id=event_id,
                        label=label,
                        phenomenon_type=ptype,
                        phenomenon_category=e.get("phenomenon_category", "").lower(),
                        primary_entity=primary_entity,
                        primary_entity_type=e.get("primary_entity_type", "company").lower(),
                        related_entities=e.get("related_entities", []),
                        date=e.get("date"),
                        date_precision=e.get("date_precision", "unknown"),
                        location_geographic=e.get("location_geographic", ""),
                        location_institutional=e.get("location_institutional", ""),
                        confidence=e.get("confidence", 0.8),
                        evidence=e.get("evidence", ""),
                        source_urls=[url] if url else [],
                        themes=e.get("themes", []),
                    ))

            logger.info(
                f"Full extraction: {len(persons)} persons, {len(companies)} companies, "
                f"{len(edges)} edges, {len(themes)} themes, {len(phenomena)} phenomena, "
                f"{len(events)} events from {url or 'text'}"
            )

            return {
                "persons": persons,
                "companies": companies,
                "edges": edges,
                "themes": themes,
                "phenomena": phenomena,
                "events": events,
                "backend": "haiku-4.5"
            }

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error in full extraction: {e}")
            return empty_result
        except Exception as e:
            logger.warning(f"Full extraction error: {e}")
            return empty_result

    async def extract_relationships_batch(
        self,
        pages: List[Dict[str, Any]]  # [{"text": "...", "entities": [...], "url": "..."}]
    ) -> List[List[Edge]]:
        """Extract relationships from multiple pages in parallel."""
        tasks = [
            self.extract_relationships(
                page["text"],
                page["entities"],
                page.get("url", "")
            )
            for page in pages
        ]
        return await asyncio.gather(*tasks)

    async def extract_all_batch(
        self,
        pages: List[Dict[str, str]]  # [{"text": "...", "url": "..."}]
    ) -> List[Dict[str, Any]]:
        """Extract entities and relationships from multiple pages in parallel."""
        tasks = [
            self.extract_all(page["text"], page.get("url", ""))
            for page in pages
        ]
        return await asyncio.gather(*tasks)


# Backwards compatibility alias
HaikuRelationshipBackend = HaikuBackend


# Convenience functions
async def extract_all(text: str, url: str = "") -> Dict[str, Any]:
    """
    Extract persons, companies, and relationships using Claude Haiku.

    This is the PRIMARY extraction function for high-value entities.
    """
    backend = HaikuBackend()
    return await backend.extract_all(text, url)


async def extract_relationships(
    text: str,
    entities: List[Entity],
    url: str = ""
) -> List[Edge]:
    """
    Extract relationships between pre-extracted entities using Claude Haiku.

    Use extract_all() instead for full entity + relationship extraction.
    """
    backend = HaikuBackend()
    return await backend.extract_relationships(text, entities, url)
