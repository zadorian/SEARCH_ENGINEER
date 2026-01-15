"""
Influence Analyzer - Analyze influence metrics for social media users.

Async functions for analyzing reach, engagement, and influence.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def analyze_influence(
    username: str,
    platform: str = "twitter"
) -> Dict[str, Any]:
    """
    Analyze influence metrics for a user.

    Args:
        username: Username to analyze
        platform: Platform to analyze on

    Returns:
        Dict with influence metrics and analysis
    """
    logger.info(f"Analyzing influence for @{username} on {platform}")

    result = {
        "username": username,
        "platform": platform,
        "metrics": {
            "followers": None,
            "following": None,
            "posts": None,
            "engagement_rate": None,
            "avg_likes": None,
            "avg_comments": None,
            "avg_shares": None
        },
        "influence_score": None,
        "tier": "unknown",
        "profile_url": None,
        "analysis_note": "Real-time metrics require API access"
    }

    # Generate profile URL
    from modules.socialite.platforms import twitter, instagram, facebook

    try:
        if platform == "twitter":
            result["profile_url"] = twitter.twitter_profile(username)
        elif platform == "instagram":
            result["profile_url"] = instagram.instagram_profile(username)
        elif platform == "facebook":
            result["profile_url"] = facebook.facebook_profile(username)
        else:
            result["profile_url"] = f"https://{platform}.com/{username}"

    except Exception as e:
        logger.warning(f"Failed to generate profile URL: {e}")

    return result


async def calculate_influence_score(
    followers: int,
    engagement_rate: float,
    verified: bool = False,
    account_age_days: int = 0
) -> Dict[str, Any]:
    """
    Calculate an influence score based on metrics.

    Args:
        followers: Follower count
        engagement_rate: Engagement rate as percentage
        verified: Whether account is verified
        account_age_days: Account age in days

    Returns:
        Dict with influence score and tier classification
    """
    # Base score from followers (log scale)
    import math
    follower_score = math.log10(max(followers, 1)) * 10

    # Engagement bonus
    engagement_score = min(engagement_rate * 5, 25)

    # Verified bonus
    verified_bonus = 10 if verified else 0

    # Account age bonus (max 10 points for 2+ years)
    age_bonus = min(account_age_days / 73, 10)  # 730 days = 2 years

    total_score = follower_score + engagement_score + verified_bonus + age_bonus

    # Determine tier
    if total_score >= 80:
        tier = "mega_influencer"
    elif total_score >= 60:
        tier = "macro_influencer"
    elif total_score >= 40:
        tier = "micro_influencer"
    elif total_score >= 20:
        tier = "nano_influencer"
    else:
        tier = "standard_user"

    return {
        "total_score": round(total_score, 2),
        "tier": tier,
        "breakdown": {
            "follower_score": round(follower_score, 2),
            "engagement_score": round(engagement_score, 2),
            "verified_bonus": verified_bonus,
            "age_bonus": round(age_bonus, 2)
        }
    }


__all__ = ["analyze_influence", "calculate_influence_score"]
