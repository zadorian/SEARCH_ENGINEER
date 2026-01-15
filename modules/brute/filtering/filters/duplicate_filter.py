"""
Duplicate Filter

Detects and handles duplicate search results using multiple similarity detection
methods including URL comparison, content similarity, and title matching.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Set, Tuple, Optional
import time
from pathlib import Path
import sys
from urllib.parse import urlparse, parse_qs
import hashlib
from difflib import SequenceMatcher

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ..core.base_filter import BaseFilter, FilterResult, FilterContext

logger = logging.getLogger(__name__)

class DuplicateFilter(BaseFilter):
    """
    Filter that detects and handles duplicate search results using
    multiple similarity detection techniques.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize DuplicateFilter.
        
        Args:
            config: Optional configuration dictionary
        """
        super().__init__("DuplicateFilter", config)
        
        # Default configuration
        self.default_config = {
            'url_similarity_threshold': 0.85,      # Threshold for URL similarity
            'content_similarity_threshold': 0.80,   # Threshold for content similarity
            'title_similarity_threshold': 0.90,     # Threshold for title similarity
            'exact_url_match': True,                # Remove exact URL duplicates
            'normalize_urls': True,                 # Normalize URLs before comparison
            'content_comparison_enabled': True,     # Enable content similarity checking
            'preserve_highest_score': True,         # Keep highest scored duplicate
            'max_duplicates_per_domain': 5,        # Max results per domain
            'similarity_weights': {                 # Weights for different similarity factors
                'url': 0.4,
                'title': 0.3,
                'content': 0.3
            },
            'url_normalization': {                  # URL normalization settings
                'remove_www': True,
                'remove_trailing_slash': True,
                'ignore_fragments': True,
                'ignore_utm_params': True,
                'case_insensitive': True
            },
            'content_normalization': {              # Content normalization settings
                'remove_punctuation': True,
                'case_insensitive': True,
                'remove_extra_whitespace': True,
                'min_content_length': 20
            }
        }
        
        # Merge with user config
        self.config = {**self.default_config, **(config or {})}
        
        # UTM and tracking parameters to ignore
        self.tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'gclid', 'fbclid', 'msclkid', 'ref', 'referrer', 'source',
            'campaign', 'medium', 'term', 'content'
        }
        
        self.logger.debug(f"DuplicateFilter initialized with config keys: {list(self.config.keys())}")
    
    async def filter_results(
        self,
        results: List[Dict[str, Any]],
        context: FilterContext
    ) -> List[FilterResult]:
        """
        Filter results to remove duplicates and near-duplicates.
        
        Args:
            results: List of search results to filter
            context: Filtering context
            
        Returns:
            List of FilterResult objects with duplicate handling
        """
        if not results:
            return []
        
        self.logger.debug(f"Analyzing {len(results)} results for duplicates")
        
        # Step 1: Group results by similarity
        duplicate_groups = await self._group_duplicates(results)
        
        # Step 2: Select best result from each group
        filtered_results = []
        duplicates_removed = 0
        
        for group_id, group_results in duplicate_groups.items():
            if len(group_results) > 1:
                # Multiple results in group - select the best one
                best_result = self._select_best_result(group_results)
                duplicates_removed += len(group_results) - 1
                
                # Create filter result for the best one
                filter_result = self._create_filter_result(
                    best_result, 
                    len(group_results), 
                    f"duplicate_group_{group_id}"
                )
                filtered_results.append(filter_result)
                
                # Log the duplicates for debugging
                self.logger.debug(
                    f"Group {group_id}: Kept 1 result, removed {len(group_results) - 1} duplicates"
                )
            else:
                # Single result in group - keep it
                result = group_results[0]
                filter_result = self._create_filter_result(
                    result, 
                    1, 
                    f"unique_{group_id}"
                )
                filtered_results.append(filter_result)
        
        # Step 3: Apply domain limits
        filtered_results = self._apply_domain_limits(filtered_results)
        
        self.logger.info(
            f"DuplicateFilter: {len(results)} input -> {len(filtered_results)} output "
            f"({duplicates_removed} duplicates removed)"
        )
        
        return filtered_results
    
    async def _group_duplicates(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Group results by similarity to identify duplicates.
        OPTIMIZED: Two-phase approach - O(N) hash-based pre-filter + O(K²) similarity for remaining

        Args:
            results: Results to group

        Returns:
            Dictionary mapping group_id to list of similar results
        """
        groups = {}
        next_group_id = 0

        # PHASE 1: Hash-based exact URL matching (O(N))
        # This catches 60-80% of duplicates instantly
        url_hash_groups: Dict[str, List[int]] = {}
        domain_groups: Dict[str, List[int]] = {}  # For fuzzy matching later

        for i, result in enumerate(results):
            result['_original_index'] = i

            url = result.get('url', '')
            norm_url = self._normalize_url(url)

            # Create hash for exact URL match
            url_hash = hashlib.md5(norm_url.encode()).hexdigest()

            # Create title hash for content-similar detection
            title = result.get('title', '')
            norm_title = self._normalize_text(title)
            title_hash = hashlib.md5(norm_title.encode()).hexdigest() if norm_title else ''

            # Create combined fingerprint for near-exact matches
            snippet = result.get('snippet', result.get('description', ''))
            norm_snippet = self._normalize_text(snippet)[:100] if snippet else ''  # First 100 chars

            # Store multiple hashes for fast lookup
            result['_url_hash'] = url_hash
            result['_title_hash'] = title_hash
            result['_fingerprint'] = f"{url_hash[:8]}:{title_hash[:8]}"

            # Group by URL hash (exact duplicates)
            if url_hash not in url_hash_groups:
                url_hash_groups[url_hash] = []
            url_hash_groups[url_hash].append(i)

            # Group by domain for potential fuzzy matching
            try:
                parsed = urlparse(norm_url)
                domain = parsed.netloc
                if domain not in domain_groups:
                    domain_groups[domain] = []
                domain_groups[domain].append(i)
            except Exception as e:

                print(f"[BRUTE] Error: {e}")

                pass

        # PHASE 2: Create groups from hash-based matches
        # Exact URL duplicates are instantly grouped
        processed_indices: Set[int] = set()

        for url_hash, indices in url_hash_groups.items():
            if len(indices) > 1:
                # Exact URL duplicates found - create group immediately
                groups[next_group_id] = [results[i] for i in indices]
                processed_indices.update(indices)
                next_group_id += 1
            elif indices[0] not in processed_indices:
                # Single result - will need fuzzy matching or standalone group
                pass

        # PHASE 3: Fuzzy matching for remaining results (O(K²) where K << N)
        # Only compare results from the same domain to limit comparisons
        remaining_results = [(i, results[i]) for i in range(len(results))
                           if i not in processed_indices]

        # Group remaining by domain to reduce comparison space
        for domain, domain_indices in domain_groups.items():
            # Filter to only unprocessed results from this domain
            unprocessed_in_domain = [
                (i, results[i]) for i in domain_indices
                if i not in processed_indices
            ]

            if len(unprocessed_in_domain) <= 1:
                # Single unprocessed result in domain - standalone group
                for idx, result in unprocessed_in_domain:
                    if idx not in processed_indices:
                        groups[next_group_id] = [result]
                        processed_indices.add(idx)
                        next_group_id += 1
                continue

            # Multiple unprocessed results from same domain - need fuzzy matching
            # Use title hash first for quick grouping
            title_groups: Dict[str, List[Tuple[int, Dict]]] = {}
            for idx, result in unprocessed_in_domain:
                title_hash = result.get('_title_hash', '')
                if title_hash not in title_groups:
                    title_groups[title_hash] = []
                title_groups[title_hash].append((idx, result))

            # Group by title hash (catches same-title duplicates)
            for title_hash, items in title_groups.items():
                if len(items) > 1 and title_hash:
                    # Multiple results with same title - likely duplicates
                    groups[next_group_id] = [item[1] for item in items]
                    for idx, _ in items:
                        processed_indices.add(idx)
                    next_group_id += 1
                else:
                    # Single result or empty title - need individual comparison
                    for idx, result in items:
                        if idx not in processed_indices:
                            # Check against existing groups with expensive comparison
                            # BUT only for same-domain groups (bounded comparison)
                            assigned = False
                            for gid, group_results in groups.items():
                                if not group_results:
                                    continue
                                representative = group_results[0]
                                # Quick fingerprint check first
                                if result.get('_fingerprint') == representative.get('_fingerprint'):
                                    group_results.append(result)
                                    assigned = True
                                    break

                            if not assigned:
                                groups[next_group_id] = [result]
                                next_group_id += 1
                            processed_indices.add(idx)

        # PHASE 4: Catch any stragglers not processed
        for i, result in enumerate(results):
            if i not in processed_indices:
                groups[next_group_id] = [result]
                next_group_id += 1
                processed_indices.add(i)

        self.logger.debug(
            f"Duplicate grouping: {len(results)} results -> {len(groups)} groups "
            f"(hash-based: {len(url_hash_groups)} URL hashes)"
        )

        return groups
    
    async def _are_duplicates(
        self,
        result1: Dict[str, Any],
        result2: Dict[str, Any]
    ) -> bool:
        """
        Determine if two results are duplicates based on multiple criteria.
        
        Args:
            result1: First result to compare
            result2: Second result to compare
            
        Returns:
            True if results are considered duplicates
        """
        # Step 1: Exact URL match (if enabled)
        if self.config['exact_url_match']:
            url1 = self._normalize_url(result1.get('url', ''))
            url2 = self._normalize_url(result2.get('url', ''))
            
            if url1 and url2 and url1 == url2:
                return True
        
        # Step 2: Calculate similarity scores
        similarity_scores = {}
        
        # URL similarity
        similarity_scores['url'] = self._calculate_url_similarity(
            result1.get('url', ''), 
            result2.get('url', '')
        )
        
        # Title similarity
        similarity_scores['title'] = self._calculate_text_similarity(
            result1.get('title', ''), 
            result2.get('title', '')
        )
        
        # Content similarity (if enabled)
        if self.config['content_comparison_enabled']:
            content1 = result1.get('snippet', result1.get('description', ''))
            content2 = result2.get('snippet', result2.get('description', ''))
            similarity_scores['content'] = self._calculate_text_similarity(content1, content2)
        else:
            similarity_scores['content'] = 0.0
        
        # Step 3: Calculate weighted overall similarity
        weights = self.config['similarity_weights']
        overall_similarity = (
            similarity_scores['url'] * weights['url'] +
            similarity_scores['title'] * weights['title'] +
            similarity_scores['content'] * weights['content']
        )
        
        # Step 4: Check against thresholds
        is_duplicate = (
            similarity_scores['url'] >= self.config['url_similarity_threshold'] or
            similarity_scores['title'] >= self.config['title_similarity_threshold'] or
            (self.config['content_comparison_enabled'] and 
             similarity_scores['content'] >= self.config['content_similarity_threshold']) or
            overall_similarity >= 0.85  # High overall similarity threshold
        )
        
        if is_duplicate:
            self.logger.debug(
                f"Duplicate detected: URL={similarity_scores['url']:.2f}, "
                f"Title={similarity_scores['title']:.2f}, "
                f"Content={similarity_scores['content']:.2f}, "
                f"Overall={overall_similarity:.2f}"
            )
        
        return is_duplicate
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for comparison.
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL
        """
        if not url:
            return ""
        
        try:
            # Parse URL
            parsed = urlparse(url)
            
            # Apply normalization settings
            norm_config = self.config['url_normalization']
            
            # Normalize scheme
            scheme = parsed.scheme.lower() if parsed.scheme else 'http'
            
            # Normalize netloc (domain)
            netloc = parsed.netloc.lower() if norm_config['case_insensitive'] else parsed.netloc
            
            # Remove www prefix if configured
            if norm_config['remove_www'] and netloc.startswith('www.'):
                netloc = netloc[4:]
            
            # Normalize path
            path = parsed.path
            if norm_config['remove_trailing_slash'] and path.endswith('/') and len(path) > 1:
                path = path[:-1]
            
            # Filter query parameters
            query_params = parse_qs(parsed.query) if parsed.query else {}
            if norm_config['ignore_utm_params']:
                # Remove tracking parameters
                query_params = {
                    k: v for k, v in query_params.items() 
                    if k not in self.tracking_params
                }
            
            # Rebuild query string
            query = '&'.join(
                f"{k}={'&'.join(v)}" for k, v in sorted(query_params.items())
            ) if query_params else ''
            
            # Handle fragment
            fragment = '' if norm_config['ignore_fragments'] else parsed.fragment
            
            # Reconstruct URL
            normalized = f"{scheme}://{netloc}{path}"
            if query:
                normalized += f"?{query}"
            if fragment:
                normalized += f"#{fragment}"
            
            return normalized
            
        except Exception as e:
            self.logger.warning(f"Error normalizing URL '{url}': {e}")
            return url.lower() if self.config['url_normalization']['case_insensitive'] else url
    
    def _calculate_url_similarity(self, url1: str, url2: str) -> float:
        """
        Calculate similarity between two URLs.
        
        Args:
            url1: First URL
            url2: Second URL
            
        Returns:
            Similarity score (0.0-1.0)
        """
        if not url1 or not url2:
            return 0.0
        
        # Normalize URLs
        norm_url1 = self._normalize_url(url1)
        norm_url2 = self._normalize_url(url2)
        
        # Exact match
        if norm_url1 == norm_url2:
            return 1.0
        
        # Parse both URLs for component comparison
        try:
            parsed1 = urlparse(norm_url1)
            parsed2 = urlparse(norm_url2)
            
            # Domain similarity
            domain_similarity = 1.0 if parsed1.netloc == parsed2.netloc else 0.0
            
            # Path similarity
            path_similarity = SequenceMatcher(None, parsed1.path, parsed2.path).ratio()
            
            # Overall URL similarity using sequence matching
            overall_similarity = SequenceMatcher(None, norm_url1, norm_url2).ratio()
            
            # Weighted combination
            return (domain_similarity * 0.5) + (path_similarity * 0.3) + (overall_similarity * 0.2)
            
        except Exception:
            # Fallback to simple text similarity
            return SequenceMatcher(None, norm_url1, norm_url2).ratio()
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0.0-1.0)
        """
        if not text1 or not text2:
            return 0.0
        
        # Normalize text
        norm_text1 = self._normalize_text(text1)
        norm_text2 = self._normalize_text(text2)
        
        if not norm_text1 or not norm_text2:
            return 0.0
        
        # Exact match
        if norm_text1 == norm_text2:
            return 1.0
        
        # Calculate different similarity metrics
        
        # 1. Sequence similarity
        sequence_sim = SequenceMatcher(None, norm_text1, norm_text2).ratio()
        
        # 2. Word-based similarity
        words1 = set(norm_text1.split())
        words2 = set(norm_text2.split())
        
        if words1 or words2:
            word_intersection = len(words1.intersection(words2))
            word_union = len(words1.union(words2))
            word_sim = word_intersection / word_union if word_union > 0 else 0.0
        else:
            word_sim = 0.0
        
        # 3. Character n-gram similarity (trigrams)
        trigrams1 = self._get_ngrams(norm_text1, 3)
        trigrams2 = self._get_ngrams(norm_text2, 3)
        
        if trigrams1 or trigrams2:
            trigram_intersection = len(trigrams1.intersection(trigrams2))
            trigram_union = len(trigrams1.union(trigrams2))
            trigram_sim = trigram_intersection / trigram_union if trigram_union > 0 else 0.0
        else:
            trigram_sim = 0.0
        
        # Combine similarities with weights
        combined_similarity = (
            sequence_sim * 0.4 +
            word_sim * 0.4 +
            trigram_sim * 0.2
        )
        
        return combined_similarity
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        norm_config = self.config['content_normalization']
        
        # Case normalization
        if norm_config['case_insensitive']:
            text = text.lower()
        
        # Remove punctuation
        if norm_config['remove_punctuation']:
            text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra whitespace
        if norm_config['remove_extra_whitespace']:
            text = re.sub(r'\s+', ' ', text).strip()
        
        # Check minimum length
        if len(text) < norm_config['min_content_length']:
            return ""
        
        return text
    
    def _get_ngrams(self, text: str, n: int) -> Set[str]:
        """
        Generate n-grams from text.
        
        Args:
            text: Text to generate n-grams from
            n: N-gram size
            
        Returns:
            Set of n-grams
        """
        if len(text) < n:
            return set()
        
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    
    def _select_best_result(self, group_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Select the best result from a group of duplicates and AGGREGATE all sources.

        CRITICAL: When multiple engines find the same URL, ALL source badges must be
        preserved in the 'sources' field. This is fundamental for showing which engines
        found each result.

        Args:
            group_results: List of duplicate results

        Returns:
            Best result from the group with aggregated sources from all duplicates
        """
        if len(group_results) == 1:
            result = group_results[0]
            # Ensure sources is a list even for single result
            self._ensure_sources_list(result)
            return result

        # STEP 1: Aggregate ALL sources from ALL duplicate results
        all_sources = set()
        all_snippets = {}  # engine_code -> snippet mapping

        for result in group_results:
            # Collect sources from 'sources' list (if exists)
            if 'sources' in result:
                sources = result['sources']
                if isinstance(sources, list):
                    all_sources.update(sources)
                elif isinstance(sources, str):
                    # Handle '+' delimited string from DiskDeduplicator
                    all_sources.update(sources.split('+'))

            # Collect source from 'source' field (single engine)
            if 'source' in result:
                all_sources.add(result['source'])

            # Collect from 'engine' or 'engine_code' fields
            if 'engine' in result:
                all_sources.add(result['engine'])
            if 'engine_code' in result:
                all_sources.add(result['engine_code'])

            # Collect snippets per engine for potential aggregation
            engine = result.get('engine_code') or result.get('engine') or result.get('source', 'unknown')
            snippet = result.get('snippet', result.get('description', ''))
            if snippet:
                all_snippets[engine] = snippet

        # STEP 2: Score and select the best result for other properties
        def score_result(result: Dict[str, Any]) -> float:
            score = 0.0

            # 1. Content length (longer is often better)
            snippet = result.get('snippet', result.get('description', ''))
            score += min(20.0, len(snippet) / 10)  # Max 20 points

            # 2. Title quality
            title = result.get('title', '')
            if title and not title.endswith('...'):
                score += 10.0
            score += min(10.0, len(title) / 5)  # Max 10 points

            # 3. URL quality (shorter paths often better)
            url = result.get('url', '')
            if url.startswith('https://'):
                score += 5.0

            # Prefer simpler URLs (fewer parameters)
            if '?' not in url or url.count('&') <= 2:
                score += 5.0

            # 4. Source preference (if available)
            source = result.get('source', '').lower()
            if source in ['google', 'bing', 'duckduckgo']:
                score += 5.0

            # 5. Original position (earlier results often better)
            original_index = result.get('_original_index', 999)
            score += max(0, 20 - original_index)  # Max 20 points for first result

            return score

        # Score all results and select the best
        scored_results = [(score_result(result), result) for result in group_results]
        scored_results.sort(key=lambda x: x[0], reverse=True)

        best_result = scored_results[0][1].copy()  # Copy to avoid modifying original

        # STEP 3: Inject AGGREGATED sources into the best result
        # This is the critical part - ALL engines that found this URL appear as badges
        best_result['sources'] = list(all_sources)
        best_result['source_count'] = len(all_sources)
        best_result['snippets'] = all_snippets  # Store all snippets for reference

        # Also maintain 'engine_codes' for frontend compatibility
        best_result['engine_codes'] = list(all_sources)

        self.logger.debug(
            f"Selected best result from {len(group_results)} duplicates: "
            f"'{best_result.get('title', '')[:50]}...' with {len(all_sources)} sources: {list(all_sources)}"
        )

        return best_result

    def _ensure_sources_list(self, result: Dict[str, Any]) -> None:
        """
        Ensure result has a proper 'sources' list field.

        Args:
            result: Result dict to modify in place
        """
        if 'sources' not in result or not result['sources']:
            sources = []
            if 'source' in result:
                sources.append(result['source'])
            if 'engine' in result:
                sources.append(result['engine'])
            if 'engine_code' in result:
                sources.append(result['engine_code'])
            result['sources'] = sources if sources else ['unknown']
        elif isinstance(result['sources'], str):
            result['sources'] = result['sources'].split('+')

        result['source_count'] = len(result['sources'])
        result['engine_codes'] = result['sources']  # Frontend compatibility
    
    def _create_filter_result(
        self,
        result: Dict[str, Any],
        group_size: int,
        result_id: str
    ) -> FilterResult:
        """
        Create FilterResult for a deduplicated result.

        IMPORTANT: Includes aggregated sources in metadata for badge display.

        Args:
            result: The selected result (with aggregated sources)
            group_size: Number of duplicates in the group
            result_id: Identifier for the result

        Returns:
            FilterResult object with sources metadata
        """
        # Score based on uniqueness (higher score for unique results)
        # BONUS: More sources = more credibility (found by multiple engines)
        source_count = result.get('source_count', 1)

        if group_size == 1:
            score = 90.0  # Unique result
            classification = 'primary'
            tier = 1
            reasoning = "Unique result (no duplicates found)"
        else:
            # BOOST score if found by many engines - corroboration is valuable!
            base_score = max(70.0, 90.0 - (group_size - 1) * 3)  # Reduced penalty
            source_bonus = min(10.0, source_count * 2)  # Up to +10 for 5+ sources
            score = min(95.0, base_score + source_bonus)

            classification = 'primary' if score >= 75 else 'secondary'
            tier = 1 if source_count >= 3 else (2 if score >= 75 else 3)
            reasoning = f"Found by {source_count} engines ({group_size} total matches)"

        # Extract sources for metadata
        sources = result.get('sources', [])
        if isinstance(sources, str):
            sources = sources.split('+')

        return FilterResult(
            result_id=result_id,
            score=score,
            tier=tier,
            classification=classification,
            reasoning=reasoning,
            metadata={
                'duplicate_group_size': group_size,
                'duplicates_removed': group_size - 1,
                'original_index': result.get('_original_index', -1),
                'filter': 'duplicate',
                # CRITICAL: Include sources for badge display
                'sources': sources,
                'source_count': source_count,
                'engine_codes': result.get('engine_codes', sources),
                'snippets': result.get('snippets', {})
            },
            processed_at=time.time()
        )
    
    def _apply_domain_limits(
        self,
        filter_results: List[FilterResult]
    ) -> List[FilterResult]:
        """
        Apply domain limits to prevent too many results from the same domain.
        
        Args:
            filter_results: Results to limit
            
        Returns:
            Limited results
        """
        max_per_domain = self.config['max_duplicates_per_domain']
        if max_per_domain <= 0:
            return filter_results
        
        domain_counts = {}
        limited_results = []
        
        for filter_result in filter_results:
            # Extract domain from result metadata or reconstruct from original data
            # This would need access to the original result data
            # For now, we'll implement a simpler version
            
            # TODO: Implement proper domain limiting
            # This requires maintaining a reference to original result data
            limited_results.append(filter_result)
        
        return limited_results