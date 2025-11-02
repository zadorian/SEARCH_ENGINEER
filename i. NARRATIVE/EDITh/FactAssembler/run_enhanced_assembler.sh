#!/bin/bash
# Run the ENHANCED assembler with Batch API and streaming

echo "⚡ ENHANCED 5-PHASE DOCUMENT ASSEMBLER"
echo "========================================"
echo "NEW FEATURES:"
echo "  💰 OpenAI Batch API: 50% cost savings"
echo "  📡 Streaming: Real-time progress"
echo "  ✅ All bulletproof fixes included"
echo "========================================"
echo ""
echo "This runs the COMPLETE assembler with:"
echo "  ✅ Phase 1: GPT-4.1-mini (Batch API)"
echo "  ✅ Phase 2: Gemini verification + caching"
echo "  ✅ Phase 3: Claude Sonnet (streaming)"
echo "  ✅ Phase 4: Claude Opus (streaming)"
echo "  ✅ Phase 5: Gemini final check (cached)"
echo "========================================"
echo ""

# Check if Python 3.10 exists
if [ ! -f "/opt/homebrew/bin/python3.10" ]; then
    echo "❌ ERROR: Python 3.10 not found at /opt/homebrew/bin/python3.10"
    echo "Please install Python 3.10 or update the path"
    exit 1
fi

# Run the enhanced assembler
/opt/homebrew/bin/python3.10 /Users/brain/GARSON/cog_chatbot/cont_int/ensambler_ultra_live_enhanced.py