"SMART BANG ORCHESTRATOR
=======================

Orchestrates the "Smart Extract" pipeline:
1. Trigger: Receives a query + bang + intent (header).
2. Search: Runs auto_bang_search to get candidates.
3. Select: Uses Watcher Extraction (Transient) to find the BEST url matching the intent.
4. Scrape: Uses JESTER (Go/Hybrid Scraper) to scrape the winner.
5. Extract: Uses Watcher Extraction (Deep) to pull specific facts.

Leverages existing modules:
- BACKEND/modules/BRUTE/auto_bang_search.py
- BACKEND/modules/LINKLATER/scraping/web/crawler.py (Jester)
- BACKEND/modules/LINKLATER/watchers/watcher_extraction.py
"

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import urlparse

# Import existing capabilities
from modules.brute.auto_bang_search import (
    auto_bang_search,
    NEWS_BANGS,
    SOCIAL_BANGS
)
from modules.LINKLATER.scraping.web.crawler import Jester, JesterConfig
from modules.LINKLATER.watchers.watcher_extraction import (
    check_source_against_watchers,
    _invoke_model,
    _get_next_model,
    ExtractionResult
)

# Setup logging
logger = logging.getLogger("SmartBang")

class SmartBangOrchestrator:
    def __init__(self):
        # Initialize JESTER (The Superior Go/Crawlee Hybrid Scraper)
        # Configured for single-target precision scraping
        self.config = JesterConfig(
            max_pages=1,
            max_depth=0,
            use_hybrid_crawler=True,  # Enable Go fast path
            go_crawler_concurrent=5,  # Low concurrency for single target
            screenshot_all=False,
            extract_entities=False,   # We use Watcher for extraction
            generate_embeddings=False,
            index_to_elasticsearch=False # Don't pollute index with transient scrapes
        )
        self.jester = Jester(self.config)

    async def close(self):
        # Jester manages its own resources (Go bridge, etc.)
        pass

    async def _select_best_source(self, candidates: List[Dict[str, str]], intent: str) -> Optional[str]:
        """
        Select the best source using the Watcher Multi-Model Infrastructure.
        Reuses _invoke_model and _get_next_model from watcher_extraction.py.
        """
        if not candidates:
            return None

        # Format candidates for the prompt
        candidates_text = ""
        for i, c in enumerate(candidates):
            candidates_text += f"[{i+1}]\nTITLE: {c.get('title', '')}\nURL: {c.get('url', '')}\nSNIPPET: {c.get('snippet', '')}\n\n"

        prompt = f"""You are an expert research assistant. Select the SINGLE best URL from the list below that satisfies the following INTENT.

INTENT: "{intent}"

CANDIDATES:
{candidates_text}

CRITERIA:
1. Prioritize official sources, registries, or primary profiles over aggregators or news mentions.
2. Ignore login pages, help pages, or generic search results.
3. If multiple valid sources exist, choose the most authoritative one.
4. If NO candidate is relevant, respond "NONE".

RESPONSE FORMAT:
Just the index number (e.g. "1") or "NONE". Do not write anything else.
"""
        try:
            # Reuse the existing Watcher model infrastructure
            model_config = await _get_next_model()
            response = await _invoke_model(prompt, model_config, max_tokens=100)
            
            if not response:
                return None
                
            clean_resp = response.strip().replace(".", "")
            if "NONE" in clean_resp.upper():
                return None
                
            # Parse index
            import re
            match = re.search(r'\d+', clean_resp)
            if match:
                idx = int(match.group(0)) - 1
                if 0 <= idx < len(candidates):
                    return candidates[idx]['url']
        except Exception as e:
            logger.error(f"Selection error: {e}")
            
        return None

    async def smart_extract(
        self,
        query: str,
        bang_key: str,
        intent_header: str,
        target_profile: str = "general"
    ) -> Dict[str, Any]:
        """
        Run the full Smart Extract pipeline.
        
        Args:
            query: The search term (e.g., "Siemens AG")
            bang_key: The specific bang ID to use (e.g., "cde")
            intent_header: The 'Watcher Header' describing what we want (e.g., "Official Registration Number")
            target_profile: context hint (company, person, etc.)
            
        Returns:
            Dict containing the extraction result and source metadata.
        """
        logger.info(f"🚀 Starting Smart Extract: {query} [{bang_key}] -> '{intent_header}'")
        
        # --- STEP 1: TARGETED SEARCH ---
        # We need to construct a custom bang dict for just this one key
        # to force auto_bang_search to use exactly what we want.
        target_bangs = {}
        
        # Look up the URL template from our known lists
        # Note: Ideally we'd look up from all_bangs.json, but for now we check the loaded dicts
        # or we accept that auto_bang_search might need a patch to accept a specific custom bang.
        # For this implementation, we'll try to find it in the loaded maps or fallback to a custom search.
        
        template = None
        if bang_key in NEWS_BANGS:
            template = NEWS_BANGS[bang_key]
        elif bang_key in SOCIAL_BANGS:
            template = SOCIAL_BANGS[bang_key]
        else:
            # Fallback for bangs not in the curated constants but potentially in all_bangs.json
            # For MVP, we default to Google Site Search if unknown
            # Real impl would query the full JSON or a DB
            template = f"https://www.google.com/search?q=site:{bang_key} {{q}}"
            
        # Execute Search
        # We use a hacked 'custom_bangs' approach by passing it to scan_bangs internally
        # But auto_bang_search doesn't expose custom_bangs arg yet.
        # We will use the underlying `scan_bangs` function directly from the module imports!
        from modules.brute.auto_bang_search import scan_bangs
        
        # If we found a template, use it. If not, use the key as a google site search for safety.
        search_map = {bang_key: template or f"https://www.google.com/search?q={query} {bang_key}"}
        
        logger.info(f"🔎 Searching via {bang_key}...")
        search_results = await scan_bangs(
            query=query,
            bangs=search_map,
            source_type="smart_bang",
            timeout=10.0
        )
        
        if not search_results:
            return {"status": "failed", "reason": "No search results found"}
            
        logger.info(f"✅ Found {len(search_results)} candidates.")

        # --- STEP 2: SMART SELECTION (AI Watcher) ---
        # Use the specialized AI Selection logic to pick the best URL
        
        candidates = search_results[:5] # Analyze top 5
        
        best_url = await self._select_best_source(
            candidates=candidates,
            intent=intent_header
        )
        
        if best_url:
            # Find the full object
            best_candidate = next((r for r in candidates if r['url'] == best_url), candidates[0])
            logger.info(f"🎯 AI Selected candidate: {best_url}")
        else:
            # Fallback: Just take the first one
            best_candidate = search_results[0]
            logger.info(f"⚠️ No AI match/selection, falling back to #1: {best_candidate['url']}")

        # --- STEP 3: DEEP SCRAPE (Jester Hybrid) ---
        logger.info(f"🕷️ Scraping via JESTER (Go/Hybrid): {best_candidate['url']}")
        
        captured_content = None
        
        # Callback to capture the page content
        def on_page_captured(doc):
            nonlocal captured_content
            captured_content = doc.content
            
        # Parse domain from URL for the crawler
        parsed = urlparse(best_candidate['url'])
        domain = parsed.netloc
        
        # Run Jester with the specific seed URL
        await self.jester.crawl(
            domain=domain,
            seed_urls=[best_candidate['url']],
            on_page=on_page_captured
        )
        
        if not captured_content:
            return {"status": "failed", "reason": "Jester scraping returned no content"}

        logger.info(f"✅ Scraped {len(captured_content)} chars via Jester")

        # --- STEP 4: DEEP EXTRACTION ---
        logger.info(f"🧠 Extracting facts for: '{intent_header}'")
        
        # Run the Watcher Extraction again on the FULL content
        extractions = await check_source_against_watchers(
            source_content=captured_content,
            source_url=best_candidate['url'],
            source_id="scraped_content",
            watchers=[{"id": "intent_1", "label": intent_header}],
            max_concurrent=5
        )
        
        facts = []
        for ext in extractions:
            facts.append({
                "fact": ext.quote,
                "relevance": ext.relevance,
                "source": best_candidate['url']
            })
            
        return {
            "status": "success",
            "bang": bang_key,
            "url": best_candidate['url'],
            "intent": intent_header,
            "facts": facts,
            "snippet": best_candidate.get('snippet'),
            "timestamp": datetime.utcnow().isoformat(),
            "scrape_source": "jester_hybrid"
        }

# Global instance
orchestrator = SmartBangOrchestrator()

async def run_smart_extract(query: str, bang: str, intent: str):
    try:
        return await orchestrator.smart_extract(query, bang, intent)
    finally:
        # connection pooling handled internally, but good practice to have explicit close if needed
        pass