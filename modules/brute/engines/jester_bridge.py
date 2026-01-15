"""
JESTER Bridge for Brute Engines

Provides unified access to JESTER scraping hierarchy for search engines.
Uses JESTER_A -> B -> C -> D fallback chain for maximum reliability.

Usage:
    from .jester_bridge import jester_scrape, jester_scrape_batch
    
    # Single URL
    html = await jester_scrape("https://example.com")
    
    # Batch
    results = await jester_scrape_batch(["url1", "url2"], max_concurrent=10)
"""

import asyncio
import logging
from typing import Optional, List, Dict, Tuple, Any

logger = logging.getLogger(__name__)

# Try to import jester
try:
    from modules.jester import Jester, JesterMethod, JesterResult
    from modules.jester import scrape_c, scrape_c_batch, rod_available
    from modules.jester import scrape_d, scrape_d_batch, jester_d_available
    JESTER_AVAILABLE = True
except ImportError:
    JESTER_AVAILABLE = False
    logger.warning("JESTER not available, falling back to basic requests")


async def jester_scrape(
    url: str,
    force_js: bool = False,
    timeout: int = 30
) -> Optional[str]:
    """
    Scrape a URL using JESTER hierarchy.
    
    Args:
        url: URL to scrape
        force_js: Force JavaScript rendering (skip JESTER_A/B, start at JESTER_C)
        timeout: Request timeout in seconds
        
    Returns:
        HTML content or None if failed
    """
    if not JESTER_AVAILABLE:
        # Fallback to basic requests
        import requests
        try:
            resp = requests.get(url, timeout=timeout, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            })
            return resp.text if resp.ok else None
        except Exception as e:
            logger.error(f"Basic scrape failed for {url}: {e}")
            return None
    
    try:
        jester = Jester()
        
        if force_js:
            # Skip A/B, go straight to C (Rod/JS rendering)
            if rod_available():
                result = await scrape_c(url)
                if result and result.html and len(result.html) > 100:
                    return result.html
            # Fallback to D if C failed
            if jester_d_available():
                result = await scrape_d(url)
                if result and result.html and len(result.html) > 100:
                    return result.html
            return None
        else:
            # Use full hierarchy
            result = await jester.scrape(url)
            if result and result.html and len(result.html) > 100:
                return result.html
            return None
            
    except Exception as e:
        logger.error(f"JESTER scrape failed for {url}: {e}")
        return None


async def jester_scrape_batch(
    urls: List[str],
    max_concurrent: int = 20,
    force_js: bool = False,
    timeout: int = 30
) -> Dict[str, Optional[str]]:
    """
    Scrape multiple URLs using JESTER.
    
    Args:
        urls: List of URLs to scrape
        max_concurrent: Max concurrent requests
        force_js: Force JavaScript rendering
        timeout: Request timeout
        
    Returns:
        Dict mapping URL -> HTML content (or None if failed)
    """
    if not JESTER_AVAILABLE:
        # Fallback to basic requests
        import requests
        from concurrent.futures import ThreadPoolExecutor
        
        def fetch(url):
            try:
                resp = requests.get(url, timeout=timeout, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
                })
                return url, resp.text if resp.ok else None
            except:
                return url, None
        
        results = {}
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            for url, html in executor.map(fetch, urls):
                results[url] = html
        return results
    
    try:
        if force_js and rod_available():
            # Use JESTER_C (Rod) for JS-heavy sites
            batch_results = await scrape_c_batch(urls, max_concurrent=max_concurrent)
            return {r.url: r.html if r and r.html and len(r.html) > 100 else None 
                    for r in batch_results}
        else:
            # Use unified JESTER with automatic fallback
            jester = Jester()
            batch_results = await jester.scrape_batch(urls, max_concurrent=max_concurrent)
            return {r.url: r.html if r and r.html and len(r.html) > 100 else None 
                    for r in batch_results}
            
    except Exception as e:
        logger.error(f"JESTER batch scrape failed: {e}")
        return {url: None for url in urls}


def jester_scrape_sync(url: str, force_js: bool = False, timeout: int = 30) -> Optional[str]:
    """Synchronous wrapper for jester_scrape"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(jester_scrape(url, force_js, timeout))


def jester_scrape_batch_sync(
    urls: List[str], 
    max_concurrent: int = 20,
    force_js: bool = False,
    timeout: int = 30
) -> Dict[str, Optional[str]]:
    """Synchronous wrapper for jester_scrape_batch"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(jester_scrape_batch(urls, max_concurrent, force_js, timeout))


# Convenience exports
__all__ = [
    "jester_scrape",
    "jester_scrape_batch", 
    "jester_scrape_sync",
    "jester_scrape_batch_sync",
    "JESTER_AVAILABLE"
]
