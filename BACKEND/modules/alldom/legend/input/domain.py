"""
Legend #6: domain input model for ALLDOM.

Entity code: 6 (domain)
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse
import re


DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}\.[a-zA-Z]{2,}$")


@dataclass
class DomainInput:
    """
    Legend #6: domain
    Routes to WHOIS, DNS, backlinks, SSL, archives, and link analysis.
    This is ALLDOM's primary input type.
    """

    domain_or_url: str
    whois_lookup: bool = True
    whois_history: bool = False
    reverse_whois: bool = False
    resolve_dns: bool = True
    include_backlinks: bool = False
    include_outlinks: bool = False
    include_wayback: bool = False
    include_ssl: bool = False
    extract_entities: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def _extract_domain(self) -> str:
        """Extract clean domain from URL or email."""
        value = self.domain_or_url.strip().lower()

        # Handle email inputs (strip domain part)
        if "@" in value and not value.startswith("http"):
            parts = value.split("@")
            if len(parts) == 2:
                return parts[1].strip()

        # Handle full URLs
        parsed = urlparse(value)
        if parsed.scheme:
            return parsed.netloc

        # Remove www. prefix
        if value.startswith("www."):
            value = value[4:]

        return value

    def validate(self) -> bool:
        domain = self._extract_domain()
        return bool(domain and DOMAIN_RE.match(domain))

    def get_tld(self) -> str:
        """Extract TLD from domain."""
        domain = self._extract_domain()
        parts = domain.split(".")
        if len(parts) >= 2:
            return parts[-1]
        return ""

    def get_root_domain(self) -> str:
        """Get root domain (e.g., example.com from sub.example.com)."""
        domain = self._extract_domain()
        parts = domain.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return domain

    def to_dict(self) -> Dict[str, object]:
        domain = self._extract_domain()
        return {
            "legend": 6,
            "input_type": "domain",
            "domain": domain,
            "original": self.domain_or_url,
            "root_domain": self.get_root_domain(),
            "tld": self.get_tld(),
            "whois_lookup": self.whois_lookup,
            "whois_history": self.whois_history,
            "reverse_whois": self.reverse_whois,
            "resolve_dns": self.resolve_dns,
            "include_backlinks": self.include_backlinks,
            "include_outlinks": self.include_outlinks,
            "include_wayback": self.include_wayback,
            "include_ssl": self.include_ssl,
            "extract_entities": self.extract_entities,
            "tags": self.tags,
        }


# Backward compatibility alias
DomainUrlInput = DomainInput
