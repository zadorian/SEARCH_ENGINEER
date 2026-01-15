#!/usr/bin/env python3
"""
SOCIALITE CLI - Social Media Intelligence

Command-line interface for SOCIALITE module operations.
Unified social media scraping via Apify actors.

Usage:
    # New unified commands (for soc:/socp:/socc: operators)
    python socialite_cli.py person "John Smith"                     # Full person social search
    python socialite_cli.py person "John Smith" --json              # JSON output
    python socialite_cli.py person "John Smith" --output-nodes      # Node graph output
    python socialite_cli.py person "John Smith" --writeup           # Include EDITH writeup
    python socialite_cli.py company "Acme Corp"                     # Company social search
    python socialite_cli.py company "Acme Corp" --writeup           # With EDITH writeup
    python socialite_cli.py auto "John Smith"                       # Auto-detect and route

    # Platform-specific commands
    python socialite_cli.py search twitter "John Smith"
    python socialite_cli.py search instagram "@username"
    python socialite_cli.py search linkedin "company name"
    python socialite_cli.py profile twitter "username"
    python socialite_cli.py profile instagram "username"
    python socialite_cli.py profile facebook "page_id"
    python socialite_cli.py posts twitter "username" --limit 50
    python socialite_cli.py posts instagram "username" --limit 20
    python socialite_cli.py followers instagram "username" --limit 100
    python socialite_cli.py list-actors
    python socialite_cli.py run-actor "actor_id" --input '{"key": "value"}'

Operators routed here:
    soc: <name>   →  socialite_cli auto <name>     (AI decides person vs company)
    socp: <name>  →  socialite_cli person <name>   (deterministic person search)
    socc: <name>  →  socialite_cli company <name>  (deterministic company search)
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
import time
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor

# Add module paths
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Person platforms to search
PERSON_PLATFORMS = ["linkedin", "twitter", "instagram", "github", "facebook", "tiktok", "youtube", "reddit"]

# Company platforms to search
COMPANY_PLATFORMS = ["linkedin", "twitter", "facebook", "youtube", "instagram"]


@dataclass
class SocialProfile:
    """Represents a social media profile."""
    platform: str
    username: Optional[str] = None
    url: Optional[str] = None
    followers: Optional[int] = None
    verified: bool = False
    active: bool = True
    bio: Optional[str] = None
    name: Optional[str] = None
    posts_count: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SocialiteNode:
    """Node for social media investigation."""
    node_id: str
    node_class: str  # "QUERY" or "SOCIAL_PROFILE"
    node_type: str   # "person_social" or "company_social"
    label: str
    props: Dict[str, Any] = field(default_factory=dict)
    profiles: List[SocialProfile] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_class": self.node_class,
            "node_type": self.node_type,
            "label": self.label,
            "props": self.props,
            "profiles": [asdict(p) for p in self.profiles],
            "metadata": self.metadata
        }


@dataclass
class SocialiteNodeSet:
    """Set of nodes from a socialite search."""
    query_node: SocialiteNode
    primary_node: SocialiteNode
    platform_nodes: List[SocialiteNode] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_ids": {
                "query": self.query_node.node_id,
                "primary": self.primary_node.node_id,
                "platforms": [n.node_id for n in self.platform_nodes]
            },
            "query": self.query_node.to_dict(),
            "primary": self.primary_node.to_dict(),
            "platform_nodes": [n.to_dict() for n in self.platform_nodes]
        }

# Actor registry
ACTORS = {
    # Instagram
    "instagram_profile": "apify/instagram-profile-scraper",
    "instagram_posts": "apify/instagram-post-scraper",
    "instagram_hashtag": "apify/instagram-hashtag-scraper",
    "instagram_comments": "apify/instagram-comment-scraper",
    "instagram_reels": "PvBJwWYJ0TrJMKxKH",
    "instagram_followers": "9dGsqv7OVS0yHB9xW",

    # Facebook
    "facebook_search": "Us34x9p7VgjCz99H6",
    "facebook_posts": "KoJrdxJCTtpon81KY",
    "facebook_pages": "apify/facebook-pages-scraper",
    "facebook_comments": "apify/facebook-comments-scraper",
    "facebook_groups": "harsheth/facebook-groups-scraper",

    # Twitter/X
    "twitter_search": "apify/twitter-scraper",
    "twitter_profile": "quacker/twitter-scraper",

    # LinkedIn
    "linkedin_profile": "anchor/linkedin-profile-scraper",
    "linkedin_posts": "anchor/linkedin-posts-scraper",
    "linkedin_company": "anchor/linkedin-company-scraper",
    "linkedin_jobs": "anchor/linkedin-jobs-scraper",

    # TikTok
    "tiktok_profile": "clockworks/tiktok-scraper",
    "tiktok_posts": "clockworks/free-tiktok-scraper",
    "tiktok_hashtag": "clockworks/tiktok-hashtag-scraper",

    # Threads
    "threads_profile": "kJdK90pa2hhYYrCK5",
    "threads_posts": "kJdK90pa2hhYYrCK5",

    # Reddit
    "reddit_user": "cgizCCmpI9tsJFexd",
    "reddit_posts": "trudax/reddit-scraper-lite",
    "reddit_subreddit": "okhowdy/reddit-subreddit-posts-scraper",

    # YouTube
    "youtube_channel": "streamers/youtube-scraper",
    "youtube_comments": "alexey/youtube-comment-scraper",
    "youtube_transcripts": "karamelo/youtube-transcripts",

    # Telegram
    "telegram_channel": "stormsource/telegram-channel-scraper",
    "telegram_posts": "apify/telegram-scraper",
}


async def call_apify_actor(actor_id: str, input_data: Dict[str, Any], timeout_secs: int = 300) -> Dict[str, Any]:
    """Call an Apify actor and return results."""
    import aiohttp

    if not APIFY_TOKEN:
        return {"error": "APIFY_TOKEN not set in environment"}

    async with aiohttp.ClientSession() as session:
        # Start actor run
        actor_encoded = quote(actor_id, safe="")
        url = f"https://api.apify.com/v2/acts/{actor_encoded}/runs"
        headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}

        async with session.post(url, json=input_data, headers=headers) as resp:
            if resp.status != 201:
                return {"error": f"Failed to start actor: {await resp.text()}"}
            run_info = await resp.json()

        run_id = run_info["data"]["id"]

        # Poll for completion
        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
        for _ in range(timeout_secs // 5):
            await asyncio.sleep(5)
            async with session.get(status_url, headers=headers) as resp:
                status = await resp.json()
                state = status["data"]["status"]
                if state in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                    break

        if state != "SUCCEEDED":
            return {"error": f"Actor run {state}", "run_id": run_id}

        # Fetch results
        dataset_id = status["data"]["defaultDatasetId"]
        results_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        async with session.get(results_url, headers=headers) as resp:
            results = await resp.json()
            return {"success": True, "items": results, "count": len(results)}


def cmd_search(args):
    """Search social platform."""
    platform = args.platform.lower()
    query = args.query

    actor_map = {
        "twitter": "twitter_search",
        "x": "twitter_search",
        "instagram": "instagram_hashtag",
        "facebook": "facebook_search",
        "linkedin": "linkedin_profile",
        "tiktok": "tiktok_hashtag",
        "reddit": "reddit_posts",
        "youtube": "youtube_channel",
    }

    actor_key = actor_map.get(platform)
    if not actor_key:
        print(f"Unknown platform: {platform}")
        print(f"Available: {', '.join(actor_map.keys())}")
        sys.exit(1)

    actor_id = ACTORS[actor_key]

    # Build input based on platform
    input_data = {}
    if platform in ("twitter", "x"):
        input_data = {"searchTerms": [query], "maxTweets": args.limit}
    elif platform == "instagram":
        input_data = {"hashtags": [query.lstrip("#")], "resultsLimit": args.limit}
    elif platform == "facebook":
        input_data = {"searchQuery": query, "maxResults": args.limit}
    elif platform == "linkedin":
        input_data = {"searchUrl": f"https://www.linkedin.com/search/results/all/?keywords={query}"}
    elif platform == "tiktok":
        input_data = {"hashtags": [query.lstrip("#")], "resultsPerPage": args.limit}
    elif platform == "reddit":
        input_data = {"searchQuery": query, "maxPosts": args.limit}
    elif platform == "youtube":
        input_data = {"searchTerms": [query], "maxResults": args.limit}

    async def run():
        result = await call_apify_actor(actor_id, input_data)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("error"):
                print(f"Error: {result['error']}")
            else:
                print(f"\n=== {platform.title()} Search: {query} ===")
                print(f"Found {result.get('count', 0)} results")
                for item in result.get("items", [])[:10]:
                    print(f"\n---")
                    # Pretty print key fields
                    for key in ["text", "content", "title", "url", "username", "name"]:
                        if key in item:
                            val = str(item[key])[:200]
                            print(f"  {key}: {val}")

    asyncio.run(run())


def cmd_profile(args):
    """Get profile from social platform."""
    platform = args.platform.lower()
    username = args.username.lstrip("@")

    actor_map = {
        "twitter": "twitter_profile",
        "x": "twitter_profile",
        "instagram": "instagram_profile",
        "facebook": "facebook_pages",
        "linkedin": "linkedin_profile",
        "tiktok": "tiktok_profile",
        "threads": "threads_profile",
        "reddit": "reddit_user",
        "youtube": "youtube_channel",
        "telegram": "telegram_channel",
    }

    actor_key = actor_map.get(platform)
    if not actor_key:
        print(f"Unknown platform: {platform}")
        sys.exit(1)

    actor_id = ACTORS[actor_key]

    # Build input
    input_data = {}
    if platform in ("twitter", "x"):
        input_data = {"twitterHandles": [username]}
    elif platform == "instagram":
        input_data = {"usernames": [username]}
    elif platform == "facebook":
        input_data = {"startUrls": [f"https://www.facebook.com/{username}"]}
    elif platform == "linkedin":
        input_data = {"profileUrls": [f"https://www.linkedin.com/in/{username}"]}
    elif platform == "tiktok":
        input_data = {"profiles": [username]}
    elif platform == "threads":
        input_data = {"usernames": [username]}
    elif platform == "reddit":
        input_data = {"username": username}
    elif platform == "youtube":
        input_data = {"channelUrls": [f"https://www.youtube.com/@{username}"]}
    elif platform == "telegram":
        input_data = {"channelUsername": username}

    async def run():
        result = await call_apify_actor(actor_id, input_data)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("error"):
                print(f"Error: {result['error']}")
            else:
                print(f"\n=== {platform.title()} Profile: @{username} ===")
                items = result.get("items", [])
                if items:
                    profile = items[0]
                    for key, val in profile.items():
                        if val and not isinstance(val, (list, dict)):
                            print(f"  {key}: {val}")

    asyncio.run(run())


def cmd_posts(args):
    """Get posts from profile."""
    platform = args.platform.lower()
    username = args.username.lstrip("@")

    actor_map = {
        "twitter": "twitter_profile",
        "instagram": "instagram_posts",
        "facebook": "facebook_posts",
        "linkedin": "linkedin_posts",
        "tiktok": "tiktok_posts",
        "threads": "threads_posts",
        "reddit": "reddit_user",
    }

    actor_key = actor_map.get(platform)
    if not actor_key:
        print(f"Unknown platform: {platform}")
        sys.exit(1)

    actor_id = ACTORS[actor_key]

    # Build input
    input_data = {"resultsLimit": args.limit}
    if platform in ("twitter", "x"):
        input_data["twitterHandles"] = [username]
        input_data["maxTweets"] = args.limit
    elif platform == "instagram":
        input_data["username"] = [username]
    elif platform == "facebook":
        input_data["startUrls"] = [f"https://www.facebook.com/{username}"]
    elif platform == "linkedin":
        input_data["profileUrl"] = f"https://www.linkedin.com/in/{username}"
    elif platform == "tiktok":
        input_data["profiles"] = [username]
    elif platform == "threads":
        input_data["usernames"] = [username]
    elif platform == "reddit":
        input_data["username"] = username

    async def run():
        result = await call_apify_actor(actor_id, input_data)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("error"):
                print(f"Error: {result['error']}")
            else:
                print(f"\n=== {platform.title()} Posts: @{username} ===")
                for i, item in enumerate(result.get("items", [])[:args.limit], 1):
                    print(f"\n--- Post {i} ---")
                    text = item.get("text") or item.get("content") or item.get("title", "")
                    print(f"  {text[:300]}")
                    if item.get("url"):
                        print(f"  URL: {item['url']}")

    asyncio.run(run())


def cmd_followers(args):
    """Get followers list."""
    platform = args.platform.lower()
    username = args.username.lstrip("@")

    if platform != "instagram":
        print("Followers currently only supported for Instagram")
        sys.exit(1)

    actor_id = ACTORS["instagram_followers"]
    input_data = {
        "username": username,
        "resultsLimit": args.limit
    }

    async def run():
        result = await call_apify_actor(actor_id, input_data)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("error"):
                print(f"Error: {result['error']}")
            else:
                print(f"\n=== {platform.title()} Followers: @{username} ===")
                print(f"Found {result.get('count', 0)} followers")
                for item in result.get("items", [])[:20]:
                    print(f"  @{item.get('username', 'unknown')}")

    asyncio.run(run())


def cmd_list_actors(args):
    """List available Apify actors."""
    if args.json:
        print(json.dumps(ACTORS, indent=2))
    else:
        print("\n=== Available SOCIALITE Actors ===\n")

        categories = {
            "Instagram": ["instagram_profile", "instagram_posts", "instagram_hashtag", "instagram_comments", "instagram_reels", "instagram_followers"],
            "Facebook": ["facebook_search", "facebook_posts", "facebook_pages", "facebook_comments", "facebook_groups"],
            "Twitter/X": ["twitter_search", "twitter_profile"],
            "LinkedIn": ["linkedin_profile", "linkedin_posts", "linkedin_company", "linkedin_jobs"],
            "TikTok": ["tiktok_profile", "tiktok_posts", "tiktok_hashtag"],
            "Threads": ["threads_profile", "threads_posts"],
            "Reddit": ["reddit_user", "reddit_posts", "reddit_subreddit"],
            "YouTube": ["youtube_channel", "youtube_comments", "youtube_transcripts"],
            "Telegram": ["telegram_channel", "telegram_posts"],
        }

        for category, actor_keys in categories.items():
            print(f"{category}:")
            for key in actor_keys:
                if key in ACTORS:
                    print(f"  {key}: {ACTORS[key]}")
            print()


def cmd_run_actor(args):
    """Run arbitrary Apify actor."""
    actor_id = args.actor_id

    # Check if it's a key from our registry
    if actor_id in ACTORS:
        actor_id = ACTORS[actor_id]

    try:
        input_data = json.loads(args.input) if args.input else {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}")
        sys.exit(1)

    async def run():
        result = await call_apify_actor(actor_id, input_data, timeout_secs=args.timeout)
        print(json.dumps(result, indent=2, default=str))

    asyncio.run(run())


# =============================================================================
# NEW: Person, Company, Auto commands (for soc:/socp:/socc: operators)
# =============================================================================

async def search_platform_for_entity(platform: str, name: str, entity_type: str = "person", limit: int = 10) -> Dict[str, Any]:
    """Search a single platform for an entity (person or company)."""
    actor_map = {
        "linkedin": "linkedin_profile" if entity_type == "person" else "linkedin_company",
        "twitter": "twitter_search",
        "instagram": "instagram_profile",
        "facebook": "facebook_search",
        "tiktok": "tiktok_profile",
        "youtube": "youtube_channel",
        "reddit": "reddit_posts",
        "github": "twitter_search",  # Placeholder - would need GitHub API
    }

    actor_key = actor_map.get(platform)
    if not actor_key or actor_key not in ACTORS:
        return {"platform": platform, "error": f"No actor for {platform}", "profiles": []}

    actor_id = ACTORS[actor_key]

    # Build platform-specific input
    input_data = {}
    if platform == "linkedin":
        if entity_type == "person":
            input_data = {"searchUrl": f"https://www.linkedin.com/search/results/people/?keywords={name}"}
        else:
            input_data = {"searchUrl": f"https://www.linkedin.com/search/results/companies/?keywords={name}"}
    elif platform in ("twitter", "x"):
        input_data = {"searchTerms": [name], "maxTweets": limit}
    elif platform == "instagram":
        input_data = {"search": name, "resultsLimit": limit}
    elif platform == "facebook":
        input_data = {"searchQuery": name, "maxResults": limit}
    elif platform == "tiktok":
        input_data = {"searchQueries": [name], "resultsPerPage": limit}
    elif platform == "youtube":
        input_data = {"searchTerms": [name], "maxResults": limit}
    elif platform == "reddit":
        input_data = {"searchQuery": name, "maxPosts": limit}

    try:
        result = await call_apify_actor(actor_id, input_data, timeout_secs=120)
        profiles = []
        if result.get("items"):
            for item in result["items"][:limit]:
                profile = SocialProfile(
                    platform=platform,
                    username=item.get("username") or item.get("handle") or item.get("name"),
                    url=item.get("url") or item.get("profileUrl"),
                    followers=item.get("followers") or item.get("followersCount"),
                    verified=item.get("verified", False),
                    bio=item.get("bio") or item.get("description"),
                    name=item.get("fullName") or item.get("name"),
                    raw_data=item
                )
                profiles.append(profile)

        return {
            "platform": platform,
            "profiles": [asdict(p) for p in profiles],
            "count": len(profiles),
            "status": "success"
        }
    except Exception as e:
        return {"platform": platform, "error": str(e), "profiles": [], "status": "error"}


async def search_all_platforms(name: str, entity_type: str = "person", platforms: List[str] = None) -> Dict[str, Any]:
    """Search all relevant platforms for an entity."""
    if platforms is None:
        platforms = PERSON_PLATFORMS if entity_type == "person" else COMPANY_PLATFORMS

    start_time = time.time()
    tasks = [search_platform_for_entity(p, name, entity_type) for p in platforms]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_profiles = []
    platform_results = {}
    errors = []

    for i, result in enumerate(results):
        platform = platforms[i]
        if isinstance(result, Exception):
            platform_results[platform] = {"error": str(result), "profiles": []}
            errors.append({"platform": platform, "error": str(result)})
        elif result.get("error"):
            platform_results[platform] = result
            errors.append({"platform": platform, "error": result.get("error")})
        else:
            platform_results[platform] = result
            all_profiles.extend(result.get("profiles", []))

    elapsed = time.time() - start_time

    return {
        "name": name,
        "entity_type": entity_type,
        "platforms_searched": platforms,
        "total_profiles": len(all_profiles),
        "profiles": all_profiles,
        "platform_results": platform_results,
        "errors": errors,
        "search_time_seconds": round(elapsed, 2)
    }


def create_socialite_node_set(name: str, entity_type: str, results: Dict[str, Any]) -> SocialiteNodeSet:
    """Create node set from search results."""
    query_node = SocialiteNode(
        node_id=f"socialite-query-{uuid.uuid4().hex[:8]}",
        node_class="QUERY",
        node_type=f"{entity_type}_social",
        label=f"{'socp' if entity_type == 'person' else 'socc'}: {name}",
        props={"raw_input": name, "entity_type": entity_type}
    )

    profiles = [SocialProfile(**p) for p in results.get("profiles", [])]

    primary_node = SocialiteNode(
        node_id=f"socialite-primary-{uuid.uuid4().hex[:8]}",
        node_class="SOCIAL_PROFILE",
        node_type=f"{entity_type}_social",
        label=name,
        profiles=profiles,
        metadata={
            "total_profiles": len(profiles),
            "platforms_found": list(set(p.platform for p in profiles)),
            "search_time": results.get("search_time_seconds", 0)
        }
    )

    # Create platform-specific nodes
    platform_nodes = []
    for platform, data in results.get("platform_results", {}).items():
        if data.get("profiles"):
            platform_profiles = [SocialProfile(**p) for p in data.get("profiles", [])]
            node = SocialiteNode(
                node_id=f"socialite-{platform}-{uuid.uuid4().hex[:8]}",
                node_class="SOCIAL_PROFILE",
                node_type=f"{entity_type}_social",
                label=f"{name} ({platform})",
                profiles=platform_profiles,
                metadata={"platform": platform, "count": len(platform_profiles)}
            )
            platform_nodes.append(node)

    return SocialiteNodeSet(
        query_node=query_node,
        primary_node=primary_node,
        platform_nodes=platform_nodes
    )


def generate_edith_writeup(name: str, entity_type: str, results: Dict[str, Any]) -> str:
    """Generate EDITH-style social media presence writeup."""
    profiles = results.get("profiles", [])
    subject = f"**{name}**"

    if entity_type == "person":
        pronoun = "the subject"
    else:
        pronoun = "the company"

    lines = ["## Social Media and Online Presence", ""]

    # Table of identified accounts
    if profiles:
        lines.append("### Identified Social Media Accounts")
        lines.append("")
        lines.append("| Platform | Handle/URL | Followers | Verified | Activity |")
        lines.append("|----------|------------|-----------|----------|----------|")

        for p in profiles[:10]:  # Limit to top 10
            platform = p.get("platform", "Unknown").title()
            handle = p.get("username") or p.get("url", "N/A")
            if len(handle) > 40:
                handle = handle[:37] + "..."
            followers = p.get("followers", "N/A")
            if isinstance(followers, int):
                followers = f"{followers:,}"
            verified = "Yes" if p.get("verified") else "No"
            active = "Active" if p.get("active", True) else "Inactive"
            lines.append(f"| {platform} | {handle} | {followers} | {verified} | {active} |")

        lines.append("")

    # Platform-specific sections
    platform_results = results.get("platform_results", {})

    # LinkedIn section
    linkedin_data = platform_results.get("linkedin", {})
    linkedin_profiles = linkedin_data.get("profiles", [])
    if linkedin_profiles:
        lines.append("### LinkedIn Profile")
        lines.append("")
        lp = linkedin_profiles[0]
        position = lp.get("bio") or lp.get("headline") or "professional"
        lines.append(f"{subject} maintains a LinkedIn profile presenting {pronoun} as {position}.")
        if lp.get("followers"):
            lines.append(f"The profile has {lp.get('followers'):,} connections.")
        lines.append("")

    # Twitter section
    twitter_data = platform_results.get("twitter", {})
    twitter_profiles = twitter_data.get("profiles", [])
    if twitter_profiles:
        lines.append("### Twitter/X Activity")
        lines.append("")
        tp = twitter_profiles[0]
        handle = tp.get("username", "unknown")
        followers = tp.get("followers", 0)
        if followers:
            lines.append(f"{subject}'s Twitter account (@{handle}) has {followers:,} followers.")
        else:
            lines.append(f"{subject}'s Twitter account (@{handle}) was identified.")
        lines.append("")

    # Instagram section
    instagram_data = platform_results.get("instagram", {})
    instagram_profiles = instagram_data.get("profiles", [])
    if instagram_profiles:
        lines.append("### Instagram Presence")
        lines.append("")
        ip = instagram_profiles[0]
        handle = ip.get("username", "unknown")
        followers = ip.get("followers", 0)
        if followers:
            lines.append(f"{subject}'s Instagram account (@{handle}) has {followers:,} followers.")
        else:
            lines.append(f"{subject}'s Instagram account (@{handle}) was identified.")
        lines.append("")

    # No social media found
    if not profiles:
        lines.append(f"No significant social media presence was identified for {subject}.")
        lines.append("")

    # Summary
    lines.append("### Summary")
    lines.append("")
    platforms_found = list(set(p.get("platform") for p in profiles))
    if platforms_found:
        lines.append(f"{subject} maintains a social media presence across {len(platforms_found)} platform(s): {', '.join(platforms_found)}.")
    else:
        lines.append(f"No verified social media presence was identified for {subject} during this search.")

    return "\n".join(lines)


async def detect_entity_type(name: str) -> str:
    """Use AI to detect if name is a person or company."""
    if not ANTHROPIC_API_KEY:
        # Heuristic fallback
        company_indicators = ["inc", "corp", "llc", "ltd", "company", "group", "holdings", "partners", "ventures", "capital", "bank", "trust", "fund"]
        name_lower = name.lower()
        for indicator in company_indicators:
            if indicator in name_lower:
                return "company"
        return "person"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            temperature=0,
            messages=[{
                "role": "user",
                "content": f'Is "{name}" a person name or a company/organization name? Reply with exactly one word: "person" or "company"'
            }]
        )

        content = response.content[0].text.strip().lower()
        if "company" in content or "organization" in content:
            return "company"
        return "person"
    except Exception:
        # Fallback to heuristic
        company_indicators = ["inc", "corp", "llc", "ltd", "company", "group", "holdings"]
        name_lower = name.lower()
        for indicator in company_indicators:
            if indicator in name_lower:
                return "company"
        return "person"


def cmd_person(args):
    """Search for a person across all social platforms."""
    name = args.name

    async def run():
        results = await search_all_platforms(name, entity_type="person")

        if args.output_nodes:
            node_set = create_socialite_node_set(name, "person", results)
            output = node_set.to_dict()
            output["raw_results"] = results
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, "person", results)
        else:
            output = results
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, "person", results)

        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"SOCIALITE PERSON SEARCH: {name}")
            print(f"{'='*60}")
            print(f"\nPlatforms searched: {', '.join(results['platforms_searched'])}")
            print(f"Total profiles found: {results['total_profiles']}")
            print(f"Search time: {results['search_time_seconds']}s")

            if results.get("profiles"):
                print(f"\n[PROFILES FOUND]")
                for p in results["profiles"][:10]:
                    platform = p.get("platform", "Unknown")
                    handle = p.get("username") or p.get("url", "N/A")
                    followers = p.get("followers", "N/A")
                    print(f"  • {platform}: {handle} ({followers} followers)")

            if results.get("errors"):
                print(f"\n[ERRORS]")
                for err in results["errors"]:
                    print(f"  • {err['platform']}: {err['error']}")

            if args.writeup:
                print(f"\n{'='*60}")
                print("EDITH WRITEUP")
                print(f"{'='*60}")
                print(output.get("writeup", "No writeup generated"))

    asyncio.run(run())


def cmd_company(args):
    """Search for a company across social platforms."""
    name = args.name

    async def run():
        results = await search_all_platforms(name, entity_type="company")

        if args.output_nodes:
            node_set = create_socialite_node_set(name, "company", results)
            output = node_set.to_dict()
            output["raw_results"] = results
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, "company", results)
        else:
            output = results
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, "company", results)

        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"SOCIALITE COMPANY SEARCH: {name}")
            print(f"{'='*60}")
            print(f"\nPlatforms searched: {', '.join(results['platforms_searched'])}")
            print(f"Total profiles found: {results['total_profiles']}")
            print(f"Search time: {results['search_time_seconds']}s")

            if results.get("profiles"):
                print(f"\n[PROFILES FOUND]")
                for p in results["profiles"][:10]:
                    platform = p.get("platform", "Unknown")
                    handle = p.get("username") or p.get("url", "N/A")
                    followers = p.get("followers", "N/A")
                    print(f"  • {platform}: {handle} ({followers} followers)")

            if args.writeup:
                print(f"\n{'='*60}")
                print("EDITH WRITEUP")
                print(f"{'='*60}")
                print(output.get("writeup", "No writeup generated"))

    asyncio.run(run())


def cmd_auto(args):
    """Auto-detect entity type and search social platforms."""
    name = args.name

    async def run():
        # Detect entity type
        entity_type = await detect_entity_type(name)
        print(f"Detected entity type: {entity_type}")

        results = await search_all_platforms(name, entity_type=entity_type)

        if args.output_nodes:
            node_set = create_socialite_node_set(name, entity_type, results)
            output = node_set.to_dict()
            output["raw_results"] = results
            output["detected_type"] = entity_type
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, entity_type, results)
        else:
            output = results
            output["detected_type"] = entity_type
            if args.writeup:
                output["writeup"] = generate_edith_writeup(name, entity_type, results)

        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"SOCIALITE AUTO SEARCH: {name}")
            print(f"Detected: {entity_type.upper()}")
            print(f"{'='*60}")
            print(f"\nPlatforms searched: {', '.join(results['platforms_searched'])}")
            print(f"Total profiles found: {results['total_profiles']}")
            print(f"Search time: {results['search_time_seconds']}s")

            if results.get("profiles"):
                print(f"\n[PROFILES FOUND]")
                for p in results["profiles"][:10]:
                    platform = p.get("platform", "Unknown")
                    handle = p.get("username") or p.get("url", "N/A")
                    followers = p.get("followers", "N/A")
                    print(f"  • {platform}: {handle} ({followers} followers)")

            if args.writeup:
                print(f"\n{'='*60}")
                print("EDITH WRITEUP")
                print(f"{'='*60}")
                print(output.get("writeup", "No writeup generated"))

    asyncio.run(run())


def main():
    parser = argparse.ArgumentParser(
        description="SOCIALITE CLI - Social Media Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Unified person/company search (for soc:/socp:/socc: operators)
  python socialite_cli.py person "John Smith"              # Full person social search
  python socialite_cli.py person "John Smith" --json       # JSON output
  python socialite_cli.py person "John Smith" --writeup    # Include EDITH writeup
  python socialite_cli.py company "Acme Corp"              # Company social search
  python socialite_cli.py auto "John Smith"                # Auto-detect and route

  # Platform-specific search
  python socialite_cli.py search twitter "John Smith"
  python socialite_cli.py profile instagram "username"
  python socialite_cli.py posts twitter "elonmusk" --limit 50
  python socialite_cli.py list-actors
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # person - unified person social search (for socp: operator)
    p_person = subparsers.add_parser("person", help="Search all social platforms for a person")
    p_person.add_argument("name", help="Person name to search")
    p_person.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_person.add_argument("--output-nodes", "-n", action="store_true", help="Output node graph structure")
    p_person.add_argument("--writeup", "-w", action="store_true", help="Include EDITH social media writeup")
    p_person.set_defaults(func=cmd_person)

    # company - unified company social search (for socc: operator)
    p_company = subparsers.add_parser("company", help="Search all social platforms for a company")
    p_company.add_argument("name", help="Company name to search")
    p_company.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_company.add_argument("--output-nodes", "-n", action="store_true", help="Output node graph structure")
    p_company.add_argument("--writeup", "-w", action="store_true", help="Include EDITH social media writeup")
    p_company.set_defaults(func=cmd_company)

    # auto - AI-powered entity detection and routing (for soc: operator)
    p_auto = subparsers.add_parser("auto", help="Auto-detect entity type and search social platforms")
    p_auto.add_argument("name", help="Name to search (person or company)")
    p_auto.add_argument("--json", "-j", action="store_true", help="JSON output")
    p_auto.add_argument("--output-nodes", "-n", action="store_true", help="Output node graph structure")
    p_auto.add_argument("--writeup", "-w", action="store_true", help="Include EDITH social media writeup")
    p_auto.set_defaults(func=cmd_auto)

    # search - platform-specific search
    p_search = subparsers.add_parser("search", help="Search social platform")
    p_search.add_argument("platform", help="Platform (twitter, instagram, facebook, linkedin, tiktok, reddit, youtube)")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", "-l", type=int, default=20, help="Max results")
    p_search.add_argument("--json", action="store_true", help="JSON output")
    p_search.set_defaults(func=cmd_search)

    # profile
    p_profile = subparsers.add_parser("profile", help="Get profile")
    p_profile.add_argument("platform", help="Platform")
    p_profile.add_argument("username", help="Username")
    p_profile.add_argument("--json", action="store_true", help="JSON output")
    p_profile.set_defaults(func=cmd_profile)

    # posts
    p_posts = subparsers.add_parser("posts", help="Get posts from profile")
    p_posts.add_argument("platform", help="Platform")
    p_posts.add_argument("username", help="Username")
    p_posts.add_argument("--limit", "-l", type=int, default=20, help="Max posts")
    p_posts.add_argument("--json", action="store_true", help="JSON output")
    p_posts.set_defaults(func=cmd_posts)

    # followers
    p_followers = subparsers.add_parser("followers", help="Get followers (Instagram only)")
    p_followers.add_argument("platform", help="Platform")
    p_followers.add_argument("username", help="Username")
    p_followers.add_argument("--limit", "-l", type=int, default=100, help="Max followers")
    p_followers.add_argument("--json", action="store_true", help="JSON output")
    p_followers.set_defaults(func=cmd_followers)

    # list-actors
    p_list = subparsers.add_parser("list-actors", help="List available actors")
    p_list.add_argument("--json", action="store_true", help="JSON output")
    p_list.set_defaults(func=cmd_list_actors)

    # run-actor
    p_run = subparsers.add_parser("run-actor", help="Run arbitrary Apify actor")
    p_run.add_argument("actor_id", help="Actor ID or key from registry")
    p_run.add_argument("--input", "-i", help="JSON input for actor")
    p_run.add_argument("--timeout", "-t", type=int, default=300, help="Timeout in seconds")
    p_run.set_defaults(func=cmd_run_actor)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
