"""Native Crossref engine (parity with legacy runner)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

try:  # Optional dependency used across the project for pooled sessions
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - shared_session is optional
    get_shared_session = None  # type: ignore


LOGGER = logging.getLogger("crossref_academic_engine")


@dataclass
class CrossrefConfig:
    base_url: str = "https://api.crossref.org/works"
    max_results_per_page: int = 1000  # Crossref API maximum
    max_pages: int = 5
    timeout: int = 20
    pause_seconds: float = 0.2
    retries: int = 3
    email: Optional[str] = None


class CrossrefEngine:
    """Specialist Crossref engine powering academic targeted searches."""

    code = "CR"
    name = "crossref"

    def __init__(self, config: Optional[CrossrefConfig] = None) -> None:
        self.config = config or CrossrefConfig()
        self.email = (
            self.config.email
            or os.getenv("USER_EMAIL")
            or os.getenv("ACADEMIC_EMAIL")
            or "search@example.com"
        )

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="CROSSREF")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": f"SearchEngineer-Crossref/1.0 (mailto:{self.email})",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        polite_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search Crossref for the given query (exact phrase friendly)."""

        email = polite_email or self.email
        seen: Dict[str, Dict[str, Any]] = {}
        cursor = "*"

        for page in range(1, self.config.max_pages + 1):
            if len(seen) >= max_results:
                break

            items, cursor = self._fetch_page(query, cursor, email)
            if not items:
                break

            for work in items:
                url = self._work_url(work)
                if not url or url in seen:
                    continue

                parsed = self._format_work(work, query)
                parsed.setdefault("engine", self.name)
                parsed.setdefault("engine_code", self.code)
                parsed.setdefault("source", "crossref")
                parsed.setdefault("engine_badge", self.code)
                seen[url] = parsed

                if len(seen) >= max_results:
                    break

            if not cursor:
                break

            time.sleep(self.config.pause_seconds)

        return list(seen.values())[:max_results]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_page(
        self, query: str, cursor: Optional[str], email: str
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        params = {
            "query": f'"{query}"',
            "rows": min(self.config.max_results_per_page, 1000),
            "mailto": email,
        }

        if cursor and cursor != "*":
            params["cursor"] = cursor
        elif cursor == "*":
            params["cursor"] = cursor

        url = f"{self.config.base_url}?{urlencode(params)}"

        attempt = 0
        while attempt < self.config.retries:
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                response.raise_for_status()
                data = response.json()
                message = data.get("message", {})
                items = message.get("items", []) or []
                next_cursor = message.get("next-cursor")
                return items, next_cursor
            except requests.RequestException as exc:  # pragma: no cover - network guard
                attempt += 1
                LOGGER.warning("Crossref request failed (%s/%s): %s", attempt, self.config.retries, exc)
                time.sleep(self.config.pause_seconds * (attempt + 1))
            except ValueError as exc:  # JSON decode errors
                LOGGER.warning("Crossref response decode error: %s", exc)
                break

        return [], None

    def _work_url(self, work: Dict[str, Any]) -> str:
        doi = work.get("DOI")
        if doi:
            return f"https://doi.org/{doi}"
        link = work.get("URL")
        if link:
            return link
        return ""

    def _format_work(self, work: Dict[str, Any], phrase: str) -> Dict[str, Any]:
        url = self._work_url(work)
        title = self._build_title(work)
        snippet = self._extract_snippet(work, phrase)
        score = work.get("score")

        metadata = {
            "doi": work.get("DOI"),
            "type": work.get("type"),
            "publisher": work.get("publisher"),
            "subjects": work.get("subject") or [],
            "issued": work.get("issued"),
            "container": work.get("container-title"),
        }

        return {
            "url": url,
            "title": title,
            "snippet": snippet,
            "score": score,
            "metadata": metadata,
        }

    def _build_title(self, work: Dict[str, Any]) -> str:
        titles = work.get("title") or []
        title = titles[0] if titles else "Untitled"

        authors = work.get("author") or []
        author_names: List[str] = []
        for author in authors[:3]:
            given = author.get("given", "")
            family = author.get("family", "")
            if given and family:
                author_names.append(f"{given} {family}")
            elif family:
                author_names.append(family)

        if len(authors) > 3:
            author_names.append("et al.")

        published = work.get("published-print") or work.get("published-online")
        year = ""
        if isinstance(published, dict):
            parts = published.get("date-parts")
            if parts and parts[0]:
                year = str(parts[0][0])

        container = ""
        containers = work.get("container-title") or []
        if containers:
            container = containers[0]

        title_parts = [title]
        if author_names:
            title_parts.append(f"by {', '.join(author_names)}")
        if container:
            title_parts.append(f"in {container}")
        if year:
            title_parts.append(f"({year})")

        return " ".join(title_parts)

    def _extract_snippet(self, work: Dict[str, Any], phrase: str) -> str:
        abstract = work.get("abstract")
        if isinstance(abstract, str):
            cleaned = (
                abstract.replace("<jats:p>", "")
                .replace("</jats:p>", "")
                .replace("<p>", "")
                .replace("</p>", "")
            )
            lowered = cleaned.lower()
            target = phrase.lower().strip()
            if target and target in lowered:
                pos = lowered.find(target)
                start = max(0, pos - 120)
                end = min(len(cleaned), pos + len(target) + 120)
                snippet = cleaned[start:end]
                if start > 0:
                    snippet = "…" + snippet
                if end < len(cleaned):
                    snippet = snippet + "…"
                return snippet

            if len(cleaned) > 240:
                return cleaned[:240] + "…"
            return cleaned

        title = " ".join(work.get("title") or [])
        subtitle = " ".join(work.get("subtitle") or [])
        snippet = title
        if subtitle:
            snippet = f"{title}. {subtitle}"

        subjects = work.get("subject") or []
        if subjects:
            snippet += f" | Subjects: {', '.join(subjects[:3])}"

        return snippet


__all__ = ["CrossrefEngine", "CrossrefConfig"]

