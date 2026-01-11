"""
Legend #2: phone input model for EYE-D.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import re


PHONE_RE = re.compile(r"^\+?[0-9\\-\\s().]{7,}$")


@dataclass
class PhoneInput:
    """
    Legend #2: phone
    Enables reverse enrichment, DeHashed pivots, and contact discovery.
    """

    phone_number: str
    normalize: bool = True
    region_hint: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.phone_number and PHONE_RE.match(self.phone_number))

    def sanitized(self) -> str:
        digits = re.sub(r"\\D+", "", self.phone_number)
        if self.normalize and digits and not self.phone_number.startswith("+"):
            return f"+{digits}"
        return self.phone_number

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 2,
            "phone_number": self.phone_number,
            "normalized": self.sanitized(),
            "region_hint": self.region_hint,
            "tags": self.tags,
        }
