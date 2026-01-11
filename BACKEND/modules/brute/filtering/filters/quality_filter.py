"""
Quality Filter

Analyzes the quality of search results based on content depth, authority signals,
technical indicators, and spam detection.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any
import time
from pathlib import Path
import sys
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class QualityFilter(BaseFilter):
    """
    Filter that analyzes content quality using multiple quality indicators
    including content depth, authority signals, and spam detection.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize QualityFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("QualityFilter", config)
        
        # Default configuration
        self.default_config = {
            'content_depth_weight': 0.25,      # Weight for content depth analysis
            'authority_signals_weight': 0.25,  # Weight for domain authority signals
            'technical_quality_weight': 0.20,  # Weight for technical quality
            'spam_detection_weight': 0.15,     # Weight for spam detection (negative)
            'freshness_weight': 0.15,          # Weight for content freshness
            'min_quality_score': 20.0,         # Minimum score to not filter
            'snippet_min_length': 50,          # Minimum snippet length for quality
            'title_min_length': 10,            # Minimum title length
            'authority_domains': [             # High-authority domains
                '.edu', '.gov', '.org',
                'wikipedia.org', 'arxiv.org', 'pubmed.gov',
                'nature.com', 'science.org', 'ieee.org',
                'acm.org', 'springer.com', 'wiley.com'
            ],
            'low_quality_domains': [           # Known low-quality domains
                'blogspot.com', 'wordpress.com', 'tumblr.com',
                'geocities.com', 'weebly.com', 'wix.com'
            ],
            'spam_indicators': [               # Common spam indicators
                'buy now', 'click here', 'free money', 'get rich',
                'limited time', 'act now', 'guaranteed', 'miracle',
                '$$$', '!!!', 'URGENT', 'AMAZING'
            ],
            'quality_keywords': [              # Keywords indicating quality content
                'research', 'study', 'analysis', 'report', 'documentation',
                'guide', 'tutorial', 'reference', 'specification'
            ]
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"QualityFilter initialized with config keys: {list(self.config.keys())}")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on content quality indicators.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with quality scores
        """
        if not results:
            return []
        
        filter_results = []
        
        self.logger.debug(f"Analyzing quality for {len(results)} results")
        
        for i, result in enumerate(results):
            try:
                # Calculate comprehensive quality score
                quality_score = await self._calculate_quality_score(result, context)
                
                # Determine tier and classification
                tier, classification = self._classify_result(quality_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(result, quality_score)
                
                # Get detailed quality breakdown
                quality_breakdown = self._get_quality_breakdown(result)
                
                filter_result = FilterResult(
                    result_id=f"quality_{i}",
                    score=quality_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'quality_breakdown': quality_breakdown,
                        'filter': 'quality'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                # Create low-score result for error cases
                filter_results.append(FilterResult(
                    result_id=f"quality_error_{i}",
                    score=30.0,  # Low but not zero score
                    tier=4,
                    classification='secondary',
                    reasoning=f"Quality analysis error: {str(e)}",
                    metadata={'error': True, 'filter': 'quality'},
                    processed_at=time.time()
                ))
        
        avg_score = sum(fr.score for fr in filter_results) / len(filter_results)
        self.logger.debug(f"QualityFilter processed {len(results)} results, average score: {avg_score:.1f}")
        
        return filter_results
    
    async def _calculate_quality_score(
        self,
        result: Dict[str, Any],
        context: FilterContext
    ) -> float:
        """
        Calculate comprehensive quality score for a result.
        
        Args:
            result: Search result to analyze
            context: Filtering context
            
        Returns:
            Quality score (0-100)
        """
        scores = {}
        
        # 1. Content depth analysis
        scores['content_depth'] = self._analyze_content_depth(result) * self.config['content_depth_weight']
        
        # 2. Authority signals
        scores['authority'] = self._analyze_authority_signals(result) * self.config['authority_signals_weight']
        
        # 3. Technical quality
        scores['technical'] = self._analyze_technical_quality(result) * self.config['technical_quality_weight']
        
        # 4. Spam detection (negative scoring)
        spam_score = self._detect_spam_indicators(result)
        scores['spam_penalty'] = -(spam_score * self.config['spam_detection_weight'])
        
        # 5. Freshness indicators
        scores['freshness'] = self._analyze_freshness(result) * self.config['freshness_weight']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Normalize to 0-100 range
        quality_score = min(100.0, max(0.0, total_score))
        
        return quality_score
    
    def _analyze_content_depth(self, result: Dict[str, Any]) -> float:
        """
        Analyze the depth and substance of content.
        
        Args:
            result: Search result to analyze
            
        Returns:
            Content depth score (0-100)
        """
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        
        score = 0.0
        
        # Title analysis
        if len(title) >= self.config['title_min_length']:
            score += 20.0
            
            # Bonus for descriptive titles
            if len(title) > 30:
                score += 10.0
            
            # Penalty for all caps or excessive punctuation
            if title.isupper():
                score -= 15.0
            if title.count('!') > 2:
                score -= 10.0
        
        # Snippet analysis
        if len(snippet) >= self.config['snippet_min_length']:
            score += 30.0
            
            # Bonus for substantial content
            if len(snippet) > 200:
                score += 15.0
            
            # Check for quality indicators
            quality_keywords = self.config['quality_keywords']
            quality_matches = sum(1 for keyword in quality_keywords 
                                if keyword.lower() in snippet.lower())
            score += min(15.0, quality_matches * 5)
            
            # Analyze sentence structure
            sentences = snippet.split('.')
            if len(sentences) > 2:
                score += 10.0
        
        # URL structure analysis
        parsed_url = urlparse(url)
        if parsed_url.path and len(parsed_url.path) > 10:
            score += 5.0
            
            # Bonus for structured URLs
            if '/' in parsed_url.path[1:]:  # Multiple path segments
                score += 5.0
        
        return min(100.0, score)
    
    def _analyze_authority_signals(self, result: Dict[str, Any]) -> float:
        """
        Analyze domain and source authority signals.
        
        Args:
            result: Search result to analyze
            
        Returns:
            Authority score (0-100)
        """
        url = result.get('url', '').lower()
        source = result.get('source', '').lower()
        
        score = 50.0  # Default neutral score
        
        # Check for high-authority domains
        for domain in self.config['authority_domains']:
            if domain in url:
                score = 90.0
                break
        
        # Check for low-quality domains
        for domain in self.config['low_quality_domains']:
            if domain in url:
                score = min(score, 30.0)
                break
        
        # HTTPS bonus
        if url.startswith('https://'):
            score += 5.0
        
        # Domain length analysis (very short domains might be suspicious)
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain:
            if len(domain) < 5:
                score -= 10.0
            elif len(domain) > 50:
                score -= 5.0
        
        # Check for subdomain patterns
        if parsed_url.netloc.count('.') > 2:  # Many subdomains might indicate lower quality
            score -= 5.0
        
        # News and media authority
        news_indicators = ['news', 'times', 'post', 'herald', 'journal', 'gazette']
        if any(indicator in url for indicator in news_indicators):
            score += 10.0
        
        return min(100.0, max(0.0, score))
    
    def _analyze_technical_quality(self, result: Dict[str, Any]) -> float:
        """
        Analyze technical quality indicators.
        
        Args:
            result: Search result to analyze
            
        Returns:
            Technical quality score (0-100)
        """
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        
        score = 50.0  # Default neutral score
        
        # Title quality checks
        if title:
            # Proper capitalization
            if title.istitle() or (title[0].isupper() and not title.isupper()):
                score += 10.0
            
            # No truncation indicators
            if not title.endswith('...'):
                score += 5.0
            
            # Reasonable length
            if 20 <= len(title) <= 100:
                score += 10.0
        
        # Snippet quality checks
        if snippet:
            # Proper sentence structure
            if snippet.endswith('.') or snippet.endswith('!') or snippet.endswith('?'):
                score += 10.0
            
            # No excessive repetition
            words = snippet.lower().split()
            if len(set(words)) / max(len(words), 1) > 0.7:  # Good word diversity
                score += 10.0
            
            # Check for complete sentences
            if len([s for s in snippet.split('.') if len(s.strip()) > 10]) >= 2:
                score += 10.0
        
        # URL quality
        if url:
            # Clean URL structure
            if not any(char in url for char in ['?', '&', '=']) or url.count('?') <= 1:
                score += 5.0
            
            # No excessive parameters
            if url.count('&') <= 3:
                score += 5.0
        
        return min(100.0, max(0.0, score))
    
    def _detect_spam_indicators(self, result: Dict[str, Any]) -> float:
        """
        Detect spam and low-quality indicators.
        
        Args:
            result: Search result to analyze
            
        Returns:
            Spam score (0-100, higher means more spammy)
        """
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        url = result.get('url', '').lower()
        
        spam_score = 0.0
        
        # Check for spam keywords
        combined_text = f"{title} {snippet}"
        for indicator in self.config['spam_indicators']:
            if indicator.lower() in combined_text:
                spam_score += 15.0
        
        # Excessive punctuation
        exclamation_count = title.count('!') + snippet.count('!')
        if exclamation_count > 3:
            spam_score += exclamation_count * 5
        
        # ALL CAPS content
        caps_ratio = sum(1 for c in combined_text if c.isupper()) / max(len(combined_text), 1)
        if caps_ratio > 0.3:
            spam_score += caps_ratio * 50
        
        # Suspicious URL patterns
        if any(pattern in url for pattern in ['?id=', '&ref=', 'affiliate', 'promo']):
            spam_score += 10.0
        
        # Excessive numbers in title (might indicate spam)
        number_count = sum(1 for c in title if c.isdigit())
        if number_count > len(title) * 0.2:  # More than 20% numbers
            spam_score += 20.0
        
        # Short, low-quality content
        if len(snippet) < 30 and title.count(' ') < 3:
            spam_score += 25.0
        
        return min(100.0, spam_score)
    
    def _analyze_freshness(self, result: Dict[str, Any]) -> float:
        """
        Analyze content freshness indicators.
        
        Args:
            result: Search result to analyze
            
        Returns:
            Freshness score (0-100)
        """
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        
        score = 60.0  # Default neutral score
        
        # Look for freshness indicators
        fresh_indicators = [
            '2024', '2023', 'recent', 'latest', 'new', 'updated', 
            'current', 'today', 'this year', 'recently'
        ]
        
        stale_indicators = [
            '2020', '2019', '2018', 'old', 'archived', 'legacy',
            'deprecated', 'outdated'
        ]
        
        # Check for freshness indicators
        for indicator in fresh_indicators:
            if indicator in title or indicator in snippet:
                score += 10.0
                break
        
        # Check for staleness indicators
        for indicator in stale_indicators:
            if indicator in title or indicator in snippet:
                score -= 15.0
                break
        
        # URL freshness indicators
        url = result.get('url', '').lower()
        if any(year in url for year in ['2024', '2023']):
            score += 10.0
        elif any(year in url for year in ['2020', '2019', '2018']):
            score -= 10.0
        
        return min(100.0, max(0.0, score))
    
    def _classify_result(self, quality_score: float) -> tuple:
        """
        Classify result based on quality score.
        
        Args:
            quality_score: Calculated quality score
            
        Returns:
            Tuple of (tier, classification)
        """
        if quality_score >= 80.0:
            return 1, 'primary'
        elif quality_score >= 65.0:
            return 2, 'primary'
        elif quality_score >= 45.0:
            return 3, 'secondary'
        elif quality_score >= self.config['min_quality_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out
    
    def _generate_reasoning(self, result: Dict[str, Any], score: float) -> str:
        """Generate human-readable reasoning for the quality score."""
        reasons = []
        
        if score >= 80:
            reasons.append("High quality content")
        elif score >= 65:
            reasons.append("Good quality content")
        elif score >= 45:
            reasons.append("Moderate quality content")
        else:
            reasons.append("Lower quality content")
        
        # Add specific quality indicators
        url = result.get('url', '').lower()
        for domain in self.config['authority_domains']:
            if domain in url:
                reasons.append(f"Authoritative source ({domain})")
                break
        
        snippet = result.get('snippet', result.get('description', ''))
        if len(snippet) > 200:
            reasons.append("Substantial content")
        
        # Check for quality keywords
        quality_matches = [kw for kw in self.config['quality_keywords'] 
                          if kw.lower() in snippet.lower()]
        if quality_matches:
            reasons.append(f"Quality indicators: {', '.join(quality_matches[:3])}")
        
        # Check for spam indicators
        spam_matches = [ind for ind in self.config['spam_indicators'] 
                       if ind.lower() in (result.get('title', '') + ' ' + snippet).lower()]
        if spam_matches:
            reasons.append(f"Potential spam indicators detected")
        
        return "; ".join(reasons)
    
    def _get_quality_breakdown(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed quality breakdown for debugging."""
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        
        return {
            'title_length': len(title),
            'snippet_length': len(snippet),
            'url_length': len(url),
            'has_https': url.startswith('https://'),
            'authority_domain': any(domain in url.lower() for domain in self.config['authority_domains']),
            'quality_keywords': [kw for kw in self.config['quality_keywords'] 
                               if kw.lower() in snippet.lower()],
            'spam_indicators': [ind for ind in self.config['spam_indicators'] 
                              if ind.lower() in (title + ' ' + snippet).lower()],
            'content_depth_score': self._analyze_content_depth(result),
            'authority_score': self._analyze_authority_signals(result),
            'technical_score': self._analyze_technical_quality(result),
            'spam_score': self._detect_spam_indicators(result),
            'freshness_score': self._analyze_freshness(result)
        }