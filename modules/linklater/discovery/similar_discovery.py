"""
LINKLATER Similar Content Discovery

Find websites similar to a target URL using multiple sources:
- Exa API (findSimilar endpoint)
- CLINK (entity-based related sites)
- Ahrefs Similar Content
- Google "related:" operator (legacy)

Part of LINKLATER's related site discovery capabilities.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SimilarSite:
    """A site similar to the target."""
    url: str
    domain: str
    title: str = ""
    score: float = 0.0
    source: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if not self.domain and self.url:
            self.domain = self._extract_domain(self.url)
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return domain.replace("www.", "")
        except:
            return ""


class SimilarContentDiscovery:
    """
    Discover websites similar to a target URL.
    
    Combines multiple methods:
    - Exa API: Content similarity via LLM embeddings
    - CLINK: Entity-based related sites
    - Ahrefs: Backlink-based similarity
    """
    
    def __init__(self):
        self.exa_available = False
        self.clink_available = False
        self.ahrefs_available = False
        self._init_sources()
    
    def _init_sources(self):
        """Initialize available similarity sources."""
        # Check Exa
        try:
            from modules.brute.engines.exa import ExaEngine
            self.exa_available = True
            self.exa = ExaEngine()
        except ImportError:
            logger.warning("Exa engine not available for similar content")
            self.exa = None
        
        # Check CLINK
        try:
            from CLASSES.NEXUS.clink import CLINK
            self.clink_available = True
        except ImportError:
            logger.warning("CLINK not available for entity-based similarity")
        
        # Check Ahrefs
        try:
            import os
            if os.getenv("AHREFS_API_KEY"):
                self.ahrefs_available = True
        except:
            pass
    
    async def find_similar_exa(
        self, 
        url: str, 
        limit: int = 20,
        **kwargs
    ) -> List[SimilarSite]:
        """
        Find similar sites using Exa API.
        Uses LLM embeddings for content similarity.
        """
        if not self.exa_available or not self.exa:
            return []
        
        try:
            response = await self.exa.find_similar(url, num_results=limit, **kwargs)
            
            results = []
            for item in response.get("results", []):
                results.append(SimilarSite(
                    url=item.get("url"),
                    domain="",
                    title=item.get("title", ""),
                    score=item.get("score", 0.0),
                    source="exa",
                    metadata={
                        "similarity_score": item.get("score"),
                        "published_date": item.get("publishedDate"),
                        "author": item.get("author"),
                        "highlights": item.get("highlights", [])
                    }
                ))
            
            return results
        except Exception as e:
            logger.error(f"Exa similar content error: {e}")
            return []
    
    async def find_similar_clink(
        self,
        url: str,
        limit: int = 20,
        **kwargs
    ) -> List[SimilarSite]:
        """
        Find related sites using CLINK entity matching.
        Extracts entities from target URL, finds sites mentioning same entities.
        """
        if not self.clink_available:
            return []
        
        try:
            from CLASSES.NEXUS.clink import CLINK
            from modules.alldom.utils.entity_extraction import extract_entities
            from modules.jester import Jester
            
            # Step 1: Scrape target URL to get entities
            jester = Jester()
            result = await jester.scrape(url)
            await jester.close()
            
            if not result or not result.content:
                return []
            
            # Step 2: Extract entities
            payload = {
                "content": result.content,
                "html": result.content,
                "url": url
            }
            entities = extract_entities(payload, fallback_url=url)
            
            if not entities:
                return []
            
            # Step 3: Use CLINK to find related sites
            clink = CLINK()
            clink_entities = [
                {"value": e.get("value"), "entity_type": e.get("type")}
                for e in entities
            ]
            
            related = await clink.discover(
                clink_entities,
                source_url=url,
                max_results=limit
            )
            
            await clink.close()
            
            # Convert to SimilarSite format
            results = []
            for site in related:
                results.append(SimilarSite(
                    url=site.get("url"),
                    domain=site.get("domain", ""),
                    title=site.get("title", ""),
                    score=site.get("match_count", 0) / len(entities) if entities else 0,
                    source="clink",
                    metadata={
                        "matched_entities": site.get("matched_entities", []),
                        "match_count": site.get("match_count", 0),
                        "engines": site.get("engines", [])
                    }
                ))
            
            return results
        except Exception as e:
            logger.error(f"CLINK similar content error: {e}")
            return []
    
    async def find_similar_all(
        self,
        url: str,
        limit: int = 20,
        methods: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, List[SimilarSite]]:
        """
        Find similar sites using all available methods.
        
        Args:
            url: Target URL
            limit: Max results per method
            methods: List of methods to use ['exa', 'clink'], or None for all
        
        Returns:
            Dict mapping method name to list of similar sites
        """
        if methods is None:
            methods = []
            if self.exa_available:
                methods.append('exa')
            if self.clink_available:
                methods.append('clink')
        
        tasks = []
        if 'exa' in methods and self.exa_available:
            tasks.append(('exa', self.find_similar_exa(url, limit, **kwargs)))
        if 'clink' in methods and self.clink_available:
            tasks.append(('clink', self.find_similar_clink(url, limit, **kwargs)))
        
        results = {}
        for method, task in tasks:
            try:
                results[method] = await task
            except Exception as e:
                logger.error(f"Error in {method} similar discovery: {e}")
                results[method] = []
        
        return results
    
    async def find_similar(
        self,
        url: str,
        limit: int = 20,
        prefer_method: str = "exa",
        **kwargs
    ) -> List[SimilarSite]:
        """
        Find similar sites using preferred method with fallback.
        
        Args:
            url: Target URL
            limit: Max results
            prefer_method: Preferred method ('exa' or 'clink')
        
        Returns:
            List of similar sites from first successful method
        """
        methods = [prefer_method]
        if prefer_method == "exa" and self.clink_available:
            methods.append("clink")
        elif prefer_method == "clink" and self.exa_available:
            methods.append("exa")
        
        for method in methods:
            if method == "exa" and self.exa_available:
                results = await self.find_similar_exa(url, limit, **kwargs)
                if results:
                    return results
            elif method == "clink" and self.clink_available:
                results = await self.find_similar_clink(url, limit, **kwargs)
                if results:
                    return results
        
        return []


# Convenience functions
async def find_similar(url: str, limit: int = 20, **kwargs) -> List[SimilarSite]:
    """Find similar sites (convenience function)."""
    discovery = SimilarContentDiscovery()
    return await discovery.find_similar(url, limit, **kwargs)


async def find_similar_all(url: str, limit: int = 20, **kwargs) -> Dict[str, List[SimilarSite]]:
    """Find similar sites using all methods (convenience function)."""
    discovery = SimilarContentDiscovery()
    return await discovery.find_similar_all(url, limit, **kwargs)


# CLI
async def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python similar_discovery.py <url> [limit]")
        return
    
    url = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    print(f"Finding sites similar to: {url}")
    print(f"Limit: {limit} per method\n")
    
    results = await find_similar_all(url, limit)
    
    for method, sites in results.items():
        print(f"\n=== {method.upper()} ({len(sites)} results) ===")
        for site in sites[:10]:
            print(f"  [{site.score:.2f}] {site.url}")
            if site.title:
                print(f"       {site.title}")


if __name__ == "__main__":
    asyncio.run(main())

# Alias for compatibility
find_similar_content = find_similar
