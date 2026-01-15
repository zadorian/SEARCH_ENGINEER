"""
Google News Search via Bright Data API.

Shared engine for both Brute and Torpedo modules.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Configuration
API_ENDPOINT = "https://api.brightdata.com/datasets/v3/scrape?dataset_id=gd_lnsxoxzi1omrwnka5r&notify=false&include_errors=true"
TRIGGER_ENDPOINT = "https://api.brightdata.com/datasets/v3/trigger?dataset_id=gd_lnsxoxzi1omrwnka5r&notify=false&include_errors=true"
SNAPSHOT_ENDPOINT = "https://api.brightdata.com/datasets/v3/snapshot"
API_TOKEN = "4a23084cbf6adea6cd86487f4fbae5023ee6a3038548ec8a7f1d1d957f4b9139"

async def fetch_google_news(
    inputs: List[Dict[str, str]],
    timeout: int = 60,
    async_mode: bool = False
) -> List[Dict[str, Any]]:
    """
    Fetch Google News results using Bright Data API.

    Args:
        inputs: List of dicts, each containing:
            - keyword: Search query
            - country: ISO 2-letter country code (e.g. 'US', 'GB')
            - language: (Optional) Language code (e.g. 'en')
            - url: (Optional) Base URL, defaults to https://news.google.com/
        timeout: Request timeout in seconds.
        async_mode: If True, use asynchronous batch trigger and polling.

    Returns:
        List of results normalized to standard format.
    """
    if not inputs:
        return []

    # Prepare payload
    payload_inputs = []
    for item in inputs:
        payload_inputs.append({
            "url": item.get("url", "https://news.google.com/"),
            "keyword": item.get("keyword", ""),
            "country": item.get("country", "US"),
            "language": item.get("language", "")
        })

    payload = {"input": payload_inputs}
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            if async_mode:
                # 1. Trigger the job
                logger.info(f"Triggering async Google News job for {len(payload_inputs)} inputs")
                response = await client.post(
                    TRIGGER_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"Bright Data Trigger error: {response.status_code} - {response.text}")
                    return []
                
                trigger_data = response.json()
                snapshot_id = trigger_data.get("snapshot_id")
                
                if not snapshot_id:
                    logger.error("No snapshot_id returned from Bright Data trigger")
                    return []
                
                logger.info(f"Job triggered, snapshot_id: {snapshot_id}. Polling...")
                
                # 2. Poll for results
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < timeout:
                    await asyncio.sleep(5) # Wait between polls
                    
                    poll_url = f"{SNAPSHOT_ENDPOINT}/{snapshot_id}?format=json"
                    poll_response = await client.get(poll_url, headers=headers, timeout=30)
                    
                    if poll_response.status_code == 200:
                        # Success - data is ready
                        # Bright Data returns the JSON data directly when ready?
                        # Or checking status first? 
                        # Usually the snapshot endpoint returns 202 Accepted if processing, 200 OK with data if done.
                        # Let's handle parsing if 200.
                        try:
                            data = poll_response.json()
                            if data and isinstance(data, (list, dict)):
                                # Ensure it's not a status object saying "running"
                                if isinstance(data, dict) and data.get("status") in ["running", "collecting"]:
                                    continue
                                break # We have data
                        except json.JSONDecodeError:
                            # Might be NDJSON or not ready?
                            text = poll_response.text
                            if text.strip():
                                lines = text.strip().split('\n')
                                data = [json.loads(line) for line in lines if line.strip()]
                                break
                    elif poll_response.status_code == 202:
                        continue # Still processing
                    else:
                        logger.warning(f"Polling status {poll_response.status_code}: {poll_response.text}")
                        # Don't break immediately, might be transient?
                else:
                    logger.error(f"Timed out polling snapshot {snapshot_id}")
                    return []

            else:
                # Synchronous mode
                logger.info(f"Sending Google News request to Bright Data for {len(payload_inputs)} inputs")
                response = await client.post(
                    API_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                
                if response.status_code != 200:
                    logger.error(f"Bright Data API error: {response.status_code} - {response.text}")
                    return []

                try:
                    data = response.json()
                except json.JSONDecodeError:
                    # Try NDJSON
                    lines = response.text.strip().split('\n')
                    data = [json.loads(line) for line in lines if line.strip()]

            # Normalize results (common logic)
            normalized_results = []
            
            # Handle if data is wrapped
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                title = item.get("title") or item.get("headline")
                url = item.get("url") or item.get("link") or item.get("article_url")
                
                if not title or not url:
                    continue
                    
                normalized_results.append({
                    "title": title,
                    "url": url,
                    "snippet": item.get("description") or item.get("snippet") or "",
                    "date": item.get("date") or item.get("published_date") or item.get("time") or "",
                    "source": item.get("source") or "Google News",
                    "domain": "news.google.com",
                    "engine": "google_news_brightdata",
                    "language": item.get("language"),
                    "country": item.get("country_code") 
                })
                
            logger.info(f"Bright Data returned {len(normalized_results)} articles")
            return normalized_results

    except Exception as e:
        logger.error(f"Error calling Bright Data API: {e}")
        return []
