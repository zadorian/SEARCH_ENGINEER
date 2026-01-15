#!/usr/bin/env python3
"""
Facebook platform support for Socialite.

Provides:
- URL generators for profiles, search, pages, groups
- BrightData API integration for structured data collection (posts, comments, reels)

URL Generators (no auth required):
    facebook_profile(username) -> profile URL
    facebook_search(query) -> Google site search
    facebook_people(name) -> people search URL
    facebook_pages(query) -> pages search URL
    facebook_groups(query) -> groups search URL

BrightData Data Collection (requires BRIGHTDATA_API_TOKEN):
    collect_posts(profile_url, num_of_posts) -> list[dict]
    collect_group_posts(group_url, num_of_posts) -> list[dict]
    collect_comments(post_url, num_of_comments) -> list[dict]
    collect_reels(profile_url, num_of_posts) -> list[dict]

    # Typed wrappers (returns dataclasses)
    FacebookDataCollector - async context manager for typed results
"""

import os
import re
import json
import base64
import requests
from urllib.parse import quote_plus, quote, urlencode, urlparse, parse_qs
from typing import Optional, Any, Tuple, List, Dict, Iterable, Union, Sequence
import logging

from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# APIFY INTEGRATION - Facebook Search
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
FACEBOOK_SEARCH_ACTOR_ID = "Us34x9p7VgjCz99H6"


def _get_apify_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


def apify_facebook_search(
    categories: List[str],
    locations: Optional[List[str]] = None,
    results_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search Facebook pages/places by category and location using Apify.

    Args:
        categories: List of categories to search (e.g., ["Pub", "Restaurant"])
        locations: Optional list of locations to filter by
        results_limit: Maximum results to return (default 20)

    Returns:
        List of Facebook page/place results
    """
    client = _get_apify_client()

    run_input = {
        "categories": categories,
        "locations": locations or [],
        "resultsLimit": results_limit,
    }

    run = client.actor(FACEBOOK_SEARCH_ACTOR_ID).call(run_input=run_input)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def apify_facebook_search_category(
    category: str,
    location: Optional[str] = None,
    results_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search Facebook for a single category.

    Args:
        category: Category to search (e.g., "Pub", "Restaurant", "Hotel")
        location: Optional location filter
        results_limit: Maximum results

    Returns:
        List of results
    """
    locations = [location] if location else []
    return apify_facebook_search([category], locations, results_limit)


def apify_facebook_places(
    query: str,
    location: Optional[str] = None,
    results_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search Facebook places/businesses.

    Args:
        query: Search query (treated as category)
        location: Optional location
        results_limit: Max results

    Returns:
        List of place results
    """
    return apify_facebook_search([query], [location] if location else [], results_limit)


# =============================================================================
# URL GENERATORS (no auth required)
# =============================================================================

def facebook_profile(username: str) -> str:
    """Direct link to Facebook profile"""
    return f"https://www.facebook.com/{username}"


def facebook_search(query: str) -> str:
    """Facebook search via Google (Facebook's search is locked down without auth)"""
    google_query = f"site:facebook.com {query}"
    return f"https://www.google.com/search?q={quote_plus(google_query)}"


def facebook_people(name: str) -> str:
    """Search Facebook for people with this name"""
    return f"https://www.facebook.com/search/people/?q={quote(name)}"


def facebook_pages(query: str) -> str:
    """Search Facebook pages"""
    return f"https://www.facebook.com/search/pages/?q={quote(query)}"


def facebook_groups(query: str) -> str:
    """Search Facebook groups"""
    return f"https://www.facebook.com/search/groups/?q={quote(query)}"


# =============================================================================
# BRIGHTDATA INTEGRATION
# =============================================================================

# Import BrightData components
try:
    from ..brightdata_social import (
        FacebookAPI,
        FacebookPost,
        FacebookComment,
        FacebookReel,
        FacebookGroupPost,
        brightdata_facebook_available,
        get_brightdata_client,
    )
    BRIGHTDATA_AVAILABLE = True
except ImportError:
    BRIGHTDATA_AVAILABLE = False
    FacebookAPI = None
    FacebookPost = None
    FacebookComment = None
    FacebookReel = None
    FacebookGroupPost = None
    brightdata_facebook_available = lambda: False
    get_brightdata_client = None


def is_data_collection_available() -> bool:
    """Check if BrightData data collection is available."""
    return BRIGHTDATA_AVAILABLE and brightdata_facebook_available()


# =============================================================================
# DATA COLLECTION FUNCTIONS
# =============================================================================

async def collect_posts(
    profile_url: str,
    num_of_posts: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Collect posts from a Facebook profile.

    Args:
        profile_url: Facebook profile URL (e.g., "https://facebook.com/zuck")
        num_of_posts: Maximum posts to collect (None = no limit)
        start_date: Start date filter MM-DD-YYYY
        end_date: End date filter MM-DD-YYYY

    Returns:
        List of post dicts with: post_id, content, hashtags, num_likes, num_comments, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Facebook data collection")
        return []

    try:
        async with FacebookAPI() as fb:
            posts = await fb.posts_by_profile(
                profile_url,
                num_of_posts=num_of_posts,
                start_date=start_date,
                end_date=end_date,
            )
            return [p.raw for p in posts]
    except Exception as e:
        logger.error(f"Failed to collect Facebook posts: {e}")
        return []


async def collect_group_posts(
    group_url: str,
    num_of_posts: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Collect posts from a Facebook group.

    Args:
        group_url: Facebook group URL
        num_of_posts: Maximum posts to collect
        start_date: Start date filter MM-DD-YYYY
        end_date: End date filter MM-DD-YYYY

    Returns:
        List of group post dicts with group metadata
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Facebook data collection")
        return []

    try:
        async with FacebookAPI() as fb:
            posts = await fb.posts_by_group(
                group_url,
                num_of_posts=num_of_posts,
                start_date=start_date,
                end_date=end_date,
            )
            return [p.raw for p in posts]
    except Exception as e:
        logger.error(f"Failed to collect Facebook group posts: {e}")
        return []


async def collect_comments(
    post_url: str,
    num_of_comments: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Collect comments from a Facebook post.

    Args:
        post_url: Facebook post URL
        num_of_comments: Maximum comments to collect
        start_date: Start date filter MM-DD-YYYY
        end_date: End date filter MM-DD-YYYY

    Returns:
        List of comment dicts with: comment_id, comment_text, user_name, replies, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Facebook data collection")
        return []

    try:
        async with FacebookAPI() as fb:
            comments = await fb.comments(
                post_url,
                num_of_comments=num_of_comments,
                start_date=start_date,
                end_date=end_date,
            )
            return [c.raw for c in comments]
    except Exception as e:
        logger.error(f"Failed to collect Facebook comments: {e}")
        return []


async def collect_reels(
    profile_url: str,
    num_of_posts: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Collect reels from a Facebook profile.

    Args:
        profile_url: Facebook profile URL
        num_of_posts: Maximum reels to collect (default: up to 1600)
        start_date: Start date filter
        end_date: End date filter

    Returns:
        List of reel dicts with: post_id, content, video_view_count, audio, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Facebook data collection")
        return []

    try:
        async with FacebookAPI() as fb:
            reels = await fb.reels(
                profile_url,
                num_of_posts=num_of_posts,
                start_date=start_date,
                end_date=end_date,
            )
            return [r.raw for r in reels]
    except Exception as e:
        logger.error(f"Failed to collect Facebook reels: {e}")
        return []


async def collect_post_by_url(post_url: str) -> Optional[dict]:
    """
    Collect data from a specific Facebook post URL.

    Args:
        post_url: Direct Facebook post URL

    Returns:
        Post dict or None if failed
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for Facebook data collection")
        return None

    try:
        async with FacebookAPI() as fb:
            post = await fb.posts_by_url(post_url)
            return post.raw if post else None
    except Exception as e:
        logger.error(f"Failed to collect Facebook post: {e}")
        return None


# =============================================================================
# TYPED DATA COLLECTOR (convenience wrapper)
# =============================================================================

class FacebookDataCollector:
    """
    Typed Facebook data collector using BrightData.

    Usage:
        async with FacebookDataCollector() as fb:
            posts: list[FacebookPost] = await fb.posts("https://facebook.com/zuck", 10)
            comments: list[FacebookComment] = await fb.comments(post_url)
            reels: list[FacebookReel] = await fb.reels(profile_url)
    """

    def __init__(self, timeout: int = 240):
        self.timeout = timeout
        self._api: Optional[Any] = None

    @property
    def available(self) -> bool:
        return is_data_collection_available()

    async def __aenter__(self):
        if not BRIGHTDATA_AVAILABLE:
            raise RuntimeError("BrightData SDK not installed")
        if not brightdata_facebook_available():
            raise RuntimeError("BRIGHTDATA_API_TOKEN not configured")
        self._api = FacebookAPI(timeout=self.timeout)
        await self._api.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._api:
            await self._api.__aexit__(exc_type, exc_val, exc_tb)

    async def posts(
        self,
        profile_url: str,
        num_of_posts: Optional[int] = None,
        **kwargs
    ) -> list:
        """Collect posts from profile. Returns list[FacebookPost]."""
        return await self._api.posts_by_profile(profile_url, num_of_posts, **kwargs)

    async def group_posts(
        self,
        group_url: str,
        num_of_posts: Optional[int] = None,
        **kwargs
    ) -> list:
        """Collect posts from group. Returns list[FacebookGroupPost]."""
        return await self._api.posts_by_group(group_url, num_of_posts, **kwargs)

    async def comments(
        self,
        post_url: str,
        num_of_comments: Optional[int] = None,
        **kwargs
    ) -> list:
        """Collect comments from post. Returns list[FacebookComment]."""
        return await self._api.comments(post_url, num_of_comments, **kwargs)

    async def reels(
        self,
        profile_url: str,
        num_of_posts: Optional[int] = None,
        **kwargs
    ) -> list:
        """Collect reels from profile. Returns list[FacebookReel]."""
        return await self._api.reels(profile_url, num_of_posts, **kwargs)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # URL generators
    "facebook_profile",
    "facebook_search",
    "facebook_people",
    "facebook_pages",
    "facebook_groups",
    # Apify search
    "apify_facebook_search",
    "apify_facebook_search_category",
    "apify_facebook_places",
    # Data collection
    "is_data_collection_available",
    "collect_posts",
    "collect_group_posts",
    "collect_comments",
    "collect_reels",
    "collect_post_by_url",
    # Typed collector
    "FacebookDataCollector",
    # Re-exports from brightdata_social
    "FacebookPost",
    "FacebookComment",
    "FacebookReel",
    "FacebookGroupPost",
]

# =============================================================================
# SEARCH HELPERS (merged from facebook_search.py)
# =============================================================================



logger = logging.getLogger(__name__)


def _quote_phrase(text: str) -> str:
    return quote(f'"{text}"')


def facebook_top(query: str) -> str:
    return f"https://www.facebook.com/search/top/?q={_quote_phrase(query)}"


def facebook_people(query: str) -> str:
    return f"https://www.facebook.com/search/people/?q={_quote_phrase(query)}"


def facebook_photos(query: str) -> str:
    return f"https://www.facebook.com/search/photos/?q={_quote_phrase(query)}"


def facebook_videos(query: str) -> str:
    return f"https://www.facebook.com/search/videos/?q={_quote_phrase(query)}"


def facebook_marketplace(query: str) -> str:
    return f"https://www.facebook.com/search/marketplace/?q={_quote_phrase(query)}"


def facebook_pages(query: str) -> str:
    return f"https://www.facebook.com/search/pages/?q={_quote_phrase(query)}"


def _build_filters_payload(start_date: Optional[str], end_date: Optional[str]) -> Optional[str]:
    """Return Base64 URL filter payload for Facebook date filters."""

    if not start_date and not end_date:
        return None

    def _split(parts: str) -> Dict[str, str]:
        y, m, d = parts.split("-")
        return {
            "year": y,
            "month": f"{y}-{int(m)}",
            "day": f"{y}-{int(m)}-{int(d)}",
        }

    payload_args: Dict[str, str] = {}
    if start_date:
        payload_args.update({
            "start_year": _split(start_date)["year"],
            "start_month": _split(start_date)["month"],
            "start_day": _split(start_date)["day"],
        })
    if end_date:
        payload_args.update({
            "end_year": _split(end_date)["year"],
            "end_month": _split(end_date)["month"],
            "end_day": _split(end_date)["day"],
        })

    if not payload_args:
        return None

    filters = {
        "rp_creation_time": json.dumps({"name": "creation_time", "args": json.dumps(payload_args)}),
        "rp_author": json.dumps({"name": "merged_public_posts", "args": ""}),
    }
    encoded = base64.b64encode(json.dumps(filters, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    return encoded


def facebook_search_with_filters(scope: str, query: str, filters_b64: Optional[str]) -> str:
    params = {"q": query}
    if filters_b64:
        params["filters"] = filters_b64
    return f"https://www.facebook.com/search/{scope}/?{urlencode(params, quote_via=quote_plus)}"


def _resolve_profile_identifier(profile_url: str) -> str:
    parsed = urlparse(profile_url)
    qs = parse_qs(parsed.query)
    if "id" in qs and qs["id"]:
        return qs["id"][0]

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return ""

    identifier = parts[-1]
    if identifier.lower() == "profile.php":
        return qs.get("id", [""])[0]
    return identifier


def resolve_user_id_via_graph(
    profile_url: str,
    *,
    access_token: Optional[str] = None,
    graph_version: str = "v23.0",
) -> Tuple[Optional[str], Optional[str]]:
    token = access_token or os.getenv("FACEBOOK_GRAPH_ACCESS_TOKEN")
    if not token:
        return None, "Missing access token (set FACEBOOK_GRAPH_ACCESS_TOKEN or pass access_token)"

    identifier = _resolve_profile_identifier(profile_url)
    if not identifier:
        return None, "Could not parse identifier from URL"

    try:
        resp = requests.get(
            f"https://graph.facebook.com/{graph_version}/{identifier}",
            params={"fields": "id,name", "access_token": token},
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"Exception: {exc}"

    if resp.status_code == 200:
        data = resp.json()
        return data.get("id"), data.get("name")

    return None, f"Error {resp.status_code}: {resp.text}"


def resolve_user_id_with_cookie(
    profile_url: str,
    *,
    cookie: str,
    timeout: int = 10,
) -> Tuple[Optional[str], Optional[str]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Cookie": cookie,
    }

    try:
        parsed = urlparse(profile_url)
        username = parsed.path.strip("/")
        if not username or username.lower().startswith("profile.php"):
            target = profile_url
        else:
            target = f"https://m.facebook.com/{username}"

        resp = requests.get(target, headers=headers, allow_redirects=True, timeout=timeout)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"Exception: {exc}"

    # Trace redirects first
    chain = [resp] + list(getattr(resp, "history", []))
    for hop in chain:
        parsed = urlparse(hop.url)
        if parsed.path.endswith("/profile.php"):
            qs = parse_qs(parsed.query)
            if "id" in qs and qs["id"]:
                return qs["id"][0], None

    html = resp.text or ""
    markers = (
        "entity_id\":\"",
        "profile_id\":\"",
        "container_ID\":\"",
        "selectedID\":\"",
        "profile_owner\":\"",
    )
    for marker in markers:
        idx = html.find(marker)
        if idx != -1:
            start = idx + len(marker)
            end = html.find("\"", start)
            if end != -1 and html[start:end].isdigit():
                return html[start:end], None

    regexes = (
        r'"entity_id"\s*:\s*"(\d+)"',
        r'"profile_id"\s*:\s*"(\d+)"',
        r'"container_ID"\s*:\s*"(\d+)"',
        r'"selectedID"\s*:\s*"(\d+)"',
        r'"profile_owner"\s*:\s*"(\d+)"',
        r'\buser\s*ID\b[^\d]*(\d+)',
    )
    for pat in regexes:
        match = re.search(pat, html, re.IGNORECASE)
        if match:
            return match.group(1), None

    return None, "Could not extract user id (cookie may be invalid or insufficient access)"


def fb_user_timeline(user_id: str) -> str:
    return f"https://www.facebook.com/profile.php?id={quote(user_id)}"


def fb_user_photos(user_id: str) -> str:
    return f"https://www.facebook.com/profile.php?id={quote(user_id)}&sk=photos"


def fb_user_videos(user_id: str) -> str:
    return f"https://www.facebook.com/profile.php?id={quote(user_id)}&sk=videos"


def fb_user_search(user_id: str, keyword: str) -> str:
    return f"https://www.facebook.com/profile/{quote(user_id)}/search/?q={quote(keyword)}"


def fb_location_posts(location_id: str) -> str:
    return f"https://www.facebook.com/search/str/{quote(location_id)}/stories-in"


def fb_location_photos(location_id: str) -> str:
    return f"https://www.facebook.com/search/str/{quote(location_id)}/photos-in"


def fb_location_videos(location_id: str) -> str:
    return f"https://www.facebook.com/search/str/{quote(location_id)}/videos-in"


def fb_location_events(location_id: str) -> str:
    return f"https://www.facebook.com/search/str/{quote(location_id)}/events-in"


def facebook_results(
    query: str,
    *,
    include_verticals: Optional[Iterable[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Compatibility helper mirroring legacy `as_results` output."""
    results = build_facebook_links(
        query,
        include_verticals=include_verticals,
        start_date=start_date,
        end_date=end_date,
    )

    serpapi_key = os.getenv("SERPAPI_KEY")
    if serpapi_key and query:
        results.append({
            "title": f"Facebook Profile (SerpAPI): {query}",
            "url": f"https://serpapi.com/search.json?engine=facebook_profile&profile_id={quote(query)}",
            "source": "facebook_profile",
            "search_engine": "facebook",
            "engine_code": "FBP",
            "engine_badge": "FB",
            "metadata": {
                "type": "profile_lookup",
                "profile_id": query,
                "serpapi": True,
            },
        })

    return results


def facebook_top_by_date(query: str, start_date: str, end_date: str) -> str:
    payload = _build_filters_payload(start_date, end_date)
    if payload:
        return facebook_search_with_filters("top", query, payload)
    return facebook_top(query)


def facebook_photos_by_date(query: str, start_date: str, end_date: str) -> str:
    payload = _build_filters_payload(start_date, end_date)
    if payload:
        return facebook_search_with_filters("photos", query, payload)
    return facebook_photos(query)


def facebook_videos_by_date(query: str, start_date: str, end_date: str) -> str:
    payload = _build_filters_payload(start_date, end_date)
    if payload:
        return facebook_search_with_filters("videos", query, payload)
    return facebook_videos(query)


def facebook_get_user_id(
    profile_url: str,
    *,
    access_token: Optional[str] = None,
    graph_version: str = "v23.0",
) -> Tuple[Optional[str], Optional[str]]:
    """Compatibility alias for Graph API ID lookup."""

    return resolve_user_id_via_graph(
        profile_url,
        access_token=access_token,
        graph_version=graph_version,
    )


def _build_standard_verticals(
    query: str,
    allowed: Sequence[str],
    filters_payload: Optional[str],
) -> List[Dict[str, Any]]:
    vertical_map = {
        "top": ("Facebook Top", facebook_top, "top"),
        "people": ("Facebook People", facebook_people, "people"),
        "photos": ("Facebook Photos", facebook_photos, "photos"),
        "videos": ("Facebook Videos", facebook_videos, "videos"),
        "marketplace": ("Facebook Marketplace", facebook_marketplace, "marketplace"),
        "pages": ("Facebook Pages", facebook_pages, "pages"),
    }

    results: List[Dict[str, Any]] = []
    for vertical, (title, builder, scope) in vertical_map.items():
        if vertical not in allowed:
            continue
        url = builder(query)
        if filters_payload:
            url = facebook_search_with_filters(scope, query, filters_payload)
        results.append({
            "title": f"{title}: {query}",
            "url": url,
            "source": "facebook",
            "search_engine": "facebook",
            "engine_code": "FB",
            "engine_badge": "FB",
            "metadata": {
                "type": "standard_vertical",
                "vertical": vertical,
                "has_date_filter": bool(filters_payload),
            },
        })
    return results


def _build_user_verticals(
    user_id: str,
    *,
    include_sections: Optional[Iterable[str]] = None,
    keyword: Optional[str] = None,
    resolved_name: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    allowed = set(include_sections or ["timeline", "photos", "videos", "search"])
    section_map = {
        "timeline": ("Facebook User Timeline", fb_user_timeline),
        "photos": ("Facebook User Photos", fb_user_photos),
        "videos": ("Facebook User Videos", fb_user_videos),
    }

    results: List[Dict[str, Any]] = []
    label = resolved_name or user_id

    for section, (title, builder) in section_map.items():
        if section not in allowed:
            continue
        url = builder(user_id)
        results.append({
            "title": f"{title}: {label}",
            "url": url,
            "source": "facebook",
            "search_engine": "facebook",
            "engine_code": "FB",
            "engine_badge": "FB",
            "metadata": {
                "type": "user_vertical",
                "section": section,
                "user_id": user_id,
                "resolved_name": resolved_name,
                "profile_url": profile_url,
            },
        })

    if "search" in allowed:
        keyword_to_use = keyword or label
        results.append({
            "title": f"Facebook User Search: {label} → {keyword_to_use}",
            "url": fb_user_search(user_id, keyword_to_use),
            "source": "facebook",
            "search_engine": "facebook",
            "engine_code": "FB",
            "engine_badge": "FB",
            "metadata": {
                "type": "user_vertical",
                "section": "search",
                "user_id": user_id,
                "resolved_name": resolved_name,
                "profile_url": profile_url,
                "keyword": keyword_to_use,
            },
        })

    return results


def _build_location_verticals(
    location_id: str,
    *,
    include_sections: Optional[Iterable[str]] = None,
    label: Optional[str] = None,
) -> List[Dict[str, Any]]:
    allowed = set(include_sections or ["stories", "photos", "videos", "events"])
    section_map = {
        "stories": ("Facebook Location Stories", fb_location_posts),
        "photos": ("Facebook Location Photos", fb_location_photos),
        "videos": ("Facebook Location Videos", fb_location_videos),
        "events": ("Facebook Location Events", fb_location_events),
    }

    results: List[Dict[str, Any]] = []
    for section, (title, builder) in section_map.items():
        if section not in allowed:
            continue
        results.append({
            "title": f"{title}: {label or location_id}",
            "url": builder(location_id),
            "source": "facebook",
            "search_engine": "facebook",
            "engine_code": "FB",
            "engine_badge": "FB",
            "metadata": {
                "type": "location_vertical",
                "section": section,
                "location_id": location_id,
                "label": label,
            },
        })
    return results


def build_facebook_links(
    query: str,
    *,
    include_verticals: Optional[Iterable[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    profile_url: Optional[str] = None,
    user_id: Optional[str] = None,
    access_token: Optional[str] = None,
    graph_version: str = "v23.0",
    cookie: Optional[str] = None,
    include_user_sections: Optional[Iterable[str]] = None,
    user_keyword: Optional[str] = None,
    location_id: Optional[str] = None,
    include_location_sections: Optional[Iterable[str]] = None,
    location_label: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return list of Facebook entry points for the given query."""

    allowed = set(include_verticals or ["top", "people", "photos", "videos", "marketplace", "pages"])
    filters_payload = _build_filters_payload(start_date, end_date)

    results: List[Dict[str, Any]] = []
    results.extend(_build_standard_verticals(query, allowed, filters_payload))

    resolved_user_id = user_id
    resolved_name: Optional[str] = None
    user_error: Optional[str] = None

    if not resolved_user_id and profile_url:
        resolved_user_id, name_or_error = resolve_user_id_via_graph(
            profile_url,
            access_token=access_token,
            graph_version=graph_version,
        )
        if resolved_user_id:
            resolved_name = name_or_error
        else:
            user_error = name_or_error

    if not resolved_user_id and profile_url and cookie:
        resolved_user_id, cookie_error = resolve_user_id_with_cookie(
            profile_url,
            cookie=cookie,
        )
        if resolved_user_id:
            user_error = None
        else:
            user_error = user_error or cookie_error

    if resolved_user_id:
        results.extend(
            _build_user_verticals(
                resolved_user_id,
                include_sections=include_user_sections,
                keyword=user_keyword,
                resolved_name=resolved_name,
                profile_url=profile_url,
            )
        )
    elif profile_url and user_error:
        logger.info("Facebook user resolution failed for %s: %s", profile_url, user_error)

    if location_id:
        results.extend(
            _build_location_verticals(
                location_id,
                include_sections=include_location_sections,
                label=location_label or query,
            )
        )

    return results


@dataclass
class FacebookTargetedSearch:
    """Simple wrapper to integrate Facebook vertical links into targeted search."""

    include_verticals: Optional[Iterable[str]] = None
    include_user_sections: Optional[Iterable[str]] = None
    include_location_sections: Optional[Iterable[str]] = None

    def search(
        self,
        query: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        profile_url: Optional[str] = None,
        user_id: Optional[str] = None,
        user_keyword: Optional[str] = None,
        access_token: Optional[str] = None,
        graph_version: str = "v23.0",
        cookie: Optional[str] = None,
        location_id: Optional[str] = None,
        location_label: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        return build_facebook_links(
            query,
            include_verticals=self.include_verticals,
            start_date=start_date,
            end_date=end_date,
            profile_url=profile_url,
            user_id=user_id,
            access_token=access_token,
            graph_version=graph_version,
            cookie=cookie,
            include_user_sections=self.include_user_sections,
            user_keyword=user_keyword,
            location_id=location_id,
            include_location_sections=self.include_location_sections,
            location_label=location_label,
        )


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class FacebookPost:
    """Facebook post data."""
    post_id: str
    post_url: str
    content: str = ""
    hashtags: list[str] = field(default_factory=list)
    date_posted: Optional[datetime] = None
    num_comments: int = 0
    num_likes: int = 0
    num_shares: int = 0

    # Page/Profile info
    page_name: str = ""
    page_category: str = ""
    page_followers: int = 0
    profile_handle: str = ""

    # Media
    post_image: str = ""
    attachments: list[str] = field(default_factory=list)
    video_view_count: int = 0

    # Raw data
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "FacebookPost":
        """Create from BrightData API response."""
        return cls(
            post_id=data.get("post_id", ""),
            post_url=data.get("post_url", "") or data.get("url", ""),
            content=data.get("content", ""),
            hashtags=data.get("hashtags", []) or [],
            date_posted=cls._parse_date(data.get("date_posted")),
            num_comments=data.get("num_comments", 0) or 0,
            num_likes=data.get("num_likes", 0) or 0,
            num_shares=data.get("num_shares", 0) or 0,
            page_name=data.get("page_name", ""),
            page_category=data.get("page_category", ""),
            page_followers=data.get("page_followers", 0) or 0,
            profile_handle=data.get("profile_handle", ""),
            post_image=data.get("post_image", ""),
            attachments=data.get("attachments", []) or [],
            video_view_count=data.get("video_view_count", 0) or 0,
            raw=data,
        )

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m-%d-%Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None


@dataclass
class FacebookComment:
    """Facebook comment data."""
    comment_id: str
    comment_text: str = ""
    num_likes: int = 0
    num_replies: int = 0
    commenter_url: str = ""
    user_name: str = ""
    user_id: str = ""
    post_id: str = ""
    post_url: str = ""
    attached_files: list[str] = field(default_factory=list)
    video_length: int = 0
    replies: list["FacebookComment"] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "FacebookComment":
        """Create from BrightData API response."""
        replies_raw = data.get("replies", []) or []
        replies = [cls.from_api(r) for r in replies_raw if isinstance(r, dict)]

        return cls(
            comment_id=data.get("comment_id", ""),
            comment_text=data.get("comment_text", ""),
            num_likes=data.get("num_likes", 0) or 0,
            num_replies=data.get("num_replies", 0) or 0,
            commenter_url=data.get("commenter_url", ""),
            user_name=data.get("user_name", ""),
            user_id=data.get("user_id", ""),
            post_id=data.get("post_id", ""),
            post_url=data.get("post_url", ""),
            attached_files=data.get("attached_files", []) or [],
            video_length=data.get("video_length", 0) or 0,
            replies=replies,
            raw=data,
        )


@dataclass
class FacebookReel:
    """Facebook reel data."""
    post_id: str
    post_url: str = ""
    content: str = ""
    hashtags: list[str] = field(default_factory=list)
    date_posted: Optional[datetime] = None
    num_comments: int = 0
    num_likes: int = 0
    video_view_count: int = 0
    audio: dict = field(default_factory=dict)
    page_name: str = ""
    page_category: str = ""
    page_followers: int = 0
    profile_handle: str = ""
    external_link: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "FacebookReel":
        """Create from BrightData API response."""
        return cls(
            post_id=data.get("post_id", ""),
            post_url=data.get("post_url", "") or data.get("url", ""),
            content=data.get("content", ""),
            hashtags=data.get("hashtags", []) or [],
            date_posted=FacebookPost._parse_date(data.get("date_posted")),
            num_comments=data.get("num_comments", 0) or 0,
            num_likes=data.get("num_likes", 0) or 0,
            video_view_count=data.get("video_view_count", 0) or 0,
            audio=data.get("audio", {}) or {},
            page_name=data.get("page_name", ""),
            page_category=data.get("page_category", ""),
            page_followers=data.get("page_followers", 0) or 0,
            profile_handle=data.get("profile_handle", ""),
            external_link=data.get("external_link", ""),
            raw=data,
        )


@dataclass
class FacebookProfile:
    """Facebook profile/page data."""
    profile_url: str
    name: str = ""
    username: str = ""
    category: str = ""
    followers: int = 0
    likes: int = 0
    about: str = ""
    website: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    is_verified: bool = False
    profile_image: str = ""
    cover_image: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "FacebookProfile":
        return cls(
            profile_url=data.get("url", "") or data.get("profile_url", ""),
            name=data.get("name", "") or data.get("page_name", ""),
            username=data.get("username", "") or data.get("profile_handle", ""),
            category=data.get("category", "") or data.get("page_category", ""),
            followers=data.get("followers", 0) or data.get("page_followers", 0) or 0,
            likes=data.get("likes", 0) or 0,
            about=data.get("about", "") or data.get("description", ""),
            website=data.get("website", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            address=data.get("address", ""),
            is_verified=data.get("is_verified", False),
            profile_image=data.get("profile_image", "") or data.get("profile_pic", ""),
            cover_image=data.get("cover_image", "") or data.get("cover_photo", ""),
            raw=data,
        )


@dataclass
class FacebookEvent:
    """Facebook event data."""
    event_id: str
    event_url: str
    name: str = ""
    description: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: str = ""
    venue: str = ""
    organizer: str = ""
    organizer_url: str = ""
    attendees: int = 0
    interested: int = 0
    is_online: bool = False
    cover_image: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "FacebookEvent":
        return cls(
            event_id=data.get("event_id", "") or data.get("id", ""),
            event_url=data.get("url", "") or data.get("event_url", ""),
            name=data.get("name", "") or data.get("title", ""),
            description=data.get("description", ""),
            start_time=FacebookPost._parse_date(data.get("start_time")),
            end_time=FacebookPost._parse_date(data.get("end_time")),
            location=data.get("location", ""),
            venue=data.get("venue", ""),
            organizer=data.get("organizer", "") or data.get("host_name", ""),
            organizer_url=data.get("organizer_url", "") or data.get("host_url", ""),
            attendees=data.get("attendees", 0) or data.get("going", 0) or 0,
            interested=data.get("interested", 0) or 0,
            is_online=data.get("is_online", False),
            cover_image=data.get("cover_image", "") or data.get("cover_photo", ""),
            raw=data,
        )


@dataclass
class FacebookGroupPost(FacebookPost):
    """Facebook group post with additional group metadata."""
    group_name: str = ""
    group_id: str = ""
    group_url: str = ""
    group_intro: str = ""
    group_category: str = ""
    user_url: str = ""
    user_username: str = ""
    user_is_verified: bool = False
    original_post_url: str = ""
    other_posts_url: list[str] = field(default_factory=list)
    post_external_link: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "FacebookGroupPost":
        """Create from BrightData API response."""
        base = FacebookPost.from_api(data)
        return cls(
            post_id=base.post_id,
            post_url=base.post_url,
            content=base.content,
            hashtags=base.hashtags,
            date_posted=base.date_posted,
            num_comments=base.num_comments,
            num_likes=base.num_likes,
            num_shares=base.num_shares,
            page_name=base.page_name,
            page_category=base.page_category,
            page_followers=base.page_followers,
            profile_handle=base.profile_handle,
            post_image=base.post_image,
            attachments=base.attachments,
            video_view_count=base.video_view_count,
            raw=data,
            group_name=data.get("group_name", ""),
            group_id=data.get("group_id", ""),
            group_url=data.get("group_url", ""),
            group_intro=data.get("group_intro", ""),
            group_category=data.get("group_category", ""),
            user_url=data.get("user_url", ""),
            user_username=data.get("user_username", ""),
            user_is_verified=data.get("user_is_verified", False),
            original_post_url=data.get("original_post_url", ""),
            other_posts_url=data.get("other_posts_url", []) or [],
            post_external_link=data.get("post_external_link", ""),
        )


# =============================================================================
# SDK CLIENT FACTORY
# =============================================================================
