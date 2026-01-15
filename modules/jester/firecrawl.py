"""
Firecrawl - External Firecrawl API v2

External paid API fallback (NOT part of JESTER).
Use when JESTER A/B/C/D all fail.

Usage:
    from modules.jester.firecrawl import Firecrawl, scrape_firecrawl

    scraper = Firecrawl()
    result = await scraper.scrape("https://example.com")

    # Batch scrape v2 (async job with polling)
    results = await scraper.batch_scrape_v2(
        urls=["https://a.com", "https://b.com"],
        formats=["html", "markdown"],
        max_concurrency=50,
    )

Requires:
    FIRECRAWL_API_KEY environment variable
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from enum import Enum

import httpx
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

logger = logging.getLogger("FIRECRAWL")

# Constants
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CONCURRENT = 10  # Firecrawl rate limits
MIN_VALID_HTML_LENGTH = 100
DEFAULT_BASE_URL = "https://api.firecrawl.dev/v2"


# =============================================================================
# ENUMS & TYPES
# =============================================================================

class ProxyType(str, Enum):
    """Firecrawl proxy types."""
    BASIC = "basic"      # Fast, basic anti-bot
    STEALTH = "stealth"  # Advanced anti-bot, 5 credits/request
    AUTO = "auto"        # Auto-retry with stealth if basic fails


class ActionType(str, Enum):
    """Pre-scrape action types."""
    WAIT = "wait"
    CLICK = "click"
    WRITE = "write"
    PRESS = "press"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    SCRAPE = "scrape"
    EXECUTE_JS = "executeJavascript"
    PDF = "pdf"


@dataclass
class ScrapeAction:
    """Action to perform before scraping."""
    type: ActionType
    selector: Optional[str] = None
    milliseconds: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    direction: Optional[str] = None  # "up" or "down"
    script: Optional[str] = None
    full_page: Optional[bool] = None
    all_matches: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API payload."""
        d = {"type": self.type.value if isinstance(self.type, ActionType) else self.type}
        if self.selector:
            d["selector"] = self.selector
        if self.milliseconds:
            d["milliseconds"] = self.milliseconds
        if self.text:
            d["text"] = self.text
        if self.key:
            d["key"] = self.key
        if self.direction:
            d["direction"] = self.direction
        if self.script:
            d["script"] = self.script
        if self.full_page is not None:
            d["fullPage"] = self.full_page
        if self.all_matches is not None:
            d["all"] = self.all_matches
        return d


@dataclass
class WebhookConfig:
    """Webhook configuration for batch scrape."""
    url: str
    headers: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, Any]] = None
    events: Optional[List[str]] = None  # "completed", "page", "failed", "started"

    def to_dict(self) -> Dict[str, Any]:
        d = {"url": self.url}
        if self.headers:
            d["headers"] = self.headers
        if self.metadata:
            d["metadata"] = self.metadata
        if self.events:
            d["events"] = self.events
        return d


@dataclass
class BatchScrapeStatus:
    """Status of a batch scrape job."""
    job_id: str
    status: str  # "scraping", "completed", "failed"
    total: int = 0
    completed: int = 0
    credits_used: int = 0
    expires_at: Optional[str] = None
    invalid_urls: List[str] = field(default_factory=list)


@dataclass
class FirecrawlResult:
    """Result from Firecrawl API scrape."""
    url: str
    html: str
    status_code: int
    latency_ms: int
    content_length: int
    markdown: str = ""
    metadata: Dict = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def success(self) -> bool:
        return self.html and len(self.html) >= MIN_VALID_HTML_LENGTH and not self.error


class Firecrawl:
    """
    Firecrawl API wrapper.

    External paid service for scraping. Reliable fallback when
    JESTER A/B/C/D fail. Handles JavaScript, bypasses some anti-bot.

    Requires FIRECRAWL_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        use_cache: bool = True,
    ):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self.base_url = base_url
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.use_cache = use_cache

        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    @property
    def available(self) -> bool:
        """Check if Firecrawl API key is configured."""
        return bool(self.api_key)

    async def _ensure_init(self):
        """Initialize HTTP client if needed."""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("FIRECRAWL_API_KEY not configured")

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._ensure_init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def scrape(
        self,
        url: str,
        formats: List[str] = None,
        only_main_content: bool = False,
        country: Optional[str] = None,
        languages: Optional[List[str]] = None,
    ) -> FirecrawlResult:
        """
        Scrape a single URL with Firecrawl API.

        Args:
            url: URL to scrape
            formats: Output formats (default: ["html"])
            only_main_content: Extract only main content (default: False)
            country: Proxy location country code (e.g., "US", "BR")
            languages: Proxy location languages (e.g., ["en"])

        Returns:
            FirecrawlResult with HTML content or error
        """
        await self._ensure_init()
        start = time.time()

        if formats is None:
            formats = ["html"]

        try:
            async with self._semaphore:
                payload = {
                    "url": url,
                    "formats": formats,
                    "onlyMainContent": only_main_content,
                }

                # Location-based proxy configuration
                if country or languages:
                    payload["location"] = {}
                    if country:
                        payload["location"]["country"] = country
                    if languages:
                        payload["location"]["languages"] = languages

                # Use cache for faster responses (30 days)
                if self.use_cache:
                    payload["maxAge"] = 2592000000  # 30 days in ms

                resp = await self._client.post(
                    f"{self.base_url}/scrape",
                    json=payload,
                )
                latency = int((time.time() - start) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    result_data = data.get("data", {})

                    html = result_data.get("html", "")
                    markdown = result_data.get("markdown", "")
                    metadata = result_data.get("metadata", {})

                    return FirecrawlResult(
                        url=url,
                        html=html,
                        status_code=200,
                        latency_ms=latency,
                        content_length=len(html),
                        markdown=markdown,
                        metadata=metadata,
                    )

                # Handle errors
                error_msg = f"Firecrawl returned {resp.status_code}"
                try:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                except:
                    pass

                return FirecrawlResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=latency,
                    content_length=0,
                    error=error_msg,
                )

        except httpx.TimeoutException:
            latency = int((time.time() - start) * 1000)
            return FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="Timeout",
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e),
            )

    async def scrape_batch(
        self,
        urls: List[str],
        country: Optional[str] = None,
        languages: Optional[List[str]] = None,
    ) -> List[FirecrawlResult]:
        """
        Scrape multiple URLs with Firecrawl API.

        Rate limited to avoid API throttling.

        Args:
            urls: List of URLs to scrape
            country: Proxy location country code to apply to all URLs
            languages: Proxy location languages to apply to all URLs

        Returns:
            List of FirecrawlResult for each URL
        """
        if not urls:
            return []

        await self._ensure_init()

        tasks = [self.scrape(url, country=country, languages=languages) for url in urls]
        return await asyncio.gather(*tasks)

    async def crawl(
        self,
        url: str,
        max_depth: int = 2,
        max_pages: int = 10,
        formats: List[str] = None,
    ) -> List[FirecrawlResult]:
        """
        Crawl a website starting from URL (Firecrawl's crawl endpoint).

        Args:
            url: Starting URL
            max_depth: Maximum crawl depth
            max_pages: Maximum pages to crawl
            formats: Output formats

        Returns:
            List of FirecrawlResult for crawled pages
        """
        await self._ensure_init()

        if formats is None:
            formats = ["html"]

        try:
            # Start crawl job
            resp = await self._client.post(
                f"{self.base_url}/crawl",
                json={
                    "url": url,
                    "maxDepth": max_depth,
                    "limit": max_pages,
                    "scrapeOptions": {
                        "formats": formats,
                    },
                },
            )

            if resp.status_code != 200:
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=0,
                    content_length=0,
                    error=f"Crawl start failed: {resp.status_code}",
                )]

            data = resp.json()
            job_id = data.get("id")

            if not job_id:
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=0,
                    content_length=0,
                    error="No job ID returned",
                )]

            # Poll for completion
            results = []
            while True:
                await asyncio.sleep(2)  # Poll every 2 seconds

                status_resp = await self._client.get(f"{self.base_url}/crawl/{job_id}")
                status_data = status_resp.json()

                status = status_data.get("status")
                if status == "completed":
                    for page in status_data.get("data", []):
                        results.append(FirecrawlResult(
                            url=page.get("url", url),
                            html=page.get("html", ""),
                            status_code=200,
                            latency_ms=0,
                            content_length=len(page.get("html", "")),
                            markdown=page.get("markdown", ""),
                            metadata=page.get("metadata", {}),
                        ))
                    break
                elif status == "failed":
                    return [FirecrawlResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=0,
                        content_length=0,
                        error=status_data.get("error", "Crawl failed"),
                    )]

            return results

        except Exception as e:
            return [FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=0,
                content_length=0,
                error=str(e),
            )]

    # =========================================================================
    # BATCH SCRAPE V2 - Async job-based batch scraping
    # =========================================================================

    async def batch_scrape_v2(
        self,
        urls: List[str],
        formats: Optional[List[str]] = None,
        only_main_content: bool = True,
        country: Optional[str] = None,
        languages: Optional[List[str]] = None,
        actions: Optional[List[ScrapeAction]] = None,
        proxy: Optional[ProxyType] = None,
        max_concurrency: Optional[int] = None,
        webhook: Optional[WebhookConfig] = None,
        ignore_invalid_urls: bool = True,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        wait_for: int = 0,
        mobile: bool = False,
        block_ads: bool = True,
        timeout_ms: Optional[int] = None,
        poll_interval: float = 2.0,
        max_poll_time: float = 600.0,
        progress_callback: Optional[Callable[[BatchScrapeStatus], None]] = None,
    ) -> List[FirecrawlResult]:
        """
        Batch scrape multiple URLs using Firecrawl v2 async job API.

        This submits a batch job and polls for completion. More efficient than
        individual scrapes for large URL lists.

        Args:
            urls: List of URLs to scrape
            formats: Output formats - "html", "markdown", "links", "screenshot", etc.
            only_main_content: Extract only main content (default True)
            country: ISO country code for proxy location (e.g., "US", "DE")
            languages: Preferred languages (e.g., ["en-US"])
            actions: Pre-scrape actions (click, wait, scroll, etc.)
            proxy: Proxy type - "basic", "stealth", or "auto"
            max_concurrency: Max concurrent scrapes (defaults to team limit)
            webhook: Webhook config for real-time updates
            ignore_invalid_urls: Skip invalid URLs instead of failing (default True)
            include_tags: HTML tags to include
            exclude_tags: HTML tags to exclude
            wait_for: Milliseconds to wait before scraping
            mobile: Emulate mobile device
            block_ads: Block ads and cookie popups (default True)
            timeout_ms: Request timeout in milliseconds
            poll_interval: Seconds between status polls (default 2.0)
            max_poll_time: Maximum seconds to wait for completion (default 600)
            progress_callback: Optional callback for progress updates

        Returns:
            List of FirecrawlResult for each URL

        Example:
            results = await firecrawl.batch_scrape_v2(
                urls=["https://example.com", "https://test.com"],
                formats=["html", "markdown"],
                actions=[
                    ScrapeAction(type=ActionType.WAIT, milliseconds=2000),
                    ScrapeAction(type=ActionType.CLICK, selector="#load-more"),
                ],
                proxy=ProxyType.AUTO,
                max_concurrency=50,
            )
        """
        await self._ensure_init()

        if not urls:
            return []

        if formats is None:
            formats = ["html", "markdown"]

        start_time = time.time()

        # Build payload
        payload: Dict[str, Any] = {
            "urls": urls,
            "formats": formats,
            "onlyMainContent": only_main_content,
            "ignoreInvalidURLs": ignore_invalid_urls,
            "blockAds": block_ads,
        }

        # Location settings
        if country or languages:
            payload["location"] = {}
            if country:
                payload["location"]["country"] = country
            if languages:
                payload["location"]["languages"] = languages

        # Actions
        if actions:
            payload["actions"] = [a.to_dict() for a in actions]

        # Proxy
        if proxy:
            payload["proxy"] = proxy.value if isinstance(proxy, ProxyType) else proxy

        # Concurrency
        if max_concurrency:
            payload["maxConcurrency"] = max_concurrency

        # Webhook
        if webhook:
            payload["webhook"] = webhook.to_dict()

        # Optional filters
        if include_tags:
            payload["includeTags"] = include_tags
        if exclude_tags:
            payload["excludeTags"] = exclude_tags
        if wait_for > 0:
            payload["waitFor"] = wait_for
        if mobile:
            payload["mobile"] = True
        if timeout_ms:
            payload["timeout"] = timeout_ms

        # Use cache for faster responses
        if self.use_cache:
            payload["maxAge"] = 172800000  # 2 days in ms (v2 default)

        try:
            # Submit batch job
            logger.info(f"Submitting batch scrape for {len(urls)} URLs...")
            resp = await self._client.post(
                f"{self.base_url}/batch/scrape",
                json=payload,
            )

            if resp.status_code != 200:
                error_msg = f"Batch scrape start failed: {resp.status_code}"
                try:
                    error_data = resp.json()
                    if "error" in error_data:
                        error_msg = error_data["error"]
                except:
                    pass
                logger.error(error_msg)
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=resp.status_code,
                    latency_ms=0,
                    content_length=0,
                    error=error_msg,
                ) for url in urls]

            data = resp.json()
            job_id = data.get("id")
            invalid_urls = data.get("invalidURLs", [])

            if not job_id:
                return [FirecrawlResult(
                    url=url,
                    html="",
                    status_code=0,
                    latency_ms=0,
                    content_length=0,
                    error="No job ID returned",
                ) for url in urls]

            logger.info(f"Batch job started: {job_id}")
            if invalid_urls:
                logger.warning(f"Invalid URLs skipped: {invalid_urls}")

            # Poll for completion
            results: List[FirecrawlResult] = []
            url_to_result: Dict[str, FirecrawlResult] = {}

            while (time.time() - start_time) < max_poll_time:
                await asyncio.sleep(poll_interval)

                status_resp = await self._client.get(f"{self.base_url}/batch/scrape/{job_id}")

                if status_resp.status_code != 200:
                    logger.warning(f"Status check failed: {status_resp.status_code}")
                    continue

                status_data = status_resp.json()
                status = status_data.get("status", "unknown")
                total = status_data.get("total", len(urls))
                completed = status_data.get("completed", 0)
                credits_used = status_data.get("creditsUsed", 0)

                # Report progress
                batch_status = BatchScrapeStatus(
                    job_id=job_id,
                    status=status,
                    total=total,
                    completed=completed,
                    credits_used=credits_used,
                    invalid_urls=invalid_urls,
                )

                if progress_callback:
                    progress_callback(batch_status)

                logger.debug(f"Batch status: {status} ({completed}/{total})")

                # Process completed results
                for page in status_data.get("data", []):
                    page_url = page.get("metadata", {}).get("sourceURL") or page.get("url", "")
                    if page_url and page_url not in url_to_result:
                        url_to_result[page_url] = FirecrawlResult(
                            url=page_url,
                            html=page.get("html", ""),
                            status_code=page.get("metadata", {}).get("statusCode", 200),
                            latency_ms=0,
                            content_length=len(page.get("html", "")),
                            markdown=page.get("markdown", ""),
                            metadata=page.get("metadata", {}),
                        )

                if status == "completed":
                    logger.info(f"Batch completed: {completed} pages, {credits_used} credits")
                    break
                elif status == "failed":
                    error = status_data.get("error", "Batch scrape failed")
                    logger.error(f"Batch failed: {error}")
                    # Return partial results + errors for remaining
                    break

            # Build final results list preserving URL order
            latency = int((time.time() - start_time) * 1000)

            for url in urls:
                if url in url_to_result:
                    result = url_to_result[url]
                    result.latency_ms = latency
                    results.append(result)
                elif url in invalid_urls:
                    results.append(FirecrawlResult(
                        url=url,
                        html="",
                        status_code=400,
                        latency_ms=latency,
                        content_length=0,
                        error="Invalid URL",
                    ))
                else:
                    results.append(FirecrawlResult(
                        url=url,
                        html="",
                        status_code=0,
                        latency_ms=latency,
                        content_length=0,
                        error="No result returned",
                    ))

            return results

        except httpx.TimeoutException:
            latency = int((time.time() - start_time) * 1000)
            return [FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error="Batch scrape timeout",
            ) for url in urls]
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            logger.error(f"Batch scrape error: {e}")
            return [FirecrawlResult(
                url=url,
                html="",
                status_code=0,
                latency_ms=latency,
                content_length=0,
                error=str(e),
            ) for url in urls]

    async def batch_scrape_v2_start(
        self,
        urls: List[str],
        **kwargs,
    ) -> Optional[str]:
        """
        Start a batch scrape job and return the job ID immediately.

        Use this for fire-and-forget batch scrapes with webhooks,
        or when you want to poll manually.

        Args:
            urls: List of URLs to scrape
            **kwargs: Same options as batch_scrape_v2

        Returns:
            Job ID string, or None on failure
        """
        await self._ensure_init()

        if not urls:
            return None

        formats = kwargs.get("formats", ["html", "markdown"])

        payload: Dict[str, Any] = {
            "urls": urls,
            "formats": formats,
            "onlyMainContent": kwargs.get("only_main_content", True),
            "ignoreInvalidURLs": kwargs.get("ignore_invalid_urls", True),
            "blockAds": kwargs.get("block_ads", True),
        }

        # Location
        country = kwargs.get("country")
        languages = kwargs.get("languages")
        if country or languages:
            payload["location"] = {}
            if country:
                payload["location"]["country"] = country
            if languages:
                payload["location"]["languages"] = languages

        # Actions
        actions = kwargs.get("actions")
        if actions:
            payload["actions"] = [a.to_dict() for a in actions]

        # Proxy
        proxy = kwargs.get("proxy")
        if proxy:
            payload["proxy"] = proxy.value if isinstance(proxy, ProxyType) else proxy

        # Concurrency
        max_concurrency = kwargs.get("max_concurrency")
        if max_concurrency:
            payload["maxConcurrency"] = max_concurrency

        # Webhook
        webhook = kwargs.get("webhook")
        if webhook:
            payload["webhook"] = webhook.to_dict()

        try:
            resp = await self._client.post(
                f"{self.base_url}/batch/scrape",
                json=payload,
            )

            if resp.status_code == 200:
                data = resp.json()
                return data.get("id")
            else:
                logger.error(f"Batch start failed: {resp.status_code}")
                return None

        except Exception as e:
            logger.error(f"Batch start error: {e}")
            return None

    async def batch_scrape_v2_status(
        self,
        job_id: str,
    ) -> Optional[BatchScrapeStatus]:
        """
        Check status of a batch scrape job.

        Args:
            job_id: Job ID from batch_scrape_v2_start

        Returns:
            BatchScrapeStatus or None on error
        """
        await self._ensure_init()

        try:
            resp = await self._client.get(f"{self.base_url}/batch/scrape/{job_id}")

            if resp.status_code == 200:
                data = resp.json()
                return BatchScrapeStatus(
                    job_id=job_id,
                    status=data.get("status", "unknown"),
                    total=data.get("total", 0),
                    completed=data.get("completed", 0),
                    credits_used=data.get("creditsUsed", 0),
                    expires_at=data.get("expiresAt"),
                    invalid_urls=data.get("invalidURLs", []),
                )
            else:
                logger.error(f"Status check failed: {resp.status_code}")
                return None

        except Exception as e:
            logger.error(f"Status check error: {e}")
            return None

    async def batch_scrape_v2_results(
        self,
        job_id: str,
    ) -> List[FirecrawlResult]:
        """
        Get results from a completed batch scrape job.

        Args:
            job_id: Job ID from batch_scrape_v2_start

        Returns:
            List of FirecrawlResult
        """
        await self._ensure_init()

        try:
            resp = await self._client.get(f"{self.base_url}/batch/scrape/{job_id}")

            if resp.status_code != 200:
                logger.error(f"Results fetch failed: {resp.status_code}")
                return []

            data = resp.json()
            results = []

            for page in data.get("data", []):
                page_url = page.get("metadata", {}).get("sourceURL") or page.get("url", "")
                results.append(FirecrawlResult(
                    url=page_url,
                    html=page.get("html", ""),
                    status_code=page.get("metadata", {}).get("statusCode", 200),
                    latency_ms=0,
                    content_length=len(page.get("html", "")),
                    markdown=page.get("markdown", ""),
                    metadata=page.get("metadata", {}),
                ))

            return results

        except Exception as e:
            logger.error(f"Results fetch error: {e}")
            return []

    # =========================================================================
    # AGENT - Deep research and autonomous data collection
    # =========================================================================

    async def agent(
        self,
        prompt: str,
        urls: Optional[List[str]] = None,
        schema: Optional[Dict[str, Any]] = None,
        max_credits: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        poll_interval: float = 2.0,
        max_poll_time: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Run a Firecrawl Agent job and wait for results.

        Agent is "deep research for data". It autonomously searches, navigates,
        and gathers data based on the prompt.

        Args:
            prompt: Description of data to gather (required)
            urls: Optional list of URLs to focus the agent
            schema: Optional JSON schema for structured output
            max_credits: Limit credits used by this job
            timeout_ms: Request timeout in milliseconds
            poll_interval: Seconds between status polls
            max_poll_time: Maximum seconds to wait for completion

        Returns:
            Dict containing success, status, data, and metadata
        """
        job_id = await self.agent_start(
            prompt=prompt,
            urls=urls,
            schema=schema,
            max_credits=max_credits,
            timeout_ms=timeout_ms
        )

        if not job_id:
            return {"success": False, "error": "Agent job start failed"}

        start_time = time.time()
        while (time.time() - start_time) < max_poll_time:
            await asyncio.sleep(poll_interval)
            status = await self.agent_status(job_id)
            
            if not status or not status.get("success"):
                return {"success": False, "error": "Status check failed", "job_id": job_id}
            
            state = status.get("status")
            if state == "completed":
                return status
            elif state == "failed":
                return {"success": False, "error": "Agent job failed", "job_id": job_id, "data": status}
            
            logger.debug(f"Agent job {job_id} status: {state}")

        return {"success": False, "error": "Agent job timed out", "job_id": job_id}

    async def agent_start(
        self,
        prompt: str,
        urls: Optional[List[str]] = None,
        schema: Optional[Dict[str, Any]] = None,
        max_credits: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Optional[str]:
        """Start an agent job and return ID."""
        await self._ensure_init()

        payload: Dict[str, Any] = {
            "prompt": prompt
        }
        if urls:
            payload["urls"] = urls
        if schema:
            payload["schema"] = schema
        if max_credits:
            payload["maxCredits"] = max_credits
        if timeout_ms:
            payload["timeout"] = timeout_ms

        try:
            resp = await self._client.post(
                f"{self.base_url}/agent",
                json=payload
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get("id")
            else:
                logger.error(f"Agent start failed: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Agent start error: {e}")
            return None

    async def agent_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get agent job status."""
        await self._ensure_init()
        try:
            resp = await self._client.get(f"{self.base_url}/agent/{job_id}")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"Agent status error: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


# Convenience functions
async def scrape_firecrawl(url: str, **kwargs) -> FirecrawlResult:
    """Quick single-URL scrape with Firecrawl."""
    async with Firecrawl(**kwargs) as scraper:
        return await scraper.scrape(url)


async def scrape_firecrawl_batch(urls: List[str], **kwargs) -> List[FirecrawlResult]:
    """Quick batch scrape with Firecrawl (simple per-URL calls)."""
    async with Firecrawl(**kwargs) as scraper:
        return await scraper.scrape_batch(urls)


async def batch_scrape_firecrawl_v2(
    urls: List[str],
    formats: Optional[List[str]] = None,
    actions: Optional[List[ScrapeAction]] = None,
    proxy: Optional[ProxyType] = None,
    max_concurrency: Optional[int] = None,
    progress_callback: Optional[Callable[[BatchScrapeStatus], None]] = None,
    **kwargs,
) -> List[FirecrawlResult]:
    """
    Quick batch scrape with Firecrawl v2 async job API.

    This is the recommended way to scrape many URLs with Firecrawl.
    Uses async job submission + polling for efficient batch processing.

    Args:
        urls: List of URLs to scrape
        formats: Output formats (default: ["html", "markdown"])
        actions: Pre-scrape actions (click, wait, scroll, etc.)
        proxy: Proxy type - ProxyType.BASIC, STEALTH, or AUTO
        max_concurrency: Max concurrent scrapes
        progress_callback: Optional callback for progress updates
        **kwargs: Additional options passed to batch_scrape_v2

    Returns:
        List of FirecrawlResult for each URL

    Example:
        from modules.jester.firecrawl import (
            batch_scrape_firecrawl_v2,
            ScrapeAction, ActionType, ProxyType
        )

        # Simple batch
        results = await batch_scrape_firecrawl_v2(
            ["https://example.com", "https://test.com"]
        )

        # With actions and stealth proxy
        results = await batch_scrape_firecrawl_v2(
            urls,
            actions=[ScrapeAction(type=ActionType.WAIT, milliseconds=2000)],
            proxy=ProxyType.STEALTH,
            max_concurrency=100,
        )
    """
    async with Firecrawl() as scraper:
        return await scraper.batch_scrape_v2(
            urls=urls,
            formats=formats,
            actions=actions,
            proxy=proxy,
            max_concurrency=max_concurrency,
            progress_callback=progress_callback,
            **kwargs,
        )


def firecrawl_available() -> bool:
    """Check if Firecrawl API key is configured."""
    return bool(os.getenv("FIRECRAWL_API_KEY"))


# CLI test
if __name__ == "__main__":
    import sys

    async def test_single():
        """Test single URL scrape."""
        print("Firecrawl - Single URL Scrape")
        print("=" * 50)

        url = "https://example.com"
        result = await scrape_firecrawl(url)

        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Content length: {result.content_length}")
        print(f"Markdown length: {len(result.markdown)}")
        print(f"Success: {result.success}")
        if result.error:
            print(f"Error: {result.error}")

    async def test_batch_v2():
        """Test batch scrape v2."""
        print("\nFirecrawl - Batch Scrape v2")
        print("=" * 50)

        urls = [
            "https://example.com",
            "https://httpbin.org/html",
        ]

        def progress(status: BatchScrapeStatus):
            print(f"  Progress: {status.completed}/{status.total} ({status.status})")

        results = await batch_scrape_firecrawl_v2(
            urls=urls,
            formats=["html", "markdown"],
            max_concurrency=10,
            progress_callback=progress,
        )

        print(f"\nResults ({len(results)} URLs):")
        for r in results:
            status = "✓" if r.success else "✗"
            print(f"  {status} {r.url}: {r.content_length} bytes")
            if r.error:
                print(f"      Error: {r.error}")

    async def test_batch_with_actions():
        """Test batch scrape with pre-scrape actions."""
        print("\nFirecrawl - Batch with Actions")
        print("=" * 50)

        urls = ["https://example.com"]

        results = await batch_scrape_firecrawl_v2(
            urls=urls,
            actions=[
                ScrapeAction(type=ActionType.WAIT, milliseconds=1000),
            ],
            proxy=ProxyType.AUTO,
        )

        for r in results:
            print(f"URL: {r.url}")
            print(f"Success: {r.success}")
            print(f"Content: {r.content_length} bytes")

    async def main():
        if not firecrawl_available():
            print("ERROR: FIRECRAWL_API_KEY not set")
            return

        mode = sys.argv[1] if len(sys.argv) > 1 else "single"

        if mode == "single":
            await test_single()
        elif mode == "batch":
            await test_batch_v2()
        elif mode == "actions":
            await test_batch_with_actions()
        elif mode == "all":
            await test_single()
            await test_batch_v2()
        else:
            print(f"Usage: python firecrawl.py [single|batch|actions|all]")

    asyncio.run(main())
