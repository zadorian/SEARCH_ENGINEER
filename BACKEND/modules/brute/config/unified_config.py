#!/usr/bin/env python3
"""
Unified Configuration for Brute Search Module
Loads settings from environment and provides defaults
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


class UnifiedConfig:
    """Central configuration for brute search module"""

    def __init__(self):
        # Elasticsearch settings
        # CYMONIDES MANDATE: No default index - use cymonides-1-{project_id} pattern
        self.es_host = os.getenv('ELASTICSEARCH_HOST', 'http://localhost:9200')
        self.es_index = os.getenv('ELASTICSEARCH_INDEX', None)  # DEPRECATED - use project-specific indices
        self.es_username = os.getenv('ELASTICSEARCH_USERNAME', '')
        self.es_password = os.getenv('ELASTICSEARCH_PASSWORD', '')

        # API keys
        self.brave_api_key = os.getenv('BRAVE_API_KEY', '')
        self.google_api_key = os.getenv('GOOGLE_API_KEY', '')
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID', '') or os.getenv('GOOGLE_SEARCH_ENGINE_ID', '')
        self.bing_api_key = os.getenv('BING_API_KEY', '')
        self.exa_api_key = os.getenv('EXA_API_KEY', '')
        self.newsapi_key = os.getenv('NEWSAPI_API_KEY', '') or os.getenv('NEWS_API_KEY', '')
        self.aleph_api_key = os.getenv('ALEPH_API_KEY', '')
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY', '')
        self.majestic_api_key = os.getenv('MAJESTIC_API_KEY', '')
        self.publicwww_api_key = os.getenv('PUBLICWWW_API_KEY', '')

        # Firecrawl
        self.firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY', '')

        # Vector/embeddings
        self.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY', '')
        self.google_genai_key = os.getenv('GOOGLE_GENAI_API_KEY', '')

        # Search defaults
        self.default_max_results = int(os.getenv('DEFAULT_MAX_RESULTS', '50'))
        self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))

        # Cache settings
        self.cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.cache_ttl = int(os.getenv('CACHE_TTL', '3600'))

        # Vector settings
        self.VECTOR_DIMENSIONS = int(os.getenv('VECTOR_DIMENSIONS', '384'))
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')

        # Paths
        self.project_root = PROJECT_ROOT
        self.brute_root = Path(__file__).resolve().parent.parent

    def get(self, key: str, default=None):
        """Get config value by key"""
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        return getattr(self, key)


# Global config instance
config = UnifiedConfig()

__all__ = ['config', 'UnifiedConfig']
