#!/usr/bin/env python3
"""
AHREFS - Domain Analytics via Apify.

Actor: radeance/ahrefs-scraper
Cost: Pay-per-result pricing

Provides domain analytics data from Ahrefs:
- Web authority (DR/UR)
- Traffic estimates
- Backlinks analysis
- Keywords ranking
- Competitor analysis
- Top pages
- SERP data

Usage:
    from socialite.platforms.ahrefs import (
        analyze_domain,
        get_backlinks,
        get_traffic_data,
        search_keyword,
        AhrefsAnalysis
    )

    # Full domain analysis
    analysis = analyze_domain("example.com")

    # Get backlinks only
    backlinks = get_backlinks("example.com")

    # Traffic data
    traffic = get_traffic_data("example.com")

    # Keyword search
    results = search_keyword("ai automation", domain="make.com")
"""

import os
import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
AHREFS_ACTOR_ID = "radeance/ahrefs-scraper"

MODES = ["subdomains", "exact", "prefix", "domain"]
COUNTRIES = ["us", "uk", "de", "fr", "es", "it", "nl", "au", "ca", "jp", "br", "in", "ru", "mx"]

# Categories for top websites
TOP_WEBSITE_CATEGORIES = [
    "all", "arts_entertainment", "business", "computers_electronics",
    "finance", "food_drink", "games", "health", "hobbies_leisure",
    "home_garden", "internet_telecom", "jobs_education", "law_government",
    "news", "online_communities", "people_society", "pets_animals",
    "real_estate", "reference", "science", "shopping", "sports", "travel"
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AhrefsBacklink:
    """Ahrefs backlink data."""
    source_url: str = ""
    source_domain: str = ""
    target_url: str = ""
    anchor_text: str = ""
    domain_rating: float = 0.0
    url_rating: float = 0.0
    traffic: int = 0
    is_dofollow: bool = True
    first_seen: Optional[str] = None
    last_checked: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "AhrefsBacklink":
        return cls(
            source_url=data.get("sourceUrl", "") or data.get("referring_page", ""),
            source_domain=data.get("sourceDomain", "") or data.get("referring_domain", ""),
            target_url=data.get("targetUrl", "") or data.get("target_page", ""),
            anchor_text=data.get("anchorText", "") or data.get("anchor", ""),
            domain_rating=float(data.get("domainRating", 0) or data.get("dr", 0) or 0),
            url_rating=float(data.get("urlRating", 0) or data.get("ur", 0) or 0),
            traffic=int(data.get("traffic", 0) or 0),
            is_dofollow=data.get("isDofollow", True) or data.get("dofollow", True),
            first_seen=data.get("firstSeen") or data.get("first_seen"),
            last_checked=data.get("lastChecked") or data.get("last_checked"),
            raw=data,
        )


@dataclass
class AhrefsKeyword:
    """Ahrefs keyword data."""
    keyword: str = ""
    search_volume: int = 0
    keyword_difficulty: int = 0
    cpc: float = 0.0
    position: int = 0
    traffic: int = 0
    traffic_potential: int = 0
    url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "AhrefsKeyword":
        return cls(
            keyword=data.get("keyword", ""),
            search_volume=int(data.get("volume", 0) or data.get("searchVolume", 0) or 0),
            keyword_difficulty=int(data.get("kd", 0) or data.get("difficulty", 0) or 0),
            cpc=float(data.get("cpc", 0) or 0),
            position=int(data.get("position", 0) or 0),
            traffic=int(data.get("traffic", 0) or 0),
            traffic_potential=int(data.get("trafficPotential", 0) or data.get("potential", 0) or 0),
            url=data.get("url", ""),
            raw=data,
        )


@dataclass
class AhrefsAnalysis:
    """Full Ahrefs domain analysis."""
    domain: str = ""
    domain_rating: float = 0.0
    url_rating: float = 0.0
    ahrefs_rank: int = 0
    referring_domains: int = 0
    backlinks: int = 0
    organic_traffic: int = 0
    organic_keywords: int = 0
    paid_traffic: int = 0
    paid_keywords: int = 0
    traffic_value: float = 0.0
    top_keywords: List[AhrefsKeyword] = field(default_factory=list)
    top_backlinks: List[AhrefsBacklink] = field(default_factory=list)
    competitors: List[Dict[str, Any]] = field(default_factory=list)
    broken_links: List[Dict[str, Any]] = field(default_factory=list)
    top_pages: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "AhrefsAnalysis":
        """Create from Apify actor output."""
        # Parse keywords
        keywords = []
        for kw_data in data.get("keywords", []) or data.get("topKeywords", []) or []:
            keywords.append(AhrefsKeyword.from_apify(kw_data))

        # Parse backlinks
        backlinks = []
        for bl_data in data.get("backlinks", []) or data.get("topBacklinks", []) or []:
            backlinks.append(AhrefsBacklink.from_apify(bl_data))

        return cls(
            domain=data.get("domain", "") or data.get("url", ""),
            domain_rating=float(data.get("domainRating", 0) or data.get("dr", 0) or 0),
            url_rating=float(data.get("urlRating", 0) or data.get("ur", 0) or 0),
            ahrefs_rank=int(data.get("ahrefsRank", 0) or data.get("rank", 0) or 0),
            referring_domains=int(data.get("referringDomains", 0) or data.get("refDomains", 0) or 0),
            backlinks=int(data.get("backlinks", 0) if isinstance(data.get("backlinks"), int) else len(backlinks)),
            organic_traffic=int(data.get("organicTraffic", 0) or data.get("traffic", 0) or 0),
            organic_keywords=int(data.get("organicKeywords", 0) or data.get("keywords", 0) if isinstance(data.get("keywords"), int) else 0),
            paid_traffic=int(data.get("paidTraffic", 0) or 0),
            paid_keywords=int(data.get("paidKeywords", 0) or 0),
            traffic_value=float(data.get("trafficValue", 0) or 0),
            top_keywords=keywords,
            top_backlinks=backlinks,
            competitors=data.get("competitors", []) or [],
            broken_links=data.get("brokenLinks", []) or data.get("broken_links", []) or [],
            top_pages=data.get("topPages", []) or data.get("pages", []) or [],
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "domain": self.domain,
            "domain_rating": self.domain_rating,
            "url_rating": self.url_rating,
            "ahrefs_rank": self.ahrefs_rank,
            "referring_domains": self.referring_domains,
            "backlinks_count": self.backlinks,
            "organic_traffic": self.organic_traffic,
            "organic_keywords": self.organic_keywords,
            "traffic_value": self.traffic_value,
            "top_keywords_count": len(self.top_keywords),
            "competitors_count": len(self.competitors),
        }


# =============================================================================
# SCRAPING FUNCTIONS
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


def analyze_domain(
    url: str,
    *,
    keyword: Optional[str] = None,
    country: str = "us",
    mode: Literal["subdomains", "exact", "prefix", "domain"] = "subdomains",
    include_web_authority: bool = True,
    include_traffic: bool = True,
    include_keywords: bool = False,
    include_keywords_difficulty: bool = False,
    include_keywords_ranking: bool = False,
    include_serp: bool = False,
    include_backlinks: bool = True,
    include_broken_links: bool = False,
    include_competitors: bool = False,
) -> Optional[AhrefsAnalysis]:
    """
    Full domain analysis via Ahrefs.

    Args:
        url: Domain to analyze (e.g., "example.com")
        keyword: Optional keyword filter
        country: Country code for data (us, uk, de, etc.)
        mode: Analysis mode (subdomains, exact, prefix, domain)
        include_web_authority: Include DR/UR scores
        include_traffic: Include traffic estimates
        include_keywords: Include keyword data
        include_keywords_difficulty: Include KD scores
        include_keywords_ranking: Include ranking data
        include_serp: Include SERP features
        include_backlinks: Include backlink data
        include_broken_links: Include broken links
        include_competitors: Include competitor analysis

    Returns:
        AhrefsAnalysis object or None

    Example:
        analysis = analyze_domain("make.com")
        analysis = analyze_domain("example.com", include_competitors=True)
    """
    client = _get_client()

    run_input = {
        "url": url,
        "country": country,
        "mode": mode,
        "include_web_authority": include_web_authority,
        "include_traffic": include_traffic,
        "include_keywords": include_keywords,
        "include_keywords_difficulty": include_keywords_difficulty,
        "include_keywords_ranking": include_keywords_ranking,
        "include_serp": include_serp,
        "include_backlinks": include_backlinks,
        "include_broken_links": include_broken_links,
        "include_competitors": include_competitors,
        "include_top_websites": False,
    }

    if keyword:
        run_input["keyword"] = keyword

    try:
        logger.info(f"Analyzing domain via Ahrefs: {url}")
        run = client.actor(AHREFS_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if results:
            return AhrefsAnalysis.from_apify(results[0])
        return None
    except Exception as e:
        logger.error(f"Ahrefs analysis failed: {e}")
        return None


def get_backlinks(
    url: str,
    *,
    country: str = "us",
    mode: str = "subdomains",
) -> List[AhrefsBacklink]:
    """
    Get backlinks for a domain.

    Args:
        url: Domain to analyze
        country: Country code
        mode: Analysis mode

    Returns:
        List of AhrefsBacklink objects
    """
    analysis = analyze_domain(
        url,
        country=country,
        mode=mode,
        include_web_authority=False,
        include_traffic=False,
        include_backlinks=True,
    )
    return analysis.top_backlinks if analysis else []


def get_traffic_data(
    url: str,
    *,
    country: str = "us",
    mode: str = "subdomains",
) -> Dict[str, Any]:
    """
    Get traffic data for a domain.

    Args:
        url: Domain to analyze
        country: Country code
        mode: Analysis mode

    Returns:
        Dict with traffic metrics
    """
    analysis = analyze_domain(
        url,
        country=country,
        mode=mode,
        include_web_authority=True,
        include_traffic=True,
        include_backlinks=False,
    )
    if analysis:
        return {
            "domain": analysis.domain,
            "domain_rating": analysis.domain_rating,
            "organic_traffic": analysis.organic_traffic,
            "organic_keywords": analysis.organic_keywords,
            "traffic_value": analysis.traffic_value,
            "referring_domains": analysis.referring_domains,
        }
    return {}


def search_keyword(
    keyword: str,
    *,
    domain: Optional[str] = None,
    country: str = "us",
    include_difficulty: bool = True,
    include_serp: bool = False,
) -> List[AhrefsKeyword]:
    """
    Search for keyword data.

    Args:
        keyword: Keyword to search
        domain: Optional domain to filter results
        country: Country code
        include_difficulty: Include keyword difficulty
        include_serp: Include SERP data

    Returns:
        List of AhrefsKeyword objects
    """
    client = _get_client()

    run_input = {
        "keyword": keyword,
        "country": country,
        "include_keywords": True,
        "include_keywords_difficulty": include_difficulty,
        "include_serp": include_serp,
        "include_web_authority": False,
        "include_traffic": False,
        "include_backlinks": False,
    }

    if domain:
        run_input["url"] = domain

    try:
        logger.info(f"Searching Ahrefs keyword: {keyword}")
        run = client.actor(AHREFS_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        keywords = []
        for result in results:
            for kw_data in result.get("keywords", []) or []:
                keywords.append(AhrefsKeyword.from_apify(kw_data))
        return keywords
    except Exception as e:
        logger.error(f"Ahrefs keyword search failed: {e}")
        return []


def get_competitors(
    url: str,
    *,
    country: str = "us",
) -> List[Dict[str, Any]]:
    """
    Get competitor domains.

    Args:
        url: Domain to analyze
        country: Country code

    Returns:
        List of competitor dicts with domain, traffic, keywords
    """
    analysis = analyze_domain(
        url,
        country=country,
        include_web_authority=False,
        include_traffic=False,
        include_backlinks=False,
        include_competitors=True,
    )
    return analysis.competitors if analysis else []


def get_top_websites(
    category: str = "all",
    country: str = "worldwide",
) -> List[Dict[str, Any]]:
    """
    Get top websites by category.

    Args:
        category: Category to filter (see TOP_WEBSITE_CATEGORIES)
        country: Country code or "worldwide"

    Returns:
        List of top website dicts
    """
    client = _get_client()

    run_input = {
        "include_top_websites": True,
        "category_top_websites": category,
        "country_top_websites": country,
        "include_web_authority": False,
        "include_traffic": False,
        "include_backlinks": False,
    }

    try:
        logger.info(f"Getting top websites: {category} / {country}")
        run = client.actor(AHREFS_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if results:
            return results[0].get("topWebsites", []) or results[0].get("top_websites", []) or []
        return []
    except Exception as e:
        logger.error(f"Ahrefs top websites failed: {e}")
        return []


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "AhrefsAnalysis",
    "AhrefsBacklink",
    "AhrefsKeyword",
    # Functions
    "analyze_domain",
    "get_backlinks",
    "get_traffic_data",
    "search_keyword",
    "get_competitors",
    "get_top_websites",
    # Config
    "MODES",
    "COUNTRIES",
    "TOP_WEBSITE_CATEGORIES",
    "AHREFS_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python ahrefs.py <domain_or_keyword>")
        print("\nExamples:")
        print("  python ahrefs.py example.com")
        print("  python ahrefs.py keyword:ai automation")
        print("  python ahrefs.py backlinks:example.com")
        sys.exit(1)

    query = sys.argv[1]

    if query.startswith("keyword:"):
        keyword = query[8:]
        print(f"🔍 Searching Ahrefs keyword: {keyword}")
        keywords = search_keyword(keyword)
        print(f"\n📊 Found {len(keywords)} keywords")
        for kw in keywords[:10]:
            print(f"  {kw.keyword}: vol={kw.search_volume}, kd={kw.keyword_difficulty}, traffic={kw.traffic}")
    elif query.startswith("backlinks:"):
        domain = query[10:]
        print(f"🔗 Getting backlinks for: {domain}")
        backlinks = get_backlinks(domain)
        print(f"\n🔗 Found {len(backlinks)} backlinks")
        for bl in backlinks[:10]:
            print(f"  {bl.source_domain} -> DR:{bl.domain_rating} traffic:{bl.traffic}")
    else:
        print(f"📊 Analyzing domain via Ahrefs: {query}")
        analysis = analyze_domain(query, include_competitors=True)
        if analysis:
            print(f"\n🏷️  {analysis.domain}")
            print(f"   Domain Rating: {analysis.domain_rating}")
            print(f"   Referring Domains: {analysis.referring_domains:,}")
            print(f"   Organic Traffic: {analysis.organic_traffic:,}")
            print(f"   Organic Keywords: {analysis.organic_keywords:,}")
            print(f"   Traffic Value: ${analysis.traffic_value:,.2f}")
            if analysis.competitors:
                print(f"\n   🏆 Top Competitors ({len(analysis.competitors)}):")
                for comp in analysis.competitors[:5]:
                    print(f"      - {comp.get('domain', comp.get('url', 'Unknown'))}")
        else:
            print("   No results found")
