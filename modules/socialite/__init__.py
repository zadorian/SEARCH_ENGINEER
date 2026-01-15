"""SOCIALITE - Social Media Search and Analysis."""

from . import platforms
from . import engines
from . import analysis
from . import apify

# Account identification
from .identifier import (
    SocialIdentifier,
    SocialIdentificationResult,
    ExtractedAccount,
    VerifiedAccount,
    identify_social_accounts,
)

# Social data routing (BrightData collection with prefix-based queries)
from .social_data_router import (
    SocialDataRouter,
    route_social_query,
    parse_social_query,
    is_social_query,
    ParsedQuery,
    SocialDataResult,
    Platform,
    EntityType,
    get_supported_prefixes,
    detect_platform_from_url,
)

# BrightData APIs (structured data collection via official SDK)
from .brightdata_social import (
    # SDK client access
    get_brightdata_client,
    get_brightdata_sync_client,
    brightdata_sdk_available,
    # Facebook client wrapper
    FacebookAPI,
    # Facebook data structures
    FacebookPost,
    FacebookComment,
    FacebookReel,
    FacebookGroupPost,
    FacebookProfile,
    FacebookEvent,
    # Facebook convenience functions
    facebook_posts_by_profile,
    facebook_posts_by_group,
    facebook_post,
    facebook_comments,
    facebook_reels,
    facebook_profile,
    facebook_profiles,
    facebook_event,
    facebook_events,
    facebook_posts_by_username,
    brightdata_facebook_available,
    FACEBOOK_DATASETS,
)

# LinkedIn BrightData integration
from .platforms.linkedin import (
    # Data structures
    LinkedInProfile,
    LinkedInCompany,
    LinkedInJob,
    LinkedInPost,
    # URL-based
    linkedin_profile_data as person_linkedin,
    linkedin_company_data as company_linkedin,
    linkedin_job_data as job_linkedin,
    linkedin_jobs_data as jobs_linkedin,
    linkedin_post_data as post_linkedin,
    linkedin_posts_data as posts_linkedin,
    # name/keyword input
    search_profiles as name_person_linkedin,
    search_jobs as job,
    discover_posts as person_posts_linkedin,
    # Collector class
    LinkedInDataCollector,
    # Dataset IDs
    LINKEDIN_DATASETS,
)

# Apify unified integration
from .apify import (
    # Config
    APIFY_TOKEN,
    ACTORS as APIFY_ACTORS,
    is_available as apify_available,
    get_client as get_apify_client,
    # Core
    run_actor as apify_run,
    # News
    NewsArticle,
    scrape_bloomberg_article,
    scrape_bloomberg_articles,
    # Social bridges
    facebook_search as apify_facebook_search,
    threads_profile as apify_threads_profile,
    threads_profiles as apify_threads_profiles,
    # Search
    google_search as apify_google_search,
    google_maps_search as apify_google_maps,
)

__version__ = "1.0.0"
__all__ = [
    # Submodules
    "platforms",
    "engines",
    "analysis",
    "apify",
    # Account identification
    "SocialIdentifier",
    "SocialIdentificationResult",
    "ExtractedAccount",
    "VerifiedAccount",
    "identify_social_accounts",
    # Social data routing
    "SocialDataRouter",
    "route_social_query",
    "parse_social_query",
    "is_social_query",
    "ParsedQuery",
    "SocialDataResult",
    "Platform",
    "EntityType",
    "get_supported_prefixes",
    "detect_platform_from_url",
    # BrightData SDK access
    "get_brightdata_client",
    "get_brightdata_sync_client",
    "brightdata_sdk_available",
    # BrightData Facebook
    "FacebookAPI",
    "FacebookPost",
    "FacebookComment",
    "FacebookReel",
    "FacebookGroupPost",
    "FacebookProfile",
    "FacebookEvent",
    "facebook_posts_by_profile",
    "facebook_posts_by_group",
    "facebook_post",
    "facebook_comments",
    "facebook_reels",
    "facebook_profile",
    "facebook_profiles",
    "facebook_event",
    "facebook_events",
    "facebook_posts_by_username",
    "brightdata_facebook_available",
    "FACEBOOK_DATASETS",
    # BrightData LinkedIn
    "LinkedInProfile",
    "LinkedInCompany",
    "LinkedInJob",
    "LinkedInPost",
    "person_linkedin",
    "company_linkedin",
    "job_linkedin",
    "jobs_linkedin",
    "post_linkedin",
    "posts_linkedin",
    "name_person_linkedin",
    "job",
    "person_posts_linkedin",
    "LinkedInDataCollector",
    "LINKEDIN_DATASETS",
    # Apify unified integration
    "APIFY_TOKEN",
    "APIFY_ACTORS",
    "apify_available",
    "get_apify_client",
    "apify_run",
    "NewsArticle",
    "scrape_bloomberg_article",
    "scrape_bloomberg_articles",
    "apify_facebook_search",
    "apify_threads_profile",
    "apify_threads_profiles",
    "apify_google_search",
    "apify_google_maps",
]
