"""
PACMAN Tier Classifier
Classifies URLs/content into tiers for scraping strategy
"""

import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Tier(Enum):
    FULL = 'FULL'           # Full extraction + scraping
    EXTRACT = 'EXTRACT'     # Entity extraction only
    URL_ONLY = 'URL_ONLY'   # Just store URL
    SKIP = 'SKIP'           # Skip entirely


@dataclass
class TierResult:
    tier: Tier
    confidence: float
    reasons: List[str]
    metadata: Optional[Dict] = None


# High-value domains for full extraction
HIGH_VALUE_DOMAINS = {
    'linkedin.com', 'companieshouse.gov.uk', 'opencorporates.com',
    'bloomberg.com', 'reuters.com', 'ft.com', 'wsj.com',
    'sec.gov', 'fca.org.uk', 'bafin.de',
}

# Low-value domains to skip
SKIP_DOMAINS = {
    'google.com', 'facebook.com', 'twitter.com', 'instagram.com',
    'pinterest.com', 'tumblr.com', 'tiktok.com',
    'amazon.com', 'ebay.com', 'aliexpress.com',
}

# Path patterns indicating high value
HIGH_VALUE_PATHS = [
    r'/company/', r'/people/', r'/person/', r'/officer/',
    r'/profile/', r'/about/', r'/team/', r'/management/',
    r'/investor/', r'/annual-report/', r'/filing/',
    r'/press-release/', r'/news/', r'/announcement/',
]

# Path patterns indicating low value
LOW_VALUE_PATHS = [
    r'/login', r'/signup', r'/register', r'/cart', r'/checkout',
    r'/search', r'/404', r'/error', r'/privacy', r'/terms',
    r'/cookie', r'/gdpr', r'/unsubscribe',
]

# Content indicators for full extraction
FULL_EXTRACTION_KEYWORDS = {
    'director', 'officer', 'shareholder', 'beneficial owner',
    'registered agent', 'incorporation', 'company number',
    'lei', 'vat', 'iban', 'registration',
}


def classify_url(url: str) -> TierResult:
    """Classify a URL into a tier based on domain and path."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    
    reasons = []
    
    # Check skip domains first
    for skip_domain in SKIP_DOMAINS:
        if skip_domain in domain:
            return TierResult(
                tier=Tier.SKIP,
                confidence=0.95,
                reasons=[f'Domain {skip_domain} in skip list']
            )
    
    # Check high-value domains
    for hv_domain in HIGH_VALUE_DOMAINS:
        if hv_domain in domain:
            reasons.append(f'High-value domain: {hv_domain}')
            return TierResult(
                tier=Tier.FULL,
                confidence=0.9,
                reasons=reasons
            )
    
    # Check high-value paths
    for pattern in HIGH_VALUE_PATHS:
        if re.search(pattern, path):
            reasons.append(f'High-value path pattern: {pattern}')
            return TierResult(
                tier=Tier.FULL,
                confidence=0.8,
                reasons=reasons
            )
    
    # Check low-value paths
    for pattern in LOW_VALUE_PATHS:
        if re.search(pattern, path):
            reasons.append(f'Low-value path pattern: {pattern}')
            return TierResult(
                tier=Tier.URL_ONLY,
                confidence=0.85,
                reasons=reasons
            )
    
    # Default: extract
    return TierResult(
        tier=Tier.EXTRACT,
        confidence=0.6,
        reasons=['Default tier - no specific signals']
    )


def classify_content(content: str, url: str = '') -> TierResult:
    """Classify content into a tier based on signals in text."""
    content_lower = content.lower()
    reasons = []
    score = 0
    
    # Check for full extraction keywords
    keyword_matches = []
    for keyword in FULL_EXTRACTION_KEYWORDS:
        if keyword in content_lower:
            keyword_matches.append(keyword)
            score += 1
    
    if keyword_matches:
        reasons.append(f'Keywords found: {", ".join(keyword_matches[:5])}')
    
    # Length-based scoring
    if len(content) > 10000:
        score += 1
        reasons.append('Long content (>10K chars)')
    elif len(content) < 500:
        score -= 1
        reasons.append('Short content (<500 chars)')
    
    # URL classification as tiebreaker
    if url:
        url_result = classify_url(url)
        if url_result.tier == Tier.FULL:
            score += 2
        elif url_result.tier == Tier.SKIP:
            return url_result
        reasons.extend(url_result.reasons)
    
    # Determine tier from score
    if score >= 3:
        return TierResult(tier=Tier.FULL, confidence=0.85, reasons=reasons)
    elif score >= 1:
        return TierResult(tier=Tier.EXTRACT, confidence=0.7, reasons=reasons)
    elif score <= -1:
        return TierResult(tier=Tier.URL_ONLY, confidence=0.7, reasons=reasons)
    else:
        return TierResult(tier=Tier.EXTRACT, confidence=0.5, reasons=reasons)


def batch_classify(urls: List[str]) -> Dict[str, TierResult]:
    """Classify multiple URLs."""
    return {url: classify_url(url) for url in urls}
