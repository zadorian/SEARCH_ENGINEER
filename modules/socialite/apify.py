#!/usr/bin/env python3
"""
APIFY - Unified Apify Integration Hub

Centralizes all Apify actor integrations for:
- Social media (Facebook, Instagram, LinkedIn, Reddit, TikTok, Telegram, YouTube)
- Search engines (Google, Bing, DuckDuckGo, Yandex)
- Google Maps & location data
- News sources (Bloomberg, Reuters)
- Jobs (Glassdoor, LinkedIn Jobs, Indeed)
- Business intel (Crunchbase, PitchBook, SimilarWeb, Ahrefs)

Like TORPEDO but for Apify-based scraping. Each platform bridges
to its respective file in platforms/.

=== MCP SERVER INTEGRATION (75+ ACTORS) ===
Full MCP URL with all pre-configured actors:
  See apify_mcp_config.json for complete configuration

Quick setup - add to Claude's MCP settings:
{
  "mcpServers": {
    "apify": {
      "url": "https://mcp.apify.com/?tools=actors,docs,<actor-list>",
      "headers": {"Authorization": "Bearer ${APIFY_TOKEN}"}
    }
  }
}

Categories available via MCP:
- Instagram (10 actors): scraper, reels, posts, profiles, hashtags, comments, followers
- Facebook (11 actors): posts, pages, comments, groups, search, reviews, reels, photos
- LinkedIn (9 actors): profile posts, jobs, company data, enrichment
- YouTube (4 actors): transcripts, comments, email finder, channels
- Telegram (6 actors): channels, media, phone info, username lookup
- Reddit (4 actors): subreddits, posts, videos, API
- Google Maps (4 actors): places, extractor, business
- Search Engines (6 actors): Google, Bing, DuckDuckGo, Yandex
- Business Intel (7 actors): employees, Ahrefs, investors, PitchBook, Crunchbase
- Jobs (3 actors): LinkedIn, Indeed

MCP Tools provided:
- search-actors: Find actors in Apify Store
- fetch-actor-details: Get actor info
- call-actor: Execute any actor
- add-actor: Dynamically add actors as tools
- search-apify-docs: Search documentation
- fetch-apify-docs: Get full docs pages
"""

import os
import logging
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")

# Actor IDs registry
ACTORS = {
    # Social Media
    "facebook_search": "Us34x9p7VgjCz99H6",
    "threads_profile": "kJdK90pa2hhYYrCK5",
    "instagram_profile": "apify/instagram-profile-scraper",
    "instagram_posts": "apify/instagram-post-scraper",
    "twitter_search": None,  # Apify Twitter scraper discontinued - use URL generation
    "reddit_user": "cgizCCmpI9tsJFexd",  # Reddit user/posts/comments scraper

    # Search Engines & Maps
    "google_search": "apify/google-search-scraper",
    "google_maps": "nwua9Gu5YrADL7ZDj",  # compass/crawler-google-places
    "google_maps_email": "lukaskrivka/google-maps-with-contact-details",  # Email extractor

    # Jobs
    "glassdoor_jobs": "cGlsIU5HiYjpXpmhs",  # Glassdoor job scraper

    # News
    "bloomberg_article": "KIZXeJ0LsBt6YYeLi",
    "google_news": "KIe0dFDnUt4mqQyVI",
    "reuters_article": "anchor/reuters-scraper",

    # Corporate Registries
    "handelsregister": "CZBHNvjaWtrEw9O9R",  # German Handelsregister (radeance/handelsregister-api)
    "openactor_business": "h3OriIkWaInEm8g9q",  # UK/US/AU/CA company registry search

    # UK Government
    "uk_contracts_finder": "nocodeventure/uk-government-contracts",  # UK public sector contracts

    # Analytics & SEO
    "ahrefs": "radeance/ahrefs-scraper",  # Domain analytics, backlinks, traffic, keywords

    # Asset Tracking
    "faa_aircraft": "ii2e5GTophh9VtXHa",  # FAA Aircraft Registry (N-Number)

    # LinkedIn
    "linkedin_company": "taHaRcqil3scbchuI",  # LinkedIn company scraper

    # Reddit
    "reddit_profile": "ILMCNaVwoOZyWEsrk",  # Reddit user profile scraper

    # Telegram
    "telegram_channel": "TpLqaxMYSJzwVnXoj",  # Telegram channel/group message scraper
    "telegram_profile": "lAybf7rRybdzabbBk",  # agentx/telegram-info-scraper - 40+ fields
    "telegram_profile_lite": "cheapget/telegram-profile",  # Basic profile metadata
    "telegram_group_members": "cheapget/telegram-group-member",  # Group member extraction

    # SEO & Domain Analytics
    "semrush_domain": "radeance/semrush-scraper",  # Domain analysis, authority, traffic, backlinks
    "semrush_search": "TMBawM4LZpKN15DZX",  # Keyword/search research

    # Infrastructure
    "proxy_scraper": "UvkeX4n0DvIkcyIY3",  # Free proxy list aggregator/validator

    # General
    "web_scraper": "apify/web-scraper",
    "cheerio_scraper": "apify/cheerio-scraper",
}

# Actor metadata
ACTOR_INFO = {
    "google_maps": {
        "id": "nwua9Gu5YrADL7ZDj",
        "name": "Google Maps Scraper",
        "publisher": "compass",
        "full_id": "compass/crawler-google-places",
        "capabilities": [
            "business_search",
            "place_details",
            "reviews",
            "images",
            "contact_enrichment",
            "leads_enrichment",
            "social_media_enrichment",
            "neighborhood_data",
            "opening_hours",
            "popular_times",
        ],
    },
    "facebook_search": {
        "id": "Us34x9p7VgjCz99H6",
        "name": "Facebook Search",
        "capabilities": ["category_search", "location_search", "places"],
    },
    "threads_profile": {
        "id": "kJdK90pa2hhYYrCK5",
        "name": "Threads Profile Scraper",
        "capabilities": ["profile_data", "posts", "followers"],
    },
    "bloomberg_article": {
        "id": "KIZXeJ0LsBt6YYeLi",
        "name": "Bloomberg Article Scraper",
        "capabilities": ["article_content", "authors", "entities", "tags"],
    },
    "google_news": {
        "id": "KIe0dFDnUt4mqQyVI",
        "name": "Google News Scraper",
        "capabilities": [
            "keyword_search",
            "time_filter",
            "language_filter",
            "country_filter",
            "trending_news",
        ],
        "time_filters": [
            "Past hour", "Past 24 hours", "Past week",
            "Past month", "Past year", "Recent",
        ],
    },
    "google_maps_email": {
        "id": "lukaskrivka/google-maps-with-contact-details",
        "name": "Google Maps Email Extractor",
        "publisher": "lukaskrivka",
        "cost_per_result": 0.01,
        "cost_per_1000": 10.00,
        "capabilities": [
            "email_extraction",
            "phone_extraction",
            "social_media_extraction",
            "business_search",
            "category_search",
            "location_search",
            "coordinates_search",
            "rating_filter",
            "skip_closed",
        ],
        "social_media": [
            "LinkedIn",
            "Twitter",
            "Facebook",
            "Instagram",
            "YouTube",
            "TikTok",
            "Pinterest",
            "Discord",
        ],
        "note": "Input: address/location/search term -> Output: emails, phones, social profiles",
    },
    "glassdoor_jobs": {
        "id": "cGlsIU5HiYjpXpmhs",
        "name": "Glassdoor Jobs Scraper",
        "capabilities": [
            "job_search",
            "company_filter",
            "location_filter",
            "country_filter",
            "keyword_search",
            "job_type_filter",
            "date_posted_filter",
        ],
        "job_types": [
            "fulltime",
            "parttime",
            "contract",
            "internship",
            "temporary",
        ],
        "date_posted_options": [
            "all",
            "today",
            "3days",
            "week",
            "month",
        ],
        "note": "Input: company/location/keyword -> Output: job listings from Glassdoor",
    },
    "reddit_user": {
        "id": "cgizCCmpI9tsJFexd",
        "name": "Reddit User Scraper",
        "cost_per_result": 0.004,
        "cost_per_1000": 4.00,
        "capabilities": [
            "user_posts",
            "user_comments",
            "user_profile",
            "karma_data",
            "media_links",
            "engagement_metrics",
        ],
        "scrape_types": ["posts", "comments", "profile"],
        "sort_options": ["new", "top", "hot"],
        "time_options": ["hour", "day", "week", "month", "year", "all"],
        "output_fields": [
            "subreddit", "title", "selftext", "author", "score",
            "upvote_ratio", "num_comments", "created_utc", "url",
            "is_video", "over_18", "awards",
        ],
        "note": "Input: username/URL -> Output: posts, comments, profile, karma, media",
    },
    "handelsregister": {
        "id": "CZBHNvjaWtrEw9O9R",
        "name": "German Handelsregister",
        "publisher": "radeance",
        "full_id": "radeance/handelsregister-api",
        "capabilities": [
            "company_search",
            "register_lookup",
            "keyword_search",
            "deep_search",
            "representatives",
            "address",
            "documents",
        ],
        "register_types": ["HRA", "HRB", "GnR", "PR", "VR", "GsR"],
        "search_modes": ["identifier", "keyword", "register_number"],
        "output_fields": [
            "name", "legal_form", "status", "register_type", "register_number",
            "register_court", "registration_date", "purpose", "capital",
            "address", "representatives", "documents",
        ],
        "note": "Input: company name/EU-ID/register number -> Output: company data from German Commercial Register",
    },
    "ahrefs": {
        "id": "radeance/ahrefs-scraper",
        "name": "Ahrefs Domain Analytics",
        "publisher": "radeance",
        "full_id": "radeance/ahrefs-scraper",
        "capabilities": [
            "domain_rating",
            "url_rating",
            "traffic_analysis",
            "backlinks_analysis",
            "keyword_research",
            "keyword_difficulty",
            "serp_analysis",
            "competitor_analysis",
            "broken_links",
            "top_pages",
            "top_websites",
        ],
        "modes": ["subdomains", "exact", "prefix", "domain"],
        "countries": ["us", "uk", "de", "fr", "es", "it", "nl", "au", "ca", "jp"],
        "output_fields": [
            "domain_rating", "url_rating", "ahrefs_rank", "referring_domains",
            "backlinks", "organic_traffic", "organic_keywords", "traffic_value",
            "keywords", "competitors", "broken_links", "top_pages",
        ],
        "note": "Input: domain/keyword -> Output: DR, traffic, backlinks, keywords, competitors from Ahrefs",
    },
    "openactor_business": {
        "id": "h3OriIkWaInEm8g9q",
        "name": "Business Entity Search",
        "capabilities": [
            "company_search",
            "registration_lookup",
            "uk_companies_house",
            "us_sec",
            "australia_asic",
            "canada_corporations",
            "director_search",
            "filings",
            "sic_codes",
        ],
        "countries": ["GB", "US", "AU", "CA"],
        "search_modes": ["by_name", "by_registration_number"],
        "output_fields": [
            "entityName", "registrationNumber", "country", "status",
            "registeredAddress", "directors", "sicCodes", "filings",
            "firmographics", "searchResultsTop10", "diagnostics",
        ],
        "note": "Input: company name/registration number + country codes -> Output: entity data from UK/US/AU/CA registries",
    },
    "linkedin_company": {
        "id": "taHaRcqil3scbchuI",
        "name": "LinkedIn Company Scraper",
        "capabilities": [
            "company_profile",
            "company_posts",
            "employee_count",
            "specialties",
            "locations",
            "similar_companies",
        ],
        "output_fields": [
            "name", "headline", "url", "universalName", "employeeCount",
            "specialties", "locations", "founded", "logo", "posts",
            "similarCompanies", "affiliatedCompanies",
        ],
        "note": "Input: LinkedIn company URL/name -> Output: company profile, posts, employees, locations",
    },
    "reddit_profile": {
        "id": "ILMCNaVwoOZyWEsrk",
        "name": "Reddit User Profile Scraper",
        "capabilities": [
            "user_posts",
            "user_comments",
            "user_profile",
            "karma_data",
        ],
        "output_fields": [
            "title", "selftext", "subreddit", "author", "score",
            "upvote_ratio", "num_comments", "created_utc", "url",
            "is_video", "over_18",
        ],
        "note": "Input: Reddit user URL -> Output: user posts, comments, profile data",
    },
    "semrush_domain": {
        "id": "radeance/semrush-scraper",
        "name": "Semrush Domain Analyzer",
        "publisher": "radeance",
        "capabilities": [
            "authority_score",
            "domain_analytics",
            "traffic_data",
            "backlinks_profile",
            "keyword_rankings",
            "competitor_analysis",
            "ai_visibility",
            "seo_audit",
            "moz_integration",
        ],
        "output_fields": [
            "data_captured_at", "authority_score", "moz_domain_authority",
            "visits", "bounce_rate", "pages_per_visit", "traffic_organic",
            "traffic_paid", "backlinks_total", "backlink_domains_total",
            "ai_visibility_score", "global_rank", "country_rank",
        ],
        "note": "Input: domain URL, keyword -> Output: full SEO analysis with historical data",
    },
    "semrush_search": {
        "id": "TMBawM4LZpKN15DZX",
        "name": "Semrush Keyword Search",
        "capabilities": [
            "keyword_search",
            "serp_analysis",
            "search_results",
        ],
        "output_fields": [
            "title", "url", "description", "position", "domain",
        ],
        "note": "Input: query, resultsCount, searchType -> Output: search results",
    },
    "proxy_scraper": {
        "id": "UvkeX4n0DvIkcyIY3",
        "name": "Proxy List Aggregator",
        "publisher": "mstephen190",
        "full_id": "mstephen190/proxy-scraper",
        "capabilities": [
            "proxy_aggregation",
            "proxy_validation",
            "multi_source_scraping",
        ],
        "sources": [
            "free-proxy-list.net", "sslproxies.org", "us-proxy.org",
            "socks-proxy.net", "geonode.com", "spys.one", "hidemy.name",
            "proxynova.com", "proxy-list.download", "pubproxy.com",
        ],
        "input_fields": [
            "testProxies", "testTimeout", "testTarget",
            "kvStoreName", "pushToKvStore", "datasetName",
        ],
        "output_fields": ["host", "port", "full"],
        "note": "Scrapes ~2500 proxies from 17 sources, validates, returns ~20-60 working proxies",
    },
    "telegram_channel": {
        "id": "TpLqaxMYSJzwVnXoj",
        "name": "Telegram Channel Message Scraper",
        "publisher": "cheapget",
        "full_id": "cheapget/telegram-channel-message",
        "capabilities": [
            "channel_messages",
            "group_messages",
            "media_download",
            "engagement_metrics",
            "forward_tracking",
            "reactions",
            "service_events",
        ],
        "input_fields": [
            "telegram_target",  # https://t.me/channel or @channel
            "download_medias",  # text, image, all
            "start_date",  # YYYY-MM-DD or "7 days"
        ],
        "output_fields": [
            "id", "type", "date", "text", "sender", "silent", "pinned",
            "view_count", "reply_count", "forward_count", "reply_to",
            "album_id", "topic_name", "service_type", "service_info",
            "forward_info", "reactions", "media_url",
            "source_id", "source_name", "source_type",
        ],
        "pricing": {
            "message": 0.00038,
            "media": 0.00077,
        },
        "note": "Extract Telegram channel/group messages with 20+ fields, reactions, forwards, media",
    },
    "telegram_profile": {
        "id": "lAybf7rRybdzabbBk",
        "name": "Telegram Data Finder",
        "publisher": "agentx",
        "full_id": "agentx/telegram-info-scraper",
        "capabilities": [
            "user_profile",
            "bot_profile",
            "channel_profile",
            "group_profile",
            "batch_profiles",
            "contact_info",
            "premium_detection",
            "verification_status",
            "membership_analytics",
        ],
        "input_fields": [
            "user_name",  # List of usernames/@handles/URLs (5-10000)
        ],
        "output_fields": [
            # Core identity
            "id", "type", "usernames", "title", "first_name", "last_name",
            "phone", "lang_code", "description", "profile_photo",
            # Status flags
            "is_premium", "is_verified", "is_scam", "is_fake", "is_deleted",
            "is_support", "is_restricted", "is_blocked",
            # Communication settings
            "phone_calls", "video_calls", "voice_messages", "can_pin",
            "premium_contact", "private_calls", "private_reads",
            # User activity
            "last_seen", "common_chats_count", "has_scheduled", "can_manage_emoji",
            # Group/channel specific
            "member_count", "online_count", "admins_count", "banned_count",
            "join_to_send", "join_request", "is_forum", "no_forwards",
            "gigagroup", "slowmode", "created_date", "linked_chat_id",
            "view_members", "call_active", "view_stats", "has_location", "location",
        ],
        "pricing": {
            "per_target": 0.005,
            "min_per_run": 0.05,
        },
        "note": "Comprehensive 40+ field profile extraction for users/bots/groups/channels",
    },
    "telegram_profile_lite": {
        "id": "cheapget/telegram-profile",
        "name": "Telegram Profile Scraper (MTProto)",
        "publisher": "cheapget",
        "capabilities": [
            "user_profile",
            "bot_profile",
            "channel_profile",
            "group_profile",
            "supergroup_profile",
            "batch_profiles",  # 1-10,000 targets
            "contact_info",
            "premium_detection",
            "verification_status",
            "scam_detection",
            "mtproto_protocol",
        ],
        "input_fields": [
            "telegram_targets",  # Array: @user, t.me/user, https://t.me/user, username
        ],
        "output_fields": [
            # Meta
            "status", "source_url", "processor", "processed_at",
            # Core identity
            "type", "id", "usernames", "title", "first_name", "last_name",
            "phone", "lang_code", "description", "profile_photo",
            # Status flags
            "is_premium", "is_verified", "is_scam", "is_fake",
            "is_deleted", "is_support", "is_restricted", "is_blocked",
            # User communication
            "premium_contact", "phone_calls", "video_calls", "voice_messages",
            "can_pin", "private_calls", "private_reads",
            # User activity
            "last_seen", "common_chats_count", "has_scheduled", "can_manage_emoji",
            # Group/channel specific
            "member_count", "online_count", "admins_count", "banned_count",
            "join_to_send", "join_request", "is_forum", "no_forwards",
            "has_location", "gigagroup", "slowmode", "created_date",
            "view_members", "call_active", "view_stats", "linked_chat_id", "location",
        ],
        "pricing": {
            "per_profile": 0.0045,
            "runtime": 0.00001,
            "min_targets": 5,  # Minimum charge
            "max_targets": 10000,
        },
        "note": "MTProto-powered comprehensive profile extraction - 40+ fields, batch up to 10K",
    },
    "telegram_group_members": {
        "id": "cheapget/telegram-group-member",
        "name": "Telegram Group Member Extractor",
        "publisher": "cheapget",
        "capabilities": [
            "member_extraction",
            "deep_search",
            "hidden_groups",
            "historical_members",
            "admin_detection",
            "premium_detection",
        ],
        "input_fields": [
            "group_name",  # https://t.me/group or @group
            "deep_search",  # bool - enable for hidden groups + historical data
        ],
        "output_fields": [
            "id", "first_name", "last_name", "usernames", "phone", "type",
            "is_admin", "is_deleted", "is_verified", "is_premium",
            "is_scam", "is_fake", "is_restricted",
            "lang_code", "last_seen", "stories_hidden", "premium_contact",
        ],
        "pricing": {
            "standard": 0.0009,
            "deep_search": 0.0011,
            "max_billable": 10000,  # Max members charged
        },
        "note": "Extract group members with 15+ fields - supports deep search for hidden groups",
    },
    "uk_contracts_finder": {
        "id": "nocodeventure/uk-government-contracts",
        "name": "UK Government Contracts Finder",
        "publisher": "nocodeventure",
        "capabilities": [
            "contract_search",
            "tender_search",
            "awarded_contracts",
            "value_filter",
            "cpv_filter",
            "location_filter",
            "region_filter",
            "sme_filter",
        ],
        "input_fields": [
            "keywords", "postcode", "postcodeDistance", "regions",
            "locationType", "valueFrom", "valueTo", "cpvCodes",
            "includeEarlyEngagement", "includeFutureOpportunity",
            "includeOpportunity", "includeAwarded", "includeOpenOnly",
            "suitableForSME", "suitableForVCSE",
            "publishedFrom", "publishedTo", "closingFrom", "closingTo",
            "awardedFrom", "awardedTo", "maxResults", "scrapeDetails",
        ],
        "output_fields": [
            "title", "noticeIdentifier", "reference", "noticeStatus",
            "procurementStage", "description", "url", "value",
            "publishedDate", "closingDate", "contractStartDate", "contractEndDate",
            "location", "contractType", "procedureType", "cpvCodes", "cpvDescriptions",
            "isSuitableForSME", "isSuitableForVCSE",
            "buyer", "suppliers", "awardedDate", "awardedValue", "documents",
        ],
        "note": "UK public sector contracts - tenders, awarded contracts, procurement opportunities",
    },
}


# =============================================================================
# CLIENT MANAGEMENT
# =============================================================================

_client = None


def get_client():
    """Get or create Apify client singleton."""
    global _client
    if _client is None:
        if not APIFY_TOKEN:
            raise ValueError(
                "APIFY_API_TOKEN or APIFY_TOKEN environment variable required"
            )
        try:
            from apify_client import ApifyClient
            _client = ApifyClient(APIFY_TOKEN)
        except ImportError:
            raise ImportError(
                "apify-client not installed. Run: pip install apify-client"
            )
    return _client


def is_available() -> bool:
    """Check if Apify is configured and available."""
    return bool(APIFY_TOKEN)


# =============================================================================
# CORE EXECUTION
# =============================================================================

def run_actor(
    actor_id: str,
    run_input: Dict[str, Any],
    timeout_secs: int = 300,
    memory_mbytes: int = 1024,
) -> List[Dict[str, Any]]:
    """
    Run an Apify actor and return results.

    Args:
        actor_id: Actor ID (can be shortname from ACTORS or full ID)
        run_input: Actor input parameters
        timeout_secs: Maximum run time
        memory_mbytes: Memory allocation

    Returns:
        List of result items from dataset
    """
    # Resolve shortname to full actor ID
    resolved_id = ACTORS.get(actor_id, actor_id)

    client = get_client()

    run = client.actor(resolved_id).call(
        run_input=run_input,
        timeout_secs=timeout_secs,
        memory_mbytes=memory_mbytes,
    )

    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


async def run_actor_async(
    actor_id: str,
    run_input: Dict[str, Any],
    timeout_secs: int = 300,
) -> List[Dict[str, Any]]:
    """Async version of run_actor."""
    import asyncio
    return await asyncio.to_thread(
        run_actor, actor_id, run_input, timeout_secs
    )


# =============================================================================
# NEWS SCRAPERS
# =============================================================================

@dataclass
class NewsArticle:
    """Structured news article data."""
    url: str
    title: str = ""
    content: str = ""
    author: str = ""
    published_date: str = ""
    source: str = ""
    summary: str = ""
    entities: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_bloomberg(cls, data: Dict[str, Any]) -> "NewsArticle":
        """Create from Bloomberg scraper output."""
        return cls(
            url=data.get("url", ""),
            title=data.get("title", "") or data.get("headline", ""),
            content=data.get("content", "") or data.get("body", ""),
            author=data.get("author", "") or ", ".join(data.get("authors", [])),
            published_date=data.get("publishedAt", "") or data.get("date", ""),
            source="Bloomberg",
            summary=data.get("summary", "") or data.get("abstract", ""),
            entities=data.get("entities", []) or data.get("tags", []),
            raw=data,
        )


def scrape_bloomberg_article(url: str) -> NewsArticle:
    """
    Scrape a Bloomberg news article.

    Args:
        url: Bloomberg article URL

    Returns:
        NewsArticle with extracted data
    """
    results = run_actor("bloomberg_article", {"url": url})
    if results:
        return NewsArticle.from_bloomberg(results[0])
    return NewsArticle(url=url)


def scrape_bloomberg_articles(urls: List[str]) -> List[NewsArticle]:
    """
    Scrape multiple Bloomberg articles.

    Args:
        urls: List of Bloomberg article URLs

    Returns:
        List of NewsArticle objects
    """
    articles = []
    for url in urls:
        try:
            article = scrape_bloomberg_article(url)
            articles.append(article)
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            articles.append(NewsArticle(url=url))
    return articles


# =============================================================================
# SOCIAL MEDIA - BRIDGES TO PLATFORMS
# =============================================================================

def facebook_search(
    categories: List[str],
    locations: Optional[List[str]] = None,
    results_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search Facebook pages/places by category.
    Bridge to platforms/facebook.py
    """
    from .platforms.facebook import apify_facebook_search
    return apify_facebook_search(categories, locations, results_limit)


def threads_profile(username: str) -> Dict[str, Any]:
    """
    Scrape Threads profile.
    Bridge to platforms/threads.py
    """
    from .platforms.threads import scrape_profile
    return scrape_profile(username)


def threads_profiles(usernames: List[str]) -> List[Dict[str, Any]]:
    """
    Scrape multiple Threads profiles.
    Bridge to platforms/threads.py
    """
    from .platforms.threads import scrape_profiles
    return scrape_profiles(usernames)


# =============================================================================
# SEARCH ENGINE SCRAPERS
# =============================================================================

def google_search(
    query: str,
    num_results: int = 10,
    country: str = "us",
    language: str = "en",
) -> List[Dict[str, Any]]:
    """
    Perform Google search via Apify.

    Args:
        query: Search query
        num_results: Max results
        country: Country code
        language: Language code

    Returns:
        List of search results
    """
    run_input = {
        "queries": query,
        "maxPagesPerQuery": 1,
        "resultsPerPage": num_results,
        "countryCode": country,
        "languageCode": language,
    }
    return run_actor("google_search", run_input)


def google_maps_search(
    query: str,
    location: Optional[str] = None,
    max_results: int = 20,
    *,
    country_code: Optional[str] = None,
    city: Optional[str] = None,
    scrape_details: bool = False,
    scrape_contacts: bool = False,
    skip_closed: bool = False,
    language: str = "en",
) -> List[Dict[str, Any]]:
    """
    Search Google Maps for places/businesses.

    Args:
        query: Search query (e.g., "restaurants")
        location: Location to search in (free text)
        max_results: Maximum results per search term
        country_code: Country code (e.g., "us")
        city: City name
        scrape_details: Scrape full place details
        scrape_contacts: Extract contacts from websites
        skip_closed: Skip closed businesses
        language: Results language

    Returns:
        List of place results with full Google Maps data
    """
    run_input = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": max_results,
        "language": language,
        "skipClosedPlaces": skip_closed,
        "scrapePlaceDetailPage": scrape_details,
        "scrapeContacts": scrape_contacts,
    }

    if location:
        run_input["locationQuery"] = location
    if country_code:
        run_input["countryCode"] = country_code
    if city:
        run_input["city"] = city

    return run_actor("google_maps", run_input)


def google_maps_neighborhood(
    address: str,
    radius_km: float = 1.0,
) -> Dict[str, Any]:
    """
    Get neighborhood info for an address from Google Maps.
    Bridge to platforms/google_maps.py

    Args:
        address: Address to enrich
        radius_km: Search radius for nearby places

    Returns:
        Neighborhood info dict
    """
    from .platforms.google_maps import enrich_address_with_neighborhood
    info = enrich_address_with_neighborhood(address, search_radius_km=radius_km)
    return {
        "neighborhood": info.neighborhood,
        "city": info.city,
        "state": info.state,
        "country_code": info.country_code,
        "postal_code": info.postal_code,
        "plus_code": info.plus_code,
        "location": info.location,
        "nearby_places": info.nearby_places,
        "popular_categories": info.popular_categories,
    }


# =============================================================================
# GENERIC WEB SCRAPING
# =============================================================================

def scrape_url(
    url: str,
    selector: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generic URL scraping via Cheerio.

    Args:
        url: URL to scrape
        selector: Optional CSS selector

    Returns:
        Scraped data
    """
    run_input = {
        "startUrls": [{"url": url}],
        "pageFunction": """
        async function pageFunction(context) {
            const { $, request } = context;
            return {
                url: request.url,
                title: $('title').text(),
                body: $('body').text().substring(0, 5000),
            };
        }
        """,
    }
    results = run_actor("cheerio_scraper", run_input)
    return results[0] if results else {"url": url}


# =============================================================================
# BATCH OPERATIONS
# =============================================================================

def batch_scrape(
    actor_id: str,
    inputs: List[Dict[str, Any]],
    concurrent: int = 5,
) -> List[Dict[str, Any]]:
    """
    Batch scrape with multiple inputs.

    Args:
        actor_id: Actor to use
        inputs: List of input configs
        concurrent: Max concurrent runs

    Returns:
        Aggregated results from all runs
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_results = []

    with ThreadPoolExecutor(max_workers=concurrent) as executor:
        futures = {
            executor.submit(run_actor, actor_id, inp): inp
            for inp in inputs
        }

        for future in as_completed(futures):
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Batch scrape failed: {e}")

    return all_results


# =============================================================================
# MCP SERVER CONFIGURATION
# =============================================================================

MCP_SERVER_URL = "https://mcp.apify.com/sse"
MCP_SERVER_TOOLS_URL = "https://mcp.apify.com/sse?tools=actors,docs,apify/rag-web-browser"


def get_mcp_config(
    *,
    hosted: bool = True,
    token: Optional[str] = None,
    tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate MCP server configuration for Claude.

    Args:
        hosted: Use hosted server (True) or local npx (False)
        token: Apify token (uses env var if not provided)
        tools: List of tools to enable (default: actors, docs)

    Returns:
        MCP configuration dict for claude settings

    Example:
        config = get_mcp_config()
        # Add to claude_desktop_config.json or MCP settings
    """
    api_token = token or APIFY_TOKEN
    if not api_token:
        raise ValueError("APIFY_TOKEN required for MCP config")

    if hosted:
        tool_list = tools or ["actors", "docs", "apify/rag-web-browser"]
        tool_param = ",".join(tool_list)
        return {
            "mcpServers": {
                "apify": {
                    "url": f"{MCP_SERVER_URL}?tools={tool_param}",
                    "headers": {
                        "Authorization": f"Bearer {api_token}"
                    }
                }
            }
        }
    else:
        return {
            "mcpServers": {
                "apify": {
                    "command": "npx",
                    "args": ["@apify/actors-mcp-server"],
                    "env": {
                        "APIFY_TOKEN": api_token
                    }
                }
            }
        }


def print_mcp_config(hosted: bool = True) -> None:
    """Print MCP configuration for copy/paste."""
    import json
    try:
        config = get_mcp_config(hosted=hosted)
        print(json.dumps(config, indent=2))
    except ValueError as e:
        print(f"Error: {e}")
        print("\nSet APIFY_TOKEN environment variable or pass token parameter.")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Config
    "APIFY_TOKEN",
    "ACTORS",
    "ACTOR_INFO",
    "is_available",
    "get_client",

    # Core
    "run_actor",
    "run_actor_async",

    # News
    "NewsArticle",
    "scrape_bloomberg_article",
    "scrape_bloomberg_articles",

    # Social Media (bridges)
    "facebook_search",
    "threads_profile",
    "threads_profiles",

    # Search
    "google_search",
    "google_maps_search",
    "google_maps_neighborhood",

    # Generic
    "scrape_url",
    "batch_scrape",

    # MCP
    "MCP_SERVER_URL",
    "get_mcp_config",
    "print_mcp_config",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python apify.py <actor> <input_json>")
        print("\nActors:")
        for name, actor_id in ACTORS.items():
            print(f"  {name}: {actor_id}")
        sys.exit(1)

    actor = sys.argv[1]
    input_json = json.loads(sys.argv[2])

    results = run_actor(actor, input_json)
    print(json.dumps(results, indent=2, default=str))
