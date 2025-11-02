#!/usr/bin/env python3
"""
FirmenABC Optimized Multi-Engine Scraper
Intelligently distributes load across Firecrawl, Apify, and HTTP
with proxy support and rate limit optimization
"""

import asyncio
import time
import random
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
from collections import deque
import logging
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

class EngineType(Enum):
    FIRECRAWL = "firecrawl"
    APIFY = "apify"
    HTTP = "http"

@dataclass
class EngineConfig:
    """Configuration for each scraping engine"""
    engine_type: EngineType
    max_concurrent: int
    requests_per_second: float
    cost_per_request: float  # in USD
    has_proxy: bool
    batch_size: Optional[int] = None
    
    @property
    def delay_between_requests(self) -> float:
        """Calculate delay needed between requests"""
        return 1.0 / self.requests_per_second if self.requests_per_second > 0 else 0

@dataclass
class ScrapingTask:
    """Represents a URL to be scraped"""
    url: str
    sitemap_source: str
    entity_type: str  # 'company' or 'person'
    priority: int = 0  # Higher priority processed first
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class EngineStats:
    """Track performance metrics for each engine"""
    processed: int = 0
    failed: int = 0
    total_time: float = 0
    last_request_time: float = 0
    current_load: int = 0
    
    @property
    def success_rate(self) -> float:
        total = self.processed + self.failed
        return self.processed / total if total > 0 else 1.0
    
    @property
    def avg_time_per_request(self) -> float:
        return self.total_time / self.processed if self.processed > 0 else 1.0

class OptimizedScraper:
    """
    Multi-engine scraper with intelligent load distribution
    """
    
    # Engine configurations with real-world constraints
    ENGINE_CONFIGS = {
        EngineType.FIRECRAWL: EngineConfig(
            engine_type=EngineType.FIRECRAWL,
            max_concurrent=50,  # Firecrawl supports 50 parallel
            requests_per_second=25,  # Can handle high throughput
            cost_per_request=0.002,
            has_proxy=True,  # Built-in proxy rotation
            batch_size=50
        ),
        EngineType.APIFY: EngineConfig(
            engine_type=EngineType.APIFY,
            max_concurrent=30,  # Apify actor concurrency
            requests_per_second=10,  # More conservative
            cost_per_request=0.001,
            has_proxy=True,  # useApifyProxy option
            batch_size=100  # Can process many URLs in one actor run
        ),
        EngineType.HTTP: EngineConfig(
            engine_type=EngineType.HTTP,
            max_concurrent=10,  # Be polite without proxy
            requests_per_second=2,  # Rate limited without proxy
            cost_per_request=0.0,  # Free but slow
            has_proxy=False,
            batch_size=1
        )
    }
    
    def __init__(self, 
                 enable_firecrawl: bool = True,
                 enable_apify: bool = True,
                 enable_http: bool = True,
                 optimize_for: str = "speed"):  # "speed", "cost", or "reliability"
        
        self.engines: Dict[EngineType, EngineConfig] = {}
        self.engine_stats: Dict[EngineType, EngineStats] = {}
        
        # Initialize available engines
        if enable_firecrawl:
            self.engines[EngineType.FIRECRAWL] = self.ENGINE_CONFIGS[EngineType.FIRECRAWL]
            self.engine_stats[EngineType.FIRECRAWL] = EngineStats()
            
        if enable_apify:
            self.engines[EngineType.APIFY] = self.ENGINE_CONFIGS[EngineType.APIFY]
            self.engine_stats[EngineType.APIFY] = EngineStats()
            
        if enable_http:
            self.engines[EngineType.HTTP] = self.ENGINE_CONFIGS[EngineType.HTTP]
            self.engine_stats[EngineType.HTTP] = EngineStats()
        
        self.optimize_for = optimize_for
        self.task_queue: deque[ScrapingTask] = deque()
        self.processing: Set[str] = set()  # URLs currently being processed
        self.completed: Set[str] = set()
        
        logger.info(f"Initialized with engines: {list(self.engines.keys())}")
        logger.info(f"Optimization strategy: {optimize_for}")
    
    def add_tasks_from_sitemap(self, sitemap_url: str, entity_type: str = "company"):
        """Add all URLs from a sitemap to the task queue"""
        import requests
        import xml.etree.ElementTree as ET
        
        try:
            resp = requests.get(sitemap_url, timeout=30)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                count = 0
                for url_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                    url = url_elem.text
                    # Assign priority based on URL patterns
                    priority = 0
                    if "ag_" in url or "gmbh_" in url:  # Prioritize companies
                        priority = 10
                    elif "/person/" in url:  # Lower priority for persons
                        priority = 5
                        
                    task = ScrapingTask(
                        url=url,
                        sitemap_source=sitemap_url,
                        entity_type=entity_type,
                        priority=priority
                    )
                    self.task_queue.append(task)
                    count += 1
                    
                logger.info(f"Added {count} tasks from sitemap {sitemap_url[:50]}...")
                return count
        except Exception as e:
            logger.error(f"Failed to fetch sitemap: {e}")
        return 0
    
    def select_best_engine(self) -> Optional[EngineType]:
        """
        Select the best engine based on current conditions and optimization strategy
        """
        available_engines = []
        
        for engine_type, config in self.engines.items():
            stats = self.engine_stats[engine_type]
            
            # Check if engine is available (not overloaded)
            if stats.current_load < config.max_concurrent:
                # Check rate limiting
                time_since_last = time.time() - stats.last_request_time
                if time_since_last >= config.delay_between_requests:
                    available_engines.append(engine_type)
        
        if not available_engines:
            return None
        
        # Select based on optimization strategy
        if self.optimize_for == "speed":
            # Choose fastest engine (highest requests per second)
            return max(available_engines, 
                      key=lambda e: self.engines[e].requests_per_second)
            
        elif self.optimize_for == "cost":
            # Choose cheapest engine
            return min(available_engines,
                      key=lambda e: self.engines[e].cost_per_request)
            
        elif self.optimize_for == "reliability":
            # Choose most reliable engine (highest success rate)
            return max(available_engines,
                      key=lambda e: self.engine_stats[e].success_rate)
        
        # Default: round-robin
        return random.choice(available_engines)
    
    async def process_with_engine(self, 
                                  tasks: List[ScrapingTask], 
                                  engine_type: EngineType) -> List[bool]:
        """
        Process a batch of tasks with the specified engine
        Returns list of success/failure for each task
        """
        config = self.engines[engine_type]
        stats = self.engine_stats[engine_type]
        
        logger.info(f"Processing {len(tasks)} tasks with {engine_type.value}")
        
        # Update stats
        stats.current_load += len(tasks)
        stats.last_request_time = time.time()
        start_time = time.time()
        
        results = []
        
        try:
            if engine_type == EngineType.FIRECRAWL:
                results = await self._process_firecrawl(tasks, config)
            elif engine_type == EngineType.APIFY:
                results = await self._process_apify(tasks, config)
            else:  # HTTP
                results = await self._process_http(tasks, config)
            
            # Update statistics
            success_count = sum(results)
            stats.processed += success_count
            stats.failed += len(results) - success_count
            stats.total_time += time.time() - start_time
            
        except Exception as e:
            logger.error(f"Engine {engine_type.value} error: {e}")
            results = [False] * len(tasks)
            stats.failed += len(tasks)
        
        finally:
            stats.current_load -= len(tasks)
        
        return results
    
    async def _process_firecrawl(self, 
                                 tasks: List[ScrapingTask], 
                                 config: EngineConfig) -> List[bool]:
        """Process with Firecrawl batch API"""
        # Simulate Firecrawl batch processing
        # In production, this would call the actual Firecrawl API
        
        urls = [task.url for task in tasks]
        
        # Firecrawl features:
        # - Batch processing up to 50 URLs
        # - Built-in proxy rotation
        # - Async job processing
        
        logger.info(f"🔥 Firecrawl batch: {len(urls)} URLs with proxy rotation")
        
        # Add some processing delay
        await asyncio.sleep(len(urls) * 0.02)  # ~20ms per URL in batch
        
        # Simulate 95% success rate with proxy
        results = [random.random() < 0.95 for _ in tasks]
        
        for task, success in zip(tasks, results):
            if success:
                self.completed.add(task.url)
            elif task.retry_count < task.max_retries:
                task.retry_count += 1
                self.task_queue.append(task)  # Re-queue for retry
        
        return results
    
    async def _process_apify(self, 
                            tasks: List[ScrapingTask], 
                            config: EngineConfig) -> List[bool]:
        """Process with Apify actor"""
        # Simulate Apify actor processing
        
        urls = [task.url for task in tasks]
        
        # Apify features:
        # - Actor-based processing
        # - Built-in proxy (useApifyProxy)
        # - Concurrent crawling
        
        logger.info(f"🎭 Apify actor: {len(urls)} URLs with proxy")
        
        # Add actor startup time + processing
        await asyncio.sleep(2 + len(urls) * 0.05)  # Startup + 50ms per URL
        
        # Simulate 90% success rate
        results = [random.random() < 0.90 for _ in tasks]
        
        for task, success in zip(tasks, results):
            if success:
                self.completed.add(task.url)
            elif task.retry_count < task.max_retries:
                task.retry_count += 1
                task.priority -= 1  # Lower priority for retries
                self.task_queue.append(task)
        
        return results
    
    async def _process_http(self, 
                           tasks: List[ScrapingTask], 
                           config: EngineConfig) -> List[bool]:
        """Process with direct HTTP requests"""
        # Simulate HTTP processing
        
        # HTTP limitations:
        # - No proxy (unless custom implementation)
        # - Rate limited to avoid blocking
        # - Sequential or limited concurrent
        
        logger.info(f"🌐 HTTP: {len(tasks)} URLs (no proxy, rate limited)")
        
        results = []
        for task in tasks:
            # Add delay for rate limiting
            await asyncio.sleep(config.delay_between_requests)
            
            # Simulate 70% success rate without proxy
            success = random.random() < 0.70
            results.append(success)
            
            if success:
                self.completed.add(task.url)
            elif task.retry_count < task.max_retries:
                task.retry_count += 1
                task.priority -= 2  # Lower priority significantly
                self.task_queue.append(task)
        
        return results
    
    async def run(self, max_urls: int = 10000):
        """
        Main processing loop with intelligent distribution
        """
        logger.info("="*80)
        logger.info("OPTIMIZED MULTI-ENGINE SCRAPING")
        logger.info(f"Strategy: {self.optimize_for}")
        logger.info(f"Max URLs: {max_urls}")
        logger.info("="*80)
        
        processed_count = 0
        start_time = time.time()
        
        # Process while we have tasks and haven't hit the limit
        while self.task_queue and processed_count < max_urls:
            # Select best engine
            engine = self.select_best_engine()
            
            if not engine:
                # All engines are busy or rate limited
                await asyncio.sleep(0.1)
                continue
            
            config = self.engines[engine]
            
            # Get batch of tasks
            batch_size = min(
                config.batch_size or 1,
                len(self.task_queue),
                max_urls - processed_count
            )
            
            batch = []
            for _ in range(batch_size):
                if self.task_queue:
                    # Get highest priority task
                    task = self.task_queue.popleft()
                    batch.append(task)
                    self.processing.add(task.url)
            
            if batch:
                # Process batch with selected engine
                results = await self.process_with_engine(batch, engine)
                processed_count += len(batch)
                
                # Remove from processing set
                for task in batch:
                    self.processing.discard(task.url)
                
                # Log progress
                elapsed = time.time() - start_time
                rate = processed_count / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {processed_count}/{max_urls} "
                          f"({rate:.1f} URLs/sec) - "
                          f"Queue: {len(self.task_queue)}")
        
        # Final statistics
        elapsed = time.time() - start_time
        
        logger.info("\n" + "="*80)
        logger.info("SCRAPING COMPLETE")
        logger.info("="*80)
        
        logger.info(f"\n📊 Overall Statistics:")
        logger.info(f"  Total processed: {processed_count}")
        logger.info(f"  Total time: {elapsed:.2f} seconds")
        logger.info(f"  Average rate: {processed_count/elapsed:.1f} URLs/second")
        logger.info(f"  Completed successfully: {len(self.completed)}")
        
        logger.info(f"\n📈 Engine Performance:")
        total_cost = 0
        for engine_type, stats in self.engine_stats.items():
            if stats.processed > 0 or stats.failed > 0:
                config = self.engines[engine_type]
                cost = stats.processed * config.cost_per_request
                total_cost += cost
                
                logger.info(f"\n  {engine_type.value}:")
                logger.info(f"    Processed: {stats.processed}")
                logger.info(f"    Failed: {stats.failed}")
                logger.info(f"    Success rate: {stats.success_rate:.1%}")
                logger.info(f"    Avg time: {stats.avg_time_per_request:.3f}s")
                logger.info(f"    Cost: ${cost:.2f}")
                logger.info(f"    Has proxy: {config.has_proxy}")
        
        logger.info(f"\n💰 Total cost: ${total_cost:.2f}")
        
        # Cost savings analysis
        if EngineType.HTTP in self.engine_stats:
            http_only_time = processed_count / self.ENGINE_CONFIGS[EngineType.HTTP].requests_per_second
            time_saved = http_only_time - elapsed
            logger.info(f"\n⚡ Time saved vs HTTP-only: {time_saved:.1f} seconds")
            logger.info(f"   Speed improvement: {http_only_time/elapsed:.1f}x")

async def main():
    """Demo the optimized scraper"""
    
    # Example sitemaps
    sitemaps = [
        ("https://www.firmenabc.at/sitemap.xml?page=1&sitemap=companies&cHash=270921102c6eeb450d3b381a2d5eda55", "company"),
        ("https://www.firmenabc.at/sitemap.xml?page=2&sitemap=companies&cHash=df1db4099f0cabdb6eb4c6f4b07245d9", "company"),
        ("https://www.firmenabc.at/sitemap.xml?sitemap=shareholders&cHash=2dd6b9836bca3484a6ea0698485c65e5", "person"),
    ]
    
    # Test different optimization strategies
    for strategy in ["speed", "cost", "reliability"]:
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing strategy: {strategy.upper()}")
        logger.info("="*80)
        
        scraper = OptimizedScraper(
            enable_firecrawl=True,
            enable_apify=True,
            enable_http=True,
            optimize_for=strategy
        )
        
        # Add tasks from sitemaps
        total_tasks = 0
        for sitemap_url, entity_type in sitemaps:
            count = scraper.add_tasks_from_sitemap(sitemap_url, entity_type)
            total_tasks += count
        
        logger.info(f"Total tasks queued: {total_tasks}")
        
        # Run scraping
        await scraper.run(max_urls=100)  # Process first 100 for demo
        
        # Small delay between strategies
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())