"""
CommonCrawl PDF discovery for BACKDRILL.

Discover PDF documents (annual reports, filings, etc.) from CommonCrawl.

SOURCE: LINKLATER/mapping/cc_pdf_discovery.py

Features:
- Multi-signal scoring (0-100):
  - URL pattern (annual, report, investor)
  - File size (larger = more likely report)
  - Temporal (year in filename)
  - Path authority (/investor-relations/, /corporate/)
  - Jurisdiction matching
"""

import re
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# URL patterns that indicate valuable PDFs
REPORT_PATTERNS = [
    # English
    r'annual[-_]?report', r'financial[-_]?statement', r'investor[-_]?relations',
    r'corporate[-_]?governance', r'sustainability[-_]?report', r'esg[-_]?report',
    # German
    r'jahresbericht', r'geschaeftsbericht', r'geschäftsbericht', r'finanzbericht',
    r'nachhaltigkeitsbericht', r'konzernbericht',
    # French
    r'rapport[-_]?annuel', r'rapport[-_]?financier', r'rapport[-_]?activite',
    # Spanish
    r'informe[-_]?anual', r'memoria[-_]?anual', r'estados[-_]?financieros',
    # Italian
    r'relazione[-_]?annuale', r'bilancio[-_]?annuale',
]

PATH_AUTHORITY = [
    '/investor', '/investors', '/ir/', '/corporate', '/governance',
    '/financials', '/reports', '/publications', '/downloads',
    '/investoren', '/berichte', '/publikationen',
]


class CCPDFDiscovery:
    """
    Discover PDF documents from CommonCrawl Index.

    Usage:
        discovery = CCPDFDiscovery()
        pdfs = await discovery.discover("example.com", jurisdiction="DE")
    """

    def __init__(self, archive: str = "CC-MAIN-2024-51"):
        self.archive = archive

    async def discover(
        self,
        domain: str,
        jurisdiction: Optional[str] = None,
        min_score: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Discover PDFs from a domain in CommonCrawl.

        Args:
            domain: Target domain
            jurisdiction: Optional 2-letter country code for scoring boost
            min_score: Minimum score threshold (0-100)
            limit: Max PDFs to return

        Returns:
            List of PDF records sorted by score
        """
        from ..index import CCIndex

        idx = CCIndex(archive=self.archive)
        records = await idx.scan_domain(domain, limit=limit * 5)

        pdfs = []
        for record in records:
            url = record.get('url', '')
            mime = record.get('mime', '')

            # Filter to PDFs
            if not url.lower().endswith('.pdf') and 'pdf' not in mime.lower():
                continue

            score = self._score_pdf(url, jurisdiction)

            if score >= min_score:
                pdfs.append({
                    'url': url,
                    'timestamp': record.get('timestamp'),
                    'score': score,
                    'warc_filename': record.get('warc_filename'),
                    'mime': mime,
                })

        # Sort by score descending
        pdfs.sort(key=lambda x: x['score'], reverse=True)
        return pdfs[:limit]

    def _score_pdf(
        self,
        url: str,
        jurisdiction: Optional[str] = None,
    ) -> int:
        """
        Score a PDF URL for relevance (0-100).

        Scoring:
        - Base: 30
        - Report patterns: +20
        - Path authority: +15
        - Year in filename: +10
        - Jurisdiction match: +15
        - Financial keywords: +10
        """
        score = 30  # Base score
        url_lower = url.lower()

        # Report patterns
        for pattern in REPORT_PATTERNS:
            if re.search(pattern, url_lower):
                score += 20
                break

        # Path authority
        for path in PATH_AUTHORITY:
            if path in url_lower:
                score += 15
                break

        # Year in filename (20XX)
        if re.search(r'20[0-2]\d', url_lower):
            score += 10

        # Jurisdiction match
        if jurisdiction:
            jur_lower = jurisdiction.lower()
            # Check for country code in URL
            if f'/{jur_lower}/' in url_lower or f'.{jur_lower}/' in url_lower:
                score += 15
            # Check for common jurisdiction patterns
            if jur_lower in url_lower:
                score += 10

        # Financial keywords
        financial_keywords = [
            'financial', 'finanzen', 'accounts', 'bilanz', 'balance',
            'revenue', 'profit', 'earnings', 'quarterly', 'q1', 'q2', 'q3', 'q4'
        ]
        if any(kw in url_lower for kw in financial_keywords):
            score += 10

        return min(score, 100)


async def discover_pdfs(
    domain: str,
    jurisdiction: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Convenience function to discover PDFs from a domain.

    Args:
        domain: Target domain
        jurisdiction: Optional country code for scoring
        limit: Max results

    Returns:
        List of PDF records sorted by relevance score
    """
    discovery = CCPDFDiscovery()
    return await discovery.discover(domain, jurisdiction, limit=limit)
