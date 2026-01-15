#!/usr/bin/env python3
"""
Multi-Jurisdiction Annual Report Pattern Definitions

Defines jurisdiction-specific patterns for discovering annual reports in Common Crawl.
Supports Swedish (SE), UK, US, and EU reporting formats with localized naming conventions.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict
import re


@dataclass
class AnnualReportPattern:
    """
    Jurisdiction-specific pattern definition for annual reports.

    Attributes:
        jurisdiction: ISO 3166-1 alpha-2 code (SE, UK, US, EU, etc.)
        url_patterns: Compiled regex patterns for URL matching
        required_keywords: Keywords that should appear in content/title
        optional_keywords: Additional keywords that boost confidence
        file_size_range: (min_bytes, max_bytes) expected file size
        doc_types: Document type identifiers
        path_authority_patterns: High-confidence path patterns
        year_formats: Expected year format patterns in URLs
        language_codes: ISO 639-1 language codes for this jurisdiction
    """
    jurisdiction: str
    url_patterns: List[re.Pattern]
    required_keywords: List[str]
    optional_keywords: List[str] = field(default_factory=list)
    file_size_range: Tuple[int, int] = (500_000, 50_000_000)  # 500KB-50MB default
    doc_types: List[str] = field(default_factory=list)
    path_authority_patterns: List[re.Pattern] = field(default_factory=list)
    year_formats: List[re.Pattern] = field(default_factory=list)
    language_codes: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """Compile regex patterns after initialization."""
        if isinstance(self.url_patterns[0], str):
            self.url_patterns = [re.compile(p, re.IGNORECASE) for p in self.url_patterns]
        if self.path_authority_patterns and isinstance(self.path_authority_patterns[0], str):
            self.path_authority_patterns = [re.compile(p, re.IGNORECASE) for p in self.path_authority_patterns]
        if self.year_formats and isinstance(self.year_formats[0], str):
            self.year_formats = [re.compile(p) for p in self.year_formats]


# =============================================================================
# SWEDISH (SE) PATTERNS
# =============================================================================

SE_PATTERN = AnnualReportPattern(
    jurisdiction='SE',
    url_patterns=[
        # HIGH PRIORITY: Explicit patterns with year (99% confidence)
        r'annual[_-]?report[_-]?(\d{4})',
        r'årsredovisning[_-]?(\d{4})',
        r'arsredovisning[_-]?(\d{4})',
        r'(\d{4})[_-]?annual[_-]?report',
        r'(\d{4})[_-]?årsredovisning',
        r'(\d{4})[_-]?arsredovisning',

        # MEDIUM PRIORITY: With year but less explicit
        r'årsrapport[_-]?(\d{4})',
        r'arsrapport[_-]?(\d{4})',
        r'financial[_-]?report[_-]?(\d{4})',
        r'bokslutskommunik[eé][_-]?(\d{4})',

        # LOWER PRIORITY: Abbreviated with year
        r'ar[_-]?(\d{4})',
        r'/ar(\d{4})\.pdf',

        # FALLBACK: Without year but with .pdf
        r'årsredovisning.*\.pdf',
        r'arsredovisning.*\.pdf',
        r'annual[_-]?report.*\.pdf',
    ],
    required_keywords=[
        'årsredovisning', 'arsredovisning', 'annual report',
        'årsrapport', 'financial report', 'bokslutskommuniké'
    ],
    optional_keywords=[
        'koncern', 'group', 'consolidated', 'finansiell',
        'resultat', 'balansräkning', 'kassaflöde',
        'balance sheet', 'cash flow', 'income statement'
    ],
    file_size_range=(500_000, 50_000_000),  # 500KB-50MB
    doc_types=[
        'annual-report', 'årsredovisning', 'financial-statement',
        'bokslutskommuniké', 'delårsrapport'
    ],
    path_authority_patterns=[
        r'/investor[_-]?relations?/',
        r'/financial[_-]?information/',
        r'/reports?[_-]?and[_-]?publications/',
        r'/investerare/',
        r'/om[_-]?oss/',  # About us
        r'/ekonomisk[_-]?information/',
    ],
    year_formats=[
        r'\b(19|20)\d{2}\b',  # 4-digit year
        r'\bfy\d{2}\b',  # Fiscal year (FY24)
        r'\b\d{4}[_-]\d{4}\b',  # Year range (2023-2024)
    ],
    language_codes={'sv', 'en'}
)


# =============================================================================
# UK PATTERNS
# =============================================================================

UK_PATTERN = AnnualReportPattern(
    jurisdiction='UK',
    url_patterns=[
        # HIGH PRIORITY: Explicit with year
        r'annual[_-]?report.*?(\d{4})',
        r'(\d{4}).*?annual[_-]?report',
        r'annual[_-]?accounts?.*?(\d{4})',
        r'(\d{4}).*?annual[_-]?accounts?',

        # MEDIUM PRIORITY: UK-specific patterns
        r'strategic[_-]?report.*?(\d{4})',
        r'financial[_-]?statements?.*?(\d{4})',
        r'group[_-]?accounts?.*?(\d{4})',

        # LOWER PRIORITY: Abbreviated
        r'/ara?[_-]?(\d{4})',

        # FALLBACK: Without year
        r'annual[_-]?report.*\.pdf',
        r'annual[_-]?accounts?.*\.pdf',
    ],
    required_keywords=[
        'annual report', 'annual accounts', 'financial statements',
        'strategic report', 'directors report'
    ],
    optional_keywords=[
        'companies act', 'consolidated', 'group accounts',
        'auditor', 'FCA', 'LSE', 'premium listed',
        'corporate governance'
    ],
    file_size_range=(500_000, 50_000_000),
    doc_types=[
        'annual-report', 'annual-accounts', 'strategic-report',
        'financial-statements', 'directors-report'
    ],
    path_authority_patterns=[
        r'/investor[_-]?relations?/',
        r'/shareholders?/',
        r'/reports?[_-]?and[_-]?publications/',
        r'/financial[_-]?information/',
        r'/corporate[_-]?governance/',
    ],
    year_formats=[
        r'\b(19|20)\d{2}\b',
        r'\bfy\d{2}\b',
        r'\b\d{4}[/_-]\d{2,4}\b',  # UK often uses 2023/24 format
    ],
    language_codes={'en'}
)


# =============================================================================
# US PATTERNS
# =============================================================================

US_PATTERN = AnnualReportPattern(
    jurisdiction='US',
    url_patterns=[
        # HIGH PRIORITY: 10-K with year (SEC filings)
        r'10-?k.*?(\d{4})',
        r'(\d{4}).*?10-?k',
        r'form[_-]?10-?k.*?(\d{4})',

        # HIGH PRIORITY: Annual report with year
        r'annual[_-]?report.*?(\d{4})',
        r'(\d{4}).*?annual[_-]?report',

        # MEDIUM PRIORITY: Proxy statements
        r'proxy.*?(\d{4})',
        r'def[_-]?14a.*?(\d{4})',

        # LOWER PRIORITY: Abbreviated
        r'/ar[_-]?(\d{4})',

        # FALLBACK: Without year
        r'10-?k.*\.pdf',
        r'annual[_-]?report.*\.pdf',
    ],
    required_keywords=[
        'annual report', '10-K', 'form 10-K', 'proxy statement',
        'securities and exchange commission', 'SEC'
    ],
    optional_keywords=[
        'edgar', 'CIK', 'fiscal year', 'auditor report',
        'management discussion', 'MD&A', 'consolidated statements',
        'sarbanes-oxley', 'SOX', 'GAAP'
    ],
    file_size_range=(1_000_000, 100_000_000),  # 1MB-100MB (SEC filings are larger)
    doc_types=[
        '10-K', 'annual-report', 'proxy-statement',
        'DEF-14A', 'form-10-K'
    ],
    path_authority_patterns=[
        r'/investor[_-]?relations?/',
        r'/sec[_-]?filings?/',
        r'/financial[_-]?information/',
        r'/shareholders?/',
        r'/edgar/',
    ],
    year_formats=[
        r'\b(19|20)\d{2}\b',
        r'\bfy\d{2}\b',
        r'\bq[1-4]\b',  # Quarterly filings
    ],
    language_codes={'en'}
)


# =============================================================================
# EU PATTERNS (Multi-language)
# =============================================================================

EU_PATTERN = AnnualReportPattern(
    jurisdiction='EU',
    url_patterns=[
        # HIGH PRIORITY: Multi-language with year
        # French
        r'rapport[_-]?annuel.*?(\d{4})',
        r'(\d{4}).*?rapport[_-]?annuel',

        # German
        r'jahresbericht.*?(\d{4})',
        r'geschäftsbericht.*?(\d{4})',
        r'geschaftsbericht.*?(\d{4})',
        r'(\d{4}).*?jahresbericht',

        # Italian
        r'relazione[_-]?annuale.*?(\d{4})',
        r'bilancio.*?(\d{4})',

        # Spanish
        r'informe[_-]?anual.*?(\d{4})',
        r'memoria[_-]?anual.*?(\d{4})',

        # Dutch
        r'jaarverslag.*?(\d{4})',
        r'jaarrapport.*?(\d{4})',

        # English (common for EU multinationals)
        r'annual[_-]?report.*?(\d{4})',
        r'(\d{4}).*?annual[_-]?report',

        # FALLBACK: Without year
        r'rapport[_-]?annuel.*\.pdf',
        r'jahresbericht.*\.pdf',
        r'annual[_-]?report.*\.pdf',
    ],
    required_keywords=[
        'annual', 'rapport', 'jahresbericht', 'relazione', 'informe',
        'jaarverslag', 'financial', 'consolidated'
    ],
    optional_keywords=[
        'IFRS', 'consolidated', 'group', 'auditor',
        'corporate governance', 'ESG', 'sustainability'
    ],
    file_size_range=(500_000, 50_000_000),
    doc_types=[
        'annual-report', 'rapport-annuel', 'jahresbericht',
        'relazione-annuale', 'informe-anual', 'jaarverslag'
    ],
    path_authority_patterns=[
        r'/investor[_-]?relations?/',
        r'/financial[_-]?information/',
        r'/publications?/',
        r'/shareholders?/',
        r'/investisseurs?/',
        r'/anleger/',
    ],
    year_formats=[
        r'\b(19|20)\d{2}\b',
        r'\b\d{4}[/_-]\d{2,4}\b',
    ],
    language_codes={'fr', 'de', 'it', 'es', 'nl', 'en'}
)


# =============================================================================
# PATTERN REGISTRY
# =============================================================================

JURISDICTION_PATTERNS: Dict[str, AnnualReportPattern] = {
    'SE': SE_PATTERN,
    'UK': UK_PATTERN,
    'US': US_PATTERN,
    'EU': EU_PATTERN,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_pattern(jurisdiction: str) -> AnnualReportPattern:
    """
    Get pattern for jurisdiction code.

    Args:
        jurisdiction: ISO 3166-1 alpha-2 code (SE, UK, US, EU)

    Returns:
        AnnualReportPattern for jurisdiction

    Raises:
        ValueError: If jurisdiction not supported
    """
    pattern = JURISDICTION_PATTERNS.get(jurisdiction.upper())
    if not pattern:
        raise ValueError(
            f"Jurisdiction '{jurisdiction}' not supported. "
            f"Available: {list(JURISDICTION_PATTERNS.keys())}"
        )
    return pattern


def match_url_pattern(url: str, jurisdiction: str) -> bool:
    """
    Check if URL matches any pattern for jurisdiction.

    Args:
        url: URL to check
        jurisdiction: Jurisdiction code

    Returns:
        True if URL matches any pattern
    """
    pattern = get_pattern(jurisdiction)
    return any(regex.search(url) for regex in pattern.url_patterns)


def extract_year_from_url(url: str, jurisdiction: str) -> int:
    """
    Extract year from URL using jurisdiction patterns.

    Args:
        url: URL containing year
        jurisdiction: Jurisdiction code

    Returns:
        Year as integer, or 0 if not found
    """
    import re

    # First try: Direct 4-digit year search (most common)
    year_match = re.search(r'\b(19|20)\d{2}\b', url)
    if year_match:
        year = int(year_match.group(0))
        if 1990 <= year <= 2030:
            return year

    # Second try: FY format (fy2024, fy24, FY24, etc.)
    fy_match = re.search(r'fy[_-]?(\d{2,4})', url, re.IGNORECASE)
    if fy_match:
        fy_str = fy_match.group(1)
        if len(fy_str) == 4:
            return int(fy_str)
        elif len(fy_str) == 2:
            fy_year = int(fy_str)
            return 2000 + fy_year if fy_year < 50 else 1900 + fy_year

    # Third try: Pattern-based extraction
    pattern = get_pattern(jurisdiction)

    for regex in pattern.url_patterns:
        match = regex.search(url)
        if match:
            # Try to extract year from capture groups
            for group in match.groups():
                if group and group.isdigit() and len(group) == 4:
                    year = int(group)
                    if 1990 <= year <= 2030:
                        return year

    return 0


def get_all_jurisdictions() -> List[str]:
    """Get list of all supported jurisdiction codes."""
    return list(JURISDICTION_PATTERNS.keys())


def get_all_patterns() -> Dict[str, AnnualReportPattern]:
    """Get all jurisdiction patterns."""
    return JURISDICTION_PATTERNS.copy()
