#!/usr/bin/env python3
"""
PDF Search Module - Searches Anna's Archive specifically for PDF files
Extracts MD5 download links from search results
"""

import os
import re
import time
import logging
import requests
from typing import List, Dict, Optional, Iterator
from urllib.parse import quote, urlencode
from bs4 import BeautifulSoup
from datetime import datetime
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFSearch:
    """Search Anna's Archive specifically for PDF files and extract download links"""
    
    def __init__(self, query: str = None):
        """
        Initialize PDF search
        
        Args:
            query: Search query (without pdf: operator)
        """
        self.query = query
        self.base_url = "https://annas-archive.org"
        self.search_id = str(uuid.uuid4())[:8]
        
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
        
        logger.info(f"PDFSearch initialized for query: {query}")
    
    def build_search_url(self, page: int = 1) -> str:
        """
        Build Anna's Archive search URL for PDFs
        
        Args:
            page: Page number
            
        Returns:
            Search URL with PDF filter
        """
        params = {
            'q': self.query,
            'ext': 'pdf',  # Filter for PDFs only
            'page': page,
            'index': '',  # Search all indexes
            'display': '',
            'sort': ''
        }
        
        url = f"{self.base_url}/search?{urlencode(params)}"
        logger.debug(f"PDF search URL: {url}")
        return url
    
    def extract_md5_links(self, html: str) -> List[Dict]:
        """
        Extract MD5 download links from Anna's Archive HTML
        
        Args:
            html: HTML content from search page
            
        Returns:
            List of dictionaries with PDF information and download links
        """
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all links with /md5/ in the href
            # Anna's Archive uses these patterns:
            # <a href="/md5/HASH" class="js-vim-focus...">
            md5_links = soup.find_all('a', href=re.compile(r'/md5/[a-fA-F0-9]+'))
            
            for link in md5_links:
                try:
                    # Extract MD5 hash from href
                    href = link.get('href', '')
                    md5_match = re.search(r'/md5/([a-fA-F0-9]+)', href)
                    if not md5_match:
                        continue
                    
                    md5_hash = md5_match.group(1)
                    download_url = f"{self.base_url}/md5/{md5_hash}"
                    
                    # Try to extract title and metadata from the link's parent container
                    result = {
                        'md5': md5_hash,
                        'url': download_url,
                        'download_url': download_url,
                        'format': 'PDF'
                    }
                    
                    # Find the parent container that has the full result information
                    parent = link.parent
                    while parent and parent.name not in ['body', 'html']:
                        # Look for title
                        if not result.get('title'):
                            title_elem = parent.find('h3') or parent.find('div', class_=re.compile(r'font-bold|truncate'))
                            if title_elem:
                                title_text = title_elem.get_text(strip=True)
                                if title_text and len(title_text) > 3:
                                    result['title'] = title_text
                        
                        # Look for author
                        if not result.get('author'):
                            author_elem = parent.find('div', class_=re.compile(r'italic|text-gray'))
                            if author_elem:
                                author_text = author_elem.get_text(strip=True)
                                if author_text and not author_text.startswith('MD5'):
                                    result['author'] = author_text
                        
                        # Look for metadata (size, year, pages)
                        meta_elems = parent.find_all('div', class_='text-xs') or parent.find_all('span', class_='text-gray-500')
                        for meta in meta_elems:
                            text = meta.get_text(strip=True)
                            
                            # Extract year
                            if not result.get('year'):
                                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                                if year_match:
                                    result['year'] = year_match.group()
                            
                            # Extract size
                            if not result.get('size'):
                                if 'MB' in text or 'KB' in text or 'GB' in text:
                                    result['size'] = text
                            
                            # Extract page count
                            if not result.get('pages'):
                                page_match = re.search(r'(\d+)\s*(?:pages?|p\.)', text, re.IGNORECASE)
                                if page_match:
                                    result['pages'] = page_match.group(1) + ' pages'
                        
                        parent = parent.parent
                    
                    # Set default title if none found
                    if not result.get('title'):
                        result['title'] = f"PDF Document (MD5: {md5_hash[:8]}...)"
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.debug(f"Error extracting MD5 link data: {e}")
                    continue
            
            logger.info(f"Extracted {len(results)} PDF download links")
            
        except Exception as e:
            logger.error(f"Error parsing PDF search results: {e}")
        
        return results
    
    def search(self, limit: int = 50) -> List[Dict]:
        """
        Search Anna's Archive for PDFs and extract download links
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of PDF results with download links
        """
        if not self.query:
            logger.warning("No query provided")
            return []
        
        all_results = []
        page = 1
        max_pages = 5  # Limit pages to avoid too many requests
        
        while len(all_results) < limit and page <= max_pages:
            try:
                url = self.build_search_url(page)
                logger.info(f"Searching Anna's Archive PDFs page {page}: {url}")
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Extract MD5 links from the page
                pdf_results = self.extract_md5_links(response.text)
                
                if not pdf_results:
                    logger.info("No more PDF results found")
                    break
                
                # Format results for Search_Engineer
                for pdf in pdf_results:
                    formatted = self.format_result(pdf)
                    if formatted:
                        all_results.append(formatted)
                
                logger.info(f"Found {len(pdf_results)} PDFs on page {page}")
                
                page += 1
                time.sleep(1)  # Be polite to the server
                
            except requests.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}")
                break
        
        return all_results[:limit]
    
    def format_result(self, pdf_data: Dict) -> Dict:
        """
        Format PDF result for Search_Engineer compatibility
        
        Args:
            pdf_data: Raw PDF data from extraction
            
        Returns:
            Formatted result dictionary
        """
        try:
            # Create snippet from metadata
            snippet_parts = []
            if pdf_data.get('author'):
                snippet_parts.append(f"by {pdf_data['author']}")
            if pdf_data.get('year'):
                snippet_parts.append(f"({pdf_data['year']})")
            if pdf_data.get('size'):
                snippet_parts.append(f"[{pdf_data['size']}]")
            if pdf_data.get('pages'):
                snippet_parts.append(pdf_data['pages'])
            
            snippet = ' '.join(snippet_parts) if snippet_parts else 'PDF available for download'
            
            # Format for grid display
            formatted = {
                # Primary fields
                'url': pdf_data['download_url'],  # Direct download link
                'title': pdf_data.get('title', 'Unknown PDF'),
                'snippet': snippet,
                'engines': ['PDF'],
                'query': self.query,
                
                # Type information
                'type': 'document',
                'subtype': 'pdf',
                'source': "Anna's Archive PDFs",
                
                # Metadata
                'metadata': {
                    'md5': pdf_data.get('md5'),
                    'author': pdf_data.get('author'),
                    'year': pdf_data.get('year'),
                    'size': pdf_data.get('size'),
                    'pages': pdf_data.get('pages'),
                    'format': 'PDF',
                    'download_url': pdf_data['download_url']
                },
                
                # Additional fields
                'value': pdf_data['download_url'],
                'project_id': 'pdf_search',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error formatting PDF result: {e}")
            return None
    
    def run(self) -> Iterator[Dict]:
        """
        Run search and yield results (generator for streaming)
        
        Yields:
            PDF search results one by one
        """
        results = self.search()
        
        for result in results:
            # Add streaming metadata
            result['streaming'] = True
            result['engine'] = 'PDF'
            result['search_id'] = self.search_id
            
            yield result


class PDFSearchRunner:
    """Runner class for integration with brute search"""
    
    def __init__(self, phrase: str, **kwargs):
        """
        Initialize runner for brute search compatibility
        
        Args:
            phrase: Search query
            **kwargs: Additional arguments (ignored)
        """
        self.phrase = phrase
        self.search = PDFSearch(query=phrase)
        self.results_found = False
    
    def run(self) -> Iterator[Dict]:
        """
        Run search and yield results
        
        Yields:
            PDF search results formatted for brute search
        """
        try:
            for result in self.search.run():
                self.results_found = True
                
                # Add brute search compatibility fields
                result['engine'] = 'PDF'
                result['engines'] = ['PDF']
                result['found_by_engines'] = ['PDF']
                result['domain'] = 'annas-archive.org'
                
                yield result
                
        except Exception as e:
            logger.error(f"Error in PDF search: {e}")
            return
    
    def has_results(self) -> bool:
        """Check if search found results"""
        return self.results_found


# Factory function for brute search
def create_pdf_search_client():
    """Create PDF search client for brute search integration"""
    return PDFSearchRunner

# Adapter to match web_api.api.search expectation
def search(query: str, limit: int = 50):
    return PDFSearch(query=query).search(limit=limit)


# Command-line interface
def main(argv=None):
    """Command-line interface for PDF search"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Search Anna\'s Archive for PDFs')
    parser.add_argument('-q', '--query', type=str, required=False,
                       help='Search query')
    parser.add_argument('query_positional', type=str, nargs='?',
                       help='Search query (positional)')
    parser.add_argument('--limit', type=int, default=20,
                       help='Maximum number of results')
    
    args = parser.parse_args(argv)
    
    # Get query from either -q or positional argument
    query = args.query or args.query_positional
    
    # Strip pdf: prefix if present
    if query and query.startswith('pdf:'):
        query = query[4:].strip()
    
    if not query:
        parser.error("Query is required")
    
    # Initialize search
    search = PDFSearch(query=query)
    
    # Perform search
    print(f"\nSearching Anna's Archive for PDFs: {query}")
    print("-" * 80)
    
    results = search.search(limit=args.limit)
    
    if not results:
        print("No PDF results found.")
        return
    
    # Display results
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   Download: {result['url']}")
        if result['metadata'].get('author'):
            print(f"   Author: {result['metadata']['author']}")
        if result['metadata'].get('year'):
            print(f"   Year: {result['metadata']['year']}")
        if result['metadata'].get('size'):
            print(f"   Size: {result['metadata']['size']}")
        if result['metadata'].get('pages'):
            print(f"   Pages: {result['metadata']['pages']}")
    
    print(f"\nFound {len(results)} PDF results.")


if __name__ == '__main__':
    main()