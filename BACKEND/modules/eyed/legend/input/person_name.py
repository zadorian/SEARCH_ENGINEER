"""
Legend #7: person_name input model for EYE-D.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PersonNameInput:
    """
    Legend #7: person_name
    Drives person enrichment, linked identifiers, and corporate role discovery.
    """

    full_name: str
    location_hint: Optional[str] = None
    employer_hint: Optional[str] = None
    include_social: bool = True
    include_corporate_roles: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.full_name and len(self.full_name.split()) >= 2)

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 7,
            "full_name": self.full_name,
            "location_hint": self.location_hint,
            "employer_hint": self.employer_hint,
            "include_social": self.include_social,
            "include_corporate_roles": self.include_corporate_roles,
            "tags": self.tags,
        }
