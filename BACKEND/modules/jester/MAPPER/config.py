"""
JESTER MAPPER - Configuration
==============================

Centralized configuration for all URL discovery sources.
API keys loaded from project root .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# =============================================================================
# API KEYS (from .env)
# =============================================================================

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
WHOISXML_API_KEY = os.getenv("WHOISXML_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")  # Bing via SerpAPI
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
MAJESTIC_API_KEY = os.getenv("MAJESTIC_API_KEY")

# Elasticsearch
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
ES_INDEX_WEBGRAPH = os.getenv("ES_INDEX_WEBGRAPH", "cc_webgraph")


# =============================================================================
# FIRECRAWL CONFIGURATION
# =============================================================================

FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"

FIRECRAWL_MAP_CONFIG = {
    "ignoreSitemap": False,
    "includeSubdomains": True,
    "limit": 100000,  # Up to 100K URLs
}

# 30 days in milliseconds (max allowed by Firecrawl) = 500% speed boost from cache
FIRECRAWL_MAX_AGE_MS = 2592000000  # 30 * 24 * 60 * 60 * 1000

FIRECRAWL_CRAWL_CONFIG = {
    "maxConcurrency": 100,  # 100-parallel subscription
    "crawlEntireDomain": True,
    "allowSubdomains": True,
    "limit": 50000,
    "scrapeOptions": {
        "formats": ["links", "html"],  # Get links AND html to extract all assets
        "maxAge": FIRECRAWL_MAX_AGE_MS,  # Use cached content for 500% speed boost
    },
}

FIRECRAWL_SCRAPE_CONFIG = {
    "formats": ["markdown", "links"],
    "maxAge": FIRECRAWL_MAX_AGE_MS,  # Use cached content for 500% speed boost
}


# =============================================================================
# RATE LIMITS (requests per second)
# =============================================================================

RATE_LIMITS = {
    # Free sources
    "crt.sh": 1,           # Be nice to free service
    "sublist3r": 0.5,      # Very slow, limited
    "dnsdumpster": 0.2,    # Very slow
    "wayback": 5,          # Internet Archive is generous
    "commoncrawl": 10,     # CC Index is fast
    "sitemap": 10,         # Just HTTP fetch
    "robots": 10,          # Just HTTP fetch

    # Paid sources
    "firecrawl": 100,      # 100-parallel subscription
    "whoisxml": 10,        # Paid API
    "google": 1,           # Limited free tier
    "bing": 3,             # Limited free tier
    "brave": 5,            # Generous free tier
    "exa": 5,              # Paid API
    "majestic": 5,         # Paid API

    # Local sources
    "elasticsearch": 100,  # Local ES is fast
}


# =============================================================================
# TWO-MODE SOURCE SYSTEM: FAST vs THOROUGH
# =============================================================================
# THOROUGH (default) = FAST + SLOW sources - runs everything, fast results stream first
# FAST = quick sources only for rapid scanning

# FAST sources (complete in <10 seconds)
FAST_SOURCES = [
    "sitemap",        # <1s - just HTTP fetch
    "elasticsearch",  # <1s - local ES query
    "crt.sh",         # 1-3s - certificate transparency
    "firecrawl_map",  # 2-5s - fast site mapping
    "google",         # 2-5s - search API
    "bing",           # 2-5s - search via SerpAPI
    "brave",          # 2-5s - search API
    "duckduckgo",     # 2-5s - HTML scraping
]

# SLOW sources (10 seconds to 5+ minutes)
SLOW_SOURCES = [
    "whoisxml",        # 5-15s - subdomain API
    "exa",             # 5-10s - semantic search
    "cc_webgraph",     # 5-15s - local ES backlinks
    "wayback",         # 10-30s - archive.org CDX
    "majestic",        # 10-30s - backlink API
    "commoncrawl",     # 30-60s - CC index API
    "sublist3r",       # 30-120s - multi-source subdomain
    "dnsdumpster",     # 30-60s - DNS recon
    "firecrawl_crawl", # 60-300s - deep recursive crawl
]

# THOROUGH = ALL sources (default mode)
# Fast sources complete first naturally, slow ones stream in later
THOROUGH_SOURCES = FAST_SOURCES + SLOW_SOURCES

# Alias for backwards compatibility
ALL_SOURCES = THOROUGH_SOURCES

# Source priority for queue ordering (lower = higher priority = processed first)
SOURCE_PRIORITY = {
    # Fast sources get priority 1
    **{src: 1 for src in FAST_SOURCES},
    # Slow sources get priority 10
    **{src: 10 for src in SLOW_SOURCES},
}

# Free mode: Only sources that don't cost money
FREE_SOURCES = [
    "crt.sh", "sublist3r", "dnsdumpster",
    "wayback", "commoncrawl",
    "sitemap",
    "duckduckgo",
    "cc_webgraph",
    "elasticsearch",
]

# Subdomain-only mode
SUBDOMAIN_SOURCES = [
    "crt.sh", "whoisxml", "sublist3r", "dnsdumpster",
]


# =============================================================================
# TIMEOUTS (seconds)
# =============================================================================

TIMEOUTS = {
    "default": 30,
    "crt.sh": 60,
    "sublist3r": 120,
    "firecrawl_map": 300,
    "firecrawl_crawl": 600,
    "wayback": 120,
    "commoncrawl": 180,
}


# =============================================================================
# DEDUPLICATION
# =============================================================================

# SQLite database for URL deduplication
DEDUP_DB_PATH = PROJECT_ROOT / "BACKEND" / "modules" / "JESTER" / "MAPPER" / "data" / "seen_urls.db"

# In-memory dedup threshold (switch to SQLite above this)
DEDUP_MEMORY_THRESHOLD = 10000
