#!/usr/bin/env bash
#
# LinkLater Pipeline: Extract All Documents from Domain
#
# Discovers ALL document types (PDF, DOCX, XLSX, PPTX) from a domain,
# extracts text, and optionally extracts entities.
#
# USAGE:
#   ./extract_domain_docs.sh "company.com"
#   ./extract_domain_docs.sh "example.com" output_dir/
#
# FALLBACK CHAIN (Automatic):
#   1. Common Crawl (free)
#   2. Wayback Machine (free)
#   3. Firecrawl (paid)
#

set -e

DOMAIN="${1:?Usage: $0 <domain> [output_dir]}"
OUTPUT_DIR="${2:-./linklater_results}"

mkdir -p "$OUTPUT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "LinkLater Pipeline: Full Document Extraction"
echo "============================================================"
echo "Domain: $DOMAIN"
echo "Output Directory: $OUTPUT_DIR"
echo "============================================================"
echo ""

# Document types to extract
EXTENSIONS=("pdf" "docx" "xlsx" "pptx" "doc" "xls" "ppt")

# Step 1: Discover all document URLs for each type
echo "[1/4] Discovering document URLs..."
ALL_URLS="$OUTPUT_DIR/${DOMAIN}_all_urls.txt"
> "$ALL_URLS"  # Clear file

for ext in "${EXTENSIONS[@]}"; do
  echo "  Searching for *.${ext}..."
  python3 "$SCRIPT_DIR/../cli.py" \
    --url "*.${DOMAIN}/*.${ext}" \
    --format text \
    --cc-only \
    --output "/tmp/${ext}_urls.txt" 2>/dev/null || true

  if [ -f "/tmp/${ext}_urls.txt" ]; then
    cat "/tmp/${ext}_urls.txt" >> "$ALL_URLS"
  fi
done

TOTAL_URLS=$(wc -l < "$ALL_URLS" | tr -d ' ')
echo "  Found $TOTAL_URLS document URLs"

# Step 2: Extract content from all documents
echo ""
echo "[2/4] Extracting document content (with fallback chain)..."
python3 "$SCRIPT_DIR/../cli.py" \
  --file "$ALL_URLS" \
  --extract-binary \
  --concurrent 100 \
  --output "$OUTPUT_DIR/${DOMAIN}_documents.json" \
  --format json \
  --verbose

# Step 3: Extract entities
echo ""
echo "[3/4] Extracting entities from documents..."
python3 -c "
import sys
import json
sys.path.insert(0, '$SCRIPT_DIR/../../..')

from modules.linklater.enrichment.cc_enricher import CCEnricher
import asyncio

async def extract():
    with open('$OUTPUT_DIR/${DOMAIN}_documents.json') as f:
        docs = json.load(f)

    enricher = CCEnricher(extract_entities=True, extract_outlinks=True)
    results = await enricher.enrich_batch([{'url': d['url'], 'title': '', 'snippet': d.get('content', '')[:500]} for d in docs])

    with open('$OUTPUT_DIR/${DOMAIN}_entities.json', 'w') as f:
        json.dump({
            'domain': '$DOMAIN',
            'total_documents': len(docs),
            'companies': [e for r in results[0] for e in r.companies],
            'persons': [e for r in results[0] for e in r.persons],
            'registrations': [e for r in results[0] for e in r.registrations]
        }, f, indent=2)

asyncio.run(extract())
"

# Step 4: Summary
echo ""
echo "============================================================"
echo "✅ Pipeline Complete!"
echo "============================================================"
echo "Documents:  $OUTPUT_DIR/${DOMAIN}_documents.json"
echo "Entities:   $OUTPUT_DIR/${DOMAIN}_entities.json"
echo ""
echo "To view results:"
echo "  cat $OUTPUT_DIR/${DOMAIN}_entities.json | jq '.companies'"
echo ""
