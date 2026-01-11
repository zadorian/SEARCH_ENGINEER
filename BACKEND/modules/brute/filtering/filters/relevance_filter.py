"""
Relevance Filter

Analyzes the relevance of search results based on query-content matching,
keyword density, and semantic similarity.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class RelevanceFilter(BaseFilter):
    """
    Filter that analyzes content relevance to the search query using
    multiple relevance scoring techniques.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize RelevanceFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("RelevanceFilter", config)
        
        # Default configuration
        self.default_config = {
            'title_weight': 0.4,           # Weight for title matching
            'snippet_weight': 0.3,         # Weight for snippet matching
            'url_weight': 0.1,             # Weight for URL matching
            'exact_match_bonus': 0.2,      # Bonus for exact phrase matches
            'keyword_density_weight': 0.15, # Weight for keyword density
            'min_relevance_score': 10.0,   # Minimum score to not filter
            'exact_phrase_multiplier': 1.5, # Multiplier for exact phrase queries
            'case_sensitive': False,        # Case sensitive matching
            'stemming_enabled': True,       # Enable basic stemming
            'stop_words': [                 # Common stop words to ignore
                'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for',
                'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on',
                'that', 'the', 'to', 'was', 'were', 'will', 'with'
            ]
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        self.logger.debug(f"RelevanceFilter initialized with config: {self.config}")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results based on relevance to the query.
        
        Args:
            results: List of search results to filter
            context: Filtering context with query information
            
        Returns:
            List of FilterResult objects with relevance scores
        """
        if not results or not context.query:
            return []
        
        filter_results = []
        query = context.query.strip()
        
        # Preprocess query for matching
        processed_query = self._preprocess_query(query)
        query_terms = self._extract_query_terms(processed_query)
        is_exact_phrase = self._is_exact_phrase_query(query)
        
        self.logger.debug(
            f"Processing {len(results)} results for query: '{query}' "
            f"(terms: {query_terms}, exact_phrase: {is_exact_phrase})"
        )
        
        for i, result in enumerate(results):
            try:
                # Calculate relevance score
                relevance_score = await self._calculate_relevance_score(
                    result, query, query_terms, is_exact_phrase
                )
                
                # Determine tier and classification
                tier, classification = self._classify_result(relevance_score)
                
                # Generate reasoning
                reasoning = self._generate_reasoning(
                    result, query, relevance_score, query_terms
                )
                
                filter_result = FilterResult(
                    result_id=f"relevance_{i}",
                    score=relevance_score,
                    tier=tier,
                    classification=classification,
                    reasoning=reasoning,
                    metadata={
                        'query_terms': query_terms,
                        'exact_phrase': is_exact_phrase,
                        'relevance_breakdown': self._get_score_breakdown(result, query_terms),
                        'filter': 'relevance'
                    },
                    processed_at=time.time()
                )
                
                filter_results.append(filter_result)
                
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {e}")
                # Create low-score result for error cases
                filter_results.append(FilterResult(
                    result_id=f"relevance_error_{i}",
                    score=0.0,
                    tier=4,
                    classification='secondary',
                    reasoning=f"Relevance calculation error: {str(e)}",
                    metadata={'error': True, 'filter': 'relevance'},
                    processed_at=time.time()
                ))
        
        self.logger.debug(
            f"RelevanceFilter processed {len(results)} results, "
            f"average score: {sum(fr.score for fr in filter_results) / len(filter_results):.1f}"
        )
        
        return filter_results
    
    def _preprocess_query(self, query: str) -> str:
        """
        Preprocess query for better matching.
        
        Args:
            query: Raw query string
            
        Returns:
            Preprocessed query
        """
        # Remove quotes for exact phrase queries
        if query.startswith('"') and query.endswith('"'):
            query = query[1:-1]
        elif query.startswith("'") and query.endswith("'"):
            query = query[1:-1]
        
        # Basic cleanup
        query = re.sub(r'[^\w\s-]', ' ', query)  # Remove punctuation except hyphens
        query = re.sub(r'\s+', ' ', query)       # Normalize whitespace
        
        if not self.config['case_sensitive']:
            query = query.lower()
        
        return query.strip()
    
    def _extract_query_terms(self, query: str) -> List[str]:
        """
        Extract meaningful terms from the query.
        
        Args:
            query: Preprocessed query
            
        Returns:
            List of query terms
        """
        terms = query.split()
        
        # Remove stop words if enabled
        if self.config.get('remove_stop_words', True):
            terms = [
                term for term in terms 
                if term.lower() not in self.config['stop_words']
            ]
        
        # Apply basic stemming if enabled
        if self.config['stemming_enabled']:
            terms = [self._simple_stem(term) for term in terms]
        
        return [term for term in terms if len(term) > 1]  # Remove single characters
    
    def _simple_stem(self, word: str) -> str:
        """
        Apply basic stemming to a word.
        
        Args:
            word: Word to stem
            
        Returns:
            Stemmed word
        """
        # Very basic stemming rules
        if word.endswith('ing'):
            return word[:-3]
        elif word.endswith('ed'):
            return word[:-2]
        elif word.endswith('ly'):
            return word[:-2]
        elif word.endswith('s') and len(word) > 3:
            return word[:-1]
        
        return word
    
    def _is_exact_phrase_query(self, query: str) -> bool:
        """Check if query is an exact phrase search."""
        return (
            (query.startswith('"') and query.endswith('"')) or
            (query.startswith("'") and query.endswith("'"))
        )
    
    async def _calculate_relevance_score(
        self,
        result: Dict[str, Any],
        original_query: str,
        query_terms: List[str],
        is_exact_phrase: bool
    ) -> float:
        """
        Calculate comprehensive relevance score for a result.
        
        Args:
            result: Search result to score
            original_query: Original search query
            query_terms: Extracted query terms
            is_exact_phrase: Whether this is an exact phrase query
            
        Returns:
            Relevance score (0-100)
        """
        if not query_terms:
            return 50.0  # Neutral score if no terms
        
        # Extract text fields
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        url = result.get('url', '')
        
        # Preprocess text fields
        title_text = self._preprocess_text(title)
        snippet_text = self._preprocess_text(snippet)
        url_text = self._preprocess_text(url)
        
        scores = {}
        
        # 1. Title matching score
        scores['title'] = self._calculate_text_match_score(
            title_text, query_terms, original_query, is_exact_phrase
        ) * self.config['title_weight']
        
        # 2. Snippet matching score
        scores['snippet'] = self._calculate_text_match_score(
            snippet_text, query_terms, original_query, is_exact_phrase
        ) * self.config['snippet_weight']
        
        # 3. URL matching score
        scores['url'] = self._calculate_text_match_score(
            url_text, query_terms, original_query, is_exact_phrase
        ) * self.config['url_weight']
        
        # 4. Keyword density score
        combined_text = f"{title_text} {snippet_text}"
        scores['density'] = self._calculate_keyword_density_score(
            combined_text, query_terms
        ) * self.config['keyword_density_weight']
        
        # 5. Exact phrase bonus
        scores['exact_bonus'] = 0.0
        if is_exact_phrase:
            exact_score = self._calculate_exact_phrase_score(
                combined_text, original_query.strip('"').strip("'")
            )
            scores['exact_bonus'] = exact_score * self.config['exact_match_bonus']
        
        # Calculate total score
        total_score = sum(scores.values())
        
        # Apply exact phrase multiplier
        if is_exact_phrase and total_score > 0:
            total_score *= self.config['exact_phrase_multiplier']
        
        # Normalize to 0-100 range
        relevance_score = min(100.0, max(0.0, total_score))
        
        return relevance_score
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for matching."""
        if not text:
            return ""
        
        # Clean and normalize
        text = re.sub(r'[^\w\s-]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        if not self.config['case_sensitive']:
            text = text.lower()
        
        return text.strip()
    
    def _calculate_text_match_score(
        self,
        text: str,
        query_terms: List[str],
        original_query: str,
        is_exact_phrase: bool
    ) -> float:
        """
        Calculate how well text matches query terms.
        
        Args:
            text: Text to analyze
            query_terms: Query terms to match
            original_query: Original query string
            is_exact_phrase: Whether this is exact phrase matching
            
        Returns:
            Match score (0-100)
        """
        if not text or not query_terms:
            return 0.0
        
        # For exact phrase queries, check for phrase presence
        if is_exact_phrase:
            clean_query = original_query.strip('"').strip("'")
            if not self.config['case_sensitive']:
                clean_query = clean_query.lower()
                
            if clean_query in text:
                return 100.0
            else:
                # Check for partial phrase matches
                query_words = clean_query.split()
                matches = sum(1 for word in query_words if word in text)
                return (matches / len(query_words)) * 70.0
        
        # For regular queries, calculate term matching
        text_words = text.split()
        if not text_words:
            return 0.0
        
        # Count term matches
        matches = 0
        for term in query_terms:
            if term in text:
                matches += 1
        
        # Calculate match percentage
        match_percentage = matches / len(query_terms)
        
        # Bonus for early matches (terms appearing early in text)
        early_match_bonus = 0
        for i, word in enumerate(text_words[:10]):  # Check first 10 words
            if any(term in word for term in query_terms):
                early_match_bonus += (10 - i) / 10 * 10  # Up to 10 point bonus
        
        total_score = (match_percentage * 80) + min(early_match_bonus, 20)
        
        return min(100.0, total_score)
    
    def _calculate_keyword_density_score(
        self,
        text: str,
        query_terms: List[str]
    ) -> float:
        """
        Calculate keyword density score.
        
        Args:
            text: Text to analyze
            query_terms: Query terms
            
        Returns:
            Density score (0-100)
        """
        if not text or not query_terms:
            return 0.0
        
        words = text.split()
        if not words:
            return 0.0
        
        # Count query term occurrences
        term_count = 0
        for word in words:
            if any(term in word for term in query_terms):
                term_count += 1
        
        # Calculate density
        density = term_count / len(words)
        
        # Optimal density is around 2-5%, score accordingly
        if density == 0:
            return 0.0
        elif 0.02 <= density <= 0.05:  # Optimal range
            return 100.0
        elif density < 0.02:  # Too low
            return density / 0.02 * 100
        else:  # Too high (might be spam)
            return max(20.0, 100.0 - (density - 0.05) * 1000)
    
    def _calculate_exact_phrase_score(
        self,
        text: str,
        phrase: str
    ) -> float:
        """
        Calculate score for exact phrase matching.
        
        Args:
            text: Text to search in
            phrase: Exact phrase to find
            
        Returns:
            Exact phrase score (0-100)
        """
        if not text or not phrase:
            return 0.0
        
        if not self.config['case_sensitive']:
            text = text.lower()
            phrase = phrase.lower()
        
        # Check for exact phrase
        if phrase in text:
            # Bonus for multiple occurrences
            count = text.count(phrase)
            return min(100.0, 80.0 + (count - 1) * 10)
        
        # Check for phrase with minor variations
        phrase_words = phrase.split()
        if len(phrase_words) > 1:
            # Look for words in sequence with small gaps
            text_words = text.split()
            max_gap_score = 0
            
            for i in range(len(text_words) - len(phrase_words) + 1):
                gap_score = self._calculate_sequence_score(
                    text_words[i:i+len(phrase_words)*2], phrase_words
                )
                max_gap_score = max(max_gap_score, gap_score)
            
            return max_gap_score
        
        return 0.0
    
    def _calculate_sequence_score(
        self,
        text_sequence: List[str],
        phrase_words: List[str]
    ) -> float:
        """Calculate score for word sequence matching."""
        if not text_sequence or not phrase_words:
            return 0.0
        
        matches = 0
        gaps = 0
        phrase_idx = 0
        
        for word in text_sequence:
            if phrase_idx < len(phrase_words) and word == phrase_words[phrase_idx]:
                matches += 1
                phrase_idx += 1
                if phrase_idx == len(phrase_words):
                    break
            elif phrase_idx > 0:  # We've started matching but found a gap
                gaps += 1
        
        if matches == len(phrase_words):
            # All words found in sequence
            gap_penalty = gaps * 10  # 10 points penalty per gap
            return max(0.0, 60.0 - gap_penalty)
        
        return 0.0
    
    def _classify_result(self, relevance_score: float) -> tuple:
        """
        Classify result based on relevance score.
        
        Args:
            relevance_score: Calculated relevance score
            
        Returns:
            Tuple of (tier, classification)
        """
        if relevance_score >= 80.0:
            return 1, 'primary'
        elif relevance_score >= 60.0:
            return 2, 'primary'
        elif relevance_score >= 40.0:
            return 3, 'secondary'
        elif relevance_score >= self.config['min_relevance_score']:
            return 4, 'secondary'
        else:
            return 4, 'secondary'  # Don't completely filter out, but mark as low quality
    
    def _generate_reasoning(
        self,
        result: Dict[str, Any],
        query: str,
        score: float,
        query_terms: List[str]
    ) -> str:
        """Generate human-readable reasoning for the score."""
        title = result.get('title', '')
        snippet = result.get('snippet', result.get('description', ''))
        
        reasons = []
        
        if score >= 80:
            reasons.append("Excellent relevance")
        elif score >= 60:
            reasons.append("Good relevance")
        elif score >= 40:
            reasons.append("Moderate relevance")
        else:
            reasons.append("Low relevance")
        
        # Check for query terms in title
        title_matches = [term for term in query_terms if term.lower() in title.lower()]
        if title_matches:
            reasons.append(f"Query terms in title: {', '.join(title_matches)}")
        
        # Check for query terms in snippet
        snippet_matches = [term for term in query_terms if term.lower() in snippet.lower()]
        if snippet_matches:
            reasons.append(f"Query terms in content: {', '.join(snippet_matches)}")
        
        return "; ".join(reasons)
    
    def _get_score_breakdown(
        self,
        result: Dict[str, Any],
        query_terms: List[str]
    ) -> Dict[str, float]:
        """Get detailed score breakdown for debugging."""
        title = self._preprocess_text(result.get('title', ''))
        snippet = self._preprocess_text(result.get('snippet', ''))
        
        return {
            'title_matches': len([t for t in query_terms if t in title]),
            'snippet_matches': len([t for t in query_terms if t in snippet]),
            'total_query_terms': len(query_terms),
            'title_length': len(title.split()),
            'snippet_length': len(snippet.split())
        }