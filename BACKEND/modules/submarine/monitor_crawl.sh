#!/bin/bash
# Real-time crawler monitoring
INDEX=${1:-submarine-scrapes}

while true; do
    clear
    date
    echo "===================="
    echo "SUBMARINE CRAWL PROGRESS"
    echo "===================="
    echo
    
    # Document count
    COUNT=$(curl -s --max-time 5 "http://localhost:9200/$INDEX/_count" | jq -c '.count' 2>/dev/null)
    echo "Documents indexed: $COUNT"
    
    # Index size
    SIZE=$(curl -s --max-time 5 "http://localhost:9200/_cat/indices/$INDEX?h=docs.count,store.size" 2>/dev/null)
    echo "Index stats: $SIZE"
    
    echo
    echo "Active crawlers:"
    ACTIVE=$(ps aux | grep '[j]ester_crawler_pacman' | wc -l)
    echo "  $ACTIVE workers running"
    
    echo
    echo "Recent logs (last 5 lines per worker):"
    for log in /tmp/crawler_*.log; do
        if [ -f "$log" ]; then
            echo "  $(basename $log):"
            tail -5 "$log" 2>/dev/null | sed 's/^/    /'
        fi
    done | head -30
    
    echo
    echo "Load average:"
    uptime
    
    sleep 10
done
