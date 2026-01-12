#!/bin/bash
# SUBMARINE Quick Tuning Script

echo "========================================"
echo "SUBMARINE QUICK TUNING"
echo "========================================"
echo

echo "Current Settings:"
echo "----------------"
WORKERS=$(grep 'WORKERS=' /data/SUBMARINE/launch_parallel_crawl.sh | grep -v '#' | head -1 | cut -d'=' -f2)
CONCURRENT=$(grep 'DOMAINS_CONCURRENT' /data/SUBMARINE/jester_crawler_pacman.py | grep -v '#' | head -1 | awk '{print $3}')
CONCURRENT_A=$(grep 'CONCURRENT_A' /data/SUBMARINE/jester_crawler_pacman.py | grep -v '#' | head -1 | awk '{print $3}')
ES_HEAP=$(cat /etc/elasticsearch/jvm.options.d/heap.options 2>/dev/null | grep Xmx | sed 's/-Xmx//')

echo "Workers: $WORKERS"
echo "Concurrent/worker: $CONCURRENT"
echo "Total concurrent: $(( WORKERS * CONCURRENT ))"
echo "HTTP concurrent: $CONCURRENT_A"
echo "ES Heap: $ES_HEAP"
echo

echo "Presets:"
echo "--------"
echo "1. Maximum Speed (4-6 hours, 2.8M domains)"
echo "   Workers: 19, Concurrent: 30, ES: 32GB"
echo
echo "2. Balanced (6-8 hours, 2.8M domains)"
echo "   Workers: 19, Concurrent: 20, ES: 24GB"
echo
echo "3. Conservative (10-14 hours, 2.8M domains)"
echo "   Workers: 10, Concurrent: 20, ES: 24GB"
echo
echo "4. ES Stability (12-16 hours, 2.8M domains)"
echo "   Workers: 8, Concurrent: 15, ES: 24GB"
echo
echo "5. Custom"
echo

read -p "Select preset (1-5): " PRESET

case $PRESET in
  1)
    WORKERS=19
    CONCURRENT=30
    CONCURRENT_A=300
    ES_HEAP="32g"
    ;;
  2)
    WORKERS=19
    CONCURRENT=20
    CONCURRENT_A=200
    ES_HEAP="24g"
    ;;
  3)
    WORKERS=10
    CONCURRENT=20
    CONCURRENT_A=200
    ES_HEAP="24g"
    ;;
  4)
    WORKERS=8
    CONCURRENT=15
    CONCURRENT_A=150
    ES_HEAP="24g"
    ;;
  5)
    read -p "Workers (5-20): " WORKERS
    read -p "Concurrent per worker (10-40): " CONCURRENT
    read -p "HTTP concurrent (100-500): " CONCURRENT_A
    read -p "ES Heap (16-32g): " ES_HEAP
    ;;
  *)
    echo "Invalid selection"
    exit 1
    ;;
esac

echo
echo "Applying settings:"
echo "------------------"
echo "Workers: $WORKERS"
echo "Concurrent/worker: $CONCURRENT"
echo "Total concurrent: $(( WORKERS * CONCURRENT ))"
echo "HTTP concurrent: $CONCURRENT_A"
echo "ES Heap: $ES_HEAP"
echo

read -p "Proceed? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
  echo "Cancelled"
  exit 0
fi

# Backup files
cp /data/SUBMARINE/launch_parallel_crawl.sh /data/SUBMARINE/launch_parallel_crawl.sh.backup
cp /data/SUBMARINE/jester_crawler_pacman.py /data/SUBMARINE/jester_crawler_pacman.py.backup

# Apply settings
sed -i "s/WORKERS=[0-9]*/WORKERS=$WORKERS/" /data/SUBMARINE/launch_parallel_crawl.sh
sed -i "s/DOMAINS_CONCURRENT = [0-9]*/DOMAINS_CONCURRENT = $CONCURRENT/" /data/SUBMARINE/jester_crawler_pacman.py
sed -i "s/CONCURRENT_A = [0-9]*/CONCURRENT_A = $CONCURRENT_A/" /data/SUBMARINE/jester_crawler_pacman.py

# Update ES heap
echo "-Xms$ES_HEAP" > /etc/elasticsearch/jvm.options.d/heap.options
echo "-Xmx$ES_HEAP" >> /etc/elasticsearch/jvm.options.d/heap.options

echo
echo "✓ Settings applied"
echo

read -p "Restart Elasticsearch? (y/n): " RESTART_ES
if [ "$RESTART_ES" = "y" ]; then
  echo "Restarting Elasticsearch..."
  systemctl restart elasticsearch
  sleep 30
  curl -s http://localhost:9200/_cluster/health | jq .status
  echo "✓ Elasticsearch restarted"
fi

echo
echo "========================================"
echo "New Configuration:"
echo "Workers: $WORKERS"
echo "Concurrent/worker: $CONCURRENT"
echo "Total concurrent: $(( WORKERS * CONCURRENT )) domains"
echo "HTTP concurrent: $CONCURRENT_A requests/domain"
echo "ES Heap: $ES_HEAP"
echo "========================================"
echo
echo "Launch crawl:"
echo "  cd /data/SUBMARINE"
echo "  ./launch_parallel_crawl.sh domains.txt"
echo
echo "Monitor:"
echo "  ./monitor_crawl.sh submarine-scrapes"
