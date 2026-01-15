#!/usr/bin/env python3
"""
TOMBA - Email Finder & Domain Search API.

Find email addresses associated with domains and verify email deliverability.
Similar to Hunter.io but with different coverage.

Usage:
    from socialite.platforms.tomba import (
        search_domain,
        find_email,
        verify_email,
        get_domain_status,
        TombaDomainResult,
        TombaEmail,
    )

    # Find all emails for a domain
    result = search_domain("stripe.com")
    for email in result.emails:
        print(f"{email.email} - {email.first_name} {email.last_name}")

    # Find specific person's email
    email = find_email("stripe.com", first_name="Patrick", last_name="Collison")

    # Verify an email
    status = verify_email("patrick@stripe.com")
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

TOMBA_API_KEY = os.getenv("TOMBA_API_KEY", "")
TOMBA_SECRET = os.getenv("TOMBA_SECRET", "")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TombaEmail:
    """Individual email result from Tomba."""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    position: str = ""
    department: str = ""
    linkedin: str = ""
    twitter: str = ""
    phone_number: str = ""
    confidence: int = 0
    type: str = ""  # generic, personal
    sources: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "TombaEmail":
        return cls(
            email=data.get("email", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            full_name=data.get("full_name", ""),
            position=data.get("position", ""),
            department=data.get("department", ""),
            linkedin=data.get("linkedin", ""),
            twitter=data.get("twitter", ""),
            phone_number=data.get("phone_number", ""),
            confidence=int(data.get("confidence", 0) or 0),
            type=data.get("type", ""),
            sources=data.get("sources", []),
            raw=data,
        )


@dataclass
class TombaOrganization:
    """Organization data from Tomba."""
    name: str = ""
    domain: str = ""
    website_url: str = ""
    description: str = ""
    industry: str = ""
    founded: str = ""
    location: str = ""
    country: str = ""
    employees_count: int = 0
    social_links: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "TombaOrganization":
        return cls(
            name=data.get("organization", "") or data.get("name", ""),
            domain=data.get("domain", ""),
            website_url=data.get("website_url", ""),
            description=data.get("description", ""),
            industry=data.get("industry", ""),
            founded=data.get("founded", ""),
            location=data.get("location", {}).get("city", "") if isinstance(data.get("location"), dict) else "",
            country=data.get("country", ""),
            employees_count=int(data.get("employees_count", 0) or 0),
            social_links=data.get("social_links", {}),
            raw=data,
        )


@dataclass
class TombaDomainResult:
    """Domain search result from Tomba."""
    data_captured_at: str = ""
    domain: str = ""
    organization: Optional[TombaOrganization] = None
    emails: List[TombaEmail] = field(default_factory=list)
    total_emails: int = 0
    email_pattern: str = ""
    webmail: bool = False
    disposable: bool = False
    accept_all: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_captured_at": self.data_captured_at,
            "domain": self.domain,
            "organization": self.organization.name if self.organization else "",
            "total_emails": self.total_emails,
            "email_pattern": self.email_pattern,
            "emails": [e.email for e in self.emails],
        }


@dataclass
class TombaVerification:
    """Email verification result."""
    data_captured_at: str = ""
    email: str = ""
    status: str = ""  # valid, invalid, accept_all, webmail, disposable, unknown
    deliverable: bool = False
    score: int = 0
    mx_records: bool = False
    smtp_check: bool = False
    free: bool = False
    role: bool = False
    disposable: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "TombaVerification":
        email_data = data.get("data", {}).get("email", {})
        return cls(
            data_captured_at=datetime.utcnow().isoformat(),
            email=email_data.get("email", ""),
            status=email_data.get("status", ""),
            deliverable=email_data.get("result") == "deliverable",
            score=int(email_data.get("score", 0) or 0),
            mx_records=email_data.get("mx_records", False),
            smtp_check=email_data.get("smtp_check", False),
            free=email_data.get("free", False),
            role=email_data.get("role", False),
            disposable=email_data.get("disposable", False),
            raw=data,
        )


# =============================================================================
# CLIENT
# =============================================================================

_client = None


def _get_client():
    """Get Tomba client."""
    global _client
    if _client is None:
        if not TOMBA_API_KEY or not TOMBA_SECRET:
            raise ValueError(
                "TOMBA_API_KEY and TOMBA_SECRET environment variables required"
            )
        try:
            from tomba.client import Client
            _client = Client()
            _client.set_key(TOMBA_API_KEY).set_secret(TOMBA_SECRET)
        except ImportError:
            raise ImportError("tomba not installed. Run: pip install tomba")
    return _client


def is_available() -> bool:
    """Check if Tomba is configured."""
    return bool(TOMBA_API_KEY and TOMBA_SECRET)


# =============================================================================
# API FUNCTIONS
# =============================================================================

def search_domain(
    domain: str,
    page: int = 1,
    limit: int = 10,
    department: Optional[str] = None,
) -> Optional[TombaDomainResult]:
    """
    Search for emails associated with a domain.

    Args:
        domain: Domain to search (e.g., "stripe.com")
        page: Page number for pagination
        limit: Results per page (max 100)
        department: Filter by department (executive, finance, hr, it, marketing, sales, etc.)

    Returns:
        TombaDomainResult with organization info and emails

    Example:
        result = search_domain("stripe.com")
        print(f"Found {result.total_emails} emails")
        for email in result.emails:
            print(f"  {email.email} - {email.position}")
    """
    try:
        from tomba.services.domain import Domain

        client = _get_client()
        domain_service = Domain(client)

        response = domain_service.domain_search(domain, page=page, limit=limit)

        if not response or "data" not in response:
            return None

        data = response["data"]

        # Parse organization
        org_data = data.get("organization", {})
        organization = TombaOrganization.from_api(org_data) if org_data else None

        # Parse emails
        emails = [TombaEmail.from_api(e) for e in data.get("emails", [])]

        return TombaDomainResult(
            data_captured_at=datetime.utcnow().isoformat(),
            domain=domain,
            organization=organization,
            emails=emails,
            total_emails=data.get("total", len(emails)),
            email_pattern=data.get("pattern", ""),
            webmail=data.get("webmail", False),
            disposable=data.get("disposable", False),
            accept_all=data.get("accept_all", False),
            raw=response,
        )
    except Exception as e:
        logger.error(f"Tomba domain search failed: {e}")
        return None


def find_email(
    domain: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    full_name: Optional[str] = None,
) -> Optional[TombaEmail]:
    """
    Find a specific person's email at a domain.

    Args:
        domain: Company domain
        first_name: Person's first name
        last_name: Person's last name
        full_name: Full name (alternative to first/last)

    Returns:
        TombaEmail or None

    Example:
        email = find_email("stripe.com", first_name="Patrick", last_name="Collison")
        if email:
            print(f"Found: {email.email} (confidence: {email.confidence}%)")
    """
    try:
        from tomba.services.finder import Finder

        client = _get_client()
        finder = Finder(client)

        response = finder.email_finder(
            domain,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
        )

        if not response or "data" not in response:
            return None

        data = response["data"]
        email_data = data.get("email", {})

        if not email_data:
            return None

        result = TombaEmail.from_api(email_data)
        result.raw["data_captured_at"] = datetime.utcnow().isoformat()
        return result

    except Exception as e:
        logger.error(f"Tomba email finder failed: {e}")
        return None


def verify_email(email: str) -> Optional[TombaVerification]:
    """
    Verify if an email address is deliverable.

    Args:
        email: Email address to verify

    Returns:
        TombaVerification with status and deliverability

    Example:
        result = verify_email("patrick@stripe.com")
        if result.deliverable:
            print(f"Valid email with score {result.score}")
    """
    try:
        from tomba.services.verifier import Verifier

        client = _get_client()
        verifier = Verifier(client)

        response = verifier.email_verifier(email)

        if not response:
            return None

        return TombaVerification.from_api(response)

    except Exception as e:
        logger.error(f"Tomba email verification failed: {e}")
        return None


def get_domain_status(domain: str) -> Optional[Dict[str, Any]]:
    """
    Get domain status (webmail, disposable, pattern).

    Args:
        domain: Domain to check

    Returns:
        Dict with domain metadata

    Example:
        status = get_domain_status("stripe.com")
        print(f"Pattern: {status['pattern']}")
        print(f"Accept all: {status['accept_all']}")
    """
    try:
        from tomba.services.status import Status

        client = _get_client()
        status_service = Status(client)

        response = status_service.domain_status(domain)

        if not response or "data" not in response:
            return None

        data = response["data"]
        return {
            "data_captured_at": datetime.utcnow().isoformat(),
            "domain": domain,
            "webmail": data.get("webmail", False),
            "disposable": data.get("disposable", False),
            "accept_all": data.get("accept_all", False),
            "pattern": data.get("pattern", ""),
            "organization": data.get("organization", ""),
            "country": data.get("country", ""),
        }

    except Exception as e:
        logger.error(f"Tomba domain status failed: {e}")
        return None


def count_emails(domain: str) -> int:
    """
    Get count of emails available for a domain.

    Args:
        domain: Domain to check

    Returns:
        Number of emails available
    """
    try:
        from tomba.services.count import Count

        client = _get_client()
        count_service = Count(client)

        response = count_service.email_count(domain)

        if response and "data" in response:
            return response["data"].get("total", 0)
        return 0

    except Exception as e:
        logger.error(f"Tomba email count failed: {e}")
        return 0


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "TombaEmail",
    "TombaOrganization",
    "TombaDomainResult",
    "TombaVerification",
    # Functions
    "search_domain",
    "find_email",
    "verify_email",
    "get_domain_status",
    "count_emails",
    "is_available",
]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tomba.py <domain>")
        print("       python tomba.py <domain> <first_name> <last_name>")
        print("       python tomba.py verify <email>")
        print("\nExamples:")
        print("  python tomba.py stripe.com")
        print("  python tomba.py stripe.com Patrick Collison")
        print("  python tomba.py verify patrick@stripe.com")
        sys.exit(1)

    if sys.argv[1] == "verify" and len(sys.argv) > 2:
        email = sys.argv[2]
        print(f"🔍 Verifying {email}")
        result = verify_email(email)
        if result:
            print(f"   Status: {result.status}")
            print(f"   Deliverable: {result.deliverable}")
            print(f"   Score: {result.score}")
        else:
            print("   ❌ Verification failed")
    elif len(sys.argv) >= 4:
        domain, first, last = sys.argv[1], sys.argv[2], sys.argv[3]
        print(f"🔍 Finding email for {first} {last} at {domain}")
        result = find_email(domain, first_name=first, last_name=last)
        if result:
            print(f"   Email: {result.email}")
            print(f"   Confidence: {result.confidence}%")
            print(f"   Position: {result.position}")
        else:
            print("   ❌ Email not found")
    else:
        domain = sys.argv[1]
        print(f"🔍 Searching {domain}")
        result = search_domain(domain)
        if result:
            print(f"\n📧 {result.organization.name if result.organization else domain}")
            print(f"   Total emails: {result.total_emails}")
            print(f"   Pattern: {result.email_pattern}")
            print(f"\n   Emails found:")
            for e in result.emails[:10]:
                print(f"   • {e.email} - {e.full_name or 'N/A'} ({e.position or 'N/A'})")
        else:
            print("   ❌ Search failed")
