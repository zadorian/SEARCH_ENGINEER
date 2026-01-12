"""
EXIF Scanner - Domain-wide metadata extraction.

Discovers all files on a domain and extracts metadata.
"""

import asyncio
import aiohttp
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from .extractors import MetadataResult, extract_metadata, get_file_type, FILE_TYPE_MAP

logger = logging.getLogger(__name__)

# Load supported file extensions
SUPPORTED_EXTENSIONS = set()
try:
    _config_path = Path(__file__).parent / "supported_files.json"
    with open(_config_path) as f:
        _config = json.load(f)
        # Use high + medium priority for scanning
        SUPPORTED_EXTENSIONS = set(
            ext.lower() for ext in
            _config["investigation_priority"]["high"]["extensions"] +
            _config["investigation_priority"]["medium"]["extensions"]
        )
except Exception:
    # Fallback
    SUPPORTED_EXTENSIONS = {
        "jpg", "jpeg", "png", "gif", "tiff", "tif", "heic", "webp",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "mp4", "mov", "mp3", "wav"
    }


@dataclass
class ScanResult:
    """Result of a domain metadata scan."""
    domain: str
    files_discovered: int = 0
    files_scanned: int = 0
    files_with_metadata: int = 0
    results: List[MetadataResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Aggregated metadata for entity extraction
    all_authors: List[str] = field(default_factory=list)
    all_companies: List[str] = field(default_factory=list)
    all_software: List[str] = field(default_factory=list)
    all_gps: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "files_discovered": self.files_discovered,
            "files_scanned": self.files_scanned,
            "files_with_metadata": self.files_with_metadata,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
            "aggregated": {
                "authors": list(set(self.all_authors)),
                "companies": list(set(self.all_companies)),
                "software": list(set(self.all_software)),
                "gps_locations": self.all_gps,
            }
        }


class MetadataScanner:
    """
    Scan a domain for files and extract metadata.

    Usage:
        scanner = MetadataScanner()
        result = await scanner.scan_domain("example.com")
        entities = await scanner.extract_entities(result)
    """

    def __init__(
        self,
        max_files: int = 200,
        max_file_size_mb: int = 50,
        timeout: int = 30,
        concurrent: int = 10,
    ):
        self.max_files = max_files
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.timeout = timeout
        self.concurrent = concurrent

    async def scan_domain(
        self,
        domain: str,
        file_types: Optional[List[str]] = None,
    ) -> ScanResult:
        """
        Scan domain for files and extract metadata.

        Args:
            domain: Target domain
            file_types: Specific extensions to scan (default: all high/medium priority)

        Returns:
            ScanResult with all extracted metadata
        """
        result = ScanResult(domain=domain)

        # Discover files on domain
        logger.info(f"Discovering files on {domain}")
        file_urls = await self._discover_files(domain, file_types)
        result.files_discovered = len(file_urls)

        if not file_urls:
            logger.warning(f"No files found on {domain}")
            return result

        logger.info(f"Found {len(file_urls)} files, extracting metadata...")

        # Extract metadata from files
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as session:
            semaphore = asyncio.Semaphore(self.concurrent)

            tasks = [
                self._extract_file_metadata(session, url, semaphore)
                for url in file_urls[:self.max_files]
            ]

            for coro in asyncio.as_completed(tasks):
                try:
                    meta_result = await coro
                    if meta_result:
                        result.files_scanned += 1

                        if meta_result.success:
                            result.files_with_metadata += 1
                            result.results.append(meta_result)

                            # Aggregate for entity extraction
                            if meta_result.author:
                                result.all_authors.append(meta_result.author)
                            if meta_result.company:
                                result.all_companies.append(meta_result.company)
                            if meta_result.software:
                                result.all_software.append(meta_result.software)
                            if meta_result.gps_lat and meta_result.gps_lon:
                                result.all_gps.append({
                                    "lat": meta_result.gps_lat,
                                    "lon": meta_result.gps_lon,
                                    "url": meta_result.url,
                                })
                except Exception as e:
                    result.errors.append(str(e))

        logger.info(
            f"Scan complete: {result.files_scanned} scanned, "
            f"{result.files_with_metadata} with metadata"
        )

        return result

    async def _discover_files(
        self,
        domain: str,
        file_types: Optional[List[str]] = None
    ) -> List[str]:
        """Discover files on domain using multiple methods."""
        file_urls: Set[str] = set()
        target_extensions = file_types or SUPPORTED_EXTENSIONS

        # Method 1: Try JESTER MAPPER
        try:
            from modules.JESTER.MAPPER.mapper import JesterMapper
            mapper = JesterMapper()
            urls = await mapper.discover(domain, mode="fast")
            for url_obj in urls:
                url = url_obj.url if hasattr(url_obj, "url") else str(url_obj)
                if self._is_target_file(url, target_extensions):
                    file_urls.add(url)
        except Exception as e:
            logger.debug(f"MAPPER discovery failed: {e}")

        # Method 2: Try Firecrawl map
        try:
            from modules.alldom.sources.firecrawl_mapper import FirecrawlMapper
            fm = FirecrawlMapper()
            async for discovered in fm.map_domain(domain):
                if self._is_target_file(discovered.url, target_extensions):
                    file_urls.add(discovered.url)
        except Exception as e:
            logger.debug(f"Firecrawl discovery failed: {e}")

        # Method 3: Try search engines with filetype operators
        if len(file_urls) < 50:
            try:
                file_urls.update(await self._search_engine_discovery(domain, target_extensions))
            except Exception as e:
                logger.debug(f"Search engine discovery failed: {e}")

        # Method 4: Try sitemap
        try:
            file_urls.update(await self._sitemap_discovery(domain, target_extensions))
        except Exception as e:
            logger.debug(f"Sitemap discovery failed: {e}")

        # Method 5: Common file paths
        file_urls.update(await self._common_path_discovery(domain, target_extensions))

        return list(file_urls)[:self.max_files]

    def _is_target_file(self, url: str, target_extensions: Set[str]) -> bool:
        """Check if URL points to a target file type."""
        try:
            path = urlparse(url).path.lower()
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            return ext in target_extensions
        except Exception:
            return False

    async def _search_engine_discovery(
        self,
        domain: str,
        extensions: Set[str]
    ) -> Set[str]:
        """Discover files via search engines with filetype operator."""
        results = set()

        try:
            from modules.brute.engines.google import GoogleEngine

            engine = GoogleEngine()

            # Search for high-value file types
            for ext in ["pdf", "docx", "xlsx", "jpg"]:
                if ext in extensions:
                    query = f"site:{domain} filetype:{ext}"
                    try:
                        search_results = await engine.search(query, limit=20)
                        for r in search_results:
                            url = r.get("url") or r.get("link")
                            if url and self._is_target_file(url, extensions):
                                results.add(url)
                    except Exception:
                        pass
        except ImportError:
            pass

        return results

    async def _sitemap_discovery(
        self,
        domain: str,
        extensions: Set[str]
    ) -> Set[str]:
        """Discover files from sitemap."""
        results = set()

        try:
            async with aiohttp.ClientSession() as session:
                for sitemap_url in [
                    f"https://{domain}/sitemap.xml",
                    f"https://{domain}/sitemap_index.xml",
                    f"https://www.{domain}/sitemap.xml",
                ]:
                    try:
                        async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                text = await resp.text()
                                # Simple regex to find URLs
                                import re
                                urls = re.findall(r"<loc>([^<]+)</loc>", text)
                                for url in urls:
                                    if self._is_target_file(url, extensions):
                                        results.add(url)
                    except Exception:
                        pass
        except Exception:
            pass

        return results

    async def _common_path_discovery(
        self,
        domain: str,
        extensions: Set[str]
    ) -> Set[str]:
        """Check common file paths."""
        results = set()
        base_url = f"https://{domain}"

        common_paths = [
            "/uploads/", "/images/", "/media/", "/files/", "/documents/",
            "/assets/", "/static/", "/content/", "/wp-content/uploads/",
            "/resources/", "/downloads/", "/pdf/", "/docs/",
        ]

        # Try robots.txt for additional paths
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/robots.txt",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Look for Disallow paths that might have files
                        import re
                        paths = re.findall(r"(?:Dis)?allow:\s*(/[^\s]+)", text)
                        common_paths.extend(paths[:20])
        except Exception:
            pass

        return results

    async def _extract_file_metadata(
        self,
        session: aiohttp.ClientSession,
        url: str,
        semaphore: asyncio.Semaphore
    ) -> Optional[MetadataResult]:
        """Download file and extract metadata."""
        async with semaphore:
            try:
                # First do HEAD to check size
                async with session.head(url, allow_redirects=True) as head_resp:
                    content_length = head_resp.headers.get("Content-Length")
                    if content_length and int(content_length) > self.max_file_size:
                        logger.debug(f"Skipping {url}: too large ({content_length} bytes)")
                        return None

                # Download file
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return None

                    # Check content type
                    content_type = resp.headers.get("Content-Type", "")

                    # Read file (with size limit)
                    data = await resp.content.read(self.max_file_size)

                    if len(data) < 100:  # Too small
                        return None

                    # Extract metadata
                    return extract_metadata(data, url, content_type)

            except asyncio.TimeoutError:
                logger.debug(f"Timeout downloading {url}")
            except Exception as e:
                logger.debug(f"Error downloading {url}: {e}")

            return None

    async def scan_stream(
        self,
        domain: str,
        file_types: Optional[List[str]] = None
    ) -> AsyncIterator[MetadataResult]:
        """
        Stream metadata results as they're extracted.

        Yields MetadataResult objects as files are processed.
        """
        file_urls = await self._discover_files(domain, file_types)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as session:
            semaphore = asyncio.Semaphore(self.concurrent)

            for url in file_urls[:self.max_files]:
                try:
                    result = await self._extract_file_metadata(session, url, semaphore)
                    if result and result.success:
                        yield result
                except Exception:
                    pass
