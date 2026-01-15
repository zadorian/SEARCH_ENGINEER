#!/usr/bin/env python3
"""
GLASSDOOR - Job scraping via Apify.

Actor: cGlsIU5HiYjpXpmhs
Scrapes job listings from Glassdoor by company, location, keyword.

Usage:
    jobs = search_jobs(company="Google", location="San Francisco")
    jobs = search_jobs(keyword="python developer", country="United States")
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
GLASSDOOR_ACTOR_ID = "cGlsIU5HiYjpXpmhs"

JOB_TYPES = ["fulltime", "parttime", "contract", "internship", "temporary"]
DATE_POSTED = ["all", "today", "3days", "week", "month"]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GlassdoorJob:
    """Job listing from Glassdoor."""
    job_id: str = ""
    title: str = ""
    company: str = ""
    company_id: str = ""
    location: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = ""
    job_type: str = ""
    posted_date: Optional[datetime] = None
    description: str = ""
    url: str = ""
    company_rating: Optional[float] = None
    easy_apply: bool = False
    remote: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_apify(cls, data: Dict[str, Any]) -> "GlassdoorJob":
        """Create from Apify actor output."""
        # Parse salary range
        salary = data.get("salary", {}) or {}
        salary_min = salary.get("min") or data.get("salaryMin")
        salary_max = salary.get("max") or data.get("salaryMax")

        # Parse date
        posted = None
        if data.get("postedDate"):
            try:
                posted = datetime.fromisoformat(data["postedDate"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            job_id=str(data.get("jobId", "") or data.get("id", "")),
            title=data.get("jobTitle", "") or data.get("title", ""),
            company=data.get("employerName", "") or data.get("company", ""),
            company_id=str(data.get("employerId", "")),
            location=data.get("location", "") or data.get("locationName", ""),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary.get("currency", "USD"),
            job_type=data.get("jobType", "") or data.get("employmentType", ""),
            posted_date=posted,
            description=data.get("description", "") or data.get("jobDescription", ""),
            url=data.get("jobUrl", "") or data.get("url", ""),
            company_rating=data.get("employerRating") or data.get("rating"),
            easy_apply=data.get("easyApply", False),
            remote=data.get("remote", False) or "remote" in data.get("location", "").lower(),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": {
                "min": self.salary_min,
                "max": self.salary_max,
                "currency": self.salary_currency,
            } if self.salary_min or self.salary_max else None,
            "job_type": self.job_type,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "url": self.url,
            "company_rating": self.company_rating,
            "easy_apply": self.easy_apply,
            "remote": self.remote,
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


def search_jobs(
    *,
    company: str = "",
    location: str = "",
    country: str = "",
    keyword: str = "",
    job_type: Optional[str] = None,
    date_posted: str = "all",
    pages: int = 1,
) -> List[GlassdoorJob]:
    """
    Search Glassdoor for job listings.

    Args:
        company: Company name filter
        location: Location/city filter
        country: Country name filter
        keyword: Keyword search
        job_type: Job type filter (fulltime, parttime, contract, internship, temporary)
        date_posted: Date filter (all, today, 3days, week, month)
        pages: Number of pages to fetch (default 1)

    Returns:
        List of GlassdoorJob objects

    Example:
        # Search by company
        jobs = search_jobs(company="Google", location="San Francisco")

        # Search by keyword
        jobs = search_jobs(keyword="python developer", country="United States")

        # Filter by job type
        jobs = search_jobs(company="Meta", job_type="fulltime", date_posted="week")
    """
    client = _get_client()

    run_input = {
        "countryName": country,
        "companyName": company,
        "locationName": location,
        "includeKeyword": keyword,
        "pagesToFetch": pages,
        "jobType": job_type,
        "datePosted": date_posted,
    }

    # Remove empty values
    run_input = {k: v for k, v in run_input.items() if v}

    try:
        run = client.actor(GLASSDOOR_ACTOR_ID).call(run_input=run_input)
        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        return [GlassdoorJob.from_apify(r) for r in results]
    except Exception as e:
        logger.error(f"Glassdoor search failed: {e}")
        return []


def search_company_jobs(
    company: str,
    location: str = "",
    max_pages: int = 3,
) -> List[GlassdoorJob]:
    """
    Search all jobs at a specific company.

    Args:
        company: Company name
        location: Optional location filter
        max_pages: Maximum pages to fetch

    Returns:
        List of GlassdoorJob objects
    """
    return search_jobs(company=company, location=location, pages=max_pages)


def search_remote_jobs(
    keyword: str,
    country: str = "United States",
    max_pages: int = 3,
) -> List[GlassdoorJob]:
    """
    Search for remote jobs.

    Args:
        keyword: Job keyword/title
        country: Country filter
        max_pages: Maximum pages

    Returns:
        List of remote GlassdoorJob objects
    """
    jobs = search_jobs(keyword=keyword, country=country, location="Remote", pages=max_pages)
    return [j for j in jobs if j.remote or "remote" in j.location.lower()]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "GlassdoorJob",
    "search_jobs",
    "search_company_jobs",
    "search_remote_jobs",
    "JOB_TYPES",
    "DATE_POSTED",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python glassdoor.py <company|keyword> [location] [pages]")
        print("\nExamples:")
        print("  python glassdoor.py Google")
        print("  python glassdoor.py 'software engineer' 'New York' 2")
        sys.exit(1)

    query = sys.argv[1]
    location = sys.argv[2] if len(sys.argv) > 2 else ""
    pages = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    # Try as company first, then keyword
    jobs = search_jobs(company=query, location=location, pages=pages)
    if not jobs:
        jobs = search_jobs(keyword=query, location=location, pages=pages)

    print(f"\n📊 Found {len(jobs)} jobs")
    for job in jobs[:10]:
        print(f"\n  {job.title} @ {job.company}")
        print(f"    📍 {job.location}")
        if job.salary_min or job.salary_max:
            print(f"    💰 {job.salary_currency} {job.salary_min}-{job.salary_max}")
        print(f"    🔗 {job.url}")
