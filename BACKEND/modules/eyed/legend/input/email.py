"""
Legend #1: email input model for EYE-D.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class EmailInput:
    """
    Legend #1: email
    Drives breach discovery, person enrichment, and linked domain intelligence.
    """

    email: str
    check_breaches: bool = True
    enrich_person: bool = True
    analyze_domain: bool = True
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        if not self.email or "@" not in self.email:
            return False
        local, _, domain = self.email.partition("@")
        return bool(local.strip() and "." in domain)

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 1,
            "email": self.email,
            "check_breaches": self.check_breaches,
            "enrich_person": self.enrich_person,
            "analyze_domain": self.analyze_domain,
            "tags": self.tags,
        }
