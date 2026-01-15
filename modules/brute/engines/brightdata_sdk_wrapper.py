"""
Bright Data SDK Wrapper.

Provides an interface to the official `brightdata-sdk` if installed.
Useful for accessing Datasets and Scraping Browser features using the official patterns.

Installation:
    pip install brightdata-sdk playwright

Usage:
    from brute.engines.brightdata_sdk_wrapper import get_client, list_datasets
"""

import logging
import os
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Global client cache
_BD_CLIENT = None
SDK_AVAILABLE = False

try:
    from brightdata import BrightDataClient
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

def get_client(api_token: Optional[str] = None) -> Optional[Any]:
    """
    Get or initialize the Bright Data client.
    """
    global _BD_CLIENT
    if not SDK_AVAILABLE:
        logger.warning("brightdata-sdk not installed. Skipping SDK initialization.")
        return None

    if _BD_CLIENT:
        return _BD_CLIENT

    token = api_token or os.getenv("BRIGHTDATA_API_TOKEN")
    if not token:
        # Try fallback to the hardcoded token from serp_brightdata if available
        # (This is a convenience for this specific project context)
        token = "4a23084cbf6adea6cd86487f4fbae5023ee6a3038548ec8a7f1d1d957f4b9139"

    try:
        _BD_CLIENT = BrightDataClient(token=token)
        return _BD_CLIENT
    except Exception as e:
        logger.error(f"Failed to initialize BrightDataClient: {e}")
        return None

def list_datasets() -> List[str]:
    """
    List available datasets using the SDK.
    """
    client = get_client()
    if not client:
        return []

    try:
        response = client.datasets.list()
        if response.success:
            return response.data
        else:
            logger.error(f"Failed to list datasets: {response.error_message}")
            return []
    except Exception as e:
        logger.error(f"Error listing datasets: {e}")
        return []

def get_dataset_metadata(dataset_id: str) -> Dict[str, Any]:
    """
    Get metadata for a specific dataset.
    """
    client = get_client()
    if not client:
        return {}

    try:
        response = client.datasets.metadata(dataset_id=dataset_id)
        if response.success:
            return response.data
        return {}
    except Exception as e:
        logger.error(f"Error fetching metadata for {dataset_id}: {e}")
        return {}

def get_browser_cdp_url(zone_name: str = "scraping_browser") -> Optional[str]:
    """
    Get the CDP URL for connecting to the Scraping Browser.
    """
    client = get_client()
    if not client:
        return None
    
    # Note: SDK might need specific zone credentials passed or configured
    # client.connect_browser() usually returns the WS URL
    try:
        # We need zone credentials. If not in env, we might fail.
        # This is a wrapper, so we assume env vars are set or we return None.
        return client.connect_browser()
    except Exception as e:
        logger.warning(f"Could not get browser URL via SDK: {e}")
        return None
