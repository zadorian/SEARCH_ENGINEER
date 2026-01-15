"""Native OpenAlex engine (parity with legacy runner)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

try:  # Optional pooled session helper
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    get_shared_session = None  # type: ignore


LOGGER = logging.getLogger("openalex_academic_engine")


@dataclass
class OpenAlexConfig:
    base_url: str = "https://api.openalex.org/works"
    max_results_per_page: int = 100
    max_pages: int = 10
    timeout: int = 20
    pause_seconds: float = 0.1
    email: Optional[str] = None


class OpenAlexEngine:
    code = "OA"
    name = "openalex"

    def __init__(self, config: Optional[OpenAlexConfig] = None) -> None:
        self.config = config or OpenAlexConfig()
        self.email = (
            self.config.email
            or os.getenv("USER_EMAIL")
            or os.getenv("ACADEMIC_EMAIL")
            or "search@example.com"
        )

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="OPENALEX")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": f"SearchEngineer-OpenAlex/1.0 (mailto:{self.email})",
                "Accept": "application/json",
            }
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        polite_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        email = polite_email or self.email
        seen: Dict[str, Dict[str, Any]] = {}

        for page in range(1, self.config.max_pages + 1):
            if len(seen) >= max_results:
                break

            url = self._build_url(query, page, email)
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network guard
                LOGGER.warning("OpenAlex request failed on page %s: %s", page, exc)
                break

            payload = response.json()
            results = payload.get("results") or []
            if not results:
                break

            for record in results:
                url_key = self._record_url(record)
                if not url_key or url_key in seen:
                    continue

                parsed = self._format_record(record, query)
                parsed.setdefault("engine", self.name)
                parsed.setdefault("engine_code", self.code)
                parsed.setdefault("engine_badge", self.code)
                parsed.setdefault("source", "openalex")
                seen[url_key] = parsed

                if len(seen) >= max_results:
                    break

            meta = payload.get("meta", {})
            total = meta.get("count", 0)
            if page * self.config.max_results_per_page >= total:
                break

            time.sleep(self.config.pause_seconds)

        ordered = sorted(seen.values(), key=lambda item: item.get("score", 0), reverse=True)
        return ordered[:max_results]

    def _build_url(self, query: str, page: int, email: str) -> str:
        params = {
            "search": f'"{query}"',
            "page": page,
            "per-page": min(self.config.max_results_per_page, 200),
            "mailto": email,
        }
        query_string = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
        return f"{self.config.base_url}?{query_string}"

    def _record_url(self, work: Dict[str, Any]) -> str:
        doi = work.get("doi")
        if doi:
            return doi
        identifier = work.get("id")
        if identifier:
            return identifier
        return ""

    def _format_record(self, work: Dict[str, Any], phrase: str) -> Dict[str, Any]:
        url = self._record_url(work)
        title = work.get("display_name") or "Untitled"

        venue = work.get("primary_location", {}).get("source", {}).get("display_name", "")
        year = work.get("publication_year")
        if venue and year:
            title = f"{title} ({venue}, {year})"
        elif year:
            title = f"{title} ({year})"

        snippet = self._build_snippet(work, phrase)
        score = work.get("relevance_score")

        metadata = {
            "type": work.get("type"),
            "open_access": work.get("open_access"),
            "authorships": work.get("authorships"),
            "primary_topic": work.get("primary_topic"),
        }

        return {
            "url": url,
            "title": title,
            "snippet": snippet,
            "score": score,
            "metadata": metadata,
        }

    def _build_snippet(self, work: Dict[str, Any], phrase: str) -> str:
        abstract = work.get("abstract")
        if isinstance(abstract, str):
            lowered = abstract.lower()
            phrase_lower = phrase.lower()
            if phrase_lower and phrase_lower in lowered:
                pos = lowered.find(phrase_lower)
                start = max(0, pos - 120)
                end = min(len(abstract), pos + len(phrase_lower) + 120)
                snippet = abstract[start:end]
                if start > 0:
                    snippet = "…" + snippet
                if end < len(abstract):
                    snippet += "…"
                return snippet
            if len(abstract) > 240:
                return abstract[:240] + "…"
            return abstract

        tl_dr = work.get("tldr") or {}
        if isinstance(tl_dr, dict):
            shortened = tl_dr.get("text")
            if shortened:
                return shortened

        return work.get("display_name") or "OpenAlex result"


__all__ = ["OpenAlexEngine", "OpenAlexConfig"]

