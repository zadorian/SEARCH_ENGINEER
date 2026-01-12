#!/bin/bash
# SUBMARINE FILE-BASED CRAWLER - No ES bottleneck

DOMAIN_FILE="$1"
MAX_PAGES=${2:-50}
MAX_DEPTH=${3:-2}
OUTPUT_DIR="/data/crawl_output"

if [ -z "$DOMAIN_FILE" ]; then
    echo "Usage: $0 domains.txt [max_pages] [max_depth]"
    exit 1
fi

TOTAL_LINES=$(wc -l < "$DOMAIN_FILE")
WORKERS=15  # Can go higher without ES
DOMAINS_PER_WORKER=$((TOTAL_LINES / WORKERS + 1))

echo "================================"
echo "SUBMARINE FILE-BASED CRAWLER"
echo "================================"
echo "Total domains: $TOTAL_LINES"
echo "Workers: $WORKERS"
echo "Domains/worker: $DOMAINS_PER_WORKER"
echo "Max pages: $MAX_PAGES"
echo "Max depth: $MAX_DEPTH"
echo "Output: $OUTPUT_DIR"
echo "================================"
echo

# Create output directory
mkdir -p $OUTPUT_DIR

# Split domains
rm -f /tmp/crawl_chunk_*
split -l $DOMAINS_PER_WORKER "$DOMAIN_FILE" /tmp/crawl_chunk_

TOTAL_CHUNKS=$(ls -1 /tmp/crawl_chunk_* | wc -l)
echo "Created $TOTAL_CHUNKS chunks"
echo

# Launch workers
i=0
for chunk in /tmp/crawl_chunk_*; do
    i=$((i+1))
    domains=$(wc -l < $chunk)
    output_file="$OUTPUT_DIR/worker_${i}.jsonl"
    
    echo "[$i/$TOTAL_CHUNKS] Worker $i: $domains domains -> $output_file"
    
    # Launch with --no-index, output to file
    screen -dmS "crawler_$i" bash -c "cd /data/SUBMARINE && python3 -u jester_crawler_pacman.py $chunk --max-pages $MAX_PAGES --max-depth $MAX_DEPTH --no-index 2>&1 | tee $output_file"
    
    sleep 5  # Stagger startup
done

echo
echo "✅ Launched $i workers (file-based mode)"
echo
echo "Monitor:"
echo "  watch -n 5 'wc -l $OUTPUT_DIR/*.jsonl'"
echo
echo "Later index with:"
echo "  python3 bulk_index_files.py $OUTPUT_DIR"
