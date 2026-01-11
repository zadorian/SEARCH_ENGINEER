#!/usr/bin/env python3
"""
Academic Search Operator - Routes searches to academic/scholarly engines only
Supports academic! and scholar! operators for focused academic research
Leverages specialized academic search engines for comprehensive scholarly coverage
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for academic search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Academic-specific search engines to use
ACADEMIC_ENGINES = [
    'OA',  # OpenAlex - 240M+ academic works
    'CR',  # Crossref - 150M+ scholarly content
    'PM',  # PubMed Central - Medical/biomedical
    'AX',  # arXiv - Physics/CS/Math preprints
    'SE',  # Semantic Scholar - AI-enhanced academic (changed from SS to avoid conflict)
    'NT',  # Nature - High-impact scientific journals
    'JS',  # JSTOR - Historical and current scholarship
    'MU',  # Project MUSE - Humanities and social sciences
    'SG',  # SAGE Journals - Science, technology, medicine, social sciences
    'AA',  # Anna's Archive - Searches both books AND journals
    'LG',  # LibGen - Library Genesis academic books and articles
    'BK',  # Local book collection - Academic PDFs
    'WP',  # Wikipedia - Encyclopedic content
    'GO',  # Google - Can find academic PDFs
    'BI',  # Bing - Academic results
]

# Fallback engines if primary academic engines aren't available
FALLBACK_ENGINES = ['GO', 'BI', 'DD', 'BR']

class AcademicSearch:
    """
    Academic search operator implementation.
    Routes searches exclusively to academic/scholarly search engines.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize academic search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which academic engines are available in the system."""
        available = []
        
        # Check ENGINE_CONFIG from brute.py
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in ACADEMIC_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Academic engine {engine_code} available")
                else:
                    logger.debug(f"Academic engine {engine_code} not configured")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            # Use fallback engines
            available = FALLBACK_ENGINES
        
        if not available:
            logger.warning("No academic engines available, using fallback engines")
            available = FALLBACK_ENGINES
        
        logger.info(f"Available academic engines: {available}")
        return available
    
    async def search(self, query: str, max_results: int = 100, tier: int = 1) -> List[Dict[str, Any]]:
        """
        Execute academic search across available scholarly engines.
        
        Args:
            query: The search query (without the academic! operator)
            max_results: Maximum results to return
            
        Returns:
            List of search results from academic sources
        """
        # Strip the operator if it's still present
        query = query.replace(' academic!', '').replace(' scholar!', '').strip()
        
        logger.info(f"Starting academic search for: '{query}' (tier={tier})")
        
        if self.streamer:
            await self.streamer.emit_search_started('academic', query, self.available_engines)
        
        # Import and run brute search with academic engines only
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            # Central filtering (optional)
            try:
                from brute.filtering.core.filter_manager import get_filter_manager
                fm = get_filter_manager()
            except Exception:
                fm = None
            
            # Create output file for results
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/academic_{timestamp}.json"
            
            # Tiered engine groups
            tier1 = ['OA', 'CR', 'PM', 'AX', 'SE', 'NT', 'JS', 'MU', 'SG']
            tier2 = ['GO', 'BI', 'BR', 'DD']
            tier3 = ['AA', 'LG', 'BK', 'WP']

            ordered_groups = []
            if tier >= 1:
                ordered_groups.append(('L1', [e for e in tier1 if e in self.available_engines]))
            if tier >= 2:
                ordered_groups.append(('L2', [e for e in tier2 if e in self.available_engines or e in self.available_engines]))
            if tier >= 3:
                ordered_groups.append(('L3', [e for e in tier3 if e in self.available_engines]))

            combined_results: List[Dict[str, Any]] = []

            for layer_tag, engines in ordered_groups:
                if not engines:
                    continue
                try:
                    searcher = BruteSearchEngine(
                        keyword=query,
                        output_file=output_file,
                        engines=engines,
                        max_workers=min(len(engines), 8),
                        event_emitter=self.event_emitter,
                        return_results=True
                    )
                    searcher.search()
                    layer_results = searcher.final_results if hasattr(searcher, 'final_results') else []
                    for r in layer_results or []:
                        try:
                            r['layer_used'] = layer_tag
                        except Exception:
                            pass
                    combined_results.extend(layer_results or [])
                except Exception as e:
                    logger.warning(f"Tier group {layer_tag} failed: {e}")

            results = combined_results[:max_results]
            
            if self.streamer:
                await self.streamer.emit_search_completed('academic', len(results))
            
            # Apply central filtering if available; keep return type as list (primary)
            primary_results = results
            if fm and results:
                try:
                    processed = await fm.process_results(
                        results=results,
                        search_type='academic',
                        query_context={'query': query, 'tier': tier},
                        filter_config={'strictness': 0.5}
                    )
                    primary_results = processed.get('primary', results)
                except Exception as e:
                    logger.warning(f"Academic filtering failed, returning unfiltered results: {e}")

            logger.info(f"Academic search completed with {len(primary_results)} primary results (from {len(results)} total)")
            return primary_results[:max_results]
            
        except ImportError as e:
            logger.error(f"Failed to import BruteForceSearch: {e}")
            return []
        except Exception as e:
            logger.error(f"Academic search failed: {e}")
            return []
    
    def search_sync(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_academic_query(query: str) -> bool:
    """
    Detect if a query should be routed to academic search.
    
    Patterns:
    - "search term academic!"
    - "search term scholar!"
    - "academic:search term"
    - "scholar:search term"
    """
    query_lower = query.lower()
    
    # Check for operators at the end
    if query_lower.endswith(' academic!') or query_lower.endswith(' scholar!'):
        return True
    
    # Check for operators at the beginning
    if query_lower.startswith('academic:') or query_lower.startswith('scholar:'):
        return True
    
    return False

def extract_academic_query(query: str) -> str:
    """Extract the actual search query from an academic search query."""
    # Remove operators
    query = query.replace(' academic!', '').replace(' scholar!', '')
    
    # Remove prefix operators
    if query.lower().startswith('academic:'):
        query = query[9:].strip()
    elif query.lower().startswith('scholar:'):
        query = query[8:].strip()
    
    return query.strip()

# Main entry point for academic search
async def run_academic_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """
    Main entry point for academic search.
    
    Args:
        query: The full query including academic!/scholar! operator
        event_emitter: Optional event emitter for streaming updates
        
    Returns:
        List of academic search results
    """
    # Extract the actual query
    clean_query = extract_academic_query(query)
    
    # Create academic searcher
    searcher = AcademicSearch(event_emitter)
    
    # Run search
    return await searcher.search(clean_query)

def run_academic_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for academic search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_academic_search(query, event_emitter))
    finally:
        loop.close()

if __name__ == "__main__":
    # Test academic search
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "machine learning academic!"
    
    print(f"Testing academic search with: {test_query}")
    
    if detect_academic_query(test_query):
        print("Academic query detected!")
        results = run_academic_search_sync(test_query)
        
        print(f"\nFound {len(results)} academic results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Source: {result.get('source', 'Unknown')}")
    else:
        print("Not an academic query")