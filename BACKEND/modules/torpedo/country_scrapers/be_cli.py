#!/usr/bin/env python3
"""
Belgium CLI - Belgian Public Records via KBO/BCE
=================================================
Uses KBO/BCE (Crossroads Bank for Enterprises) Public Search - FREE, no API key required.
Web Interface: https://kbopub.economie.fgov.be/

Also integrates:
- Belgian Official Gazette (Belgisch Staatsblad) - Capital/Share publications
- NBB Central Balance Sheet Office - Annual accounts with PDF extraction

OPERATOR SYNTAX:
    cbe: <company>      - Belgian company search by name or enterprise number

FLAGS:
    --max-pages N       - Max pages of Staatsblad results (default: 3)

USAGE:
    python be_cli.py "cbe: 0417497106"              # Full lookup with ownership
    python be_cli.py "cbe: AB InBev"                # Name search
    python be_cli.py "cbe: 0417497106" --max-pages 50  # All historical docs

FEATURES:
    - Company basic info (name, address, legal form, status)
    - Directors/Functions (names and appointment dates)
    - Financial info (capital, fiscal year)
    - NACE activity codes
    - Capital/Share publications from Official Gazette (automatic for number lookups)
    - AI-powered ownership analysis from documents (automatic for number lookups)
"""

import asyncio
import aiohttp
import json
import re
import sys
import os
import logging
import io
import base64
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger("be_unified_cli")

# PDF extraction libraries
try:
    import fitz  # pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

# Claude/Anthropic for AI extraction
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Load environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "BACKEND" / "modules"))

# Load .env file for API keys
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # dotenv not installed


@dataclass
class BESearchResult:
    """Result from Belgian company search."""
    query: str
    query_type: str  # 'name' or 'number'
    source: str = "KBO/BCE Public Search"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Company data
    companies: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    total_results: int = 0
    search_duration_ms: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "companies": self.companies,
            "total_results": self.total_results,
            "search_duration_ms": self.search_duration_ms,
            "errors": self.errors
        }


# =============================================================================
# BELGIUM OPERATOR DEFINITIONS
# =============================================================================

BE_OPERATORS = {
    'cbe:': {
        'name': 'Belgium Company Search',
        'entity_type': 'company',
        'sources': ['kbo_bce'],
        'description': 'Search Belgian company registry (KBO/BCE)',
    },
    'pbe:': {
        'name': 'Belgium Person Search',
        'entity_type': 'person',
        'sources': ['kbo_bce'],
        'description': 'Search Belgian directors/officers',
    },
    'regbe:': {
        'name': 'Belgium Regulatory',
        'entity_type': 'company',
        'sources': ['fsma'],
        'description': 'Search Belgian financial regulator (FSMA)',
    },
    'litbe:': {
        'name': 'Belgium Litigation',
        'entity_type': 'case',
        'sources': ['staatsblad'],
        'description': 'Search Belgian Official Gazette for court notices',
    },
    'propbe:': {
        'name': 'Belgium Property',
        'entity_type': 'property',
        'sources': ['kadaster'],
        'description': 'Search Belgian land registry',
    },
    'crbe:': {
        'name': 'Belgium Registry Lookup',
        'entity_type': 'company',
        'sources': ['kbo_bce'],
        'description': 'Direct enterprise number lookup',
    },
    'wikibe:': {
        'name': 'BE Wiki Sources',
        'entity_type': 'source',
        'category': 'wiki',
        'sources': ['wiki_sections', 'edith_injections'],
        'description': 'Belgian jurisdiction guides, tips, source intelligence',
    },
    'newsbe:': {
        'name': 'BE News Search',
        'entity_type': 'article',
        'category': 'news',
        'sources': ['news_recipes', 'torpedo_news'],
        'description': 'Search Belgian news sites via Torpedo',
    },
    'tmplbe:': {
        'name': 'BE EDITH Templates',
        'entity_type': 'template',
        'category': 'templates',
        'sources': ['edith_templates'],
        'description': 'Belgian writing templates for reports (KBO, FSMA)',
    },
}


def get_be_operators() -> Dict:
    """Return all Belgian operators."""
    return BE_OPERATORS


def has_be_operator(query: str) -> bool:
    """Check if query contains a Belgian operator."""
    query_lower = query.lower().strip()
    return any(query_lower.startswith(op) for op in BE_OPERATORS.keys())


async def execute_be_query(query: str) -> 'BESearchResult':
    """Execute a Belgian query and return results."""
    cli = BECLI()
    return await cli.execute(query)


class BECLI:
    """
    Belgian company search via KBO/BCE Public Search.
    No API key required - scrapes public web interface.
    """

    def __init__(self):
        self.base_url = "https://kbopub.economie.fgov.be/kbopub"
        self.staatsblad_url = "https://www.ejustice.just.fgov.be/cgi_tsv"
        self.nbb_url = "https://consult.cbso.nbb.be"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        # Wiki/News/Templates bridges (lazy loaded)
        self._wiki = None
        self._news = None
        self._templates = None

    async def execute(self, query: str, max_pages: int = 3) -> BESearchResult:
        """
        Execute Belgian company search with ownership extraction.

        For enterprise number lookups, automatically fetches Staatsblad documents
        and extracts ownership data.

        Also routes to wiki, news, and template bridges for respective operators.
        """
        start_time = datetime.now(timezone.utc)

        # Parse query - check for operator prefix
        clean_query = query.strip()
        query_lower = clean_query.lower()

        # Route to wiki/news/template bridges first
        if query_lower.startswith('wikibe:'):
            clean_query = clean_query[7:].strip()
            result = BESearchResult(query=clean_query, query_type='wiki')
            await self._execute_wiki_search(clean_query, result)
            end_time = datetime.now(timezone.utc)
            result.search_duration_ms = int((end_time - start_time).total_seconds() * 1000)
            result.total_results = len(result.companies)
            return result

        if query_lower.startswith('newsbe:'):
            clean_query = clean_query[7:].strip()
            result = BESearchResult(query=clean_query, query_type='news')
            await self._execute_news_search(clean_query, result)
            end_time = datetime.now(timezone.utc)
            result.search_duration_ms = int((end_time - start_time).total_seconds() * 1000)
            result.total_results = len(result.companies)
            return result

        if query_lower.startswith('tmplbe:'):
            clean_query = clean_query[7:].strip()
            result = BESearchResult(query=clean_query, query_type='templates')
            await self._execute_template_search(clean_query, result)
            end_time = datetime.now(timezone.utc)
            result.search_duration_ms = int((end_time - start_time).total_seconds() * 1000)
            result.total_results = len(result.companies)
            return result

        # Remove company search operator prefixes
        for prefix in ['cbe:', 'CBE:', 'crbe:', 'CRBE:']:
            if clean_query.lower().startswith(prefix.lower()):
                clean_query = clean_query[len(prefix):].strip()
                break

        # Determine if query is enterprise number or name
        number_pattern = re.compile(r'^[0-9.\s]+$')
        clean_number = re.sub(r'[.\s]', '', clean_query)

        if number_pattern.match(clean_query) and len(clean_number) >= 9:
            query_type = 'number'
            if len(clean_number) == 9:
                clean_number = '0' + clean_number
            result = BESearchResult(query=clean_query, query_type=query_type)
            await self._search_by_number(clean_number, result)

            # Auto-fetch ownership documents for enterprise number lookups
            if result.companies:
                company = result.companies[0]

                # Fetch Staatsblad documents (default 3 pages = ~60 docs)
                staatsblad_docs = await self._fetch_staatsblad_documents(clean_number, max_pages=max_pages)

                # Extract text from documents
                for doc in staatsblad_docs:
                    if doc.get('pdf_content'):
                        text = await self._extract_pdf_text(doc['pdf_content'])
                        doc['extracted_text'] = text
                        doc['text_length'] = len(text) if text else 0

                # Extract ownership with Claude
                if any(d.get('extracted_text') for d in staatsblad_docs):
                    ownership_data = await self._extract_ownership_with_claude(
                        staatsblad_docs, company.get('name', '')
                    )
                    company['ownership_data'] = ownership_data

                # Add document info (without binary content)
                company['documents'] = staatsblad_docs
                company['document_count'] = len(staatsblad_docs)
        else:
            query_type = 'name'
            result = BESearchResult(query=clean_query, query_type=query_type)
            await self._search_by_name(clean_query, result)

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        result.search_duration_ms = int((end_time - start_time).total_seconds() * 1000)
        result.total_results = len(result.companies)

        return result

    async def _search_by_number(self, number: str, result: BESearchResult):
        """Search by enterprise number - direct lookup."""
        url = f"{self.base_url}/toonondernemingps.html?ondernemingsnummer={number}&lang=en"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, timeout=30) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        company = self._parse_company_page(html, number)
                        if company:
                            # Add NBB annual accounts URL
                            company['nbb_url'] = self._get_nbb_url(number)

                            # Add Staatsblad search URL for capital/share publications
                            company['staatsblad_url'] = self._get_staatsblad_url(number)

                            result.companies.append(company)
                    else:
                        result.errors.append(f"HTTP {resp.status} for enterprise number {number}")
            except Exception as e:
                result.errors.append(f"Error fetching {number}: {str(e)}")

    async def _search_by_name(self, name: str, result: BESearchResult):
        """Search by company name - returns list of matches."""
        # 1. JESTER scraping via Torpedo.search_cr (PRIMARY - KBO)
        try:
            from TORPEDO.torpedo import Torpedo
            torpedo = Torpedo()
            await torpedo.load_sources()

            cr_result = await torpedo.search_cr(name, 'BE')
            if cr_result.get('success') and cr_result.get('profile'):
                profile = cr_result['profile']
                result.companies.append({
                    'name': profile.get('company_name', name),
                    'enterprise_number': profile.get('enterprise_number', ''),
                    'status': profile.get('status', ''),
                    'source': 'kbo_jester',
                    'profile_url': cr_result.get('profile_url', ''),
                    'scrape_method': cr_result.get('scrape_method', ''),
                })
                return  # JESTER worked
        except Exception as e:
            logger.warning(f"JESTER search_cr failed: {e}")

        # 2. KBO website scraping fallback
        url = f"{self.base_url}/zoekwoordaliasaliasaliasaliasform.html"

        async with aiohttp.ClientSession() as session:
            try:
                # POST search with form data
                form_data = {
                    'searchWord': name,
                    'pstcdeNPRP': '',
                    'rechtession': '',
                    'ondession': 'true',
                }

                async with session.post(url, data=form_data, headers=self.headers, timeout=30, allow_redirects=True) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        companies = self._parse_search_results(html)

                        # Fetch details for top results (max 10)
                        for company in companies[:10]:
                            if 'enterprise_number' in company:
                                detail = await self._fetch_company_details(session, company['enterprise_number'])
                                if detail:
                                    company.update(detail)

                        result.companies = companies
                    else:
                        result.errors.append(f"HTTP {resp.status} searching for '{name}'")
            except Exception as e:
                result.errors.append(f"Error searching '{name}': {str(e)}")

    async def _search_opencorporates(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search OpenCorporates via Torpedo + BrightData.
        This is the most reliable source for Belgian company searches.
        """
        try:
            from TORPEDO.torpedo import Torpedo
            torpedo = Torpedo()
            await torpedo.load_sources()

            # Use fetch_opencorporates with BE jurisdiction
            oc_result = await torpedo.fetch_opencorporates(query, 'BE')

            if oc_result.get('success') and oc_result.get('companies'):
                results = []
                for company in oc_result['companies'][:limit]:
                    # Extract enterprise number from OC URL
                    # URLs like /companies/be/0417497106
                    oc_url = company.get('oc_url', '')
                    ent_num = ''
                    if '/be/' in oc_url:
                        ent_num = oc_url.split('/be/')[-1]

                    results.append({
                        'name': company.get('name', ''),
                        'enterprise_number': ent_num,
                        'status': company.get('status', ''),
                        'source': 'opencorporates',
                        'opencorporates_url': oc_url,
                    })

                logger.info(f"OpenCorporates found {len(results)} Belgian companies for '{query}'")
                return results

        except ImportError as e:
            logger.warning(f"Torpedo not available: {e}")
        except Exception as e:
            logger.warning(f"OpenCorporates search failed: {e}")

        return []

    async def _fetch_company_details(self, session: aiohttp.ClientSession, number: str) -> Optional[Dict]:
        """Fetch full company details."""
        url = f"{self.base_url}/toonondernemingps.html?ondernemingsnummer={number}&lang=en"

        try:
            async with session.get(url, headers=self.headers, timeout=30) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    return self._parse_company_page(html, number)
        except:
            pass
        return None

    def _parse_search_results(self, html: str) -> List[Dict]:
        """Parse search results page."""
        soup = BeautifulSoup(html, 'html.parser')
        companies = []

        # Find result table rows
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                link = row.find('a', href=True)
                if link and 'ondernemingsnummer' in link.get('href', ''):
                    # Extract enterprise number from link
                    href = link['href']
                    match = re.search(r'ondernemingsnummer=(\d+)', href)
                    if match:
                        company = {
                            'enterprise_number': match.group(1),
                            'name': link.get_text(strip=True)
                        }
                        companies.append(company)

        return companies

    def _parse_company_page(self, html: str, number: str) -> Optional[Dict]:
        """Parse company details page."""
        soup = BeautifulSoup(html, 'html.parser')

        # Check for error
        if 'Wrong or missing parameter' in html:
            return None

        company = {
            'enterprise_number': number,
            'source_url': f"{self.base_url}/toonondernemingps.html?ondernemingsnummer={number}&lang=en"
        }

        # Parse table rows
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)

                if 'enterprise number' in label:
                    company['enterprise_number_formatted'] = value.split('\n')[0].strip()
                elif 'status' in label and 'legal' not in label:
                    company['status'] = value
                elif 'legal situation' in label:
                    company['legal_situation'] = value.split('\n')[0].strip()
                elif 'start date' in label:
                    company['start_date'] = value.split('\n')[0].strip()
                elif 'name' in label and 'abbreviation' not in label:
                    # Get primary name
                    names = value.split('\n')
                    company['name'] = names[0].strip() if names else value
                    company['all_names'] = [n.strip() for n in names if n.strip() and 'since' not in n.lower()]
                elif 'abbreviation' in label:
                    company['abbreviation'] = value.split('\n')[0].strip()
                elif 'address' in label and 'web' not in label and 'email' not in label:
                    company['address'] = value.replace('\n', ', ').strip()
                elif 'entity type' in label:
                    company['entity_type'] = value
                elif 'legal form' in label:
                    company['legal_form'] = value.split('\n')[0].strip()
                elif 'capital' in label:
                    company['capital'] = value
                elif 'annual assembly' in label:
                    company['annual_assembly_month'] = value
                elif 'end date financial year' in label:
                    company['financial_year_end'] = value

        # Parse directors/functions
        # Method 1: Hidden table with id="toonfctie" (for NV/SA companies)
        # Method 2: Directly in main table after "Functions" header (for BV companies)
        directors = []

        # Try hidden functions table first (NV companies)
        functions_table = soup.find('table', {'id': 'toonfctie'})
        if functions_table:
            for row in functions_table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 3:
                    role = cells[0].get_text(strip=True)
                    name = cells[1].get_text(strip=True)
                    date_info = cells[2].get_text(strip=True)

                    if role and name:
                        directors.append({
                            'role': role,
                            'name': name,
                            'since': date_info.replace('Since ', '').strip()
                        })

        # If no directors found, try main table (BV companies)
        if not directors:
            functions_header = soup.find('h2', string=re.compile('Functions', re.I))
            if functions_header:
                # Find the parent row and look at following rows
                parent_tr = functions_header.find_parent('tr')
                if parent_tr:
                    for sibling in parent_tr.find_next_siblings('tr'):
                        cells = sibling.find_all('td')
                        if len(cells) >= 3:
                            role = cells[0].get_text(strip=True)
                            name = cells[1].get_text(strip=True)
                            date_info = cells[2].get_text(strip=True)

                            # Check if this is a director-type role
                            if role and name and any(r in role.lower() for r in ['director', 'manager', 'gérant', 'bestuurder', 'administrateur']):
                                directors.append({
                                    'role': role,
                                    'name': name,
                                    'since': date_info.replace('Since ', '').strip()
                                })
                        # Stop when we hit another section header
                        if cells and cells[0].find('h2'):
                            break

        if directors:
            company['directors'] = directors
            company['director_count'] = len(directors)

        # Parse NACE codes
        nace_codes = []
        for row in soup.select('table tr'):
            text = row.get_text()
            if 'VAT' in text or 'NSSO' in text:
                # Look for NACE code pattern
                match = re.search(r'(\d{2}\.\d{3})', text)
                if match:
                    code = match.group(1)
                    # Get description
                    desc_match = re.search(r'\d{2}\.\d{3}\s*-\s*([^\n]+)', text)
                    nace_codes.append({
                        'code': code,
                        'description': desc_match.group(1).strip() if desc_match else ''
                    })

        if nace_codes:
            # Deduplicate
            seen = set()
            unique_codes = []
            for nc in nace_codes:
                if nc['code'] not in seen:
                    seen.add(nc['code'])
                    unique_codes.append(nc)
            company['nace_codes'] = unique_codes

        return company if 'name' in company else None

    def _get_staatsblad_url(self, number: str) -> str:
        """
        Generate URL to search Belgian Official Gazette (Staatsblad) for capital/share publications.
        The Staatsblad contains over 1 million "kapitaal-aandelen" publications including:
        - Founding shareholders (in articles of association)
        - Capital increases/decreases
        - Share transfers requiring notarial acts
        """
        clean_number = number.replace('.', '').replace(' ', '')
        # Link to the new Staatsblad search interface pre-filled with enterprise number
        return f"https://www.ejustice.just.fgov.be/cgi_tsv_pub/welcome.pl?language=nl&btw={clean_number}"

    def _get_nbb_url(self, number: str) -> str:
        """Generate NBB annual accounts URL for a company."""
        clean_number = number.replace('.', '').replace(' ', '')
        return f"{self.nbb_url}/?onderession={clean_number}"

    # ==================== DOCUMENT EXTRACTION METHODS ====================

    async def execute_document_extraction(self, query: str, max_pages: int = 10) -> BESearchResult:
        """
        Execute document extraction for Belgian company.
        Fetches NBB annual accounts and Staatsblad publications, extracts ownership data.

        Args:
            query: Enterprise number (with optional cbe: prefix)
            max_pages: Maximum pages of Staatsblad results to fetch (default 10)
        """
        start_time = datetime.now(timezone.utc)

        # Parse query - remove operator prefix
        clean_query = query.strip()
        for prefix in ['cbe:', 'CBE:']:
            if clean_query.lower().startswith(prefix.lower()):
                clean_query = clean_query[len(prefix):].strip()
                break

        # Normalize enterprise number
        clean_number = re.sub(r'[.\s]', '', clean_query)
        if len(clean_number) == 9:
            clean_number = '0' + clean_number

        result = BESearchResult(query=clean_query, query_type='document_extraction')

        # First get company info
        await self._search_by_number(clean_number, result)

        if not result.companies:
            result.errors.append(f"Company not found: {clean_number}")
            return result

        company = result.companies[0]

        # Fetch and analyze documents
        documents = []

        # 1. Fetch NBB annual accounts
        nbb_docs = await self._fetch_nbb_documents(clean_number)
        documents.extend(nbb_docs)

        # 2. Fetch Staatsblad publications (founding docs, capital changes)
        staatsblad_docs = await self._fetch_staatsblad_documents(clean_number, max_pages=max_pages)
        documents.extend(staatsblad_docs)

        # 3. Extract text from all PDFs
        for doc in documents:
            if doc.get('pdf_content'):
                text = await self._extract_pdf_text(doc['pdf_content'])
                doc['extracted_text'] = text
                doc['text_length'] = len(text) if text else 0

        # 4. Use Claude to extract ownership data
        ownership_data = await self._extract_ownership_with_claude(documents, company.get('name', ''))

        # Add to company data
        company['documents'] = documents
        company['document_count'] = len(documents)
        company['ownership_data'] = ownership_data

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        result.search_duration_ms = int((end_time - start_time).total_seconds() * 1000)
        result.total_results = len(result.companies)

        return result

    async def _fetch_nbb_documents(self, number: str) -> List[Dict]:
        """
        Fetch NBB annual accounts documents.
        NBB provides annual accounts which may include shareholder structure in section 5.1.
        """
        documents = []

        # NBB API for annual accounts listing
        # The public search interface at consult.cbso.nbb.be
        api_url = f"https://consult.cbso.nbb.be/api/v1/enterprise/{number}/accounts"

        async with aiohttp.ClientSession() as session:
            try:
                # First try to get the list of available accounts
                async with session.get(api_url, headers=self.headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        accounts = data.get('accounts', [])

                        # Fetch the most recent 3 annual accounts
                        for acc in accounts[:3]:
                            account_id = acc.get('id')
                            if account_id:
                                pdf_url = f"https://consult.cbso.nbb.be/api/v1/account/{account_id}/pdf"
                                pdf_doc = await self._download_pdf(session, pdf_url, f"NBB Annual Account {acc.get('year', 'Unknown')}")
                                if pdf_doc:
                                    pdf_doc['source'] = 'NBB'
                                    pdf_doc['year'] = acc.get('year')
                                    pdf_doc['type'] = 'annual_account'
                                    documents.append(pdf_doc)
                    else:
                        # Fallback: try direct XBRL viewer URL
                        viewer_url = f"https://consult.cbso.nbb.be/consult-enterprise/{number}"
                        documents.append({
                            'source': 'NBB',
                            'type': 'viewer_link',
                            'url': viewer_url,
                            'note': 'Direct PDF download requires browser authentication. Use viewer link.'
                        })
            except Exception as e:
                logger.warning(f"NBB API error for {number}: {e}")
                # Add fallback link
                documents.append({
                    'source': 'NBB',
                    'type': 'viewer_link',
                    'url': f"https://consult.cbso.nbb.be/consult-enterprise/{number}",
                    'note': f'API access failed: {str(e)}'
                })

        return documents

    async def _fetch_staatsblad_documents(self, number: str, max_pages: int = 10) -> List[Dict]:
        """
        Fetch Belgian Official Gazette (Staatsblad) publications.
        Contains founding documents, capital changes, share transfers.

        Uses POST to rech_res.pl with iso-8859-1 encoding.
        Document type c07 = "kapitaal - aandelen" (capital-shares) publications.

        Args:
            number: Enterprise number
            max_pages: Maximum pages to fetch (default 10, ~200 publications)
        """
        documents = []
        search_url = "https://www.ejustice.just.fgov.be/cgi_tsv/rech_res.pl"

        async with aiohttp.ClientSession() as session:
            page = 1
            found_on_page = True

            while page <= max_pages and found_on_page:
                found_on_page = False
                try:
                    # Search by enterprise number - form uses iso-8859-1
                    form_data = aiohttp.FormData()
                    form_data.add_field('btw', number)
                    form_data.add_field('naam', '')
                    form_data.add_field('postkode', '')
                    form_data.add_field('localite', '')
                    form_data.add_field('akte', '')  # Empty = all document types
                    form_data.add_field('numpu', '')
                    form_data.add_field('language', 'nl')
                    if page > 1:
                        form_data.add_field('page', str(page))

                    headers = {
                        **self.headers,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    }

                    async with session.post(search_url, data=form_data, headers=headers, timeout=30) as resp:
                        if resp.status == 200:
                            # Handle iso-8859-1 encoding
                            content = await resp.read()
                            try:
                                html = content.decode('iso-8859-1')
                            except UnicodeDecodeError:
                                html = content.decode('latin-1', errors='ignore')

                            soup = BeautifulSoup(html, 'html.parser')

                            # Parse publication links - look for PDF links
                            pdf_links = soup.select('a[href*="pdf"], a[href*="tsv_l"]')

                            for link in pdf_links:
                                href = link.get('href', '')
                                if not href:
                                    continue

                                full_url = f"https://www.ejustice.just.fgov.be{href}" if href.startswith('/') else href

                                # Get context from parent row
                                row = link.find_parent('tr')
                                pub_date = ''
                                doc_type = ''
                                if row:
                                    cells = row.find_all('td')
                                    if len(cells) >= 2:
                                        pub_date = cells[0].get_text(strip=True)
                                        doc_type = cells[1].get_text(strip=True)[:50] if len(cells) > 1 else ''

                                # Try to download as PDF
                                pdf_doc = await self._download_pdf(session, full_url, f"Staatsblad {pub_date}")
                                if pdf_doc:
                                    pdf_doc['source'] = 'Staatsblad'
                                    pdf_doc['publication_date'] = pub_date
                                    pdf_doc['document_type'] = doc_type
                                    pdf_doc['type'] = 'official_publication'
                                    documents.append(pdf_doc)
                                    found_on_page = True

                            # Check for next page link
                            next_link = soup.select_one('a[href*="page"]')
                            if not next_link and not found_on_page:
                                break

                            page += 1
                        else:
                            break

                except Exception as e:
                    logger.warning(f"Staatsblad page {page} error for {number}: {e}")
                    break

            # If no documents found, add search link
            if not documents:
                documents.append({
                    'source': 'Staatsblad',
                    'type': 'search_link',
                    'url': self._get_staatsblad_url(number),
                    'note': 'No publications found via API. Try manual search.'
                })

        return documents

    async def _download_pdf(self, session: aiohttp.ClientSession, url: str, name: str) -> Optional[Dict]:
        """Download a PDF document."""
        try:
            async with session.get(url, headers=self.headers, timeout=60) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('Content-Type', '')
                    if 'pdf' in content_type.lower() or url.lower().endswith('.pdf'):
                        content = await resp.read()
                        return {
                            'name': name,
                            'url': url,
                            'pdf_content': content,
                            'size_bytes': len(content)
                        }
        except Exception as e:
            logger.warning(f"PDF download failed for {url}: {e}")
        return None

    async def _extract_pdf_text(self, pdf_content: bytes) -> str:
        """
        Extract text from PDF using multiple methods.
        Falls back through pymupdf -> pdfminer -> PyPDF2 -> Claude Vision OCR.
        """
        text = ""

        # Method 1: pymupdf (fitz) - best for most PDFs
        if PYMUPDF_AVAILABLE:
            try:
                with fitz.open(stream=pdf_content, filetype="pdf") as doc:
                    for page in doc:
                        text += page.get_text()
                if text.strip():
                    logger.info(f"Text extracted via pymupdf: {len(text)} chars")
                    return text
            except Exception as e:
                logger.warning(f"pymupdf failed: {e}")

        # Method 2: pdfminer - good for text-heavy PDFs
        if PDFMINER_AVAILABLE:
            try:
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                    tmp.write(pdf_content)
                    tmp.flush()
                    text = pdfminer_extract(tmp.name)
                    os.unlink(tmp.name)
                if text.strip():
                    logger.info(f"Text extracted via pdfminer: {len(text)} chars")
                    return text
            except Exception as e:
                logger.warning(f"pdfminer failed: {e}")

        # Method 3: PyPDF2 - fallback
        if PYPDF2_AVAILABLE:
            try:
                reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
                if text.strip():
                    logger.info(f"Text extracted via PyPDF2: {len(text)} chars")
                    return text
            except Exception as e:
                logger.warning(f"PyPDF2 failed: {e}")

        # Method 4: Claude Vision OCR for scanned documents
        if not text.strip() and ANTHROPIC_AVAILABLE:
            logger.info("All text extractors failed, trying Claude Vision OCR...")
            text = await self._ocr_with_claude_vision(pdf_content)

        return text

    async def _ocr_with_claude_vision(self, pdf_content: bytes) -> str:
        """
        Use Claude Vision to OCR scanned PDF pages.
        Converts PDF pages to images and sends to Claude.
        """
        if not ANTHROPIC_AVAILABLE:
            return ""

        if not PYMUPDF_AVAILABLE:
            logger.warning("pymupdf required for PDF-to-image conversion")
            return ""

        try:
            client = anthropic.Anthropic()
            all_text = []

            with fitz.open(stream=pdf_content, filetype="pdf") as doc:
                # Process first 10 pages max
                for page_num, page in enumerate(doc[:10]):
                    # Render page to image
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_bytes).decode()

                    # Send to Claude Vision
                    response = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=4000,
                        messages=[{
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": img_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": "Extract ALL text from this document page. Include all names, numbers, dates, and data. Output the raw text only, preserving structure."
                                }
                            ]
                        }]
                    )

                    page_text = response.content[0].text
                    all_text.append(f"=== Page {page_num + 1} ===\n{page_text}")

            return "\n\n".join(all_text)

        except Exception as e:
            logger.error(f"Claude Vision OCR failed: {e}")
            return ""

    async def _extract_ownership_with_claude(self, documents: List[Dict], company_name: str) -> Dict:
        """
        Use Claude to extract ownership/shareholder data from document text.
        """
        if not ANTHROPIC_AVAILABLE:
            return {"error": "Anthropic library not available"}

        # Collect all extracted text
        all_text = []
        for doc in documents:
            if doc.get('extracted_text'):
                source = doc.get('source', 'Unknown')
                doc_type = doc.get('type', 'document')
                all_text.append(f"=== {source} - {doc_type} ===\n{doc['extracted_text'][:15000]}")  # Limit per doc

        if not all_text:
            return {"error": "No text extracted from documents"}

        combined_text = "\n\n".join(all_text)[:50000]  # Total limit

        try:
            client = anthropic.Anthropic()

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze these Belgian company documents for {company_name} and extract ownership/shareholder information.

DOCUMENTS:
{combined_text}

Extract and return JSON with this structure:
{{
    "shareholders": [
        {{
            "name": "shareholder name",
            "shares": "number or percentage",
            "share_class": "type if mentioned (A, B, etc)",
            "since": "date if available",
            "nationality": "if mentioned"
        }}
    ],
    "share_capital": {{
        "amount": "total capital",
        "currency": "EUR",
        "shares_total": "total number of shares",
        "share_classes": ["list of share classes"]
    }},
    "founding_shareholders": [
        {{
            "name": "name",
            "initial_shares": "shares at founding",
            "contribution": "amount contributed"
        }}
    ],
    "capital_changes": [
        {{
            "date": "date",
            "type": "increase/decrease",
            "amount": "amount",
            "description": "brief description"
        }}
    ],
    "beneficial_owners": [
        {{
            "name": "name",
            "percentage": "ownership %",
            "type": "direct/indirect"
        }}
    ],
    "notes": "any relevant ownership notes"
}}

IMPORTANT:
- Extract ALL shareholder names found in the documents
- Include founding shareholders from articles of association
- Note any capital changes or share transfers
- Belgian BV companies must publish shareholder register
- NBB annual accounts section 5.1 contains shareholder structure
- Return valid JSON only"""
                }]
            )

            # Parse JSON response
            response_text = response.content[0].text

            # Try to extract JSON
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"raw_response": response_text, "error": "Could not parse JSON"}

        except Exception as e:
            logger.error(f"Claude ownership extraction failed: {e}")
            return {"error": str(e)}

    # ==================== END DOCUMENT EXTRACTION METHODS ====================

    def format_output(self, result: BESearchResult, json_output: bool = False) -> str:
        """Format search results for display."""
        if json_output:
            return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"BELGIUM KBO/BCE SEARCH RESULTS")
        lines.append(f"{'='*70}")
        lines.append(f"Query: {result.query}")
        lines.append(f"Type: {result.query_type}")
        lines.append(f"Results: {result.total_results}")
        lines.append(f"Duration: {result.search_duration_ms}ms")

        if result.errors:
            lines.append(f"\nErrors: {', '.join(result.errors)}")

        for i, company in enumerate(result.companies, 1):
            lines.append(f"\n{'-'*70}")
            lines.append(f"[{i}] {company.get('name', 'Unknown')}")
            lines.append(f"{'-'*70}")

            if 'enterprise_number_formatted' in company:
                lines.append(f"  Enterprise Number: {company['enterprise_number_formatted']}")
            elif 'enterprise_number' in company:
                lines.append(f"  Enterprise Number: {company['enterprise_number']}")

            if 'status' in company:
                lines.append(f"  Status: {company['status']}")
            if 'legal_form' in company:
                lines.append(f"  Legal Form: {company['legal_form']}")
            if 'address' in company:
                lines.append(f"  Address: {company['address']}")
            if 'start_date' in company:
                lines.append(f"  Founded: {company['start_date']}")
            if 'capital' in company:
                lines.append(f"  Capital: {company['capital']}")

            if 'directors' in company:
                lines.append(f"\n  Directors ({company.get('director_count', len(company['directors']))}):")
                for d in company['directors'][:10]:  # Show first 10
                    lines.append(f"    - {d['name']} ({d['role']}, since {d['since']})")
                if len(company['directors']) > 10:
                    lines.append(f"    ... and {len(company['directors']) - 10} more")

            if 'nace_codes' in company:
                lines.append(f"\n  Activities:")
                for nc in company['nace_codes'][:3]:
                    lines.append(f"    - {nc['code']}: {nc['description']}")

            if 'source_url' in company:
                lines.append(f"\n  Sources:")
                lines.append(f"    KBO: {company['source_url']}")
            if 'nbb_url' in company:
                lines.append(f"    NBB Annual Accounts: {company['nbb_url']}")
            if 'staatsblad_url' in company:
                lines.append(f"    Staatsblad (Capital/Share publications): {company['staatsblad_url']}")

            # Document extraction results
            if 'documents' in company:
                lines.append(f"\n  Documents Fetched ({company.get('document_count', 0)}):")
                for doc in company['documents']:
                    source = doc.get('source', 'Unknown')
                    doc_type = doc.get('type', 'document')
                    pub_date = doc.get('publication_date', '')
                    date_str = f" [{pub_date}]" if pub_date else ''
                    if doc.get('text_length'):
                        lines.append(f"    - {source}/{doc_type}{date_str}: {doc['text_length']:,} chars extracted")
                    elif doc.get('url'):
                        lines.append(f"    - {source}/{doc_type}{date_str}: {doc['url']}")
                    if doc.get('note'):
                        lines.append(f"      Note: {doc['note']}")

            # Ownership data from AI extraction
            if 'ownership_data' in company:
                ownership = company['ownership_data']
                if ownership.get('error'):
                    lines.append(f"\n  Ownership Extraction: {ownership['error']}")
                else:
                    lines.append(f"\n  EXTRACTED OWNERSHIP DATA:")

                    if ownership.get('share_capital'):
                        cap = ownership['share_capital']
                        lines.append(f"\n  Share Capital:")
                        if cap.get('amount'):
                            lines.append(f"    Amount: {cap['amount']} {cap.get('currency', 'EUR')}")
                        if cap.get('shares_total'):
                            lines.append(f"    Total Shares: {cap['shares_total']}")
                        if cap.get('share_classes'):
                            lines.append(f"    Share Classes: {', '.join(cap['share_classes'])}")

                    if ownership.get('shareholders'):
                        lines.append(f"\n  Shareholders ({len(ownership['shareholders'])}):")
                        for sh in ownership['shareholders'][:15]:
                            shares_info = sh.get('shares', '')
                            share_class = f" ({sh['share_class']})" if sh.get('share_class') else ''
                            since = f" since {sh['since']}" if sh.get('since') else ''
                            lines.append(f"    - {sh['name']}: {shares_info}{share_class}{since}")
                        if len(ownership['shareholders']) > 15:
                            lines.append(f"    ... and {len(ownership['shareholders']) - 15} more")

                    if ownership.get('founding_shareholders'):
                        lines.append(f"\n  Founding Shareholders:")
                        for fs in ownership['founding_shareholders'][:10]:
                            contrib = f" (contributed {fs['contribution']})" if fs.get('contribution') else ''
                            lines.append(f"    - {fs['name']}: {fs.get('initial_shares', 'N/A')} shares{contrib}")

                    if ownership.get('capital_changes'):
                        lines.append(f"\n  Capital Changes:")
                        for cc in ownership['capital_changes'][:5]:
                            lines.append(f"    - {cc.get('date', 'Unknown')}: {cc.get('type', '')} {cc.get('amount', '')}")
                            if cc.get('description'):
                                lines.append(f"      {cc['description']}")

                    if ownership.get('beneficial_owners'):
                        lines.append(f"\n  Beneficial Owners:")
                        for bo in ownership['beneficial_owners'][:10]:
                            bo_type = f" ({bo['type']})" if bo.get('type') else ''
                            lines.append(f"    - {bo['name']}: {bo.get('percentage', 'N/A')}{bo_type}")

                    if ownership.get('notes'):
                        lines.append(f"\n  Notes: {ownership['notes']}")

        lines.append(f"\n{'='*70}\n")
        return '\n'.join(lines)

    # =========================================================================
    # WIKI SEARCH (wikibe:)
    # =========================================================================

    def _get_wiki(self):
        """Lazy load BE wiki bridge."""
        if self._wiki is None:
            try:
                from .be_wiki import BEWiki
                self._wiki = BEWiki()
            except ImportError as e:
                logger.warning(f"BE Wiki not available: {e}")
        return self._wiki

    async def _execute_wiki_search(self, query: str, result: BESearchResult):
        """
        Get BE wiki sources and guides.

        Query can be:
        - Empty: Get all sections
        - Section code: cr, lit, reg, ass
        - Search term: Search wiki content
        """
        wiki = self._get_wiki()
        if not wiki:
            result.errors.append("BE Wiki bridge not available")
            return

        try:
            wiki_result = await wiki.execute(query)

            # Add wiki info to result
            wiki_info = {
                'sections': list(wiki_result.sections.keys()),
                'total_links': wiki_result.total_links,
                'sources_count': len(wiki_result.all_sources),
            }

            # Add wiki sources as documents
            documents = []
            for source in wiki_result.all_sources:
                documents.append({
                    'title': source.title,
                    'url': source.url,
                    'section': source.section,
                    'type': 'wiki_source',
                    'source': 'be_wiki'
                })

            if result.companies:
                result.companies[0]['wiki'] = wiki_info
                result.companies[0]['wiki_documents'] = documents
            else:
                # Create a placeholder result for wiki-only queries
                result.companies.append({
                    'name': f'BE Wiki: {query or "All Sections"}',
                    'wiki': wiki_info,
                    'wiki_documents': documents,
                })

        except Exception as e:
            result.errors.append(f"Wiki search failed: {e}")

    # =========================================================================
    # NEWS SEARCH (newsbe:)
    # =========================================================================

    def _get_news(self):
        """Lazy load BE news bridge."""
        if self._news is None:
            try:
                from .be_news import BENews
                self._news = BENews()
            except ImportError as e:
                logger.warning(f"BE News not available: {e}")
        return self._news

    async def _execute_news_search(self, query: str, result: BESearchResult):
        """
        Search Belgian news sites via Torpedo.

        Uses Belgian news site templates for targeted searching.
        """
        news = self._get_news()
        if not news:
            result.errors.append("BE News bridge not available")
            return

        try:
            news_result = await news.execute(query)

            # Add news info to result
            news_info = {
                'articles_count': len(news_result.articles),
                'sites_searched': news_result.sites_searched,
                'total_results': news_result.total_results,
            }

            # Add articles as documents
            documents = []
            for article in news_result.articles:
                documents.append({
                    'title': article.title,
                    'url': article.url,
                    'snippet': article.snippet,
                    'source_domain': article.source_domain,
                    'date': article.date,
                    'type': 'news_article',
                    'source': 'be_news'
                })

            if result.companies:
                result.companies[0]['news'] = news_info
                result.companies[0]['news_articles'] = documents
            else:
                # Create a placeholder result for news-only queries
                result.companies.append({
                    'name': f'BE News: {query}',
                    'news': news_info,
                    'news_articles': documents,
                })

            if news_result.errors:
                result.errors.extend(news_result.errors)

        except Exception as e:
            result.errors.append(f"News search failed: {e}")

    # =========================================================================
    # TEMPLATES (tmplbe:)
    # =========================================================================

    def _get_templates(self):
        """Lazy load BE templates bridge."""
        if self._templates is None:
            try:
                from .be_templates import BETemplates
                self._templates = BETemplates()
            except ImportError as e:
                logger.warning(f"BE Templates not available: {e}")
        return self._templates

    async def _execute_template_search(self, query: str, result: BESearchResult):
        """
        Get BE EDITH writing templates.

        Returns standard phrases, footnote formats, and report templates
        for Belgian jurisdiction.
        """
        templates = self._get_templates()
        if not templates:
            result.errors.append("BE Templates bridge not available")
            return

        try:
            template = await templates.execute(query)

            # Add template info to result
            template_info = {
                'jurisdiction': template.jurisdiction,
                'registries_count': len(template.registries),
                'standard_phrases_count': len(template.standard_phrases),
                'footnote_examples_count': len(template.footnote_examples),
                'arbitrage_routes_count': len(template.arbitrage_routes),
                'sources_count': len(template.sources),
                'has_content': bool(template.raw_content),
            }

            if result.companies:
                result.companies[0]['templates'] = template_info
                if template.raw_content:
                    result.companies[0]['template_content_preview'] = (
                        template.raw_content[:500] + '...'
                        if len(template.raw_content) > 500
                        else template.raw_content
                    )
            else:
                # Create a placeholder result for template-only queries
                result.companies.append({
                    'name': f'BE EDITH Templates',
                    'templates': template_info,
                    'template_content_preview': (
                        template.raw_content[:500] + '...'
                        if len(template.raw_content) > 500
                        else template.raw_content
                    ) if template.raw_content else None,
                })

        except Exception as e:
            result.errors.append(f"Template search failed: {e}")


async def main():
    """CLI entry point."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Belgium KBO/BCE Company Search')
    parser.add_argument('query', nargs='?', help='Search query (cbe: name or enterprise number)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--max-pages', type=int, default=3, help='Max pages of Staatsblad docs (default: 3)')
    parser.add_argument('--project', type=str, help='Project ID for graph persistence')
    parser.add_argument('--no-persist', action='store_true', help='Skip graph persistence')

    args = parser.parse_args()

    if not args.query:
        print("Usage: python be_cli.py 'cbe: <query>' [options]")
        print("\nOptions:")
        print("  --max-pages N    Max pages of Staatsblad results (default: 3)")
        print("  --project ID     Project ID for graph persistence")
        print("  --no-persist     Skip graph persistence")
        print("  --json           Output as JSON")
        print("\nExamples:")
        print("  python be_cli.py 'cbe: 0417497106'                          # Company + ownership")
        print("  python be_cli.py 'cbe: AB InBev'                            # Name search")
        print("  python be_cli.py 'cbe: 0417497106' --project myproject      # With graph persistence")
        print("  python be_cli.py 'cbe: 0417497106' --max-pages 20           # More docs")
        sys.exit(1)

    cli = BECLI()
    result = await cli.execute(args.query, max_pages=args.max_pages)

    # Persist to graph if project specified
    if args.project and not args.no_persist:
        try:
            # Import the graph adapter
            matrix_path = Path(__file__).resolve().parent.parent.parent.parent.parent / 'input_output' / 'matrix'
            sys.path.insert(0, str(matrix_path))
            from country_graph_adapter import CountryGraphAdapter

            adapter = CountryGraphAdapter(project_id=args.project)
            graph_result = adapter.from_be_result(result)

            print(f"\n{'='*70}")
            print(f"GRAPH CONVERSION")
            print(f"{'='*70}")
            print(f"Nodes created: {len(graph_result.nodes)}")
            print(f"Edges created: {len(graph_result.edges)}")

            # Show node breakdown
            node_types = {}
            for node in graph_result.nodes:
                t = node.node_type
                node_types[t] = node_types.get(t, 0) + 1
            for t, count in sorted(node_types.items()):
                print(f"  - {t}: {count}")

            # Show edge breakdown
            edge_types = {}
            for edge in graph_result.edges:
                t = edge.edge_type
                edge_types[t] = edge_types.get(t, 0) + 1
            for t, count in sorted(edge_types.items()):
                print(f"  - {t}: {count}")

            # Persist to Elasticsearch
            stats = await adapter.persist_to_elastic(graph_result, args.project)
            print(f"\nPersisted to cymonides-1-{args.project}:")
            print(f"  Nodes created: {stats['nodes_created']}")
            print(f"  Nodes updated: {stats['nodes_updated']}")
            print(f"  Edges embedded: {stats['edges_embedded']}")

        except Exception as e:
            print(f"\n[WARN] Graph persistence failed: {e}")
            import traceback
            traceback.print_exc()

    # Clean up binary data before JSON serialization
    if args.json:
        for company in result.companies:
            if 'documents' in company:
                for doc in company['documents']:
                    if 'pdf_content' in doc:
                        del doc['pdf_content']

    print(cli.format_output(result, json_output=args.json))


if __name__ == '__main__':
    asyncio.run(main())
