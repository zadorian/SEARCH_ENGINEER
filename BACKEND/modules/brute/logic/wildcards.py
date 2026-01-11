# Wildcards

# * or *1 - exactly 1 word between terms
# ** or *2 - exactly 2 words between terms 
# *** or *3 - exactly 3 words between terms

from typing import List, Dict
import asyncio
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'engines'))

# Import search engines from the correct modules
from exact_phrase_recall_runner_google import GoogleSearch
from exact_phrase_recall_runner_bing import BingSearch

# Import brain module for AI functionality
try:
    from brain import get_ai_brain, AIRequest, TaskType
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("Warning: AI brain module not available")

class WildcardSearch:
    """Handles wildcard searches using AROUND/NEAR operators with AI enhancement"""
    
    def __init__(self):
        self.google = GoogleSearch()
        self.bing = BingSearch()
        self.ai_brain = get_ai_brain() if AI_AVAILABLE else None
    
    def parse_wildcards(self, query: str) -> Dict[str, int]:
        """Parse wildcard operators into word counts"""
        # Remove any quotes from the query first
        query = query.replace('"', '')
        parts = query.split()
        operators = {}
        
        for i, part in enumerate(parts):
            if part.startswith("*"):
                if part.replace("*", "").isdigit():
                    # Handle *1, *2, *3 syntax
                    operators[i] = int(part.replace("*", ""))
                else:
                    # Handle *, **, *** syntax
                    operators[i] = len(part)
                    
        return operators

    async def predict_gap_fillers(self, term1: str, term2: str, gap_size: int) -> List[str]:
        """Use AI to predict words that might appear between the terms"""
        if not self.ai_brain or not AI_AVAILABLE:
            return []
            
        prompt = f"""
        Predict {gap_size} words that might naturally appear between "{term1}" and "{term2}" in text.
        Return only the words, separated by spaces.
        Example: If term1="house" and term2="street" and gap_size=1, you might return "on".
        """
        
        try:
            # Use the brain module's predict_gap_fillers function
            from brain import predict_gap_fillers
            words = await predict_gap_fillers(term1, term2, gap_size)
            return words[:gap_size]  # Ensure we only get the requested number of words
        except Exception as e:
            print(f"Error predicting gap fillers: {e}")
            return []

    async def search_with_wildcards(self, query: str, max_results: int = 30):
        """Execute search using AROUND/NEAR operators with AI enhancement"""
        query = query.replace('"', '')
        parts = query.split()
        operators = self.parse_wildcards(query)
        
        if not operators:
            return await self.basic_search(query, max_results)
            
        # Build enhanced queries
        term_pairs = []
        enhanced_queries = []
        
        for i, count in operators.items():
            if i > 0 and i < len(parts) - 1:
                term1 = parts[i-1].lower()
                term2 = parts[i+1].lower()
                term_pairs.append((term1, term2, count))
                
                # Get AI predictions for gap fillers
                gap_fillers = await self.predict_gap_fillers(term1, term2, count)
                if gap_fillers:
                    # Add exact phrase query with predicted words
                    exact_query = f'{term1} {" ".join(gap_fillers)} {term2}'
                    enhanced_queries.append(exact_query)
                
                # Add AROUND/NEAR queries
                google_query = query.replace(parts[i], f'AROUND({count})')
                bing_query = query.replace(parts[i], f'near:{count}')
                enhanced_queries.extend([google_query, bing_query])
        
        # Execute all queries and aggregate results
        all_results = []
        for q in enhanced_queries:
            print(f"\nTrying query: {q}")
            try:
                google_results = self.google.search(q, max_results * 2)
                all_results.extend(google_results)
            except Exception as e:
                print(f"Google search error: {e}")
            
            try:
                bing_results = self.bing.search(q, max_results * 2)
                all_results.extend(bing_results)
            except Exception as e:
                print(f"Bing search error: {e}")
        
        # Filter results for exact word distances
        filtered_results = []
        seen_urls = set()
        
        for result in all_results:
            if result['url'] in seen_urls:
                continue
                
            snippet = result.get('snippet', '').lower()
            sentences = snippet.split('.')
            
            valid = False
            for term1, term2, required_distance in term_pairs:
                for sentence in sentences:
                    words = [w.strip('.,!?()[]{}":;') for w in sentence.split()]
                    
                    for i in range(len(words) - (required_distance + 2)):
                        if (words[i] == term1 and 
                            words[i + required_distance + 1] == term2):
                            between_words = words[i+1:i+required_distance+1]
                            if len(between_words) == required_distance:
                                print(f"\nFound exact match: ...{' '.join(words[i:i+required_distance+2])}...")
                                valid = True
                                break
                    if valid:
                        break
                if valid:
                    break
            
            if valid:
                filtered_results.append(result)
                seen_urls.add(result['url'])
                if len(filtered_results) >= max_results:
                    break
        
        if not filtered_results:
            print("\nNo results found with exact word distance requirements.")
            if gap_fillers:
                print(f"\nSuggested phrase: {term1} {' '.join(gap_fillers)} {term2}")
            print("\nTry:")
            print("1. Different word forms (singular/plural, tense)")
            print("2. Different word order")
            print("3. A smaller word distance")
            print("4. More common terms")
        
        return filtered_results

async def main():
    """Interactive CLI for wildcard search"""
    searcher = WildcardSearch()
    
    print("\nWildcard Search")
    print("Supported operators:")
    print("* or *1 - exactly 1 word")
    print("** or *2 - exactly 2 words")
    print("*** or *3 - exactly 3 words")
    print("\nEnter your search query (Ctrl+C to exit)")
    
    while True:
        try:
            query = input("\nSearch: ")
            results = await searcher.search_with_wildcards(query)
            
            print(f"\nFound {len(results)} total results:")
            for i, result in enumerate(results, 1):
                print(f"\n{i}. {result['url']}")
                print(f"   {result.get('snippet', '')}")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())