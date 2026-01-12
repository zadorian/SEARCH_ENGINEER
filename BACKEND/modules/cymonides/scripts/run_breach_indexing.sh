#!/bin/bash
# Breach Indexing Runner - runs in tmux, maintains tunnel, handles restarts

LOG_DIR="/Volumes/My Book/Raidforums/logs"
CHECKPOINT_DIR="/Volumes/My Book/Raidforums/checkpoints"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$LOG_DIR" "$CHECKPOINT_DIR"

LOG_FILE="$LOG_DIR/indexing_$(date +%Y%m%d_%H%M%S).log"

echo "================================================" | tee -a "$LOG_FILE"
echo "BREACH INDEXING STARTED: $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "================================================" | tee -a "$LOG_FILE"

# Function to ensure SSH tunnel is running
ensure_tunnel() {
    if ! nc -z localhost 9200 2>/dev/null; then
        echo "[$(date)] SSH tunnel down, reconnecting..." | tee -a "$LOG_FILE"
        pkill -f "ssh.*9200.*176.9.2.153" 2>/dev/null
        sleep 1
        sshpass -p 'qxXDgr49_9Hwxp' ssh -o StrictHostKeyChecking=no -L 9200:localhost:9200 root@176.9.2.153 -N -f
        sleep 2
        if nc -z localhost 9200 2>/dev/null; then
            echo "[$(date)] SSH tunnel restored" | tee -a "$LOG_FILE"
        else
            echo "[$(date)] ERROR: Could not restore SSH tunnel" | tee -a "$LOG_FILE"
            return 1
        fi
    fi
    return 0
}

# Initial tunnel check
ensure_tunnel || exit 1

# Run the indexer with resume support
cd "$SCRIPT_DIR"
python3 breach_bulk_indexer.py --resume --reverse 2>&1 | tee -a "$LOG_FILE"

echo "================================================" | tee -a "$LOG_FILE"
echo "BREACH INDEXING FINISHED: $(date)" | tee -a "$LOG_FILE"
echo "================================================" | tee -a "$LOG_FILE"
