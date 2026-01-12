#!/usr/bin/env python3
"""
YaCy OAI-PMH Exporter - Convert Elasticsearch to YaCy OAI-PMH format

This exports to the OAI-PMH XML format that YaCy actually processes.
"""

import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from xml.sax.saxutils import escape
from elasticsearch import AsyncElasticsearch

YACY_PATH = os.getenv("YACY_INSTALL_PATH", "/Users/attic/Applications/YaCy")
YACY_TOR_SURROGATES = f"{YACY_PATH}/yacy_tor/DATA/SURROGATES/in"
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")


def escape_xml(text: str) -> str:
    """Escape XML special characters and strip invalid XML 1.0 characters."""
    if text is None:
        return ""
    text = str(text)
    # Remove invalid XML 1.0 characters (control chars except tab, newline, carriage return)
    # Valid: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    import re
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return escape(text)


def doc_to_oaipmh_record(doc: Dict[str, Any], record_id: str) -> Optional[str]:
    """Convert an Elasticsearch document to OAI-PMH record format.

    Returns None if the document doesn't have a valid URL.
    """
    src = doc.get("_source", doc)

    # Get URL - try multiple possible field names
    url = src.get("url", "") or src.get("source_url", "") or src.get("target_url", "") or src.get("found_on_url", "")

    # Skip documents without valid URLs
    if not url or not url.startswith("http"):
        return None

    # Convert .onion URLs to gateway format for YaCy TLD validation
    # YaCy doesn't recognize .onion as a valid TLD, so we use onion.ws gateway
    if ".onion" in url:
        url = url.replace(".onion", ".onion.ws")

    title = src.get("title", "") or src.get("anchor_text", "") or src.get("label", "") or src.get("domain", "") or "Untitled"
    description = src.get("content", "") or src.get("meta", "") or src.get("snippet", "") or ""

    # For edge documents, include edge type info
    if src.get("edge_type") or src.get("type") == "outlink":
        edge_type = src.get("edge_type", src.get("type", "link"))
        from_node = src.get("from", src.get("source_domain", ""))
        to_node = src.get("to", src.get("target_domain", ""))
        if from_node or to_node:
            description = f"[{edge_type}] {from_node} → {to_node}. {description}".strip()

    # Truncate description
    if len(description) > 10000:
        description = description[:10000] + "..."

    # Get date
    date_str = src.get("fetched_at") or src.get("updated_on") or datetime.now(timezone.utc).isoformat()
    if "T" in str(date_str):
        date_str = str(date_str).split("T")[0]

    # Language
    language = src.get("language", "en") or "en"
    if len(language) > 2:
        language = language[:2].lower()

    # Domain as publisher - try multiple field names
    domain = src.get("domain", "") or src.get("source_domain", "") or src.get("target_domain", "")
    if not domain and url:
        # Extract domain from URL
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
        except:
            pass
    # Convert .onion domain to gateway format
    if domain and ".onion" in domain:
        domain = domain.replace(".onion", ".onion.ws")

    # Build keywords from entities
    subjects = []
    for field in ["emails", "persons", "companies"]:
        if field in src and src[field]:
            subjects.extend([str(s) for s in src[field][:5]])

    # Build the OAI-PMH record
    record = f'''    <record>
      <header>
        <identifier>oai:cymonides.onion:{escape_xml(record_id)}</identifier>
        <datestamp>{escape_xml(date_str)}</datestamp>
        <setSpec>onion-pages</setSpec>
      </header>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd">
          <dc:title>{escape_xml(title)}</dc:title>
          <dc:identifier>{escape_xml(url)}</dc:identifier>
          <dc:description>{escape_xml(description)}</dc:description>
          <dc:language>{escape_xml(language)}</dc:language>
          <dc:date>{escape_xml(date_str)}</dc:date>
          <dc:publisher>{escape_xml(domain)}</dc:publisher>
          <dc:source>cymonides-tor-crawler</dc:source>
          <dc:type>text/html</dc:type>
          <dc:format>text/html</dc:format>'''

    for subj in subjects[:10]:
        record += f'\n          <dc:subject>{escape_xml(subj)}</dc:subject>'

    record += '''
        </oai_dc:dc>
      </metadata>
    </record>'''

    return record


def create_oaipmh_file(records: List[str], filename: str, output_dir: str) -> str:
    """Create a complete OAI-PMH XML file."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">
  <responseDate>{timestamp}</responseDate>
  <request verb="ListRecords" metadataPrefix="oai_dc">https://cymonides.local/oai</request>
  <ListRecords>
{chr(10).join(records)}
  </ListRecords>
</OAI-PMH>
'''

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17]
    output_path = Path(output_dir) / f"oaipmh.{filename}.{ts}.xml"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    return str(output_path)


async def export_to_oaipmh(
    index_name: str,
    output_dir: str,
    batch_size: int = 100,
    max_docs: Optional[int] = None
) -> Dict[str, Any]:
    """Export an Elasticsearch index to OAI-PMH format."""
    es = AsyncElasticsearch([ES_HOST])
    stats = {"files_created": 0, "documents_exported": 0, "errors": []}

    try:
        count_result = await es.count(index=index_name, body={"query": {"match_all": {}}})
        total_docs = min(count_result["count"], max_docs or float('inf'))
        print(f"[OAI-PMH Export] Exporting {int(total_docs)} documents from {index_name}")

        records = []
        file_count = 0

        response = await es.search(
            index=index_name,
            body={"query": {"match_all": {}}},
            scroll="5m",
            size=100
        )

        scroll_id = response["_scroll_id"]
        hits = response["hits"]["hits"]

        while hits and stats["documents_exported"] < total_docs:
            for doc in hits:
                if stats["documents_exported"] >= total_docs:
                    break
                try:
                    record_id = doc.get("_id", f"doc_{stats['documents_exported']}")
                    record_xml = doc_to_oaipmh_record(doc, record_id)
                    if record_xml is None:
                        # Skip documents without valid URLs
                        continue
                    records.append(record_xml)
                    stats["documents_exported"] += 1

                    if len(records) >= batch_size:
                        file_count += 1
                        filepath = create_oaipmh_file(
                            records,
                            f"cymonides_{index_name}_batch{file_count:04d}",
                            output_dir
                        )
                        print(f"[OAI-PMH Export] Created: {Path(filepath).name} ({len(records)} docs)")
                        stats["files_created"] += 1
                        records = []
                except Exception as e:
                    stats["errors"].append(str(e))

            response = await es.scroll(scroll_id=scroll_id, scroll="5m")
            scroll_id = response["_scroll_id"]
            hits = response["hits"]["hits"]

        if records:
            file_count += 1
            filepath = create_oaipmh_file(
                records,
                f"cymonides_{index_name}_batch{file_count:04d}",
                output_dir
            )
            print(f"[OAI-PMH Export] Created: {Path(filepath).name} ({len(records)} docs)")
            stats["files_created"] += 1

        await es.clear_scroll(scroll_id=scroll_id)
    finally:
        await es.close()

    return stats


async def main():
    # Clear old surrogates first
    import glob
    for f in glob.glob(f"{YACY_TOR_SURROGATES}/*.xml"):
        os.remove(f)
    print(f"[OAI-PMH Export] Cleared old surrogates")

    total = 0

    # Export onion-pages (2,785 actual page docs with content)
    stats1 = await export_to_oaipmh("onion-pages", YACY_TOR_SURROGATES, batch_size=100)
    print(f"\n[onion-pages] Exported: {stats1['documents_exported']} docs, {stats1['files_created']} files")
    total += stats1['documents_exported']

    # Export tor-bridges (7,006 - uses source_url)
    stats2 = await export_to_oaipmh("tor-bridges", YACY_TOR_SURROGATES, batch_size=200)
    print(f"[tor-bridges] Exported: {stats2['documents_exported']} docs, {stats2['files_created']} files")
    total += stats2['documents_exported']

    # Export onion-graph-edges (267,760 - uses found_on_url)
    stats3 = await export_to_oaipmh("onion-graph-edges", YACY_TOR_SURROGATES, batch_size=500)
    print(f"[onion-graph-edges] Exported: {stats3['documents_exported']} docs, {stats3['files_created']} files")
    total += stats3['documents_exported']

    # Export onion-graph-nodes (4,904 - query nodes, may not have URLs)
    stats4 = await export_to_oaipmh("onion-graph-nodes", YACY_TOR_SURROGATES, batch_size=200)
    print(f"[onion-graph-nodes] Exported: {stats4['documents_exported']} docs, {stats4['files_created']} files")
    total += stats4['documents_exported']

    print(f"\n[OAI-PMH Export] Complete! Total: {total} docs")


if __name__ == "__main__":
    asyncio.run(main())
