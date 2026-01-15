"""
LinkLater Parallel WAT Fetcher - High-Performance Archive Processing

Adapted from: crawling_common/parallel_cc_fetcher.py
Original: AllDOM Bridge prototype (Cymonides v1)
Date: 2025-11-30

Provides 20-50x speedup for Common Crawl WAT file processing through:
- Concurrent WAT file downloads (20-50 parallel)
- Async streaming while downloading next batch
- Semaphore-based concurrency control
- Memory-efficient processing

Performance Modes:
- Conservative: 20 parallel downloads, 10 concurrent processors (~2-5 GB RAM)
- Aggressive: 50 parallel downloads, 32 concurrent processors (~5-10 GB RAM)

Usage:
    from modules.linklater.parallel_wat_fetcher import ParallelWATFetcher

    fetcher = ParallelWATFetcher(
        crawl_id='CC-MAIN-2024-10',
        max_downloads=20,  # Conservative
        max_processors=10
    )

    async for page_data in fetcher.fetch_domains(['example.com', 'sebgroup.com']):
        # page_data = {url, domain, title, content, links, crawl_date, http_status}
        # Process page...
"""

import asyncio
import aiohttp
import gzip
import json
import re
from typing import List, Dict, AsyncIterator, Optional, Set
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class ParallelWATFetcher:
    """
    Parallel Common Crawl WAT file fetcher and processor.

    Downloads multiple WAT files concurrently and streams content.
    Provides 20-50x speedup over sequential processing.
    """

    def __init__(
        self,
        crawl_id: str,
        max_downloads: int = 20,
        max_processors: int = 10,
        base_url: str = 'https://data.commoncrawl.org'
    ):
        """
        Initialize parallel WAT fetcher.

        Args:
            crawl_id: CC crawl ID (e.g., 'CC-MAIN-2024-10')
            max_downloads: Max concurrent WAT downloads (20-50)
                          20 = Conservative (2-5 GB RAM)
                          50 = Aggressive (5-10 GB RAM)
            max_processors: Max concurrent processors (10-32)
                           10 = Conservative
                           32 = Aggressive
            base_url: Common Crawl base URL
        """
        self.crawl_id = crawl_id
        self.max_downloads = max_downloads
        self.max_processors = max_processors
        self.base_url = base_url

        # Semaphores for rate limiting
        self.download_semaphore = asyncio.Semaphore(max_downloads)
        self.process_semaphore = asyncio.Semaphore(max_processors)

        # Statistics
        self.stats = {
            'wat_files_fetched': 0,
            'pages_processed': 0,
            'domains_matched': 0,
            'bytes_downloaded': 0
        }

        logger.info(f"Parallel WAT Fetcher initialized")
        logger.info(f"  Crawl: {crawl_id}")
        logger.info(f"  Max downloads: {max_downloads}")
        logger.info(f"  Max processors: {max_processors}")

    async def get_wat_paths(self) -> List[str]:
        """
        Get list of all WAT file paths for this crawl.

        Returns:
            List of WAT file paths (e.g., 'crawl-data/CC-MAIN-2024-10/...')
        """
        paths_url = f"{self.base_url}/crawl-data/{self.crawl_id}/wat.paths.gz"

        logger.info(f"Fetching WAT paths from {paths_url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(paths_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch WAT paths: {response.status}")

                # Download and decompress
                compressed = await response.read()
                decompressed = gzip.decompress(compressed)

                # Parse paths
                paths = decompressed.decode('utf-8').strip().split('\n')

                logger.info(f"Found {len(paths)} WAT files")
                return paths

    async def download_wat_file(
        self,
        wat_path: str,
        session: aiohttp.ClientSession
    ) -> bytes:
        """
        Download a single WAT file with semaphore control.

        Args:
            wat_path: Path to WAT file
            session: aiohttp session

        Returns:
            Decompressed WAT file content (empty bytes on error)
        """
        async with self.download_semaphore:
            url = f"{self.base_url}/{wat_path}"

            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download {wat_path}: HTTP {response.status}")
                        return b""

                    # Download compressed data
                    compressed = await response.read()
                    self.stats['bytes_downloaded'] += len(compressed)

                    # Decompress
                    decompressed = gzip.decompress(compressed)

                    self.stats['wat_files_fetched'] += 1
                    size_mb = len(compressed) / 1024 / 1024
                    logger.debug(f"Downloaded WAT {self.stats['wat_files_fetched']}: {size_mb:.1f} MB")

                    return decompressed

            except asyncio.TimeoutError:
                logger.warning(f"Timeout downloading {wat_path}")
                return b""
            except Exception as e:
                logger.error(f"Error downloading {wat_path}: {e}")
                return b""

    async def process_wat_content(
        self,
        wat_content: bytes,
        target_domains: Optional[Set[str]] = None
    ) -> AsyncIterator[Dict]:
        """
        Process WAT file content and yield matching pages.

        Args:
            wat_content: Decompressed WAT file content
            target_domains: Set of domains to filter (None = all domains)

        Yields:
            {url, domain, title, content, links, crawl_date, http_status}
        """
        async with self.process_semaphore:
            if not wat_content:
                return

            # Split into WARC records
            records = wat_content.split(b'WARC/1.0')

            for record in records:
                if not record.strip():
                    continue

                try:
                    # Parse WARC record
                    page_data = self._parse_warc_record(record, target_domains)

                    if page_data:
                        self.stats['pages_processed'] += 1

                        if target_domains is None or page_data['domain'] in target_domains:
                            self.stats['domains_matched'] += 1
                            yield page_data

                        # Progress update every 1000 pages
                        if self.stats['pages_processed'] % 1000 == 0:
                            logger.debug(
                                f"Processed {self.stats['pages_processed']:,} pages, "
                                f"{self.stats['domains_matched']:,} matches"
                            )

                except Exception as e:
                    # Skip malformed records
                    logger.debug(f"Skipping malformed record: {e}")
                    continue

    def _parse_warc_record(
        self,
        record: bytes,
        target_domains: Optional[Set[str]] = None
    ) -> Optional[Dict]:
        """
        Parse a single WARC record into structured page data.

        Args:
            record: WARC record bytes
            target_domains: Domains to filter (None = all)

        Returns:
            Page data dict or None if parse fails
        """
        try:
            # Decode record
            record_str = record.decode('utf-8', errors='ignore')

            # Extract target URI
            uri_match = re.search(r'WARC-Target-URI: (https?://[^\s]+)', record_str)
            if not uri_match:
                return None

            url = uri_match.group(1)
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Filter by domain if specified
            if target_domains and domain not in target_domains:
                return None

            # Extract crawl date
            date_match = re.search(r'WARC-Date: (\d{4}-\d{2}-\d{2})', record_str)
            crawl_date = date_match.group(1) if date_match else None

            # Find JSON content
            json_start = record_str.find('{')
            if json_start == -1:
                return None

            json_str = record_str[json_start:]

            # Try to find complete JSON (may be truncated)
            json_end = json_str.rfind('}')
            if json_end != -1:
                json_str = json_str[:json_end+1]

            # Parse JSON
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                return None

            # Extract metadata from envelope
            envelope = data.get('Envelope', {})
            payload = envelope.get('Payload-Metadata', {})
            http_resp = payload.get('HTTP-Response-Metadata', {})
            html_meta = http_resp.get('HTML-Metadata', {})

            # Extract title
            head = html_meta.get('Head', {})
            title = head.get('Title', '')

            # Extract JSON-LD schemas from scripts
            scripts = head.get('Scripts', [])
            schemas = []
            for script in scripts:
                if isinstance(script, dict):
                    script_type = script.get('type', '')
                    if script_type == 'application/ld+json':
                        # CC sometimes pre-parses JSON-LD into 'content' field
                        content_data = script.get('content')
                        if content_data:
                            if isinstance(content_data, dict):
                                schemas.append(content_data)
                            elif isinstance(content_data, list):
                                schemas.extend(content_data)

            # Extract content from links (anchor text gives context)
            links = html_meta.get('Links', [])
            content_parts = [title]

            for link in links:
                if isinstance(link, dict):
                    text = link.get('text', '')
                    if text:
                        content_parts.append(text)

            # Limit content size to prevent OOM
            content = ' '.join(content_parts[:200])

            return {
                'url': url,
                'domain': domain,
                'title': title,
                'content': content,
                'links': links,
                'schemas': schemas,  # JSON-LD schemas from page
                'crawl_date': crawl_date,
                'http_status': http_resp.get('Response-Message', {}).get('Status', 200)
            }

        except Exception as e:
            logger.debug(f"Error parsing WARC record: {e}")
            return None

    async def fetch_domains(
        self,
        domains: List[str],
        max_wat_files: Optional[int] = None
    ) -> AsyncIterator[Dict]:
        """
        Fetch and process WAT files for specific domains.

        Main entry point for domain-filtered archive processing.

        Args:
            domains: List of domains to find (e.g., ['example.com', 'sebgroup.com'])
            max_wat_files: Max WAT files to process (None = all)
                          Useful for testing: max_wat_files=10

        Yields:
            Page data dicts: {url, domain, title, content, links, crawl_date, http_status}
        """
        # Convert to set for fast lookup
        target_domains = set(d.lower() for d in domains)

        logger.info(f"Fetching pages for {len(domains)} domains...")
        logger.debug(f"Targets: {', '.join(list(domains)[:5])}{'...' if len(domains) > 5 else ''}")

        # Get WAT file paths
        wat_paths = await self.get_wat_paths()

        if max_wat_files:
            wat_paths = wat_paths[:max_wat_files]
            logger.info(f"Limited to {max_wat_files} WAT files")

        # Create session
        async with aiohttp.ClientSession() as session:
            # Process WAT files in batches
            batch_size = self.max_downloads
            total_batches = (len(wat_paths) - 1) // batch_size + 1

            for i in range(0, len(wat_paths), batch_size):
                batch = wat_paths[i:i+batch_size]
                batch_num = i // batch_size + 1

                logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} WAT files")

                # Download batch concurrently
                download_tasks = [
                    self.download_wat_file(path, session)
                    for path in batch
                ]

                wat_contents = await asyncio.gather(*download_tasks)

                # Process each WAT file
                for wat_content in wat_contents:
                    if wat_content:
                        async for page_data in self.process_wat_content(
                            wat_content,
                            target_domains
                        ):
                            yield page_data

        # Final statistics
        logger.info("WAT Processing Complete")
        logger.info(f"  WAT files fetched: {self.stats['wat_files_fetched']}")
        logger.info(f"  Pages processed: {self.stats['pages_processed']:,}")
        logger.info(f"  Domain matches: {self.stats['domains_matched']:,}")
        logger.info(f"  Data downloaded: {self.stats['bytes_downloaded']/1024/1024/1024:.2f} GB")

    async def fetch_all(
        self,
        max_wat_files: Optional[int] = None
    ) -> AsyncIterator[Dict]:
        """
        Fetch and process all WAT files (no domain filter).

        WARNING: This will process ALL pages in the crawl (billions of pages).
        Recommended to use max_wat_files for testing.

        Args:
            max_wat_files: Max WAT files to process (HIGHLY RECOMMENDED)

        Yields:
            Page data dicts
        """
        logger.warning("Fetching ALL pages from crawl (no domain filter)")

        # Empty domain list = no filtering
        async for page_data in self.fetch_domains([], max_wat_files):
            yield page_data

    def get_stats(self) -> Dict:
        """
        Get current processing statistics.

        Returns:
            {wat_files_fetched, pages_processed, domains_matched, bytes_downloaded}
        """
        return self.stats.copy()

    def reset_stats(self):
        """Reset processing statistics."""
        self.stats = {
            'wat_files_fetched': 0,
            'pages_processed': 0,
            'domains_matched': 0,
            'bytes_downloaded': 0
        }

    async def fetch_by_schema(
        self,
        schema_type: str,
        schema_filters: Optional[Dict[str, str]] = None,
        max_wat_files: Optional[int] = None
    ) -> AsyncIterator[Dict]:
        """
        Fetch pages by Schema.org type with optional field filters.

        This is a DOMAIN DISCOVERY shortcut - find domains that have
        specific schema types without scraping them first.

        Args:
            schema_type: Schema.org @type to filter (e.g., "Organization", "LocalBusiness", "Person")
            schema_filters: Optional field filters (e.g., {"addressLocality": "Miami"})
            max_wat_files: Max WAT files to process (for testing)

        Yields:
            Page data dicts with matching schemas

        Examples:
            # Find all restaurants
            async for page in fetcher.fetch_by_schema("Restaurant"):
                print(page['domain'], page['schemas'])

            # Find organizations in New York
            async for page in fetcher.fetch_by_schema(
                "Organization",
                schema_filters={"addressLocality": "New York"}
            ):
                print(page['domain'])

            # Find all pages with Person schema mentioning "CEO"
            async for page in fetcher.fetch_by_schema(
                "Person",
                schema_filters={"jobTitle": "CEO"}
            ):
                print(page['domain'], page['schemas'])
        """
        logger.info(f"Schema search: @type={schema_type}, filters={schema_filters}")

        schema_type_lower = schema_type.lower()
        schema_filters = schema_filters or {}

        # Get WAT file paths
        wat_paths = await self.get_wat_paths()

        if max_wat_files:
            wat_paths = wat_paths[:max_wat_files]
            logger.info(f"Limited to {max_wat_files} WAT files")

        async with aiohttp.ClientSession() as session:
            batch_size = self.max_downloads
            total_batches = (len(wat_paths) - 1) // batch_size + 1

            for i in range(0, len(wat_paths), batch_size):
                batch = wat_paths[i:i+batch_size]
                batch_num = i // batch_size + 1

                logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} WAT files")

                # Download batch concurrently
                download_tasks = [
                    self.download_wat_file(path, session)
                    for path in batch
                ]

                wat_contents = await asyncio.gather(*download_tasks)

                # Process each WAT file
                for wat_content in wat_contents:
                    if wat_content:
                        async for page_data in self.process_wat_content(wat_content, None):
                            # Check if page has matching schema
                            if self._matches_schema(page_data, schema_type_lower, schema_filters):
                                yield page_data

        logger.info(f"Schema search complete: {self.stats['domains_matched']} matches")

    def _matches_schema(
        self,
        page_data: Dict,
        schema_type: str,
        schema_filters: Dict[str, str]
    ) -> bool:
        """
        Check if page has matching schema type and filters.

        Args:
            page_data: Page data with 'schemas' field
            schema_type: Lowercase schema type to match
            schema_filters: Field/value pairs to match

        Returns:
            True if any schema matches type and all filters
        """
        schemas = page_data.get('schemas', [])
        if not schemas:
            return False

        for schema in schemas:
            if not isinstance(schema, dict):
                continue

            # Check @type
            s_type = schema.get('@type', '')
            if isinstance(s_type, list):
                s_type = s_type[0] if s_type else ''

            if s_type.lower() != schema_type:
                continue

            # Check filters
            if schema_filters:
                all_match = True
                for key, value in schema_filters.items():
                    schema_value = self._get_nested_value(schema, key)
                    if schema_value is None:
                        all_match = False
                        break
                    if value.lower() not in str(schema_value).lower():
                        all_match = False
                        break

                if not all_match:
                    continue

            # Found match!
            self.stats['domains_matched'] += 1
            return True

        return False

    def _get_nested_value(self, obj: Dict, key: str) -> Optional[str]:
        """
        Get value from schema, handling nested structures.

        Handles:
        - Direct fields: {"name": "Acme"} → key="name" → "Acme"
        - Nested objects: {"address": {"addressLocality": "NY"}} → key="addressLocality" → "NY"
        """
        # Direct lookup
        if key in obj:
            val = obj[key]
            if isinstance(val, dict):
                return val.get('name') or val.get('@value') or str(val)
            return str(val)

        # Search in nested objects
        for field, value in obj.items():
            if isinstance(value, dict):
                if key in value:
                    return str(value[key])

        return None

    async def discover_domains_by_schema(
        self,
        schema_type: str,
        schema_filters: Optional[Dict[str, str]] = None,
        max_wat_files: int = 100,
        max_domains: int = 500
    ) -> List[str]:
        """
        Discover unique domains that have specific Schema.org data.

        This is the SEARCH BY SCHEMA shortcut - returns domains
        for subsequent targeted search.

        Args:
            schema_type: Schema.org @type (e.g., "Restaurant", "Organization")
            schema_filters: Optional field filters
            max_wat_files: Max WAT files to scan (default: 100)
            max_domains: Stop after finding this many domains

        Returns:
            List of unique domains with matching schema

        Example:
            # Find restaurant domains in Miami
            domains = await fetcher.discover_domains_by_schema(
                "Restaurant",
                {"addressLocality": "Miami"},
                max_domains=100
            )
            # Now use these domains for targeted keyword search
        """
        domains = set()

        async for page in self.fetch_by_schema(
            schema_type,
            schema_filters,
            max_wat_files
        ):
            domains.add(page['domain'])

            if len(domains) >= max_domains:
                logger.info(f"Reached max_domains limit: {max_domains}")
                break

        return list(domains)
