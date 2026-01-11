"""
Corporella Input: company_reg_id
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class CompanyIDInput:
    """
    Input: company_reg_id
    Drives precise corporate registry lookups and filings retrieval.
    """
    company_id: str
    jurisdiction_code: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.company_id and len(self.company_id.strip()) > 0)

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 14,
            "company_id": self.company_id,
            "jurisdiction_code": self.jurisdiction_code,
            "tags": self.tags,
        }
