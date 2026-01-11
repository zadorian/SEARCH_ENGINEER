#!/usr/bin/env python3
"""
qwant_scraper.py

Qwant search scraper/client that handles individual searches.
Supports JavaScript rendering via Firecrawl when available.
"""

import time
import logging
import requests
from typing import List, Dict, Optional
from urllib.parse import quote, urlencode
from bs4 import BeautifulSoup
import re
import os
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QwantScraper:
    """Qwant search scraper for individual queries with locale support."""
    
    def __init__(self, phrase: str = None, search_type: str = 'web', 
                 locale: str = None, max_results: int = 50):
        """
        Initialize Qwant scraper.
        
        Args:
            phrase: Search query
            search_type: Type of search ('web', 'videos', 'news', 'images')
            locale: Locale code (e.g., 'en_US', 'fr_FR')
            max_results: Maximum number of results to return
        """
        self.phrase = phrase
        self.search_type = search_type.lower()
        self.locale = locale
        self.max_results = max_results
        self.base_url = "https://www.qwant.com/"
        self.results_found = False
        
        # Session for consistent requests
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
        
        # Initialize Firecrawl if available
        self.firecrawl_client = None
        self.use_firecrawl = False
        
        if os.getenv('FIRECRAWL_API_KEY'):
            try:
                # Import FirecrawlClient from scraper
                import sys
                from pathlib import Path
                project_root = Path(__file__).parent.parent
                sys.path.insert(0, str(project_root))
                from brute.scraper.firecrawl_client import FirecrawlClient
                
                # Initialize client - we'll use it in async context
                self.firecrawl_client = FirecrawlClient()
                self.use_firecrawl = True
                logger.info(f"Firecrawl enabled for Qwant {search_type} search")
            except Exception as e:
                logger.warning(f"Could not initialize Firecrawl: {e}")
                self.use_firecrawl = False
        else:
            logger.debug("FIRECRAWL_API_KEY not found, using standard HTTP requests")
    
    def build_url(self, offset: int = 0) -> str:
        """
        Build Qwant search URL with locale support.
        
        Args:
            offset: Pagination offset
            
        Returns:
            Complete search URL
        """
        params = {'q': self.phrase}
        
        # Add locale if specified
        if self.locale:
            params['locale'] = self.locale
        
        # Add type parameter for non-web searches
        if self.search_type != 'web':
            params['t'] = self.search_type
        
        # Add pagination if needed
        if offset > 0:
            params['p'] = offset // 10 + 1  # Qwant uses page numbers
        
        url = f"{self.base_url}?{urlencode(params)}"
        logger.debug(f"Built URL: {url}")
        return url
    
    async def _scrape_with_firecrawl(self, url: str) -> Optional[str]:
        """
        Scrape a URL using Firecrawl for JavaScript rendering.
        
        Args:
            url: URL to scrape
            
        Returns:
            HTML content or None if failed
        """
        try:
            async with self.firecrawl_client as client:
                # Use Firecrawl with JavaScript wait to ensure content loads
                result = await client.scrape_url(
                    url,
                    formats=['markdown', 'html'],
                    waitFor=3000,  # Wait 3 seconds for JS to load
                    onlyMainContent=False  # Get full page for search results
                )
                
                if result.success and result.markdown:
                    logger.info(f"Firecrawl successfully scraped {url}")
                    # Return HTML for parsing, fallback to markdown if needed
                    return result.metadata.get('html', result.markdown)
                else:
                    logger.warning(f"Firecrawl scraping failed: {result.error}")
                    return None
                    
        except Exception as e:
            logger.error(f"Firecrawl error: {e}")
            return None
    
    def extract_web_results(self, html: str) -> List[Dict]:
        """Extract standard web search results."""
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for result containers - Qwant structure may vary
            # Common patterns: data-testid="webResult" or class containing result
            result_containers = soup.find_all('div', {'data-testid': re.compile('webResult|result')})
            
            if not result_containers:
                # Alternative: look for links with specific patterns
                result_containers = soup.find_all('article') or soup.find_all('div', class_=re.compile('result|item'))
            
            for container in result_containers[:self.max_results]:
                try:
                    result = {}
                    
                    # Extract URL
                    link = container.find('a', href=True)
                    if link:
                        result['url'] = link.get('href', '')
                        
                    # Extract title
                    title_elem = container.find(['h2', 'h3', 'h4']) or link
                    if title_elem:
                        result['title'] = title_elem.get_text(strip=True)
                    
                    # Extract snippet
                    snippet_elem = container.find('p') or container.find('span', class_=re.compile('desc|snippet'))
                    if snippet_elem:
                        result['snippet'] = snippet_elem.get_text(strip=True)
                    
                    if result.get('url') and result.get('title'):
                        results.append(result)
                        
                except Exception as e:
                    logger.debug(f"Error extracting web result: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing web results: {e}")
        
        return results
    
    def extract_video_results(self, html: str) -> List[Dict]:
        """Extract video search results."""
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find videos container
            videos_container = soup.find('div', {'data-testid': 'videosList'})
            
            if not videos_container:
                # Alternative: look for video-related containers
                videos_container = soup.find('div', class_=re.compile('video'))
            
            if videos_container:
                # Extract video links
                video_links = videos_container.find_all('a', href=True)
                
                for link in video_links[:self.max_results]:
                    try:
                        url = link.get('href', '')
                        
                        # Filter for actual video URLs (YouTube, Vimeo, etc.)
                        if any(domain in url for domain in ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com']):
                            result = {
                                'url': url,
                                'type': 'video',
                                'source': self._extract_video_source(url)
                            }
                            
                            # Try to extract title from link or nearby text
                            title_elem = link.find(['h3', 'h4', 'span']) or link
                            if title_elem:
                                result['title'] = title_elem.get_text(strip=True)
                            
                            # Try to extract thumbnail
                            img = link.find('img')
                            if img:
                                result['thumbnail'] = img.get('src', '')
                            
                            # Try to extract duration
                            duration_elem = link.find('span', class_=re.compile('duration|time'))
                            if duration_elem:
                                result['duration'] = duration_elem.get_text(strip=True)
                            
                            if result.get('url'):
                                results.append(result)
                                
                    except Exception as e:
                        logger.debug(f"Error extracting video result: {e}")
                        continue
            
            # Fallback: look for any video links on the page
            if not results:
                all_links = soup.find_all('a', href=re.compile(r'youtube\.com/watch|youtu\.be/|vimeo\.com/|dailymotion\.com/'))
                for link in all_links[:self.max_results]:
                    try:
                        url = link.get('href', '')
                        if url.startswith('/'):
                            url = 'https://www.qwant.com' + url
                        
                        result = {
                            'url': url,
                            'title': link.get_text(strip=True) or 'Video',
                            'type': 'video',
                            'source': self._extract_video_source(url)
                        }
                        results.append(result)
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing video results: {e}")
        
        return results
    
    def extract_news_results(self, html: str) -> List[Dict]:
        """Extract news search results."""
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find news container
            news_container = soup.find('div', {'data-testid': 'newsList'})
            
            if not news_container:
                # Alternative: look for news-related containers
                news_container = soup.find('div', class_=re.compile('news'))
            
            if news_container:
                # Extract news articles
                articles = news_container.find_all(['article', 'div'], class_=re.compile('article|news-item|card'))
                
                for article in articles[:self.max_results]:
                    try:
                        result = {'type': 'news'}
                        
                        # Extract URL
                        link = article.find('a', href=True)
                        if link:
                            result['url'] = link.get('href', '')
                            
                        # Extract title
                        title_elem = article.find(['h2', 'h3', 'h4']) or link
                        if title_elem:
                            result['title'] = title_elem.get_text(strip=True)
                        
                        # Extract snippet
                        snippet_elem = article.find('p') or article.find('span', class_=re.compile('desc|snippet|summary'))
                        if snippet_elem:
                            result['snippet'] = snippet_elem.get_text(strip=True)
                        
                        # Extract source
                        source_elem = article.find('span', class_=re.compile('source|publisher'))
                        if source_elem:
                            result['source'] = source_elem.get_text(strip=True)
                        
                        # Extract date
                        date_elem = article.find('time') or article.find('span', class_=re.compile('date|time'))
                        if date_elem:
                            result['date'] = date_elem.get_text(strip=True)
                        
                        if result.get('url') and result.get('title'):
                            results.append(result)
                            
                    except Exception as e:
                        logger.debug(f"Error extracting news result: {e}")
                        continue
            
            # Fallback: look for any article-like structures
            if not results:
                articles = soup.find_all(['article', 'div'], class_=re.compile('result|item'))
                for article in articles[:self.max_results]:
                    try:
                        link = article.find('a', href=True)
                        if link:
                            result = {
                                'url': link.get('href', ''),
                                'title': link.get_text(strip=True),
                                'type': 'news',
                                'snippet': article.get_text(strip=True)[:200]
                            }
                            if result['url'] and result['title']:
                                results.append(result)
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing news results: {e}")
        
        return results
    
    def extract_image_results(self, html: str) -> List[Dict]:
        """Extract image search results."""
        results = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find images container
            images_container = soup.find('div', {'data-testid': 'imagesList'})
            
            if not images_container:
                # Alternative: look for image galleries
                images_container = soup.find('div', class_=re.compile('image|gallery'))
            
            if images_container:
                # Extract image links
                images = images_container.find_all('img')
                
                for img in images[:self.max_results]:
                    try:
                        result = {
                            'type': 'image',
                            'thumbnail': img.get('src', ''),
                            'title': img.get('alt', 'Image'),
                        }
                        
                        # Try to find full-size image URL
                        parent_link = img.find_parent('a')
                        if parent_link:
                            result['url'] = parent_link.get('href', '')
                        else:
                            result['url'] = result['thumbnail']
                        
                        # Extract dimensions if available
                        if img.get('width'):
                            result['width'] = img.get('width')
                        if img.get('height'):
                            result['height'] = img.get('height')
                        
                        if result.get('url'):
                            results.append(result)
                            
                    except Exception as e:
                        logger.debug(f"Error extracting image result: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing image results: {e}")
        
        return results
    
    def _extract_video_source(self, url: str) -> str:
        """Extract video source from URL."""
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'YouTube'
        elif 'vimeo.com' in url:
            return 'Vimeo'
        elif 'dailymotion.com' in url:
            return 'Dailymotion'
        else:
            return 'Video'
    
    def search(self) -> List[Dict]:
        """
        Perform search and return results.
        
        Returns:
            List of search results
        """
        if not self.phrase:
            logger.warning("No search phrase provided")
            return []
        
        all_results = []
        
        # Build URL for search with locale
        url = self.build_url(0)
        logger.info(f"Searching Qwant {self.search_type}: {url}")
        
        # Try Firecrawl first if available
        html_content = None
        if self.use_firecrawl:
            try:
                # Run async scraping in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                html_content = loop.run_until_complete(self._scrape_with_firecrawl(url))
                loop.close()
            except Exception as e:
                logger.warning(f"Firecrawl scraping failed, falling back to standard requests: {e}")
        
        # Fallback to standard HTTP request if Firecrawl failed or unavailable
        if not html_content:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                html_content = response.text
            except requests.RequestException as e:
                logger.error(f"Error fetching Qwant results: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return []
        
        # Extract results based on search type
        if self.search_type == 'videos':
            all_results = self.extract_video_results(html_content)
        elif self.search_type == 'news':
            all_results = self.extract_news_results(html_content)
        elif self.search_type == 'images':
            all_results = self.extract_image_results(html_content)
        else:  # web search
            all_results = self.extract_web_results(html_content)
        
        logger.info(f"Found {len(all_results)} results total")
        
        self.results_found = len(all_results) > 0
        return all_results[:self.max_results]
    
    def has_results(self) -> bool:
        """Check if search found results."""
        return self.results_found


def main():
    """Test the Qwant scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Qwant Scraper')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--type', default='web', 
                       choices=['web', 'videos', 'news', 'images'],
                       help='Search type')
    parser.add_argument('--locale', help='Locale code (e.g., en_US, fr_FR)')
    parser.add_argument('--limit', type=int, default=10, help='Maximum results')
    
    args = parser.parse_args()
    
    scraper = QwantScraper(
        phrase=args.query,
        search_type=args.type,
        locale=args.locale,
        max_results=args.limit
    )
    
    print(f"Searching Qwant {args.type} for: {args.query}")
    if args.locale:
        print(f"Locale: {args.locale}")
    print("-" * 60)
    
    results = scraper.search()
    
    if results:
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
            if result.get('snippet'):
                print(f"   Snippet: {result['snippet'][:150]}...")
    else:
        print("No results found")


if __name__ == '__main__':
    main()