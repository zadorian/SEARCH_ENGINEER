"""Native JSTOR engine (parity with legacy runner)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

# JESTER for scraping (auto-fallback A->B->C->D)
try:
    from .jester_bridge import jester_scrape_sync, JESTER_AVAILABLE
except ImportError:
    JESTER_AVAILABLE = False
    jester_scrape_sync = None

try:
    from shared_session import get_shared_session  # type: ignore
except ImportError:  # pragma: no cover
    get_shared_session = None  # type: ignore


@dataclass
class JSTORConfig:
    use_authentication: bool = True
    use_proxy: bool = False
    content_type: Optional[str] = None
    date_range: Optional[Tuple[int, int]] = None
    max_results_per_page: int = 25
    max_pages: int = 10


class _JSTORRunner:
    def __init__(self, phrase: str, config: JSTORConfig) -> None:
        self.phrase = phrase
        self.config = config

        if config.use_proxy and os.getenv("UCL_PROXY_USERNAME"):
            self.base_url = "https://www-jstor-org.ejournals.alumni.ucl.ac.uk"
            self.login_url = "https://ejournals.alumni.ucl.ac.uk/login"
            self.proxy_mode = True
        else:
            self.base_url = "https://www.jstor.org"
            self.login_url = f"{self.base_url}/action/doLogin"
            self.proxy_mode = False

        if get_shared_session:
            try:
                self.session = get_shared_session(engine_name="JSTOR")
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

        self.authenticated = False
        if config.use_authentication:
            self._attempt_login()

    def _attempt_login(self) -> None:
        try:
            if self.proxy_mode:
                username = os.getenv("UCL_PROXY_USERNAME")
                password = os.getenv("UCL_PROXY_PASSWORD")
                if not username or not password:
                    return
                response = self.session.post(
                    self.login_url,
                    data={"username": username, "password": password, "submit": "Login"},
                    timeout=30,
                )
                if response.status_code == 200 and "logout" in response.text.lower():
                    self.authenticated = True
            else:
                username = os.getenv("JSTOR_USERNAME")
                password = os.getenv("JSTOR_PASSWORD")
                if not username or not password:
                    return

                login_page = self.session.get(f"{self.base_url}/action/showLogin", timeout=30)
                soup = BeautifulSoup(login_page.text, "html.parser")
                csrf_input = soup.find("input", {"name": "csrfToken"})
                csrf_token = csrf_input.get("value") if csrf_input else None

                login_data = {
                    "username": username,
                    "password": password,
                    "submit": "Log in",
                    "redirectUri": "/account/workspace",
                }
                if csrf_token:
                    login_data["csrfToken"] = csrf_token

                response = self.session.post(self.login_url, data=login_data, timeout=30)
                if response.status_code == 200 and (
                    "logout" in response.text.lower() or "my workspace" in response.text.lower()
                ):
                    self.authenticated = True
        except Exception:  # pragma: no cover
            self.authenticated = False

    def _build_search_url(self, page: int) -> str:
        params = {"Query": self.phrase, "so": "rel", "si": (page - 1) * self.config.max_results_per_page + 1}
        if self.config.content_type:
            mapping = {
                "articles": "jtype:journal-article",
                "books": "jtype:book",
                "chapters": "jtype:book-chapter",
            }
            if self.config.content_type in mapping:
                params["filter"] = mapping[self.config.content_type]
        if self.config.date_range:
            params["sd"] = self.config.date_range[0]
            params["ed"] = self.config.date_range[1]
        return f"{self.base_url}/action/doBasicSearch?{urlencode(params)}"

    def _extract_item(self, element: BeautifulSoup) -> Optional[Dict[str, str]]:
        try:
            title_elem = element.find("span", class_="title") or element.find("a", class_="title")
            if not title_elem:
                return None
            link = title_elem if title_elem.name == "a" else element.find("a")
            if not link:
                return None

            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href:
                return None
            if href.startswith("/"):
                url = f"{self.base_url}{href}"
            else:
                url = href

            snippet = element.find("span", class_="snippet")
            highlight = snippet.get_text(strip=True) if snippet else ""

            publication = element.find("span", class_="subtitle")
            pub_text = publication.get_text(strip=True) if publication else ""

            authors_elem = element.find("span", class_="details")
            authors = authors_elem.get_text(strip=True) if authors_elem else ""

            return {
                "title": title,
                "url": url,
                "snippet": highlight or pub_text,
                "authors": authors,
                "source": "jstor",
            }
        except Exception:
            return None

    def _search_pages(self) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for page in range(1, self.config.max_pages + 1):
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
                articles = soup.find_all("li", class_="search-result")
                if not articles:
                    break

                for elem in articles:
                    item = self._extract_item(elem)
                    if not item:
                        continue
                    lower_phrase = self.phrase.lower()
                    if lower_phrase in item.get("title", "").lower() or lower_phrase in item.get(
                        "snippet", ""
                    ).lower():
                        results.append(item)
                    if len(results) >= self.config.max_results_per_page * self.config.max_pages:
                        break

                if len(articles) < self.config.max_results_per_page:
                    break
                time.sleep(0.3)
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


class JSTOREngine:
    code = "JS"
    name = "jstor"

    def __init__(self, config: Optional[JSTORConfig] = None) -> None:
        self.config = config or JSTORConfig()

    def search(
        self,
        query: str,
        max_results: int = 60,
        *,
        use_authentication: Optional[bool] = None,
        use_proxy: Optional[bool] = None,
        content_type: Optional[str] = None,
        date_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, str]]:
        runner_config = JSTORConfig(
            use_authentication=self.config.use_authentication if use_authentication is None else use_authentication,
            use_proxy=self.config.use_proxy if use_proxy is None else use_proxy,
            content_type=content_type or self.config.content_type,
            date_range=date_range or self.config.date_range,
            max_results_per_page=self.config.max_results_per_page,
            max_pages=self.config.max_pages,
        )
        runner = _JSTORRunner(query, runner_config)
        return runner.search(max_results)


__all__ = ["JSTOREngine", "JSTORConfig"]

