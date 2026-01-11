"""
Content Filter

Analyzes content type, format, and structure to ensure results match
expected content criteria and quality standards.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Set
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

class ContentFilter(BaseFilter):
    """
    Filter that analyzes content type, format, and structure to ensure
    results match expected content criteria and quality standards.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize ContentFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("ContentFilter", config)
        
        # Default configuration
        self.default_config = {
            'format_analysis_weight': 0.3,     # Weight for format/filetype analysis
            'structure_analysis_weight': 0.25, # Weight for content structure
            'completeness_weight': 0.25,       # Weight for content completeness
            'format_matching_weight': 0.2,     # Weight for format matching query intent
            'min_content_score': 20.0,         # Minimum score to not filter
            'strict_filetype_matching': False, # Require exact filetype matches
            
            # File type categories and extensions
            'filetype_categories': {
                'document': {
                    'extensions': ['.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt'],
                    'keywords': ['document', 'paper', 'report', 'manual', 'guide'],
                    'score_boost': 20.0
                },
                'spreadsheet': {
                    'extensions': ['.xls', '.xlsx', '.ods', '.csv'],
                    'keywords': ['spreadsheet', 'data', 'excel', 'csv', 'table'],
                    'score_boost': 15.0
                },
                'presentation': {
                    'extensions': ['.ppt', '.pptx', '.odp'],
                    'keywords': ['presentation', 'slides', 'powerpoint'],
                    'score_boost': 15.0
                },
                'code': {
                    'extensions': ['.py', '.js', '.java', '.cpp', '.c', '.cs', '.rb', '.go', '.php'],
                    'keywords': ['code', 'source', 'script', 'program', 'api'],
                    'score_boost': 20.0
                },
                'image': {
                    'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
                    'keywords': ['image', 'photo', 'picture', 'graphic', 'icon'],
                    'score_boost': 10.0
                },
                'archive': {
                    'extensions': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
                    'keywords': ['archive', 'compressed', 'download', 'package'],
                    'score_boost': 10.0
                },
                'video': {
                    'extensions': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'],
                    'keywords': ['video', 'movie', 'film', 'recording'],
                    'score_boost': 10.0
                },
                'audio': {
                    'extensions': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],
                    'keywords': ['audio', 'music', 'sound', 'podcast', 'recording'],
                    'score_boost': 10.0
                }
            },
            
            # Content structure indicators
            'structure_indicators': {
                'academic_paper': {
                    'keywords': ['abstract', 'introduction', 'methodology', 'conclusion', 'references'],
                    'score_boost': 25.0
                },
                'technical_documentation': {
                    'keywords': ['api', 'documentation', 'specification', 'guide', 'tutorial'],
                    'score_boost': 20.0
                },
                'news_article': {
                    'keywords': ['breaking', 'news', 'reported', 'journalist', 'source'],
                    'score_boost': 15.0
                },
                'blog_post': {
                    'keywords': ['posted', 'author', 'comment', 'share', 'tags'],
                    'score_boost': 10.0
                },
                'product_page': {
                    'keywords': ['price', 'buy', 'product', 'specifications', 'reviews'],
                    'score_boost': 5.0
                }
            },
            
            # Content quality indicators
            'quality_indicators': {
                'high_quality': {
                    'min_length': 500,
                    'keywords': ['research', 'study', 'analysis', 'comprehensive', 'detailed'],
                    'score_boost': 20.0
                },
                'medium_quality': {
                    'min_length': 200,
                    'keywords': ['overview', 'summary', 'guide', 'tutorial'],
                    'score_boost': 10.0
                },
                'basic_quality': {
                    'min_length': 50,
                    'keywords': ['info', 'about', 'description'],
                    'score_boost': 5.0
                }
            },
            
            # Content completeness checks
            'completeness_checks': {
                'has_title': 15.0,
                'has_substantial_content': 20.0,
                'has_metadata': 10.0,
                'has_structured_data': 15.0
            },
            
            # Format mismatch penalties
            'format_penalties': {
                'wrong_filetype': -30.0,
                'no_file_extension': -10.0,
                'suspicious_content': -25.0,
                'truncated_content': -15.0
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"ContentFilter initialized with {len(self.config['filetype_categories'])} content categories")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on content type and quality analysis.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with content scores
        """
        if not results:
            return []
        
        filter_results = []
        
        # Analyze query for content intent
        content_intent = self._analyze_query_intent(context.query, context.query_context)
        
        self.logger.debug(
            f"Analyzing content for {len(results)} results with intent: {content_intent}"
        )
        
        for i, result in enumerate(results):
            try:
                # Calculate content score
                content_score = await self._calculate_content_score(
                    result, context, content_intent
                )
                
                # Determine tier and classification
                tier, classification = self._classify_result(content_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(result, content_score, content_intent)
                
                # Get detailed content analysis
                content_analysis = self._get_content_analysis(result, content_intent)
                
                filter_result = FilterResult(
                    result_id=f"content_{i}",
                    score=content_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'content_analysis': content_analysis,
                        'content_intent': content_intent,
                        'filter': 'content'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                filter_results.append(self._create_error_result(i, str(e)))
        
        avg_score = sum(fr.score for fr in filter_results) / len(filter_results)
        self.logger.debug(f"ContentFilter processed {len(results)} results, average score: {avg_score:.1f}")
        
        return filter_results
    
    def _analyze_query_intent(
        self,
        query: str,
        query_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze query to understand content intent.
        
        Args:
            query: Search query
            query_context: Additional query context
            
        Returns:
            Dictionary with content intent analysis
        """
        intent = {
            'expected_filetype': None,
            'expected_category': None,
            'quality_level': 'medium',
            'structure_preference': None,
            'keywords': []
        }
        
        query_lower = query.lower()
        
        # Extract filetype intent from query context (e.g., from filetype search)
        if query_context.get('filetype'):
            filetype = query_context['filetype'].lower().replace('!', '')
            intent['expected_filetype'] = filetype
            
            # Map filetype to category
            for category, info in self.config['filetype_categories'].items():
                if f'.{filetype}' in info['extensions']:
                    intent['expected_category'] = category
                    break
        
        # Extract filetype intent from query text
        if not intent['expected_filetype']:
            for category, info in self.config['filetype_categories'].items():
                for ext in info['extensions']:
                    ext_name = ext[1:]  # Remove dot
                    if ext_name in query_lower or f"{ext_name}!" in query_lower:
                        intent['expected_filetype'] = ext_name
                        intent['expected_category'] = category
                        break
                if intent['expected_filetype']:
                    break
        
        # Analyze structure preference
        for structure_type, info in self.config['structure_indicators'].items():
            if any(keyword in query_lower for keyword in info['keywords']):
                intent['structure_preference'] = structure_type
                break
        
        # Analyze quality level intent
        quality_keywords = {
            'high': ['comprehensive', 'detailed', 'research', 'academic', 'study'],
            'medium': ['guide', 'tutorial', 'overview', 'introduction'],
            'basic': ['simple', 'basic', 'quick', 'summary']
        }
        
        for level, keywords in quality_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                intent['quality_level'] = level
                break
        
        # Extract relevant keywords
        intent['keywords'] = [
            word for word in query_lower.split()
            if len(word) > 3 and word not in ['the', 'and', 'for', 'with', 'from']
        ]
        
        return intent
    
    async def _calculate_content_score(
        self,
        result: Dict[str, Any],
        context: FilterContext,
        content_intent: Dict[str, Any]
    ) -> float:
        """
        Calculate comprehensive content score.
        
        Args:
            result: Search result to analyze
            context: Filtering context
            content_intent: Analyzed content intent
            
        Returns:
            Content score (0-100)
        """
        scores = {}
        
        # 1. Format analysis
        scores['format'] = self._analyze_format_match(
            result, content_intent
        ) * self.config['format_analysis_weight']
        
        # 2. Structure analysis
        scores['structure'] = self._analyze_content_structure(
            result, content_intent
        ) * self.config['structure_analysis_weight']
        
        # 3. Completeness analysis
        scores['completeness'] = self._analyze_content_completeness(
            result
        ) * self.config['completeness_weight']
        
        # 4. Format matching
        scores['format_matching'] = self._analyze_format_matching(
            result, content_intent
        ) * self.config['format_matching_weight']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Apply format penalties if applicable
        penalties = self._calculate_format_penalties(result, content_intent)
        total_score += penalties
        
        # Normalize to 0-100 range
        content_score = min(100.0, max(0.0, total_score))
        
        return content_score
    
    def _analyze_format_match(
        self,
        result: Dict[str, Any],
        content_intent: Dict[str, Any]
    ) -> float:
        """Analyze how well the result format matches the expected format."""
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        
        score = 60.0  # Default neutral score
        
        expected_filetype = content_intent.get('expected_filetype')
        expected_category = content_intent.get('expected_category')
        
        if expected_filetype:
            # Check for exact filetype match in URL
            if f'.{expected_filetype}' in url:
                score = 100.0
            # Check for filetype mention in title
            elif expected_filetype in title:
                score = 80.0
            # Check for category keywords
            elif expected_category:
                category_info = self.config['filetype_categories'].get(expected_category, {})
                category_keywords = category_info.get('keywords', [])
                if any(keyword in title for keyword in category_keywords):
                    score = 70.0
        
        # Boost score for recognized file types
        for category, info in self.config['filetype_categories'].items():
            for ext in info['extensions']:
                if ext in url:
                    score += info['score_boost']
                    break
        
        return min(100.0, score)
    
    def _analyze_content_structure(
        self,
        result: Dict[str, Any],
        content_intent: Dict[str, Any]
    ) -> float:
        """Analyze content structure and organization."""
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        combined_text = f"{title} {snippet}"
        
        score = 50.0  # Default neutral score
        
        # Check for expected structure type
        expected_structure = content_intent.get('structure_preference')
        if expected_structure and expected_structure in self.config['structure_indicators']:
            structure_info = self.config['structure_indicators'][expected_structure]
            keywords = structure_info['keywords']
            matches = sum(1 for keyword in keywords if keyword in combined_text)
            if matches > 0:
                score += structure_info['score_boost'] * (matches / len(keywords))
        
        # General structure analysis
        for structure_type, info in self.config['structure_indicators'].items():
            keywords = info['keywords']
            matches = sum(1 for keyword in keywords if keyword in combined_text)
            if matches >= 2:  # At least 2 structure indicators
                score += info['score_boost'] * 0.5  # Partial boost
                break
        
        # Content organization indicators
        organization_indicators = [
            'table of contents', 'index', 'chapter', 'section',
            'part', 'appendix', 'bibliography', 'references'
        ]
        
        org_matches = sum(1 for indicator in organization_indicators 
                         if indicator in combined_text)
        if org_matches > 0:
            score += org_matches * 5.0
        
        return min(100.0, score)
    
    def _analyze_content_completeness(self, result: Dict[str, Any]) -> float:
        """Analyze content completeness and depth."""
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        
        score = 0.0
        checks = self.config['completeness_checks']
        
        # Has title check
        if title and len(title.strip()) > 5:
            score += checks['has_title']
        
        # Has substantial content check
        if snippet and len(snippet) >= 100:
            score += checks['has_substantial_content']
            
            # Bonus for very substantial content
            if len(snippet) >= 500:
                score += 10.0
        
        # Has metadata check (basic heuristics)
        if any(indicator in snippet.lower() for indicator in 
               ['author:', 'date:', 'published:', 'updated:', 'source:']):
            score += checks['has_metadata']
        
        # Has structured data check
        if any(indicator in snippet.lower() for indicator in 
               ['abstract:', 'summary:', 'keywords:', 'tags:']):
            score += checks['has_structured_data']
        
        # Content quality based on length and indicators
        for quality_level, info in self.config['quality_indicators'].items():
            if len(snippet) >= info['min_length']:
                quality_matches = sum(1 for keyword in info['keywords'] 
                                    if keyword in snippet.lower())
                if quality_matches > 0:
                    score += info['score_boost'] * (quality_matches / len(info['keywords']))
                    break
        
        return min(100.0, score)
    
    def _analyze_format_matching(
        self,
        result: Dict[str, Any],
        content_intent: Dict[str, Any]
    ) -> float:
        """Analyze how well the format matches the query intent."""
        score = 60.0  # Default neutral score
        
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', '')).lower()
        
        # Check intent keywords in content
        intent_keywords = content_intent.get('keywords', [])
        combined_text = f"{title} {snippet}"
        
        if intent_keywords:
            keyword_matches = sum(1 for keyword in intent_keywords 
                                if keyword in combined_text)
            keyword_score = (keyword_matches / len(intent_keywords)) * 40.0
            score += keyword_score
        
        # Quality level matching
        quality_level = content_intent.get('quality_level', 'medium')
        if quality_level in self.config['quality_indicators']:
            quality_info = self.config['quality_indicators'][quality_level]
            
            # Check minimum length requirement
            if len(snippet) >= quality_info['min_length']:
                score += 10.0
            
            # Check quality keywords
            quality_matches = sum(1 for keyword in quality_info['keywords'] 
                                if keyword in combined_text)
            if quality_matches > 0:
                score += 15.0
        
        return min(100.0, score)
    
    def _calculate_format_penalties(
        self,
        result: Dict[str, Any],
        content_intent: Dict[str, Any]
    ) -> float:
        """Calculate penalties for format mismatches."""
        penalties = 0.0
        
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        snippet = result.get('snippet', result.get('description', ''))
        
        # Wrong filetype penalty
        expected_filetype = content_intent.get('expected_filetype')
        if expected_filetype and self.config['strict_filetype_matching']:
            if f'.{expected_filetype}' not in url and expected_filetype not in title:
                penalties += self.config['format_penalties']['wrong_filetype']
        
        # No file extension penalty (for file searches)
        if expected_filetype and '.' not in url.split('/')[-1]:
            penalties += self.config['format_penalties']['no_file_extension']
        
        # Suspicious content penalty
        suspicious_indicators = [
            'error', '404', 'not found', 'access denied', 'forbidden',
            'under construction', 'coming soon', 'placeholder'
        ]
        
        combined_text = f"{title} {snippet}".lower()
        if any(indicator in combined_text for indicator in suspicious_indicators):
            penalties += self.config['format_penalties']['suspicious_content']
        
        # Truncated content penalty
        if snippet.endswith('...') or len(snippet) < 30:
            penalties += self.config['format_penalties']['truncated_content']
        
        return penalties
    
    def _classify_result(self, content_score: float) -> tuple:
        """Classify result based on content score."""
        if content_score >= 85.0:
            return 1, 'primary'
        elif content_score >= 70.0:
            return 2, 'primary'
        elif content_score >= 50.0:
            return 3, 'secondary'
        elif content_score >= self.config['min_content_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out
    
    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        score: float,
        content_intent: Dict[str, Any]
    ) -> str:
        """Generate human-readable reasoning for the content score."""
        reasons = []
        
        if score >= 85:
            reasons.append("Excellent content match")
        elif score >= 70:
            reasons.append("Good content match")
        elif score >= 50:
            reasons.append("Adequate content match")
        else:
            reasons.append("Poor content match")
        
        # Add specific content indicators
        url = result.get('url', '').lower()
        expected_filetype = content_intent.get('expected_filetype')
        
        if expected_filetype and f'.{expected_filetype}' in url:
            reasons.append(f"Exact filetype match ({expected_filetype})")
        
        snippet = result.get('snippet', result.get('description', ''))
        if len(snippet) > 200:
            reasons.append("Substantial content")
        
        expected_category = content_intent.get('expected_category')
        if expected_category:
            category_info = self.config['filetype_categories'].get(expected_category, {})
            if any(keyword in snippet.lower() for keyword in category_info.get('keywords', [])):
                reasons.append(f"Content type indicators ({expected_category})")
        
        return "; ".join(reasons)
    
    def _get_content_analysis(
        self,
        result: Dict[str, Any],
        content_intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get detailed content analysis for debugging."""
        url = result.get('url', '')
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        
        # Extract file extension from URL
        url_parts = url.split('/')
        filename = url_parts[-1] if url_parts else ''
        file_extension = ''
        if '.' in filename:
            file_extension = filename.split('.')[-1].lower()
        
        return {
            'url_length': len(url),
            'title_length': len(title),
            'snippet_length': len(snippet),
            'file_extension': file_extension,
            'expected_filetype': content_intent.get('expected_filetype'),
            'expected_category': content_intent.get('expected_category'),
            'has_file_extension': bool(file_extension),
            'format_match': f'.{content_intent.get("expected_filetype", "")}' in url.lower(),
            'content_keywords': [
                kw for kw in content_intent.get('keywords', [])
                if kw in snippet.lower()
            ],
            'structure_indicators': [
                structure for structure, info in self.config['structure_indicators'].items()
                if any(keyword in snippet.lower() for keyword in info['keywords'])
            ]
        }
    
    def _create_error_result(self, index: int, error_msg: str) -> FilterResult:
        """Create result for processing errors."""
        return FilterResult(
            result_id=f"content_error_{index}",
            score=40.0,  # Neutral-low score for errors
            tier=4,
            classification='secondary',
            reasoning=f"Content analysis error: {error_msg}",
            metadata={'filter': 'content', 'error': True},
            processed_at=time.time()
        )