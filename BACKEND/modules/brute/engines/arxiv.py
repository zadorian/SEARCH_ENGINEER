"""Native arXiv engine (parity with legacy runner)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

try:  # Optional pooled session helper
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    get_shared_session = None  # type: ignore


LOGGER = logging.getLogger("arxiv_academic_engine")


@dataclass
class ArxivConfig:
    base_url: str = "http://export.arxiv.org/api/query"
    max_results_per_page: int = 100
    max_pages: int = 10
    timeout: int = 20
    pause_seconds: float = 0.2


class ArxivEngine:
    code = "AX"
    name = "arxiv"

    def __init__(self, config: Optional[ArxivConfig] = None) -> None:
        self.config = config or ArxivConfig()

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="ARXIV")
            except Exception:  # pragma: no cover - defensive
                self.session = requests.Session()
        else:
            self.session = requests.Session()

        self.session.headers.update({"User-Agent": "SearchEngineer-arXiv/1.0"})

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        search_mode: str = "all",
        category: Optional[str] = None,
        date_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        formatted_query = self._build_query(query, search_mode=search_mode, category=category)
        start = 0
        collected: List[Dict[str, Any]] = []

        for page in range(self.config.max_pages):
            if len(collected) >= max_results:
                break

            params = {
                "search_query": formatted_query,
                "start": start,
                "max_results": self.config.max_results_per_page,
            }

            if date_range:
                params["startDate"] = f"{date_range[0]}01010000"
                params["endDate"] = f"{date_range[1]}12312359"

            url = f"{self.config.base_url}?{urlencode(params)}"
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network guard
                LOGGER.warning("arXiv request failed (page %s): %s", page, exc)
                break

            entries = self._parse_feed(response.text)
            if not entries:
                break

            for entry in entries:
                entry.setdefault("engine", self.name)
                entry.setdefault("engine_code", self.code)
                entry.setdefault("engine_badge", self.code)
                entry.setdefault("source", "arxiv")
                collected.append(entry)
                if len(collected) >= max_results:
                    break

            start += self.config.max_results_per_page

        return collected[:max_results]

    def _build_query(self, phrase: str, *, search_mode: str, category: Optional[str]) -> str:
        quoted = f'"{phrase}"'
        if search_mode == "title":
            query = f"ti:{quoted}"
        elif search_mode == "abstract":
            query = f"abs:{quoted}"
        elif search_mode == "author":
            query = f"au:{quoted}"
        elif search_mode == "comment":
            query = f"co:{quoted}"
        else:
            query = f"all:{quoted}"

        if category:
            query = f"{query} AND cat:{category}"
        return query

    def _parse_feed(self, xml_payload: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(xml_payload)
        except ET.ParseError as exc:  # pragma: no cover - malformed response
            LOGGER.warning("Unable to parse arXiv response: %s", exc)
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        entries: List[Dict[str, Any]] = []

        for entry in root.findall("atom:entry", ns):
            parsed = self._parse_entry(entry, ns)
            if parsed:
                entries.append(parsed)

        return entries

    def _parse_entry(self, element: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
        title_el = element.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None else "Untitled"

        summary_el = element.find("atom:summary", ns)
        summary = summary_el.text.strip() if summary_el is not None else ""

        url = ""
        for link in element.findall("atom:link", ns):
            link_type = link.get("type")
            if link_type == "application/pdf":
                url = link.get("href", "")
                break
            if link_type == "text/html":
                url = url or link.get("href", "")

        authors = []
        for author in element.findall("atom:author", ns):
            name_el = author.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text)

        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        published_el = element.find("atom:published", ns)
        year = ""
        if published_el is not None and published_el.text:
            try:
                year = str(datetime.fromisoformat(published_el.text.replace("Z", "+00:00")).year)
            except ValueError:
                year = ""

        categories = [cat.get("term") for cat in element.findall("atom:category", ns) if cat.get("term")]

        arxiv_id_el = element.find("atom:id", ns)
        arxiv_id = ""
        if arxiv_id_el is not None and arxiv_id_el.text:
            segments = arxiv_id_el.text.split("/")
            if segments:
                arxiv_id = segments[-1]

        comment_el = element.find("arxiv:comment", ns)
        comment = comment_el.text.strip() if comment_el is not None and comment_el.text else ""

        title_parts = [title]
        if author_str:
            title_parts.append(f"- {author_str}")
        if year:
            title_parts.append(f"({year})")
        enhanced_title = " ".join(title_parts)

        snippet_parts: List[str] = []
        if arxiv_id:
            snippet_parts.append(arxiv_id)
        if categories:
            snippet_parts.append(f"Categories: {', '.join(categories[:3])}")
        if comment:
            snippet_parts.append(comment[:100])
        if summary:
            preview = summary[:240]
            if len(summary) > 240:
                preview += "…"
            snippet_parts.append(preview)

        snippet = " | ".join(snippet_parts) if snippet_parts else "arXiv preprint"

        return {
            "url": url,
            "title": enhanced_title,
            "snippet": snippet,
            "metadata": {
                "arxiv_id": arxiv_id,
                "categories": categories,
                "comment": comment,
            },
        }


__all__ = ["ArxivEngine", "ArxivConfig"]

