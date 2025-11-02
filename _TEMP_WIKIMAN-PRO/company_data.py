#!/usr/bin/env python3
"""
Company Data Search with DuckDuckGo Bangs and Location/Language Targeting
Enhanced with country/language indexing for targeted company data searches
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
import re

# Add project root to path (local WIKIMAN-PRO directory)
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the enhanced company data bangs with location/language indexing
from Search_Types.company_data_bangs import (
    COMPANY_DATA_BANGS_DATABASE, CompanyDataBang,
    get_company_bangs_by_country, get_company_bangs_by_language, get_company_bangs_by_category,
    get_company_bangs_by_data_type, get_company_bangs_for_location_language,
    get_company_bangs_by_regional_focus, ALL_COMPANY_DATA_BANGS, PRIORITY_COMPANY_DATA_BANGS,
    AVAILABLE_COMPANY_COUNTRIES, AVAILABLE_COMPANY_LANGUAGES, AVAILABLE_COMPANY_CATEGORIES,
    AVAILABLE_COMPANY_DATA_TYPES, get_company_data_bangs_stats,
    CATEGORY_DESCRIPTIONS, DATA_TYPE_DESCRIPTIONS
)

# Import search engines (local copy in WIKIMAN-PRO)
sys.path.insert(0, str(PROJECT_ROOT / 'Search_Engines'))
try:
    from exact_phrase_recall_runner_duckduck import MaxExactDuckDuckGo
    DUCKDUCKGO_AVAILABLE = True
except ImportError as e:
    DUCKDUCKGO_AVAILABLE = False
    print(f"Warning: DuckDuckGo search not available: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CompanyDataSearcher:
    """Enhanced company data search with location/language targeting using DuckDuckGo bangs"""
    
    def __init__(self):
        """Initialize the company data searcher with DuckDuckGo engine"""
        self.ddg_engine = None
        if DUCKDUCKGO_AVAILABLE:
            try:
                self.ddg_engine = MaxExactDuckDuckGo()
                logger.info("Initialized DuckDuckGo engine for company data search")
            except Exception as e:
                logger.error(f"Failed to initialize DuckDuckGo engine: {e}")
                
    def get_targeted_company_bangs(self, country_code: Optional[str] = None, 
                                  language_code: Optional[str] = None,
                                  category: Optional[str] = None,
                                  data_type: Optional[str] = None,
                                  regional_focus: Optional[str] = None,
                                  use_priority: bool = False) -> List[CompanyDataBang]:
        """
        Get company data bangs targeted by location, language, category, data type, or regional focus
        
        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., 'US', 'UK', 'DE')
            language_code: ISO 639-1 language code (e.g., 'en', 'de', 'fr')
            category: Data category (e.g., 'financial', 'regulatory', 'business')
            data_type: Specific data type (e.g., 'filings', 'financials', 'profiles')
            regional_focus: Regional focus (e.g., 'us', 'europe', 'global')
            use_priority: Whether to use only priority company data bangs
            
        Returns:
            List of CompanyDataBang objects matching the criteria
        """
        if use_priority:
            # Filter priority bangs by criteria
            priority_bang_names = set(PRIORITY_COMPANY_DATA_BANGS)
            filtered_bangs = [bang for bang in COMPANY_DATA_BANGS_DATABASE if bang.bang in priority_bang_names]
        else:
            filtered_bangs = COMPANY_DATA_BANGS_DATABASE.copy()
        
        # Apply filters
        if country_code:
            filtered_bangs = [bang for bang in filtered_bangs if bang.country == country_code.upper()]
        
        if language_code:
            filtered_bangs = [bang for bang in filtered_bangs if bang.language == language_code.lower()]
            
        if category:
            filtered_bangs = [bang for bang in filtered_bangs if bang.category == category.lower()]
            
        if data_type:
            filtered_bangs = [bang for bang in filtered_bangs if bang.data_type == data_type.lower()]
            
        if regional_focus:
            filtered_bangs = [bang for bang in filtered_bangs if bang.regional_focus == regional_focus.lower()]
        
        return filtered_bangs
    
    def get_bangs_by_company_type(self, company_type: str) -> List[CompanyDataBang]:
        """Get bangs suitable for specific company types (public, private, startup, etc.)"""
        type_mapping = {
            'public': ['financial', 'regulatory', 'esg'],
            'private': ['business', 'credit_rating', 'regulatory'],
            'startup': ['startup', 'business', 'employment'],
            'multinational': ['financial', 'esg', 'regulatory'],
            'small_business': ['business', 'employment', 'credit_rating'],
            'tech': ['startup', 'business', 'employment', 'intellectual_property'],
            'financial': ['financial', 'regulatory', 'credit_rating'],
            'manufacturing': ['business', 'esg', 'regulatory'],
            'retail': ['business', 'employment', 'esg']
        }
        
        relevant_categories = type_mapping.get(company_type.lower(), ['business'])
        result = []
        for category in relevant_categories:
            result.extend(get_company_bangs_by_category(category))
        
        # Remove duplicates
        seen = set()
        unique_result = []
        for bang in result:
            if bang.bang not in seen:
                seen.add(bang.bang)
                unique_result.append(bang)
        
        return unique_result
    
    def get_bangs_by_research_purpose(self, purpose: str) -> List[CompanyDataBang]:
        """Get bangs suitable for specific research purposes"""
        purpose_mapping = {
            'due_diligence': ['regulatory', 'financial', 'credit_rating', 'business'],
            'investment_research': ['financial', 'esg', 'credit_rating', 'business'],
            'competitive_intelligence': ['business', 'web_analytics', 'technology', 'employment'],
            'risk_assessment': ['credit_rating', 'regulatory', 'financial', 'security'],
            'compliance': ['regulatory', 'esg', 'government', 'intellectual_property'],
            'market_research': ['business', 'statistics', 'economic', 'web_analytics'],
            'recruitment': ['employment', 'business', 'professional', 'startup'],
            'sales_prospecting': ['business', 'employment', 'professional', 'technology'],
            'academic_research': ['research', 'statistics', 'economic', 'government'],
            'journalism': ['business', 'regulatory', 'financial', 'investigative'],
            'cybersecurity': ['security', 'technology', 'regulatory', 'business']
        }
        
        relevant_categories = purpose_mapping.get(purpose.lower(), ['business'])
        result = []
        for category in relevant_categories:
            result.extend(get_company_bangs_by_category(category))
        
        # Remove duplicates
        seen = set()
        unique_result = []
        for bang in result:
            if bang.bang not in seen:
                seen.add(bang.bang)
                unique_result.append(bang)
        
        return unique_result
    
    async def search_company_data_bangs(self, query: str, 
                                       country_code: Optional[str] = None,
                                       language_code: Optional[str] = None,
                                       category: Optional[str] = None,
                                       data_type: Optional[str] = None,
                                       regional_focus: Optional[str] = None,
                                       company_type: Optional[str] = None,
                                       research_purpose: Optional[str] = None,
                                       use_priority: bool = False,
                                       max_results_per_bang: int = 10,
                                       max_bangs: int = 50) -> Dict[str, Any]:
        """
        Search company data using targeted DuckDuckGo bangs with location/language filtering
        
        Args:
            query: Search query (company name, industry, etc.)
            country_code: Target country (ISO 3166-1 alpha-2)
            language_code: Target language (ISO 639-1)
            category: Data category filter
            data_type: Specific data type filter
            regional_focus: Regional focus filter
            company_type: Type of company (public, private, startup, etc.)
            research_purpose: Purpose of research (due_diligence, investment_research, etc.)
            use_priority: Use only priority company data bangs
            max_results_per_bang: Maximum results per bang
            max_bangs: Maximum number of bangs to use
            
        Returns:
            Dictionary with search results and metadata
        """
        if not self.ddg_engine:
            return {
                'error': 'DuckDuckGo engine not available',
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'total_results': 0,
                'results': []
            }
        
        # Get targeted company data bangs
        targeted_bangs = self.get_targeted_company_bangs(
            country_code=country_code,
            language_code=language_code,
            category=category,
            data_type=data_type,
            regional_focus=regional_focus,
            use_priority=use_priority
        )
        
        # Apply company type filter if specified
        if company_type:
            type_bangs = self.get_bangs_by_company_type(company_type)
            type_bang_names = set(bang.bang for bang in type_bangs)
            targeted_bangs = [bang for bang in targeted_bangs if bang.bang in type_bang_names]
        
        # Apply research purpose filter if specified
        if research_purpose:
            purpose_bangs = self.get_bangs_by_research_purpose(research_purpose)
            purpose_bang_names = set(bang.bang for bang in purpose_bangs)
            targeted_bangs = [bang for bang in targeted_bangs if bang.bang in purpose_bang_names]
        
        if not targeted_bangs:
            logger.warning(f"No company data bangs found for criteria")
            # Fallback to priority bangs if no targeted bangs found
            targeted_bangs = self.get_targeted_company_bangs(use_priority=True)
        
        # Limit number of bangs
        if len(targeted_bangs) > max_bangs:
            targeted_bangs = targeted_bangs[:max_bangs]
            logger.info(f"Limited to {max_bangs} company data bangs")
        
        logger.info(f"Using {len(targeted_bangs)} company data bangs for query: '{query}'")
        
        # Create search tasks for each bang
        search_tasks = []
        for company_bang in targeted_bangs:
            bang_query = f"!{company_bang.bang} {query}"
            task = self._search_single_bang(bang_query, company_bang, max_results_per_bang)
            search_tasks.append(task)
        
        # Execute searches in parallel
        logger.info(f"Executing {len(search_tasks)} parallel bang searches")
        bang_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Process results
        all_results = []
        bang_stats = {}
        successful_bangs = 0
        failed_bangs = 0
        
        for i, result in enumerate(bang_results):
            company_bang = targeted_bangs[i]
            
            if isinstance(result, Exception):
                logger.error(f"Bang '{company_bang.bang}' failed: {result}")
                bang_stats[company_bang.bang] = {
                    'name': company_bang.name,
                    'country': company_bang.country,
                    'language': company_bang.language,
                    'category': company_bang.category,
                    'data_type': company_bang.data_type,
                    'status': 'failed',
                    'error': str(result),
                    'results_count': 0
                }
                failed_bangs += 1
            else:
                successful_bangs += 1
                results_count = len(result)
                bang_stats[company_bang.bang] = {
                    'name': company_bang.name,
                    'country': company_bang.country,
                    'language': company_bang.language,
                    'category': company_bang.category,
                    'data_type': company_bang.data_type,
                    'regional_focus': company_bang.regional_focus,
                    'status': 'success',
                    'results_count': results_count
                }
                
                # Add metadata to each result
                for res in result:
                    res['source_bang'] = company_bang.bang
                    res['source_name'] = company_bang.name
                    res['source_country'] = company_bang.country
                    res['source_language'] = company_bang.language
                    res['source_category'] = company_bang.category
                    res['source_data_type'] = company_bang.data_type
                    res['source_regional_focus'] = company_bang.regional_focus
                    res['source_domain'] = company_bang.domain
                    all_results.append(res)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # Sort results by relevance and data type priority
        def result_priority(result):
            # Priority order for data types
            priority_order = {
                'filings': 1, 'financials': 2, 'analysis': 3, 'profiles': 4,
                'registry': 5, 'ratings': 6, 'market_data': 7, 'leads': 8
            }
            data_type_priority = priority_order.get(result.get('source_data_type', ''), 999)
            return (data_type_priority, result.get('rank', 999))
        
        unique_results.sort(key=result_priority)
        
        # Prepare summary statistics
        category_stats = {}
        data_type_stats = {}
        country_stats = {}
        language_stats = {}
        
        for bang in targeted_bangs:
            # Category stats
            if bang.category not in category_stats:
                category_stats[bang.category] = {'count': 0, 'results': 0}
            category_stats[bang.category]['count'] += 1
            category_stats[bang.category]['results'] += bang_stats.get(bang.bang, {}).get('results_count', 0)
            
            # Data type stats
            if bang.data_type not in data_type_stats:
                data_type_stats[bang.data_type] = {'count': 0, 'results': 0}
            data_type_stats[bang.data_type]['count'] += 1
            data_type_stats[bang.data_type]['results'] += bang_stats.get(bang.bang, {}).get('results_count', 0)
            
            # Country stats
            if bang.country not in country_stats:
                country_stats[bang.country] = {'count': 0, 'results': 0}
            country_stats[bang.country]['count'] += 1
            country_stats[bang.country]['results'] += bang_stats.get(bang.bang, {}).get('results_count', 0)
            
            # Language stats
            if bang.language not in language_stats:
                language_stats[bang.language] = {'count': 0, 'results': 0}
            language_stats[bang.language]['count'] += 1
            language_stats[bang.language]['results'] += bang_stats.get(bang.bang, {}).get('results_count', 0)
        
        return {
            'query': query,
            'filters': {
                'country_code': country_code,
                'language_code': language_code,
                'category': category,
                'data_type': data_type,
                'regional_focus': regional_focus,
                'company_type': company_type,
                'research_purpose': research_purpose,
                'use_priority': use_priority
            },
            'timestamp': datetime.now().isoformat(),
            'total_results': len(unique_results),
            'unique_results': len(unique_results),
            'duplicate_results_removed': len(all_results) - len(unique_results),
            'bangs_used': len(targeted_bangs),
            'successful_bangs': successful_bangs,
            'failed_bangs': failed_bangs,
            'statistics': {
                'by_category': category_stats,
                'by_data_type': data_type_stats,
                'by_country': country_stats,
                'by_language': language_stats
            },
            'bang_details': bang_stats,
            'results': unique_results
        }
    
    async def _search_single_bang(self, bang_query: str, company_bang: CompanyDataBang, max_results: int) -> List[Dict]:
        """Execute a single bang search"""
        try:
            results = await asyncio.to_thread(
                self.ddg_engine.search,
                bang_query,
                max_results=max_results
            )
            return results if results else []
        except Exception as e:
            logger.error(f"Error searching bang '{company_bang.bang}': {e}")
            raise e
    
    def get_available_filters(self) -> Dict[str, List[str]]:
        """Get available filter options"""
        return {
            'countries': AVAILABLE_COMPANY_COUNTRIES,
            'languages': AVAILABLE_COMPANY_LANGUAGES,
            'categories': AVAILABLE_COMPANY_CATEGORIES,
            'data_types': AVAILABLE_COMPANY_DATA_TYPES,
            'category_descriptions': CATEGORY_DESCRIPTIONS,
            'data_type_descriptions': DATA_TYPE_DESCRIPTIONS,
            'company_types': ['public', 'private', 'startup', 'multinational', 'small_business', 'tech', 'financial', 'manufacturing', 'retail'],
            'research_purposes': ['due_diligence', 'investment_research', 'competitive_intelligence', 'risk_assessment', 'compliance', 'market_research', 'recruitment', 'sales_prospecting', 'academic_research', 'journalism', 'cybersecurity']
        }
    
    def get_company_data_bangs_info(self) -> Dict[str, Any]:
        """Get information about available company data bangs"""
        return get_company_data_bangs_stats()

# Convenience functions for direct usage
async def search_company_data_by_country(query: str, country_code: str, 
                                        max_results_per_bang: int = 10,
                                        max_bangs: int = 30) -> Dict[str, Any]:
    """Search company data targeted to a specific country"""
    searcher = CompanyDataSearcher()
    return await searcher.search_company_data_bangs(
        query=query,
        country_code=country_code,
        max_results_per_bang=max_results_per_bang,
        max_bangs=max_bangs
    )

async def search_company_data_by_type(query: str, company_type: str,
                                     max_results_per_bang: int = 10,
                                     max_bangs: int = 30) -> Dict[str, Any]:
    """Search company data for a specific company type"""
    searcher = CompanyDataSearcher()
    return await searcher.search_company_data_bangs(
        query=query,
        company_type=company_type,
        max_results_per_bang=max_results_per_bang,
        max_bangs=max_bangs
    )

async def search_company_data_for_purpose(query: str, research_purpose: str,
                                         max_results_per_bang: int = 10,
                                         max_bangs: int = 30) -> Dict[str, Any]:
    """Search company data for a specific research purpose"""
    searcher = CompanyDataSearcher()
    return await searcher.search_company_data_bangs(
        query=query,
        research_purpose=research_purpose,
        max_results_per_bang=max_results_per_bang,
        max_bangs=max_bangs
    )

async def search_priority_company_data(query: str, max_results_per_bang: int = 15,
                                      max_bangs: int = 20) -> Dict[str, Any]:
    """Search using only priority company data bangs"""
    searcher = CompanyDataSearcher()
    return await searcher.search_company_data_bangs(
        query=query,
        use_priority=True,
        max_results_per_bang=max_results_per_bang,
        max_bangs=max_bangs
    )

# Command-line interface
async def main():
    """Command-line interface for company data search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Company Data Search with Location/Language Targeting')
    parser.add_argument('query', help='Search query (company name, industry, etc.)')
    parser.add_argument('--country', '-c', help='Country code (e.g., US, UK, DE)')
    parser.add_argument('--language', '-l', help='Language code (e.g., en, de, fr)')
    parser.add_argument('--category', '-cat', help='Data category (e.g., financial, regulatory, business)')
    parser.add_argument('--data-type', '-dt', help='Data type (e.g., filings, financials, profiles)')
    parser.add_argument('--regional-focus', '-rf', help='Regional focus (e.g., us, europe, global)')
    parser.add_argument('--company-type', '-ct', help='Company type (e.g., public, private, startup)')
    parser.add_argument('--research-purpose', '-rp', help='Research purpose (e.g., due_diligence, investment_research)')
    parser.add_argument('--priority', '-p', action='store_true', help='Use only priority company data bangs')
    parser.add_argument('--max-results', '-mr', type=int, default=10, help='Max results per bang')
    parser.add_argument('--max-bangs', '-mb', type=int, default=30, help='Max number of bangs to use')
    parser.add_argument('--list-filters', action='store_true', help='List available filter options')
    parser.add_argument('--stats', action='store_true', help='Show company data bangs statistics')
    
    args = parser.parse_args()
    
    searcher = CompanyDataSearcher()
    
    if args.list_filters:
        filters = searcher.get_available_filters()
        print("Available Filters:")
        print(f"Countries ({len(filters['countries'])}): {', '.join(filters['countries'])}")
        print(f"Languages ({len(filters['languages'])}): {', '.join(filters['languages'])}")
        print(f"Categories ({len(filters['categories'])}): {', '.join(filters['categories'])}")
        print(f"Data Types ({len(filters['data_types'])}): {', '.join(filters['data_types'])}")
        print(f"Company Types: {', '.join(filters['company_types'])}")
        print(f"Research Purposes: {', '.join(filters['research_purposes'])}")
        return
    
    if args.stats:
        stats = searcher.get_company_data_bangs_info()
        print("Company Data Bangs Statistics:")
        print(f"Total bangs: {stats['total_bangs']}")
        print(f"Countries covered: {stats['countries_covered']}")
        print(f"Languages covered: {stats['languages_covered']}")
        print(f"Categories covered: {stats['categories_covered']}")
        print(f"Data types covered: {stats['data_types_covered']}")
        return
    
    # Perform search
    results = await searcher.search_company_data_bangs(
        query=args.query,
        country_code=args.country,
        language_code=args.language,
        category=args.category,
        data_type=args.data_type,
        regional_focus=args.regional_focus,
        company_type=args.company_type,
        research_purpose=args.research_purpose,
        use_priority=args.priority,
        max_results_per_bang=args.max_results,
        max_bangs=args.max_bangs
    )
    
    # Display results
    print(f"\nCompany Data Search Results for: '{args.query}'")
    print(f"Filters: Country={args.country}, Language={args.language}, Category={args.category}")
    print(f"Data Type={args.data_type}, Company Type={args.company_type}, Purpose={args.research_purpose}")
    print(f"Total results: {results['total_results']}")
    print(f"Bangs used: {results['bangs_used']} (successful: {results['successful_bangs']}, failed: {results['failed_bangs']})")
    print(f"Duplicates removed: {results['duplicate_results_removed']}")
    
    if results['results']:
        print("\nTop Results:")
        for i, result in enumerate(results['results'][:20], 1):
            print(f"{i}. {result.get('title', 'No title')}")
            print(f"   Source: {result.get('source_name', 'Unknown')} ({result.get('source_country', 'Unknown')})")
            print(f"   Category: {result.get('source_category', 'Unknown')}, Data Type: {result.get('source_data_type', 'Unknown')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            if result.get('snippet'):
                print(f"   Snippet: {result['snippet'][:100]}...")
            print()
    
    # Show statistics
    if results['statistics']:
        print("\nStatistics:")
        if results['statistics']['by_category']:
            print("By Category:")
            for cat, stats in results['statistics']['by_category'].items():
                print(f"  {cat}: {stats['count']} bangs, {stats['results']} results")
        
        if results['statistics']['by_data_type']:
            print("By Data Type:")
            for dt, stats in results['statistics']['by_data_type'].items():
                print(f"  {dt}: {stats['count']} bangs, {stats['results']} results")

if __name__ == "__main__":
    asyncio.run(main()) 