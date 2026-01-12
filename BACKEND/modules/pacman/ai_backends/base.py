"""
PACMAN Backend Base Class
All extraction backends inherit from this
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class EntityType(Enum):
    PERSON = 'PERSON'
    COMPANY = 'COMPANY'
    EMAIL = 'EMAIL'
    PHONE = 'PHONE'
    ADDRESS = 'ADDRESS'
    DATE = 'DATE'
    MONEY = 'MONEY'
    URL = 'URL'
    IDENTIFIER = 'IDENTIFIER'  # LEI, IBAN, etc.
    CRYPTO = 'CRYPTO'


@dataclass
class ExtractedEntity:
    """Standard entity result format."""
    value: str
    entity_type: EntityType
    confidence: float
    source: str  # Which backend extracted it
    context: Optional[str] = None  # Surrounding text
    metadata: Optional[Dict] = None


class ExtractionBackend(ABC):
    """Base class for all extraction backends."""
    
    name: str = 'base'
    requires_api: bool = False
    cost_per_call: float = 0.0
    
    @abstractmethod
    async def extract(
        self, 
        content: str, 
        entity_types: Optional[List[EntityType]] = None
    ) -> List[ExtractedEntity]:
        """
        Extract entities from content.
        
        Args:
            content: Text to extract from
            entity_types: Optional filter for specific types
            
        Returns:
            List of ExtractedEntity objects
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available (API key, model loaded, etc)."""
        pass
    
    def estimate_cost(self, content: str) -> float:
        """Estimate cost to process content."""
        if not self.requires_api:
            return 0.0
        # Rough estimate: /bin/zsh.001 per 1K tokens
        tokens = len(content) / 4
        return (tokens / 1000) * self.cost_per_call


class BackendRegistry:
    """Registry of available backends."""
    
    _backends: Dict[str, ExtractionBackend] = {}
    
    @classmethod
    def register(cls, backend: ExtractionBackend):
        """Register a backend."""
        cls._backends[backend.name] = backend
    
    @classmethod
    def get(cls, name: str) -> Optional[ExtractionBackend]:
        """Get backend by name."""
        return cls._backends.get(name)
    
    @classmethod
    def available(cls) -> List[str]:
        """List available backends."""
        return [name for name, backend in cls._backends.items() if backend.is_available()]
    
    @classmethod
    def all_backends(cls) -> Dict[str, ExtractionBackend]:
        """Get all registered backends."""
        return cls._backends.copy()
