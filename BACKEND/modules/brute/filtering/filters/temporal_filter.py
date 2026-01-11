"""
Temporal Filter

Analyzes temporal relevance of search results based on date indicators,
freshness requirements, and time-based content matching.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
import time
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class TemporalFilter(BaseFilter):
    """
    Filter that analyzes temporal relevance based on date indicators,
    content freshness, and time-based query requirements.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize TemporalFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("TemporalFilter", config)
        
        # Default configuration
        self.default_config = {
            'date_matching_weight': 0.4,        # Weight for direct date matching
            'freshness_weight': 0.3,            # Weight for content freshness
            'temporal_context_weight': 0.2,     # Weight for temporal context
            'recency_preference_weight': 0.1,   # Weight for recency preferences
            'min_temporal_score': 25.0,         # Minimum score to not filter
            'strict_date_matching': False,      # Require exact date matches
            'freshness_decay_days': 365,        # Days after which content starts decaying
            'boost_recent_content': True,       # Boost recently published content
            'current_year': datetime.now().year, # Current year for calculations
            
            # Date patterns and formats
            'date_patterns': [
                # ISO format
                r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',
                # US format
                r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
                # European format
                r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b',
                # Long format
                r'\b(\w+)\s+(\d{1,2}),?\s+(\d{4})\b',
                # Year only
                r'\b(\d{4})\b',
                # Month year
                r'\b(\w+)\s+(\d{4})\b'
            ],
            
            # Temporal keywords
            'temporal_keywords': {
                'recent': ['recent', 'latest', 'new', 'current', 'updated', 'fresh'],
                'past': ['historical', 'archive', 'old', 'vintage', 'classic', 'legacy'],
                'future': ['upcoming', 'planned', 'future', 'scheduled', 'forecast'],
                'specific_time': ['today', 'yesterday', 'this week', 'this month', 
                                'this year', 'last week', 'last month', 'last year'],
                'urgency': ['breaking', 'urgent', 'immediate', 'now', 'live'],
                'timeline': ['before', 'after', 'during', 'since', 'until', 'between']
            },
            
            # Month name mappings
            'month_names': {
                'january': 1, 'jan': 1, 'february': 2, 'feb': 2,
                'march': 3, 'mar': 3, 'april': 4, 'apr': 4,
                'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
                'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
                'october': 10, 'oct': 10, 'november': 11, 'nov': 11,
                'december': 12, 'dec': 12
            },
            
            # Content type freshness requirements
            'content_freshness_requirements': {
                'news': {'max_age_days': 30, 'optimal_age_days': 7},
                'technology': {'max_age_days': 180, 'optimal_age_days': 90},
                'academic': {'max_age_days': 1095, 'optimal_age_days': 365},  # 3 years
                'reference': {'max_age_days': 1825, 'optimal_age_days': 730}, # 5 years
                'general': {'max_age_days': 730, 'optimal_age_days': 365}     # 2 years
            },
            
            # Date operator patterns (from Search_Engineer operators)
            'date_operators': {
                'year_only': r'(\d{4})!',
                'year_range': r'(\d{4})\s*-\s*(\d{4})!',
                'before_year': r'<-\s*(\d{4})!',
                'after_year': r'(\d{4})\s*->!',
                'specific_date': r'(\d{1,2})\s+(\w+)\s+(\d{4})!'
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"TemporalFilter initialized for year {self.config['current_year']}")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on temporal relevance.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with temporal scores
        """
        if not results:
            return []
        
        filter_results = []
        
        # Extract temporal intent from query and context
        temporal_intent = self._extract_temporal_intent(context.query, context.query_context)
        
        self.logger.debug(
            f"Analyzing temporal relevance for {len(results)} results "
            f"with temporal intent: {temporal_intent}"
        )
        
        for i, result in enumerate(results):
            try:
                # Calculate temporal score
                temporal_score = await self._calculate_temporal_score(
                    result, context, temporal_intent
                )
                
                # Determine tier and classification
                tier, classification = self._classify_result(temporal_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(result, temporal_score, temporal_intent)
                
                # Get detailed temporal analysis
                temporal_analysis = self._get_temporal_analysis(result, temporal_intent)
                
                filter_result = FilterResult(
                    result_id=f"temporal_{i}",
                    score=temporal_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'temporal_analysis': temporal_analysis,
                        'temporal_intent': temporal_intent,
                        'filter': 'temporal'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                filter_results.append(self._create_error_result(i, str(e)))
        
        avg_score = sum(fr.score for fr in filter_results) / len(filter_results)
        self.logger.debug(f"TemporalFilter processed {len(results)} results, average score: {avg_score:.1f}")
        
        return filter_results
    
    def _extract_temporal_intent(
        self,
        query: str,
        query_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract temporal intent from query and context.
        
        Args:
            query: Search query
            query_context: Additional query context
            
        Returns:
            Dictionary with temporal intent analysis
        """
        intent = {
            'has_temporal_intent': False,
            'temporal_type': None,  # 'specific', 'recent', 'range', 'relative'
            'date_constraints': {},
            'freshness_preference': 'medium',  # 'high', 'medium', 'low'
            'temporal_keywords': [],
            'content_type': 'general'
        }
        
        query_lower = query.lower()
        
        # Check for date operators from Search_Engineer system
        for operator, pattern in self.config['date_operators'].items():
            match = re.search(pattern, query)
            if match:
                intent['has_temporal_intent'] = True
                intent['temporal_type'] = 'specific'
                
                if operator == 'year_only':
                    intent['date_constraints'] = {
                        'year': int(match.group(1)),
                        'operator': 'year_only'
                    }
                elif operator == 'year_range':
                    intent['date_constraints'] = {
                        'start_year': int(match.group(1)),
                        'end_year': int(match.group(2)),
                        'operator': 'year_range'
                    }
                elif operator == 'before_year':
                    intent['date_constraints'] = {
                        'before_year': int(match.group(1)),
                        'operator': 'before'
                    }
                elif operator == 'after_year':
                    intent['date_constraints'] = {
                        'after_year': int(match.group(1)),
                        'operator': 'after'
                    }
                break
        
        # Check for temporal keywords
        for category, keywords in self.config['temporal_keywords'].items():
            found_keywords = [kw for kw in keywords if kw in query_lower]
            if found_keywords:
                intent['has_temporal_intent'] = True
                intent['temporal_keywords'].extend(found_keywords)
                
                if category == 'recent':
                    intent['temporal_type'] = 'recent'
                    intent['freshness_preference'] = 'high'
                elif category == 'urgency':
                    intent['temporal_type'] = 'urgent'
                    intent['freshness_preference'] = 'high'
                elif category == 'specific_time':
                    intent['temporal_type'] = 'relative'
        
        # Extract dates from query text
        extracted_dates = self._extract_dates_from_text(query)
        if extracted_dates:
            intent['has_temporal_intent'] = True
            intent['temporal_type'] = 'specific'
            intent['date_constraints'].update(extracted_dates)
        
        # Infer content type for freshness requirements
        content_indicators = {
            'news': ['news', 'breaking', 'report', 'announcement'],
            'technology': ['tech', 'software', 'api', 'framework', 'tool'],
            'academic': ['research', 'study', 'paper', 'journal', 'academic'],
            'reference': ['documentation', 'manual', 'guide', 'specification']
        }
        
        for content_type, indicators in content_indicators.items():
            if any(indicator in query_lower for indicator in indicators):
                intent['content_type'] = content_type
                break
        
        # Check query context for additional temporal info
        if 'date' in query_context:
            intent['has_temporal_intent'] = True
            intent['date_constraints'].update(query_context['date'])
        
        return intent
    
    def _extract_dates_from_text(self, text: str) -> Dict[str, Any]:
        """Extract dates from text using pattern matching."""
        dates = {}
        
        for pattern in self.config['date_patterns']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                groups = match.groups()
                
                try:
                    if len(groups) == 1 and groups[0].isdigit():
                        # Year only
                        year = int(groups[0])
                        if 1900 <= year <= 2030:  # Reasonable year range
                            dates['year'] = year
                    
                    elif len(groups) == 2:
                        # Month year format
                        month_str, year_str = groups
                        if month_str.lower() in self.config['month_names']:
                            month = self.config['month_names'][month_str.lower()]
                            year = int(year_str)
                            dates.update({'year': year, 'month': month})
                    
                    elif len(groups) == 3:
                        # Full date formats
                        if groups[0].isdigit() and groups[1].isdigit() and groups[2].isdigit():
                            # Numeric date
                            dates.update({
                                'year': int(groups[2]),
                                'month': int(groups[1]),
                                'day': int(groups[0])
                            })
                        else:
                            # Text month format
                            month_str = groups[0].lower()
                            if month_str in self.config['month_names']:
                                dates.update({
                                    'month': self.config['month_names'][month_str],
                                    'day': int(groups[1]),
                                    'year': int(groups[2])
                                })
                except (ValueError, KeyError):
                    continue
        
        return dates
    
    async def _calculate_temporal_score(
        self,
        result: Dict[str, Any],
        context: FilterContext,
        temporal_intent: Dict[str, Any]
    ) -> float:
        """
        Calculate comprehensive temporal relevance score.
        
        Args:
            result: Search result to analyze
            context: Filtering context
            temporal_intent: Extracted temporal intent
            
        Returns:
            Temporal score (0-100)
        """
        # If no temporal intent, return neutral score
        if not temporal_intent['has_temporal_intent']:
            return 60.0  # Neutral score for non-temporal searches
        
        scores = {}
        
        # 1. Date matching analysis
        scores['date_matching'] = self._analyze_date_matching(
            result, temporal_intent
        ) * self.config['date_matching_weight']
        
        # 2. Content freshness analysis
        scores['freshness'] = self._analyze_content_freshness(
            result, temporal_intent
        ) * self.config['freshness_weight']
        
        # 3. Temporal context analysis
        scores['temporal_context'] = self._analyze_temporal_context(
            result, temporal_intent
        ) * self.config['temporal_context_weight']
        
        # 4. Recency preference analysis
        scores['recency_preference'] = self._analyze_recency_preference(
            result, temporal_intent
        ) * self.config['recency_preference_weight']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Apply recency boost if configured
        if self.config['boost_recent_content'] and temporal_intent['freshness_preference'] == 'high':
            total_score *= 1.15  # 15% boost for high freshness preference
        
        # Normalize to 0-100 range
        temporal_score = min(100.0, max(0.0, total_score))
        
        return temporal_score
    
    def _analyze_date_matching(
        self,
        result: Dict[str, Any],
        temporal_intent: Dict[str, Any]
    ) -> float:
        """Analyze direct date matching in content."""
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        combined_text = f"{title} {snippet} {url}"
        
        score = 40.0  # Base score for temporal queries
        
        date_constraints = temporal_intent.get('date_constraints', {})
        if not date_constraints:
            return score
        
        # Extract dates from result content
        content_dates = self._extract_dates_from_text(combined_text)
        
        if not content_dates:
            return score
        
        # Check specific date constraints
        if 'year' in date_constraints:
            target_year = date_constraints['year']
            
            if 'year' in content_dates:
                content_year = content_dates['year']
                
                if content_year == target_year:
                    score += 40.0  # Exact year match
                elif abs(content_year - target_year) <= 1:
                    score += 25.0  # Within 1 year
                elif abs(content_year - target_year) <= 2:
                    score += 15.0  # Within 2 years
        
        # Check year range constraints
        if 'start_year' in date_constraints and 'end_year' in date_constraints:
            start_year = date_constraints['start_year']
            end_year = date_constraints['end_year']
            
            if 'year' in content_dates:
                content_year = content_dates['year']
                if start_year <= content_year <= end_year:
                    score += 35.0  # Within range
        
        # Check before/after constraints
        if 'before_year' in date_constraints:
            before_year = date_constraints['before_year']
            if 'year' in content_dates and content_dates['year'] < before_year:
                score += 30.0
        
        if 'after_year' in date_constraints:
            after_year = date_constraints['after_year']
            if 'year' in content_dates and content_dates['year'] > after_year:
                score += 30.0
        
        return min(100.0, score)
    
    def _analyze_content_freshness(
        self,
        result: Dict[str, Any],
        temporal_intent: Dict[str, Any]
    ) -> float:
        """Analyze content freshness based on content type and age indicators."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        url = result.get('url', '').lower()
        combined_text = f"{title} {snippet}"
        
        score = 50.0  # Base score
        
        content_type = temporal_intent.get('content_type', 'general')
        freshness_req = self.config['content_freshness_requirements'].get(
            content_type, self.config['content_freshness_requirements']['general']
        )
        
        # Look for freshness indicators
        freshness_indicators = {
            'very_fresh': ['today', 'breaking', 'live', 'just published', 'minutes ago'],
            'fresh': ['yesterday', 'this week', 'recent', 'latest', 'updated'],
            'moderate': ['this month', 'this year', 'new'],
            'stale': ['archived', 'historical', 'old', 'vintage', 'legacy']
        }
        
        for freshness_level, indicators in freshness_indicators.items():
            if any(indicator in combined_text for indicator in indicators):
                if freshness_level == 'very_fresh':
                    score += 30.0
                elif freshness_level == 'fresh':
                    score += 20.0
                elif freshness_level == 'moderate':
                    score += 10.0
                elif freshness_level == 'stale':
                    score -= 20.0
                break
        
        # Check for version numbers (indicating updates)
        version_patterns = [
            r'v\d+\.\d+', r'version\s+\d+', r'\d+\.\d+\.\d+',
            r'update\s+\d+', r'revision\s+\d+'
        ]
        
        for pattern in version_patterns:
            if re.search(pattern, combined_text):
                score += 10.0
                break
        
        # Check URL for date indicators
        current_year = self.config['current_year']
        if str(current_year) in url or str(current_year - 1) in url:
            score += 15.0
        elif any(str(year) in url for year in range(current_year - 3, current_year - 1)):
            score += 5.0
        
        return min(100.0, score)
    
    def _analyze_temporal_context(
        self,
        result: Dict[str, Any],
        temporal_intent: Dict[str, Any]
    ) -> float:
        """Analyze temporal context and relevance."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        combined_text = f"{title} {snippet}"
        
        score = 50.0  # Base score
        
        temporal_keywords = temporal_intent.get('temporal_keywords', [])
        
        # Check for matching temporal keywords in content
        keyword_matches = 0
        for keyword in temporal_keywords:
            if keyword in combined_text:
                keyword_matches += 1
        
        if keyword_matches > 0:
            score += keyword_matches * 10.0
        
        # Check for temporal context indicators
        temporal_context_indicators = [
            'timeline', 'chronology', 'history', 'evolution', 'development',
            'progression', 'sequence', 'period', 'era', 'phase'
        ]
        
        context_matches = sum(1 for indicator in temporal_context_indicators 
                            if indicator in combined_text)
        score += context_matches * 5.0
        
        # Check for specific time references
        time_references = [
            'morning', 'afternoon', 'evening', 'night',
            'weekend', 'weekday', 'monday', 'tuesday', 'wednesday',
            'thursday', 'friday', 'saturday', 'sunday'
        ]
        
        time_ref_matches = sum(1 for ref in time_references if ref in combined_text)
        score += time_ref_matches * 3.0
        
        return min(100.0, score)
    
    def _analyze_recency_preference(
        self,
        result: Dict[str, Any],
        temporal_intent: Dict[str, Any]
    ) -> float:
        """Analyze how well the result matches recency preferences."""
        score = 50.0  # Base score
        
        freshness_pref = temporal_intent.get('freshness_preference', 'medium')
        
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        combined_text = f"{title} {snippet}"
        
        if freshness_pref == 'high':
            # High freshness preference - boost recent content
            recent_indicators = ['2024', '2023', 'recent', 'latest', 'new', 'current']
            if any(indicator in combined_text for indicator in recent_indicators):
                score += 25.0
            
            # Penalty for old content
            old_indicators = ['2020', '2019', '2018', 'old', 'archived', 'historical']
            if any(indicator in combined_text for indicator in old_indicators):
                score -= 20.0
        
        elif freshness_pref == 'low':
            # Low freshness preference - neutral or favor established content
            established_indicators = ['established', 'proven', 'classic', 'traditional']
            if any(indicator in combined_text for indicator in established_indicators):
                score += 15.0
        
        return min(100.0, max(0.0, score))
    
    def _classify_result(self, temporal_score: float) -> tuple:
        """Classify result based on temporal score."""
        if temporal_score >= 85.0:
            return 1, 'primary'
        elif temporal_score >= 70.0:
            return 2, 'primary'
        elif temporal_score >= 50.0:
            return 3, 'secondary'
        elif temporal_score >= self.config['min_temporal_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out
    
    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        score: float,
        temporal_intent: Dict[str, Any]
    ) -> str:
        """Generate human-readable reasoning for the temporal score."""
        reasons = []
        
        if not temporal_intent['has_temporal_intent']:
            return "No temporal intent detected"
        
        if score >= 85:
            reasons.append("Excellent temporal relevance")
        elif score >= 70:
            reasons.append("Good temporal relevance")
        elif score >= 50:
            reasons.append("Moderate temporal relevance")
        else:
            reasons.append("Limited temporal relevance")
        
        # Add specific temporal matches
        date_constraints = temporal_intent.get('date_constraints', {})
        if 'year' in date_constraints:
            reasons.append(f"Target year: {date_constraints['year']}")
        
        temporal_keywords = temporal_intent.get('temporal_keywords', [])
        if temporal_keywords:
            reasons.append(f"Temporal keywords: {', '.join(temporal_keywords[:3])}")
        
        # Check for freshness indicators in content
        combined_text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
        
        freshness_indicators = ['recent', 'latest', 'new', 'updated', '2024', '2023']
        found_indicators = [ind for ind in freshness_indicators if ind in combined_text]
        
        if found_indicators:
            reasons.append(f"Freshness indicators: {', '.join(found_indicators[:2])}")
        
        return "; ".join(reasons)
    
    def _get_temporal_analysis(
        self,
        result: Dict[str, Any],
        temporal_intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get detailed temporal analysis for debugging."""
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        combined_text = f"{title} {snippet} {url}"
        
        # Extract dates from content
        content_dates = self._extract_dates_from_text(combined_text)
        
        return {
            'has_temporal_intent': temporal_intent['has_temporal_intent'],
            'temporal_type': temporal_intent.get('temporal_type'),
            'date_constraints': temporal_intent.get('date_constraints', {}),
            'freshness_preference': temporal_intent.get('freshness_preference'),
            'content_type': temporal_intent.get('content_type'),
            'extracted_dates': content_dates,
            'temporal_keywords_found': [
                kw for kw in temporal_intent.get('temporal_keywords', [])
                if kw in combined_text.lower()
            ],
            'freshness_indicators': [
                indicator for indicator in ['recent', 'latest', 'new', 'updated', 'current']
                if indicator in combined_text.lower()
            ],
            'year_in_url': bool(re.search(r'\b20\d{2}\b', url)),
            'current_year_mentioned': str(self.config['current_year']) in combined_text
        }
    
    def _create_error_result(self, index: int, error_msg: str) -> FilterResult:
        """Create result for processing errors."""
        return FilterResult(
            result_id=f"temporal_error_{index}",
            score=50.0,  # Neutral score for errors
            tier=3,
            classification='secondary',
            reasoning=f"Temporal analysis error: {error_msg}",
            metadata={'filter': 'temporal', 'error': True},
            processed_at=time.time()
        )