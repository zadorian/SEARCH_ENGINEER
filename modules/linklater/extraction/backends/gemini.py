"""
Gemini 2.0 Flash Backend for Entity Extraction

Fast API-based NER using Google's Gemini model.
Uses REGEX-FIRST to find candidate snippets, then Gemini for extraction.
"""

import os
import re
import json
import asyncio
from typing import List, Optional
from pathlib import Path

# Load env
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

from ..models import Entity, ExtractionResult

# Centralized logging
from ...config import get_logger
logger = get_logger(__name__)


# REGEX patterns for candidate snippet extraction
PERSON_SIGNALS = [
    r'(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder|Owner|Partner|Chief|Head of|VP|Vice President|Chairman|Executive)\s+[A-Z][a-z]+',
    r'[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*,\s*(?:CEO|CFO|CTO|COO|CMO|President|Director|Manager|Founder)',
    r'(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+[A-Z][a-z]+\s+[A-Z][a-z]+',
    r'[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:said|stated|announced|reported)',
    r'(?:by|author|contact|written by)\s*:?\s*[A-Z][a-z]+\s+[A-Z][a-z]+',
]

COMPANY_SIGNALS = [
    r'[A-Z][A-Za-z\s&]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company|Group|Holdings|Partners|Associates|Solutions|Technologies|Services)',
    r'(?:About|Founded by|Owned by|Partner with|Client)\s+[A-Z][A-Za-z\s&]+',
    r'©\s*\d{4}\s*[A-Z][A-Za-z\s&]+',
]

ALL_SIGNALS = PERSON_SIGNALS + COMPANY_SIGNALS


def extract_candidate_snippets(text: str, max_snippets: int = 20) -> List[str]:
    """Extract promising snippets using regex signals."""
    snippets = []
    seen = set()

    for pattern in ALL_SIGNALS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # 200 chars before + 300 chars after
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 300)
            snippet = text[start:end].strip()

            # Dedup by first 100 chars
            key = snippet[:100]
            if key not in seen:
                seen.add(key)
                snippets.append(snippet)

            if len(snippets) >= max_snippets:
                return snippets

    return snippets


class GeminiBackend:
    """Gemini 2.0 Flash entity extraction backend."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model = None
        self._init_client()

    def _init_client(self):
        """Initialize Gemini client."""
        if not self.api_key:
            logger.warning("No API key found (GOOGLE_API_KEY or GEMINI_API_KEY)")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Gemini client ready")
        except Exception as e:
            logger.error(f"Init failed: {e}")

    def _build_prompt(self, snippets: List[str]) -> str:
        """Build extraction prompt for a batch of snippets."""
        combined = "\n---\n".join(snippets)

        return f"""Extract ONLY real person names and company names from this text.

RULES:
- Person names must be actual human names (First Last format)
- Do NOT include: job titles, pronouns, social media handles, generic terms
- Company names must include legal suffix (Inc, LLC, Ltd, Corp, etc) or be known company names
- Return ONLY unique entities, no duplicates

Return JSON only:
{{"persons": ["Full Name 1", "Full Name 2"], "companies": ["Company Name Inc", "Other Corp"]}}

TEXT:
{combined}

JSON:"""

    async def extract(
        self,
        html: str,
        url: str = "",
        entity_types: List[str] = None
    ) -> ExtractionResult:
        """Extract entities from HTML."""
        from bs4 import BeautifulSoup

        result = ExtractionResult()

        if not self.model:
            return result

        # Convert HTML to text
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ')

        # Extract emails directly via regex
        if entity_types is None or "email" in entity_types:
            for email in re.findall(r'[\w.-]+@[\w.-]+\.\w+', html):
                email = email.lower()
                result.emails.append(Entity(
                    value=email,
                    type="email",
                    archive_urls=[url] if url else []
                ))

        # Extract phones directly via regex
        if entity_types is None or "phone" in entity_types:
            for phone in re.findall(r'\+?[\d\s\-\(\)]{10,}', text):
                cleaned = re.sub(r'[^\d+]', '', phone)
                if len(cleaned) >= 10:
                    result.phones.append(Entity(
                        value=phone.strip(),
                        type="phone",
                        archive_urls=[url] if url else []
                    ))

        # REGEX-FIRST: Get candidate snippets
        snippets = extract_candidate_snippets(text)
        if not snippets:
            return result

        # Build and send prompt
        prompt = self._build_prompt(snippets)

        try:
            # Run synchronously in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            content = response.text

            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())

                for name in data.get("persons", []):
                    result.persons.append(Entity(
                        value=name,
                        type="person",
                        archive_urls=[url] if url else []
                    ))

                for name in data.get("companies", []):
                    result.companies.append(Entity(
                        value=name,
                        type="company",
                        archive_urls=[url] if url else []
                    ))

        except Exception as e:
            logger.warning(f"Extraction error: {e}")

        return result
