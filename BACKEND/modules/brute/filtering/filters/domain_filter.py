"""
Domain Filter

Analyzes domain authority, reputation, and trustworthiness of search results
based on domain characteristics, security indicators, and known reputation data.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Set
import time
from pathlib import Path
import sys
from urllib.parse import urlparse
import socket

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class DomainFilter(BaseFilter):
    """
    Filter that analyzes domain authority, reputation, and trustworthiness
    to identify high-quality sources and potential spam or malicious sites.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize DomainFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("DomainFilter", config)
        
        # Default configuration
        self.default_config = {
            'authority_weight': 0.4,           # Weight for domain authority
            'security_weight': 0.3,           # Weight for security indicators
            'reputation_weight': 0.2,         # Weight for reputation signals
            'technical_weight': 0.1,          # Weight for technical indicators
            'min_domain_score': 25.0,         # Minimum score to not filter
            'blocklist_enabled': True,         # Enable known bad domain blocking
            'whitelist_enabled': True,         # Enable known good domain boosting
            'subdomain_penalty': 10.0,         # Penalty for excessive subdomains
            'max_domain_results': 10,          # Max results per domain
            
            # High authority domains
            'high_authority_domains': [
                # Educational
                '.edu', '.ac.uk', '.ac.au', '.edu.au', '.uni-', 'university',
                
                # Government
                '.gov', '.gov.uk', '.gov.au', '.gov.ca', '.mil',
                
                # Research & Academic
                'arxiv.org', 'pubmed.ncbi.nlm.nih.gov', 'scholar.google.com',
                'researchgate.net', 'academia.edu', 'jstor.org',
                
                # Scientific Publishers
                'nature.com', 'science.org', 'cell.com', 'elsevier.com',
                'springer.com', 'wiley.com', 'taylor', 'sage',
                
                # Technical Standards
                'ieee.org', 'acm.org', 'ietf.org', 'w3.org', 'iso.org',
                
                # Major News Organizations
                'reuters.com', 'ap.org', 'bbc.com', 'npr.org',
                
                # Reference Sites
                'wikipedia.org', 'britannica.com', 'merriam-webster.com'
            ],
            
            # Medium authority domains
            'medium_authority_domains': [
                'github.com', 'stackoverflow.com', 'reddit.com',
                'medium.com', 'linkedin.com', 'youtube.com',
                'cnn.com', 'nytimes.com', 'wsj.com', 'guardian.com',
                'forbes.com', 'bloomberg.com', 'techcrunch.com'
            ],
            
            # Low quality domains (not blocked, but scored lower)
            'low_quality_domains': [
                'blogspot.com', 'wordpress.com', 'tumblr.com',
                'geocities.com', 'angelfire.com', 'tripod.com',
                'weebly.com', 'wix.com', 'squarespace.com'
            ],
            
            # Known spam/malicious domains (blocked)
            'blocked_domains': [
                'bit.ly', 'tinyurl.com', 'goo.gl',  # URL shorteners (can be suspicious)
                # Add known bad domains here
            ],
            
            # TLD authority rankings
            'tld_authority': {
                '.edu': 95, '.gov': 95, '.mil': 90,
                '.org': 75, '.com': 60, '.net': 55,
                '.info': 40, '.biz': 35, '.cc': 30,
                '.tk': 20, '.ml': 20, '.ga': 20, '.cf': 20
            },
            
            # Security indicators
            'security_indicators': {
                'https_required': True,
                'certificate_check': False,  # Disabled by default (requires network calls)
                'suspicious_ports': [8080, 8000, 3000, 4000],
                'suspicious_protocols': ['ftp://', 'telnet://']
            },
            
            # Reputation indicators
            'reputation_signals': {
                'social_media_official': [
                    'twitter.com', 'facebook.com', 'linkedin.com',
                    'youtube.com', 'instagram.com'
                ],
                'cdn_domains': [
                    'amazonaws.com', 'cloudfront.net', 'cloudflare.com',
                    'akamai.com', 'fastly.com'
                ]
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"DomainFilter initialized with {len(self.config['high_authority_domains'])} authority domains")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on domain authority and reputation.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with domain scores
        """
        if not results:
            return []
        
        filter_results = []
        domain_counts = {}  # Track results per domain
        
        self.logger.debug(f"Analyzing domain authority for {len(results)} results")
        
        for i, result in enumerate(results):
            try:
                url = result.get('url', '')
                if not url:
                    # No URL - create neutral result
                    filter_results.append(self._create_neutral_result(i, "No URL provided"))
                    continue
                
                # Extract domain information
                domain_info = self._extract_domain_info(url)
                
                # Check if domain is blocked
                if self._is_blocked_domain(domain_info):
                    filter_results.append(self._create_blocked_result(i, domain_info))
                    continue
                
                # Apply domain limits
                domain = domain_info['domain']
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                
                if domain_counts[domain] > self.config['max_domain_results']:
                    filter_results.append(self._create_limited_result(i, domain_info))
                    continue
                
                # Calculate domain score
                domain_score = await self._calculate_domain_score(result, domain_info, context)
                
                # Determine tier and classification
                tier, classification = self._classify_result(domain_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(domain_info, domain_score)
                
                filter_result = FilterResult(
                    result_id=f"domain_{i}",
                    score=domain_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'domain_info': domain_info,
                        'domain_count': domain_counts[domain],
                        'filter': 'domain'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                filter_results.append(self._create_error_result(i, str(e)))
        
        avg_score = sum(fr.score for fr in filter_results) / len(filter_results)
        self.logger.debug(f"DomainFilter processed {len(results)} results, average score: {avg_score:.1f}")
        
        return filter_results
    
    def _extract_domain_info(self, url: str) -> Dict[str, Any]:
        """
        Extract comprehensive domain information from URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            Dictionary with domain information
        """
        try:
            parsed = urlparse(url)
            
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Extract TLD
            tld = ''
            domain_parts = domain.split('.')
            if len(domain_parts) >= 2:
                tld = '.' + domain_parts[-1]
                if len(domain_parts) >= 3 and domain_parts[-1] in ['uk', 'au', 'ca']:
                    tld = '.' + '.'.join(domain_parts[-2:])
            
            # Count subdomains
            subdomain_count = len(domain_parts) - 2 if len(domain_parts) > 2 else 0
            
            return {
                'url': url,
                'domain': domain,
                'tld': tld,
                'subdomain_count': subdomain_count,
                'scheme': parsed.scheme.lower(),
                'port': parsed.port,
                'path': parsed.path,
                'has_www': parsed.netloc.lower().startswith('www.'),
                'domain_length': len(domain)
            }
            
        except Exception as e:
            self.logger.warning(f"Error parsing URL '{url}': {e}")
            return {
                'url': url,
                'domain': url,
                'tld': '',
                'subdomain_count': 0,
                'scheme': 'http',
                'port': None,
                'path': '',
                'has_www': False,
                'domain_length': len(url)
            }
    
    def _is_blocked_domain(self, domain_info: Dict[str, Any]) -> bool:
        """
        Check if domain is in the blocklist.
        
        Args:
            domain_info: Domain information
            
        Returns:
            True if domain should be blocked
        """
        if not self.config['blocklist_enabled']:
            return False
        
        domain = domain_info['domain']
        
        # Check exact domain matches
        for blocked in self.config['blocked_domains']:
            if blocked.lower() in domain:
                return True
        
        # Check for suspicious characteristics
        
        # Extremely short domains (less than 4 chars, excluding TLD)
        main_domain = domain.split('.')[0]
        if len(main_domain) < 3:
            return True
        
        # Too many subdomains (potential subdomain abuse)
        if domain_info['subdomain_count'] > 4:
            return True
        
        # Suspicious protocols
        scheme = domain_info['scheme']
        for suspicious in self.config['security_indicators']['suspicious_protocols']:
            if scheme + '://' == suspicious:
                return True
        
        return False
    
    async def _calculate_domain_score(
        self,
        result: Dict[str, Any],
        domain_info: Dict[str, Any],
        context: FilterContext
    ) -> float:
        """
        Calculate comprehensive domain score.
        
        Args:
            result: Search result
            domain_info: Domain information
            context: Filtering context
            
        Returns:
            Domain score (0-100)
        """
        scores = {}
        
        # 1. Authority score
        scores['authority'] = self._calculate_authority_score(domain_info) * self.config['authority_weight']
        
        # 2. Security score
        scores['security'] = self._calculate_security_score(domain_info) * self.config['security_weight']
        
        # 3. Reputation score
        scores['reputation'] = self._calculate_reputation_score(domain_info) * self.config['reputation_weight']
        
        # 4. Technical score
        scores['technical'] = self._calculate_technical_score(domain_info) * self.config['technical_weight']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Apply penalties
        
        # Subdomain penalty
        if domain_info['subdomain_count'] > 2:
            penalty = (domain_info['subdomain_count'] - 2) * 5
            total_score -= min(penalty, self.config['subdomain_penalty'])
        
        # Normalize to 0-100 range
        domain_score = min(100.0, max(0.0, total_score))
        
        return domain_score
    
    def _calculate_authority_score(self, domain_info: Dict[str, Any]) -> float:
        """Calculate domain authority score."""
        domain = domain_info['domain']
        tld = domain_info['tld']
        
        score = 50.0  # Default neutral score
        
        # Check high authority domains
        for auth_domain in self.config['high_authority_domains']:
            if auth_domain.lower() in domain:
                score = 95.0
                break
        
        # Check medium authority domains
        if score == 50.0:  # Not already high authority
            for med_domain in self.config['medium_authority_domains']:
                if med_domain.lower() in domain:
                    score = 75.0
                    break
        
        # Check low quality domains
        if score == 50.0:  # Not already categorized
            for low_domain in self.config['low_quality_domains']:
                if low_domain.lower() in domain:
                    score = 30.0
                    break
        
        # TLD authority bonus/penalty
        if tld in self.config['tld_authority']:
            tld_score = self.config['tld_authority'][tld]
            # Blend TLD score with existing score (30% TLD, 70% domain)
            score = score * 0.7 + tld_score * 0.3
        
        return min(100.0, score)
    
    def _calculate_security_score(self, domain_info: Dict[str, Any]) -> float:
        """Calculate security score based on security indicators."""
        score = 50.0  # Default neutral score
        
        # HTTPS check
        if self.config['security_indicators']['https_required']:
            if domain_info['scheme'] == 'https':
                score += 25.0
            else:
                score -= 20.0
        
        # Port check
        port = domain_info['port']
        if port:
            if port in self.config['security_indicators']['suspicious_ports']:
                score -= 30.0
            elif port not in [80, 443, 8080]:  # Common web ports
                score -= 10.0
        
        # Domain structure security
        domain = domain_info['domain']
        
        # Check for suspicious patterns
        if re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', domain):  # IP address
            score -= 40.0
        
        if '-' in domain and domain.count('-') > 3:  # Too many hyphens
            score -= 15.0
        
        if any(char.isdigit() for char in domain) and sum(char.isdigit() for char in domain) > len(domain) * 0.3:
            score -= 15.0  # Too many numbers
        
        return min(100.0, max(0.0, score))
    
    def _calculate_reputation_score(self, domain_info: Dict[str, Any]) -> float:
        """Calculate reputation score based on known signals."""
        score = 50.0  # Default neutral score
        domain = domain_info['domain']
        
        # Social media official accounts
        for social in self.config['reputation_signals']['social_media_official']:
            if social in domain:
                score += 20.0
                break
        
        # CDN domains (usually legitimate)
        for cdn in self.config['reputation_signals']['cdn_domains']:
            if cdn in domain:
                score += 15.0
                break
        
        # Domain age estimation (very basic heuristics)
        # Shorter domains often older/more established
        if len(domain.split('.')[0]) <= 6 and not any(char.isdigit() for char in domain):
            score += 10.0
        
        # Common words in domain (might indicate legitimacy)
        common_words = ['news', 'tech', 'science', 'research', 'university', 'company', 'corp']
        if any(word in domain for word in common_words):
            score += 10.0
        
        return min(100.0, score)
    
    def _calculate_technical_score(self, domain_info: Dict[str, Any]) -> float:
        """Calculate technical quality score."""
        score = 50.0  # Default neutral score
        
        # Domain length (not too short, not too long)
        domain_length = domain_info['domain_length']
        if 8 <= domain_length <= 30:
            score += 20.0
        elif domain_length < 5:
            score -= 20.0
        elif domain_length > 50:
            score -= 15.0
        
        # Subdomain analysis
        subdomain_count = domain_info['subdomain_count']
        if subdomain_count == 0:
            score += 10.0  # Clean domain
        elif subdomain_count <= 2:
            score += 5.0   # Reasonable subdomain use
        else:
            score -= subdomain_count * 5  # Penalty for excessive subdomains
        
        # Path structure (basic check)
        path = domain_info['path']
        if path == '/' or not path:
            score += 5.0  # Clean root URL
        elif len(path.split('/')) <= 4:
            score += 3.0  # Reasonable path depth
        
        return min(100.0, max(0.0, score))
    
    def _classify_result(self, domain_score: float) -> tuple:
        """Classify result based on domain score."""
        if domain_score >= 85.0:
            return 1, 'primary'
        elif domain_score >= 70.0:
            return 2, 'primary'
        elif domain_score >= 50.0:
            return 3, 'secondary'
        elif domain_score >= self.config['min_domain_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out
    
    def _generate_reasoning(self, domain_info: Dict[str, Any], score: float) -> str:
        """Generate human-readable reasoning for the domain score."""
        domain = domain_info['domain']
        reasons = []
        
        if score >= 85:
            reasons.append("High authority domain")
        elif score >= 70:
            reasons.append("Good reputation domain")
        elif score >= 50:
            reasons.append("Standard domain")
        else:
            reasons.append("Lower trust domain")
        
        # Add specific indicators
        for auth_domain in self.config['high_authority_domains']:
            if auth_domain.lower() in domain:
                reasons.append(f"Authoritative source ({auth_domain})")
                break
        
        if domain_info['scheme'] == 'https':
            reasons.append("Secure HTTPS")
        else:
            reasons.append("Non-secure HTTP")
        
        if domain_info['subdomain_count'] > 2:
            reasons.append(f"Multiple subdomains ({domain_info['subdomain_count']})")
        
        return "; ".join(reasons)
    
    def _create_neutral_result(self, index: int, reason: str) -> FilterResult:
        """Create neutral result for edge cases."""
        return FilterResult(
            result_id=f"domain_neutral_{index}",
            score=50.0,
            tier=3,
            classification='secondary',
            reasoning=reason,
            metadata={'filter': 'domain', 'neutral': True},
            processed_at=time.time()
        )
    
    def _create_blocked_result(self, index: int, domain_info: Dict[str, Any]) -> FilterResult:
        """Create result for blocked domains."""
        return FilterResult(
            result_id=f"domain_blocked_{index}",
            score=5.0,  # Very low score but not zero
            tier=4,
            classification='secondary',
            reasoning=f"Blocked domain: {domain_info['domain']}",
            metadata={'filter': 'domain', 'blocked': True, 'domain_info': domain_info},
            processed_at=time.time()
        )
    
    def _create_limited_result(self, index: int, domain_info: Dict[str, Any]) -> FilterResult:
        """Create result for domain-limited results."""
        return FilterResult(
            result_id=f"domain_limited_{index}",
            score=40.0,  # Reduced score due to over-representation
            tier=4,
            classification='secondary',
            reasoning=f"Too many results from domain: {domain_info['domain']}",
            metadata={'filter': 'domain', 'limited': True, 'domain_info': domain_info},
            processed_at=time.time()
        )
    
    def _create_error_result(self, index: int, error_msg: str) -> FilterResult:
        """Create result for processing errors."""
        return FilterResult(
            result_id=f"domain_error_{index}",
            score=30.0,
            tier=4,
            classification='secondary',
            reasoning=f"Domain analysis error: {error_msg}",
            metadata={'filter': 'domain', 'error': True},
            processed_at=time.time()
        )