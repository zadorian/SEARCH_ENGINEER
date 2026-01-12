"""
PACMAN GLiNER Backend
Local NER model for entity extraction
No API costs, runs on CPU/GPU
"""

from typing import Dict, List, Optional
from .base import ExtractionBackend, ExtractedEntity, EntityType, BackendRegistry
from ..config.settings import MAX_CONTENT_SCAN

# Try to import GLiNER
_GLINER_AVAILABLE = False
_model = None

try:
    from gliner import GLiNER
    _GLINER_AVAILABLE = True
except ImportError:
    pass


# GLiNER label to EntityType mapping
LABEL_MAP = {
    'person': EntityType.PERSON,
    'organization': EntityType.COMPANY,
    'company': EntityType.COMPANY,
    'location': EntityType.ADDRESS,
    'address': EntityType.ADDRESS,
    'date': EntityType.DATE,
    'money': EntityType.MONEY,
    'email': EntityType.EMAIL,
    'phone': EntityType.PHONE,
    'url': EntityType.URL,
}


class GLiNERBackend(ExtractionBackend):
    """
    Local GLiNER NER model backend.
    Fast on GPU, moderate on CPU (~100ms-1s).
    Free, no API costs.
    """
    
    name = 'gliner'
    requires_api = False
    cost_per_call = 0.0
    
    # Labels to extract
    DEFAULT_LABELS = [
        'person', 'organization', 'location', 'date', 
        'money', 'email', 'phone', 'url'
    ]
    
    def __init__(self, model_name: str = 'urchade/gliner_base'):
        self.model_name = model_name
        self._model = None
    
    def _load_model(self):
        """Lazy load model on first use."""
        global _model
        if _model is None and _GLINER_AVAILABLE:
            try:
                _model = GLiNER.from_pretrained(self.model_name)
            except Exception as e:
                print(f'Failed to load GLiNER model: {e}')
                return None
        self._model = _model
        return self._model
    
    async def extract(
        self, 
        content: str, 
        entity_types: Optional[List[EntityType]] = None
    ) -> List[ExtractedEntity]:
        """Extract entities using GLiNER."""
        if not content or not self.is_available():
            return []
        
        model = self._load_model()
        if model is None:
            return []
        
        text = content[:MAX_CONTENT_SCAN]
        results = []
        
        # Determine labels to use
        if entity_types:
            labels = []
            for et in entity_types:
                for label, mapped_type in LABEL_MAP.items():
                    if mapped_type == et:
                        labels.append(label)
        else:
            labels = self.DEFAULT_LABELS
        
        if not labels:
            return []
        
        try:
            # GLiNER extraction
            entities = model.predict_entities(text, labels, threshold=0.5)
            
            for entity in entities:
                entity_type = LABEL_MAP.get(entity['label'].lower())
                if entity_type is None:
                    continue
                
                results.append(ExtractedEntity(
                    value=entity['text'],
                    entity_type=entity_type,
                    confidence=entity['score'],
                    source='gliner',
                    context=self._get_context(text, entity['start'], entity['end']),
                    metadata={
                        'label': entity['label'],
                        'start': entity['start'],
                        'end': entity['end']
                    }
                ))
        except Exception as e:
            print(f'GLiNER extraction error: {e}')
        
        return results
    
    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Get surrounding context for an entity."""
        ctx_start = max(0, start - window)
        ctx_end = min(len(text), end + window)
        return text[ctx_start:ctx_end]
    
    def is_available(self) -> bool:
        """Check if GLiNER is installed and model can load."""
        if not _GLINER_AVAILABLE:
            return False
        try:
            model = self._load_model()
            return model is not None
        except:
            return False


# Auto-register if available
if _GLINER_AVAILABLE:
    BackendRegistry.register(GLiNERBackend())
