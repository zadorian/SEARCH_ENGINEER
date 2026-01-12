"""
GPT Backend - OpenAI GPT-5-nano Entity Extraction

Fast, cheap entity extraction using GPT-5-nano (OpenAI's lightweight model).

Best for:
- Fast extraction when speed matters
- Cloud-based processing
- Good balance of quality vs cost

Note: GPT-5-nano does NOT support temperature/top_p parameters.
Use reasoning_effort and text_verbosity instead.

Usage:
    from linklater.extraction.backends.gpt import GPTBackend

    backend = GPTBackend()
    result = backend.extract(html, url)
    # Returns: {"persons": [...], "companies": [...], "emails": [...], "phones": [...]}
"""

import os
import re
import json
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path

# Load env
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

from ..models import Entity, ExtractionResult

# Centralized logging
from ...config import get_logger
logger = get_logger(__name__)

# GPT-5-nano configuration
GPT_MODEL = "gpt-5-nano"
MAX_CONTENT_LENGTH = 20000  # GPT-5-nano context limit

# Optional OpenAI import
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not installed: pip install openai")


class GPTBackend:
    """
    Entity extraction backend using GPT-5-nano.

    Fast and cheap API-based extraction. Falls back to regex if API unavailable.
    """

    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,5}[-\s\.]?[0-9]{1,5}')

    SYSTEM_PROMPT = """You are an entity extraction engine. Extract people, organizations, emails, phones, and addresses from text.

Return ONLY a JSON array with this exact structure:
[
  {"type": "person", "value": "John Smith", "confidence": 0.95},
  {"type": "company", "value": "Acme Corp", "confidence": 0.9},
  {"type": "email", "value": "john@example.com", "confidence": 1.0},
  {"type": "phone", "value": "+1-555-0123", "confidence": 0.85},
  {"type": "address", "value": "123 Main St", "confidence": 0.8}
]

Entity types: person, company, email, phone, address
Confidence: 0.0-1.0 (how certain you are)

Extract EVERY entity you find. Return an empty array [] if nothing found."""

    def __init__(self, model: str = GPT_MODEL, max_content_length: int = MAX_CONTENT_LENGTH):
        """
        Initialize GPT backend.

        Args:
            model: OpenAI model to use (default: gpt-5-nano)
            max_content_length: Maximum content length to process
        """
        self.model = model
        self.max_content_length = max_content_length
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client."""
        if not OPENAI_AVAILABLE:
            return

        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            try:
                self._client = OpenAI(api_key=api_key)
                logger.info(f"GPT backend initialized with model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self._client = None
        else:
            logger.warning("OPENAI_API_KEY not found, GPT extraction unavailable")

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags, scripts, styles."""
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_with_regex(self, text: str) -> List[Dict[str, Any]]:
        """
        Fast regex-based entity extraction (fallback if GPT unavailable).

        Returns entities with type, value, confidence.
        """
        entities = []

        # Email extraction
        for match in self.EMAIL_PATTERN.finditer(text.lower()):
            email = match.group()
            # Filter false positives
            if any(fp in email for fp in ['example.com', 'test.com', 'localhost', '.png', '.jpg']):
                continue
            entities.append({
                'type': 'email',
                'value': email,
                'confidence': 0.9,
                'method': 'regex'
            })

        # Phone extraction
        for match in self.PHONE_PATTERN.finditer(text):
            phone = match.group()
            # Only keep if at least 10 digits
            if len(re.sub(r'\D', '', phone)) >= 10:
                entities.append({
                    'type': 'phone',
                    'value': phone,
                    'confidence': 0.7,
                    'method': 'regex'
                })

        # Deduplicate by value
        seen = set()
        unique_entities = []
        for entity in entities:
            key = f"{entity['type']}:{entity['value']}"
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        return unique_entities

    def _extract_with_gpt(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities using GPT-5-nano.

        Returns entities with type, value, confidence.
        """
        if not self._client:
            logger.warning("OpenAI client not initialized, falling back to regex")
            return self._extract_with_regex(text)

        # Truncate content if too long
        truncated_text = text[:self.max_content_length] if len(text) > self.max_content_length else text

        try:
            # GPT-5-nano uses chat completions API
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": truncated_text}
                ],
            )

            # Parse response
            content = response.choices[0].message.content
            entities = self._parse_entities_json(content)

            # Tag with method
            for entity in entities:
                entity['method'] = 'gpt5nano'

            logger.debug(f"Extracted {len(entities)} entities with GPT-5-nano")
            return entities

        except Exception as e:
            logger.error(f"GPT-5-nano extraction failed: {e}, falling back to regex")
            return self._extract_with_regex(text)

    def _parse_entities_json(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSON array of entities from GPT response."""
        # Strip markdown code blocks if present
        text = text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

        try:
            entities = json.loads(text)
            if not isinstance(entities, list):
                logger.warning("Expected JSON array, got something else")
                return []

            # Validate entity format
            valid_entities = []
            for entity in entities:
                if not isinstance(entity, dict):
                    continue

                entity_type = entity.get('type', '').strip().lower()
                value = entity.get('value', '').strip()
                confidence = entity.get('confidence', 0.9)

                # Validate type
                if entity_type not in ['person', 'company', 'email', 'phone', 'address']:
                    continue

                # Validate value
                if not value:
                    continue

                # Normalize confidence
                try:
                    confidence = float(confidence)
                    confidence = max(0.0, min(1.0, confidence))
                except Exception as e:
                    confidence = 0.9

                valid_entities.append({
                    'type': entity_type,
                    'value': value,
                    'confidence': confidence
                })

            return valid_entities

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse entity JSON: {e}")
            return []

    async def extract(
        self,
        html: str,
        url: str = "",
        entity_types: List[str] = None,
    ) -> ExtractionResult:
        """
        Extract entities from HTML content (async interface).

        Args:
            html: Raw HTML content
            url: Source URL (for logging)
            entity_types: Types to extract (person, company, email, phone)

        Returns:
            ExtractionResult with persons, companies, emails, phones
        """
        result = ExtractionResult()
        text = self._strip_html(html)

        if not text.strip():
            return result

        # Run GPT extraction in thread pool (it's sync)
        loop = asyncio.get_event_loop()
        entities = await loop.run_in_executor(
            None,
            lambda: self._extract_with_gpt(text)
        )

        # Convert to ExtractionResult format
        for entity in entities:
            entity_type = entity.get('type', '')
            value = entity.get('value', '')
            confidence = entity.get('confidence', 0.9)

            entity_obj = Entity(
                value=value,
                type=entity_type,
                confidence=confidence,
                archive_urls=[url] if url else []
            )

            if entity_type == 'person':
                result.persons.append(entity_obj)
            elif entity_type == 'company':
                result.companies.append(entity_obj)
            elif entity_type == 'email':
                result.emails.append(entity_obj)
            elif entity_type == 'phone':
                result.phones.append(entity_obj)

        logger.info(f"GPT-5-nano extracted: {len(result.persons)} persons, {len(result.companies)} companies from {url}")
        return result


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_backend = None


def get_backend() -> GPTBackend:
    """Get singleton backend instance."""
    global _backend
    if _backend is None:
        _backend = GPTBackend()
    return _backend


def extract(html: str, url: str = "") -> Dict[str, Any]:
    """
    Quick extraction using default GPT backend.

    Args:
        html: HTML content
        url: Source URL

    Returns:
        Dict with persons, companies, emails, phones, addresses
    """
    backend = get_backend()
    return backend.extract(html, url)


# For unified interface compatibility
def extract_entities(html: str, url: str = "", **kwargs) -> Dict[str, Any]:
    """Unified interface for entity extraction."""
    return extract(html, url)
