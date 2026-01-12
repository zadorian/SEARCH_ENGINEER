#!/bin/bash
# Monitor file-based SUBMARINE crawl

echo "=== SUBMARINE File Crawl Monitor ==="
echo "Time: $(date)"
echo

# Count active workers
ACTIVE=$(ps aux | grep "jester_crawler_pacman.py" | grep -v grep | wc -l)
echo "Active workers: $ACTIVE"
echo

# Check output directory
OUTPUT_DIR="/data/crawl_output"
if [ -d "$OUTPUT_DIR" ]; then
    echo "Output files:"
    ls -lh $OUTPUT_DIR/*.jsonl 2>/dev/null | awk '{print $9, $5}'
    echo

    # Count total lines (pages crawled)
    TOTAL_LINES=$(cat $OUTPUT_DIR/*.jsonl 2>/dev/null | wc -l)
    echo "Total pages crawled: $TOTAL_LINES"
    echo

    # Show disk usage
    DISK_USAGE=$(du -sh $OUTPUT_DIR 2>/dev/null | awk '{print $1}')
    echo "Disk usage: $DISK_USAGE"
else
    echo "Output directory not created yet"
fi

echo
echo "Screen sessions:"
screen -ls | grep crawler

echo
echo "Recent progress (last 5 lines from worker 1 log):"
tail -5 /tmp/crawler_1.log 2>/dev/null || echo "No logs yet"
