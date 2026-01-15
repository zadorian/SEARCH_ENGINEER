"""
Multi-backend integration for GoogleSearch and BingSearch.
PRIORITY ORDER: Paid APIs first (SerpAPI, BrightData), then native CSE, scraping last (for JESTER)
"""

import os
import logging
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Import backends
try:
    from .serp_api import search_serpapi_google, search_serpapi_bing
    SERPAPI_AVAILABLE = True
except ImportError:
    SERPAPI_AVAILABLE = False
    logger.debug("SerpAPI not available")

try:
    from .serp_brightdata import fetch_serp_results
    import asyncio
    BRIGHTDATA_AVAILABLE = True
except ImportError:
    BRIGHTDATA_AVAILABLE = False
    logger.debug("BrightData SERP not available")


def multi_backend_google(query: str, max_results: int = 100, 
                         native_search_func=None, 
                         gl: str = None, **kwargs) -> Tuple[List[Dict], Optional[int]]:
    """
    Search Google using ALL available backends in parallel.
    PRIORITY: SerpAPI, BrightData (paid) -> CSE (quota-based) -> Scraping (JESTER fallback)
    
    Args:
        query: Search query
        max_results: Max results total
        native_search_func: Native CSE search function
        gl: Geolocation code (e.g., 'us', 'uk', 'de') for geo-rotation
    """
    all_results = []
    seen_urls = set()
    total_estimate = None
    
    per_backend = max(30, max_results // 3)
    
    def run_serpapi():
        """PRIORITY 1: SerpAPI (paid, fast)"""
        if SERPAPI_AVAILABLE:
            try:
                # SerpAPI supports gl parameter
                results = search_serpapi_google(query, num=per_backend, gl=gl)
                for r in results or []:
                    r['_backend'] = 'SerpAPI'
                    if gl:
                        r['_geo'] = gl
                return results or []
            except Exception as e:
                logger.warning(f"SerpAPI Google failed: {e}")
        return []
    
    def run_brightdata():
        """PRIORITY 2: BrightData SERP (paid, fast)"""
        if BRIGHTDATA_AVAILABLE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # BrightData supports country parameter
                    results = loop.run_until_complete(
                        fetch_serp_results(query, engine="google", num=per_backend, country=gl)
                    )
                    for r in results or []:
                        r['_backend'] = 'BrightData'
                        if gl:
                            r['_geo'] = gl
                    return results or []
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"BrightData Google failed: {e}")
        return []
    
    def run_native():
        """PRIORITY 3: Native CSE (quota-based)"""
        if native_search_func:
            try:
                results, total = native_search_func(query, per_backend, gl=gl, **kwargs)
                for r in results or []:
                    r['_backend'] = 'CSE'
                    if gl:
                        r['_geo'] = gl
                return results or [], total
            except Exception as e:
                logger.warning(f"Native Google CSE failed: {e}")
        return [], None
    
    # Run ALL backends in parallel - paid first gets results faster
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_serpapi): 'SerpAPI',
            executor.submit(run_brightdata): 'BrightData',
            executor.submit(run_native): 'CSE',
        }
        
        for future in as_completed(futures):
            backend = futures[future]
            try:
                result = future.result()
                if isinstance(result, tuple):
                    results, total = result
                    if total and total_estimate is None:
                        total_estimate = total
                else:
                    results = result
                
                # Dedupe by URL
                count_new = 0
                for r in results:
                    url = r.get('url') or r.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
                        count_new += 1
                
                geo_tag = f" [{gl}]" if gl else ""
                logger.info(f"[Google{geo_tag}] {backend}: +{count_new} new (total {len(results)})")
            except Exception as e:
                logger.warning(f"[Google] {backend} error: {e}")
    
    geo_tag = f" [{gl}]" if gl else ""
    logger.info(f"[Google{geo_tag}] Multi-backend total: {len(all_results)} unique results")
    return all_results, total_estimate


def multi_backend_bing(query: str, max_results: int = 100,
                       native_search_func=None, 
                       mkt: str = None, **kwargs) -> List[Dict]:
    """
    Search Bing using ALL available backends in parallel.
    PRIORITY: SerpAPI, BrightData (paid) -> Scraping (JESTER fallback)
    """
    all_results = []
    seen_urls = set()
    
    per_backend = max(30, max_results // 3)
    
    def run_serpapi():
        """PRIORITY 1: SerpAPI (paid)"""
        if SERPAPI_AVAILABLE:
            try:
                results = search_serpapi_bing(query, count=per_backend)
                for r in results or []:
                    r['_backend'] = 'SerpAPI'
                return results or []
            except Exception as e:
                logger.warning(f"SerpAPI Bing failed: {e}")
        return []
    
    def run_brightdata():
        """PRIORITY 2: BrightData (paid)"""
        if BRIGHTDATA_AVAILABLE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(
                        fetch_serp_results(query, engine="bing", num=per_backend)
                    )
                    for r in results or []:
                        r['_backend'] = 'BrightData'
                    return results or []
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"BrightData Bing failed: {e}")
        return []
    
    def run_native():
        """PRIORITY 3: Scraping (free, for JESTER fallback)"""
        if native_search_func:
            try:
                results = native_search_func(query, per_backend, mkt=mkt or 'en-US')
                for r in results or []:
                    r['_backend'] = 'Scrape'
                return results or []
            except Exception as e:
                logger.warning(f"Native Bing scraping failed: {e}")
        return []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_serpapi): 'SerpAPI',
            executor.submit(run_brightdata): 'BrightData',
            executor.submit(run_native): 'Scrape',
        }
        
        for future in as_completed(futures):
            backend = futures[future]
            try:
                results = future.result()
                count_new = 0
                for r in results:
                    url = r.get('url') or r.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
                        count_new += 1
                logger.info(f"[Bing] {backend}: +{count_new} new (total {len(results)})")
            except Exception as e:
                logger.warning(f"[Bing] {backend} error: {e}")
    
    logger.info(f"[Bing] Multi-backend total: {len(all_results)} unique results")
    return all_results


def multi_backend_duckduckgo(query: str, max_results: int = 100,
                              native_search_func=None) -> List[Dict]:
    """
    Search DuckDuckGo using ALL available backends in parallel.
    DDG is privacy-focused so no geo-rotation (results are neutral).
    """
    all_results = []
    seen_urls = set()
    
    per_backend = max(30, max_results // 3)
    
    def run_serpapi():
        if SERPAPI_AVAILABLE:
            try:
                from .serp_api import search_serpapi_duckduckgo
                results = search_serpapi_duckduckgo(query, num=per_backend)
                for r in results or []:
                    r['_backend'] = 'SerpAPI'
                return results or []
            except Exception as e:
                logger.warning(f"SerpAPI DuckDuckGo failed: {e}")
        return []
    
    def run_brightdata():
        if BRIGHTDATA_AVAILABLE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(
                        fetch_serp_results(query, engine="duckduckgo", num=per_backend)
                    )
                    for r in results or []:
                        r['_backend'] = 'BrightData'
                    return results or []
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"BrightData DuckDuckGo failed: {e}")
        return []
    
    def run_native():
        if native_search_func:
            try:
                results = native_search_func(query, per_backend)
                for r in results or []:
                    r['_backend'] = 'Native'
                return results or []
            except Exception as e:
                logger.warning(f"Native DuckDuckGo failed: {e}")
        return []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_serpapi): 'SerpAPI',
            executor.submit(run_brightdata): 'BrightData',
            executor.submit(run_native): 'Native',
        }
        
        for future in as_completed(futures):
            backend = futures[future]
            try:
                results = future.result()
                count_new = 0
                for r in results:
                    url = r.get('url') or r.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
                        count_new += 1
                logger.info(f"[DuckDuckGo] {backend}: +{count_new} new")
            except Exception as e:
                logger.warning(f"[DuckDuckGo] {backend} error: {e}")
    
    logger.info(f"[DuckDuckGo] Multi-backend total: {len(all_results)} unique results")
    return all_results


def multi_backend_yandex(query: str, max_results: int = 100,
                         native_search_func=None, lr: str = None) -> List[Dict]:
    """
    Search Yandex using ALL available backends in parallel.
    Supports region codes for geo-rotation within Russia/CIS.
    """
    all_results = []
    seen_urls = set()
    
    per_backend = max(30, max_results // 3)
    
    def run_serpapi():
        if SERPAPI_AVAILABLE:
            try:
                from .serp_api import search_serpapi_yandex
                results = search_serpapi_yandex(query, num=per_backend, lr=lr)
                for r in results or []:
                    r['_backend'] = 'SerpAPI'
                    if lr:
                        r['_region'] = lr
                return results or []
            except Exception as e:
                logger.warning(f"SerpAPI Yandex failed: {e}")
        return []
    
    def run_brightdata():
        if BRIGHTDATA_AVAILABLE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(
                        fetch_serp_results(query, engine="yandex", num=per_backend)
                    )
                    for r in results or []:
                        r['_backend'] = 'BrightData'
                    return results or []
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"BrightData Yandex failed: {e}")
        return []
    
    def run_native():
        if native_search_func:
            try:
                results = native_search_func(query, per_backend)
                for r in results or []:
                    r['_backend'] = 'Native'
                return results or []
            except Exception as e:
                logger.warning(f"Native Yandex failed: {e}")
        return []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_serpapi): 'SerpAPI',
            executor.submit(run_brightdata): 'BrightData',
            executor.submit(run_native): 'Native',
        }
        
        for future in as_completed(futures):
            backend = futures[future]
            try:
                results = future.result()
                count_new = 0
                for r in results:
                    url = r.get('url') or r.get('link', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
                        count_new += 1
                logger.info(f"[Yandex] {backend}: +{count_new} new")
            except Exception as e:
                logger.warning(f"[Yandex] {backend} error: {e}")
    
    logger.info(f"[Yandex] Multi-backend total: {len(all_results)} unique results")
    return all_results
