#!/usr/bin/env python3
"""
Hybrid Entity Extractor - Maximum Speed + Quality

Strategy:
1. If total URLs <= 20: Use Gemini for ALL (fast enough, best quality)
2. If > 20 URLs:
   - Priority URLs (main domain, about, team, investors, etc.) -> Gemini + GPT-5-nano in PARALLEL
   - Rest -> GLiNER (fast local, no API cost)
3. Merge results with confidence scoring

Priority URL keywords (entity-rich pages):
- Main domain root (/)
- about, team, leadership, management, board, directors
- contact, contacts, get-in-touch
- investor, investors, shareholders, annual-report
- company, corporate, overview, history
- subsidiaries, affiliates, partners
- legal, privacy, terms, imprint
- press, news, media
- careers, jobs (often has founder/CEO quotes)
"""

import os
import re
import json
import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
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


# Priority URL patterns - pages likely to contain entity-rich content
PRIORITY_URL_PATTERNS = [
    # Exact paths
    r'^https?://[^/]+/?$',  # Root domain
    r'/about/?$',
    r'/about-us/?$',
    r'/team/?$',
    r'/our-team/?$',
    r'/leadership/?$',
    r'/management/?$',
    r'/board/?$',
    r'/directors/?$',
    r'/contact/?$',
    r'/contacts/?$',
    r'/get-in-touch/?$',
    r'/investor/?$',
    r'/investors/?$',
    r'/investor-relations/?$',
    r'/shareholders/?$',
    r'/annual-report/?',
    r'/company/?$',
    r'/corporate/?$',
    r'/overview/?$',
    r'/history/?$',
    r'/subsidiaries/?$',
    r'/affiliates/?$',
    r'/partners/?$',
    r'/legal/?$',
    r'/privacy/?$',
    r'/terms/?$',
    r'/imprint/?$',
    r'/impressum/?$',
    r'/press/?$',
    r'/news/?$',
    r'/media/?$',
    r'/careers/?$',
    r'/jobs/?$',
]

# Compiled patterns for speed
PRIORITY_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in PRIORITY_URL_PATTERNS]


def is_priority_url(url: str) -> bool:
    """Check if URL is a priority page for entity extraction."""
    for pattern in PRIORITY_PATTERNS_COMPILED:
        if pattern.search(url):
            return True
    return False


@dataclass
class ExtractedEntity:
    """Entity with provenance and confidence."""
    value: str
    type: str  # person, company
    source_model: str  # gemini, gpt5nano, gliner, merged
    confidence: float = 1.0
    archive_urls: List[str] = field(default_factory=list)
    found_in_snapshots: int = 0


class HybridEntityExtractor:
    """
    Hybrid extractor using multiple models in parallel for maximum speed.

    - Gemini 2.0 Flash: Best quality, ~1s per batch
    - GPT-5-nano: Fast, good quality, ~0.5s per batch
    - GLiNER: Local, no API cost, good for bulk

    Strategy:
    - Small batches (<=20): Gemini only (fast enough)
    - Large batches: Gemini+GPT5 parallel for priority, GLiNER for rest
    """

    GEMINI_ONLY_THRESHOLD = 20  # Use Gemini for all if <= this many URLs

    def __init__(self):
        self._gemini = None
        self._gpt5 = None
        self._gliner = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._init_extractors()

    def _init_extractors(self):
        """Initialize available extractors."""
        # Gemini
        try:
            from extractors.gemini_ner import get_gemini_extractor
            self._gemini = get_gemini_extractor()
            print("[Hybrid] Gemini extractor ready")
        except Exception as e:
            print(f"[Hybrid] Gemini not available: {e}")

        # GPT-5-nano
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                from openai import OpenAI
                self._gpt5_client = OpenAI(api_key=api_key)
                self._gpt5 = True
                print("[Hybrid] GPT-5-nano ready")
        except Exception as e:
            print(f"[Hybrid] GPT-5-nano not available: {e}")
            self._gpt5 = None

        # GLiNER (lazy load to avoid startup cost)
        self._gliner_model = None

    def _get_gliner(self):
        """Lazy load GLiNER model."""
        if self._gliner_model is None:
            try:
                from gliner import GLiNER
                self._gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
                print("[Hybrid] GLiNER model loaded")
            except Exception as e:
                print(f"[Hybrid] GLiNER not available: {e}")
        return self._gliner_model

    def _extract_with_gemini(self, text: str) -> Dict[str, List[str]]:
        """Extract using Gemini."""
        if not self._gemini:
            return {"persons": [], "companies": []}
        return self._gemini.extract_sync(text)

    def _extract_with_gpt5(self, text: str) -> Dict[str, List[str]]:
        """Extract using GPT-5-nano."""
        if not self._gpt5:
            return {"persons": [], "companies": []}

        # Truncate text for token budget
        text = text[:8000]

        prompt = f"""Extract person names and company names from this text.
Return ONLY valid JSON: {{"persons": ["Name1"], "companies": ["Company1"]}}

TEXT:
{text}"""

        try:
            response = self._gpt5_client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content

            # Parse JSON
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "persons": data.get("persons", []),
                    "companies": data.get("companies", [])
                }
        except Exception as e:
            print(f"[Hybrid] GPT-5-nano error: {e}")

        return {"persons": [], "companies": []}

    def _extract_with_gliner(self, text: str) -> Dict[str, List[str]]:
        """Extract using GLiNER (local model)."""
        model = self._get_gliner()
        if not model:
            return {"persons": [], "companies": []}

        persons = []
        companies = []

        # REGEX-FIRST: Extract candidate snippets
        from extractors.gemini_ner import extract_candidate_snippets
        snippets = extract_candidate_snippets(text, max_snippets=20)

        labels = ["person name", "organization", "company"]

        for snippet in snippets:
            try:
                results = model.predict_entities(snippet, labels, threshold=0.5)
                for ent in results:
                    value = ent.get('text', '').strip()
                    ent_type = ent.get('label', '')

                    if len(value) < 3:
                        continue

                    if ent_type == 'person name':
                        if ' ' in value and any(w[0].isupper() for w in value.split() if w):
                            persons.append(value)
                    elif ent_type in ('organization', 'company'):
                        companies.append(value)
            except Exception as e:

                print(f"[LINKLATER] Error: {e}")

                pass

        return {"persons": list(set(persons)), "companies": list(set(companies))}

    async def extract_parallel(
        self,
        text: str,
        url: str = "",
        use_all_models: bool = False
    ) -> Dict[str, Any]:
        """
        Extract entities using multiple models in parallel.

        Args:
            text: Text to extract from
            url: URL for priority detection
            use_all_models: Force use of all models (for priority URLs)

        Returns:
            Dict with entities and metadata
        """
        is_priority = use_all_models or is_priority_url(url)

        loop = asyncio.get_event_loop()

        if is_priority and self._gemini and self._gpt5:
            # Run Gemini and GPT-5 in parallel for priority URLs
            gemini_task = loop.run_in_executor(
                self._executor, self._extract_with_gemini, text
            )
            gpt5_task = loop.run_in_executor(
                self._executor, self._extract_with_gpt5, text
            )

            gemini_result, gpt5_result = await asyncio.gather(
                gemini_task, gpt5_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(gemini_result, Exception):
                gemini_result = {"persons": [], "companies": []}
            if isinstance(gpt5_result, Exception):
                gpt5_result = {"persons": [], "companies": []}

            # Merge results - entities found by BOTH get higher confidence
            gemini_persons = set(p.lower() for p in gemini_result.get("persons", []))
            gpt5_persons = set(p.lower() for p in gpt5_result.get("persons", []))

            gemini_companies = set(c.lower() for c in gemini_result.get("companies", []))
            gpt5_companies = set(c.lower() for c in gpt5_result.get("companies", []))

            # High confidence: found by both
            confirmed_persons = gemini_persons & gpt5_persons
            confirmed_companies = gemini_companies & gpt5_companies

            # All entities (union)
            all_persons = gemini_persons | gpt5_persons
            all_companies = gemini_companies | gpt5_companies

            # Build result with original case from Gemini (usually better)
            persons = []
            for p in gemini_result.get("persons", []) + gpt5_result.get("persons", []):
                if p.lower() in all_persons:
                    confidence = 1.0 if p.lower() in confirmed_persons else 0.7
                    persons.append({
                        "value": p,
                        "confidence": confidence,
                        "source": "both" if p.lower() in confirmed_persons else "single"
                    })
                    all_persons.discard(p.lower())  # Remove to avoid duplicates

            companies = []
            for c in gemini_result.get("companies", []) + gpt5_result.get("companies", []):
                if c.lower() in all_companies:
                    confidence = 1.0 if c.lower() in confirmed_companies else 0.7
                    companies.append({
                        "value": c,
                        "confidence": confidence,
                        "source": "both" if c.lower() in confirmed_companies else "single"
                    })
                    all_companies.discard(c.lower())

            return {
                "persons": persons,
                "companies": companies,
                "method": "parallel_gemini_gpt5",
                "is_priority": True
            }

        elif self._gemini:
            # Gemini only
            result = await loop.run_in_executor(
                self._executor, self._extract_with_gemini, text
            )
            return {
                "persons": [{"value": p, "confidence": 0.9, "source": "gemini"} for p in result.get("persons", [])],
                "companies": [{"value": c, "confidence": 0.9, "source": "gemini"} for c in result.get("companies", [])],
                "method": "gemini_only",
                "is_priority": is_priority
            }

        else:
            # GLiNER fallback
            result = await loop.run_in_executor(
                self._executor, self._extract_with_gliner, text
            )
            return {
                "persons": [{"value": p, "confidence": 0.6, "source": "gliner"} for p in result.get("persons", [])],
                "companies": [{"value": c, "confidence": 0.6, "source": "gliner"} for c in result.get("companies", [])],
                "method": "gliner_fallback",
                "is_priority": is_priority
            }

    async def extract_batch(
        self,
        texts_with_urls: List[Tuple[str, str, str]],  # (text, url, timestamp)
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Extract entities from a batch of texts.

        Strategy:
        - If batch <= 20: Use Gemini for all
        - If batch > 20: Priority URLs get parallel Gemini+GPT5, rest get GLiNER

        Args:
            texts_with_urls: List of (text, url, timestamp) tuples
            progress_callback: Optional async callback for progress updates

        Returns:
            Aggregated entity results
        """
        total = len(texts_with_urls)

        # Track entities: (type, value_lower) -> {value, urls, count, confidence}
        entity_tracker: Dict[Tuple[str, str], Dict] = defaultdict(
            lambda: {"value": "", "urls": [], "count": 0, "max_confidence": 0}
        )

        use_gemini_for_all = total <= self.GEMINI_ONLY_THRESHOLD

        # Separate priority and non-priority URLs
        priority_items = []
        regular_items = []

        for text, url, timestamp in texts_with_urls:
            if use_gemini_for_all or is_priority_url(url):
                priority_items.append((text, url, timestamp))
            else:
                regular_items.append((text, url, timestamp))

        processed = 0

        # Process priority items with parallel models
        for text, url, timestamp in priority_items:
            archive_url = f"https://web.archive.org/web/{timestamp}/{url}"

            result = await self.extract_parallel(text, url, use_all_models=use_gemini_for_all)

            # Track persons
            for p in result.get("persons", []):
                key = ("person", p["value"].lower())
                entity_tracker[key]["value"] = p["value"]
                entity_tracker[key]["urls"].append(archive_url)
                entity_tracker[key]["count"] += 1
                entity_tracker[key]["max_confidence"] = max(
                    entity_tracker[key]["max_confidence"],
                    p.get("confidence", 0.9)
                )

            # Track companies
            for c in result.get("companies", []):
                key = ("company", c["value"].lower())
                entity_tracker[key]["value"] = c["value"]
                entity_tracker[key]["urls"].append(archive_url)
                entity_tracker[key]["count"] += 1
                entity_tracker[key]["max_confidence"] = max(
                    entity_tracker[key]["max_confidence"],
                    c.get("confidence", 0.9)
                )

            processed += 1
            if progress_callback and processed % 5 == 0:
                await progress_callback({
                    "processed": processed,
                    "total": total,
                    "percent": int(100 * processed / total),
                    "priority_done": processed >= len(priority_items)
                })

        # Process regular items with GLiNER (if any)
        if regular_items:
            loop = asyncio.get_event_loop()

            for text, url, timestamp in regular_items:
                archive_url = f"https://web.archive.org/web/{timestamp}/{url}"

                result = await loop.run_in_executor(
                    self._executor, self._extract_with_gliner, text
                )

                for p in result.get("persons", []):
                    key = ("person", p.lower())
                    entity_tracker[key]["value"] = p
                    entity_tracker[key]["urls"].append(archive_url)
                    entity_tracker[key]["count"] += 1
                    entity_tracker[key]["max_confidence"] = max(
                        entity_tracker[key]["max_confidence"], 0.6
                    )

                for c in result.get("companies", []):
                    key = ("company", c.lower())
                    entity_tracker[key]["value"] = c
                    entity_tracker[key]["urls"].append(archive_url)
                    entity_tracker[key]["count"] += 1
                    entity_tracker[key]["max_confidence"] = max(
                        entity_tracker[key]["max_confidence"], 0.6
                    )

                processed += 1
                if progress_callback and processed % 10 == 0:
                    await progress_callback({
                        "processed": processed,
                        "total": total,
                        "percent": int(100 * processed / total)
                    })

        # Build final results
        persons = []
        companies = []

        for (ent_type, _), data in entity_tracker.items():
            entity = {
                "value": data["value"],
                "type": ent_type,
                "archive_urls": list(set(data["urls"]))[:5],
                "found_in_snapshots": data["count"],
                "confidence": data["max_confidence"]
            }

            if ent_type == "person":
                persons.append(entity)
            else:
                companies.append(entity)

        # Sort by confidence * count (quality + frequency)
        persons.sort(key=lambda x: -(x["confidence"] * x["found_in_snapshots"]))
        companies.sort(key=lambda x: -(x["confidence"] * x["found_in_snapshots"]))

        return {
            "persons": persons,
            "companies": companies,
            "stats": {
                "total_processed": total,
                "priority_urls": len(priority_items),
                "regular_urls": len(regular_items),
                "method": "gemini_all" if use_gemini_for_all else "hybrid"
            }
        }


# Module-level singleton
_HYBRID_EXTRACTOR: Optional[HybridEntityExtractor] = None


def get_hybrid_extractor() -> HybridEntityExtractor:
    """Get or create singleton hybrid extractor."""
    global _HYBRID_EXTRACTOR
    if _HYBRID_EXTRACTOR is None:
        _HYBRID_EXTRACTOR = HybridEntityExtractor()
    return _HYBRID_EXTRACTOR


async def test_hybrid():
    """Test hybrid extraction."""
    import time

    print("=" * 70)
    print("HYBRID ENTITY EXTRACTOR TEST")
    print("=" * 70)

    extractor = get_hybrid_extractor()

    # Test text
    sample_text = """
    SOAX is a proxy service founded by Robin Geuens and Sergey Konovalov.
    The company has partnerships with Google, Amazon, and Microsoft.
    CEO John Smith announced the new product line.
    Dr. Maria Garcia, Chief Technology Officer, leads the engineering team.
    SOAX Ltd. is headquartered in Europe. Contact sales@soax.com for more info.
    The company works with Fortune 500 clients including Apple Inc., Meta Corporation, and Tesla Holdings.
    """

    # Test priority URL detection
    test_urls = [
        "https://soax.com/",
        "https://soax.com/about",
        "https://soax.com/team",
        "https://soax.com/investors",
        "https://soax.com/blog/some-post",
        "https://soax.com/pricing",
    ]

    print("\nPriority URL Detection:")
    for url in test_urls:
        is_p = is_priority_url(url)
        print(f"  {url}: {'PRIORITY' if is_p else 'regular'}")

    # Test single extraction
    print("\n" + "-" * 40)
    print("Single URL Extraction (parallel Gemini + GPT-5):")
    print("-" * 40)

    start = time.time()
    result = await extractor.extract_parallel(sample_text, "https://soax.com/about", use_all_models=True)
    elapsed = time.time() - start

    print(f"Time: {elapsed:.2f}s")
    print(f"Method: {result['method']}")
    print(f"Persons: {len(result['persons'])}")
    for p in result['persons'][:5]:
        print(f"  - {p['value']} (conf: {p['confidence']}, source: {p['source']})")
    print(f"Companies: {len(result['companies'])}")
    for c in result['companies'][:5]:
        print(f"  - {c['value']} (conf: {c['confidence']}, source: {c['source']})")

    # Test batch extraction
    print("\n" + "-" * 40)
    print("Batch Extraction (5 URLs):")
    print("-" * 40)

    batch = [
        (sample_text, "soax.com/", "20240101120000"),
        (sample_text + " VP David Chen joined from Oracle Corp.", "soax.com/about", "20240201120000"),
        (sample_text, "soax.com/pricing", "20240301120000"),
        ("Contact our sales team at sales@soax.com", "soax.com/contact", "20240401120000"),
        ("Blog post about proxies and web scraping.", "soax.com/blog/proxies", "20240501120000"),
    ]

    start = time.time()

    async def progress(p):
        print(f"  Progress: {p['percent']}%")

    result = await extractor.extract_batch(batch, progress_callback=progress)
    elapsed = time.time() - start

    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Stats: {result['stats']}")
    print(f"\nPersons found: {len(result['persons'])}")
    for p in result['persons'][:10]:
        print(f"  - {p['value']} (x{p['found_in_snapshots']}, conf: {p['confidence']:.1f})")
    print(f"\nCompanies found: {len(result['companies'])}")
    for c in result['companies'][:10]:
        print(f"  - {c['value']} (x{c['found_in_snapshots']}, conf: {c['confidence']:.1f})")


if __name__ == "__main__":
    asyncio.run(test_hybrid())
