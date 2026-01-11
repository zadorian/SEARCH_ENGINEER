#!/usr/bin/env python3
"""
Sherlock Project Integration for Username OSINT
Provides username search across 400+ social networks and websites
Using Sherlock's database of site patterns
"""

import json
import logging
import asyncio
import aiohttp
from typing import List, Dict, Optional, Any
from pathlib import Path
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Sherlock site data - Top sites with high reliability
# Full list available at: https://github.com/sherlock-project/sherlock
SHERLOCK_SITES = {
    "GitHub": {
        "url": "https://github.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "coding"
    },
    "Twitter": {
        "url": "https://twitter.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Instagram": {
        "url": "https://www.instagram.com/{}/",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Facebook": {
        "url": "https://www.facebook.com/{}",
        "error_type": "response_url",
        "error_url": "https://www.facebook.com/help",
        "category": "social"
    },
    "YouTube": {
        "url": "https://www.youtube.com/@{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "video"
    },
    "Reddit": {
        "url": "https://www.reddit.com/user/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Pinterest": {
        "url": "https://www.pinterest.com/{}/",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Tumblr": {
        "url": "https://{}.tumblr.com",
        "error_type": "status_code",
        "error_code": 404,
        "category": "blogging"
    },
    "Flickr": {
        "url": "https://www.flickr.com/people/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "photo"
    },
    "Steam": {
        "url": "https://steamcommunity.com/id/{}",
        "error_type": "message",
        "error_msg": "The specified profile could not be found",
        "category": "gaming"
    },
    "Vimeo": {
        "url": "https://vimeo.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "video"
    },
    "SoundCloud": {
        "url": "https://soundcloud.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "music"
    },
    "Disqus": {
        "url": "https://disqus.com/by/{}/",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Medium": {
        "url": "https://medium.com/@{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "blogging"
    },
    "DeviantArt": {
        "url": "https://www.deviantart.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "art"
    },
    "VK": {
        "url": "https://vk.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "About.me": {
        "url": "https://about.me/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "social"
    },
    "Imgur": {
        "url": "https://imgur.com/user/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "photo"
    },
    "Flipboard": {
        "url": "https://flipboard.com/@{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "news"
    },
    "SlideShare": {
        "url": "https://www.slideshare.net/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "business"
    },
    "Spotify": {
        "url": "https://open.spotify.com/user/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "music"
    },
    "Scribd": {
        "url": "https://www.scribd.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "documents"
    },
    "Patreon": {
        "url": "https://www.patreon.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "creator"
    },
    "BitBucket": {
        "url": "https://bitbucket.org/{}/",
        "error_type": "status_code",
        "error_code": 404,
        "category": "coding"
    },
    "GitLab": {
        "url": "https://gitlab.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "coding"
    },
    "Behance": {
        "url": "https://www.behance.net/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "design"
    },
    "Dribbble": {
        "url": "https://dribbble.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "design"
    },
    "AngelList": {
        "url": "https://angel.co/u/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "business"
    },
    "ProductHunt": {
        "url": "https://www.producthunt.com/@{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "tech"
    },
    "HackerNews": {
        "url": "https://news.ycombinator.com/user?id={}",
        "error_type": "message",
        "error_msg": "No such user",
        "category": "tech"
    },
    "CodePen": {
        "url": "https://codepen.io/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "coding"
    },
    "Gravatar": {
        "url": "https://en.gravatar.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "avatar"
    },
    "Keybase": {
        "url": "https://keybase.io/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "security"
    },
    "HackerOne": {
        "url": "https://hackerone.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "security"
    },
    "BugCrowd": {
        "url": "https://bugcrowd.com/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "security"
    },
    "DevTo": {
        "url": "https://dev.to/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "coding"
    },
    "Hashnode": {
        "url": "https://hashnode.com/@{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "blogging"
    },
    "Telegram": {
        "url": "https://t.me/{}",
        "error_type": "status_code",
        "error_code": 404,
        "category": "messaging"
    }
}


class SherlockIntegration:
    """
    Integration with Sherlock Project patterns for username OSINT
    """
    
    def __init__(self, timeout: int = 10, max_concurrent: int = 10):
        """
        Initialize Sherlock integration
        
        Args:
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent checks
        """
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def check_username(self, username: str, sites: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Check username across multiple sites
        
        Args:
            username: Username to search
            sites: List of site names to check (None = all sites)
        
        Returns:
            List of results with found profiles
        """
        if not self.session:
            async with aiohttp.ClientSession() as session:
                self.session = session
                return await self._check_username_internal(username, sites)
        return await self._check_username_internal(username, sites)
    
    async def _check_username_internal(self, username: str, sites: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Internal username checking logic"""
        sites_to_check = sites if sites else list(SHERLOCK_SITES.keys())
        
        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Check all sites concurrently
        tasks = []
        for site_name in sites_to_check:
            if site_name in SHERLOCK_SITES:
                task = self._check_site(username, site_name, SHERLOCK_SITES[site_name], semaphore)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out errors and None results
        valid_results = []
        for result in results:
            if isinstance(result, dict) and result.get('found'):
                valid_results.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Error checking site: {result}")
        
        return valid_results
    
    async def _check_site(self, username: str, site_name: str, site_info: Dict, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        """
        Check a single site for username
        
        Args:
            username: Username to check
            site_name: Name of the site
            site_info: Site configuration
            semaphore: Rate limiting semaphore
        
        Returns:
            Result dict if found, None otherwise
        """
        async with semaphore:
            try:
                url = site_info['url'].format(username)
                
                async with self.session.get(url, allow_redirects=True, ssl=False) as response:
                    # Check based on error type
                    error_type = site_info.get('error_type')
                    
                    if error_type == 'status_code':
                        # Check if status code indicates profile exists
                        if response.status != site_info.get('error_code', 404):
                            return {
                                'found': True,
                                'site': site_name,
                                'url': url,
                                'category': site_info.get('category', 'unknown'),
                                'status_code': response.status,
                                'username': username
                            }
                    
                    elif error_type == 'response_url':
                        # Check if redirected to error page
                        if str(response.url) != site_info.get('error_url'):
                            return {
                                'found': True,
                                'site': site_name,
                                'url': url,
                                'category': site_info.get('category', 'unknown'),
                                'final_url': str(response.url),
                                'username': username
                            }
                    
                    elif error_type == 'message':
                        # Check if error message is in response
                        text = await response.text()
                        if site_info.get('error_msg') not in text:
                            return {
                                'found': True,
                                'site': site_name,
                                'url': url,
                                'category': site_info.get('category', 'unknown'),
                                'username': username
                            }
                    
                    else:
                        # Default: assume found if status is 200
                        if response.status == 200:
                            return {
                                'found': True,
                                'site': site_name,
                                'url': url,
                                'category': site_info.get('category', 'unknown'),
                                'status_code': response.status,
                                'username': username
                            }
                
            except asyncio.TimeoutError:
                logger.debug(f"Timeout checking {site_name} for {username}")
            except Exception as e:
                logger.debug(f"Error checking {site_name} for {username}: {e}")
        
        return None
    
    def get_site_categories(self) -> Dict[str, List[str]]:
        """
        Get sites organized by category
        
        Returns:
            Dict mapping categories to site names
        """
        categories = {}
        for site_name, site_info in SHERLOCK_SITES.items():
            category = site_info.get('category', 'unknown')
            if category not in categories:
                categories[category] = []
            categories[category].append(site_name)
        return categories
    
    def get_sites_by_category(self, category: str) -> List[str]:
        """
        Get sites for a specific category
        
        Args:
            category: Category name
        
        Returns:
            List of site names in that category
        """
        return [
            site_name for site_name, site_info in SHERLOCK_SITES.items()
            if site_info.get('category') == category
        ]


async def search_username_sherlock(username: str, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Search for username using Sherlock patterns
    
    Args:
        username: Username to search
        categories: Optional list of categories to search
    
    Returns:
        List of found profiles
    """
    async with SherlockIntegration() as sherlock:
        # Get sites to check based on categories
        sites_to_check = None
        if categories:
            sites_to_check = []
            for category in categories:
                sites_to_check.extend(sherlock.get_sites_by_category(category))
        
        # Check username
        results = await sherlock.check_username(username, sites_to_check)
        
        # Sort by category
        results.sort(key=lambda x: x.get('category', 'unknown'))
        
        return results


def search_username_sherlock_sync(username: str, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for Sherlock username search
    
    Args:
        username: Username to search
        categories: Optional list of categories to search
    
    Returns:
        List of found profiles
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(search_username_sherlock(username, categories))
    finally:
        loop.close()


if __name__ == "__main__":
    # Test the Sherlock integration
    import sys
    
    if len(sys.argv) > 1:
        test_username = sys.argv[1]
    else:
        test_username = "johndoe"
    
    print(f"Testing Sherlock integration for username: {test_username}\n")
    
    # Test async version
    async def test_async():
        async with SherlockIntegration() as sherlock:
            # Test all sites
            print("Checking all sites...")
            results = await sherlock.check_username(test_username)
            
            print(f"\nFound {len(results)} profiles:")
            for result in results[:10]:  # Show first 10
                print(f"  ✓ {result['site']}: {result['url']}")
            
            # Test by category
            print("\n\nChecking only social sites...")
            social_results = await sherlock.check_username(test_username, sherlock.get_sites_by_category('social'))
            
            print(f"\nFound {len(social_results)} social profiles:")
            for result in social_results:
                print(f"  ✓ {result['site']}: {result['url']}")
    
    # Run test
    asyncio.run(test_async())
    
    # Test sync version
    print("\n\nTesting synchronous wrapper...")
    sync_results = search_username_sherlock_sync(test_username, ['coding', 'tech'])
    print(f"Found {len(sync_results)} coding/tech profiles")