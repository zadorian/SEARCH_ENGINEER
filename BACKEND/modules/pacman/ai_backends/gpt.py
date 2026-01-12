"""
PACMAN GPT Backend
OpenAI-powered entity extraction
Best for: High accuracy, structured extraction
"""

import os
import json
from typing import Dict, List, Optional
from .base import ExtractionBackend, ExtractedEntity, EntityType, BackendRegistry
from ..config.settings import MAX_CONTENT_SCAN

# Try to import OpenAI
_OPENAI_AVAILABLE = False
_client = None

try:
    import openai
    _OPENAI_AVAILABLE = True
except ImportError:
    pass


EXTRACTION_PROMPT = '''Extract all entities from this text. Return JSON array with objects containing:
- value: the extracted entity
- type: one of PERSON, COMPANY, EMAIL, PHONE, ADDRESS, DATE, MONEY, URL, IDENTIFIER
- confidence: 0.0-1.0

TEXT:
{content}

Return ONLY valid JSON array.'''


class GPTBackend(ExtractionBackend):
    """
    GPT extraction backend.
    Uses gpt-4.1-nano for fast, cheap extraction.
    Cost: ~/bin/zsh.0001/1K tokens
    """
    
    name = 'gpt'
    requires_api = True
    cost_per_call = 0.0002
    
    def __init__(self):
        self._client = None
        self.model = 'gpt-4.1-nano'
    
    def _get_client(self):
        """Get or create OpenAI client."""
        global _client
        if _client is None and _OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                _client = openai.OpenAI(api_key=api_key)
        self._client = _client
        return self._client
    
    async def extract(
        self, 
        content: str, 
        entity_types: Optional[List[EntityType]] = None
    ) -> List[ExtractedEntity]:
        """Extract entities using GPT."""
        if not content or not self.is_available():
            return []
        
        client = self._get_client()
        if client is None:
            return []
        
        text = content[:MAX_CONTENT_SCAN]
        results = []
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': EXTRACTION_PROMPT.format(content=text[:10000])
                }],
                max_tokens=4096,
                temperature=0.1
            )
            
            response_text = response.choices[0].message.content
            
            # Parse JSON
            try:
                if response_text.startswith('['):
                    entities = json.loads(response_text)
                else:
                    # Try to extract JSON from text
                    import re
                    match = re.search(r'\[[\s\S]*\]', response_text)
                    if match:
                        entities = json.loads(match.group())
                    else:
                        entities = []
                
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
                        source='gpt',
                        metadata={'model': self.model}
                    ))
            except json.JSONDecodeError:
                pass
        except Exception as e:
            print(f'GPT extraction error: {e}')
        
        return results
    
    def _map_type(self, type_str: str) -> Optional[EntityType]:
        """Map string type to EntityType enum."""
        type_map = {
            'PERSON': EntityType.PERSON,
            'COMPANY': EntityType.COMPANY,
            'ORGANIZATION': EntityType.COMPANY,
            'EMAIL': EntityType.EMAIL,
            'PHONE': EntityType.PHONE,
            'ADDRESS': EntityType.ADDRESS,
            'LOCATION': EntityType.ADDRESS,
            'DATE': EntityType.DATE,
            'MONEY': EntityType.MONEY,
            'URL': EntityType.URL,
            'IDENTIFIER': EntityType.IDENTIFIER,
        }
        return type_map.get(type_str.upper())
    
    def is_available(self) -> bool:
        """Check if OpenAI client is available."""
        if not _OPENAI_AVAILABLE:
            return False
        return os.getenv('OPENAI_API_KEY') is not None


# Auto-register
BackendRegistry.register(GPTBackend())
