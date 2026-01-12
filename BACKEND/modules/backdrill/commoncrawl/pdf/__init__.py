"""
CommonCrawl PDF discovery for BACKDRILL.

Find PDF documents (annual reports, filings, etc.) in CommonCrawl.

SOURCE: LINKLATER/mapping/cc_pdf_discovery.py

Features:
- Multi-signal scoring (URL pattern, file size, temporal, jurisdiction)
- Jurisdiction pattern matching
- Annual report detection
"""

from .discovery import CCPDFDiscovery, discover_pdfs

__all__ = ["CCPDFDiscovery", "discover_pdfs"]
