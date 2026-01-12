"""
PACMAN Link Extractor
Extracts links from HTML content with classification
"""

import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass
from enum import Enum


class LinkType(Enum):
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    SOCIAL = 'social'
    DOCUMENT = 'document'
    ARCHIVE = 'archive'
    REGISTRY = 'registry'
    NEWS = 'news'
    LINKEDIN = 'linkedin'
    OTHER = 'other'


@dataclass
class ExtractedLink:
    url: str
    link_type: LinkType
    anchor_text: str
    domain: str
    is_outlink: bool
    context: Optional[str] = None
    metadata: Optional[Dict] = None


SOCIAL_DOMAINS = {
    'facebook.com', 'twitter.com', 'x.com', 'linkedin.com', 'instagram.com',
    'youtube.com', 'tiktok.com', 'reddit.com', 'pinterest.com', 'tumblr.com',
}

DOC_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv'}

ARCHIVE_DOMAINS = {'archive.org', 'web.archive.org', 'archive.is', 'archive.today'}

HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
ANCHOR_PATTERN = re.compile(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', re.IGNORECASE | re.DOTALL)


def extract_links(html: str, base_url: str, include_internal: bool = False, max_links: int = 100) -> List[ExtractedLink]:
    if not html:
        return []
    
    base_domain = urlparse(base_url).netloc.lower()
    results = []
    seen_urls = set()
    
    for match in ANCHOR_PATTERN.finditer(html):
        href = match.group(1).strip()
        anchor = match.group(2).strip()
        
        if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue
        
        full_url = urljoin(base_url, href)
        
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        parsed = urlparse(full_url)
        domain = parsed.netloc.lower()
        
        is_internal = domain == base_domain or domain.endswith('.' + base_domain)
        
        if is_internal and not include_internal:
            continue
        
        link_type = classify_link(full_url, domain)
        
        results.append(ExtractedLink(
            url=full_url,
            link_type=link_type,
            anchor_text=anchor,
            domain=domain,
            is_outlink=not is_internal,
        ))
        
        if len(results) >= max_links:
            break
    
    return results


def classify_link(url: str, domain: str) -> LinkType:
    domain_lower = domain.lower()
    url_lower = url.lower()
    
    if 'linkedin.com' in domain_lower:
        return LinkType.LINKEDIN
    
    for social in SOCIAL_DOMAINS:
        if social in domain_lower:
            return LinkType.SOCIAL
    
    for ext in DOC_EXTENSIONS:
        if url_lower.endswith(ext):
            return LinkType.DOCUMENT
    
    for archive in ARCHIVE_DOMAINS:
        if archive in domain_lower:
            return LinkType.ARCHIVE
    
    return LinkType.EXTERNAL


def extract_domains(html: str, base_url: str) -> Set[str]:
    links = extract_links(html, base_url, include_internal=False, max_links=500)
    return {link.domain for link in links}


def extract_social_profiles(html: str, base_url: str) -> List[ExtractedLink]:
    links = extract_links(html, base_url, include_internal=False, max_links=200)
    return [link for link in links if link.link_type == LinkType.SOCIAL]
