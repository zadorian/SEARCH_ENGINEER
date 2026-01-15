"""
Exact Phrase Filter

Strict filtering for exact phrase searches using PhraseMatcher integration.
Ensures that results without exact phrase matches are filtered out.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Set
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext
from brute.scraper.phrase_matcher import PhraseMatcher

logger = logging.getLogger(__name__)

class ExactPhraseFilter(BaseFilter):
    """
    Filter that performs strict exact phrase matching for quoted search queries.
    
    This filter ensures that:
    1. Exact phrase searches (quoted text) only return results containing the exact phrase
    2. File type searches only return results with the correct file extension
    3. Results are properly highlighted when they match
    4. Non-matching results are filtered out to the "Filtered Out" tab
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize ExactPhraseFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("ExactPhraseFilter", config)
        
        # Initialize phrase matcher with distance=2 for two-word phrases
        self.phrase_matcher = PhraseMatcher(max_distance=2)
        
        # Default configuration
        self.default_config = {
            'strict_exact_phrase': True,        # Require exact phrase matches
            'strict_filetype': True,            # Require exact filetype matches
            'min_score_threshold': 50.0,        # Minimum score to pass filter
            'enable_highlighting': True,        # Add highlighting metadata
            'case_sensitive': False,            # Case insensitive matching
            'proximity_fallback': True,         # Allow proximity matches as fallback
            'url_symbol_matching': True,        # Handle URL symbols (-, ., +)
            
            # Scoring weights
            'exact_match_score': 100.0,
            'proximity_match_score': 80.0,
            'partial_match_score': 0.0,        # Set to 0 to filter out partial matches
            'no_match_score': 0.0,
            
            # File type matching
            'supported_filetypes': {
                'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                'txt', 'rtf', 'odt', 'ods', 'odp', 'csv', 'json',
                'xml', 'html', 'htm', 'md', 'zip', 'rar',
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg',
                'mp3', 'mp4', 'avi', 'mov', 'wav'
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"ExactPhraseFilter initialized with config: {self.config}")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on exact phrase matching.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with phrase matching scores
        """
        if not results:
            return []
        
        filter_results = []
        
        # Extract query information
        query = context.query or ""
        query_context = context.query_context or {}
        
        # Extract exact phrases from query
        exact_phrases = self.phrase_matcher.extract_phrases(query)
        
        # Handle force_exact_phrase
        if not exact_phrases and query_context.get('force_exact_phrase'):
            # Use the cleaned exact phrase if available, otherwise the whole query
            phrase = query_context.get('exact_phrase') or query
            if phrase:
                exact_phrases = [phrase]
                self.logger.info(f"Forcing exact phrase match for: {phrase}")

        # Detect file type searches
        detected_filetype = self._detect_filetype_search(query, query_context)
        
        self.logger.info(
            f"Filtering {len(results)} results - "
            f"Phrases: {exact_phrases}, Filetype: {detected_filetype}"
        )
        
        for i, result in enumerate(results):
            try:
                # Calculate phrase match score
                phrase_score = await self._calculate_phrase_score(
                    result, exact_phrases, context
                )
                
                # Calculate filetype score if applicable
                filetype_score = self._calculate_filetype_score(
                    result, detected_filetype
                )
                
                # Combine scores
                final_score = self._combine_scores(phrase_score, filetype_score)
                
                # Determine if result passes filter
                passes_filter = final_score >= self.config['min_score_threshold']
                
                # Determine tier and classification
                tier, classification = self._classify_result(final_score, passes_filter)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(
                    result, phrase_score, filetype_score, exact_phrases, detected_filetype
                )
                
                # Create highlighting metadata
                highlighting_data = self._create_highlighting_metadata(
                    result, exact_phrases, detected_filetype, phrase_score
                )
                
                filter_result = FilterResult(
                    result_id=f"exact_phrase_{i}",
                    score=final_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'exact_phrases': exact_phrases,
                        'detected_filetype': detected_filetype,
                        'phrase_score': phrase_score,
                        'filetype_score': filetype_score,
                        'passes_filter': passes_filter,
                        'highlighting': highlighting_data,
                        'filter': 'exact_phrase'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                filter_results.append(self._create_error_result(i, str(e)))
        
        # Log filtering summary  
        passed_count = sum(1 for fr in filter_results if fr.metadata.get('passes_filter', False))
        filtered_count = len(filter_results) - passed_count
        
        self.logger.info(
            f"ExactPhraseFilter: {passed_count} passed, {filtered_count} filtered out"
        )
        
        return filter_results
    
    def _detect_filetype_search(self, query: str, query_context: Dict[str, Any]) -> str:
        """
        Detect if this is a filetype-specific search.
        
        Args:
            query: Search query
            query_context: Additional query context
            
        Returns:
            Detected filetype or empty string
        """
        # Check query context for filetype
        if 'filetype' in query_context:
            return query_context['filetype'].lower().replace('!', '')
        
        # Check for filetype operators in query (pdf!, docx!, etc.)
        filetype_pattern = r'\b(\w{2,5})!'
        matches = re.findall(filetype_pattern, query.lower())
        
        for match in matches:
            if match in self.config['supported_filetypes']:
                return match
        
        return ""
    
    async def _calculate_phrase_score(
        self,
        result: Dict[str, Any],
        exact_phrases: List[str],
        context: FilterContext
    ) -> float:
        """
        Calculate score based on phrase matching.
        
        Args:
            result: Search result to analyze
            exact_phrases: List of exact phrases to match
            context: Filtering context
            
        Returns:
            Phrase matching score (0-100)
        """
        if not exact_phrases:
            return 100.0  # No phrase filtering needed
        
        # Get text content to search
        snippet = result.get('snippet') or result.get('description') or result.get('summary') or ""
        title = result.get('title') or ""
        url = result.get('url') or ""
        
        # Combine all text for matching
        combined_text = f"{title} {snippet} {url}"
        
        if not combined_text.strip():
            return 0.0
        
        # Score each phrase
        phrase_scores = []
        
        for phrase in exact_phrases:
            # Use PhraseMatcher to score this phrase
            match_info = self.phrase_matcher.score_snippet(combined_text, [phrase])
            
            if match_info['exact_matches']:
                phrase_scores.append(self.config['exact_match_score'])
            elif match_info['proximity_matches'] and self.config['proximity_fallback']:
                phrase_scores.append(self.config['proximity_match_score'])
            elif match_info['partial_matches']:
                phrase_scores.append(self.config['partial_match_score'])
            else:
                phrase_scores.append(self.config['no_match_score'])
        
        # Return the minimum score (all phrases must match for high score)
        return min(phrase_scores) if phrase_scores else 0.0
    
    def _calculate_filetype_score(self, result: Dict[str, Any], detected_filetype: str) -> float:
        """
        Calculate score based on filetype matching.
        
        Args:
            result: Search result to analyze
            detected_filetype: Required filetype
            
        Returns:
            Filetype matching score (0-100)
        """
        if not detected_filetype:
            return 100.0  # No filetype filtering needed

        # Use 'or' to handle None values (get() returns None if key exists but value is None)
        url = (result.get('url') or '').lower()
        title = (result.get('title') or '').lower()
        
        # Check for exact file extension in URL
        if f'.{detected_filetype}' in url:
            return 100.0
        
        # Check for filetype mention in title
        if detected_filetype in title:
            return 75.0
        
        # Check for common PDF indicators
        if detected_filetype == 'pdf':
            pdf_indicators = ['pdf', 'document', 'report', 'paper', 'manual']
            if any(indicator in title or indicator in url for indicator in pdf_indicators):
                return 50.0
        
        # If strict filetype matching is enabled, filter out non-matches
        if self.config['strict_filetype']:
            return 0.0
        
        return 25.0  # Low score for potential matches
    
    def _combine_scores(self, phrase_score: float, filetype_score: float) -> float:
        """
        Combine phrase and filetype scores.
        
        Args:
            phrase_score: Phrase matching score
            filetype_score: Filetype matching score
            
        Returns:
            Combined score
        """
        # Both must pass for result to be included
        return min(phrase_score, filetype_score)
    
    def _classify_result(self, score: float, passes_filter: bool) -> tuple:
        """
        Classify result based on score.
        
        Args:
            score: Final result score
            passes_filter: Whether result passes the filter
            
        Returns:
            Tuple of (tier, classification)
        """
        if not passes_filter:
            return 4, 'filtered'  # Special classification for filtered results
        
        if score >= 90.0:
            return 1, 'primary'
        elif score >= 70.0:
            return 2, 'primary'
        elif score >= 50.0:
            return 3, 'secondary'
        else:
            return 4, 'secondary'
    
    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        phrase_score: float,
        filetype_score: float,
        exact_phrases: List[str],
        detected_filetype: str
    ) -> str:
        """
        Generate human-readable reasoning for the score.
        
        Args:
            result: Search result
            phrase_score: Phrase matching score
            filetype_score: Filetype matching score
            exact_phrases: Required phrases
            detected_filetype: Required filetype
            
        Returns:
            Reasoning string
        """
        reasons = []
        
        # Phrase matching reasoning
        if exact_phrases:
            if phrase_score >= 90:
                reasons.append(f"Exact phrase match: {', '.join(exact_phrases)}")
            elif phrase_score >= 70:
                reasons.append(f"Proximity phrase match: {', '.join(exact_phrases)}")
            elif phrase_score > 0:
                reasons.append(f"Partial phrase match: {', '.join(exact_phrases)}")
            else:
                reasons.append(f"No phrase match found: {', '.join(exact_phrases)}")
        
        # Filetype reasoning
        if detected_filetype:
            if filetype_score >= 90:
                reasons.append(f"Exact filetype match: {detected_filetype}")
            elif filetype_score >= 50:
                reasons.append(f"Likely filetype match: {detected_filetype}")
            else:
                reasons.append(f"No filetype match: {detected_filetype}")
        
        return "; ".join(reasons) if reasons else "No specific filtering criteria"
    
    def _create_highlighting_metadata(
        self,
        result: Dict[str, Any],
        exact_phrases: List[str],
        detected_filetype: str,
        phrase_score: float
    ) -> Dict[str, Any]:
        """
        Create metadata for highlighting matched terms.
        
        Args:
            result: Search result
            exact_phrases: Phrases to highlight
            detected_filetype: Filetype to highlight
            phrase_score: Phrase matching score
            
        Returns:
            Highlighting metadata
        """
        highlighting = {
            'should_highlight': phrase_score > 0,
            'highlight_phrases': exact_phrases,
            'highlight_filetype': detected_filetype,
            'highlight_color': 'yellow'
        }
        
        # Add specific highlighting instructions
        if phrase_score >= 90:
            highlighting['highlight_style'] = 'exact-match'
        elif phrase_score >= 70:
            highlighting['highlight_style'] = 'proximity-match'
        else:
            highlighting['highlight_style'] = 'no-match'
        
        return highlighting
    
    def _create_error_result(self, index: int, error_msg: str) -> FilterResult:
        """Create result for processing errors."""
        return FilterResult(
            result_id=f"exact_phrase_error_{index}",
            score=0.0,  # Low score for errors - will be filtered out
            tier=4,
            classification='filtered',
            reasoning=f"Exact phrase filter error: {error_msg}",
            metadata={
                'filter': 'exact_phrase',
                'error': True,
                'passes_filter': False
            },
            processed_at=time.time()
        )