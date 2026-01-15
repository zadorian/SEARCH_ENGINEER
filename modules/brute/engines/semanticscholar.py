"""Native Semantic Scholar engine (parity with legacy runner)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

try:  # Optional pooled session helper
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    get_shared_session = None  # type: ignore


LOGGER = logging.getLogger("semantic_scholar_academic_engine")


@dataclass
class SemanticScholarConfig:
    base_url: str = "https://api.semanticscholar.org/graph/v1/paper/search"
    max_results_per_page: int = 100
    max_pages: int = 10
    timeout: int = 20
    pause_seconds: float = 0.2
    api_key: Optional[str] = None


class SemanticScholarEngine:
    code = "SE"
    name = "semantic_scholar"

    def __init__(self, config: Optional[SemanticScholarConfig] = None) -> None:
        self.config = config or SemanticScholarConfig()
        api_key = self.config.api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="SEMANTIC_SCHOLAR")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()

        headers = {"User-Agent": "SearchEngineer-SemanticScholar/1.0"}
        if api_key:
            headers["x-api-key"] = api_key
        self.session.headers.update(headers)

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        search_mode: str = "all",
        year_range: Optional[Tuple[int, int]] = None,
        fields_of_study: Optional[Sequence[str]] = None,
        open_access_only: bool = False,
        min_citations: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        offset = 0

        for page in range(self.config.max_pages):
            if len(collected) >= max_results:
                break

            payload = self._search_page(
                query,
                offset=offset,
                search_mode=search_mode,
                year_range=year_range,
                fields_of_study=fields_of_study,
                open_access_only=open_access_only,
                min_citations=min_citations,
            )

            data = payload.get("data") or []
            if not data:
                break

            for paper in data:
                parsed = self._format_paper(paper)
                parsed.setdefault("engine", self.name)
                parsed.setdefault("engine_code", self.code)
                parsed.setdefault("engine_badge", self.code)
                parsed.setdefault("source", "semantic_scholar")
                collected.append(parsed)

                if len(collected) >= max_results:
                    break

            offset += self.config.max_results_per_page

            total = payload.get("total", 0)
            if offset >= total:
                break

            time.sleep(self.config.pause_seconds)

        return collected[:max_results]

    def _search_page(
        self,
        phrase: str,
        *,
        offset: int,
        search_mode: str,
        year_range: Optional[Tuple[int, int]],
        fields_of_study: Optional[Sequence[str]],
        open_access_only: bool,
        min_citations: Optional[int],
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": self._build_query(
                phrase,
                year_range=year_range,
                fields_of_study=fields_of_study,
                open_access_only=open_access_only,
                min_citations=min_citations,
            ),
            "offset": offset,
            "limit": self.config.max_results_per_page,
            "fields": self._response_fields(),
        }

        if search_mode == "title":
            params["queryFields"] = "title"
        elif search_mode == "abstract":
            params["queryFields"] = "abstract"
        elif search_mode == "venue":
            params["queryFields"] = "venue"
        elif search_mode == "author":
            params["queryFields"] = "authors"

        try:
            response = self.session.get(self.config.base_url, params=params, timeout=self.config.timeout)
            if response.status_code == 429:  # rate limit
                LOGGER.warning("Semantic Scholar rate limit reached, sleeping before retry")
                time.sleep(10)
                return {"data": [], "total": 0}
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:  # pragma: no cover - network guard
            LOGGER.warning("Semantic Scholar request failed (offset=%s): %s", offset, exc)
            return {"data": [], "total": 0}

    def _build_query(
        self,
        phrase: str,
        *,
        year_range: Optional[Tuple[int, int]],
        fields_of_study: Optional[Sequence[str]],
        open_access_only: bool,
        min_citations: Optional[int],
    ) -> str:
        query = f'"{phrase}"'
        if year_range:
            query += f" year:{year_range[0]}-{year_range[1]}"
        if fields_of_study:
            for field in fields_of_study:
                query += f' fieldsOfStudy:"{field}"'
        if open_access_only:
            query += " isOpenAccess:true"
        if min_citations:
            query += f" citationCount:>{min_citations}"
        return query

    def _response_fields(self) -> str:
        fields = [
            "paperId",
            "title",
            "abstract",
            "authors",
            "year",
            "venue",
            "citationCount",
            "influentialCitationCount",
            "isOpenAccess",
            "fieldsOfStudy",
            "url",
            "openAccessPdf",
            "publicationTypes",
            "journal",
            "doi",
            "tldr",
        ]
        return ",".join(fields)

    def _format_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        title = paper.get("title") or "Untitled"

        authors = paper.get("authors") or []
        author_names: List[str] = []
        for author in authors[:3]:
            if isinstance(author, dict):
                name = author.get("name")
                if name:
                    author_names.append(name)
        if len(authors) > 3:
            author_names.append("et al.")

        year = paper.get("year")
        title_parts = [title]
        if author_names:
            title_parts.append(f"- {', '.join(author_names)}")
        if year:
            title_parts.append(f"({year})")
        enhanced_title = " ".join(title_parts)

        snippet = self._build_snippet(paper)
        url = paper.get("url") or paper.get("openAccessPdf", {}).get("url") or ""

        metadata = {
            "citations": paper.get("citationCount"),
            "influential_citations": paper.get("influentialCitationCount"),
            "fields_of_study": paper.get("fieldsOfStudy") or [],
            "open_access": paper.get("isOpenAccess"),
            "publication_types": paper.get("publicationTypes"),
            "doi": paper.get("doi"),
        }

        return {
            "url": url,
            "title": enhanced_title,
            "snippet": snippet,
            "metadata": metadata,
        }

    def _build_snippet(self, paper: Dict[str, Any]) -> str:
        parts: List[str] = []

        venue = paper.get("venue")
        journal = paper.get("journal")
        if isinstance(journal, dict) and journal.get("name"):
            parts.append(f"Journal: {journal['name']}")
        elif venue:
            parts.append(f"Venue: {venue}")

        citations = paper.get("citationCount")
        influential = paper.get("influentialCitationCount")
        if citations:
            cite_str = f"{citations:,} citations"
            if influential:
                cite_str += f" ({influential} influential)"
            parts.append(cite_str)

        fields = paper.get("fieldsOfStudy") or []
        if fields:
            parts.append(f"Fields: {', '.join(fields[:3])}")

        tldr = paper.get("tldr")
        if isinstance(tldr, dict) and tldr.get("text"):
            parts.append(tldr["text"])

        abstract = paper.get("abstract")
        if abstract and not parts:
            preview = abstract[:240]
            if len(abstract) > 240:
                preview += "…"
            parts.append(preview)

        return " | ".join(parts) if parts else "Semantic Scholar result"


__all__ = ["SemanticScholarEngine", "SemanticScholarConfig"]

