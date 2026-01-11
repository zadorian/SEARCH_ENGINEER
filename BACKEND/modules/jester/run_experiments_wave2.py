#!/usr/bin/env python3
"""
Wave 2 Experimentation - Real Company Names with Retries

Uses real company names from test_queries_v2.json and tries 2-3 per source
before considering it a failure. Focuses on sources that had "no_results"
in Wave 1.

Usage:
    python run_experiments_wave2.py                    # Run on no_results sources
    python run_experiments_wave2.py --all             # Run on ALL sources
    python run_experiments_wave2.py --concurrent 20   # Adjust parallelism
    python run_experiments_wave2.py --max-tries 3     # Queries per source
"""

import asyncio
import json
import logging
import argparse
import os
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
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
logger = logging.getLogger("Wave2")

# Paths
SOURCES_V3_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"
TEST_QUERIES_PATH = Path(__file__).parent / "test_queries_v2.json"
CHECKPOINT_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "wave2_checkpoint.json"
RESULTS_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "wave2_experiments.json"

# Fallback queries by jurisdiction type
FALLBACK_QUERIES = {
    "HU": ["OTP Bank", "Richter Gedeon", "Wizz Air"],
    "DE": ["Deutsche Bank", "Siemens", "Volkswagen"],
    "AT": ["OMV", "Erste Group", "Voestalpine"],
    "CH": ["Nestlé", "UBS", "Novartis"],
    "FR": ["BNP Paribas", "Total", "L'Oréal"],
    "ES": ["Banco Santander", "Telefónica", "Iberdrola"],
    "IT": ["Eni", "Enel", "UniCredit"],
    "NL": ["ING", "Shell", "Philips"],
    "BE": ["AB InBev", "KBC", "Solvay"],
    "PL": ["PKO Bank", "PGE", "PKN Orlen"],
    "CZ": ["CEZ", "Skoda", "Agrofert"],
    "RO": ["Petrom", "BCR", "Banca Transilvania"],
    "BG": ["Lukoil Bulgaria", "Aurubis Bulgaria", "DSK Bank"],
    "GB": ["HSBC", "BP", "Barclays"],
    "IE": ["CRH", "Ryanair", "Kerry Group"],
    "US": ["Apple", "Microsoft", "Amazon"],
    "CA": ["Royal Bank", "TD Bank", "Shopify"],
    "AU": ["Commonwealth Bank", "BHP", "Westpac"],
    "BR": ["Petrobras", "Itaú", "Vale"],
    "AR": ["YPF", "Mercado Libre", "Telecom Argentina"],
    "MX": ["Pemex", "América Móvil", "Grupo Bimbo"],
    "GLOBAL": ["Bank", "Holdings", "International"],
}


@dataclass
class Wave2Result:
    """Result of Wave 2 experimentation on a source."""
    source_id: str
    jurisdiction: str
    domain: str
    status: str  # "success", "no_results", "blocked", "failed"
    queries_tried: List[str]
    successful_query: Optional[str] = None
    output_schema: Optional[Dict] = None
    scrape_method: str = "unknown"
    avg_latency: float = 0.0
    tested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


class ModelPool:
    """Rotates AI requests across providers to avoid rate limits."""

    def __init__(self):
        self.providers = []
        self.current_idx = 0
        self._setup_providers()

    def _setup_providers(self):
        """Setup available AI providers."""
        # Gemini
        if os.getenv("GEMINI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                self.providers.append({
                    "name": "gemini",
                    "model": genai.GenerativeModel("gemini-2.0-flash-exp"),
                    "call": self._call_gemini
                })
                logger.info("Gemini provider added")
            except Exception as e:
                logger.warning(f"Gemini setup failed: {e}")

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.providers.append({
                    "name": "anthropic",
                    "client": anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")),
                    "call": self._call_anthropic
                })
                logger.info("Anthropic provider added")
            except Exception as e:
                logger.warning(f"Anthropic setup failed: {e}")

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                import openai
                self.providers.append({
                    "name": "openai",
                    "client": openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY")),
                    "call": self._call_openai
                })
                logger.info("OpenAI provider added")
            except Exception as e:
                logger.warning(f"OpenAI setup failed: {e}")

        logger.info(f"Model pool initialized with {len(self.providers)} providers")

    async def _call_gemini(self, provider: dict, prompt: str) -> str:
        response = provider["model"].generate_content(prompt)
        return response.text

    async def _call_anthropic(self, provider: dict, prompt: str) -> str:
        response = provider["client"].messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    async def _call_openai(self, provider: dict, prompt: str) -> str:
        response = provider["client"].chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        return response.choices[0].message.content

    async def call(self, prompt: str) -> str:
        """Call next provider in rotation."""
        if not self.providers:
            raise ValueError("No AI providers available")

        # Try each provider up to 2 times
        attempts = len(self.providers) * 2

        for _ in range(attempts):
            provider = self.providers[self.current_idx]
            self.current_idx = (self.current_idx + 1) % len(self.providers)

            try:
                result = await provider["call"](provider, prompt)
                return result
            except Exception as e:
                logger.warning(f"Provider {provider['name']} failed: {str(e)[:100]}")
                await asyncio.sleep(1)

        raise Exception("All providers failed")


class Wave2Experimenter:
    """Run Wave 2 experiments with real company names."""

    OUTPUT_SCHEMA_PROMPT = """Analyze this search results page and extract the OUTPUT SCHEMA.

URL: {url}
Query: {query}

HTML (truncated):
{html}

Extract the structure of results returned. Focus on:
1. What fields are shown for each result?
2. What CSS selectors identify each field?
3. Is it a table, list, or cards layout?

Return JSON:
{{
  "result_type": "table|list|cards|single_record|json_api",
  "has_results": true/false,
  "fields": [
    {{"name": "company_name", "css_selector": "td.name, .company-name", "example": "Example Corp"}},
    {{"name": "registration_number", "css_selector": "td.reg-num", "example": "12345678"}},
    {{"name": "status", "css_selector": "span.status", "example": "Active"}}
  ],
  "pagination": true/false,
  "total_results_selector": ".results-count",
  "notes": "Any relevant observations"
}}

Return ONLY valid JSON, no markdown."""

    def __init__(self, concurrent: int = 15, max_tries: int = 3):
        self.concurrent = concurrent
        self.max_tries = max_tries
        self.semaphore = asyncio.Semaphore(concurrent)
        self.http = None
        self.model_pool = None
        self.test_queries = {}
        self.results: Dict[str, Wave2Result] = {}
        self.stats = {
            "success": 0,
            "no_results": 0,
            "blocked": 0,
            "failed": 0,
            "total": 0
        }

    async def setup(self):
        """Initialize HTTP client and model pool."""
        self.http = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        self.model_pool = ModelPool()

        # Load test queries
        if TEST_QUERIES_PATH.exists():
            with open(TEST_QUERIES_PATH) as f:
                data = json.load(f)
                self.test_queries = data.get("queries", {})
                logger.info(f"Loaded test queries for {len(self.test_queries)} jurisdictions")
        else:
            logger.warning("No test_queries_v2.json found, using fallbacks")
            self.test_queries = FALLBACK_QUERIES

    async def close(self):
        if self.http:
            await self.http.aclose()

    def get_test_queries(self, jurisdiction: str) -> List[str]:
        """Get test queries for a jurisdiction."""
        queries = self.test_queries.get(jurisdiction, [])
        if not queries:
            queries = self.test_queries.get("GLOBAL", FALLBACK_QUERIES["GLOBAL"])

        # Shuffle and return up to max_tries
        queries = list(queries)
        random.shuffle(queries)
        return queries[:self.max_tries]

    async def scrape_url(self, url: str) -> tuple[str, str, float]:
        """
        Scrape a URL. Returns (html, method, latency).
        Method: "direct" if simple HTTP worked, "firecrawl" if needed browser.
        """
        start = time.time()

        # Try direct HTTP first
        try:
            resp = await self.http.get(url)
            latency = time.time() - start

            if resp.status_code == 200:
                content = resp.text

                # Check if it's actually content or JS shell
                if len(content) > 1000 and content.count("<") > 20:
                    # Check for JS-only indicators
                    js_shell_indicators = [
                        '<div id="root"></div>',
                        '<div id="app"></div>',
                        "window.__INITIAL_STATE__",
                        "__NEXT_DATA__"
                    ]
                    if not any(ind in content for ind in js_shell_indicators):
                        return content, "direct", latency

            # Fall through to Firecrawl
        except Exception:
            pass

        # Try Firecrawl
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_key:
            try:
                fc_resp = await self.http.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {firecrawl_key}"},
                    json={"url": url, "formats": ["html"]},
                    timeout=30.0
                )
                latency = time.time() - start

                if fc_resp.status_code == 200:
                    data = fc_resp.json()
                    html = data.get("data", {}).get("html", "")
                    if html:
                        return html, "firecrawl", latency
            except Exception:
                pass

        # Try Bright Data (for blocked/captcha sites)
        bright_api_key = os.getenv("BRIGHTDATA_API_KEY") or os.getenv("BRIGHT_DATA_API_KEY")
        if bright_api_key:
            try:
                bright_resp = await self.http.post(
                    "https://api.brightdata.com/request",
                    headers={
                        "Authorization": f"Bearer {bright_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "zone": "web_unlocker",
                        "url": url,
                        "format": "raw"
                    },
                    timeout=45.0
                )
                latency = time.time() - start

                if bright_resp.status_code == 200:
                    html = bright_resp.text
                    if html and len(html) > 500:
                        return html, "brightdata", latency
            except Exception as e:
                logger.debug(f"Bright Data failed: {e}")

        return "", "failed", time.time() - start

    async def analyze_page(self, html: str, url: str, query: str) -> Optional[Dict]:
        """Use AI to extract output schema from page."""
        if not html or len(html) < 500:
            return None

        # Truncate for AI
        html_truncated = html[:15000]

        prompt = self.OUTPUT_SCHEMA_PROMPT.format(
            url=url,
            query=query,
            html=html_truncated
        )

        try:
            response = await self.model_pool.call(prompt)

            # Parse JSON from response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            schema = json.loads(response)
            return schema
        except Exception as e:
            logger.debug(f"AI analysis failed: {e}")
            return None

    async def experiment_source(self, source: Dict, jurisdiction: str) -> Wave2Result:
        """Run experiment on a single source with multiple query attempts."""
        domain = source.get("domain", "")
        source_id = source.get("id", domain)
        template = source.get("search_template", "")

        result = Wave2Result(
            source_id=source_id,
            jurisdiction=jurisdiction,
            domain=domain,
            status="no_results",
            queries_tried=[]
        )

        if not template or "{q}" not in template:
            result.status = "failed"
            result.notes = "No search template"
            return result

        queries = self.get_test_queries(jurisdiction)

        async with self.semaphore:
            latencies = []

            for query in queries:
                url = template.replace("{q}", quote_plus(query))
                result.queries_tried.append(query)

                # Scrape
                html, method, latency = await self.scrape_url(url)
                latencies.append(latency)
                result.scrape_method = method

                if not html:
                    continue

                # Check for blocked indicators
                html_lower = html.lower()
                blocked_indicators = ["captcha", "recaptcha", "cloudflare", "access denied", "403"]
                if any(ind in html_lower for ind in blocked_indicators):
                    result.status = "blocked"
                    result.notes = "Captcha/block detected"
                    continue

                # Analyze with AI
                schema = await self.analyze_page(html, url, query)

                if schema and schema.get("has_results"):
                    result.status = "success"
                    result.successful_query = query
                    result.output_schema = schema
                    result.avg_latency = sum(latencies) / len(latencies)
                    break

            if not latencies:
                result.status = "failed"
            elif result.status == "no_results":
                result.avg_latency = sum(latencies) / len(latencies)

        return result

    def load_checkpoint(self) -> Set[str]:
        """Load completed source IDs from checkpoint."""
        if CHECKPOINT_PATH.exists():
            with open(CHECKPOINT_PATH) as f:
                data = json.load(f)
                return set(data.get("completed", []))
        return set()

    def save_checkpoint(self):
        """Save progress checkpoint."""
        with open(CHECKPOINT_PATH, "w") as f:
            json.dump({
                "completed": list(self.results.keys()),
                "stats": self.stats,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

    def save_results(self):
        """Save experiment results."""
        output = {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "results": {
                k: {
                    "source_id": v.source_id,
                    "jurisdiction": v.jurisdiction,
                    "domain": v.domain,
                    "status": v.status,
                    "queries_tried": v.queries_tried,
                    "successful_query": v.successful_query,
                    "output_schema": v.output_schema,
                    "scrape_method": v.scrape_method,
                    "avg_latency": v.avg_latency,
                    "tested_at": v.tested_at,
                    "notes": v.notes
                }
                for k, v in self.results.items()
            }
        }

        with open(RESULTS_PATH, "w") as f:
            json.dump(output, f, indent=2)

    async def run(self, sources_data: Dict, target_sources: Optional[Set[str]] = None):
        """Run Wave 2 experiments."""
        await self.setup()

        # Load checkpoint
        completed = self.load_checkpoint()
        if completed:
            logger.info(f"Resuming: {len(completed)} already completed")

        # Collect sources to process
        to_process = []
        for jur, entries in sources_data.items():
            for source in entries:
                source_id = source.get("id", source.get("domain"))

                # Skip if already done
                if source_id in completed:
                    continue

                # If targeting specific sources, filter
                if target_sources and source_id not in target_sources:
                    continue

                # Skip if no template
                if not source.get("search_template"):
                    continue

                to_process.append((source, jur))

        logger.info(f"Processing {len(to_process)} sources")

        # Process in batches
        batch_size = 50
        for i in range(0, len(to_process), batch_size):
            batch = to_process[i:i + batch_size]

            tasks = [
                self.experiment_source(source, jur)
                for source, jur in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Experiment failed: {result}")
                    continue

                self.results[result.source_id] = result
                self.stats[result.status] = self.stats.get(result.status, 0) + 1
                self.stats["total"] += 1

            # Progress
            done = min(i + batch_size, len(to_process))
            logger.info(f"Progress: {done}/{len(to_process)} ({100*done/len(to_process):.1f}%)")
            logger.info(f"  Success: {self.stats['success']}, No results: {self.stats['no_results']}, Blocked: {self.stats['blocked']}")

            # Save checkpoint
            if done % 100 == 0:
                self.save_checkpoint()
                self.save_results()

        await self.close()

        # Final save
        self.save_checkpoint()
        self.save_results()

        return self.results


async def main():
    parser = argparse.ArgumentParser(description="Wave 2 Experiments with Real Company Names")
    parser.add_argument("--concurrent", type=int, default=15, help="Concurrent requests")
    parser.add_argument("--max-tries", type=int, default=3, help="Queries per source")
    parser.add_argument("--all", action="store_true", help="Run on ALL sources (not just no_results)")
    parser.add_argument("--jurisdiction", "-j", type=str, help="Limit to specific jurisdiction")
    args = parser.parse_args()

    # Load sources
    logger.info(f"Loading sources from {SOURCES_V3_PATH}")
    with open(SOURCES_V3_PATH) as f:
        sources_data = json.load(f)

    # If not --all, target only sources that failed in Wave 1
    target_sources = None
    if not args.all:
        # Load Wave 1 results to find failed sources
        wave1_path = PROJECT_ROOT / "input_output2" / "matrix" / "experiments.json"
        if wave1_path.exists():
            with open(wave1_path) as f:
                wave1 = json.load(f)

            # Find sources that had success=false
            target_sources = set()
            for jur, entries in wave1.items():
                for entry in entries:
                    if not entry.get("success", False):
                        source_id = entry.get("id", entry.get("domain"))
                        target_sources.add(source_id)

            logger.info(f"Targeting {len(target_sources)} sources from Wave 1 (failed/no_results)")
        else:
            logger.info("No Wave 1 results found, running on all sources")

    # Filter by jurisdiction if specified
    if args.jurisdiction:
        filtered = {args.jurisdiction: sources_data.get(args.jurisdiction, [])}
        sources_data = filtered
        logger.info(f"Filtered to jurisdiction: {args.jurisdiction}")

    # Count sources
    total = sum(len(entries) for entries in sources_data.values())
    with_templates = sum(
        1 for entries in sources_data.values()
        for e in entries if e.get("search_template")
    )
    logger.info(f"Total sources: {total}")
    logger.info(f"With templates: {with_templates}")

    print("\n" + "=" * 60)
    logger.info("WAVE 2 EXPERIMENT RUN")
    logger.info("=" * 60)
    logger.info(f"Concurrent: {args.concurrent}")
    logger.info(f"Max tries per source: {args.max_tries}")
    logger.info(f"Target: {'ALL sources' if args.all else 'no_results/failed only'}")
    logger.info("=" * 60 + "\n")

    # Run
    experimenter = Wave2Experimenter(
        concurrent=args.concurrent,
        max_tries=args.max_tries
    )

    results = await experimenter.run(sources_data, target_sources)

    # Summary
    print("\n" + "=" * 60)
    print("WAVE 2 SUMMARY")
    print("=" * 60)
    print(f"Total processed: {experimenter.stats['total']}")
    print(f"")
    print(f"Success (with schema):  {experimenter.stats['success']:,}")
    print(f"No results:             {experimenter.stats['no_results']:,}")
    print(f"Blocked:                {experimenter.stats['blocked']:,}")
    print(f"Failed:                 {experimenter.stats['failed']:,}")

    if experimenter.stats['total'] > 0:
        success_rate = experimenter.stats['success'] / experimenter.stats['total'] * 100
        print(f"\nSuccess rate: {success_rate:.1f}%")

    print(f"\nResults saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
