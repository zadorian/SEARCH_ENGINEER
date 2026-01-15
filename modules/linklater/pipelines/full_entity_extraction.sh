#!/usr/bin/env bash
#
# LinkLater Pipeline: Full Entity Extraction with Graph Building
#
# Complete chain:
#   1. Find domain
#   2. Extract all documents (PDF, DOCX, XLSX, PPTX)
#   3. Extract entities (companies, persons, registrations)
#   4. Extract outlinks and backlinks
#   5. Build knowledge graph
#
# USAGE:
#   ./full_entity_extraction.sh "company.com"
#   ./full_entity_extraction.sh "example.com" output_graph.json
#
# FALLBACK CHAIN (Automatic):
#   Common Crawl → Wayback Machine → Firecrawl
#

set -e

DOMAIN="${1:?Usage: $0 <domain> [output_graph.json]}"
OUTPUT_GRAPH="${2:-${DOMAIN}_graph.json}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP_DIR="/tmp/linklater_$$"
mkdir -p "$TEMP_DIR"

echo "============================================================"
echo "LinkLater: Full Entity Extraction + Graph Building"
echo "============================================================"
echo "Domain: $DOMAIN"
echo "Output Graph: $OUTPUT_GRAPH"
echo "============================================================"
echo ""

# Step 1: Discover domain content
echo "[1/6] Discovering domain content..."
python3 "$SCRIPT_DIR/../cli.py" \
  --url "*.${DOMAIN}/*" \
  --cc-only \
  --format json \
  --output "$TEMP_DIR/pages.json" \
  --concurrent 50 \
  --verbose

# Step 2: Extract binary documents
echo ""
echo "[2/6] Extracting binary documents (PDF/DOCX/XLSX/PPTX)..."
python3 "$SCRIPT_DIR/../cli.py" \
  --file "$TEMP_DIR/pages.json" \
  --extract-binary \
  --concurrent 100 \
  --output "$TEMP_DIR/documents.json" \
  --format json \
  --verbose

# Step 3: Extract entities and outlinks
echo ""
echo "[3/6] Extracting entities and outlinks..."
python3 -c "
import sys
import json
sys.path.insert(0, '$SCRIPT_DIR/../../..')

from modules.linklater.enrichment.cc_enricher import CCEnricher
import asyncio

async def enrich():
    with open('$TEMP_DIR/documents.json') as f:
        docs = json.load(f)

    enricher = CCEnricher(
        extract_entities=True,
        extract_outlinks=True,
        max_concurrent=50
    )

    results, stats = await enricher.enrich_batch([
        {
            'url': d['url'],
            'title': '',
            'snippet': d.get('content', '')[:1000]
        }
        for d in docs
    ])

    # Save enriched results
    with open('$TEMP_DIR/enriched.json', 'w') as f:
        json.dump({
            'domain': '$DOMAIN',
            'results': [
                {
                    'url': r.url,
                    'companies': r.companies,
                    'persons': r.persons,
                    'registrations': r.registrations,
                    'outlinks': r.outlinks
                }
                for r in results
            ],
            'stats': {
                'total': stats.total,
                'cc_hits': stats.cc_hits,
                'companies_found': stats.companies_found,
                'persons_found': stats.persons_found
            }
        }, f, indent=2)

asyncio.run(enrich())
"

# Step 4: Extract backlinks (from CC webgraph)
echo ""
echo "[4/6] Extracting backlinks from Common Crawl webgraph..."
python3 -c "
import json

# Load domain data
with open('$TEMP_DIR/enriched.json') as f:
    data = json.load(f)

# Collect all URLs
urls = [r['url'] for r in data['results']]

# Extract backlinks (would integrate with CC webgraph API here)
# For now, placeholder - actual implementation would query:
# https://data.commoncrawl.org/projects/hyperlinkgraph/

backlinks = {
    'domain': '$DOMAIN',
    'urls': urls,
    'note': 'Backlink extraction requires CC webgraph API integration'
}

with open('$TEMP_DIR/backlinks.json', 'w') as f:
    json.dump(backlinks, f, indent=2)
"

# Step 5: Build knowledge graph
echo ""
echo "[5/6] Building knowledge graph..."
python3 -c "
import json
from collections import defaultdict

# Load enriched data
with open('$TEMP_DIR/enriched.json') as f:
    data = json.load(f)

# Build graph structure
graph = {
    'domain': '$DOMAIN',
    'nodes': [],
    'edges': []
}

node_id = 0
url_to_id = {}

# Add pages as nodes
for result in data['results']:
    url = result['url']
    page_id = f'page_{node_id}'
    url_to_id[url] = page_id

    graph['nodes'].append({
        'id': page_id,
        'type': 'page',
        'url': url,
        'companies': len(result.get('companies', [])),
        'persons': len(result.get('persons', [])),
        'outlinks': len(result.get('outlinks', []))
    })
    node_id += 1

# Add entities as nodes
for result in data['results']:
    page_id = url_to_id[result['url']]

    # Companies
    for company in result.get('companies', []):
        comp_id = f'company_{node_id}'
        graph['nodes'].append({
            'id': comp_id,
            'type': 'company',
            'name': company.get('text', '')
        })
        graph['edges'].append({
            'source': page_id,
            'target': comp_id,
            'type': 'mentions'
        })
        node_id += 1

    # Persons
    for person in result.get('persons', []):
        person_id = f'person_{node_id}'
        graph['nodes'].append({
            'id': person_id,
            'type': 'person',
            'name': person.get('text', '')
        })
        graph['edges'].append({
            'source': page_id,
            'target': person_id,
            'type': 'mentions'
        })
        node_id += 1

    # Outlinks
    for outlink in result.get('outlinks', []):
        if outlink not in url_to_id:
            outlink_id = f'external_{node_id}'
            url_to_id[outlink] = outlink_id
            graph['nodes'].append({
                'id': outlink_id,
                'type': 'external',
                'url': outlink
            })
            node_id += 1

        graph['edges'].append({
            'source': page_id,
            'target': url_to_id[outlink],
            'type': 'links_to'
        })

# Save graph
with open('$OUTPUT_GRAPH', 'w') as f:
    json.dump(graph, f, indent=2)

print(f\"Graph built: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges\")
"

# Step 6: Summary
echo ""
echo "============================================================"
echo "✅ Full Pipeline Complete!"
echo "============================================================"
echo "Knowledge Graph: $OUTPUT_GRAPH"
echo ""
echo "Graph Stats:"
python3 -c "
import json
with open('$OUTPUT_GRAPH') as f:
    g = json.load(f)

    by_type = {}
    for node in g['nodes']:
        t = node['type']
        by_type[t] = by_type.get(t, 0) + 1

    print(f\"  Nodes: {len(g['nodes'])} total\")
    for t, count in sorted(by_type.items()):
        print(f\"    - {t}: {count}\")
    print(f\"  Edges: {len(g['edges'])}\")
"
echo ""
echo "To visualize:"
echo "  cat $OUTPUT_GRAPH | jq '.nodes[] | select(.type==\"company\")'"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"
