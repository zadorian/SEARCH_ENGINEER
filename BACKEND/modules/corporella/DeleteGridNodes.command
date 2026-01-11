#!/bin/zsh
set -euo pipefail
export PATH="$HOME/.n/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd /Users/attic/DRILL_SEARCH/drill-search-app || exit 1
echo "Deleting all Drill Search grid nodes..."
pnpm tsx scripts/clearGridNodes.ts
echo "\nCompleted. Close this window or press any key."
read -n 1 -s -r -p "Press any key to exit..."
