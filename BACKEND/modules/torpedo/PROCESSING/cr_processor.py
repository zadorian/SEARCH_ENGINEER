#!/usr/bin/env python3
"""
TORPEDO CR PROCESSOR - Corporate Registry Classification & Field Extraction

Based on eu_registry_audit.py pattern. For each CR source:
1. Test scrape method (jester_bridge cascade)
2. Extract fields from response
3. Translate to IO Matrix codes via FieldTranslator
4. Take screenshot + vision validation (optional)
5. Save to sources/corporate_registries.json with:
   - scrape_method
   - outputs (IO Matrix field codes extracted)
   - input_schema
   - validated

Usage:
    python -m TORPEDO.PROCESSING.cr_processor --jurisdiction HR --concurrent 10
    python -m TORPEDO.PROCESSING.cr_processor --all --validate-vision
"""

import asyncio
import json
import logging
import os
import base64
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).parent
MODULE_DIR = SCRIPT_DIR.parent  # TORPEDO
load_dotenv(PROJECT_ROOT / ".env")

# Import jester_bridge for scraping (relative import from parent TORPEDO module)
from ..jester_bridge import TorpedoScraper, ScrapeMethod, ScrapeResult

# Import FieldTranslator for IO Matrix codes
try:
    translator_path = PROJECT_ROOT / "input_output" / "matrix" / "field_translator.py"
    if translator_path.exists():
        spec = importlib.util.spec_from_file_location("field_translator", translator_path)
        field_translator_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(field_translator_module)
        FieldTranslator = field_translator_module.FieldTranslator
        TRANSLATOR_AVAILABLE = True
    else:
        TRANSLATOR_AVAILABLE = False
        FieldTranslator = None
except Exception as e:
    TRANSLATOR_AVAILABLE = False
    FieldTranslator = None

# AI clients
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

from bs4 import BeautifulSoup

logger = logging.getLogger("TORPEDO.CRProcessor")

# Config
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# Source files
CR_SOURCES_PATH = PROJECT_ROOT / "input_output" / "matrix" / "sources" / "corporate_registries.json"
SOURCES_PATH = PROJECT_ROOT / "input_output" / "matrix" / "sources.json"  # Fallback

# Output directory for screenshots
OUTPUT_DIR = MODULE_DIR / "PROCESSING" / "cr_audit_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# Test queries by jurisdiction
TEST_QUERIES = {
    "HU": "kft",
    "DE": "gmbh",
    "AT": "gmbh",
    "CH": "ag",
    "FR": "sarl",
    "ES": "sl",
    "IT": "srl",
    "NL": "bv",
    "BE": "bvba",
    "PL": "sp",
    "CZ": "sro",
    "RO": "srl",
    "BG": "eood",
    "GB": "ltd",
    "UK": "ltd",
    "IE": "ltd",
    "US": "llc",
    "HR": "d.o.o.",
    "RS": "d.o.o.",
    "SI": "d.o.o.",
    "BA": "d.o.o.",
    "GLOBAL": "bank",
}


@dataclass
class CRProcessorResult:
    """Result of processing a CR source."""
    domain: str
    jurisdiction: str
    source_id: str

    # Scrape classification
    scrape_method: str
    latency_ms: int
    status_code: int

    # Field extraction
    outputs: List[int]  # IO Matrix field codes
    outputs_named: List[str]  # Field names
    raw_fields: List[str]  # Original field names found
    unmapped_fields: List[str]  # Fields that couldn't be mapped

    # Input schema (what the search accepts)
    input_schema: Dict[str, Any]

    # Validation
    success: bool
    validated: bool  # Vision validated
    vision_missed: List[str]  # Fields visible but not extracted

    # Metadata
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    notes: str = ""
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)


class CRProcessor:
    """
    Corporate Registry Processor.

    Tests sources, extracts fields, translates to IO Matrix codes,
    optionally validates with vision, saves to sources JSON.
    """

    def __init__(self):
        self.scraper = TorpedoScraper()
        self.translator = FieldTranslator() if TRANSLATOR_AVAILABLE else None
        self.results: List[CRProcessorResult] = []
        self.sources_by_jurisdiction: Dict[str, List[Dict]] = {}
        self.loaded = False

        # HTTP client for screenshots
        self.http = None
        if HTTPX_AVAILABLE:
            self.http = httpx.AsyncClient(timeout=30, follow_redirects=True)

        # Screenshots directory
        self.screenshots_dir = OUTPUT_DIR / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)

        # Stats
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "with_outputs": 0,
            "vision_validated": 0,
        }

        logger.info(f"CRProcessor initialized")
        logger.info(f"  FieldTranslator: {'✓' if TRANSLATOR_AVAILABLE else '✗'}")
        logger.info(f"  Anthropic (vision): {'✓' if ANTHROPIC_API_KEY else '✗'}")
        logger.info(f"  Firecrawl (screenshots): {'✓' if FIRECRAWL_API_KEY else '✗'}")

    async def load_sources(self) -> int:
        """Load CR sources from cr_sources.json."""
        if self.loaded:
            return sum(len(s) for s in self.sources_by_jurisdiction.values())

        # Determine path
        path = CR_SOURCES_PATH if CR_SOURCES_PATH.exists() else SOURCES_PATH
        logger.info(f"Loading from {path}")

        try:
            with open(path) as f:
                data = json.load(f)

            count = 0

            # cr_sources.json has by_jurisdiction structure
            if "by_jurisdiction" in data:
                for jur, sources_list in data["by_jurisdiction"].items():
                    if jur == "GB":
                        jur = "UK"

                    if jur not in self.sources_by_jurisdiction:
                        self.sources_by_jurisdiction[jur] = []

                    for source in sources_list:
                        template = source.get("search_template") or source.get("search_url")
                        if not template or "{q}" not in template:
                            continue

                        domain = source.get("domain", "")
                        self.sources_by_jurisdiction[jur].append({
                            "domain": domain,
                            "search_template": template,
                            "jurisdiction": jur,
                            "name": source.get("name", domain),
                            "source_id": source.get("id", f"{jur}_{domain.replace('.', '_')}"),
                            "existing_scrape_method": source.get("scrape_method"),
                            "existing_outputs": source.get("outputs", []),
                        })
                        count += 1
            else:
                # Fallback: sources.json has flat sources dict
                sources_dict = data.get("sources", data)
                for domain, source in sources_dict.items():
                    category = source.get("category", "").lower()
                    source_type = source.get("type", "").lower()
                    section = source.get("section", "").lower()
                    is_cr = "cr" in category or "registry" in category or "corporate" in source_type or section == "cr"
                    if not is_cr:
                        continue

                    template = source.get("search_template") or source.get("search_url")
                    if not template or "{q}" not in template:
                        continue

                    jur = source.get("jurisdiction", "GLOBAL")
                    if jur == "GB":
                        jur = "UK"

                    if jur not in self.sources_by_jurisdiction:
                        self.sources_by_jurisdiction[jur] = []

                    self.sources_by_jurisdiction[jur].append({
                        "domain": domain,
                        "search_template": template,
                        "jurisdiction": jur,
                        "name": source.get("name", domain),
                        "source_id": source.get("id", f"{jur}_{domain.replace('.', '_')}"),
                        "existing_scrape_method": source.get("scrape_method"),
                        "existing_outputs": source.get("outputs", []),
                    })
                    count += 1

            self.loaded = True
            logger.info(f"Loaded {count} CR sources across {len(self.sources_by_jurisdiction)} jurisdictions")
            return count

        except Exception as e:
            logger.error(f"Failed to load CR sources: {e}")
            return 0

    def get_jurisdictions(self) -> List[str]:
        """Get list of jurisdictions with CR sources."""
        return sorted(self.sources_by_jurisdiction.keys())

    def get_sources_for_jurisdiction(self, jurisdiction: str) -> List[Dict]:
        """Get CR sources for a jurisdiction."""
        if jurisdiction == "GB":
            jurisdiction = "UK"
        return self.sources_by_jurisdiction.get(jurisdiction.upper(), [])

    async def process_source(
        self,
        source: Dict,
        validate_vision: bool = False
    ) -> CRProcessorResult:
        """
        Process a single CR source:
        1. Scrape with jester_bridge cascade
        2. Extract fields from HTML
        3. Translate to IO Matrix codes
        4. Optionally validate with vision
        """
        domain = source["domain"]
        jur = source["jurisdiction"]
        template = source["search_template"]
        source_id = source["source_id"]

        # Build test URL
        test_query = TEST_QUERIES.get(jur, TEST_QUERIES["GLOBAL"])
        url = template.replace("{q}", quote_plus(test_query))

        logger.info(f"  Processing {domain} ({jur})...")

        # 1. Scrape with cascade
        scrape_result = await self.scraper.scrape(url)

        if not scrape_result.success:
            return CRProcessorResult(
                domain=domain,
                jurisdiction=jur,
                source_id=source_id,
                scrape_method="failed",
                latency_ms=scrape_result.latency_ms,
                status_code=scrape_result.status_code,
                outputs=[],
                outputs_named=[],
                raw_fields=[],
                unmapped_fields=[],
                input_schema={},
                success=False,
                validated=False,
                vision_missed=[],
                error=scrape_result.error,
                notes="Scrape cascade failed"
            )

        html = scrape_result.html
        scrape_method = scrape_result.method.value

        # 2. Extract fields from HTML
        raw_fields = self._extract_fields_from_html(html, domain)

        # 3. Translate to IO Matrix codes
        outputs = []
        outputs_named = []
        unmapped = []

        if self.translator and raw_fields:
            for field_name in raw_fields:
                code = self.translator.to_code(field_name)
                if code is not None:
                    outputs.append(code)
                    canonical = self.translator.to_name(code)
                    if canonical:
                        outputs_named.append(canonical)
                else:
                    unmapped.append(field_name)
        else:
            unmapped = raw_fields

        # 4. Detect input schema
        input_schema = self._detect_input_schema(html, domain, jur)

        # 5. Vision validation (optional)
        screenshot_path = None
        vision_missed = []
        validated = False

        if validate_vision and FIRECRAWL_API_KEY and ANTHROPIC_API_KEY:
            screenshot_path = await self._capture_screenshot(url, f"{jur}_{domain.replace('.', '_')}")
            if screenshot_path:
                _, vision_missed = await self._validate_with_vision(
                    screenshot_path,
                    raw_fields,
                    domain
                )
                validated = True

        # Build result
        result = CRProcessorResult(
            domain=domain,
            jurisdiction=jur,
            source_id=source_id,
            scrape_method=scrape_method,
            latency_ms=scrape_result.latency_ms,
            status_code=scrape_result.status_code,
            outputs=outputs,
            outputs_named=outputs_named,
            raw_fields=raw_fields,
            unmapped_fields=unmapped,
            input_schema=input_schema,
            success=True,
            validated=validated,
            vision_missed=vision_missed,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            notes=f"Extracted {len(raw_fields)} fields, {len(outputs)} mapped to IO codes"
        )

        self.results.append(result)

        # Update stats
        self.stats["total"] += 1
        self.stats["success"] += 1
        if outputs:
            self.stats["with_outputs"] += 1
        if validated:
            self.stats["vision_validated"] += 1

        return result

    def _extract_fields_from_html(self, html: str, domain: str) -> List[str]:
        """Extract field names from HTML - looks for company data patterns."""
        fields = set()

        try:
            soup = BeautifulSoup(html, "html.parser")
        except:
            soup = BeautifulSoup(html, "lxml")

        # 1. Definition lists (dl/dt/dd)
        for dl in soup.select("dl"):
            for dt in dl.select("dt"):
                label = dt.text.strip().lower().replace(" ", "_").replace(":", "").replace("-", "_")
                if label and len(label) > 1 and len(label) < 50:
                    fields.add(label)

        # 2. Tables with label/value pairs
        for table in soup.select("table"):
            for row in table.select("tr"):
                cells = row.select("td, th")
                if len(cells) >= 2:
                    label = cells[0].text.strip().lower().replace(" ", "_").replace(":", "")
                    if label and len(label) > 1 and len(label) < 50:
                        fields.add(label)

        # 3. Form labels
        for label in soup.select("label"):
            text = label.text.strip().lower().replace(" ", "_").replace(":", "")
            if text and len(text) > 1 and len(text) < 50:
                fields.add(text)

        # 4. Common CR field patterns
        cr_patterns = [
            "company_name", "registration_number", "reg_number", "company_number",
            "tax_id", "vat_number", "status", "legal_form", "legal_status",
            "registered_address", "address", "headquarters",
            "incorporation_date", "founded", "registration_date",
            "directors", "officers", "shareholders", "beneficial_owners",
            "share_capital", "capital", "authorized_capital",
            "industry", "sic_code", "nace_code", "business_activity",
            "employees", "revenue", "turnover",
            "website", "email", "phone", "telephone",
            "previous_names", "trade_names",
        ]

        # Check if any pattern appears in page text
        page_text = soup.get_text().lower()
        for pattern in cr_patterns:
            if pattern.replace("_", " ") in page_text or pattern.replace("_", "") in page_text:
                fields.add(pattern)

        return sorted(list(fields))

    def _detect_input_schema(self, html: str, domain: str, jurisdiction: str) -> Dict:
        """Detect what input the search form accepts."""
        schema = {
            "input_type": "company_name",  # default
            "format": "free_text",
            "accepts_wildcards": False,
            "case_sensitive": False,
        }

        try:
            soup = BeautifulSoup(html, "html.parser")
        except:
            return schema

        # Look for input fields
        for inp in soup.select("input[type='text'], input[type='search'], input:not([type])"):
            name = (inp.get("name") or "").lower()
            placeholder = (inp.get("placeholder") or "").lower()

            # Detect ID-based search
            if any(x in name or x in placeholder for x in ["id", "number", "reg", "crn", "cin"]):
                schema["input_type"] = "registration_id"
                schema["format"] = "alphanumeric"

            # Detect pattern
            pattern = inp.get("pattern")
            if pattern:
                schema["format_pattern"] = pattern

            # Max length
            maxlen = inp.get("maxlength")
            if maxlen:
                schema["max_length"] = int(maxlen)

        return schema

    async def _capture_screenshot(self, url: str, filename: str) -> Optional[Path]:
        """Capture screenshot via Firecrawl."""
        if not FIRECRAWL_API_KEY or not self.http:
            return None

        try:
            response = await self.http.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "url": url,
                    "formats": ["screenshot"],
                    "waitFor": 3000
                }
            )

            if response.status_code == 200:
                data = response.json()
                screenshot_url = data.get("data", {}).get("screenshot")

                if screenshot_url:
                    img_response = await self.http.get(screenshot_url)
                    if img_response.status_code == 200:
                        filepath = self.screenshots_dir / f"{filename}.png"
                        filepath.write_bytes(img_response.content)
                        return filepath
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")

        return None

    async def _validate_with_vision(
        self,
        screenshot_path: Path,
        extracted_fields: List[str],
        domain: str
    ) -> Tuple[str, List[str]]:
        """Validate extraction with Claude vision."""
        if not ANTHROPIC_API_KEY:
            return "", []

        try:
            with open(screenshot_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            import requests
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": f"""Analyze this corporate registry page screenshot.

ALREADY EXTRACTED FIELDS:
{json.dumps(extracted_fields, indent=2)}

List any company data fields VISIBLE in the screenshot that were NOT extracted.
Return as JSON array of field names only:
["field1", "field2", ...]

If all visible fields were extracted, return: []"""
                            }
                        ]
                    }]
                },
                timeout=60
            )

            if response.status_code == 200:
                text = response.json()["content"][0]["text"]
                # Parse JSON array
                import re
                match = re.search(r'\[.*\]', text, re.DOTALL)
                if match:
                    missed = json.loads(match.group())
                    return text, missed

        except Exception as e:
            logger.warning(f"Vision validation failed: {e}")

        return "", []

    async def process_jurisdiction(
        self,
        jurisdiction: str,
        concurrent: int = 10,
        validate_vision: bool = False
    ) -> List[CRProcessorResult]:
        """Process all sources for a jurisdiction."""
        if not self.loaded:
            await self.load_sources()

        sources = self.get_sources_for_jurisdiction(jurisdiction)
        if not sources:
            logger.warning(f"No CR sources for {jurisdiction}")
            return []

        logger.info(f"Processing {len(sources)} CR sources for {jurisdiction}")

        semaphore = asyncio.Semaphore(concurrent)

        async def process_one(source: Dict) -> CRProcessorResult:
            async with semaphore:
                return await self.process_source(source, validate_vision)

        tasks = [process_one(s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                source = sources[i]
                final_results.append(CRProcessorResult(
                    domain=source["domain"],
                    jurisdiction=jurisdiction,
                    source_id=source["source_id"],
                    scrape_method="failed",
                    latency_ms=0,
                    status_code=0,
                    outputs=[],
                    outputs_named=[],
                    raw_fields=[],
                    unmapped_fields=[],
                    input_schema={},
                    success=False,
                    validated=False,
                    vision_missed=[],
                    error=str(r)
                ))
                self.stats["failed"] += 1
            else:
                final_results.append(r)

        return final_results

    async def process_all(
        self,
        concurrent: int = 10,
        jurisdictions: List[str] = None,
        validate_vision: bool = False
    ) -> List[CRProcessorResult]:
        """Process all CR sources."""
        if not self.loaded:
            await self.load_sources()

        jurs = jurisdictions or self.get_jurisdictions()
        all_results = []

        for jur in jurs:
            results = await self.process_jurisdiction(jur, concurrent, validate_vision)
            all_results.extend(results)

        return all_results

    def save_to_sources_json(self):
        """
        Update sources/corporate_registries.json with processing results.

        Adds/updates for each source:
        - scrape_method
        - outputs (IO Matrix codes)
        - input_schema
        - validated
        - http_latency
        """
        path = CR_SOURCES_PATH if CR_SOURCES_PATH.exists() else SOURCES_PATH

        with open(path) as f:
            data = json.load(f)

        sources_dict = data.get("sources", data)

        # Build lookup by domain
        by_domain = {r.domain: r for r in self.results}

        updated = 0
        for domain, source in sources_dict.items():
            result = by_domain.get(domain)
            if result and result.success:
                source["scrape_method"] = result.scrape_method
                source["outputs"] = result.outputs
                source["outputs_named"] = result.outputs_named
                source["input_schema"] = result.input_schema
                source["http_latency"] = result.latency_ms
                source["validated"] = result.validated
                source["last_processed"] = result.processed_at

                if result.vision_missed:
                    source["vision_missed"] = result.vision_missed

                updated += 1

        # Write back
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Updated {updated} sources in {path}")

    def save_results_json(self, output_path: Path):
        """Save detailed results to separate JSON file."""
        output = {
            "processed_at": datetime.now().isoformat(),
            "stats": self.stats,
            "results": [r.to_dict() for r in self.results]
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved {len(self.results)} results to {output_path}")

    async def close(self):
        """Close connections."""
        await self.scraper.close()
        if self.http:
            await self.http.aclose()


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

async def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="TORPEDO CR Processor")
    parser.add_argument("--jurisdiction", "-j", help="Single jurisdiction to process")
    parser.add_argument("--all", action="store_true", help="Process all jurisdictions")
    parser.add_argument("--concurrent", "-c", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--validate-vision", action="store_true", help="Validate with Claude vision")
    parser.add_argument("--output", "-o", help="Output path for detailed results")
    parser.add_argument("--list-jurisdictions", action="store_true", help="List available jurisdictions")
    args = parser.parse_args()

    processor = CRProcessor()
    await processor.load_sources()

    if args.list_jurisdictions:
        jurs = processor.get_jurisdictions()
        print(f"Available jurisdictions ({len(jurs)}):")
        for j in jurs:
            count = len(processor.get_sources_for_jurisdiction(j))
            print(f"  {j}: {count} sources")
        return

    # Process
    if args.jurisdiction:
        await processor.process_jurisdiction(
            args.jurisdiction,
            concurrent=args.concurrent,
            validate_vision=args.validate_vision
        )
    elif args.all:
        await processor.process_all(
            concurrent=args.concurrent,
            validate_vision=args.validate_vision
        )
    else:
        print("Specify --jurisdiction XX or --all")
        return

    # Save to sources JSON
    processor.save_to_sources_json()

    # Save detailed results
    output_path = Path(args.output) if args.output else OUTPUT_DIR / "cr_processing_results.json"
    processor.save_results_json(output_path)

    # Summary
    print(f"\n{'='*50}")
    print("CR PROCESSING COMPLETE")
    print(f"{'='*50}")
    print(f"  Total: {processor.stats['total']}")
    print(f"  Success: {processor.stats['success']}")
    print(f"  With outputs: {processor.stats['with_outputs']}")
    print(f"  Vision validated: {processor.stats['vision_validated']}")
    print(f"  Failed: {processor.stats['failed']}")

    await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
