#!/usr/bin/env python3
"""
SEMRUSH - Semrush SEO Analytics Scraper via Apify.

Provides comprehensive SEO intelligence from Semrush:
- Domain authority scores (authority_score, moz_domain_authority)
- Traffic analytics (visits, bounce_rate, pages_per_visit)
- Backlink profiles with historical data
- Keyword rankings and volume data
- SERP analysis
- SEO audits
- AI visibility scores
- Competitor analysis
- Top trending websites

Usage:
    from socialite.platforms.semrush import (
        analyze_domain,
        get_authority,
        get_traffic,
        get_backlinks,
        search_keyword,
        audit_seo,
        SemrushDomainAnalysis,
    )

    # Full domain analysis
    analysis = analyze_domain("example.com", country="us")

    # Quick authority check
    authority = get_authority("example.com")

    # Traffic data
    traffic = get_traffic("example.com")

    # Keyword research
    keyword = search_keyword("digital marketing", country="us")
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")

# Semrush actor IDs
SEMRUSH_DOMAIN_ACTOR = "radeance/semrush-scraper"  # Domain analysis (urls, keyword)
SEMRUSH_SEARCH_ACTOR = "TMBawM4LZpKN15DZX"  # Keyword/search research (query, resultsCount, searchType)

# Legacy env var support
SEMRUSH_ACTOR_ID = os.getenv("SEMRUSH_ACTOR_ID", SEMRUSH_DOMAIN_ACTOR)

SUPPORTED_COUNTRIES = [
    "us", "uk", "de", "fr", "es", "it", "nl", "au", "ca", "jp", "br", "ru",
    "in", "mx", "ar", "pl", "se", "no", "dk", "fi", "be", "ch", "at", "za"
]

# Top website industries
TOP_WEBSITE_INDUSTRIES = [
    "all", "accounting-and-auditing", "advertising-and-marketing", "banking",
    "education", "engineering", "finance", "government", "healthcare",
    "hospitality", "insurance", "legal", "manufacturing", "media",
    "real-estate", "retail", "technology", "telecommunications", "travel"
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SemrushAuthorityData:
    """Domain authority metrics from Semrush."""
    data_captured_at: str = ""
    last_updated: str = ""
    domain: str = ""
    authority_score: int = 0
    moz_domain_authority: int = 0
    moz_spam_score: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushAuthorityData":
        return cls(
            data_captured_at=data.get("data_captured_at", datetime.utcnow().isoformat()),
            last_updated=data.get("last_updated", ""),
            domain=data.get("domain", ""),
            authority_score=int(data.get("authority_score", 0) or 0),
            moz_domain_authority=int(data.get("moz_domain_authority", 0) or 0),
            moz_spam_score=data.get("moz_spam_score", ""),
            raw=data,
        )


@dataclass
class SemrushTrafficData:
    """Traffic analytics from Semrush."""
    data_captured_at: str = ""
    last_updated: str = ""
    domain: str = ""
    visits: int = 0
    bounce_rate: float = 0.0
    pages_per_visit: float = 0.0
    time_on_site: float = 0.0
    global_rank: Optional[int] = None
    country_rank: Optional[int] = None
    traffic_organic: int = 0
    traffic_paid: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushTrafficData":
        global_rank = data.get("global_rank", {})
        country_rank = data.get("country_rank", {})
        return cls(
            data_captured_at=data.get("data_captured_at", datetime.utcnow().isoformat()),
            last_updated=data.get("last_updated", ""),
            domain=data.get("domain", ""),
            visits=int(data.get("visits", 0) or 0),
            bounce_rate=float(data.get("bounce_rate", 0) or 0),
            pages_per_visit=float(data.get("pages_per_visit", 0) or 0),
            time_on_site=float(data.get("time_on_site", 0) or 0),
            global_rank=global_rank.get("rank") if isinstance(global_rank, dict) else global_rank,
            country_rank=country_rank.get("rank") if isinstance(country_rank, dict) else country_rank,
            traffic_organic=int(data.get("traffic_organic", 0) or 0),
            traffic_paid=int(data.get("traffic_paid", 0) or 0),
            raw=data,
        )


@dataclass
class SemrushBacklink:
    """Individual backlink from Semrush."""
    link: str = ""
    anchor: str = ""
    newlink: bool = False
    lostlink: bool = False
    nofollow: bool = False
    link_title: str = ""
    page_score: int = 0
    target_link: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushBacklink":
        return cls(
            link=data.get("link", ""),
            anchor=data.get("anchor", ""),
            newlink=data.get("newlink", False),
            lostlink=data.get("lostlink", False),
            nofollow=data.get("nofollow", False),
            link_title=data.get("link_title", ""),
            page_score=int(data.get("page_score", 0) or 0),
            target_link=data.get("target_link", ""),
            raw=data,
        )


@dataclass
class SemrushBacklinksData:
    """Backlinks profile from Semrush."""
    data_captured_at: str = ""
    last_updated: str = ""
    domain: str = ""
    authority_score: int = 0
    backlinks_total: int = 0
    backlink_domains_total: int = 0
    backlinks: List[SemrushBacklink] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushBacklinksData":
        backlinks_data = data.get("backlinks", [])
        backlinks = [SemrushBacklink.from_apify(b) for b in backlinks_data]
        return cls(
            data_captured_at=data.get("data_captured_at", datetime.utcnow().isoformat()),
            last_updated=data.get("last_updated", ""),
            domain=data.get("domain", ""),
            authority_score=int(data.get("authority_score", 0) or 0),
            backlinks_total=int(data.get("backlinks_total", 0) or 0),
            backlink_domains_total=int(data.get("backlink_domains_total", 0) or 0),
            backlinks=backlinks,
            raw=data,
        )


@dataclass
class SemrushKeyword:
    """Keyword data from Semrush."""
    keyword: str = ""
    position: int = 0
    traffic_share: float = 0.0
    search_volume: int = 0
    cpc: float = 0.0
    difficulty: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushKeyword":
        return cls(
            keyword=data.get("keyword", ""),
            position=int(data.get("position", 0) or 0),
            traffic_share=float(data.get("traffic_share", 0) or 0),
            search_volume=int(data.get("search_volume", 0) or 0),
            cpc=float(data.get("cpc", 0) or 0),
            difficulty=int(data.get("difficulty", 0) or data.get("keyword_difficulty_index", 0) or 0),
            raw=data,
        )


@dataclass
class SemrushCompetitor:
    """Competitor data from Semrush."""
    domain: str = ""
    relevance: float = 0.0
    organic_keywords: int = 0
    common_keywords: int = 0
    organic_traffic: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushCompetitor":
        return cls(
            domain=data.get("domain", ""),
            relevance=float(data.get("relevance", 0) or 0),
            organic_keywords=int(data.get("organic_keywords", 0) or 0),
            common_keywords=int(data.get("common_keywords", 0) or 0),
            organic_traffic=int(data.get("organic_traffic", 0) or 0),
            raw=data,
        )


@dataclass
class SemrushAIVisibility:
    """AI visibility metrics from Semrush."""
    data_captured_at: str = ""
    domain: str = ""
    ai_visibility_score: float = 0.0
    ai_mentions_total: int = 0
    ai_mentions_google_ai_overview: int = 0
    ai_mentions_chat_gpt: int = 0
    competitors: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "SemrushAIVisibility":
        return cls(
            data_captured_at=data.get("data_captured_at", datetime.utcnow().isoformat()),
            domain=data.get("domain", ""),
            ai_visibility_score=float(data.get("ai_visibility_score", 0) or 0),
            ai_mentions_total=int(data.get("ai_mentions_total", 0) or 0),
            ai_mentions_google_ai_overview=int(data.get("ai_mentions_google_ai_overview", 0) or 0),
            ai_mentions_chat_gpt=int(data.get("ai_mentions_chat_gpt", 0) or 0),
            competitors=data.get("ai_visibility_competitors", []),
            raw=data,
        )


@dataclass
class SemrushDomainAnalysis:
    """Complete Semrush domain analysis."""
    data_captured_at: str = ""
    domain: str = ""
    country: str = "us"

    # Core metrics
    authority: Optional[SemrushAuthorityData] = None
    traffic: Optional[SemrushTrafficData] = None
    backlinks: Optional[SemrushBacklinksData] = None
    ai_visibility: Optional[SemrushAIVisibility] = None

    # Lists
    top_keywords: List[SemrushKeyword] = field(default_factory=list)
    competitors: List[SemrushCompetitor] = field(default_factory=list)

    # History data
    authority_history: List[Dict[str, Any]] = field(default_factory=list)
    backlinks_history: List[Dict[str, Any]] = field(default_factory=list)
    traffic_history: List[Dict[str, Any]] = field(default_factory=list)

    # Raw data
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "data_captured_at": self.data_captured_at,
            "domain": self.domain,
            "country": self.country,
            "authority_score": self.authority.authority_score if self.authority else 0,
            "moz_domain_authority": self.authority.moz_domain_authority if self.authority else 0,
            "visits": self.traffic.visits if self.traffic else 0,
            "bounce_rate": self.traffic.bounce_rate if self.traffic else 0,
            "traffic_organic": self.traffic.traffic_organic if self.traffic else 0,
            "traffic_paid": self.traffic.traffic_paid if self.traffic else 0,
            "backlinks_total": self.backlinks.backlinks_total if self.backlinks else 0,
            "backlink_domains": self.backlinks.backlink_domains_total if self.backlinks else 0,
            "ai_visibility_score": self.ai_visibility.ai_visibility_score if self.ai_visibility else 0,
            "top_keywords_count": len(self.top_keywords),
            "competitors_count": len(self.competitors),
        }


# =============================================================================
# I/O LEGEND CODES
# =============================================================================

"""
Semrush Scraper I/O Legend:

INPUTS:
- urls                   : Domains/URLs to analyze
- keyword                : Keyword for research
- country                : Country code (us, uk, de, etc.)
- include_ai_visibility  : Include AI visibility metrics
- include_overview       : Include basic domain metrics
- include_traffic        : Include traffic data
- include_authority      : Include authority metrics
- include_backlinks      : Include backlinks data
- include_competitors    : Include competitor analysis
- include_keyword_volume : Include keyword volume data
- include_keywords_ranking: Include keyword rankings
- include_seo            : Include SEO audit
- include_serp           : Include SERP data
- include_top_websites   : Include top websites ranking

OUTPUTS:
- data_captured_at       : Timestamp of data capture
- last_updated           : When Semrush last updated
- authority_score        : Domain authority (0-100)
- moz_domain_authority   : Moz DA score
- moz_spam_score         : Spam score percentage
- visits                 : Monthly visits
- bounce_rate            : Bounce rate (0-1)
- pages_per_visit        : Average pages per visit
- time_on_site           : Average time on site (seconds)
- global_rank            : Global ranking
- country_rank           : Country-specific ranking
- traffic_organic        : Organic search traffic
- traffic_paid           : Paid search traffic
- backlinks_total        : Total backlinks
- backlink_domains_total : Referring domains
- top_keywords           : Top ranking keywords
- competitors            : Competitor domains

RELATIONSHIPS:
- domain            -> domain
- authority_score   -> seo_authority
- backlinks_total   -> backlinks_count
- traffic_organic   -> organic_traffic
- competitors       -> competitor_domains
"""


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
    domain: str,
    *,
    country: str = "us",
    include_ai_visibility: bool = True,
    include_overview: bool = True,
    include_traffic: bool = True,
    include_authority: bool = True,
    include_backlinks: bool = True,
    include_competitors: bool = True,
    include_keyword_volume: bool = False,
    include_keywords_ranking: bool = False,
    include_seo: bool = False,
) -> Optional[SemrushDomainAnalysis]:
    """
    Perform full Semrush domain analysis.

    Args:
        domain: Domain to analyze
        country: Country code for analysis
        include_*: Flags to include specific data types

    Returns:
        SemrushDomainAnalysis or None

    Example:
        analysis = analyze_domain("example.com", country="us")
        print(f"Authority: {analysis.authority.authority_score}")
        print(f"Traffic: {analysis.traffic.visits:,} visits/month")
    """
    client = _get_client()

    run_input = {
        "urls": [domain],
        "country": country,
        "include_ai_visibility": include_ai_visibility,
        "include_overview": include_overview,
        "include_traffic": include_traffic,
        "include_authority": include_authority,
        "include_backlinks": include_backlinks,
        "include_competitors": include_competitors,
        "include_keyword_volume": include_keyword_volume,
        "include_keywords_ranking": include_keywords_ranking,
        "include_seo": include_seo,
    }

    try:
        logger.info(f"Running Semrush analysis for {domain}")
        run = client.actor(SEMRUSH_DOMAIN_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        if not results:
            return None

        analysis = SemrushDomainAnalysis(
            data_captured_at=datetime.utcnow().isoformat(),
            domain=domain,
            country=country,
            raw=results,
        )

        # Parse results by type
        for item in results:
            item_type = item.get("type", "")

            if item_type == "domain_authority" or "authority_score" in item:
                analysis.authority = SemrushAuthorityData.from_apify(item)
                analysis.authority_history = item.get("authority_score_history", [])
                analysis.backlinks_history = item.get("backlinks_history", [])

            elif item_type == "website_traffic" or "visits" in item:
                analysis.traffic = SemrushTrafficData.from_apify(item)
                analysis.traffic_history = item.get("search_traffic_history", [])

            elif item_type == "backlinks" or "backlinks_total" in item:
                analysis.backlinks = SemrushBacklinksData.from_apify(item)

            elif item_type == "ai_visibility":
                analysis.ai_visibility = SemrushAIVisibility.from_apify(item)

            elif item_type == "competitors":
                for comp in item.get("competitors", []):
                    analysis.competitors.append(SemrushCompetitor.from_apify(comp))

            # Extract keywords from any result that has them
            for kw in item.get("organic_keywords", []) or item.get("top_organic_keywords", []):
                analysis.top_keywords.append(SemrushKeyword.from_apify(kw))

        return analysis
    except Exception as e:
        logger.error(f"Semrush analysis failed: {e}")
        return None


def get_authority(domain: str, country: str = "us") -> Optional[SemrushAuthorityData]:
    """
    Get domain authority metrics.

    Args:
        domain: Domain to check
        country: Country code

    Returns:
        SemrushAuthorityData or None
    """
    analysis = analyze_domain(
        domain,
        country=country,
        include_authority=True,
        include_traffic=False,
        include_backlinks=False,
        include_competitors=False,
        include_ai_visibility=False,
    )
    return analysis.authority if analysis else None


def get_traffic(domain: str, country: str = "us") -> Optional[SemrushTrafficData]:
    """
    Get traffic analytics.

    Args:
        domain: Domain to check
        country: Country code

    Returns:
        SemrushTrafficData or None
    """
    analysis = analyze_domain(
        domain,
        country=country,
        include_traffic=True,
        include_authority=False,
        include_backlinks=False,
        include_competitors=False,
        include_ai_visibility=False,
    )
    return analysis.traffic if analysis else None


def get_backlinks(domain: str, country: str = "us") -> Optional[SemrushBacklinksData]:
    """
    Get backlinks profile.

    Args:
        domain: Domain to check
        country: Country code

    Returns:
        SemrushBacklinksData or None
    """
    analysis = analyze_domain(
        domain,
        country=country,
        include_backlinks=True,
        include_traffic=False,
        include_authority=False,
        include_competitors=False,
        include_ai_visibility=False,
    )
    return analysis.backlinks if analysis else None


def get_ai_visibility(domain: str) -> Optional[SemrushAIVisibility]:
    """
    Get AI visibility score and mentions.

    Args:
        domain: Domain to check

    Returns:
        SemrushAIVisibility or None
    """
    analysis = analyze_domain(
        domain,
        include_ai_visibility=True,
        include_traffic=False,
        include_authority=False,
        include_backlinks=False,
        include_competitors=False,
    )
    return analysis.ai_visibility if analysis else None


def search_keyword(
    keyword: str,
    results_count: int = 10,
    search_type: str = "top",
) -> Optional[List[Dict[str, Any]]]:
    """
    Search keyword rankings using Semrush search actor.

    Args:
        keyword: Keyword/query to research
        results_count: Number of results (default 10)
        search_type: Type of search - "top", "organic", etc.

    Returns:
        List of search results or None

    Example:
        results = search_keyword("Tesla", results_count=10)
        for r in results:
            print(r["title"], r["url"])
    """
    client = _get_client()

    run_input = {
        "query": keyword,
        "resultsCount": results_count,
        "searchType": search_type,
    }

    try:
        logger.info(f"Searching Semrush for keyword: {keyword}")
        run = client.actor(SEMRUSH_SEARCH_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        # Return results with data_captured_at added
        enriched = []
        captured_at = datetime.utcnow().isoformat()
        for item in results:
            item["data_captured_at"] = captured_at
            item["query"] = keyword
            enriched.append(item)

        return enriched if enriched else None
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return None


def search_keyword_volume(
    keyword: str,
    country: str = "us",
) -> Optional[Dict[str, Any]]:
    """
    Search keyword volume and metrics using domain analysis actor.

    Args:
        keyword: Keyword to research
        country: Country code

    Returns:
        Keyword volume data dict or None
    """
    client = _get_client()

    run_input = {
        "keyword": keyword,
        "country": country,
        "include_keyword_volume": True,
        "include_serp": True,
    }

    try:
        run = client.actor(SEMRUSH_DOMAIN_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        for item in results:
            if item.get("type") == "keyword_volume":
                return {
                    "data_captured_at": item.get("data_captured_at", datetime.utcnow().isoformat()),
                    "keyword": keyword,
                    "country": country,
                    "search_volume": item.get("monthly_average_search_volume", 0),
                    "global_volume": item.get("global_search_volume", 0),
                    "difficulty": item.get("keyword_difficulty_index", 0),
                    "cpc": item.get("average_cpc", 0),
                    "intent": item.get("intent", []),
                    "country_shares": item.get("country_shares", []),
                }

        return None
    except Exception as e:
        logger.error(f"Keyword volume search failed: {e}")
        return None


def audit_seo(domain: str) -> Optional[Dict[str, Any]]:
    """
    Perform SEO audit of a domain.

    Args:
        domain: Domain to audit

    Returns:
        SEO audit data dict or None
    """
    client = _get_client()

    run_input = {
        "urls": [domain],
        "include_seo": True,
    }

    try:
        run = client.actor(SEMRUSH_DOMAIN_ACTOR).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        for item in results:
            if item.get("type") == "seo_audit":
                return {
                    "data_captured_at": item.get("data_captured_at", datetime.utcnow().isoformat()),
                    "domain": domain,
                    "domain_authority": item.get("domain_authority", 0),
                    "referral_domains": item.get("referral_domains", 0),
                    "keyword_count": item.get("keyword_count", 0),
                    "title": item.get("title", ""),
                    "meta_description": item.get("meta_description", ""),
                    "headings": item.get("headings", {}),
                    "word_count": item.get("word_count", 0),
                    "images": len(item.get("images", [])),
                    "links_internal": len(item.get("links_internal", [])),
                    "links_external": len(item.get("links_external", [])),
                    "robots_txt": item.get("robots_txt", ""),
                    "sitemap": item.get("sitemap", ""),
                }

        return None
    except Exception as e:
        logger.error(f"SEO audit failed: {e}")
        return None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "SemrushDomainAnalysis",
    "SemrushAuthorityData",
    "SemrushTrafficData",
    "SemrushBacklinksData",
    "SemrushBacklink",
    "SemrushKeyword",
    "SemrushCompetitor",
    "SemrushAIVisibility",
    # Search functions
    "analyze_domain",
    "get_authority",
    "get_traffic",
    "get_backlinks",
    "get_ai_visibility",
    "search_keyword",
    "search_keyword_volume",
    "audit_seo",
    # Config
    "SUPPORTED_COUNTRIES",
    "TOP_WEBSITE_INDUSTRIES",
    "SEMRUSH_DOMAIN_ACTOR",
    "SEMRUSH_SEARCH_ACTOR",
    "SEMRUSH_ACTOR_ID",  # Legacy
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python semrush.py <domain> [country]")
        print("\nExamples:")
        print("  python semrush.py example.com")
        print("  python semrush.py example.com uk")
        print("\nActors:")
        print(f"  Domain: {SEMRUSH_DOMAIN_ACTOR}")
        print(f"  Search: {SEMRUSH_SEARCH_ACTOR}")
        sys.exit(1)

    domain = sys.argv[1]
    country = sys.argv[2] if len(sys.argv) > 2 else "us"

    print(f"📊 Analyzing {domain} with Semrush ({country})")

    analysis = analyze_domain(domain, country=country)

    if analysis:
        print(f"\n📋 {analysis.domain}")
        if analysis.authority:
            print(f"   Authority Score: {analysis.authority.authority_score}")
            print(f"   Moz DA: {analysis.authority.moz_domain_authority}")
        if analysis.traffic:
            print(f"   Monthly Visits: {analysis.traffic.visits:,}")
            print(f"   Bounce Rate: {analysis.traffic.bounce_rate:.1%}")
            print(f"   Organic Traffic: {analysis.traffic.traffic_organic:,}")
        if analysis.backlinks:
            print(f"   Total Backlinks: {analysis.backlinks.backlinks_total:,}")
            print(f"   Referring Domains: {analysis.backlinks.backlink_domains_total:,}")
        if analysis.ai_visibility:
            print(f"   AI Visibility Score: {analysis.ai_visibility.ai_visibility_score}")
            print(f"   AI Mentions: {analysis.ai_visibility.ai_mentions_total}")
        if analysis.competitors:
            print(f"   Top Competitors: {[c.domain for c in analysis.competitors[:5]]}")
    else:
        print("❌ Analysis failed - check SEMRUSH_ACTOR_ID is set")
