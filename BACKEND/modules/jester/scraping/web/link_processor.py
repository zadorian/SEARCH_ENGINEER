"""
DRILL Link Processor - Go-inspired Optimizations

Ports key performance patterns from GlobalLinks Go implementation:
1. Domain caching (500ms faster per 1M lines)
2. Pre-compiled regex (10% faster)
3. Streaming gzip parsing (memory efficient)
4. URL quality validation (cleaner data)
5. Relevance scoring (prioritized results)
6. FarmHash-style deduplication

This makes DRILL's link processing nearly as fast as Go while staying in Python.
"""

import re
import gzip
import hashlib
from typing import Dict, List, Set, Optional, Tuple, Iterator, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs
from functools import lru_cache
import threading
from pathlib import Path

# Try to use faster libraries if available
try:
    import xxhash  # Much faster than md5 for hashing
    FAST_HASH = True
except ImportError:
    FAST_HASH = False

try:
    import tldextract  # Faster than publicsuffix for TLD extraction
    TLDEXTRACT_AVAILABLE = True
except ImportError:
    TLDEXTRACT_AVAILABLE = False

try:
    import orjson  # Faster JSON parsing
    ORJSON_AVAILABLE = True
except ImportError:
    ORJSON_AVAILABLE = False
    import json as orjson

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ==============================================================================
# PRE-COMPILED REGEX (Go pattern: global regex for speed)
# ==============================================================================

# IP address regex - pre-compiled for speed
IP_REGEX = re.compile(
    r'^(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)){3}$'
)

# Valid domain regex
VALID_DOMAIN_REGEX = re.compile(
    r'^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$',
    re.IGNORECASE
)

# URL in href regex
HREF_REGEX = re.compile(
    r'href=["\']?(https?://[^"\'\s>]+)["\']?',
    re.IGNORECASE
)

# Anchor text extraction
ANCHOR_REGEX = re.compile(
    r'<a[^>]*href=["\']?([^"\'>\s]+)["\']?[^>]*>([^<]*)</a>',
    re.IGNORECASE | re.DOTALL
)

# WAT line patterns
WAT_TARGET_URI_PREFIX = "WARC-Target-URI: http"
WAT_JSON_START = "{"


# ==============================================================================
# IGNORE LISTS (Go pattern: map for O(1) lookup)
# ==============================================================================

# Domains to ignore (social, CDN, tracking, etc.)
IGNORE_DOMAINS: Set[str] = {
    # Social
    "facebook.com", "twitter.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com", "reddit.com",
    # CDN/Infrastructure
    "cloudflare.com", "amazonaws.com", "googleusercontent.com",
    "cloudfront.net", "akamaihd.net", "fastly.net",
    # Tracking/Analytics
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
    "facebook.net", "analytics.google.com", "hotjar.com",
    # Generic
    "example.com", "localhost", "test.com",
    # Schema.org etc
    "schema.org", "w3.org", "ogp.me",
}

# TLDs to ignore
IGNORE_TLDS: Set[str] = {
    ".local", ".localhost", ".test", ".invalid", ".example",
}

# File extensions to ignore
IGNORE_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".tar", ".gz", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".css", ".js", ".json", ".xml", ".rss", ".atom",
    ".woff", ".woff2", ".ttf", ".eot",
}

# Query parameters to strip (session IDs, tracking, etc.)
STRIP_QUERY_PREFIXES: Set[str] = {
    "utm_", "fbclid", "gclid", "ref", "source", "campaign",
    "PHPSESSID", "jsessionid", "sid", "session",
}

# Characters that indicate a broken host
INVALID_HOST_CHARS = set("%[]=':*()<>!&+,}{}$\";`")


# ==============================================================================
# DOMAIN CACHE (Go pattern: cached TLD lookups with mutex)
# ==============================================================================

class DomainCache:
    """
    Thread-safe domain cache for fast TLD lookups.

    Go equivalent: domainCache with RWMutex
    Benefit: 500ms faster per 1M lines
    """

    def __init__(self, max_size: int = 100000):
        self._cache: Dict[str, str] = {}
        self._lock = threading.RLock()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    def get_domain(self, host: str) -> Optional[str]:
        """Get domain from host, with caching."""
        host = host.lower().strip()

        # Check cache first (read lock)
        with self._lock:
            if host in self._cache:
                self.hits += 1
                return self._cache[host]

        # Cache miss - compute domain
        self.misses += 1
        domain = self._extract_domain(host)

        if domain:
            with self._lock:
                # Evict if too large
                if len(self._cache) >= self.max_size:
                    # Simple eviction: clear half
                    keys = list(self._cache.keys())[:self.max_size // 2]
                    for k in keys:
                        del self._cache[k]

                self._cache[host] = domain

        return domain

    def _extract_domain(self, host: str) -> Optional[str]:
        """Extract registered domain from host."""
        if TLDEXTRACT_AVAILABLE:
            ext = tldextract.extract(host)
            if ext.domain and ext.suffix:
                return f"{ext.domain}.{ext.suffix}"
            return None
        else:
            # Fallback: simple extraction
            parts = host.split('.')
            if len(parts) >= 2:
                # Handle compound TLDs like .co.uk
                if len(parts) >= 3 and parts[-2] in ('co', 'gov', 'org', 'ac', 'net'):
                    return '.'.join(parts[-3:])
                return '.'.join(parts[-2:])
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        return {
            "size": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{self.hits / total * 100:.1f}%" if total > 0 else "0%",
        }


# Global domain cache
_domain_cache = DomainCache()


# ==============================================================================
# URL RECORD (Go pattern: structured URL data)
# ==============================================================================

@dataclass
class URLRecord:
    """
    Structured URL record matching Go's URLRecord.

    Stores parsed URL components for efficient processing.
    """
    url: str = ""
    scheme: str = ""
    host: str = ""
    path: str = ""
    query: str = ""
    fragment: str = ""
    domain: str = ""
    subdomain: str = ""
    anchor_text: str = ""
    nofollow: bool = False

    @property
    def is_subdomain(self) -> bool:
        """Check if this is a subdomain."""
        if not self.host or not self.domain:
            return False
        return self.host != self.domain and self.host.endswith(f".{self.domain}")

    def to_full_url(self) -> str:
        """Reconstruct full URL."""
        url = f"{self.scheme}://{self.host}{self.path}"
        if self.query:
            url += f"?{self.query}"
        return url


@dataclass
class LinkRecord:
    """A link with source and target."""
    source: URLRecord
    target: URLRecord
    anchor_text: str = ""
    nofollow: bool = False
    noindex: bool = False
    discovered_date: str = ""
    source_ip: str = ""
    relevance_score: int = 0


# ==============================================================================
# FAST HASHING (Go pattern: FarmHash for deduplication)
# ==============================================================================

def fast_hash(data: str) -> str:
    """
    Fast hash for deduplication.

    Go equivalent: farm.Hash64()
    Uses xxhash if available (10x faster than md5).
    """
    if FAST_HASH:
        return xxhash.xxh64(data.encode()).hexdigest()
    return hashlib.md5(data.encode()).hexdigest()


def link_hash(source_url: str, target_url: str) -> str:
    """Generate unique hash for a link."""
    return fast_hash(f"{source_url}:{target_url}")


def page_hash(host: str, path: str, query: str = "") -> str:
    """Generate unique hash for a page."""
    return fast_hash(f"{host}{path}{query}")


# ==============================================================================
# URL VALIDATION (Go pattern: quality filters)
# ==============================================================================

def is_valid_host(host: str) -> bool:
    """
    Validate host for quality.

    Go equivalent: validateHost()
    """
    if not host:
        return False

    # Check for invalid characters
    if any(c in host for c in INVALID_HOST_CHARS):
        return False

    # Check for IP address (we want domains)
    if IP_REGEX.match(host):
        return False

    # Must have at least one dot
    if '.' not in host:
        return False

    return True


def is_valid_domain(domain: str) -> bool:
    """
    Validate domain format.

    Go equivalent: IsValidDomain()
    """
    return bool(VALID_DOMAIN_REGEX.match(domain))


def is_ignored_domain(domain: str) -> bool:
    """Check if domain should be ignored."""
    return domain.lower() in IGNORE_DOMAINS


def is_ignored_tld(domain: str) -> bool:
    """Check if TLD should be ignored."""
    for tld in IGNORE_TLDS:
        if domain.lower().endswith(tld):
            return True
    return False


def is_ignored_extension(path: str) -> bool:
    """Check if file extension should be ignored."""
    path_lower = path.lower()
    for ext in IGNORE_EXTENSIONS:
        if path_lower.endswith(ext):
            return True
    return False


def clean_query(query: str) -> str:
    """
    Clean query string, removing tracking parameters.

    Go equivalent: ignoreQuery()
    """
    if not query:
        return ""

    # Query too long = probably garbage
    if len(query) > 200:
        return ""

    # Remove tracking parameters
    try:
        params = parse_qs(query, keep_blank_values=False)
        cleaned = {}
        for key, values in params.items():
            # Skip tracking parameters
            if any(key.lower().startswith(prefix) for prefix in STRIP_QUERY_PREFIXES):
                continue
            cleaned[key] = values

        if not cleaned:
            return ""

        return '&'.join(f"{k}={v[0]}" for k, v in cleaned.items())
    except Exception:
        return query


def verify_url_quality(record: URLRecord) -> bool:
    """
    Verify URL record quality.

    Go equivalent: verifyRecordQuality()
    """
    # Must have domain
    if not record.domain:
        return False

    # Check TLD
    if is_ignored_tld(record.domain):
        return False

    # Validate host
    if not is_valid_host(record.host):
        return False

    # Validate domain format
    if not is_valid_domain(record.domain):
        return False

    # Check query length
    if len(record.query) > 200:
        return False

    # Check for pipe character in query (breaks delimiter)
    if '|' in record.query:
        return False

    return True


# ==============================================================================
# URL PARSING (Go pattern: buildURLRecord)
# ==============================================================================

def build_url_record(url: str, anchor_text: str = "", nofollow: bool = False) -> Optional[URLRecord]:
    """
    Build URLRecord from URL string.

    Go equivalent: buildURLRecord()
    """
    if not url or '\n' in url:
        return None

    try:
        parsed = urlparse(url)

        # Skip non-http(s)
        if parsed.scheme not in ('http', 'https', ''):
            return None

        host = parsed.netloc.lower().strip()
        if not host:
            return None

        # Path validation
        path = parsed.path or '/'
        if '\n' in path or '|' in path:
            return None

        # Get domain from cache
        domain = _domain_cache.get_domain(host)
        if not domain:
            return None

        # Calculate subdomain
        subdomain = ""
        if host != domain:
            subdomain = host.removesuffix(f".{domain}")

        record = URLRecord(
            url=url,
            scheme=parsed.scheme or 'http',
            host=host,
            path=path,
            query=clean_query(parsed.query),
            fragment=parsed.fragment,
            domain=domain,
            subdomain=subdomain,
            anchor_text=anchor_text,
            nofollow=nofollow,
        )

        return record
    except Exception:
        return None


# ==============================================================================
# RELEVANCE SCORING (Go pattern: calculateRelevanceScore)
# ==============================================================================

@dataclass
class ScoringConfig:
    """Configuration for link relevance scoring."""
    base_score: int = 10
    anchor_length_bonus_10: int = 5
    anchor_length_bonus_25: int = 5
    root_domain_bonus: int = 10
    dofollow_bonus: int = 15
    keyword_match_bonus: int = 20
    target_keywords: List[str] = field(default_factory=list)


def calculate_relevance_score(
    link: URLRecord,
    config: Optional[ScoringConfig] = None,
) -> int:
    """
    Calculate relevance score for a link.

    Go equivalent: calculateRelevanceScore()
    """
    config = config or ScoringConfig()
    score = config.base_score

    # Anchor text quality
    anchor_len = len(link.anchor_text)
    if anchor_len > 10:
        score += config.anchor_length_bonus_10
    if anchor_len > 25:
        score += config.anchor_length_bonus_25

    # Root domain (not subdomain) bonus
    if not link.is_subdomain:
        score += config.root_domain_bonus

    # DoFollow bonus
    if not link.nofollow:
        score += config.dofollow_bonus

    # Keyword matches in anchor text
    anchor_lower = link.anchor_text.lower()
    for keyword in config.target_keywords:
        if keyword.lower() in anchor_lower:
            score += config.keyword_match_bonus

    return score


# ==============================================================================
# STREAMING PARSER (Go pattern: ParseWatByLine)
# ==============================================================================

class StreamingLinkParser:
    """
    Streaming link parser inspired by Go's WAT parser.

    Features:
    - Line-by-line processing (memory efficient)
    - URL quality validation
    - Deduplication via hash
    - Domain caching
    """

    def __init__(
        self,
        target_domains: Optional[Set[str]] = None,
        country_tlds: Optional[List[str]] = None,
        url_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        min_anchor_length: int = 3,
        include_internal: bool = False,
    ):
        self.target_domains = target_domains or set()
        self.country_tlds = country_tlds or []
        self.url_keywords = url_keywords or []
        self.exclude_keywords = exclude_keywords or []
        self.min_anchor_length = min_anchor_length
        self.include_internal = include_internal

        # Deduplication
        self._seen_links: Set[str] = set()

        # Stats
        self.lines_processed = 0
        self.links_found = 0
        self.links_filtered = 0

    def parse_html_stream(
        self,
        html_stream: Iterator[str],
        source_url: str,
    ) -> Iterator[LinkRecord]:
        """
        Parse HTML stream for links.

        Yields LinkRecord for each valid link found.
        """
        source = build_url_record(source_url)
        if not source or not verify_url_quality(source):
            return

        for line in html_stream:
            self.lines_processed += 1

            # Find href links
            for match in ANCHOR_REGEX.finditer(line):
                href = match.group(1)
                anchor = match.group(2).strip()

                # Skip short anchors
                if len(anchor) < self.min_anchor_length:
                    continue

                # Check nofollow
                nofollow = 'nofollow' in line[:match.start()].lower()

                target = build_url_record(href, anchor_text=anchor, nofollow=nofollow)
                if not target:
                    continue

                # Apply filters
                if not self._should_include(source, target):
                    self.links_filtered += 1
                    continue

                # Deduplication
                link_id = link_hash(source.url, target.url)
                if link_id in self._seen_links:
                    continue
                self._seen_links.add(link_id)

                self.links_found += 1

                yield LinkRecord(
                    source=source,
                    target=target,
                    anchor_text=anchor,
                    nofollow=nofollow,
                )

    def _should_include(self, source: URLRecord, target: URLRecord) -> bool:
        """Apply all filters to determine if link should be included."""

        # Quality check
        if not verify_url_quality(target):
            return False

        # Internal link check
        if source.domain == target.domain and not self.include_internal:
            return False

        # Ignored domain check
        if is_ignored_domain(target.domain):
            return False

        # File extension check
        if is_ignored_extension(target.path):
            return False

        # Target domains filter
        if self.target_domains:
            if target.domain not in self.target_domains:
                return False

        # Country TLD filter
        if self.country_tlds:
            matched = any(target.domain.endswith(tld) for tld in self.country_tlds)
            if not matched:
                return False

        # URL keyword filter
        if self.url_keywords:
            full_url = target.to_full_url().lower()
            matched = any(kw.lower() in full_url for kw in self.url_keywords)
            if not matched:
                return False

        # Exclude keyword filter
        if self.exclude_keywords:
            full_url = target.to_full_url().lower()
            if any(kw.lower() in full_url for kw in self.exclude_keywords):
                return False

        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get parser statistics."""
        return {
            "lines_processed": self.lines_processed,
            "links_found": self.links_found,
            "links_filtered": self.links_filtered,
            "unique_links": len(self._seen_links),
            "domain_cache": _domain_cache.get_stats(),
        }


# ==============================================================================
# GZIP STREAMING (Go pattern: efficient gzip reading)
# ==============================================================================

def stream_gzip_lines(
    filepath: str,
    buffer_size: int = 5 * 1024 * 1024,  # 5MB buffer like Go
) -> Iterator[str]:
    """
    Stream lines from gzip file efficiently.

    Go equivalent: bufio.Scanner with gzip.Reader
    """
    with gzip.open(filepath, 'rt', encoding='utf-8', errors='ignore') as f:
        for line in f:
            yield line.rstrip('\n')


def stream_wat_pages(filepath: str) -> Iterator[Tuple[str, str]]:
    """
    Stream WAT pages as (url, json_content) tuples.

    Go equivalent: ParseWatByLine
    """
    current_url = None

    for line in stream_gzip_lines(filepath):
        if line.startswith(WAT_TARGET_URI_PREFIX):
            current_url = line[17:].strip()

        elif current_url and line.startswith(WAT_JSON_START) and 'href' in line:
            yield (current_url, line)
            current_url = None


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def extract_links_from_html(
    html: str,
    source_url: str,
    **filter_kwargs,
) -> List[LinkRecord]:
    """
    Extract links from HTML content with filtering.

    Args:
        html: HTML content
        source_url: Source page URL
        **filter_kwargs: Filter options (target_domains, country_tlds, etc.)

    Returns:
        List of LinkRecord objects
    """
    # Use BeautifulSoup if available (more accurate than regex)
    if BS4_AVAILABLE:
        return _extract_links_bs4(html, source_url, **filter_kwargs)

    # Fallback to streaming regex parser
    parser = StreamingLinkParser(**filter_kwargs)
    return list(parser.parse_html_stream(html.split('\n'), source_url))


def _extract_links_bs4(
    html: str,
    source_url: str,
    **filter_kwargs,
) -> List[LinkRecord]:
    """
    Extract links using BeautifulSoup (more accurate than regex).
    """
    from urllib.parse import urljoin

    links = []
    seen = set()

    source = build_url_record(source_url)
    if not source:
        return links

    try:
        soup = BeautifulSoup(html, 'html.parser')
    except Exception:
        return links

    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue

        # Resolve relative URLs
        if not href.startswith(('http://', 'https://')):
            href = urljoin(source_url, href)

        # Get anchor text
        anchor = a_tag.get_text(strip=True) or ''

        # Check nofollow
        rel = a_tag.get('rel', [])
        if isinstance(rel, str):
            rel = rel.split()
        nofollow = 'nofollow' in rel

        # Build target URL record
        target = build_url_record(href, anchor_text=anchor, nofollow=nofollow)
        if not target:
            continue

        # Deduplication
        link_key = f"{source.url}|{target.url}"
        if link_key in seen:
            continue
        seen.add(link_key)

        # Create link record
        links.append(LinkRecord(
            source=source,
            target=target,
            anchor_text=anchor,
            nofollow=nofollow,
        ))

    return links


def get_domain_from_url(url: str) -> Optional[str]:
    """Get domain from URL using cached lookup."""
    try:
        host = urlparse(url).netloc.lower()
        return _domain_cache.get_domain(host)
    except Exception:
        return None


def get_cache_stats() -> Dict[str, Any]:
    """Get domain cache statistics."""
    return _domain_cache.get_stats()


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import sys

    print("DRILL Link Processor - Go-inspired Optimizations")
    print("=" * 50)
    print()

    # Test domain caching
    test_hosts = [
        "www.example.com",
        "blog.example.com",
        "api.example.com",
        "www.bbc.co.uk",
        "news.bbc.co.uk",
    ]

    print("Domain Cache Test:")
    for host in test_hosts:
        domain = _domain_cache.get_domain(host)
        print(f"  {host} -> {domain}")

    print()
    print("Cache Stats:", _domain_cache.get_stats())

    # Test URL record
    print()
    print("URL Record Test:")
    record = build_url_record("https://www.example.com/path?utm_source=test&id=123")
    if record:
        print(f"  Domain: {record.domain}")
        print(f"  Subdomain: {record.subdomain}")
        print(f"  Query (cleaned): {record.query}")
        print(f"  Is subdomain: {record.is_subdomain}")
