from typing import Dict, Optional, List, Any
import traceback
import sys
import time
import re
import logging
from pathlib import Path
# from cymonides.indexer.logging_config import debug_logger, progress_logger
# from tags.base.scenarios.scenario_ai_search import AISearchScenario  # Add this import!
from datetime import datetime  # Add this import

logger = logging.getLogger(__name__)
# Use standard logger as debug_logger substitute
debug_logger = logger
progress_logger = logger

# -----------------------------------------------------------------------------
# Project Imports
# -----------------------------------------------------------------------------
# Add project root to path BEFORE imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# External libs
from openai import OpenAI
import google.generativeai as genai

# Local config
from config import config

# -----------------------------------------------------------------------------
# Initialize Clients
# -----------------------------------------------------------------------------
# Import the AI models from the correct location using absolute imports
from AI_models.chatgpt_4o_mini import call_gpt4o_mini  # Using absolute import with hyphen
from AI_models.gemini_flash_1_5 import generate_with_retry as gemini_generate

# Import the new GPT-4 AI searcher with embeddings and batch processing
try:
    from AI_models.ai_search_gpt4 import EnhancedAISearcher, GPT4AISearcher
    enhanced_searcher = EnhancedAISearcher()
    logger.info("Enhanced AI searcher with GPT-4.1 initialized")
except ImportError:
    enhanced_searcher = None
    logger.warning("Enhanced AI searcher not available")

# Initialize OpenAI client using only the API key from config
client = OpenAI(api_key=config.OPENAI_API_KEY)

print(f"DEBUG: Using OpenAI API Key: {config.OPENAI_API_KEY[:5]}*****")  # Masked for security

# Also initialize Gemini if needed
genai.configure(api_key=config.GEMINI_API_KEY)

# WARNING: DO NOT MODIFY THE MODEL NAME BELOW!
MODEL_NAME = "gpt-4o-mini"  # This must stay as gpt-4o-mini - DO NOT CHANGE!

# -----------------------------------------------------------------------------
# (Optional) Gemini generator function
# -----------------------------------------------------------------------------
def generate_with_gemini(prompt: str, max_retries: int = 3, delay: float = 1.0) -> Optional[str]:
    """Generate content using Gemini with retry logic"""
    model = genai.GenerativeModel('gemini-pro')
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            else:
                print(f"Empty Gemini response on attempt {attempt + 1}")
                
        except Exception as e:
            print(f"Gemini attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                print("Max retries reached for Gemini")
                return None
                
    return None


# -----------------------------------------------------------------------------
# Modified SINGLE-PASS approach (ensuring the source URL is present)
# -----------------------------------------------------------------------------
async def analyze_with_ai(query: str, batch_text: List[str], domain: str, chunk_range: str) -> Optional[str]:
    """
    Performs a single-pass analysis using AI.
    The answer MUST _begin_ with the source URL(s).
    If the AI response does not begin with a valid source URL, we retry up to three times.
    As a fallback, we prepend a default URL derived from the domain.
    """
    analysis_prompt = f"""Based ONLY on the following content chunk, answer the question: {query}

Content from {domain} ({chunk_range}):
{chr(10).join(batch_text)}

IMPORTANT:
1. Use only the facts from the provided content.
2. Your answer MUST be divided in two parts:
   - Part One: List ONLY the exact source URL(s) where each fact is derived.
     Each URL must be on its own line in the following format:
         Source URL: https://example.com/page
   - Part Two: Provide a detailed analysis.
3. CRITICAL EXTRACTION REQUIREMENTS:
   - Extract ALL entities: people (full names, family), companies, institutions, universities, locations
   - Extract ALL relationships: who knows whom, family ties, professional connections
   - Extract ALL personal details: education, career, hobbies, preferences, quotes, dates
   - If query asks for "everything" - include EVERYTHING, no matter how minor
4. End your answer with an EXACT line that reads: CONCLUSIVE: Yes or CONCLUSIVE: No.
"""
    try:
        # Initial call to the AI
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "You are a comprehensive information extraction AI. When analyzing content:\n"
                               "1. Extract ALL entities: people, companies, institutions, locations, dates\n"
                               "2. Extract ALL relationships and connections\n"
                               "3. Extract ALL personal details and contextual information\n"
                               "4. NEVER summarize or skip details - include EVERYTHING\n"
                               "5. You MUST always begin your answer with the exact source URL(s) in the required format."
                },
                { "role": "user", "content": analysis_prompt }
            ]
        )
        ai_response = response.choices[0].message.content or ""
        
        # Retry logic: try up to 3 times to force a URL at the beginning.
        max_retries = 3
        retry_count = 0
        while not re.search(r'^Source URL:\s*https?://', ai_response, re.MULTILINE) and retry_count < max_retries:
            retry_prompt = (
                "Your previous answer did not include the required source URLs. "
                "Please provide ONLY the exact source URL(s) from which the provided information was derived, "
                "with each URL on a separate line in the format: 'Source URL: https://example.com/page'."
            )
            retry_response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": "IMPORTANT: Your answer MUST BEGIN with the list of source URLs as specified."
                    },
                    { "role": "user", "content": retry_prompt }
                ]
            )
            urls_part = retry_response.choices[0].message.content.strip()
            # Prepend the obtained URL(s) to the original answer.
            ai_response = urls_part + "\n\n" + ai_response
            retry_count += 1
        
        # Final safety: if still missing a valid URL, prepend a default one based on the domain.
        if not re.search(r'^Source URL:\s*https?://', ai_response, re.MULTILINE):
            default_url = f"Source URL: https://{domain.strip('?').strip()}"
            ai_response = default_url + "\n\n" + ai_response
        
        # Process tags or logging as required.
        try:
            # scenario = AISearchScenario()
            # Comment out scenario-related code
            return ai_response
        except Exception as e:
            print(f"Error creating AI analysis tags: {str(e)}")
            traceback.print_exc()
        
        return ai_response

    except Exception as e:
        debug_logger.error(f"Error in AI analysis: {str(e)}", exc_info=True)
        return f"Error processing AI analysis: {str(e)}"


def _score_page_relevance(url: str, content: str, search_type: str = 'company') -> float:
    """Score a page's relevance for different search types"""
    score = 0.0
    url = url.lower()
    
    # Base relevance patterns for company information
    high_value_patterns = {
        'url': {
            'company': ['about', 'company', 'overview', 'profile', 'history'],
            'people': ['team', 'people', 'management', 'leadership', 'staff'],
            'products': ['products', 'services', 'solutions', 'offerings'],
            'contact': ['contact', 'locations', 'offices']
        },
        'content': {
            'company': ['founded', 'established', 'history', 'mission', 'vision'],
            'people': ['ceo', 'president', 'director', 'board', 'management'],
            'products': ['provide', 'offer', 'deliver', 'product', 'service'],
            'contact': ['email', 'phone', 'address', 'contact']
        }
    }

    # Score based on URL patterns
    for pattern in high_value_patterns['url'].get(search_type, []):
        if pattern in url:
            score += 2.0
            debug_logger.debug(f"URL boost (+2.0) for '{pattern}' in {url}")

    # Penalize deep URLs
    depth = url.count('/')
    penalty = depth * 0.5
    score -= penalty
    if penalty > 0:
        debug_logger.debug(f"Depth penalty (-{penalty}) for {url}")

    # Penalize obviously irrelevant pages
    irrelevant = ['assets/', 'images/', 'css/', 'js/', '.pdf', '.jpg', '.png']
    for pattern in irrelevant:
        if pattern in url:
            score -= 5.0
            debug_logger.debug(f"Irrelevant content penalty (-5.0) for {url}")
            break

    # Score based on content patterns (if content is provided)
    if content:
        content = content.lower()
        for pattern in high_value_patterns['content'].get(search_type, []):
            if pattern in content:
                score += 1.0
                debug_logger.debug(f"Content boost (+1.0) for '{pattern}' in {url}")

    return score


async def handle_ai_search(prompt: str, content: Dict) -> str:
    """Handle AI search using two-step analysis."""
    try:
        # Use the two-step analysis approach
        return await handle_ai_search_two_step(prompt, content)
    except Exception as e:
        print(f"Error in AI search: {str(e)}")
        traceback.print_exc()
        return f"Error in AI search: {str(e)}"

async def _create_tags(ai_results: List[Dict], prompt: str):
    """Helper function to create and index tags"""
    if ai_results:
        try:
            print("\nCreating and indexing tags...")
            for result in ai_results:
                # scenario = AISearchScenario()
                # Comment out scenario-related code
                created_tags = await scenario.process(
                    query=result['query'],
                    url=result['url'],
                    ai_response=result['response'],
                    search_type="current"
                )
                
                if created_tags:
                    print(f"Created and indexed {len(created_tags)} tags for URL: {result['url']}")
                    print("Tags created:")
                    for tag in created_tags:
                        print(f"- {tag['class_']}: {tag['name']['value']} ({tag['id_']})")
                else:
                    print(f"Failed to create tags for URL: {result['url']}")
                
        except Exception as e:
            print(f"Error creating AI analysis tags: {str(e)}")
            traceback.print_exc()


# -----------------------------------------------------------------------------
#  NEW: Two-Step Approach (unchanged except for potential similar modifications)
# -----------------------------------------------------------------------------
def parse_page_numbers(ai_response: str, max_pages: int) -> List[int]:
    """
    Naive parser to extract 'Page X' references from AI's response,
    returning them as a list of integers (1-based).
    """
    possible = re.findall(r'[Pp]age\s*(\d+)', ai_response)
    chosen = []
    for val in possible:
        try:
            num = int(val)
            if 1 <= num <= max_pages:
                chosen.append(num)
        except ValueError:
            pass
    # Deduplicate while preserving order
    final = []
    for page_idx in chosen:
        if page_idx not in final:
            final.append(page_idx)
    return final


async def select_relevant_urls(query: str, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Let GPT-4 pick which pages are relevant to the query, based on just the URL or a short snippet.
    Returns a subset of `pages`.
    """
    if not pages:
        return []

    # Optionally skip media/binary files you know are not textual:
    text_like_pages = []
    skip_extensions = (".jpg", ".jpeg", ".gif", ".png", ".svg", ".pdf", ".zip", ".rar", "/media/")
    for page in pages:
        url = page.get("url", "").lower()
        if not any(url.endswith(ext) or (ext in url) for ext in skip_extensions):
            text_like_pages.append(page)

    # Make short summaries (URL + snippet) for the model
    summaries = []
    for idx, page in enumerate(text_like_pages):
        url = page.get('url', '')
        snippet = (page.get('text', '') or page.get('content', '') or page.get('raw_text', ''))
        snippet_preview = snippet[:200].replace('\n', ' ')
        summaries.append(f"Page {idx+1}: URL={url}\n  snippet={snippet_preview}...\n")

    # Create the prompt
    content_for_model = f"""
We have {len(text_like_pages)} possible pages (URLs). The user's query is:
    {query}

Below are short summaries (URLs + snippet). 
For each page that seems relevant, explain WHY you think it might contain useful information.
Then list the page numbers in order of likely relevance.

Format your response as:
REASONING:
- Page X: <reason why this page might be relevant>
- Page Y: <reason why this page might be relevant>

SELECTED PAGES: Page X, Page Y, ...

If no pages seem relevant, explain why and say "SELECTED PAGES: none"

Summaries:
{chr(10).join(summaries)}
"""
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an AI that selects relevant web pages based on user queries."},
                {"role": "user", "content": content_for_model}
            ]
        )
        ai_response = response.choices[0].message.content
        print("\n=== Page Selection Analysis ===\n", ai_response, "\n==================================\n")

        # Extract numeric page references from the SELECTED PAGES line
        selected_line = [line for line in ai_response.split('\n') if line.startswith('SELECTED PAGES:')]
        if not selected_line:
            return text_like_pages  # Fallback to all pages if format is wrong
            
        selected_text = selected_line[0].replace('SELECTED PAGES:', '').strip()
        
        if selected_text.lower() == 'none':
            print("\nNo pages were deemed relevant by initial analysis.")
            print("Falling back to analyzing all pages...\n")
            return text_like_pages

        chosen_numbers = parse_page_numbers(selected_text, max_pages=len(text_like_pages))
        if not chosen_numbers:
            print("\nNo pages were successfully parsed from selection.")
            print("Falling back to analyzing all pages...\n")
            return text_like_pages

        # Convert from 1-based to actual pages
        relevant_pages = []
        for idx in chosen_numbers:
            relevant_pages.append(text_like_pages[idx-1])
        return relevant_pages

    except Exception as e:
        print(f"Error selecting relevant URLs: {e}")
        # If something fails, fallback to returning all text-like pages
        return text_like_pages


async def handle_ai_search_two_step(query: str, content: Dict) -> str:
    """Two-step analysis with batched processing of relevant pages."""
    try:
        # Check if we should use enhanced searcher with embeddings
        if enhanced_searcher and len(content.get('pages', [])) > 0:
            # Try to extract domain for caching
            pages = content.get('pages', [])
            domain = None
            if pages and pages[0].get('url'):
                url = pages[0]['url']
                domain = url.split('//')[1].split('/')[0] if '//' in url else None
            
            if domain:
                logger.info(f"Using enhanced AI searcher with embeddings for {domain}")
                return await enhanced_searcher.analyze_cached_content(query, content, domain)
        
        # Fall back to original implementation
        pages = content.get('pages', []) or content.get('urls', [])
        print(f"\nFound {len(pages)} total pages")
        
        # STEP 1: Let AI pick promising URLs
        relevant_pages = await select_relevant_urls(query, pages)
        print(f"\nAI selected {len(relevant_pages)} relevant pages to analyze\n")
        
        urls_with_answers = set()
        all_responses = {}
        
        # STEP 2: Process relevant pages in batches of 4-5
        batch_size = 4
        for i in range(0, len(relevant_pages), batch_size):
            batch = relevant_pages[i:i + batch_size]
            
            # Combine batch content
            batch_text = []
            batch_urls = []
            for page in batch:
                url = page.get('url', '')
                text = page.get('text', '') or page.get('content', '') or page.get('raw_text', '')
                if text:
                    batch_text.append(f"\n=== Content from {url} ===\n{text}\n")
                    batch_urls.append(url)
            
            if not batch_text:
                continue
                
            print(f"Analyzing batch of {len(batch)} pages...")
            
            # Combine all text for analysis
            combined_text = "\n".join(batch_text)
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a literal text analyzer. Extract ONLY factual information "
                            "from the provided content to answer the question. If you cannot find "
                            "a clear answer, say so explicitly."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Question: {query}\n\nContent to analyze:\n{combined_text}"
                    }
                ]
            )
            
            analysis = response.choices[0].message.content
            
            # If we found answers, record them
            if analysis and not analysis.lower().startswith("no "):
                for url in batch_urls:
                    urls_with_answers.add(url)
                    all_responses[url] = analysis
            
            # If we found answers, we can stop
            if urls_with_answers:
                break
        
        # Only show actual results
        final_summary = "\nResults:\n"
        if urls_with_answers:
            for url in urls_with_answers:
                final_summary += f"\nFrom {url}:\n{all_responses[url]}\n"
        else:
            final_summary += "\nNo relevant information found in the analyzed pages."
        
        return final_summary

    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return f"Error in search: {str(e)}"