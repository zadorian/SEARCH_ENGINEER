#!/usr/bin/env python3
"""
Reprocess existing submarine-scrapes documents with full extraction.
Adds: industries, professions, titles, outlinks
"""

import sys
import json
import time
import re
from typing import Dict, Any, List, Set
from urllib.parse import urljoin, urlparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup paths
sys.path.insert(0, "/data")
sys.path.insert(0, "/data/CLASSES")
sys.path.insert(0, "/data/SUBMARINE")

ES_HOST = "http://localhost:9200"
ES_INDEX = "submarine-scrapes"
BATCH_SIZE = 100


# Import extractors
try:
    from SUBJECT.detector import classify_text
    SUBJECT_AVAILABLE = True
    print("SUBJECT detector loaded OK")
except ImportError as e:
    SUBJECT_AVAILABLE = False
    print(f"SUBJECT detector not available: {e}")

try:
    from simple_extractor import extract_persons, extract_companies
    SIMPLE_EXTRACTOR_AVAILABLE = True
    print("Simple extractor loaded OK")
except ImportError as e:
    SIMPLE_EXTRACTOR_AVAILABLE = False
    print(f"Simple extractor not available: {e}")


def extract_outlinks(html: str, base_url: str, max_links: int = 100) -> List[Dict]:
    """Extract links from HTML."""
    if not html:
        return []

    base_domain = urlparse(base_url).netloc.lower().replace("www.", "")

    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\'<>]+)["\'](?:[^>]*>([^<]*)</a)?',
        re.IGNORECASE
    )

    results = []
    seen_urls: Set[str] = set()

    for match in link_pattern.finditer(html):
        href = match.group(1).strip()
        anchor_text = match.group(2).strip() if match.group(2) else ""

        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        full_url = urljoin(base_url, href)

        try:
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            target_domain = parsed.netloc.lower().replace("www.", "")
        except:
            continue

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        is_external = target_domain != base_domain

        results.append({
            "url": full_url,
            "text": anchor_text[:200],
            "domain": target_domain,
            "is_external": is_external,
        })

        if len(results) >= max_links:
            break

    return results


def run_extraction(text: str, html: str, url: str) -> Dict[str, Any]:
    """Run full extraction on content."""
    result = {
        "professions": [],
        "titles": [],
        "industries": [],
        "industry": None,
        "outlinks": [],
        "outlinks_external": [],
    }

    content = text or html
    if not content or len(content) < 50:
        return result

    # SUBJECT detection
    if SUBJECT_AVAILABLE:
        try:
            subject_result = classify_text(content[:100000])

            if subject_result.get("professions"):
                result["professions"] = [
                    {"name": p["name"], "confidence": p["confidence"],
                     "language": p["language"], "matched_term": p["matched_term"]}
                    for p in subject_result["professions"]
                ]

            if subject_result.get("titles"):
                result["titles"] = [
                    {"name": t["name"], "confidence": t["confidence"],
                     "language": t["language"], "matched_term": t["matched_term"]}
                    for t in subject_result["titles"]
                ]

            if subject_result.get("industries"):
                result["industries"] = [
                    {"name": i["name"], "confidence": i["confidence"],
                     "language": i["language"], "matched_term": i["matched_term"]}
                    for i in subject_result["industries"]
                ]

            if subject_result.get("primary_industry"):
                result["industry"] = subject_result["primary_industry"]

        except Exception as e:
            print(f"  SUBJECT error: {e}")

    # Outlinks
    if html and url:
        try:
            all_links = extract_outlinks(html, url, max_links=100)
            result["outlinks"] = all_links
            result["outlinks_external"] = [l for l in all_links if l.get("is_external")]
        except Exception as e:
            print(f"  Outlinks error: {e}")

    return result


def update_mapping():
    """Add new fields to ES mapping."""
    mapping_update = {
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

    try:
        resp = requests.put(
            f"{ES_HOST}/{ES_INDEX}/_mapping",
            json=mapping_update,
            headers={"Content-Type": "application/json"}
        )
        if resp.status_code == 200:
            print("Mapping updated with outlinks fields")
        else:
            print(f"Mapping update response: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Mapping update error: {e}")


def get_docs_to_process(scroll_id=None):
    """Scroll through docs missing extraction fields."""
    if scroll_id:
        resp = requests.post(
            f"{ES_HOST}/_search/scroll",
            json={"scroll": "5m", "scroll_id": scroll_id}
        )
    else:
        # Get docs that don't have outlinks field yet
        query = {
            "query": {
                "bool": {
                    "must_not": [
                        {"exists": {"field": "outlinks"}}
                    ]
                }
            },
            "_source": ["url", "domain", "html", "text"],
            "size": BATCH_SIZE
        }
        resp = requests.post(
            f"{ES_HOST}/{ES_INDEX}/_search?scroll=5m",
            json=query,
            headers={"Content-Type": "application/json"}
        )

    if resp.status_code != 200:
        print(f"Search error: {resp.text[:200]}")
        return None, []

    data = resp.json()
    return data.get("_scroll_id"), data.get("hits", {}).get("hits", [])


def process_doc(doc):
    """Process single document."""
    doc_id = doc["_id"]
    source = doc["_source"]

    url = source.get("url", "")
    html = source.get("html", "")
    text = source.get("text", "")

    extraction = run_extraction(text, html, url)

    # Update doc
    update = {
        "doc": {
            "professions": extraction["professions"],
            "titles": extraction["titles"],
            "industries": extraction["industries"],
            "industry": extraction["industry"],
            "outlinks": extraction["outlinks"],
            "outlinks_external": extraction["outlinks_external"],
        }
    }

    resp = requests.post(
        f"{ES_HOST}/{ES_INDEX}/_update/{doc_id}",
        json=update,
        headers={"Content-Type": "application/json"}
    )

    return {
        "id": doc_id,
        "domain": source.get("domain", ""),
        "professions": len(extraction["professions"]),
        "titles": len(extraction["titles"]),
        "industries": len(extraction["industries"]),
        "outlinks": len(extraction["outlinks"]),
        "success": resp.status_code == 200,
    }


def main():
    print("=" * 60)
    print("SUBMARINE Document Reprocessor")
    print("Adds: professions, titles, industries, outlinks")
    print("=" * 60)

    # Update mapping first
    update_mapping()

    # Get total count
    resp = requests.get(f"{ES_HOST}/{ES_INDEX}/_count")
    total = resp.json().get("count", 0)
    print(f"\nTotal docs in index: {total:,}")

    # Count docs needing processing
    query = {"query": {"bool": {"must_not": [{"exists": {"field": "outlinks"}}]}}}
    resp = requests.post(f"{ES_HOST}/{ES_INDEX}/_count", json=query)
    to_process = resp.json().get("count", 0)
    print(f"Docs needing processing: {to_process:,}")

    if to_process == 0:
        print("All docs already processed!")
        return

    processed = 0
    scroll_id = None
    stats = {"professions": 0, "titles": 0, "industries": 0, "outlinks": 0}

    print(f"\nProcessing {to_process:,} documents...")
    start_time = time.time()

    while True:
        scroll_id, docs = get_docs_to_process(scroll_id)

        if not docs:
            break

        # Process batch with thread pool
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_doc, doc): doc for doc in docs}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    processed += 1

                    if result["professions"] > 0:
                        stats["professions"] += 1
                    if result["titles"] > 0:
                        stats["titles"] += 1
                    if result["industries"] > 0:
                        stats["industries"] += 1
                    if result["outlinks"] > 0:
                        stats["outlinks"] += 1

                    if processed % 1000 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed
                        remaining = (to_process - processed) / rate if rate > 0 else 0
                        print(f"  {processed:,}/{to_process:,} ({processed/to_process*100:.1f}%) "
                              f"- {rate:.0f}/s - ETA: {remaining/60:.1f}m")
                        print(f"    Stats: prof={stats['professions']} titles={stats['titles']} "
                              f"ind={stats['industries']} links={stats['outlinks']}")

                except Exception as e:
                    print(f"  Error: {e}")

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"COMPLETE: Processed {processed:,} docs in {elapsed:.1f}s")
    print(f"Final stats:")
    print(f"  Docs with professions: {stats['professions']:,}")
    print(f"  Docs with titles: {stats['titles']:,}")
    print(f"  Docs with industries: {stats['industries']:,}")
    print(f"  Docs with outlinks: {stats['outlinks']:,}")


if __name__ == "__main__":
    main()
