"""WorldLII specialist engine (legal case law aggregator)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


class WorldLIIEngine:
    """Lightweight scraper for the WorldLII consolidated case-law index."""

    code = "WLI"
    name = "worldlii"

    BASE_URL = "https://www.worldlii.org"
    SEARCH_ENDPOINT = "/cgi-bin/sinosrch.cgi"
    DEFAULT_PARAMS: Dict[str, str] = {
        "method": "auto",
        "meta": "/worldlii",
        "results": "50",
        "submit": "Search",
        "rank": "on",
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0"
                )
            }
        )

    def search(
        self,
        query: str,
        max_results: int = 50,
        *,
        site: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Execute a WorldLII (or companion LII) search."""

        if not query:
            return []

        site_key = (site or "worldlii").lower()
        params = dict(self.DEFAULT_PARAMS)
        base_url = self.BASE_URL

        if site_key != "worldlii":
            mapping = self._site_mapping().get(site_key)
            if not mapping:
                logger.warning("Unknown LII site '%s' – defaulting to WorldLII", site_key)
            else:
                base_url = mapping["base_url"]
                params.update(mapping.get("params", {}))

        params["query"] = query

        try:
            response = self.session.get(
                f"{base_url}{self.SEARCH_ENDPOINT}", params=params, timeout=15
            )
            response.raise_for_status()
        except Exception as exc:
            logger.error("WorldLII search failed: %s", exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: List[Dict[str, str]] = []

        # Common result structure: <a href="..."><b>Case Title</b></a>
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            title = anchor.get_text(strip=True)

            if not href or not title:
                continue
            if not any(segment in href for segment in ("/cases/", "/legal/", "/law")):
                continue

            url = urljoin(base_url, href)
            snippet = self._extract_context(anchor)

            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet[:400] if snippet else "Legal material",
                    "source": site_key.upper(),
                    "engine": self.name,
                    "engine_code": self.code,
                }
            )

            if len(results) >= max_results:
                break

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _site_mapping(self) -> Dict[str, Dict[str, str]]:
        return {
            "austlii": {
                "base_url": "https://www.austlii.edu.au",
                "params": {"meta": "/austlii"},
            },
            "asianlii": {
                "base_url": "http://www.asianlii.org",
                "params": {"meta": "/asianlii"},
            },
            "commonlii": {
                "base_url": "https://www.commonlii.org",
                "params": {"meta": "/commonlii"},
            },
            "saflii": {
                "base_url": "https://www.saflii.org",
                "params": {"meta": "/saflii"},
            },
            "paclii": {
                "base_url": "http://www.paclii.org",
                "params": {"meta": "/paclii"},
            },
            "nzlii": {
                "base_url": "http://www.nzlii.org",
                "params": {"meta": "/nzlii"},
            },
        }

    def _extract_context(self, anchor: BeautifulSoup) -> str:
        parent = anchor.parent
        if not parent:
            return ""
        texts = parent.find_all(text=True, recursive=False)
        snippet = " ".join(text.strip() for text in texts if text.strip())
        if not snippet and parent.parent:
            texts = parent.parent.find_all(text=True, recursive=False)
            snippet = " ".join(text.strip() for text in texts if text.strip())
        return snippet


def main(query: str) -> List[Dict[str, str]]:
    engine = WorldLIIEngine()
    return engine.search(query)


