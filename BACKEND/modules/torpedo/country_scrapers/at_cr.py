#!/usr/bin/env python3
"""
Austria Company Registry (at_cr.py)
===================================

Wrapper for Austrian company registry searches using FirmenABC.
Provides a unified interface matching the UK pattern.

SOURCES:
- FirmenABC (firmenabc.at) - Comprehensive Austrian business directory
- Firmenbuch (commercial register) - Via FirmenABC data

USAGE:
    from country_engines.AT.at_cr import ATCompanyRegistry

    cr = ATCompanyRegistry()

    # Search companies
    results = await cr.search("Erste Bank")

    # Search persons (directors, shareholders)
    results = await cr.search_person("Wolfgang Plasser")

    # Get full company profile
    profile = await cr.get_full_profile("FN 33209 m")
"""

import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "BACKEND" / "modules"))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ATCompany:
    """Austrian company profile."""
    name: str
    fn_number: Optional[str] = None  # Firmenbuchnummer (e.g., "FN 33209 m")
    uid: Optional[str] = None  # UID/VAT number (e.g., "ATU12345678")
    status: Optional[str] = None
    legal_form: Optional[str] = None  # GmbH, AG, KG, etc.
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: str = "Austria"
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    founding_date: Optional[str] = None
    business_activity: Optional[str] = None
    firmenabc_url: Optional[str] = None

    # Related entities
    officers: List[Dict] = field(default_factory=list)
    shareholders: List[Dict] = field(default_factory=list)
    properties: List[Dict] = field(default_factory=list)

    # Raw data
    raw: Dict = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)


# =============================================================================
# AT COMPANY REGISTRY CLASS
# =============================================================================

class ATCompanyRegistry:
    """
    Austrian Company Registry - Wrapper for FirmenABC.

    Provides company search, person search, and full profile retrieval.
    """

    def __init__(self):
        self._ingest = None
        self._db_path = None
        self._initialized = False

    def _lazy_init(self):
        """Lazy initialize FirmenABC ingestion."""
        if self._initialized:
            return

        try:
            from .firmenabc_api import FirmenABCIngest, IngestConfig

            # Use a temp database for search results
            self._db_path = f"/tmp/at_company_registry_{datetime.now().strftime('%Y%m%d')}.db"

            config = IngestConfig(
                project="at_company_search",
                db_path=self._db_path,
                concurrency=10,
                timeout=30.0,
            )
            self._ingest = FirmenABCIngest(config)
            logger.info(f"ATCompanyRegistry initialized with DB: {self._db_path}")

        except ImportError as e:
            logger.warning(f"FirmenABC ingestion not available: {e}")

        self._initialized = True

    async def search(self, query: str, direct: bool = False, max_results: int = 20) -> Dict[str, Any]:
        """
        Search Austrian companies.

        Args:
            query: Company name or partial name
            direct: If True, bypass FirmenABC and use direct Firmenbuch (not implemented)
            max_results: Maximum results to return

        Returns:
            Dict with companies, persons, and metadata
        """
        self._lazy_init()

        result = {
            'companies': [],
            'persons': [],
            'sources_queried': ['firmenabc'],
            'sources_succeeded': [],
            'errors': [],
        }

        if not self._ingest:
            result['errors'].append("FirmenABC ingestion not available")
            return result

        try:
            # Build FirmenABC search URL
            import aiohttp

            search_url = f"https://www.firmenabc.at/result.aspx?what={query.replace(' ', '+')}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    headers={'User-Agent': self._ingest.cfg.user_agent},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        result['errors'].append(f"FirmenABC search returned {resp.status}")
                        return result

                    html = await resp.text()

            # Parse search results
            from .firmenabc_api import BeautifulSoup, iter_jsonld_blocks, extract_company_from_jsonld

            if BeautifulSoup:
                try:
                    soup = BeautifulSoup(html, 'lxml')
                except Exception:
                    soup = BeautifulSoup(html, 'html.parser')

                # Find company links in search results
                company_links = []
                for a in soup.find_all('a', href=True):
                    href = a.get('href', '')
                    # FirmenABC company URLs have a specific pattern
                    if re.match(r'^/[a-z0-9-]+_[A-Za-z0-9]+$', href):
                        full_url = f"https://www.firmenabc.at{href}"
                        if full_url not in company_links:
                            company_links.append(full_url)
                        if len(company_links) >= max_results:
                            break

                # Fetch each company page
                for url in company_links[:max_results]:
                    try:
                        company_data = await self._fetch_company_page(url)
                        if company_data:
                            result['companies'].append(company_data)
                    except Exception as e:
                        logger.debug(f"Error fetching {url}: {e}")

            result['sources_succeeded'].append('firmenabc')

        except Exception as e:
            result['errors'].append(f"FirmenABC search failed: {str(e)}")
            logger.error(f"ATCompanyRegistry search error: {e}")

        return result

    async def search_person(self, query: str, max_results: int = 50) -> Dict[str, Any]:
        """
        Search Austrian persons (directors, shareholders).

        Args:
            query: Person name
            max_results: Maximum results

        Returns:
            Dict with persons and metadata
        """
        self._lazy_init()

        result = {
            'persons': [],
            'sources_queried': ['firmenabc_shareholders'],
            'sources_succeeded': [],
            'errors': [],
        }

        if not self._ingest:
            result['errors'].append("FirmenABC ingestion not available")
            return result

        try:
            import aiohttp

            # Search FirmenABC person pages
            search_url = f"https://www.firmenabc.at/personen?q={query.replace(' ', '+')}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    headers={'User-Agent': self._ingest.cfg.user_agent},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        result['errors'].append(f"FirmenABC person search returned {resp.status}")
                        return result

                    html = await resp.text()

            # Parse person results
            from .firmenabc_api import BeautifulSoup

            if BeautifulSoup:
                try:
                    soup = BeautifulSoup(html, 'lxml')
                except Exception:
                    soup = BeautifulSoup(html, 'html.parser')

                # Find person links
                for a in soup.find_all('a', href=True):
                    href = a.get('href', '')
                    if '/person/' in href:
                        person_name = a.get_text(strip=True)
                        if person_name and query.lower() in person_name.lower():
                            result['persons'].append({
                                'name': person_name,
                                'url': f"https://www.firmenabc.at{href}" if href.startswith('/') else href,
                                'source': 'firmenabc'
                            })
                            if len(result['persons']) >= max_results:
                                break

            result['sources_succeeded'].append('firmenabc_shareholders')

        except Exception as e:
            result['errors'].append(f"FirmenABC person search failed: {str(e)}")
            logger.error(f"ATCompanyRegistry person search error: {e}")

        return result

    async def get_full_profile(self, identifier: str) -> Optional[ATCompany]:
        """
        Get full company profile.

        Args:
            identifier: FN number (e.g., "FN 33209 m") or FirmenABC URL

        Returns:
            ATCompany with full details
        """
        self._lazy_init()

        if not self._ingest:
            return None

        try:
            # If identifier is a URL, fetch directly
            if identifier.startswith('http'):
                url = identifier
            else:
                # Search for FN number
                search_result = await self.search(identifier, max_results=1)
                if search_result['companies']:
                    company = search_result['companies'][0]
                    url = company.get('firmenabc_url')
                    if not url:
                        return ATCompany(
                            name=company.get('name', ''),
                            fn_number=company.get('fn_number'),
                            uid=company.get('uid'),
                            status=company.get('status'),
                            legal_form=company.get('legal_form'),
                            address=company.get('address'),
                            sources=['firmenabc'],
                            raw=company,
                        )
                else:
                    return None

            # Fetch full company page
            company_data = await self._fetch_company_page(url, full_profile=True)
            if not company_data:
                return None

            return ATCompany(
                name=company_data.get('name', ''),
                fn_number=company_data.get('fn_number'),
                uid=company_data.get('uid'),
                status=company_data.get('status'),
                legal_form=company_data.get('legal_form'),
                address=company_data.get('address'),
                postal_code=company_data.get('postal_code'),
                city=company_data.get('city'),
                phone=company_data.get('phone'),
                email=company_data.get('email'),
                website=company_data.get('website'),
                founding_date=company_data.get('founding_date'),
                business_activity=company_data.get('business_activity'),
                firmenabc_url=url,
                officers=company_data.get('officers', []),
                shareholders=company_data.get('shareholders', []),
                sources=['firmenabc'],
                raw=company_data,
            )

        except Exception as e:
            logger.error(f"Error getting full profile for {identifier}: {e}")
            return None

    async def _fetch_company_page(self, url: str, full_profile: bool = False) -> Optional[Dict]:
        """Fetch and parse a FirmenABC company page."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={'User-Agent': self._ingest.cfg.user_agent if self._ingest else 'Mozilla/5.0'},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return None
                    html = await resp.text()

            from .firmenabc_api import (
                iter_jsonld_blocks,
                extract_company_from_jsonld,
                extract_company_ids,
                extract_emails,
                extract_tel_links,
                extract_official_website,
                extract_founding_date,
                extract_legal_form,
                extract_business_activity,
                extract_company_shareholders,
                BeautifulSoup,
            )

            # Parse JSON-LD
            blocks = iter_jsonld_blocks(html)
            company_jsonld = extract_company_from_jsonld(blocks)

            if not company_jsonld:
                # Try to extract from HTML
                if BeautifulSoup:
                    try:
                        soup = BeautifulSoup(html, 'lxml')
                    except Exception:
                        soup = BeautifulSoup(html, 'html.parser')

                    h1 = soup.find('h1')
                    company_name = h1.get_text(strip=True) if h1 else None
                    if not company_name:
                        return None
                    company_jsonld = {'name': company_name}
                else:
                    return None

            # Extract additional data
            ids = extract_company_ids(html)
            emails = extract_emails(html)
            phones = extract_tel_links(html)
            website = extract_official_website(html)
            founding_date = extract_founding_date(html)
            legal_form = extract_legal_form(html)
            business_activity = extract_business_activity(html)

            # Build result
            result = {
                'name': company_jsonld.get('name', ''),
                'fn_number': ids.get('fn'),
                'uid': ids.get('uid'),
                'firmenabc_nr': ids.get('firmenabc_nr'),
                'address': company_jsonld.get('address', {}).get('street') if company_jsonld.get('address') else None,
                'postal_code': company_jsonld.get('address', {}).get('postal') if company_jsonld.get('address') else None,
                'city': company_jsonld.get('address', {}).get('city') if company_jsonld.get('address') else None,
                'phone': phones[0] if phones else company_jsonld.get('telephone'),
                'email': emails[0] if emails else None,
                'website': website or company_jsonld.get('url'),
                'founding_date': founding_date,
                'legal_form': legal_form,
                'business_activity': business_activity,
                'firmenabc_url': url,
                'source': 'firmenabc',
            }

            # Extract shareholders/officers for full profile
            if full_profile:
                shareholders = extract_company_shareholders(html)
                result['shareholders'] = shareholders
                result['officers'] = [s for s in shareholders if s.get('role') in ['managing_director', 'board_member', 'director']]

            return result

        except Exception as e:
            logger.debug(f"Error fetching company page {url}: {e}")
            return None


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Austria Company Registry - Search Austrian companies")
    parser.add_argument("query", help="Company name or FN number to search")
    parser.add_argument("--person", "-p", action="store_true", help="Search for persons instead of companies")
    parser.add_argument("--full", "-f", action="store_true", help="Get full profile")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    async def main():
        import json

        cr = ATCompanyRegistry()

        if args.full:
            result = await cr.get_full_profile(args.query)
            if result:
                if args.json:
                    print(json.dumps(result.__dict__, indent=2, default=str))
                else:
                    print(f"Name: {result.name}")
                    print(f"FN: {result.fn_number}")
                    print(f"UID: {result.uid}")
                    print(f"Legal Form: {result.legal_form}")
                    print(f"Address: {result.address}")
                    print(f"Phone: {result.phone}")
                    print(f"Website: {result.website}")
                    print(f"Shareholders: {len(result.shareholders)}")
            else:
                print("Company not found")
        elif args.person:
            result = await cr.search_person(args.query)
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Found {len(result['persons'])} persons:")
                for p in result['persons'][:10]:
                    print(f"  - {p.get('name')}")
        else:
            result = await cr.search(args.query)
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f"Found {len(result['companies'])} companies:")
                for c in result['companies'][:10]:
                    print(f"  - {c.get('name')} (FN: {c.get('fn_number')})")

    asyncio.run(main())
