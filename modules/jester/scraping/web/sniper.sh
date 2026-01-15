#!/bin/bash

# sniper.sh - Fast backlink extractor using offline CC Index lookup
# Usage: ./sniper.sh <target_domain> <source_domain> [archive]

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <target_domain> <source_domain> [archive]"
    echo "Example: $0 soax.com bbc.com CC-MAIN-2024-10"
    exit 1
fi

TARGET=$1
SOURCE=$2
ARCHIVE=${3:-"CC-MAIN-2024-10"}
THREADS=16

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$DIR/cc_offline_sniper.py"
GO_BINARY="$DIR/go/bin/outlinker"
TEMP_JSON="/tmp/wat_list_$$.json"

# Check if python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Check if Go binary exists
if [ ! -f "$GO_BINARY" ]; then
    echo "Error: Go binary not found at $GO_BINARY"
    exit 1
fi

echo "🎯 Sniper Target: $TARGET"
echo "🌐 Source Domain: $SOURCE"
echo "📁 Archive: $ARCHIVE"
echo "---------------------------------------------------"

# Step 1: Get WAT list from Python offline lookup
echo "🔍 Step 1: Looking up WAT files (Offline Mode)..."
python3 "$PYTHON_SCRIPT" "$SOURCE" "$ARCHIVE" > "$TEMP_JSON"

if [ ! -s "$TEMP_JSON" ]; then
    echo "❌ No WAT files found for $SOURCE"
    rm "$TEMP_JSON"
    exit 1
fi

WAT_COUNT=$(grep -o "wat_filename" "$TEMP_JSON" | wc -l)
echo "✅ Found $WAT_COUNT pages. Feeding to Go binary..."

# Step 2: Feed to Go binary
echo "🚀 Step 2: Extracting links..."
"$GO_BINARY" sniper \
    --target-domain="$TARGET" \
    --wat-list="$TEMP_JSON" \
    --archive="$ARCHIVE" \
    --threads="$THREADS"

# Cleanup
rm "$TEMP_JSON"
echo "---------------------------------------------------"
echo "🏁 Done."
