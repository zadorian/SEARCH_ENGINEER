#!/usr/bin/env python3
"""
Technology Stack Discovery Module

Detect CMS, frameworks, analytics, and other technologies used by a domain.

Discovery Methods:
1. HTTP Headers: Server, X-Powered-By, X-Generator
2. HTML Fingerprinting: Meta tags, script sources, CSS frameworks
3. PublicWWW API: Search for technology fingerprints in HTML

Use Cases:
- Find all sites using WordPress: "What domains use WordPress?"
- Cluster by tech: "Find sites with same tech stack as target"
- Identify vulnerabilities: "What version of jQuery is this site using?"
"""

import os
import httpx
import logging
import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

logger = logging.getLogger(__name__)

# PublicWWW API for fingerprint searching
PUBLICWWW_API_KEY = os.getenv('PUBLICWWW_API_KEY')

# Technology fingerprints for detection
TECH_FINGERPRINTS = {
    # CMS
    "wordpress": {
        "headers": [],
        "meta": ["generator:WordPress"],
        "html": ["wp-content", "wp-includes", "/wp-json/"],
        "scripts": ["wp-emoji-release.min.js", "jquery/jquery.js"],
    },
    "drupal": {
        "headers": ["X-Generator:Drupal"],
        "meta": ["generator:Drupal"],
        "html": ["/sites/default/files/", "drupal.js"],
        "scripts": ["misc/drupal.js"],
    },
    "joomla": {
        "headers": [],
        "meta": ["generator:Joomla"],
        "html": ["/media/jui/", "/templates/"],
        "scripts": [],
    },
    "shopify": {
        "headers": ["X-ShopId"],
        "meta": [],
        "html": ["cdn.shopify.com", "Shopify.theme"],
        "scripts": ["shopify.com/s/files/"],
    },
    "wix": {
        "headers": [],
        "meta": [],
        "html": ["static.wixstatic.com", "wix-code-sdk"],
        "scripts": ["wix.com"],
    },
    "squarespace": {
        "headers": [],
        "meta": [],
        "html": ["squarespace.com", "static1.squarespace.com"],
        "scripts": [],
    },
    # Frameworks
    "react": {
        "headers": [],
        "meta": [],
        "html": ["react-root", "__NEXT_DATA__", "_reactRootContainer"],
        "scripts": ["react.production.min.js", "react-dom.production"],
    },
    "angular": {
        "headers": [],
        "meta": [],
        "html": ["ng-app", "ng-controller", "ng-version"],
        "scripts": ["angular.min.js", "angular.js"],
    },
    "vue": {
        "headers": [],
        "meta": [],
        "html": ["vue-app", "__vue__", "data-v-"],
        "scripts": ["vue.min.js", "vue.js", "vue.runtime"],
    },
    "nextjs": {
        "headers": ["X-Powered-By:Next.js"],
        "meta": [],
        "html": ["__NEXT_DATA__", "_next/static"],
        "scripts": ["/_next/"],
    },
    "nuxt": {
        "headers": [],
        "meta": [],
        "html": ["__NUXT__", "_nuxt/"],
        "scripts": ["/_nuxt/"],
    },
    # Analytics
    "google_analytics": {
        "headers": [],
        "meta": [],
        "html": ["google-analytics.com/analytics.js", "gtag/js", "UA-"],
        "scripts": ["googletagmanager.com", "google-analytics.com"],
    },
    "google_tag_manager": {
        "headers": [],
        "meta": [],
        "html": ["googletagmanager.com/gtm.js", "GTM-"],
        "scripts": ["googletagmanager.com/gtm.js"],
    },
    "facebook_pixel": {
        "headers": [],
        "meta": [],
        "html": ["connect.facebook.net/en_US/fbevents.js", "fbq("],
        "scripts": ["connect.facebook.net"],
    },
    "hotjar": {
        "headers": [],
        "meta": [],
        "html": ["static.hotjar.com", "hjid="],
        "scripts": ["static.hotjar.com"],
    },
    # CDNs
    "cloudflare": {
        "headers": ["Server:cloudflare", "CF-RAY"],
        "meta": [],
        "html": [],
        "scripts": ["cdnjs.cloudflare.com"],
    },
    "akamai": {
        "headers": ["X-Akamai-Transformed", "Server:AkamaiGHost"],
        "meta": [],
        "html": [],
        "scripts": [],
    },
    "fastly": {
        "headers": ["X-Served-By", "X-Cache:HIT", "Via:.*varnish"],
        "meta": [],
        "html": [],
        "scripts": [],
    },
    "aws_cloudfront": {
        "headers": ["X-Amz-Cf-Id", "X-Amz-Cf-Pop", "Via:.*cloudfront"],
        "meta": [],
        "html": [],
        "scripts": ["cloudfront.net"],
    },
    # JavaScript Libraries
    "jquery": {
        "headers": [],
        "meta": [],
        "html": ["jQuery v", "jquery.min.js"],
        "scripts": ["jquery.min.js", "jquery-"],
    },
    "bootstrap": {
        "headers": [],
        "meta": [],
        "html": ["bootstrap.min.css", "bootstrap.min.js"],
        "scripts": ["bootstrap.min.js", "bootstrap.bundle"],
    },
    "tailwind": {
        "headers": [],
        "meta": [],
        "html": ["tailwind", "class=\"tw-"],
        "scripts": ["tailwindcss"],
    },
    # Servers
    "nginx": {
        "headers": ["Server:nginx"],
        "meta": [],
        "html": [],
        "scripts": [],
    },
    "apache": {
        "headers": ["Server:Apache"],
        "meta": [],
        "html": [],
        "scripts": [],
    },
    "iis": {
        "headers": ["Server:Microsoft-IIS"],
        "meta": [],
        "html": [],
        "scripts": [],
    },
    # Languages
    "php": {
        "headers": ["X-Powered-By:PHP"],
        "meta": [],
        "html": [".php"],
        "scripts": [],
    },
    "asp_net": {
        "headers": ["X-Powered-By:ASP.NET", "X-AspNet-Version"],
        "meta": [],
        "html": [".aspx", ".ashx"],
        "scripts": [],
    },
    "java": {
        "headers": ["X-Powered-By:Servlet", "X-Powered-By:JSP"],
        "meta": [],
        "html": [".jsp", ".jsf"],
        "scripts": [],
    },
}


@dataclass
class TechnologyResult:
    """Single technology detection result"""
    name: str
    category: str  # cms, framework, analytics, cdn, library, server, language
    confidence: float  # 0.0 - 1.0
    version: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TechDiscoveryResponse:
    """Technology discovery response"""
    domain: str
    technologies: List[TechnologyResult]
    headers_analyzed: Dict[str, str]
    total_found: int
    elapsed_ms: int = 0
    source: str = "header_fingerprint"


def categorize_tech(tech_name: str) -> str:
    """Get category for a technology"""
    categories = {
        "cms": ["wordpress", "drupal", "joomla", "shopify", "wix", "squarespace"],
        "framework": ["react", "angular", "vue", "nextjs", "nuxt"],
        "analytics": ["google_analytics", "google_tag_manager", "facebook_pixel", "hotjar"],
        "cdn": ["cloudflare", "akamai", "fastly", "aws_cloudfront"],
        "library": ["jquery", "bootstrap", "tailwind"],
        "server": ["nginx", "apache", "iis"],
        "language": ["php", "asp_net", "java"],
    }
    for category, techs in categories.items():
        if tech_name in techs:
            return category
    return "other"


def extract_version(text: str, tech_name: str) -> Optional[str]:
    """Try to extract version from text"""
    # Common version patterns
    patterns = [
        rf'{tech_name}[/\s]v?(\d+\.\d+(?:\.\d+)?)',
        rf'{tech_name}[/\s]?(\d+\.\d+(?:\.\d+)?)',
        r'v(\d+\.\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


async def analyze_domain(
    domain: str,
    timeout: float = 15.0,
    follow_redirects: bool = True
) -> TechDiscoveryResponse:
    """
    Analyze a domain to detect its technology stack.

    Args:
        domain: Target domain (e.g., "sebgroup.com")
        timeout: Request timeout in seconds
        follow_redirects: Follow HTTP redirects

    Returns:
        TechDiscoveryResponse with detected technologies
    """
    import time
    start_time = time.time()

    # Normalize domain
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain.startswith("http"):
        url = f"https://{domain}"
    else:
        url = domain
        domain = urlparse(url).netloc

    logger.info(f"[Tech Discovery] Analyzing: {domain}")

    detected: Dict[str, TechnologyResult] = {}
    headers_analyzed: Dict[str, str] = {}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=False  # Some sites have SSL issues
        ) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            # Extract headers
            headers_analyzed = dict(response.headers)
            html_content = response.text[:100000]  # First 100KB

            # Analyze each technology
            for tech_name, fingerprints in TECH_FINGERPRINTS.items():
                evidence = []
                confidence = 0.0
                version = None

                # Check headers
                for header_pattern in fingerprints.get("headers", []):
                    if ":" in header_pattern:
                        header_name, header_value = header_pattern.split(":", 1)
                        actual_value = response.headers.get(header_name, "")
                        if re.search(header_value, actual_value, re.IGNORECASE):
                            evidence.append(f"Header: {header_name}={actual_value}")
                            confidence += 0.4
                            version = version or extract_version(actual_value, tech_name)
                    else:
                        if header_pattern in response.headers:
                            evidence.append(f"Header: {header_pattern}")
                            confidence += 0.4

                # Check meta tags
                for meta_pattern in fingerprints.get("meta", []):
                    if ":" in meta_pattern:
                        meta_name, meta_value = meta_pattern.split(":", 1)
                        pattern = rf'<meta[^>]*name=["\']?{meta_name}["\']?[^>]*content=["\']?([^"\']+)'
                        match = re.search(pattern, html_content, re.IGNORECASE)
                        if match and meta_value.lower() in match.group(1).lower():
                            evidence.append(f"Meta: {meta_name}={match.group(1)}")
                            confidence += 0.5
                            version = version or extract_version(match.group(1), tech_name)

                # Check HTML patterns
                for html_pattern in fingerprints.get("html", []):
                    if html_pattern.lower() in html_content.lower():
                        evidence.append(f"HTML: {html_pattern}")
                        confidence += 0.3
                        version = version or extract_version(html_content, tech_name)

                # Check script sources
                for script_pattern in fingerprints.get("scripts", []):
                    if script_pattern.lower() in html_content.lower():
                        evidence.append(f"Script: {script_pattern}")
                        confidence += 0.35
                        version = version or extract_version(html_content, tech_name)

                # Cap confidence at 1.0
                confidence = min(confidence, 1.0)

                # Only include if confident enough
                if confidence >= 0.3:
                    detected[tech_name] = TechnologyResult(
                        name=tech_name.replace("_", " ").title(),
                        category=categorize_tech(tech_name),
                        confidence=round(confidence, 2),
                        version=version,
                        evidence=evidence[:5],  # Top 5 pieces of evidence
                        metadata={}
                    )

            logger.info(f"[Tech Discovery] Found {len(detected)} technologies on {domain}")

    except httpx.TimeoutException:
        logger.warning(f"[Tech Discovery] Timeout for {domain}")
    except Exception as e:
        logger.error(f"[Tech Discovery] Error analyzing {domain}: {e}")

    elapsed_ms = int((time.time() - start_time) * 1000)

    # Sort by confidence
    results = sorted(detected.values(), key=lambda x: x.confidence, reverse=True)

    return TechDiscoveryResponse(
        domain=domain,
        technologies=results,
        headers_analyzed=headers_analyzed,
        total_found=len(results),
        elapsed_ms=elapsed_ms,
        source="header_fingerprint"
    )


async def find_domains_by_technology(
    technology: str,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Find domains using a specific technology via PublicWWW API.

    Args:
        technology: Technology name or fingerprint to search for
        limit: Maximum results to return

    Returns:
        List of domains using the technology
    """
    if not PUBLICWWW_API_KEY:
        logger.warning("[Tech Discovery] Missing PUBLICWWW_API_KEY")
        return []

    # Map technology names to fingerprints
    fingerprint_map = {
        "wordpress": 'wp-content',
        "drupal": 'sites/default/files',
        "shopify": 'cdn.shopify.com',
        "react": 'react-dom',
        "angular": 'ng-app',
        "vue": 'vue.js',
        "nextjs": '__NEXT_DATA__',
        "google_analytics": 'google-analytics.com/analytics.js',
        "cloudflare": 'cdnjs.cloudflare.com',
        "jquery": 'jquery.min.js',
        "bootstrap": 'bootstrap.min.css',
    }

    search_term = fingerprint_map.get(technology.lower(), technology)

    logger.info(f"[Tech Discovery PublicWWW] Searching for: {search_term}")

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                "https://publicwww.com/websites",
                params={
                    "key": PUBLICWWW_API_KEY,
                    "q": f'"{search_term}"',
                    "export": "urls",
                    "limit": limit
                }
            )

            if response.status_code == 200:
                # PublicWWW returns plain text, one URL per line
                urls = response.text.strip().split('\n')
                for url in urls:
                    if url:
                        domain = urlparse(url).netloc
                        if domain:
                            results.append({
                                "domain": domain,
                                "url": url,
                                "technology": technology,
                                "source": "publicwww"
                            })

                logger.info(f"[Tech Discovery PublicWWW] Found {len(results)} domains using {technology}")
            else:
                logger.warning(f"[Tech Discovery PublicWWW] API error: {response.status_code}")

        except Exception as e:
            logger.error(f"[Tech Discovery PublicWWW] Error: {e}")

    return results


async def batch_analyze_domains(
    domains: List[str],
    max_concurrent: int = 5
) -> Dict[str, TechDiscoveryResponse]:
    """
    Batch analyze multiple domains for their technology stacks.

    Args:
        domains: List of domains to analyze
        max_concurrent: Maximum concurrent requests

    Returns:
        Dict mapping domain to its TechDiscoveryResponse
    """
    import asyncio

    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_with_semaphore(domain: str):
        async with semaphore:
            return domain, await analyze_domain(domain)

    tasks = [analyze_with_semaphore(d) for d in domains]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for resp in responses:
        if isinstance(resp, Exception):
            logger.error(f"[Tech Discovery Batch] Error: {resp}")
            continue
        domain, discovery_response = resp
        results[domain] = discovery_response

    return results


async def find_similar_tech_stack(
    domain: str,
    min_overlap: int = 3
) -> List[Dict[str, Any]]:
    """
    Find domains with similar technology stack.

    This combines:
    1. Analyze target domain
    2. Search for each detected technology
    3. Rank by overlap

    Args:
        domain: Target domain
        min_overlap: Minimum number of shared technologies

    Returns:
        List of domains with similar tech stack
    """
    # First analyze the target
    target_tech = await analyze_domain(domain)

    if target_tech.total_found == 0:
        logger.warning(f"[Tech Discovery] No technologies detected on {domain}")
        return []

    # Get top technologies (highest confidence)
    top_techs = [t.name.lower().replace(" ", "_") for t in target_tech.technologies[:5]]

    logger.info(f"[Tech Discovery] Finding domains with similar stack to {domain}: {top_techs}")

    # Search for each technology
    domain_scores: Dict[str, int] = {}

    for tech in top_techs:
        matches = await find_domains_by_technology(tech, limit=50)
        for match in matches:
            match_domain = match["domain"]
            if match_domain != domain:
                domain_scores[match_domain] = domain_scores.get(match_domain, 0) + 1

    # Filter by minimum overlap and sort
    similar = [
        {"domain": d, "shared_techs": count, "target_techs": top_techs}
        for d, count in domain_scores.items()
        if count >= min_overlap
    ]

    similar.sort(key=lambda x: x["shared_techs"], reverse=True)

    logger.info(f"[Tech Discovery] Found {len(similar)} domains with similar tech stack")

    return similar[:50]


# CLI entry point
if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Detect technology stack on domains")
    parser.add_argument("domain", help="Target domain (e.g., sebgroup.com)")
    parser.add_argument("-s", "--search", help="Search for domains using this technology")
    parser.add_argument("-l", "--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()

    async def main():
        if args.search:
            print(f"\n🔍 Searching for domains using: {args.search}")
            results = await find_domains_by_technology(args.search, limit=args.limit)
            print(f"Found: {len(results)} domains\n")
            for r in results[:20]:
                print(f"  - {r['domain']}")
        else:
            print(f"\n🔧 Analyzing technology stack for: {args.domain}")
            response = await analyze_domain(args.domain)

            print(f"\nFound {response.total_found} technologies in {response.elapsed_ms}ms:\n")

            for tech in response.technologies:
                version_str = f" v{tech.version}" if tech.version else ""
                print(f"  [{tech.category.upper()}] {tech.name}{version_str}")
                print(f"    Confidence: {tech.confidence:.0%}")
                print(f"    Evidence: {', '.join(tech.evidence[:3])}")
                print()

    asyncio.run(main())

# Alias for compatibility
discover_tech_stack = analyze_domain
