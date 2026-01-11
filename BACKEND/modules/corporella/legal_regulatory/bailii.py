"""BAILII specialist engine.

Ported from the legacy Search_Types implementation so the engine can be
consumed directly by the matrix/targeted-search layer.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


class BailiiEngine:
    """Case-law search powered by the public BAILII endpoints."""

    code = "BAI"
    name = "bailii"
    BASE_URL = "https://www.bailii.org"

    # Court mappings copied from the legacy runner for parity
    COURTS: Dict[str, str] = {
        "uksc": "uk/cases/UKSC",
        "ukhl": "uk/cases/UKHL",
        "ukpc": "uk/cases/UKPC",
        "ewca_civ": "ew/cases/EWCA/Civ",
        "ewca_crim": "ew/cases/EWCA/Crim",
        "ewhc_admin": "ew/cases/EWHC/Admin",
        "ewhc_ch": "ew/cases/EWHC/Ch",
        "ewhc_comm": "ew/cases/EWHC/Comm",
        "ewhc_costs": "ew/cases/EWHC/Costs",
        "ewhc_fam": "ew/cases/EWHC/Fam",
        "ewhc_ipec": "ew/cases/EWHC/IPEC",
        "ewhc_kb": "ew/cases/EWHC/KB",
        "ewhc_pat": "ew/cases/EWHC/Pat",
        "ewhc_qb": "ew/cases/EWHC/QB",
        "ewhc_scco": "ew/cases/EWHC/SCCO",
        "ewhc_tcc": "ew/cases/EWHC/TCC",
        "ukut": "uk/cases/UKUT",
        "ukftt": "uk/cases/UKFTT",
        "ukeat": "uk/cases/UKEAT",
        "ukait": "uk/cases/UKAIT",
        "ukipt": "uk/cases/UKIPT",
        "scotcs": "scot/cases/ScotCS",
        "scothc": "scot/cases/ScotHC",
        "nica": "nie/cases/NICA",
        "nihc": "nie/cases/NIHC",
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search(self, query: str, max_results: int = 20, **kwargs) -> List[Dict[str, str]]:
        """Execute a BAILII search."""

        query = query.strip()
        if not query:
            return self.get_recent_decisions(limit=max_results)

        # direct citation e.g. [2023] UKSC 34
        citation_url = self._citation_to_url(query)
        if citation_url:
            case = self._fetch_case(citation_url)
            return [case] if case else []

        params = self._parse_search_query(query)
        if params.get("court") and params.get("year"):
            return self._browse_court_year(params["court"], params["year"], max_results)

        results = self._search_cases(params.get("query", query))
        return results[:max_results]

    def get_recent_decisions(self, limit: int = 20) -> List[Dict[str, str]]:
        url = f"{self.BASE_URL}/recent-decisions.html"
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return []

        results: List[Dict[str, str]] = []
        for link in soup.find_all("a", href=re.compile(r"/cases/.*\.html")):
            if len(results) >= limit:
                break
            case_url = urljoin(self.BASE_URL, link["href"])
            title = link.get_text(strip=True)
            date_match = re.search(r"\((\d{1,2}\s+\w+\s+\d{4})\)", title)
            date = date_match.group(1) if date_match else "Recent"
            results.append(
                {
                    "title": title,
                    "url": case_url,
                    "snippet": f"Recent decision - {date}",
                    "source": "BAILII",
                    "engine": self.name,
                    "engine_code": self.code,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _parse_search_query(self, query: str) -> Dict[str, Optional[str]]:
        params: Dict[str, Optional[str]] = {}
        court_match = re.search(r"court:(\S+)", query)
        if court_match:
            params["court"] = court_match.group(1)
            query = query.replace(court_match.group(0), "")

        year_match = re.search(r"year:(\d{4})", query)
        if year_match:
            params["year"] = int(year_match.group(1))
            query = query.replace(year_match.group(0), "")

        party_match = re.search(r'party:"([^"]+)"', query)
        if not party_match:
            party_match = re.search(r"party:(\S+)", query)
        if party_match:
            params["party"] = party_match.group(1)
            query = query.replace(party_match.group(0), "")

        query = re.sub(r"bailii!:", "", query)
        params["query"] = query.strip()
        return params

    def _citation_to_url(self, citation: str) -> Optional[str]:
        pattern = r"\[(\d{4})\]\s+([A-Z]+)\s+(\d+)(?:\s+\(([A-Za-z]+)\))?"
        match = re.match(pattern, citation.strip())
        if not match:
            return None

        year, court, number, division = match.groups()
        court_key = f"{court.lower()}_{division.lower()}" if division else court.lower()

        if court_key in self.COURTS:
            court_path = self.COURTS[court_key]
        elif court.lower() in self.COURTS:
            court_path = self.COURTS[court.lower()]
            if division:
                court_path += f"/{division.capitalize()}"
        else:
            return None

        return f"{self.BASE_URL}/{court_path}/{year}/{number}.html"

    def _fetch_case(self, url: str) -> Optional[Dict[str, str]]:
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return None
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return None

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Case"
        snippet = ""
        for paragraph in soup.find_all("p")[:3]:
            text = paragraph.get_text(strip=True)
            if len(text) > 50:
                snippet = text[:500] + "..."
                break

        return {
            "title": title,
            "url": url,
            "snippet": snippet,
            "source": "BAILII",
            "engine": self.name,
            "engine_code": self.code,
        }

    def _search_cases(self, query: str) -> List[Dict[str, str]]:
        search_url = f"{self.BASE_URL}/cgi-bin/lucy_search_1.cgi"
        params = {
            "sort": "rank",
            "method": "boolean",
            "query": f"({query})" if query else "",
            "mask_path": "/",
            "highlight": "1",
            "results": "200",
        }

        try:
            response = self.session.get(search_url, params=params, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return []

        results: List[Dict[str, str]] = []
        for link in soup.find_all("a", href=re.compile(r"/.*/cases/.+\.html")):
            case_url = urljoin(self.BASE_URL, link["href"])
            context = self._extract_context(link)
            results.append(
                {
                    "title": link.get_text(strip=True) or case_url,
                    "url": case_url,
                    "snippet": context[:300] if context else "Legal case from BAILII",
                    "source": "BAILII",
                    "engine": self.name,
                    "engine_code": self.code,
                }
            )
            if len(results) >= 200:
                break
        return results

    def _extract_context(self, link: BeautifulSoup) -> str:
        parent = link.parent
        context_parts: List[str] = []
        if parent:
            context_parts.extend(text.strip() for text in parent.find_all(text=True, recursive=False) if text.strip())
            if parent.parent:
                context_parts.extend(
                    text.strip()
                    for text in parent.parent.find_all(text=True, recursive=False)
                    if text.strip()
                )
        return " ".join(context_parts)

    def _browse_court_year(self, court: str, year: int, max_results: int) -> List[Dict[str, str]]:
        court_key = court.lower()
        if court_key not in self.COURTS:
            return []

        url = f"{self.BASE_URL}/{self.COURTS[court_key]}/{year}/"
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return []

        results: List[Dict[str, str]] = []
        for link in soup.find_all("a", href=re.compile(r"^\d+\.html")):
            if len(results) >= max_results:
                break
            case_url = urljoin(url, link["href"])
            number_match = re.search(r"(\d+)\.html", link["href"])
            case_number = number_match.group(1) if number_match else ""
            case_name = link.next_sibling
            if case_name:
                case_name = str(case_name).strip()
            else:
                case_name = link.get_text(strip=True)

            results.append(
                {
                    "title": f"[{year}] {court.upper()} {case_number} - {case_name}",
                    "url": case_url,
                    "snippet": f"Case from {court.upper()} decided in {year}",
                    "source": "BAILII",
                    "engine": self.name,
                    "engine_code": self.code,
                }
            )

        return results


def main(query: str) -> List[Dict[str, str]]:
    """CLI helper for quick manual checks."""

    engine = BailiiEngine()
    return engine.search(query, max_results=20)


