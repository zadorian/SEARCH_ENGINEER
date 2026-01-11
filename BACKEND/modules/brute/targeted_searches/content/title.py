#!/usr/bin/env python3
"""
Title Search - Search for terms within page titles using intitle: and allintitle: operators
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import os
import asyncio
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search engines from engines directory
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

# Set up logger
logger = logging.getLogger(__name__)

# Import from self-contained runner modules with individual error handling
try:
    from exact_phrase_recall_runner_google import GoogleSearch
    GOOGLE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Google search: {e}")
    GOOGLE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_bing import BingSearch
    BING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Bing search: {e}")
    BING_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yandex import YandexSearch
    YANDEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yandex search: {e}")
    YANDEX_AVAILABLE = False

try:
    from exact_phrase_recall_runner_brave import BraveSearch
    BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Brave search: {e}")
    BRAVE_AVAILABLE = False

try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    DUCKDUCKGO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import DuckDuckGo search: {e}")
    DUCKDUCKGO_AVAILABLE = False

try:
    from exact_phrase_recall_runner_yep import YepScraper as YepSearch
    YEP_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Could not import Yep search: {e}")
    YEP_AVAILABLE = False

# Import Majestic for title search
# SearchByKeyword returns ScoreInTitle, ScoreInURL, ScoreInAnchor - we filter by ScoreInTitle
try:
    import httpx
    MAJESTIC_API_KEY = os.getenv("MAJESTIC_API_KEY")
    MAJESTIC_AVAILABLE = bool(MAJESTIC_API_KEY)
    MAJESTIC_BASE_URL = "https://api.majestic.com/api/json"
    if not MAJESTIC_AVAILABLE:
        logger.warning("MAJESTIC_API_KEY not set - Majestic title search disabled")
except ImportError:
    MAJESTIC_AVAILABLE = False
    MAJESTIC_API_KEY = None
    MAJESTIC_BASE_URL = None

class TitleSearcher:
    """Search for terms within page titles using title-specific operators"""
    
    # Engine-specific title operator mappings
    ENGINE_OPERATORS = {
        'google': {
            'intitle': 'intitle:',
            'allintitle': 'allintitle:'
        },
        'bing': {
            'intitle': 'intitle:',
            'allintitle': 'allintitle:'
        },
        'yandex': {
            'intitle': 'title:',
            'allintitle': 'title:'
        },
        'brave': {
            'intitle': 'intitle:',
            'allintitle': 'allintitle:'
        },
        'duckduckgo': {
            'intitle': 'intitle:',
            'allintitle': 'allintitle:'
        },
        'yep': {
            'intitle': 'intitle:',
            'allintitle': 'allintitle:'
        }
    }
    
    def __init__(self):
        """Initialize search engines"""
        self.engines = {}
        
        # Initialize engines based on availability
        if GOOGLE_AVAILABLE:
            try:
                self.engines['google'] = GoogleSearch()
                logger.info("Initialized Google search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize Google for title search: {e}")
        
        if BING_AVAILABLE:
            try:
                self.engines['bing'] = BingSearch()
                logger.info("Initialized Bing search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize Bing for title search: {e}")
        
        if YANDEX_AVAILABLE:
            try:
                self.engines['yandex'] = YandexSearch()
                logger.info("Initialized Yandex search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize Yandex for title search: {e}")
        
        if BRAVE_AVAILABLE:
            try:
                self.engines['brave'] = BraveSearch()
                logger.info("Initialized Brave search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize Brave for title search: {e}")
        
        if DUCKDUCKGO_AVAILABLE:
            try:
                self.engines['duckduckgo'] = DuckDuckGoSearch()
                logger.info("Initialized DuckDuckGo search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize DuckDuckGo for title search: {e}")
        
        if YEP_AVAILABLE:
            try:
                self.engines['yep'] = YepSearch()
                logger.info("Initialized Yep search for title search")
            except Exception as e:
                logger.warning(f"Could not initialize Yep for title search: {e}")

        # Majestic is handled separately (async API call)
        self.majestic_available = MAJESTIC_AVAILABLE
        if MAJESTIC_AVAILABLE:
            logger.info("Majestic SearchByKeyword available for title search")
    
    def parse_title_query(self, query: str) -> Tuple[str, str, str]:
        """Parse title operators from query"""
        # Check for intitle: operator
        intitle_match = re.search(r'intitle:([^\s]+)', query, re.IGNORECASE)
        if intitle_match:
            term = intitle_match.group(1)
            keywords = re.sub(r'intitle:[^\s]+\s*', '', query, flags=re.IGNORECASE).strip()
            return 'intitle', term, keywords
        
        # Check for allintitle: operator
        allintitle_match = re.search(r'allintitle:(.+)', query, re.IGNORECASE)
        if allintitle_match:
            term = allintitle_match.group(1).strip()
            return 'allintitle', term, ''
        
        # No title operator found
        return 'none', '', query
    
    def format_query_for_engine(self, operator: str, term: str, keywords: str, engine_name: str) -> str:
        """Format the query string for a specific engine"""
        if operator == 'none':
            return keywords
        
        engine_ops = self.ENGINE_OPERATORS.get(engine_name, {})
        
        if operator == 'intitle':
            engine_op = engine_ops.get('intitle', 'intitle:')
            formatted_query = f"{engine_op}{term}"
            if keywords:
                formatted_query += f" {keywords}"
            return formatted_query
        
        elif operator == 'allintitle':
            engine_op = engine_ops.get('allintitle', 'allintitle:')
            return f"{engine_op}{term}"
        
        return keywords
    
    def generate_search_variations(self, operator: str, term: str, keywords: str, engine_name: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 query variations"""
        variations = []
        
        # L1: Native Operator (High Precision)
        l1_query = self.format_query_for_engine(operator, term, keywords, engine_name)
        variations.append((l1_query, 'L1'))
        
        # L2: URL Expansion (Tricks - URL often matches title)
        if operator == 'intitle':
            # Convert intitle:term to inurl:term
            if ' ' in term:
                # Handle quoted terms
                l2_query = f'inurl:"{term}" {keywords}'.strip()
            else:
                l2_query = f'inurl:{term} {keywords}'.strip()
            variations.append((l2_query, 'L2'))
            
        # L3: Brute Force (Broad match + Strict Filtering)
        # Search for the term as an exact phrase anywhere, then filter for title later
        if ' ' in term:
            l3_query = f'"{term}" {keywords}'.strip()
        else:
            l3_query = f'{term} {keywords}'.strip()
        variations.append((l3_query, 'L3'))
        
        return variations

    async def search_title(self, query: str, max_results_per_engine: int = 50) -> Dict:
        """Search for title-specific queries across all engines using L1/L2/L3 strategies"""
        # Parse the title query
        operator, term, keywords = self.parse_title_query(query)
        
        if operator == 'none':
            print("No title operator detected in query")
            return {'error': 'No title operator found'}
        
        print(f"\nTitle search detected:")
        print(f"  Operator: {operator}")
        print(f"  Term: {term}")
        print(f"  Additional keywords: {keywords}")
        
        seen_urls = set()
        all_results = []
        stats_by_source = {}
        tasks = []
        
        # Create search tasks for each engine
        for engine_name, engine in self.engines.items():
            tasks.append(self._search_engine_with_variations(engine_name, engine, operator, term, keywords, max_results_per_engine))

        # Add Majestic SearchByKeyword (filters by ScoreInTitle > 0)
        if self.majestic_available:
            tasks.append(self._search_majestic_title(term, max_results_per_engine))

        # Gather results
        engine_outputs = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for output in engine_outputs:
            if isinstance(output, Exception):
                logger.error(f"Search task failed: {output}")
                continue
            
            engine_name, results_list = output
            
            if engine_name not in stats_by_source:
                stats_by_source[engine_name] = {'processed_results': 0, 'unique_added': 0, 'filtered_out': 0}
            
            processed = 0
            unique_added = 0
            filtered_out = 0
            
            for result in results_list:
                processed += 1
                url = result.get('url', '')
                strategy = result.get('strategy', 'L1')
                
                # L3 Filtering: Strict Title Check
                if strategy == 'L3':
                    title = result.get('title', '').lower()
                    term_lower = term.lower().replace('"', '')
                    if term_lower not in title:
                        filtered_out += 1
                        continue # Skip this result
                
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    result['source'] = engine_name
                    all_results.append(result)
                    unique_added += 1
            
            stats_by_source[engine_name]['processed_results'] += processed
            stats_by_source[engine_name]['unique_added'] += unique_added
            stats_by_source[engine_name]['filtered_out'] += filtered_out
        
        # Final output
        print("\n--- Title Search Summary ---")
        total_unique = len(all_results)
        print(f"Query: {query}")
        print(f"Operator: {operator}")
        print(f"Term: {term}")
        print(f"Total unique results: {total_unique}")
        print("\nResults per source:")
        for source, stats in stats_by_source.items():
            print(f"  - {source}: Processed {stats['processed_results']}, Added {stats['unique_added']} unique, Filtered {stats['filtered_out']} (L3)")
        print("----------------------------")
        
        # Sort results by relevance (title matches first)
        all_results.sort(key=lambda x: self._calculate_title_relevance(x, term), reverse=True)
        
        output_data = {
            'query': query,
            'operator': operator,
            'term': term,
            'keywords': keywords,
            'timestamp': datetime.now().isoformat(),
            'search_type': 'title',
            'total_unique_results': total_unique,
            'engine_stats': stats_by_source,
            'results': all_results
        }
        
        self.save_results(output_data)
        return output_data
    
    async def _search_engine_with_variations(self, engine_name: str, engine_instance, operator: str, term: str, keywords: str, max_results: int):
        """Run search on a specific engine instance iterating through L1/L2/L3 variations"""
        engine_results_list = []
        
        try:
            # Get variations
            variations = self.generate_search_variations(operator, term, keywords, engine_name)
            
            # Use the search method from our self-contained runners
            search_method = getattr(engine_instance, 'search', None)
            if not search_method or not callable(search_method):
                logger.warning(f"Engine {engine_name} has no suitable search method.")
                return engine_name, []
            
            # Distribute max_results among variations
            limit_per_var = max(10, max_results // len(variations))
            
            for query_var, strategy in variations:
                logger.info(f"{engine_name.title()} [{strategy}] Query: {query_var}")
                
                try:
                    partial_results = search_method(query_var, max_results=limit_per_var)
                    if partial_results:
                        for res in partial_results:
                            res['query_used'] = query_var
                            res['strategy'] = strategy # Mark for filtering
                            res['source'] = engine_name
                        engine_results_list.extend(partial_results)
                        logger.info(f"{engine_name.title()} [{strategy}]: Found {len(partial_results)} results")
                except Exception as e:
                    logger.warning(f"{engine_name.title()} [{strategy}] search error: {e}")
                    continue

            return engine_name, engine_results_list
        
        except Exception as e:
            logger.error(f"{engine_name.title()} search error: {e}")
            return engine_name, []

    async def _search_engine(self, engine_name: str, engine_instance, operator: str, term: str, keywords: str, max_results: int):
        """Legacy wrapper - deprecated in favor of _search_engine_with_variations"""
        return await self._search_engine_with_variations(engine_name, engine_instance, operator, term, keywords, max_results)

    async def _search_majestic_title(self, keyword: str, max_results: int) -> Tuple[str, List[Dict]]:
        """
        Search Majestic's index for pages with keyword in title.

        Majestic SearchByKeyword returns separate scores for Title/URL/Anchor.
        We filter to only return results where ScoreInTitle > 0.

        Args:
            keyword: The keyword to search for in titles
            max_results: Maximum results to return

        Returns:
            Tuple of (engine_name, results_list)
        """
        if not MAJESTIC_AVAILABLE:
            return 'majestic', []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    "app_api_key": MAJESTIC_API_KEY,
                    "cmd": "SearchByKeyword",
                    "Query": keyword,
                    "Scope": 2,  # Both historic and fresh
                    "MaxResults": min(max_results, 100),
                    "Highlight": 0,
                }

                response = await client.get(MAJESTIC_BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("Code") != "OK":
                    logger.warning(f"Majestic SearchByKeyword error: {data.get('ErrorMessage')}")
                    return 'majestic', []

                results = []
                items = data.get("DataTables", {}).get("Results", {}).get("Data", [])

                for item in items:
                    # Only include results where keyword matched in title
                    score_in_title = item.get("ScoreInTitle", 0)
                    if score_in_title <= 0:
                        continue

                    url = item.get("URL", "")
                    title = item.get("Title", "")

                    if url:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": f"Title match score: {score_in_title}",
                            "source": "majestic",
                            "strategy": "L1",  # Direct title match
                            "score_in_title": score_in_title,
                            "score_in_url": item.get("ScoreInURL", 0),
                            "score_in_anchor": item.get("ScoreInAnchor", 0),
                        })

                logger.info(f"Majestic title search: {len(results)} results with ScoreInTitle > 0")
                return 'majestic', results

        except httpx.TimeoutException:
            logger.warning(f"Majestic title search timeout for '{keyword}'")
            return 'majestic', []
        except Exception as e:
            logger.error(f"Majestic title search error: {e}")
            return 'majestic', []
    
    def _calculate_title_relevance(self, result: Dict, term: str) -> float:
        """Calculate relevance score based on title match"""
        score = 0.0
        title = result.get('title', '').lower()
        term_lower = term.lower()
        
        # Exact match in title
        if term_lower in title:
            score += 1.0
        
        # Partial match
        term_words = term_lower.split()
        title_words = title.split()
        
        matches = sum(1 for word in term_words if word in title_words)
        if len(term_words) > 0:
            score += (matches / len(term_words)) * 0.5
        
        return score
    
    def save_results(self, data: Dict):
        """Save title search results to a JSON file"""
        results_dir = "search_results"
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(c if c.isalnum() else "_" for c in data['query'])[:50]
        filename = f"title_search_{safe_query}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Saved title search results to {filepath}")
        except Exception as e:
            print(f"Error saving title search results to {filepath}: {e}")


def main():
    """Main entry point for title search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Title-specific search across multiple engines')
    parser.add_argument('query', help='Search query with title operators (intitle: or allintitle:)')
    parser.add_argument('-o', '--output', help='Output JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    async def run_search():
        searcher = TitleSearcher()
        
        results_data = await searcher.search_title(args.query)
        
        if 'error' in results_data:
            print(f"Error: {results_data['error']}")
            return
        
        if results_data.get('results'):
            print("\n--- Sample Results ---")
            for i, result in enumerate(results_data['results'][:10], 1):
                print(f"\n{i}. [{result.get('source', 'N/A')}] {result.get('title', 'No Title')}")
                print(f"   🔗 URL: {result.get('url', 'N/A')}")
                print(f"   📝 Query Used: {result.get('query_used', 'N/A')}")
                snippet = result.get('snippet', result.get('description', ''))
                if snippet:
                    snippet = snippet[:200] + '...' if len(snippet) > 200 else snippet
                    print(f"   📄 Snippet: {snippet}")
        else:
            print("No results found.")
        
        # Save to file if specified
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results_data, f, indent=2)
            print(f"\n💾 Results saved to: {args.output}")
    
    asyncio.run(run_search())


if __name__ == "__main__":
    main()