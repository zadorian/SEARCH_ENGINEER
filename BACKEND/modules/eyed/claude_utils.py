"""
Claude Haiku 4.5 utilities for cleaning malformed data
From EYE-D server.py
"""

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize Anthropic client
try:
    import anthropic
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
    if anthropic_client:
        logger.info("Claude Haiku 4.5 initialized for data cleaning")
except ImportError:
    logger.warning("Anthropic module not available - Claude cleaning disabled")
    anthropic_client = None


def should_clean_with_claude(text: str) -> bool:
    """
    Check if text contains malformed characters that need Claude cleaning.
    Detects corrupted data from OpenCorporates/WHOIS APIs.
    """
    if not text or not isinstance(text, str):
        return False

    # Patterns indicating malformed data
    malformed_patterns = [
        r'[}\]]',          # Closing brackets
        r':\w+=>',         # Key-value separators like :Kod_statu=>
        r'[{\[].*[}\]]',   # Bracket pairs
        r'^["\'>:=]+',     # Starts with quotes/symbols
        r':\\\\',          # Escaped backslashes
        r'\\[nt]',         # Escaped newlines/tabs
    ]

    for pattern in malformed_patterns:
        if re.search(pattern, text):
            logger.debug(f"Malformed pattern detected: {pattern} in '{text}'")
            return True

    return False


def clean_with_claude(malformed_text: str, max_retries: int = 2) -> str:
    """
    Use Claude Haiku 4.5 to clean malformed address/node text.
    Falls back to basic regex cleaning if Claude unavailable.
    """
    if not malformed_text:
        return ""

    # If Claude not available, use basic cleaning
    if not anthropic_client:
        logger.debug("Claude unavailable, using basic regex cleaning")
        return basic_text_cleanup(malformed_text)

    try:
        message = f"""Please clean this malformed address/location text and make it comprehensible.
The text appears to be corrupted data from OpenCorporates or similar sources.
Return ONLY the cleaned, readable address without any explanation:

Malformed text: {malformed_text}"""

        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": message}]
        )

        cleaned = response.content[0].text.strip()
        logger.info(f"Claude cleaned: '{malformed_text[:50]}...' → '{cleaned}'")
        return cleaned

    except Exception as e:
        logger.error(f"Error cleaning with Claude: {e}")
        # Fallback to basic cleaning
        return basic_text_cleanup(malformed_text)


def basic_text_cleanup(text: str) -> str:
    """
    Basic regex-based cleanup as fallback
    """
    # Remove brackets and special characters
    cleaned = re.sub(r'[}\]\[\{]', '', text)

    # Remove key-value separators
    cleaned = re.sub(r':\w+=>',

 '', cleaned)

    # Remove quotes and extra symbols
    cleaned = re.sub(r'["\'>:=]+', ' ', cleaned)

    # Remove escaped characters
    cleaned = re.sub(r'\\[nt\\]', ' ', cleaned)

    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned
