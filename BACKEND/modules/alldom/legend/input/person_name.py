"""
Legend #7: person_name input model for ALLDOM.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class PersonNameInput:
    """
    Legend #7: person_name
    Routes to corporate registries, reverse WHOIS, sanctions checks, and entity enrichment.
    """

    full_name: str
    location_hint: Optional[str] = None
    employer_hint: Optional[str] = None
    jurisdiction: Optional[str] = None
    include_corporate_roles: bool = True
    include_sanctions: bool = True
    reverse_whois: bool = False
    extract_entities: bool = False
    tags: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        return bool(self.full_name and len(self.full_name.split()) >= 2)

    def name_parts(self) -> Dict[str, str]:
        """Split name into components."""
        parts = self.full_name.strip().split()
        if len(parts) >= 3:
            return {
                "first_name": parts[0],
                "middle_name": " ".join(parts[1:-1]),
                "last_name": parts[-1],
            }
        elif len(parts) == 2:
            return {
                "first_name": parts[0],
                "middle_name": "",
                "last_name": parts[1],
            }
        return {"first_name": self.full_name, "middle_name": "", "last_name": ""}

    def name_variations(self) -> List[str]:
        """Generate common name variations for search."""
        parts = self.name_parts()
        variations = [self.full_name]
        
        if parts["last_name"]:
            variations.append(f"{parts['last_name']}, {parts['first_name']}")
        if parts["middle_name"]:
            # First + Middle Initial + Last
            middle_init = parts["middle_name"][0]
            variations.append(f"{parts['first_name']} {middle_init}. {parts['last_name']}")
        
        return list(set(variations))

    def to_dict(self) -> Dict[str, object]:
        return {
            "legend": 7,
            "input_type": "person_name",
            "full_name": self.full_name,
            "name_parts": self.name_parts(),
            "variations": self.name_variations(),
            "location_hint": self.location_hint,
            "employer_hint": self.employer_hint,
            "jurisdiction": self.jurisdiction,
            "include_corporate_roles": self.include_corporate_roles,
            "include_sanctions": self.include_sanctions,
            "reverse_whois": self.reverse_whois,
            "extract_entities": self.extract_entities,
            "tags": self.tags,
        }
