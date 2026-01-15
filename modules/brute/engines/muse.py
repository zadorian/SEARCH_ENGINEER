"""Native Project MUSE engine (parity with legacy runner)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

# JESTER for scraping (auto-fallback A->B->C->D)
try:
    from .jester_bridge import jester_scrape_sync, JESTER_AVAILABLE
except ImportError:
    JESTER_AVAILABLE = False
    jester_scrape_sync = None

try:  # Optional shared session helper used across the project
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    get_shared_session = None  # type: ignore


@dataclass
class ProjectMUSEConfig:
    use_authentication: bool = True
    use_proxy: bool = False
    content_type: Optional[str] = None  # "articles", "books", "all"
    date_range: Optional[Tuple[int, int]] = None
    max_results_per_page: int = 20
    max_pages: int = 10


class _ProjectMUSERunner:
    """Port of the legacy Project MUSE runner with minimal tweaks."""

    def __init__(self, phrase: str, config: ProjectMUSEConfig) -> None:
        self.phrase = phrase
        self.config = config

        if config.use_proxy and os.getenv("UCL_PROXY_USERNAME"):
            self.base_url = "https://muse-jhu-edu.ejournals.alumni.ucl.ac.uk"
            self.login_url = "https://ejournals.alumni.ucl.ac.uk/login"
            self.proxy_mode = True
        else:
            self.base_url = "https://muse.jhu.edu"
            self.login_url = f"{self.base_url}/login"
            self.proxy_mode = False

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="MUSE")
            except Exception:  # pragma: no cover - defensive
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

        self.authenticated = False
        if config.use_authentication:
            self._attempt_login()

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------
    def _attempt_login(self) -> None:
        try:
            if self.proxy_mode:
                username = os.getenv("UCL_PROXY_USERNAME")
                password = os.getenv("UCL_PROXY_PASSWORD")

                if not username or not password:
                    return

                login_data = {"username": username, "password": password, "submit": "Login"}
                response = self.session.post(self.login_url, data=login_data, timeout=30)
                if response.status_code == 200 and "logout" in response.text.lower():
                    self.authenticated = True
            else:
                username = os.getenv("MUSE_USERNAME")
                password = os.getenv("MUSE_PASSWORD")
                if not username or not password:
                    return

                login_data = {"email": username, "password": password, "submit": "Sign In"}
                response = self.session.post(self.login_url, data=login_data, timeout=30)
                if response.status_code == 200 and (
                    "sign out" in response.text.lower() or "my muse" in response.text.lower()
                ):
                    self.authenticated = True
        except Exception:  # pragma: no cover - authentication is best effort
            self.authenticated = False

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------
    def _build_search_url(self, page: int) -> str:
        offset = (page - 1) * self.config.max_results_per_page
        params = {
            "action": "search",
            "query": f"content:{self.phrase}",
            "min": offset + 1,
            "max": offset + self.config.max_results_per_page,
            "t": "header",
        }

        if self.config.content_type == "articles":
            params["res"] = "journal"
        elif self.config.content_type == "books":
            params["res"] = "book"

        if self.config.date_range:
            params["y1"] = self.config.date_range[0]
            params["y2"] = self.config.date_range[1]

        return f"{self.base_url}/search?{urlencode(params)}"

    def _extract_article(self, element: BeautifulSoup) -> Optional[Dict[str, str]]:
        try:
            result: Dict[str, str] = {}
            title_elem = element.find("span", class_="title") or element.find("a", class_="title")
            if title_elem:
                link = title_elem if title_elem.name == "a" else element.find("a")
                if link:
                    result["title"] = link.get_text(strip=True)
                    href = link.get("href", "")
                else:
                    result["title"] = title_elem.get_text(strip=True)
                    href = ""
            else:
                return None

            if href:
                if href.startswith("/"):
                    result["url"] = f"{self.base_url}{href}"
                elif href.startswith("http"):
                    result["url"] = href
                else:
                    result["url"] = f"{self.base_url}/{href.strip('/') }"

            authors_elem = element.find("span", class_="byline")
            if authors_elem:
                result["authors"] = authors_elem.get_text(strip=True)

            pub_elem = element.find("span", class_="journal")
            if pub_elem:
                result["journal"] = pub_elem.get_text(strip=True)

            date_elem = element.find("span", class_="date")
            if date_elem:
                result["date"] = date_elem.get_text(strip=True)

            snippet_elem = element.find("p", class_="snippet")
            if snippet_elem:
                result["snippet"] = snippet_elem.get_text(strip=True)

            doi_elem = element.find("span", class_="doi")
            if doi_elem:
                result["doi"] = doi_elem.get_text(strip=True)

            return result if "url" in result else None
        except Exception:
            return None

    def _search_pages(self) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for page in range(1, self.config.max_pages + 1):
            if len(results) >= self.config.max_results_per_page * self.config.max_pages:
                break

            url = self._build_search_url(page)
            try:
                # Use JESTER for scraping
                if JESTER_AVAILABLE and jester_scrape_sync:
                    _jester_html = jester_scrape_sync(url, force_js=False, timeout=30)
                    if _jester_html:
                        class _JesterResponse:
                            text = _jester_html
                            status_code = 200
                            def raise_for_status(self): pass
                        response = _JesterResponse()
                    else:
                        response = self.session.get(url, timeout=30)
                else:
                    response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                entries = soup.find_all("li", class_="result")
                if not entries:
                    entries = soup.find_all("article", class_="result")
                if not entries:
                    break

                for elem in entries:
                    article = self._extract_article(elem)
                    if not article:
                        continue

                    snippet = article.get("snippet", "").lower()
                    title = article.get("title", "").lower()
                    if self.phrase.lower() in title or self.phrase.lower() in snippet:
                        article.setdefault("source", "muse")
                        results.append(article)

                    if len(results) >= self.config.max_results_per_page * self.config.max_pages:
                        break

                time.sleep(0.3)
            except Exception:
                break

        return results

    def search(self, max_results: int) -> List[Dict[str, str]]:
        results = self._search_pages()
        unique: Dict[str, Dict[str, str]] = {}
        for item in results:
            url = item.get("url")
            if url and url not in unique:
                unique[url] = item
        return list(unique.values())[:max_results]


class ProjectMUSEEngine:
    code = "MU"
    name = "project_muse"

    def __init__(self, config: Optional[ProjectMUSEConfig] = None) -> None:
        self.config = config or ProjectMUSEConfig()

    def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        use_authentication: Optional[bool] = None,
        use_proxy: Optional[bool] = None,
        content_type: Optional[str] = None,
        date_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, str]]:
        runner_config = ProjectMUSEConfig(
            use_authentication=self.config.use_authentication if use_authentication is None else use_authentication,
            use_proxy=self.config.use_proxy if use_proxy is None else use_proxy,
            content_type=content_type or self.config.content_type,
            date_range=date_range or self.config.date_range,
            max_results_per_page=self.config.max_results_per_page,
            max_pages=self.config.max_pages,
        )

        runner = _ProjectMUSERunner(query, runner_config)
        return runner.search(max_results)


__all__ = ["ProjectMUSEEngine", "ProjectMUSEConfig"]

