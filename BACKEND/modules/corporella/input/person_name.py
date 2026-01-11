"""
Corporella Input: person_name
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class PersonNameInput:
    """
    Input: person_name
    Drives officer checks, beneficial ownership searches, and PEP screening.
    """
    full_name: str
    company_association: Optional[str] = None
    jurisdiction_hint: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.full_name and len(self.full_name.strip().split()) >= 2)

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 7,
            "full_name": self.full_name,
            "company_association": self.company_association,
            "jurisdiction_hint": self.jurisdiction_hint,
            "tags": self.tags,
        }
