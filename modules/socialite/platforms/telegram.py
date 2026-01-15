#!/usr/bin/env python3
"""
TELEGRAM - Telegram Channel/Group Message Scraper via Apify.

Extract messages from public Telegram channels and groups with:
- Full message content and metadata
- Engagement metrics (views, replies, forwards, reactions)
- Forward chain tracking
- Media downloads (images, videos, documents)
- Service events (joins, pins, title changes)

Usage:
    from socialite.platforms.telegram import (
        scrape_channel,
        scrape_messages,
        get_recent_messages,
        TelegramMessage,
        TelegramChannel,
    )

    # Scrape channel messages
    result = scrape_channel("binance_announcements", days=7)
    for msg in result.messages:
        print(f"{msg.sender}: {msg.text[:50]}...")

    # Quick recent messages
    messages = get_recent_messages("@duaborev", days=1)
"""

import os
import logging
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
TELEGRAM_CHANNEL_ACTOR = "TpLqaxMYSJzwVnXoj"  # cheapget/telegram-channel-message
TELEGRAM_PROFILE_ACTOR = "lAybf7rRybdzabbBk"  # agentx/telegram-info-scraper (40+ fields)
TELEGRAM_PROFILE_LITE_ACTOR = "cheapget/telegram-profile"  # Basic profile metadata
TELEGRAM_GROUP_MEMBERS_ACTOR = "cheapget/telegram-group-member"  # Group member extraction

# Legacy alias
TELEGRAM_ACTOR_ID = TELEGRAM_CHANNEL_ACTOR

# Media download options
MEDIA_TEXT = "text"      # No media, text only
MEDIA_IMAGE = "image"    # Photos only
MEDIA_ALL = "all"        # All media types


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TelegramForwardInfo:
    """Forward chain information."""
    date: str = ""
    from_id: int = 0
    from_name: str = ""
    message_id: int = 0

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> Optional["TelegramForwardInfo"]:
        if not data:
            return None
        return cls(
            date=data.get("date", ""),
            from_id=data.get("from_id", 0),
            from_name=data.get("from_name", ""),
            message_id=data.get("message_id", 0),
        )


@dataclass
class TelegramMessage:
    """Individual Telegram message."""
    data_captured_at: str = ""
    id: int = 0
    type: str = ""  # Regular, Service, Unknown
    date: str = ""
    text: str = ""
    sender: str = ""
    silent: bool = False
    pinned: bool = False
    view_count: int = 0
    reply_count: int = 0
    forward_count: int = 0
    reply_to: Optional[int] = None
    album_id: Optional[int] = None
    topic_name: str = ""
    service_type: str = ""
    service_info: str = ""
    forward_info: Optional[TelegramForwardInfo] = None
    reactions: Dict[str, int] = field(default_factory=dict)
    media_url: str = ""
    source_id: int = 0
    source_name: str = ""
    source_type: str = ""  # Channel, Group
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "TelegramMessage":
        return cls(
            data_captured_at=data.get("processed_at", datetime.utcnow().isoformat()),
            id=data.get("id", 0),
            type=data.get("type", ""),
            date=data.get("date", ""),
            text=data.get("text", ""),
            sender=data.get("sender", ""),
            silent=data.get("silent", False),
            pinned=data.get("pinned", False),
            view_count=data.get("view_count", 0),
            reply_count=data.get("reply_count", 0),
            forward_count=data.get("forward_count", 0),
            reply_to=data.get("reply_to"),
            album_id=data.get("album_id"),
            topic_name=data.get("topic_name", ""),
            service_type=data.get("service_type", ""),
            service_info=data.get("service_info", ""),
            forward_info=TelegramForwardInfo.from_apify(data.get("forward_info")),
            reactions=data.get("reactions", {}),
            media_url=data.get("media_url", ""),
            source_id=data.get("source_id", 0),
            source_name=data.get("source_name", ""),
            source_type=data.get("source_type", ""),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_captured_at": self.data_captured_at,
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "text": self.text,
            "sender": self.sender,
            "view_count": self.view_count,
            "reply_count": self.reply_count,
            "forward_count": self.forward_count,
            "reactions": self.reactions,
            "media_url": self.media_url,
            "source_name": self.source_name,
        }


@dataclass
class TelegramChannel:
    """Telegram channel/group scrape result."""
    data_captured_at: str = ""
    target: str = ""
    source_id: int = 0
    source_name: str = ""
    source_type: str = ""
    messages: List[TelegramMessage] = field(default_factory=list)
    total_messages: int = 0
    date_range: str = ""
    media_mode: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_captured_at": self.data_captured_at,
            "target": self.target,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "total_messages": self.total_messages,
            "date_range": self.date_range,
        }


@dataclass
class TelegramGroupMember:
    """Individual member from a Telegram group."""
    # Core identity
    data_captured_at: str = ""
    id: int = 0
    type: str = ""  # user, bot
    first_name: str = ""
    last_name: str = ""
    usernames: List[str] = field(default_factory=list)
    phone: str = ""
    lang_code: str = ""

    # Status flags
    is_admin: bool = False
    is_deleted: bool = False
    is_verified: bool = False
    is_premium: bool = False
    is_scam: bool = False
    is_fake: bool = False
    is_restricted: bool = False

    # Activity/settings
    last_seen: str = ""
    stories_hidden: bool = False
    premium_contact: bool = False

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def username(self) -> str:
        """Primary username."""
        return self.usernames[0] if self.usernames else ""

    @property
    def full_name(self) -> str:
        """Full display name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "TelegramGroupMember":
        usernames = data.get("usernames", [])
        if not usernames and data.get("username"):
            usernames = [data["username"]]

        return cls(
            data_captured_at=data.get("processed_at", datetime.utcnow().isoformat()),
            id=data.get("id", 0),
            type=data.get("type", "user"),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            usernames=usernames,
            phone=data.get("phone", ""),
            lang_code=data.get("lang_code", ""),
            is_admin=data.get("is_admin", False),
            is_deleted=data.get("is_deleted", False),
            is_verified=data.get("is_verified", False),
            is_premium=data.get("is_premium", False),
            is_scam=data.get("is_scam", False),
            is_fake=data.get("is_fake", False),
            is_restricted=data.get("is_restricted", False),
            last_seen=data.get("last_seen", ""),
            stories_hidden=data.get("stories_hidden", False),
            premium_contact=data.get("premium_contact", False),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_captured_at": self.data_captured_at,
            "id": self.id,
            "type": self.type,
            "username": self.username,
            "full_name": self.full_name,
            "phone": self.phone,
            "is_admin": self.is_admin,
            "is_premium": self.is_premium,
            "is_verified": self.is_verified,
            "is_scam": self.is_scam,
            "last_seen": self.last_seen,
        }


@dataclass
class TelegramProfile:
    """Telegram channel/user/bot/group profile with 40+ fields."""
    # Core identity
    data_captured_at: str = ""
    id: int = 0
    type: str = ""  # user, bot, channel, supergroup, group
    usernames: List[str] = field(default_factory=list)
    title: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    lang_code: str = ""
    description: str = ""
    profile_photo: bool = False

    # Status flags
    is_premium: bool = False
    is_verified: bool = False
    is_scam: bool = False
    is_fake: bool = False
    is_deleted: bool = False
    is_support: bool = False
    is_restricted: bool = False
    is_blocked: bool = False

    # Communication settings (users)
    phone_calls: bool = False
    video_calls: bool = False
    voice_messages: bool = False
    can_pin: bool = False
    premium_contact: bool = False
    private_calls: bool = False
    private_reads: bool = False

    # User activity
    last_seen: str = ""
    common_chats_count: int = 0
    has_scheduled: bool = False
    can_manage_emoji: bool = False

    # Group/channel specific
    member_count: int = 0
    online_count: int = 0
    admins_count: int = 0
    banned_count: int = 0
    join_to_send: bool = False
    join_request: bool = False
    is_forum: bool = False
    no_forwards: bool = False
    gigagroup: bool = False
    slowmode: bool = False
    created_date: str = ""
    linked_chat_id: int = 0
    view_members: bool = False
    call_active: bool = False
    view_stats: bool = False
    has_location: bool = False
    location: Dict[str, Any] = field(default_factory=dict)

    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def username(self) -> str:
        """Primary username."""
        return self.usernames[0] if self.usernames else ""

    @property
    def full_name(self) -> str:
        """Full name for users."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.title

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "TelegramProfile":
        usernames = data.get("usernames", [])
        if not usernames and data.get("username"):
            usernames = [data["username"]]

        return cls(
            data_captured_at=data.get("processed_at", datetime.utcnow().isoformat()),
            id=data.get("id", 0),
            type=data.get("type", ""),
            usernames=usernames,
            title=data.get("title", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone=data.get("phone", ""),
            lang_code=data.get("lang_code", ""),
            description=data.get("description", ""),
            profile_photo=data.get("profile_photo", False),
            # Status flags
            is_premium=data.get("is_premium", False),
            is_verified=data.get("is_verified", False),
            is_scam=data.get("is_scam", False),
            is_fake=data.get("is_fake", False),
            is_deleted=data.get("is_deleted", False),
            is_support=data.get("is_support", False),
            is_restricted=data.get("is_restricted", False),
            is_blocked=data.get("is_blocked", False),
            # Communication
            phone_calls=data.get("phone_calls", False),
            video_calls=data.get("video_calls", False),
            voice_messages=data.get("voice_messages", False),
            can_pin=data.get("can_pin", False),
            premium_contact=data.get("premium_contact", False),
            private_calls=data.get("private_calls", False),
            private_reads=data.get("private_reads", False),
            # Activity
            last_seen=data.get("last_seen", ""),
            common_chats_count=data.get("common_chats_count", 0),
            has_scheduled=data.get("has_scheduled", False),
            can_manage_emoji=data.get("can_manage_emoji", False),
            # Group/channel
            member_count=data.get("member_count", 0),
            online_count=data.get("online_count", 0),
            admins_count=data.get("admins_count", 0),
            banned_count=data.get("banned_count", 0),
            join_to_send=data.get("join_to_send", False),
            join_request=data.get("join_request", False),
            is_forum=data.get("is_forum", False),
            no_forwards=data.get("no_forwards", False),
            gigagroup=data.get("gigagroup", False),
            slowmode=data.get("slowmode", False),
            created_date=data.get("created_date", ""),
            linked_chat_id=data.get("linked_chat_id", 0),
            view_members=data.get("view_members", False),
            call_active=data.get("call_active", False),
            view_stats=data.get("view_stats", False),
            has_location=data.get("has_location", False),
            location=data.get("location", {}),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_captured_at": self.data_captured_at,
            "id": self.id,
            "type": self.type,
            "username": self.username,
            "title": self.title or self.full_name,
            "description": self.description,
            "phone": self.phone,
            "member_count": self.member_count,
            "online_count": self.online_count,
            "is_premium": self.is_premium,
            "is_verified": self.is_verified,
            "is_scam": self.is_scam,
            "last_seen": self.last_seen,
            "created_date": self.created_date,
        }


# =============================================================================
# CLIENT
# =============================================================================

def _get_client():
    """Get Apify client."""
    if not APIFY_TOKEN:
        raise ValueError("APIFY_API_TOKEN or APIFY_TOKEN environment variable required")
    try:
        from apify_client import ApifyClient
        return ApifyClient(APIFY_TOKEN)
    except ImportError:
        raise ImportError("apify-client not installed. Run: pip install apify-client")


# =============================================================================
# SCRAPING FUNCTIONS
# =============================================================================

def scrape_channel(
    target: str,
    *,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    download_medias: str = MEDIA_TEXT,
) -> Optional[TelegramChannel]:
    """
    Scrape messages from a Telegram channel or group.

    Args:
        target: Channel identifier - URL (https://t.me/channel), @channel, or channel_name
        days: Number of days back to scrape (e.g., 7 for last week)
        start_date: Absolute date (YYYY-MM-DD) or relative ("7 days", "2 weeks")
        download_medias: "text", "image", or "all"

    Returns:
        TelegramChannel with messages

    Example:
        result = scrape_channel("binance_announcements", days=7)
        for msg in result.messages:
            print(f"[{msg.view_count} views] {msg.text[:100]}")
    """
    client = _get_client()

    # Build date parameter
    if days:
        date_param = f"{days} days"
    elif start_date:
        date_param = start_date
    else:
        date_param = "7 days"  # Default to 1 week

    # Normalize target
    if not target.startswith(("https://", "http://", "@")):
        target = f"https://t.me/{target}"

    run_input = {
        "telegram_target": target,
        "download_medias": download_medias,
        "start_date": date_param,
    }

    try:
        logger.info(f"Scraping Telegram: {target} ({date_param})")
        run = client.actor(TELEGRAM_CHANNEL_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if not results:
            return None

        messages = [TelegramMessage.from_apify(item) for item in results]

        # Get channel info from first message
        first = messages[0] if messages else None

        return TelegramChannel(
            data_captured_at=datetime.utcnow().isoformat(),
            target=target,
            source_id=first.source_id if first else 0,
            source_name=first.source_name if first else "",
            source_type=first.source_type if first else "",
            messages=messages,
            total_messages=len(messages),
            date_range=date_param,
            media_mode=download_medias,
        )
    except Exception as e:
        logger.error(f"Telegram scrape failed: {e}")
        return None


def scrape_messages(
    target: str,
    start_date: str,
    download_medias: str = MEDIA_TEXT,
) -> List[TelegramMessage]:
    """
    Scrape messages with explicit date control.

    Args:
        target: Channel/group identifier
        start_date: Start date (YYYY-MM-DD or relative like "30 days")
        download_medias: Media download mode

    Returns:
        List of TelegramMessage objects
    """
    result = scrape_channel(
        target,
        start_date=start_date,
        download_medias=download_medias,
    )
    return result.messages if result else []


def get_recent_messages(
    target: str,
    days: int = 1,
    include_media: bool = False,
) -> List[TelegramMessage]:
    """
    Get recent messages from a channel.

    Args:
        target: Channel/group identifier
        days: Number of days back
        include_media: Whether to download images

    Returns:
        List of TelegramMessage objects

    Example:
        msgs = get_recent_messages("@durov", days=3)
        for m in msgs:
            print(f"{m.date}: {m.text[:80]}")
    """
    result = scrape_channel(
        target,
        days=days,
        download_medias=MEDIA_IMAGE if include_media else MEDIA_TEXT,
    )
    return result.messages if result else []


def search_channel_text(
    target: str,
    query: str,
    days: int = 30,
) -> List[TelegramMessage]:
    """
    Search channel messages for text content.

    Args:
        target: Channel/group identifier
        query: Text to search for (case-insensitive)
        days: How far back to search

    Returns:
        Messages containing the query text
    """
    messages = get_recent_messages(target, days=days)
    query_lower = query.lower()
    return [m for m in messages if query_lower in m.text.lower()]


def get_forwarded_messages(
    target: str,
    days: int = 7,
) -> List[TelegramMessage]:
    """
    Get only forwarded messages from a channel.

    Args:
        target: Channel/group identifier
        days: Number of days back

    Returns:
        Messages that were forwarded from other sources
    """
    messages = get_recent_messages(target, days=days)
    return [m for m in messages if m.forward_info is not None]


def get_engagement_stats(
    target: str,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Get engagement statistics for a channel.

    Args:
        target: Channel/group identifier
        days: Analysis period

    Returns:
        Dict with engagement metrics
    """
    messages = get_recent_messages(target, days=days)

    if not messages:
        return {"error": "no_messages"}

    total_views = sum(m.view_count for m in messages)
    total_replies = sum(m.reply_count for m in messages)
    total_forwards = sum(m.forward_count for m in messages)

    # Aggregate reactions
    all_reactions: Dict[str, int] = {}
    for m in messages:
        for emoji, count in m.reactions.items():
            all_reactions[emoji] = all_reactions.get(emoji, 0) + count

    return {
        "data_captured_at": datetime.utcnow().isoformat(),
        "target": target,
        "period_days": days,
        "total_messages": len(messages),
        "total_views": total_views,
        "total_replies": total_replies,
        "total_forwards": total_forwards,
        "avg_views": total_views // len(messages) if messages else 0,
        "top_reactions": dict(sorted(all_reactions.items(), key=lambda x: -x[1])[:5]),
        "pinned_count": sum(1 for m in messages if m.pinned),
    }


# =============================================================================
# PROFILE SCRAPING FUNCTIONS
# =============================================================================

def scrape_profile(target: str) -> Optional[TelegramProfile]:
    """
    Get profile metadata for a single Telegram channel/user.

    Args:
        target: Channel/user identifier (@username, t.me/username, or username)

    Returns:
        TelegramProfile or None

    Example:
        profile = scrape_profile("@durov")
        print(f"{profile.title}: {profile.member_count:,} members")
    """
    profiles = scrape_profiles([target])
    return profiles[0] if profiles else None


def scrape_profiles(targets: List[str]) -> List[TelegramProfile]:
    """
    Get comprehensive profile metadata for multiple Telegram entities.

    Uses agentx/telegram-info-scraper with 40+ output fields.

    Args:
        targets: List of channel/user identifiers (5-10000 items)

    Returns:
        List of TelegramProfile objects with 40+ fields

    Example:
        profiles = scrape_profiles(["@binance", "@coinbase", "@BotFather"])
        for p in profiles:
            print(f"{p.username}: {p.type} - {p.member_count:,} members")
            if p.is_premium:
                print("  Premium user!")
            if p.phone:
                print(f"  Phone: {p.phone}")
    """
    client = _get_client()

    # Normalize targets - actor accepts various formats
    normalized = []
    for t in targets:
        if t.startswith("https://"):
            normalized.append(t)
        elif t.startswith("@"):
            normalized.append(t[1:])  # Remove @
        elif t.startswith("t.me/"):
            normalized.append(t.replace("t.me/", ""))
        else:
            normalized.append(t)

    # Note: agentx actor uses "user_name" field
    run_input = {
        "user_name": normalized,
    }

    try:
        logger.info(f"Scraping {len(targets)} Telegram profiles (40+ fields)")
        run = client.actor(TELEGRAM_PROFILE_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return [TelegramProfile.from_apify(item) for item in results]
    except Exception as e:
        logger.error(f"Telegram profile scrape failed: {e}")
        return []


def scrape_profiles_mtproto(targets: List[str]) -> List[TelegramProfile]:
    """
    Get profile metadata using MTProto protocol (cheapget/telegram-profile).

    Alternative to scrape_profiles() with different pricing and capabilities:
    - MTProto protocol for higher reliability
    - Batch up to 10,000 targets per request
    - $0.0045 per profile (minimum 5 targets charged)
    - 95%+ success rate

    Args:
        targets: List of Telegram identifiers (1-10,000 items)
                 Formats: @username, t.me/user, https://t.me/user, plain username

    Returns:
        List of TelegramProfile objects with 40+ fields

    Example:
        profiles = scrape_profiles_mtproto(["@binance", "telegram", "t.me/BotFather"])
        for p in profiles:
            print(f"{p.username}: {p.type} - {p.member_count:,} members")
    """
    client = _get_client()

    # Normalize targets - actor accepts multiple formats
    normalized = []
    for t in targets:
        # Actor accepts @username, t.me/user, https://t.me/user, or plain username
        normalized.append(t)

    run_input = {
        "telegram_targets": normalized,
    }

    try:
        logger.info(f"Scraping {len(targets)} Telegram profiles via MTProto")
        run = client.actor(TELEGRAM_PROFILE_LITE_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        profiles = []
        for item in results:
            if item.get("status") == "success":
                profiles.append(TelegramProfile.from_apify(item))
            else:
                logger.warning(f"Profile failed: {item.get('source_url')} - {item.get('status')}")

        return profiles
    except Exception as e:
        logger.error(f"MTProto profile scrape failed: {e}")
        return []


def get_channel_info(target: str) -> Optional[Dict[str, Any]]:
    """
    Get basic channel information.

    Args:
        target: Channel identifier

    Returns:
        Dict with channel info or None
    """
    profile = scrape_profile(target)
    if profile:
        return profile.to_dict()
    return None


def compare_channels(targets: List[str]) -> List[Dict[str, Any]]:
    """
    Compare multiple channels by member count.

    Args:
        targets: List of channel identifiers

    Returns:
        List sorted by member count (descending)
    """
    profiles = scrape_profiles(targets)
    result = [p.to_dict() for p in profiles]
    return sorted(result, key=lambda x: x.get("member_count", 0), reverse=True)


# =============================================================================
# GROUP MEMBER SCRAPING
# =============================================================================

def scrape_group_members(
    group_name: str,
    deep_search: bool = False,
) -> List[TelegramGroupMember]:
    """
    Extract members from a Telegram group.

    Uses cheapget/telegram-group-member actor to get member list with
    profile metadata including admin status, premium status, and more.

    Args:
        group_name: Group identifier (username, @username, or t.me/group URL)
        deep_search: If True, retrieves more detailed info per member (slower)

    Returns:
        List of TelegramGroupMember objects

    Example:
        members = scrape_group_members("my_group_name")
        admins = [m for m in members if m.is_admin]
        premium = [m for m in members if m.is_premium]
        print(f"Found {len(members)} members, {len(admins)} admins, {len(premium)} premium")

        for member in members:
            status = "👑" if member.is_admin else "👤"
            premium_badge = "⭐" if member.is_premium else ""
            print(f"  {status}{premium_badge} {member.full_name} (@{member.username})")
    """
    client = _get_client()

    # Normalize group name - actor expects plain username
    if group_name.startswith("https://t.me/"):
        group_name = group_name.replace("https://t.me/", "")
    elif group_name.startswith("t.me/"):
        group_name = group_name.replace("t.me/", "")
    elif group_name.startswith("@"):
        group_name = group_name[1:]

    run_input = {
        "group_name": group_name,
        "deep_search": deep_search,
    }

    try:
        logger.info(f"Scraping group members: {group_name} (deep_search={deep_search})")
        run = client.actor(TELEGRAM_GROUP_MEMBERS_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        members = [TelegramGroupMember.from_apify(item) for item in results]
        logger.info(f"Found {len(members)} members in {group_name}")
        return members
    except Exception as e:
        logger.error(f"Group member scrape failed: {e}")
        return []


def get_group_admins(group_name: str) -> List[TelegramGroupMember]:
    """
    Get only admin members from a group.

    Args:
        group_name: Group identifier

    Returns:
        List of admin TelegramGroupMember objects
    """
    members = scrape_group_members(group_name)
    return [m for m in members if m.is_admin]


def get_group_stats(group_name: str) -> Dict[str, Any]:
    """
    Get statistics about group membership.

    Args:
        group_name: Group identifier

    Returns:
        Dict with membership statistics
    """
    members = scrape_group_members(group_name)

    if not members:
        return {"error": "no_members_found"}

    admins = [m for m in members if m.is_admin]
    premium = [m for m in members if m.is_premium]
    verified = [m for m in members if m.is_verified]
    deleted = [m for m in members if m.is_deleted]
    scam = [m for m in members if m.is_scam]
    bots = [m for m in members if m.type == "bot"]

    return {
        "data_captured_at": datetime.utcnow().isoformat(),
        "group_name": group_name,
        "total_members": len(members),
        "admin_count": len(admins),
        "premium_count": len(premium),
        "verified_count": len(verified),
        "deleted_count": len(deleted),
        "scam_count": len(scam),
        "bot_count": len(bots),
        "premium_ratio": round(len(premium) / len(members) * 100, 1) if members else 0,
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "TelegramMessage",
    "TelegramChannel",
    "TelegramForwardInfo",
    "TelegramProfile",
    "TelegramGroupMember",
    # Constants
    "MEDIA_TEXT",
    "MEDIA_IMAGE",
    "MEDIA_ALL",
    "TELEGRAM_CHANNEL_ACTOR",
    "TELEGRAM_PROFILE_ACTOR",
    "TELEGRAM_PROFILE_LITE_ACTOR",
    "TELEGRAM_GROUP_MEMBERS_ACTOR",
    "TELEGRAM_ACTOR_ID",  # Legacy
    # Message functions
    "scrape_channel",
    "scrape_messages",
    "get_recent_messages",
    "search_channel_text",
    "get_forwarded_messages",
    "get_engagement_stats",
    # Profile functions
    "scrape_profile",
    "scrape_profiles",
    "scrape_profiles_mtproto",
    "get_channel_info",
    "compare_channels",
    # Group member functions
    "scrape_group_members",
    "get_group_admins",
    "get_group_stats",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python telegram.py <channel> [days]")
        print("       python telegram.py stats <channel> [days]")
        print("       python telegram.py members <group> [--deep]")
        print("       python telegram.py profile <username>")
        print("\nExamples:")
        print("  python telegram.py binance_announcements")
        print("  python telegram.py @durov 7")
        print("  python telegram.py stats binance_announcements 30")
        print("  python telegram.py members my_group")
        print("  python telegram.py members my_group --deep")
        print("  python telegram.py profile @durov")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats" and len(sys.argv) > 2:
        channel = sys.argv[2]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        print(f"📊 Engagement stats for {channel} ({days} days)")
        stats = get_engagement_stats(channel, days=days)
        if "error" not in stats:
            print(f"   Messages: {stats['total_messages']}")
            print(f"   Total views: {stats['total_views']:,}")
            print(f"   Avg views: {stats['avg_views']:,}")
            print(f"   Forwards: {stats['total_forwards']:,}")
            print(f"   Top reactions: {stats['top_reactions']}")
        else:
            print("   ❌ No messages found")

    elif cmd == "members" and len(sys.argv) > 2:
        group = sys.argv[2]
        deep = "--deep" in sys.argv
        print(f"👥 Scraping members from {group} (deep={deep})")
        members = scrape_group_members(group, deep_search=deep)
        if members:
            admins = [m for m in members if m.is_admin]
            premium = [m for m in members if m.is_premium]
            print(f"\n   Total: {len(members)} members")
            print(f"   Admins: {len(admins)}")
            print(f"   Premium: {len(premium)}")
            print("\n   Members:")
            for m in members[:20]:
                status = "👑" if m.is_admin else "👤"
                prem = "⭐" if m.is_premium else ""
                scam = "⚠️" if m.is_scam else ""
                name = m.full_name or f"id:{m.id}"
                uname = f"@{m.username}" if m.username else ""
                print(f"   {status}{prem}{scam} {name} {uname}")
            if len(members) > 20:
                print(f"   ... and {len(members) - 20} more")
        else:
            print("   ❌ No members found")

    elif cmd == "profile" and len(sys.argv) > 2:
        target = sys.argv[2]
        print(f"👤 Fetching profile: {target}")
        profile = scrape_profile(target)
        if profile:
            print(f"\n   Type: {profile.type}")
            print(f"   Name: {profile.full_name or profile.title}")
            print(f"   Username: @{profile.username}" if profile.username else "")
            if profile.phone:
                print(f"   Phone: {profile.phone}")
            if profile.member_count:
                print(f"   Members: {profile.member_count:,}")
            if profile.description:
                print(f"   Bio: {profile.description[:100]}...")
            flags = []
            if profile.is_premium:
                flags.append("Premium")
            if profile.is_verified:
                flags.append("Verified")
            if profile.is_scam:
                flags.append("SCAM")
            if flags:
                print(f"   Flags: {', '.join(flags)}")
        else:
            print("   ❌ Profile not found")

    else:
        channel = sys.argv[1]
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(f"📱 Scraping {channel} ({days} days)")
        result = scrape_channel(channel, days=days)
        if result:
            print(f"\n📢 {result.source_name} ({result.source_type})")
            print(f"   Messages: {result.total_messages}")
            print("\n   Recent messages:")
            for msg in result.messages[:10]:
                views = f"[{msg.view_count:,} views]" if msg.view_count else ""
                text = msg.text[:60].replace("\n", " ") if msg.text else "[no text]"
                print(f"   • {views} {text}...")
        else:
            print("   ❌ Scrape failed")
