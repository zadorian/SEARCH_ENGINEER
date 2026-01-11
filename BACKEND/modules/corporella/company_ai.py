import sys
from pathlib import Path

# Add project root to system path (do this before any other imports)
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Now we can import from AI directory
from AI.query_ai import QueryOptimizer
from AI.gemini_flash import generate_with_retry
from AI.chatgpt4o import chat_with_gpt4o
from AI.claude_writing import BusinessAnalyzer

# Rest of the imports
import os
import asyncio
from openai import OpenAI
import tiktoken
from exa_py import Exa
from typing import Dict, List
import json
import google.generativeai as genai
from dotenv import load_dotenv
from config import config  # Add this import at the top

# Initialize OpenAI client
client = OpenAI()

# Initialize AI services (in __init__ or at module level)
genai.configure(api_key=config.GEMINI_API_KEY)



def keyword_search(
    exa_api_key: str,
    search_term: str,
    additional_context: str = "",
    num_results: int = 50
) -> List[Dict]:
    """Enhanced keyword search using Exa with minimal exact phrases"""
    exa = Exa(exa_api_key)
    all_results = []
    seen_urls = set()

    # Normalize company name case (Title Case)
    search_term = search_term.title()
    
    # First, get the base company name without legal form
    base_name = ' '.join(search_term.split()[:-1]) if search_term.lower().split()[-1] in ['ltd', 'limited', 'llc', 'inc', 'corp'] else search_term

    # Create basic search combinations with minimal exact phrases
    search_combinations = [
        f'"{search_term}"',  # Full name with legal form
        f'"{base_name}"'     # Name without legal form
    ]

    # If there's additional context, split into minimal phrases
    if additional_context:
        # Split context into meaningful phrases
        context_phrases = additional_context.split(',')
        for phrase in context_phrases:
            # Clean and normalize each phrase
            clean_phrase = ' '.join(word for word in phrase.strip().split() 
                                  if word.lower() not in ['related', 'to', 'with', 'and', 'aka', 'is'])
            if clean_phrase:
                # Add each clean phrase as a separate search combination
                search_combinations.extend([
                    f'"{search_term}" "{clean_phrase}"',
                    f'"{base_name}" "{clean_phrase}"'
                ])

    print("\n\033[1;34mTrying search combinations:\033[0m")
    for combo in search_combinations:
        print(f"- {combo}")

    try:
        for search_query in search_combinations:
            try:
                response = exa.search_and_contents(
                    search_query,
                    type="keyword",
                    num_results=num_results,
                    text=True,
                    highlights=True
                )
                
                if response and hasattr(response, 'results'):
                    for result in response.results:
                        if result.url not in seen_urls:
                            seen_urls.add(result.url)
                            item = {
                                'title': result.title,
                                'url': result.url,
                                'published_date': result.published_date,
                                'content': result.text,
                                'highlights': result.highlights if hasattr(result, 'highlights') else None,
                                'matched_variation': search_query,
                                'search_term_used': search_query
                            }
                            all_results.append(item)
            
            except Exception as e:
                print(f"\033[1;31mError with search query '{search_query}': {str(e)}\033[0m")
                continue
        
        return all_results
            
    except Exception as e:
        print(f"\033[1;31mError in search: {str(e)}\033[0m")
        return []

class CompanyAI:
    def __init__(self, exa_api_key: str):
        self.exa_api_key = exa_api_key
        self.openai_client = OpenAI()
        self.encoder = tiktoken.encoding_for_model("gpt-4")
        self.max_tokens = 10000
        self.query_optimizer = QueryOptimizer()
        self.exa = Exa(self.exa_api_key)

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string"""
        return len(self.encoder.encode(text))

    def truncate_to_token_limit(self, text: str, limit: int) -> str:
        """Truncate text to stay within token limit"""
        tokens = self.encoder.encode(text)
        if len(tokens) <= limit:
            return text
        return self.encoder.decode(tokens[:limit])

    def _format_content_for_summary(self, results: List[Dict]) -> str:
        """Format the search results with clear source attribution"""
        formatted_content = []
        total_tokens = 0
        
        for idx, result in enumerate(results, 1):
            article_content = f"""
            SOURCE [{idx}]: {result['url']}
            TITLE: {result['title']}
            DATE: {result['published_date']}
            
            CONTENT:
            {result['content']}
            
            HIGHLIGHTS:
            {self._format_highlights(result['highlights'][:3]) if result['highlights'] else 'No highlights available'}
            
            ========================================
            """
            
            tokens = self.count_tokens(article_content)
            if total_tokens + tokens > self.max_tokens:
                break
                
            total_tokens += tokens
            formatted_content.append(article_content)
        
        return "\n".join(formatted_content)

    async def get_dual_summary(
        self, 
        search_term: str, 
        additional_context: str = "",
        num_results: int = 50
    ) -> Dict:
        """Get detailed summaries with careful entity disambiguation"""
        # STEP 1: Get first round search queries
        print("\n\033[1;34mCalling QueryOptimizer for First Round Search Variations...\033[0m")
        search_combinations = self.query_optimizer.optimize_search_query(search_term, additional_context)
        print("\n\033[1;32mQueryOptimizer generated first round variations:\033[0m")
        for combo in search_combinations:
            print(f"- {combo}")

        # STEP 2: Execute first round searches and show results
        print("\n\033[1;34mExecuting First Round Search...\033[0m")
        first_round_results = self._execute_searches(search_combinations, num_results)
        
        if not first_round_results:
            print("\n\033[1;31mNo results found in first round search.\033[0m")
            return {"error": "No results found from Exa search"}

        print("\n\033[1;32mFirst Round Results:\033[0m")
        for result in first_round_results:
            print(f"\nTitle: {result['title']}")
            print(f"URL: {result['url']}")
            print(f"Date: {result['published_date']}")
            print("\nContent:")
            print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
            if result.get('highlights'):
                print("\nHighlights:")
                for highlight in result['highlights'][:3]:  # Show top 3 highlights
                    print(f"- {highlight}")
            print("-" * 80)

        # STEP 3: Get AI summaries of first round
        print("\n\033[1;34mGenerating First Round AI Analysis...\033[0m")
        content_to_summarize = self._format_content_for_summary(first_round_results)
        
        print("\n\033[1;32mGPT Analysis of First Round:\033[0m")
        gpt_summary = self._extract_entities_gpt(content_to_summarize, search_term)
        print(json.dumps(gpt_summary, indent=2))
        
        print("\n\033[1;32mGemini Analysis of First Round:\033[0m")
        gemini_summary = self._extract_entities_gemini(content_to_summarize, search_term)
        print(json.dumps(gemini_summary, indent=2))

        # STEP 4: Get second round queries based on first round analysis
        print("\n\033[1;34mGenerating Second Round Search Queries...\033[0m")
        round_two_combinations = self.query_optimizer.round_two(
            first_round_results=first_round_results,
            original_query=search_term,
            gpt_summary=gpt_summary,
            gemini_summary=gemini_summary
        )
        print("\n\033[1;32mSecond Round Search Queries:\033[0m")
        for combo in round_two_combinations:
            print(f"- {combo}")

        # STEP 5: Execute second round searches and show results
        print("\n\033[1;34mExecuting Second Round Searches...\033[0m")
        second_round_results = self._execute_searches(round_two_combinations, num_results)
        
        print("\n\033[1;32mSecond Round Results:\033[0m")
        for result in second_round_results:
            print(f"\nTitle: {result['title']}")
            print(f"URL: {result['url']}")
            print(f"Date: {result['published_date']}")
            print("\nContent:")
            print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
            if result.get('highlights'):
                print("\nHighlights:")
                for highlight in result['highlights'][:3]:
                    print(f"- {highlight}")
            print("-" * 80)

        # STEP 6: Analyze second round results
        print("\n\033[1;34mAnalyzing Second Round Results...\033[0m")
        second_round_content = self._format_content_for_summary(second_round_results)
        
        print("\n\033[1;32mGPT Analysis of Second Round:\033[0m")
        second_round_gpt = self._extract_entities_gpt(second_round_content, search_term)
        print(json.dumps(second_round_gpt, indent=2))
        
        print("\n\033[1;32mGemini Analysis of Second Round:\033[0m")
        second_round_gemini = self._extract_entities_gemini(second_round_content, search_term)
        print(json.dumps(second_round_gemini, indent=2))

        # STEP 7: Final Claude analysis
        print("\n\033[1;34mGenerating Final Comprehensive Analysis...\033[0m")
        business_analyzer = BusinessAnalyzer()
        combined_analysis = {
            "search_term": search_term,
            "context": additional_context,
            "first_round": {
                "gpt_analysis": gpt_summary,
                "gemini_analysis": gemini_summary
            },
            "second_round": {
                "gpt_analysis": second_round_gpt,
                "gemini_analysis": second_round_gemini
            }
        }

        print("\n\033[1;34mGenerating Comprehensive GPT Analysis...\033[0m")
        comprehensive_prompt = f"""Analyze all the collected information about {search_term} and provide:
        1. Company Overview
        2. Key Personnel and Leadership
        3. Business Activities and Services
        4. Market Position and Relationships
        5. Recent Developments and Changes
        6. Risk Factors or Concerns (if any)
        7. Overall Assessment

        Be specific and factual, only use information from the provided data."""

        gpt_comprehensive = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a business analyst providing detailed company analysis."},
                {"role": "user", "content": f"{comprehensive_prompt}\n\nData:\n{json.dumps(combined_analysis, indent=2)}"}
            ]
        )

        print("\n\033[1;32mComprehensive GPT Analysis:\033[0m")
        print(gpt_comprehensive.choices[0].message.content)

        claude_summary = await business_analyzer.analyze_business_content(
            text=json.dumps(combined_analysis, indent=2),
            output_format="text"
        )
        
        print("\n\033[1;32mClaude's Comprehensive Analysis:\033[0m")
        print(claude_summary if isinstance(claude_summary, str) else claude_summary.get('content', 'Analysis failed'))

        return {
            "search_term": search_term,
            "total_results": len(first_round_results) + len(second_round_results),
            "first_round": {
                "results": first_round_results,
                "gpt_summary": gpt_summary,
                "gemini_summary": gemini_summary
            },
            "second_round": {
                "results": second_round_results,
                "gpt_summary": second_round_gpt,
                "gemini_summary": second_round_gemini
            },
            "claude_analysis": claude_summary if isinstance(claude_summary, str) else claude_summary.get('content', 'Analysis failed')
        }

    def _format_highlights(self, highlights: List[str]) -> str:
        """Format the highlights into a clean string"""
        if not highlights:
            return "No highlights available"
        
        return "\n".join([f"- {highlight}" for highlight in highlights])

    def keyword_search(self, search_term: str, additional_context: str = "") -> List[Dict]:
        """Execute keyword search using optimized queries from QueryOptimizer"""
        queries = self.query_optimizer.optimize_search_query(search_term, additional_context)
        return self._execute_searches(queries)

    def _execute_searches(self, search_combinations: List[str], num_results: int) -> List[Dict]:
        """Helper method to execute a batch of searches using class's exa client"""
        results = []
        seen_urls = set()
        
        for search_query in search_combinations:
            try:
                response = self.exa.search_and_contents(
                    search_query,
                    type="keyword",
                    num_results=num_results,
                    text=True,
                    highlights=True
                )
                
                if response and hasattr(response, 'results'):
                    for result in response.results:
                        if result.url not in seen_urls:
                            seen_urls.add(result.url)
                            item = {
                                'title': result.title,
                                'url': result.url,
                                'published_date': result.published_date,
                                'content': result.text,
                                'highlights': result.highlights if hasattr(result, 'highlights') else None,
                                'matched_variation': search_query,
                                'search_term_used': search_query
                            }
                            results.append(item)
            
            except Exception as e:
                print(f"\033[1;31mError with search query '{search_query}': {str(e)}\033[0m")
                continue
        
        return results

    def _extract_entities_gpt(self, content: str, search_term: str) -> Dict:
        """Extract entities from content using GPT-4"""
        try:
            prompt = f"""Analyze these search results about {search_term} and extract entities mentioned in the text.

            FIRST: Identify if there is an official corporate website for {search_term} in the results.
            If found, note its URL and any key information from it.

            THEN extract:
            1. Company names mentioned (including subsidiaries, partners, competitors)
            2. Product/service names and technologies
            3. Key people (specifically executives, employees mentioned)
            4. Industry terms used in the text
            5. Geographic locations mentioned

            IMPORTANT: Extract ONLY entities that appear in the provided text. Do not make up or infer entities.
            Format as JSON with these exact keys:
            {{
                "official_website": {{
                    "url": "URL if found, null if not",
                    "key_info": "Brief summary of official website content, null if not found"
                }},
                "companies": [],
                "products": [],
                "people": [],
                "terms": [],
                "locations": []
            }}"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an entity extraction specialist. Return only valid JSON."},
                    {"role": "user", "content": f"{prompt}\n\nContent to analyze:\n{content}"}
                ],
                response_format={ "type": "json_object" }
            )
            
            return json.loads(response.choices[0].message.content)
        
        except Exception as e:
            print(f"\n\033[1;31mError in GPT entity extraction: {str(e)}\033[0m")
            return {
                "official_website": {
                    "url": None,
                    "key_info": None
                },
                "companies": [],
                "products": [],
                "people": [],
                "terms": [],
                "locations": []
            }

    def _extract_entities_gemini(self, content: str, search_term: str) -> Dict:
        """Extract entities from content using Gemini"""
        try:
            prompt = f"""Analyze these search results about {search_term} and extract entities mentioned in the text.

            CRITICAL: You MUST return a valid JSON object with EXACTLY these keys:
            {{
                "companies": [],
                "products": [],
                "people": [],
                "terms": [],
                "locations": []
            }}

            RULES:
            1. ONLY return the JSON object, nothing else
            2. NO markdown, NO comments, NO explanations
            3. ONLY include items that appear in the provided text
            4. Each key MUST contain a list, even if empty
            5. NO nested objects, ONLY simple lists

            Content to analyze:
            {content}"""

            response = generate_with_retry(prompt)
            
            # Force proper JSON structure
            try:
                data = json.loads(response)
                required_keys = ['companies', 'products', 'people', 'terms', 'locations']
                return {k: data.get(k, []) for k in required_keys}
            except json.JSONDecodeError:
                print(f"\n\033[1;31mInvalid JSON from Gemini\033[0m")
                return {k: [] for k in required_keys}
            
        except Exception as e:
            print(f"\n\033[1;31mGemini Analysis Error: {str(e)}\033[0m")
            return {
                "companies": [],
                "products": [],
                "people": [],
                "terms": [],
                "locations": []
            }

    def analyze_with_gemini(self, results: List[Dict]) -> Dict:
        """Analyze search results using Google's Gemini"""
        try:
            prompt = f"""Analyze these search results and extract key information into these categories:
            - companies: List of company names
            - products: List of products/services
            - people: List of people names
            - terms: List of business terms, roles and activities
            - locations: List of locations
            
            Format as JSON. Only include items that appear in the text. Return ONLY the JSON."""

            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt + str(results))
            
            # Clean and parse the response
            response_text = response.text.strip()
            
            # Remove any markdown code block syntax
            if '```' in response_text:
                response_text = ''.join(response_text.split('```')[1:-1])
            
            # Remove any "json" language identifier
            response_text = response_text.replace('json\n', '')
            
            # Parse JSON and validate structure
            parsed = json.loads(response_text.strip())
            
            # Ensure all required keys exist
            required_keys = ['companies', 'products', 'people', 'terms', 'locations']
            for key in required_keys:
                if key not in parsed:
                    parsed[key] = []
                
            return parsed

        except Exception as e:
            print(f"\n\033[1;31mGemini Analysis Error: {str(e)}\033[0m")
            return {
                "companies": [],
                "products": [],
                "people": [],
                "terms": [],
                "locations": []
            }

# Modified main function with user prompt
async def main():
    exa_api_key = "ecd713df-48c2-4fb7-b99a-55f3472478b1"
    company_ai = CompanyAI(exa_api_key)
    
    # Add colorful prompt for better visibility
    print("\n" + "="*50)
    print("\033[1;36mWelcome to Company Research AI!\033[0m")
    print("="*50)
    
    while True:
        # Get company name from user
        print("\n\033[1;33mEnter a company name to research (or 'quit' to exit):\033[0m")
        search_term = input("> ").strip()
        
        if search_term.lower() in ['quit', 'exit', 'q']:
            print("\n\033[1;32mThank you for using Company Research AI!\033[0m")
            break
            
        if not search_term:
            print("\n\033[1;31mPlease enter a valid company name.\033[0m")
            continue
        
        print("\n\033[1;33mEnter additional context or filtering criteria (press Enter to skip):\033[0m")
        print("Examples: 'founded in 2020', 'healthcare sector', 'acquisitions', etc.")
        additional_context = input("> ").strip()
            
        print(f"\n\033[1;34mResearching {search_term}...\033[0m")
        if additional_context:
            print(f"\033[1;34mWith additional context: {additional_context}\033[0m")
        
        try:
            results = await company_ai.get_dual_summary(search_term, additional_context)
            
            if results.get("error"):
                print(f"\n\033[1;31mError: {results['error']}\033[0m")
                continue
                
            print("\n\033[1;32mGPT-4 Summary:\033[0m")
            print("=" * 80)
            print(results["first_round"]["gpt_summary"])
            
            print("\n\033[1;32mGemini Summary:\033[0m")
            print("=" * 80)
            print(results["first_round"]["gemini_summary"])
            
            print("\n\033[1;32mSecond Round GPT-4 Summary:\033[0m") 
            print("=" * 80)
            print(results["second_round"]["gpt_summary"])
            
            print("\n\033[1;32mSecond Round Gemini Summary:\033[0m")
            print("=" * 80)
            print(results["second_round"]["gemini_summary"])
            
            print("\n\033[1;32mClaude's Analysis:\033[0m")
            print("=" * 80)
            print(results["claude_analysis"])
            
            # Add clear source reference section with index numbers
            print("\n\033[1;36mSources Referenced:\033[0m")
            print("=" * 80)
            for idx, source in enumerate(results["first_round"]["results"] + results["second_round"]["results"], 1):
                print(f"[{idx}] {source['url']}")
            
        except Exception as e:
            print(f"\n\033[1;31mAn error occurred: {str(e)}\033[0m")
            
        print("\n" + "-"*50)

if __name__ == "__main__":
    print("\nLoaded configuration:")
    print("OPENAI_API_KEY: Set" if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY: Not Set")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n\033[1;32mThank you for using Company Research AI!\033[0m")
    except Exception as e:
        print(f"\n\033[1;31mAn error occurred: {str(e)}\033[0m")
