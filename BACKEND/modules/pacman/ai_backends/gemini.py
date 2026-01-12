"""
PACMAN Gemini Backend
Google AI-powered entity extraction
"""

import os
import json
from typing import Dict, List, Optional
from .base import ExtractionBackend, ExtractedEntity, EntityType, BackendRegistry
from ..config.settings import MAX_CONTENT_SCAN

# Try to import Google AI
_GOOGLE_AVAILABLE = False
_model = None

try:
    import google.generativeai as genai
    _GOOGLE_AVAILABLE = True
except ImportError:
    pass


EXTRACTION_PROMPT = '''Extract all entities from this text. Return JSON array with objects containing:
- value: the extracted entity
- type: one of PERSON, COMPANY, EMAIL, PHONE, ADDRESS, DATE, MONEY, URL, IDENTIFIER
- confidence: 0.0-1.0

TEXT:
{content}

Return ONLY valid JSON array.'''


class GeminiBackend(ExtractionBackend):
    """
    Gemini extraction backend.
    Cost: Free tier available, then ~/bin/zsh.0001/1K chars
    """
    
    name = 'gemini'
    requires_api = True
    cost_per_call = 0.0001
    
    def __init__(self):
        self._model = None
        self.model_name = 'models/gemini-3-pro-latest'
    
    def _get_model(self):
        """Get or create Gemini model."""
        global _model
        if _model is None and _GOOGLE_AVAILABLE:
            api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
                _model = genai.GenerativeModel(self.model_name)
        self._model = _model
        return self._model
    
    async def extract(
        self, 
        content: str, 
        entity_types: Optional[List[EntityType]] = None
    ) -> List[ExtractedEntity]:
        """Extract entities using Gemini."""
        if not content or not self.is_available():
            return []
        
        model = self._get_model()
        if model is None:
            return []
        
        text = content[:MAX_CONTENT_SCAN]
        results = []
        
        try:
            response = model.generate_content(
                EXTRACTION_PROMPT.format(content=text[:10000]),
                generation_config={
                    'temperature': 0.1,
                    'max_output_tokens': 4096
                }
            )
            
            response_text = response.text
            
            # Parse JSON
            try:
                if response_text.startswith('['):
                    entities = json.loads(response_text)
                else:
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
                        source='gemini',
                        metadata={'model': self.model_name}
                    ))
            except json.JSONDecodeError:
                pass
        except Exception as e:
            print(f'Gemini extraction error: {e}')
        
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
        """Check if Gemini is available."""
        if not _GOOGLE_AVAILABLE:
            return False
        return os.getenv('GOOGLE_API_KEY') is not None or os.getenv('GEMINI_API_KEY') is not None


# Auto-register
BackendRegistry.register(GeminiBackend())
