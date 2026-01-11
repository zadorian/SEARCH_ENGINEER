"""
Binary cascade - escalate disambiguation with progressively specific queries.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BinaryCascade:
    """Generate wedge queries with increasing specificity."""
    discriminators: List[str] = field(default_factory=lambda: [
        "middle name",
        "date of birth",
        "spouse name",
        "professional license number",
    ])

    def generate_queries(self, entity_name: str, location: Optional[str] = None) -> List[str]:
        """Build a cascade of disambiguation queries."""
        base = f"\"{entity_name}\""
        if location:
            base = f"{base} \"{location}\""
        return [f"{base} {disc}" for disc in self.discriminators]
