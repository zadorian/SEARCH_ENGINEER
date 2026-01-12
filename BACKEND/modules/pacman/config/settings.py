"""
PACMAN Configuration - Centralized settings
"""

# === CONCURRENCY ===
CONCURRENT_TIER_A = 500      # httpx (async Python)
CONCURRENT_TIER_B = 100      # Colly (Go)
CONCURRENT_TIER_C = 50       # Rod (Go, headless)
CONCURRENT_BLITZ = 500       # Blitz mode domains
CONCURRENT_REQUESTS = 2000   # Total HTTP connections

# === TIMEOUTS (seconds) ===
TIMEOUT_TIER_A = 10
TIMEOUT_TIER_B = 20
TIMEOUT_TIER_C = 45
TIMEOUT_DEFAULT = 15

# === ELASTICSEARCH ===
ES_HOST = 'http://localhost:9200'
ES_INDEX_TIERED = 'pacman-tiered'
ES_INDEX_CRAWLER = 'pacman-crawl'
ES_INDEX_BLITZ = 'pacman-blitz'
ES_BULK_SIZE = 500

# === PATHS ===
COLLY_BIN = '/data/submarine/bin/colly_crawler_linux'
ROD_BIN = '/data/submarine/bin/rod_crawler_linux'
CHECKPOINT_DIR = '/data/PACMAN/checkpoints'

# === EXTRACTION LIMITS ===
MAX_CONTENT_SCAN = 100000    # Characters to scan
MAX_PERSONS = 30
MAX_COMPANIES = 20
MAX_IDENTIFIERS = 20
MAX_LINKS = 100
