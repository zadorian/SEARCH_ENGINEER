"""
PACMAN Fast Extractor - Regex-only extraction (~5ms)
No AI, no model loading. Pure pattern matching.
"""

from typing import Dict, List, Set
from ..patterns import ALL_PATTERNS
from ..config.settings import MAX_CONTENT_SCAN, MAX_IDENTIFIERS


def extract_fast(content: str) -> Dict[str, List[str]]:
    """
    Fast regex-only extraction. No AI, no external dependencies.
    
    Args:
        content: Text content to extract from (HTML stripped)
    
    Returns:
        Dict mapping entity type to list of matches
        e.g. {'LEI': ['5493001...'], 'EMAIL': ['info@company.com']}
    """
    if not content:
        return {}
    
    # Limit scan size for performance
    text = content[:MAX_CONTENT_SCAN]
    entities: Dict[str, List[str]] = {}
    
    for name, pattern in ALL_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            # Handle tuple results from groups
            if matches and isinstance(matches[0], tuple):
                matches = [' '.join(filter(None, m)) for m in matches]
            # Dedupe and limit
            unique = list(set(matches))[:MAX_IDENTIFIERS]
            if unique:
                entities[name] = unique
    
    return entities


def extract_by_type(content: str, types: List[str]) -> Dict[str, List[str]]:
    """Extract only specific entity types."""
    if not content or not types:
        return {}
    
    text = content[:MAX_CONTENT_SCAN]
    entities: Dict[str, List[str]] = {}
    
    for entity_type in types:
        if entity_type in ALL_PATTERNS:
            pattern = ALL_PATTERNS[entity_type]
            matches = pattern.findall(text)
            if matches:
                if matches and isinstance(matches[0], tuple):
                    matches = [' '.join(filter(None, m)) for m in matches]
                unique = list(set(matches))[:MAX_IDENTIFIERS]
                if unique:
                    entities[entity_type] = unique
    
    return entities
