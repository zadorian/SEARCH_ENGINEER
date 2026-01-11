"""
archiveorg.py
Wrapper for Internet Archive Search API
"""

import logging
import time
from typing import List, Dict, Optional
import requests
try:
    import internetarchive as ia
except ImportError:
    ia = None

logger = logging.getLogger(__name__)

class ArchiveOrgSearch:
    """Search wrapper for Archive.org"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        if not ia:
            logger.warning("internetarchive library not installed. Functionality will be limited.")

    def search(self, archive_query_string: str, max_results: int = 50) -> List[Dict]:
        """
        Search Archive.org using query string.
        
        Args:
            archive_query_string: Advanced search query (e.g. 'title:("exact phrase")')
            max_results: Maximum results to return
            
        Returns:
            List of dicts with 'title', 'url', 'snippet', etc.
        """
        results = []
        
        if not ia:
            logger.error("Cannot search: internetarchive library missing")
            return []
            
        try:
            # Use internetarchive library search
            # search_items yields Item objects
            search = ia.search_items(archive_query_string)
            
            count = 0
            for result in search.iter_as_results():
                if count >= max_results:
                    break
                
                # item is a dict in iter_as_results
                identifier = result.get('identifier')
                if not identifier:
                    continue
                    
                title = result.get('title', identifier)
                description = result.get('description', '')
                if isinstance(description, list):
                    description = " ".join(str(x) for x in description)
                
                # Construct URL
                url = f"https://archive.org/details/{identifier}"
                
                # Get mediatype/format
                mediatype = result.get('mediatype', 'unknown')
                
                results.append({
                    'title': title,
                    'url': url,
                    'snippet': description[:300] if description else f"Archive.org item: {title}",
                    'source': 'archive.org',
                    'mediatype': mediatype,
                    'date': result.get('date', ''),
                    'creator': result.get('creator', '')
                })
                count += 1
                
        except Exception as e:
            logger.error(f"Archive.org search error: {e}")
            
        return results
