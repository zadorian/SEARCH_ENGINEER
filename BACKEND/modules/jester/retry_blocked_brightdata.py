#!/usr/bin/env python3
"""
Retry Blocked Sources with Bright Data

Uses Bright Data Web Unlocker to retry sources that were blocked by captcha/403.
This runs AFTER Wave 2 completes to recover blocked sources.

Usage:
    python retry_blocked_brightdata.py                    # Retry all blocked
    python retry_blocked_brightdata.py --concurrent 10   # Adjust parallelism
    python retry_blocked_brightdata.py --limit 100       # Limit sources
"""

import asyncio
import json
import logging
import argparse
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
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
logger = logging.getLogger("BrightDataRetry")

# Paths
SOURCES_V3_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"
WAVE2_RESULTS_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "wave2_experiments.json"
TEST_QUERIES_PATH = Path(__file__).parent / "test_queries_v2.json"
BRIGHTDATA_RESULTS_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "brightdata_retry.json"

# Fallback queries
FALLBACK_QUERIES = {
    "HU": ["OTP Bank", "Richter Gedeon", "Wizz Air"],
    "DE": ["Deutsche Bank", "Siemens", "Volkswagen"],
    "US": ["Apple", "Microsoft", "Amazon"],
    "GB": ["HSBC", "BP", "Barclays"],
    "GLOBAL": ["Bank", "Holdings", "International"],
}


class BrightDataRetry:
    """Retry blocked sources using Bright Data Web Unlocker."""

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
    {{"name": "registration_number", "css_selector": "td.reg-num", "example": "12345678"}}
  ],
  "pagination": true/false,
  "notes": "Any relevant observations"
}}

Return ONLY valid JSON, no markdown."""

    def __init__(self, concurrent: int = 5):
        self.concurrent = concurrent
        self.semaphore = asyncio.Semaphore(concurrent)
        self.http = None
        self.model_pool = None
        self.test_queries = {}
        self.bright_api_key = os.getenv("BRIGHTDATA_API_KEY")
        self.results = {}
        self.stats = {
            "success": 0,
            "no_results": 0,
            "still_blocked": 0,
            "failed": 0,
            "total": 0
        }

    async def setup(self):
        """Initialize HTTP client and model pool."""
        self.http = httpx.AsyncClient(timeout=90.0)

        # Load test queries
        if TEST_QUERIES_PATH.exists():
            with open(TEST_QUERIES_PATH) as f:
                data = json.load(f)
                self.test_queries = data.get("queries", {})
        else:
            self.test_queries = FALLBACK_QUERIES

        # Setup model pool for AI analysis
        self._setup_model_pool()

    def _setup_model_pool(self):
        """Setup AI providers."""
        self.providers = []

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.providers.append({
                    "name": "anthropic",
                    "client": anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")),
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
                })
                logger.info("OpenAI provider added")
            except Exception as e:
                logger.warning(f"OpenAI setup failed: {e}")

    async def call_ai(self, prompt: str) -> str:
        """Call AI for analysis."""
        if not self.providers:
            return ""

        provider = self.providers[0]

        try:
            if provider["name"] == "anthropic":
                response = provider["client"].messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            elif provider["name"] == "openai":
                response = provider["client"].chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4000
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"AI call failed: {e}")

        return ""

    async def close(self):
        if self.http:
            await self.http.aclose()

    def get_test_queries(self, jurisdiction: str) -> list:
        """Get multiple test queries for jurisdiction - try all before giving up."""
        queries = self.test_queries.get(jurisdiction, [])
        if not queries:
            queries = self.test_queries.get("GLOBAL", FALLBACK_QUERIES["GLOBAL"])

        result = []
        # Add first 2 company names (cleaned)
        for q in queries[:2]:
            cleaned = self._clean_company_query(q)
            if cleaned and cleaned not in result:
                result.append(cleaned)

        # Add generic word in local language
        generic_by_lang = {
            "DE": "Firma", "AT": "Firma", "CH": "Firma",
            "ES": "empresa", "AR": "empresa", "MX": "empresa", "CO": "empresa",
            "FR": "société", "BE": "société",
            "IT": "azienda",
            "PT": "empresa", "BR": "empresa",
            "NL": "bedrijf",
            "PL": "firma",
            "CZ": "firma", "SK": "firma",
            "HU": "cég",
            "RO": "firma",
            "RU": "компания",
            "JP": "会社",
            "CN": "公司",
            "KR": "회사",
            "GLOBAL": "company",
        }
        generic = generic_by_lang.get(jurisdiction, "company")
        if generic not in result:
            result.append(generic)

        return result if result else ["company"]

    def get_test_query(self, jurisdiction: str) -> str:
        """Get first test query (for backwards compat)."""
        return self.get_test_queries(jurisdiction)[0]

    def _clean_company_query(self, query: str) -> str:
        """Clean company name: remove designations, use first word only."""
        # Remove common company designations
        designations = [
            " S.A.", " SA", " S.A", " GmbH", " Ltd", " Ltd.", " LLC", " Inc",
            " Inc.", " Corp", " Corp.", " PLC", " Plc", " AG", " SE", " NV",
            " BV", " Pty", " Kft", " Kft.", " SRL", " S.R.L.", " SpA", " S.p.A.",
            " Co.", " Co", " & Co", " A/S", " AS", " AB", " Oy", " SARL",
            " d.o.o.", " d.o.o", " A.D.", " JSC", " PJSC", " OOO", " ZAO",
        ]
        cleaned = query
        for d in designations:
            cleaned = cleaned.replace(d, "").replace(d.upper(), "").replace(d.lower(), "")

        # Use first word only (for multi-word names)
        words = cleaned.strip().split()
        if words:
            return words[0]
        return query

    async def scrape_with_brightdata(self, url: str) -> tuple[str, float]:
        """Scrape URL using Bright Data Web Unlocker."""
        if not self.bright_api_key:
            return "", 0.0

        start = time.time()

        try:
            resp = await self.http.post(
                "https://api.brightdata.com/request",
                headers={
                    "Authorization": f"Bearer {self.bright_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "zone": "mcp_unlocker",
                    "url": url,
                    "format": "raw"
                },
                timeout=60.0
            )
            latency = time.time() - start

            if resp.status_code == 200:
                html = resp.text
                if html and len(html) > 500:
                    return html, latency

            logger.debug(f"Bright Data returned {resp.status_code} for {url[:50]}")

        except Exception as e:
            logger.debug(f"Bright Data error: {e}")

        return "", time.time() - start

    async def analyze_page(self, html: str, url: str, query: str) -> Optional[Dict]:
        """Use AI to extract output schema."""
        if not html or len(html) < 500:
            return None

        # Check for blocked indicators - but be SMART about it
        # Large pages (50KB+) are almost never block pages
        html_lower = html.lower()

        # Only check small pages for block indicators (block pages are typically < 50KB)
        if len(html) < 50000:
            # Actual block page signatures (not just word presence)
            block_signatures = [
                "please verify you are human",
                "checking your browser",
                "just a moment...",
                "enable javascript and cookies",
                "ray id:",  # Cloudflare specific
                "attention required",
                "access denied</title>",
                "403 forbidden</title>",
                "blocked</title>",
            ]
            if any(sig in html_lower for sig in block_signatures):
                return {"has_results": False, "blocked": True}

        # Truncate for AI
        html_truncated = html[:15000]

        prompt = self.OUTPUT_SCHEMA_PROMPT.format(
            url=url,
            query=query,
            html=html_truncated
        )

        try:
            response = await self.call_ai(prompt)
            if not response:
                return None

            # Parse JSON
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            return json.loads(response)
        except Exception as e:
            logger.debug(f"AI analysis failed: {e}")
            return None

    async def retry_source(self, source_id: str, source_data: Dict) -> Dict:
        """Retry a single blocked source with multiple queries."""
        domain = source_data.get("domain", "")
        jurisdiction = source_data.get("jurisdiction", "GLOBAL")
        template = source_data.get("search_template", "")

        result = {
            "source_id": source_id,
            "domain": domain,
            "jurisdiction": jurisdiction,
            "status": "failed",
            "scrape_method": "brightdata",
            "output_schema": None,
            "latency": 0.0,
            "queries_tried": [],
            "successful_query": None,
            "tested_at": datetime.now().isoformat()
        }

        if not template or "{q}" not in template:
            result["notes"] = "No template"
            return result

        # Get multiple queries to try
        queries = self.get_test_queries(jurisdiction)
        total_latency = 0.0

        async with self.semaphore:
            for query in queries:
                result["queries_tried"].append(query)
                url = template.replace("{q}", quote_plus(query))

                # Scrape with Bright Data
                html, latency = await self.scrape_with_brightdata(url)
                total_latency += latency

                if not html:
                    continue  # Try next query

                # Analyze
                schema = await self.analyze_page(html, url, query)

                if schema:
                    if schema.get("blocked"):
                        result["status"] = "still_blocked"
                        break  # Site is blocked, no point trying more
                    elif schema.get("has_results"):
                        result["status"] = "success"
                        result["output_schema"] = schema
                        result["successful_query"] = query
                        break  # Success! Stop trying
                    # else: no results, try next query

            # If we tried all queries and none worked
            if result["status"] == "failed" and result["queries_tried"]:
                result["status"] = "no_results"

            result["latency"] = total_latency

        return result

    async def run(self, blocked_sources: List[Dict], limit: int = None):
        """Run retry on blocked sources."""
        await self.setup()

        if not self.bright_api_key:
            logger.error("BRIGHTDATA_API_KEY not found in environment!")
            return {}

        sources_to_process = blocked_sources[:limit] if limit else blocked_sources
        logger.info(f"Retrying {len(sources_to_process)} blocked sources with Bright Data")

        # Process in batches
        batch_size = 20
        for i in range(0, len(sources_to_process), batch_size):
            batch = sources_to_process[i:i + batch_size]

            tasks = [
                self.retry_source(s["source_id"], s)
                for s in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Retry failed: {result}")
                    continue

                self.results[result["source_id"]] = result
                self.stats[result["status"]] = self.stats.get(result["status"], 0) + 1
                self.stats["total"] += 1

            # Progress
            done = min(i + batch_size, len(sources_to_process))
            logger.info(f"Progress: {done}/{len(sources_to_process)} ({100*done/len(sources_to_process):.1f}%)")
            logger.info(f"  Success: {self.stats['success']}, Still blocked: {self.stats['still_blocked']}, No results: {self.stats['no_results']}")

            # Save periodically
            if done % 50 == 0:
                self.save_results()

        await self.close()
        self.save_results()

        return self.results

    def save_results(self):
        """Save results to file."""
        output = {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "results": self.results
        }

        with open(BRIGHTDATA_RESULTS_PATH, "w") as f:
            json.dump(output, f, indent=2)


async def main():
    parser = argparse.ArgumentParser(description="Retry blocked sources with Bright Data")
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--limit", type=int, help="Limit number of sources")
    args = parser.parse_args()

    # Load blocked sources from Wave 2 results
    if not WAVE2_RESULTS_PATH.exists():
        logger.error(f"Wave 2 results not found: {WAVE2_RESULTS_PATH}")
        return

    with open(WAVE2_RESULTS_PATH) as f:
        wave2_data = json.load(f)

    # Load sources_v3 for templates
    with open(SOURCES_V3_PATH) as f:
        sources_v3 = json.load(f)

    # Build source lookup
    source_lookup = {}
    for jur, entries in sources_v3.items():
        for s in entries:
            sid = s.get("id", s.get("domain"))
            source_lookup[sid] = {**s, "jurisdiction": jur}

    # Find blocked sources
    blocked = []
    for sid, result in wave2_data.get("results", {}).items():
        if result.get("status") == "blocked":
            if sid in source_lookup:
                blocked.append({
                    "source_id": sid,
                    **source_lookup[sid]
                })

    logger.info(f"Found {len(blocked)} blocked sources")

    if not blocked:
        logger.info("No blocked sources to retry!")
        return

    print("\n" + "=" * 60)
    logger.info("BRIGHT DATA RETRY RUN")
    logger.info("=" * 60)
    logger.info(f"Concurrent: {args.concurrent}")
    logger.info(f"Blocked sources: {len(blocked)}")
    logger.info("=" * 60 + "\n")

    # Run
    retrier = BrightDataRetry(concurrent=args.concurrent)
    results = await retrier.run(blocked, args.limit)

    # Summary
    print("\n" + "=" * 60)
    print("BRIGHT DATA RETRY SUMMARY")
    print("=" * 60)
    print(f"Total processed: {retrier.stats['total']}")
    print(f"")
    print(f"Success (unblocked):    {retrier.stats['success']:,}")
    print(f"Still blocked:          {retrier.stats['still_blocked']:,}")
    print(f"No results:             {retrier.stats['no_results']:,}")
    print(f"Failed:                 {retrier.stats['failed']:,}")

    if retrier.stats['total'] > 0:
        success_rate = retrier.stats['success'] / retrier.stats['total'] * 100
        print(f"\nRecovery rate: {success_rate:.1f}%")

    print(f"\nResults saved to: {BRIGHTDATA_RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
