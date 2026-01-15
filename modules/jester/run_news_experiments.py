#!/usr/bin/env python3
"""
News Source Experimentation - Extract CSS Selectors for Working Sources

Takes the classification results (news_scrape_classification.json) and runs
AI-powered schema extraction on working sources (JESTER_A and JESTER_C) to
learn their extraction patterns.

Usage:
    python run_news_experiments.py                    # Run on all working sources
    python run_news_experiments.py --jurisdiction GB  # Single jurisdiction
    python run_news_experiments.py --limit 50         # Test run
    python run_news_experiments.py --concurrent 10    # Adjust parallelism
    python run_news_experiments.py --resume           # Resume from checkpoint
"""

import asyncio
import json
import logging
import argparse
import os
import time
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import quote_plus
import httpx
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NewsExperiments")

# Paths
MATRIX_DIR = PROJECT_ROOT / "input_output" / "matrix"
CLASSIFICATION_PATH = MATRIX_DIR / "news_scrape_classification.json"
NEWS_SOURCES_PATH = MATRIX_DIR / "sources" / "news.json"
OUTPUT_PATH = MATRIX_DIR / "news_extraction_recipes.json"
CHECKPOINT_PATH = MATRIX_DIR / "news_experiment_checkpoint.json"

# Go binaries for JESTER_B/C
GO_BIN_DIR = PROJECT_ROOT / "BACKEND" / "modules" / "LINKLATER" / "scraping" / "web" / "go" / "bin"
ROD_BIN = GO_BIN_DIR / "rod_crawler"


NEWS_SCHEMA_PROMPT = """You are analyzing a news search results page.
Your task is to identify the RESULT STRUCTURE - what articles/links are shown.

Domain: {domain}
Query: {query}

I will show you the HTML content of the search results page.
Identify:

1. RESULT TYPE: Is it a list, cards, grid, or timeline?
2. CSS SELECTORS: What selectors extract each result?
3. FIELDS: title, url, snippet, date, author, thumbnail

HTML Content (truncated):
{html_snippet}

Return JSON:
{{
    "result_type": "list|cards|grid|timeline",
    "results_container": "CSS selector for all results wrapper",
    "article_selector": "CSS selector for each result item",
    "fields": {{
        "title": {{
            "selector": "h2 a|.headline a|.title",
            "attribute": "text|href",
            "required": true
        }},
        "url": {{
            "selector": "a.article-link|h2 a",
            "attribute": "href",
            "required": true
        }},
        "snippet": {{
            "selector": ".summary|.excerpt|p",
            "attribute": "text",
            "required": false
        }},
        "date": {{
            "selector": "time|.date|.timestamp",
            "attribute": "datetime|text",
            "required": false
        }},
        "author": {{
            "selector": ".author|.byline",
            "attribute": "text",
            "required": false
        }}
    }},
    "pagination": {{
        "has_pagination": true|false,
        "next_selector": ".next|.pagination a[rel=next]"
    }},
    "notes": "Any observations about the structure"
}}

Only include selectors you can actually identify from the HTML.
Be specific with CSS selectors that will work for extraction.
"""


@dataclass
class NewsExtractionRecipe:
    """Extraction recipe for a news source."""
    source_id: str
    domain: str
    jurisdiction: str
    scrape_method: str  # JESTER_A, JESTER_C
    result_type: str = "list"
    results_container: Optional[str] = None
    article_selector: Optional[str] = None
    fields: Dict[str, Any] = field(default_factory=dict)
    pagination: Dict[str, Any] = field(default_factory=dict)
    success: bool = False
    tested_at: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class ModelPool:
    """Rotate AI calls across providers to avoid rate limits."""

    def __init__(self):
        self.providers = []
        self._setup_providers()
        self.call_count = 0

    def _setup_providers(self):
        """Initialize available AI providers."""
        # Gemini
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                self.providers.append({
                    "name": "gemini",
                    "model": genai.GenerativeModel("gemini-2.0-flash-exp"),
                    "call": self._call_gemini
                })
                logger.info("Gemini provider ready")
            except Exception as e:
                logger.warning(f"Gemini setup failed: {e}")

        # Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic
                self.providers.append({
                    "name": "anthropic",
                    "client": anthropic.Anthropic(api_key=anthropic_key),
                    "call": self._call_anthropic
                })
                logger.info("Anthropic provider ready")
            except Exception as e:
                logger.warning(f"Anthropic setup failed: {e}")

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self.providers.append({
                    "name": "openai",
                    "client": AsyncOpenAI(api_key=openai_key),
                    "call": self._call_openai
                })
                logger.info("OpenAI provider ready")
            except Exception as e:
                logger.warning(f"OpenAI setup failed: {e}")

        if not self.providers:
            raise RuntimeError("No AI providers available! Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY")

    async def _call_gemini(self, provider: Dict, prompt: str) -> str:
        response = await asyncio.to_thread(
            provider["model"].generate_content,
            prompt
        )
        return response.text

    async def _call_anthropic(self, provider: Dict, prompt: str) -> str:
        response = await asyncio.to_thread(
            provider["client"].messages.create,
            model="claude-3-5-haiku-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    async def _call_openai(self, provider: Dict, prompt: str) -> str:
        response = await provider["client"].chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )
        return response.choices[0].message.content

    async def call(self, prompt: str) -> str:
        """Call AI with round-robin provider selection."""
        provider = self.providers[self.call_count % len(self.providers)]
        self.call_count += 1
        try:
            return await provider["call"](provider, prompt)
        except Exception as e:
            logger.warning(f"{provider['name']} failed: {e}")
            # Try next provider
            if len(self.providers) > 1:
                next_provider = self.providers[self.call_count % len(self.providers)]
                self.call_count += 1
                return await next_provider["call"](next_provider, prompt)
            raise


class NewsExperimenter:
    """Extracts CSS selectors from news search result pages."""

    def __init__(self):
        self.http = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        self.model_pool = ModelPool()
        self.rod_available = ROD_BIN.exists()

    async def close(self):
        await self.http.aclose()

    async def scrape(self, url: str, method: str) -> tuple[str, float]:
        """Scrape URL using appropriate method."""
        start = time.time()

        if method == "JESTER_A":
            try:
                resp = await self.http.get(url, timeout=15)
                latency = time.time() - start
                if resp.status_code == 200:
                    return resp.text, latency
            except Exception as e:
                logger.debug(f"JESTER_A failed: {e}")
            return "", time.time() - start

        elif method == "JESTER_C" and self.rod_available:
            try:
                result = await asyncio.create_subprocess_exec(
                    str(ROD_BIN),
                    "test", url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(result.communicate(), timeout=30)
                latency = time.time() - start

                if result.returncode == 0 and stdout:
                    data = json.loads(stdout.decode())
                    # Rod returns HTML in the response
                    html = data.get("html", "") or data.get("content", "")
                    return html, latency
            except Exception as e:
                logger.debug(f"JESTER_C failed: {e}")
            return "", time.time() - start

        return "", 0

    def _extract_snippet(self, html: str, max_len: int = 15000) -> str:
        """Extract relevant snippet from HTML for AI analysis."""
        # Try to find main content area
        import re

        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Look for results container patterns
        patterns = [
            r'<main[^>]*>(.*?)</main>',
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]*class="[^"]*search-result[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*results[^"]*"[^>]*>(.*?)</div>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match and len(match.group(1)) > 500:
                return match.group(1)[:max_len]

        # Fall back to body content
        body = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body:
            return body.group(1)[:max_len]

        return html[:max_len]

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from AI response."""
        import re

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # Try the whole text
        try:
            return json.loads(text)
        except:
            pass

        # Try to find JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass

        return None

    async def extract_recipe(self, source: Dict) -> NewsExtractionRecipe:
        """Extract CSS selectors for a news source."""
        domain = source.get("domain", "")
        jurisdiction = source.get("jurisdiction", "")
        method = source.get("method", "JESTER_A")
        template = source.get("search_template", "")
        source_id = f"{jurisdiction}_{domain}".replace(".", "_")

        recipe = NewsExtractionRecipe(
            source_id=source_id,
            domain=domain,
            jurisdiction=jurisdiction,
            scrape_method=method,
            tested_at=datetime.now(UTC).isoformat()
        )

        if not template or "{q}" not in template:
            recipe.notes = "No valid search template"
            return recipe

        # Use a test query
        test_url = template.replace("{q}", quote_plus("news"))

        # Scrape
        html, latency = await self.scrape(test_url, method)
        if not html or len(html) < 500:
            recipe.notes = f"Scrape failed or insufficient content ({len(html)} chars)"
            return recipe

        # Extract snippet for AI
        snippet = self._extract_snippet(html)

        # AI analysis
        prompt = NEWS_SCHEMA_PROMPT.format(
            domain=domain,
            query="news",
            html_snippet=snippet
        )

        try:
            ai_response = await self.model_pool.call(prompt)
            schema = self._parse_json(ai_response)

            if schema:
                recipe.result_type = schema.get("result_type", "list")
                recipe.results_container = schema.get("results_container")
                recipe.article_selector = schema.get("article_selector")
                recipe.fields = schema.get("fields", {})
                recipe.pagination = schema.get("pagination", {})
                recipe.notes = schema.get("notes", "")
                recipe.success = bool(recipe.article_selector or recipe.fields)
            else:
                recipe.notes = "Failed to parse AI response"

        except Exception as e:
            recipe.notes = f"AI analysis error: {str(e)[:100]}"

        return recipe

    async def run_batch(
        self,
        sources: List[Dict],
        output_path: Path,
        concurrent: int = 10,
        resume: bool = True
    ) -> List[NewsExtractionRecipe]:
        """Run extraction on multiple sources."""
        # Load checkpoint
        done: Dict[str, Dict] = {}
        if resume and output_path.exists():
            try:
                with open(output_path) as f:
                    data = json.load(f)
                    for r in data.get("recipes", []):
                        done[r.get("source_id")] = r
                logger.info(f"Resuming: {len(done)} already processed")
            except:
                pass

        remaining = [s for s in sources if f"{s.get('jurisdiction')}_{s.get('domain')}".replace(".", "_") not in done]
        logger.info(f"Processing {len(remaining)} sources ({len(done)} skipped)")

        recipes = list(done.values())
        sem = asyncio.Semaphore(concurrent)
        save_lock = asyncio.Lock()
        success_count = 0

        async def process(source: Dict, idx: int) -> NewsExtractionRecipe:
            nonlocal success_count
            async with sem:
                recipe = await self.extract_recipe(source)

                if recipe.success:
                    success_count += 1
                    logger.info(f"[{idx+1}/{len(remaining)}] {source['domain']} - ✓ Found {len(recipe.fields)} fields")
                else:
                    logger.info(f"[{idx+1}/{len(remaining)}] {source['domain']} - ✗ {recipe.notes[:50]}")

                async with save_lock:
                    recipes.append(recipe.to_dict())
                    # Save every 10
                    if len(recipes) % 10 == 0:
                        self._save(output_path, recipes)

                # Small delay
                await asyncio.sleep(0.5)
                return recipe

        tasks = [process(s, i) for i, s in enumerate(remaining)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final save
        self._save(output_path, recipes)

        logger.info(f"\n{'='*60}")
        logger.info(f"EXTRACTION COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total: {len(recipes)}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Failed: {len(recipes) - success_count}")
        logger.info(f"{'='*60}")

        return [NewsExtractionRecipe(**r) if isinstance(r, dict) else r for r in recipes]

    def _save(self, path: Path, recipes: List):
        """Save recipes to JSON."""
        data = {
            "extracted_at": datetime.now(UTC).isoformat(),
            "total": len(recipes),
            "success": sum(1 for r in recipes if (r.get("success") if isinstance(r, dict) else r.success)),
            "recipes": recipes
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


def load_working_sources() -> List[Dict]:
    """Load sources that passed classification (JESTER_A or JESTER_C)."""
    if not CLASSIFICATION_PATH.exists():
        raise FileNotFoundError(f"Run classify_news_sources.py first! Missing: {CLASSIFICATION_PATH}")

    with open(CLASSIFICATION_PATH) as f:
        data = json.load(f)

    # Also load original sources for templates
    if not NEWS_SOURCES_PATH.exists():
        raise FileNotFoundError(f"Missing news sources: {NEWS_SOURCES_PATH}")

    with open(NEWS_SOURCES_PATH) as f:
        original = json.load(f)

    # Build domain -> source mapping
    domain_to_source = {}
    for jur, entries in original.items():
        for entry in entries:
            entry["jurisdiction"] = jur
            domain_to_source[entry.get("domain", "")] = entry

    # Filter working sources
    working = []
    for result in data.get("results", []):
        method = result.get("method", "")
        if method in ["JESTER_A", "JESTER_C"]:
            domain = result.get("domain", "")
            if domain in domain_to_source:
                source = domain_to_source[domain].copy()
                source["method"] = method
                source["classification"] = result
                working.append(source)

    return working


async def main():
    parser = argparse.ArgumentParser(description="Extract CSS selectors from news sources")
    parser.add_argument("--jurisdiction", "-j", help="Filter by jurisdiction (e.g., GB)")
    parser.add_argument("--limit", type=int, help="Limit number of sources")
    parser.add_argument("--concurrent", type=int, default=10, help="Max concurrent requests")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from checkpoint")
    parser.add_argument("--output", "-o", help="Output path")
    args = parser.parse_args()

    logger.info("Loading working news sources...")
    sources = load_working_sources()
    logger.info(f"Loaded {len(sources)} working sources")

    if args.jurisdiction:
        sources = [s for s in sources if s.get("jurisdiction") == args.jurisdiction.upper()]
        logger.info(f"Filtered to {len(sources)} sources in {args.jurisdiction}")

    if args.limit:
        sources = sources[:args.limit]
        logger.info(f"Limited to {len(sources)} sources")

    output_path = Path(args.output) if args.output else OUTPUT_PATH

    experimenter = NewsExperimenter()
    try:
        await experimenter.run_batch(
            sources,
            output_path,
            concurrent=args.concurrent,
            resume=args.resume
        )
    finally:
        await experimenter.close()

    logger.info(f"\nRecipes saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
