"""Native PubMed engine (parity with legacy runner)."""

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


LOGGER = logging.getLogger("pubmed_academic_engine")


@dataclass
class PubMedConfig:
    search_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    summary_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    retmode: str = "json"
    database: str = "pmc"
    max_results_per_page: int = 200
    max_pages: int = 10
    timeout: int = 20
    pause_seconds: float = 0.35  # be polite to NCBI (max 3 req/sec)
    email: Optional[str] = None


class PubMedEngine:
    code = "PM"
    name = "pubmed"

    def __init__(self, config: Optional[PubMedConfig] = None) -> None:
        self.config = config or PubMedConfig()
        self.email = (
            self.config.email
            or os.getenv("ACADEMIC_EMAIL")
            or os.getenv("USER_EMAIL")
            or "search@example.com"
        )

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="PUBMED")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()

        self.session.headers.update({"User-Agent": f"SearchEngineer-PubMed/1.0 ({self.email})"})

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        search_mode: str = "all",
        date_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        pmc_ids = self._search_ids(query, search_mode=search_mode, date_range=date_range, limit=max_results)
        if not pmc_ids:
            return []

        summaries = self._fetch_summaries(pmc_ids)
        results: List[Dict[str, Any]] = []
        for summary in summaries:
            parsed = self._format_summary(summary)
            parsed.setdefault("engine", self.name)
            parsed.setdefault("engine_code", self.code)
            parsed.setdefault("engine_badge", self.code)
            parsed.setdefault("source", "pubmed")
            results.append(parsed)

        return results[:max_results]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _search_ids(
        self,
        phrase: str,
        *,
        search_mode: str,
        date_range: Optional[Tuple[int, int]],
        limit: int,
    ) -> List[str]:
        query = self._build_query(phrase, search_mode=search_mode, date_range=date_range)
        params = {
            "db": self.config.database,
            "term": query,
            "retmode": self.config.retmode,
            "retmax": min(limit * 2, self.config.max_results_per_page * self.config.max_pages),
            "email": self.email,
            "usehistory": "y",
        }

        try:
            response = self.session.get(self.config.search_url, params=params, timeout=self.config.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:  # pragma: no cover - network guard
            LOGGER.warning("PubMed search request failed: %s", exc)
            return []

        result = data.get("esearchresult", {})
        id_list = result.get("idlist", [])

        self._webenv = result.get("webenv")
        self._query_key = result.get("querykey")

        return id_list[:limit]

    def _fetch_summaries(self, pmc_ids: Sequence[str]) -> List[Dict[str, Any]]:
        if not pmc_ids:
            return []

        summaries: List[Dict[str, Any]] = []
        batch_size = 200
        ids = list(pmc_ids)

        for start in range(0, len(ids), batch_size):
            batch = ids[start : start + batch_size]
            params = {
                "db": self.config.database,
                "id": ",".join(batch),
                "retmode": self.config.retmode,
                "email": self.email,
            }

            try:
                response = self.session.get(self.config.summary_url, params=params, timeout=self.config.timeout)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as exc:  # pragma: no cover - network guard
                LOGGER.warning("PubMed summary request failed: %s", exc)
                continue

            result = data.get("result", {})
            for pmc_id in batch:
                summary = result.get(pmc_id)
                if summary:
                    summary["_pmc_id"] = pmc_id
                    summaries.append(summary)

            if start + batch_size < len(ids):
                time.sleep(self.config.pause_seconds)

        return summaries

    def _build_query(
        self,
        phrase: str,
        *,
        search_mode: str,
        date_range: Optional[Tuple[int, int]],
    ) -> str:
        quoted = f'"{phrase}"'

        if search_mode == "title":
            query = f"{quoted}[Title]"
        elif search_mode == "abstract":
            query = f"{quoted}[Abstract]"
        elif search_mode == "fulltext":
            query = f"{quoted}[Text Word]"
        elif search_mode == "author":
            query = f"{quoted}[Author]"
        else:
            query = quoted

        if date_range:
            start_year, end_year = date_range
            query += f" AND {start_year}:{end_year}[Publication Date]"

        query += " AND pmc[filter]"
        return query

    def _format_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        title = summary.get("title", "Untitled")
        authors = summary.get("authors") or []
        author_names: List[str] = []
        for author in authors[:3]:
            name = author.get("name")
            if name:
                author_names.append(name)
        if len(authors) > 3:
            author_names.append("et al.")

        pub_date = summary.get("pubdate", "")
        year = pub_date.split()[0] if pub_date else ""

        title_parts = [title]
        if author_names:
            title_parts.append(f"- {', '.join(author_names)}")
        if year:
            title_parts.append(f"({year})")
        enhanced_title = " ".join(title_parts)

        source = summary.get("source", "")
        volume = summary.get("volume", "")
        issue = summary.get("issue", "")
        pages = summary.get("pages", "")

        snippet_parts: List[str] = []
        if source:
            snippet_parts.append(source)
        if volume and issue:
            snippet_parts.append(f"Vol {volume}, Issue {issue}")
        elif volume:
            snippet_parts.append(f"Vol {volume}")
        if pages:
            snippet_parts.append(f"pp. {pages}")

        pmc_id = summary.get("_pmc_id")
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/" if pmc_id else summary.get("elocationid", "")

        snippet = " | ".join(snippet_parts) if snippet_parts else "PubMed Central article"

        metadata = {
            "pmc_id": pmc_id,
            "journal": source,
            "publication_date": pub_date,
            "mesh": summary.get("meshheadinglist") or [],
        }

        return {
            "url": url,
            "title": enhanced_title,
            "snippet": snippet,
            "metadata": metadata,
        }


__all__ = ["PubMedEngine", "PubMedConfig"]

