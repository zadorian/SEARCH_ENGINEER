#!/usr/bin/env python3
"""
Obchodny register SR (Slovak Commercial Register) API Client
=============================================================

Web scraping client for the Slovak Commercial Register at orsr.sk.

The Slovak Commercial Register does not have a public REST API, so this
module uses web scraping to extract company information.

Usage:
    from country_engines.SK.cr.orsr_api import OrSrAPI

    api = OrSrAPI()
    async with aiohttp.ClientSession() as session:
        results = await api.search_companies(session, "Tatra banka")

Sources:
    - https://www.orsr.sk/ - Official Commercial Register
    - https://www.orsr.sk/search_subjekt.asp - Search endpoint
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, quote

import aiohttp

logger = logging.getLogger("orsr_api")

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[5]
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


class OrSrAPI:
    """
    Obchodny register SR (Slovak Commercial Register) API client.

    Uses web scraping since there is no official REST API.
    """

    BASE_URL = "https://www.orsr.sk"
    SEARCH_URL = "https://www.orsr.sk/hladaj_subjekt.asp"

    def __init__(self):
        self._session_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sk,en;q=0.5",
            "Accept-Charset": "windows-1250,utf-8",
        }

    async def search_companies(
        self,
        session: aiohttp.ClientSession,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for companies in Obchodny register.

        Args:
            session: aiohttp ClientSession
            query: Company name or ICO to search
            limit: Maximum number of results

        Returns:
            List of company dicts with keys:
            - obchodne_meno: Company name
            - ico: Company registration number
            - sidlo: Registered address
            - stav: Status (active, in liquidation, etc.)
            - pravna_forma: Legal form (s.r.o., a.s., etc.)
            - datum_vzniku: Date of incorporation
            - orsr_url: URL to full details on orsr.sk
        """
        try:
            # ORSR uses GET with OBMENO parameter for company name search
            params = {
                "SID": "0",  # 0 = all courts
                "OBMENO": query,  # obchodné meno (company name)
                "P": "0",  # page
            }

            # Check if query looks like ICO (8 digits)
            if re.match(r'^\d{8}$', query.strip()):
                # Use different search page for ICO
                url = "https://www.orsr.sk/hladaj_ico.asp"
                params = {
                    "SID": "0",
                    "ICO": query.strip(),
                    "P": "0",
                }
            else:
                url = self.SEARCH_URL

            async with session.get(
                url,
                params=params,
                headers=self._session_headers,
                timeout=30
            ) as resp:
                if resp.status != 200:
                    logger.error(f"ORSR search failed: HTTP {resp.status}")
                    return []

                # Handle windows-1250 encoding
                raw_bytes = await resp.read()
                try:
                    html = raw_bytes.decode('windows-1250')
                except UnicodeDecodeError:
                    html = raw_bytes.decode('utf-8', errors='replace')

                return self._parse_search_results(html, limit)

        except asyncio.TimeoutError:
            logger.error("ORSR search timed out")
            return []
        except Exception as e:
            logger.error(f"ORSR search error: {e}")
            return []

    def _parse_search_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse search results HTML into structured data."""
        results = []

        try:
            # Pattern to find company links in ORSR results
            # Format: <a href="vypis.asp?ID=12345&amp;SID=2&amp;P=0" class = "link">Company Name</a>
            pattern = r'<a\s+href="(vypis\.asp\?ID=\d+[^"]*)"[^>]*class\s*=\s*"link"[^>]*>([^<]+)</a>'

            matches = re.findall(pattern, html, re.IGNORECASE)

            seen_names = set()  # Deduplicate
            for match in matches:
                url, name = match

                # Clean up extracted data
                name = re.sub(r'\s+', ' ', name.strip())
                name = name.replace('&amp;', '&')

                # Skip navigation links and duplicates
                if not name or name in seen_names:
                    continue
                if len(name) < 3:  # Too short to be a company name
                    continue
                if any(x in name.lower() for x in ['vyhľadáva', 'hľadaj', 'aktuálny', 'úplný', 'stránka']):
                    continue

                seen_names.add(name)

                # Build full URL
                full_url = url.replace('&amp;', '&')
                if not full_url.startswith('http'):
                    full_url = f"{self.BASE_URL}/{full_url}"

                company = {
                    'obchodne_meno': name,
                    'ico': '',  # Would need detail page for ICO
                    'sidlo': '',  # Would need detail page
                    'stav': 'v likvidácii' if 'v likvidácii' in name.lower() else 'Aktívny',
                    'pravna_forma': self._guess_legal_form(name),
                    'datum_vzniku': None,
                    'orsr_url': full_url,
                }

                results.append(company)

                if len(results) >= limit:
                    break

            logger.info(f"ORSR: Found {len(results)} companies")

        except Exception as e:
            logger.error(f"Error parsing ORSR results: {e}")

        return results

    def _guess_legal_form(self, name: str) -> str:
        """Guess legal form from company name."""
        name_upper = name.upper()

        if 'A.S.' in name_upper or 'AKCIOVÁ SPOLOČNOSŤ' in name_upper:
            return 'a.s.'
        elif 'S.R.O.' in name_upper or 'SPOL. S R.O.' in name_upper:
            return 's.r.o.'
        elif 'K.S.' in name_upper:
            return 'k.s.'
        elif 'V.O.S.' in name_upper:
            return 'v.o.s.'
        elif 'DRUŽSTVO' in name_upper:
            return 'družstvo'
        elif 'NADÁCIA' in name_upper:
            return 'nadácia'

        return ''

    async def get_company_detail(
        self,
        session: aiohttp.ClientSession,
        orsr_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed company information from ORSR.

        Args:
            session: aiohttp ClientSession
            orsr_url: URL to company detail page

        Returns:
            Dict with full company details including:
            - officers (konatelia, prokuristi)
            - shareholders (spolocnici)
            - share capital (zakladne imanie)
            - business activities (predmet podnikania)
        """
        try:
            async with session.get(
                orsr_url,
                headers=self._session_headers,
                timeout=30
            ) as resp:
                if resp.status != 200:
                    return None

                html = await resp.text()
                return self._parse_company_detail(html)

        except Exception as e:
            logger.error(f"Error fetching company detail: {e}")
            return None

    def _parse_company_detail(self, html: str) -> Dict[str, Any]:
        """Parse company detail page HTML."""
        result = {
            'konatelia': [],  # Directors
            'prokuristi': [],  # Procurists
            'spolocnici': [],  # Shareholders
            'zakladne_imanie': None,  # Share capital
            'predmet_podnikania': [],  # Business activities
        }

        # This would need proper HTML parsing
        # For now, return empty structure
        # In production, use BeautifulSoup or lxml

        return result


# CLI for testing
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ORSR API CLI")
    parser.add_argument("query", help="Company name or ICO to search")
    args = parser.parse_args()

    async def main():
        api = OrSrAPI()
        async with aiohttp.ClientSession() as session:
            results = await api.search_companies(session, args.query)
            print(json.dumps(results, indent=2, ensure_ascii=False))

    asyncio.run(main())
