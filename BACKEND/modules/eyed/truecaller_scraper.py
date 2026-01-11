"""
Truecaller Scraper - Phone number lookup via web scraping

Uses JESTER hierarchy (httpx -> Colly -> Rod -> Playwright) to scrape
Truecaller search results without their expensive API.

Returns: name, carrier, location, spam reports
"""

import asyncio
import re
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Try to import JESTER using proper import
try:
    from modules.JESTER.scraper import Jester, JesterMethod
    HAS_JESTER = True
except ImportError:
    try:
        from JESTER.scraper import Jester, JesterMethod
        HAS_JESTER = True
    except ImportError:
        HAS_JESTER = False
        logger.warning("JESTER not available, Truecaller scraper disabled")


class TruecallerScraper:
    """
    Scrapes Truecaller for phone number information.

    URL pattern: https://www.truecaller.com/search/{country}/{phone}
    """

    COUNTRY_CODES = {
        '+1': 'us', '+44': 'gb', '+49': 'de', '+33': 'fr', '+39': 'it',
        '+34': 'es', '+31': 'nl', '+32': 'be', '+43': 'at', '+41': 'ch',
        '+48': 'pl', '+46': 'se', '+47': 'no', '+45': 'dk', '+358': 'fi',
        '+91': 'in', '+86': 'cn', '+81': 'jp', '+82': 'kr', '+61': 'au',
        '+64': 'nz', '+55': 'br', '+52': 'mx', '+7': 'ru', '+380': 'ua',
        '+385': 'hr', '+36': 'hu', '+420': 'cz', '+421': 'sk', '+386': 'si',
        '+40': 'ro', '+359': 'bg', '+30': 'gr', '+90': 'tr', '+972': 'il',
        '+971': 'ae', '+966': 'sa', '+27': 'za', '+234': 'ng', '+254': 'ke',
        '+20': 'eg',
    }

    def __init__(self):
        self.jester = Jester() if HAS_JESTER else None
        self._stats = {'success': 0, 'failed': 0, 'blocked': 0}

    def _normalize_phone(self, phone: str) -> tuple:
        cleaned = re.sub(r'[^\d+]', '', phone)
        country_slug = 'us'
        phone_digits = cleaned.lstrip('+')

        for prefix, slug in sorted(self.COUNTRY_CODES.items(), key=lambda x: -len(x[0])):
            if cleaned.startswith(prefix):
                country_slug = slug
                phone_digits = cleaned[len(prefix):]
                break

        return phone_digits, country_slug

    def _build_url(self, phone: str) -> str:
        digits, country = self._normalize_phone(phone)
        return f"https://www.truecaller.com/search/{country}/{digits}"

    def _extract_data(self, html: str, phone: str) -> Dict[str, Any]:
        result = {
            'phone': phone,
            'name': None,
            'carrier': None,
            'location': None,
            'spam_reports': 0,
            'type': None,
            'source': 'truecaller_scrape'
        }

        # JSON-LD extraction
        json_ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if json_ld:
            try:
                data = json.loads(json_ld.group(1))
                if isinstance(data, dict):
                    result['name'] = data.get('name')
                    if 'address' in data and isinstance(data['address'], dict):
                        result['location'] = data['address'].get('addressLocality')
            except json.JSONDecodeError:
                pass

        # Meta tag extraction
        og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if og_title and not result['name']:
            parts = og_title.group(1).split('|')
            if parts:
                name = parts[0].strip()
                if name.lower() not in ['unknown', 'phone number']:
                    result['name'] = name

        # Name patterns
        for pattern in [r'"name"\s*:\s*"([^"]+)"', r'<h1[^>]*>([^<]+)</h1>']:
            match = re.search(pattern, html, re.IGNORECASE)
            if match and not result['name']:
                name = match.group(1).strip()
                if name.lower() not in ['unknown', 'private number', 'spam']:
                    result['name'] = name
                    break

        # Carrier
        carrier = re.search(r'"carrier"\s*:\s*"([^"]+)"', html)
        if carrier:
            result['carrier'] = carrier.group(1).strip()

        # Location
        loc = re.search(r'"location"\s*:\s*"([^"]+)"', html)
        if loc and not result['location']:
            result['location'] = loc.group(1).strip()

        # Spam reports
        spam = re.search(r'(\d+)\s*(?:spam|report)', html, re.IGNORECASE)
        if spam:
            result['spam_reports'] = int(spam.group(1))

        # Phone type
        if re.search(r'mobile|cell', html, re.IGNORECASE):
            result['type'] = 'mobile'
        elif re.search(r'landline|fixed', html, re.IGNORECASE):
            result['type'] = 'landline'

        return result

    async def lookup(self, phone: str) -> Optional[Dict[str, Any]]:
        if not HAS_JESTER:
            return None

        url = self._build_url(phone)
        logger.info(f"Truecaller lookup: {url}")

        try:
            result = await self.jester.scrape(url)

            if result.method == JesterMethod.BLOCKED:
                self._stats['blocked'] += 1
                return None

            if not result.html or result.status_code != 200:
                self._stats['failed'] += 1
                return None

            data = self._extract_data(result.html, phone)
            data['scrape_method'] = result.method.value
            data['url'] = url
            self._stats['success'] += 1
            return data

        except Exception as e:
            self._stats['failed'] += 1
            logger.error(f"Truecaller error: {e}")
            return None

    async def lookup_batch(self, phones: List[str], max_concurrent: int = 5) -> List[Dict[str, Any]]:
        if not HAS_JESTER:
            return []

        semaphore = asyncio.Semaphore(max_concurrent)

        async def lookup_one(p):
            async with semaphore:
                return await self.lookup(p)

        results = await asyncio.gather(*[lookup_one(p) for p in phones], return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()

    async def close(self):
        if self.jester:
            await self.jester.close()
