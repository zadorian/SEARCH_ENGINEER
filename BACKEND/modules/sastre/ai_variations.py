"""
SASTRE AI Variation Enhancer - GPT-5-nano powered variations.

Adds creative, context-aware variations on top of rule-based generation.
Uses GPT-5-nano for fast, cheap enhancement of name/entity variations.

CRITICAL: GPT-5 models do NOT support temperature/top_p.
Uses `reasoning_effort` parameter instead (none/low/medium/high).

Architecture:
    Rule-Based Layer (fast, deterministic)
        └── PersonVariator, CompanyVariator, PhoneVariator

    AI Enhancement Layer (GPT-5-nano)
        └── Context-aware, creative variations
        └── Handles edge cases rules miss
        └── Language/cultural awareness

Usage:
    from SASTRE.ai_variations import AIVariationEnhancer

    enhancer = AIVariationEnhancer()
    ai_vars = await enhancer.enhance_person("János Kovács", existing_variations)
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Load from project root .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

logger = logging.getLogger(__name__)


class VariationType(Enum):
    """Types of variations the AI can generate."""
    TRANSLITERATION = "transliteration"  # Cyrillic, Arabic, etc.
    CULTURAL = "cultural"                 # Nicknames, diminutives
    OCR_ERROR = "ocr_error"              # 0/O, 1/I confusion
    HISTORICAL = "historical"            # Old spellings
    REGIONAL = "regional"                # Country-specific formats


@dataclass
class AIVariation:
    """A single AI-generated variation with metadata."""
    value: str
    variation_type: VariationType
    confidence: float  # 0.0 - 1.0
    reasoning: Optional[str] = None


# =============================================================================
# GPT-5-NANO VARIATION ENHANCER
# =============================================================================

class AIVariationEnhancer:
    """
    GPT-5-nano powered variation generation.

    Enhances rule-based variations with:
    - Transliterations (Cyrillic, Arabic, etc.)
    - Cultural variants (nicknames, diminutives)
    - OCR/transcription errors
    - Historical spellings
    - Regional formats

    CRITICAL: Uses reasoning_effort, NOT temperature (GPT-5 API change).
    """

    MODEL = "gpt-5-nano"

    # Prompts optimized for GPT-5-nano (concise, structured output)
    PERSON_PROMPT = '''Generate name variations for: "{value}"
Already have: {existing}

Generate 3-5 MORE variations that rules might miss:
- Transliterations (Cyrillic→Latin, Arabic→Latin)
- Nicknames/diminutives (János→Jani, William→Bill)
- Surname-first formats (Smith John)
- OCR errors (0/O, 1/I, l/I confusion)

Return JSON only: {{"variations": ["var1", "var2"]}}'''

    COMPANY_PROMPT = '''Generate company name variations for: "{value}"
Already have: {existing}

Generate 3-5 MORE variations:
- Regional suffixes (Ltd/Limited/GmbH/Kft/d.o.o.)
- With/without suffixes
- Abbreviations (International→Intl)
- Typos/misspellings

Return JSON only: {{"variations": ["var1", "var2"]}}'''

    PHONE_PROMPT = '''Generate phone number variations for: "{value}"
Already have: {existing}

Generate 3-5 MORE variations:
- Country code formats (+36, 0036, 36)
- Local format (without country code)
- OCR errors (0/O, 1/I)
- Common formatting (spaces, dashes, dots)

Return JSON only: {{"variations": ["var1", "var2"]}}'''

    EMAIL_PROMPT = '''Generate email variations for: "{value}"
Already have: {existing}

Generate 3-5 MORE variations:
- Plus addressing (user+tag@domain)
- Dot variations (j.smith vs jsmith)
- Common misspellings
- Domain typos (gmail.com vs googlemail.com)

Return JSON only: {{"variations": ["var1", "var2"]}}'''

    def __init__(self, enabled: bool = True):
        """
        Initialize the AI variation enhancer.

        Args:
            enabled: If False, returns empty lists (for testing/fallback)
        """
        self.enabled = enabled
        self._client = None

    @property
    def client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("OPENAI_API_KEY not found, AI variations disabled")
                    self.enabled = False
                    return None
                self._client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                logger.warning("openai package not installed, AI variations disabled")
                self.enabled = False
                return None
        return self._client

    async def enhance_person(
        self,
        name: str,
        existing_variations: List[str],
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Generate person name variations using AI.

        Args:
            name: The person's name
            existing_variations: Already-generated rule-based variations
            context: Optional context (e.g., "Hungarian investigation")

        Returns:
            List of AI-generated variations (deduplicated from existing)
        """
        if not self.enabled:
            return []

        prompt = self.PERSON_PROMPT.format(
            value=name,
            existing=existing_variations[:8],  # Limit context size
        )

        if context:
            prompt += f"\nContext: {context}"

        return await self._call_gpt5_nano(prompt, existing_variations)

    async def enhance_company(
        self,
        name: str,
        existing_variations: List[str],
        jurisdiction: Optional[str] = None,
    ) -> List[str]:
        """
        Generate company name variations using AI.

        Args:
            name: The company name
            existing_variations: Already-generated rule-based variations
            jurisdiction: Optional jurisdiction (e.g., "HU" for Hungary)

        Returns:
            List of AI-generated variations
        """
        if not self.enabled:
            return []

        prompt = self.COMPANY_PROMPT.format(
            value=name,
            existing=existing_variations[:8],
        )

        if jurisdiction:
            prompt += f"\nJurisdiction: {jurisdiction}"

        return await self._call_gpt5_nano(prompt, existing_variations)

    async def enhance_phone(
        self,
        phone: str,
        existing_variations: List[str],
        country_code: Optional[str] = None,
    ) -> List[str]:
        """
        Generate phone number variations using AI.

        Args:
            phone: The phone number
            existing_variations: Already-generated rule-based variations
            country_code: Optional country code (e.g., "+36")

        Returns:
            List of AI-generated variations
        """
        if not self.enabled:
            return []

        prompt = self.PHONE_PROMPT.format(
            value=phone,
            existing=existing_variations[:8],
        )

        if country_code:
            prompt += f"\nCountry code: {country_code}"

        return await self._call_gpt5_nano(prompt, existing_variations)

    async def enhance_email(
        self,
        email: str,
        existing_variations: List[str],
    ) -> List[str]:
        """
        Generate email variations using AI.

        Args:
            email: The email address
            existing_variations: Already-generated rule-based variations

        Returns:
            List of AI-generated variations
        """
        if not self.enabled:
            return []

        prompt = self.EMAIL_PROMPT.format(
            value=email,
            existing=existing_variations[:8],
        )

        return await self._call_gpt5_nano(prompt, existing_variations)

    async def enhance_generic(
        self,
        value: str,
        value_type: str,
        existing_variations: List[str],
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Route to appropriate enhancer based on value type.

        Args:
            value: The value to generate variations for
            value_type: "person", "company", "phone", "email"
            existing_variations: Already-generated variations
            context: Optional context string

        Returns:
            List of AI-generated variations
        """
        if value_type in ("person", "p:"):
            return await self.enhance_person(value, existing_variations, context)
        elif value_type in ("company", "c:", "organization"):
            return await self.enhance_company(value, existing_variations)
        elif value_type in ("phone", "t:"):
            return await self.enhance_phone(value, existing_variations)
        elif value_type in ("email", "e:"):
            return await self.enhance_email(value, existing_variations)
        else:
            # Generic fallback - try person-style variations
            return await self.enhance_person(value, existing_variations, context)

    async def _call_gpt5_nano(
        self,
        prompt: str,
        existing_variations: List[str],
    ) -> List[str]:
        """
        Call GPT-5-nano API and parse response.

        CRITICAL: Uses reasoning_effort, NOT temperature.
        GPT-5 models do not support temperature parameter.

        Args:
            prompt: The prompt to send
            existing_variations: Existing variations to deduplicate against

        Returns:
            List of new variations (deduplicated)
        """
        if not self.client:
            return []

        try:
            response = await self.client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                reasoning_effort="low",  # GPT-5 uses this instead of temperature
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            variations = self._parse_json_response(content)

            # Deduplicate against existing
            existing_set = set(v.lower() for v in existing_variations)
            new_variations = [
                v for v in variations
                if v.lower() not in existing_set
            ]

            logger.debug(f"AI generated {len(new_variations)} new variations")
            return new_variations

        except Exception as e:
            logger.warning(f"GPT-5-nano call failed: {e}")
            return []

    def _parse_json_response(self, content: str) -> List[str]:
        """
        Parse JSON response from GPT-5-nano.

        Handles various response formats:
        - {"variations": [...]}
        - ["var1", "var2"]
        - Markdown code blocks
        """
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        try:
            data = json.loads(content)

            if isinstance(data, dict) and "variations" in data:
                return data["variations"]
            elif isinstance(data, list):
                return data
            else:
                return []

        except json.JSONDecodeError:
            # Try to extract strings from malformed response
            logger.debug(f"Failed to parse JSON: {content[:100]}")
            return []


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Singleton enhancer instance
_enhancer: Optional[AIVariationEnhancer] = None


def get_enhancer() -> AIVariationEnhancer:
    """Get or create the singleton AIVariationEnhancer."""
    global _enhancer
    if _enhancer is None:
        _enhancer = AIVariationEnhancer()
    return _enhancer


async def enhance_variations(
    value: str,
    value_type: str,
    existing_variations: List[str],
    context: Optional[str] = None,
) -> List[str]:
    """
    Convenience function to enhance variations using AI.

    Args:
        value: The value to generate variations for
        value_type: "person", "company", "phone", "email"
        existing_variations: Already-generated variations
        context: Optional context string

    Returns:
        List of AI-generated variations (combined with existing)
    """
    enhancer = get_enhancer()
    ai_vars = await enhancer.enhance_generic(value, value_type, existing_variations, context)
    return existing_variations + ai_vars


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_enhancer():
        """Test the AI variation enhancer."""
        enhancer = AIVariationEnhancer()

        # Test person variations
        person_vars = await enhancer.enhance_person(
            "János Kovács",
            ["Janos Kovacs", "Kovács János", "J. Kovács"],
            context="Hungarian investigation"
        )
        print(f"Person variations: {person_vars}")

        # Test company variations
        company_vars = await enhancer.enhance_company(
            "Acme International Ltd",
            ["Acme International", "ACME Ltd"],
            jurisdiction="UK"
        )
        print(f"Company variations: {company_vars}")

        # Test phone variations
        phone_vars = await enhancer.enhance_phone(
            "+36301234567",
            ["36301234567", "0036301234567"],
            country_code="+36"
        )
        print(f"Phone variations: {phone_vars}")

    asyncio.run(test_enhancer())
