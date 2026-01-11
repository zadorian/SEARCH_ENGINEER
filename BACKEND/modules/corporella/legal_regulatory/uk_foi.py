"""WhatDoTheyKnow (UK FOI) specialist engine."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys


logger = logging.getLogger(__name__)


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[5]
COMPANY_ENGINES_ROOT = PROJECT_ROOT / "iv. LOCATION" / "COMPANY_ENGINES" / "NATIONAL" / "UK"

if str(COMPANY_ENGINES_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPANY_ENGINES_ROOT))

try:
    from whatdotheyknow_api import WhatDoTheyKnowAPI
except Exception as exc:  # pragma: no cover - optional during tests
    logger.warning("WhatDoTheyKnow API import failed: %s", exc)
    WhatDoTheyKnowAPI = None  # type: ignore


class UKFOIEngine:
    """Search UK FOI requests via WhatDoTheyKnow."""

    code = "UKFOI"
    name = "uk_foi"

    def __init__(self) -> None:
        if WhatDoTheyKnowAPI is None:
            raise RuntimeError("WhatDoTheyKnowAPI unavailable")
        self.client = WhatDoTheyKnowAPI()

    def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        authority: Optional[str] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        data = self.client.search_requests(
            query=query or None,
            authority=authority,
            status=status,
            tag=tag,
            start_date=start_date,
            end_date=end_date,
            format="json",
        )

        items: List[Dict[str, Any]]
        if isinstance(data, dict):
            items = data.get("results") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        results: List[Dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue

            url = self._extract_url(raw)
            if not url:
                continue

            title = raw.get("title") or raw.get("url_title") or "FOI Request"
            snippet = self._build_snippet(raw)
            date_str = (raw.get("created_at") or raw.get("display_date") or "")

            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": "WhatDoTheyKnow",
                    "engine": self.name,
                    "engine_code": self.code,
                    "metadata": {
                        "status": raw.get("described_state") or raw.get("status"),
                        "authority": self._extract_authority(raw),
                        "user": self._extract_user(raw),
                        "created_at": date_str,
                    },
                }
            )

            if len(results) >= max_results:
                break

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_url(self, item: Dict[str, Any]) -> Optional[str]:
        if item.get("url"):
            return item["url"]
        if item.get("url_title"):
            slug = item["url_title"]
            if slug.startswith("http"):
                return slug
            return f"https://www.whatdotheyknow.com/request/{slug}"
        return None

    def _extract_authority(self, item: Dict[str, Any]) -> str:
        public_body = item.get("public_body")
        if isinstance(public_body, dict):
            return public_body.get("name", "")
        return item.get("public_body_name", "")

    def _extract_user(self, item: Dict[str, Any]) -> str:
        user = item.get("user")
        if isinstance(user, dict):
            return user.get("name", "")
        return item.get("user_name", "")

    def _build_snippet(self, item: Dict[str, Any]) -> str:
        parts: List[str] = []

        status = item.get("described_state") or item.get("status")
        if status:
            parts.append(f"Status: {status}")

        authority = self._extract_authority(item)
        if authority:
            parts.append(f"Authority: {authority}")

        date_str = item.get("created_at") or item.get("display_date")
        if date_str:
            parts.append(f"Date: {date_str[:10]}")

        description = item.get("description") or item.get("notes")
        if description:
            parts.append(description[:200])

        return " | ".join(parts)


def main(query: str) -> List[Dict[str, Any]]:
    engine = UKFOIEngine()
    return engine.search(query)


