import sys
import os
import logging
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Add the directory containing domain_search/age to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..' , 'domain_search', 'age'))

# Import age estimation modules with error handling
try:
    from whoisxmlapi_AgeEstimater import get_whois_data
    WHOIS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WHOIS module not available: {e}")
    WHOIS_AVAILABLE = False

try:
    from wayback_AgeEstimater import get_earliest_snapshot
    WAYBACK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Wayback module not available: {e}")
    WAYBACK_AVAILABLE = False

def normalize_input(input_string):
    """Clean and normalize input, determining if it's a URL or domain."""
    input_string = input_string.lower().strip()
    if input_string.startswith(('http://', 'https://')):
        parsed = urlparse(input_string)
        return parsed.netloc if parsed.netloc else parsed.path, True # Return domain and is_url flag
    else:
        # Assume it's a domain if no scheme
        return input_string.replace('www.', ''), False # Return domain and is_url flag

async def get_age_info(query_target):
    """Determines the age of a domain or URL based on the query target.

    Args:
        query_target (str): The domain or URL to analyze.

    Returns:
        dict: A dictionary containing age information.
    """
    normalized_target, is_url = normalize_input(query_target)
    results = {}
    
    # Check if any modules are available
    if not WHOIS_AVAILABLE and not WAYBACK_AVAILABLE:
        results["error"] = "No age estimation modules available. Please check WHOISXML_API_KEY and dependencies."
        return results

    if is_url:
        # For URLs, prioritize Wayback Machine snapshot date
        if WAYBACK_AVAILABLE:
            try:
                earliest_snapshot, error = get_earliest_snapshot(query_target) # Use original query_target for wayback
                if earliest_snapshot:
                    results["url_earliest_snapshot"] = earliest_snapshot
                if error:
                    results["url_snapshot_error"] = error
            except Exception as e:
                logger.error(f"Wayback Machine error: {e}")
                results["url_snapshot_error"] = f"Wayback Machine error: {str(e)}"

        # Also get WHOIS data for the domain part of the URL
        if WHOIS_AVAILABLE:
            try:
                whois_info = get_whois_data(normalized_target)
                if whois_info:
                    results["domain_whois_info"] = whois_info
            except Exception as e:
                logger.error(f"WHOIS error: {e}")
                results["domain_whois_error"] = f"WHOIS error: {str(e)}"

    else:
        # For domains, only get WHOIS data
        if WHOIS_AVAILABLE:
            try:
                whois_info = get_whois_data(normalized_target)
                if whois_info:
                    results["domain_whois_info"] = whois_info
            except Exception as e:
                logger.error(f"WHOIS error: {e}")
                results["domain_whois_error"] = f"WHOIS error: {str(e)}"
        else:
            results["domain_whois_error"] = "WHOIS module not available"

    return results

# Example usage (for testing within the module)
async def main():
    test_domain = "example.com"
    test_url = "https://www.google.com/search?q=test"

    print(f"\n--- Analyzing Domain: {test_domain} ---")
    domain_age = await get_age_info(test_domain)
    print(domain_age)

    print(f"\n--- Analyzing URL: {test_url} ---")
    url_age = await get_age_info(test_url)
    print(url_age)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())