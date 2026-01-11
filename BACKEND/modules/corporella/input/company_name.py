"""
Corporella Input: company_name
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class CompanyNameInput:
    """
    Input: company_name
    Drives corporate registry lookups, news searches, and regulatory checks.
    """
    company_name: str
    jurisdiction_code: Optional[str] = None
    registration_number: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.company_name and len(self.company_name.strip()) > 1)

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 13,
            "company_name": self.company_name,
            "jurisdiction_code": self.jurisdiction_code,
            "registration_number": self.registration_number,
            "tags": self.tags,
        }
