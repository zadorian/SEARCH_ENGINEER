#!/usr/bin/env python3
"""
Date Search Router - Handles date-based search operators across multiple engines
Supports: yyyy!, yyyy-yyyy!, <- yyyy!, yyyy ->!, month yyyy!, dd month yyyy!
"""

import re
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import calendar

# Filtering integration
try:
    from brute.scraper.phrase_matcher import PhraseMatcher
    from brute.filtering.core.filter_manager import FilterManager
    FILTERING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Filtering not available: {e}")
    FILTERING_AVAILABLE = False

# Streaming integration
try:
    from brute.infrastructure.base_streamer import SearchTypeEventEmitter
    STREAMING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Streaming not available: {e}")
    STREAMING_AVAILABLE = False
    # Fallback class
    class SearchTypeEventEmitter:
        def __init__(self, search_type=None): pass
        def enable_streaming(self, handler=None): pass
        def emit_search_result(self, result, engine=None): pass
        def emit_search_filtered_result(self, result, engine=None): pass
        def emit_engine_status(self, engine, status, results=0): pass
        def start_search(self, query, engines=None): pass
        def complete_search(self, summary=None): pass
        def mark_engine_complete(self, engine, results_count=0, success=True): pass
        def get_search_summary(self): return {}

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import search runners from self-contained modules
sys.path.insert(0, str(Path(__file__).parent.parent / 'engines'))

from exact_phrase_recall_runner_yep import YepScraper

# Wrapper for YepScraper to match the expected engine interface
class YepEngineWrapper:
    def __init__(self, scraper: YepScraper):
        self.scraper = scraper

    def search(self, query: str, max_results: int = 50) -> List[Dict]:
        return self.scraper.fetch_yep_results(query, num_results=max_results)

try:
    from exact_phrase_recall_runner_google import GoogleSearch
    from exact_phrase_recall_runner_bing import BingSearch  
    from exact_phrase_recall_runner_yandex import YandexSearch
    from exact_phrase_recall_runner_brave import BraveSearch
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo as DuckDuckGoSearch
    SEARCH_ENGINES_AVAILABLE = True
except ImportError as e:
    print(f"Error importing search engines: {e}")
    print("Make sure the runner files are in engines directory")
    SEARCH_ENGINES_AVAILABLE = False

logger = logging.getLogger(__name__)

class DateSearchRouter(SearchTypeEventEmitter):
    """Routes date searches to appropriate engines with correct syntax"""
    
    def __init__(self, enable_streaming: bool = False, event_handler: Optional[callable] = None):
        # Initialize streaming first
        super().__init__(search_type="date")
        
        self.engines = self._initialize_engines()
        
        # Set up streaming if requested
        if enable_streaming and event_handler:
            self.enable_streaming(event_handler)
        
        # Initialize filtering components
        if FILTERING_AVAILABLE:
            try:
                self.phrase_matcher = PhraseMatcher(max_distance=3)
                self.filter_manager = FilterManager()
                self.enable_exact_phrase_filter = True
                self.filtered_results = []
                logger.info("Filtering integration initialized for date search")
            except Exception as e:
                logger.warning(f"Could not initialize filtering: {e}")
                self.phrase_matcher = None
                self.filter_manager = None
                self.enable_exact_phrase_filter = False
                self.filtered_results = []
        else:
            self.phrase_matcher = None
            self.filter_manager = None
            self.enable_exact_phrase_filter = False
            self.filtered_results = []
        
    def _initialize_engines(self) -> Dict[str, Any]:
        """Initialize available search engines"""
        engines = {}
        
        if not SEARCH_ENGINES_AVAILABLE:
            logger.error("Search engines not available - import failed")
            return engines
        
        try:
            engines['google'] = GoogleSearch()
            logger.info("Initialized Google search")
        except Exception as e:
            logger.warning(f"Could not initialize Google: {e}")
            
        try:
            engines['bing'] = BingSearch()
            logger.info("Initialized Bing search")
        except Exception as e:
            logger.warning(f"Could not initialize Bing: {e}")
            
        try:
            engines['yandex'] = YandexSearch()
            logger.info("Initialized Yandex search")
        except Exception as e:
            logger.warning(f"Could not initialize Yandex: {e}")
            
        try:
            engines['brave'] = BraveSearch()
            logger.info("Initialized Brave search")
        except Exception as e:
            logger.warning(f"Could not initialize Brave: {e}")
            
        try:
            engines['duckduckgo'] = DuckDuckGoSearch(phrase="") # Initialize with empty phrase
            logger.info("Initialized DuckDuckGo search")
        except Exception as e:
            logger.warning(f"Could not initialize DuckDuckGo: {e}")
            
        try:
            yep_scraper_instance = YepScraper()
            engines['yep'] = YepEngineWrapper(yep_scraper_instance)
            logger.info("Initialized Yep search")
        except Exception as e:
            logger.warning(f"Could not initialize Yep: {e}")
            
        return engines
    
    def parse_date_query(self, query: str) -> Tuple[Dict[str, Any], str]:
        """Parse date operators from query"""
        # Remove trailing ! if present
        query = query.rstrip('!').strip()
        
        result = {
            'type': None,
            'year': None,
            'month': None,
            'day': None,
            'start_date': None,
            'end_date': None,
            'keywords': ''
        }
        
        # Extract the date pattern and remaining keywords
        query_lower = query.lower()
        
        # Year range patterns: "2020-2023"
        year_range_match = re.search(r'(\d{4})\s*-\s*(\d{4})', query)
        if year_range_match:
            start_year, end_year = year_range_match.groups()
            result['type'] = 'range'
            result['start_date'] = f"{start_year}-01-01"
            result['end_date'] = f"{end_year}-12-31"
            keywords = query[:year_range_match.start()] + query[year_range_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # Before year patterns: "<- 2022"
        before_match = re.search(r'<-\s*(\d{4})', query)
        if before_match:
            year = before_match.group(1)
            result['type'] = 'before'
            result['end_date'] = f"{year}-01-01"
            keywords = query[:before_match.start()] + query[before_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # After year patterns: "2023 ->"
        after_match = re.search(r'(\d{4})\s*->', query)
        if after_match:
            year = after_match.group(1)
            result['type'] = 'after'
            result['start_date'] = f"{year}-12-31"
            keywords = query[:after_match.start()] + query[after_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # Full date patterns: "dd month yyyy"
        full_date_match = re.search(r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})', query_lower)
        if full_date_match:
            day, month_name, year = full_date_match.groups()
            month_num = self._month_name_to_number(month_name)
            result['type'] = 'exact'
            result['year'] = year
            result['month'] = month_num
            result['day'] = int(day)
            # Create properly formatted date
            date_str = f"{year}-{month_num:02d}-{int(day):02d}"
            result['start_date'] = date_str
            result['end_date'] = date_str
            keywords = query[:full_date_match.start()] + query[full_date_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # Month year patterns: "month yyyy"
        month_year_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})', query_lower)
        if month_year_match:
            month_name, year = month_year_match.groups()
            month_num = self._month_name_to_number(month_name)
            result['type'] = 'month'
            result['year'] = year
            result['month'] = month_num
            # Get last day of month
            last_day = calendar.monthrange(int(year), month_num)[1]
            result['start_date'] = f"{year}-{month_num:02d}-01"
            result['end_date'] = f"{year}-{month_num:02d}-{last_day}"
            keywords = query[:month_year_match.start()] + query[month_year_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # Year only patterns: "yyyy"
        year_only_match = re.search(r'\b(\d{4})\b', query)
        if year_only_match:
            year = year_only_match.group(1)
            result['type'] = 'year'
            result['year'] = year
            result['start_date'] = f"{year}-01-01"
            result['end_date'] = f"{year}-12-31"
            keywords = query[:year_only_match.start()] + query[year_only_match.end():]
            result['keywords'] = keywords.strip()
            return result, keywords.strip()
        
        # No date pattern found
        result['keywords'] = query
        return result, query
    
    def _filter_results(self, results: List[Dict[str, Any]], original_query: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Filter results based on exact phrase matching and return both filtered and non-matching."""
        if not self.enable_exact_phrase_filter or not self.phrase_matcher:
            return results, []
        
        # Extract exact phrases from the original query
        phrases = self.phrase_matcher.extract_phrases(original_query)
        if not phrases:
            return results, []
        
        filtered_results = []
        non_matching_results = []
        
        for result in results:
            title = result.get('title', '')
            snippet = result.get('snippet', result.get('description', ''))
            
            # Check if any exact phrase is found in title or snippet
            phrase_found = False
            for phrase in phrases:
                if self.phrase_matcher.check_exact_match(phrase, title) or \
                   self.phrase_matcher.check_exact_match(phrase, snippet) or \
                   self.phrase_matcher.check_proximity_match(phrase, title) or \
                   self.phrase_matcher.check_proximity_match(phrase, snippet):
                    phrase_found = True
                    break
            
            if phrase_found:
                filtered_results.append(result)
            else:
                # Mark as filtered for the "Filtered Out" tab
                filtered_result = result.copy()
                filtered_result['filter_reason'] = f"Exact phrase not found: {', '.join(phrases)}"
                filtered_result['filter_type'] = 'exact_phrase'
                non_matching_results.append(filtered_result)
        
        return filtered_results, non_matching_results
    
    def _month_name_to_number(self, month_name: str) -> int:
        """Convert month name to number"""
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        return months.get(month_name.lower(), 1)
    
    def translate_to_engine_syntax(self, date_info: Dict[str, Any], keywords: str, engine: str) -> str:
        """Translate date query to engine-specific syntax"""
        
        if engine == 'google':
            # Google uses before: and after: operators
            if date_info['type'] == 'before':
                return f'{keywords} before:{date_info["end_date"]}'
            elif date_info['type'] == 'after':
                return f'{keywords} after:{date_info["start_date"]}'
            elif date_info['type'] in ['range', 'year', 'month', 'exact']:
                # For ranges, use both operators
                return f'{keywords} after:{date_info["start_date"]} before:{date_info["end_date"]}'
        
        elif engine == 'bing':
            # Bing uses date range syntax
            if date_info['type'] == 'before':
                return f'{keywords} date:<{date_info["end_date"].replace("-", "")}'
            elif date_info['type'] == 'after':
                return f'{keywords} date:>{date_info["start_date"].replace("-", "")}'
            elif date_info['type'] in ['range', 'year', 'month', 'exact']:
                start = date_info["start_date"].replace("-", "")
                end = date_info["end_date"].replace("-", "")
                return f'{keywords} date:{start}..{end}'
        
        elif engine == 'yandex':
            # Yandex uses date:> and date:< operators
            if date_info['type'] == 'before':
                return f'{keywords} date:<{date_info["end_date"].replace("-", "")}'
            elif date_info['type'] == 'after':
                return f'{keywords} date:>{date_info["start_date"].replace("-", "")}'
            elif date_info['type'] in ['range', 'year', 'month', 'exact']:
                start = date_info["start_date"].replace("-", "")
                end = date_info["end_date"].replace("-", "")
                return f'{keywords} date:{start}..{end}'
        
        elif engine == 'brave':
            # Brave might use similar syntax to Google
            if date_info['type'] == 'before':
                return f'{keywords} before:{date_info["end_date"]}'
            elif date_info['type'] == 'after':
                return f'{keywords} after:{date_info["start_date"]}'
            elif date_info['type'] in ['range', 'year', 'month', 'exact']:
                return f'{keywords} after:{date_info["start_date"]} before:{date_info["end_date"]}'
        
        # Default: just return keywords if engine doesn't support date filtering
        return keywords
    
    def _generate_date_variations(self, date_info: Dict[str, Any], keywords: str, engine: str) -> List[Tuple[str, str]]:
        """Generate L1/L2/L3 date query variations"""
        variations = []
        
        # L1: Native Engine Syntax (High Precision)
        l1_query = self.translate_to_engine_syntax(date_info, keywords, engine)
        if l1_query:
            variations.append((l1_query, 'L1'))
            
        # L2: Keyword & URL Tricks (Expansion)
        if date_info['type'] in ['exact', 'month', 'year']:
            year = date_info.get('year')
            month = date_info.get('month')
            
            if year:
                # "Month Year" (e.g., "January 2024")
                if month:
                    month_name = calendar.month_name[month]
                    variations.append((f'{keywords} "{month_name} {year}"', 'L2'))
                    variations.append((f'{keywords} "{year}-{month:02d}"', 'L2'))
                    
                    # inurl:2024/01
                    if engine in ['google', 'bing', 'brave', 'duckduckgo', 'yandex']:
                        variations.append((f'{keywords} inurl:{year}/{month:02d}', 'L2'))
                        variations.append((f'{keywords} inurl:{year}-{month:02d}', 'L2'))
                
                # "YYYY" in URL (e.g., inurl:2024) - Broad but effective
                elif engine in ['google', 'bing', 'brave', 'duckduckgo', 'yandex']:
                    variations.append((f'{keywords} inurl:{year}', 'L2'))

        # L3: Brute Force (Broad Match + Filtering)
        # Just append the year/date as a keyword
        if date_info['type'] == 'year' and date_info.get('year'):
            variations.append((f'{keywords} "{date_info["year"]}"', 'L3'))
            
        return variations

    def _verify_date_relevance(self, result: Dict, date_info: Dict) -> bool:
        """Check if L2/L3 results actually contain the relevant date strings"""
        text = (result.get('title', '') + ' ' + result.get('snippet', '') + ' ' + result.get('url', '')).lower()
        
        year = str(date_info.get('year', ''))
        if not year or year not in text:
            return False
            
        if date_info.get('month'):
            month_num = f"{date_info['month']:02d}"
            month_name = calendar.month_name[date_info['month']].lower()
            if month_num not in text and month_name not in text:
                return False
                
        return True

    def search(self, query: str, output_file: str = None) -> Dict[str, Any]:
        """Execute date search across multiple engines with L1/L2/L3 strategies"""
        # Start streaming
        engines_list = list(self.engines.keys())
        self.start_search(query, engines_list)
        
        # Parse the date query
        date_info, keywords = self.parse_date_query(query)
        
        if not date_info['type']:
            error_msg = 'No date pattern found'
            print("No date pattern detected in query")
            self.complete_search({'error': error_msg})
            return {'error': error_msg}
        
        print(f"\nDate search detected:")
        print(f"  Type: {date_info['type']}")
        print(f"  Date range: {date_info['start_date']} to {date_info['end_date']}")
        print(f"  Keywords: {keywords}")
        
        results = {
            'query': query,
            'date_info': date_info,
            'keywords': keywords,
            'engines': {},
            'total_results': 0,
            'unique_urls': set()
        }
        
        # Search with each engine
        for engine_name, engine in self.engines.items():
            print(f"\nSearching with {engine_name}...")
            
            # Generate variations
            variations = self._generate_date_variations(date_info, keywords, engine_name)
            engine_results = []
            
            try:
                # Distribute effort among variations
                limit_per_var = max(10, 50 // len(variations)) if variations else 50
                
                for query_var, strategy in variations:
                    print(f"  [{strategy}] Query: {query_var}")
                    
                    try:
                        partial_results = engine.search(query_var, max_results=limit_per_var)
                        
                        # Filter L2/L3 results strictly
                        if strategy in ['L2', 'L3']:
                            partial_results = [r for r in partial_results if self._verify_date_relevance(r, date_info)]
                        
                        engine_results.extend(partial_results)
                        print(f"    Found {len(partial_results)} results")
                        
                    except Exception as e:
                        logger.warning(f"Error in variation {query_var}: {e}")
                        continue

                # Apply filtering if enabled
                if self.enable_exact_phrase_filter and engine_results:
                    filtered_results, non_matching = self._filter_results(engine_results, query)
                    
                    # Emit filtered results as streaming events
                    for filtered_result in non_matching:
                        self.emit_search_filtered_result(filtered_result, engine_name)
                    
                    # Store filtered results for "Filtered Out" tab
                    self.filtered_results.extend(non_matching)
                    
                    # Use filtered results for processing
                    engine_results = filtered_results
                    
                    if non_matching:
                        logger.info(f"Filtered out {len(non_matching)} results from {engine_name} that didn't match exact phrases")
                
                # Store results
                results['engines'][engine_name] = {
                    'query': variations[0][0] if variations else '', # Log primary query
                    'results': engine_results,
                    'count': len(engine_results)
                }
                
                # Track unique URLs and emit results
                for result in engine_results:
                    if 'url' in result:
                        results['unique_urls'].add(result['url'])
                    # Emit result as streaming event
                    self.emit_search_result(result, engine_name)
                
                results['total_results'] += len(engine_results)
                
                # Mark engine as completed
                self.mark_engine_complete(engine_name, len(engine_results), success=True)
                
            except Exception as e:
                logger.error(f"Error searching with {engine_name}: {e}")
                results['engines'][engine_name] = {
                    'error': str(e),
                    'count': 0
                }
                # Mark engine as failed
                self.mark_engine_complete(engine_name, 0, success=False)
        
        # Convert set to list for JSON serialization
        results['unique_urls'] = list(results['unique_urls'])
        results['unique_count'] = len(results['unique_urls'])
        
        # Add filtering statistics
        if self.enable_exact_phrase_filter:
            results['filtered_count'] = len(self.filtered_results)
            results['filtered_results'] = self.filtered_results
            if self.filtered_results:
                print(f"\nFiltered out: {len(self.filtered_results)} results ({len(self.filtered_results)/(results['total_results']+len(self.filtered_results) if results['total_results'] else 1)*100:.1f}%)")
        
        # Save results if output file specified
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {output_file}")
        
        print(f"\nTotal results: {results['total_results']}")
        print(f"Unique URLs: {results['unique_count']}")
        
        # Complete streaming with summary
        summary = {
            'total_results': results['total_results'],
            'unique_results': results['unique_count'],
            'filtered_count': len(self.filtered_results),
            'date_info': date_info
        }
        self.complete_search(summary)
        
        return results


def main():
    """Main entry point for date search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Date-based search across multiple engines')
    parser.add_argument('query', help='Search query with date operators')
    parser.add_argument('-o', '--output', help='Output JSON file')
    
    args = parser.parse_args()
    
    router = DateSearchRouter()
    router.search(args.query, args.output)


if __name__ == '__main__':
    main()