"""
Specialized Search Operators - Category-specific search implementations

Each module provides:
- Search class (e.g., GovSearcher, FinanceSearcher)
- detect_*_query() - Check if query matches this category
- extract_*_query() - Extract query from operator prefix
- run_*_search() - Async entry point
- run_*_search_sync() - Sync wrapper
- search() - Web API compatible function
- main() - CLI entry point

Categories:
- academic: Academic/scholarly sources (OpenAlex, arXiv, PubMed, etc.)
- corporate: Corporate registries (Companies House, OpenCorporates, etc.)
- crypto: Cryptocurrency (blockchain explorers, exchanges)
- edu: Educational content (Coursera, edX, etc.)
- event: Events and conferences
- finance: Financial data (SEC, Bloomberg, etc.)
- gov: Government portals and official sources
- legal: Court cases and legal databases
- medical: Medical/health information
- product: E-commerce/product search
- recruitment: Job boards and career sites
- social: Social media platforms
"""

# Academic search
from .academic import (
    AcademicSearch,
    detect_academic_query,
    extract_academic_query,
    run_academic_search,
    run_academic_search_sync,
)

# Corporate registry search
from .corporate import (
    CorporateSearcher,
    detect_corporate_query,
    extract_corporate_query,
    run_corporate_search,
    run_corporate_search_sync,
)

# Cryptocurrency search
from .crypto import (
    detect_crypto_query,
    extract_crypto_query,
)

# Educational content search
from .edu import (
    EduSearch,
    detect_edu_query,
    extract_edu_query,
    run_edu_search,
    run_edu_search_sync,
)

# Finance search
from .finance import (
    FinanceSearcher,
    detect_finance_query,
    extract_finance_query,
    run_finance_search,
    run_finance_search_sync,
)

# Government search
from .gov import (
    GovSearcher,
    detect_gov_query,
    extract_gov_query,
    run_gov_search,
    run_gov_search_sync,
)

# Legal search
from .legal import (
    LegalSearcher,
    detect_legal_query,
    extract_legal_query,
    run_legal_search,
    run_legal_search_sync,
)

# Medical search
from .medical import (
    detect_medical_query,
    extract_medical_query,
)

# Product/e-commerce search
from .product import (
    detect_product_query,
    extract_product_query,
)

# Social media search
from .social import (
    SocialSearcher,
    detect_social_query,
    extract_social_query,
    run_social_search,
    run_social_search_sync,
)

__all__ = [
    # Academic
    'AcademicSearch',
    'detect_academic_query',
    'extract_academic_query',
    'run_academic_search',
    'run_academic_search_sync',
    # Corporate
    'CorporateSearcher',
    'detect_corporate_query',
    'extract_corporate_query',
    'run_corporate_search',
    'run_corporate_search_sync',
    # Crypto
    'detect_crypto_query',
    'extract_crypto_query',
    # Educational
    'EduSearch',
    'detect_edu_query',
    'extract_edu_query',
    'run_edu_search',
    'run_edu_search_sync',
    # Finance
    'FinanceSearcher',
    'detect_finance_query',
    'extract_finance_query',
    'run_finance_search',
    'run_finance_search_sync',
    # Government
    'GovSearcher',
    'detect_gov_query',
    'extract_gov_query',
    'run_gov_search',
    'run_gov_search_sync',
    # Legal
    'LegalSearcher',
    'detect_legal_query',
    'extract_legal_query',
    'run_legal_search',
    'run_legal_search_sync',
    # Medical
    'detect_medical_query',
    'extract_medical_query',
    # Product
    'detect_product_query',
    'extract_product_query',
    # Social
    'SocialSearcher',
    'detect_social_query',
    'extract_social_query',
    'run_social_search',
    'run_social_search_sync',
]
