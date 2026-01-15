#!/usr/bin/env python3
"""
Apify Web Scraper Engine

General-purpose web scraper using Apify's Web Scraper Actor.
Actor: apify/web-scraper

Use cases:
- Crawling specific websites with custom extraction
- Following links to build crawl graphs
- Extracting structured data with page functions
- JESTER fallback for JS-heavy sites

This is NOT a search engine - it's a scraper for crawling known URLs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False
    logger.warning("apify_client not installed")

APIFY_TOKEN = os.getenv('APIFY_API_TOKEN') or os.getenv('APIFY_TOKEN')
APIFY_PROXY_PASSWORD = os.getenv('APIFY_PROXY_PASSWORD')  # Found at console.apify.com/proxy
WEB_SCRAPER_ACTOR = "apify/web-scraper"

# Proxy configuration options
PROXY_CONFIG = {
    'datacenter': {'useApifyProxy': True},  # Default datacenter (cheap, fast)
    'residential': {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL']},  # More anonymous
    'residential_us': {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL'], 'apifyProxyCountry': 'US'},
    'residential_uk': {'useApifyProxy': True, 'apifyProxyGroups': ['RESIDENTIAL'], 'apifyProxyCountry': 'GB'},
    'none': None,  # No proxy
}


# Default page function for content extraction
DEFAULT_PAGE_FUNCTION = """
async function pageFunction(context) {
    const $ = context.jQuery;
    
    // Extract all text content
    const title = $('title').first().text().trim();
    const h1 = $('h1').first().text().trim();
    const meta_desc = $('meta[name="description"]').attr('content') || '';
    
    // Extract all paragraph text
    const paragraphs = [];
    $('p').each((i, el) => {
        const text = $(el).text().trim();
        if (text.length > 20) paragraphs.push(text);
    });
    
    // Extract all links
    const links = [];
    $('a[href]').each((i, el) => {
        const href = $(el).attr('href');
        const text = $(el).text().trim();
        if (href && href.startsWith('http')) {
            links.push({ url: href, text: text.substring(0, 100) });
        }
    });
    
    // Extract emails and phones
    const bodyText = $('body').text();
    const emails = bodyText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g) || [];
    const phones = bodyText.match(/[+]?[0-9][0-9\\s.-]{7,}[0-9]/g) || [];
    
    return {
        url: context.request.url,
        title,
        h1,
        meta_desc,
        text: paragraphs.slice(0, 50).join('\\n\\n'),
        links: links.slice(0, 100),
        emails: [...new Set(emails)].slice(0, 20),
        phones: [...new Set(phones)].slice(0, 20),
        scraped_at: new Date().toISOString()
    };
}
"""


class ApifyWebScraper:
    """
    Apify Web Scraper client for crawling websites.
    
    This is a SCRAPER, not a search engine. Use for:
    - Crawling known URLs
    - Extracting content from JS-heavy sites
    - JESTER fallback when other methods fail
    """

    def __init__(self, api_token: str = None):
        self.api_token = api_token or APIFY_TOKEN
        self.client = ApifyClient(self.api_token) if APIFY_AVAILABLE and self.api_token else None

    def scrape_url(
        self,
        url: str,
        max_pages: int = 1,
        max_depth: int = 0,
        page_function: str = None,
        link_selector: str = "a[href]",
        globs: List[str] = None,
        excludes: List[str] = None,
        wait_until: str = "networkidle2",
        timeout_secs: int = 120,
        use_proxy: bool = True,
        proxy_type: str = "datacenter",  # datacenter, residential, residential_us, residential_uk, none
    ) -> List[Dict[str, Any]]:
        """
        Scrape a URL using Apify Web Scraper.

        Args:
            url: Starting URL to scrape
            max_pages: Maximum pages to crawl (1 = single page)
            max_depth: How deep to follow links (0 = only starting URL)
            page_function: Custom JS extraction function
            link_selector: CSS selector for finding links
            globs: URL patterns to follow (glob format)
            excludes: URL patterns to exclude
            wait_until: Page load event to wait for
            timeout_secs: Actor timeout
            use_proxy: Use Apify proxy

        Returns:
            List of scraped page results
        """
        if not self.client:
            logger.error("Apify client not available")
            return []

        try:
            # Build run input
            run_input = {
                "runMode": "PRODUCTION",
                "startUrls": [{"url": url}],
                "respectRobotsTxtFile": False,
                "maxRequestsPerCrawl": max_pages,
                "maxCrawlingDepth": max_depth,
                "linkSelector": link_selector,
                "pageFunction": page_function or DEFAULT_PAGE_FUNCTION,
                "waitUntil": [wait_until],
                "injectJQuery": True,
            }

            # URL filtering
            if globs:
                run_input["globs"] = [{"glob": g} for g in globs]
            
            if excludes:
                run_input["excludes"] = [{"glob": e} for e in excludes]
            else:
                # Default exclusions for non-content files
                run_input["excludes"] = [
                    {"glob": "/**/*.{png,jpg,jpeg,gif,svg,pdf,zip,mp4,mp3}"}
                ]

            # Proxy configuration (datacenter, residential, or country-specific)
            if use_proxy and proxy_type in PROXY_CONFIG and PROXY_CONFIG[proxy_type]:
                run_input["proxyConfiguration"] = PROXY_CONFIG[proxy_type]
            elif use_proxy:
                run_input["proxyConfiguration"] = {"useApifyProxy": True}

            logger.info(f"Apify Scraper: Crawling {url} (max {max_pages} pages, depth {max_depth})")

            # Run the Actor
            run = self.client.actor(WEB_SCRAPER_ACTOR).call(
                run_input=run_input,
                timeout_secs=timeout_secs
            )

            # Collect results
            results = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                results.append({
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "h1": item.get("h1", ""),
                    "meta_desc": item.get("meta_desc", ""),
                    "text": item.get("text", ""),
                    "links": item.get("links", []),
                    "emails": item.get("emails", []),
                    "phones": item.get("phones", []),
                    "scraped_at": item.get("scraped_at", ""),
                    "source": "apify_scraper",
                })

            logger.info(f"Apify Scraper: Got {len(results)} pages from {url}")
            return results

        except Exception as e:
            logger.error(f"Apify Scraper error: {e}")
            return []

    def scrape_batch(
        self,
        urls: List[str],
        max_pages_per_url: int = 1,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Scrape multiple URLs."""
        all_results = []
        for url in urls:
            results = self.scrape_url(url, max_pages=max_pages_per_url, **kwargs)
            all_results.extend(results)
        return all_results

    def crawl_domain(
        self,
        domain: str,
        max_pages: int = 50,
        max_depth: int = 2,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Crawl an entire domain.

        Args:
            domain: Domain to crawl (e.g., 'example.com')
            max_pages: Maximum pages to crawl
            max_depth: Maximum link depth

        Returns:
            List of scraped pages
        """
        # Ensure proper URL format
        if not domain.startswith('http'):
            domain = f"https://{domain}"

        # Set globs to stay within domain
        from urllib.parse import urlparse
        parsed = urlparse(domain)
        base_domain = parsed.netloc or parsed.path
        
        globs = [f"https://{base_domain}/**", f"http://{base_domain}/**"]

        return self.scrape_url(
            url=domain,
            max_pages=max_pages,
            max_depth=max_depth,
            globs=globs,
            **kwargs
        )


class JesterApifyBridge:
    """
    Bridge for JESTER integration.
    
    Use as JESTER fallback tier when other methods fail.
    Position: After JESTER_D_PROXY, before BRIGHTDATA_SCRAPER
    """
    
    def __init__(self):
        self.scraper = ApifyWebScraper()
        self.name = "APIFY_SCRAPER"
    
    async def scrape(self, url: str) -> Dict[str, Any]:
        """JESTER-compatible scrape interface."""
        results = self.scraper.scrape_url(url, max_pages=1, max_depth=0)
        
        if not results:
            return {"success": False, "method": self.name, "content": None}
        
        result = results[0]
        return {
            "success": True,
            "method": self.name,
            "url": result.get("url"),
            "title": result.get("title"),
            "content": result.get("text"),
            "links": result.get("links", []),
            "emails": result.get("emails", []),
            "phones": result.get("phones", []),
        }
    
    def is_available(self) -> bool:
        return APIFY_AVAILABLE and bool(APIFY_TOKEN)


__all__ = ['ApifyWebScraper', 'JesterApifyBridge', 'APIFY_AVAILABLE', 'DEFAULT_PAGE_FUNCTION']
