#!/usr/bin/env python3
"""
InDOM Search Type - Find domains containing keywords
Example: searching "tesla" finds tesla.com, teslashop.com, teslamotors.com, etc.

This is a targeted_searches interface that calls the specialist indom tools.
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add paths for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent / 'specialist_sources' / 'url_dom_search'))
BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import snippet enrichment
try:
    from snippet_enrichment import SnippetEnricher
    ENRICHMENT_AVAILABLE = True
except ImportError as e:
    ENRICHMENT_AVAILABLE = False
    print(f"Warning: Snippet enrichment not available: {e}")

# Import the specialist indom module
try:
    from .specialist_sources.url_dom_search.indom import InDOMSearch
    INDOM_AVAILABLE = True
except ImportError as e:
    INDOM_AVAILABLE = False
    print(f"Warning: InDOM specialist module not available: {e}")

# Import the FTS5 domain search
try:
    from .domain_fts5_search import DomainFTS5Search
    FTS5_AVAILABLE = True
except ImportError as e:
    FTS5_AVAILABLE = False
    print(f"Warning: FTS5 domain search not available: {e}")

# Optional ATLAS unified domain list
try:
    from modules.atlas import atlas as atlas_client
    ATLAS_AVAILABLE = True
except Exception as e:
    ATLAS_AVAILABLE = False
    atlas_client = None
    print(f"Warning: Atlas indom not available: {e}")

logger = logging.getLogger(__name__)


class IndomSearcher:
    """Standardized searcher class for indom searches."""
    
    def __init__(self, additional_args: List[str] = None):
        self.additional_args = additional_args or []
        self.indom_engine = self._initialize_indom_engine()
        self.fts5_engine = self._initialize_fts5_engine()
        self.enricher = self._initialize_enricher()
        self.atlas = atlas_client if ATLAS_AVAILABLE else None
    
    def _initialize_indom_engine(self):
        """Initialize the InDOM search engine"""
        if INDOM_AVAILABLE:
            try:
                return InDOMSearch()
            except Exception as e:
                logger.error(f"Failed to initialize InDOM engine: {e}")
        return None
    
    def _initialize_fts5_engine(self):
        """Initialize the FTS5 domain search engine"""
        if FTS5_AVAILABLE:
            try:
                return DomainFTS5Search()
            except Exception as e:
                logger.error(f"Failed to initialize FTS5 engine: {e}")
                logger.info("Run create_domain_fts5_index.py to create the domain database")
        return None
    
    def _initialize_enricher(self):
        """Initialize the snippet enricher"""
        if ENRICHMENT_AVAILABLE:
            try:
                return SnippetEnricher()
            except Exception as e:
                logger.error(f"Failed to initialize snippet enricher: {e}")
        return None
    
    def search(self, query: str) -> Dict[str, Any]:
        """Standardized search method called by main.py."""
        try:
            # Extract keyword(s) from query
            # Remove any indom: prefix if present
            if query.lower().startswith('indom:'):
                keyword = query[6:].strip()
            else:
                keyword = query.strip()
            
            formatted_results = []
            seen_domains = set()
            
            # First, search FTS5 database (2.3M domains)
            if self.fts5_engine:
                try:
                    fts5_results = self.fts5_engine.search(keyword, limit=100)
                    for result in fts5_results:
                        domain = result['domain']
                        if domain not in seen_domains:
                            seen_domains.add(domain)
                            formatted_results.append({
                                'url': f"https://{domain}",
                                'domain': domain,
                                'title': result['name'] or f"Domain: {domain}",
                                'snippet': f"Category: {result['subcategory'][:100]}..." if result['subcategory'] else f"Domain containing '{keyword}'",
                                'source': f'fts5_{result["source"].lower()}',
                                'bang': result['bang'],
                                'rank': len(formatted_results) + 1
                            })
                except Exception as e:
                    logger.error(f"FTS5 search error: {e}")

            # Next, use ATLAS unified domain list (if available)
            if self.atlas:
                try:
                    atlas_result = self.atlas.indom(keyword, limit=200)
                    atlas_results = getattr(atlas_result, "results", []) if atlas_result else []
                    for result in atlas_results:
                        if not isinstance(result, dict):
                            continue
                        domain = result.get("domain")
                        if not domain or domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        categories = result.get("categories") or []
                        snippet = f"Atlas unified domain match for '{keyword}'"
                        if categories:
                            snippet = f"Atlas categories: {', '.join(categories[:3])}"
                        formatted_results.append({
                            'url': f"https://{domain}",
                            'domain': domain,
                            'title': f"Domain: {domain}",
                            'snippet': snippet,
                            'source': 'atlas_unified',
                            'rank': len(formatted_results) + 1
                        })
                except Exception as e:
                    logger.error(f"Atlas indom error: {e}")
            
            # Then, use original InDOM engine for additional results
            if self.indom_engine:
                try:
                    domains = self.indom_engine.search_domains(keyword)
                    for domain in domains:
                        if domain not in seen_domains:
                            seen_domains.add(domain)
                            formatted_results.append({
                                'url': f"http://{domain}",
                                'domain': domain,
                                'title': f"Domain: {domain}",
                                'snippet': f"Domain containing '{keyword}': {domain}",
                                'source': 'indom_original',
                                'rank': len(formatted_results) + 1
                            })
                except Exception as e:
                    logger.error(f"InDOM engine error: {e}")
            
            # If neither engine is available, return error
            if not self.fts5_engine and not self.indom_engine:
                return {'error': 'No domain search engines available', 'results': []}
            
            # Enrich results with real snippets if enricher is available
            if self.enricher and formatted_results:
                # Run async enrichment in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    enriched_results = loop.run_until_complete(
                        self._enrich_results_async(formatted_results)
                    )
                    formatted_results = enriched_results
                finally:
                    loop.close()
            
            return {
                'query': query,
                'keyword': keyword,
                'total_results': len(formatted_results),
                'results': formatted_results,
                'search_type': 'indom',
                'engines_used': {
                    'fts5': self.fts5_engine is not None,
                    'indom_original': self.indom_engine is not None,
                    'atlas_unified': self.atlas is not None,
                    'enrichment': self.enricher is not None
                }
            }
            
        except Exception as e:
            logger.error(f"Error during indom search: {e}")
            return {'error': str(e), 'results': []}
    
    async def _enrich_results_async(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich results with real titles and snippets"""
        # Extract URLs for enrichment
        urls = [r['url'] for r in results]
        
        # Enrich in batches
        logger.info(f"Enriching {len(urls)} domain results with snippets")
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
    """Test the indom search functionality"""
    import argparse
    
    parser = argparse.ArgumentParser(description='InDOM Search - Find domains containing keywords')
    parser.add_argument('keyword', help='Keyword to search for in domains')
    parser.add_argument('--limit', '-l', type=int, default=50, help='Maximum results to return')
    
    args = parser.parse_args()
    
    searcher = IndomSearcher()
    
    print(f"🔍 Searching for domains containing: '{args.keyword}'")
    print("=" * 60)
    
    result = searcher.search(args.keyword)
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
        return
    
    results = result['results'][:args.limit]
    
    print(f"✅ Found {result['total_results']} domains:")
    print()
    
    for i, res in enumerate(results, 1):
        print(f"{i:3d}. {res['domain']}")
        if i % 20 == 0:  # Pause every 20 results
            input("Press Enter to continue...")


if __name__ == "__main__":
    main()
