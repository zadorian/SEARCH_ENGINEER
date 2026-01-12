#!/usr/bin/env python3
"""
Add outlinks to all existing submarine-scrapes docs.
Extracts links from already-scraped HTML.
"""

import re
import json
import time
import requests
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-scrapes"
BATCH_SIZE = 500
WORKERS = 20


def extract_outlinks(html: str, base_url: str):
    """Extract links from HTML."""
    if not html or not base_url:
        return [], []

    try:
        base_domain = urlparse(base_url).netloc.lower().replace("www.", "")
    except:
        return [], []

    pattern = re.compile(r'<a[^>]+href=["\']([^"\'<>]+)["\'](?:[^>]*>([^<]*)</a)?', re.IGNORECASE)

    all_links = []
    external_links = []
    seen = set()

    for match in pattern.finditer(html[:500000]):  # Limit scan
        href = match.group(1).strip()
        text = (match.group(2) or "").strip()[:200]

        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        try:
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            target_domain = parsed.netloc.lower().replace("www.", "")
        except:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        is_external = target_domain != base_domain
        link = {"url": full_url, "text": text, "domain": target_domain, "is_external": is_external}

        all_links.append(link)
        if is_external:
            external_links.append(link)

        if len(all_links) >= 100:
            break

    return all_links, external_links


def process_batch(docs):
    """Process a batch of docs and return bulk update actions."""
    actions = []
    stats = {"processed": 0, "with_links": 0, "external": 0}

    for doc in docs:
        doc_id = doc["_id"]
        source = doc["_source"]
        html = source.get("html", "")
        url = source.get("url", "")

        all_links, external = extract_outlinks(html, url)

        actions.append(json.dumps({"update": {"_id": doc_id, "_index": ES_INDEX}}))
        actions.append(json.dumps({"doc": {"outlinks": all_links, "outlinks_external": external}}))

        stats["processed"] += 1
        if all_links:
            stats["with_links"] += 1
        if external:
            stats["external"] += 1

    return actions, stats


def bulk_update(actions):
    """Execute bulk update."""
    if not actions:
        return True

    body = "\n".join(actions) + "\n"
    resp = requests.post(
        f"{ES_HOST}/_bulk",
        data=body,
        headers={"Content-Type": "application/x-ndjson"}
    )
    return resp.status_code == 200


def main():
    print("=" * 60)
    print("OUTLINKS EXTRACTOR - Adding links to all docs")
    print("=" * 60)

    # Update mapping first
    mapping = {
        "properties": {
            "outlinks": {"type": "nested", "properties": {
                "url": {"type": "keyword"},
                "text": {"type": "text"},
                "domain": {"type": "keyword"},
                "is_external": {"type": "boolean"},
            }},
            "outlinks_external": {"type": "nested", "properties": {
                "url": {"type": "keyword"},
                "text": {"type": "text"},
                "domain": {"type": "keyword"},
                "is_external": {"type": "boolean"},
            }},
        }
    }
    resp = requests.put(f"{ES_HOST}/{ES_INDEX}/_mapping", json=mapping)
    print(f"Mapping update: {resp.status_code}")

    # Get total count
    resp = requests.get(f"{ES_HOST}/{ES_INDEX}/_count")
    total = resp.json().get("count", 0)
    print(f"Total docs: {total:,}")

    # Scroll through all docs
    query = {
        "_source": ["url", "html"],
        "size": BATCH_SIZE,
        "query": {"match_all": {}}
    }

    resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_search?scroll=10m", json=query)
    data = resp.json()
    scroll_id = data.get("_scroll_id")
    docs = data.get("hits", {}).get("hits", [])

    processed = 0
    total_with_links = 0
    total_external = 0
    start = time.time()

    while docs:
        # Process batch
        actions, stats = process_batch(docs)

        # Bulk update
        if actions:
            bulk_update(actions)

        processed += stats["processed"]
        total_with_links += stats["with_links"]
        total_external += stats["external"]

        # Progress
        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0

        print(f"  {processed:,}/{total:,} ({processed/total*100:.1f}%) "
              f"| {rate:.0f}/s | ETA: {eta/60:.1f}m "
              f"| links: {total_with_links:,} | external: {total_external:,}")

        # Next batch
        resp = requests.post(f"{ES_HOST}/_search/scroll", json={"scroll": "10m", "scroll_id": scroll_id})
        data = resp.json()
        scroll_id = data.get("_scroll_id")
        docs = data.get("hits", {}).get("hits", [])

    # Clear scroll
    requests.delete(f"{ES_HOST}/_search/scroll", json={"scroll_id": scroll_id})

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"DONE: {processed:,} docs in {elapsed:.0f}s")
    print(f"Docs with links: {total_with_links:,} ({total_with_links/processed*100:.1f}%)")
    print(f"Docs with external links: {total_external:,} ({total_external/processed*100:.1f}%)")


if __name__ == "__main__":
    main()
