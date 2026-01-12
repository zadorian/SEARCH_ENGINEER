#!/usr/bin/env python3
"""
Multi-Model Entity Extraction Speed Test

Compares:
1. GLiNER (local) - Current approach
2. GPT-5-nano (OpenAI) - Fast cloud model
3. Gemini 2.0 Flash (Google) - Fast cloud model

All use REGEX-FIRST: Find candidate snippets, then extract entities from those only.
"""

import os
import re
import json
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass
from collections import defaultdict

# Load env
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Person and company signal patterns for REGEX-FIRST
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


def extract_candidate_snippets(text: str, max_snippets: int = 30) -> List[str]:
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
class ExtractionResult:
    """Result from entity extraction."""
    persons: List[str]
    companies: List[str]
    model: str
    time_seconds: float
    snippet_count: int


class GLiNERExtractor:
    """Local GLiNER model extraction."""

    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from gliner import GLiNER
            self.model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
            print("[GLiNER] Model loaded")
        except Exception as e:
            print(f"[GLiNER] Failed to load: {e}")

    def extract(self, snippets: List[str]) -> ExtractionResult:
        """Extract entities from snippets."""
        start = time.time()
        persons = set()
        companies = set()

        if not self.model:
            return ExtractionResult([], [], "gliner", 0, len(snippets))

        labels = ["person name", "organization", "company"]

        for snippet in snippets:
            try:
                results = self.model.predict_entities(snippet, labels, threshold=0.5)
                for ent in results:
                    value = ent.get('text', '').strip()
                    ent_type = ent.get('label', '')

                    if len(value) < 3:
                        continue

                    if ent_type == 'person name':
                        # Basic filtering
                        if ' ' in value and any(w[0].isupper() for w in value.split() if w):
                            persons.add(value)
                    elif ent_type in ('organization', 'company'):
                        if len(value) >= 3:
                            companies.add(value)
            except Exception as e:
                print(f"[GLiNER] Error: {e}")
                break

        elapsed = time.time() - start
        return ExtractionResult(
            list(persons), list(companies), "gliner", elapsed, len(snippets)
        )


class GPT5NanoExtractor:
    """OpenAI GPT-5-nano extraction - FAST."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                print("[GPT-5-nano] Client initialized")
            except Exception as e:
                print(f"[GPT-5-nano] Failed: {e}")

    def extract(self, snippets: List[str]) -> ExtractionResult:
        """Extract entities using GPT-5-nano."""
        start = time.time()

        if not self.client:
            return ExtractionResult([], [], "gpt-5-nano", 0, len(snippets))

        # Batch all snippets into one call for speed
        combined = "\n---\n".join(snippets[:20])  # Limit for token budget

        prompt = f"""Extract ONLY person names and company names from this text.
Return JSON: {{"persons": ["Name1", "Name2"], "companies": ["Company1", "Company2"]}}
Only include real names, not job titles or generic terms.

TEXT:
{combined}

JSON:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}],
                # GPT-5 doesn't support temperature
            )

            content = response.choices[0].message.content
            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                persons = data.get('persons', [])
                companies = data.get('companies', [])
            else:
                persons, companies = [], []

        except Exception as e:
            print(f"[GPT-5-nano] Error: {e}")
            persons, companies = [], []

        elapsed = time.time() - start
        return ExtractionResult(persons, companies, "gpt-5-nano", elapsed, len(snippets))


class Gemini2Extractor:
    """Google Gemini 2.0 Flash extraction - FAST."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel('gemini-2.0-flash')
                print("[Gemini-2.0-Flash] Client initialized")
            except Exception as e:
                print(f"[Gemini-2.0-Flash] Failed: {e}")

    def extract(self, snippets: List[str]) -> ExtractionResult:
        """Extract entities using Gemini 2.0 Flash."""
        start = time.time()

        if not self.client:
            return ExtractionResult([], [], "gemini-2.0-flash", 0, len(snippets))

        # Batch all snippets
        combined = "\n---\n".join(snippets[:20])

        prompt = f"""Extract person names and company names from this text.
Return ONLY valid JSON: {{"persons": ["Name1"], "companies": ["Company1"]}}

TEXT:
{combined}"""

        try:
            response = self.client.generate_content(prompt)
            content = response.text

            # Parse JSON
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                persons = data.get('persons', [])
                companies = data.get('companies', [])
            else:
                persons, companies = [], []

        except Exception as e:
            print(f"[Gemini-2.0-Flash] Error: {e}")
            persons, companies = [], []

        elapsed = time.time() - start
        return ExtractionResult(persons, companies, "gemini-2.0-flash", elapsed, len(snippets))


class HybridExtractor:
    """
    Hybrid: Use GPT-5-nano for SPEED, Gemini for VERIFICATION.

    Strategy:
    1. GPT-5-nano extracts entities (fast, ~0.5s)
    2. Gemini verifies/filters false positives (parallel)
    3. Stream results as they come in
    """

    def __init__(self):
        self.gpt = GPT5NanoExtractor()
        self.gemini = Gemini2Extractor()

    async def extract_streaming(self, snippets: List[str]) -> AsyncIterator[Dict[str, Any]]:
        """Extract with streaming results."""

        # First pass: GPT-5-nano (fast)
        yield {"type": "status", "message": "Running GPT-5-nano extraction..."}
        gpt_result = self.gpt.extract(snippets)

        yield {
            "type": "partial",
            "model": "gpt-5-nano",
            "persons": gpt_result.persons,
            "companies": gpt_result.companies,
            "time": gpt_result.time_seconds
        }

        # Second pass: Gemini verification (parallel)
        yield {"type": "status", "message": "Verifying with Gemini..."}
        gemini_result = self.gemini.extract(snippets)

        yield {
            "type": "partial",
            "model": "gemini-2.0-flash",
            "persons": gemini_result.persons,
            "companies": gemini_result.companies,
            "time": gemini_result.time_seconds
        }

        # Merge: entities found by BOTH models = high confidence
        gpt_persons = set(p.lower() for p in gpt_result.persons)
        gemini_persons = set(p.lower() for p in gemini_result.persons)
        confirmed_persons = gpt_persons & gemini_persons

        gpt_companies = set(c.lower() for c in gpt_result.companies)
        gemini_companies = set(c.lower() for c in gemini_result.companies)
        confirmed_companies = gpt_companies & gemini_companies

        # Return original case versions
        final_persons = [p for p in gpt_result.persons if p.lower() in confirmed_persons]
        final_companies = [c for c in gpt_result.companies if c.lower() in confirmed_companies]

        # Also include high-confidence from either (could tune this)
        all_persons = list(set(gpt_result.persons + gemini_result.persons))
        all_companies = list(set(gpt_result.companies + gemini_result.companies))

        yield {
            "type": "final",
            "confirmed_persons": final_persons,
            "confirmed_companies": final_companies,
            "all_persons": all_persons,
            "all_companies": all_companies,
            "total_time": gpt_result.time_seconds + gemini_result.time_seconds
        }


async def run_speed_comparison(text: str):
    """Run all extractors and compare speed."""
    print("=" * 70)
    print("MULTI-MODEL NER SPEED COMPARISON")
    print("=" * 70)

    # Extract candidate snippets first
    print("\n[1] Extracting candidate snippets...")
    snippets = extract_candidate_snippets(text)
    print(f"    Found {len(snippets)} candidate snippets")

    # Initialize extractors
    print("\n[2] Initializing extractors...")
    gliner = GLiNERExtractor()
    gpt5 = GPT5NanoExtractor()
    gemini = Gemini2Extractor()

    # Run each
    print("\n[3] Running extractions...")
    print("-" * 50)

    # GLiNER
    print("\n  GLiNER (local):")
    gliner_result = gliner.extract(snippets)
    print(f"    Time: {gliner_result.time_seconds:.2f}s")
    print(f"    Persons: {len(gliner_result.persons)}")
    print(f"    Companies: {len(gliner_result.companies)}")
    for p in gliner_result.persons[:5]:
        print(f"      - {p}")

    # GPT-5-nano
    print("\n  GPT-5-nano (cloud):")
    gpt_result = gpt5.extract(snippets)
    print(f"    Time: {gpt_result.time_seconds:.2f}s")
    print(f"    Persons: {len(gpt_result.persons)}")
    print(f"    Companies: {len(gpt_result.companies)}")
    for p in gpt_result.persons[:5]:
        print(f"      - {p}")

    # Gemini
    print("\n  Gemini-2.0-Flash (cloud):")
    gemini_result = gemini.extract(snippets)
    print(f"    Time: {gemini_result.time_seconds:.2f}s")
    print(f"    Persons: {len(gemini_result.persons)}")
    print(f"    Companies: {len(gemini_result.companies)}")
    for p in gemini_result.persons[:5]:
        print(f"      - {p}")

    # Summary
    print("\n" + "=" * 70)
    print("SPEED COMPARISON SUMMARY")
    print("=" * 70)
    print(f"  GLiNER:          {gliner_result.time_seconds:.2f}s ({len(gliner_result.persons)} persons, {len(gliner_result.companies)} companies)")
    print(f"  GPT-5-nano:      {gpt_result.time_seconds:.2f}s ({len(gpt_result.persons)} persons, {len(gpt_result.companies)} companies)")
    print(f"  Gemini-2.0:      {gemini_result.time_seconds:.2f}s ({len(gemini_result.persons)} persons, {len(gemini_result.companies)} companies)")

    fastest = min([
        ("GLiNER", gliner_result.time_seconds),
        ("GPT-5-nano", gpt_result.time_seconds),
        ("Gemini-2.0", gemini_result.time_seconds)
    ], key=lambda x: x[1] if x[1] > 0 else 999)

    print(f"\n  FASTEST: {fastest[0]} ({fastest[1]:.2f}s)")

    return {
        "gliner": gliner_result,
        "gpt5": gpt_result,
        "gemini": gemini_result,
    }


if __name__ == "__main__":
    # Test with sample text
    sample_text = """
    SOAX is a proxy service founded by Robin Geuens and Sergey Konovalov.
    The company has partnerships with Google, Amazon, and Microsoft.
    CEO John Smith announced the new product line.
    Dr. Maria Garcia, Chief Technology Officer, leads the engineering team.
    SOAX Ltd. is headquartered in Europe. Contact sales@soax.com for more info.
    The company works with Fortune 500 clients including Apple Inc., Meta Corporation, and Tesla Holdings.
    """

    asyncio.run(run_speed_comparison(sample_text))
