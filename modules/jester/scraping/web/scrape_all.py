#!/usr/bin/env python3
"""
DRILL Scrape All Command - !domain.com

Usage:
    python scrape_all.py example.com

Flow:
    1. Discover all URLs (12 free sources + subdomains)
    2. Crawl all discovered pages
    3. Index to Elasticsearch (domain, URL, outlinks, content)
    4. Export deduplicated outlinks JSON
"""

import asyncio
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse

# Add parent paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from . import Drill, DrillConfig
from .discovery import DrillDiscovery
from .indexer import DrillIndexer


def export_outlinks(domain: str, output_dir: Path = None, verbose: bool = True) -> dict:
    """
    Export deduplicated outlinks from Elasticsearch to JSON.

    Output format (HARDCODED - do not change):
    [
        {
            "outlink": "https://external-site.com/page",
            "found_on": ["https://domain.com/page1", "https://domain.com/page2"],
            "count": 5
        },
        ...
    ]

    Only includes EXTERNAL links (excludes internal domain links).
    """
    from elasticsearch import Elasticsearch
    import os

    # Connect to Elasticsearch
    es = Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"))

    # Query all pages for this domain
    query = {
        "query": {"term": {"domain": domain}},
        "size": 10000,
        "_source": ["url", "outlinks"]
    }

    try:
        result = es.search(index="drill_pages", body=query)
    except Exception as e:
        if verbose:
            print(f"  ! Elasticsearch query failed: {e}")
        return {"error": str(e), "outlinks": []}

    hits = result.get('hits', {}).get('hits', [])
    if not hits:
        if verbose:
            print("  ! No pages found in Elasticsearch")
        return {"outlinks": [], "count": 0}

    # Build: outlink -> [source pages that link to it]
    outlink_sources = defaultdict(list)

    for hit in hits:
        src = hit['_source']
        source_url = src.get('url', '')
        outlinks = src.get('outlinks', [])

        for outlink in outlinks:
            # Skip internal links (same domain)
            try:
                outlink_domain = urlparse(outlink).netloc.lower()
                if domain.lower() in outlink_domain or outlink_domain in domain.lower():
                    continue
            except Exception as e:
                continue

            outlink_sources[outlink].append(source_url)

    # Build clean export format
    export = []
    for outlink, sources in sorted(outlink_sources.items()):
        export.append({
            'outlink': outlink,
            'found_on': sources[:5],  # First 5 source pages (limit for readability)
            'count': len(sources)
        })

    # Sort by count (most referenced first)
    export.sort(key=lambda x: x['count'], reverse=True)

    # Save to file
    if output_dir is None:
        output_dir = Path.cwd()

    output_file = output_dir / f"{domain}_outlinks.json"
    with open(output_file, 'w') as f:
        json.dump(export, f, indent=2)

    if verbose:
        print(f"  ✓ Exported {len(export)} unique outlinks to {output_file}")

    return {
        "count": len(export),
        "file": str(output_file)
    }


def export_entities(domain: str, output_dir: Path = None, verbose: bool = True) -> dict:
    """
    Export entities with context snippets from Elasticsearch to JSON.

    Output format (HARDCODED - do not change):
    [
        {
            "value": "John Smith",
            "type": "person",
            "snippets": [
                {"text": "...John Smith, CEO of Acme Corp...", "source": "https://..."},
                ...
            ],
            "source_count": 3
        },
        ...
    ]

    Aggregates entities across all pages, deduplicated by value+type.
    """
    from elasticsearch import Elasticsearch
    import os

    es = Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"))

    query = {
        "query": {"term": {"domain": domain}},
        "size": 10000,
        "_source": ["url", "companies", "persons", "emails", "phones", "keywords_found"]
    }

    try:
        result = es.search(index="drill_pages", body=query)
    except Exception as e:
        if verbose:
            print(f"  ! Elasticsearch query failed: {e}")
        return {"error": str(e), "entities": []}

    hits = result.get('hits', {}).get('hits', [])
    if not hits:
        if verbose:
            print("  ! No pages found in Elasticsearch")
        return {"count": 0, "file": None}

    # Aggregate: (entity_value, entity_type) -> list of source URLs
    entity_sources = defaultdict(list)

    for hit in hits:
        src = hit['_source']
        source_url = src.get('url', '')

        # Companies
        for company in src.get('companies', []):
            entity_sources[(company, 'company')].append(source_url)

        # Persons
        for person in src.get('persons', []):
            entity_sources[(person, 'person')].append(source_url)

        # Emails
        for email in src.get('emails', []):
            entity_sources[(email, 'email')].append(source_url)

        # Phones
        for phone in src.get('phones', []):
            entity_sources[(phone, 'phone')].append(source_url)

        # Keywords
        for keyword in src.get('keywords_found', []):
            entity_sources[(keyword, 'keyword')].append(source_url)

    # Build export format
    export = []
    for (value, entity_type), sources in entity_sources.items():
        export.append({
            'value': value,
            'type': entity_type,
            'found_on': list(set(sources))[:5],  # Dedupe and limit
            'source_count': len(set(sources))
        })

    # Sort by source_count (most common first), then by type
    type_order = {'person': 0, 'company': 1, 'email': 2, 'phone': 3, 'keyword': 4}
    export.sort(key=lambda x: (type_order.get(x['type'], 5), -x['source_count']))

    # Save to file
    if output_dir is None:
        output_dir = Path.cwd()

    output_file = output_dir / f"{domain}_entities.json"
    with open(output_file, 'w') as f:
        json.dump(export, f, indent=2)

    if verbose:
        # Summary by type
        by_type = defaultdict(int)
        for e in export:
            by_type[e['type']] += 1
        summary = ", ".join(f"{count} {t}s" for t, count in sorted(by_type.items()))
        print(f"  ✓ Exported {len(export)} entities ({summary}) to {output_file}")

    return {
        "count": len(export),
        "file": str(output_file)
    }


async def scrape_all(domain: str, max_pages: int = 500, verbose: bool = True, output_dir: Path = None):
    """
    !domain.com - Full domain scrape

    1. Map domain (discover paths, subdomains)
    2. Scrape all pages
    3. Index to Elasticsearch
    4. Export deduplicated outlinks to {domain}_outlinks.json
    5. Export entities with context to {domain}_entities.json
    """
    start_time = datetime.now()

    if verbose:
        print("=" * 60)
        print(f"DRILL SCRAPE ALL: {domain}")
        print("=" * 60)

    # Phase 1: Discovery
    if verbose:
        print(f"\n[1/5] MAPPING DOMAIN...")
        print("  Sources: crt.sh, Sublist3r, Common Crawl, Wayback, Sitemap, etc.")

    discovery = DrillDiscovery(free_only=True)
    discovery_result = await discovery.discover(domain, include_subdomains=True, include_archives=True)

    if verbose:
        print(f"  ✓ Found {discovery_result.total_urls} URLs")
        print(f"  ✓ Subdomains: {len(discovery_result.subdomains)}")
        for source, urls in discovery_result.urls_by_source.items():
            if urls:
                print(f"    - {source}: {len(urls)} URLs")

    # Phase 2: Crawling
    if verbose:
        print(f"\n[2/5] CRAWLING (max {max_pages} pages)...")

    config = DrillConfig(
        max_pages=max_pages,
        max_depth=10,
        max_concurrent=50,
        extract_entities=True,
        generate_embeddings=False,  # Disable for speed
        index_to_elasticsearch=True,  # Real-time indexing
        use_sitemap_first=True,
        discover_subdomains=True,
        discover_archives=True,
        # SPEED: Skip slow archive freshness checks
        check_cc_freshness=False,
        check_wayback_freshness=False,
        archive_skip_policy="never_skip",
    )

    drill = Drill(config)

    # Crawl with discovered URLs as seeds
    seeds = discovery_result.all_urls[:max_pages] if hasattr(discovery_result, 'all_urls') else None
    stats = await drill.crawl(domain, seed_urls=seeds)

    if verbose:
        print(f"  ✓ Pages crawled: {stats.pages_crawled}")
        print(f"  ✓ Links extracted: {stats.links_extracted}")
        print(f"  ✓ Indexed to ES: {stats.pages_crawled}")  # All crawled pages are indexed

    # Phase 3: Export outlinks
    if verbose:
        print(f"\n[3/5] EXPORTING OUTLINKS...")

    outlinks_result = export_outlinks(domain, output_dir=output_dir, verbose=verbose)

    # Phase 4: Export entities
    if verbose:
        print(f"\n[4/5] EXPORTING ENTITIES...")

    entities_result = export_entities(domain, output_dir=output_dir, verbose=verbose)

    # Phase 5: Summary
    elapsed = (datetime.now() - start_time).total_seconds()

    if verbose:
        print(f"\n[5/5] COMPLETE!")
        print("-" * 40)
        print(f"  Domain: {domain}")
        print(f"  Pages crawled/indexed: {stats.pages_crawled}")
        print(f"  Links extracted: {stats.links_extracted}")
        print(f"  Unique external outlinks: {outlinks_result.get('count', 0)}")
        print(f"  Entities extracted: {entities_result.get('count', 0)}")
        print(f"  High-relevance links: {stats.high_relevance_links}")
        print(f"  Subdomains found: {len(discovery_result.subdomains)}")
        print(f"  Time elapsed: {elapsed:.1f}s")
        print(f"\n  ES Index: drill_pages")
        print(f"  Query: domain:{domain}")
        if outlinks_result.get('file'):
            print(f"  Outlinks: {outlinks_result['file']}")
        if entities_result.get('file'):
            print(f"  Entities: {entities_result['file']}")
        print("=" * 60)

    return {
        "domain": domain,
        "discovery": {
            "total_urls": discovery_result.total_urls,
            "subdomains": discovery_result.subdomains,
            "sources": list(discovery_result.urls_by_source.keys()),
        },
        "crawl": {
            "pages_crawled": stats.pages_crawled,
            "links_extracted": stats.links_extracted,
            "high_relevance_links": stats.high_relevance_links,
        },
        "outlinks": {
            "count": outlinks_result.get('count', 0),
            "file": outlinks_result.get('file'),
        },
        "entities": {
            "count": entities_result.get('count', 0),
            "file": entities_result.get('file'),
        },
        "elapsed_seconds": elapsed,
    }


async def main():
    parser = argparse.ArgumentParser(description="DRILL Scrape All - !domain.com")
    parser.add_argument("domain", help="Target domain (e.g., example.com)")
    parser.add_argument("--max-pages", "-m", type=int, default=500, help="Max pages to crawl")
    parser.add_argument("--output-dir", "-o", type=Path, default=None, help="Output directory for outlinks JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")

    args = parser.parse_args()

    # Strip any ! prefix
    domain = args.domain.lstrip("!")

    result = await scrape_all(
        domain,
        args.max_pages,
        verbose=not args.quiet,
        output_dir=args.output_dir
    )

    if args.quiet:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
