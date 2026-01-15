"""
GPT Integration Module for Search_Engineer
Provides GPT 4.1-nano integration for categorization and other AI tasks
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI, OpenAI
import time

# Initialize logger
logger = logging.getLogger(__name__)

# Global client instances
gpt_model = None
async_client = None
sync_client = None

# Model configuration
DEFAULT_MODEL = "gpt-4.1-nano"  # Use GPT 4.1-nano as default
FALLBACK_MODEL = "gpt-3.5-turbo"  # Fallback if 4.1-nano not available

def configure_gpt(api_key: Optional[str] = None) -> bool:
    """
    Configure GPT client with API key
    Returns True if successful, False otherwise
    """
    global gpt_model, async_client, sync_client
    
    # Get API key from parameter or environment
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        logger.error("No OpenAI API key provided")
        return False
    
    try:
        # Initialize both async and sync clients
        async_client = AsyncOpenAI(api_key=api_key)
        sync_client = OpenAI(api_key=api_key)
        
        # Set the model (will be validated on first use)
        gpt_model = DEFAULT_MODEL
        
        logger.info(f"GPT configured successfully with model: {gpt_model}")
        print(f"GPT: Configured with API key length: {len(api_key)}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to configure GPT: {e}")
        print(f"GPT: Configuration failed: {e}")
        return False

async def generate_with_gpt_retry(
    prompt: str, 
    max_retries: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    response_format: Optional[Dict] = None
) -> str:
    """
    Generate response from GPT with retry logic
    Supports both regular and structured output formats
    """
    global async_client, gpt_model
    
    if not async_client:
        if not configure_gpt():
            raise ValueError("GPT not configured and unable to auto-configure")
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Prepare the API call parameters
            params = {
                "model": gpt_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # Add response format if specified (for structured output)
            if response_format:
                params["response_format"] = response_format
            
            # Make the API call
            response = await async_client.chat.completions.create(**params)
            
            # Extract and return the response
            return response.choices[0].message.content
            
        except Exception as e:
            last_error = e
            error_str = str(e)
            
            # Check if it's a model availability error
            if "model" in error_str.lower() and gpt_model == DEFAULT_MODEL:
                logger.warning(f"Model {DEFAULT_MODEL} not available, falling back to {FALLBACK_MODEL}")
                gpt_model = FALLBACK_MODEL
                continue
            
            # Rate limiting
            if "rate_limit" in error_str.lower():
                wait_time = (attempt + 1) * 2  # Exponential backoff
                logger.warning(f"Rate limit hit, waiting {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            
            # Other errors
            logger.error(f"GPT API error (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Brief pause between retries
    
    # If all retries failed, raise the last error
    raise last_error or Exception("Failed to generate GPT response")

def generate_with_gpt_sync(
    prompt: str,
    max_retries: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    response_format: Optional[Dict] = None
) -> str:
    """
    Synchronous version of generate_with_gpt_retry
    """
    global sync_client, gpt_model
    
    if not sync_client:
        if not configure_gpt():
            raise ValueError("GPT not configured and unable to auto-configure")
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Prepare the API call parameters
            params = {
                "model": gpt_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # Add response format if specified
            if response_format:
                params["response_format"] = response_format
            
            # Make the API call
            response = sync_client.chat.completions.create(**params)
            
            # Extract and return the response
            return response.choices[0].message.content
            
        except Exception as e:
            last_error = e
            error_str = str(e)
            
            # Check if it's a model availability error
            if "model" in error_str.lower() and gpt_model == DEFAULT_MODEL:
                logger.warning(f"Model {DEFAULT_MODEL} not available, falling back to {FALLBACK_MODEL}")
                gpt_model = FALLBACK_MODEL
                continue
            
            # Rate limiting
            if "rate_limit" in error_str.lower():
                wait_time = (attempt + 1) * 2
                logger.warning(f"Rate limit hit, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            
            logger.error(f"GPT API error (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(1)
    
    raise last_error or Exception("Failed to generate GPT response")

async def categorize_urls_with_gpt(
    urls: List[Dict[str, str]], 
    categories: List[str]
) -> Dict[str, str]:
    """
    Categorize URLs using GPT
    Returns mapping of URL to category
    """
    # Prepare the prompt
    urls_text = []
    for i, item in enumerate(urls):
        text = f"{i}. URL: {item['url']}"
        if item.get('title'):
            text += f" | Title: {item['title'][:100]}"
        if item.get('description'):
            text += f" | Description: {item['description'][:200]}"
        urls_text.append(text)
    
    categories_text = "\n".join(f"- {cat}" for cat in categories)
    
    prompt = f"""Categorize these URLs into EXACTLY one of these categories:
{categories_text}

Consider the URL structure, domain, title, and description.
Choose the single most appropriate category for each URL.

URLs to categorize:
{chr(10).join(urls_text)}

Return ONLY a JSON object mapping the index number to category, like:
{{"0": "news media", "1": "corporate website", "2": "blogs"}}

Use ONLY the exact category names provided above."""

    try:
        response = await generate_with_gpt_retry(prompt, temperature=0.3)
        
        # Clean up response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:].strip()
        if response.endswith("```"):
            response = response[:-3].strip()
        
        # Parse and validate JSON
        result = json.loads(response)
        
        # Validate categories
        valid_result = {}
        for idx, category in result.items():
            if category in categories:
                valid_result[idx] = category
            else:
                logger.warning(f"Invalid category '{category}' for index {idx}, using 'miscellaneous'")
                valid_result[idx] = "miscellaneous"
        
        return valid_result
        
    except Exception as e:
        logger.error(f"Failed to categorize URLs with GPT: {e}")
        # Return empty dict on failure
        return {}

# Auto-configure on import if API key is available
if os.getenv("OPENAI_API_KEY"):
    configure_gpt()

# Export public API
__all__ = [
    'configure_gpt',
    'generate_with_gpt',
    'generate_with_gpt_retry',
    'categorize_urls_with_gpt',
    'async_client',
    'gpt_model',
    'DEFAULT_MODEL',
    'FALLBACK_MODEL'
]