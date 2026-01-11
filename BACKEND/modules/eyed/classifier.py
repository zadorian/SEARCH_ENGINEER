"""
EYE-D Query Classifier
Uses GPT-5-nano/gpt-4.1-nano to classify query types for routing
"""

import os
import re
from typing import Dict, Tuple
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def classify_query_with_gpt(query: str) -> str:
    """
    Use GPT to classify ambiguous queries
    Returns: 'email', 'phone', 'company', 'domain', 'person', or 'unknown'
    """
    if not openai_client:
        logger.warning("OpenAI client not available, falling back to pattern matching")
        return classify_query_pattern(query)[0]

    try:
        prompt = f"""Classify this query into ONE category only:

Categories:
- email (email address with @ symbol)
- phone (phone number with digits, may have + or country code)
- company (company/organization name, may have Ltd/LLC/Inc/Corp/GmbH/etc)
- domain (website domain like example.com, github.com)
- person (person's full name)
- unknown (if unclear)

Query: "{query}"

Return ONLY the category name, nothing else."""

        response = await openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )

        classification = response.choices[0].message.content.strip().lower()

        # Validate response
        valid_types = ['email', 'phone', 'company', 'domain', 'person', 'unknown']
        if classification not in valid_types:
            logger.warning(f"GPT returned invalid classification: {classification}")
            return classify_query_pattern(query)[0]

        logger.info(f"GPT classified '{query}' as: {classification}")
        return classification

    except Exception as e:
        logger.error(f"GPT classification failed: {e}")
        return classify_query_pattern(query)[0]


def classify_query_pattern(query: str) -> Tuple[str, float]:
    """
    Fast pattern-based classification
    Returns: (type, confidence)
    """
    query = query.strip()

    # Email detection (highest priority if @ present)
    if '@' in query and '.' in query:
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if re.match(email_pattern, query):
            return ('email', 1.0)
        return ('email', 0.8)

    # Phone detection
    # Remove common phone separators
    digits_only = re.sub(r'[\s\-\(\)\.+]', '', query)
    if digits_only.isdigit() and len(digits_only) >= 7:
        return ('phone', 0.9)

    # Starts with + followed by digits (international format)
    if query.startswith('+') and len(digits_only) >= 10:
        return ('phone', 0.95)

    # Domain detection (has . but no @, looks like domain)
    if '.' in query and ' ' not in query and not '@' in query:
        domain_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$'
        if re.match(domain_pattern, query):
            return ('domain', 0.9)

    # Company detection (has legal suffix)
    company_suffixes = ['ltd', 'llc', 'inc', 'corp', 'corporation', 'gmbh', 'sa', 'sl', 'bv', 'ag', 'plc', 'limited']
    query_lower = query.lower()
    for suffix in company_suffixes:
        if f' {suffix}' in query_lower or query_lower.endswith(suffix):
            return ('company', 0.8)

    # Person name (2-4 capitalized words, no symbols)
    words = query.split()
    if 2 <= len(words) <= 4:
        if all(word[0].isupper() for word in words if word):
            return ('person', 0.6)

    # Unknown
    return ('unknown', 0.0)


async def classify_eyed_query(query: str, use_gpt: bool = True) -> str:
    """
    Main classification function
    Tries pattern matching first, uses GPT if confidence < 0.8 or use_gpt=True
    """
    # First try fast pattern matching
    pattern_type, confidence = classify_query_pattern(query)

    logger.info(f"Pattern classified '{query}' as {pattern_type} (confidence: {confidence})")

    # If high confidence, use pattern result
    if confidence >= 0.8:
        return pattern_type

    # If ambiguous and GPT available, use GPT
    if use_gpt and openai_client:
        gpt_type = await classify_query_with_gpt(query)
        return gpt_type

    # Fallback to pattern matching
    return pattern_type


def get_search_endpoint(query_type: str) -> str:
    """
    Map query type to EYE-D API endpoint
    """
    endpoint_map = {
        'email': '/api/osint',
        'phone': '/api/osint',
        'company': '/api/corporate/unified',  # Replaced by Corporella - /data/corporella/,
        'domain': '/api/whois',
        'person': '/api/osint',  # Try OSINT for person names
        'unknown': '/api/search'  # Fallback to general search
    }
    return endpoint_map.get(query_type, '/api/search')
