"""
JESTER MAPPER - Subdomain Discovery (Optimized)
================================================

Discover subdomains using multiple sources:
    - crt.sh (Certificate Transparency) - FREE
    - WhoisXML API - PAID ($)
    - Sublist3r (multi-source) - FREE
    - DNSDumpster - FREE

Optimizations:
    - Accepts shared HTTP client for connection reuse
    - httpx with HTTP/2 support when available

Usage:
    discovery = SubdomainDiscovery()
    async for url in discovery.discover_all("example.com"):
        print(url.url, url.source)
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import AsyncGenerator, Set, Optional, Any

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    import aiohttp
    HTTPX_AVAILABLE = False

from ..models import DiscoveredURL
from ..config import WHOISXML_API_KEY, TIMEOUTS

logger = logging.getLogger(__name__)


class SubdomainDiscovery:
    """
    Multi-source subdomain discovery (optimized).

    Sources:
        1. crt.sh - Certificate Transparency logs (FREE)
        2. WhoisXML API - WHOIS/DNS database (PAID)
        3. Sublist3r - Multi-source subdomain enumeration (FREE)
        4. DNSDumpster - DNS recon (FREE, requires scraping)
    """

    def __init__(self):
        self.whoisxml_key = WHOISXML_API_KEY

    async def _get_client(self, client: Optional[Any] = None):
        """Get a client - use provided or create temporary one."""
        if client is not None:
            return client, False
        if HTTPX_AVAILABLE:
            return httpx.AsyncClient(http2=True, timeout=httpx.Timeout(60.0)), True
        else:
            return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)), True

    async def _close_client(self, client: Any, should_close: bool):
        """Close client if we created it."""
        if should_close and client is not None:
            if HTTPX_AVAILABLE:
                await client.aclose()
            else:
                await client.close()

    async def discover_all(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Run all subdomain discovery sources in parallel.

        Args:
            domain: Base domain
            client: Optional shared HTTP client

        Yields:
            DiscoveredURL objects for each subdomain found
        """
        seen: Set[str] = set()

        generators = [
            ("crt.sh", self.discover_crtsh(domain, client=client)),
            ("whoisxml", self.discover_whoisxml(domain, client=client)),
            ("sublist3r", self.discover_sublist3r(domain)),
        ]

        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def consume(name: str, gen):
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                logger.error(f"Subdomain source '{name}' failed: {exc}")
            finally:
                await queue.put(sentinel)

        tasks = [asyncio.create_task(consume(name, gen)) for name, gen in generators]

        completed = 0
        try:
            while completed < len(tasks):
                item = await queue.get()
                if item is sentinel:
                    completed += 1
                    continue
                if item is not None and item.url not in seen:
                    seen.add(item.url)
                    yield item
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task

        logger.info(f"Subdomain discovery complete: {len(seen)} unique subdomains")

    async def discover_crtsh(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query crt.sh Certificate Transparency logs.

        FREE - No API key required.
        """
        logger.info(f"[crt.sh] Searching for subdomains of: {domain}")

        http_client, should_close = await self._get_client(client)
        url = "https://crt.sh/"
        params = {"q": f"%.{domain}", "output": "json"}

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.get(url, params=params)
                status = response.status_code
                if status == 200:
                    try:
                        data = response.json()
                    except json.JSONDecodeError:
                        logger.warning("[crt.sh] No results (non-JSON response)")
                        return
                else:
                    logger.error(f"[crt.sh] HTTP {status}")
                    return
            else:
                async with http_client.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("crt.sh", 60))
                ) as response:
                    status = response.status
                    if status == 200:
                        try:
                            data = await response.json()
                        except json.JSONDecodeError:
                            logger.warning("[crt.sh] No results (non-JSON response)")
                            return
                    else:
                        logger.error(f"[crt.sh] HTTP {status}")
                        return

            subdomains: Set[str] = set()

            for entry in data:
                name_value = entry.get("name_value", "")

                for subdomain in name_value.split("\n"):
                    subdomain = subdomain.strip().lower()

                    if "*" in subdomain:
                        continue

                    if not (subdomain == domain or subdomain.endswith(f".{domain}")):
                        continue

                    if subdomain not in subdomains:
                        subdomains.add(subdomain)
                        yield DiscoveredURL(
                            url=f"https://{subdomain}",
                            source="crt.sh",
                            domain=domain,
                            subdomain=subdomain.replace(f".{domain}", "") if subdomain != domain else None,
                        )

            logger.info(f"[crt.sh] Found {len(subdomains)} subdomains")

        except asyncio.TimeoutError:
            logger.error("[crt.sh] Timeout")
        except Exception as e:
            logger.error(f"[crt.sh] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)

    async def discover_whoisxml(
        self,
        domain: str,
        client: Optional[Any] = None,
    ) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query WhoisXML Subdomain Lookup API.

        PAID - Requires WHOISXML_API_KEY.
        """
        if not self.whoisxml_key:
            logger.debug("[whoisxml] Skipping - no API key")
            return

        logger.info(f"[whoisxml] Searching for subdomains of: {domain}")

        http_client, should_close = await self._get_client(client)
        url = "https://subdomains.whoisxmlapi.com/api/v1"
        params = {"apiKey": self.whoisxml_key, "domainName": domain}

        try:
            if HTTPX_AVAILABLE:
                response = await http_client.get(url, params=params)
                status = response.status_code
                data = response.json() if status == 200 else None
            else:
                async with http_client.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUTS.get("default", 30))
                ) as response:
                    status = response.status
                    data = await response.json() if status == 200 else None

            if status == 403:
                logger.error("[whoisxml] API key invalid or quota exceeded")
                return
            if status != 200 or data is None:
                logger.error(f"[whoisxml] HTTP {status}")
                return

            records = data.get("result", {}).get("records", [])
            count = 0

            for record in records:
                subdomain = record.get("domain", "").lower()
                if not subdomain:
                    continue

                if not (subdomain == domain or subdomain.endswith(f".{domain}")):
                    continue

                count += 1
                yield DiscoveredURL(
                    url=f"https://{subdomain}",
                    source="whoisxml",
                    domain=domain,
                    subdomain=subdomain.replace(f".{domain}", "") if subdomain != domain else None,
                )

            logger.info(f"[whoisxml] Found {count} subdomains")

        except asyncio.TimeoutError:
            logger.error("[whoisxml] Timeout")
        except Exception as e:
            logger.error(f"[whoisxml] Error: {e}")
        finally:
            await self._close_client(http_client, should_close)

    async def discover_sublist3r(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Run Sublist3r multi-source subdomain enumeration.

        FREE - Requires sublist3r package installed.
        """
        logger.info(f"[sublist3r] Searching for subdomains of: {domain}")

        try:
            try:
                import sublist3r
            except ImportError:
                logger.debug("[sublist3r] Not installed - skipping")
                return

            loop = asyncio.get_event_loop()

            def run_sublist3r():
                return sublist3r.main(
                    domain,
                    40,
                    savefile=None,
                    ports=None,
                    silent=True,
                    verbose=False,
                    enable_bruteforce=False,
                    engines=None,
                )

            subdomains = await asyncio.wait_for(
                loop.run_in_executor(None, run_sublist3r),
                timeout=TIMEOUTS.get("sublist3r", 120),
            )

            if not subdomains:
                logger.info("[sublist3r] No subdomains found")
                return

            count = 0
            for subdomain in subdomains:
                subdomain = subdomain.lower()

                if not (subdomain == domain or subdomain.endswith(f".{domain}")):
                    continue

                count += 1
                yield DiscoveredURL(
                    url=f"https://{subdomain}",
                    source="sublist3r",
                    domain=domain,
                    subdomain=subdomain.replace(f".{domain}", "") if subdomain != domain else None,
                )

            logger.info(f"[sublist3r] Found {count} subdomains")

        except asyncio.TimeoutError:
            logger.error("[sublist3r] Timeout")
        except Exception as e:
            logger.error(f"[sublist3r] Error: {e}")

    async def discover_dnsdumpster(self, domain: str) -> AsyncGenerator[DiscoveredURL, None]:
        """
        Query DNSDumpster.com for subdomains.

        FREE - Requires web scraping with CSRF token handling.
        Currently a stub.
        """
        logger.debug(f"[dnsdumpster] Not yet implemented for: {domain}")
        return
        yield  # Make this a generator
