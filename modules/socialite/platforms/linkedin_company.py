#!/usr/bin/env python3
"""
LINKEDIN COMPANY - LinkedIn Company Scraper via Apify.

Actor: taHaRcqil3scbchuI
Scrapes LinkedIn company profiles for business intelligence.

Usage:
    from socialite.platforms.linkedin_company import (
        scrape_company,
        scrape_companies,
        LinkedInCompany,
    )

    # Scrape single company
    company = scrape_company("https://www.linkedin.com/company/apple")

    # Scrape multiple companies
    companies = scrape_companies([
        "https://www.linkedin.com/company/microsoft",
        "https://www.linkedin.com/company/google",
    ])
"""

import os
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
LINKEDIN_COMPANY_ACTOR_ID = "taHaRcqil3scbchuI"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LinkedInLocation:
    """Company location."""
    city: str = ""
    country: str = ""
    geographic_area: str = ""
    postal_code: str = ""
    street_1: str = ""
    street_2: str = ""
    is_headquarters: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "LinkedInLocation":
        return cls(
            city=data.get("city", ""),
            country=data.get("country", ""),
            geographic_area=data.get("geographicArea", "") or data.get("state", ""),
            postal_code=data.get("postalCode", ""),
            street_1=data.get("line1", "") or data.get("street1", ""),
            street_2=data.get("line2", "") or data.get("street2", ""),
            is_headquarters=data.get("isHeadquarters", False) or data.get("headquarter", False),
            raw=data,
        )

    @property
    def full_address(self) -> str:
        parts = [self.street_1, self.street_2, self.city, self.geographic_area, self.postal_code, self.country]
        return ", ".join(p for p in parts if p)


@dataclass
class LinkedInPost:
    """Company post."""
    text: str = ""
    num_likes: int = 0
    num_comments: int = 0
    posted_at: str = ""
    url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "LinkedInPost":
        return cls(
            text=data.get("text", "") or data.get("content", ""),
            num_likes=int(data.get("numLikes", 0) or data.get("likeCount", 0) or 0),
            num_comments=int(data.get("numComments", 0) or data.get("commentCount", 0) or 0),
            posted_at=data.get("postedAt", "") or data.get("postedDate", ""),
            url=data.get("url", "") or data.get("postUrl", ""),
            raw=data,
        )


@dataclass
class LinkedInCompany:
    """
    LinkedIn company profile data.
    """
    # Basic info
    name: str = ""
    headline: str = ""
    url: str = ""
    universal_name: str = ""

    # Details
    description: str = ""
    website: str = ""
    industry: str = ""
    company_type: str = ""
    founded_year: Optional[int] = None

    # Size
    employee_count: int = 0
    employee_count_range: str = ""
    follower_count: int = 0

    # Specialties
    specialties: List[str] = field(default_factory=list)

    # Locations
    locations: List[LinkedInLocation] = field(default_factory=list)
    headquarters: Optional[LinkedInLocation] = None

    # Branding
    logo: str = ""
    cover_image: str = ""

    # Content
    posts: List[LinkedInPost] = field(default_factory=list)

    # Related
    similar_companies: List[Dict[str, Any]] = field(default_factory=list)
    affiliated_companies: List[Dict[str, Any]] = field(default_factory=list)

    # Raw
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "LinkedInCompany":
        """Create from Apify actor output."""
        # Parse locations
        locations_data = data.get("locations") or data.get("confirmedLocations") or []
        locations = [LinkedInLocation.from_apify(loc) for loc in locations_data]

        # Find headquarters
        headquarters = None
        for loc in locations:
            if loc.is_headquarters:
                headquarters = loc
                break

        # Parse posts
        posts_data = data.get("posts") or data.get("updates") or []
        posts = [LinkedInPost.from_apify(p) for p in posts_data]

        # Parse founded year
        founded_year = None
        if data.get("foundedYear") or data.get("founded"):
            try:
                founded_year = int(data.get("foundedYear") or data.get("founded"))
            except (ValueError, TypeError):
                pass

        return cls(
            name=data.get("name", "") or data.get("companyName", ""),
            headline=data.get("headline", "") or data.get("tagline", ""),
            url=data.get("url", "") or data.get("linkedInUrl", ""),
            universal_name=data.get("universalName", "") or data.get("companyId", ""),
            description=data.get("description", "") or data.get("about", ""),
            website=data.get("website", "") or data.get("companyPageUrl", ""),
            industry=data.get("industry", "") or data.get("industries", [""])[0] if data.get("industries") else "",
            company_type=data.get("companyType", "") or data.get("type", ""),
            founded_year=founded_year,
            employee_count=int(data.get("employeeCount", 0) or data.get("staffCount", 0) or 0),
            employee_count_range=data.get("employeeCountRange", "") or data.get("staffCountRange", ""),
            follower_count=int(data.get("followerCount", 0) or data.get("followersCount", 0) or 0),
            specialties=data.get("specialties", []) or [],
            locations=locations,
            headquarters=headquarters,
            logo=data.get("logo", "") or data.get("logoUrl", ""),
            cover_image=data.get("coverImage", "") or data.get("backgroundCoverImage", ""),
            posts=posts,
            similar_companies=data.get("similarCompanies", []) or [],
            affiliated_companies=data.get("affiliatedCompanies", []) or [],
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "headline": self.headline,
            "url": self.url,
            "description": self.description[:500] if self.description else "",
            "website": self.website,
            "industry": self.industry,
            "company_type": self.company_type,
            "founded_year": self.founded_year,
            "employee_count": self.employee_count,
            "follower_count": self.follower_count,
            "specialties": self.specialties[:10],
            "headquarters": self.headquarters.full_address if self.headquarters else "",
            "locations_count": len(self.locations),
            "posts_count": len(self.posts),
            "similar_companies_count": len(self.similar_companies),
        }


# =============================================================================
# I/O LEGEND CODES
# =============================================================================

"""
LinkedIn Company Scraper I/O Legend:

INPUTS:
- startUrls         : LinkedIn company URLs to scrape
- maxItems          : Maximum items to return
- skipUserPosts     : Skip fetching company posts

OUTPUTS:
- name              : Company name
- headline          : Company tagline/headline
- url               : LinkedIn profile URL
- universalName     : LinkedIn company ID
- description       : Company about text
- website           : Company website
- industry          : Primary industry
- companyType       : Company type (Public, Private, etc.)
- foundedYear       : Year founded
- employeeCount     : Number of employees
- followerCount     : LinkedIn followers
- specialties       : Company specialties list
- locations         : Office locations
- posts             : Recent company posts
- similarCompanies  : Similar companies on LinkedIn
- affiliatedCompanies: Affiliated companies

RELATIONSHIPS:
- name            -> company_name
- url             -> social_profile (LinkedIn)
- industry        -> industry_classification
- locations       -> address[]
- website         -> domain
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


def scrape_company(
    url: str,
    *,
    include_posts: bool = True,
    max_posts: int = 10,
) -> Optional[LinkedInCompany]:
    """
    Scrape a LinkedIn company profile.

    Args:
        url: LinkedIn company URL (e.g., "https://www.linkedin.com/company/apple")
        include_posts: Include company posts
        max_posts: Maximum posts to fetch

    Returns:
        LinkedInCompany or None

    Example:
        company = scrape_company("https://www.linkedin.com/company/apple")
        if company:
            print(f"{company.name}: {company.employee_count} employees")
    """
    results = scrape_companies([url], include_posts=include_posts, max_posts=max_posts)
    return results[0] if results else None


def scrape_companies(
    urls: List[str],
    *,
    include_posts: bool = True,
    max_posts: int = 10,
    max_items: int = 50,
) -> List[LinkedInCompany]:
    """
    Scrape multiple LinkedIn company profiles.

    Args:
        urls: List of LinkedIn company URLs
        include_posts: Include company posts
        max_posts: Maximum posts per company
        max_items: Maximum total items

    Returns:
        List of LinkedInCompany objects

    Example:
        companies = scrape_companies([
            "https://www.linkedin.com/company/microsoft",
            "https://www.linkedin.com/company/google",
        ])
    """
    client = _get_client()

    # Build startUrls
    start_urls = [{"url": url} if not isinstance(url, dict) else url for url in urls]

    run_input = {
        "startUrls": start_urls,
        "maxItems": max_items,
        "skipUserPosts": not include_posts,
    }

    try:
        logger.info(f"Scraping {len(urls)} LinkedIn companies")
        run = client.actor(LINKEDIN_COMPANY_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        return [LinkedInCompany.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"LinkedIn company scrape failed: {e}")
        return []


def scrape_by_name(
    company_name: str,
) -> Optional[LinkedInCompany]:
    """
    Scrape a LinkedIn company by name (constructs URL).

    Args:
        company_name: Company name (will be converted to URL slug)

    Returns:
        LinkedInCompany or None

    Example:
        company = scrape_by_name("Apple")
    """
    # Convert name to URL slug (simplified)
    slug = company_name.lower().replace(" ", "-").replace(".", "").replace(",", "")
    url = f"https://www.linkedin.com/company/{slug}"
    return scrape_company(url)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "LinkedInCompany",
    "LinkedInLocation",
    "LinkedInPost",
    # Scraping functions
    "scrape_company",
    "scrape_companies",
    "scrape_by_name",
    # Config
    "LINKEDIN_COMPANY_ACTOR_ID",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python linkedin_company.py <company_url_or_name>")
        print("\nExamples:")
        print("  python linkedin_company.py https://www.linkedin.com/company/apple")
        print("  python linkedin_company.py apple")
        sys.exit(1)

    input_val = sys.argv[1]

    if input_val.startswith("http"):
        print(f"🔗 Scraping LinkedIn company: {input_val}")
        company = scrape_company(input_val)
    else:
        print(f"🔍 Searching LinkedIn for: {input_val}")
        company = scrape_by_name(input_val)

    if company:
        print(f"\n📋 {company.name}")
        print(f"   Headline: {company.headline}")
        print(f"   Industry: {company.industry}")
        print(f"   Website: {company.website}")
        print(f"   Founded: {company.founded_year}")
        print(f"   Employees: {company.employee_count} ({company.employee_count_range})")
        print(f"   Followers: {company.follower_count:,}")
        if company.headquarters:
            print(f"   HQ: {company.headquarters.full_address}")
        if company.specialties:
            print(f"   Specialties: {', '.join(company.specialties[:5])}")
        if company.posts:
            print(f"\n   Recent Posts ({len(company.posts)}):")
            for post in company.posts[:3]:
                print(f"     - {post.text[:80]}... ({post.num_likes} likes)")
    else:
        print("❌ Company not found")
