"""
Watcher Extraction Pipeline - MULTI-MODEL PARALLEL EXECUTION

Evaluates sources against watcher headers using multiple LLMs in parallel.
Models: Claude Haiku 4.5, GPT-5-mini, Gemini 2.0 Flash (via Vertex AI)
Batches 2 headers per call for efficiency (falls back to 1 for long sources).

Key optimization: Round-robin model distribution for maximum throughput.
"""

import asyncio
import os
import re
import aiohttp
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from anthropic import AsyncAnthropic, APIError

# Load from project root .env
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Initialize Anthropic client
anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Vertex AI / Google GenAI configuration
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or "trans-411306"
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"

# Initialize Gemini client (Vertex AI - no rate limits)
gemini_client = None
try:
    from google import genai
    gemini_client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    print(f"[WatcherExtraction] Gemini Vertex AI client initialized (project={GCP_PROJECT})")
except Exception as e:
    print(f"[WatcherExtraction] Gemini Vertex AI not available: {e}")

# Model configuration - MULTI-MODEL for parallel execution
# gpt-5-mini for better relevance weighting (nano is for entity extraction)
# Gemini via Vertex AI (no rate limits) with OpenRouter fallback
WATCHER_MODELS = [
    {
        "id": "claude-haiku-4-5-20251001",
        "provider": "anthropic",
        "max_tokens": 800,
    },
    {
        "id": "gpt-5-mini",
        "provider": "openai",
        "max_tokens": 800,
    },
    {
        "id": "gemini-2.0-flash-exp",  # Vertex AI (primary) or OpenRouter (fallback)
        "provider": "vertex",
        "max_tokens": 800,
    },
]

# Fallback for single-model mode
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 800  # Enough for 2 topics
BATCH_SIZE = 2  # Check 2 headers per call
LONG_SOURCE_THRESHOLD = 15000  # Fall back to single header if source > 15k chars
SOURCE_CONTENT_LIMIT = 8000  # Truncate source content to this

# API keys for multi-model execution
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # Fallback for Gemini


@dataclass
class ExtractionResult:
    """Result of checking a source against a watcher header"""
    watcher_id: str
    watcher_header: str
    found: bool
    quote: Optional[str] = None
    relevance: Optional[str] = None
    source_id: Optional[str] = None
    source_url: Optional[str] = None


# Model index for round-robin distribution
_model_index = 0
_model_lock = asyncio.Lock()


async def _get_next_model() -> Dict:
    """Get next model in round-robin fashion"""
    global _model_index
    async with _model_lock:
        model = WATCHER_MODELS[_model_index % len(WATCHER_MODELS)]
        _model_index += 1
        return model


async def _invoke_model(
    prompt: str,
    model_config: Dict,
    max_tokens: int = 400,
) -> Optional[str]:
    """
    Invoke any model via its provider.
    Returns the response text or None on failure.
    """
    provider = model_config["provider"]
    model_id = model_config["id"]

    try:
        if provider == "anthropic":
            response = await anthropic_client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()

        elif provider == "openai":
            # Use OpenAI API directly
            if not OPENAI_API_KEY:
                return None
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                    },
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
            return None

        elif provider == "openrouter":
            return await _invoke_openrouter(prompt, model_id, max_tokens)

        elif provider == "vertex":
            # OpenRouter free tier FIRST, Vertex AI as fallback
            if OPENROUTER_API_KEY:
                try:
                    result = await _invoke_openrouter(prompt, f"google/{model_id}:free", max_tokens)
                    if result:
                        return result
                except Exception as or_err:
                    print(f"[WatcherExtraction] OpenRouter free error: {or_err}, falling back to Vertex AI")

            # Fallback to Vertex AI (no rate limits, but costs GCP credits)
            if gemini_client:
                try:
                    response = await gemini_client.aio.models.generate_content(
                        model=model_id,
                        contents=prompt,
                        config={"max_output_tokens": max_tokens}
                    )
                    return response.text
                except Exception as vertex_err:
                    print(f"[WatcherExtraction] Vertex AI fallback also failed: {vertex_err}")
            return None

    except Exception as e:
        # Silent failure - parallel execution handles partial failures
        return None


async def _invoke_openrouter(prompt: str, model_id: str, max_tokens: int) -> Optional[str]:
    """Invoke model via OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://drill-search.ai",
                    "X-Title": "Drill Search Watcher",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
    except Exception as e:

        print(f"[LINKLATER] Error: {e}")

        pass
    return None


def _parse_single_topic_response(response_text: str, header: str) -> Optional[Dict]:
    """Parse response for a single topic check"""
    text = response_text.strip()

    if text.upper().startswith("NO"):
        return None

    if text.upper().startswith("YES"):
        quote = ""
        relevance = ""

        for line in text.split("\n"):
            line = line.strip()
            if line.upper().startswith("QUOTE:"):
                quote = line[6:].strip().strip('"\'')
            elif line.upper().startswith("RELEVANCE:"):
                relevance = line[10:].strip()

        if quote:
            return {
                "header": header,
                "quote": quote[:500],  # Cap quote length
                "relevance": relevance[:200] if relevance else "",
            }

    return None


def _parse_multi_topic_response(
    response_text: str, headers: List[str]
) -> Dict[str, Optional[Dict]]:
    """Parse response for multiple topics check"""
    results: Dict[str, Optional[Dict]] = {h: None for h in headers}

    # Split by topic sections (--- delimiter)
    sections = re.split(r"-{3,}", response_text)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Find which topic this section is about
        topic_match = re.search(r"TOPIC:\s*(.+?)(?:\n|$)", section, re.IGNORECASE)
        if not topic_match:
            continue

        topic = topic_match.group(1).strip()

        # Find matching header (case-insensitive partial match)
        matched_header = None
        for h in headers:
            if h.lower() in topic.lower() or topic.lower() in h.lower():
                matched_header = h
                break

        if not matched_header:
            continue

        # Check result
        result_match = re.search(r"RESULT:\s*(YES|NO)", section, re.IGNORECASE)
        if not result_match:
            continue

        if result_match.group(1).upper() == "NO":
            results[matched_header] = None
            continue

        # Extract quote
        quote_match = re.search(r"QUOTE:\s*(.+?)(?:\n|$)", section, re.IGNORECASE | re.DOTALL)
        if quote_match:
            quote = quote_match.group(1).strip().strip('"\'')
            results[matched_header] = {
                "header": matched_header,
                "quote": quote[:500],
                "relevance": "",
            }

    return results


async def check_source_against_single_watcher(
    source_content: str,
    source_url: str,
    watcher_header: str,
    semaphore: asyncio.Semaphore,
    model_config: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    Check if source contains information relevant to a single watcher header.
    Uses round-robin model selection for parallel multi-model execution.
    Returns None if no match, or extraction dict if match found.
    """
    async with semaphore:
        prompt = f"""You are evaluating whether a source contains information relevant to a specific topic.

TOPIC: {watcher_header}

SOURCE URL: {source_url}

SOURCE CONTENT:
{source_content[:SOURCE_CONTENT_LIMIT]}

TASK: Is there ANY information in this source directly relevant to "{watcher_header}"?

Respond in EXACTLY this format:
NO

OR:

YES
QUOTE: [exact quote from source, max 300 characters]
RELEVANCE: [1 sentence explaining why this is relevant]

Be strict. Only say YES if there is a direct, specific quote about the topic. Do not include general information that merely mentions related terms."""

        # Get model via round-robin if not specified
        if model_config is None:
            model_config = await _get_next_model()

        text = await _invoke_model(prompt, model_config, max_tokens=400)
        if text:
            return _parse_single_topic_response(text, watcher_header)
        return None


async def check_source_against_watchers_batch(
    source_content: str,
    source_url: str,
    watcher_headers: List[str],
    semaphore: asyncio.Semaphore,
) -> Dict[str, Optional[Dict]]:
    """
    Check source against multiple watcher headers in single call (max 2).
    If source is very long (>15k chars), falls back to single header.
    """
    # If source is very long, check headers one at a time
    if len(source_content) > LONG_SOURCE_THRESHOLD and len(watcher_headers) > 1:
        results: Dict[str, Optional[Dict]] = {}
        for header in watcher_headers:
            result = await check_source_against_single_watcher(
                source_content, source_url, header, semaphore
            )
            results[header] = result
        return results

    # Batch check multiple headers
    async with semaphore:
        headers_list = "\n".join(f"- {h}" for h in watcher_headers)

        prompt = f"""You are evaluating whether a source contains information relevant to specific topics.

TOPICS TO CHECK:
{headers_list}

SOURCE URL: {source_url}

SOURCE CONTENT:
{source_content[:SOURCE_CONTENT_LIMIT]}

TASK: For EACH topic listed above, determine if the source contains directly relevant information.

Respond with one section per topic, separated by "---", in this format:

TOPIC: [topic name]
RESULT: NO
---

OR:

TOPIC: [topic name]
RESULT: YES
QUOTE: [exact quote from source, max 300 characters]
---

Be strict. Only say YES if there is a direct, specific quote about that topic. General mentions don't count."""

        # Get model via round-robin
        model_config = await _get_next_model()
        text = await _invoke_model(prompt, model_config, max_tokens=MAX_TOKENS)

        if text:
            return _parse_multi_topic_response(text, watcher_headers)
        else:
            # Return empty results on error
            return {h: None for h in watcher_headers}


async def check_source_against_watchers(
    source_content: str,
    source_url: str,
    source_id: str,
    watchers: List[Dict],  # List of {id, label} dicts
    max_concurrent: int = 100,  # HIGH CONCURRENCY: 3 models × 33 parallel calls each
) -> List[ExtractionResult]:
    """
    Check a single source against all watchers.
    Batches 2 watcher headers per Haiku call for efficiency.

    Args:
        source_content: Full text content of the source
        source_url: URL of the source
        source_id: Node ID of the source
        watchers: List of watcher dicts with 'id' and 'label' keys
        max_concurrent: Max concurrent Haiku calls

    Returns:
        List of ExtractionResult objects (only for positive matches)
    """
    if not watchers or not source_content:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)
    results: List[ExtractionResult] = []

    # Build header -> watcher_id mapping
    header_to_watcher: Dict[str, str] = {w["label"]: w["id"] for w in watchers}
    headers = list(header_to_watcher.keys())

    # Process headers in batches of 2
    tasks = []
    batches = []

    for i in range(0, len(headers), BATCH_SIZE):
        batch = headers[i : i + BATCH_SIZE]
        batches.append(batch)
        task = check_source_against_watchers_batch(
            source_content, source_url, batch, semaphore
        )
        tasks.append(task)

    # Run all batch checks
    batch_results = await asyncio.gather(*tasks)

    # Collect positive results
    for i, batch_result in enumerate(batch_results):
        for header, extraction in batch_result.items():
            if extraction:
                watcher_id = header_to_watcher[header]
                results.append(
                    ExtractionResult(
                        watcher_id=watcher_id,
                        watcher_header=header,
                        found=True,
                        quote=extraction["quote"],
                        relevance=extraction.get("relevance"),
                        source_id=source_id,
                        source_url=source_url,
                    )
                )

    return results


async def process_watchers_batch(
    watchers: List[Dict],  # List of {id, label} dicts
    sources: List[Dict],   # List of {id, url, content} dicts
    max_concurrent: int = 100,  # HIGH CONCURRENCY: 3 models × 33 parallel calls each
) -> Dict[str, List[ExtractionResult]]:
    """
    Process all watchers against all sources.
    Returns dict mapping watcher_id -> list of extraction results.

    Args:
        watchers: List of watcher dicts with 'id' and 'label'
        sources: List of source dicts with 'id', 'url', 'content'
        max_concurrent: Max concurrent Haiku calls

    Returns:
        Dict mapping watcher_id to list of ExtractionResult objects
    """
    all_results: Dict[str, List[ExtractionResult]] = {w["id"]: [] for w in watchers}

    for source in sources:
        source_results = await check_source_against_watchers(
            source_content=source.get("content", ""),
            source_url=source.get("url", ""),
            source_id=source["id"],
            watchers=watchers,
            max_concurrent=max_concurrent,
        )

        for result in source_results:
            all_results[result.watcher_id].append(result)

    return all_results


# ========== CLI for testing ==========

if __name__ == "__main__":
    import sys

    async def test():
        test_content = """
        John Smith was appointed CEO of Acme Corp in January 2019.
        The company has operations in London and New York.
        Revenue increased by 15% year over year.
        """

        test_watchers = [
            {"id": "w1", "label": "Corporate Officers"},
            {"id": "w2", "label": "Financial Performance"},
            {"id": "w3", "label": "Legal Issues"},  # Should not match
        ]

        results = await check_source_against_watchers(
            source_content=test_content,
            source_url="https://example.com/article",
            source_id="src_123",
            watchers=test_watchers,
        )

        print(f"\nFound {len(results)} matches:")
        for r in results:
            print(f"  - {r.watcher_header}: '{r.quote[:50]}...'")

    asyncio.run(test())
