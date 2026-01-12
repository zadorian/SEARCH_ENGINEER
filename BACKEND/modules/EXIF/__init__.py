"""
EXIF - Domain-wide Metadata Extraction Module

Extracts metadata from ALL files on a target domain:
- Images: EXIF (camera, GPS, timestamps, author)
- PDFs: Author, creator, title, dates
- Office docs: Author, company, last modified by
- Videos: Duration, codec, creation date

Then uses Claude Haiku to extract person names and entities from
the collective metadata for investigation purposes.

Usage:
    from modules.EXIF import MetadataScanner

    scanner = MetadataScanner()

    # Scan domain for metadata
    results = await scanner.scan_domain("example.com")

    # Extract entities from metadata
    entities = await scanner.extract_entities(results)
"""

from .scanner import MetadataScanner, MetadataResult
from .extractors import extract_metadata, extract_exif, extract_pdf_meta, extract_office_meta
from .entity_extractor import extract_persons_from_metadata

__all__ = [
    "MetadataScanner",
    "MetadataResult",
    "extract_metadata",
    "extract_exif",
    "extract_pdf_meta",
    "extract_office_meta",
    "extract_persons_from_metadata",
]
