#!/usr/bin/env python3
"""
Strict URL validation for filetype searches
Ensures that results actually match the requested file type
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


class FiletypeURLValidator:
    """Validates that URLs actually contain the requested file extensions"""
    
    def __init__(self):
        # Common URL patterns that might contain false positives
        self.false_positive_patterns = [
            r'/pdf[\w-]*/(?!.*\.pdf)',  # URLs with /pdf/ in path but no .pdf file
            r'/documents?/(?!.*\.pdf)',  # Document folders without actual PDFs
            r'/files?/(?!.*\.pdf)',      # File folders without actual PDFs
            r'[?&].*pdf.*(?!\.pdf)',     # Query parameters mentioning pdf
            r'#.*pdf.*(?!\.pdf)',        # Fragments mentioning pdf
        ]
        
        # Compile patterns for efficiency
        self.false_positive_regexes = [re.compile(p, re.IGNORECASE) for p in self.false_positive_patterns]
        
        # Valid file extension patterns (must be at end of path, before query/fragment)
        self.valid_extension_pattern = re.compile(
            r'\.({ext})(?:\?|#|$)',  # Extension followed by ?, #, or end of string
            re.IGNORECASE
        )
    
    def validate_url_filetype(self, url: str, extensions: List[str]) -> bool:
        """
        Strictly validate that URL contains one of the requested file extensions
        
        Args:
            url: URL to validate
            extensions: List of file extensions to check (without dots)
            
        Returns:
            True if URL appears to point to a file with requested extension
        """
        if not url or not extensions:
            return False
            
        # Decode URL to handle encoded characters
        try:
            decoded_url = unquote(url)
        except Exception as e:
            decoded_url = url
            
        # Parse URL to get the path component
        try:
            parsed = urlparse(decoded_url)
            path = parsed.path.lower()
            
            # Special case: URLs ending with just domain should be rejected
            if not path or path == '/':
                return False
                
        except Exception as e:
            logger.warning(f"Failed to parse URL: {url}")
            return False
        
        # Check if any valid extension is present at the end of the path
        ext_pattern = self.valid_extension_pattern.pattern.replace(
            '{ext}', 
            '|'.join(re.escape(ext) for ext in extensions)
        )
        
        if re.search(ext_pattern, path):
            # Found a valid extension, now check for false positives
            for false_positive_regex in self.false_positive_regexes:
                if false_positive_regex.search(decoded_url):
                    logger.debug(f"URL rejected as false positive: {url}")
                    return False
            return True
            
        return False
    
    def extract_filename(self, url: str) -> Optional[str]:
        """Extract the filename from URL if present"""
        try:
            parsed = urlparse(unquote(url))
            path = parsed.path
            
            # Get the last component of the path
            if '/' in path:
                filename = path.split('/')[-1]
            else:
                filename = path
                
            # Only return if it looks like a filename (has extension)
            if '.' in filename and len(filename) > 3:
                return filename
                
        except Exception as e:

            print(f"[BRUTE] Error: {e}")

            pass
            
        return None
    
    def validate_result(self, result: Dict[str, Any], extensions: List[str]) -> bool:
        """
        Validate a search result for filetype match
        
        Checks URL first, then title/snippet for additional validation
        """
        url = result.get('url', '')
        
        # Primary validation: URL must contain the file extension
        if not self.validate_url_filetype(url, extensions):
            return False
            
        # Additional validation: Check if title or snippet suggests it's not a direct file
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        
        # Reject results that appear to be listing pages
        rejection_keywords = [
            'search results',
            'browse',
            'directory',
            'index of',
            'list of',
            'collection of',
            'database',
            'repository'
        ]
        
        combined_text = f"{title} {snippet}"
        if any(keyword in combined_text for keyword in rejection_keywords):
            # But allow if the URL has a clear filename
            filename = self.extract_filename(url)
            if not filename or not any(f".{ext}" in filename.lower() for ext in extensions):
                logger.debug(f"Result rejected due to listing page indicators: {url}")
                return False
                
        return True
    
    def filter_results(self, results: List[Dict[str, Any]], extensions: List[str]) -> List[Dict[str, Any]]:
        """
        Filter a list of results to only include valid filetypes
        
        Returns filtered list and adds validation metadata
        """
        filtered = []
        
        for result in results:
            if self.validate_result(result, extensions):
                # Add validation metadata
                result['filetype_validated'] = True
                result['detected_filename'] = self.extract_filename(result.get('url', ''))
                filtered.append(result)
            else:
                logger.debug(f"Filtered out non-matching result: {result.get('url', '')}")
                
        logger.info(f"Filetype validation: {len(filtered)}/{len(results)} results passed "
                   f"({len(results) - len(filtered)} filtered out)")
        
        return filtered


# Example usage
if __name__ == "__main__":
    validator = FiletypeURLValidator()
    
    # Test cases
    test_urls = [
        # Valid PDFs
        "https://example.com/document.pdf",
        "https://example.com/path/to/file.pdf?param=value",
        "https://example.com/download.pdf#page=1",
        
        # Invalid - not PDFs
        "https://example.com/pdf-generator",
        "https://example.com/pdf/",
        "https://example.com/documents/",
        "https://example.com/search?q=pdf",
        "https://example.com/page#pdf-section",
        "https://example.com/file.html",
    ]
    
    for url in test_urls:
        is_valid = validator.validate_url_filetype(url, ['pdf'])
        print(f"{url}: {'✓' if is_valid else '✗'}")