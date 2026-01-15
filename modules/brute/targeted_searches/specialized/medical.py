#!/usr/bin/env python3
"""
Medical/Health Search Operator - Searches for medical and health information
Supports medical:, health:, symptom: operators with schema integration
Leverages medical platforms and Schema.org MedicalCondition/Drug structured data
"""

import sys
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import time
import re

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import event streaming for filtering events
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logging.warning("Event streaming not available for medical search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Medical search engines
MEDICAL_ENGINES = [
    'GO',  # Google - with schema search
    'BI',  # Bing
    'BR',  # Brave
    'DD',  # DuckDuckGo
    'PM',  # PubMed - medical literature
]

# Major medical/health platforms
MEDICAL_PLATFORMS = {
    'pubmed': 'site:pubmed.ncbi.nlm.nih.gov',
    'webmd': 'site:webmd.com',
    'mayo_clinic': 'site:mayoclinic.org',
    'nih': 'site:nih.gov',
    'medlineplus': 'site:medlineplus.gov',
    'healthline': 'site:healthline.com',
    'cleveland_clinic': 'site:clevelandclinic.org',
    'hopkins': 'site:hopkinsmedicine.org',
    'harvard_health': 'site:health.harvard.edu',
    'medscape': 'site:medscape.com',
    'drugs_com': 'site:drugs.com',
    'rxlist': 'site:rxlist.com',
    'cdc': 'site:cdc.gov',
    'who': 'site:who.int',
    'patient_info': 'site:patient.info',
    'medical_news': 'site:medicalnewstoday.com',
    'clinicaltrials': 'site:clinicaltrials.gov',
}

# Schema.org structured data queries for medical content
MEDICAL_SCHEMAS = [
    'more:pagemap:medicalcondition',
    'more:pagemap:medicalcondition-name',
    'more:pagemap:drug',
    'more:pagemap:drug-name',
    'more:pagemap:medicalprocedure',
    'more:pagemap:medicaltest',
    'more:pagemap:medicalclinic',
    'more:pagemap:medicalstudy',
    'more:pagemap:medicaltreatment',
    'more:pagemap:healthtopicpage',
]

class MedicalSearch:
    """
    Medical search operator implementation.
    Routes searches to medical platforms and uses schema-enhanced queries.
    """
    
    def __init__(self, event_emitter=None):
        """Initialize medical search with optional event streaming."""
        self.event_emitter = event_emitter
        self.available_engines = self._check_available_engines()
        
        if STREAMING_AVAILABLE and event_emitter:
            self.streamer = SearchTypeEventEmitter(event_emitter)
        else:
            self.streamer = None
    
    def _check_available_engines(self) -> List[str]:
        """Check which medical-supporting engines are available in the system."""
        available = []
        
        try:
            from brute.targeted_searches.brute import ENGINE_CONFIG
            
            for engine_code in MEDICAL_ENGINES:
                if engine_code in ENGINE_CONFIG:
                    available.append(engine_code)
                    logger.info(f"Medical engine {engine_code} available")
        except ImportError:
            logger.error("Could not import ENGINE_CONFIG from brute.py")
            available = ['GO', 'BI', 'BR']
        
        if not available:
            available = ['GO', 'BI', 'BR']
        
        logger.info(f"Available medical engines: {available}")
        return available
    
    def _build_medical_queries(self, query: str, include_platforms: bool = True, 
                               include_schemas: bool = True) -> List[str]:
        """Build comprehensive medical search queries."""
        queries = []
        
        # Base queries
        queries.append(f'{query} symptoms')
        queries.append(f'{query} treatment')
        queries.append(f'{query} diagnosis')
        queries.append(f'{query} causes')
        queries.append(f'{query} medication')
        queries.append(f'{query} medical')
        
        # Platform-specific searches
        if include_platforms:
            top_platforms = ['pubmed', 'webmd', 'mayo_clinic', 'nih', 
                           'medlineplus', 'healthline', 'cdc']
            for platform_name in top_platforms:
                if platform_name in MEDICAL_PLATFORMS:
                    platform_filter = MEDICAL_PLATFORMS[platform_name]
                    queries.append(f'{platform_filter} {query}')
        
        # Schema-enhanced searches (Google API only)
        if include_schemas and 'GO' in self.available_engines:
            for schema in MEDICAL_SCHEMAS:
                queries.append(f'{schema} {query}')
            
            queries.extend([
                f'more:pagemap:medicalcondition-name:"{query}"',
                f'more:pagemap:drug-name:"{query}"',
                f'more:pagemap:medicalprocedure {query}',
            ])
        
        # Medical-specific patterns
        queries.extend([
            f'"{query}" side effects',
            f'"{query}" prevention',
            f'"{query}" risk factors',
            f'"{query}" prognosis',
            f'"{query}" clinical trial',
            f'"{query}" research',
        ])
        
        return queries
    
    async def search(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Execute medical search across available engines."""
        cleaned_query = query.strip()
        
        logger.info(f"Starting medical search for: '{cleaned_query}'")
        
        if self.streamer:
            await self.streamer.emit_search_started('medical', cleaned_query, self.available_engines)
        
        # Build comprehensive medical queries
        medical_queries = self._build_medical_queries(cleaned_query)
        
        try:
            from brute.targeted_searches.brute import BruteSearchEngine
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"results/medical_{timestamp}.json"
            
            all_results = []
            
            for medical_query in medical_queries[:12]:
                logger.info(f"Searching with query: '{medical_query}'")
                
                searcher = BruteSearchEngine(
                    keyword=medical_query,
                    output_file=output_file,
                    engines=self.available_engines,
                    max_workers=min(len(self.available_engines), 5),
                    event_emitter=self.event_emitter,
                    return_results=True
                )
                
                searcher.search()
                
                if hasattr(searcher, 'final_results'):
                    results = searcher.final_results
                    for result in results:
                        result['search_type'] = 'medical'
                        result['medical_query'] = cleaned_query
                        result['query_variant'] = medical_query
                    all_results.extend(results)
            
            # Deduplicate results
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            # Score and sort results
            scored_results = self._score_medical_results(unique_results, cleaned_query)
            
            if self.streamer:
                await self.streamer.emit_search_completed('medical', len(scored_results))
            
            return scored_results[:max_results]
            
        except Exception as e:
            logger.error(f"Medical search failed: {e}")
            return []
    
    def _score_medical_results(self, results: List[Dict], query: str) -> List[Dict]:
        """Score and sort medical results by relevance."""
        query_lower = query.lower()
        
        def score_result(result):
            score = 0
            url = result.get('url', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Check if from known medical platform (highest priority)
            major_platforms = ['pubmed.ncbi.nlm.nih.gov', 'mayoclinic.org', 'nih.gov',
                             'webmd.com', 'medlineplus.gov', 'healthline.com',
                             'cdc.gov', 'who.int', 'hopkinsmedicine.org']
            for platform in major_platforms:
                if platform in url:
                    score += 60
                    break
            
            # Check for medical schema markup
            if 'query_variant' in result:
                variant = result['query_variant']
                if 'more:pagemap:medicalcondition' in variant:
                    score += 50
                elif 'more:pagemap:drug' in variant:
                    score += 45
            
            # Medical keywords in title
            medical_keywords = ['symptoms', 'treatment', 'diagnosis', 'medication',
                              'disease', 'condition', 'syndrome', 'disorder',
                              'therapy', 'medicine', 'health', 'clinical']
            for keyword in medical_keywords:
                if keyword in title:
                    score += 25
                    break
            
            # Query appears in title
            if query_lower in title:
                score += 30
            
            # Medical credibility indicators
            if any(word in snippet.lower() for word in ['peer-reviewed', 'clinical trial', 
                                                         'research', 'study', 'journal']):
                score += 15
            
            # Medical professional indicators
            if any(word in snippet.lower() for word in ['md', 'phd', 'doctor', 'physician',
                                                         'specialist', 'expert']):
                score += 10
            
            # Warning: Non-professional sources (lower score)
            if any(word in url for word in ['forum', 'blog', 'answers', 'quora']):
                score -= 20
            
            return score
        
        # Score all results
        for result in results:
            result['medical_score'] = score_result(result)
        
        # Sort by score
        results.sort(key=lambda x: x.get('medical_score', 0), reverse=True)
        
        return results
    
    def search_sync(self, query: str, max_results: int = 200) -> List[Dict[str, Any]]:
        """Synchronous wrapper for search method."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.search(query, max_results))
        finally:
            loop.close()

def detect_medical_query(query: str) -> bool:
    """Detect if a query should be routed to medical search."""
    query_lower = query.lower()
    
    medical_patterns = [
        'medical:',
        'health:',
        'symptom:',
        'symptoms:',
        'disease:',
        'treatment:',
        'medication:',
        'drug:',
    ]
    
    for pattern in medical_patterns:
        if pattern in query_lower:
            return True
    
    return False

def extract_medical_query(query: str) -> str:
    """Extract the actual search query from a medical search query."""
    query = query.strip()
    
    prefixes = [
        'medical:', 'health:', 'symptom:', 'symptoms:', 'disease:', 
        'treatment:', 'medication:', 'drug:',
        'Medical:', 'Health:', 'Symptom:', 'Symptoms:', 'Disease:',
        'Treatment:', 'Medication:', 'Drug:'
    ]
    
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            if query.startswith('"') and query.endswith('"'):
                query = query[1:-1]
            elif query.startswith("'") and query.endswith("'"):
                query = query[1:-1]
            return query
    
    return query.strip()

# Main entry point
async def run_medical_search(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Main entry point for medical search."""
    clean_query = extract_medical_query(query)
    searcher = MedicalSearch(event_emitter)
    return await searcher.search(clean_query)

def run_medical_search_sync(query: str, event_emitter=None) -> List[Dict[str, Any]]:
    """Synchronous wrapper for medical search."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_medical_search(query, event_emitter))
    finally:
        loop.close()


def search(query: str) -> List[Dict[str, Any]]:
    """Synchronous search function for web API compatibility"""
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
        # We're already in an async context, use ThreadPoolExecutor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_medical_search(query))
            return future.result()
    except RuntimeError:
        # No event loop running, create one
        return asyncio.run(run_medical_search(query))

def main():
    """Main entry point for Medical/health search - compatible with SearchRouter"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Medical/health search')
    parser.add_argument('-q', '--query', required=True, help='Search query')
    args = parser.parse_args()
    
    query = args.query
    
    # Extract clean query by removing operator prefix
    if ':' in query:
        clean_query = query.split(':', 1)[1].strip()
    else:
        clean_query = query
    
    print(f"\n🔍 Medical/health search: {clean_query}")
    
    # Try to use existing search function if available
    try:
        if 'run_medical_search_sync' in globals():
            results = globals()['run_medical_search_sync'](clean_query)
        elif 'search' in globals():
            results = search(clean_query)
        else:
            print("Note: This search type needs full implementation")
            results = []
    except Exception as e:
        print(f"Search implementation in progress: {e}")
        results = []
    
    if results:
        print(f"\nFound {len(results)} results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No Title')}")
            print(f"   URL: {result.get('url')}")
            if result.get('snippet'):
                print(f"   {result['snippet'][:200]}...")
    else:
        print("\nNo results found (implementation may be pending).")
    
    return results

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = "medical:diabetes symptoms"
    
    print(f"Testing medical search with: {test_query}")
    
    if detect_medical_query(test_query):
        print("Medical query detected!")
        clean_query = extract_medical_query(test_query)
        print(f"Extracted query: '{clean_query}'")
        
        results = run_medical_search_sync(test_query)
        
        print(f"\nFound {len(results)} medical results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            print(f"   Score: {result.get('medical_score', 0)}")
    else:
        print("Not a medical query")