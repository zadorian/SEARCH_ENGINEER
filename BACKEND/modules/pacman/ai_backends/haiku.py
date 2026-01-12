"""
PACMAN Claude Haiku Backend
AI-powered entity and relationship extraction
"""

import os
import json
from typing import Dict, List, Optional
from .base import ExtractionBackend, ExtractedEntity, EntityType, BackendRegistry
from ..config.settings import MAX_CONTENT_SCAN

_ANTHROPIC_AVAILABLE = False
_client = None

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    pass


EXTRACTION_PROMPT = """Extract all entities from this text. Return JSON array with:
- value: the entity
- type: PERSON, COMPANY, EMAIL, PHONE, ADDRESS, DATE, MONEY, URL, IDENTIFIER
- confidence: 0.0-1.0

TEXT:
{content}

Return ONLY valid JSON array."""


class HaikuBackend(ExtractionBackend):
    name = 'haiku'
    requires_api = True
    cost_per_call = 0.0005
    
    def __init__(self):
        self._client = None
        self.model = 'claude-haiku-4-5-20251001'
    
    def _get_client(self):
        global _client
        if _client is None and _ANTHROPIC_AVAILABLE:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                _client = anthropic.Anthropic(api_key=api_key)
        self._client = _client
        return self._client
    
    async def extract(self, content: str, entity_types: Optional[List[EntityType]] = None) -> List[ExtractedEntity]:
        if not content or not self.is_available():
            return []
        
        client = self._get_client()
        if client is None:
            return []
        
        text = content[:MAX_CONTENT_SCAN]
        results = []
        
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{'role': 'user', 'content': EXTRACTION_PROMPT.format(content=text[:10000])}]
            )
            
            response_text = message.content[0].text
            
            # Clean response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]
            
            entities = json.loads(response_text)
            
            for entity in entities:
                entity_type = self._map_type(entity.get('type', ''))
                if entity_type is None:
                    continue
                if entity_types and entity_type not in entity_types:
                    continue
                
                results.append(ExtractedEntity(
                    value=entity.get('value', ''),
                    entity_type=entity_type,
                    confidence=float(entity.get('confidence', 0.8)),
                    source='haiku',
                    metadata={'raw': entity}
                ))
        except Exception as e:
            print(f'Haiku extraction error: {e}')
        
        return results
    
    def _map_type(self, type_str: str) -> Optional[EntityType]:
        type_map = {
            'PERSON': EntityType.PERSON,
            'COMPANY': EntityType.COMPANY,
            'ORGANIZATION': EntityType.COMPANY,
            'EMAIL': EntityType.EMAIL,
            'PHONE': EntityType.PHONE,
            'ADDRESS': EntityType.ADDRESS,
            'DATE': EntityType.DATE,
            'MONEY': EntityType.MONEY,
            'URL': EntityType.URL,
            'IDENTIFIER': EntityType.IDENTIFIER,
        }
        return type_map.get(type_str.upper())
    
    def is_available(self) -> bool:
        if not _ANTHROPIC_AVAILABLE:
            return False
        return os.getenv('ANTHROPIC_API_KEY') is not None


BackendRegistry.register(HaikuBackend())
