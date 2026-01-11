"""
Legend #1: email input model for ALLDOM.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class EmailInput:
    """
    Legend #1: email
    Routes to reverse WHOIS, domain analysis, and entity enrichment.
    """

    email: str
    reverse_whois: bool = True
    analyze_domain: bool = True
    extract_entities: bool = False
    jurisdiction: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        if not self.email or "@" not in self.email:
            return False
        local, _, domain = self.email.partition("@")
        return bool(local.strip() and "." in domain)

    def extract_domain(self) -> str:
        """Extract domain part from email."""
        if "@" in self.email:
            return self.email.split("@")[1].strip().lower()
        return ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 1,
            "input_type": "email",
            "email": self.email,
            "domain": self.extract_domain(),
            "reverse_whois": self.reverse_whois,
            "analyze_domain": self.analyze_domain,
            "extract_entities": self.extract_entities,
            "jurisdiction": self.jurisdiction,
            "tags": self.tags,
        }
