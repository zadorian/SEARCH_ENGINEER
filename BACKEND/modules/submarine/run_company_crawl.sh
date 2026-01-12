#!/bin/bash
# SUBMARINE Company Domain Crawler
# Full domain crawl with PACMAN extraction → sastre ES

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
DOMAINS_CSV="/Users/attic/01. DRILL_SEARCH/datasets/company_linkedin_domains.csv"

cd "$BACKEND_DIR"

echo "========================================"
echo "SUBMARINE Company Domain Crawler"
echo "========================================"
echo "Domains: $DOMAINS_CSV"
echo "Total: ~3M domains"
echo ""

# Default: full crawl with PACMAN, 50 pages/domain, 10 concurrent domains
# Adjust based on your needs:

python3 -m modules.SUBMARINE.distributed_scraper \
    --domains "$DOMAINS_CSV" \
    --full-crawl \
    --max-pages 50 \
    --max-depth 3 \
    --concurrent-domains 10 \
    --es-host 176.9.2.153 \
    --es-port 9200 \
    "$@"

# For HOMEPAGE ONLY mode (faster, less thorough):
# python3 -m modules.SUBMARINE.distributed_scraper \
#     --domains "$DOMAINS_CSV" \
#     --concurrent 100 \
#     --es-host 176.9.2.153 \
#     "$@"
