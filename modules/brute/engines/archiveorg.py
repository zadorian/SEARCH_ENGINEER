"""
Archive.org Search Engine - MAX RECALL VERSION

Combines:
1. Archive.org Search API (items, texts, web archives)
2. Wayback Machine CDX API (historical web pages)
3. Multiple query variations for max recall
"""

import os
import logging
import asyncio
import aiohttp
import requests
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

logger = logging.getLogger(__name__)

# Wayback CDX API
CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"

# Archive.org Search API  
ARCHIVE_SEARCH_API = "https://archive.org/advancedsearch.php"

# Mediatypes to search for max recall
MEDIATYPES = [
    'texts',      # Books, documents
    'web',        # Archived websites  
    'audio',      # Audio files
    'movies',     # Video content
    'image',      # Images
    'software',   # Software
    'data',       # Datasets
]

try:
    import internetarchive as ia
    IA_AVAILABLE = True
except ImportError:
    ia = None
    IA_AVAILABLE = False


class ArchiveOrgSearch:
    """Archive.org search with max recall capabilities."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search Archive.org items.
        
        Args:
            query: Search query
            max_results: Max results to return
            
        Returns:
            List of result dicts
        """
        results = []
        
        try:
            # Use Advanced Search API (more reliable than library)
            params = {
                'q': query,
                'fl[]': ['identifier', 'title', 'description', 'mediatype', 'date', 'creator'],
                'rows': min(max_results, 500),
                'page': 1,
                'output': 'json'
            }
            
            response = requests.get(ARCHIVE_SEARCH_API, params=params, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                docs = data.get('response', {}).get('docs', [])
                
                for doc in docs:
                    identifier = doc.get('identifier')
                    if not identifier:
                        continue
                    
                    title = doc.get('title', identifier)
                    if isinstance(title, list):
                        title = title[0] if title else identifier
                        
                    description = doc.get('description', '')
                    if isinstance(description, list):
                        description = ' '.join(str(x) for x in description[:3])
                    
                    results.append({
                        'title': str(title),
                        'url': f"https://archive.org/details/{identifier}",
                        'snippet': str(description)[:300] if description else f"Archive.org: {title}",
                        'source': 'archive.org',
                        'engine': 'archive.org',
                        'mediatype': doc.get('mediatype', 'unknown'),
                        'date': doc.get('date', ''),
                        'creator': doc.get('creator', ''),
                    })
            else:
                logger.warning(f"Archive.org API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Archive.org search error: {e}")
        
        logger.info(f"Archive.org search: {len(results)} results")
        return results

    def search_wayback_cdx(self, url_pattern: str, max_results: int = 100) -> List[Dict]:
        """
        Search Wayback Machine CDX for URL patterns.
        
        Args:
            url_pattern: URL or pattern (e.g., '*.example.com/*')
            max_results: Max results
            
        Returns:
            List of archived page results
        """
        results = []
        
        try:
            params = {
                'url': url_pattern,
                'matchType': 'prefix' if '*' in url_pattern else 'exact',
                'output': 'json',
                'limit': max_results,
                'fl': 'timestamp,original,mimetype,statuscode,length',
                'filter': 'statuscode:200',
                'collapse': 'urlkey',  # Dedupe by URL
            }
            
            response = requests.get(CDX_API, params=params, timeout=60)
            
            if response.status_code == 200:
                lines = response.json()
                
                # First line is header
                if lines and len(lines) > 1:
                    for row in lines[1:]:
                        if len(row) >= 5:
                            timestamp, original, mimetype, status, length = row[:5]
                            
                            # Format wayback URL
                            wayback_url = f"{WAYBACK_URL}/{timestamp}/{original}"
                            
                            results.append({
                                'title': f"Archived: {original}",
                                'url': wayback_url,
                                'original_url': original,
                                'snippet': f"Archived on {timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
                                'source': 'wayback',
                                'engine': 'archive.org',
                                'timestamp': timestamp,
                                'mimetype': mimetype,
                                '_archived': True,
                            })
                            
        except Exception as e:
            logger.error(f"Wayback CDX error: {e}")
        
        logger.info(f"Wayback CDX: {len(results)} results for {url_pattern}")
        return results


class ExactPhraseRecallRunnerArchiveOrg:
    """
    Archive.org Max Recall Runner
    
    Searches:
    1. Archive.org items (texts, web, audio, video, etc.)
    2. Wayback Machine CDX (if query looks like a URL)
    3. Multiple query variations for max coverage
    """
    
    def __init__(self, archive: ArchiveOrgSearch = None):
        self.client = archive or ArchiveOrgSearch()
    
    def run(self, phrase: str, tier: int = 3, max_workers: int = 10) -> List[Dict]:
        """
        Execute max recall search.
        
        Args:
            phrase: Search phrase
            tier: Search intensity (1-3)
            max_workers: Parallel workers
            
        Returns:
            Deduplicated results
        """
        if tier == 1:
            return self._tier1_basic(phrase)
        elif tier == 2:
            return self._tier2_expanded(phrase, max_workers)
        else:
            return self._tier3_max_recall(phrase, max_workers)
    
    def _tier1_basic(self, phrase: str) -> List[Dict]:
        """Tier 1: Basic search."""
        return self.client.search(f'"{phrase}"', max_results=100)
    
    def _tier2_expanded(self, phrase: str, max_workers: int) -> List[Dict]:
        """Tier 2: Expanded search with title/description."""
        all_results = []
        seen_urls = set()
        
        queries = [
            f'"{phrase}"',
            f'title:"{phrase}"',
            f'description:"{phrase}"',
            f'creator:"{phrase}"',
        ]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.client.search, q, 100) for q in queries]
            
            for future in as_completed(futures):
                try:
                    for r in future.result():
                        url = r.get('url')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(r)
                except Exception as e:
                    logger.warning(f"Tier 2 query failed: {e}")
        
        return all_results
    
    def _tier3_max_recall(self, phrase: str, max_workers: int) -> List[Dict]:
        """
        Tier 3: MAXIMUM RECALL
        - All mediatypes
        - Multiple query variations
        - Title, description, creator fields
        - Wayback CDX if phrase looks like URL/domain
        """
        all_results = []
        seen_urls = set()
        
        # Build query variations
        queries = []
        
        # Exact phrase variations
        queries.append(f'"{phrase}"')
        queries.append(f'title:"{phrase}"')
        queries.append(f'description:"{phrase}"')
        queries.append(f'creator:"{phrase}"')
        queries.append(f'subject:"{phrase}"')
        
        # Per-mediatype searches for broader coverage
        for mediatype in MEDIATYPES:
            queries.append(f'"{phrase}" AND mediatype:{mediatype}')
        
        # Date ranges (last year, 5 years, 10 years, all time)
        current_year = datetime.now().year
        queries.append(f'"{phrase}" AND year:[{current_year-1} TO {current_year}]')
        queries.append(f'"{phrase}" AND year:[{current_year-5} TO {current_year}]')
        queries.append(f'"{phrase}" AND year:[{current_year-10} TO {current_year}]')
        
        logger.info(f"Archive.org Tier 3: Executing {len(queries)} query variations")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            for query in queries:
                future = executor.submit(self.client.search, query, 100)
                futures[future] = query
            
            for future in as_completed(futures):
                query = futures[future]
                try:
                    results = future.result()
                    new_count = 0
                    for r in results:
                        url = r.get('url')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append(r)
                            new_count += 1
                    if new_count > 0:
                        logger.debug(f"Archive.org +{new_count} from: {query[:50]}...")
                except Exception as e:
                    logger.warning(f"Query failed: {e}")
        
        # If phrase looks like URL/domain, also search Wayback CDX
        if '.' in phrase and ' ' not in phrase:
            try:
                cdx_results = self.client.search_wayback_cdx(f"*{phrase}*", max_results=200)
                for r in cdx_results:
                    url = r.get('url')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(r)
            except Exception as e:
                logger.warning(f"Wayback CDX failed: {e}")
        
        logger.info(f"Archive.org Tier 3 complete: {len(all_results)} unique results")
        return all_results


# Aliases for compatibility
ArchiveSearch = ArchiveOrgSearch
ExactPhraseRecallRunnerArchiveorg = ExactPhraseRecallRunnerArchiveOrg
