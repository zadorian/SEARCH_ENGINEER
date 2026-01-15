"""
LINKLATER Related Entities Module

Discovers and extracts related entities from link analysis results,
then passes them to brute search for comprehensive coverage.

Integration Points:
- PACMAN: Entity extraction from scraped content
- Nexus Bridge: Graph relationship building
- Brute Tier 1: Fast search (no scraping) for discovered entities

Usage:
    from linklater.related_entities import discover_related_entities
    
    entities = await discover_related_entities(
        domain="example.com",
        depth=2
    )
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Ensure modules are importable
sys.path.insert(0, "/data")


@dataclass
class RelatedEntity:
    """Entity discovered from link analysis."""
    value: str
    entity_type: str  # person, company, email, phone, address, identifier
    source_domain: str
    discovery_method: str  # majestic_backlink, whois_registrant, content_extraction
    confidence: float = 0.0
    context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityDiscoveryResult:
    """Result of entity discovery process."""
    target_domain: str
    discovered_at: datetime
    entities: List[RelatedEntity]
    domains_analyzed: int
    backlinks_processed: int
    error: Optional[str] = None


class RelatedEntitiesDiscovery:
    """
    Discovers related entities through link analysis.
    
    Pipeline:
    1. LINKLATER Discovery → Get backlinks, WHOIS, related domains
    2. PACMAN Extraction → Extract entities from discovered content
    3. Nexus Bridge → Build entity relationships in graph
    4. Brute Tier 1 → Fast search for new entities (no scraping)
    
    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    ENTITY DISCOVERY                         │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
    │  │  LINKLATER   │    │    PACMAN    │    │    NEXUS     │  │
    │  │  Discovery   │───▶│  Extraction  │───▶│   Bridge     │  │
    │  │              │    │              │    │              │  │
    │  │ • Majestic   │    │ • Regex      │    │ • Graph add  │  │
    │  │ • WHOIS      │    │ • GLiNER     │    │ • Relations  │  │
    │  │ • Archives   │    │ • GPT/Gemini │    │ • Edges      │  │
    │  └──────────────┘    └──────────────┘    └──────────────┘  │
    │                             │                               │
    │                             ▼                               │
    │                    ┌──────────────┐                        │
    │                    │ BRUTE Tier 1 │                        │
    │                    │ Fast Search  │                        │
    │                    │ (no scrape)  │                        │
    │                    └──────────────┘                        │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.pacman_bridge = None
        self.nexus_bridge = None
        self._init_bridges()
    
    def _init_bridges(self):
        """Initialize PACMAN and Nexus bridges."""
        try:
            # PACMAN bridge for entity extraction
            from PACMAN.entity_extractors import extract_persons, extract_companies
            from PACMAN.patterns import ALL_PATTERNS
            self.pacman_available = True
            logger.info("PACMAN bridge initialized")
        except ImportError as e:
            logger.warning(f"PACMAN not available: {e}")
            self.pacman_available = False
        
        try:
            # Nexus bridge for graph operations
            # TODO: Implement when Nexus module is available
            self.nexus_available = False
            logger.info("Nexus bridge: placeholder")
        except Exception as e:
            logger.warning(f"Nexus not available: {e}")
            self.nexus_available = False
    
    async def discover(
        self,
        domain: str,
        depth: int = 2,
        include_backlinks: bool = True,
        include_whois: bool = True,
        max_entities: int = 100
    ) -> EntityDiscoveryResult:
        """
        Discover related entities for a domain.
        
        Args:
            domain: Target domain to analyze
            depth: How many levels of links to follow
            include_backlinks: Use Majestic backlink data
            include_whois: Use WHOIS registrant data
            max_entities: Maximum entities to return
        
        Returns:
            EntityDiscoveryResult with discovered entities
        """
        entities: List[RelatedEntity] = []
        domains_analyzed = 0
        backlinks_processed = 0
        
        try:
            # Step 1: LINKLATER Discovery
            logger.info(f"[DISCOVERY] Starting for {domain}")
            
            if include_backlinks:
                backlink_entities = await self._extract_from_backlinks(domain)
                entities.extend(backlink_entities)
                backlinks_processed = len(backlink_entities)
                logger.info(f"[BACKLINKS] Found {len(backlink_entities)} entities")
            
            if include_whois:
                whois_entities = await self._extract_from_whois(domain)
                entities.extend(whois_entities)
                logger.info(f"[WHOIS] Found {len(whois_entities)} entities")
            
            # Step 2: PACMAN Extraction (if available)
            if self.pacman_available and entities:
                enhanced = await self._enhance_with_pacman(entities)
                entities = enhanced
                logger.info(f"[PACMAN] Enhanced to {len(entities)} entities")
            
            # Step 3: Nexus Bridge (placeholder)
            if self.nexus_available:
                await self._add_to_graph(domain, entities)
            
            # Deduplicate and limit
            entities = self._deduplicate(entities)[:max_entities]
            
            return EntityDiscoveryResult(
                target_domain=domain,
                discovered_at=datetime.utcnow(),
                entities=entities,
                domains_analyzed=domains_analyzed,
                backlinks_processed=backlinks_processed
            )
            
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            return EntityDiscoveryResult(
                target_domain=domain,
                discovered_at=datetime.utcnow(),
                entities=entities,
                domains_analyzed=domains_analyzed,
                backlinks_processed=backlinks_processed,
                error=str(e)
            )
    
    async def _extract_from_backlinks(self, domain: str) -> List[RelatedEntity]:
        """Extract entities from Majestic backlink data."""
        entities = []
        
        try:
            from linklater.discovery.majestic_discovery import get_backlink_data
            
            result = await get_backlink_data(domain)
            if not result or not result.results:
                return entities
            
            for backlink in result.results:
                # Extract domain as potential entity
                if backlink.source_domain:
                    entities.append(RelatedEntity(
                        value=backlink.source_domain,
                        entity_type="domain",
                        source_domain=domain,
                        discovery_method="majestic_backlink",
                        confidence=backlink.trust_flow / 100 if backlink.trust_flow else 0.5,
                        context=backlink.anchor_text,
                        metadata={
                            "trust_flow": backlink.trust_flow,
                            "citation_flow": backlink.citation_flow,
                            "source_url": backlink.source_url
                        }
                    ))
                
                # Extract from anchor text (potential names/companies)
                if backlink.anchor_text and len(backlink.anchor_text) > 3:
                    entities.append(RelatedEntity(
                        value=backlink.anchor_text,
                        entity_type="text",  # Will be classified by PACMAN
                        source_domain=backlink.source_domain,
                        discovery_method="majestic_anchor",
                        confidence=0.4,
                        metadata={"source_url": backlink.source_url}
                    ))
        
        except Exception as e:
            logger.error(f"Backlink extraction error: {e}")
        
        return entities
    
    async def _extract_from_whois(self, domain: str) -> List[RelatedEntity]:
        """Extract entities from WHOIS registration data."""
        entities = []
        
        try:
            from linklater.discovery.whois_discovery import whois_lookup
            
            record = await whois_lookup(domain)
            if not record:
                return entities
            
            # Registrant info
            if hasattr(record, "registrant_name") and record.registrant_name:
                entities.append(RelatedEntity(
                    value=record.registrant_name,
                    entity_type="person",
                    source_domain=domain,
                    discovery_method="whois_registrant",
                    confidence=0.9,
                    metadata={"field": "registrant_name"}
                ))
            
            if hasattr(record, "registrant_org") and record.registrant_org:
                entities.append(RelatedEntity(
                    value=record.registrant_org,
                    entity_type="company",
                    source_domain=domain,
                    discovery_method="whois_registrant",
                    confidence=0.9,
                    metadata={"field": "registrant_org"}
                ))
            
            # Admin/tech contacts
            for contact_type in ["admin", "tech"]:
                name_field = f"{contact_type}_name"
                org_field = f"{contact_type}_org"
                email_field = f"{contact_type}_email"
                
                if hasattr(record, name_field) and getattr(record, name_field):
                    entities.append(RelatedEntity(
                        value=getattr(record, name_field),
                        entity_type="person",
                        source_domain=domain,
                        discovery_method=f"whois_{contact_type}",
                        confidence=0.8,
                        metadata={"field": name_field}
                    ))
                
                if hasattr(record, email_field) and getattr(record, email_field):
                    entities.append(RelatedEntity(
                        value=getattr(record, email_field),
                        entity_type="email",
                        source_domain=domain,
                        discovery_method=f"whois_{contact_type}",
                        confidence=0.95,
                        metadata={"field": email_field}
                    ))
        
        except Exception as e:
            logger.error(f"WHOIS extraction error: {e}")
        
        return entities
    
    async def _enhance_with_pacman(self, entities: List[RelatedEntity]) -> List[RelatedEntity]:
        """Use PACMAN to enhance entity classification."""
        try:
            from PACMAN.entity_extractors.persons import validate_person
            from PACMAN.entity_extractors.companies import validate_company
            
            enhanced = []
            for entity in entities:
                if entity.entity_type == "text":
                    # Try to classify unknown text
                    person_conf = validate_person(entity.value)
                    company_conf, _ = validate_company(entity.value)
                    
                    if person_conf > 0.7:
                        entity.entity_type = "person"
                        entity.confidence = person_conf
                    elif company_conf > 0.7:
                        entity.entity_type = "company"
                        entity.confidence = company_conf
                
                enhanced.append(entity)
            
            return enhanced
        except Exception as e:
            logger.warning(f"PACMAN enhancement failed: {e}")
            return entities
    
    async def _add_to_graph(self, domain: str, entities: List[RelatedEntity]):
        """Add discovered entities to the knowledge graph via Nexus bridge."""
        # TODO: Implement when Nexus module is available
        logger.info(f"[NEXUS] Would add {len(entities)} entities to graph for {domain}")
    
    def _deduplicate(self, entities: List[RelatedEntity]) -> List[RelatedEntity]:
        """Remove duplicate entities."""
        seen: Set[str] = set()
        unique = []
        
        for entity in entities:
            key = f"{entity.entity_type}:{entity.value.lower()}"
            if key not in seen:
                seen.add(key)
                unique.append(entity)
        
        # Sort by confidence
        unique.sort(key=lambda e: e.confidence, reverse=True)
        return unique


# Convenience function
async def discover_related_entities(domain: str, **kwargs) -> EntityDiscoveryResult:
    """
    Discover related entities for a domain.
    
    This is the main entry point for entity discovery.
    
    Example:
        result = await discover_related_entities("example.com")
        for entity in result.entities:
            print(f"{entity.entity_type}: {entity.value}")
    """
    discovery = RelatedEntitiesDiscovery()
    return await discovery.discover(domain, **kwargs)


# CLI for testing
async def main():
    """CLI for testing related entities discovery."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Discover related entities")
    parser.add_argument("domain", help="Target domain")
    parser.add_argument("--depth", type=int, default=2, help="Discovery depth")
    parser.add_argument("--max", type=int, default=50, help="Max entities")
    args = parser.parse_args()
    
    result = await discover_related_entities(
        args.domain,
        depth=args.depth,
        max_entities=args.max
    )
    
    print(f"\n=== Related Entities for {args.domain} ===\n")
    print(f"Domains analyzed: {result.domains_analyzed}")
    print(f"Backlinks processed: {result.backlinks_processed}")
    print(f"Entities found: {len(result.entities)}")
    
    if result.error:
        print(f"Error: {result.error}")
    
    print("\n--- Entities ---")
    for entity in result.entities[:20]:
        print(f"  [{entity.entity_type}] {entity.value} ({entity.confidence:.2f})")
        print(f"    via: {entity.discovery_method}")


if __name__ == "__main__":
    asyncio.run(main())
