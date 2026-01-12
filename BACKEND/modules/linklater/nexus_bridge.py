#!/usr/bin/env python3
"""
LINKLATER -> NEXUS Bridge

Bridge for calling NEXUS modules from LINKLATER.
Primary use: Call CLINK for chain entity discovery.

Usage:
    from nexus_bridge import NexusBridge
    
    bridge = NexusBridge()
    
    # Discover related sites from entities extracted by LINKLATER
    entities = [
        {"value": "John Smith", "type": "person"},
        {"value": "Acme Corp", "type": "company"}
    ]
    results = await bridge.discover_related(entities, source_url="https://example.com")
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add NEXUS to path
sys.path.insert(0, "/data/CLASSES")
sys.path.insert(0, "/data/CLASSES/NEXUS")

# Import CLINK from NEXUS
try:
    from NEXUS.clink import CLINK
except ImportError:
    try:
        from clink import CLINK
    except ImportError:
        CLINK = None


class NexusBridge:
    """
    Bridge between LINKLATER and NEXUS modules.
    
    Provides interface for:
    - CLINK: Chain entity discovery
    - Future NEXUS modules
    """
    
    def __init__(self, engines: Optional[List[str]] = None):
        """
        Initialize the bridge.
        
        Args:
            engines: Search engines for CLINK. Default: free engines
        """
        self.engines = engines or ["brave"]
        self._clink = None
    
    async def _get_clink(self) -> CLINK:
        """Lazy load CLINK instance."""
        if self._clink is None:
            if CLINK is None:
                raise RuntimeError("CLINK not available. Check NEXUS module at /data/CLASSES/NEXUS/")
            self._clink = CLINK(engines=self.engines)
        return self._clink
    
    async def discover_related(
        self,
        entities: List[Dict[str, Any]],
        source_url: Optional[str] = None,
        min_matches: int = 2,
        max_results_per_combo: int = 20
    ) -> Dict[str, Any]:
        """
        Discover related sites from entities using CLINK.
        
        This is the main method LINKLATER uses to find sites mentioning
        the same entities extracted from backlinks or WHOIS data.
        
        Args:
            entities: List of entities with 'value' and 'type' keys
                     Types: person, company, email, phone, domain
            source_url: Original URL to exclude from results
            min_matches: Minimum entities a site must mention
            max_results_per_combo: Max search results per entity
            
        Returns:
            Dict containing:
                - related_sites: Sites with multiple entity matches
                - entity_results: Raw results per entity
                - stats: Discovery statistics
        """
        clink = await self._get_clink()
        return await clink.discover(
            entities=entities,
            source_url=source_url,
            min_matches=min_matches,
            max_results_per_combo=max_results_per_combo
        )
    
    async def search_single_entity(
        self,
        value: str,
        entity_type: str,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for a single entity with variations.
        
        Args:
            value: Entity value (e.g., "John Smith")
            entity_type: Type (person, company, email, phone, domain)
            max_results: Max results to return
            
        Returns:
            List of search results
        """
        clink = await self._get_clink()
        from NEXUS.clink import Entity
        entity = Entity(value=value, entity_type=entity_type)
        return await clink.search_entity(entity, max_results=max_results)
    
    async def close(self):
        """Clean up resources."""
        if self._clink:
            await self._clink.close()
            self._clink = None


# Convenience function for LINKLATER integration
async def discover_from_linklater(
    majestic_entities: List[Dict[str, Any]] = None,
    whois_entities: List[Dict[str, Any]] = None,
    source_domain: str = None,
    min_matches: int = 2
) -> Dict[str, Any]:
    """
    Convenience function for LINKLATER to discover related sites.
    
    Combines entities from Majestic backlinks and WHOIS clustering,
    then uses CLINK to find sites mentioning multiple entities.
    
    Args:
        majestic_entities: Entities extracted from Majestic backlinks
        whois_entities: Entities extracted from WHOIS clustering
        source_domain: Original domain to exclude
        min_matches: Minimum entity matches required
        
    Returns:
        CLINK discovery results
    """
    all_entities = []
    
    if majestic_entities:
        all_entities.extend(majestic_entities)
    if whois_entities:
        all_entities.extend(whois_entities)
    
    if not all_entities:
        return {
            "related_sites": [],
            "entity_results": {},
            "stats": {"error": "No entities provided"}
        }
    
    # Deduplicate by value
    seen = set()
    unique_entities = []
    for e in all_entities:
        key = (e.get("value", "").lower(), e.get("type", ""))
        if key not in seen and e.get("value"):
            seen.add(key)
            unique_entities.append(e)
    
    source_url = f"https://{source_domain}" if source_domain else None
    
    bridge = NexusBridge()
    try:
        return await bridge.discover_related(
            entities=unique_entities,
            source_url=source_url,
            min_matches=min_matches
        )
    finally:
        await bridge.close()


# CLI for testing
async def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="LINKLATER -> NEXUS Bridge")
    parser.add_argument("--entities", "-e", nargs="+", help="Entities (value:type)")
    parser.add_argument("--source", "-s", help="Source domain to exclude")
    parser.add_argument("--min-matches", "-m", type=int, default=2)
    parser.add_argument("--json", "-j", action="store_true")
    
    args = parser.parse_args()
    
    if not args.entities:
        # Demo
        entities = [
            {"value": "GitHub", "type": "company"},
            {"value": "Microsoft", "type": "company"},
        ]
        print("[Bridge] Using demo entities: GitHub, Microsoft")
    else:
        entities = []
        for e in args.entities:
            if ":" in e:
                value, etype = e.rsplit(":", 1)
                entities.append({"value": value, "type": etype})
            else:
                entities.append({"value": e, "type": "unknown"})
    
    bridge = NexusBridge()
    try:
        results = await bridge.discover_related(
            entities=entities,
            source_url=f"https://{args.source}" if args.source else None,
            min_matches=args.min_matches
        )
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\n=== NEXUS Bridge Results ===")
            print(f"Entities searched: {results['stats']['entities_provided']}")
            print(f"Total results: {results['stats']['total_results']}")
            print(f"Related sites found: {results['stats']['unique_sites']}")
            
            for site in results["related_sites"][:10]:
                print(f"\n[{site['match_count']} matches] {site['domain']}")
                print(f"  URL: {site['url']}")
                entities_str = ", ".join(site["matched_entities"])
                print(f"  Entities: {entities_str}")
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
