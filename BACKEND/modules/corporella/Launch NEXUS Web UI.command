#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Starting NEXUS Web UI..."

# Check if port 8000 is in use
PORT_CHECK=$(lsof -ti:8000 2>/dev/null)

if [ ! -z "$PORT_CHECK" ]; then
    echo -e "${YELLOW}⚠️  Port 8000 is already in use (PID: $PORT_CHECK)${NC}"

    # Get full process info
    PROCESS_INFO=$(ps -p $PORT_CHECK -o command= 2>/dev/null)
    echo -e "${YELLOW}Process: $PROCESS_INFO${NC}"

    # Check if it's Python (likely an old server)
    if echo "$PROCESS_INFO" | grep -qi "python"; then
        echo -e "${YELLOW}🔄 Found Python process, assuming old server - killing it...${NC}"
    else
        echo -e "${YELLOW}🔄 Unknown process on port 8000 - killing it anyway...${NC}"
    fi

    # Try graceful shutdown first
    kill $PORT_CHECK 2>/dev/null
    sleep 1

    # Check if still running and force kill if needed
    if lsof -ti:8000 >/dev/null 2>&1; then
        echo -e "${YELLOW}⚡ Process didn't stop gracefully, forcing shutdown...${NC}"
        kill -9 $PORT_CHECK 2>/dev/null
        sleep 1
    fi

    # Verify it's gone
    if lsof -ti:8000 >/dev/null 2>&1; then
        echo -e "${RED}❌ Failed to kill process on port 8000${NC}"
        echo -e "${RED}Try manually: sudo lsof -ti:8000 | xargs kill -9${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ Port 8000 cleared${NC}"
fi

# Final check that port is free
if lsof -ti:8000 >/dev/null 2>&1; then
    echo -e "${RED}❌ Failed to free port 8000. Please manually kill the process and try again.${NC}"
    echo "Run: lsof -ti:8000 | xargs kill -9"
    exit 1
fi

# Change to NEXUS directory
cd "/Volumes/My Book/NEXUS/web_ui"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Could not find NEXUS directory at /Volumes/My Book/NEXUS/web_ui${NC}"
    exit 1
fi

# Start server in background
echo -e "${GREEN}🌟 Starting NEXUS server on port 8000...${NC}"
python3 server.py &
SERVER_PID=$!

# Wait for server to start
sleep 2

# Check if server is actually running
if ! ps -p $SERVER_PID > /dev/null; then
    echo -e "${RED}❌ Server failed to start. Check for errors above.${NC}"
    exit 1
fi

# Open browser
echo -e "${GREEN}🌐 Opening browser at http://localhost:8000${NC}"
open http://localhost:8000

echo -e "${GREEN}✅ NEXUS Web UI is running (PID: $SERVER_PID)${NC}"
echo "Press Ctrl+C to stop the server"

# Keep terminal open and wait for server
wait $SERVER_PID
