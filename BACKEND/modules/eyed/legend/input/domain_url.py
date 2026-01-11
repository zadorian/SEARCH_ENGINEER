"""
Legend #6: domain_url input model for EYE-D.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse
import re


DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}\\.[a-zA-Z]{2,}$")


@dataclass
class DomainUrlInput:
    """
    Legend #6: domain_url
    Used for WHOIS, backlinks, DNS, SSL, and historic timeline analysis.
    """

    domain_or_url: str
    resolve_dns: bool = True
    include_wayback: bool = True
    include_ssl: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def _extract_domain(self) -> str:
        value = self.domain_or_url.strip()
        
        # Handle email inputs (strip domain part)
        if "@" in value and not value.startswith("http"):
            parts = value.split("@")
            if len(parts) == 2:
                return parts[1].strip()

        parsed = urlparse(value)
        if parsed.scheme:
            return parsed.netloc
        return value

    def validate(self) -> bool:
        domain = self._extract_domain()
        return bool(domain and DOMAIN_RE.match(domain))

    def to_dict(self) -> Dict[str, object]:
        domain = self._extract_domain()
        return {
            "legend": 6,
            "domain": domain,
            "original": self.domain_or_url,
            "resolve_dns": self.resolve_dns,
            "include_wayback": self.include_wayback,
            "include_ssl": self.include_ssl,
            "tags": self.tags,
        }
