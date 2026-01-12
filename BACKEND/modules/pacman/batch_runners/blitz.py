"""
PACMAN Blitz Runner
High-throughput domain intelligence scanning
"""

import asyncio
import time
from typing import Dict, List, Optional, AsyncIterator, Set
from datetime import datetime
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    httpx = None

from .base import BaseRunner, RunnerResult, RunnerStatus
from ..config.settings import CONCURRENT_BLITZ, TIMEOUT_TIER_A
from ..entity_extractors import extract_fast
from ..link_extractors import extract_links, extract_domains


# Important paths for domain intelligence
IMPORTANT_PATHS = [
    '/', '/about', '/about-us', '/team', '/management', '/leadership',
    '/contact', '/contact-us', '/impressum', '/imprint',
    '/company', '/corporate', '/investors', '/investor-relations',
    '/privacy', '/privacy-policy', '/terms', '/legal',
]


class BlitzRunner(BaseRunner):
    """
    High-throughput domain scanner.
    Quickly scans multiple paths per domain.
    """
    
    name = 'blitz'
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._http_client = None
        self._semaphore = asyncio.Semaphore(CONCURRENT_BLITZ)
    
    async def _get_client(self):
        if self._http_client is None and httpx:
            self._http_client = httpx.AsyncClient(
                timeout=TIMEOUT_TIER_A,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; PACMAN-Blitz/1.0)'}
            )
        return self._http_client
    
    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def run(self, domains: List[str]) -> AsyncIterator[RunnerResult]:
        """Run blitz scan on domains."""
        self.status = RunnerStatus.RUNNING
        self.stats.total = len(domains)
        self.stats.start_time = datetime.utcnow()
        
        # Process domains concurrently
        for domain in domains:
            if self.status == RunnerStatus.PAUSED:
                break
            
            result = await self.run_single(domain)
            self.stats.processed += 1
            
            if result.status == 'success':
                self.stats.succeeded += 1
            else:
                self.stats.failed += 1
            
            yield result
        
        self.stats.end_time = datetime.utcnow()
        self.status = RunnerStatus.COMPLETED
    
    async def run_single(self, domain: str) -> RunnerResult:
        """Scan a single domain across important paths."""
        start_time = time.time()
        
        # Ensure domain format
        if not domain.startswith('http'):
            domain = f'https://{domain}'
        
        parsed = urlparse(domain)
        base_url = f'{parsed.scheme}://{parsed.netloc}'
        
        all_entities = {}
        all_links: Set[str] = set()
        successful_paths = []
        
        # Generate URLs to scan
        urls = [f'{base_url}{path}' for path in IMPORTANT_PATHS]
        
        # Scan all paths concurrently
        async with self._semaphore:
            tasks = [self._fetch_url(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                continue
            if result is None:
                continue
            
            content, status = result
            if status == 200 and content:
                successful_paths.append(url)
                
                # Extract entities
                entities = extract_fast(content)
                for entity_type, values in entities.items():
                    if entity_type not in all_entities:
                        all_entities[entity_type] = []
                    all_entities[entity_type].extend(values)
                
                # Extract links
                links = extract_links(content, url)
                all_links.update(l.url for l in links)
        
        # Deduplicate entities
        for entity_type in all_entities:
            all_entities[entity_type] = list(set(all_entities[entity_type]))
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        if successful_paths:
            return RunnerResult(
                url=base_url,
                status='success',
                entities=all_entities,
                links=list(all_links)[:100],
                scrape_method='BLITZ',
                duration_ms=duration_ms,
                metadata={
                    'paths_scanned': len(urls),
                    'paths_successful': len(successful_paths),
                    'successful_paths': successful_paths,
                }
            )
        else:
            return RunnerResult(
                url=base_url,
                status='failed',
                error='No paths accessible',
                scrape_method='BLITZ',
                duration_ms=duration_ms,
            )
    
    async def _fetch_url(self, url: str):
        """Fetch a single URL."""
        if not httpx:
            return None
        
        try:
            client = await self._get_client()
            response = await client.get(url)
            return (response.text, response.status_code)
        except Exception:
            return None
