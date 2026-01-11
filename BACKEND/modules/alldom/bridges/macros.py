"""
ALLDOM Bridge: MACROS

Thin wrapper for domain macro operations (age!, ga!, tech!).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def age(domain_or_url: str, **kwargs) -> Dict[str, Any]:
    """
    Get domain/URL age information (age!).

    Combines WHOIS creation date + Wayback earliest snapshot.
    """
    try:
        from modules.alldom.inputs.domain_url import get_age_info

        result = await get_age_info(domain_or_url)

        # Normalize response
        return {
            "target": domain_or_url,
            "whois_created": result.get("domain_whois_info", {}).get("created_date"),
            "wayback_first": result.get("url_earliest_snapshot"),
            "age_source": "whois" if result.get("domain_whois_info") else "wayback",
            "raw": result,
            "success": bool(result.get("domain_whois_info") or result.get("url_earliest_snapshot")),
        }
    except Exception as e:
        logger.error(f"Age lookup error: {e}")
        return {"target": domain_or_url, "success": False, "error": str(e)}


async def ga(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Extract Google Analytics/GTM codes from domain (ga!).

    Uses alldom GA analysis source.
    """
    try:
        from modules.alldom.sources.ga_analysis import GAAnalysisDiscovery

        ga_disc = GAAnalysisDiscovery()
        results = []

        async for discovered in ga_disc.discover_ga_codes(domain):
            results.append({
                "code": discovered.url,  # GA code is stored in url field
                "type": discovered.metadata.get("type", "unknown"),
                "found_on": discovered.metadata.get("found_on"),
            })

        # Dedupe by code
        seen = set()
        unique = []
        for r in results:
            if r["code"] not in seen:
                seen.add(r["code"])
                unique.append(r)

        return {
            "domain": domain,
            "ga_codes": [r for r in unique if r.get("type") in ("UA", "GA4", "G-")],
            "gtm_codes": [r for r in unique if r.get("type") == "GTM"],
            "all_codes": unique,
            "success": bool(unique),
        }
    except ImportError:
        logger.warning("GA analysis not available")
        return {"domain": domain, "success": False, "error": "GA analysis not installed"}
    except Exception as e:
        logger.error(f"GA analysis error: {e}")
        return {"domain": domain, "success": False, "error": str(e)}


async def tech(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Detect technologies used by domain (tech!).

    Extracts: CMS, frameworks, analytics, hosting, CDN, etc.
    """
    try:
        # Try Wappalyzer-style detection
        from modules.alldom.sources.tech_detection import TechDetector

        detector = TechDetector()
        result = await detector.detect(domain)

        return {
            "domain": domain,
            "technologies": result.get("technologies", []),
            "categories": result.get("categories", {}),
            "headers": result.get("headers", {}),
            "success": True,
        }
    except ImportError:
        # Fallback to basic detection
        return await _fallback_tech_detect(domain)
    except Exception as e:
        logger.error(f"Tech detection error: {e}")
        return {"domain": domain, "success": False, "error": str(e)}


async def _fallback_tech_detect(domain: str) -> Dict[str, Any]:
    """Basic tech detection via HTTP headers."""
    import aiohttp

    technologies = []
    headers_found = {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://{domain}",
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as response:
                headers = dict(response.headers)
                headers_found = headers

                # Detect from headers
                if "X-Powered-By" in headers:
                    technologies.append({
                        "name": headers["X-Powered-By"],
                        "category": "backend",
                        "confidence": 1.0,
                    })

                if "Server" in headers:
                    technologies.append({
                        "name": headers["Server"],
                        "category": "server",
                        "confidence": 1.0,
                    })

                if "X-Generator" in headers:
                    technologies.append({
                        "name": headers["X-Generator"],
                        "category": "cms",
                        "confidence": 1.0,
                    })

                # Check for Cloudflare
                if "cf-ray" in headers or "CF-RAY" in headers:
                    technologies.append({
                        "name": "Cloudflare",
                        "category": "cdn",
                        "confidence": 1.0,
                    })

        return {
            "domain": domain,
            "technologies": technologies,
            "headers": headers_found,
            "success": True,
            "source": "headers",
        }
    except Exception as e:
        return {"domain": domain, "success": False, "error": str(e)}


async def ssl(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Get SSL certificate information.
    """
    import ssl
    import socket
    from datetime import datetime

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

                return {
                    "domain": domain,
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "valid_from": cert.get("notBefore"),
                    "valid_until": cert.get("notAfter"),
                    "san": cert.get("subjectAltName", []),
                    "success": True,
                }
    except Exception as e:
        return {"domain": domain, "success": False, "error": str(e)}


async def robots(domain: str, **kwargs) -> Dict[str, Any]:
    """
    Fetch and parse robots.txt.
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://{domain}/robots.txt",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    content = await response.text()
                    return {
                        "domain": domain,
                        "content": content,
                        "success": True,
                    }
                return {
                    "domain": domain,
                    "success": False,
                    "error": f"HTTP {response.status}",
                }
    except Exception as e:
        return {"domain": domain, "success": False, "error": str(e)}
