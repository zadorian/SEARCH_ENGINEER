"""
SEEKLEECH - Search Template Miner

Finds search pages and URL templates for registry websites.
Uses Haiku for AI analysis, with fallback chain for bot protection.

Flow:
1. Sitemap/robots.txt check (free)
2. Scrape homepage → extract links/forms only → Haiku analyzes
3. If not found → Haiku generates Google query → search
4. If not found → CC Index URL patterns
5. Validate template works
6. Save progress after each (resume-safe)

Fallback chain for scraping:
1. Direct httpx
2. Firecrawl API (bypasses bots)
3. Bright Data MCP (browser automation) - TODO

Usage:
    python seekleech.py --input sources.json --output enriched.json --jurisdiction HU --limit 50
"""

import asyncio
import json
import os
import re
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import logging
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from ...paths import env_file

# Load environment BEFORE reading env vars (best-effort)
_env = env_file()
if _env:
    load_dotenv(_env)

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

# Google Genai (Vertex-compatible) - same as gemini_longtext.py
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False
    google_genai = None
    genai_types = None

logger = logging.getLogger("SeekLeech")

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Use GEMINI_API_KEY for direct Gemini/Vertex access (like gemini_longtext.py)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # For Custom Search API only
GOOGLE_CX = os.getenv("GOOGLE_CX") or os.getenv("GOOGLE_CSE_ID")  # Google Custom Search Engine ID
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")

# Startup verification
logger.info(f"SeekLeech Config:")
logger.info(f"  Anthropic: {'✓' if ANTHROPIC_API_KEY else '✗'}")
logger.info(f"  Gemini (google-genai): {'✓' if GEMINI_API_KEY and GOOGLE_GENAI_AVAILABLE else '✗'}")
logger.info(f"  OpenAI: {'✓' if OPENAI_API_KEY else '✗'}")
logger.info(f"  OpenRouter: {'✓' if OPENROUTER_API_KEY else '✗'}")
logger.info(f"  Google CSE: {'✓' if GOOGLE_CX else '✗'}")
logger.info(f"  Firecrawl: {'✓' if FIRECRAWL_API_KEY else '✗'}")

# Initialize clients
anthropic_client = (
    anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    if ANTHROPIC_API_KEY and ANTHROPIC_AVAILABLE
    else None
)

# Initialize Gemini client - EXACT same as gemini_longtext.py
gemini_client = None
if GOOGLE_GENAI_AVAILABLE and GEMINI_API_KEY:
    try:
        gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
        logger.info("  Gemini client initialized")
    except Exception as e:
        logger.warning(f"  Failed to initialize Gemini client: {e}")

openai_client = (
    AsyncOpenAI(api_key=OPENAI_API_KEY)
    if OPENAI_API_KEY and OPENAI_AVAILABLE
    else None
)

openrouter_client = (
    AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    if OPENROUTER_API_KEY and OPENAI_AVAILABLE
    else None
)


# ─────────────────────────────────────────────────────────────
# Model Pool - Rotate across providers for max concurrency
# ─────────────────────────────────────────────────────────────

class ModelPool:
    """
    Rotates AI calls across multiple providers to avoid rate limits.
    Each provider can handle ~50 concurrent, so 4 providers = 200 concurrent.
    """

    def __init__(self):
        self.models = []
        self.index = 0
        self.lock = asyncio.Lock()

        # Gemini via Vertex AI (no free tier limits)
        if gemini_client:
            self.models.append(("gemini", "gemini-2.0-flash"))
            self.models.append(("gemini", "gemini-2.5-flash"))

        if ANTHROPIC_API_KEY and ANTHROPIC_AVAILABLE:
            self.models.append(("anthropic", "claude-haiku-4-5-20251001"))

        if OPENAI_API_KEY and OPENAI_AVAILABLE:
            self.models.append(("openai", "gpt-5-mini"))

        if OPENROUTER_API_KEY and OPENAI_AVAILABLE:
            # Add OpenRouter models for more capacity
            self.models.append(("openrouter", "anthropic/claude-3-haiku:beta"))

        if not self.models:
            raise RuntimeError("No AI API keys configured! Need at least one of: GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY")

        logger.info(f"ModelPool initialized with {len(self.models)} models: {[m[1] for m in self.models]}")

    async def get_next(self) -> Tuple[str, str]:
        """Get next model in rotation (thread-safe)."""
        async with self.lock:
            model = self.models[self.index]
            self.index = (self.index + 1) % len(self.models)
            return model

    async def call(self, prompt: str) -> str:
        """Call next available model."""
        last_error = None
        for _ in range(len(self.models)):
            provider, model = await self.get_next()
            try:
                if provider == "anthropic":
                    resp = await anthropic_client.messages.create(
                        model=model,
                        max_tokens=4000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return resp.content[0].text

                elif provider == "gemini":
                    # Use google-genai client (like gemini_longtext.py)
                    # Run in thread pool since google-genai is synchronous
                    def _call_gemini():
                        response = gemini_client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=genai_types.GenerateContentConfig(
                                max_output_tokens=4000,
                            )
                        )
                        return response.text

                    return await asyncio.to_thread(_call_gemini)

                elif provider == "openai":
                    # GPT-5 uses max_completion_tokens, not max_tokens
                    resp = await openai_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_completion_tokens=4000
                    )
                    return resp.choices[0].message.content

                elif provider == "openrouter":
                    resp = await openrouter_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=4000
                    )
                    return resp.choices[0].message.content

            except Exception as e:
                last_error = e
                logger.warning(f"Model {provider}/{model} failed: {e}")
                continue

        raise RuntimeError(
            f"All AI providers failed. Last error: {last_error}"
        )


# Global model pool (initialized lazily)
_model_pool: Optional[ModelPool] = None

def get_model_pool() -> ModelPool:
    global _model_pool
    if _model_pool is None:
        _model_pool = ModelPool()
    return _model_pool


@dataclass
class InputSchema:
    """What input a search template accepts."""
    input_type: str = "company_name"  # company_name, person_name, reg_id, case_number, address, date_range
    format: str = "free_text"  # free_text, numeric, alphanumeric, formatted
    format_pattern: Optional[str] = None  # regex pattern e.g. r"^\d{8}$" for 8-digit IDs
    examples: List[str] = None  # ["12345678", "OTP Bank"]
    accepts_wildcards: bool = False  # True if * or % work
    case_sensitive: bool = False
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    encoding: str = "utf-8"  # utf-8, latin-1, url-encoded

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['examples'] = self.examples or []
        return d


# Thematic taxonomy for source classification
THEMATIC_TAXONOMY = {
    "corporate": ["corporate_registry", "officers", "shareholders", "beneficial_ownership", "filings", "branches"],
    "legal": ["court_records", "litigation", "bankruptcy", "liens", "enforcement"],
    "property": ["land_registry", "cadastre", "mortgages", "planning"],
    "regulatory": ["sanctions", "pep", "licenses", "procurement", "tax_records"],
    "financial": ["stock_exchange", "banking", "insurance", "investment"],
    "professional": ["lawyers", "doctors", "accountants", "engineers"],
}


@dataclass
class TemplateResult:
    """Result of template extraction."""
    template: str
    method: str = "GET"  # GET or POST
    input_type: str = "name"  # name, id, mixed
    confidence: float = 0.0
    notes: str = ""


@dataclass
class SeekLeechResult:
    """Full result for a registry."""
    id: str
    domain: str
    jurisdiction: str
    url: str
    status: str  # found, not_found, scrape_failed, etc.
    method: str = ""  # how we found it: homepage, google, cc_index
    templates: Dict[str, Any] = None  # search_by_name, search_by_id, profile_by_id, etc.
    requires_browser: bool = False  # True if POST form or JS-heavy
    validated: bool = False
    timestamp: str = ""
    notes: str = ""

    # NEW: Enhanced discovery fields
    input_schema: Dict[str, Any] = None  # InputSchema for each template type
    thematic_tags: List[str] = None  # ["corporate_registry", "officers", "shareholders"]
    language: str = ""  # detected page language
    requires_translation: bool = False  # True if search requires local language input

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['templates'] = self.templates or {}
        d['input_schema'] = self.input_schema or {}
        d['thematic_tags'] = self.thematic_tags or []
        return d


class SeekLeech:
    """
    Mines registry URLs for search templates.
    """

    def __init__(self):
        self.http = httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )

    async def close(self):
        await self.http.aclose()

    # ─────────────────────────────────────────────────────────────
    # Scraping with fallback chain
    # ─────────────────────────────────────────────────────────────

    async def scrape(self, url: str) -> Tuple[Optional[str], str]:
        """
        Scrape URL with fallback chain.
        Returns (html, method_used) or (None, error).
        """
        # Method 1: Direct httpx
        try:
            resp = await self.http.get(url)
            if resp.status_code == 200:
                return resp.text, "direct"
            elif resp.status_code in (403, 429, 503):
                logger.info(f"  🔥 Bot blocked ({resp.status_code}), trying Firecrawl...")
            else:
                # Still try Firecrawl for other errors
                logger.debug(f"HTTP {resp.status_code}, trying Firecrawl...")
        except Exception as e:
            logger.debug(f"Direct scrape failed: {e}")

        # Method 2: Firecrawl API
        if FIRECRAWL_API_KEY:
            try:
                resp = await self.http.post(
                    f"{FIRECRAWL_BASE_URL}/scrape",
                    headers={
                        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={"url": url, "formats": ["html"]}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("data", {}).get("html"):
                        logger.info(f"  🔥 Firecrawl SUCCESS for {url[:50]}")
                        return data["data"]["html"], "firecrawl"
            except Exception as e:
                logger.debug(f"Firecrawl failed: {e}")

        # Method 3: Bright Data MCP - TODO
        # Would use mcp__BrightData__scrape_as_markdown here

        return None, "all_failed"

    # ─────────────────────────────────────────────────────────────
    # HTML preprocessing - extract only what matters
    # ─────────────────────────────────────────────────────────────

    def extract_essentials(self, html: str, base_url: str) -> str:
        """Extract just links and forms from HTML. Reduces 60k → 2k tokens."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except:
            soup = BeautifulSoup(html, 'lxml')

        # Get page title
        title = soup.title.string if soup.title else ""

        # Extract all links
        links = []
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').strip()
            text = a.get_text(strip=True)[:80]

            # Skip junk
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            if len(href) > 500:  # Skip data URLs etc.
                continue

            links.append(f"[{text}] → {href}")

        # Extract all forms
        forms = []
        for f in soup.find_all('form'):
            action = f.get('action', '') or base_url
            method = f.get('method', 'GET').upper()

            inputs = []
            for inp in f.find_all(['input', 'select', 'textarea']):
                name = inp.get('name', '')
                inp_type = inp.get('type', 'text')
                placeholder = inp.get('placeholder', '')
                if name and inp_type not in ('hidden', 'submit', 'button'):
                    inputs.append(f"{name}({inp_type}){': ' + placeholder if placeholder else ''}")

            if inputs:
                forms.append(f"FORM [{method}] action={action}\n  Fields: {', '.join(inputs)}")

        # Build compact representation
        output = f"PAGE: {title}\nURL: {base_url}\n\n"
        output += f"=== LINKS ({len(links)}) ===\n"
        output += "\n".join(links[:80])  # Limit links
        output += f"\n\n=== FORMS ({len(forms)}) ===\n"
        output += "\n\n".join(forms)

        return output

    # ─────────────────────────────────────────────────────────────
    # Free checks - sitemap, robots
    # ─────────────────────────────────────────────────────────────

    async def check_sitemap_robots(self, domain: str) -> List[str]:
        """Check sitemap.xml and robots.txt for search URLs - FREE."""
        candidates = []

        for path in ['/sitemap.xml', '/sitemap_index.xml', '/robots.txt']:
            try:
                resp = await self.http.get(f"https://{domain}{path}", timeout=10)
                if resp.status_code != 200:
                    continue

                text = resp.text
                # Find URLs containing search-related terms
                patterns = [
                    r'https?://[^\s<>"\']+(?:search|find|query|lookup|buscar|recherche|suche|ricerca|zoeken|keresés|szukaj|haku|søk|søg|pesquisa|cerca|поиск|検索|搜索)[^\s<>"\']*',
                ]
                for pattern in patterns:
                    for match in re.findall(pattern, text, re.I):
                        if domain in match:
                            candidates.append(match)
            except:
                pass

        return list(set(candidates))

    # ─────────────────────────────────────────────────────────────
    # AI - Uses model pool for max concurrency
    # ─────────────────────────────────────────────────────────────

    async def ai(self, prompt: str) -> str:
        """Call next available AI model from pool."""
        pool = get_model_pool()
        return await pool.call(prompt)

    # Alias for backwards compatibility
    async def haiku(self, prompt: str) -> str:
        return await self.ai(prompt)

    def parse_json(self, text: str) -> Dict:
        """Extract JSON from Haiku response."""
        # Find JSON block
        text = text.replace('```json', '').replace('```', '')
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                pass
        return {}

    async def analyze_page(self, domain: str, page_content: str, context: str = "") -> Dict:
        """
        AI analyzes extracted links/forms to find search functionality.
        Returns templates, input_schema, and thematic classification.
        """
        prompt = f"""You are analyzing a registry/database website for automation.
Domain: {domain}
{context}

FIND AND DOCUMENT:

1. SEARCH FUNCTIONALITY
   - All search URLs with {{query}} placeholder
   - Form methods (GET vs POST)
   - Required parameters vs optional

2. INPUT SCHEMA (Critical for Automation)
   For each search template, determine:
   - input_type: company_name, person_name, reg_id, case_number, address, date_range, mixed
   - format: free_text, numeric, alphanumeric, formatted
   - format_pattern: regex if specific format required (e.g., "^\\d{{8}}$" for 8-digit IDs)
   - examples: actual examples from the page (quote exactly)
   - accepts_wildcards: true if * or % work
   - max_length/min_length: if specified

3. THEMATIC CLASSIFICATION
   Assign tags from: corporate_registry, officers, shareholders, beneficial_ownership, filings,
   branches, court_records, litigation, bankruptcy, liens, enforcement, land_registry,
   cadastre, mortgages, sanctions, pep, licenses, procurement, tax_records, stock_exchange

4. LANGUAGE & LOCALIZATION
   - Page language code (en, de, hu, hr, sr, etc.)
   - Does search require local language input?

{page_content}

Return JSON:
{{
    "language": "en",
    "requires_translation": false,
    "found": true/false,
    "templates": {{
        "search_by_name": {{
            "url": "...",
            "template": "https://domain/search?q={{query}}",
            "method": "GET/POST"
        }},
        "search_by_id": {{
            "url": "...",
            "template": "https://domain/lookup?id={{id}}",
            "method": "GET"
        }},
        "profile_by_id": {{"template": "https://domain/company/{{id}}", "id_format": "numeric/alphanumeric"}},
        "officer_search": {{"template": "..."}},
        "document_search": {{"template": "..."}}
    }},
    "input_schema": {{
        "search_by_name": {{
            "input_type": "company_name",
            "format": "free_text",
            "format_pattern": null,
            "examples": ["Example Corp", "OTP Bank"],
            "accepts_wildcards": true,
            "case_sensitive": false,
            "max_length": 100
        }},
        "search_by_id": {{
            "input_type": "reg_id",
            "format": "numeric",
            "format_pattern": "^\\d{{8}}$",
            "examples": ["12345678"],
            "accepts_wildcards": false
        }}
    }},
    "thematic_tags": ["corporate_registry", "officers", "shareholders"],
    "requires_browser": false,
    "google_query": "site:{domain} [search terms in site's language with OR variations]",
    "notes": "what you found"
}}

Only include template types you actually found. Use {{query}}, {{id}}, {{name}} as placeholders.
For POST forms, set requires_browser: true.
"""

        response = await self.haiku(prompt)
        return self.parse_json(response)

    # ─────────────────────────────────────────────────────────────
    # Google site: search (using Google Custom Search API)
    # ─────────────────────────────────────────────────────────────

    async def google_search(self, query: str, domain: str) -> List[str]:
        """Google search via Custom Search API, filter to domain."""
        if not GOOGLE_API_KEY or not GOOGLE_CX:
            logger.debug("No GOOGLE_API_KEY or GOOGLE_CX")
            return []

        try:
            resp = await self.http.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CX,
                    "q": query,
                    "num": 10,  # Max 10 per request for CSE
                }
            )
            data = resp.json()

            urls = []
            for item in data.get("items", []):
                url = item.get("link", "")
                if url and domain in url:
                    urls.append(url)
            return urls
        except Exception as e:
            logger.error(f"Google CSE search failed: {e}")
        return []

    # ─────────────────────────────────────────────────────────────
    # CC Index
    # ─────────────────────────────────────────────────────────────

    async def get_cc_urls(self, domain: str, limit: int = 300) -> List[str]:
        """Get all URLs for domain from Common Crawl index."""
        try:
            resp = await self.http.get(
                "https://index.commoncrawl.org/CC-MAIN-2024-10-index",
                params={
                    "url": f"*.{domain}/*",
                    "matchType": "domain",
                    "output": "json",
                    "limit": limit,
                    "filter": "status:200"
                },
                timeout=30
            )

            urls = []
            for line in resp.text.strip().split('\n'):
                if line:
                    try:
                        data = json.loads(line)
                        urls.append(data.get("url", ""))
                    except:
                        pass
            return urls
        except Exception as e:
            logger.debug(f"CC Index failed: {e}")
        return []

    async def analyze_url_patterns(self, domain: str, urls: List[str]) -> Dict:
        """Haiku finds patterns in URL list."""
        if not urls:
            return {}

        # Dedupe and sample
        unique = list(set(urls))[:150]
        url_list = "\n".join(unique)

        prompt = f"""Analyze these URLs from {domain} (a registry/database).

Find:
1. Search page URLs
2. Profile URL templates - URLs with company ID or name in them

Examples of profile templates:
- /company/12345 → /company/{{id}}
- /entity/ACME-LTD → /entity/{{name}}
- /register/view?id=789 → /register/view?id={{id}}

Return JSON:
{{
    "search_pages": ["url1", "url2"],
    "profile_templates": [
        {{"example": "/company/12345", "template": "https://{domain}/company/{{id}}", "type": "numeric_id"}},
        {{"example": "/entity/ACME-LTD", "template": "https://{domain}/entity/{{name}}", "type": "company_name"}}
    ]
}}

URLs:
{url_list}
"""
        response = await self.haiku(prompt)
        return self.parse_json(response)

    # ─────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────

    async def validate_template(self, template: str) -> bool:
        """Test that template actually works."""
        # Build test URL
        test_url = template
        test_url = test_url.replace('{query}', 'test')
        test_url = test_url.replace('{id}', '12345')
        test_url = test_url.replace('{name}', 'acme')

        try:
            resp = await self.http.get(test_url, timeout=15)
            # Should return 200 and have some content
            if resp.status_code == 200 and len(resp.text) > 500:
                return True
        except:
            pass
        return False

    # ─────────────────────────────────────────────────────────────
    # Main mining logic
    # ─────────────────────────────────────────────────────────────

    async def mine(self, registry: Dict) -> SeekLeechResult:
        """Mine a single registry for templates."""

        url = (registry.get("url") or "").rstrip("/")
        domain = registry.get("domain") or ""
        jurisdiction = registry.get("jurisdiction") or ""
        reg_id = registry.get("id") or domain

        result = SeekLeechResult(
            id=reg_id,
            domain=domain,
            jurisdiction=jurisdiction,
            url=url,
            status="pending",
            timestamp=datetime.now().isoformat()
        )

        # Skip if already has template
        if registry.get("search_template"):
            result.status = "skipped_has_template"
            result.templates = {"search_by_name": {"template": registry["search_template"]}}
            return result

        # ── STEP 0: Check sitemap/robots (FREE) ──
        sitemap_urls = await self.check_sitemap_robots(domain)
        if sitemap_urls:
            logger.info(f"  Found {len(sitemap_urls)} candidates in sitemap/robots")
            # Try first candidate
            for surl in sitemap_urls[:2]:
                html, method = await self.scrape(surl)
                if html:
                    content = self.extract_essentials(html, surl)
                    analysis = await self.analyze_page(domain, content, "Found via sitemap - likely search page.")
                    if analysis.get("found") and analysis.get("templates"):
                        result.status = "found"
                        result.method = "sitemap"
                        result.templates = analysis["templates"]
                        result.requires_browser = analysis.get("requires_browser", False)
                        # NEW: Enhanced discovery fields
                        result.input_schema = analysis.get("input_schema", {})
                        result.thematic_tags = analysis.get("thematic_tags", [])
                        result.language = analysis.get("language", "")
                        result.requires_translation = analysis.get("requires_translation", False)
                        return result

        # ── STEP 1: Homepage ──
        logger.info(f"  [1/3] Scraping homepage...")
        html, scrape_method = await self.scrape(url)

        if not html:
            result.status = f"scrape_failed_{scrape_method}"
            return result

        content = self.extract_essentials(html, url)
        analysis = await self.analyze_page(domain, content)

        if analysis.get("found") and analysis.get("templates"):
            result.status = "found"
            result.method = f"homepage_{scrape_method}"
            result.templates = analysis["templates"]
            result.requires_browser = analysis.get("requires_browser", False)
            # NEW: Enhanced discovery fields
            result.input_schema = analysis.get("input_schema", {})
            result.thematic_tags = analysis.get("thematic_tags", [])
            result.language = analysis.get("language", "")
            result.requires_translation = analysis.get("requires_translation", False)

            # If we found a search URL but not the template, fetch that page
            for ttype, tdata in list(result.templates.items()):
                if tdata and isinstance(tdata, dict) and tdata.get("url") and not tdata.get("template"):
                    search_url = tdata["url"]
                    if search_url.startswith("/"):
                        search_url = f"https://{domain}{search_url}"

                    shtml, _ = await self.scrape(search_url)
                    if shtml:
                        scontent = self.extract_essentials(shtml, search_url)
                        sanalysis = await self.analyze_page(domain, scontent, "This IS the search page. Extract template.")
                        if sanalysis.get("templates"):
                            result.templates.update(sanalysis["templates"])

            return result

        # ── STEP 2: Google site: search ──
        google_query = analysis.get("google_query", "")
        if google_query:
            logger.info(f"  [2/3] Google: {google_query[:60]}...")
            google_urls = await self.google_search(google_query, domain)

            for gurl in google_urls[:3]:
                ghtml, gmethod = await self.scrape(gurl)
                if ghtml:
                    gcontent = self.extract_essentials(ghtml, gurl)
                    ganalysis = await self.analyze_page(domain, gcontent, "Found via Google - likely search page.")

                    if ganalysis.get("found") and ganalysis.get("templates"):
                        result.status = "found"
                        result.method = f"google_{gmethod}"
                        result.templates = ganalysis["templates"]
                        result.requires_browser = ganalysis.get("requires_browser", False)
                        # NEW: Enhanced discovery fields
                        result.input_schema = ganalysis.get("input_schema", {})
                        result.thematic_tags = ganalysis.get("thematic_tags", [])
                        result.language = ganalysis.get("language", "")
                        result.requires_translation = ganalysis.get("requires_translation", False)
                        return result
        else:
            logger.info(f"  [2/3] Skipping Google (no query generated)")

        # ── STEP 3: CC Index patterns ──
        logger.info(f"  [3/3] CC Index...")
        cc_urls = await self.get_cc_urls(domain)

        if cc_urls:
            patterns = await self.analyze_url_patterns(domain, cc_urls)

            # Try search pages from CC
            for sp_url in patterns.get("search_pages", [])[:2]:
                sphtml, spmethod = await self.scrape(sp_url)
                if sphtml:
                    spcontent = self.extract_essentials(sphtml, sp_url)
                    spanalysis = await self.analyze_page(domain, spcontent, "Search page from CC archives.")

                    if spanalysis.get("templates"):
                        result.status = "found"
                        result.method = f"cc_index_{spmethod}"
                        result.templates = spanalysis["templates"]
                        # NEW: Enhanced discovery fields
                        result.input_schema = spanalysis.get("input_schema", {})
                        result.thematic_tags = spanalysis.get("thematic_tags", [])
                        result.language = spanalysis.get("language", "")
                        result.requires_translation = spanalysis.get("requires_translation", False)
                        return result

            # If we found profile templates at least
            if patterns.get("profile_templates"):
                result.status = "found_profiles_only"
                result.method = "cc_index"
                result.templates = {}
                for pt in patterns["profile_templates"]:
                    key = f"profile_by_{pt.get('type', 'id')}"
                    result.templates[key] = {"template": pt.get("template"), "example": pt.get("example")}
                return result

        result.status = "not_found"
        result.notes = analysis.get("notes", "")
        return result

    # ─────────────────────────────────────────────────────────────
    # Batch processing with persistence
    # ─────────────────────────────────────────────────────────────

    async def run(
        self,
        registries: List[Dict],
        output: Path,
        concurrent: int = 3,
        resume: bool = True,
        validate: bool = True
    ) -> List[SeekLeechResult]:
        """
        Process registries with progress persistence.
        """

        # Load existing progress
        done: Dict[str, Dict] = {}
        if resume and output.exists():
            try:
                with open(output) as f:
                    for r in json.load(f):
                        key = r.get('id') or r.get('domain')
                        done[key] = r
                logger.info(f"Resuming: {len(done)} already done")
            except:
                pass

        # Filter to remaining
        remaining = []
        for r in registries:
            key = r.get('id') or r.get('domain')
            if key not in done:
                remaining.append(r)

        logger.info(f"Processing {len(remaining)} registries ({len(done)} skipped)")

        results = list(done.values())
        sem = asyncio.Semaphore(concurrent)
        found_count = 0
        processed_count = 0

        async def process(reg: Dict, idx: int) -> SeekLeechResult:
            nonlocal found_count, processed_count
            async with sem:
                domain = reg.get('domain', '')

                result = await self.mine(reg)

                # Validate templates
                if validate and result.templates:
                    for ttype, tdata in list(result.templates.items()):
                        if not tdata or not isinstance(tdata, dict):
                            continue
                        template = tdata.get("template", "")
                        if template and "{" in template:
                            valid = await self.validate_template(template)
                            tdata["validated"] = valid
                            if valid:
                                result.validated = True

                processed_count += 1

                # Log with clear SUCCESS indicator
                if result.status == "found":
                    found_count += 1
                    # Get first template for display
                    first_template = ""
                    if result.templates:
                        for ttype, tdata in list(result.templates.items()):
                            if tdata and isinstance(tdata, dict) and tdata.get("template"):
                                first_template = tdata["template"][:80]
                                break
                    logger.info(f"")
                    logger.info(f"🎯 FOUND [{found_count}] {domain}")
                    logger.info(f"   Template: {first_template}")
                    logger.info(f"   Method: {result.method}")
                    logger.info(f"   Progress: {processed_count}/{len(remaining)} ({100*processed_count//len(remaining)}%)")
                    logger.info(f"")
                elif "profile" in result.status:
                    logger.info(f"○ [{processed_count}/{len(remaining)}] {domain} → profiles only")
                else:
                    # Just show progress every 50
                    if processed_count % 50 == 0:
                        logger.info(f"... {processed_count}/{len(remaining)} processed, {found_count} found ...")

                return result

        # Process in parallel batches
        save_lock = asyncio.Lock()

        async def process_and_save(reg: Dict, idx: int):
            result = await process(reg, idx)
            async with save_lock:
                results.append(result.to_dict())
                # Save progress periodically (every 10)
                if len(results) % 10 == 0:
                    with open(output, 'w') as f:
                        json.dump(results, f, indent=2)
            return result

        # Launch all tasks with semaphore controlling concurrency
        tasks = [process_and_save(reg, i) for i, reg in enumerate(remaining)]
        await asyncio.gather(*tasks)

        # Final save
        with open(output, 'w') as f:
            json.dump(results, f, indent=2)

        # Final stats
        found = sum(1 for r in results if r.get('status') == 'found')
        profiles = sum(1 for r in results if 'profile' in r.get('status', ''))
        failed = sum(1 for r in results if 'failed' in r.get('status', ''))

        logger.info(f"\n{'='*50}")
        logger.info(f"DONE: {found} search templates, {profiles} profile-only, {failed} failed")
        logger.info(f"Results saved to {output}")

        return results


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"
    )

    parser = argparse.ArgumentParser(description="Mine registry URLs for search templates")
    parser.add_argument("--input", required=True, help="Path to sources.json")
    parser.add_argument("--output", default="prospector_results.json", help="Output path")
    parser.add_argument("--jurisdiction", help="Filter by jurisdiction (e.g., HU, DE, US)")
    parser.add_argument("--type", help="Filter by type (e.g., corporate_registry)")
    parser.add_argument("--limit", type=int, default=50, help="Max registries to process")
    parser.add_argument("--concurrent", type=int, default=3, help="Concurrent requests")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh, ignore existing progress")
    parser.add_argument("--no-validate", action="store_true", help="Skip template validation")

    args = parser.parse_args()

    async def main():
        # Load sources
        with open(args.input) as f:
            sources = json.load(f)

        # Flatten and filter
        registries = []
        for jur, entries in sources.items():
            if args.jurisdiction and jur != args.jurisdiction:
                continue
            for e in entries:
                if args.type and e.get("type") != args.type:
                    continue
                if not e.get("search_template"):  # Only those without templates
                    registries.append(e)

        # Sort by URL count (process most-used first)
        registries.sort(
            key=lambda r: -(r.get("metadata", {}).get("url_count_in_reports", 0))
        )

        registries = registries[:args.limit]

        if not registries:
            logger.error("No registries to process!")
            return

        logger.info(f"Found {len(registries)} registries to process")

        leech = SeekLeech()
        try:
            await leech.run(
                registries,
                output=Path(args.output),
                concurrent=args.concurrent,
                resume=not args.no_resume,
                validate=not args.no_validate
            )
        finally:
            await leech.close()

    asyncio.run(main())
