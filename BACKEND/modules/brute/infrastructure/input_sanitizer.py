#!/usr/bin/env python3
"""
Input Sanitization and Validation for targeted_searches
Provides security measures to prevent injection attacks and malicious input
"""

import re
import html
import urllib.parse
from typing import Dict, List, Optional, Any, Union
import logging

logger = logging.getLogger(__name__)

class InputSanitizer:
    """
    Comprehensive input sanitization for search queries and parameters
    """
    
    # Dangerous patterns that should be blocked
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',               # JavaScript URLs
        r'data:',                     # Data URLs
        r'vbscript:',                # VBScript URLs
        r'onload\s*=',               # Event handlers
        r'onerror\s*=',
        r'onclick\s*=',
        r'onmouseover\s*=',
        r'eval\s*\(',                # Eval function
        r'expression\s*\(',          # CSS expression
        r'import\s+\w+',             # Python imports
        r'exec\s*\(',                # Exec function
        r'system\s*\(',              # System calls
        r'subprocess\.',             # Subprocess module
        r'__import__',               # Dynamic imports
        r'file://',                  # File URLs
        r'\.\./\.\.',                # Directory traversal
        r'\.\.\\\.\.\\',             # Windows path traversal
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'union\s+select',
        r'drop\s+table',
        r'delete\s+from',
        r'insert\s+into',
        r'update\s+\w+\s+set',
        r';.*--',                    # SQL comments
        r"'.*or.*'.*'",              # OR injection
        r'".*or.*".*"',              # OR injection with quotes
    ]
    
    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r';.*?rm\s+',
        r';.*?cat\s+',
        r';.*?curl\s+',
        r';.*?wget\s+',
        r'\|\s*nc\s+',               # Netcat piping
        r'&&\s*rm\s+',
        r'\|\|\s*rm\s+',
        r'`.*`',                     # Backtick execution
        r'\$\(.*\)',                 # Command substitution
    ]
    
    # Maximum lengths for different input types
    MAX_LENGTHS = {
        'query': 1000,
        'url': 2000,
        'domain': 253,
        'filename': 255,
        'parameter': 500,
        'general': 1000
    }
    
    @classmethod
    def sanitize_search_query(cls, query: str) -> str:
        """
        Sanitize a search query for safe processing
        
        Args:
            query: Raw search query string
            
        Returns:
            Sanitized query string
            
        Raises:
            ValueError: If query contains dangerous patterns
        """
        if not isinstance(query, str):
            raise ValueError("Query must be a string")
        
        # Check length
        if len(query) > cls.MAX_LENGTHS['query']:
            raise ValueError(f"Query too long: {len(query)} > {cls.MAX_LENGTHS['query']}")
        
        # Check for dangerous patterns
        cls._check_dangerous_patterns(query, 'search query')
        
        # Basic sanitization
        sanitized = query.strip()
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        # HTML decode (in case of double encoding)
        sanitized = html.unescape(sanitized)
        
        # Remove control characters except normal whitespace
        sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        logger.debug(f"Sanitized query: '{query}' -> '{sanitized}'")
        return sanitized
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """
        Sanitize a URL for safe processing
        
        Args:
            url: Raw URL string
            
        Returns:
            Sanitized URL string
            
        Raises:
            ValueError: If URL contains dangerous patterns
        """
        if not isinstance(url, str):
            raise ValueError("URL must be a string")
        
        # Check length
        if len(url) > cls.MAX_LENGTHS['url']:
            raise ValueError(f"URL too long: {len(url)} > {cls.MAX_LENGTHS['url']}")
        
        # Check for dangerous patterns
        cls._check_dangerous_patterns(url, 'URL')
        
        # Basic sanitization
        sanitized = url.strip()
        
        # Ensure it starts with http/https
        if sanitized and not re.match(r'^https?://', sanitized):
            if '://' in sanitized:
                raise ValueError("Invalid URL scheme")
            sanitized = 'https://' + sanitized
        
        # URL encode dangerous characters
        try:
            parsed = urllib.parse.urlparse(sanitized)
            # Reconstruct with safe components
            sanitized = urllib.parse.urlunparse(parsed)
        except Exception:
            raise ValueError("Invalid URL format")
        
        return sanitized
    
    @classmethod
    def sanitize_parameter(cls, param: Any, param_type: str = 'general') -> Union[str, int, float, bool]:
        """
        Sanitize a parameter value based on its type
        
        Args:
            param: Parameter value
            param_type: Type of parameter ('general', 'domain', 'filename', etc.)
            
        Returns:
            Sanitized parameter value
            
        Raises:
            ValueError: If parameter contains dangerous patterns
        """
        if param is None:
            return None
        
        # Handle different types
        if isinstance(param, bool):
            return param
        elif isinstance(param, (int, float)):
            return param
        elif isinstance(param, str):
            # Check length
            max_len = cls.MAX_LENGTHS.get(param_type, cls.MAX_LENGTHS['general'])
            if len(param) > max_len:
                raise ValueError(f"Parameter too long: {len(param)} > {max_len}")
            
            # Check for dangerous patterns
            cls._check_dangerous_patterns(param, f'{param_type} parameter')
            
            # Basic sanitization
            sanitized = param.strip()
            sanitized = sanitized.replace('\x00', '')
            sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', sanitized)
            
            return sanitized
        else:
            raise ValueError(f"Unsupported parameter type: {type(param)}")
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize all values in a dictionary
        
        Args:
            data: Dictionary to sanitize
            
        Returns:
            Dictionary with sanitized values
        """
        if not isinstance(data, dict):
            raise ValueError("Data must be a dictionary")
        
        sanitized = {}
        for key, value in data.items():
            # Sanitize key
            clean_key = cls.sanitize_parameter(key, 'parameter')
            
            # Sanitize value based on key name
            if key.lower() in ['url', 'link', 'href']:
                clean_value = cls.sanitize_url(value) if isinstance(value, str) else value
            elif key.lower() in ['query', 'q', 'search']:
                clean_value = cls.sanitize_search_query(value) if isinstance(value, str) else value
            else:
                clean_value = cls.sanitize_parameter(value)
            
            sanitized[clean_key] = clean_value
        
        return sanitized
    
    @classmethod
    def _check_dangerous_patterns(cls, text: str, context: str = 'input'):
        """
        Check text against dangerous patterns
        
        Args:
            text: Text to check
            context: Context for error messages
            
        Raises:
            ValueError: If dangerous patterns are found
        """
        text_lower = text.lower()
        
        # Check dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE | re.DOTALL):
                logger.warning(f"Dangerous pattern detected in {context}: {pattern}")
                raise ValueError(f"Dangerous pattern detected in {context}")
        
        # Check SQL injection patterns
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"SQL injection pattern detected in {context}: {pattern}")
                raise ValueError(f"SQL injection attempt detected in {context}")
        
        # Check command injection patterns
        for pattern in cls.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.warning(f"Command injection pattern detected in {context}: {pattern}")
                raise ValueError(f"Command injection attempt detected in {context}")


class SecureSearchRequest:
    """
    Wrapper for search requests with built-in sanitization
    """
    
    def __init__(self, query: str, engines: Optional[List[str]] = None, 
                 max_results: Optional[int] = None, **kwargs):
        """
        Initialize secure search request
        
        Args:
            query: Search query
            engines: List of engine codes
            max_results: Maximum results
            **kwargs: Additional parameters
        """
        self.query = InputSanitizer.sanitize_search_query(query)
        self.engines = self._sanitize_engines(engines)
        self.max_results = self._sanitize_max_results(max_results)
        self.parameters = InputSanitizer.sanitize_dict(kwargs)
    
    def _sanitize_engines(self, engines: Optional[List[str]]) -> List[str]:
        """Sanitize engine list"""
        if not engines:
            return []
        
        if not isinstance(engines, list):
            raise ValueError("Engines must be a list")
        
        sanitized = []
        for engine in engines:
            clean_engine = InputSanitizer.sanitize_parameter(engine, 'parameter')
            # Validate engine code format (2-3 uppercase letters)
            if not re.match(r'^[A-Z]{2,3}$', clean_engine):
                raise ValueError(f"Invalid engine code: {clean_engine}")
            sanitized.append(clean_engine)
        
        return sanitized
    
    def _sanitize_max_results(self, max_results: Optional[int]) -> Optional[int]:
        """Sanitize max results parameter"""
        if max_results is None:
            return None
        
        if not isinstance(max_results, int):
            try:
                max_results = int(max_results)
            except (ValueError, TypeError):
                raise ValueError("max_results must be an integer")
        
        # Reasonable limits
        if max_results < 1 or max_results > 10000:
            raise ValueError("max_results must be between 1 and 10000")
        
        return max_results
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls"""
        result = {
            'query': self.query,
            'engines': self.engines,
            'max_results': self.max_results
        }
        result.update(self.parameters)
        return result


# Convenience functions
def sanitize_search_input(query: str, **kwargs) -> SecureSearchRequest:
    """
    Create a secure search request from raw input
    
    Args:
        query: Raw search query
        **kwargs: Additional parameters
        
    Returns:
        SecureSearchRequest object
    """
    return SecureSearchRequest(query, **kwargs)


def validate_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and sanitize search results
    
    Args:
        results: List of search result dictionaries
        
    Returns:
        List of sanitized search results
    """
    if not isinstance(results, list):
        raise ValueError("Results must be a list")
    
    sanitized_results = []
    for result in results:
        try:
            sanitized_result = InputSanitizer.sanitize_dict(result)
            sanitized_results.append(sanitized_result)
        except ValueError as e:
            logger.warning(f"Skipping invalid result: {e}")
            continue
    
    return sanitized_results


# Example usage and testing
if __name__ == "__main__":
    # Test sanitization
    test_queries = [
        "normal search query",
        "query with <script>alert('xss')</script>",
        "query' OR '1'='1",
        "query; rm -rf /",
        "query`cat /etc/passwd`",
        "very " * 200 + "long query",  # Too long
    ]
    
    for query in test_queries:
        try:
            sanitized = InputSanitizer.sanitize_search_query(query)
            print(f"✅ '{query[:50]}...' -> '{sanitized[:50]}...'")
        except ValueError as e:
            print(f"❌ '{query[:50]}...' -> ERROR: {e}")
