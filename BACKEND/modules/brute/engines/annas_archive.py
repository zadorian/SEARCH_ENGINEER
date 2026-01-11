"""Native Anna's Archive engine with content-type filters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("annas_archive_engine")


@dataclass
class AnnasArchiveConfig:
    max_results: int = 50
    search_fiction: bool = True
    search_nonfiction: bool = True
    search_scholarly: bool = True
    search_journals: bool = True
    search_mode: str = "all"  # "all", "books", "journals"


class _AnnasArchiveRunner:
    base_url = "https://annas-archive.org"

    def __init__(self, phrase: str, config: AnnasArchiveConfig) -> None:
        self.phrase = phrase
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

    def _build_search_url(self, page: int = 1) -> str:
        params = {"q": self.phrase, "page": page}
        if self.config.search_mode == "journals":
            params["index"] = "journals"
        elif self.config.search_mode == "books":
            params["content"] = "book_fiction,book_nonfiction"
        else:
            content: List[str] = []
            if self.config.search_fiction:
                content.append("book_fiction")
            if self.config.search_nonfiction:
                content.append("book_nonfiction")
            if self.config.search_scholarly:
                content.extend(["journal_article", "standards_document", "magazine"])
            if self.config.search_journals:
                content.append("journal_article")
            if content:
                params["content"] = ",".join(dict.fromkeys(content))
        return f"{self.base_url}/search?{urlencode(params)}"

    def _extract_result_data(self, item) -> Optional[Dict[str, str]]:
        result: Dict[str, str] = {}
        title_elem = (
            item.find("h3")
            or item.find("div", class_="truncate")
            or item.find("div", class_="text-lg")
            or item.find("a", class_="truncate")
        )
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)

        author_elem = (
            item.find("div", class_="text-sm")
            or item.find("div", lambda css: css and "italic" in css)
        )
        if author_elem:
            author_text = author_elem.get_text(strip=True)
            if author_text and not author_text.startswith("MD5"):
                result["author"] = author_text

        meta_elems = item.find_all("div", class_="text-xs") or item.find_all(
            "span", class_="text-gray-500"
        )
        for meta in meta_elems:
            text = meta.get_text(strip=True)
            if not text:
                continue
            if any(ch.isdigit() for ch in text):
                import re

                match = re.search(r"\b(19|20)\d{2}\b", text)
                if match:
                    result.setdefault("year", match.group())
            if any(fmt in text.upper() for fmt in ("PDF", "EPUB", "MOBI", "AZW3", "DJVU")):
                result.setdefault("format", text.upper().split()[0])
            if any(unit in text for unit in ("MB", "KB", "GB")):
                result.setdefault("size", text)

        link_elem = item.find("a", href=True)
        if link_elem:
            href = link_elem["href"]
            if href.startswith("/"):
                result["url"] = f"{self.base_url}{href}"
            else:
                result["url"] = href
            if "/md5/" in href:
                result["md5"] = href.split("/md5/")[-1].split("/")[0]

        if not result.get("title"):
            return None

        snippet_parts: List[str] = []
        if result.get("author"):
            snippet_parts.append(f"by {result['author']}")
        if result.get("year"):
            snippet_parts.append(f"({result['year']})")
        if result.get("format"):
            snippet_parts.append(f"[{result['format']}]")
        if result.get("size"):
            snippet_parts.append(result["size"])
        result["snippet"] = " ".join(snippet_parts) if snippet_parts else "Listing on Anna's Archive"
        result.setdefault("source", "annas_archive")
        return result

    def _parse_table_result(self, row) -> Optional[Dict[str, str]]:
        cells = row.find_all("td")
        if len(cells) < 3:
            return None
        result: Dict[str, str] = {}
        link = cells[1].find("a", href=True)
        if link:
            result["title"] = link.get_text(strip=True)
            href = link["href"]
            result["url"] = href if href.startswith("http") else f"{self.base_url}{href}"
        result["author"] = cells[2].get_text(strip=True)
        if len(cells) > 3:
            result["year"] = cells[3].get_text(strip=True)
        if len(cells) > 4:
            result["format"] = cells[4].get_text(strip=True)
        if len(cells) > 5:
            result["size"] = cells[5].get_text(strip=True)
        if not result.get("title"):
            return None
        snippet_parts = [result.get("author", ""), result.get("format", ""), result.get("size", "")]
        result["snippet"] = " ".join(part for part in snippet_parts if part).strip()
        result.setdefault("source", "annas_archive")
        return result

    def search(self) -> List[Dict[str, str]]:
        url = self._build_search_url()
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.error("Anna's Archive request failed: %s", exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("div", class_="h-[125]") or soup.find_all("a", class_="js-vim-focus")
        results: List[Dict[str, str]] = []
        for card in cards:
            parsed = self._extract_result_data(card)
            if parsed:
                results.append(parsed)
            if len(results) >= self.config.max_results:
                return results

        if not results:
            table = soup.find("table", class_="table")
            if table:
                for row in table.find_all("tr")[1:]:
                    parsed = self._parse_table_result(row)
                    if parsed:
                        results.append(parsed)
                    if len(results) >= self.config.max_results:
                        break

        return results[: self.config.max_results]


class AnnasArchiveEngine:
    code = "AA"
    name = "annas_archive"

    def __init__(self, config: Optional[AnnasArchiveConfig] = None) -> None:
        self.config = config or AnnasArchiveConfig()

    def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        search_fiction: Optional[bool] = None,
        search_nonfiction: Optional[bool] = None,
        search_scholarly: Optional[bool] = None,
        search_journals: Optional[bool] = None,
        search_mode: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        runner_config = AnnasArchiveConfig(
            max_results=min(max_results, self.config.max_results),
            search_fiction=self.config.search_fiction if search_fiction is None else search_fiction,
            search_nonfiction=self.config.search_nonfiction if search_nonfiction is None else search_nonfiction,
            search_scholarly=self.config.search_scholarly if search_scholarly is None else search_scholarly,
            search_journals=self.config.search_journals if search_journals is None else search_journals,
            search_mode=search_mode or self.config.search_mode,
        )
        runner = _AnnasArchiveRunner(query, runner_config)
        results = runner.search()
        for item in results:
            item.setdefault("engine", self.name)
        return results[:max_results]


__all__ = ["AnnasArchiveEngine", "AnnasArchiveConfig"]

