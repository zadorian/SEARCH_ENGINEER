#!/usr/bin/env python3
"""
AllDOM Search Type - Find ALL URLs from a specific domain
Wraps the specialist alldom tool and adds snippet enrichment
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add paths for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import snippet enrichment
try:
    from snippet_enrichment import SnippetEnricher
    ENRICHMENT_AVAILABLE = True
except ImportError as e:
    ENRICHMENT_AVAILABLE = False
    print(f"Warning: Snippet enrichment not available: {e}")

# Import the specialist alldom module
try:
    from .specialist_sources.url_dom_search.alldom import collect_all_urls
    from .specialist_sources.url_dom_search.master_search import FirecrawlIntegration
    ALLDOM_AVAILABLE = True
except ImportError as e:
    ALLDOM_AVAILABLE = False
    print(f"Warning: AllDOM specialist module not available: {e}")

logger = logging.getLogger(__name__)


class AlldomSearcher:
    """Standardized searcher class for alldom searches."""
    
    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
        self.enricher = self._initialize_enricher()
        self.firecrawl = self._initialize_firecrawl()
        
    def _initialize_enricher(self):
        """Initialize the snippet enricher"""
        if ENRICHMENT_AVAILABLE:
            try:
                return SnippetEnricher()
            except Exception as e:
                logger.error(f"Failed to initialize snippet enricher: {e}")
        return None
        
    def _initialize_firecrawl(self):
        """Initialize Firecrawl integration"""
        if ALLDOM_AVAILABLE:
            try:
                return FirecrawlIntegration()
            except Exception as e:
                logger.error(f"Failed to initialize Firecrawl: {e}")
        return None
    
    def search(self, query: str) -> Dict[str, Any]:
        """Standardized search method called by main.py."""
        try:
            # Extract domain from query
            # Remove any alldom: prefix if present
            if query.lower().startswith('alldom:'):
                domain = query[7:].strip()
            else:
                domain = query.strip()
                
            # Clean domain
            if domain.startswith(('http://', 'https://')):
                from urllib.parse import urlparse
                domain = urlparse(domain).netloc
            
            if not ALLDOM_AVAILABLE:
                return {'error': 'AllDOM module not available', 'results': []}
                
            # Run async collection synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                urls = loop.run_until_complete(collect_all_urls(domain))
            finally:
                loop.close()
                
            # Format results
            formatted_results = []
            for url in urls:
                # Ensure URL has protocol
                if not url.startswith(('http://', 'https://')):
                    full_url = f'https://{url}'
                else:
                    full_url = url
                    
                formatted_results.append({
                    'url': full_url,
                    'title': f'Page at {url}',
                    'snippet': f'Found on domain {domain}',
                    'source': 'alldom',
                    'rank': len(formatted_results) + 1
                })
            
            # Limit results for enrichment (too many URLs can be slow)
            max_enrich = 100  # Enrich first 100 URLs
            
            # Enrich results with real snippets if enricher is available
            if self.enricher and formatted_results:
                results_to_enrich = formatted_results[:max_enrich]
                remaining_results = formatted_results[max_enrich:]
                
                # Run async enrichment in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    enriched_results = loop.run_until_complete(
                        self._enrich_results_async(results_to_enrich)
                    )
                    # Combine enriched and remaining results
                    formatted_results = enriched_results + remaining_results
                finally:
                    loop.close()
            
            return {
                'query': query,
                'domain': domain,
                'total_results': len(formatted_results),
                'results': formatted_results,
                'search_type': 'alldom',
                'enriched_count': min(max_enrich, len(formatted_results)) if self.enricher else 0,
                'sources': {
                    'firecrawl_map': True,
                    'search_engines': True,
                    'wayback': True,
                    'sitemaps': True,
                    'enrichment': self.enricher is not None
                }
            }
            
        except Exception as e:
            logger.error(f"Error during alldom search: {e}")
            return {'error': str(e), 'results': []}
    
    async def _enrich_results_async(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich results with real titles and snippets"""
        # Extract URLs for enrichment
        urls = [r['url'] for r in results]
        
        # Enrich in batches
        logger.info(f"Enriching {len(urls)} alldom results with snippets")
        enrichment_data = await self.enricher.enrich(urls)
        
        # Update results with enriched data
        enriched_results = []
        for result in results:
            url = result['url']
            enrichment = enrichment_data.get(url) if isinstance(enrichment_data, dict) else None
            
            if enrichment:
                # Update with real title and snippet
                result['title'] = enrichment.get('title', result['title'])
                result['snippet'] = enrichment.get('snippet', result['snippet'])
                result['enriched'] = True
                result['enrichment_backend'] = enrichment.get('backend', 'unknown')
            else:
                # Keep original placeholder data
                result['enriched'] = False
                
            enriched_results.append(result)
            
        return enriched_results
    
    async def search_async(self, query: str) -> Dict[str, Any]:
        """Async version of search"""
        # Run the sync search in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.search, query)


def main():
    """Test the alldom search functionality"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AllDOM Search - Find all URLs from a domain')
    parser.add_argument('domain', help='Domain to search (e.g., example.com)')
    parser.add_argument('--limit', '-l', type=int, default=50, help='Maximum results to display')
    
    args = parser.parse_args()
    
    searcher = AlldomSearcher()
    
    print(f"🔍 Searching for all URLs on: '{args.domain}'")
    print("=" * 60)
    
    result = searcher.search(args.domain)
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
        return
    
    results = result['results'][:args.limit]
    
    print(f"✅ Found {result['total_results']} URLs:")
    print(f"   Enriched: {result.get('enriched_count', 0)} URLs with real titles/snippets")
    print()
    
    for i, res in enumerate(results, 1):
        print(f"{i:3d}. {res['url']}")
        if res.get('enriched'):
            print(f"     Title: {res['title']}")
            print(f"     Snippet: {res['snippet'][:100]}...")
        if i % 10 == 0:  # Pause every 10 results
            input("Press Enter to continue...")


if __name__ == "__main__":
    main()