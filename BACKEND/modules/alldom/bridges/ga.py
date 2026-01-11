"""
ALLDOM Bridge: Google Analytics Discovery

Extract Google Analytics/GTM tracking codes from domains.
Operator: ga!:domain
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# GA/GTM code patterns
GA_PATTERNS = [
    re.compile(r"UA-\d+-\d+"),  # Universal Analytics
    re.compile(r"G-[A-Z0-9]+"),  # GA4
    re.compile(r"GTM-[A-Z0-9]+"),  # Google Tag Manager
    re.compile(r"AW-\d+"),  # Google Ads
]


async def discover_codes(domain: str, max_pages: int = 10, **kwargs) -> List[Dict[str, Any]]:
    """
    Discover Google Analytics/GTM codes from domain (ga!:domain).
    
    Scrapes multiple pages from domain and extracts tracking codes.
    Returns list of domains/URLs that share the same GA/GTM codes.
    
    Args:
        domain: Target domain to analyze
        max_pages: Maximum pages to scrape (default: 10)
        **kwargs: Additional scraping parameters
    
    Returns:
        List of dicts with domain, code, code_type, pages_found_on
    """
    try:
        from modules.JESTER import Jester
        from modules.JESTER.MAPPER.mapper import JesterMapper
        
        # Step 1: Discover URLs on domain
        mapper = JesterMapper()
        urls = []
        async for discovered in mapper.discover_stream(domain, mode="fast"):
            urls.append(discovered.url)
            if len(urls) >= max_pages:
                break
        
        if not urls:
            urls = [f"https://{domain}"]
        
        # Step 2: Scrape pages to extract codes
        jester = Jester()
        codes_found = {}  # code -> {type, pages}
        
        for url in urls[:max_pages]:
            result = await jester.scrape(url)
            if not result or not result.content:
                continue
            
            content = result.content
            
            # Extract all tracking codes
            for pattern in GA_PATTERNS:
                matches = pattern.findall(content)
                for code in matches:
                    # Determine code type
                    if code.startswith("UA-"):
                        code_type = "universal_analytics"
                    elif code.startswith("G-"):
                        code_type = "ga4"
                    elif code.startswith("GTM-"):
                        code_type = "google_tag_manager"
                    elif code.startswith("AW-"):
                        code_type = "google_ads"
                    else:
                        code_type = "unknown"
                    
                    if code not in codes_found:
                        codes_found[code] = {
                            "type": code_type,
                            "pages": []
                        }
                    codes_found[code]["pages"].append(url)
        
        await jester.close()
        
        # Step 3: For each code found, search for other domains using it
        # (This would require additional API calls to GA reverse lookup services)
        
        results = []
        for code, data in codes_found.items():
            results.append({
                "code": code,
                "code_type": data["type"],
                "pages_on_target": data["pages"],
                "source": "ga_analysis",
                "metadata": {
                    "target_domain": domain,
                    "pages_scanned": len(urls)
                }
            })
        
        return results
        
    except ImportError as e:
        logger.warning(f"GA analysis dependencies not available: {e}")
        return []
    except Exception as e:
        logger.error(f"GA analysis error: {e}")
        return []


async def find_shared_ga_codes(domain: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Find domains that share GA/GTM codes with target domain.
    Returns list of related domains.
    """
    codes_data = await discover_codes(domain, **kwargs)
    
    # TODO: Query reverse GA lookup service for each code
    # to find other domains using the same codes
    
    # For now, return discovered codes
    return codes_data
