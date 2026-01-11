#!/usr/bin/env python3
"""
SeekLeech Engine v2.0 - Full Experimentation Runner

Runs experiments on ALL sources with templates to learn:
1. Output structure (table, list, cards, JSON API)
2. Field mapping (what data is returned)
3. CSS selectors for extraction
4. Reliability metrics (success rate, latency)

This creates the intelligence needed to know EXACTLY what we can
retrieve from each source and how to display it.

Usage:
    python run_experiments.py                    # Run on all sources
    python run_experiments.py --jurisdiction HU  # Single jurisdiction
    python run_experiments.py --limit 100        # Test run
    python run_experiments.py --concurrent 20    # Adjust parallelism
    python run_experiments.py --resume           # Resume from checkpoint
"""

import asyncio
import json
import logging
import argparse
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from dataclasses import asdict
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

from schemas import EnhancedSource, OutputSchema, OutputField, InputSchema, ReliabilityMetrics
from taxonomy import detect_thematic_tags, THEMATIC_TAXONOMY

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SeekLeech.Experiments")

# Paths
SOURCES_V2_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v2.json"
SOURCES_V3_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"
EXPERIMENTS_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "experiments.json"
CHECKPOINT_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "experiment_checkpoint.json"


# ─────────────────────────────────────────────────────────────
# Model Pool - Rotate across providers for rate limit avoidance
# ─────────────────────────────────────────────────────────────

class ModelPool:
    """Rotate AI calls across multiple providers."""

    def __init__(self):
        self.providers = []
        self._setup_providers()
        self.call_count = 0

    def _setup_providers(self):
        """Initialize available providers."""
        import google.generativeai as genai
        import anthropic
        from openai import AsyncOpenAI

        # Gemini
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            genai.configure(api_key=gemini_key)
            self.providers.append({
                "name": "gemini",
                "model": genai.GenerativeModel("gemini-2.0-flash-exp"),
                "type": "gemini"
            })
            logger.info("Gemini provider added")

        # Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self.providers.append({
                "name": "anthropic",
                "client": anthropic.AsyncAnthropic(api_key=anthropic_key),
                "model": "claude-sonnet-4-5-20250929",
                "type": "anthropic"
            })
            logger.info("Anthropic provider added")

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.providers.append({
                "name": "openai",
                "client": AsyncOpenAI(api_key=openai_key),
                "model": "gpt-4o-mini",
                "type": "openai"
            })
            logger.info("OpenAI provider added")

        if not self.providers:
            raise RuntimeError("No AI providers configured! Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY")

        logger.info(f"Model pool initialized with {len(self.providers)} providers")

    async def call(self, prompt: str, max_tokens: int = 4000) -> str:
        """Make AI call with provider rotation."""
        if not self.providers:
            raise RuntimeError("No providers available")

        # Round-robin selection
        provider = self.providers[self.call_count % len(self.providers)]
        self.call_count += 1

        try:
            if provider["type"] == "gemini":
                response = await asyncio.to_thread(
                    provider["model"].generate_content,
                    prompt,
                    generation_config={"max_output_tokens": max_tokens}
                )
                return response.text

            elif provider["type"] == "anthropic":
                response = await provider["client"].messages.create(
                    model=provider["model"],
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text

            elif provider["type"] == "openai":
                response = await provider["client"].chat.completions.create(
                    model=provider["model"],
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content

        except Exception as e:
            logger.warning(f"Provider {provider['name']} failed: {e}")
            # Try next provider
            if len(self.providers) > 1:
                next_provider = self.providers[(self.call_count) % len(self.providers)]
                return await self._call_provider(next_provider, prompt, max_tokens)
            raise

    async def _call_provider(self, provider: dict, prompt: str, max_tokens: int) -> str:
        """Call specific provider."""
        if provider["type"] == "gemini":
            response = await asyncio.to_thread(
                provider["model"].generate_content,
                prompt,
                generation_config={"max_output_tokens": max_tokens}
            )
            return response.text
        elif provider["type"] == "anthropic":
            response = await provider["client"].messages.create(
                model=provider["model"],
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        elif provider["type"] == "openai":
            response = await provider["client"].chat.completions.create(
                model=provider["model"],
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content


# ─────────────────────────────────────────────────────────────
# Output Schema Analysis Prompt
# ─────────────────────────────────────────────────────────────

OUTPUT_ANALYSIS_PROMPT = """You are analyzing a search results page from a public records registry/database.
Your task is to identify the OUTPUT STRUCTURE so we know exactly what data we can extract.

Domain: {domain}
Jurisdiction: {jurisdiction}
Query used: "{query}"

Analyze the HTML and identify:

1. RESULT TYPE: Is it a table, list of items, cards, single record detail, or JSON API response?

2. RESULTS CONTAINER: What CSS selector contains all results?
   - Look for: table, ul/ol, div.results, etc.

3. ROW/ITEM SELECTOR: What CSS selector identifies each individual result?
   - For tables: tr, tbody tr
   - For lists: li, .result-item, .card

4. FIELDS: For each piece of data shown per result, identify:
   - Field name (standardized): company_name, registration_number, status, incorporation_date,
     registered_address, officers, shareholders, capital, company_type, jurisdiction_code
   - CSS selector to extract it (relative to row)
   - Example value from the page
   - Data type: string, number, date, boolean, list
   - Is it always present?

5. PAGINATION: Does it paginate? How many results per page?

6. LANGUAGE: What language is the content?

HTML Content (truncated):
```html
{html_snippet}
```

Return ONLY valid JSON (no markdown, no explanation):
{{
    "result_type": "table|list|cards|single_record|json_api|no_results|error_page",
    "pagination": true|false,
    "max_results_per_page": 10,
    "results_container": ".results-table" or null,
    "row_selector": "tr.result-row" or "tbody tr" or null,
    "fields": [
        {{
            "name": "company_name",
            "css_selector": "td:nth-child(1)",
            "json_path": null,
            "example_value": "Acme Corp Ltd",
            "data_type": "string",
            "always_present": true
        }},
        {{
            "name": "registration_number",
            "css_selector": "td:nth-child(2)",
            "json_path": null,
            "example_value": "12345678",
            "data_type": "string",
            "always_present": true
        }}
    ],
    "language": "en",
    "notes": "Any important observations about extracting from this source"
}}

If no results are found or page is an error, still return valid JSON with result_type="no_results" or "error_page".
"""


# ─────────────────────────────────────────────────────────────
# Test Queries by Jurisdiction
# ─────────────────────────────────────────────────────────────

TEST_QUERIES = {
    # Common names that should return results in most registries
    "GLOBAL": ["bank", "holdings", "energy", "trading", "limited"],
    "US": ["bank", "corp", "llc", "inc", "holdings"],
    "GB": ["limited", "plc", "bank", "trading", "services"],
    "DE": ["gmbh", "ag", "bank", "holding", "gruppe"],
    "FR": ["sa", "sas", "banque", "groupe", "services"],
    "HU": ["kft", "zrt", "bank", "holding", "csoport"],
    "NL": ["bv", "nv", "holding", "bank", "groep"],
    "ES": ["sl", "sa", "banco", "grupo", "servicios"],
    "IT": ["srl", "spa", "banca", "gruppo", "servizi"],
    "AT": ["gmbh", "ag", "bank", "holding", "gruppe"],
    "CH": ["ag", "sa", "gmbh", "bank", "holding"],
    "PL": ["sp", "sa", "bank", "holding", "grupa"],
    "CZ": ["sro", "as", "banka", "holding", "skupina"],
    "RO": ["srl", "sa", "banca", "holding", "grup"],
    "BG": ["eood", "ad", "bank", "holding", "grupa"],
    "RU": ["ooo", "oao", "bank", "holding", "gruppa"],
    "UA": ["tov", "at", "bank", "holding", "grupa"],
    "CN": ["有限", "银行", "集团", "控股", "贸易"],
    "JP": ["株式会社", "銀行", "ホールディングス", "グループ"],
    "KR": ["주식회사", "은행", "홀딩스", "그룹"],
    "IN": ["limited", "bank", "holdings", "pvt", "services"],
    "AU": ["pty", "limited", "bank", "holdings", "group"],
    "NZ": ["limited", "bank", "holdings", "group", "services"],
    "SG": ["pte", "limited", "bank", "holdings", "group"],
    "HK": ["limited", "bank", "holdings", "group", "trading"],
    "AE": ["llc", "bank", "holding", "group", "trading"],
    "SA": ["llc", "bank", "holding", "group", "trading"],
    "BR": ["ltda", "sa", "banco", "holding", "grupo"],
    "MX": ["sa", "cv", "banco", "grupo", "servicios"],
    "AR": ["sa", "srl", "banco", "grupo", "servicios"],
    "CL": ["sa", "ltda", "banco", "grupo", "servicios"],
    "ZA": ["pty", "limited", "bank", "holdings", "group"],
    "NG": ["limited", "plc", "bank", "holdings", "group"],
    "KE": ["limited", "bank", "holdings", "group", "services"],
    "EG": ["llc", "bank", "holding", "group", "services"],
    "IL": ["ltd", "bank", "holdings", "group", "services"],
}


def get_test_query(jurisdiction: str) -> str:
    """Get a test query for a jurisdiction."""
    queries = TEST_QUERIES.get(jurisdiction, TEST_QUERIES["GLOBAL"])
    return queries[0]  # Use first query - most likely to return results


# ─────────────────────────────────────────────────────────────
# Scraper
# ─────────────────────────────────────────────────────────────

import httpx
from urllib.parse import quote_plus

class Scraper:
    """HTTP scraper with Firecrawl fallback."""

    def __init__(self):
        self.http = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        self.firecrawl_url = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")

    async def close(self):
        await self.http.aclose()

    async def scrape(self, url: str) -> tuple[Optional[str], float, str]:
        """
        Scrape URL.
        Returns: (html, latency, method)
        """
        start = time.time()

        # Try direct first
        try:
            resp = await self.http.get(url)
            if resp.status_code == 200 and len(resp.text) > 500:
                return resp.text, time.time() - start, "direct"
        except Exception as e:
            logger.debug(f"Direct scrape failed: {e}")

        # Firecrawl fallback
        if self.firecrawl_key:
            try:
                resp = await self.http.post(
                    f"{self.firecrawl_url}/scrape",
                    headers={
                        "Authorization": f"Bearer {self.firecrawl_key}",
                        "Content-Type": "application/json"
                    },
                    json={"url": url, "formats": ["html"]},
                    timeout=45
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("data", {}).get("html"):
                        return data["data"]["html"], time.time() - start, "firecrawl"
            except Exception as e:
                logger.debug(f"Firecrawl failed: {e}")

        return None, time.time() - start, "failed"


# ─────────────────────────────────────────────────────────────
# Experiment Runner
# ─────────────────────────────────────────────────────────────

class ExperimentRunner:
    """Run experiments on sources to learn their output structure."""

    def __init__(self, concurrent: int = 10):
        self.scraper = Scraper()
        self.model_pool = ModelPool()
        self.concurrent = concurrent
        self.semaphore = asyncio.Semaphore(concurrent)

        # Stats
        self.total_processed = 0
        self.total_success = 0
        self.total_failed = 0
        self.total_no_results = 0

    async def close(self):
        await self.scraper.close()

    def _truncate_html(self, html: str, max_chars: int = 12000) -> str:
        """Extract relevant snippet for AI analysis."""
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove scripts, styles, nav, footer
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
                tag.decompose()

            # Try to find main content
            main = (
                soup.find('main') or
                soup.find(class_=lambda x: x and ('result' in x.lower() or 'content' in x.lower())) or
                soup.find('table') or
                soup.body
            )

            if main:
                content = str(main)
            else:
                content = str(soup)

            # Truncate
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... [TRUNCATED]"

            return content

        except Exception:
            return html[:max_chars] if len(html) > max_chars else html

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from AI response."""
        # Remove markdown code blocks
        text = text.replace('```json', '').replace('```', '').strip()

        # Find JSON object
        start = text.find('{')
        end = text.rfind('}') + 1

        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None

    async def experiment_source(self, source: Dict, jurisdiction: str) -> Dict:
        """Run experiment on a single source."""
        async with self.semaphore:
            result = {
                "id": source.get("id", source.get("domain")),
                "domain": source.get("domain"),
                "jurisdiction": jurisdiction,
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "output_schema": None,
                "reliability": {
                    "success_rate": 0.0,
                    "avg_latency": 0.0,
                    "test_count": 1
                },
                "notes": ""
            }

            template = source.get("search_template")
            if not template or "{q}" not in template:
                result["notes"] = "No valid search template"
                return result

            # Get test query
            query = get_test_query(jurisdiction)
            url = template.replace("{q}", quote_plus(query))

            # Scrape
            html, latency, method = await self.scraper.scrape(url)

            result["reliability"]["avg_latency"] = latency
            result["scrape_method"] = method  # "direct" = easy HTML (Go-scrapeable), "firecrawl" = needs browser

            if not html:
                result["notes"] = f"Scrape failed ({method})"
                self.total_failed += 1
                return result

            result["reliability"]["success_rate"] = 1.0

            # Truncate HTML for AI
            html_snippet = self._truncate_html(html)

            # AI analysis
            try:
                prompt = OUTPUT_ANALYSIS_PROMPT.format(
                    domain=source.get("domain"),
                    jurisdiction=jurisdiction,
                    query=query,
                    html_snippet=html_snippet
                )

                ai_response = await self.model_pool.call(prompt)
                schema_data = self._parse_json(ai_response)

                if schema_data:
                    result_type = schema_data.get("result_type", "unknown")

                    if result_type in ["no_results", "error_page"]:
                        result["notes"] = f"Page returned {result_type}"
                        self.total_no_results += 1
                    else:
                        # Build output schema
                        fields = []
                        for f in schema_data.get("fields", []):
                            fields.append({
                                "name": f.get("name", ""),
                                "css_selector": f.get("css_selector"),
                                "json_path": f.get("json_path"),
                                "example_value": f.get("example_value", ""),
                                "data_type": f.get("data_type", "string"),
                                "always_present": f.get("always_present", False)
                            })

                        result["output_schema"] = {
                            "result_type": result_type,
                            "pagination": schema_data.get("pagination", False),
                            "max_results_per_page": schema_data.get("max_results_per_page", 25),
                            "results_container": schema_data.get("results_container"),
                            "row_selector": schema_data.get("row_selector"),
                            "fields": fields,
                            "language": schema_data.get("language", "en")
                        }

                        result["success"] = True
                        result["notes"] = schema_data.get("notes", "")
                        self.total_success += 1

                else:
                    result["notes"] = "AI failed to return valid JSON"
                    self.total_failed += 1

            except Exception as e:
                result["notes"] = f"AI analysis failed: {str(e)}"
                self.total_failed += 1

            self.total_processed += 1
            return result

    async def run_batch(
        self,
        sources_by_jur: Dict[str, List[Dict]],
        output_path: Path,
        checkpoint_path: Path,
        limit: Optional[int] = None,
        jurisdiction_filter: Optional[str] = None,
        resume: bool = True
    ) -> Dict[str, List[Dict]]:
        """Run experiments on all sources."""

        # Load checkpoint
        done_ids: Set[str] = set()
        results: Dict[str, List[Dict]] = {}

        if resume and checkpoint_path.exists():
            try:
                with open(checkpoint_path) as f:
                    checkpoint = json.load(f)
                    done_ids = set(checkpoint.get("done_ids", []))
                    results = checkpoint.get("results", {})
                logger.info(f"Resuming from checkpoint: {len(done_ids)} already done")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")

        # Collect sources to process
        to_process = []
        for jur, entries in sources_by_jur.items():
            if jurisdiction_filter and jur != jurisdiction_filter:
                continue

            for source in entries:
                if not source.get("search_template"):
                    continue

                source_id = source.get("id", source.get("domain"))
                if source_id in done_ids:
                    continue

                to_process.append((source, jur))

        # Apply limit
        if limit:
            to_process = to_process[:limit]

        total = len(to_process)
        logger.info(f"Processing {total} sources ({len(done_ids)} skipped)")

        if total == 0:
            logger.info("Nothing to process!")
            return results

        # Process in batches
        batch_size = 50
        save_interval = 25

        for batch_start in range(0, total, batch_size):
            batch = to_process[batch_start:batch_start + batch_size]

            tasks = [
                self.experiment_source(source, jur)
                for source, jur in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for (source, jur), result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Exception for {source.get('domain')}: {result}")
                    continue

                source_id = result.get("id")
                done_ids.add(source_id)

                if jur not in results:
                    results[jur] = []
                results[jur].append(result)

            # Progress
            processed = batch_start + len(batch)
            logger.info(
                f"Progress: {processed}/{total} | "
                f"Success: {self.total_success} | "
                f"Failed: {self.total_failed} | "
                f"No results: {self.total_no_results}"
            )

            # Save checkpoint
            if processed % save_interval == 0 or processed == total:
                checkpoint = {
                    "done_ids": list(done_ids),
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                    "stats": {
                        "processed": self.total_processed,
                        "success": self.total_success,
                        "failed": self.total_failed,
                        "no_results": self.total_no_results
                    }
                }
                with open(checkpoint_path, 'w') as f:
                    json.dump(checkpoint, f)

                # Also save results
                with open(output_path, 'w') as f:
                    json.dump(results, f, indent=2)

            # Small delay between batches
            await asyncio.sleep(0.5)

        return results


# ─────────────────────────────────────────────────────────────
# Build sources_v3.json
# ─────────────────────────────────────────────────────────────

def merge_experiments_to_v3(
    sources_v2: Dict[str, List[Dict]],
    experiments: Dict[str, List[Dict]],
    output_path: Path
):
    """Merge experiment results into sources_v3.json."""
    logger.info("Merging experiments into sources_v3.json...")

    # API sources - domains that have API keys in .env
    # These should be flagged as access: "api" instead of scraping
    API_SOURCES = {
        # UK
        "company-information.service.gov.uk": "COMPANIES_HOUSE_API_KEY",
        "find-and-update.company-information.service.gov.uk": "COMPANIES_HOUSE_API_KEY",
        "landregistry.gov.uk": "UK_LAND_REGISTRY_API_KEY",
        "search.landregistry.gov.uk": "UK_LAND_REGISTRY_API_KEY",
        "fca.org.uk": "FCA_API_KEY",
        "register.fca.org.uk": "FCA_API_KEY",
        # Global
        "opencorporates.com": "OPENCORPORATES_API_KEY",
        "api.opencorporates.com": "OPENCORPORATES_API_KEY",
        "opensanctions.org": "OPENSANCTIONS_API_KEY",
        "data.occrp.org": "ALEPH_API_KEY",
        "aleph.occrp.org": "ALEPH_API_KEY",
        # Search
        "youtube.com": "YOUTUBE_API_KEY",
        "www.youtube.com": "YOUTUBE_API_KEY",
    }

    # Check which API keys are actually configured
    configured_apis = set()
    for domain, key_name in API_SOURCES.items():
        if os.getenv(key_name):
            configured_apis.add(domain)

    logger.info(f"API sources with keys configured: {len(configured_apis)}")

    # Build experiment lookup
    exp_lookup = {}
    for jur, results in experiments.items():
        for r in results:
            exp_lookup[r.get("id", r.get("domain"))] = r

    # Merge
    sources_v3 = {}
    total_merged = 0
    api_flagged = 0

    for jur, entries in sources_v2.items():
        sources_v3[jur] = []

        for source in entries:
            source_id = source.get("id", source.get("domain"))
            domain = source.get("domain", "")
            exp = exp_lookup.get(source_id)

            enhanced = {
                **source,
                "id": source_id,
                "jurisdiction": jur
            }

            # Flag API sources
            if domain in configured_apis:
                enhanced["access"] = "api"
                enhanced["api_key_env"] = API_SOURCES[domain]
                api_flagged += 1
            elif not enhanced.get("access"):
                enhanced["access"] = "scrape"

            if exp:
                # Add output schema
                if exp.get("output_schema"):
                    enhanced["output_schema"] = exp["output_schema"]
                    total_merged += 1

                # Add reliability
                if exp.get("reliability"):
                    enhanced["reliability"] = exp["reliability"]

                # Add scrape method - critical for knowing if Go binary can handle it
                # "direct" = simple HTTP, Go-scrapeable, fast
                # "firecrawl" = needs browser/JS rendering, slow
                if exp.get("scrape_method"):
                    enhanced["scrape_method"] = exp["scrape_method"]

                # Detect thematic tags if not present
                if not enhanced.get("thematic_tags"):
                    enhanced["thematic_tags"] = detect_thematic_tags(
                        source.get("name", ""),
                        source.get("url", ""),
                        source.get("domain", "")
                    )

            sources_v3[jur].append(enhanced)

    # Save
    with open(output_path, 'w') as f:
        json.dump(sources_v3, f, indent=2)

    logger.info(f"Created sources_v3.json: {total_merged} sources with output schemas, {api_flagged} API sources flagged")
    return sources_v3


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Run SeekLeech experiments on all sources")
    parser.add_argument("--concurrent", type=int, default=15, help="Concurrent requests")
    parser.add_argument("--limit", type=int, help="Limit number of sources (for testing)")
    parser.add_argument("--jurisdiction", "-j", help="Filter to specific jurisdiction")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh, ignore checkpoint")
    parser.add_argument("--merge-only", action="store_true", help="Only merge existing experiments to v3")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without processing")

    args = parser.parse_args()

    # Load sources
    logger.info(f"Loading sources from {SOURCES_V2_PATH}")
    with open(SOURCES_V2_PATH) as f:
        sources_v2 = json.load(f)

    # Count
    total_sources = sum(len(entries) for entries in sources_v2.values())
    with_templates = sum(
        1 for entries in sources_v2.values()
        for e in entries if e.get("search_template")
    )
    logger.info(f"Total sources: {total_sources}")
    logger.info(f"With templates: {with_templates}")
    logger.info(f"Jurisdictions: {len(sources_v2)}")

    if args.dry_run:
        # Show stats by jurisdiction
        logger.info("\nBy jurisdiction:")
        for jur, entries in sorted(sources_v2.items(), key=lambda x: -len(x[1]))[:30]:
            templates = sum(1 for e in entries if e.get("search_template"))
            logger.info(f"  {jur}: {len(entries)} sources, {templates} with templates")
        return

    if args.merge_only:
        # Load existing experiments and merge
        if not EXPERIMENTS_PATH.exists():
            logger.error(f"No experiments file found at {EXPERIMENTS_PATH}")
            return

        with open(EXPERIMENTS_PATH) as f:
            experiments = json.load(f)

        merge_experiments_to_v3(sources_v2, experiments, SOURCES_V3_PATH)
        return

    # Run experiments
    logger.info(f"\n{'='*60}")
    logger.info("SEEKLEECH EXPERIMENT RUN")
    logger.info(f"{'='*60}")
    logger.info(f"Concurrent: {args.concurrent}")
    if args.limit:
        logger.info(f"Limit: {args.limit}")
    if args.jurisdiction:
        logger.info(f"Jurisdiction filter: {args.jurisdiction}")
    logger.info(f"Resume: {not args.no_resume}")
    logger.info(f"{'='*60}\n")

    runner = ExperimentRunner(concurrent=args.concurrent)

    try:
        results = await runner.run_batch(
            sources_v2,
            output_path=EXPERIMENTS_PATH,
            checkpoint_path=CHECKPOINT_PATH,
            limit=args.limit,
            jurisdiction_filter=args.jurisdiction,
            resume=not args.no_resume
        )

        # Final stats
        logger.info(f"\n{'='*60}")
        logger.info("COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Processed: {runner.total_processed}")
        logger.info(f"Success (with schema): {runner.total_success}")
        logger.info(f"Failed: {runner.total_failed}")
        logger.info(f"No results: {runner.total_no_results}")

        # Merge to v3
        logger.info("\nMerging to sources_v3.json...")
        merge_experiments_to_v3(sources_v2, results, SOURCES_V3_PATH)

        logger.info(f"\nExperiments saved to: {EXPERIMENTS_PATH}")
        logger.info(f"Sources v3 saved to: {SOURCES_V3_PATH}")

    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
