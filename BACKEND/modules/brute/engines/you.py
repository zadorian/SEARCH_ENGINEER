#!/usr/bin/env python3
"""
You.com Search API Runner
Supports both web search and news search with exact phrase capabilities
API Documentation: https://documentation.you.com/api-reference/
"""

import os
import requests
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import time
from urllib.parse import quote

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YouSearch:
    """You.com search wrapper for exact phrase and general searches"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize You.com search client
        
        Args:
            api_key: You.com API key. If not provided, will look for YOU_API_KEY env var
        """
        self.api_key = api_key or os.getenv('YOU_API_KEY')
        if not self.api_key:
            raise ValueError("You.com API key required. Set YOU_API_KEY environment variable or pass api_key parameter")
        
        # API endpoints
        self.web_search_url = "https://api.ydc-index.io/search"
        self.news_search_url = "https://api.ydc-index.io/news"
        
        # Default headers
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
        logger.info("You.com search client initialized")
    
    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _process_exact_phrase_query(self, query: str) -> str:
        """Process query to add + operator for exact term requirements
        
        According to You.com docs:
        - Use + to require exact terms
        - Quoted phrases should have + added to each word for exact matching
        
        Args:
            query: Original search query
            
        Returns:
            Processed query with + operators for exact matching
        """
        import re
        
        # Check if this is an exact phrase search (quoted)
        if query.startswith('"') and query.endswith('"'):
            # Extract the phrase
            phrase = query[1:-1]
            # Split into words and add + to each
            words = phrase.split()
            exact_words = [f'+{word}' for word in words]
            # Reconstruct as quoted phrase with + operators
            return f'"{" ".join(exact_words)}"'
        
        # Handle multiple quoted phrases in query
        def replace_quoted(match):
            phrase = match.group(1)
            words = phrase.split()
            exact_words = [f'+{word}' for word in words]
            return f'"{" ".join(exact_words)}"'
        
        # Process all quoted phrases in the query
        processed = re.sub(r'"([^"]+)"', replace_quoted, query)
        
        # For non-quoted critical terms, we could also add + selectively
        # But for now, focus on exact phrase handling
        
        return processed
    
    def search(self, query: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Main search method for web search
        
        Args:
            query: Search query (supports exact phrases in quotes)
            max_results: Maximum number of results to return
            **kwargs: Additional search parameters
            
        Returns:
            List of search results with title, url, snippet
        """
        return self.search_web(query, max_results, **kwargs)
    
    def search_web(self, query: str, max_results: int = 50, 
                   country: Optional[str] = None,
                   safe_search: str = "off",
                   freshness: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search You.com web results
        
        Args:
            query: Search query (supports exact phrases in quotes)
            max_results: Maximum number of results (You.com returns max 20 per request)
            country: Country code for localized results (e.g., 'US', 'GB')
            safe_search: Safe search setting ('off', 'moderate', 'strict')
            freshness: Result freshness ('day', 'week', 'month', 'year')
            
        Returns:
            List of search results
        """
        self._rate_limit()
        
        # Process query for exact phrase handling
        processed_query = self._process_exact_phrase_query(query)
        
        # You.com returns max 20 results per request, need pagination for more
        all_results = []
        offset = 0
        
        while len(all_results) < max_results:
            # Build request parameters
            params = {
                "query": processed_query,
                "num_web_results": min(20, max_results - len(all_results)),  # Max 20 per request
                "offset": offset,
                "safesearch": safe_search
            }
            
            # Add optional parameters
            if country:
                params["country"] = country
            
            if freshness:
                params["recency"] = freshness
            
            try:
                response = requests.get(
                    self.web_search_url,
                    params=params,
                    headers=self.headers,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extract web results - You.com uses "hits" not "results"!
                results_key = "hits" if "hits" in data else "results"
                if results_key in data:
                    for result in data[results_key]:
                        formatted_result = {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": result.get("description", ""),
                            "source": "you.com",
                            "rank": len(all_results) + 1
                        }
                        
                        # Add additional metadata if available
                        if "age" in result:
                            formatted_result["published_date"] = result["age"]
                        
                        # Handle snippets array if present
                        if "snippets" in result and result["snippets"]:
                            # Combine snippets into one
                            formatted_result["snippet"] = " ... ".join(result["snippets"])
                        
                        all_results.append(formatted_result)
                        
                        if len(all_results) >= max_results:
                            break
                
                # Check if more results are available
                if len(data.get(results_key, [])) < 20:
                    break  # No more results available
                
                offset += 20
                
            except requests.exceptions.RequestException as e:
                logger.error(f"You.com web search error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in You.com web search: {e}")
                break
        
        logger.info(f"You.com web search returned {len(all_results)} results for query: {query}")
        return all_results[:max_results]
    
    def search_filetype(self, query: str, filetype: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search for specific file types using native filetype: operator
        
        Args:
            query: Base search query
            filetype: File extension (pdf, doc, xls, etc.)
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # You.com supports native filetype: operator
        # Process query for exact terms if quoted
        processed_query = self._process_exact_phrase_query(query) if '"' in query else query
        filetype_query = f'{processed_query} filetype:{filetype}'
        return self.search_web(filetype_query, max_results, **kwargs)
    
    def search_site(self, query: str, domain: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search within a specific site using native site: operator
        
        Args:
            query: Search query
            domain: Domain to search within
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # You.com supports native site: operator
        site_query = f'{query} site:{domain}'
        return self.search_web(site_query, max_results, **kwargs)
    
    def search_exclude(self, query: str, exclude_terms: List[str], max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search with exclusion using native - operator
        
        Args:
            query: Base search query
            exclude_terms: Terms to exclude
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # Build exclusion query with - operator
        exclusions = ' '.join([f'-{term}' for term in exclude_terms])
        exclude_query = f'{query} {exclusions}'
        return self.search_web(exclude_query, max_results, **kwargs)
    
    def search_language(self, query: str, language_code: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search in specific language using native lang: operator
        
        Args:
            query: Search query
            language_code: ISO 639-1 language code (en, es, fr, etc.)
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # You.com supports native lang: operator
        lang_query = f'{query} lang:{language_code}'
        return self.search_web(lang_query, max_results, **kwargs)
    
    def search_location(self, query: str, country_code: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search with location filter using country parameter
        
        Args:
            query: Search query
            country_code: Country code (US, GB, FR, etc.)
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # Use country parameter for location-specific results
        return self.search_web(query, max_results, country=country_code, **kwargs)
    
    def search_date(self, query: str, freshness: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search with date/freshness filter
        
        Args:
            query: Search query
            freshness: Freshness filter ('day', 'week', 'month', 'year')
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results
        """
        # Use freshness parameter for date filtering
        return self.search_web(query, max_results, freshness=freshness, **kwargs)
    
    def search_definition(self, term: str, subject: Optional[str] = None, location: Optional[str] = None, 
                         max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search for definitions with optional subject and location context
        
        Args:
            term: Term to define
            subject: Optional subject/domain context (e.g., 'medicine', 'law', 'technology')
            location: Optional location context (country code or location name)
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results focused on definitions
        """
        # Build definitional query with + operator for precision
        definition_queries = [
            f'+define +{term}',
            f'+"what is {term}"',
            f'+{term} +definition',
            f'+{term} +meaning'
        ]
        
        # Add subject context if provided
        if subject:
            definition_queries = [
                f'{q} +{subject}' for q in definition_queries
            ]
            # Also add subject-specific sites
            if subject.lower() in ['medicine', 'medical', 'health']:
                definition_queries.append(f'+{term} site:nih.gov OR site:webmd.com OR site:mayoclinic.org')
            elif subject.lower() in ['law', 'legal']:
                definition_queries.append(f'+{term} site:law.cornell.edu OR site:findlaw.com')
            elif subject.lower() in ['technology', 'tech', 'computer']:
                definition_queries.append(f'+{term} site:techopedia.com OR site:techtarget.com')
            elif subject.lower() in ['science', 'scientific']:
                definition_queries.append(f'+{term} site:britannica.com OR site:sciencedirect.com')
            elif subject.lower() in ['business', 'finance']:
                definition_queries.append(f'+{term} site:investopedia.com OR site:businessdictionary.com')
        
        # Add location context if provided
        location_params = {}
        if location:
            # If location is a country code
            if len(location) == 2:
                location_params['country'] = location.upper()
            else:
                # Add location to query for context
                definition_queries = [
                    f'{q} +{location}' for q in definition_queries
                ]
        
        # Collect results from multiple definition-focused queries
        all_results = []
        seen_urls = set()
        
        for query in definition_queries[:3]:  # Use top 3 query variations
            try:
                results = self.search_web(query, max_results=max_results//3, **location_params, **kwargs)
                for result in results:
                    if result.get('url') not in seen_urls:
                        seen_urls.add(result.get('url'))
                        result['definition_query'] = query
                        result['subject_context'] = subject
                        result['location_context'] = location
                        all_results.append(result)
            except Exception as e:
                logger.error(f"Definition search error for query '{query}': {e}")
                continue
        
        # Prioritize results that look like definitions
        def score_definition_relevance(result):
            score = 0
            title_lower = result.get('title', '').lower()
            snippet_lower = result.get('snippet', '').lower()
            url_lower = result.get('url', '').lower()
            
            # Check for definition indicators in title
            if 'definition' in title_lower or 'meaning' in title_lower or 'what is' in title_lower:
                score += 3
            if term.lower() in title_lower:
                score += 2
                
            # Check for definition patterns in snippet
            if f'{term.lower()} is' in snippet_lower or f'{term.lower()} means' in snippet_lower:
                score += 2
            if 'definition' in snippet_lower or 'defined as' in snippet_lower:
                score += 1
                
            # Bonus for authoritative definition sites
            authority_domains = ['dictionary.com', 'merriam-webster.com', 'oxford', 'cambridge.org',
                               'wikipedia.org', 'britannica.com', 'investopedia.com']
            if any(domain in url_lower for domain in authority_domains):
                score += 2
                
            return score
        
        # Sort by definition relevance
        all_results.sort(key=score_definition_relevance, reverse=True)
        
        logger.info(f"Definition search for '{term}' (subject: {subject}, location: {location}) returned {len(all_results)} results")
        return all_results[:max_results]
    
    def search_subject(self, query: str, subject: str, max_results: int = 50, **kwargs) -> List[Dict[str, Any]]:
        """Search within a specific subject domain
        
        Args:
            query: Search query
            subject: Subject domain (e.g., 'medicine', 'law', 'technology', 'science')
            max_results: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of search results focused on the subject
        """
        # Map subjects to authoritative domains
        subject_domains = {
            'medicine': ['nih.gov', 'pubmed.ncbi.nlm.nih.gov', 'webmd.com', 'mayoclinic.org', 'who.int'],
            'medical': ['nih.gov', 'pubmed.ncbi.nlm.nih.gov', 'webmd.com', 'mayoclinic.org', 'who.int'],
            'health': ['nih.gov', 'cdc.gov', 'webmd.com', 'healthline.com', 'who.int'],
            'law': ['law.cornell.edu', 'findlaw.com', 'justia.com', 'law.com', 'lexisnexis.com'],
            'legal': ['law.cornell.edu', 'findlaw.com', 'justia.com', 'law.com', 'lexisnexis.com'],
            'technology': ['ieee.org', 'acm.org', 'techcrunch.com', 'arstechnica.com', 'stackoverflow.com'],
            'tech': ['github.com', 'stackoverflow.com', 'dev.to', 'medium.com', 'hackernoon.com'],
            'computer': ['ieee.org', 'acm.org', 'stackoverflow.com', 'github.com', 'computerworld.com'],
            'science': ['nature.com', 'science.org', 'sciencedirect.com', 'plos.org', 'arxiv.org'],
            'physics': ['physics.org', 'aps.org', 'iop.org', 'arxiv.org', 'physicsworld.com'],
            'chemistry': ['acs.org', 'rsc.org', 'chemspider.com', 'pubchem.ncbi.nlm.nih.gov'],
            'biology': ['bio.org', 'ncbi.nlm.nih.gov', 'plos.org', 'nature.com/subjects/biological-sciences'],
            'business': ['harvard.edu', 'wharton.upenn.edu', 'bloomberg.com', 'wsj.com', 'forbes.com'],
            'finance': ['investopedia.com', 'bloomberg.com', 'reuters.com', 'ft.com', 'wsj.com'],
            'education': ['ed.gov', 'edutopia.org', 'chronicle.com', 'educationweek.org', 'eric.ed.gov'],
            'history': ['history.com', 'archives.gov', 'loc.gov', 'historychannel.com', 'bbc.co.uk/history'],
            'philosophy': ['plato.stanford.edu', 'iep.utm.edu', 'philosophynow.org', 'apaonline.org'],
            'psychology': ['apa.org', 'psychology.org', 'psychologytoday.com', 'ncbi.nlm.nih.gov/pmc'],
            'engineering': ['ieee.org', 'asme.org', 'nspe.org', 'engineering.com', 'engr.psu.edu']
        }
        
        # Get domains for the subject
        domains = subject_domains.get(subject.lower(), [])
        
        # Build subject-focused queries
        subject_queries = []
        
        # If we have specific domains for this subject, use site: operator
        if domains:
            # Create OR query with multiple sites
            site_query = ' OR '.join([f'site:{domain}' for domain in domains[:5]])
            subject_queries.append(f'{self._process_exact_phrase_query(query)} ({site_query})')
        
        # Also add subject keyword to the query for broader results
        subject_queries.append(f'{self._process_exact_phrase_query(query)} +{subject}')
        
        # For academic subjects, add scholarly search patterns
        if subject.lower() in ['science', 'medicine', 'physics', 'chemistry', 'biology', 'psychology']:
            subject_queries.append(f'{self._process_exact_phrase_query(query)} +"peer reviewed" +{subject}')
            subject_queries.append(f'{self._process_exact_phrase_query(query)} +"research" +"journal" +{subject}')
        
        # Collect results
        all_results = []
        seen_urls = set()
        
        for subject_query in subject_queries[:2]:  # Use top 2 queries
            try:
                results = self.search_web(subject_query, max_results=max_results//2, **kwargs)
                for result in results:
                    if result.get('url') not in seen_urls:
                        seen_urls.add(result.get('url'))
                        result['subject'] = subject
                        result['subject_query'] = subject_query
                        all_results.append(result)
            except Exception as e:
                logger.error(f"Subject search error for query '{subject_query}': {e}")
                continue
        
        logger.info(f"Subject search for '{query}' in {subject} returned {len(all_results)} results")
        return all_results[:max_results]
    
    def search_news(self, query: str, max_results: int = 50,
                    country: Optional[str] = None,
                    freshness: str = "week") -> List[Dict[str, Any]]:
        """Search You.com news results
        
        Args:
            query: Search query (supports exact phrases in quotes)
            max_results: Maximum number of results
            country: Country code for localized news
            freshness: News freshness ('day', 'week', 'month')
            
        Returns:
            List of news results
        """
        self._rate_limit()
        
        all_results = []
        offset = 0
        
        while len(all_results) < max_results:
            # Build request parameters
            params = {
                "q": query,
                "count": min(20, max_results - len(all_results)),
                "offset": offset
            }
            
            # Add optional parameters
            if country:
                params["country"] = country
            
            if freshness:
                params["recency"] = freshness
            
            try:
                response = requests.get(
                    self.news_search_url,
                    params=params,
                    headers=self.headers,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extract news results
                if "news" in data and "results" in data["news"]:
                    for result in data["news"]["results"]:
                        formatted_result = {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": result.get("description", ""),
                            "source": result.get("source", "you.com_news"),
                            "published_date": result.get("age", ""),
                            "type": "news",
                            "rank": len(all_results) + 1
                        }
                        
                        # Add publisher info if available
                        if "publisher" in result:
                            formatted_result["publisher"] = result["publisher"]
                        
                        all_results.append(formatted_result)
                        
                        if len(all_results) >= max_results:
                            break
                
                # Check if more results are available
                if len(data.get("news", {}).get("results", [])) < 20:
                    break  # No more results available
                
                offset += 20
                
            except requests.exceptions.RequestException as e:
                logger.error(f"You.com news search error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in You.com news search: {e}")
                break
        
        logger.info(f"You.com news search returned {len(all_results)} results for query: {query}")
        return all_results[:max_results]


class ExactPhraseRecallRunnerYou:
    """Exact phrase recall runner for You.com - compatible with brute.py"""
    
    def __init__(self, phrase: str, max_results_per_query: int = 100):
        """Initialize the exact phrase runner
        
        Args:
            phrase: Exact phrase to search for
            max_results_per_query: Maximum results per query
        """
        self.phrase = phrase
        self.max_results = max_results_per_query
        self.client = YouSearch()
        
        # Build queries with exact phrase - You.com requires + for exact terms
        # Split phrase into words and add + to each for maximum precision
        words = phrase.split()
        exact_query = ' '.join([f'+{word}' for word in words])
        
        self.queries = [
            f'"{exact_query}"',  # Quoted with + for each word (maximum precision)
            exact_query,  # Just + operators without quotes
            f'"{phrase}"',  # Standard quoted phrase (will be processed by _process_exact_phrase_query)
        ]
        
        logger.info(f"You.com exact phrase runner initialized for: {phrase} with + operators")
    
    def run(self) -> List[Dict[str, Any]]:
        """Run the exact phrase search
        
        Returns:
            List of all results from all query variations
        """
        all_results = []
        seen_urls = set()
        
        for query in self.queries:
            try:
                results = self.client.search_web(query, self.max_results)
                
                for result in results:
                    # Deduplicate by URL
                    url = result.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        result['query_used'] = query
                        all_results.append(result)
                
                # Small delay between queries
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error with query '{query}': {e}")
                continue
        
        logger.info(f"You.com exact phrase search completed. Total unique results: {len(all_results)}")
        return all_results


# Convenience function for backward compatibility
def you_web(query: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Quick web search function
    
    Args:
        query: Search query
        max_results: Maximum results
        
    Returns:
        List of search results
    """
    try:
        client = YouSearch()
        return client.search_web(query, max_results)
    except Exception as e:
        logger.error(f"You.com web search failed: {e}")
        return []


def you_news(query: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """Quick news search function
    
    Args:
        query: Search query
        max_results: Maximum results
        
    Returns:
        List of news results
    """
    try:
        client = YouSearch()
        return client.search_news(query, max_results)
    except Exception as e:
        logger.error(f"You.com news search failed: {e}")
        return []


# Testing
if __name__ == "__main__":
    import sys
    
    # Test search
    if len(sys.argv) > 1:
        test_query = ' '.join(sys.argv[1:])
    else:
        test_query = '"artificial intelligence" ethics'
    
    print(f"\n🔍 Testing You.com search with query: {test_query}")
    print("=" * 60)
    
    try:
        # Test web search
        print("\n📰 Web Search Results:")
        web_results = you_web(test_query, max_results=5)
        for i, result in enumerate(web_results, 1):
            print(f"\n{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            print(f"   Snippet: {result['snippet'][:150]}...")
        
        # Test news search
        print("\n📰 News Search Results:")
        news_results = you_news(test_query, max_results=5)
        for i, result in enumerate(news_results, 1):
            print(f"\n{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            print(f"   Source: {result.get('publisher', result.get('source', 'Unknown'))}")
            print(f"   Date: {result.get('published_date', 'Unknown')}")
        
        # Test exact phrase runner
        print("\n🎯 Exact Phrase Runner Test:")
        runner = ExactPhraseRecallRunnerYou(test_query.replace('"', ''), max_results_per_query=5)
        exact_results = runner.run()
        print(f"Found {len(exact_results)} total results")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
    
    print("\n✅ All tests completed successfully!")