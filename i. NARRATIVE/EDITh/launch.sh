#!/bin/bash

# Navigate to EDITh directory
cd "$(dirname "$0")"

# Check if server is already running on port 8080
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo "Server already running, opening browser..."
else
    echo "Starting EDITh server..."
    # Start server in background
    node server.js &
    SERVER_PID=$!
    
    # Wait a moment for server to start
    sleep 2
fi

# Open in default browser
open http://localhost:8080

# Keep terminal open to show server logs
wait