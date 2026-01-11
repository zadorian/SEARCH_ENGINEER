"""
Scoring Engine

Advanced scoring algorithms that calculate individual factor scores for
relevance, quality, authority, and freshness components of the ranking system.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
import time
from datetime import datetime
from pathlib import Path
import sys
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Calculates individual factor scores for comprehensive result ranking.
    Provides detailed scoring for relevance, quality, authority, and freshness.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ScoringEngine.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.ScoringEngine")
        
        # Default configuration
        self.default_config = {
            # Relevance scoring configuration
            'relevance_config': {
                'title_weight': 0.4,
                'snippet_weight': 0.3,
                'url_weight': 0.1,
                'keyword_density_weight': 0.2,
                'exact_match_bonus': 20.0,
                'partial_match_bonus': 10.0,
                'early_position_bonus': 15.0
            },
            
            # Quality scoring configuration
            'quality_config': {
                'content_depth_weight': 0.3,
                'structure_quality_weight': 0.25,
                'language_quality_weight': 0.2,
                'metadata_quality_weight': 0.15,
                'technical_quality_weight': 0.1,
                'min_content_length': 50,
                'optimal_content_length': 300
            },
            
            # Authority scoring configuration
            'authority_config': {
                'domain_authority_weight': 0.4,
                'source_credibility_weight': 0.3,
                'backlink_indicators_weight': 0.2,
                'social_signals_weight': 0.1,
                'high_authority_domains': [
                    '.edu', '.gov', '.org', 'wikipedia.org', 'arxiv.org',
                    'nature.com', 'science.org', 'ieee.org'
                ],
                'medium_authority_domains': [
                    'github.com', 'stackoverflow.com', 'medium.com',
                    'reuters.com', 'bbc.com', 'nytimes.com'
                ]
            },
            
            # Freshness scoring configuration
            'freshness_config': {
                'date_analysis_weight': 0.4,
                'update_indicators_weight': 0.3,
                'version_indicators_weight': 0.2,
                'temporal_relevance_weight': 0.1,
                'current_year': datetime.now().year,
                'freshness_decay_months': 12,
                'version_keywords': ['v', 'version', 'update', 'revision', 'release']
            },
            
            # Advanced scoring features
            'advanced_features': {
                'semantic_similarity': False,  # Requires external libraries
                'entity_recognition': False,   # Requires external libraries
                'sentiment_analysis': False,   # Requires external libraries
                'readability_analysis': True,
                'multimedia_content_bonus': True,
                'interactive_content_bonus': True
            }
        }
        
        # Merge configurations
        self.config = {**self.default_config, **self.config}
        
        self.logger.debug("ScoringEngine initialized with advanced scoring algorithms")
    
    async def calculate_factor_scores(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Calculate individual factor scores for a result.
        
        Args:
            result: Combined result data
            context: Scoring context
            
        Returns:
            Dictionary with individual factor scores
        """
        scores = {}
        
        try:
            # Calculate each factor score
            scores['relevance'] = await self._calculate_relevance_score(result, context)
            scores['quality'] = await self._calculate_quality_score(result, context)
            scores['authority'] = await self._calculate_authority_score(result, context)
            scores['freshness'] = await self._calculate_freshness_score(result, context)
            
            # Calculate additional factors if enabled
            if self.config['advanced_features']['readability_analysis']:
                scores['readability'] = await self._calculate_readability_score(result)
            
            if self.config['advanced_features']['multimedia_content_bonus']:
                scores['multimedia_bonus'] = await self._calculate_multimedia_bonus(result)
            
            self.logger.debug(
                f"Calculated factor scores: relevance={scores['relevance']:.1f}, "
                f"quality={scores['quality']:.1f}, authority={scores['authority']:.1f}, "
                f"freshness={scores['freshness']:.1f}"
            )
            
        except Exception as e:
            self.logger.warning(f"Error calculating factor scores: {e}")
            # Return neutral scores on error
            scores = {
                'relevance': 50.0,
                'quality': 50.0,
                'authority': 50.0,
                'freshness': 50.0
            }
        
        return scores
    
    async def _calculate_relevance_score(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate relevance score based on query-content matching."""
        relevance_config = self.config['relevance_config']
        query = context.get('query', '').lower()
        
        if not query:
            return 50.0  # Neutral score if no query
        
        # Extract text fields
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        url = result.get('url', '').lower()
        
        # Prepare query terms
        query_terms = self._extract_query_terms(query)
        
        scores = {}
        
        # Title relevance
        scores['title'] = self._calculate_text_relevance(
            title, query_terms, query
        ) * relevance_config['title_weight']
        
        # Snippet relevance
        scores['snippet'] = self._calculate_text_relevance(
            snippet, query_terms, query
        ) * relevance_config['snippet_weight']
        
        # URL relevance
        scores['url'] = self._calculate_text_relevance(
            url, query_terms, query
        ) * relevance_config['url_weight']
        
        # Keyword density
        combined_text = f"{title} {snippet}"
        scores['keyword_density'] = self._calculate_keyword_density(
            combined_text, query_terms
        ) * relevance_config['keyword_density_weight']
        
        base_score = sum(scores.values())
        
        # Apply bonuses
        
        # Exact match bonus
        if query in title or query in snippet:
            base_score += relevance_config['exact_match_bonus']
        
        # Partial match bonus
        elif any(term in title for term in query_terms):
            base_score += relevance_config['partial_match_bonus']
        
        # Early position bonus (for query terms appearing early in text)
        early_bonus = self._calculate_early_position_bonus(
            combined_text, query_terms
        )
        base_score += early_bonus * relevance_config['early_position_bonus'] / 100
        
        return min(100.0, max(0.0, base_score))
    
    def _extract_query_terms(self, query: str) -> List[str]:
        """Extract meaningful terms from query."""
        # Remove quotes and special characters
        cleaned_query = re.sub(r'[^\w\s]', ' ', query)
        terms = cleaned_query.split()
        
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be'
        }
        
        return [term for term in terms if term.lower() not in stop_words and len(term) > 2]
    
    def _calculate_text_relevance(
        self,
        text: str,
        query_terms: List[str],
        full_query: str
    ) -> float:
        """Calculate relevance of text to query terms."""
        if not text or not query_terms:
            return 0.0
        
        # Exact phrase match
        if full_query in text:
            return 100.0
        
        # Term matching
        matched_terms = sum(1 for term in query_terms if term in text)
        term_ratio = matched_terms / len(query_terms)
        
        # Position bonus for matches at start of text
        position_bonus = 0.0
        words = text.split()[:10]  # First 10 words
        early_matches = sum(1 for word in words if any(term in word for term in query_terms))
        if early_matches > 0:
            position_bonus = (early_matches / min(len(words), len(query_terms))) * 20
        
        base_score = (term_ratio * 80) + position_bonus
        
        return min(100.0, base_score)
    
    def _calculate_keyword_density(self, text: str, query_terms: List[str]) -> float:
        """Calculate keyword density score."""
        if not text or not query_terms:
            return 0.0
        
        words = text.split()
        if not words:
            return 0.0
        
        # Count query term occurrences
        term_count = sum(1 for word in words if any(term in word.lower() for term in query_terms))
        
        # Calculate density
        density = term_count / len(words)
        
        # Optimal density is around 2-5%
        if 0.02 <= density <= 0.05:
            return 100.0
        elif density < 0.02:
            return (density / 0.02) * 100
        else:
            # Penalize over-optimization
            return max(20.0, 100.0 - (density - 0.05) * 1000)
    
    def _calculate_early_position_bonus(self, text: str, query_terms: List[str]) -> float:
        """Calculate bonus for query terms appearing early in text."""
        words = text.split()
        if not words or not query_terms:
            return 0.0
        
        # Check first 20 words
        early_words = words[:20]
        
        bonus = 0.0
        for i, word in enumerate(early_words):
            if any(term in word.lower() for term in query_terms):
                # Higher bonus for earlier positions
                position_bonus = (20 - i) / 20 * 100
                bonus = max(bonus, position_bonus)
        
        return bonus
    
    async def _calculate_quality_score(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate content quality score."""
        quality_config = self.config['quality_config']
        
        scores = {}
        
        # Content depth analysis
        scores['content_depth'] = self._analyze_content_depth(
            result
        ) * quality_config['content_depth_weight']
        
        # Structure quality
        scores['structure'] = self._analyze_structure_quality(
            result
        ) * quality_config['structure_quality_weight']
        
        # Language quality
        scores['language'] = self._analyze_language_quality(
            result
        ) * quality_config['language_quality_weight']
        
        # Metadata quality
        scores['metadata'] = self._analyze_metadata_quality(
            result
        ) * quality_config['metadata_quality_weight']
        
        # Technical quality
        scores['technical'] = self._analyze_technical_quality(
            result
        ) * quality_config['technical_quality_weight']
        
        return min(100.0, max(0.0, sum(scores.values())))
    
    def _analyze_content_depth(self, result: Dict[str, Any]) -> float:
        """Analyze content depth and substance."""
        snippet = result.get('snippet', '')
        title = result.get('title', '')
        
        score = 30.0  # Base score
        
        # Length analysis
        min_length = self.config['quality_config']['min_content_length']
        optimal_length = self.config['quality_config']['optimal_content_length']
        
        if len(snippet) >= optimal_length:
            score += 40.0
        elif len(snippet) >= min_length:
            length_ratio = len(snippet) / optimal_length
            score += length_ratio * 40.0
        
        # Content indicators
        depth_indicators = [
            'detailed', 'comprehensive', 'thorough', 'complete',
            'analysis', 'research', 'study', 'investigation',
            'explanation', 'description', 'overview'
        ]
        
        combined_text = f"{title} {snippet}".lower()
        indicator_matches = sum(1 for indicator in depth_indicators 
                               if indicator in combined_text)
        score += min(20.0, indicator_matches * 5.0)
        
        # Sentence structure
        sentences = snippet.split('.')
        if len(sentences) > 2:
            score += 10.0
        
        return min(100.0, score)
    
    def _analyze_structure_quality(self, result: Dict[str, Any]) -> float:
        """Analyze content structure and organization."""
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        
        score = 40.0  # Base score
        
        # Title quality
        if title:
            if 20 <= len(title) <= 100:  # Optimal title length
                score += 15.0
            
            if title[0].isupper() and not title.isupper():  # Proper capitalization
                score += 10.0
            
            if not title.endswith('...'):  # Not truncated
                score += 5.0
        
        # Content structure
        if snippet:
            # Proper punctuation
            if snippet.strip().endswith(('.', '!', '?')):
                score += 10.0
            
            # Paragraph breaks
            if '\n' in snippet or '  ' in snippet:
                score += 10.0
            
            # Bullet points or lists
            if any(indicator in snippet for indicator in ['•', '◦', '1.', '2.', '-']):
                score += 10.0
        
        return min(100.0, score)
    
    def _analyze_language_quality(self, result: Dict[str, Any]) -> float:
        """Analyze language quality and readability."""
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        combined_text = f"{title} {snippet}"
        
        score = 50.0  # Base score
        
        if not combined_text:
            return score
        
        # Word diversity
        words = combined_text.lower().split()
        if words:
            unique_words = len(set(words))
            diversity_ratio = unique_words / len(words)
            score += diversity_ratio * 20.0
        
        # Grammar indicators (simplified)
        # Proper sentence structure
        sentences = [s.strip() for s in combined_text.split('.') if s.strip()]
        if sentences:
            avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
            if 8 <= avg_sentence_length <= 25:  # Optimal sentence length
                score += 15.0
        
        # Spelling quality (basic check for obvious errors)
        error_indicators = ['teh', 'recieve', 'occured', 'seperate', 'definately']
        if not any(error in combined_text.lower() for error in error_indicators):
            score += 15.0
        
        return min(100.0, score)
    
    def _analyze_metadata_quality(self, result: Dict[str, Any]) -> float:
        """Analyze metadata quality and completeness."""
        score = 40.0  # Base score
        
        # Check for essential metadata
        if result.get('title'):
            score += 20.0
        
        if result.get('snippet') and len(result['snippet']) > 20:
            score += 20.0
        
        if result.get('url'):
            score += 10.0
        
        if result.get('source'):
            score += 10.0
        
        return min(100.0, score)
    
    def _analyze_technical_quality(self, result: Dict[str, Any]) -> float:
        """Analyze technical quality indicators."""
        url = result.get('url', '')
        
        score = 50.0  # Base score
        
        # HTTPS check
        if url.startswith('https://'):
            score += 20.0
        
        # Clean URL structure
        if '?' not in url or url.count('&') <= 2:
            score += 15.0
        
        # No excessive parameters
        if url.count('=') <= 3:
            score += 15.0
        
        return min(100.0, score)
    
    async def _calculate_authority_score(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate authority and credibility score."""
        authority_config = self.config['authority_config']
        url = result.get('url', '').lower()
        
        scores = {}
        
        # Domain authority
        scores['domain'] = self._analyze_domain_authority(
            url
        ) * authority_config['domain_authority_weight']
        
        # Source credibility
        scores['credibility'] = self._analyze_source_credibility(
            result
        ) * authority_config['source_credibility_weight']
        
        # Backlink indicators (simplified)
        scores['backlinks'] = self._analyze_backlink_indicators(
            result
        ) * authority_config['backlink_indicators_weight']
        
        # Social signals (simplified)
        scores['social'] = self._analyze_social_signals(
            result
        ) * authority_config['social_signals_weight']
        
        return min(100.0, max(0.0, sum(scores.values())))
    
    def _analyze_domain_authority(self, url: str) -> float:
        """Analyze domain authority indicators."""
        authority_config = self.config['authority_config']
        
        score = 40.0  # Base score
        
        # High authority domains
        for domain in authority_config['high_authority_domains']:
            if domain in url:
                return 95.0
        
        # Medium authority domains
        for domain in authority_config['medium_authority_domains']:
            if domain in url:
                return 75.0
        
        # TLD analysis
        if '.edu' in url or '.gov' in url:
            score = 90.0
        elif '.org' in url:
            score = 65.0
        elif '.com' in url:
            score = 50.0
        
        return score
    
    def _analyze_source_credibility(self, result: Dict[str, Any]) -> float:
        """Analyze source credibility indicators."""
        source = result.get('source', '').lower()
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        
        score = 50.0  # Base score
        
        # Known credible sources
        credible_sources = [
            'reuters', 'ap', 'bbc', 'cnn', 'npr', 'pbs',
            'nature', 'science', 'ieee', 'acm'
        ]
        
        if any(source_name in source for source_name in credible_sources):
            score += 30.0
        
        # Author indicators
        author_indicators = ['by ', 'author:', 'written by', 'published by']
        if any(indicator in snippet for indicator in author_indicators):
            score += 10.0
        
        # Publication indicators
        pub_indicators = ['published', 'journal', 'research', 'study']
        if any(indicator in snippet for indicator in pub_indicators):
            score += 10.0
        
        return min(100.0, score)
    
    def _analyze_backlink_indicators(self, result: Dict[str, Any]) -> float:
        """Analyze backlink and citation indicators."""
        snippet = result.get('snippet', '').lower()
        
        score = 50.0  # Base score
        
        # Citation indicators
        citation_indicators = ['cited by', 'references', 'bibliography', 'doi:']
        if any(indicator in snippet for indicator in citation_indicators):
            score += 20.0
        
        # Academic indicators
        academic_indicators = ['abstract', 'peer reviewed', 'journal']
        if any(indicator in snippet for indicator in academic_indicators):
            score += 15.0
        
        return min(100.0, score)
    
    def _analyze_social_signals(self, result: Dict[str, Any]) -> float:
        """Analyze social media and sharing indicators."""
        snippet = result.get('snippet', '').lower()
        
        score = 50.0  # Base score
        
        # Social indicators
        social_indicators = ['shares', 'likes', 'comments', 'trending', 'viral']
        if any(indicator in snippet for indicator in social_indicators):
            score += 20.0
        
        # Community indicators
        community_indicators = ['discussion', 'forum', 'community', 'reviews']
        if any(indicator in snippet for indicator in community_indicators):
            score += 10.0
        
        return min(100.0, score)
    
    async def _calculate_freshness_score(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate content freshness and recency score."""
        freshness_config = self.config['freshness_config']
        
        scores = {}
        
        # Date analysis
        scores['date'] = self._analyze_date_freshness(
            result
        ) * freshness_config['date_analysis_weight']
        
        # Update indicators
        scores['updates'] = self._analyze_update_indicators(
            result
        ) * freshness_config['update_indicators_weight']
        
        # Version indicators
        scores['versions'] = self._analyze_version_indicators(
            result
        ) * freshness_config['version_indicators_weight']
        
        # Temporal relevance
        scores['temporal'] = self._analyze_temporal_relevance(
            result, context
        ) * freshness_config['temporal_relevance_weight']
        
        return min(100.0, max(0.0, sum(scores.values())))
    
    def _analyze_date_freshness(self, result: Dict[str, Any]) -> float:
        """Analyze date-based freshness indicators."""
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        url = result.get('url', '')
        combined_text = f"{title} {snippet} {url}"
        
        current_year = self.config['freshness_config']['current_year']
        
        score = 50.0  # Base score
        
        # Look for years in content
        years = re.findall(r'\b(20\d{2})\b', combined_text)
        
        if years:
            latest_year = max(int(year) for year in years)
            year_diff = current_year - latest_year
            
            if year_diff == 0:
                score = 100.0  # Current year
            elif year_diff == 1:
                score = 85.0   # Last year
            elif year_diff <= 2:
                score = 70.0   # Within 2 years
            elif year_diff <= 5:
                score = 50.0   # Within 5 years
            else:
                score = 30.0   # Older content
        
        return score
    
    def _analyze_update_indicators(self, result: Dict[str, Any]) -> float:
        """Analyze update and modification indicators."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        combined_text = f"{title} {snippet}"
        
        score = 40.0  # Base score
        
        # Update keywords
        update_keywords = [
            'updated', 'revised', 'modified', 'latest', 'current',
            'recent', 'new', 'fresh', 'live', 'real-time'
        ]
        
        update_matches = sum(1 for keyword in update_keywords if keyword in combined_text)
        score += min(30.0, update_matches * 10.0)
        
        # Time indicators
        time_indicators = ['today', 'yesterday', 'this week', 'this month']
        if any(indicator in combined_text for indicator in time_indicators):
            score += 30.0
        
        return min(100.0, score)
    
    def _analyze_version_indicators(self, result: Dict[str, Any]) -> float:
        """Analyze version and release indicators."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        combined_text = f"{title} {snippet}"
        
        score = 50.0  # Base score
        
        version_keywords = self.config['freshness_config']['version_keywords']
        
        # Version patterns
        version_patterns = [
            r'v\d+\.\d+', r'version\s+\d+', r'\d+\.\d+\.\d+',
            r'release\s+\d+', r'build\s+\d+'
        ]
        
        for pattern in version_patterns:
            if re.search(pattern, combined_text):
                score += 15.0
                break
        
        # Version keywords
        if any(keyword in combined_text for keyword in version_keywords):
            score += 10.0
        
        return min(100.0, score)
    
    def _analyze_temporal_relevance(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Analyze temporal relevance to query context."""
        score = 60.0  # Base score
        
        # This is a simplified implementation
        # In practice, you'd analyze query for temporal intent
        # and match against result temporal characteristics
        
        query = context.get('query', '').lower()
        
        # Check for temporal query terms
        temporal_terms = [
            'recent', 'latest', 'current', 'new', 'today',
            'this year', 'modern', 'contemporary'
        ]
        
        if any(term in query for term in temporal_terms):
            # Query has temporal intent - boost fresh content
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            combined_text = f"{title} {snippet}"
            
            if any(term in combined_text for term in temporal_terms):
                score += 25.0
        
        return min(100.0, score)
    
    async def _calculate_readability_score(self, result: Dict[str, Any]) -> float:
        """Calculate readability score (simplified implementation)."""
        snippet = result.get('snippet', '')
        
        if not snippet:
            return 50.0
        
        score = 50.0  # Base score
        
        # Sentence length analysis
        sentences = [s.strip() for s in snippet.split('.') if s.strip()]
        if sentences:
            avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
            
            # Optimal sentence length: 10-20 words
            if 10 <= avg_sentence_length <= 20:
                score += 20.0
            elif avg_sentence_length < 10:
                score += 10.0  # Short sentences are okay
            else:
                # Penalty for very long sentences
                score -= min(20.0, (avg_sentence_length - 20) * 2)
        
        # Word complexity (simplified)
        words = snippet.split()
        if words:
            long_words = sum(1 for word in words if len(word) > 12)
            complexity_ratio = long_words / len(words)
            
            if complexity_ratio < 0.1:  # Less than 10% complex words
                score += 15.0
            elif complexity_ratio > 0.3:  # More than 30% complex words
                score -= 15.0
        
        return min(100.0, max(0.0, score))
    
    async def _calculate_multimedia_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate bonus for multimedia content."""
        snippet = result.get('snippet', '').lower()
        url = result.get('url', '').lower()
        
        bonus = 0.0
        
        # Image indicators
        image_indicators = ['image', 'photo', 'picture', 'screenshot', 'diagram']
        if any(indicator in snippet for indicator in image_indicators):
            bonus += 3.0
        
        # Video indicators
        video_indicators = ['video', 'watch', 'movie', 'film', 'youtube']
        if any(indicator in snippet for indicator in video_indicators):
            bonus += 5.0
        
        # Interactive content
        interactive_indicators = ['interactive', 'demo', 'tool', 'calculator', 'simulator']
        if any(indicator in snippet for indicator in interactive_indicators):
            bonus += 4.0
        
        # File type bonuses
        if any(ext in url for ext in ['.pdf', '.doc', '.ppt']):
            bonus += 2.0
        
        return min(10.0, bonus)  # Cap at 10 points