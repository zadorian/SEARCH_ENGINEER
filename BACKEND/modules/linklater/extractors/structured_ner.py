#!/usr/bin/env python3
"""
Structured Entity Extractor - Output with Snippets

Output format per URL:
{
    "url": "https://web.archive.org/web/20240601/soax.com",
    "entities": {
        "telephone": [{"value": "+1-555-123-4567", "snippet": "...contact us at +1-555-123-4567 for support..."}],
        "email": [{"value": "sales@company.com", "snippet": "...reach our team at sales@company.com today..."}],
        "company": [{"value": "SOAX Inc.", "snippet": "...powered by SOAX Inc., a leading proxy provider..."}],
        "person": [{"value": "John Smith", "snippet": "...CEO John Smith announced the new partnership..."}],
        "address": [{"value": "123 Main St, NYC", "snippet": "...headquartered at 123 Main St, NYC since 2020..."}],
        "username": [{"value": "@soax_official", "snippet": "...follow us @soax_official on Twitter..."}]
    }
}
"""

import os
import re
import json
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# Set up paths for imports
EXTRACTOR_DIR = Path(__file__).resolve().parent
LINKLATER_DIR = EXTRACTOR_DIR.parent
MODULES_DIR = LINKLATER_DIR.parent
PROJECT_ROOT = MODULES_DIR.parent.parent

# Add parent dirs to path for local imports
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
if str(LINKLATER_DIR) not in sys.path:
    sys.path.insert(0, str(LINKLATER_DIR))

# Load env
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')


# REGEX patterns for different entity types
ENTITY_PATTERNS = {
    "telephone": [
        r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US phone
        r'\+\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}',  # International
        r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}',  # (xxx) xxx-xxxx
    ],
    "email": [
        r'[\w.+-]+@[\w.-]+\.\w{2,}',
    ],
    "username": [
        r'@[A-Za-z_][\w]{2,}',  # @username
        r'(?:twitter|instagram|linkedin|github|facebook)\.com/[\w.-]+',
    ],
    "address": [
        r'\d{1,5}\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)[\s,]+[\w\s]+,?\s*(?:[A-Z]{2})?\s*\d{5}(?:-\d{4})?',
    ],
}

# Person/company signals for NER
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


@dataclass
class EntityWithSnippet:
    """Single entity with its surrounding context."""
    value: str
    type: str
    snippet: str
    confidence: float = 1.0
    source_model: str = "regex"


@dataclass
class URLEntityResult:
    """All entities found for a single URL."""
    url: str
    timestamp: str = ""
    entities: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "timestamp": self.timestamp,
            "entities": self.entities
        }


class StructuredEntityExtractor:
    """
    Extracts entities with surrounding snippets.

    Uses parallel Gemini + GPT-5-nano for accuracy,
    returns structured output with context for each entity.
    """

    SNIPPET_RADIUS = 100  # Characters before/after entity

    def __init__(self):
        self._gemini = None
        self._gpt5_client = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._init_extractors()

    def _init_extractors(self):
        """Initialize API clients."""
        # Gemini
        try:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._gemini = genai.GenerativeModel('gemini-2.0-flash')
                print("[StructuredNER] Gemini ready")
        except Exception as e:
            print(f"[StructuredNER] Gemini not available: {e}")

        # GPT-5-nano
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                from openai import OpenAI
                self._gpt5_client = OpenAI(api_key=api_key)
                print("[StructuredNER] GPT-5-nano ready")
        except Exception as e:
            print(f"[StructuredNER] GPT-5-nano not available: {e}")

    def _extract_snippet(self, text: str, start: int, end: int) -> str:
        """Extract snippet with context around match."""
        snippet_start = max(0, start - self.SNIPPET_RADIUS)
        snippet_end = min(len(text), end + self.SNIPPET_RADIUS)

        snippet = text[snippet_start:snippet_end].strip()

        # Clean up - remove extra whitespace
        snippet = re.sub(r'\s+', ' ', snippet)

        # Add ellipsis if truncated
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    def _extract_regex_entities(self, text: str) -> Dict[str, List[EntityWithSnippet]]:
        """Extract entities using regex patterns."""
        results = defaultdict(list)
        seen = defaultdict(set)  # Avoid duplicates per type

        for entity_type, patterns in ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group().strip()

                    # Basic validation
                    if len(value) < 3:
                        continue

                    # Skip duplicates
                    value_lower = value.lower()
                    if value_lower in seen[entity_type]:
                        continue
                    seen[entity_type].add(value_lower)

                    snippet = self._extract_snippet(text, match.start(), match.end())

                    results[entity_type].append(EntityWithSnippet(
                        value=value,
                        type=entity_type,
                        snippet=snippet,
                        confidence=0.9,
                        source_model="regex"
                    ))

        return results

    def _extract_with_gemini(self, text: str) -> Dict[str, List[str]]:
        """Extract persons/companies with Gemini."""
        if not self._gemini:
            return {"persons": [], "companies": []}

        # Build candidate snippets using regex signals
        snippets = []
        all_signals = PERSON_SIGNALS + COMPANY_SIGNALS

        for pattern in all_signals:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = max(0, match.start() - 200)
                end = min(len(text), match.end() + 300)
                snippet = text[start:end].strip()
                if snippet and snippet not in snippets:
                    snippets.append(snippet)
                if len(snippets) >= 20:
                    break
            if len(snippets) >= 20:
                break

        if not snippets:
            return {"persons": [], "companies": []}

        combined = "\n---\n".join(snippets)

        prompt = f"""Extract person names and company names from this text.
Return ONLY valid JSON: {{"persons": ["Name1"], "companies": ["Company1"]}}
Do not include job titles, only actual names.

TEXT:
{combined}

JSON:"""

        try:
            response = self._gemini.generate_content(prompt)
            content = response.text

            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "persons": data.get("persons", []),
                    "companies": data.get("companies", [])
                }
        except Exception as e:
            print(f"[StructuredNER] Gemini error: {e}")

        return {"persons": [], "companies": []}

    def _extract_with_gpt5(self, text: str) -> Dict[str, List[str]]:
        """Extract persons/companies with GPT-5-nano."""
        if not self._gpt5_client:
            return {"persons": [], "companies": []}

        text = text[:8000]  # Token limit

        prompt = f"""Extract person names and company names from this text.
Return ONLY valid JSON: {{"persons": ["Name1"], "companies": ["Company1"]}}

TEXT:
{text}

JSON:"""

        try:
            response = self._gpt5_client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content

            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "persons": data.get("persons", []),
                    "companies": data.get("companies", [])
                }
        except Exception as e:
            print(f"[StructuredNER] GPT-5-nano error: {e}")

        return {"persons": [], "companies": []}

    def _find_entity_in_text(self, text: str, entity_value: str) -> Optional[Tuple[int, int]]:
        """Find entity position in text for snippet extraction."""
        # Try exact match first
        idx = text.find(entity_value)
        if idx != -1:
            return (idx, idx + len(entity_value))

        # Try case-insensitive
        text_lower = text.lower()
        value_lower = entity_value.lower()
        idx = text_lower.find(value_lower)
        if idx != -1:
            return (idx, idx + len(entity_value))

        return None

    async def extract_structured(
        self,
        text: str,
        url: str = "",
        timestamp: str = ""
    ) -> URLEntityResult:
        """
        Extract all entities with snippets from text.

        Args:
            text: Full text/HTML content
            url: Source URL
            timestamp: Archive timestamp

        Returns:
            URLEntityResult with structured entity data
        """
        result = URLEntityResult(
            url=url,
            timestamp=timestamp,
            entities={
                "telephone": [],
                "email": [],
                "company": [],
                "person": [],
                "address": [],
                "username": []
            }
        )

        # Strip HTML tags for entity extraction
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, 'html.parser')
        clean_text = soup.get_text(separator=' ')
        clean_text = re.sub(r'\s+', ' ', clean_text)

        # 1. Extract regex-based entities (phone, email, address, username)
        regex_entities = self._extract_regex_entities(clean_text)

        for entity_type, entities in regex_entities.items():
            for ent in entities:
                result.entities[entity_type].append({
                    "value": ent.value,
                    "snippet": ent.snippet,
                    "confidence": ent.confidence,
                    "source": ent.source_model
                })

        # 2. Extract persons/companies with Gemini + GPT-5-nano in parallel
        loop = asyncio.get_event_loop()

        if self._gemini and self._gpt5_client:
            # Parallel extraction
            gemini_task = loop.run_in_executor(
                self._executor, self._extract_with_gemini, clean_text
            )
            gpt5_task = loop.run_in_executor(
                self._executor, self._extract_with_gpt5, clean_text
            )

            gemini_result, gpt5_result = await asyncio.gather(
                gemini_task, gpt5_task, return_exceptions=True
            )

            if isinstance(gemini_result, Exception):
                gemini_result = {"persons": [], "companies": []}
            if isinstance(gpt5_result, Exception):
                gpt5_result = {"persons": [], "companies": []}

            # Merge with confidence scoring
            gemini_persons = set(p.lower() for p in gemini_result.get("persons", []))
            gpt5_persons = set(p.lower() for p in gpt5_result.get("persons", []))
            confirmed_persons = gemini_persons & gpt5_persons
            all_persons = gemini_persons | gpt5_persons

            gemini_companies = set(c.lower() for c in gemini_result.get("companies", []))
            gpt5_companies = set(c.lower() for c in gpt5_result.get("companies", []))
            confirmed_companies = gemini_companies & gpt5_companies
            all_companies = gemini_companies | gpt5_companies

            # Get original case versions and find snippets
            seen_persons = set()
            for p in gemini_result.get("persons", []) + gpt5_result.get("persons", []):
                p_lower = p.lower()
                if p_lower in seen_persons:
                    continue
                seen_persons.add(p_lower)

                if p_lower in all_persons:
                    confidence = 1.0 if p_lower in confirmed_persons else 0.7

                    # Find snippet
                    pos = self._find_entity_in_text(clean_text, p)
                    if pos:
                        snippet = self._extract_snippet(clean_text, pos[0], pos[1])
                    else:
                        snippet = ""

                    result.entities["person"].append({
                        "value": p,
                        "snippet": snippet,
                        "confidence": confidence,
                        "source": "both" if p_lower in confirmed_persons else "single"
                    })

            seen_companies = set()
            for c in gemini_result.get("companies", []) + gpt5_result.get("companies", []):
                c_lower = c.lower()
                if c_lower in seen_companies:
                    continue
                seen_companies.add(c_lower)

                if c_lower in all_companies:
                    confidence = 1.0 if c_lower in confirmed_companies else 0.7

                    pos = self._find_entity_in_text(clean_text, c)
                    if pos:
                        snippet = self._extract_snippet(clean_text, pos[0], pos[1])
                    else:
                        snippet = ""

                    result.entities["company"].append({
                        "value": c,
                        "snippet": snippet,
                        "confidence": confidence,
                        "source": "both" if c_lower in confirmed_companies else "single"
                    })

        elif self._gemini:
            # Gemini only
            gemini_result = await loop.run_in_executor(
                self._executor, self._extract_with_gemini, clean_text
            )

            for p in gemini_result.get("persons", []):
                pos = self._find_entity_in_text(clean_text, p)
                snippet = self._extract_snippet(clean_text, pos[0], pos[1]) if pos else ""
                result.entities["person"].append({
                    "value": p,
                    "snippet": snippet,
                    "confidence": 0.9,
                    "source": "gemini"
                })

            for c in gemini_result.get("companies", []):
                pos = self._find_entity_in_text(clean_text, c)
                snippet = self._extract_snippet(clean_text, pos[0], pos[1]) if pos else ""
                result.entities["company"].append({
                    "value": c,
                    "snippet": snippet,
                    "confidence": 0.9,
                    "source": "gemini"
                })

        return result

    async def extract_async(self, text: str, url: str = "", timestamp: str = "") -> Dict[str, Any]:
        """
        Async extraction wrapper for compatibility with QueryExecutor.

        Returns dict with entities in format expected by extract_entities_structured():
        {"entities": {type: [{value, snippet, confidence, source}]}}
        """
        result = await self.extract_structured(text, url, timestamp)
        return result.to_dict()

    async def extract_batch_structured(
        self,
        texts_with_urls: List[Tuple[str, str, str]],  # (text, url, timestamp)
        progress_callback=None
    ) -> List[URLEntityResult]:
        """
        Extract structured entities from multiple URLs.

        Returns list of URLEntityResult, one per URL.
        """
        results = []
        total = len(texts_with_urls)

        for i, (text, url, timestamp) in enumerate(texts_with_urls):
            archive_url = f"https://web.archive.org/web/{timestamp}/{url}"

            result = await self.extract_structured(text, archive_url, timestamp)
            results.append(result)

            if progress_callback and (i + 1) % 5 == 0:
                await progress_callback({
                    "processed": i + 1,
                    "total": total,
                    "percent": int(100 * (i + 1) / total)
                })

        return results


# Module singleton
_STRUCTURED_EXTRACTOR: Optional[StructuredEntityExtractor] = None


def get_structured_extractor() -> StructuredEntityExtractor:
    """Get or create singleton extractor."""
    global _STRUCTURED_EXTRACTOR
    if _STRUCTURED_EXTRACTOR is None:
        _STRUCTURED_EXTRACTOR = StructuredEntityExtractor()
    return _STRUCTURED_EXTRACTOR


async def test_structured():
    """Test structured extraction."""
    import time

    print("=" * 70)
    print("STRUCTURED ENTITY EXTRACTOR TEST")
    print("=" * 70)

    extractor = get_structured_extractor()

    # Test text with various entity types
    sample_html = """
    <html>
    <body>
    <h1>About SOAX Inc.</h1>
    <p>SOAX is a proxy service founded by Robin Geuens and Sergey Konovalov.</p>
    <p>CEO John Smith announced the new partnership with Google Cloud.</p>
    <p>Contact us at sales@soax.com or call +1-555-123-4567</p>
    <p>Follow us on Twitter @soax_official</p>
    <p>Headquarters: 123 Main Street, San Francisco, CA 94102</p>
    <p>Our partners include Microsoft Corporation and Amazon Web Services Inc.</p>
    <p>Dr. Maria Garcia, Chief Technology Officer, leads the engineering team.</p>
    </body>
    </html>
    """

    print("\nExtracting from sample HTML...")
    start = time.time()

    result = await extractor.extract_structured(
        sample_html,
        url="soax.com/about",
        timestamp="20240601120000"
    )

    elapsed = time.time() - start
    print(f"Time: {elapsed:.2f}s")

    print("\n" + "=" * 70)
    print("STRUCTURED OUTPUT:")
    print("=" * 70)

    print(f"\nURL: {result.url}")
    print(f"Timestamp: {result.timestamp}")

    for entity_type, entities in result.entities.items():
        if entities:
            print(f"\n{entity_type.upper()} ({len(entities)}):")
            for ent in entities:
                print(f"  Value: {ent['value']}")
                print(f"  Snippet: {ent['snippet'][:100]}..." if len(ent.get('snippet', '')) > 100 else f"  Snippet: {ent.get('snippet', 'N/A')}")
                print(f"  Confidence: {ent.get('confidence', 'N/A')}")
                print()

    # Test batch extraction
    print("\n" + "=" * 70)
    print("BATCH EXTRACTION TEST")
    print("=" * 70)

    batch = [
        (sample_html, "soax.com/about", "20240101"),
        ("<p>Contact support@example.com or @example_help</p>", "example.com/contact", "20240201"),
        ("<p>VP David Chen from Oracle Corp announced the merger.</p>", "news.com/article", "20240301"),
    ]

    start = time.time()
    results = await extractor.extract_batch_structured(batch)
    elapsed = time.time() - start

    print(f"\nProcessed {len(results)} URLs in {elapsed:.2f}s")

    for r in results:
        print(f"\n--- {r.url} ---")
        entity_count = sum(len(e) for e in r.entities.values())
        print(f"  Total entities: {entity_count}")
        for etype, ents in r.entities.items():
            if ents:
                print(f"  {etype}: {[e['value'] for e in ents]}")


if __name__ == "__main__":
    asyncio.run(test_structured())
