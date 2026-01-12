from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .classifiers import classify_content, classify_url, scan_content
from .entity_extractors import extract_companies, extract_fast, extract_persons


@dataclass
class FullExtractResult:
    tier: str
    entities: Dict[str, Any]
    persons: List[Dict[str, Any]]
    companies: List[Dict[str, Any]]
    red_flags: List[Dict[str, Any]]


class Pacman:
    """Legacy-friendly facade over PACMAN's extraction + classification utilities."""

    def extract_entities(self, content: str) -> Dict[str, Any]:
        return extract_fast(content)

    def extract_persons(self, content: str, max_results: int = 30) -> List[Dict[str, Any]]:
        return extract_persons(content, max_results)

    def extract_companies(self, content: str, max_results: int = 30) -> List[Dict[str, Any]]:
        return extract_companies(content, max_results)

    def classify_url(self, url: str) -> str:
        result = classify_url(url)
        tier = getattr(result, "tier", result)
        return getattr(tier, "value", str(tier))

    def scan_red_flags(self, content: str) -> List[Dict[str, Any]]:
        hits = scan_content(content)
        return [
            {
                "pattern": h.pattern,
                "category": h.category.value,
                "context": h.context,
            }
            for h in hits
        ]

    def full_extract(self, content: str, url: str = "", max_results: int = 30) -> FullExtractResult:
        tier_result = classify_content(content, url)
        tier = getattr(getattr(tier_result, "tier", tier_result), "value", str(getattr(tier_result, "tier", tier_result)))

        return FullExtractResult(
            tier=tier,
            entities=extract_fast(content),
            persons=extract_persons(content, max_results),
            companies=extract_companies(content, max_results),
            red_flags=self.scan_red_flags(content),
        )


def extract(content: str) -> Dict[str, Any]:
    return extract_fast(content)


def red_flags(content: str) -> List[Dict[str, Any]]:
    return Pacman().scan_red_flags(content)

