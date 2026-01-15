"""
SOCIALITE Social Data Router - Route queries to appropriate data collectors.

Handles prefix-based queries for social media data collection:
- fb: → Facebook
- li: → LinkedIn
- ig: → Instagram
- tw: → Twitter/X
- tg: → Telegram
- tt: → TikTok
- th: → Threads
- yt: → YouTube
- rd: → Reddit

Routes to BrightData, Apify, or direct scrapers based on data type.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class Platform(Enum):
    """Supported platforms."""
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    TELEGRAM = "telegram"
    TIKTOK = "tiktok"
    THREADS = "threads"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    GOOGLE_MAPS = "google_maps"
    UNKNOWN = "unknown"


class EntityType(Enum):
    """Type of entity being queried."""
    PROFILE = "profile"
    COMPANY = "company"
    POST = "post"
    POSTS = "posts"
    JOB = "job"
    JOBS = "jobs"
    SEARCH = "search"
    CHANNEL = "channel"
    GROUP = "group"
    PLACE = "place"
    UNKNOWN = "unknown"


@dataclass
class ParsedQuery:
    """Result of parsing a social query."""
    raw_query: str
    platform: Platform
    entity_type: EntityType
    identifier: str  # username, URL, or search term
    is_url: bool = False
    modifiers: Dict[str, Any] = field(default_factory=dict)
    parsed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SocialDataResult:
    """Result from a social data query."""
    query: ParsedQuery
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    data_source: str = ""  # brightdata, apify, direct
    error: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Prefix mappings
PLATFORM_PREFIXES = {
    "fb:": Platform.FACEBOOK,
    "facebook:": Platform.FACEBOOK,
    "li:": Platform.LINKEDIN,
    "linkedin:": Platform.LINKEDIN,
    "ig:": Platform.INSTAGRAM,
    "instagram:": Platform.INSTAGRAM,
    "tw:": Platform.TWITTER,
    "twitter:": Platform.TWITTER,
    "x:": Platform.TWITTER,
    "tg:": Platform.TELEGRAM,
    "telegram:": Platform.TELEGRAM,
    "tt:": Platform.TIKTOK,
    "tiktok:": Platform.TIKTOK,
    "th:": Platform.THREADS,
    "threads:": Platform.THREADS,
    "yt:": Platform.YOUTUBE,
    "youtube:": Platform.YOUTUBE,
    "rd:": Platform.REDDIT,
    "reddit:": Platform.REDDIT,
    "gm:": Platform.GOOGLE_MAPS,
    "maps:": Platform.GOOGLE_MAPS,
}

# Entity type modifiers
ENTITY_MODIFIERS = {
    "/profile": EntityType.PROFILE,
    "/company": EntityType.COMPANY,
    "/post": EntityType.POST,
    "/posts": EntityType.POSTS,
    "/job": EntityType.JOB,
    "/jobs": EntityType.JOBS,
    "/search": EntityType.SEARCH,
    "/channel": EntityType.CHANNEL,
    "/group": EntityType.GROUP,
    "/place": EntityType.PLACE,
}

# URL patterns for platform detection
URL_PATTERNS = {
    Platform.FACEBOOK: [
        r'facebook\.com',
        r'fb\.com',
    ],
    Platform.LINKEDIN: [
        r'linkedin\.com',
    ],
    Platform.INSTAGRAM: [
        r'instagram\.com',
    ],
    Platform.TWITTER: [
        r'twitter\.com',
        r'x\.com',
    ],
    Platform.TELEGRAM: [
        r't\.me',
        r'telegram\.me',
    ],
    Platform.TIKTOK: [
        r'tiktok\.com',
    ],
    Platform.THREADS: [
        r'threads\.net',
    ],
    Platform.YOUTUBE: [
        r'youtube\.com',
        r'youtu\.be',
    ],
    Platform.REDDIT: [
        r'reddit\.com',
    ],
}


def get_supported_prefixes() -> List[str]:
    """Get list of supported query prefixes."""
    return list(PLATFORM_PREFIXES.keys())


def is_social_query(query: str) -> bool:
    """Check if a query is a social media query (has prefix or is social URL)."""
    query_lower = query.lower().strip()

    # Check for prefix
    for prefix in PLATFORM_PREFIXES.keys():
        if query_lower.startswith(prefix):
            return True

    # Check for social URL
    if query_lower.startswith(("http://", "https://")):
        platform = detect_platform_from_url(query)
        return platform != Platform.UNKNOWN

    return False


def detect_platform_from_url(url: str) -> Platform:
    """Detect the platform from a URL."""
    url_lower = url.lower()

    for platform, patterns in URL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return platform

    return Platform.UNKNOWN


def parse_social_query(query: str) -> ParsedQuery:
    """
    Parse a social media query string.

    Formats supported:
    - "fb:username" → Facebook profile
    - "li:username/posts" → LinkedIn posts
    - "https://linkedin.com/in/username" → LinkedIn profile (URL)
    - "tg:channel/messages" → Telegram channel messages

    Args:
        query: The query string

    Returns:
        ParsedQuery with parsed components
    """
    query = query.strip()
    platform = Platform.UNKNOWN
    entity_type = EntityType.PROFILE  # Default
    identifier = query
    is_url = False
    modifiers = {}

    # Check if it's a URL
    if query.lower().startswith(("http://", "https://")):
        is_url = True
        platform = detect_platform_from_url(query)
        identifier = query

        # Try to detect entity type from URL
        if "/company/" in query.lower():
            entity_type = EntityType.COMPANY
        elif "/jobs/" in query.lower() or "/job/" in query.lower():
            entity_type = EntityType.JOB
        elif "/posts/" in query.lower() or "/post/" in query.lower():
            entity_type = EntityType.POST
        elif "/in/" in query.lower():
            entity_type = EntityType.PROFILE

    else:
        # Check for prefix
        query_lower = query.lower()
        for prefix, plat in PLATFORM_PREFIXES.items():
            if query_lower.startswith(prefix):
                platform = plat
                identifier = query[len(prefix):]
                break

        # Check for entity modifier
        for mod, etype in ENTITY_MODIFIERS.items():
            if mod in identifier.lower():
                entity_type = etype
                identifier = identifier.lower().replace(mod, "").strip()
                break

        # Parse additional modifiers (key=value)
        if "?" in identifier:
            parts = identifier.split("?", 1)
            identifier = parts[0]
            if len(parts) > 1:
                for param in parts[1].split("&"):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        modifiers[key] = value

    return ParsedQuery(
        raw_query=query,
        platform=platform,
        entity_type=entity_type,
        identifier=identifier.strip(),
        is_url=is_url,
        modifiers=modifiers,
    )


class SocialDataRouter:
    """
    Routes social data queries to appropriate collectors.

    Usage:
        router = SocialDataRouter()
        result = await router.route("li:johndoe")
        print(result.data)
    """

    def __init__(self):
        self._collectors = {}

    async def route(self, query: str) -> SocialDataResult:
        """
        Route a query to the appropriate collector.

        Args:
            query: Social query string

        Returns:
            SocialDataResult with fetched data
        """
        parsed = parse_social_query(query)

        if parsed.platform == Platform.UNKNOWN:
            return SocialDataResult(
                query=parsed,
                success=False,
                error="Unknown platform. Use a prefix like fb:, li:, ig:, tw:, tg:",
            )

        # Route to appropriate collector
        try:
            data = await self._collect_data(parsed)
            return SocialDataResult(
                query=parsed,
                success=True,
                data=data,
                data_source=self._get_data_source(parsed.platform),
            )
        except Exception as e:
            logger.error(f"Data collection failed: {e}")
            return SocialDataResult(
                query=parsed,
                success=False,
                error=str(e),
            )

    async def _collect_data(self, parsed: ParsedQuery) -> Dict[str, Any]:
        """Collect data based on parsed query."""
        # TODO: Implement actual data collection
        # This would call BrightData, Apify, or direct scrapers
        return {
            "platform": parsed.platform.value,
            "entity_type": parsed.entity_type.value,
            "identifier": parsed.identifier,
            "status": "placeholder",
        }

    def _get_data_source(self, platform: Platform) -> str:
        """Determine best data source for a platform."""
        brightdata_platforms = {
            Platform.LINKEDIN,
            Platform.FACEBOOK,
            Platform.INSTAGRAM,
        }

        apify_platforms = {
            Platform.TELEGRAM,
            Platform.THREADS,
            Platform.TIKTOK,
            Platform.REDDIT,
            Platform.YOUTUBE,
        }

        if platform in brightdata_platforms:
            return "brightdata"
        elif platform in apify_platforms:
            return "apify"
        else:
            return "direct"


async def route_social_query(query: str) -> SocialDataResult:
    """
    Convenience function to route a social query.

    Args:
        query: Social query string (e.g., "li:johndoe", "fb:company/posts")

    Returns:
        SocialDataResult with fetched data
    """
    router = SocialDataRouter()
    return await router.route(query)


__all__ = [
    "Platform",
    "EntityType",
    "ParsedQuery",
    "SocialDataResult",
    "SocialDataRouter",
    "route_social_query",
    "parse_social_query",
    "is_social_query",
    "get_supported_prefixes",
    "detect_platform_from_url",
    "PLATFORM_PREFIXES",
    "ENTITY_MODIFIERS",
]
