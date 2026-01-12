#!/bin/bash

echo "========================================"
echo "  CYMONIDES STANDALONE LAUNCHER"
echo "========================================"
echo ""
echo "This launches the REAL Cymonides from DRILL SEARCH"
echo "as a standalone application."
echo ""
echo "Backend: http://localhost:3000"
echo "Frontend: Access via http://localhost:5173/drill-search-python"
echo ""
echo "Starting..."
echo ""

# Start backend
cd cymonides-standalone
node server.js &
BACKEND_PID=$!

echo "Backend started (PID: $BACKEND_PID)"
echo ""
echo "To access Cymonides, navigate to the main DRILL SEARCH app"
echo "and click on 'DrillSearch Python' or visit the Cymonides panel directly."
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Wait for Ctrl+C
trap "echo 'Shutting down...'; kill $BACKEND_PID" INT TERM
wait $BACKEND_PID
