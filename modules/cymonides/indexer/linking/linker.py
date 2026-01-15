"""
Entity Linker - Links documents to canonical C-3 entities
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)


class LinkStrategy(Enum):
    """Strategy for entity linking"""
    EXACT = "exact"           # Exact match only
    FUZZY = "fuzzy"           # Fuzzy matching allowed
    GRAPH = "graph"           # Use graph relationships
    ENSEMBLE = "ensemble"     # Combine multiple strategies


@dataclass
class LinkResult:
    """Result of entity linking attempt"""
    success: bool
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_index: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "none"  # exact, fuzzy, inferred
    matched_field: Optional[str] = None
    matched_value: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "entity_index": self.entity_index,
            "confidence": self.confidence,
            "match_type": self.match_type,
            "matched_field": self.matched_field,
        }


class EntityLinker:
    """
    Links documents to canonical entities in C-3.
    
    During indexing, extracts identifiers (emails, domains, phones, names)
    and attempts to link them to existing entities in the superindex.
    Creates bi-directional links for graph traversal.
    """
    
    # Field patterns to extract for linking
    LINKABLE_FIELDS = {
        "email": ["email", "emails", "email_address", "e_mail"],
        "domain": ["domain", "domains", "website", "url"],
        "phone": ["phone", "phones", "telephone", "mobile", "cell"],
        "name": ["name", "full_name", "person_name", "company_name"],
    }
    
    # C-3 index mapping for entity types
    ENTITY_INDICES = {
        "email": "emails_unified",
        "domain": "domains_unified",
        "phone": "phones_unified",
        "person": "persons_unified",
        "company": "companies_unified",
    }
    
    def __init__(
        self,
        es_client,
        strategy: LinkStrategy = LinkStrategy.EXACT,
        min_confidence: float = 0.7,
        cache_size: int = 10000,
    ):
        self.es = es_client
        self.strategy = strategy
        self.min_confidence = min_confidence
        self._cache: Dict[str, LinkResult] = {}
        self._cache_size = cache_size
        self._stats = {
            "attempts": 0,
            "hits": 0,
            "misses": 0,
            "cache_hits": 0,
        }
    
    def _cache_key(self, entity_type: str, value: str) -> str:
        """Generate cache key"""
        return f"{entity_type}:{value.lower()}"
    
    def _add_to_cache(self, key: str, result: LinkResult):
        """Add result to cache with LRU eviction"""
        if len(self._cache) >= self._cache_size:
            # Simple eviction: remove oldest 10%
            keys_to_remove = list(self._cache.keys())[:self._cache_size // 10]
            for k in keys_to_remove:
                del self._cache[k]
        self._cache[key] = result
    
    async def link_email(self, email: str) -> LinkResult:
        """Link email to entity in atlas"""
        email = email.lower().strip()
        cache_key = self._cache_key("email", email)
        
        if cache_key in self._cache:
            self._stats["cache_hits"] += 1
            return self._cache[cache_key]
        
        self._stats["attempts"] += 1
        
        try:
            # Search atlas for email
            resp = await self.es.search(
                index="emails_unified",
                query={"term": {"email": email}},
                size=1,
            )
            
            hits = resp.get("hits", {}).get("hits", [])
            if hits:
                hit = hits[0]
                result = LinkResult(
                    success=True,
                    entity_id=hit["_id"],
                    entity_type="email",
                    entity_index="emails_unified",
                    confidence=1.0,
                    match_type="exact",
                    matched_field="email",
                    matched_value=email,
                )
                self._stats["hits"] += 1
            else:
                result = LinkResult(success=False, matched_value=email)
                self._stats["misses"] += 1
            
            self._add_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.warning(f"Email link error: {e}")
            return LinkResult(success=False, matched_value=email)
    
    async def link_domain(self, domain: str) -> LinkResult:
        """Link domain to entity in domains_unified"""
        domain = domain.lower().strip()
        # Remove protocol and path
        if "://" in domain:
            domain = domain.split("://")[1]
        domain = domain.split("/")[0]
        
        cache_key = self._cache_key("domain", domain)
        
        if cache_key in self._cache:
            self._stats["cache_hits"] += 1
            return self._cache[cache_key]
        
        self._stats["attempts"] += 1
        
        try:
            resp = await self.es.search(
                index="domains_unified",
                query={"term": {"domain": domain}},
                size=1,
            )
            
            hits = resp.get("hits", {}).get("hits", [])
            if hits:
                hit = hits[0]
                result = LinkResult(
                    success=True,
                    entity_id=hit["_id"],
                    entity_type="domain",
                    entity_index="domains_unified",
                    confidence=1.0,
                    match_type="exact",
                    matched_field="domain",
                    matched_value=domain,
                )
                self._stats["hits"] += 1
            else:
                result = LinkResult(success=False, matched_value=domain)
                self._stats["misses"] += 1
            
            self._add_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.warning(f"Domain link error: {e}")
            return LinkResult(success=False, matched_value=domain)
    
    async def link_phone(self, phone: str) -> LinkResult:
        """Link phone to entity in atlas"""
        import re
        # Normalize phone
        phone_normalized = re.sub(r"[^0-9+]", "", phone)
        
        cache_key = self._cache_key("phone", phone_normalized)
        
        if cache_key in self._cache:
            self._stats["cache_hits"] += 1
            return self._cache[cache_key]
        
        self._stats["attempts"] += 1
        
        try:
            resp = await self.es.search(
                index="emails_unified",
                query={"term": {"phone": phone_normalized}},
                size=1,
            )
            
            hits = resp.get("hits", {}).get("hits", [])
            if hits:
                hit = hits[0]
                result = LinkResult(
                    success=True,
                    entity_id=hit["_id"],
                    entity_type="phone",
                    entity_index="emails_unified",
                    confidence=1.0,
                    match_type="exact",
                    matched_field="phone",
                    matched_value=phone_normalized,
                )
                self._stats["hits"] += 1
            else:
                result = LinkResult(success=False, matched_value=phone_normalized)
                self._stats["misses"] += 1
            
            self._add_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.warning(f"Phone link error: {e}")
            return LinkResult(success=False, matched_value=phone_normalized)
    
    async def link_document(self, doc: Dict[str, Any]) -> List[LinkResult]:
        """
        Extract linkable fields from document and attempt to link each.
        Returns list of successful links.
        """
        links = []
        
        # Extract and link emails
        for field in self.LINKABLE_FIELDS["email"]:
            if field in doc and doc[field]:
                values = doc[field] if isinstance(doc[field], list) else [doc[field]]
                for val in values:
                    if val and "@" in str(val):
                        result = await self.link_email(str(val))
                        if result.success:
                            links.append(result)
        
        # Extract and link domains
        for field in self.LINKABLE_FIELDS["domain"]:
            if field in doc and doc[field]:
                values = doc[field] if isinstance(doc[field], list) else [doc[field]]
                for val in values:
                    if val:
                        result = await self.link_domain(str(val))
                        if result.success:
                            links.append(result)
        
        # Extract and link phones
        for field in self.LINKABLE_FIELDS["phone"]:
            if field in doc and doc[field]:
                values = doc[field] if isinstance(doc[field], list) else [doc[field]]
                for val in values:
                    if val:
                        result = await self.link_phone(str(val))
                        if result.success:
                            links.append(result)
        
        return links
    
    def get_stats(self) -> Dict[str, Any]:
        """Get linker statistics"""
        total = self._stats["attempts"]
        return {
            **self._stats,
            "hit_rate": self._stats["hits"] / max(total, 1),
            "cache_hit_rate": self._stats["cache_hits"] / max(total, 1),
            "cache_size": len(self._cache),
        }
    
    def clear_cache(self):
        """Clear the link cache"""
        self._cache.clear()
