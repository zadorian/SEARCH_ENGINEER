#!/usr/bin/env python3
"""
LinkedIn platform support for Socialite.

Provides:
- URL generators for profiles and search
- Firecrawl-based screenshots (if FIRECRAWL_API_KEY set)
- BrightData API integration for structured data collection (profiles, companies, jobs, posts)

URL Generators (no auth required):
    linkedin_profile(username) -> profile URL
    linkedin_company(company_slug) -> company page URL
    linkedin_search(query) -> search URL

Firecrawl (requires FIRECRAWL_API_KEY):
    LinkedInDriver - screenshot profiles, extract bio

BrightData Data Collection (requires BRIGHTDATA_API_TOKEN):
    collect_profile(profile_url) -> dict
    collect_company(company_url) -> dict
    collect_posts(post_urls) -> list[dict]
    collect_jobs(job_urls) -> list[dict]

    # Typed wrapper
    LinkedInDataCollector - async context manager
"""

import os
import logging
import sys
import asyncio
import aiohttp
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, List, Tuple, Sequence, Iterable
from urllib.parse import quote
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LinkedInProfile:
    """LinkedIn profile data."""
    profile_url: str
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    headline: str = ""
    location: str = ""
    about: str = ""
    current_company: str = ""
    current_title: str = ""
    connections: int = 0
    followers: int = 0
    profile_image: str = ""
    banner_image: str = ""
    experience: list = field(default_factory=list)
    education: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    certifications: list = field(default_factory=list)
    languages: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "LinkedInProfile":
        return cls(
            profile_url=data.get("url", data.get("profile_url", "")),
            name=data.get("name", ""),
            first_name=data.get("first_name", data.get("firstName", "")),
            last_name=data.get("last_name", data.get("lastName", "")),
            headline=data.get("headline", data.get("title", "")),
            location=data.get("location", ""),
            about=data.get("about", data.get("summary", "")),
            current_company=data.get("current_company", data.get("company", "")),
            current_title=data.get("current_title", data.get("position", "")),
            connections=data.get("connections", 0),
            followers=data.get("followers", 0),
            profile_image=data.get("profile_image", data.get("avatar", "")),
            banner_image=data.get("banner_image", data.get("background_image", "")),
            experience=data.get("experience", []),
            education=data.get("education", []),
            skills=data.get("skills", []),
            certifications=data.get("certifications", []),
            languages=data.get("languages", []),
            raw=data,
        )


@dataclass
class LinkedInCompany:
    """LinkedIn company data."""
    company_url: str
    name: str = ""
    description: str = ""
    industry: str = ""
    company_size: str = ""
    employee_count: int = 0
    headquarters: str = ""
    founded: str = ""
    website: str = ""
    specialties: list = field(default_factory=list)
    followers: int = 0
    logo_url: str = ""
    banner_url: str = ""
    company_type: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "LinkedInCompany":
        return cls(
            company_url=data.get("url", data.get("company_url", "")),
            name=data.get("name", ""),
            description=data.get("description", data.get("about", "")),
            industry=data.get("industry", ""),
            company_size=data.get("company_size", data.get("size", "")),
            employee_count=data.get("employee_count", data.get("employees", 0)),
            headquarters=data.get("headquarters", data.get("hq", "")),
            founded=data.get("founded", ""),
            website=data.get("website", ""),
            specialties=data.get("specialties", []),
            followers=data.get("followers", 0),
            logo_url=data.get("logo", data.get("logo_url", "")),
            banner_url=data.get("banner", data.get("banner_url", "")),
            company_type=data.get("type", data.get("company_type", "")),
            raw=data,
        )


@dataclass
class LinkedInJob:
    """LinkedIn job posting data."""
    job_url: str
    job_id: str = ""
    title: str = ""
    company: str = ""
    company_url: str = ""
    location: str = ""
    description: str = ""
    employment_type: str = ""
    seniority_level: str = ""
    posted_at: Optional[datetime] = None
    applicants: int = 0
    salary: str = ""
    remote: bool = False
    skills: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "LinkedInJob":
        posted = data.get("posted_at", data.get("date_posted"))
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except:
                posted = None
        return cls(
            job_url=data.get("url", data.get("job_url", "")),
            job_id=data.get("job_id", data.get("id", "")),
            title=data.get("title", data.get("job_title", "")),
            company=data.get("company", data.get("company_name", "")),
            company_url=data.get("company_url", ""),
            location=data.get("location", ""),
            description=data.get("description", data.get("job_description", "")),
            employment_type=data.get("employment_type", data.get("job_type", "")),
            seniority_level=data.get("seniority_level", data.get("experience_level", "")),
            posted_at=posted,
            applicants=data.get("applicants", data.get("applicant_count", 0)),
            salary=data.get("salary", data.get("compensation", "")),
            remote=data.get("remote", data.get("is_remote", False)),
            skills=data.get("skills", []),
            raw=data,
        )


@dataclass
class LinkedInPost:
    """LinkedIn post data."""
    post_url: str
    post_id: str = ""
    author_name: str = ""
    author_url: str = ""
    author_headline: str = ""
    content: str = ""
    posted_at: Optional[datetime] = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    media_urls: list = field(default_factory=list)
    hashtags: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict) -> "LinkedInPost":
        posted = data.get("posted_at", data.get("date_posted", data.get("timestamp")))
        if isinstance(posted, str):
            try:
                posted = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except:
                posted = None
        return cls(
            post_url=data.get("url", data.get("post_url", "")),
            post_id=data.get("post_id", data.get("id", "")),
            author_name=data.get("author_name", data.get("author", "")),
            author_url=data.get("author_url", data.get("author_profile", "")),
            author_headline=data.get("author_headline", ""),
            content=data.get("content", data.get("text", "")),
            posted_at=posted,
            likes=data.get("likes", data.get("like_count", 0)),
            comments=data.get("comments", data.get("comment_count", 0)),
            shares=data.get("shares", data.get("share_count", 0)),
            media_urls=data.get("media_urls", data.get("media", [])),
            hashtags=data.get("hashtags", []),
            raw=data,
        )


# =============================================================================
# URL GENERATORS (no auth required)
# =============================================================================

def linkedin_profile(username: str) -> str:
    """Generate direct profile URL."""
    return f"https://www.linkedin.com/in/{username}/"


def linkedin_company(company_slug: str) -> str:
    """Generate company page URL."""
    return f"https://www.linkedin.com/company/{company_slug}/"


def linkedin_search(query: str) -> str:
    """Generate search URL."""
    return f"https://www.linkedin.com/search/results/all/?keywords={quote(query)}"


def linkedin_jobs_search(query: str, location: str = "") -> str:
    """Generate job search URL."""
    url = f"https://www.linkedin.com/jobs/search/?keywords={quote(query)}"
    if location:
        url += f"&location={quote(location)}"
    return url


# =============================================================================
# FIRECRAWL-BASED DRIVER (original functionality)
# =============================================================================

class LinkedInDriver:
    """
    LinkedIn automation driver using Firecrawl for screenshots.

    Since browser automation (Playwright/Selenium) is not available in this environment,
    this driver relies on:
    1. Direct URL generation (safe)
    2. Firecrawl API for screenshots (if key provided)
    3. Formulaic bio extraction from text
    """

    def __init__(self):
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self.firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")
        self.username = os.getenv("LINKEDIN_USERNAME")
        self.password = os.getenv("LINKEDIN_PASSWORD")
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> Dict[str, Any]:
        """
        Attempt to login to LinkedIn.

        WITHOUT PLAYWRIGHT: This cannot perform a real browser login to bypass 2FA/JS.
        It returns a stubbed session if credentials exist, or checks for existing cookies.
        """
        if not self.username or not self.password:
            return {"success": False, "error": "No credentials found (LINKEDIN_USERNAME/PASSWORD)"}

        logger.warning("Browser automation unavailable. Cannot perform real login.")

        return {
            "success": True,
            "status": "stubbed",
            "message": "Login simulated. Automation unavailable in this environment. Use Firecrawl for public profiles."
        }

    async def screenshot_profile(self, username_or_url: str) -> Dict[str, Any]:
        """
        Take a full-page screenshot of a LinkedIn profile.

        Uses Firecrawl /scrape endpoint with screenshot=true.
        """
        url = username_or_url
        if not url.startswith("http"):
            url = f"https://www.linkedin.com/in/{username_or_url}/"

        if not self.firecrawl_key:
            return {"success": False, "error": "FIRECRAWL_API_KEY not set"}

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.firecrawl_url}/scrape",
                headers={
                    "Authorization": f"Bearer {self.firecrawl_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "url": url,
                    "formats": ["screenshot"],
                    "screenshot": {"fullPage": True}
                },
                timeout=60
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return {
                            "success": True,
                            "screenshot_url": data["data"].get("screenshot"),
                            "profile_url": url
                        }
                    else:
                        return {"success": False, "error": data.get("error", "Unknown Firecrawl error")}
                else:
                    return {"success": False, "error": f"HTTP {resp.status}: {await resp.text()}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_bio(self, raw_text: str) -> Dict[str, str]:
        """
        Extract bio fields in a formulaic way from raw profile text.
        """
        bio = {
            "name": "",
            "headline": "",
            "current_role": "",
            "location": "",
            "about": ""
        }

        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        if not lines:
            return bio

        if len(lines) > 0: bio["name"] = lines[0]
        if len(lines) > 1: bio["headline"] = lines[1]
        if len(lines) > 2: bio["location"] = lines[2]

        try:
            about_idx = -1
            for i, line in enumerate(lines):
                if line.lower() == "about":
                    about_idx = i
                    break

            if about_idx != -1 and about_idx + 1 < len(lines):
                bio["about"] = lines[about_idx + 1]
        except:
            pass

        return bio


# =============================================================================
# BRIGHTDATA INTEGRATION
# =============================================================================

# Add python-libs to path
python_libs = Path("/data/python-libs")
if python_libs.exists() and str(python_libs) not in sys.path:
    sys.path.insert(0, str(python_libs))

try:
    from brightdata import BrightDataClient
    from brightdata.scrapers.linkedin.search import LinkedInSearchScraper
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    BrightDataClient = None
    LinkedInSearchScraper = None


def _get_api_token() -> Optional[str]:
    """Get BrightData API token."""
    return os.getenv("BRIGHTDATA_API_TOKEN") or os.getenv("BRIGHTDATA_API_KEY")


def is_data_collection_available() -> bool:
    """Check if BrightData data collection is available."""
    return SDK_AVAILABLE and bool(_get_api_token())


# Dataset IDs (for reference)
LINKEDIN_DATASETS = {
    "profiles": "gd_l1viktl72bvl7bjuj0",
    "companies": "gd_l1vikfnt1wgvvqz95w",
    "jobs": "gd_lpfll7v5hcqtkxl6l",
    "jobs_discovery": "gd_m487ihp32jtc4ujg45",
    "posts": "gd_lyy3tktm25m4avu764",
}


# =============================================================================
# DATA COLLECTION FUNCTIONS
# =============================================================================

async def collect_profile(
    profile_url: str,
    timeout: int = 180
) -> Optional[dict]:
    """
    Collect profile data from a LinkedIn profile URL.

    Args:
        profile_url: LinkedIn profile URL (e.g., "https://linkedin.com/in/username")
        timeout: Maximum wait time in seconds

    Returns:
        Profile dict with: name, headline, location, about, experience,
        education, skills, connections, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn data collection")
        return None

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.linkedin.profiles(url=profile_url, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data[0] if isinstance(data, list) else data
            return None
    except Exception as e:
        logger.error(f"Failed to collect LinkedIn profile: {e}")
        return None


async def collect_company(
    company_url: str,
    timeout: int = 180
) -> Optional[dict]:
    """
    Collect company data from a LinkedIn company page.

    Args:
        company_url: LinkedIn company URL (e.g., "https://linkedin.com/company/google")
        timeout: Maximum wait time in seconds

    Returns:
        Company dict with: name, description, industry, employee_count,
        headquarters, founded, specialties, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn data collection")
        return None

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.linkedin.companies(url=company_url, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data[0] if isinstance(data, list) else data
            return None
    except Exception as e:
        logger.error(f"Failed to collect LinkedIn company: {e}")
        return None


async def collect_posts(
    post_urls: Union[str, list[str]],
    timeout: int = 180
) -> list[dict]:
    """
    Collect post data from LinkedIn post URLs.

    Args:
        post_urls: Single post URL or list of URLs
        timeout: Maximum wait time in seconds

    Returns:
        List of post dicts with: post_id, content, author, like_count,
        comment_count, share_count, posted_at, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn data collection")
        return []

    urls = [post_urls] if isinstance(post_urls, str) else post_urls

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.linkedin.posts(url=urls, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data if isinstance(data, list) else [data]
            return []
    except Exception as e:
        logger.error(f"Failed to collect LinkedIn posts: {e}")
        return []


async def collect_jobs(
    job_urls: Union[str, list[str]],
    timeout: int = 180
) -> list[dict]:
    """
    Collect job listing data from LinkedIn job URLs.

    Args:
        job_urls: Single job URL or list of URLs
        timeout: Maximum wait time in seconds

    Returns:
        List of job dicts with: job_id, title, company, location, description,
        seniority_level, employment_type, posted_at, applicant_count, etc.
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn data collection")
        return []

    urls = [job_urls] if isinstance(job_urls, str) else job_urls

    try:
        async with BrightDataClient(api_token=_get_api_token()) as client:
            result = await client.crawler.linkedin.jobs(url=urls, timeout=timeout)
            if result and hasattr(result, 'data'):
                data = result.data
                return data if isinstance(data, list) else [data]
            return []
    except Exception as e:
        logger.error(f"Failed to collect LinkedIn jobs: {e}")
        return []


# =============================================================================
# TYPED DATA COLLECTOR
# =============================================================================

class LinkedInDataCollector:
    """
    LinkedIn data collector using BrightData SDK.

    Usage:
        async with LinkedInDataCollector() as li:
            profile = await li.profile("https://linkedin.com/in/username")
            company = await li.company("https://linkedin.com/company/google")
            posts = await li.posts([post_url1, post_url2])
            jobs = await li.jobs([job_url1])
    """

    def __init__(self, timeout: int = 180):
        self.timeout = timeout
        self._client: Optional[Any] = None

    @property
    def available(self) -> bool:
        return is_data_collection_available()

    async def __aenter__(self):
        if not SDK_AVAILABLE:
            raise RuntimeError("BrightData SDK not installed")
        token = _get_api_token()
        if not token:
            raise RuntimeError("BRIGHTDATA_API_TOKEN not configured")
        self._client = BrightDataClient(api_token=token)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    def _extract_data(self, result) -> list[dict]:
        """Extract data from ScrapeResult."""
        if result is None:
            return []
        if hasattr(result, 'data'):
            data = result.data
            if isinstance(data, list):
                return data
            elif data is not None:
                return [data]
        return []

    async def profile(self, profile_url: str) -> Optional[dict]:
        """Collect profile data."""
        result = await self._client.crawler.linkedin.profiles(
            url=profile_url, timeout=self.timeout
        )
        data = self._extract_data(result)
        return data[0] if data else None

    async def company(self, company_url: str) -> Optional[dict]:
        """Collect company data."""
        result = await self._client.crawler.linkedin.companies(
            url=company_url, timeout=self.timeout
        )
        data = self._extract_data(result)
        return data[0] if data else None

    async def posts(self, post_urls: Union[str, list[str]]) -> list[dict]:
        """Collect post data."""
        urls = [post_urls] if isinstance(post_urls, str) else post_urls
        result = await self._client.crawler.linkedin.posts(
            url=urls, timeout=self.timeout
        )
        return self._extract_data(result)

    async def jobs(self, job_urls: Union[str, list[str]]) -> list[dict]:
        """Collect job listing data."""
        urls = [job_urls] if isinstance(job_urls, str) else job_urls
        result = await self._client.crawler.linkedin.jobs(
            url=urls, timeout=self.timeout
        )
        return self._extract_data(result)


# =============================================================================
# SEARCH FUNCTIONS (name/keyword based discovery)
# =============================================================================

async def search_profiles(
    first_name: str,
    last_name: Optional[str] = None,
    timeout: int = 180,
) -> list[LinkedInProfile]:
    """
    Search for LinkedIn profiles by name.

    Args:
        first_name: First name to search for
        last_name: Last name to search for (optional)
        timeout: Maximum wait time in seconds

    Returns:
        List of LinkedInProfile objects matching the search
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn search")
        return []

    if not LinkedInSearchScraper:
        logger.warning("LinkedInSearchScraper not available")
        return []

    try:
        token = _get_api_token()
        scraper = LinkedInSearchScraper(bearer_token=token)
        result = await scraper.profiles(
            firstName=first_name,
            lastName=last_name,
            timeout=timeout,
        )
        if result and hasattr(result, 'data'):
            data = result.data if isinstance(result.data, list) else [result.data]
            return [LinkedInProfile.from_api(d) for d in data if d]
        return []
    except Exception as e:
        logger.error(f"Failed to search LinkedIn profiles: {e}")
        return []


async def search_jobs(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    country: Optional[str] = None,
    remote: Optional[bool] = None,
    job_type: Optional[str] = None,
    experience_level: Optional[str] = None,
    company: Optional[str] = None,
    time_range: Optional[str] = None,
    timeout: int = 180,
) -> list[LinkedInJob]:
    """
    Search for LinkedIn jobs by keyword and filters.

    Args:
        keyword: Job keyword/title (e.g., "python developer")
        location: Location filter (e.g., "New York")
        country: Country code (2-letter)
        remote: Remote jobs only
        job_type: Job type ("full-time", "part-time", "contract", etc.)
        experience_level: Experience level ("entry", "mid", "senior", etc.)
        company: Company name filter
        time_range: Time range ("day", "week", "month")
        timeout: Maximum wait time in seconds

    Returns:
        List of LinkedInJob objects matching the search
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn search")
        return []

    if not LinkedInSearchScraper:
        logger.warning("LinkedInSearchScraper not available")
        return []

    try:
        token = _get_api_token()
        scraper = LinkedInSearchScraper(bearer_token=token)
        result = await scraper.jobs(
            keyword=keyword,
            location=location,
            country=country,
            remote=remote,
            jobType=job_type,
            experienceLevel=experience_level,
            company=company,
            timeRange=time_range,
            timeout=timeout,
        )
        if result and hasattr(result, 'data'):
            data = result.data if isinstance(result.data, list) else [result.data]
            return [LinkedInJob.from_api(d) for d in data if d]
        return []
    except Exception as e:
        logger.error(f"Failed to search LinkedIn jobs: {e}")
        return []


async def discover_posts(
    profile_url: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeout: int = 180,
) -> list[LinkedInPost]:
    """
    Discover posts from a LinkedIn profile within a date range.

    Args:
        profile_url: LinkedIn profile URL
        start_date: Start date in yyyy-mm-dd format (optional)
        end_date: End date in yyyy-mm-dd format (optional)
        timeout: Maximum wait time in seconds

    Returns:
        List of LinkedInPost objects from the profile
    """
    if not is_data_collection_available():
        logger.warning("BrightData not available for LinkedIn search")
        return []

    if not LinkedInSearchScraper:
        logger.warning("LinkedInSearchScraper not available")
        return []

    try:
        token = _get_api_token()
        scraper = LinkedInSearchScraper(bearer_token=token)
        result = await scraper.posts(
            profile_url=profile_url,
            start_date=start_date,
            end_date=end_date,
            timeout=timeout,
        )
        if result and hasattr(result, 'data'):
            data = result.data if isinstance(result.data, list) else [result.data]
            return [LinkedInPost.from_api(d) for d in data if d]
        return []
    except Exception as e:
        logger.error(f"Failed to discover LinkedIn posts: {e}")
        return []


# =============================================================================
# TYPED CONVENIENCE FUNCTIONS (return dataclasses instead of dicts)
# =============================================================================

async def linkedin_profile_data(profile_url: str, timeout: int = 180) -> Optional[LinkedInProfile]:
    """Get typed LinkedIn profile data."""
    data = await collect_profile(profile_url, timeout)
    return LinkedInProfile.from_api(data) if data else None


async def linkedin_company_data(company_url: str, timeout: int = 180) -> Optional[LinkedInCompany]:
    """Get typed LinkedIn company data."""
    data = await collect_company(company_url, timeout)
    return LinkedInCompany.from_api(data) if data else None


async def linkedin_job_data(job_url: str, timeout: int = 180) -> Optional[LinkedInJob]:
    """Get typed LinkedIn job data."""
    jobs = await collect_jobs(job_url, timeout)
    return LinkedInJob.from_api(jobs[0]) if jobs else None


async def linkedin_jobs_data(job_urls: list[str], timeout: int = 180) -> list[LinkedInJob]:
    """Get typed LinkedIn jobs data."""
    jobs = await collect_jobs(job_urls, timeout)
    return [LinkedInJob.from_api(j) for j in jobs if j]


async def linkedin_post_data(post_url: str, timeout: int = 180) -> Optional[LinkedInPost]:
    """Get typed LinkedIn post data."""
    posts = await collect_posts(post_url, timeout)
    return LinkedInPost.from_api(posts[0]) if posts else None


async def linkedin_posts_data(post_urls: list[str], timeout: int = 180) -> list[LinkedInPost]:
    """Get typed LinkedIn posts data."""
    posts = await collect_posts(post_urls, timeout)
    return [LinkedInPost.from_api(p) for p in posts if p]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # URL generators
    "linkedin_profile",
    "linkedin_company",
    "linkedin_search",
    "linkedin_jobs_search",
    # Data structures
    "LinkedInProfile",
    "LinkedInCompany",
    "LinkedInJob",
    "LinkedInPost",
    # Firecrawl driver
    "LinkedInDriver",
    # Data collection (URL-based, returns dicts)
    "is_data_collection_available",
    "collect_profile",
    "collect_company",
    "collect_posts",
    "collect_jobs",
    # Typed data collection (URL-based, returns dataclasses)
    "linkedin_profile_data",
    "linkedin_company_data",
    "linkedin_job_data",
    "linkedin_jobs_data",
    "linkedin_post_data",
    "linkedin_posts_data",
    # Search/discovery functions (keyword-based)
    "search_profiles",
    "search_jobs",
    "discover_posts",
    # Typed collector class
    "LinkedInDataCollector",
    # Dataset IDs
    "LINKEDIN_DATASETS",
]

# =============================================================================
# SEARCH HELPERS (merged from linkedin_search.py)
# =============================================================================

class LinkedInCompanySearch:
    """
    Search LinkedIn for company profiles and information
    """

    # LinkedIn URL structures
    BASE_URL = "https://www.linkedin.com/uas/login?session_redirect="
    COMPANY_SEARCH_URL = "https://www.linkedin.com/search/results/companies/?"
    COMPANY_PROFILE_URL = "https://www.linkedin.com/company/"

    def __init__(self):
        """Initialize LinkedIn company search"""
        self.linkedin_engine = None
        try:
            # Try to import the LinkedIn search aggregator
            from Social_Media.linkedin_engine import LinkedInSearchAggregator
            self.linkedin_engine = LinkedInSearchAggregator()
            logger.info("LinkedIn search engine initialized")
        except ImportError:
            logger.warning("LinkedIn search engine not available")

    def build_company_search_url(self, company_name: str, **kwargs) -> str:
        """
        Build LinkedIn company search URL.

        Args:
            company_name: Company name to search
            **kwargs: Additional parameters like industry, location, size

        Returns:
            LinkedIn company search URL with login redirect
        """
        query_params = []

        # Main keywords parameter
        query_params.append(f"keywords={urllib.parse.quote(company_name)}")

        # Add industry filter if specified
        if kwargs.get('industry'):
            query_params.append(f"industry={urllib.parse.quote(kwargs['industry'])}")

        # Add location filter if specified
        if kwargs.get('location'):
            query_params.append(f"location={urllib.parse.quote(kwargs['location'])}")

        # Add company size filter if specified
        if kwargs.get('size'):
            # LinkedIn uses codes like B (1-10), C (11-50), D (51-200), E (201-500), F (501-1000), etc.
            size_map = {
                'small': 'B,C',  # 1-50 employees
                'medium': 'D,E',  # 51-500 employees
                'large': 'F,G,H',  # 500+ employees
            }
            if kwargs['size'].lower() in size_map:
                query_params.append(f"companySize={size_map[kwargs['size'].lower()]}")

        # Build the search URL
        search_params = "&".join(query_params)
        full_search_url = self.COMPANY_SEARCH_URL + search_params

        # URL encode the redirect URL for the login page
        encoded_redirect = urllib.parse.quote(full_search_url, safe='')

        final_url = self.BASE_URL + encoded_redirect

        logger.info(f"Built LinkedIn company search URL for: {company_name}")
        logger.debug(f"Final URL: {final_url}")

        return final_url

    def build_company_profile_url(self, company_slug: str) -> str:
        """
        Build direct LinkedIn company profile URL.

        Args:
            company_slug: LinkedIn company slug (e.g., 'microsoft', 'apple')

        Returns:
            Direct LinkedIn company profile URL
        """
        return f"{self.COMPANY_PROFILE_URL}{company_slug}"

    async def search_company_profiles(self, company_name: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for company profiles on LinkedIn using search engines.

        Args:
            company_name: Company name to search for
            limit: Maximum number of results

        Returns:
            Dictionary with search results
        """
        results = {
            'company_profiles': [],
            'related_pages': [],
            'total_results': 0,
            'search_url': self.build_company_search_url(company_name)
        }

        if not self.linkedin_engine:
            logger.warning("LinkedIn engine not available, returning search URL only")
            return results

        try:
            # Search for LinkedIn company pages
            search_results = await self.linkedin_engine.search_linkedin(
                f"{company_name} company about",
                max_results_per_engine=limit
            )

            # Process and categorize results
            for result in search_results:
                url = result.get('url', '')
                title = result.get('title', '')
                snippet = result.get('snippet', '')

                # Categorize LinkedIn URLs
                if '/company/' in url:
                    # Company profile page
                    results['company_profiles'].append({
                        'url': url,
                        'title': title,
                        'snippet': snippet,
                        'type': 'company_profile',
                        'source': result.get('source', 'linkedin')
                    })
                elif '/in/' in url:
                    # Skip people profiles in company search
                    continue
                elif 'linkedin.com' in url:
                    # Other LinkedIn pages (posts, articles, etc.)
                    results['related_pages'].append({
                        'url': url,
                        'title': title,
                        'snippet': snippet,
                        'type': 'related',
                        'source': result.get('source', 'linkedin')
                    })

            results['total_results'] = len(results['company_profiles']) + len(results['related_pages'])

            logger.info(f"Found {len(results['company_profiles'])} company profiles for: {company_name}")

        except Exception as e:
            logger.error(f"Error searching LinkedIn company profiles: {e}")

        return results

    def extract_company_slug(self, company_name: str) -> str:
        """
        Try to generate a LinkedIn company slug from company name.

        Args:
            company_name: Company name

        Returns:
            Probable LinkedIn slug
        """
        # Common company slug patterns
        slug = company_name.lower()

        # Remove common suffixes
        suffixes = [' inc', ' inc.', ' incorporated', ' corp', ' corp.', ' corporation',
                   ' ltd', ' ltd.', ' limited', ' llc', ' l.l.c.', ' plc', ' p.l.c.',
                   ' gmbh', ' ag', ' sa', ' s.a.', ' nv', ' n.v.', ' bv', ' b.v.']

        for suffix in suffixes:
            if slug.endswith(suffix):
                slug = slug[:-len(suffix)]
                break

        # Replace spaces and special characters
        slug = slug.replace(' & ', '-')
        slug = slug.replace('&', '-')
        slug = slug.replace(' ', '-')
        slug = slug.replace('.', '')
        slug = slug.replace(',', '')
        slug = slug.replace("'", '')

        # Remove multiple dashes
        while '--' in slug:
            slug = slug.replace('--', '-')

        # Remove leading/trailing dashes
        slug = slug.strip('-')

        return slug

    def generate_linkedin_urls(self, company_name: str) -> List[str]:
        """
        Generate multiple possible LinkedIn URLs for a company.

        Args:
            company_name: Company name

        Returns:
            List of possible LinkedIn URLs
        """
        urls = []

        # Add search URL
        urls.append(self.build_company_search_url(company_name))

        # Generate possible profile URLs
        slug = self.extract_company_slug(company_name)
        if slug:
            urls.append(self.build_company_profile_url(slug))

            # Try variations
            if '-' in slug:
                # Try without dashes
                urls.append(self.build_company_profile_url(slug.replace('-', '')))

            # Try first word only for simple names
            first_word = slug.split('-')[0]
            if first_word != slug:
                urls.append(self.build_company_profile_url(first_word))

        return urls

    def format_for_corporate_search(self, results: Dict[str, Any]) -> List[Dict]:
        """
        Format LinkedIn results for integration with corporate search.

        Args:
            results: Raw LinkedIn search results

        Returns:
            Formatted list for corporate search integration
        """
        formatted = []

        # Format company profiles
        for profile in results.get('company_profiles', []):
            formatted.append({
                'type': 'social_profile',
                'platform': 'LinkedIn',
                'profile_type': 'Company',
                'url': profile.get('url'),
                'title': profile.get('title', ''),
                'description': profile.get('snippet', ''),
                'confidence': 0.9 if '/company/' in profile.get('url', '') else 0.7,
                'data_source': 'LinkedIn Company Search'
            })

        # Add direct search URL as a result
        if results.get('search_url'):
            formatted.append({
                'type': 'search_link',
                'platform': 'LinkedIn',
                'search_type': 'Company Search',
                'url': results.get('search_url'),
                'title': "LinkedIn Company Search",
                'description': "Direct LinkedIn search for company profiles",
                'confidence': 1.0,
                'data_source': 'LinkedIn URL Builder'
            })

        return formatted


def test_linkedin_company_search():
    """Test the LinkedIn company search functionality"""

    searcher = LinkedInCompanySearch()

    test_companies = ["Apple", "Microsoft", "Tesla", "OpenAI"]

    for company in test_companies:
        print(f"\n{'='*60}")
        print(f"Testing LinkedIn search for: {company}")
        print('='*60)

        # Test URL building
        search_url = searcher.build_company_search_url(company)
        print(f"\nSearch URL: {search_url}")

        # Test slug extraction
        slug = searcher.extract_company_slug(company)
        print(f"Company slug: {slug}")
        profile_url = searcher.build_company_profile_url(slug)
        print(f"Profile URL: {profile_url}")

        # Test URL generation
        urls = searcher.generate_linkedin_urls(company)
        print(f"\nGenerated URLs:")
        for url in urls:
            print(f"  - {url}")

        # Test async search (if engine available)
        if searcher.linkedin_engine:
            print(f"\nSearching for profiles...")
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(
                searcher.search_company_profiles(company, limit=5)
            )

            print(f"Found {results['total_results']} results")
            if results['company_profiles']:
                print(f"\nCompany Profiles:")
                for profile in results['company_profiles'][:3]:
                    print(f"  - {profile['title']}")
                    print(f"    {profile['url']}")

    print("\n" + '='*60)
    print("LinkedIn Company Search Test Complete")
    print("="*60)


if __name__ == "__main__":
    test_linkedin_company_search()
