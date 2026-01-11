"""Native Nature engine (parity with legacy runner)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

try:
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover
    get_shared_session = None  # type: ignore


@dataclass
class NatureConfig:
    journal: Optional[str] = None
    article_type: Optional[str] = None
    date_range: Optional[Tuple[int, int]] = None
    max_results_per_page: int = 50
    max_pages: int = 10


class _NatureRunner:
    def __init__(self, phrase: str, config: NatureConfig) -> None:
        self.phrase = phrase
        self.config = config
        self.base_url = "https://www.nature.com"

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="NATURE")
            except Exception:  # pragma: no cover
                self.session = requests.Session()
        else:
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

    def _build_search_url(self, page: int) -> str:
        params = {"q": self.phrase, "order": "relevance", "page": page}
        if self.config.journal:
            params["journal"] = self.config.journal
        if self.config.article_type:
            params["article_type"] = self.config.article_type
        if self.config.date_range:
            params["date_from"] = f"{self.config.date_range[0]}-01-01"
            params["date_to"] = f"{self.config.date_range[1]}-12-31"
        return f"{self.base_url}/search?{urlencode(params)}"

    def _extract_article(self, element: BeautifulSoup) -> Optional[Dict[str, str]]:
        try:
            title_elem = element.find("h2", class_="c-card__title") or element.find(
                "h3", class_="c-card__title"
            )
            if not title_elem:
                title_elem = element.find("a", {"data-track-action": "view article"})

            if not title_elem:
                return None

            link = title_elem if title_elem.name == "a" else title_elem.find("a")
            if not link:
                return None

            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href:
                return None
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            authors_elem = element.find("ul", {"aria-label": "Authors"}) or element.find(
                "div", class_="c-author-list"
            )
            authors = []
            if authors_elem:
                authors = [a.get_text(strip=True) for a in authors_elem.find_all("a")]

            journal_elem = element.find("span", {"data-test": "journal"})
            journal = journal_elem.get_text(strip=True) if journal_elem else ""

            date_elem = element.find("time")
            publish_date = date_elem.get("datetime", date_elem.get_text(strip=True)) if date_elem else ""

            type_elem = element.find("span", class_="c-meta__type")
            article_type = type_elem.get_text(strip=True) if type_elem else ""

            summary_elem = element.find("div", class_="c-card__summary") or element.find(
                "p", class_="c-card__description"
            )
            snippet = summary_elem.get_text(strip=True) if summary_elem else ""

            doi_elem = element.find("span", class_="c-bibliographic-doi")
            doi = ""
            if doi_elem:
                doi_text = doi_elem.get_text(strip=True)
                if "doi:" in doi_text.lower():
                    doi = doi_text.split("doi:")[-1].strip()

            return {
                "title": title,
                "url": url,
                "snippet": snippet,
                "authors": ", ".join(authors) if authors else "",
                "journal": journal,
                "date": publish_date,
                "article_type": article_type,
                "doi": doi,
                "source": "nature",
            }
        except Exception:
            return None

    def _search_pages(self) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for page in range(1, self.config.max_pages + 1):
            url = self._build_search_url(page)
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    break
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.find_all("article", class_="c-card")
                if not cards:
                    cards = soup.find_all("li", class_="app-article-list-row__item")
                if not cards:
                    break

                for card in cards:
                    item = self._extract_article(card)
                    if not item:
                        continue
                    lower_phrase = self.phrase.lower()
                    if lower_phrase in item.get("title", "").lower() or lower_phrase in item.get(
                        "snippet", ""
                    ).lower():
                        results.append(item)

                time.sleep(0.2)
                if len(cards) < self.config.max_results_per_page:
                    break
            except Exception:
                break
        return results

    def search(self, max_results: int) -> List[Dict[str, str]]:
        results = self._search_pages()
        dedup: Dict[str, Dict[str, str]] = {}
        for item in results:
            url = item.get("url")
            if url and url not in dedup:
                dedup[url] = item
        return list(dedup.values())[:max_results]


class NatureEngine:
    code = "NT"
    name = "nature"

    def __init__(self, config: Optional[NatureConfig] = None) -> None:
        self.config = config or NatureConfig()

    def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        journal: Optional[str] = None,
        article_type: Optional[str] = None,
        date_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, str]]:
        runner_config = NatureConfig(
            journal=journal or self.config.journal,
            article_type=article_type or self.config.article_type,
            date_range=date_range or self.config.date_range,
            max_results_per_page=self.config.max_results_per_page,
            max_pages=self.config.max_pages,
        )
        runner = _NatureRunner(query, runner_config)
        return runner.search(max_results)


__all__ = ["NatureEngine", "NatureConfig"]

