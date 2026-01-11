#!/bin/bash
set -e

# SASTRE Backend Startup Script
# Starts the Data Layer (Enrichment) and Control Layer (Orchestrator)

echo "Starting SASTRE Backend..."

# Check .env
if [ ! -f .env ]; then
    echo "Warning: .env file not found in $(pwd)"
fi

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd):$(pwd)/..

# 1. Start Data Layer (Enrichment Server)
echo "Starting Data Layer (Enrichment Server) on port 8200..."
# Using nohup to keep it running if we exit the shell, but in Docker we might want strict process control
# For now, run in background
python3 ../ENRICHMENT/enrichment_server_v3.py > enrichment.log 2>&1 &
ENRICHMENT_PID=$!
echo "Data Layer started with PID $ENRICHMENT_PID"

# Wait for Data Layer to be ready (simple sleep for now)
sleep 2

# 2. Start Control Layer (Orchestrator)
echo "Starting Control Layer (Orchestrator) on port 8201..."
# Run in foreground
exec python3 orchestrator_service.py
