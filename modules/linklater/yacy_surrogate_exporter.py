#!/usr/bin/env python3
"""
YaCy Surrogate Exporter - Convert Elasticsearch indices to YaCy surrogate format

Exports documents from Elasticsearch (e.g., onion-pages) to YaCy XML surrogate
files that can be imported into YaCy's index.

YaCy Format: Dublin Core compatible XML
Destination: DATA/SURROGATES/in/

Usage:
    python yacy_surrogate_exporter.py --index onion-pages --output /path/to/yacy/DATA/SURROGATES/in/
"""

import os
import sys
import json
import asyncio
import argparse
import html
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from xml.sax.saxutils import escape
from elasticsearch import AsyncElasticsearch
import hashlib

# YaCy paths
YACY_PATH = os.getenv("YACY_INSTALL_PATH", "/Users/attic/Applications/YaCy")
YACY_MAIN_SURROGATES = f"{YACY_PATH}/yacy/DATA/SURROGATES/in"
YACY_TOR_SURROGATES = f"{YACY_PATH}/yacy_tor/DATA/SURROGATES/in"

# Elasticsearch
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")


def cdata(text: str) -> str:
    """Wrap text in CDATA section, escaping nested CDATA."""
    if text is None:
        return "<![CDATA[]]>"
    # Escape nested CDATA end markers
    text = str(text).replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


def escape_xml(text: str) -> str:
    """Escape XML special characters."""
    if text is None:
        return ""
    return escape(str(text))


def doc_to_surrogate_xml(doc: Dict[str, Any], source_name: str = "cymonides") -> str:
    """
    Convert an Elasticsearch document to YaCy Dublin Core surrogate XML.

    Args:
        doc: Elasticsearch document with _source
        source_name: Name for the collection

    Returns:
        XML string for a single <record>
    """
    src = doc.get("_source", doc)

    url = src.get("url", "")
    title = src.get("title", "") or src.get("domain", "") or "Untitled"
    description = src.get("content", "") or src.get("meta", "") or ""

    # Truncate description to reasonable size
    if len(description) > 50000:
        description = description[:50000] + "..."

    # Get date
    date_str = src.get("fetched_at") or src.get("updated_on") or src.get("crawl_date") or datetime.utcnow().isoformat()
    if isinstance(date_str, str) and "T" in date_str:
        date_str = date_str.split("T")[0]  # Just the date part

    # Language detection (default to en)
    language = src.get("language", "en") or "en"
    if len(language) > 2:
        language = language[:2].lower()

    # Build keywords from entities
    keywords = []
    for field in ["emails", "persons", "companies", "crypto_wallets"]:
        if field in src and src[field]:
            keywords.extend(src[field][:10])  # Max 10 per field
    keywords_str = ", ".join(keywords[:50])  # Max 50 total

    # H1 from title or first significant heading
    h1 = src.get("h1", "") or title

    # Build the XML record
    xml_parts = [
        '  <record>',
        f'    <dc:Title>{cdata(title)}</dc:Title>',
        f'    <dc:Identifier>{escape_xml(url)}</dc:Identifier>',
        f'    <dc:Description>{cdata(description)}</dc:Description>',
        f'    <dc:Language>{escape_xml(language)}</dc:Language>',
        f'    <dc:Date>{escape_xml(date_str)}</dc:Date>',
    ]

    # Add optional fields
    if keywords_str:
        xml_parts.append(f'    <dc:Subject>{cdata(keywords_str)}</dc:Subject>')

    # Add domain as publisher
    domain = src.get("domain", "")
    if domain:
        xml_parts.append(f'    <dc:Publisher>{escape_xml(domain)}</dc:Publisher>')

    # Add source info
    xml_parts.append(f'    <dc:Source>{escape_xml(src.get("source", source_name))}</dc:Source>')

    # Custom metadata fields
    if h1:
        xml_parts.append(f'    <md:h1_txt>{cdata(h1)}</md:h1_txt>')

    # Collection tag
    xml_parts.append(f'    <md:collection_sxt>{escape_xml(source_name)}</md:collection_sxt>')

    # Content type
    content_type = src.get("content_type", "text/html")
    xml_parts.append(f'    <md:content_type_s>{escape_xml(content_type)}</md:content_type_s>')

    xml_parts.append('  </record>')

    return '\n'.join(xml_parts)


def create_surrogate_file(records: List[str], filename: str, output_dir: str) -> str:
    """
    Create a complete YaCy surrogate XML file.

    Args:
        records: List of XML record strings
        filename: Output filename (without extension)
        output_dir: Directory to write to

    Returns:
        Path to created file
    """
    xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<surrogates xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:md="http://localhost:8090/api/schema.xml?core=collection1">
{chr(10).join(records)}
</surrogates>
'''

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:17]
    output_path = Path(output_dir) / f"{filename}.{timestamp}.xml"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    return str(output_path)


async def export_index_to_yacy(
    index_name: str,
    output_dir: str,
    batch_size: int = 500,
    max_docs: Optional[int] = None,
    query: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Export an Elasticsearch index to YaCy surrogate files.

    Args:
        index_name: Elasticsearch index to export
        output_dir: YaCy SURROGATES/in directory
        batch_size: Documents per surrogate file
        max_docs: Maximum documents to export (None for all)
        query: Optional Elasticsearch query filter

    Returns:
        Export statistics
    """
    es = AsyncElasticsearch([ES_HOST])

    stats = {
        "index": index_name,
        "output_dir": output_dir,
        "files_created": 0,
        "documents_exported": 0,
        "errors": []
    }

    try:
        # Get index count
        count_result = await es.count(index=index_name, body=query or {"query": {"match_all": {}}})
        total_docs = count_result["count"]

        if max_docs:
            total_docs = min(total_docs, max_docs)

        print(f"[YaCy Export] Exporting {total_docs} documents from {index_name}")
        print(f"[YaCy Export] Output: {output_dir}")

        # Scroll through documents
        records = []
        file_count = 0

        # Use search with scroll
        response = await es.search(
            index=index_name,
            body=query or {"query": {"match_all": {}}},
            scroll="5m",
            size=100
        )

        scroll_id = response["_scroll_id"]
        hits = response["hits"]["hits"]

        while hits and stats["documents_exported"] < total_docs:
            for doc in hits:
                if max_docs and stats["documents_exported"] >= max_docs:
                    break

                try:
                    record_xml = doc_to_surrogate_xml(doc, source_name=index_name)
                    records.append(record_xml)
                    stats["documents_exported"] += 1

                    # Write batch to file
                    if len(records) >= batch_size:
                        file_count += 1
                        filename = f"{index_name}_batch{file_count:04d}"
                        filepath = create_surrogate_file(records, filename, output_dir)
                        print(f"[YaCy Export] Created: {Path(filepath).name} ({len(records)} docs)")
                        stats["files_created"] += 1
                        records = []

                except Exception as e:
                    stats["errors"].append(f"Doc {doc.get('_id', 'unknown')}: {str(e)}")

            # Get next batch
            if stats["documents_exported"] < total_docs:
                response = await es.scroll(scroll_id=scroll_id, scroll="5m")
                scroll_id = response["_scroll_id"]
                hits = response["hits"]["hits"]
            else:
                break

        # Write remaining records
        if records:
            file_count += 1
            filename = f"{index_name}_batch{file_count:04d}"
            filepath = create_surrogate_file(records, filename, output_dir)
            print(f"[YaCy Export] Created: {Path(filepath).name} ({len(records)} docs)")
            stats["files_created"] += 1

        # Clear scroll
        await es.clear_scroll(scroll_id=scroll_id)

    except Exception as e:
        stats["errors"].append(f"Export error: {str(e)}")
        print(f"[YaCy Export] ERROR: {e}")
    finally:
        await es.close()

    return stats


async def export_onion_pages_to_yacy_tor():
    """Export onion-pages index to YaCy Tor instance."""
    return await export_index_to_yacy(
        index_name="onion-pages",
        output_dir=YACY_TOR_SURROGATES,
        batch_size=200,  # Smaller batches for .onion sites
        max_docs=None  # Export all
    )


async def export_tor_bridges_to_yacy_tor():
    """Export tor-bridges index to YaCy Tor instance."""
    return await export_index_to_yacy(
        index_name="tor-bridges",
        output_dir=YACY_TOR_SURROGATES,
        batch_size=500,
        max_docs=None
    )


def main():
    parser = argparse.ArgumentParser(description="Export Elasticsearch to YaCy surrogates")
    parser.add_argument("--index", "-i", required=True, help="Elasticsearch index name")
    parser.add_argument("--output", "-o", help="Output directory (default: YaCy Tor surrogates)")
    parser.add_argument("--batch-size", "-b", type=int, default=500, help="Documents per file")
    parser.add_argument("--max-docs", "-m", type=int, help="Maximum documents to export")
    parser.add_argument("--tor", action="store_true", help="Export to YaCy Tor instance")

    args = parser.parse_args()

    output_dir = args.output
    if not output_dir:
        output_dir = YACY_TOR_SURROGATES if args.tor else YACY_MAIN_SURROGATES

    stats = asyncio.run(export_index_to_yacy(
        index_name=args.index,
        output_dir=output_dir,
        batch_size=args.batch_size,
        max_docs=args.max_docs
    ))

    print(f"\n[YaCy Export] Complete!")
    print(f"  Documents exported: {stats['documents_exported']}")
    print(f"  Files created: {stats['files_created']}")
    if stats['errors']:
        print(f"  Errors: {len(stats['errors'])}")


if __name__ == "__main__":
    main()
