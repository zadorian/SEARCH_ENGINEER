#!/bin/bash
# SUBMARINE PARALLEL CRAWLER - One command to rule them all
# Usage: ./launch_parallel_crawl.sh domains.txt [max_pages] [max_depth]

set -e

DOMAIN_FILE="$1"
MAX_PAGES=${2:-50}
MAX_DEPTH=${3:-2}
ES_INDEX="submarine-scrapes"

# Auto-calculate optimal workers
TOTAL_LINES=$(wc -l < "$DOMAIN_FILE")
WORKERS=19  # Fixed for 20-core server
DOMAINS_PER_WORKER=$((TOTAL_LINES / WORKERS + 1))

echo "================================"
echo "SUBMARINE PARALLEL CRAWLER"
echo "================================"
echo "Domain file: $DOMAIN_FILE"
echo "Total domains: $TOTAL_LINES"
echo "Workers: $WORKERS"
echo "Domains/worker: $DOMAINS_PER_WORKER"
echo "Max pages/domain: $MAX_PAGES"
echo "Max depth: $MAX_DEPTH"
echo "Parallel domains: 20 per worker"
echo "================================"
echo

# Check domain file exists
if [ ! -f "$DOMAIN_FILE" ]; then
    echo "Error: Domain file '$DOMAIN_FILE' not found"
    exit 1
fi

# Wait for ES
echo "Checking Elasticsearch..."
for i in {1..30}; do
    if curl -s --max-time 2 http://localhost:9200/_cluster/health >/dev/null 2>&1; then
        echo "✓ ES available"
        break
    fi
    echo "Waiting for ES (attempt $i/30)..."
    sleep 2
done

# Pre-create index (avoids race conditions)
echo
echo "Pre-creating index: $ES_INDEX"
curl -s -X PUT "http://localhost:9200/$ES_INDEX" -H 'Content-Type: application/json' -d '{
  "settings": {"number_of_shards": 3, "number_of_replicas": 0},
  "mappings": {
    "properties": {
      "domain": {"type": "keyword"},
      "url": {"type": "keyword"},
      "source": {"type": "keyword"},
      "depth": {"type": "integer"},
      "status": {"type": "integer"},
      "content": {"type": "text"},
      "content_length": {"type": "integer"},
      "internal_links_count": {"type": "integer"},
      "outlinks_count": {"type": "integer"},
      "entities": {"type": "object"},
      "crawled_at": {"type": "date"}
    }
  }
}' 2>&1 | grep -q '"acknowledged":true' && echo "✓ Index created" || echo "ℹ Index exists"

echo
echo "================================"
echo "LAUNCHING PARALLEL CRAWLERS"
echo "================================"
echo

# Split domains
CHUNK_DIR="/tmp/crawler_chunks_$(date +%s)"
mkdir -p $CHUNK_DIR
split -l $DOMAINS_PER_WORKER "$DOMAIN_FILE" $CHUNK_DIR/chunk_

TOTAL_CHUNKS=$(ls -1 $CHUNK_DIR/chunk_* | wc -l)
echo "Created $TOTAL_CHUNKS worker chunks in $CHUNK_DIR"
echo

# Launch workers in batches
WORKERS_PER_BATCH=5
BATCH_DELAY=60

i=0
batch=1
for chunk in $CHUNK_DIR/chunk_*; do
    i=$((i+1))
    domains=$(wc -l < $chunk)
    
    echo "[$i/$TOTAL_CHUNKS] Worker $i: $domains domains"
    
    screen -dmS "crawler_$i" bash -c "cd /data/SUBMARINE && python3 -u jester_crawler_pacman.py $chunk --max-pages $MAX_PAGES --max-depth $MAX_DEPTH --es-index $ES_INDEX 2>&1 | tee /tmp/crawler_$i.log"
    
    # Stagger within batch
    sleep 5
    
    # After batch, longer pause
    if [ $((i % WORKERS_PER_BATCH)) -eq 0 ]; then
        echo "  Batch $batch complete. Pausing ${BATCH_DELAY}s..."
        sleep $BATCH_DELAY
        batch=$((batch+1))
    fi
done

echo
echo "✅ Launched $i parallel crawlers"
echo "Monitor: screen -ls | grep crawler"
echo "Logs: /tmp/crawler_*.log"
echo
echo "Expected completion: 6-8 hours"
echo "Current progress: curl -s http://localhost:9200/$ES_INDEX/_count | jq .count"
