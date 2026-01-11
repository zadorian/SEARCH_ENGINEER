"""
Snippet Aggregator - Combine snippets from multiple engines for the same URL
"""

import re
from typing import List, Dict, Set, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class SnippetAggregator:
    """Aggregate snippets from multiple sources for the same URL"""
    
    def __init__(self):
        self.url_snippets = defaultdict(list)  # URL -> [(snippet, engine)]
        self.url_titles = defaultdict(set)     # URL -> set of titles
        self.url_metadata = defaultdict(dict)  # URL -> metadata
        
    def add_result(self, result: Dict) -> None:
        """Add a result from any engine"""
        url = result.get('url', '').strip()
        if not url:
            return
            
        # Collect snippet
        snippet = result.get('snippet') or result.get('description') or ''
        engine = result.get('source', 'unknown')
        
        if snippet:
            self.url_snippets[url].append((snippet, engine))
        
        # Collect title
        title = result.get('title', '')
        if title:
            self.url_titles[url].add(title)
        
        # Collect other metadata
        for key in ['date', 'author', 'type', 'language']:
            if key in result and result[key]:
                if key not in self.url_metadata[url]:
                    self.url_metadata[url][key] = result[key]
    
    def aggregate_snippets(self, url: str) -> str:
        """
        Aggregate all snippets for a URL into the longest possible text
        
        Strategy:
        1. Remove duplicates while preserving unique information
        2. Merge overlapping snippets
        3. Order by relevance/completeness
        4. Return the most comprehensive aggregate
        """
        if url not in self.url_snippets:
            return ""
        
        snippets = self.url_snippets[url]
        if not snippets:
            return ""
        
        # Clean and normalize snippets
        cleaned_snippets = []
        for snippet, engine in snippets:
            cleaned = self._clean_snippet(snippet)
            if cleaned:
                cleaned_snippets.append((cleaned, engine))
        
        if not cleaned_snippets:
            return ""
        
        # If only one snippet, return it
        if len(cleaned_snippets) == 1:
            return cleaned_snippets[0][0]
        
        # Find overlaps and merge
        merged = self._merge_overlapping_snippets(cleaned_snippets)
        
        # If we couldn't merge, concatenate unique parts
        if len(merged) > 1:
            return self._concatenate_unique_parts(merged)
        
        return merged[0]
    
    def _clean_snippet(self, snippet: str) -> str:
        """Clean and normalize a snippet"""
        snippet = re.sub(r'\s+', ' ', snippet.strip())
        snippet = re.sub(r'\.{3,}$', '', snippet)
        snippet = re.sub(r'^\.{3,}', '', snippet)
        snippet = snippet.replace('&amp;', '&')
        snippet = snippet.replace('&lt;', '<')
        snippet = snippet.replace('&gt;', '>')
        snippet = snippet.replace('&quot;', '"')
        snippet = snippet.replace('&#39;', "'")
        return snippet.strip()
    
    def _merge_overlapping_snippets(self, snippets: List[Tuple[str, str]]) -> List[str]:
        """
        Merge snippets that have overlapping content
        
        Example:
        Snippet 1: "The quick brown fox jumps over..."
        Snippet 2: "...fox jumps over the lazy dog"
        Result: "The quick brown fox jumps over the lazy dog"
        """
        snippets.sort(key=lambda x: len(x[0]), reverse=True)
        
        merged = []
        used: Set[int] = set()
        
        for i, (snippet1, _) in enumerate(snippets):
            if i in used:
                continue
                
            current_merged = snippet1
            used.add(i)
            
            for j, (snippet2, _) in enumerate(snippets):
                if j in used:
                    continue
                overlap_pos = self._find_overlap(current_merged, snippet2)
                if overlap_pos is not None:
                    if overlap_pos[0] == 'prefix':
                        current_merged = snippet2[:overlap_pos[1]] + current_merged
                    else:
                        current_merged = current_merged + snippet2[overlap_pos[1]:]
                    used.add(j)
                
            merged.append(current_merged)
        
        return merged
    
    def _find_overlap(self, text1: str, text2: str, min_overlap: int = 20) -> Tuple[str, int] | None:
        """Find if text2 overlaps with text1"""
        for i in range(min_overlap, len(text2)):
            if text1.startswith(text2[i:]):
                return ('prefix', i)
        for i in range(len(text2) - min_overlap):
            if text1.endswith(text2[:len(text2)-i]):
                return ('suffix', len(text2)-i)
        if text1 in text2:
            idx = text2.index(text1)
            return ('prefix', idx) if idx > 0 else ('suffix', len(text1))
        if text2 in text1:
            return None
        return None
    
    def _concatenate_unique_parts(self, snippets: List[str]) -> str:
        """Concatenate snippets, removing duplicate sentences"""
        all_sentences = []
        for snippet in snippets:
            all_sentences.extend(re.split(r'(?<=[.!?])\s+', snippet))
        
        seen = set()
        unique_sentences = []
        for sentence in all_sentences:
            sentence_lower = sentence.lower().strip()
            if sentence_lower and sentence_lower not in seen:
                seen.add(sentence_lower)
                unique_sentences.append(sentence)
        
        result = ' '.join(unique_sentences)
        if result and not result[-1] in '.!?':
            result += '.'
        return result
