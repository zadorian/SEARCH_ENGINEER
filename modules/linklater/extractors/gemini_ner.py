#!/usr/bin/env python3
"""
Gemini 2.0 Flash Entity Extractor - FAST API-based NER

No model loading overhead - pure API calls.
Uses REGEX-FIRST to find candidate snippets, then Gemini for entity extraction.

Speed: ~1-2s per batch (vs 3-5s GLiNER model load + 0.6s inference)
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Load env
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')


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


@dataclass
class Entity:
    """Extracted entity with provenance."""
    value: str
    type: str  # person, company, email, phone
    archive_urls: List[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    found_in_snapshots: int = 0


class GeminiEntityExtractor:
    """
    Gemini 2.0 Flash entity extraction.

    No model loading - pure API calls. Fast startup, consistent speed.
    """

    def __init__(self, batch_size: int = 5):
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model = None
        self.batch_size = batch_size
        self._init_client()

    def _init_client(self):
        """Initialize Gemini client."""
        if not self.api_key:
            print("[Gemini] No API key found (GOOGLE_API_KEY or GEMINI_API_KEY)")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            print("[Gemini] Client ready")
        except Exception as e:
            print(f"[Gemini] Init failed: {e}")

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

    def extract_sync(self, text: str, archive_url: str = "") -> Dict[str, List[str]]:
        """
        Synchronous entity extraction from text.

        Returns: {"persons": [...], "companies": [...]}
        """
        if not self.model:
            return {"persons": [], "companies": []}

        # REGEX-FIRST: Get candidate snippets
        snippets = extract_candidate_snippets(text)
        if not snippets:
            return {"persons": [], "companies": []}

        # Build and send prompt
        prompt = self._build_prompt(snippets)

        try:
            response = self.model.generate_content(prompt)
            content = response.text

            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "persons": data.get("persons", []),
                    "companies": data.get("companies", [])
                }
        except Exception as e:
            print(f"[Gemini] Extraction error: {e}")

        return {"persons": [], "companies": []}

    async def extract_async(self, text: str, archive_url: str = "") -> Dict[str, List[str]]:
        """Async wrapper for extraction."""
        # Run sync extraction in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_sync, text, archive_url)

    async def extract_batch_streaming(
        self,
        texts_with_urls: List[Tuple[str, str, str]]  # (text, url, timestamp)
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream entity extraction results for a batch of texts.

        Args:
            texts_with_urls: List of (text, url, timestamp) tuples

        Yields:
            Progress updates and entity results
        """
        if not self.model:
            yield {"type": "error", "message": "Gemini not initialized"}
            return

        total = len(texts_with_urls)
        processed = 0

        # Track entities across all texts
        entity_tracker: Dict[Tuple[str, str], List[str]] = defaultdict(list)  # (type, value) -> [archive_urls]

        # Process in batches
        for i in range(0, total, self.batch_size):
            batch = texts_with_urls[i:i + self.batch_size]

            yield {
                "type": "progress",
                "processed": processed,
                "total": total,
                "percent": int(100 * processed / total)
            }

            # Extract from each text in batch (parallel)
            tasks = []
            for text, url, timestamp in batch:
                archive_url = f"https://web.archive.org/web/{timestamp}/{url}"
                tasks.append(self._extract_with_url(text, archive_url))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (text, url, timestamp), result in zip(batch, results):
                archive_url = f"https://web.archive.org/web/{timestamp}/{url}"

                if isinstance(result, Exception):
                    continue

                # Track entities with archive URLs
                for person in result.get("persons", []):
                    entity_tracker[("person", person.lower())].append(archive_url)

                for company in result.get("companies", []):
                    entity_tracker[("company", company.lower())].append(archive_url)

                processed += 1

                # Yield intermediate results every 5 pages
                if processed % 5 == 0:
                    yield {
                        "type": "partial",
                        "processed": processed,
                        "total": total,
                        "entities_so_far": len(entity_tracker)
                    }

        # Final results
        persons = []
        companies = []

        for (ent_type, value), urls in entity_tracker.items():
            entity = {
                "value": value.title() if ent_type == "person" else value,
                "type": ent_type,
                "archive_urls": list(set(urls))[:5],  # Dedupe, limit to 5
                "found_in_snapshots": len(urls)
            }

            if ent_type == "person":
                persons.append(entity)
            else:
                companies.append(entity)

        # Sort by occurrence count
        persons.sort(key=lambda x: -x["found_in_snapshots"])
        companies.sort(key=lambda x: -x["found_in_snapshots"])

        yield {
            "type": "final",
            "entities": {
                "persons": persons,
                "companies": companies
            },
            "total_processed": processed
        }

    async def _extract_with_url(self, text: str, archive_url: str) -> Dict[str, List[str]]:
        """Extract entities from a single text."""
        return await self.extract_async(text, archive_url)


# Module-level singleton for reuse
_GEMINI_EXTRACTOR: Optional[GeminiEntityExtractor] = None


def get_gemini_extractor() -> GeminiEntityExtractor:
    """Get or create singleton Gemini extractor."""
    global _GEMINI_EXTRACTOR
    if _GEMINI_EXTRACTOR is None:
        _GEMINI_EXTRACTOR = GeminiEntityExtractor()
    return _GEMINI_EXTRACTOR


async def test_speed():
    """Test extraction speed on sample text."""
    import time

    sample_text = """
    SOAX is a proxy service founded by Robin Geuens and Sergey Konovalov.
    The company has partnerships with Google, Amazon, and Microsoft.
    CEO John Smith announced the new product line.
    Dr. Maria Garcia, Chief Technology Officer, leads the engineering team.
    SOAX Ltd. is headquartered in Europe. Contact sales@soax.com for more info.
    The company works with Fortune 500 clients including Apple Inc., Meta Corporation, and Tesla Holdings.
    """

    print("=" * 60)
    print("GEMINI 2.0 FLASH ENTITY EXTRACTOR - SPEED TEST")
    print("=" * 60)

    extractor = get_gemini_extractor()

    # Time the extraction
    start = time.time()
    result = extractor.extract_sync(sample_text)
    elapsed = time.time() - start

    print(f"\nTime: {elapsed:.2f}s")
    print(f"Persons: {result['persons']}")
    print(f"Companies: {result['companies']}")

    # Test async batch
    print("\n" + "-" * 40)
    print("BATCH STREAMING TEST")
    print("-" * 40)

    # Simulate 3 archived pages
    texts = [
        (sample_text, "soax.com", "20240601120000"),
        (sample_text + " Also, VP David Chen joined from Apple Inc.", "soax.com/about", "20240715143000"),
        ("Contact our team: support@soax.com. Partners include Cloudflare Inc.", "soax.com/contact", "20240801090000"),
    ]

    start = time.time()
    async for update in extractor.extract_batch_streaming(texts):
        if update["type"] == "progress":
            print(f"  Progress: {update['percent']}%")
        elif update["type"] == "partial":
            print(f"  Partial: {update['entities_so_far']} entities found")
        elif update["type"] == "final":
            print(f"\n  FINAL: {len(update['entities']['persons'])} persons, {len(update['entities']['companies'])} companies")
            for p in update['entities']['persons']:
                print(f"    - {p['value']} (x{p['found_in_snapshots']})")
            for c in update['entities']['companies']:
                print(f"    - {c['value']} (x{c['found_in_snapshots']})")

    elapsed = time.time() - start
    print(f"\n  Total batch time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(test_speed())
