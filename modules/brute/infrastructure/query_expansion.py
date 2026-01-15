#!/usr/bin/env python3
"""
Query Expansion Module - Centralizes all query variation and expansion logic
Provides synonym generation, misspellings, stemming, and other variations
"""

import re
import logging
from typing import List, Dict, Set, Optional, Tuple
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import NLP libraries for advanced expansion
try:
    import nltk
    from nltk.corpus import wordnet
    from nltk.stem import PorterStemmer, WordNetLemmatizer
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

# Import AI brain for intelligent expansions
try:
    from brain import get_ai_brain, AIRequest, TaskType
    AI_BRAIN_AVAILABLE = True
except ImportError:
    AI_BRAIN_AVAILABLE = False

logger = logging.getLogger(__name__)


class QueryExpander:
    """Handles all query expansion and variation generation"""
    
    def __init__(self):
        self.stemmer = PorterStemmer() if NLTK_AVAILABLE else None
        self.lemmatizer = WordNetLemmatizer() if NLTK_AVAILABLE else None
        self.ai_brain = get_ai_brain() if AI_BRAIN_AVAILABLE else None
        
        # Common misspelling patterns
        self.misspelling_rules = [
            ('ie', 'ei'), ('ei', 'ie'),  # receive/recieve
            ('cc', 'c'), ('c', 'cc'),     # occur/ocur
            ('ll', 'l'), ('l', 'll'),     # until/untill
            ('ss', 's'), ('s', 'ss'),     # business/busines
            ('ff', 'f'), ('f', 'ff'),     # different/diferent
            ('oo', 'o'), ('o', 'oo'),     # choose/chose
            ('ee', 'e'), ('e', 'ee'),     # meet/met
            ('tt', 't'), ('t', 'tt'),     # letter/leter
            ('pp', 'p'), ('p', 'pp'),     # happen/hapen
            ('mm', 'm'), ('m', 'mm'),     # comment/coment
            ('nn', 'n'), ('n', 'nn'),     # beginning/begining
            ('rr', 'r'), ('r', 'rr'),     # interrupt/interupt
            ('gh', ''), ('', 'gh'),       # night/nite
            ('ph', 'f'), ('f', 'ph'),     # photo/foto
            ('ck', 'k'), ('k', 'ck'),     # check/chek
            ('qu', 'kw'), ('kw', 'qu'),   # question/kwestion
            ('x', 'ks'), ('ks', 'x'),     # example/eksample
            ('y', 'i'), ('i', 'y'),       # system/sistem
            ('tion', 'sion'), ('sion', 'tion'),  # action/acsion
            ('ise', 'ize'), ('ize', 'ise'),      # organise/organize
            ('our', 'or'), ('or', 'our'),        # colour/color
            ('re', 'er'), ('er', 're'),          # centre/center
        ]
        
        # Common search modifiers
        self.search_modifiers = {
            'filetype': ['download', 'free', 'pdf', 'doc', 'file', 'document', 'get', 'save'],
            'location': ['near', 'in', 'at', 'around', 'nearby', 'local', 'close to'],
            'date': ['latest', 'recent', 'new', 'current', 'updated', 'today', 'yesterday'],
            'quality': ['best', 'top', 'good', 'quality', 'recommended', 'popular', 'trusted'],
            'action': ['how to', 'guide', 'tutorial', 'learn', 'understand', 'find', 'search'],
        }
    
    async def expand_query(self, query: str, expansion_type: str = 'all', 
                          max_variations: int = 20) -> List[str]:
        """
        Main method to expand a query into variations
        
        Args:
            query: Original search query
            expansion_type: Type of expansion ('all', 'synonyms', 'misspellings', 
                          'stems', 'semantic', 'modifiers')
            max_variations: Maximum number of variations to return
        
        Returns:
            List of query variations
        """
        variations = set()
        variations.add(query)  # Always include original
        
        if expansion_type in ['all', 'synonyms']:
            variations.update(await self.generate_synonyms(query))
        
        if expansion_type in ['all', 'misspellings']:
            variations.update(self.generate_misspellings(query))
        
        if expansion_type in ['all', 'stems']:
            variations.update(self.generate_stems(query))
        
        if expansion_type in ['all', 'semantic']:
            variations.update(await self.generate_semantic_variations(query))
        
        if expansion_type in ['all', 'modifiers']:
            variations.update(self.add_search_modifiers(query))
        
        # Convert to list and limit
        variation_list = list(variations)
        return variation_list[:max_variations]
    
    async def generate_synonyms(self, query: str) -> List[str]:
        """Generate synonyms for query terms"""
        variations = []
        
        # Use AI brain for intelligent synonyms
        if self.ai_brain:
            try:
                prompt = f"""Generate 5-8 synonyms or closely related terms for the search query: "{query}"
                
                Return only the synonym queries, one per line.
                Each should be a complete search query that could replace the original.
                Focus on terms that would find similar content."""
                
                request = AIRequest(
                    task_type=TaskType.QUERY_EXPANSION,
                    prompt=prompt,
                    model_preference="gpt-4.1-nano",
                    temperature=0.7
                )
                
                response = await self.ai_brain.process_request(request)
                if not response.error:
                    synonyms = [line.strip() for line in response.content.strip().split('\n') 
                               if line.strip() and line.strip() != query]
                    variations.extend(synonyms[:5])
            except Exception as e:
                logger.error(f"AI synonym generation error: {e}")
        
        # Use WordNet as fallback
        if NLTK_AVAILABLE and not variations:
            words = query.split()
            for word in words:
                try:
                    synsets = wordnet.synsets(word)
                    for syn in synsets[:3]:  # Limit to avoid explosion
                        for lemma in syn.lemmas()[:3]:
                            synonym = lemma.name().replace('_', ' ')
                            if synonym.lower() != word.lower():
                                # Replace word in query
                                new_query = query.replace(word, synonym)
                                if new_query != query:
                                    variations.append(new_query)
                except Exception as e:
                    logger.debug(f"WordNet error for '{word}': {e}")
        
        return variations
    
    def generate_misspellings(self, query: str) -> List[str]:
        """Generate common misspellings of the query"""
        variations = []
        
        # Apply misspelling rules to each word
        words = query.split()
        for i, word in enumerate(words):
            for pattern, replacement in self.misspelling_rules:
                if pattern in word.lower():
                    # Create misspelled version
                    misspelled = word.lower().replace(pattern, replacement, 1)
                    if misspelled != word.lower():
                        # Replace in query
                        new_words = words.copy()
                        new_words[i] = misspelled
                        variations.append(' '.join(new_words))
        
        # Common keyboard typos (adjacent keys)
        keyboard_adjacents = {
            'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'erfcxs',
            'e': 'wrsdf', 'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yugjbn',
            'i': 'ujko', 'j': 'uikmnh', 'k': 'iolmj', 'l': 'opk',
            'm': 'njk', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol',
            'q': 'wa', 'r': 'etdf', 's': 'awedxz', 't': 'ryfg',
            'u': 'yihj', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc',
            'y': 'tugh', 'z': 'asx'
        }
        
        # Add one typo per word (limit to prevent explosion)
        for i, word in enumerate(words):
            if len(word) > 3:  # Only for longer words
                char_pos = len(word) // 2  # Middle character
                char = word[char_pos].lower()
                if char in keyboard_adjacents:
                    # Replace with adjacent key
                    for adjacent in keyboard_adjacents[char][:2]:  # Limit to 2
                        typo_word = word[:char_pos] + adjacent + word[char_pos+1:]
                        new_words = words.copy()
                        new_words[i] = typo_word
                        variations.append(' '.join(new_words))
        
        return variations[:10]  # Limit misspellings
    
    def generate_stems(self, query: str) -> List[str]:
        """Generate stemmed and lemmatized variations"""
        variations = []
        
        if not NLTK_AVAILABLE:
            return variations
        
        words = query.split()
        
        # Stemming
        stemmed_words = []
        for word in words:
            try:
                stemmed = self.stemmer.stem(word.lower())
                if stemmed != word.lower():
                    stemmed_words.append(stemmed)
                else:
                    stemmed_words.append(word)
            except Exception as e:
                stemmed_words.append(word)
        
        stemmed_query = ' '.join(stemmed_words)
        if stemmed_query != query:
            variations.append(stemmed_query)
        
        # Lemmatization
        lemmatized_words = []
        for word in words:
            try:
                # Try different POS tags
                for pos in ['n', 'v', 'a', 'r']:
                    lemma = self.lemmatizer.lemmatize(word.lower(), pos=pos)
                    if lemma != word.lower():
                        lemmatized_words.append(lemma)
                        break
                else:
                    lemmatized_words.append(word)
            except Exception as e:
                lemmatized_words.append(word)
        
        lemmatized_query = ' '.join(lemmatized_words)
        if lemmatized_query != query and lemmatized_query != stemmed_query:
            variations.append(lemmatized_query)
        
        # Plural/singular variations
        for i, word in enumerate(words):
            # Simple plural/singular rules
            if word.endswith('s') and len(word) > 3:
                singular = word[:-1]
                new_words = words.copy()
                new_words[i] = singular
                variations.append(' '.join(new_words))
            elif not word.endswith('s'):
                plural = word + 's'
                new_words = words.copy()
                new_words[i] = plural
                variations.append(' '.join(new_words))
        
        return variations
    
    async def generate_semantic_variations(self, query: str) -> List[str]:
        """Generate semantically related query variations"""
        variations = []
        
        if not self.ai_brain:
            return variations
        
        try:
            prompt = f"""Generate 5-8 semantically related search queries for: "{query}"
            
            Include:
            1. Queries that would find similar content but use different words
            2. Queries that approach the topic from different angles
            3. More specific and more general versions
            4. Related concepts and topics
            
            Return only the queries, one per line."""
            
            request = AIRequest(
                task_type=TaskType.QUERY_EXPANSION,
                prompt=prompt,
                model_preference="gpt-4.1-nano",
                temperature=0.8
            )
            
            response = await self.ai_brain.process_request(request)
            if not response.error:
                semantic_queries = [line.strip() for line in response.content.strip().split('\n') 
                                  if line.strip() and line.strip() != query]
                variations.extend(semantic_queries[:8])
        except Exception as e:
            logger.error(f"AI semantic generation error: {e}")
        
        return variations
    
    def add_search_modifiers(self, query: str) -> List[str]:
        """Add common search modifiers to the query"""
        variations = []
        
        # Determine likely query type
        query_lower = query.lower()
        query_type = 'general'
        
        if any(ext in query_lower for ext in ['pdf', 'doc', 'xls', 'ppt', 'zip']):
            query_type = 'filetype'
        elif any(loc in query_lower for loc in ['near', 'in', 'location', 'address']):
            query_type = 'location'
        elif any(d in query_lower for d in ['2019', '2020', '2021', '2022', '2023', '2024']):
            query_type = 'date'
        elif any(word in query_lower for word in ['how', 'what', 'why', 'guide', 'tutorial']):
            query_type = 'action'
        
        # Add relevant modifiers
        modifiers = self.search_modifiers.get(query_type, self.search_modifiers['quality'])
        
        for modifier in modifiers[:5]:  # Limit to prevent explosion
            # Add modifier at beginning
            variations.append(f"{modifier} {query}")
            # Add modifier at end
            variations.append(f"{query} {modifier}")
        
        # Add quotes for exact match
        if ' ' in query and not query.startswith('"'):
            variations.append(f'"{query}"')
        
        # Add wildcard variations
        words = query.split()
        if len(words) >= 2:
            # Add wildcard between words
            for i in range(len(words) - 1):
                wildcard_query = ' '.join(words[:i+1] + ['*'] + words[i+1:])
                variations.append(wildcard_query)
        
        return variations
    
    def generate_special_patterns(self, query: str, pattern_type: str) -> List[str]:
        """Generate special search patterns for specific use cases"""
        variations = []
        
        if pattern_type == 'filetype':
            # Directory listing patterns
            variations.extend([
                f'"index of" {query}',
                f'"parent directory" {query}',
                f'intitle:"index of" {query}',
                f'{query} filetype:pdf OR filetype:doc',
                f'"{query}" ext:pdf OR ext:doc',
                f'inurl:download {query}',
                f'inurl:files {query}',
                f'inurl:documents {query}',
            ])
        
        elif pattern_type == 'corporate':
            # Company search patterns
            company = query.strip('"')
            variations.extend([
                f'"{company}" "annual report"',
                f'"{company}" "financial statements"',
                f'"{company}" "investor relations"',
                f'"{company}" incorporated OR inc OR LLC OR Ltd',
                f'"{company}" CEO OR president OR founder',
                f'site:linkedin.com/company "{company}"',
                f'site:bloomberg.com "{company}"',
                f'"{company}" headquarters address',
            ])
        
        elif pattern_type == 'academic':
            # Academic search patterns
            variations.extend([
                f'{query} site:edu',
                f'{query} filetype:pdf site:edu',
                f'"{query}" "research paper"',
                f'"{query}" "journal article"',
                f'"{query}" "thesis" OR "dissertation"',
                f'scholar.google.com {query}',
                f'{query} "peer reviewed"',
                f'{query} "abstract" "introduction" "conclusion"',
            ])
        
        elif pattern_type == 'news':
            # News search patterns
            variations.extend([
                f'{query} "breaking news"',
                f'{query} "latest news"',
                f'{query} site:news.google.com',
                f'{query} "press release"',
                f'{query} "announced today"',
                f'{query} "sources say"',
                f'{query} "according to"',
            ])
        
        return variations
    
    def get_transliterations(self, query: str, target_scripts: List[str] = None) -> List[str]:
        """Generate transliterations for different scripts"""
        variations = []
        
        # This would require additional libraries like 'transliterate' or 'unidecode'
        # For now, return empty list
        # TODO: Implement transliteration support
        
        return variations
    
    def get_character_variants(self, query: str) -> List[str]:
        """Generate character encoding variants"""
        variations = []
        
        # Common character substitutions
        char_variants = {
            'a': ['à', 'á', 'â', 'ä', 'ã', 'å', 'ā'],
            'e': ['è', 'é', 'ê', 'ë', 'ē', 'ė', 'ę'],
            'i': ['ì', 'í', 'î', 'ï', 'ī', 'į'],
            'o': ['ò', 'ó', 'ô', 'ö', 'õ', 'ø', 'ō'],
            'u': ['ù', 'ú', 'û', 'ü', 'ū', 'ų'],
            'c': ['ç', 'ć', 'č'],
            'n': ['ñ', 'ń', 'ň'],
            's': ['ś', 'š', 'ş'],
            'z': ['ź', 'ž', 'ż'],
        }
        
        # Apply variants (limit to prevent explosion)
        words = query.split()
        for i, word in enumerate(words):
            for char, variants in char_variants.items():
                if char in word.lower():
                    # Replace with first variant
                    variant_word = word.lower().replace(char, variants[0], 1)
                    if variant_word != word.lower():
                        new_words = words.copy()
                        new_words[i] = variant_word
                        variations.append(' '.join(new_words))
                        break  # Only one variant per word
        
        return variations[:5]  # Limit variants


# Convenience functions for direct use
async def expand_query_simple(query: str, expansion_type: str = 'all') -> List[str]:
    """Simple function to expand a query"""
    expander = QueryExpander()
    return await expander.expand_query(query, expansion_type)


def get_query_patterns(query: str, pattern_type: str) -> List[str]:
    """Get special search patterns for a query"""
    expander = QueryExpander()
    return expander.generate_special_patterns(query, pattern_type)


if __name__ == "__main__":
    # Test the query expander
    import asyncio
    
    async def test():
        expander = QueryExpander()
        
        test_queries = [
            "python programming",
            "machine learning",
            "covid vaccine",
            "climate change",
            "Apple Inc",
        ]
        
        for query in test_queries:
            print(f"\nOriginal query: {query}")
            print("=" * 50)
            
            # Test all expansion types
            for exp_type in ['synonyms', 'misspellings', 'stems', 'semantic', 'modifiers']:
                variations = await expander.expand_query(query, exp_type)
                print(f"\n{exp_type.title()} variations:")
                for var in variations[:5]:
                    print(f"  - {var}")
    
    asyncio.run(test())