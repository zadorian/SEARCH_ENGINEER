#!/usr/bin/env python3
"""
Filetype Discovery Module

Find documents (PDF, XLSX, DOCX, etc.) on specific domains.

Discovery Methods:
1. Search Engine: site:domain.com filetype:pdf
2. Index-Based: Query Common Crawl index for URLs ending in file extensions

Use Cases:
- Find all PDFs on a domain: sebgroup.com + pdf
- Find annual reports: "annual report" + pdf + site:sebgroup.com
- Batch discovery: Find documents across multiple domains
"""

import asyncio
import httpx
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
import logging
from urllib.parse import urlparse
import re
from pathlib import Path
import sys

# Add brute module to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "modules"))

logger = logging.getLogger(__name__)

# Filetype aliases matching the main filetype.py
FILETYPE_ALIASES = {
    'pdf': ['pdf'],
    'document': ['pdf', 'doc', 'docx', 'odt', 'rtf', 'txt'],
    'word': ['doc', 'docx', 'odt', 'rtf'],
    'excel': ['xls', 'xlsx', 'ods', 'csv'],
    'spreadsheet': ['xls', 'xlsx', 'ods', 'csv', 'numbers', 'tsv'],
    'powerpoint': ['ppt', 'pptx', 'odp', 'key'],
    'presentation': ['ppt', 'pptx', 'odp', 'key'],
    'archive': ['zip', 'rar', '7z', 'tar', 'gz'],
    'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'],
    'audio': ['mp3', 'wav', 'aac', 'flac', 'ogg'],
    'video': ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'webm'],
}


@dataclass
class FiletypeResult:
    """Single filetype discovery result"""
    url: str
    domain: str
    filetype: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FiletypeDiscoveryResponse:
    """Filetype discovery response"""
    domain: str
    filetypes_searched: List[str]
    query: Optional[str]
    total_found: int
    results: List[FiletypeResult]
    sources_used: List[str]
    elapsed_ms: int = 0
    logs: List[Dict[str, Any]] = field(default_factory=list)  # Detailed logs for frontend display
    # Content-searched results: PDFs where keyword was found INSIDE the document
    content_matches: List[Dict[str, Any]] = field(default_factory=list)


def resolve_filetypes(filetype_query: str) -> List[str]:
    """Resolve filetype alias to list of extensions"""
    query_lower = filetype_query.lower().strip().replace('!', '')

    if query_lower == 'file' or query_lower == 'all':
        # Return all unique extensions
        all_exts = set()
        for exts in FILETYPE_ALIASES.values():
            all_exts.update(exts)
        return sorted(list(all_exts))

    return FILETYPE_ALIASES.get(query_lower, [query_lower])


async def google_filetype_search(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Search Google for filetypes on a domain using site: and filetype: operators
    """
    import os
    from dotenv import load_dotenv

    # Load from project root .env
    env_path = PROJECT_ROOT / '.env'
    load_dotenv(env_path)

    api_key = os.getenv('GOOGLE_API_KEY')
    cx = os.getenv('GOOGLE_CSE_ID') or os.getenv('GOOGLE_CX')

    if not api_key or not cx:
        logger.warning("[Filetype Google] Missing API key or CSE ID")
        return []

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for ext in filetypes:
            # Build query: site:domain.com filetype:pdf [keyword]
            query_parts = [f"site:{domain}", f"filetype:{ext}"]
            if keyword:
                query_parts.append(f'"{keyword}"' if ' ' in keyword else keyword)

            query = ' '.join(query_parts)

            try:
                # Google Custom Search API
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": api_key,
                        "cx": cx,
                        "q": query,
                        "num": min(10, limit // len(filetypes)),  # API limit is 10 per query
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('items', [])

                    for item in items:
                        url = item.get('link', '')

                        # Validate URL ends with expected extension
                        if not url.lower().endswith(f'.{ext}'):
                            # Check if URL contains the extension (some redirects)
                            if f'.{ext}' not in url.lower():
                                continue

                        results.append(FiletypeResult(
                            url=url,
                            domain=domain,
                            filetype=ext,
                            title=item.get('title'),
                            snippet=item.get('snippet'),
                            source='google',
                            metadata={
                                'query_used': query,
                                'display_link': item.get('displayLink')
                            }
                        ))

                    logger.info(f"[Filetype Google] {ext}: Found {len(items)} results for {domain}")
                else:
                    logger.warning(f"[Filetype Google] API error: {resp.status_code}")

            except Exception as e:
                logger.error(f"[Filetype Google] Search error for {ext}: {e}")
                continue

            # Small delay between requests
            await asyncio.sleep(0.1)

    return results


async def brave_filetype_search(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Search Brave for filetypes on a domain
    """
    import os
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / '.env'
    load_dotenv(env_path)

    api_key = os.getenv('BRAVE_SEARCH_API_KEY')

    if not api_key:
        logger.warning("[Filetype Brave] Missing API key")
        return []

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for ext in filetypes:
            # Build query
            query_parts = [f"site:{domain}", f"filetype:{ext}"]
            if keyword:
                query_parts.append(f'"{keyword}"' if ' ' in keyword else keyword)

            query = ' '.join(query_parts)

            try:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": api_key},
                    params={
                        "q": query,
                        "count": min(20, limit // len(filetypes)),
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    web_results = data.get('web', {}).get('results', [])

                    for item in web_results:
                        url = item.get('url', '')

                        # Validate URL ends with expected extension
                        if f'.{ext}' not in url.lower():
                            continue

                        results.append(FiletypeResult(
                            url=url,
                            domain=domain,
                            filetype=ext,
                            title=item.get('title'),
                            snippet=item.get('description'),
                            source='brave',
                            metadata={
                                'query_used': query,
                                'age': item.get('age')
                            }
                        ))

                    logger.info(f"[Filetype Brave] {ext}: Found {len(web_results)} results for {domain}")
                else:
                    logger.warning(f"[Filetype Brave] API error: {resp.status_code}")

            except Exception as e:
                logger.error(f"[Filetype Brave] Search error for {ext}: {e}")
                continue

            await asyncio.sleep(0.1)

    return results


async def commoncrawl_index_search(
    domain: str,
    filetypes: List[str],
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Search Common Crawl Index for URLs with specific file extensions
    This is FREE and instant - uses the CC Index API
    """
    results = []

    # Current CC index - should be updated periodically
    cc_index = "CC-MAIN-2024-46"

    async with httpx.AsyncClient(timeout=60.0) as client:
        for ext in filetypes:
            try:
                # Search for URLs ending in the extension
                # The CC index supports wildcard matching
                url_pattern = f"*.{domain}/*.{ext}"

                resp = await client.get(
                    f"https://index.commoncrawl.org/{cc_index}-index",
                    params={
                        "url": url_pattern,
                        "output": "json",
                        "limit": min(100, limit // len(filetypes))
                    }
                )

                if resp.status_code == 200:
                    # Each line is a JSON object
                    for line in resp.text.strip().split('\n'):
                        if not line:
                            continue
                        try:
                            import json
                            item = json.loads(line)
                            url = item.get('url', '')

                            results.append(FiletypeResult(
                                url=url,
                                domain=domain,
                                filetype=ext,
                                title=None,  # CC index doesn't have titles
                                snippet=None,
                                source='commoncrawl_index',
                                metadata={
                                    'warc_filename': item.get('filename'),
                                    'timestamp': item.get('timestamp'),
                                    'mime': item.get('mime'),
                                    'status': item.get('status')
                                }
                            ))
                        except Exception as e:
                            continue

                    logger.info(f"[Filetype CC] {ext}: Found results for {domain}")

            except Exception as e:
                logger.error(f"[Filetype CC] Search error for {ext}: {e}")
                continue

    return results


# MIME type mapping for CC Index queries
MIME_TYPE_MAP = {
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'csv': 'text/csv',
    'txt': 'text/plain',
    'xml': 'application/xml',
    'json': 'application/json',
}


async def cc_mime_filetype_search(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Search Common Crawl Index using MIME type filtering.

    This is more accurate than URL pattern matching because CC Index
    records the actual Content-Type header from the HTTP response.

    Uses CCPDFDiscovery infrastructure for efficient multi-archive queries.
    """
    results = []

    try:
        # Import the CC Index client
        from ..archives.cc_index_client import CCIndexClient

        cc_client = CCIndexClient()

        # Map filetypes to MIME types
        mime_types = []
        for ft in filetypes:
            if ft in MIME_TYPE_MAP:
                mime_types.append(MIME_TYPE_MAP[ft])

        if not mime_types:
            logger.warning(f"[CC MIME] No MIME types mapped for {filetypes}")
            return []

        # Query multiple archives for better coverage
        archives = [
            "CC-MAIN-2024-51",
            "CC-MAIN-2024-46",
            "CC-MAIN-2024-33",
            "CC-MAIN-2024-22",
            "CC-MAIN-2024-10",
        ]

        seen_urls: Set[str] = set()

        for archive in archives:
            if len(results) >= limit:
                break

            try:
                records = await cc_client.query_domain(
                    domain=domain,
                    archive=archive,
                    filter_mime=mime_types,
                    filter_status=[200],
                    limit=min(100, limit - len(results))
                )

                for record in records:
                    if record.url in seen_urls:
                        continue
                    seen_urls.add(record.url)

                    # Determine filetype from MIME or URL
                    ft = None
                    for ext, mime in MIME_TYPE_MAP.items():
                        if record.mime == mime:
                            ft = ext
                            break

                    if not ft:
                        # Fallback to URL extension
                        for ext in filetypes:
                            if f'.{ext}' in record.url.lower():
                                ft = ext
                                break

                    if not ft:
                        continue

                    # Keyword filter if specified
                    if keyword and keyword.lower() not in record.url.lower():
                        continue

                    results.append(FiletypeResult(
                        url=record.url,
                        domain=domain,
                        filetype=ft,
                        title=None,
                        snippet=None,
                        source='cc_mime',
                        metadata={
                            'archive': archive,
                            'mime': record.mime,
                            'status': record.status,
                            'length': record.length,
                            'timestamp': record.timestamp
                        }
                    ))

                logger.info(f"[CC MIME] {archive}: Found {len(records)} files for {domain}")

            except Exception as e:
                logger.debug(f"[CC MIME] Archive {archive} failed: {e}")
                continue

        logger.info(f"[CC MIME] Total: {len(results)} files from CC MIME search for {domain}")

    except ImportError as e:
        logger.warning(f"[CC MIME] CCIndexClient not available: {e}")
    except Exception as e:
        logger.error(f"[CC MIME] Error: {e}")

    return results[:limit]


async def firecrawl_filetype_search(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Use Firecrawl SEARCH API (not crawler) to find files on a domain.

    This uses site: and filetype: operators like Google - fast search, not crawling.
    Firecrawl Search API is different from Firecrawl Scraper/Crawler.
    """
    import os
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / '.env'
    load_dotenv(env_path)

    api_key = os.getenv('FIRECRAWL_API_KEY')

    if not api_key:
        logger.warning("[Filetype Firecrawl Search] Missing API key")
        return []

    results = []

    async with httpx.AsyncClient(timeout=45.0) as client:
        for ext in filetypes:
            # Build query with site: and filetype: operators (like Google)
            query_parts = [f"site:{domain}", f"filetype:{ext}"]
            if keyword:
                query_parts.append(f'"{keyword}"' if ' ' in keyword else keyword)

            query = ' '.join(query_parts)

            try:
                resp = await client.post(
                    "https://api.firecrawl.dev/v1/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "query": query,
                        "limit": min(20, limit // len(filetypes)),
                        "lang": "en",
                        "country": "us",
                        "scrapeOptions": {"formats": ["markdown"]}
                    }
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('success'):
                        items = data.get('data', [])

                        for item in items:
                            url = item.get('url') or (item.get('metadata') or {}).get('sourceURL', '')

                            # Validate URL contains the extension
                            if f'.{ext}' not in url.lower():
                                continue

                            results.append(FiletypeResult(
                                url=url,
                                domain=domain,
                                filetype=ext,
                                title=item.get('title') or (item.get('metadata') or {}).get('title'),
                                snippet=item.get('description') or item.get('markdown', '')[:200],
                                source='firecrawl_search',
                                metadata={
                                    'query_used': query,
                                    'has_content': bool(item.get('markdown'))
                                }
                            ))

                        logger.info(f"[Filetype Firecrawl Search] {ext}: Found {len(items)} results for {domain}")
                    else:
                        logger.warning(f"[Filetype Firecrawl Search] API returned success=false")
                else:
                    logger.warning(f"[Filetype Firecrawl Search] API error: {resp.status_code}")

            except Exception as e:
                logger.error(f"[Filetype Firecrawl Search] Search error for {ext}: {e}")
                continue

            await asyncio.sleep(0.1)

    return results[:limit]


async def drill_site_crawl(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Use DRILL Crawler to crawl a domain and find files.

    DRILL is our own crawler with better link mapping than Firecrawl.
    Uses Crawlee + Go hybrid architecture for speed.
    """
    results = []

    try:
        # Import DRILL crawler
        from ..scraping.web.crawler import Drill, DrillConfig

        # Configure for file discovery (limited crawl)
        config = DrillConfig(
            max_pages=min(200, limit * 3),  # Crawl enough pages to find files
            max_concurrent=30,
            max_depth=5,
            extract_entities=False,  # Skip entity extraction for speed
            generate_embeddings=False,
            index_to_elasticsearch=False,  # Don't index, just discover
            use_hybrid_crawler=True,  # Use Go fast path when available
        )

        drill = Drill(config)

        # Track discovered file URLs
        seen_urls: Set[str] = set()
        ext_pattern = '|'.join(re.escape(ext) for ext in filetypes)

        def on_page(doc):
            """Callback for each crawled page - extract file links"""
            # Check outlinks for file URLs
            for link in (doc.outlinks or []) + (doc.internal_links or []):
                if re.search(rf'\.({ext_pattern})(\?|$)', link.lower()):
                    if link not in seen_urls:
                        seen_urls.add(link)

                        # Extract extension
                        ext_match = re.search(rf'\.({ext_pattern})', link.lower())
                        ext = ext_match.group(1) if ext_match else filetypes[0]

                        # Keyword filter if specified
                        if keyword and keyword.lower() not in link.lower():
                            return

                        results.append(FiletypeResult(
                            url=link,
                            domain=domain,
                            filetype=ext,
                            title=None,
                            snippet=None,
                            source='drill_crawler',
                            metadata={'crawled_from': doc.url}
                        ))

        # Run the crawl
        logger.info(f"[Filetype DRILL] Starting site crawl for {domain}")
        stats = await drill.crawl(domain, on_page=on_page)

        logger.info(f"[Filetype DRILL] Crawled {stats.pages_crawled} pages, found {len(results)} files on {domain}")

    except ImportError as e:
        logger.warning(f"[Filetype DRILL] DRILL crawler not available: {e}")
    except Exception as e:
        logger.error(f"[Filetype DRILL] Error: {e}")

    return results[:limit]


async def extract_pdf_content_batch(
    pdf_urls: List[str],
    keyword: str,
    max_concurrent: int = 10
) -> List[Dict[str, Any]]:
    """
    Extract content from multiple PDFs and search for keyword.

    Four-tier extraction:
    1. Firecrawl API (parsers: ["pdf"]) - fast, cloud-based
    2. Common Crawl WARC (free, archived version) - uses CC Index to fetch archived PDFs
    3. Direct download + Local BinaryTextExtractor (pypdf/pdfplumber) - fallback, free
    4. Claude Vision OCR - for scanned/image-based PDFs

    Returns PDFs that contain the keyword with relevant snippets.
    """
    import os
    import base64
    import gzip
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / '.env'
    load_dotenv(env_path)

    firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    keyword_lower = keyword.lower()

    # Import local extractor as fallback
    try:
        from ..scraping.binary_extractor import BinaryTextExtractor
        local_extractor = BinaryTextExtractor()
        has_local_extractor = local_extractor.can_extract('application/pdf')
    except Exception:
        local_extractor = None
        has_local_extractor = False

    # Import WARC parser for CC extraction
    try:
        from ..scraping.warc_parser import WARCParser
        has_warc_parser = True
    except Exception:
        has_warc_parser = False

    # Check for Claude/Anthropic availability
    has_claude = bool(anthropic_api_key)

    # CC Index base URL
    CC_INDEX_BASE = "https://index.commoncrawl.org"
    CC_DATA_BASE = "https://data.commoncrawl.org"
    CC_ARCHIVES = ["CC-MAIN-2024-46", "CC-MAIN-2024-33", "CC-MAIN-2024-22", "CC-MAIN-2024-10"]

    async def extract_via_firecrawl(url: str, client: httpx.AsyncClient) -> Optional[str]:
        """Extract PDF content via Firecrawl API"""
        if not firecrawl_api_key:
            return None

        try:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {firecrawl_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "parsers": ["pdf"]
                }
            )

            if resp.status_code == 200:
                data = resp.json()
                return data.get('markdown', '') or data.get('data', {}).get('markdown', '')
        except Exception as e:
            logger.debug(f"[PDF Firecrawl] Failed {url}: {e}")

        return None

    async def extract_via_cc_warc(url: str, client: httpx.AsyncClient) -> Optional[str]:
        """
        Extract PDF content from Common Crawl WARC archives.

        Steps:
        1. Query CC Index to find WARC file location for this URL
        2. Fetch the WARC segment using Range header (offset + length)
        3. Parse WARC to get PDF binary
        4. Extract text using local extractor
        """
        if not has_warc_parser or not has_local_extractor:
            return None

        try:
            # Query CC Index for this URL
            for archive in CC_ARCHIVES:
                index_url = f"{CC_INDEX_BASE}/{archive}-index?url={url}&output=json"

                try:
                    resp = await client.get(index_url, timeout=10.0)
                    if resp.status_code != 200:
                        continue

                    # Parse NDJSON response (one record per line)
                    lines = resp.text.strip().split('\n')
                    if not lines or not lines[0]:
                        continue

                    # Take first record
                    record = None
                    for line in lines:
                        try:
                            rec = __import__('json').loads(line)
                            if rec.get('mime') == 'application/pdf' and rec.get('status') == '200':
                                record = rec
                                break
                        except Exception as e:
                            continue

                    if not record:
                        continue

                    # Fetch WARC segment using Range header
                    filename = record.get('filename')
                    offset = int(record.get('offset', 0))
                    length = int(record.get('length', 0))

                    if not filename or not length:
                        continue

                    warc_url = f"{CC_DATA_BASE}/{filename}"
                    range_header = f"bytes={offset}-{offset + length - 1}"

                    warc_resp = await client.get(
                        warc_url,
                        headers={"Range": range_header},
                        timeout=30.0
                    )

                    if warc_resp.status_code not in [200, 206]:
                        continue

                    warc_data = warc_resp.content

                    # Parse WARC to extract PDF binary
                    pdf_bytes, content_type = WARCParser.extract_binary(warc_data)

                    if pdf_bytes and len(pdf_bytes) > 100:
                        # Extract text from PDF
                        result = local_extractor.extract_text(
                            pdf_bytes,
                            'application/pdf',
                            url.split('/')[-1]
                        )

                        if result.success and result.text and len(result.text.strip()) > 50:
                            logger.debug(f"[PDF CC WARC] Extracted {len(result.text)} chars from {url}")
                            return result.text

                except Exception as e:
                    logger.debug(f"[PDF CC WARC] Archive {archive} failed for {url}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"[PDF CC WARC] Failed {url}: {e}")

        return None

    async def extract_via_local(url: str, pdf_bytes: bytes) -> Optional[str]:
        """Extract PDF content via local pypdf/pdfplumber"""
        if not has_local_extractor:
            return None

        try:
            # Extract text locally
            result = local_extractor.extract_text(
                pdf_bytes,
                'application/pdf',
                url.split('/')[-1]
            )

            if result.success and result.text and len(result.text.strip()) > 50:
                return result.text
        except Exception as e:
            logger.debug(f"[PDF Local] Failed {url}: {e}")

        return None

    async def extract_via_claude_vision(url: str, pdf_bytes: bytes, client: httpx.AsyncClient) -> Optional[str]:
        """
        Extract text from scanned/image-based PDFs using Claude Vision.

        Claude can natively process PDFs as images and perform OCR.
        We truncate to first 5 pages to manage cost/context.
        """
        if not has_claude:
            return None

        try:
            # Claude can process PDF directly as base64
            pdf_base64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')

            # Truncate large PDFs - Claude handles up to ~20 pages well
            # but we limit to save costs (each page ~1-2k tokens)
            MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB limit
            if len(pdf_bytes) > MAX_PDF_SIZE:
                logger.debug(f"[PDF Claude OCR] PDF too large ({len(pdf_bytes)/1024/1024:.1f}MB), skipping")
                return None

            # Call Claude API with PDF as document
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",  # Fast/cheap for OCR
                    "max_tokens": 8000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": "Extract ALL text content from this document. Perform OCR on any scanned or image-based pages. Return the complete text content, preserving structure and formatting where possible. If tables exist, format them clearly."
                                }
                            ]
                        }
                    ]
                },
                timeout=120.0  # OCR can take time
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data.get('content', [])
                if content and len(content) > 0:
                    text = content[0].get('text', '')
                    if text and len(text.strip()) > 50:
                        logger.info(f"[PDF Claude OCR] Successfully extracted {len(text)} chars from {url}")
                        return text
            else:
                logger.debug(f"[PDF Claude OCR] API error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            logger.debug(f"[PDF Claude OCR] Failed {url}: {e}")

        return None

    async def extract_single_pdf(url: str) -> Optional[Dict[str, Any]]:
        """Extract content from a single PDF and check for keyword"""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Tier 1: Try Firecrawl first (better parsing, cloud-based)
                content = await extract_via_firecrawl(url, client)
                extraction_method = "firecrawl"

                # Tier 2: Try Common Crawl WARC (free, archived)
                if not content:
                    content = await extract_via_cc_warc(url, client)
                    extraction_method = "cc_warc"

                # Download PDF if we need local or Claude extraction
                pdf_bytes = None
                if not content:
                    try:
                        resp = await client.get(url, timeout=30.0)
                        if resp.status_code == 200:
                            pdf_bytes = resp.content
                    except Exception as e:
                        logger.debug(f"[PDF Download] Failed {url}: {e}")

                # Tier 3: Fallback to local extraction
                if not content and pdf_bytes:
                    content = await extract_via_local(url, pdf_bytes)
                    extraction_method = "local"

                # Tier 4: Claude Vision OCR for scanned PDFs
                if not content and pdf_bytes and has_claude:
                    content = await extract_via_claude_vision(url, pdf_bytes, client)
                    extraction_method = "claude_ocr"

                if not content:
                    return None

                content_lower = content.lower()

                # Check if keyword exists in content
                if keyword_lower in content_lower:
                    # Extract snippet around keyword
                    idx = content_lower.find(keyword_lower)
                    start = max(0, idx - 200)
                    end = min(len(content), idx + len(keyword) + 200)
                    snippet = content[start:end].strip()

                    # Count occurrences
                    count = content_lower.count(keyword_lower)

                    return {
                        "url": url,
                        "keyword_matches": count,
                        "snippet": f"...{snippet}...",
                        "content_length": len(content),
                        "extraction_method": extraction_method
                    }

                return None

        except Exception as e:
            logger.debug(f"[PDF Extract] Error processing {url}: {e}")
            return None

    # Process PDFs in batches with controlled concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_extract(url: str) -> Optional[Dict[str, Any]]:
        async with semaphore:
            return await extract_single_pdf(url)

    tasks = [bounded_extract(url) for url in pdf_urls]
    extracted = await asyncio.gather(*tasks)

    # Filter out None results and return matches
    results = [r for r in extracted if r is not None]

    # Sort by keyword matches (most relevant first)
    results.sort(key=lambda x: x.get('keyword_matches', 0), reverse=True)

    logger.info(f"[PDF Extract] Searched {len(pdf_urls)} PDFs, found keyword in {len(results)}")

    return results


async def archive_deep_search(
    domain: str,
    filetypes: List[str],
    keyword: Optional[str] = None,
    limit: int = 100
) -> List[FiletypeResult]:
    """
    Deep archive search using:
    1. Multiple CC index archives (historical)
    2. Wayback Machine CDX API
    3. WARC binary extraction (if available)

    This is the most thorough but slowest method
    """
    results = []
    seen_urls = set()

    # Historical CC indexes to search
    cc_indexes = [
        "CC-MAIN-2024-46",
        "CC-MAIN-2024-33",
        "CC-MAIN-2024-22",
        "CC-MAIN-2024-10",
        "CC-MAIN-2023-50",
        "CC-MAIN-2023-40",
    ]

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Search multiple CC indexes
        for cc_index in cc_indexes:
            if len(results) >= limit:
                break

            for ext in filetypes:
                try:
                    url_pattern = f"*.{domain}/*.{ext}"

                    resp = await client.get(
                        f"https://index.commoncrawl.org/{cc_index}-index",
                        params={
                            "url": url_pattern,
                            "output": "json",
                            "limit": 50
                        }
                    )

                    if resp.status_code == 200:
                        for line in resp.text.strip().split('\n'):
                            if not line:
                                continue
                            try:
                                import json
                                item = json.loads(line)
                                url = item.get('url', '')

                                if url not in seen_urls:
                                    seen_urls.add(url)

                                    # Keyword filter if specified
                                    if keyword and keyword.lower() not in url.lower():
                                        continue

                                    results.append(FiletypeResult(
                                        url=url,
                                        domain=domain,
                                        filetype=ext,
                                        title=None,
                                        snippet=None,
                                        source=f'cc_archive_{cc_index}',
                                        metadata={
                                            'warc_filename': item.get('filename'),
                                            'timestamp': item.get('timestamp'),
                                            'archive': cc_index
                                        }
                                    ))
                            except Exception as e:
                                continue

                except Exception as e:
                    logger.debug(f"[Archive Deep] CC {cc_index} error: {e}")
                    continue

        # 2. Wayback Machine CDX API
        for ext in filetypes:
            if len(results) >= limit:
                break

            try:
                cdx_resp = await client.get(
                    "https://web.archive.org/cdx/search/cdx",
                    params={
                        "url": f"{domain}/*.{ext}",
                        "matchType": "prefix",
                        "output": "json",
                        "limit": 100,
                        "filter": "statuscode:200",
                        "collapse": "urlkey"
                    }
                )

                if cdx_resp.status_code == 200:
                    try:
                        cdx_data = cdx_resp.json()
                        # First row is headers
                        if cdx_data and len(cdx_data) > 1:
                            headers = cdx_data[0]
                            url_idx = headers.index('original') if 'original' in headers else 2
                            ts_idx = headers.index('timestamp') if 'timestamp' in headers else 1

                            for row in cdx_data[1:]:
                                url = row[url_idx]

                                if url not in seen_urls:
                                    seen_urls.add(url)

                                    if keyword and keyword.lower() not in url.lower():
                                        continue

                                    results.append(FiletypeResult(
                                        url=url,
                                        domain=domain,
                                        filetype=ext,
                                        title=None,
                                        snippet=None,
                                        source='wayback',
                                        metadata={
                                            'timestamp': row[ts_idx],
                                            'wayback_url': f"https://web.archive.org/web/{row[ts_idx]}/{url}"
                                        }
                                    ))
                    except Exception as e:

                        print(f"[LINKLATER] Error: {e}")

                        pass

                logger.info(f"[Archive Deep] Wayback found results for {domain}/*.{ext}")

            except Exception as e:
                logger.debug(f"[Archive Deep] Wayback error: {e}")

    logger.info(f"[Archive Deep] Total: {len(results)} files from archives for {domain}")
    return results[:limit]


@dataclass
class FiletypeDiscoveryLog:
    """Log entry for filetype discovery progress"""
    timestamp: str
    source: str
    message: str
    count: int = 0
    elapsed_ms: int = 0


async def discover_filetypes(
    domain: str,
    filetype_query: str = "document",
    keyword: Optional[str] = None,
    limit: int = 100,
    use_fallbacks: bool = True,
    cascade_mode: bool = True
) -> FiletypeDiscoveryResponse:
    """
    Main filetype discovery function with CASCADING fallback.

    CASCADE ORDER (stops when results found):
    1. Google site:domain filetype:pdf "keyword" (fast, direct)
    2. If nothing → Firecrawl site crawl (scrape links)
    3. If nothing → Brave search (fallback search engine)
    4. If nothing → Full archive pipeline (CC historical + Wayback + WARC)

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        filetype_query: Filetype alias or extension (e.g., "pdf", "document", "spreadsheet")
        keyword: Optional keyword to filter results (e.g., "annual report")
        limit: Maximum results to return
        use_fallbacks: Try multiple search engines if primary fails
        cascade_mode: Stop after first successful source (True) or search all sources (False)

    Returns:
        FiletypeDiscoveryResponse with discovered file URLs and logs

    Example:
        response = await discover_filetypes("sebgroup.com", "pdf", "annual report")
    """
    import time
    from datetime import datetime
    start_time = time.time()

    # Detailed logs for frontend display
    logs: List[Dict[str, Any]] = []

    def log(source: str, message: str, count: int = 0):
        elapsed = int((time.time() - start_time) * 1000)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "message": message,
            "count": count,
            "elapsed_ms": elapsed
        }
        logs.append(entry)
        logger.info(f"[Filetype {source}] {message}" + (f" ({count} results)" if count else ""))

    # Resolve filetype aliases
    filetypes = resolve_filetypes(filetype_query)
    if not filetypes:
        return FiletypeDiscoveryResponse(
            domain=domain,
            filetypes_searched=[],
            query=keyword,
            total_found=0,
            results=[],
            sources_used=[]
        )

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.startswith("http"):
        domain = urlparse(domain).netloc

    log("init", f"Starting cascade for {filetypes} on {domain}" +
        (f" with keyword '{keyword}'" if keyword else ""))

    all_results: List[FiletypeResult] = []
    sources_used: List[str] = []
    seen_urls: Set[str] = set()

    def add_results(results: List[FiletypeResult], source_name: str) -> int:
        """Add results and return count of new unique results"""
        added = 0
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)
                added += 1
        if added > 0:
            sources_used.append(source_name)
        return added

    # ============================================================
    # PHASE 0: ES Filetype Index (instant, pre-indexed) - BLOCKING
    # This runs first because it's instant and provides cached results
    # ============================================================
    try:
        from ..mapping.filetype_index import FiletypeIndexManager
        from ..mapping.filetype_populator import FiletypePopulator

        index_manager = FiletypeIndexManager()
        log("es_index", f"Checking pre-indexed filetype profile for {domain}")

        profile = await index_manager.get_profile(domain)

        # If no profile exists, try opportunistic profiling (queries CC Index live)
        if not profile:
            log("es_index", f"No profile found, trying opportunistic CC Index lookup...")
            populator = FiletypePopulator()
            profile = await populator.opportunistic_profile(domain, filetypes)
            if profile:
                log("es_index", f"Opportunistic profile created: {profile.total_documents} docs found")

        if profile and profile.sample_urls:
            # Filter sample URLs by filetype
            es_results = []
            for url in profile.sample_urls:
                url_lower = url.lower()
                for ft in filetypes:
                    if url_lower.endswith(f".{ft}"):
                        es_results.append(FiletypeResult(
                            url=url,
                            domain=domain,
                            filetype=ft,
                            title=f"Pre-indexed {ft.upper()}",
                            source="es_index",
                            metadata={
                                "from_index": True,
                                "pdf_count": profile.pdf_count,
                                "authority_score": profile.document_authority_score,
                                "has_annual_reports": profile.has_annual_reports
                            }
                        ))
                        break

            if es_results:
                new_count = add_results(es_results, "es_index")
                log("es_index", f"Found {len(es_results)} pre-indexed files, {new_count} unique (authority: {profile.document_authority_score:.0f})", new_count)
            else:
                log("es_index", f"Profile found ({profile.total_documents} docs) but no matching filetypes in sample_urls")
        else:
            log("es_index", f"No profile for {domain}")

    except Exception as e:
        log("es_index", f"ES index lookup failed: {str(e)[:50]}")

    # ============================================================
    # PHASE 1: ALL 7 DISCOVERY METHODS - MAXIMUM PARALLEL
    # Run everything at once for minimum total time
    # Total time = max(all methods) - optimal parallelization
    # Per-task timeouts prevent any single slow API from blocking
    # ============================================================
    log("parallel", f"Starting ALL 7 discovery methods IN PARALLEL for {domain}...")

    # All sources with their timeouts (generous - never sacrifice recall for speed)
    all_sources = [
        ("cc_mime", 60),           # CC MIME search - moderate
        ("google", 30),            # Google API - fast
        ("firecrawl_search", 45),  # Firecrawl search API - moderate
        ("brave", 30),             # Brave API - fast
        ("cc_index", 60),          # CC Index URL pattern - moderate
        ("drill_crawler", 180),    # Site crawl - needs time to crawl pages
        ("archive_deep", 120),     # Deep archive - multiple archives to query
    ]

    # Create tasks with individual timeouts
    # Timeout ensures one hung API doesn't block everything
    # But timeouts are generous - we NEVER sacrifice recall
    async def run_with_timeout(coro, timeout_sec, source_name):
        """Run coroutine with timeout, return (result, source) or (Exception, source)"""
        try:
            result = await asyncio.wait_for(coro, timeout=timeout_sec)
            return (result, source_name)
        except asyncio.TimeoutError:
            return (TimeoutError(f"{source_name} timed out after {timeout_sec}s"), source_name)
        except Exception as e:
            return (e, source_name)

    # Build all tasks
    all_tasks = [
        run_with_timeout(cc_mime_filetype_search(domain, filetypes, keyword, limit), 60, "cc_mime"),
        run_with_timeout(google_filetype_search(domain, filetypes, keyword, limit), 30, "google"),
        run_with_timeout(firecrawl_filetype_search(domain, filetypes, keyword, limit), 45, "firecrawl_search"),
        run_with_timeout(brave_filetype_search(domain, filetypes, keyword, limit), 30, "brave"),
        run_with_timeout(commoncrawl_index_search(domain, filetypes, limit), 60, "cc_index"),
        run_with_timeout(drill_site_crawl(domain, filetypes, keyword, limit), 180, "drill_crawler"),
        run_with_timeout(archive_deep_search(domain, filetypes, keyword, limit), 120, "archive_deep"),
    ]

    # Run ALL 7 methods in parallel - maximum parallelization
    # return_exceptions=True ensures one failure doesn't block others
    all_results_raw = await asyncio.gather(*all_tasks, return_exceptions=True)

    # Process results as they complete
    for item in all_results_raw:
        if isinstance(item, Exception):
            # This shouldn't happen with our wrapper, but handle it
            log("parallel", f"Task error: {str(item)[:80]}")
            continue

        result, source = item

        if isinstance(result, Exception):
            if isinstance(result, TimeoutError):
                log(source, f"Timed out (results may still come from other sources)")
            else:
                log(source, f"Failed: {str(result)[:80]}")
        elif result:
            new_count = add_results(result, source)
            log(source, f"Found {len(result)} results, {new_count} unique", new_count)
        else:
            log(source, "No results")

    log("parallel", f"All 7 methods complete: {len(all_results)} total unique results")

    # Limit results
    all_results = all_results[:limit]

    # ============================================================
    # PHASE 6: PDF Content Extraction (if keyword provided)
    # Search INSIDE found PDFs for the keyword
    # ============================================================
    content_matches: List[Dict[str, Any]] = []

    if keyword and len(all_results) > 0:
        # Extract PDF URLs only
        pdf_urls = [r.url for r in all_results if r.filetype.lower() == 'pdf']

        if pdf_urls:
            log("pdf_extract", f"Extracting content from {len(pdf_urls)} PDFs to search for '{keyword}' (4-tier: Firecrawl → CC WARC → Local → Claude OCR)")
            try:
                # Limit to first 20 PDFs for speed (each costs API credits)
                urls_to_search = pdf_urls[:20]
                content_matches = await extract_pdf_content_batch(urls_to_search, keyword, max_concurrent=10)

                # Count extraction methods used
                method_counts = {}
                for m in content_matches:
                    method = m.get('extraction_method', 'unknown')
                    method_counts[method] = method_counts.get(method, 0) + 1

                method_summary = ", ".join([f"{count} via {method}" for method, count in method_counts.items()])
                log("pdf_extract", f"Found keyword in {len(content_matches)} of {len(urls_to_search)} PDFs" +
                    (f" ({method_summary})" if method_summary else ""), len(content_matches))

                # Update results with content match info
                content_urls = {m['url'] for m in content_matches}
                for r in all_results:
                    if r.url in content_urls:
                        match_info = next((m for m in content_matches if m['url'] == r.url), None)
                        if match_info:
                            r.metadata['keyword_matches'] = match_info['keyword_matches']
                            r.metadata['extraction_method'] = match_info.get('extraction_method', 'unknown')
                            r.snippet = match_info.get('snippet')

            except Exception as e:
                log("pdf_extract", f"PDF extraction failed: {str(e)[:100]}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    log("complete", f"Discovery complete: {len(all_results)} files from {len(sources_used)} sources" +
        (f", {len(content_matches)} with keyword matches" if content_matches else ""), len(all_results))

    response = FiletypeDiscoveryResponse(
        domain=domain,
        filetypes_searched=filetypes,
        query=keyword,
        total_found=len(all_results),
        results=all_results,
        sources_used=sources_used,
        elapsed_ms=elapsed_ms,
        content_matches=content_matches  # PDFs where keyword was found inside
    )

    # Attach logs to response for frontend display
    response.logs = logs  # type: ignore

    return response


async def batch_discover_filetypes(
    domains: List[str],
    filetype_query: str = "document",
    keyword: Optional[str] = None,
    limit_per_domain: int = 50
) -> Dict[str, FiletypeDiscoveryResponse]:
    """
    Batch filetype discovery across multiple domains

    Example:
        results = await batch_discover_filetypes(
            ["sebgroup.com", "nordea.com", "handelsbanken.se"],
            "pdf",
            "annual report"
        )
    """
    results = {}

    # Run concurrently but with some rate limiting
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent searches

    async def search_domain(domain: str):
        async with semaphore:
            return domain, await discover_filetypes(
                domain, filetype_query, keyword, limit_per_domain
            )

    tasks = [search_domain(d) for d in domains]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if isinstance(resp, Exception):
            logger.error(f"[Batch Filetype] Error: {resp}")
            continue
        domain, discovery_response = resp
        results[domain] = discovery_response

    return results


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Discover files on domains")
    parser.add_argument("domain", help="Target domain (e.g., sebgroup.com)")
    parser.add_argument("-t", "--type", default="pdf", help="File type (pdf, document, excel, etc.)")
    parser.add_argument("-k", "--keyword", help="Optional keyword filter")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Max results")

    args = parser.parse_args()

    async def main():
        response = await discover_filetypes(
            args.domain,
            args.type,
            args.keyword,
            args.limit
        )

        print(f"\n📁 Files found on {response.domain}:")
        print(f"   Types searched: {', '.join(response.filetypes_searched)}")
        print(f"   Total found: {response.total_found}")
        print(f"   Sources: {', '.join(response.sources_used)}")
        print(f"   Time: {response.elapsed_ms}ms\n")

        for i, result in enumerate(response.results[:20], 1):
            print(f"{i}. [{result.filetype.upper()}] {result.title or 'No title'}")
            print(f"   URL: {result.url}")
            print(f"   Source: {result.source}")
            if result.snippet:
                print(f"   Snippet: {result.snippet[:100]}...")
            print()

    asyncio.run(main())
