#!/usr/bin/env python3
"""
YaCy ↔ Elasticsearch Bidirectional Sync

Architecture:
- Elasticsearch = Permanent store (onion-pages index)
- YaCy = Transient P2P sharing layer

Two directions:
1. HARVEST: Pull new onion discoveries from YaCy peers → ES
2. EXPORT: Push new ES documents → YaCy (for P2P sharing)

Extraction (lightweight, no embeddings):
- Regex-based entity extraction (emails, phones, persons, companies)
- TF-based keyword extraction (top terms)
- Snippet + metadata only (no full content ingestion)

Run periodically (e.g., every hour) to:
- Discover new onion pages from the YaCy Tor network
- Share your new discoveries with the network
"""

import os
import re
import json
import asyncio
import hashlib
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse
import aiohttp
from elasticsearch import AsyncElasticsearch

# Configuration
YACY_URL = os.getenv("YACY_TOR_URL", "http://localhost:8091")
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
ONION_INDEX = "onion-pages"

# Search terms to discover new onion content
DISCOVERY_QUERIES = [
    "market", "forum", "bitcoin", "service", "shop", "news",
    "blog", "wiki", "search", "directory", "hidden", "anonymous"
]

# =============================================================================
# LIGHTWEIGHT EXTRACTION (regex + keyword matching, NO EMBEDDINGS)
# =============================================================================

# Golden lists path
GOLDEN_LISTS_PATH = "/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output/matrix/golden_lists_with_embeddings.json"
RED_FLAG_ENTITIES_PATH = "/Users/attic/01. DRILL_SEARCH/drill-search-app/input_output/matrix/red_flag_entities.json"

# Cached golden lists (keyword-only, no embeddings)
_golden_keywords = None
_red_flag_lookup = None


def load_golden_keywords():
    """Load golden lists for keyword matching (no embeddings)."""
    global _golden_keywords
    if _golden_keywords is not None:
        return _golden_keywords

    _golden_keywords = {"themes": {}, "phenomena": {}, "red_flags": {}, "methodologies": {}}

    try:
        with open(GOLDEN_LISTS_PATH) as f:
            data = json.load(f)

        for cat_type in ["themes", "phenomena", "red_flags", "methodologies"]:
            categories = data.get(cat_type, {}).get("categories", [])
            for cat in categories:
                cat_id = cat.get("id", "")
                canonical = cat.get("canonical", "")
                variations = cat.get("variations", [])

                # Build keyword set for matching (lowercase)
                keywords = set()
                keywords.add(canonical.lower())
                for v in variations[:50]:  # Cap variations
                    keywords.add(v.lower())

                _golden_keywords[cat_type][cat_id] = {
                    "canonical": canonical,
                    "keywords": keywords
                }

        print(f"[Extract] Loaded golden lists: {len(_golden_keywords['themes'])} themes, "
              f"{len(_golden_keywords['phenomena'])} phenomena, "
              f"{len(_golden_keywords['red_flags'])} red_flags, "
              f"{len(_golden_keywords['methodologies'])} methodologies")

    except FileNotFoundError:
        print(f"[Extract] Golden lists not found at {GOLDEN_LISTS_PATH}")
    except Exception as e:
        print(f"[Extract] Error loading golden lists: {e}")

    return _golden_keywords


def load_red_flag_entities():
    """Load red flag entity lookup (OFAC SDN, sanctions)."""
    global _red_flag_lookup
    if _red_flag_lookup is not None:
        return _red_flag_lookup

    _red_flag_lookup = {}

    try:
        with open(RED_FLAG_ENTITIES_PATH) as f:
            data = json.load(f)

        for list_name, list_data in data.get("lists", {}).items():
            for entity in list_data.get("entities", []):
                names = [entity["name"].lower()] + [a.lower() for a in entity.get("aliases", [])]
                for name in names:
                    if len(name) > 3:  # Skip very short names
                        _red_flag_lookup[name] = {
                            "name": entity["name"],
                            "type": entity.get("type"),
                            "list": list_name,
                            "severity": list_data.get("severity", "high")
                        }

        print(f"[Extract] Loaded {len(_red_flag_lookup)} red flag entity names/aliases")

    except FileNotFoundError:
        print(f"[Extract] Red flag entities not found at {RED_FLAG_ENTITIES_PATH}")
    except Exception as e:
        print(f"[Extract] Error loading red flag entities: {e}")

    return _red_flag_lookup


def extract_themes_keywords(text: str, top_n: int = 5) -> List[Dict]:
    """Extract themes using keyword matching (no embeddings)."""
    golden = load_golden_keywords()
    text_lower = text.lower()
    matches = []

    for cat_id, cat_data in golden.get("themes", {}).items():
        score = 0
        matched_keywords = []
        for kw in cat_data["keywords"]:
            if len(kw) > 3 and kw in text_lower:
                score += 1
                matched_keywords.append(kw)

        if score > 0:
            matches.append({
                "id": cat_id,
                "canonical": cat_data["canonical"],
                "score": min(score / 3, 1.0),  # Normalize
                "matched": matched_keywords[:3]
            })

    return sorted(matches, key=lambda x: -x["score"])[:top_n]


def extract_phenomena_keywords(text: str, top_n: int = 5) -> List[Dict]:
    """Extract phenomena (events/report types) using keyword matching."""
    golden = load_golden_keywords()
    text_lower = text.lower()
    matches = []

    for cat_id, cat_data in golden.get("phenomena", {}).items():
        score = 0
        matched_keywords = []
        for kw in cat_data["keywords"]:
            if len(kw) > 3 and kw in text_lower:
                score += 1
                matched_keywords.append(kw)

        if score > 0:
            matches.append({
                "id": cat_id,
                "canonical": cat_data["canonical"],
                "score": min(score / 3, 1.0),
                "matched": matched_keywords[:3]
            })

    return sorted(matches, key=lambda x: -x["score"])[:top_n]


def extract_red_flag_themes_keywords(text: str, top_n: int = 5) -> List[Dict]:
    """Extract red flag themes using keyword matching."""
    golden = load_golden_keywords()
    text_lower = text.lower()
    matches = []

    for cat_id, cat_data in golden.get("red_flags", {}).items():
        score = 0
        matched_keywords = []
        for kw in cat_data["keywords"]:
            if len(kw) > 3 and kw in text_lower:
                score += 1
                matched_keywords.append(kw)

        if score > 0:
            matches.append({
                "id": cat_id,
                "canonical": cat_data["canonical"],
                "score": min(score / 2, 1.0),  # Red flags score faster
                "matched": matched_keywords[:3]
            })

    return sorted(matches, key=lambda x: -x["score"])[:top_n]


def extract_red_flag_entities(text: str) -> List[Dict]:
    """Detect sanctioned/red-flag entities in text."""
    lookup = load_red_flag_entities()
    if not lookup:
        return []

    text_lower = text.lower()
    matches = []
    seen = set()

    for name, info in lookup.items():
        if name in text_lower and name not in seen:
            # Verify word boundary
            pattern = r'\b' + re.escape(name) + r'\b'
            if re.search(pattern, text_lower):
                matches.append({
                    "name": info["name"],
                    "matched_as": name,
                    "type": info["type"],
                    "list": info["list"],
                    "severity": info["severity"]
                })
                seen.add(name)

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(matches, key=lambda x: severity_order.get(x["severity"], 99))


def extract_temporal(text: str) -> Dict[str, Any]:
    """Extract temporal signals (years, time focus)."""
    result = {"content_years": [], "temporal_focus": None, "date_mentions": []}

    # Extract years
    year_pattern = r'\b(19[5-9]\d|20[0-4]\d)\b'
    years = sorted(set(int(y) for y in re.findall(year_pattern, text)))
    result["content_years"] = years

    if years:
        from datetime import datetime
        current_year = datetime.now().year
        avg_year = sum(years) / len(years)
        if avg_year < current_year - 5:
            result["temporal_focus"] = "historical"
        elif avg_year > current_year:
            result["temporal_focus"] = "future"
        else:
            result["temporal_focus"] = "current"

    # Date patterns
    date_patterns = [
        r'\b(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}\b',
    ]
    for pattern in date_patterns:
        for match in re.findall(pattern, text, re.IGNORECASE)[:5]:
            result["date_mentions"].append(str(match))

    return result


def extract_spatial(text: str) -> Dict[str, Any]:
    """Extract spatial/location signals."""
    result = {"jurisdictions": [], "primary_jurisdiction": None}

    country_patterns = {
        "US": r'\b(United States|USA|U\.S\.|America|American)\b',
        "UK": r'\b(United Kingdom|UK|U\.K\.|Britain|British|England)\b',
        "DE": r'\b(Germany|German|Deutschland)\b',
        "FR": r'\b(France|French)\b',
        "CN": r'\b(China|Chinese|Beijing|Shanghai|PRC)\b',
        "RU": r'\b(Russia|Russian|Moscow|Kremlin)\b',
        "CH": r'\b(Switzerland|Swiss|Zurich|Geneva)\b',
        "AE": r'\b(UAE|Dubai|Abu Dhabi|Emirates)\b',
        "SG": r'\b(Singapore)\b',
        "HK": r'\b(Hong Kong)\b',
        "CY": r'\b(Cyprus|Cypriot)\b',
        "BVI": r'\b(British Virgin Islands|BVI)\b',
        "PA": r'\b(Panama|Panamanian)\b',
    }

    counts = {}
    for code, pattern in country_patterns.items():
        matches = len(re.findall(pattern, text, re.IGNORECASE))
        if matches > 0:
            counts[code] = matches
            result["jurisdictions"].append({"code": code, "mentions": matches})

    if counts:
        result["primary_jurisdiction"] = max(counts.items(), key=lambda x: x[1])[0]

    return result


def extract_full_lightweight(text: str, url: str = "") -> Dict[str, Any]:
    """
    Full extraction using keyword matching (NO EMBEDDINGS).

    Extracts:
    - Entities (emails, phones, persons, companies, crypto)
    - Themes (51 industry/sector categories)
    - Phenomena (60 event/report types)
    - Red flag themes (11 risk categories)
    - Red flag entities (OFAC SDN, sanctions)
    - Temporal (years, time focus)
    - Spatial (jurisdictions)
    - Keywords (top terms)
    """
    result = {
        "entities": extract_entities_lightweight(text, url),
        "themes": extract_themes_keywords(text),
        "phenomena": extract_phenomena_keywords(text),
        "red_flag_themes": extract_red_flag_themes_keywords(text),
        "red_flag_entities": extract_red_flag_entities(text),
        "temporal": extract_temporal(text),
        "spatial": extract_spatial(text),
        "keywords": extract_keywords(text, top_n=10),
    }

    # Alert flag
    result["has_red_flag"] = len(result["red_flag_entities"]) > 0 or len(result["red_flag_themes"]) > 0

    return result


# Entity patterns (from cc-pdf patterns)
EMAIL_PATTERN = re.compile(r'[\w.-]+@[\w.-]+\.\w+', re.IGNORECASE)
PHONE_PATTERNS = [
    re.compile(r'\+1[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}'),
    re.compile(r'\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}'),
    re.compile(r'\+\d{1,3}[\s\-\.]?\d{2,4}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}'),
]
PERSON_PATTERNS = [
    re.compile(r'(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', re.IGNORECASE),
    re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*,\s*(?:CEO|CFO|CTO|COO|Founder|Director|Manager)', re.IGNORECASE),
    re.compile(r'(?:by|author|contact)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)', re.IGNORECASE),
]
COMPANY_PATTERNS = [
    re.compile(r'([A-Z][A-Za-z\s&]+(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|Company|Group|Holdings))', re.IGNORECASE),
    re.compile(r'©\s*\d{4}\s*([A-Z][A-Za-z\s&]+)'),
]

# Bitcoin address patterns (common on .onion)
BITCOIN_PATTERN = re.compile(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b')
MONERO_PATTERN = re.compile(r'\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b')

# Stopwords for keyword extraction
STOPWORDS = {
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for',
    'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his',
    'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my',
    'one', 'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if',
    'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can', 'like',
    'time', 'no', 'just', 'him', 'know', 'take', 'people', 'into', 'year',
    'your', 'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then',
    'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also', 'back',
    'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well', 'way', 'even',
    'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us', 'is',
    'are', 'was', 'were', 'been', 'has', 'had', 'may', 'more', 'very', 'www',
    'http', 'https', 'com', 'org', 'net', 'onion', 'html', 'php', 'page', 'home',
}


def extract_entities_lightweight(text: str, url: str = "") -> Dict[str, List[str]]:
    """
    Extract entities using regex patterns only (no AI, no embeddings).

    Returns dict with: emails, phones, persons, companies, crypto_addresses
    """
    entities = {
        "emails": [],
        "phones": [],
        "persons": [],
        "companies": [],
        "crypto_addresses": [],
    }

    seen = set()

    # Emails
    for match in EMAIL_PATTERN.findall(text):
        email = match.lower()
        if email not in seen and not email.endswith('.onion'):
            seen.add(email)
            entities["emails"].append(email)

    # Phones
    for pattern in PHONE_PATTERNS:
        for match in pattern.findall(text):
            cleaned = re.sub(r'[^\d+]', '', match)
            if len(cleaned) >= 10 and cleaned not in seen:
                seen.add(cleaned)
                entities["phones"].append(match.strip())

    # Persons
    for pattern in PERSON_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1).strip() if match.lastindex else match.group().strip()
            if len(name) > 3 and ' ' in name and name.lower() not in seen:
                seen.add(name.lower())
                entities["persons"].append(name)

    # Companies
    for pattern in COMPANY_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1).strip() if match.lastindex else match.group().strip()
            if len(name) > 3 and name.lower() not in seen:
                seen.add(name.lower())
                entities["companies"].append(name)

    # Crypto addresses (Bitcoin, Monero)
    for match in BITCOIN_PATTERN.findall(text):
        if match not in seen:
            seen.add(match)
            entities["crypto_addresses"].append({"type": "bitcoin", "address": match})
    for match in MONERO_PATTERN.findall(text):
        if match not in seen:
            seen.add(match)
            entities["crypto_addresses"].append({"type": "monero", "address": match})

    return entities


def extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """
    Extract top keywords using simple term frequency (no embeddings).
    """
    # Tokenize and clean
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

    # Filter stopwords and short terms
    words = [w for w in words if w not in STOPWORDS and len(w) > 3]

    # Count and return top N
    counter = Counter(words)
    return [word for word, _ in counter.most_common(top_n)]


def extract_meta(title: str, content: str, url: str) -> Dict[str, Any]:
    """
    Extract metadata and create snippet.
    """
    domain = urlparse(url).netloc if url else ""

    # Create snippet (first 500 chars, cleaned)
    snippet = content[:500].strip() if content else ""
    snippet = re.sub(r'\s+', ' ', snippet)

    # Detect content type hints from title/content
    content_lower = (title + " " + content).lower()
    content_hints = []

    hint_patterns = {
        "marketplace": ["market", "shop", "buy", "sell", "vendor", "listing"],
        "forum": ["forum", "board", "discussion", "thread", "post", "reply"],
        "wiki": ["wiki", "encyclopedia", "article", "edit"],
        "blog": ["blog", "post", "article", "author"],
        "service": ["service", "provider", "hosting", "escrow"],
        "crypto": ["bitcoin", "btc", "monero", "xmr", "crypto", "wallet"],
        "news": ["news", "breaking", "headline", "update"],
    }

    for hint_type, keywords in hint_patterns.items():
        if any(kw in content_lower for kw in keywords):
            content_hints.append(hint_type)

    return {
        "domain": domain,
        "snippet": snippet,
        "title_length": len(title) if title else 0,
        "content_length": len(content) if content else 0,
        "content_hints": content_hints[:3],  # Top 3 hints
    }


async def check_yacy_available() -> bool:
    """Check if YaCy is reachable."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{YACY_URL}/Status.html", timeout=10) as resp:
                return resp.status == 200
    except Exception:
        return False


async def check_es_available() -> bool:
    """Check if Elasticsearch is reachable."""
    try:
        es = AsyncElasticsearch([ES_HOST], request_timeout=10)
        try:
            await es.info()
            return True
        finally:
            await es.close()
    except Exception:
        return False


async def get_es_indexed_urls() -> Set[str]:
    """Get all URLs already indexed in ES to avoid re-processing."""
    urls = set()
    if not await check_es_available():
        return urls

    es = AsyncElasticsearch([ES_HOST], request_timeout=30)
    try:
        # Scroll through all docs to get URLs
        result = await es.search(
            index=ONION_INDEX,
            body={"query": {"match_all": {}}, "_source": ["url"], "size": 10000}
        )
        for hit in result["hits"]["hits"]:
            urls.add(hit["_source"].get("url", ""))
    except Exception as e:
        print(f"[ES] Error fetching indexed URLs: {e}")
    finally:
        await es.close()

    return urls


async def harvest_full_index(max_pages: int = 1000) -> List[Dict[str, Any]]:
    """
    Harvest ALL onion pages from YaCy index using wildcard query with pagination.
    Much more comprehensive than keyword-based discovery.
    """
    harvested = []

    if not await check_yacy_available():
        print(f"[Harvest] YaCy not available at {YACY_URL}")
        return harvested

    # Get already indexed URLs from ES
    print("[Harvest] Fetching already-indexed URLs from ES...")
    seen_urls = await get_es_indexed_urls()
    print(f"[Harvest] {len(seen_urls)} URLs already in ES")

    async with aiohttp.ClientSession() as session:
        offset = 0
        batch_size = 100

        while offset < max_pages:
            try:
                # Wildcard query with pagination
                params = {
                    "query": "*",
                    "resource": "local",  # Our index first
                    "count": batch_size,
                    "startRecord": offset,
                    "urlmaskfilter": ".*\\.onion.*"
                }

                async with session.get(f"{YACY_URL}/yacysearch.json", params=params, timeout=60) as resp:
                    if resp.status != 200:
                        break

                    try:
                        data = await resp.json()
                    except Exception as je:
                        print(f"[Harvest] JSON parse error at offset {offset}, skipping batch")
                        offset += batch_size
                        continue
                    items = data.get("channels", [{}])[0].get("items", [])

                    if not items:
                        break  # No more results

                    new_count = 0
                    for item in items:
                        item_url = item.get("link", "")
                        if not item_url or ".onion" not in item_url:
                            continue
                        if item_url in seen_urls:
                            continue

                        seen_urls.add(item_url)
                        new_count += 1

                        title = item.get("title", "")
                        content = item.get("description", "")
                        combined_text = f"{title} {content}"

                        extraction = extract_full_lightweight(combined_text, item_url)
                        meta = extract_meta(title, content, item_url)

                        doc = {
                            "url": item_url,
                            "title": title,
                            "snippet": meta["snippet"],
                            "domain": meta["domain"],
                            "content_hints": meta["content_hints"],
                            "keywords": extraction["keywords"],
                            "entities": extraction["entities"],
                            "themes": extraction["themes"],
                            "phenomena": extraction["phenomena"],
                            "red_flag_themes": extraction["red_flag_themes"],
                            "red_flag_entities": extraction["red_flag_entities"],
                            "temporal": extraction["temporal"],
                            "spatial": extraction["spatial"],
                            "has_red_flag": extraction["has_red_flag"],
                            "source": "yacy_full_index",
                            "harvested_at": datetime.now(timezone.utc).isoformat(),
                        }
                        harvested.append(doc)

                    print(f"[Harvest] Offset {offset}: {len(items)} items, {new_count} new")
                    offset += batch_size

                    if new_count == 0 and offset > 500:
                        # No new items and we've checked a lot - stop
                        break

                    await asyncio.sleep(0.5)

            except Exception as e:
                print(f"[Harvest] Error at offset {offset}: {e}")
                break

    return harvested


async def harvest_from_yacy(
    max_per_query: int = 100,
    seen_urls: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Harvest new onion pages from YaCy peer network searches.

    Searches for common terms and extracts .onion URLs from results,
    including results from remote YaCy peers.
    """
    if seen_urls is None:
        seen_urls = set()

    harvested = []

    # Check YaCy availability first
    if not await check_yacy_available():
        print(f"[Harvest] YaCy not available at {YACY_URL} - skipping harvest")
        return harvested

    async with aiohttp.ClientSession() as session:
        for query in DISCOVERY_QUERIES:
            try:
                # Search YaCy with global resource (includes remote peers)
                url = f"{YACY_URL}/yacysearch.json"
                params = {
                    "query": query,
                    "resource": "global",  # Include remote peer results
                    "count": max_per_query,
                    "urlmaskfilter": ".*\\.onion.*"  # Only .onion URLs
                }

                async with session.get(url, params=params, timeout=60) as resp:
                    if resp.status != 200:
                        continue

                    data = await resp.json()
                    channels = data.get("channels", [])

                    for channel in channels:
                        items = channel.get("items", [])
                        for item in items:
                            item_url = item.get("link", "")

                            # Skip if already seen or not .onion
                            if not item_url or ".onion" not in item_url:
                                continue
                            if item_url in seen_urls:
                                continue

                            seen_urls.add(item_url)

                            title = item.get("title", "")
                            content = item.get("description", "")
                            combined_text = f"{title} {content}"

                            # Full lightweight extraction (themes, phenomena, red flags, temporal, spatial)
                            extraction = extract_full_lightweight(combined_text, item_url)
                            meta = extract_meta(title, content, item_url)

                            # Build document with full extraction
                            doc = {
                                "url": item_url,
                                "title": title,
                                "snippet": meta["snippet"],
                                "domain": meta["domain"],
                                "content_hints": meta["content_hints"],
                                # Full extraction fields
                                "keywords": extraction["keywords"],
                                "entities": extraction["entities"],
                                "themes": extraction["themes"],
                                "phenomena": extraction["phenomena"],
                                "red_flag_themes": extraction["red_flag_themes"],
                                "red_flag_entities": extraction["red_flag_entities"],
                                "temporal": extraction["temporal"],
                                "spatial": extraction["spatial"],
                                "has_red_flag": extraction["has_red_flag"],
                                # Source metadata
                                "source": "yacy_harvest",
                                "harvested_at": datetime.now(timezone.utc).isoformat(),
                                "yacy_query": query,
                            }
                            harvested.append(doc)

                # Small delay between queries
                await asyncio.sleep(1)

            except Exception as e:
                print(f"[Harvest] Error querying '{query}': {e}")
                continue

    return harvested


async def push_to_elasticsearch(docs: List[Dict[str, Any]]) -> Dict[str, int]:
    """Push harvested documents to Elasticsearch."""
    stats = {"indexed": 0, "skipped": 0, "errors": 0}

    if not docs:
        return stats

    # Check ES availability first
    if not await check_es_available():
        print(f"[ES] Elasticsearch not available at {ES_HOST} - skipping push")
        stats["errors"] = len(docs)
        return stats

    es = AsyncElasticsearch([ES_HOST], request_timeout=30)

    try:
        for doc in docs:
            try:
                # Generate document ID from URL
                doc_id = hashlib.md5(doc["url"].encode()).hexdigest()

                # Check if already exists
                exists = await es.exists(index=ONION_INDEX, id=doc_id)
                if exists:
                    stats["skipped"] += 1
                    continue

                # Index new document
                await es.index(index=ONION_INDEX, id=doc_id, body=doc)
                stats["indexed"] += 1

            except Exception as e:
                stats["errors"] += 1

    except Exception as e:
        print(f"[ES] Connection error during push: {e}")
    finally:
        await es.close()

    return stats


async def get_new_es_documents(since_hours: int = 24) -> List[Dict[str, Any]]:
    """Get documents from ES that haven't been exported to YaCy yet."""
    docs = []

    # Check ES availability first
    if not await check_es_available():
        print(f"[ES] Elasticsearch not available at {ES_HOST} - skipping export fetch")
        return docs

    es = AsyncElasticsearch([ES_HOST], request_timeout=30)

    try:
        # Check if index exists
        if not await es.indices.exists(index=ONION_INDEX):
            print(f"[ES] Index '{ONION_INDEX}' doesn't exist yet - skipping export")
            return docs

        # Query for documents not yet exported or recently added
        query = {
            "bool": {
                "must": [
                    {"exists": {"field": "url"}}
                ],
                "should": [
                    {"bool": {"must_not": {"exists": {"field": "yacy_exported"}}}},
                    {"range": {"fetched_at": {"gte": f"now-{since_hours}h"}}}
                ],
                "minimum_should_match": 1
            }
        }

        result = await es.search(
            index=ONION_INDEX,
            body={"query": query, "size": 500}
        )

        for hit in result["hits"]["hits"]:
            docs.append({"_id": hit["_id"], **hit["_source"]})

    except Exception as e:
        print(f"[ES] Error fetching documents for export: {e}")
    finally:
        await es.close()

    return docs


async def export_to_yacy_surrogates(
    docs: List[Dict[str, Any]],
    output_dir: str = "/Users/attic/Applications/YaCy/yacy_tor/DATA/SURROGATES/in"
) -> int:
    """
    Export ES documents to YaCy surrogate format.
    Uses the existing OAI-PMH exporter logic.
    """
    if not docs:
        return 0

    try:
        from yacy_oaipmh_exporter import doc_to_oaipmh_record, create_oaipmh_file
    except ImportError:
        print("[Export] yacy_oaipmh_exporter not available - skipping export")
        return 0

    records = []
    for doc in docs:
        try:
            record = doc_to_oaipmh_record(doc, doc.get("_id", "unknown"))
            if record:
                records.append(record)
        except Exception as e:
            print(f"[Export] Error creating record: {e}")
            continue

    if records:
        try:
            filepath = create_oaipmh_file(
                records,
                f"es_sync_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                output_dir
            )
            print(f"[Export] Created: {filepath} ({len(records)} docs)")
        except Exception as e:
            print(f"[Export] Error creating OAI-PMH file: {e}")
            return 0

        # Mark as exported in ES
        if await check_es_available():
            es = AsyncElasticsearch([ES_HOST], request_timeout=30)
            try:
                for doc in docs[:len(records)]:
                    try:
                        await es.update(
                            index=ONION_INDEX,
                            id=doc["_id"],
                            body={"doc": {"yacy_exported": datetime.now(timezone.utc).isoformat()}}
                        )
                    except Exception:
                        pass  # Non-critical - doc will be re-exported next time
            finally:
                await es.close()

    return len(records)


async def sync_bidirectional():
    """
    Run full bidirectional sync:
    1. Harvest from YaCy peers → ES
    2. Export new ES docs → YaCy
    """
    print(f"\n{'='*60}")
    print(f"[Sync] Starting bidirectional sync at {datetime.now()}")
    print(f"{'='*60}")

    # Status check
    yacy_ok = await check_yacy_available()
    es_ok = await check_es_available()
    print(f"[Status] YaCy ({YACY_URL}): {'OK' if yacy_ok else 'UNAVAILABLE'}")
    print(f"[Status] Elasticsearch ({ES_HOST}): {'OK' if es_ok else 'UNAVAILABLE'}")

    if not yacy_ok and not es_ok:
        print("[Sync] Both services unavailable - skipping sync")
        return

    # 1. HARVEST: YaCy peers → Elasticsearch
    print("\n[1/2] HARVESTING from YaCy Tor network (full index scan)...")
    harvested = await harvest_full_index(max_pages=5000)
    print(f"[Harvest] Found {len(harvested)} new onion URLs")

    if harvested:
        # Count extracted data
        total_entities = sum(
            len(d.get("entities", {}).get("emails", [])) +
            len(d.get("entities", {}).get("phones", [])) +
            len(d.get("entities", {}).get("persons", [])) +
            len(d.get("entities", {}).get("companies", [])) +
            len(d.get("entities", {}).get("crypto_addresses", []))
            for d in harvested
        )
        total_themes = sum(len(d.get("themes", [])) for d in harvested)
        total_phenomena = sum(len(d.get("phenomena", [])) for d in harvested)
        total_red_flags = sum(len(d.get("red_flag_themes", [])) + len(d.get("red_flag_entities", [])) for d in harvested)
        docs_with_flags = sum(1 for d in harvested if d.get("has_red_flag"))
        print(f"[Extract] Extracted (no embeddings):")
        print(f"  - Entities: {total_entities}")
        print(f"  - Themes: {total_themes}, Phenomena: {total_phenomena}")
        print(f"  - Red flags: {total_red_flags} ({docs_with_flags} docs flagged)")

        stats = await push_to_elasticsearch(harvested)
        print(f"[Harvest] Indexed: {stats['indexed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")

    # 2. EXPORT: Elasticsearch → YaCy
    print("\n[2/2] EXPORTING new ES docs to YaCy...")
    new_docs = await get_new_es_documents(since_hours=24)
    print(f"[Export] Found {len(new_docs)} documents to export")

    if new_docs:
        exported = await export_to_yacy_surrogates(new_docs)
        print(f"[Export] Exported {exported} documents to YaCy surrogates")

    print(f"\n{'='*60}")
    print(f"[Sync] Complete!")
    print(f"{'='*60}\n")


async def main():
    """Run sync once or continuously."""
    import argparse
    parser = argparse.ArgumentParser(description="YaCy ↔ ES Bidirectional Sync")
    parser.add_argument("--continuous", "-c", action="store_true",
                        help="Run continuously (every hour)")
    parser.add_argument("--harvest-only", action="store_true",
                        help="Only harvest from YaCy, don't export")
    parser.add_argument("--export-only", action="store_true",
                        help="Only export to YaCy, don't harvest")
    args = parser.parse_args()

    if args.continuous:
        while True:
            await sync_bidirectional()
            print("[Sync] Sleeping for 1 hour...")
            await asyncio.sleep(3600)
    else:
        await sync_bidirectional()


if __name__ == "__main__":
    asyncio.run(main())
