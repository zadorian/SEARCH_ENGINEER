"""
SerpAPI integration for Google and Bing searches.
Uses SerpAPI.com for reliable SERP results with geo-rotation support.
"""

import os
import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv('SERPAPI_KEY') or os.getenv('SERPAPI_API_KEY', '')


def search_serpapi_google(query: str, num: int = 100, gl: str = None, 
                          hl: str = None, start: int = 0) -> List[Dict]:
    """
    Search Google via SerpAPI with geo-rotation support.
    
    Args:
        query: Search query
        num: Number of results (max 100 per request)
        gl: Geolocation - country code (e.g., 'us', 'uk', 'de')
        hl: Language code (e.g., 'en', 'de', 'fr')
        start: Starting offset
        
    Returns:
        List of result dicts with title, url, snippet
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not configured")
        return []
    
    params = {
        'api_key': SERPAPI_KEY,
        'engine': 'google',
        'q': query,
        'num': min(num, 100),
    }
    
    if gl:
        params['gl'] = gl
        params['google_domain'] = _get_google_domain(gl)
    if hl:
        params['hl'] = hl
    if start > 0:
        params['start'] = start
    
    try:
        response = requests.get('https://serpapi.com/search', params=params, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"SerpAPI error: {response.status_code} - {response.text[:200]}")
            return []
        
        data = response.json()
        results = []
        
        for item in data.get('organic_results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'position': item.get('position'),
                'source': 'serpapi_google',
            })
        
        logger.info(f"SerpAPI Google [{gl or 'default'}]: {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"SerpAPI Google error: {e}")
        return []


def search_serpapi_bing(query: str, count: int = 50, mkt: str = None) -> List[Dict]:
    """
    Search Bing via SerpAPI.
    
    Args:
        query: Search query
        count: Number of results
        mkt: Market code (e.g., 'en-US', 'de-DE')
        
    Returns:
        List of result dicts
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not configured")
        return []
    
    params = {
        'api_key': SERPAPI_KEY,
        'engine': 'bing',
        'q': query,
        'count': min(count, 50),
    }
    
    if mkt:
        params['mkt'] = mkt
    
    try:
        response = requests.get('https://serpapi.com/search', params=params, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"SerpAPI Bing error: {response.status_code}")
            return []
        
        data = response.json()
        results = []
        
        for item in data.get('organic_results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'position': item.get('position'),
                'source': 'serpapi_bing',
            })
        
        logger.info(f"SerpAPI Bing: {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"SerpAPI Bing error: {e}")
        return []


def _get_google_domain(gl: str) -> str:
    """Get appropriate Google domain for country code."""
    domains = {
        'us': 'google.com',
        'uk': 'google.co.uk',
        'de': 'google.de',
        'fr': 'google.fr',
        'es': 'google.es',
        'it': 'google.it',
        'nl': 'google.nl',
        'au': 'google.com.au',
        'ca': 'google.ca',
        'br': 'google.com.br',
        'in': 'google.co.in',
        'jp': 'google.co.jp',
    }
    return domains.get(gl, 'google.com')


def search_serpapi_duckduckgo(query: str, num: int = 50) -> List[Dict]:
    """
    Search DuckDuckGo via SerpAPI.
    Note: DDG doesn't support geo params - results are neutral by design.
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not configured")
        return []
    
    params = {
        'api_key': SERPAPI_KEY,
        'engine': 'duckduckgo',
        'q': query,
    }
    
    try:
        response = requests.get('https://serpapi.com/search', params=params, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"SerpAPI DuckDuckGo error: {response.status_code}")
            return []
        
        data = response.json()
        results = []
        
        for item in data.get('organic_results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'position': item.get('position'),
                'source': 'serpapi_duckduckgo',
            })
        
        logger.info(f"SerpAPI DuckDuckGo: {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"SerpAPI DuckDuckGo error: {e}")
        return []


def search_serpapi_yandex(query: str, num: int = 100, lr: str = None) -> List[Dict]:
    """
    Search Yandex via SerpAPI with region support.
    
    Args:
        query: Search query
        num: Number of results
        lr: Yandex region code (e.g., '213' for Moscow, '2' for Saint Petersburg)
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not configured")
        return []
    
    params = {
        'api_key': SERPAPI_KEY,
        'engine': 'yandex',
        'text': query,
    }
    
    if lr:
        params['lr'] = lr
    
    try:
        response = requests.get('https://serpapi.com/search', params=params, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"SerpAPI Yandex error: {response.status_code}")
            return []
        
        data = response.json()
        results = []
        
        for item in data.get('organic_results', []):
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', ''),
                'position': item.get('position'),
                'source': 'serpapi_yandex',
            })
        
        logger.info(f"SerpAPI Yandex: {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"SerpAPI Yandex error: {e}")
        return []
