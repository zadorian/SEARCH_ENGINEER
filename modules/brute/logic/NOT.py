#!/usr/bin/env python3
"""
NOT Search - Advanced exclusion search implementation
Handles complex exclusion queries with multiple verification steps

Brave Search Operator Support:
- Brave supports both "-" and "NOT" operators for exclusion
- According to https://search.brave.com/help/operators, both should work
- Historically, Brave's NOT operators have been unreliable
- This implementation uses "-" operator by default for consistency

Configuration:
- Set BRAVE_NOT_OPERATOR environment variable to "NOT" to use NOT operator
- Default is "minus" which uses the "-" operator
- Example: export BRAVE_NOT_OPERATOR=NOT

Usage Examples:
- "cars NOT electric NOT hybrid" - Exclude electric and hybrid cars
- "cars -electric -hybrid" - Same result using minus operator
- Mixed syntax is supported: "cars NOT electric -hybrid"

Limitations:
- Some engines may not fully respect exclusion operators
- Results are verified through multiple phases for accuracy
- Site-level verification adds latency but improves precision
"""

import asyncio
import logging
import re
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path
import sys
from urllib.parse import urlparse
import json
import os

# Add parent directory to path for brain.py access
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import AI functionality
try:
    from TOOLS.openai_chatgpt import chat_sync, analyze, GPT5_MODELS
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("Warning: AI brain not available for NOT search variations")

from brute.infrastructure.brute import BruteSearchEngine
from brute.infrastructure.site import SiteSearch as SiteSearcher
# Engine codes are now in brute.py
from brute.infrastructure.brute import ENGINE_CONFIG

# Import Variator system for sophisticated variation generation
try:
    from entities.variations.company_variator import CompanyVariator
    from entities.variations.person_variator import PersonVariator
    from entities.variations.location_variator import LocationVariator
    VARIATIONS_AVAILABLE = True
except ImportError:
    try:
        # Fallback to local imports
        from company_variator import CompanyVariator
        from person_variator import PersonVariator
        from location_variator import LocationVariator
        VARIATIONS_AVAILABLE = True
    except ImportError:
        VARIATIONS_AVAILABLE = False
        print("Warning: Variation modules not available for NOT search")
VARIATOR_AVAILABLE = True

# BrightData Archive - native support for NOT operators via blacklist filters
# Supports: -lang{}!, -geo{}!, -cat{}! through language_blacklist, ip_country_blacklist, category_blacklist
try:
    from backdrill.brightdata import BrightDataArchive
    BRIGHTDATA_AVAILABLE = True
except ImportError:
    BRIGHTDATA_AVAILABLE = False

logger = logging.getLogger(__name__)


class NOTSearcher:
    """
    Advanced exclusion search with simplified verification:
    1. Layer 1: Engine-native exclusion (expanded to 20+ engines)
    2. Layer 2: Simple snippet filtering (no AI needed)
    3. Layer 3: Broad search with ALL free engines + post-filtering
    4. Final verification: Simple string matching in snippets
    
    Key improvements:
    - No AI needed - just simple string matching
    - Uses ALL free engines for maximum recall
    - Filters based on presence of exclusion terms in snippets
    """
    
    def __init__(self, max_results_per_engine: int = 50, verification_batch_size: int = 10):
        self.max_results = max_results_per_engine
        self.verification_batch_size = verification_batch_size
        
        self.site_searcher = SiteSearcher()
        
        # Configuration for operator preference
        # Can be set via environment variable: BRAVE_NOT_OPERATOR = "minus" or "NOT"
        self.brave_operator_preference = os.environ.get('BRAVE_NOT_OPERATOR', 'minus').lower()
        
        # Engines that support native exclusion based on documentation analysis
        # Format: engine_code: (supports_minus, supports_NOT, notes)
        self.engine_exclusion_support = {
            'GO': (True, False, "Only - operator, no NOT"),  # Google
            'BI': (True, True, "Both - and NOT (uppercase)"),  # Bing  
            'YA': (True, False, "Only - operator"),  # Yandex
            'DD': (True, False, "Only - operator, no NOT"),  # DuckDuckGo
            'BR': (True, True, "Both - and NOT supported per docs, using - by default"),  # Brave
            'ST': (True, False, "Uses Google's syntax"),  # Startpage
            'YE': (True, False, "Likely supports - like Google"),  # Yep
            'AR': (True, True, "NOT operator and - prefix"),  # Archive.org
            'NE': (True, True, "Supports - and NOT in query"),  # NewsAPI
            'PU': (True, False, "Only - operator"),  # PublicWWW
            'EX': (False, False, "Uses excludeText parameter instead"),  # Exa
            # Newly approved engines with native exclusion support
            'QW': (True, False, "Qwant supports - operator"),  # Qwant
            'BA': (True, False, "Baidu supports - operator"),  # Baidu
            'BS': (True, False, "BareSearch/SearXNG supports -"),  # BareSearch
            'SS': (True, False, "SocialSearcher has exclude params"),  # SocialSearcher
            'BO': (True, False, "BoardReader supports -"),  # BoardReader
            'GD': (True, False, "GDELT can exclude in query"),  # GDELT
            'HF': (True, False, "HuggingFace supports -"),  # HuggingFace
            'W': (True, False, "WikiLeaks supports -"),  # WikiLeaks
            'WP': (True, False, "Wikipedia supports -"),  # Wikipedia
        }
        
        # Engines that reliably support exclusion
        self.exclusion_capable_engines = {
            code for code, (minus, NOT, _) in self.engine_exclusion_support.items() 
            if minus or NOT
        }
        
        # All free engines to use in Layer 3 (broad search with post-filtering)
        self.free_engines_layer3 = [
            # Scrapers (no API cost)
            'QW', 'ST', 'BS', 'YE', 'BA', 'WP',
            # Free APIs
            'PM', 'AX', 'CR', 'OA', 'OL', 'GU', 'W', 'SE',
            # Generous free tiers  
            'DD', 'AR', 'HF', 'AL', 'GD', 'SS', 'BO',
            # Academic (often free)
            'JS', 'NT', 'SG', 'MU', 'AA', 'LG'
        ]
        
        # Statistics tracking
        self.stats = {
            'total_found': 0,
            'snippet_filtered': 0,
            'site_verified': 0,
            'final_results': 0,
            'engines_used': [],
            'exclusion_terms': [],
            'search_phases': []
        }
    
    async def search_not(self, query: str) -> Dict[str, Any]:
        """
        Main NOT search method implementing multi-layer exclusion
        
        Args:
            query: Search query with NOT terms (e.g., "cars NOT electric NOT hybrid")
            
        Returns:
            Dictionary with filtered results and statistics
        """
        start_time = time.time()
        logger.info(f"Starting NOT search for: {query}")
        
        # Parse the query to extract inclusion and exclusion terms
        inclusion_terms, exclusion_terms = self._parse_not_query(query)
        
        if not exclusion_terms:
            return {
                'error': 'No exclusion terms found. Use "NOT term" or "-term" syntax.',
                'query': query,
                'results': []
            }
        
        # Store inclusion terms for context-aware filtering
        self.inclusion_terms = inclusion_terms
        self.stats['exclusion_terms'] = exclusion_terms
        logger.info(f"Inclusion terms: {inclusion_terms}")
        logger.info(f"Exclusion terms: {exclusion_terms}")
        
        # Skip AI variations - just use the original exclusion terms
        # Simple string matching is more reliable than AI-generated variations
        all_exclusion_terms = exclusion_terms
        self.stats['exclusion_variations'] = []
        
        # Phase 1: Engine-native exclusion search
        phase1_results = await self._phase1_engine_exclusion(inclusion_terms, all_exclusion_terms)
        self.stats['search_phases'].append('Engine Native Exclusion')
        
        # Phase 2: Snippet-level filtering
        phase2_results = await self._phase2_snippet_filtering(phase1_results, all_exclusion_terms)
        self.stats['search_phases'].append('Snippet Filtering')
        
        # Phase 3: Broad search with all free engines + simple filtering
        phase3_results = await self._phase3_broad_search_filtering(
            inclusion_terms, all_exclusion_terms, phase2_results
        )
        self.stats['search_phases'].append('Broad Search + Filtering')
        
        # Phase 4: Site-specific verification
        final_results = await self._phase4_site_verification(phase3_results, all_exclusion_terms)
        self.stats['search_phases'].append('Site Verification')
        
        # Update final statistics
        self.stats['final_results'] = len(final_results)
        execution_time = time.time() - start_time
        
        return {
            'query': query,
            'inclusion_terms': inclusion_terms,
            'exclusion_terms': exclusion_terms,
            'results': final_results,
            'total_unique_results': len(final_results),
            'execution_time_seconds': execution_time,
            'statistics': self.stats.copy(),
            'search_phases': self.stats['search_phases'],
            'engines_used': list(set(self.stats['engines_used']))
        }
    
    def _parse_not_query(self, query: str) -> Tuple[str, List[str]]:
        """
        Parse query to separate inclusion and exclusion terms
        Supports: "cars NOT electric NOT hybrid" and "cars -electric -hybrid"
        """
        exclusion_terms = []
        
        # Handle "NOT term" pattern
        not_pattern = r'\bNOT\s+([^\s]+(?:\s+[^\s]+)*?)(?:\s+NOT|\s+-|$)'
        not_matches = re.findall(not_pattern, query, re.IGNORECASE)
        exclusion_terms.extend(not_matches)
        
        # Handle "-term" pattern
        minus_pattern = r'-([^\s]+)'
        minus_matches = re.findall(minus_pattern, query)
        exclusion_terms.extend(minus_matches)
        
        # Clean up query by removing NOT patterns and minus terms
        clean_query = query
        clean_query = re.sub(r'\bNOT\s+[^\s]+(?:\s+[^\s]+)*?(?=\s+NOT|\s+-|$)', '', clean_query, flags=re.IGNORECASE)
        clean_query = re.sub(r'-[^\s]+', '', clean_query)
        clean_query = re.sub(r'\s+', ' ', clean_query).strip()
        
        return clean_query, exclusion_terms
    
    async def _generate_exclusion_variations(self, exclusion_terms: List[str]) -> List[str]:
        """
        Generate variations of exclusion terms using GPT-4.1-mini
        Includes: synonyms, related terms, common misspellings, plural/singular forms
        """
        if not AI_AVAILABLE or not exclusion_terms:
            return []
        
        variations = []
        
        try:
            brain = None
            
            # Create a structured prompt for variation generation
            prompt = f"""Generate variations for these exclusion terms to improve search accuracy.
For each term, provide:
1. Common synonyms and related terms
2. Plural/singular forms if applicable
3. Common misspellings or typos
4. Industry-specific or domain-specific alternatives

Terms to generate variations for: {', '.join(exclusion_terms)}

Return as JSON with this structure:
{{
    "variations": [
        {{
            "original": "term",
            "variations": ["variation1", "variation2", ...]
        }}
    ]
}}

Rules:
- Keep variations semantically related to the original
- Don't include the original term in variations
- Maximum 5 variations per term
- Focus on high-recall variations that would catch related content"""

            schema = {
                "type": "object",
                "properties": {
                    "variations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "original": {"type": "string"},
                                "variations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 5
                                }
                            },
                            "required": ["original", "variations"]
                        }
                    }
                },
                "required": ["variations"]
            }
            
            request = dict()
            
            response = await brain.process_request(request)
            
            if response.structured_data and 'variations' in response.structured_data:
                for item in response.structured_data['variations']:
                    variations.extend(item.get('variations', []))
                
                # Filter out empty strings and duplicates
                variations = list(set(v.strip() for v in variations if v.strip()))
                
                logger.info(f"AI generated {len(variations)} unique variations")
                return variations
            else:
                logger.warning("AI response did not contain expected variation data")
                return []
                
        except Exception as e:
            logger.error(f"Error generating variations: {e}")
            return []
    
    def _build_engine_specific_query(self, engine_code: str, inclusion_terms: str, exclusion_terms: List[str]) -> str:
        """
        Build engine-specific exclusion query based on what each engine supports
        """
        if engine_code not in self.engine_exclusion_support:
            # Default to minus operator
            query = inclusion_terms
            for term in exclusion_terms:
                query += f' -"{term}"'
            logger.warning(f"Engine {engine_code} not in exclusion support list, using default - operator")
            return query
        
        supports_minus, supports_not, notes = self.engine_exclusion_support[engine_code]
        logger.info(f"Engine {engine_code} - Supports minus: {supports_minus}, Supports NOT: {supports_not}, Notes: {notes}")
        
        # Special handling for specific engines
        if engine_code == 'BI':  # Bing - supports both, use NOT for better reliability
            query = inclusion_terms
            for term in exclusion_terms:
                query += f' NOT "{term}"'
        elif engine_code == 'BR':  # Brave - supports both - and NOT operators
            query = inclusion_terms
            # Use configurable operator preference (default: minus)
            if self.brave_operator_preference == 'not':
                for term in exclusion_terms:
                    query += f' NOT "{term}"'
                logger.debug(f"Brave query using NOT operator (configured): {query}")
            else:
                # Default to minus operator
                for term in exclusion_terms:
                    query += f' -"{term}"'
                logger.debug(f"Brave query using - operator (configured): {query}")
        elif engine_code == 'AR':  # Archive.org - prefers NOT
            query = inclusion_terms
            for term in exclusion_terms:
                query += f' NOT "{term}"'
        elif supports_minus:  # Most engines use minus
            query = inclusion_terms
            for term in exclusion_terms:
                query += f' -"{term}"'
        else:
            # Fallback for engines without exclusion support
            query = inclusion_terms
            
        return query
    
    async def _phase1_engine_exclusion(self, inclusion_terms: str, exclusion_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Phase 1: Use engines that support native exclusion operators
        """
        logger.info("Phase 1: Engine-native exclusion search")
        
        all_results = []
        engines_to_use = list(self.exclusion_capable_engines)
        
        # Run searches with engine-specific queries
        for engine_code in engines_to_use:
            try:
                # Build engine-specific query
                engine_query = self._build_engine_specific_query(engine_code, inclusion_terms, exclusion_terms)
                logger.info(f"Engine {engine_code} query: {engine_query}")
                
                # Search with this specific engine
                brute_searcher = BruteSearchEngine(keyword=inclusion_terms)
                results_data = await brute_searcher.search_multiple_engines(
                    engine_query,
                    engines=[engine_code],
                    max_results_per_engine=self.max_results // len(engines_to_use)  # Distribute quota
                )
                
                engine_results = results_data.get('results', [])
                all_results.extend(engine_results)
                
                if results_data.get('engines_used'):
                    self.stats['engines_used'].extend(results_data['engines_used'])
                
                # Log detailed operator effectiveness
                operator_type = "NOT" if "NOT" in engine_query else "-"
                logger.info(f"Engine {engine_code} using {operator_type} operator returned {len(engine_results)} results")
                logger.debug(f"Query: {engine_query[:100]}..." if len(engine_query) > 100 else f"Query: {engine_query}")
                
            except Exception as e:
                logger.error(f"Engine {engine_code} failed: {e}")
                continue
        
        # Deduplicate results from multiple engines
        deduplicated_results = self._deduplicate_by_url(all_results)
        self.stats['total_found'] = len(deduplicated_results)
        
        logger.info(f"Phase 1 found {len(deduplicated_results)} unique results after engine exclusion")
        return deduplicated_results
    
    async def _phase2_snippet_filtering(self, results: List[Dict[str, Any]], 
                                       exclusion_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Phase 2: Simple snippet filtering
        If exclusion term appears in title/snippet, filter it out - no complex context analysis needed
        """
        logger.info("Phase 2: Simple snippet filtering")
        
        filtered_results = []
        
        for result in results:
            # Combine all text fields for simple checking
            text_to_check = f"{result.get('title', '')} {result.get('snippet', '')} {result.get('description', '')}".lower()
            
            # Check if ANY exclusion term appears (simple substring match)
            has_excluded_term = False
            for exclusion_term in exclusion_terms:
                term_lower = exclusion_term.lower()
                
                # Use word boundary for accuracy (prevent "car" matching "scar")
                pattern = rf'\b{re.escape(term_lower)}\b'
                if re.search(pattern, text_to_check):
                    has_excluded_term = True
                    logger.debug(f"Excluding {result.get('url', 'N/A')} - contains '{exclusion_term}'")
                    break
            
            if not has_excluded_term:
                filtered_results.append(result)
        
        filtered_count = len(results) - len(filtered_results)
        self.stats['snippet_filtered'] = filtered_count
        
        logger.info(f"Phase 2 filtered out {filtered_count} results, {len(filtered_results)} remain")
        return filtered_results
    
    async def _phase3_broad_search_filtering(self, inclusion_terms: str, 
                                           exclusion_terms: List[str],
                                           existing_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Phase 3: Use ALL free engines with simple post-filtering
        Cast the widest net possible, then filter out results containing exclusion terms
        """
        logger.info("Phase 3: Broad search with all free engines + simple filtering")
        
        # Get URLs from existing results to avoid duplicates
        existing_urls = {result.get('url', '') for result in existing_results}
        
        # Search with ALL free engines using just inclusion terms (no exclusion)
        all_new_results = []
        
        # Use engines that don't have native exclusion or where we want broader coverage
        additional_engines = [eng for eng in self.free_engines_layer3 
                            if eng not in self.exclusion_capable_engines]
        
        if additional_engines:
            logger.info(f"Searching with additional free engines: {additional_engines}")
            
            try:
                brute_searcher = BruteSearchEngine(keyword=inclusion_terms)
                results_data = await brute_searcher.search_multiple_engines(
                    inclusion_terms,  # Just search with inclusion terms
                    engines=additional_engines,
                    max_results_per_engine=self.max_results // len(additional_engines)
                )
                
                batch_results = results_data.get('results', [])
                
                # Simple filtering: exclude if snippet contains exclusion terms
                for result in batch_results:
                    url = result.get('url', '')
                    if url and url not in existing_urls:
                        # Check snippet for exclusion terms
                        text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
                        
                        has_excluded = False
                        for term in exclusion_terms:
                            pattern = rf'\b{re.escape(term.lower())}\b'
                            if re.search(pattern, text):
                                has_excluded = True
                                break
                        
                        if not has_excluded:
                            all_new_results.append(result)
                            existing_urls.add(url)
                
                self.stats['engines_used'].extend(results_data.get('engines_used', []))
                
            except Exception as e:
                logger.error(f"Broad search failed: {e}")
        
        # Combine with existing results
        all_results = existing_results + all_new_results
        
        logger.info(f"Phase 3 added {len(all_new_results)} new results from free engines, {len(all_results)} total")
        return all_results
    
    async def _phase4_site_verification(self, results: List[Dict[str, Any]], 
                                      exclusion_terms: List[str]) -> List[Dict[str, Any]]:
        """
        Phase 4: Simple verification - if we already have snippets, use them
        For URLs without snippets, optionally verify with site search
        """
        logger.info("Phase 4: Simple snippet-based verification")
        
        verified_results = []
        urls_needing_verification = []
        
        # First pass: filter based on existing snippets
        for result in results:
            snippet = result.get('snippet', '') + ' ' + result.get('title', '')
            
            if snippet.strip():  # We have snippet data
                # Simple check: does snippet contain exclusion terms?
                text_lower = snippet.lower()
                has_excluded = False
                
                for term in exclusion_terms:
                    pattern = rf'\b{re.escape(term.lower())}\b'
                    if re.search(pattern, text_lower):
                        has_excluded = True
                        logger.debug(f"Excluding {result.get('url', 'N/A')} - snippet contains '{term}'")
                        break
                
                if not has_excluded:
                    verified_results.append(result)
            else:
                # No snippet available, might need verification
                urls_needing_verification.append(result)
        
        # Optional: for results without snippets, do bulk site verification
        if urls_needing_verification and len(urls_needing_verification) < 50:
            logger.info(f"Verifying {len(urls_needing_verification)} URLs without snippets")
            
            for result in urls_needing_verification:
                url = result.get('url', '')
                domain = self._extract_domain(url)
                
                # Quick domain-level check for any exclusion term
                should_exclude = False
                for term in exclusion_terms[:3]:  # Check first 3 terms only for speed
                    try:
                        site_query = f'site:{domain} "{term}"'
                        check_results = await self.site_searcher.search_by_domain(term, domain, max_results=1)
                        
                        # If domain has the term anywhere, be conservative and exclude
                        if check_results and any(check_results.values()):
                            should_exclude = True
                            logger.debug(f"Domain {domain} contains '{term}' - excluding {url}")
                            break
                    except Exception as e:

                        print(f"[BRUTE] Error: {e}")

                        pass  # On error, include the result
                
                if not should_exclude:
                    verified_results.append(result)
        else:
            # Too many URLs without snippets, just include them all
            verified_results.extend(urls_needing_verification)
        
        self.stats['site_verified'] = len(results) - len(verified_results)
        
        logger.info(f"Phase 4 completed: {len(verified_results)} results remain after verification")
        return verified_results
        
        # Process URLs in parallel batches to avoid overwhelming the search engines
        verified_results = []
        
        for i in range(0, len(results), self.verification_batch_size):
            batch = results[i:i + self.verification_batch_size]
            batch_num = i // self.verification_batch_size + 1
            total_batches = (len(results) + self.verification_batch_size - 1) // self.verification_batch_size
            
            logger.info(f"Processing batch {batch_num} of {total_batches} ({len(batch)} URLs)")
            
            # Run verifications in parallel for this batch
            verification_tasks = [verify_single_url(result) for result in batch]
            batch_results = await asyncio.gather(*verification_tasks, return_exceptions=True)
            
            # Process results, handling any exceptions
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Verification task failed: {result}")
                elif result is not None:
                    verified_results.append(result)
            
            # Small delay between batches to be respectful to search engines
            if i + self.verification_batch_size < len(results):
                await asyncio.sleep(0.5)
        
        self.stats['site_verified'] = verification_count
        
        excluded_count = len(results) - len(verified_results)
        logger.info(f"Phase 4 performed {verification_count} URL verifications, excluded {excluded_count} URLs, {len(verified_results)} remain")
        return verified_results
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception as e:
            return url
    
    def _deduplicate_by_url(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate results based on URL"""
        seen_urls = set()
        deduplicated = []
        
        for result in results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(result)
        
        return deduplicated
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search statistics"""
        return self.stats.copy()


# CLI interface for testing
async def main():
    """Test the NOT searcher"""
    import argparse
    
    parser = argparse.ArgumentParser(description='NOT Search - Advanced exclusion search')
    parser.add_argument('query', help='Search query with NOT terms')
    parser.add_argument('-m', '--max-results', type=int, default=50, 
                       help='Maximum results per engine')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose logging')
    
    args = parser.parse_args()
    
    # Set up logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Run the search
    searcher = NOTSearcher(max_results_per_engine=args.max_results)
    results = await searcher.search_not(args.query)
    
    # Display results
    if 'error' in results:
        logger.error(f"Error: {results['error']}")
        return
    
    logger.info(f"🚫 NOT Search Results for: {args.query}")
    logger.info("="*60)
    logger.info(f"📝 Inclusion terms: {results['inclusion_terms']}")
    logger.info(f"🚫 Exclusion terms: {', '.join(results['exclusion_terms'])}")
    logger.info(f"⏱️  Execution time: {results['execution_time_seconds']:.2f}s")
    logger.info(f"🔍 Engines used: {', '.join(results['engines_used'])}")
    logger.info(f"📊 Search phases: {' → '.join(results['search_phases'])}")
    
    stats = results['statistics']
    logger.info(f"\n📈 Filtering Statistics:")
    logger.info(f"  Initial results: {stats['total_found']}")
    logger.info(f"  Snippet filtered: {stats['snippet_filtered']}")
    logger.info(f"  Site verifications: {stats['site_verified']}")
    logger.info(f"  Final results: {stats['final_results']}")
    
    logger.info(f"\n✅ Found {len(results['results'])} results after exclusion filtering:")
    
    for i, result in enumerate(results['results'][:10], 1):
        logger.info(f"{i}. {result.get('title', 'No Title')}")
        logger.info(f"   🔗 URL: {result.get('url', 'N/A')}")
        logger.info(f"   🏷️  Source: {result.get('source', 'N/A')}")
        
        snippet = result.get('snippet', '')
        if snippet:
            snippet = snippet[:200] + '...' if len(snippet) > 200 else snippet
            logger.info(f"   📝 Snippet: {snippet}")
    
    if len(results['results']) > 10:
        logger.info(f"\n... and {len(results['results']) - 10} more results")


if __name__ == '__main__':
    asyncio.run(main())