"""
Legend #2: phone input model for ALLDOM.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import re


PHONE_RE = re.compile(r"^\+?[0-9\-\s().]{7,}$")


@dataclass
class PhoneInput:
    """
    Legend #2: phone
    Routes to reverse lookups, entity enrichment, and regional analysis.
    """

    phone_number: str
    normalize: bool = True
    region_hint: Optional[str] = None
    reverse_lookup: bool = True
    extract_entities: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.phone_number and PHONE_RE.match(self.phone_number))

    def sanitized(self) -> str:
        """Return normalized phone number."""
        digits = re.sub(r"\D+", "", self.phone_number)
        if self.normalize and digits and not self.phone_number.startswith("+"):
            return f"+{digits}"
        return self.phone_number

    def detect_region(self) -> Optional[str]:
        """Attempt to detect region from country code."""
        digits = re.sub(r"\D+", "", self.phone_number)
        if digits.startswith("1"):
            return "US"
        elif digits.startswith("44"):
            return "UK"
        elif digits.startswith("49"):
            return "DE"
        elif digits.startswith("33"):
            return "FR"
        elif digits.startswith("39"):
            return "IT"
        elif digits.startswith("34"):
            return "ES"
        elif digits.startswith("36"):
            return "HU"
        return self.region_hint

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 2,
            "input_type": "phone",
            "phone_number": self.phone_number,
            "normalized": self.sanitized(),
            "region": self.detect_region(),
            "reverse_lookup": self.reverse_lookup,
            "extract_entities": self.extract_entities,
            "tags": self.tags,
        }
