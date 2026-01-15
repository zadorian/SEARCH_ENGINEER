#!/usr/bin/env bash
#
# LinkLater Pipeline: Extract All PDFs from Domain
#
# Automatically discovers a domain, finds all PDFs in Common Crawl/Wayback,
# extracts text, and saves results.
#
# USAGE:
#   ./extract_domain_pdfs.sh "tesla.com"
#   ./extract_domain_pdfs.sh "example.com" output.json
#
# FALLBACK CHAIN (Automatic):
#   1. Common Crawl archives (free)
#   2. Wayback Machine (free)
#   3. Firecrawl (paid - API key required)
#

set -e

DOMAIN="${1:?Usage: $0 <domain> [output.json]}"
OUTPUT="${2:-${DOMAIN}_pdfs.json}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

echo "============================================================"
echo "LinkLater Pipeline: Domain PDF Extraction"
echo "============================================================"
echo "Domain: $DOMAIN"
echo "Output: $OUTPUT"
echo "============================================================"
echo ""

# Step 1: Find all PDFs for domain in Common Crawl index
echo "[1/3] Discovering PDFs in Common Crawl archives..."
python3 "$SCRIPT_DIR/../cli.py" \
  --url "*.${DOMAIN}/*.pdf" \
  --format json \
  --extract-binary \
  --output "/tmp/linklater_pdfs_${DOMAIN}.json" \
  --verbose

# Step 2: Extract text from found PDFs (automatic fallback to Wayback/Firecrawl)
echo ""
echo "[2/3] Extracting text from PDFs (CC → Wayback → Firecrawl)..."
python3 "$SCRIPT_DIR/../cli.py" \
  --file "/tmp/linklater_pdfs_${DOMAIN}.json" \
  --extract-binary \
  --concurrent 50 \
  --output "$OUTPUT" \
  --format json \
  --verbose

# Step 3: Summary
echo ""
echo "============================================================"
echo "✅ Complete!"
echo "============================================================"
echo "Results saved to: $OUTPUT"
echo ""
echo "To view entities from extracted PDFs:"
echo "  python3 -m modules.linklater.enrichment.cc_enricher --file '$OUTPUT'"
echo ""
