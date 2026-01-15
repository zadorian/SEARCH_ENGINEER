#!/usr/bin/env python3
"""
SAGE Journals search engine for scientific and social sciences publications.
Searches 1000+ journals across science, technology, medicine, and social sciences.
Supports both public search and authenticated access for full text.
"""

import os
import time
import json
import requests
from bs4 import BeautifulSoup

# JESTER for scraping (auto-fallback A->B->C->D)
try:
    from .jester_bridge import jester_scrape_sync, JESTER_AVAILABLE
except ImportError:
    JESTER_AVAILABLE = False
    jester_scrape_sync = None
from typing import List, Dict, Optional, Iterator
from urllib.parse import quote, urlencode, urlparse
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

try:
    from shared_session import get_shared_session
    SHARED_SESSION = True
except ImportError:
    SHARED_SESSION = False


class ExactPhraseRecallRunnerSAGE:
    """Search SAGE Journals for academic papers."""
    
    def __init__(
        self,
        phrase: str,
        use_authentication: bool = True,  # Try to authenticate if credentials available
        use_proxy: bool = False,  # Use institutional proxy if configured
        search_field: Optional[str] = None,  # 'AllField', 'Title', 'Abstract', 'Keywords'
        date_range: Optional[tuple] = None,  # (start_year, end_year)
        access_type: Optional[str] = None,  # 'openaccess', 'freeaccess', 'all'
        max_results_per_page: int = 20,
        max_pages: int = 10
    ):
        self.phrase = phrase
        self.use_authentication = use_authentication
        self.use_proxy = use_proxy
        self.search_field = search_field or 'AllField'
        self.date_range = date_range
        self.access_type = access_type
        self.max_results_per_page = max_results_per_page
        self.max_pages = max_pages
        
        # URLs for different access methods
        if use_proxy and os.getenv('UCL_PROXY_USERNAME'):
            # Use UCL alumni proxy
            self.base_url = "https://journals-sagepub-com.ejournals.alumni.ucl.ac.uk"
            self.login_url = "https://ejournals.alumni.ucl.ac.uk/login"
            self.proxy_mode = True
        else:
            # Direct SAGE access
            self.base_url = "https://journals.sagepub.com"
            self.login_url = f"{self.base_url}/action/doLogin"
            self.proxy_mode = False
        
        # Create session
        if SHARED_SESSION:
            self.session = get_shared_session(engine_name='SAGE')
        else:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
        
        self.authenticated = False
        
        # Try to authenticate if requested and credentials available
        if use_authentication:
            self._attempt_login()
        
        print(f"  - ExactPhraseRecallRunnerSAGE Initialized")
        print(f"    Authentication: {'Enabled' if self.authenticated else 'Disabled (public access only)'}")
        print(f"    Search field: {search_field}")
        if date_range:
            print(f"    Date range: {date_range[0]}-{date_range[1]}")
        if access_type:
            print(f"    Access type filter: {access_type}")
    
    def _attempt_login(self):
        """Attempt to login to SAGE or proxy."""
        try:
            if self.proxy_mode:
                # Login to UCL proxy
                username = os.getenv('UCL_PROXY_USERNAME')
                password = os.getenv('UCL_PROXY_PASSWORD')
                
                if not username or not password:
                    print("UCL proxy credentials not found in .env")
                    return
                
                # UCL proxy login
                login_data = {
                    'username': username,
                    'password': password,
                    'submit': 'Login'
                }
                
                response = self.session.post(self.login_url, data=login_data, timeout=30)
                
                if response.status_code == 200 and 'logout' in response.text.lower():
                    self.authenticated = True
                    print("✅ Successfully authenticated via UCL proxy")
                else:
                    print("⚠️ UCL proxy authentication failed, using public access")
                    
            else:
                # Direct SAGE login
                username = os.getenv('SAGE_USERNAME')
                password = os.getenv('SAGE_PASSWORD')
                
                if not username or not password:
                    print("SAGE credentials not found in .env - using public access")
                    return
                
                # Get login page to extract any tokens
                login_page = self.session.get(f"{self.base_url}/action/showLogin", timeout=30)
                soup = BeautifulSoup(login_page.text, 'html.parser')
                
                # Extract CSRF token if present
                csrf_token = None
                csrf_input = soup.find('input', {'name': 'csrfToken'})
                if csrf_input:
                    csrf_token = csrf_input.get('value')
                
                # Prepare login data
                login_data = {
                    'email': username,
                    'password': password,
                    'rememberMe': 'true',
                    'submit': 'Sign in'
                }
                
                if csrf_token:
                    login_data['csrfToken'] = csrf_token
                
                # Attempt login
                response = self.session.post(self.login_url, data=login_data, timeout=30)
                
                # Check if login was successful
                if response.status_code == 200:
                    if 'sign out' in response.text.lower() or 'my account' in response.text.lower():
                        self.authenticated = True
                        print("✅ Successfully authenticated with SAGE Journals")
                    else:
                        print("⚠️ SAGE authentication may have failed, using public access")
                else:
                    print(f"⚠️ SAGE login returned status {response.status_code}, using public access")
                    
        except Exception as e:
            print(f"Authentication error: {e} - continuing with public access")
            self.authenticated = False
    
    def _build_search_url(self, page: int = 1) -> str:
        """Build the SAGE search URL."""
        # Base parameters - SAGE uses startPage for pagination
        params = {
            self.search_field: self.phrase,
            'startPage': page - 1,  # SAGE uses 0-based page numbering
            'pageSize': self.max_results_per_page
        }
        
        # Add date range if specified
        if self.date_range:
            params['AfterYear'] = self.date_range[0]
            params['BeforeYear'] = self.date_range[1]
        
        # Add access type filter
        if self.access_type == 'openaccess':
            params['access'] = 'openAccess'
        elif self.access_type == 'freeaccess':
            params['access'] = 'freeAccess'
        
        # Build query string
        query_string = urlencode(params)
        return f"{self.base_url}/action/doSearch?{query_string}"
    
    def _extract_article_data(self, article_elem) -> Optional[Dict[str, str]]:
        """Extract data from a single article element."""
        try:
            result = {}
            
            # Get title and URL
            title_elem = article_elem.find('a', class_='ref')
            if not title_elem:
                title_elem = article_elem.find('span', class_='hlFld-Title')
            
            if title_elem:
                result['title'] = title_elem.get_text(strip=True)
                if title_elem.name == 'a':
                    href = title_elem.get('href', '')
                    if href:
                        if href.startswith('/'):
                            result['url'] = f"{self.base_url}{href}"
                        else:
                            result['url'] = href
            
            # Get authors
            authors_elem = article_elem.find('div', class_='art_authors')
            if not authors_elem:
                authors_elem = article_elem.find('span', class_='hlFld-ContribAuthor')
            
            if authors_elem:
                # Clean up author names
                authors_text = authors_elem.get_text(strip=True)
                # Remove "Show all authors" link text if present
                authors_text = authors_text.replace('Show all authors', '').strip()
                result['authors'] = authors_text
            
            # Get journal information
            journal_elem = article_elem.find('span', class_='journalTitle')
            if not journal_elem:
                journal_elem = article_elem.find('a', class_='journalTitle')
            
            if journal_elem:
                result['journal'] = journal_elem.get_text(strip=True)
            
            # Get publication info (volume, issue, pages, date)
            pub_info_elem = article_elem.find('div', class_='art_meta')
            if pub_info_elem:
                meta_text = pub_info_elem.get_text(strip=True)
                result['pub_info'] = meta_text
            
            # Get DOI
            doi_elem = article_elem.find('a', {'title': 'Open DOI'})
            if not doi_elem:
                doi_elem = article_elem.find('span', class_='doi')
            
            if doi_elem:
                doi_text = doi_elem.get_text(strip=True)
                if 'doi' in doi_text.lower():
                    result['doi'] = doi_text.replace('https://doi.org/', '').replace('doi:', '').strip()
            
            # Get abstract/snippet
            abstract_elem = article_elem.find('div', class_='art_abstract')
            if not abstract_elem:
                abstract_elem = article_elem.find('span', class_='hlFld-Abstract')
            
            if abstract_elem:
                result['snippet'] = abstract_elem.get_text(strip=True)
            
            # Get access information
            access_elem = article_elem.find('img', {'alt': 'Open Access'})
            if access_elem:
                result['open_access'] = True
            
            # Check for full text if authenticated
            if self.authenticated:
                pdf_elem = article_elem.find('a', {'title': 'PDF'})
                if pdf_elem:
                    result['has_pdf'] = True
            
            # Get metrics if available
            metrics_elem = article_elem.find('div', class_='article-metrics')
            if metrics_elem:
                citations = metrics_elem.find('span', class_='citations')
                if citations:
                    result['citations'] = citations.get_text(strip=True)
            
            return result if 'title' in result else None
            
        except Exception as e:
            print(f"Error extracting article data: {e}")
            return None
    
    def _parse_search_page(self, html: str) -> tuple[List[Dict], int]:
        """Parse search results page and return articles and total count."""
        soup = BeautifulSoup(html, 'html.parser')
        articles = []
        
        # Find all article items
        article_elements = soup.find_all('div', class_='art_title')
        if not article_elements:
            # Try alternative structure
            article_elements = soup.find_all('li', class_='search__item')
        
        # Each article is contained in a parent div
        for elem in article_elements:
            # Get the parent container that has all article info
            parent = elem.find_parent('div', class_='searchResultItem')
            if not parent:
                parent = elem.find_parent('li')
            if not parent:
                parent = elem
            
            article_data = self._extract_article_data(parent)
            if article_data:
                articles.append(article_data)
        
        # Get total results count
        total_count = 0
        count_elem = soup.find('span', class_='result__count')
        if not count_elem:
            count_elem = soup.find('div', class_='searchResultsCount')
        
        if count_elem:
            text = count_elem.get_text()
            # Extract number from text like "1-20 of 1,234"
            import re
            match = re.search(r'of\s+([\d,]+)', text)
            if match:
                total_count = int(match.group(1).replace(',', ''))
            else:
                # Try alternative format
                match = re.search(r'([\d,]+)\s+results?', text)
                if match:
                    total_count = int(match.group(1).replace(',', ''))
        
        return articles, total_count
    
    def _format_result(self, article: Dict) -> Dict[str, str]:
        """Format article data into standard result format."""
        # Build title
        title_parts = [article.get('title', 'Untitled')]
        
        authors = article.get('authors', '')
        if authors:
            # Limit author list length
            if len(authors) > 100:
                authors = authors[:97] + '...'
            title_parts.append(f"- {authors}")
        
        # Extract year from pub_info if available
        pub_info = article.get('pub_info', '')
        if pub_info:
            import re
            year_match = re.search(r'\b(19|20)\d{2}\b', pub_info)
            if year_match:
                title_parts.append(f"({year_match.group()})")
        
        enhanced_title = ' '.join(title_parts)
        
        # Build snippet
        snippet_parts = []
        
        # Add journal
        journal = article.get('journal')
        if journal:
            snippet_parts.append(f"Journal: {journal}")
        
        # Add publication info
        if pub_info:
            snippet_parts.append(pub_info)
        
        # Add DOI
        doi = article.get('doi')
        if doi:
            snippet_parts.append(f"DOI: {doi}")
        
        # Add access indicators
        if article.get('open_access'):
            snippet_parts.append("🔓 Open Access")
        elif self.authenticated and article.get('has_pdf'):
            snippet_parts.append("📄 PDF Available")
        
        # Add citations if available
        citations = article.get('citations')
        if citations:
            snippet_parts.append(f"Citations: {citations}")
        
        # Add abstract
        abstract = article.get('snippet', '')
        if abstract:
            # Limit abstract length
            if len(abstract) > 300:
                abstract = abstract[:297] + '...'
            snippet_parts.append(abstract)
        
        snippet = ' | '.join(snippet_parts) if snippet_parts else "SAGE Journals article"
        
        return {
            'url': article.get('url', ''),
            'title': enhanced_title,
            'snippet': snippet,
            'source': 'sage'
        }
    
    def search(self, max_results: int = 100) -> List[Dict[str, str]]:
        """Search SAGE Journals for papers matching the phrase."""
        access_type = "authenticated" if self.authenticated else "public"
        print(f"🔍 Searching SAGE Journals ({access_type}) for: '{self.phrase}'")
        
        all_results = []
        
        try:
            for page in range(1, self.max_pages + 1):
                if len(all_results) >= max_results:
                    break
                
                url = self._build_search_url(page)
                
                # Make request
                # Use JESTER for scraping
                if JESTER_AVAILABLE and jester_scrape_sync:
                    _jester_html = jester_scrape_sync(url, force_js=False, timeout=30)
                    if _jester_html:
                        class _JesterResponse:
                            text = _jester_html
                            status_code = 200
                            def raise_for_status(self): pass
                        response = _JesterResponse()
                    else:
                        response = self.session.get(url, timeout=30)
                else:
                    response = self.session.get(url, timeout=30)
                
                if response.status_code != 200:
                    print(f"SAGE search error: HTTP {response.status_code}")
                    # If authentication failed, try to re-login
                    if response.status_code == 401 and self.use_authentication:
                        print("Session expired, attempting to re-authenticate...")
                        self._attempt_login()
                        if self.authenticated:
                            # Use JESTER for scraping
                if JESTER_AVAILABLE and jester_scrape_sync:
                    _jester_html = jester_scrape_sync(url, force_js=False, timeout=30)
                    if _jester_html:
                        class _JesterResponse:
                            text = _jester_html
                            status_code = 200
                            def raise_for_status(self): pass
                        response = _JesterResponse()
                    else:
                        response = self.session.get(url, timeout=30)
                else:
                    response = self.session.get(url, timeout=30)
                        else:
                            break
                    else:
                        break
                
                # Parse results
                articles, total_count = self._parse_search_page(response.text)
                
                if not articles:
                    print(f"No more results found on page {page}")
                    break
                
                # Process and add results
                for article in articles:
                    if len(all_results) >= max_results:
                        break
                    
                    # Format the result
                    result = self._format_result(article)
                    
                    # Only include if it has required fields
                    if result['url'] and result['title']:
                        # Check if phrase appears in title or snippet
                        phrase_lower = self.phrase.lower()
                        if (phrase_lower in result['title'].lower() or 
                            phrase_lower in result['snippet'].lower()):
                            all_results.append(result)
                
                print(f"  Page {page}: Found {len(articles)} articles (Total available: {total_count:,})")
                
                # Check if we've seen all results
                if len(all_results) >= total_count or page * self.max_results_per_page >= total_count:
                    break
                
                # Rate limiting
                if page < self.max_pages:
                    if self.authenticated:
                        time.sleep(1)  # Faster for authenticated users
                    else:
                        time.sleep(2)  # Slower for public access
            
        except Exception as e:
            print(f"SAGE search error: {e}")
        
        print(f"✅ Found {len(all_results)} results from SAGE Journals")
        return all_results[:max_results]
    
    def run(self) -> List[Dict[str, str]]:
        """Run the search - standard interface."""
        return self.search(max_results=self.max_results_per_page * self.max_pages)


# For backward compatibility
def search_sage_exact_phrase(phrase: str, max_results: int = 100, **kwargs) -> List[Dict[str, str]]:
    """Search SAGE Journals for exact phrase."""
    searcher = ExactPhraseRecallRunnerSAGE(phrase, **kwargs)
    return searcher.search(max_results)


if __name__ == "__main__":
    # Test the searcher
    print("Testing SAGE Journals search...")
    print("Note: For authenticated access, add to .env:")
    print("  SAGE_USERNAME=your_email")
    print("  SAGE_PASSWORD=your_password")
    print("  UCL_PROXY_USERNAME=your_username (optional)")
    print("  UCL_PROXY_PASSWORD=your_password (optional)")
    print()
    
    searcher = ExactPhraseRecallRunnerSAGE(
        "machine learning",
        use_authentication=True,  # Will try to login if credentials in .env
        search_field='AllField',
        date_range=(2022, 2024)
    )
    results = searcher.search(max_results=5)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Info: {result['snippet'][:200]}...")