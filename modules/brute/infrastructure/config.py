#!/usr/bin/env python3
"""
Configuration loader for Search_Engineer
Handles environment variables and API keys
"""

import os
from typing import Dict, Optional, Any
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for Search_Engineer"""
    
    # API Keys
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
    GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID', '')
    BING_API_KEY = os.getenv('BING_API_KEY', '')
    YANDEX_API_KEY = os.getenv('YANDEX_API_KEY', '')
    BRAVE_API_KEY = os.getenv('BRAVE_API_KEY', '')
    EXA_API_KEY = os.getenv('EXA_API_KEY', '')
    NEWSAPI_KEY = os.getenv('NEWSAPI_KEY', '')
    PUBLICWWW_API_KEY = os.getenv('PUBLICWWW_API_KEY', '')
    SOCIALSEARCHER_API_KEY = os.getenv('SOCIALSEARCHER_API_KEY', '')
    GDELT_API_KEY = os.getenv('GDELT_API_KEY', '')
    ARCHIVE_ORG_EMAIL = os.getenv('ARCHIVE_ORG_EMAIL', '')
    XAI_API_KEY = os.getenv('XAI_API_KEY', '')
    ALEPH_API_KEY = os.getenv('ALEPH_API_KEY', '')
    FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY', '')
    
    # Rate Limiting
    MAX_CONCURRENT_ENGINES = int(os.getenv('MAX_CONCURRENT_ENGINES', '5'))
    MAX_RESULTS_PER_ENGINE = int(os.getenv('MAX_RESULTS_PER_ENGINE', '1000'))
    REQUEST_DELAY_SECONDS = float(os.getenv('REQUEST_DELAY_SECONDS', '1'))
    
    # Output Configuration
    DEFAULT_OUTPUT_FORMAT = os.getenv('DEFAULT_OUTPUT_FORMAT', 'json')
    DEFAULT_OUTPUT_DIR = os.getenv('DEFAULT_OUTPUT_DIR', './results')
    ENABLE_STREAMING = os.getenv('ENABLE_STREAMING', 'true').lower() == 'true'
    
    # Proxy Configuration
    HTTP_PROXY = os.getenv('HTTP_PROXY', '')
    HTTPS_PROXY = os.getenv('HTTPS_PROXY', '')
    NO_PROXY = os.getenv('NO_PROXY', 'localhost,127.0.0.1')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'search_engineer.log')
    ENABLE_DEBUG_MODE = os.getenv('ENABLE_DEBUG_MODE', 'false').lower() == 'true'
    
    # Search Configuration
    DEFAULT_LANGUAGE = os.getenv('DEFAULT_LANGUAGE', 'en')
    DEFAULT_COUNTRY = os.getenv('DEFAULT_COUNTRY', 'US')
    SAFE_SEARCH = os.getenv('SAFE_SEARCH', 'off')
    INCLUDE_SIMILAR_RESULTS = os.getenv('INCLUDE_SIMILAR_RESULTS', 'false').lower() == 'true'
    
    # Performance Configuration
    CACHE_ENABLED = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
    CACHE_EXPIRY_HOURS = int(os.getenv('CACHE_EXPIRY_HOURS', '24'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    TIMEOUT_SECONDS = int(os.getenv('TIMEOUT_SECONDS', '30'))
    
    # Query Expansion Configuration
    ENABLE_QUERY_EXPANSION = os.getenv('ENABLE_QUERY_EXPANSION', 'false').lower() == 'true'
    TARGET_RESULTS_PER_QUERY = int(os.getenv('TARGET_RESULTS_PER_QUERY', '10000'))
    ENABLE_PAGINATION = os.getenv('ENABLE_PAGINATION', 'false').lower() == 'true'
    MAX_PAGES_PER_ENGINE = int(os.getenv('MAX_PAGES_PER_ENGINE', '10'))
    
    # Engine-Specific Settings
    RESULTS_PER_PAGE_GOOGLE = int(os.getenv('RESULTS_PER_PAGE_GOOGLE', '100'))
    RESULTS_PER_PAGE_BING = int(os.getenv('RESULTS_PER_PAGE_BING', '50'))
    RESULTS_PER_PAGE_YANDEX = int(os.getenv('RESULTS_PER_PAGE_YANDEX', '100'))
    
    # Exception Search Configuration
    ENABLE_EXCEPTION_SEARCH = os.getenv('ENABLE_EXCEPTION_SEARCH', 'true').lower() == 'true'
    EXCEPTION_SEARCH_DELAY = float(os.getenv('EXCEPTION_SEARCH_DELAY', '0'))
    MAX_DOMAIN_EXCLUSIONS = int(os.getenv('MAX_DOMAIN_EXCLUSIONS', '50'))
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    REDIS_URL = os.getenv('REDIS_URL', '')
    
    # Feature Flags
    ENABLE_DATE_SEARCH = os.getenv('ENABLE_DATE_SEARCH', 'true').lower() == 'true'
    ENABLE_URL_SEARCH = os.getenv('ENABLE_URL_SEARCH', 'true').lower() == 'true'
    ENABLE_DEDUPLICATION = os.getenv('ENABLE_DEDUPLICATION', 'true').lower() == 'true'
    ENABLE_PARALLEL_EXECUTION = os.getenv('ENABLE_PARALLEL_EXECUTION', 'true').lower() == 'true'
    
    @classmethod
    def get_api_key(cls, engine_code: str) -> Optional[str]:
        """Get API key for a specific engine"""
        api_key_map = {
            'GO': cls.GOOGLE_API_KEY,
            'BI': cls.BING_API_KEY,
            'YA': cls.YANDEX_API_KEY,
            'BR': cls.BRAVE_API_KEY,
            'EX': cls.EXA_API_KEY,
            'NA': cls.NEWSAPI_KEY,
            'PW': cls.PUBLICWWW_API_KEY,
            'SS': cls.SOCIALSEARCHER_API_KEY,
            'GD': cls.GDELT_API_KEY,
            'GR': cls.XAI_API_KEY,
            'AL': cls.ALEPH_API_KEY,
        }
        return api_key_map.get(engine_code, '')
    
    @classmethod
    def get_proxy_config(cls) -> Dict[str, Optional[str]]:
        """Get proxy configuration"""
        proxies = {}
        if cls.HTTP_PROXY:
            proxies['http'] = cls.HTTP_PROXY
        if cls.HTTPS_PROXY:
            proxies['https'] = cls.HTTPS_PROXY
        return proxies if proxies else None
    
    @classmethod
    def validate_config(cls) -> Dict[str, bool]:
        """Validate configuration and return status"""
        status = {}
        
        # Check API keys
        api_keys = {
            'Google': cls.GOOGLE_API_KEY,
            'Bing': cls.BING_API_KEY,
            'Yandex': cls.YANDEX_API_KEY,
            'Brave': cls.BRAVE_API_KEY,
            'Exa': cls.EXA_API_KEY,
            'NewsAPI': cls.NEWSAPI_KEY,
            'PublicWWW': cls.PUBLICWWW_API_KEY,
            'SocialSearcher': cls.SOCIALSEARCHER_API_KEY,
            'GDELT': cls.GDELT_API_KEY,
        }
        
        for name, key in api_keys.items():
            status[f'{name}_API'] = bool(key)
        
        # Check other configurations
        status['Output_Directory'] = os.path.exists(cls.DEFAULT_OUTPUT_DIR) or True
        status['Proxy_Config'] = bool(cls.HTTP_PROXY or cls.HTTPS_PROXY)
        
        return status
    
    @classmethod
    def print_config_status(cls):
        """Print configuration status"""
        print("\nSearch_Engineer Configuration Status")
        print("=" * 40)
        
        status = cls.validate_config()
        for key, value in status.items():
            status_str = "✓ Configured" if value else "✗ Not configured"
            print(f"{key:.<30} {status_str}")
        
        print("\nFeature Flags:")
        print(f"  Date Search:........... {'Enabled' if cls.ENABLE_DATE_SEARCH else 'Disabled'}")
        print(f"  URL Search:............ {'Enabled' if cls.ENABLE_URL_SEARCH else 'Disabled'}")
        print(f"  Deduplication:......... {'Enabled' if cls.ENABLE_DEDUPLICATION else 'Disabled'}")
        print(f"  Parallel Execution:.... {'Enabled' if cls.ENABLE_PARALLEL_EXECUTION else 'Disabled'}")
        print(f"  Streaming:............. {'Enabled' if cls.ENABLE_STREAMING else 'Disabled'}")
        
        print("\nPerformance Settings:")
        print(f"  Max Concurrent Engines: {cls.MAX_CONCURRENT_ENGINES}")
        print(f"  Max Results per Engine: {cls.MAX_RESULTS_PER_ENGINE}")
        print(f"  Request Delay:......... {cls.REQUEST_DELAY_SECONDS}s")
        print(f"  Timeout:............... {cls.TIMEOUT_SECONDS}s")
        print(f"  Max Retries:........... {cls.MAX_RETRIES}")
        
        print("\nQuery Expansion Settings:")
        print(f"  Query Expansion:....... {'Enabled' if cls.ENABLE_QUERY_EXPANSION else 'Disabled'}")
        print(f"  Target Results:........ {cls.TARGET_RESULTS_PER_QUERY}")
        print(f"  Pagination:............ {'Enabled' if cls.ENABLE_PAGINATION else 'Disabled'}")
        print(f"  Max Pages per Engine:.. {cls.MAX_PAGES_PER_ENGINE}")


if __name__ == '__main__':
    # Print configuration status when run directly
    Config.print_config_status()