#!/bin/bash
# Helper script to stop a TrailBlazer recording session

if [ -z "$1" ]; then
    echo "Usage: $0 <flow_name>"
    echo "Example: $0 uk_companies_house"
    echo ""
    echo "Or close the browser window to stop recording."
    exit 1
fi

FLOW_NAME="$1"
SIGNAL_FILE="/tmp/wikiman-recording-stop-${FLOW_NAME}.signal"

touch "$SIGNAL_FILE"
echo "✓ Stop signal sent for flow: $FLOW_NAME"
echo "Recording will stop within 1 second."
