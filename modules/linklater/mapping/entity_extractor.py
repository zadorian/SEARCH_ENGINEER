"""
LinkLater Simplified Entity Extractor
======================================
Fast, cheap entity extraction using GPT-5-nano only (no edges).

This is a standalone component that extracts entities from cached content
retrieved by LinkLater. It connects to the broader drill-search entity
extraction pipeline which indexes results to cymonides-1 with smart edges.

Architecture:
- LinkLater: Retrieves and caches content
- This module: Fast entity extraction (persons, companies, emails, phones, addresses)
- Cache entity pipeline: Indexes to cymonides-1 with smart edges

Differences from historic_entity_extractor.py:
- Uses only GPT-5-nano (not GPT-4.1-nano)
- No relationship extraction (no edges)
- Faster and cheaper
- Designed for cached content processing
"""

import os
import logging
import re
from typing import Dict, List, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# GPT-5-nano configuration
GPT_MODEL = "gpt-5-nano"
MAX_CONTENT_LENGTH = 20000  # GPT-5-nano context limit


class SimplifiedEntityExtractor:
    """Fast entity extraction using GPT-5-nano only"""

    def __init__(self):
        """Initialize OpenAI client for GPT-5-nano"""
        self.client = None
        api_key = os.getenv('OPENAI_API_KEY')

        if api_key:
            try:
                self.client = OpenAI(api_key=api_key)
                logger.info("SimplifiedEntityExtractor initialized with GPT-5-nano")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None
        else:
            logger.warning("OPENAI_API_KEY not found, entity extraction unavailable")

    def _extract_with_regex(self, text: str) -> List[Dict[str, Any]]:
        """
        Fast regex-based entity extraction (fallback if GPT unavailable)

        Returns entities with type, value, confidence
        """
        entities = []

        # Email extraction
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            entities.append({
                'type': 'email',
                'value': match.group().lower(),
                'confidence': 0.9,
                'method': 'regex'
            })

        # Phone extraction (international format)
        phone_pattern = r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,5}[-\s\.]?[0-9]{1,5}'
        for match in re.finditer(phone_pattern, text):
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

    def _extract_with_gpt5nano(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities using GPT-5-nano

        Returns entities with type, value, confidence
        """
        if not self.client:
            logger.warning("OpenAI client not initialized, falling back to regex")
            return self._extract_with_regex(text)

        # Truncate content if too long
        truncated_text = text[:MAX_CONTENT_LENGTH] if len(text) > MAX_CONTENT_LENGTH else text

        # System prompt for entity extraction
        system_prompt = """You are an entity extraction engine. Extract people, organizations, emails, phones, and addresses from text.

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

        try:
            # Use Responses API with minimal reasoning
            response = self.client.responses.create(
                model=GPT_MODEL,
                input=truncated_text,
                instructions=system_prompt,
                reasoning={"effort": "minimal"},
                text={"verbosity": "low"}
            )

            # Parse response
            output_text = self._response_to_text(response)
            entities = self._parse_entities_json(output_text)

            # Tag with method
            for entity in entities:
                entity['method'] = 'gpt5nano'

            logger.debug(f"Extracted {len(entities)} entities with GPT-5-nano")
            return entities

        except Exception as e:
            logger.error(f"GPT-5-nano extraction failed: {e}, falling back to regex")
            return self._extract_with_regex(text)

    def _response_to_text(self, response) -> str:
        """Convert OpenAI response to text"""
        if hasattr(response, 'output_text') and response.output_text:
            return response.output_text

        # Try to extract from output array
        if hasattr(response, 'output') and response.output:
            parts = []
            for item in response.output:
                if hasattr(item, 'content'):
                    content = item.content
                    if isinstance(content, list):
                        for fragment in content:
                            if isinstance(fragment, dict) and 'text' in fragment:
                                parts.append(fragment['text'])
            if parts:
                return ''.join(parts)

        return str(response)

    def _parse_entities_json(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSON array of entities from GPT response"""
        import json

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

    def extract_entities(self, content: str, source_url: Optional[str] = None,
                        method: str = "gpt5nano") -> Dict[str, Any]:
        """
        Extract entities from content

        Args:
            content: Text content to extract from
            source_url: Optional source URL for metadata
            method: Extraction method ('gpt5nano' or 'regex')

        Returns:
            {
                'entities': [{'type': str, 'value': str, 'confidence': float, 'method': str}],
                'total': int,
                'method': str,
                'source_url': str
            }
        """
        if not content or not content.strip():
            return {
                'entities': [],
                'total': 0,
                'method': method,
                'source_url': source_url
            }

        # Extract entities based on method
        if method == "regex":
            entities = self._extract_with_regex(content)
        else:  # default to gpt5nano
            entities = self._extract_with_gpt5nano(content)

        return {
            'entities': entities,
            'total': len(entities),
            'method': method,
            'source_url': source_url
        }

    def extract_from_cached_content(self, cached_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract entities from LinkLater cached content

        Args:
            cached_content: Cached content dict with 'content', 'url', etc.

        Returns:
            Same format as extract_entities()
        """
        # Extract text from various fields
        text_parts = []

        # Main content
        if 'content' in cached_content:
            text_parts.append(cached_content['content'])

        # Markdown
        if 'markdown' in cached_content:
            text_parts.append(cached_content['markdown'])

        # Metadata fields
        metadata = cached_content.get('metadata', {})
        if metadata.get('title'):
            text_parts.append(metadata['title'])
        if metadata.get('description'):
            text_parts.append(metadata['description'])

        # Combine text
        combined_text = '\n\n'.join(text_parts)
        source_url = cached_content.get('url')

        return self.extract_entities(combined_text, source_url)


# Singleton instance
_extractor = None

def get_extractor() -> SimplifiedEntityExtractor:
    """Get or create singleton extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = SimplifiedEntityExtractor()
    return _extractor


# Convenience functions
def extract_entities(content: str, source_url: Optional[str] = None,
                    method: str = "gpt5nano") -> Dict[str, Any]:
    """Extract entities from text content"""
    extractor = get_extractor()
    return extractor.extract_entities(content, source_url, method)


def extract_from_cached_content(cached_content: Dict[str, Any]) -> Dict[str, Any]:
    """Extract entities from LinkLater cached content"""
    extractor = get_extractor()
    return extractor.extract_from_cached_content(cached_content)
