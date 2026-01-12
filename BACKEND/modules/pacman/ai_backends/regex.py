"""
PACMAN Regex Backend
Fast, free, pattern-based extraction
"""

from typing import Dict, List, Optional
from .base import ExtractionBackend, ExtractedEntity, EntityType, BackendRegistry
from ..patterns import ALL_PATTERNS
from ..entity_extractors import extract_persons, extract_companies
from ..config.settings import MAX_CONTENT_SCAN


class RegexBackend(ExtractionBackend):
    """
    Pure regex extraction backend.
    Fast (~5ms), free, no external dependencies.
    """
    
    name = 'regex'
    requires_api = False
    cost_per_call = 0.0
    
    def __init__(self):
        self._pattern_type_map = {
            'EMAIL': EntityType.EMAIL,
            'PHONE_INTL': EntityType.PHONE,
            'PHONE_US': EntityType.PHONE,
            'PHONE_UK': EntityType.PHONE,
            'PHONE_EU': EntityType.PHONE,
            'LEI': EntityType.IDENTIFIER,
            'IBAN': EntityType.IDENTIFIER,
            'SWIFT': EntityType.IDENTIFIER,
            'VAT': EntityType.IDENTIFIER,
            'IMO': EntityType.IDENTIFIER,
            'MMSI': EntityType.IDENTIFIER,
            'ISIN': EntityType.IDENTIFIER,
            'DUNS': EntityType.IDENTIFIER,
            'BTC': EntityType.CRYPTO,
            'BTC_BECH32': EntityType.CRYPTO,
            'ETH': EntityType.CRYPTO,
            'LTC': EntityType.CRYPTO,
            'XRP': EntityType.CRYPTO,
            'XMR': EntityType.CRYPTO,
        }
    
    async def extract(
        self, 
        content: str, 
        entity_types: Optional[List[EntityType]] = None
    ) -> List[ExtractedEntity]:
        """Extract entities using regex patterns."""
        if not content:
            return []
        
        text = content[:MAX_CONTENT_SCAN]
        results = []
        
        # Pattern-based extraction
        for pattern_name, pattern in ALL_PATTERNS.items():
            entity_type = self._pattern_type_map.get(pattern_name)
            if entity_type is None:
                continue
            
            if entity_types and entity_type not in entity_types:
                continue
            
            matches = pattern.findall(text)
            for match in matches:
                value = match if isinstance(match, str) else ' '.join(filter(None, match))
                results.append(ExtractedEntity(
                    value=value.strip(),
                    entity_type=entity_type,
                    confidence=0.9,  # High confidence for regex matches
                    source='regex',
                    metadata={'pattern': pattern_name}
                ))
        
        # Person extraction
        if not entity_types or EntityType.PERSON in entity_types:
            persons = extract_persons(text)
            for p in persons:
                results.append(ExtractedEntity(
                    value=p['name'],
                    entity_type=EntityType.PERSON,
                    confidence=p['confidence'],
                    source='regex',
                    metadata={'detection_source': p['source']}
                ))
        
        # Company extraction
        if not entity_types or EntityType.COMPANY in entity_types:
            companies = extract_companies(text)
            for c in companies:
                results.append(ExtractedEntity(
                    value=c['name'],
                    entity_type=EntityType.COMPANY,
                    confidence=c['confidence'],
                    source='regex',
                    metadata={
                        'suffix': c.get('suffix'),
                        'crn': c.get('crn'),
                        'detection_source': c['source']
                    }
                ))
        
        # Deduplicate
        seen = set()
        unique_results = []
        for r in results:
            key = (r.value.lower(), r.entity_type)
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        return unique_results
    
    def is_available(self) -> bool:
        """Always available - no external dependencies."""
        return True


# Auto-register
BackendRegistry.register(RegexBackend())
