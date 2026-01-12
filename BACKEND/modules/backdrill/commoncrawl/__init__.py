"""
CommonCrawl submodule for BACKDRILL.

Components:
- CCIndex: CC Index API queries (cluster.idx binary search)
- CCWARCFetcher: WARC content fetch (wraps ccwarc_linux Go binary)
- CCLinksExtractor: WAT link extraction (wraps cclinks_linux Go binary)
- CCPDFDiscovery: PDF document discovery

SOURCE FILES:
- index.py ← LINKLATER/scraping/web/cc_offline_sniper.py
- warc.py ← SUBMARINE/sastre_submarine.py CCWARCFetcher class
- wat.py ← SUBMARINE/sastre_submarine.py CCLinksExtractor class
- pdf/discovery.py ← LINKLATER/mapping/cc_pdf_discovery.py

GO BINARIES:
- ccwarc_linux: /data/submarine/bin/ or LINKLATER/scraping/web/go/cmd/ccwarc/
- cclinks_linux: /data/submarine/bin/ or LINKLATER/scraping/web/go/cmd/cclinks/
"""

from .index import CCIndex
from .warc import CCWARCFetcher
from .wat import CCLinksExtractor

# Legacy alias
CommonCrawl = CCIndex

__all__ = [
    "CCIndex",
    "CCWARCFetcher",
    "CCLinksExtractor",
    "CommonCrawl",
]
