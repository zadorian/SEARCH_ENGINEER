"""Native Library Genesis (LibGen) engine with mirror fallback."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger("libgen_engine")


@dataclass
class LibGenConfig:
    max_results: int = 100
    search_fiction: bool = True
    search_scimag: bool = False
    search_comics: bool = False


class _LibGenRunner:
    MIRRORS = [
        "https://libgen.li",
        "https://libgen.is",
        "https://libgen.st",
        "https://libgen.rs",
        "http://gen.lib.rus.ec",
    ]

    def __init__(self, phrase: str, config: LibGenConfig) -> None:
        self.phrase = phrase
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "DNT": "1",
            }
        )
        self.base_url = self._find_working_mirror()

    def _find_working_mirror(self) -> str:
        for mirror in self.MIRRORS:
            try:
                response = self.session.get(mirror, timeout=10)
                if response.status_code == 200:
                    return mirror
            except requests.RequestException:
                continue
        LOGGER.warning("No LibGen mirror responded; falling back to %s", self.MIRRORS[0])
        return self.MIRRORS[0]

    def _build_search_url(self) -> str:
        params: List[str] = [f"req={quote(self.phrase)}", "filesuns=all", f"res={self.config.max_results}"]
        # columns to display
        for col in ["t", "a", "s", "y", "p", "i"]:
            params.append(f"columns%5B%5D={col}")

        objects: List[str] = []
        if self.config.search_fiction:
            objects.extend(["f", "e"])
        if self.config.search_scimag:
            objects.append("s")
        if self.config.search_comics:
            objects.append("c")
        if not objects:
            objects = ["f", "e", "s", "a", "p", "w"]

        for obj in objects:
            params.append(f"objects%5B%5D={obj}")

        for topic in ["l", "c", "f", "a", "m", "r", "s"]:
            params.append(f"topics%5B%5D={topic}")

        return f"{self.base_url}/index.php?{'&'.join(params)}"

    def _parse_table(self, html: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        results: List[Dict[str, str]] = []

        target = None
        for table in tables:
            rows = table.find_all("tr")
            if rows and len(rows) > 3:
                target = table
                break
        if not target:
            return results

        for row in target.find_all("tr"):
            if row.find("th"):
                continue
            parsed = self._extract_row(row)
            if parsed:
                results.append(parsed)
            if len(results) >= self.config.max_results:
                break

        return results

    def _extract_row(self, row) -> Optional[Dict[str, str]]:
        cells = row.find_all("td")
        if len(cells) < 5:
            return None

        result: Dict[str, str] = {}
        title_cell = None
        for cell in cells:
            link = cell.find("a")
            if not link:
                continue
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text:
                continue
            if "book" in href or len(text) > 10:
                result["title"] = text
                title_cell = cell
                md5_match = re.search(r"md5=([a-fA-F0-9]{32})", href)
                if md5_match:
                    result["md5"] = md5_match.group(1)
                break

        if not title_cell:
            return None

        for cell in cells:
            if cell is title_cell:
                continue
            text = cell.get_text(strip=True)
            if not text:
                continue
            if not result.get("author") and "," in text and not any(ch.isdigit() for ch in text[:5]):
                result["author"] = text
            elif not result.get("year") and re.match(r"^(19|20)\d{2}$", text):
                result["year"] = text
            elif not result.get("size") and any(unit in text for unit in ("KB", "MB", "GB")):
                result["size"] = text
            elif not result.get("format") and len(text) <= 4 and text.lower() in {
                "pdf",
                "epub",
                "mobi",
                "djvu",
                "azw3",
                "fb2",
                "txt",
                "doc",
                "docx",
            }:
                result["format"] = text.upper()
            elif not result.get("language") and text.lower() in {
                "english",
                "russian",
                "german",
                "french",
                "spanish",
                "italian",
                "chinese",
                "japanese",
            }:
                result["language"] = text
            elif not result.get("pages") and re.match(r"^\d+\s*(p|pp)?\.?$", text):
                result["pages"] = text
            elif not result.get("publisher") and len(text) > 5 and not any(ch.isdigit() for ch in text[:3]):
                if result.get("author") != text:
                    result["publisher"] = text

        for link in row.find_all("a", href=True):
            href = link["href"]
            if any(domain in href for domain in ("library.lol", "libgen.lc", "get.php", "ads.php")):
                result["download_url"] = href if href.startswith("http") else f"http:{href}"
                break

        if result.get("md5"):
            result["url"] = f"{self.base_url}/book/index.php?md5={result['md5']}"
        else:
            result["url"] = f"{self.base_url}/search.php?req={quote(self.phrase)}"

        snippet_parts: List[str] = []
        if result.get("author"):
            snippet_parts.append(f"by {result['author']}")
        if result.get("year"):
            snippet_parts.append(f"({result['year']})")
        if result.get("publisher"):
            snippet_parts.append(f"Publisher: {result['publisher']}")
        if result.get("format"):
            snippet_parts.append(f"[{result['format']}]")
        if result.get("size"):
            snippet_parts.append(result["size"])
        if result.get("pages"):
            snippet_parts.append(f"{result['pages']} pages")

        result["snippet"] = " ".join(snippet_parts) if snippet_parts else "Book available on LibGen"
        result.setdefault("source", "libgen")
        return result

    def search(self) -> List[Dict[str, str]]:
        url = self._build_search_url()
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.error("LibGen request failed: %s", exc)
            return []

        return self._parse_table(response.text)


class LibGenEngine:
    code = "LG"
    name = "libgen"

    def __init__(self, config: Optional[LibGenConfig] = None) -> None:
        self.config = config or LibGenConfig()

    def search(
        self,
        query: str,
        max_results: int = 100,
        *,
        search_fiction: Optional[bool] = None,
        search_scimag: Optional[bool] = None,
        search_comics: Optional[bool] = None,
    ) -> List[Dict[str, str]]:
        runner_config = LibGenConfig(
            max_results=min(max_results, self.config.max_results),
            search_fiction=self.config.search_fiction if search_fiction is None else search_fiction,
            search_scimag=self.config.search_scimag if search_scimag is None else search_scimag,
            search_comics=self.config.search_comics if search_comics is None else search_comics,
        )
        runner = _LibGenRunner(query, runner_config)
        results = runner.search()
        for item in results:
            item.setdefault("engine", self.name)
        return results[:max_results]


__all__ = ["LibGenEngine", "LibGenConfig"]

