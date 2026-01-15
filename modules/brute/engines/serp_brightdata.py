"""
SERP API Search via Bright Data.

Standard web search (Google, Bing, etc.) using Bright Data's SERP API.
Uses the /request endpoint with zone serp_api2.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
import httpx

logger = logging.getLogger(__name__)

# Configuration - UPDATED to use correct endpoint and zone
API_ENDPOINT = "https://api.brightdata.com/request"
API_TOKEN = "4a23084cbf6adea6cd86487f4fbae5023ee6a3038548ec8a7f1d1d957f4b9139"
ZONE = "serp_api2"


async def fetch_serp_results(
    query: str,
    country: Optional[str] = None,
    lang: Optional[str] = None,
    engine: str = "google",
    num: int = 10,
    start: int = 0,
    timeout: int = 60,
    async_mode: bool = False,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Fetch SERP results using Bright Data API.

    Args:
        query: Search query
        country: ISO 2-letter country code
        lang: Language code
        engine: Search engine ('google', 'bing', 'yandex', etc.)
        num: Number of results
        start: Offset
        timeout: Request timeout in seconds.
        async_mode: If True, use asynchronous request and polling.

    Returns:
        List of results normalized to standard format.
    """

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    # URL-encode the query
    encoded_query = quote_plus(query)

    # Build search URL based on engine
    if engine.lower() == "google":
        search_url = f"https://www.google.com/search?q={encoded_query}&num={num}"
        if start > 0:
            search_url += f"&start={start}"
        if country:
            search_url += f"&gl={country}"
        if lang:
            search_url += f"&hl={lang}"
    elif engine.lower() == "bing":
        search_url = f"https://www.bing.com/search?q={encoded_query}&count={num}"
        if start > 0:
            search_url += f"&first={start}"
        if country:
            search_url += f"&cc={country}"
    elif engine.lower() == "yandex":
        search_url = f"https://yandex.com/search/?text={encoded_query}"
        if num:
            search_url += f"&numdoc={num}"
    elif engine.lower() == "duckduckgo":
        search_url = f"https://duckduckgo.com/?q={encoded_query}"
    else:
        search_url = f"https://www.google.com/search?q={encoded_query}&num={num}"

    # Build payload for /request endpoint
    payload = {
        "zone": ZONE,
        "url": search_url,
        "format": "json",
    }

    if country:
        payload["country"] = country

    logger.info(f"Sending SERP ({engine}) request to Bright Data for query: {query}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=timeout
            )

            if response.status_code != 200:
                logger.error(f"Bright Data SERP error: {response.status_code} - {response.text[:200]}")
                return []

            data = response.json()

            # Parse the response - body contains the actual SERP data as JSON string
            body = data.get("body", "{}")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    logger.warning("Could not parse body as JSON")
                    return []

            # Extract organic results
            results = []
            organic = body.get("organic", [])

            for item in organic:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", "") or item.get("url", ""),
                    "snippet": item.get("description", "") or item.get("snippet", ""),
                    "position": item.get("rank") or item.get("position"),
                    "engine": engine,
                    "source": f"brightdata_{engine}",
                })

            logger.info(f"Bright Data SERP ({engine}): {len(results)} organic results")
            return results

    except httpx.TimeoutException:
        logger.error(f"Bright Data SERP timeout for {engine}")
        return []
    except Exception as e:
        logger.error(f"Bright Data SERP error: {e}")
        return []


class SerpBrightData:
    """Wrapper class for engine compatibility."""

    name = "BrightData SERP"
    code = "SB"

    def __init__(self, engine: str = "google"):
        self.engine = engine

    def search(self, query: str, max_results: int = 100) -> List[Dict]:
        """Synchronous search wrapper."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    fetch_serp_results(query, engine=self.engine, num=max_results)
                )
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"SerpBrightData search error: {e}")
            return []


# Test function
async def main():
    print("Testing BrightData SERP API...")
    results = await fetch_serp_results('"Backward Spyglass"', engine="google", num=10)
    print(f"Got {len(results)} results:")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.get('title', '')[:50]}")
        print(f"     {r.get('url', '')[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
