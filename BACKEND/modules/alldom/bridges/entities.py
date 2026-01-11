"""
ALLDOM Bridge: Entity Extraction

Thin wrapper for entity extraction operations (@ent?, @p?, @c?, etc).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def extract_all(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract all entity types from domain/URL (@ent?).
    """
    try:
        from modules.alldom.utils.entity_extraction import extract_entities
        from modules.alldom.libs.cymonides import get_scraper

        # First scrape the target
        scraper = get_scraper()
        if not scraper:
            return []

        # Determine if URL or domain
        if domain_or_url.startswith(("http://", "https://")):
            # Single URL
            result = await scraper.scrape_url(domain_or_url)
            if not result.get("success"):
                return []
            entities = extract_entities(result, fallback_url=domain_or_url)
        else:
            # Domain - scrape homepage
            url = f"https://{domain_or_url}"
            result = await scraper.scrape_url(url)
            if not result.get("success"):
                return []
            entities = extract_entities(result, fallback_url=url)

        return entities
    except ImportError:
        logger.warning("Entity extraction not available")
        return []
    except Exception as e:
        logger.error(f"Entity extraction error: {e}")
        return []


async def extract_persons(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract person entities only (@p?).
    """
    all_entities = await extract_all(domain_or_url, **kwargs)
    return [e for e in all_entities if e.get("type") == "person"]


async def extract_companies(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract organization entities only (@c?).
    """
    all_entities = await extract_all(domain_or_url, **kwargs)
    return [e for e in all_entities if e.get("type") in ("organization", "company")]


async def extract_emails(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract email entities only (@e?).
    """
    all_entities = await extract_all(domain_or_url, **kwargs)
    return [e for e in all_entities if e.get("type") == "email"]


async def extract_phones(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract phone entities only (@t?).
    """
    all_entities = await extract_all(domain_or_url, **kwargs)
    return [e for e in all_entities if e.get("type") == "phone"]


async def extract_addresses(domain_or_url: str, **kwargs) -> List[Dict[str, Any]]:
    """
    Extract address entities only (@a?).
    """
    all_entities = await extract_all(domain_or_url, **kwargs)
    return [e for e in all_entities if e.get("type") == "address"]


async def extract_from_content(content: str, content_type: str = "html", **kwargs) -> List[Dict[str, Any]]:
    """
    Extract entities from raw content (no scraping needed).
    """
    try:
        from modules.alldom.utils.entity_extraction import extract_entities

        payload = {
            "content": content,
            "html": content if content_type == "html" else None,
            "markdown": content if content_type == "markdown" else None,
        }

        return extract_entities(payload)
    except Exception as e:
        logger.error(f"Content entity extraction error: {e}")
        return []


async def extract_domain_wide(
    domain: str,
    max_pages: int = 50,
    entity_types: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract entities from multiple pages across a domain.

    Returns dict mapping URL to list of entities.
    """
    try:
        from modules.alldom.sources.firecrawl_mapper import FirecrawlMapper
        from modules.alldom.libs.cymonides import get_scraper
        from modules.alldom.utils.entity_extraction import extract_entities

        # First discover URLs
        fm = FirecrawlMapper()
        urls = []
        async for discovered in fm.map_domain(domain):
            urls.append(discovered.url)
            if len(urls) >= max_pages:
                break

        if not urls:
            urls = [f"https://{domain}"]

        # Scrape and extract
        scraper = get_scraper()
        if not scraper:
            return {}

        result = await scraper.scrape_multiple_urls(urls[:max_pages], max_concurrent=10)

        entities_by_url = {}
        for page in result.get("scraped_pages", []):
            url = page.get("url")
            if not url or not page.get("success", True):
                continue

            entities = extract_entities(page, fallback_url=url)

            # Filter by type if requested
            if entity_types:
                entities = [e for e in entities if e.get("type") in entity_types]

            if entities:
                entities_by_url[url] = entities

        return entities_by_url
    except Exception as e:
        logger.error(f"Domain-wide entity extraction error: {e}")
        return {}
