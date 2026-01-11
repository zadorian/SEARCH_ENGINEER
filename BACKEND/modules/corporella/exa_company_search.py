#!/usr/bin/env python3
"""
Exa Company Search Adapter for Corporate Search v3.2
Provides neural search, keyword search, and news monitoring for company intelligence
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from exa_py import Exa
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ExaCompanySearch:
    """
    Exa integration for corporate intelligence gathering.
    Implements multi-strategy search approach for comprehensive company data.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Exa client with API key."""
        self.api_key = api_key or os.environ.get('EXA_API_KEY')
        if not self.api_key:
            raise ValueError("EXA_API_KEY not found in environment or parameters")
        
        self.exa = Exa(self.api_key)
        self.logger = logging.getLogger(__name__)
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def search_company(self, company_name: str, max_results: int = 50) -> Dict[str, Any]:
        """
        Multi-strategy Exa search for company information.
        
        Args:
            company_name: Name of the company to search
            max_results: Maximum results per search type
            
        Returns:
            Dictionary containing neural_results, exact_matches, news, and domain_matches
        """
        self.logger.info(f"Starting Exa search for company: {company_name}")
        
        # Run searches in parallel for better performance
        loop = asyncio.get_event_loop()
        
        tasks = [
            loop.run_in_executor(self.executor, self._neural_search, company_name, max_results),
            loop.run_in_executor(self.executor, self._exact_search, f'"{company_name}"', max_results),
            loop.run_in_executor(self.executor, self._news_search, company_name, 90, max_results),
            loop.run_in_executor(self.executor, self._domain_search, company_name, max_results)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results and exceptions
        search_results = {
            'neural_results': results[0] if not isinstance(results[0], Exception) else [],
            'exact_matches': results[1] if not isinstance(results[1], Exception) else [],
            'news': results[2] if not isinstance(results[2], Exception) else [],
            'domain_matches': results[3] if not isinstance(results[3], Exception) else []
        }
        
        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                search_type = ['neural', 'exact', 'news', 'domain'][i]
                self.logger.error(f"Error in {search_type} search: {str(result)}")
        
        # Consolidate and deduplicate results
        consolidated = self._consolidate_exa_results(search_results, company_name)
        
        return consolidated
    
    def _neural_search(self, company_name: str, max_results: int = 50) -> List[Dict]:
        """
        Neural search for company intelligence using Exa's AI capabilities.
        """
        try:
            search_params = {
                "type": "neural",
                "use_autoprompt": True,
                "num_results": max_results,
                "text": True,
                "highlights": {"num_sentences": 5, "highlights_per_url": 3}
            }
            
            # Enhanced query for company intelligence
            query = f"{company_name} company business operations revenue ownership management"
            
            response = self.exa.search_and_contents(query, **search_params)
            
            results = []
            for result in response.results:
                results.append({
                    "url": result.url,
                    "title": getattr(result, 'title', 'No title'),
                    "score": getattr(result, 'score', 0),
                    "highlights": getattr(result, 'highlights', []),
                    "text_snippet": self._extract_snippet(result),
                    "search_type": "neural",
                    "relevance": "high" if getattr(result, 'score', 0) > 0.8 else "medium"
                })
            
            return sorted(results, key=lambda x: x['score'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Neural search error: {str(e)}")
            return []
    
    def _exact_search(self, quoted_company_name: str, max_results: int = 50) -> List[Dict]:
        """
        Exact phrase search for precise company mentions.
        """
        try:
            search_params = {
                "type": "keyword",
                "use_autoprompt": False,
                "num_results": max_results,
                "text": True,
                "highlights": {"num_sentences": 3, "highlights_per_url": 2}
            }
            
            response = self.exa.search_and_contents(quoted_company_name, **search_params)
            
            results = []
            query_text = quoted_company_name.strip('"').lower()
            
            for result in response.results:
                if hasattr(result, 'text') and result.text:
                    match_count = result.text.lower().count(query_text)
                    if match_count > 0:
                        results.append({
                            "url": result.url,
                            "title": getattr(result, 'title', 'No title'),
                            "match_count": match_count,
                            "highlights": getattr(result, 'highlights', []),
                            "search_type": "exact",
                            "relevance": "exact_match"
                        })
            
            return sorted(results, key=lambda x: x['match_count'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Exact search error: {str(e)}")
            return []
    
    def _news_search(self, company_name: str, days_back: int = 90, max_results: int = 50) -> List[Dict]:
        """
        Search for recent news about the company.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            search_params = {
                "type": "neural",
                "use_autoprompt": True,
                "num_results": max_results,
                "start_published_date": start_date.strftime('%Y-%m-%d'),
                "end_published_date": end_date.strftime('%Y-%m-%d'),
                "text": True,
                "highlights": {"num_sentences": 3, "highlights_per_url": 2}
            }
            
            # News-focused query
            query = f"{company_name} news announcement update report"
            
            response = self.exa.search_and_contents(query, **search_params)
            
            results = []
            for result in response.results:
                results.append({
                    "url": result.url,
                    "title": getattr(result, 'title', 'No title'),
                    "score": getattr(result, 'score', 0),
                    "date_published": getattr(result, 'published_date', 'N/A'),
                    "highlights": getattr(result, 'highlights', []),
                    "search_type": "news",
                    "relevance": "recent"
                })
            
            return sorted(results, key=lambda x: (x.get('date_published', ''), x['score']), reverse=True)
            
        except Exception as e:
            self.logger.error(f"News search error: {str(e)}")
            return []
    
    def _domain_search(self, company_name: str, max_results: int = 25) -> List[Dict]:
        """
        Search within specific high-value domains for company information.
        """
        # High-value domains for corporate intelligence
        domains = [
            "bloomberg.com",
            "reuters.com",
            "ft.com",
            "wsj.com",
            "forbes.com",
            "businessinsider.com",
            "crunchbase.com",
            "pitchbook.com",
            "sec.gov",
            "companieshouse.gov.uk"
        ]
        
        try:
            search_params = {
                "type": "keyword",
                "use_autoprompt": False,
                "num_results": max_results,
                "include_domains": domains,
                "text": True,
                "highlights": {"num_sentences": 3, "highlights_per_url": 2}
            }
            
            response = self.exa.search_and_contents(f'"{company_name}"', **search_params)
            
            results = []
            for result in response.results:
                domain = self._extract_domain(result.url)
                results.append({
                    "url": result.url,
                    "title": getattr(result, 'title', 'No title'),
                    "domain": domain,
                    "highlights": getattr(result, 'highlights', []),
                    "search_type": "domain",
                    "relevance": "authoritative",
                    "source_quality": "high"
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Domain search error: {str(e)}")
            return []
    
    def _consolidate_exa_results(self, results: Dict[str, List], company_name: str) -> Dict[str, Any]:
        """
        Consolidate and deduplicate results from different search strategies.
        """
        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        
        # Priority order: exact matches, domain results, neural results, news
        for search_type in ['exact_matches', 'domain_matches', 'neural_results', 'news']:
            for result in results.get(search_type, []):
                if result['url'] not in seen_urls:
                    seen_urls.add(result['url'])
                    unique_results.append(result)
        
        # Extract key intelligence categories
        intelligence = {
            'company_overview': [],
            'ownership_mentions': [],
            'financial_data': [],
            'recent_developments': [],
            'executive_mentions': [],
            'regulatory_filings': []
        }
        
        # Categorize results based on content
        for result in unique_results:
            categorized = self._categorize_result(result, company_name)
            for category, is_relevant in categorized.items():
                if is_relevant:
                    intelligence[category].append(result)
        
        # Summary statistics
        summary = {
            'total_results': len(unique_results),
            'exact_mentions': len(results.get('exact_matches', [])),
            'news_articles': len(results.get('news', [])),
            'authoritative_sources': len(results.get('domain_matches', [])),
            'highest_relevance_score': max([r.get('score', 0) for r in unique_results], default=0)
        }
        
        return {
            'search_timestamp': datetime.now().isoformat(),
            'company_name': company_name,
            'summary': summary,
            'intelligence': intelligence,
            'all_results': unique_results[:50]  # Limit to top 50 for response size
        }
    
    def _categorize_result(self, result: Dict, company_name: str) -> Dict[str, bool]:
        """
        Categorize a result into intelligence categories based on content analysis.
        """
        # Combine all text content for analysis
        text_content = ' '.join([
            result.get('title', ''),
            ' '.join(result.get('highlights', [])),
            result.get('text_snippet', '')
        ]).lower()
        
        company_lower = company_name.lower()
        
        # Keywords for each category
        ownership_keywords = ['owner', 'shareholder', 'stake', 'acquisition', 'subsidiary', 'parent company', 'holding']
        financial_keywords = ['revenue', 'profit', 'earnings', 'valuation', 'funding', 'investment', 'ipo', 'market cap']
        executive_keywords = ['ceo', 'cfo', 'cto', 'president', 'director', 'executive', 'board', 'management']
        regulatory_keywords = ['filing', 'sec', 'regulatory', 'compliance', 'registration', 'annual report', '10-k', '10-q']
        
        return {
            'company_overview': company_lower in text_content,
            'ownership_mentions': any(keyword in text_content for keyword in ownership_keywords),
            'financial_data': any(keyword in text_content for keyword in financial_keywords),
            'recent_developments': result.get('search_type') == 'news',
            'executive_mentions': any(keyword in text_content for keyword in executive_keywords),
            'regulatory_filings': any(keyword in text_content for keyword in regulatory_keywords)
        }
    
    def _extract_snippet(self, result) -> str:
        """
        Extract a relevant text snippet from the result.
        """
        if hasattr(result, 'text') and result.text:
            # Return first 500 characters
            return result.text[:500] + "..." if len(result.text) > 500 else result.text
        return ""
    
    def _extract_domain(self, url: str) -> str:
        """
        Extract domain from URL.
        """
        try:
            if '://' in url:
                domain = url.split('://')[1].split('/')[0]
            else:
                domain = url.split('/')[0]
            return domain.lower()
        except Exception as e:
            return ""


# Standalone test function
async def test_exa_search():
    """Test the Exa search functionality."""
    # Test companies
    test_companies = ["Apple Inc", "Revolut Ltd", "OpenAI"]
    
    try:
        searcher = ExaCompanySearch()
        
        for company in test_companies:
            print(f"\n{'='*80}")
            print(f"Testing Exa search for: {company}")
            print('='*80)
            
            results = await searcher.search_company(company, max_results=10)
            
            print(f"\nSummary:")
            print(f"- Total unique results: {results['summary']['total_results']}")
            print(f"- Exact mentions: {results['summary']['exact_mentions']}")
            print(f"- News articles: {results['summary']['news_articles']}")
            print(f"- Authoritative sources: {results['summary']['authoritative_sources']}")
            
            print(f"\nIntelligence categories found:")
            for category, items in results['intelligence'].items():
                if items:
                    print(f"- {category}: {len(items)} results")
            
            print(f"\nTop 3 results:")
            for i, result in enumerate(results['all_results'][:3], 1):
                print(f"\n{i}. {result['title']}")
                print(f"   URL: {result['url']}")
                print(f"   Type: {result['search_type']}")
                print(f"   Relevance: {result.get('relevance', 'N/A')}")
                
    except Exception as e:
        print(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run test
    asyncio.run(test_exa_search())
