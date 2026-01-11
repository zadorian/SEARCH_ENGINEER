"""Facebook targeted search helpers (URL generators, Graph API helpers)."""

from __future__ import annotations

import logging
import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, quote_plus, urlencode, urlparse, parse_qs

import requests


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

