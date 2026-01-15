"""
LINKLATER Configuration

Central configuration for all LINKLATER modules.
Loads from project root .env file.

Logging:
    from modules.linklater.config import get_logger
    logger = get_logger(__name__)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Import logging utilities
from .logging_config import (
    get_logger,
    get_log_level,
    configure_all_loggers,
    log_info,
    log_debug,
    log_warning,
    log_error,
)

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
MAJESTIC_API_KEY = os.getenv("MAJESTIC_API_KEY")

# Elasticsearch
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "linklater")

# Common Crawl
CC_DEFAULT_ARCHIVES = ["CC-MAIN-2024-51", "CC-MAIN-2024-46", "CC-MAIN-2024-42"]
CC_INDEX_SERVER = "https://index.commoncrawl.org"

# Wayback
WAYBACK_CDX_URL = "http://web.archive.org/cdx/search/cdx"

# Timeouts
DEFAULT_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 10

__all__ = [
    # Configuration
    "PROJECT_ROOT",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "FIRECRAWL_API_KEY",
    "MAJESTIC_API_KEY",
    "ES_HOST",
    "ES_INDEX",
    "CC_DEFAULT_ARCHIVES",
    "CC_INDEX_SERVER",
    "WAYBACK_CDX_URL",
    "DEFAULT_TIMEOUT",
    "MAX_CONCURRENT_REQUESTS",
    # Logging
    "get_logger",
    "get_log_level",
    "configure_all_loggers",
    "log_info",
    "log_debug",
    "log_warning",
    "log_error",
]
