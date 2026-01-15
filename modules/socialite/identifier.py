"""
SOCIALITE Identifier - Social account identification and verification.

Identifies social media accounts from various inputs:
- Names → Search across all platforms via Google + direct APIs
- Usernames → Cross-platform discovery (same username on multiple platforms)
- Email addresses → Find associated social profiles
- Phone numbers → Find associated accounts

Uses Apify actors for:
- Instagram profile scraping
- Twitter/X search and profiles
- Threads profile scraping
- Reddit user profiles
- Telegram profiles
- Facebook search

Provides verification status for discovered accounts.
"""

import re
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Try to import Apify client
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    ApifyClient = None

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")


class VerificationLevel(Enum):
    """Level of account verification."""
    CONFIRMED = "confirmed"      # Directly verified (e.g., email match, bio match)
    PROBABLE = "probable"        # High confidence match (name + location match)
    POSSIBLE = "possible"        # Potential match, needs review
    UNVERIFIED = "unverified"    # Found but not verified


class Platform(Enum):
    """Supported social media platforms."""
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    THREADS = "threads"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    GITHUB = "github"
    UNKNOWN = "unknown"


# Apify actor IDs for each platform
PLATFORM_ACTORS = {
    Platform.INSTAGRAM: "apify/instagram-profile-scraper",
    Platform.TWITTER: "apify/twitter-scraper",
    Platform.THREADS: "kJdK90pa2hhYYrCK5",
    Platform.REDDIT: "ILMCNaVwoOZyWEsrk",  # reddit_profile
    Platform.TELEGRAM: "lAybf7rRybdzabbBk",  # telegram_profile
    Platform.FACEBOOK: "Us34x9p7VgjCz99H6",  # facebook_search
}

# Google search site prefixes for each platform
PLATFORM_SITES = {
    Platform.LINKEDIN: "site:linkedin.com/in",
    Platform.FACEBOOK: "site:facebook.com",
    Platform.TWITTER: "site:twitter.com OR site:x.com",
    Platform.INSTAGRAM: "site:instagram.com",
    Platform.THREADS: "site:threads.net",
    Platform.TIKTOK: "site:tiktok.com/@",
    Platform.YOUTUBE: "site:youtube.com/@",
    Platform.REDDIT: "site:reddit.com/user",
    Platform.TELEGRAM: "site:t.me",
    Platform.GITHUB: "site:github.com",
}

# URL patterns for username extraction
URL_PATTERNS = {
    Platform.LINKEDIN: [
        r'linkedin\.com/in/([^/?]+)',
    ],
    Platform.FACEBOOK: [
        r'facebook\.com/([^/?]+)',
    ],
    Platform.TWITTER: [
        r'twitter\.com/([^/?]+)',
        r'x\.com/([^/?]+)',
    ],
    Platform.INSTAGRAM: [
        r'instagram\.com/([^/?]+)',
    ],
    Platform.THREADS: [
        r'threads\.net/@?([^/?]+)',
    ],
    Platform.TIKTOK: [
        r'tiktok\.com/@([^/?]+)',
    ],
    Platform.YOUTUBE: [
        r'youtube\.com/@([^/?]+)',
        r'youtube\.com/c/([^/?]+)',
    ],
    Platform.REDDIT: [
        r'reddit\.com/user/([^/?]+)',
        r'reddit\.com/u/([^/?]+)',
    ],
    Platform.TELEGRAM: [
        r't\.me/([^/?]+)',
    ],
    Platform.GITHUB: [
        r'github\.com/([^/?]+)',
    ],
}


@dataclass
class ExtractedAccount:
    """A social media account extracted from search results."""
    platform: Platform
    username: str
    profile_url: str
    display_name: str = ""
    bio: str = ""
    followers: int = 0
    following: int = 0
    verified_badge: bool = False
    profile_image: str = ""
    discovered_via: str = ""  # name_search, username_search, email, phone
    raw_data: Dict[str, Any] = field(default_factory=dict)
    extracted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class VerifiedAccount(ExtractedAccount):
    """An account that has been verified to belong to the target."""
    verification_level: VerificationLevel = VerificationLevel.UNVERIFIED
    verification_method: str = ""
    verification_evidence: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class SocialIdentificationResult:
    """Result of social account identification."""
    query: str
    query_type: str  # name, username, email, phone
    verified_accounts: List[VerifiedAccount] = field(default_factory=list)
    extracted_accounts: List[ExtractedAccount] = field(default_factory=list)
    platforms_searched: List[Platform] = field(default_factory=list)
    search_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    errors: List[str] = field(default_factory=list)

    @property
    def total_found(self) -> int:
        return len(self.verified_accounts) + len(self.extracted_accounts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "total_found": self.total_found,
            "verified_count": len(self.verified_accounts),
            "extracted_count": len(self.extracted_accounts),
            "platforms_searched": [p.value for p in self.platforms_searched],
            "accounts": [
                {
                    "platform": a.platform.value,
                    "username": a.username,
                    "profile_url": a.profile_url,
                    "display_name": a.display_name,
                    "verification_level": a.verification_level.value if isinstance(a, VerifiedAccount) else "extracted",
                }
                for a in self.verified_accounts + self.extracted_accounts
            ],
            "errors": self.errors,
        }


class SocialIdentifier:
    """
    Identifies social media accounts from names, usernames, emails, phones.

    Usage:
        identifier = SocialIdentifier()

        # Search by name
        result = await identifier.identify_from_name("John Smith")

        # Search by username (cross-platform)
        result = await identifier.identify_from_username("johnsmith123")

        # Search by email
        result = await identifier.identify_from_email("john@example.com")
    """

    EXCLUDE_USERNAMES = {
        'login', 'signup', 'search', 'help', 'about', 'settings',
        'explore', 'home', 'messages', 'notifications', 'profile',
        'status', 'share', 'watch', 'reels', 'stories',
    }

    def __init__(self, platforms: Optional[List[Platform]] = None):
        self.platforms = platforms or [
            Platform.INSTAGRAM,
            Platform.TWITTER,
            Platform.THREADS,
            Platform.REDDIT,
            Platform.TELEGRAM,
            Platform.FACEBOOK,
            Platform.LINKEDIN,
            Platform.TIKTOK,
            Platform.YOUTUBE,
            Platform.GITHUB,
        ]
        self._client = None

    def _get_client(self) -> ApifyClient:
        """Get Apify client."""
        if not APIFY_AVAILABLE:
            raise ImportError("apify-client not installed. Run: pip install apify-client")
        if not APIFY_TOKEN:
            raise ValueError("APIFY_API_TOKEN environment variable not set")
        if self._client is None:
            self._client = ApifyClient(APIFY_TOKEN)
        return self._client

    def _build_profile_url(self, platform: Platform, username: str) -> str:
        """Build profile URL for a platform."""
        templates = {
            Platform.LINKEDIN: f"https://www.linkedin.com/in/{username}",
            Platform.FACEBOOK: f"https://www.facebook.com/{username}",
            Platform.TWITTER: f"https://x.com/{username}",
            Platform.INSTAGRAM: f"https://www.instagram.com/{username}",
            Platform.THREADS: f"https://www.threads.net/@{username}",
            Platform.TIKTOK: f"https://www.tiktok.com/@{username}",
            Platform.YOUTUBE: f"https://www.youtube.com/@{username}",
            Platform.REDDIT: f"https://www.reddit.com/user/{username}",
            Platform.TELEGRAM: f"https://t.me/{username}",
            Platform.GITHUB: f"https://github.com/{username}",
        }
        return templates.get(platform, "")

    def _extract_username_from_url(self, url: str, platform: Platform) -> Optional[str]:
        """Extract username from a profile URL."""
        patterns = URL_PATTERNS.get(platform, [])
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1)
                if username.lower() not in self.EXCLUDE_USERNAMES:
                    return username
        return None

    def _detect_platform_from_url(self, url: str) -> Tuple[Platform, str]:
        """Detect platform and extract username from URL."""
        for platform, patterns in URL_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    username = match.group(1)
                    if username.lower() not in self.EXCLUDE_USERNAMES:
                        return platform, username
        return Platform.UNKNOWN, ""

    # =========================================================================
    # PLATFORM-SPECIFIC SCRAPERS
    # =========================================================================

    async def _scrape_instagram_profile(self, username: str) -> Optional[ExtractedAccount]:
        """Scrape Instagram profile via Apify."""
        try:
            client = self._get_client()
            run_input = {
                "usernames": [username],
            }
            run = client.actor("apify/instagram-profile-scraper").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if results:
                data = results[0]
                return ExtractedAccount(
                    platform=Platform.INSTAGRAM,
                    username=data.get("username", username),
                    profile_url=f"https://www.instagram.com/{username}",
                    display_name=data.get("fullName", ""),
                    bio=data.get("biography", ""),
                    followers=data.get("followersCount", 0),
                    following=data.get("followsCount", 0),
                    verified_badge=data.get("verified", False),
                    profile_image=data.get("profilePicUrl", ""),
                    discovered_via="instagram_scraper",
                    raw_data=data,
                )
        except Exception as e:
            logger.error(f"Instagram scrape failed for {username}: {e}")
        return None

    async def _scrape_twitter_profile(self, username: str) -> Optional[ExtractedAccount]:
        """Scrape Twitter/X profile via Apify."""
        try:
            client = self._get_client()
            run_input = {
                "handles": [username],
                "tweetsDesired": 0,
                "profilesDesired": 1,
            }
            run = client.actor("apify/twitter-scraper").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if results:
                data = results[0]
                return ExtractedAccount(
                    platform=Platform.TWITTER,
                    username=data.get("username", username),
                    profile_url=f"https://x.com/{username}",
                    display_name=data.get("name", ""),
                    bio=data.get("description", ""),
                    followers=data.get("followers", 0),
                    following=data.get("following", 0),
                    verified_badge=data.get("isVerified", False),
                    profile_image=data.get("profileImageUrl", ""),
                    discovered_via="twitter_scraper",
                    raw_data=data,
                )
        except Exception as e:
            logger.error(f"Twitter scrape failed for {username}: {e}")
        return None

    async def _scrape_threads_profile(self, username: str) -> Optional[ExtractedAccount]:
        """Scrape Threads profile via Apify."""
        try:
            client = self._get_client()
            run_input = {
                "usernames": [username],
            }
            run = client.actor("kJdK90pa2hhYYrCK5").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if results:
                data = results[0]
                return ExtractedAccount(
                    platform=Platform.THREADS,
                    username=data.get("username", username),
                    profile_url=f"https://www.threads.net/@{username}",
                    display_name=data.get("full_name", data.get("fullName", "")),
                    bio=data.get("biography", data.get("bio", "")),
                    followers=data.get("follower_count", data.get("followers", 0)),
                    following=data.get("following_count", 0),
                    verified_badge=data.get("is_verified", False),
                    profile_image=data.get("profile_pic_url", ""),
                    discovered_via="threads_scraper",
                    raw_data=data,
                )
        except Exception as e:
            logger.error(f"Threads scrape failed for {username}: {e}")
        return None

    async def _scrape_reddit_profile(self, username: str) -> Optional[ExtractedAccount]:
        """Scrape Reddit user profile via Apify."""
        try:
            client = self._get_client()
            run_input = {
                "startUrls": [{"url": f"https://www.reddit.com/user/{username}"}],
            }
            run = client.actor("ILMCNaVwoOZyWEsrk").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if results:
                data = results[0]
                return ExtractedAccount(
                    platform=Platform.REDDIT,
                    username=data.get("author", username),
                    profile_url=f"https://www.reddit.com/user/{username}",
                    display_name=data.get("author", username),
                    bio="",
                    followers=0,
                    following=0,
                    verified_badge=False,
                    profile_image="",
                    discovered_via="reddit_scraper",
                    raw_data=data,
                )
        except Exception as e:
            logger.error(f"Reddit scrape failed for {username}: {e}")
        return None

    async def _scrape_telegram_profile(self, username: str) -> Optional[ExtractedAccount]:
        """Scrape Telegram profile via Apify."""
        try:
            client = self._get_client()
            run_input = {
                "user_name": [username],
            }
            run = client.actor("lAybf7rRybdzabbBk").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            if results:
                data = results[0]
                display_name = data.get("title", "")
                if not display_name:
                    first = data.get("first_name", "")
                    last = data.get("last_name", "")
                    display_name = f"{first} {last}".strip()

                return ExtractedAccount(
                    platform=Platform.TELEGRAM,
                    username=username,
                    profile_url=f"https://t.me/{username}",
                    display_name=display_name,
                    bio=data.get("description", ""),
                    followers=data.get("member_count", 0),
                    following=0,
                    verified_badge=data.get("is_verified", False),
                    profile_image="",
                    discovered_via="telegram_scraper",
                    raw_data=data,
                )
        except Exception as e:
            logger.error(f"Telegram scrape failed for {username}: {e}")
        return None

    # =========================================================================
    # GOOGLE SEARCH FOR PROFILES
    # =========================================================================

    async def _google_search_for_profiles(
        self,
        query: str,
        platform: Platform,
        max_results: int = 10,
    ) -> List[str]:
        """
        Search Google for social profiles.

        Returns list of profile URLs found.
        """
        site_prefix = PLATFORM_SITES.get(platform, "")
        if not site_prefix:
            return []

        search_query = f'"{query}" {site_prefix}'

        try:
            client = self._get_client()
            run_input = {
                "queries": search_query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": max_results,
            }
            run = client.actor("apify/google-search-scraper").call(run_input=run_input)
            results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

            urls = []
            for result in results:
                organic = result.get("organicResults", [])
                for item in organic:
                    url = item.get("url", "")
                    if url:
                        urls.append(url)

            return urls
        except Exception as e:
            logger.error(f"Google search failed for {query} on {platform}: {e}")
            return []

    # =========================================================================
    # MAIN IDENTIFICATION METHODS
    # =========================================================================

    async def identify_from_name(
        self,
        name: str,
        location: Optional[str] = None,
        company: Optional[str] = None,
    ) -> SocialIdentificationResult:
        """
        Find social accounts by person name.

        Searches Google for "[name] site:platform.com" for each platform,
        then scrapes found profiles via Apify.
        """
        result = SocialIdentificationResult(
            query=name,
            query_type="name",
            platforms_searched=self.platforms,
        )

        # Build enhanced query
        query_parts = [name]
        if location:
            query_parts.append(location)
        if company:
            query_parts.append(company)
        search_query = " ".join(query_parts)

        logger.info(f"🔍 Searching for: {search_query}")

        # Search each platform via Google
        all_urls = []
        for platform in self.platforms:
            urls = await self._google_search_for_profiles(search_query, platform)
            for url in urls:
                all_urls.append((url, platform))

        logger.info(f"   Found {len(all_urls)} potential profile URLs")

        # Extract accounts from URLs and scrape where possible
        seen_accounts = set()
        for url, expected_platform in all_urls:
            platform, username = self._detect_platform_from_url(url)
            if platform == Platform.UNKNOWN or not username:
                continue

            key = (platform, username.lower())
            if key in seen_accounts:
                continue
            seen_accounts.add(key)

            # Try to scrape the profile
            account = await self._scrape_profile(platform, username)
            if account:
                account.discovered_via = "name_search"
                result.extracted_accounts.append(account)
            else:
                # Create basic account from URL
                result.extracted_accounts.append(ExtractedAccount(
                    platform=platform,
                    username=username,
                    profile_url=url,
                    discovered_via="name_search_url",
                ))

        logger.info(f"   Extracted {len(result.extracted_accounts)} accounts")
        return result

    async def identify_from_username(
        self,
        username: str,
    ) -> SocialIdentificationResult:
        """
        Find accounts across platforms using a username.

        Tries the same username on all platforms via direct scraping.
        """
        result = SocialIdentificationResult(
            query=username,
            query_type="username",
            platforms_searched=self.platforms,
        )

        logger.info(f"🔍 Cross-platform search for username: {username}")

        # Try scraping each platform with this username
        tasks = []
        for platform in self.platforms:
            tasks.append(self._scrape_profile(platform, username))

        accounts = await asyncio.gather(*tasks, return_exceptions=True)

        for account in accounts:
            if isinstance(account, ExtractedAccount):
                account.discovered_via = "username_search"
                result.extracted_accounts.append(account)
            elif isinstance(account, Exception):
                result.errors.append(str(account))

        logger.info(f"   Found {len(result.extracted_accounts)} accounts")
        return result

    async def identify_from_email(
        self,
        email: str,
    ) -> SocialIdentificationResult:
        """
        Find social accounts associated with an email address.

        Uses Google search with email to find profiles.
        """
        result = SocialIdentificationResult(
            query=email,
            query_type="email",
            platforms_searched=self.platforms,
        )

        logger.info(f"🔍 Searching for email: {email}")

        # Search each platform for this email
        all_urls = []
        for platform in self.platforms:
            urls = await self._google_search_for_profiles(email, platform)
            for url in urls:
                all_urls.append((url, platform))

        # Process URLs
        seen_accounts = set()
        for url, _ in all_urls:
            platform, username = self._detect_platform_from_url(url)
            if platform == Platform.UNKNOWN or not username:
                continue

            key = (platform, username.lower())
            if key in seen_accounts:
                continue
            seen_accounts.add(key)

            account = await self._scrape_profile(platform, username)
            if account:
                account.discovered_via = "email_search"
                result.extracted_accounts.append(account)

        return result

    async def identify_from_phone(
        self,
        phone: str,
        country_code: str = "",
    ) -> SocialIdentificationResult:
        """
        Find social accounts associated with a phone number.
        """
        result = SocialIdentificationResult(
            query=phone,
            query_type="phone",
            platforms_searched=self.platforms,
        )

        logger.info(f"🔍 Searching for phone: {phone}")

        # Similar to email search
        all_urls = []
        for platform in self.platforms:
            urls = await self._google_search_for_profiles(phone, platform)
            for url in urls:
                all_urls.append((url, platform))

        seen_accounts = set()
        for url, _ in all_urls:
            platform, username = self._detect_platform_from_url(url)
            if platform == Platform.UNKNOWN or not username:
                continue

            key = (platform, username.lower())
            if key in seen_accounts:
                continue
            seen_accounts.add(key)

            account = await self._scrape_profile(platform, username)
            if account:
                account.discovered_via = "phone_search"
                result.extracted_accounts.append(account)

        return result

    async def _scrape_profile(
        self,
        platform: Platform,
        username: str,
    ) -> Optional[ExtractedAccount]:
        """Scrape a profile on any platform."""
        scrapers = {
            Platform.INSTAGRAM: self._scrape_instagram_profile,
            Platform.TWITTER: self._scrape_twitter_profile,
            Platform.THREADS: self._scrape_threads_profile,
            Platform.REDDIT: self._scrape_reddit_profile,
            Platform.TELEGRAM: self._scrape_telegram_profile,
        }

        scraper = scrapers.get(platform)
        if scraper:
            return await scraper(username)

        # For platforms without scrapers, create basic account
        profile_url = self._build_profile_url(platform, username)
        if profile_url:
            return ExtractedAccount(
                platform=platform,
                username=username,
                profile_url=profile_url,
                discovered_via="url_generated",
            )

        return None

    def verify_account(
        self,
        account: ExtractedAccount,
        evidence: List[str],
        method: str = "manual",
    ) -> VerifiedAccount:
        """Upgrade an extracted account to verified status."""
        level = VerificationLevel.CONFIRMED if len(evidence) >= 2 else VerificationLevel.PROBABLE
        if not evidence:
            level = VerificationLevel.POSSIBLE

        return VerifiedAccount(
            platform=account.platform,
            username=account.username,
            profile_url=account.profile_url,
            display_name=account.display_name,
            bio=account.bio,
            followers=account.followers,
            following=account.following,
            verified_badge=account.verified_badge,
            profile_image=account.profile_image,
            discovered_via=account.discovered_via,
            raw_data=account.raw_data,
            extracted_at=account.extracted_at,
            verification_level=level,
            verification_method=method,
            verification_evidence=evidence,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def identify_social_accounts(
    query: str,
    query_type: str = "auto",
    platforms: Optional[List[Platform]] = None,
) -> SocialIdentificationResult:
    """
    Convenience function to identify social accounts.

    Args:
        query: The search query (name, username, email, or phone)
        query_type: "name", "username", "email", "phone", or "auto"
        platforms: List of platforms to search (None = all)

    Returns:
        SocialIdentificationResult with found accounts
    """
    identifier = SocialIdentifier(platforms=platforms)

    # Auto-detect query type
    if query_type == "auto":
        if "@" in query and "." in query:
            query_type = "email"
        elif query.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            query_type = "phone"
        elif " " in query:
            query_type = "name"
        else:
            query_type = "username"

    if query_type == "email":
        return await identifier.identify_from_email(query)
    elif query_type == "phone":
        return await identifier.identify_from_phone(query)
    elif query_type == "name":
        return await identifier.identify_from_name(query)
    else:
        return await identifier.identify_from_username(query)


async def search_username_all_platforms(username: str) -> SocialIdentificationResult:
    """Search for a username across all platforms."""
    identifier = SocialIdentifier()
    return await identifier.identify_from_username(username)


async def search_name_all_platforms(
    name: str,
    location: Optional[str] = None,
    company: Optional[str] = None,
) -> SocialIdentificationResult:
    """Search for a name across all platforms."""
    identifier = SocialIdentifier()
    return await identifier.identify_from_name(name, location, company)


__all__ = [
    "VerificationLevel",
    "Platform",
    "ExtractedAccount",
    "VerifiedAccount",
    "SocialIdentificationResult",
    "SocialIdentifier",
    "identify_social_accounts",
    "search_username_all_platforms",
    "search_name_all_platforms",
    "PLATFORM_ACTORS",
    "PLATFORM_SITES",
]
