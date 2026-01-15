"""Native Project Gutenberg engine using the Gutendex API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote

import requests

try:  # Optional shared session helper used across the project
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - shared_session is optional
    get_shared_session = None  # type: ignore


LOGGER = logging.getLogger("gutenberg_engine")


@dataclass
class GutenbergConfig:
    search_mode: str = "all"  # kept for parity with legacy runner
    languages: Sequence[str] = ("en",)
    max_results_per_page: int = 32
    max_pages: int = 10


class _GutenbergRunner:
    base_url = "https://gutendex.com"

    def __init__(self, phrase: str, config: GutenbergConfig) -> None:
        self.phrase = phrase
        self.config = config
        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="GUTENBERG")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()
        self.session.headers.update({"User-Agent": "SearchEngineer/1.0"})

    # ------------------------------------------------------------------
    # Helpers copied from the legacy runner
    # ------------------------------------------------------------------
    def _build_search_url(self, page: int = 1) -> str:
        params = {
            "search": self.phrase,
            "page": page,
        }
        if self.config.languages:
            params["languages"] = ",".join(self.config.languages)
        query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        return f"{self.base_url}/books?{query}"

    def _get_book_text_url(self, book: Dict[str, any]) -> str:
        formats = book.get("formats", {})
        preferred_order = [
            "text/plain; charset=us-ascii",
            "text/plain; charset=utf-8",
            "text/plain",
        ]
        for fmt in preferred_order:
            if fmt in formats:
                return formats[fmt]
        for key, value in formats.items():
            if "text/html" in key:
                return value
        book_id = book.get("id")
        if book_id:
            return f"https://www.gutenberg.org/ebooks/{book_id}"
        return ""

    def _extract_snippet(self, book: Dict[str, any]) -> str:
        parts: List[str] = []
        subjects = book.get("subjects", [])
        if subjects:
            parts.append(f"Subjects: {', '.join(subjects[:3])}")
        bookshelves = book.get("bookshelves", [])
        if bookshelves:
            parts.append(f"Categories: {', '.join(bookshelves[:2])}")
        download_count = book.get("download_count")
        if download_count:
            parts.append(f"Downloads: {download_count:,}")
        languages = book.get("languages", [])
        if languages:
            parts.append(f"Language: {', '.join(languages)}")
        return " | ".join(parts) if parts else "Project Gutenberg entry"

    def _format_book(self, book: Dict[str, any]) -> Dict[str, str]:
        url = self._get_book_text_url(book)
        title = book.get("title", "Untitled")
        authors = book.get("authors", [])
        author_names = [a.get("name", "") for a in authors if a.get("name")]
        author_str = ", ".join(author_names) if author_names else "Unknown Author"
        if authors and authors[0].get("birth_year"):
            birth = authors[0].get("birth_year")
            death = authors[0].get("death_year")
            if birth and death:
                author_str += f" ({birth}-{death})"
            elif birth:
                author_str += f" (b. {birth})"
        display_title = f"{title} by {author_str}"
        snippet = self._extract_snippet(book)
        return {
            "url": url,
            "title": display_title,
            "snippet": snippet,
            "source": "gutenberg",
            "engine": "gutenberg",
        }

    # ------------------------------------------------------------------
    def search(self, max_results: int) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for page in range(1, self.config.max_pages + 1):
            if len(results) >= max_results:
                break
            url = self._build_search_url(page)
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
            except requests.RequestException as exc:
                LOGGER.warning("Gutendex request failed: %s", exc)
                break

            payload = response.json()
            books = payload.get("results", [])
            if not books:
                break

            for book in books:
                title = book.get("title", "").lower()
                authors = " ".join(a.get("name", "") for a in book.get("authors", []))
                phrase_lower = self.phrase.lower()
                if (
                    phrase_lower in title
                    or phrase_lower in authors.lower()
                    or phrase_lower in " ".join(book.get("subjects", [])).lower()
                ):
                    results.append(self._format_book(book))
                if len(results) >= max_results:
                    break

            if not payload.get("next"):
                break

        return results[:max_results]


class GutenbergEngine:
    code = "GU"
    name = "gutenberg"

    def __init__(self, config: Optional[GutenbergConfig] = None) -> None:
        self.config = config or GutenbergConfig()

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        search_mode: Optional[str] = None,
        languages: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, str]]:
        runner_config = GutenbergConfig(
            search_mode=search_mode or self.config.search_mode,
            languages=languages or self.config.languages,
            max_results_per_page=self.config.max_results_per_page,
            max_pages=self.config.max_pages,
        )
        runner = _GutenbergRunner(query, runner_config)
        return runner.search(max_results)


__all__ = ["GutenbergEngine", "GutenbergConfig"]

