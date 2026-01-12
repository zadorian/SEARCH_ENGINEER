#!/usr/bin/env python3
"""
JESTER BLITZ + PACMAN - Maximum throughput domain intelligence

STRATEGY: Don't crawl when you can TARGET
- Skip link discovery: request known important paths directly
- Sitemap-first: one request can give 1000s of URLs
- Parallel everything: process 1000 domains simultaneously
- PACMAN inline: regex extraction adds <5ms/page

PERFORMANCE:
- Target: 1000+ pages/second sustained
- 2.85M domains × 15 paths = 42.75M requests
- At 1000/s = ~12 hours

Usage:
    python3 jester_blitz_pacman.py domains.txt --workers 1000
    python3 jester_blitz_pacman.py domains.txt --with-sitemaps  # Try sitemaps first
    python3 jester_blitz_pacman.py domains.txt --paths-only     # Skip sitemaps entirely
"""

import asyncio
import json
import sys
import re
import time
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import httpx
from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

# === PACMAN: names-dataset ===
try:
    from names_dataset import NameDataset
    _nd = NameDataset()
    HAS_NAMES = True
except ImportError:
    _nd = None
    HAS_NAMES = False

# === CONFIG ===
COLLY_BIN = Path("/data/SUBMARINE/bin/colly_crawler_linux")
ROD_BIN = Path("/data/SUBMARINE/bin/rod_crawler_linux")

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-blitz"

# Concurrency settings - AGGRESSIVE
CONCURRENT_DOMAINS = 500      # Process 500 domains simultaneously
CONCURRENT_REQUESTS = 2000    # Total HTTP connections
REQUESTS_PER_DOMAIN = 4       # Max concurrent requests per domain (politeness)

# === IMPORTANT PATHS FOR COMPANY INTELLIGENCE (MULTILINGUAL) ===
# These paths contain the highest-value information for investigations
# Covering: English, German, French, Spanish, Italian, Dutch, Portuguese, Polish, Hungarian, Croatian, Czech, Swedish, Norwegian, Danish, Finnish
IMPORTANT_PATHS = [
    # Homepage
    '/',

    # === ABOUT ===
    '/about', '/about-us', '/about-company', '/aboutus',
    # German
    '/ueber-uns', '/uber-uns', '/unternehmen', '/firma', '/wir-ueber-uns',
    # French
    '/a-propos', '/apropos', '/qui-sommes-nous', '/notre-societe', '/entreprise',
    # Spanish
    '/sobre-nosotros', '/quienes-somos', '/empresa', '/acerca-de',
    # Italian
    '/chi-siamo', '/azienda', '/societa',
    # Dutch
    '/over-ons', '/bedrijf',
    # Portuguese
    '/sobre-nos', '/quem-somos', '/a-empresa',
    # Polish
    '/o-nas', '/firma', '/o-firmie',
    # Hungarian
    '/rolunk', '/cegunk', '/bemutatkozas',
    # Croatian/Serbian
    '/o-nama', '/tvrtka',
    # Czech/Slovak
    '/o-nas', '/spolecnost', '/firma',
    # Nordic (Swedish, Norwegian, Danish)
    '/om-oss', '/om-os', '/foretaget', '/virksomheden', '/selskapet',
    # Finnish
    '/meista', '/yritys',

    # === TEAM / PEOPLE ===
    '/team', '/our-team', '/the-team', '/people', '/staff', '/employees',
    # German
    '/team', '/unser-team', '/mitarbeiter', '/mannschaft',
    # French
    '/equipe', '/notre-equipe', '/collaborateurs',
    # Spanish
    '/equipo', '/nuestro-equipo', '/personal',
    # Italian
    '/team', '/il-nostro-team', '/personale',
    # Dutch
    '/team', '/ons-team', '/medewerkers',
    # Portuguese
    '/equipe', '/equipa', '/nossa-equipe',
    # Polish
    '/zespol', '/nasz-zespol',
    # Hungarian
    '/csapat', '/csapatunk', '/munkatarsak',
    # Croatian
    '/tim', '/nas-tim',
    # Nordic
    '/team', '/vart-team', '/medarbetare', '/ansatte',

    # === LEADERSHIP / MANAGEMENT ===
    '/leadership', '/management', '/executives', '/board', '/board-of-directors', '/directors',
    # German
    '/geschaeftsfuehrung', '/geschaeftsleitung', '/vorstand', '/management', '/fuehrung', '/leitung',
    # French
    '/direction', '/equipe-dirigeante', '/dirigeants', '/conseil-administration',
    # Spanish
    '/direccion', '/directivos', '/equipo-directivo', '/consejo',
    # Italian
    '/direzione', '/management', '/consiglio',
    # Dutch
    '/directie', '/management', '/bestuur',
    # Portuguese
    '/direcao', '/gestao', '/diretoria',
    # Polish
    '/zarzad', '/kierownictwo', '/dyrekcja',
    # Hungarian
    '/vezetes', '/vezetoseg', '/igazgatosag',
    # Croatian
    '/vodstvo', '/uprava', '/menadzment',
    # Nordic
    '/ledelse', '/ledning', '/styrelse', '/bestyrelse',

    # === CONTACT ===
    '/contact', '/contact-us', '/contactus', '/get-in-touch',
    # German
    '/kontakt', '/kontaktieren',
    # French
    '/contact', '/contactez-nous', '/nous-contacter',
    # Spanish
    '/contacto', '/contactenos', '/contactar',
    # Italian
    '/contatti', '/contattaci',
    # Dutch
    '/contact', '/neem-contact-op',
    # Portuguese
    '/contato', '/contacto', '/fale-conosco',
    # Polish
    '/kontakt',
    # Hungarian
    '/kapcsolat', '/elerhetoseg',
    # Croatian
    '/kontakt',
    # Nordic
    '/kontakt', '/kontakta-oss',

    # === COMPANY INFO ===
    '/company', '/company-info', '/corporate',
    # German
    '/unternehmen', '/firma', '/gesellschaft',
    # French
    '/societe', '/entreprise',
    # Spanish
    '/empresa', '/compania',
    # Italian
    '/azienda', '/societa',
    # Dutch
    '/bedrijf',
    # Portuguese
    '/empresa',

    # === INVESTORS / PRESS ===
    '/investors', '/investor-relations', '/ir',
    '/press', '/news', '/newsroom', '/media',
    # German
    '/investoren', '/investor-relations', '/presse', '/aktuelles', '/neuigkeiten',
    # French
    '/investisseurs', '/presse', '/actualites', '/medias',
    # Spanish
    '/inversores', '/prensa', '/noticias', '/sala-de-prensa',
    # Italian
    '/investitori', '/stampa', '/notizie',
    # Dutch
    '/investeerders', '/pers', '/nieuws',
    # Nordic
    '/investerare', '/nyheter', '/pressrum',

    # === CAREERS ===
    '/careers', '/jobs', '/work-with-us', '/join-us',
    # German
    '/karriere', '/jobs', '/stellenangebote',
    # French
    '/carrieres', '/emplois', '/recrutement', '/rejoignez-nous',
    # Spanish
    '/carreras', '/empleo', '/trabaja-con-nosotros',
    # Italian
    '/lavora-con-noi', '/carriere',
    # Dutch
    '/vacatures', '/werken-bij',
    # Portuguese
    '/carreiras', '/vagas', '/trabalhe-conosco',
    # Polish
    '/kariera', '/praca',
    # Hungarian
    '/karrier', '/allasok',
    # Nordic
    '/karriar', '/lediga-jobb', '/jobb',

    # === LEGAL / IMPRINT (often has company registration!) ===
    '/imprint', '/impressum', '/legal', '/legal-notice',
    # German
    '/impressum', '/rechtliches',
    # French
    '/mentions-legales',
    # Spanish
    '/aviso-legal',
    # Italian
    '/note-legali',
    # Dutch
    '/juridisch',
]

# === PACMAN PATTERNS (compiled once) ===
# Includes company registration numbers for many jurisdictions
FAST_PATTERNS = {
    # === GLOBAL ===
    'LEI': re.compile(r'\b[A-Z0-9]{4}00[A-Z0-9]{12}\d{2}\b'),  # Legal Entity Identifier
    'IBAN': re.compile(r'\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b'),
    'BTC': re.compile(r'\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b'),
    'ETH': re.compile(r'\b(0x[a-fA-F0-9]{40})\b'),
    'IMO': re.compile(r'\bIMO[:\s]*(\d{7})\b', re.I),
    'EMAIL': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.I),
    'PHONE': re.compile(r'(?:\+|00)[\d\s\-\(\)]{10,20}'),

    # === COMPANY REGISTRATION NUMBERS BY JURISDICTION ===
    # UK - Companies House (8 digits, optional prefix)
    'UK_CRN': re.compile(r'\b(?:CRN|Company\s*(?:No|Number|Reg(?:istration)?)|Registered\s*(?:No|Number))[:\s]*([A-Z]{0,2}\d{6,8})\b', re.I),

    # Germany - Handelsregister (HRA/HRB + number)
    'DE_HRB': re.compile(r'\b(HR[AB])\s*(\d{4,6})\b', re.I),

    # France - SIREN/SIRET
    'FR_SIREN': re.compile(r'\b(?:SIREN|SIRET)[:\s]*(\d{9}(?:\d{5})?)\b', re.I),
    'FR_RCS': re.compile(r'\bRCS[:\s]*([A-Z]+)\s*(\d{9})\b', re.I),

    # Netherlands - KVK number
    'NL_KVK': re.compile(r'\b(?:KVK|KvK|Kvk)[:\s]*(\d{8})\b', re.I),

    # Belgium - BCE/KBO number
    'BE_BCE': re.compile(r'\b(?:BCE|KBO|BTW|TVA)[:\s]*(?:BE)?[\s]?(\d{4}[\.\s]?\d{3}[\.\s]?\d{3})\b', re.I),

    # Spain - CIF/NIF
    'ES_CIF': re.compile(r'\b(?:CIF|NIF)[:\s]*([A-Z]\d{7}[A-Z0-9])\b', re.I),

    # Italy - Partita IVA / Codice Fiscale
    'IT_PIVA': re.compile(r'\b(?:P\.?\s*IVA|Partita\s*IVA)[:\s]*(?:IT)?(\d{11})\b', re.I),
    'IT_REA': re.compile(r'\b(?:REA|C\.C\.I\.A\.A\.)[:\s]*([A-Z]{2})[:\s-]*(\d{5,7})\b', re.I),

    # Austria - FN (Firmenbuchnummer)
    'AT_FN': re.compile(r'\b(?:FN|Firmenbuch)[:\s]*(\d{5,6}[a-z]?)\b', re.I),

    # Switzerland - UID
    'CH_UID': re.compile(r'\b(?:UID|CHE)[:\s-]*(\d{3}[\.\s]?\d{3}[\.\s]?\d{3})\b', re.I),

    # Poland - KRS/NIP/REGON
    'PL_KRS': re.compile(r'\b(?:KRS)[:\s]*(\d{10})\b', re.I),
    'PL_NIP': re.compile(r'\b(?:NIP)[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2})\b', re.I),
    'PL_REGON': re.compile(r'\b(?:REGON)[:\s]*(\d{9}(?:\d{5})?)\b', re.I),

    # Czech Republic - ICO
    'CZ_ICO': re.compile(r'\b(?:IČO?|ICO)[:\s]*(\d{8})\b', re.I),

    # Hungary - Cégjegyzékszám
    'HU_CEGJSZ': re.compile(r'\b(?:Cg\.|Cégjegyzék)[:\s]*(\d{2}-\d{2}-\d{6})\b', re.I),

    # Croatia - OIB
    'HR_OIB': re.compile(r'\b(?:OIB)[:\s]*(\d{11})\b', re.I),
    'HR_MBS': re.compile(r'\b(?:MBS)[:\s]*(\d{11})\b', re.I),

    # Slovenia - Matična številka
    'SI_MAT': re.compile(r'\b(?:matična\s*št|mat\.?\s*št)[:\s]*(\d{7,10})\b', re.I),

    # Romania - CUI/CIF
    'RO_CUI': re.compile(r'\b(?:CUI|CIF|Cod\s*fiscal)[:\s]*(?:RO)?(\d{2,10})\b', re.I),

    # Bulgaria - EIK/BULSTAT
    'BG_EIK': re.compile(r'\b(?:EIK|BULSTAT|ЕИК)[:\s]*(\d{9,13})\b', re.I),

    # Nordic countries - Organization numbers
    'NO_ORGNR': re.compile(r'\b(?:Org\.?\s*nr\.?|organisasjonsnummer)[:\s]*(\d{9})\b', re.I),
    'SE_ORGNR': re.compile(r'\b(?:Org\.?\s*nr\.?|organisationsnummer)[:\s]*(\d{6}-?\d{4})\b', re.I),
    'DK_CVR': re.compile(r'\b(?:CVR)[:\s]*(\d{8})\b', re.I),
    'FI_YTUNNUS': re.compile(r'\b(?:Y-tunnus|FI)[:\s]*(\d{7}-?\d)\b', re.I),

    # Portugal - NIPC
    'PT_NIPC': re.compile(r'\b(?:NIPC|NIF)[:\s]*(\d{9})\b', re.I),

    # Greece - GEMI
    'GR_GEMI': re.compile(r'\b(?:ΓΕΜΗ|GEMI|ΑΦΜ)[:\s]*(\d{9,12})\b', re.I),

    # VAT numbers (generic pattern for EU)
    'VAT': re.compile(r'\b(?:VAT|TVA|BTW|MwSt|IVA|USt)[:\s]*([A-Z]{2}\d{8,12})\b', re.I),
}

NAME_PATTERN = re.compile(
    r'\b([A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+(?:\s+[A-ZÀ-ÖØ-ÞĀ-ŐŒ-Ž][a-zà-öø-ÿā-őœ-ž]+){1,2})\b'
)

NAME_EXCLUSIONS = {
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december',
    'american', 'british', 'german', 'french', 'italian', 'spanish', 'russian',
    'chinese', 'japanese', 'korean', 'indian', 'european', 'african', 'asian',
    'company', 'limited', 'incorporated', 'corporation', 'association', 'foundation',
    'terms', 'conditions', 'privacy', 'policy', 'copyright', 'reserved', 'rights',
    'contact', 'about', 'services', 'products', 'home', 'news', 'blog', 'press',
    'read', 'more', 'learn', 'click', 'here', 'view', 'see', 'get', 'find', 'search',
    'login', 'sign', 'register', 'subscribe', 'download', 'upload', 'share',
}

COMPANY_SUFFIXES = {
    'Ltd', 'LLC', 'Inc', 'Corp', 'GmbH', 'AG', 'SA', 'BV', 'Kft', 'NV', 'PLC',
    'Limited', 'Incorporated', 'Corporation', 'Company', 'Co', 'LLP', 'LP',
    'Pty', 'Pvt', 'Srl', 'SpA', 'AB', 'AS', 'Oy', 'ApS', 'SAS', 'SARL'
}

COMPANY_PATTERN = re.compile(
    rf'\b((?:[A-Z][A-Za-z0-9\-&]+\s*){{1,5}})({"|".join(COMPANY_SUFFIXES)})\b'
)

# Link extraction from HTML (for Tier A)
LINK_PATTERN = re.compile(r'href=["\']([^"\'#][^"\']*)["\']', re.I)


def extract_persons(text: str) -> List[str]:
    """Extract person names using names-dataset."""
    if not HAS_NAMES or not text:
        return []

    results = []
    seen = set()
    for match in NAME_PATTERN.finditer(text[:80000]):
        candidate = match.group(1)
        if candidate in seen:
            continue
        seen.add(candidate)

        words = candidate.split()
        if any(w.lower() in NAME_EXCLUSIONS for w in words):
            continue
        if len(words) < 2:
            continue

        result = _nd.search(words[0])
        if result and result.get('first_name'):
            results.append(candidate)
            if len(results) >= 30:
                break

    return results


def extract_companies(text: str) -> List[str]:
    """Extract company names."""
    if not text:
        return []

    results = []
    seen = set()
    for match in COMPANY_PATTERN.finditer(text[:80000]):
        company = (match.group(1).strip() + ' ' + match.group(2)).strip()
        if company not in seen and len(company) > 5:
            seen.add(company)
            results.append(company)
            if len(results) >= 20:
                break

    return results


def extract_fast(content: str) -> Dict[str, List[str]]:
    """PACMAN fast extraction - inline, no slowdown."""
    if not content:
        return {}

    entities = {}
    text = content[:100000]  # Limit scan size

    for name, pattern in FAST_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            entities[name] = list(set(matches))[:20]

    persons = extract_persons(text)
    if persons:
        entities['PERSON'] = persons

    companies = extract_companies(text)
    if companies:
        entities['COMPANY'] = companies

    return entities


def extract_links_from_html(html: str, base_url: str) -> List[str]:
    """Extract internal links from HTML (for Tier A without colly)."""
    if not html:
        return []

    try:
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc.lower().replace('www.', '')

        links = []
        seen = set()

        for match in LINK_PATTERN.finditer(html[:500000]):
            href = match.group(1)

            # Skip non-http
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:')):
                continue

            # Resolve relative URLs
            if href.startswith('/'):
                full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
            elif not href.startswith('http'):
                full_url = urljoin(base_url, href)
            else:
                full_url = href

            # Check if internal
            try:
                link_domain = urlparse(full_url).netloc.lower().replace('www.', '')
                if link_domain == base_domain and full_url not in seen:
                    seen.add(full_url)
                    links.append(full_url)
            except:
                pass

        return links[:100]  # Limit
    except:
        return []


async def parse_sitemap(content: str, base_url: str) -> List[str]:
    """Parse sitemap XML and extract URLs."""
    urls = []
    try:
        # Handle sitemap index
        if '<sitemapindex' in content:
            # Extract sitemap URLs from index
            for match in re.finditer(r'<loc>([^<]+)</loc>', content):
                urls.append(match.group(1))
        else:
            # Regular sitemap - extract page URLs
            for match in re.finditer(r'<loc>([^<]+)</loc>', content):
                url = match.group(1)
                # Filter to important paths
                path = urlparse(url).path.lower()
                if any(imp in path for imp in ['/about', '/team', '/contact', '/company',
                                                '/leader', '/manag', '/board', '/people',
                                                '/press', '/news', '/investor', '/career']):
                    urls.append(url)
    except:
        pass
    return urls[:50]  # Limit URLs per sitemap


@dataclass
class DomainResult:
    """Results for a single domain."""
    domain: str
    pages: List[dict] = field(default_factory=list)
    sitemap_urls: int = 0
    errors: int = 0

    def to_summary(self) -> dict:
        all_entities = defaultdict(list)
        for page in self.pages:
            for k, v in page.get('entities', {}).items():
                all_entities[k].extend(v)

        return {
            'domain': self.domain,
            'pages_scraped': len(self.pages),
            'sitemap_urls': self.sitemap_urls,
            'errors': self.errors,
            'entities': {k: list(set(v)) for k, v in all_entities.items()}
        }


class JesterBlitz:
    """Maximum throughput domain scraper."""

    def __init__(self, workers: int = CONCURRENT_DOMAINS, with_sitemaps: bool = True):
        self.workers = workers
        self.with_sitemaps = with_sitemaps

        # Stats
        self.stats = {
            'domains_processed': 0,
            'pages_scraped': 0,
            'sitemaps_found': 0,
            'errors': 0,
            'tier_a': 0,
            'tier_b': 0,
            'tier_c': 0,
        }

        # Rate limiting
        self.domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.global_sem = asyncio.Semaphore(CONCURRENT_REQUESTS)

        # HTTP client
        self.client: Optional[httpx.AsyncClient] = None

        # Results queue for ES indexing
        self.results_queue: asyncio.Queue = asyncio.Queue()
        self.indexing_done = False

    async def init_client(self):
        """Initialize HTTP client with optimized settings."""
        limits = httpx.Limits(
            max_connections=CONCURRENT_REQUESTS,
            max_keepalive_connections=500,
            keepalive_expiry=30
        )
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=limits,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; JESTER-Blitz/1.0; Research Bot)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )

    async def close(self):
        """Cleanup."""
        if self.client:
            await self.client.aclose()

    def get_domain_sem(self, domain: str) -> asyncio.Semaphore:
        """Get per-domain semaphore for politeness."""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(REQUESTS_PER_DOMAIN)
        return self.domain_semaphores[domain]

    async def fetch_url(self, url: str, domain: str) -> Optional[dict]:
        """Fetch single URL with rate limiting."""
        domain_sem = self.get_domain_sem(domain)

        async with self.global_sem:
            async with domain_sem:
                try:
                    start = time.time()
                    r = await self.client.get(url)
                    latency = int((time.time() - start) * 1000)

                    if r.status_code == 200 and len(r.text) > 100:
                        self.stats['tier_a'] += 1
                        return {
                            'url': str(r.url),
                            'input_url': url,
                            'domain': domain,
                            'status': r.status_code,
                            'content': r.text,
                            'content_length': len(r.text),
                            'latency_ms': latency,
                            'source': 'blitz_a',
                        }
                except httpx.TimeoutException:
                    pass
                except Exception as e:
                    pass

        self.stats['errors'] += 1
        return None

    async def fetch_with_colly(self, url: str, domain: str) -> Optional[dict]:
        """Fallback to colly for failed URLs."""
        if not COLLY_BIN.exists():
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                str(COLLY_BIN), "test", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)

            output = stdout.decode()
            json_start = output.find('{')
            if json_start >= 0:
                data = json.loads(output[json_start:])
                if data.get('status_code') == 200 and data.get('content'):
                    self.stats['tier_b'] += 1
                    return {
                        'url': data.get('url', url),
                        'input_url': url,
                        'domain': domain,
                        'status': 200,
                        'content': data['content'],
                        'content_length': len(data['content']),
                        'latency_ms': data.get('latency_ms', 0),
                        'source': 'blitz_b',
                        'internal_links': data.get('internal_links', []),
                    }
        except:
            pass
        return None

    async def fetch_sitemap(self, domain: str) -> List[str]:
        """Try to fetch and parse sitemap."""
        sitemap_urls = [
            f"https://{domain}/sitemap.xml",
            f"https://www.{domain}/sitemap.xml",
            f"https://{domain}/sitemap_index.xml",
        ]

        for sitemap_url in sitemap_urls:
            result = await self.fetch_url(sitemap_url, domain)
            if result and result.get('content'):
                urls = await parse_sitemap(result['content'], sitemap_url)
                if urls:
                    self.stats['sitemaps_found'] += 1
                    return urls

        return []

    async def process_domain(self, domain: str) -> DomainResult:
        """Process a single domain - sitemap + important paths."""
        result = DomainResult(domain=domain)
        urls_to_scrape = []

        # Normalize domain
        domain = domain.lower().replace('www.', '').strip()
        if not domain:
            return result

        # Step 1: Try sitemap (optional)
        if self.with_sitemaps:
            sitemap_urls = await self.fetch_sitemap(domain)
            if sitemap_urls:
                result.sitemap_urls = len(sitemap_urls)
                urls_to_scrape.extend(sitemap_urls)

        # Step 2: Add important paths
        for path in IMPORTANT_PATHS:
            url = f"https://{domain}{path}"
            if url not in urls_to_scrape:
                urls_to_scrape.append(url)

        # Also try with www
        www_url = f"https://www.{domain}/"
        if www_url not in urls_to_scrape:
            urls_to_scrape.insert(0, www_url)

        # Step 3: Scrape all URLs
        tasks = [self.fetch_url(url, domain) for url in urls_to_scrape[:30]]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 4: Process results + PACMAN
        for r in responses:
            if isinstance(r, dict) and r:
                # PACMAN extraction
                r['entities'] = extract_fast(r.get('content', ''))

                # Extract links for potential follow-up
                r['internal_links'] = extract_links_from_html(
                    r.get('content', ''), r.get('url', '')
                )

                result.pages.append(r)
                self.stats['pages_scraped'] += 1

                # Output progress
                entities = r.get('entities', {})
                entity_summary = {k: len(v) for k, v in entities.items() if v}
                if entity_summary:
                    print(json.dumps({
                        'domain': domain,
                        'url': r['url'],
                        'len': r['content_length'],
                        'entities': entity_summary
                    }), flush=True)

        self.stats['domains_processed'] += 1
        return result

    async def es_indexer(self, es: AsyncElasticsearch, index: str):
        """Background task to bulk index results."""
        batch = []
        batch_size = 500

        while not self.indexing_done or not self.results_queue.empty():
            try:
                result = await asyncio.wait_for(
                    self.results_queue.get(), timeout=1.0
                )

                for page in result.pages:
                    doc_id = f"blitz_{page['domain']}_{urlparse(page['url']).path.replace('/', '_')[:80]}"
                    batch.append({
                        "_index": index,
                        "_id": doc_id,
                        "_source": {
                            "domain": page.get('domain', ''),
                            "url": page.get('url', ''),
                            "path": urlparse(page.get('url', '')).path,
                            "source": page.get('source', ''),
                            "status": page.get('status', 0),
                            "content": page.get('content', '')[:50000],
                            "content_length": page.get('content_length', 0),
                            "latency_ms": page.get('latency_ms', 0),
                            "internal_links_count": len(page.get('internal_links', [])),
                            "entities": page.get('entities', {}),
                            "scraped_at": datetime.utcnow().isoformat()
                        }
                    })

                if len(batch) >= batch_size:
                    try:
                        success, _ = await async_bulk(es, batch, raise_on_error=False, stats_only=True)
                        print(f"[ES] Indexed {success} docs", file=sys.stderr)
                    except Exception as e:
                        print(f"[ES] Error: {e}", file=sys.stderr)
                    batch = []

            except asyncio.TimeoutError:
                continue

        # Final batch
        if batch:
            try:
                success, _ = await async_bulk(es, batch, raise_on_error=False, stats_only=True)
                print(f"[ES] Final batch: {success} docs", file=sys.stderr)
            except:
                pass

    async def run(self, domains: List[str], es_index: str = ES_INDEX, no_index: bool = False):
        """Main execution loop."""
        await self.init_client()

        # Init ES
        es = None
        indexer_task = None
        if not no_index:
            es = AsyncElasticsearch([ES_HOST])
            if not await es.indices.exists(index=es_index):
                await es.indices.create(index=es_index, body={
                    "settings": {"number_of_shards": 5, "number_of_replicas": 0},
                    "mappings": {
                        "properties": {
                            "domain": {"type": "keyword"},
                            "url": {"type": "keyword"},
                            "path": {"type": "keyword"},
                            "source": {"type": "keyword"},
                            "status": {"type": "integer"},
                            "content": {"type": "text"},
                            "content_length": {"type": "integer"},
                            "internal_links_count": {"type": "integer"},
                            "entities": {"type": "object"},
                            "scraped_at": {"type": "date"}
                        }
                    }
                })
            indexer_task = asyncio.create_task(self.es_indexer(es, es_index))

        start_time = time.time()
        total = len(domains)

        print(f"[BLITZ] Starting: {total} domains, {self.workers} concurrent", file=sys.stderr)
        print(f"[BLITZ] Sitemaps: {'enabled' if self.with_sitemaps else 'disabled'}", file=sys.stderr)
        print(f"[BLITZ] Paths per domain: {len(IMPORTANT_PATHS)}", file=sys.stderr)

        # Process domains in batches
        sem = asyncio.Semaphore(self.workers)

        async def process_with_sem(domain):
            async with sem:
                result = await self.process_domain(domain)
                if not no_index:
                    await self.results_queue.put(result)
                return result

        # Create all tasks
        tasks = [process_with_sem(d) for d in domains]

        # Progress monitoring
        completed = 0
        for coro in asyncio.as_completed(tasks):
            try:
                await coro
                completed += 1

                if completed % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / max(elapsed, 0.1)
                    eta = (total - completed) / max(rate, 0.1)
                    print(f"[PROGRESS] {completed}/{total} domains ({completed*100/total:.1f}%) | "
                          f"{rate:.1f} dom/s | {self.stats['pages_scraped']} pages | "
                          f"ETA: {eta/60:.0f}m", file=sys.stderr)
            except Exception as e:
                completed += 1

        # Cleanup
        self.indexing_done = True
        if indexer_task:
            await indexer_task
        if es:
            await es.close()
        await self.close()

        elapsed = time.time() - start_time
        print(f"\n[DONE] {self.stats['domains_processed']} domains, "
              f"{self.stats['pages_scraped']} pages in {elapsed/60:.1f}m", file=sys.stderr)
        print(f"[STATS] Tier A: {self.stats['tier_a']} | Tier B: {self.stats['tier_b']} | "
              f"Sitemaps: {self.stats['sitemaps_found']} | Errors: {self.stats['errors']}", file=sys.stderr)


async def main():
    parser = argparse.ArgumentParser(description='JESTER BLITZ + PACMAN')
    parser.add_argument('input_file', help='File with domains (one per line)')
    parser.add_argument('--workers', type=int, default=CONCURRENT_DOMAINS,
                        help=f'Concurrent domains (default: {CONCURRENT_DOMAINS})')
    parser.add_argument('--with-sitemaps', action='store_true', default=True,
                        help='Try sitemaps first (default: True)')
    parser.add_argument('--no-sitemaps', action='store_true',
                        help='Skip sitemap checking')
    parser.add_argument('--es-index', default=ES_INDEX,
                        help=f'Elasticsearch index (default: {ES_INDEX})')
    parser.add_argument('--no-index', action='store_true',
                        help='Skip Elasticsearch indexing')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of domains (0 = all)')
    args = parser.parse_args()

    # Read domains
    with open(args.input_file) as f:
        domains = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Handle URLs or plain domains
                if line.startswith('http'):
                    domain = urlparse(line).netloc
                else:
                    domain = line
                domain = domain.lower().replace('www.', '')
                if domain:
                    domains.append(domain)

    # Dedupe
    domains = list(dict.fromkeys(domains))

    if args.limit > 0:
        domains = domains[:args.limit]

    print(f"[BLITZ] Loaded {len(domains)} unique domains", file=sys.stderr)

    # Run
    blitz = JesterBlitz(
        workers=args.workers,
        with_sitemaps=not args.no_sitemaps
    )

    await blitz.run(
        domains=domains,
        es_index=args.es_index,
        no_index=args.no_index
    )


if __name__ == "__main__":
    if HAS_NAMES:
        print("[PACMAN] names-dataset loaded", file=sys.stderr)
    else:
        print("[PACMAN] names-dataset not available", file=sys.stderr)

    asyncio.run(main())
