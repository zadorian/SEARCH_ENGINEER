"""
Configuration file for Ultimate InDom Search Tool
Contains all API keys and settings

IMPORTANT: API keys are loaded from environment variables.
Copy .env.example to .env and add your API keys there.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the same directory as this config file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Google Custom Search API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Bing Search API
BING_API_KEY = os.getenv("BING_API_KEY")
BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/search"

# Brave Search API
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

# WhoisXML API
WHOISXML_API_KEY = os.getenv("WHOISXML_API_KEY")

# Ahrefs API
AHREFS_API_KEY = os.getenv("AHREFS_API_KEY")

# OpenAI API (GPT-5-nano)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Firecrawl API (optional)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Validate required API keys
_REQUIRED_KEYS = {
    "GOOGLE_API_KEY": GOOGLE_API_KEY,
    "GOOGLE_CSE_ID": GOOGLE_CSE_ID,
    "BING_API_KEY": BING_API_KEY,
    "OPENAI_API_KEY": OPENAI_API_KEY,
}

_missing_keys = [key for key, value in _REQUIRED_KEYS.items() if not value]
if _missing_keys:
    raise ValueError(
        f"Missing required API keys: {', '.join(_missing_keys)}\n"
        f"Please copy .env.example to .env and add your API keys."
    )

# Search Settings
DEFAULT_NUM_RESULTS = 200
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 10  # seconds

# Performance Settings
CONNECTION_LIMIT = 100  # Total connections
CONNECTION_LIMIT_PER_HOST = 10  # Connections per host
ENABLE_DNS_CACHE = True  # Cache DNS lookups
SEMAPHORE_LIMIT = 10  # Max concurrent requests per API

# Timeout Settings (optimized for speed)
DOMAIN_CHECK_TIMEOUT = 2  # Domain live/dead check (reduced from 5s)
API_REQUEST_TIMEOUT = 8  # API requests
WAYBACK_TIMEOUT = 15  # Wayback can be slow

# Early Termination
MAX_RESULTS_PER_SOURCE = 200  # Stop search after this many results
ENABLE_EARLY_TERMINATION = True  # Stop when enough results found

# Country TLDs for targeted searching
COUNTRY_TLDS = [
    # Major European markets
    'uk', 'de', 'fr', 'es', 'it', 'nl', 'pl', 'se',
    # Secondary European markets
    'at', 'ch', 'be', 'dk', 'no', 'fi', 'pt', 'ie',
    # Eastern European markets
    'cz', 'hu', 'ro', 'sk', 'bg', 'hr', 'si',
    # Baltic states
    'ee', 'lv', 'lt',
    # Major global markets
    'us', 'ca', 'au', 'nz', 'in', 'sg', 'jp', 'cn', 'br', 'mx', 'za'
]

# Domain variations for searching
DOMAIN_VARIATIONS = [
    '.com', '.org', '.net', '.edu', '.gov', '.io', '.ai',
    '.co', '.ac', '.mil', '.info', '.biz'
]

# Language codes for Google
LANGUAGE_CODES = [
    'en', 'de', 'fr', 'es', 'it', 'nl', 'pl', 'sv',
    'da', 'fi', 'no', 'cs', 'hu', 'ro', 'sk', 'bg', 'hr', 'sl'
]

# Bing market codes
BING_MARKET_CODES = [
    'en-US', 'en-GB', 'de-DE', 'fr-FR', 'es-ES', 'it-IT',
    'nl-NL', 'pl-PL', 'sv-SE', 'da-DK', 'fi-FI', 'nb-NO'
]

# GPT-5-nano settings
GPT_MODEL = "gpt-5-nano"
GPT_MAX_TOKENS = 4096
GPT_TEMPERATURE = 0.3  # Lower for more consistent URL cleaning
