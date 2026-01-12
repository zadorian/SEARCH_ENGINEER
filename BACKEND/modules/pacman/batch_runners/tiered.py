"""
PACMAN Tiered Runner
Tiered scraping: A (httpx) -> B (Colly) -> C (Rod) -> D (Playwright)
"""

import asyncio
import time
from typing import Dict, List, Optional, AsyncIterator
from datetime import datetime

try:
    import httpx
except ImportError:
    httpx = None

from .base import BaseRunner, RunnerResult, RunnerStatus
from ..config.settings import (
    CONCURRENT_TIER_A, CONCURRENT_TIER_B, CONCURRENT_TIER_C,
    TIMEOUT_TIER_A, TIMEOUT_TIER_B, TIMEOUT_TIER_C,
    COLLY_BIN, ROD_BIN,
)
from ..classifiers import classify_url, classify_content, Tier
from ..entity_extractors import extract_fast
from ..link_extractors import extract_links


class TieredRunner(BaseRunner):
    """
    Tiered scraping runner.
    Tries methods in order: A -> B -> C -> D
    """
    
    name = 'tiered'
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._http_client = None
        self._semaphore_a = asyncio.Semaphore(CONCURRENT_TIER_A)
        self._semaphore_b = asyncio.Semaphore(CONCURRENT_TIER_B)
        self._semaphore_c = asyncio.Semaphore(CONCURRENT_TIER_C)
    
    async def _get_client(self):
        if self._http_client is None and httpx:
            self._http_client = httpx.AsyncClient(
                timeout=TIMEOUT_TIER_A,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; PACMAN/1.0)'}
            )
        return self._http_client
    
    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def run(self, inputs: List[str]) -> AsyncIterator[RunnerResult]:
        """Run tiered extraction on URLs."""
        self.status = RunnerStatus.RUNNING
        self.stats.total = len(inputs)
        self.stats.start_time = datetime.utcnow()
        
        # Load checkpoint if exists
        processed = set(self.load_checkpoint())
        remaining = [u for u in inputs if u not in processed]
        
        # Process in batches
        batch_size = CONCURRENT_TIER_A
        for i in range(0, len(remaining), batch_size):
            if self.status == RunnerStatus.PAUSED:
                break
            
            batch = remaining[i:i + batch_size]
            tasks = [self.run_single(url) for url in batch]
            
            for result in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(result, Exception):
                    self.stats.failed += 1
                    yield RunnerResult(
                        url='unknown',
                        status='error',
                        error=str(result)
                    )
                else:
                    self.stats.processed += 1
                    if result.status == 'success':
                        self.stats.succeeded += 1
                    else:
                        self.stats.failed += 1
                    yield result
            
            # Save checkpoint
            processed.update(batch)
            self.save_checkpoint(list(processed))
        
        self.stats.end_time = datetime.utcnow()
        self.status = RunnerStatus.COMPLETED
    
    async def run_single(self, url: str) -> RunnerResult:
        """Process a single URL through tiers."""
        start_time = time.time()
        
        # Pre-classify URL
        url_tier = classify_url(url)
        if url_tier.tier == Tier.SKIP:
            return RunnerResult(
                url=url,
                status='skipped',
                tier='SKIP',
                metadata={'skip_reason': url_tier.reasons}
            )
        
        # Try Tier A: httpx
        async with self._semaphore_a:
            result = await self._try_tier_a(url)
            if result:
                result.duration_ms = int((time.time() - start_time) * 1000)
                return result
        
        # Try Tier B: Colly
        async with self._semaphore_b:
            result = await self._try_tier_b(url)
            if result:
                result.duration_ms = int((time.time() - start_time) * 1000)
                return result
        
        # Try Tier C: Rod
        async with self._semaphore_c:
            result = await self._try_tier_c(url)
            if result:
                result.duration_ms = int((time.time() - start_time) * 1000)
                return result
        
        # All tiers failed
        return RunnerResult(
            url=url,
            status='failed',
            error='All tiers failed',
            duration_ms=int((time.time() - start_time) * 1000)
        )
    
    async def _try_tier_a(self, url: str) -> Optional[RunnerResult]:
        """Try httpx (fast, async)."""
        if not httpx:
            return None
        
        try:
            client = await self._get_client()
            response = await client.get(url)
            
            if response.status_code == 200:
                content = response.text
                
                # Extract entities
                entities = extract_fast(content)
                
                # Extract links
                links = extract_links(content, url)
                link_urls = [l.url for l in links[:50]]
                
                # Classify content
                tier_result = classify_content(content, url)
                
                return RunnerResult(
                    url=url,
                    status='success',
                    content=content[:50000],
                    entities=entities,
                    links=link_urls,
                    tier=tier_result.tier.value,
                    scrape_method='TIER_A_HTTPX'
                )
            elif response.status_code in (403, 429, 503):
                return None  # Try next tier
            else:
                return RunnerResult(
                    url=url,
                    status='failed',
                    error=f'HTTP {response.status_code}',
                    scrape_method='TIER_A_HTTPX'
                )
        except Exception as e:
            return None  # Try next tier
    
    async def _try_tier_b(self, url: str) -> Optional[RunnerResult]:
        """Try Colly Go binary (static HTML)."""
        import subprocess
        from pathlib import Path
        
        if not Path(COLLY_BIN).exists():
            return None
        
        try:
            proc = await asyncio.create_subprocess_exec(
                COLLY_BIN, url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=TIMEOUT_TIER_B
            )
            
            if proc.returncode == 0 and stdout:
                content = stdout.decode('utf-8', errors='replace')
                entities = extract_fast(content)
                links = extract_links(content, url)
                tier_result = classify_content(content, url)
                
                return RunnerResult(
                    url=url,
                    status='success',
                    content=content[:50000],
                    entities=entities,
                    links=[l.url for l in links[:50]],
                    tier=tier_result.tier.value,
                    scrape_method='TIER_B_COLLY'
                )
            return None
        except Exception:
            return None
    
    async def _try_tier_c(self, url: str) -> Optional[RunnerResult]:
        """Try Rod Go binary (JS rendering)."""
        import subprocess
        from pathlib import Path
        
        if not Path(ROD_BIN).exists():
            return None
        
        try:
            proc = await asyncio.create_subprocess_exec(
                ROD_BIN, url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=TIMEOUT_TIER_C
            )
            
            if proc.returncode == 0 and stdout:
                content = stdout.decode('utf-8', errors='replace')
                entities = extract_fast(content)
                links = extract_links(content, url)
                tier_result = classify_content(content, url)
                
                return RunnerResult(
                    url=url,
                    status='success',
                    content=content[:50000],
                    entities=entities,
                    links=[l.url for l in links[:50]],
                    tier=tier_result.tier.value,
                    scrape_method='TIER_C_ROD'
                )
            return None
        except Exception:
            return None
