#!/usr/bin/env python3
"""
Merge Bright Data retry results into sources_v3.json.
Updates scrape_method to 'brightdata' for sources that were successfully unblocked.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCES_V3_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "sources_v3.json"
BRIGHTDATA_RESULTS_PATH = PROJECT_ROOT / "input_output2" / "matrix" / "brightdata_retry.json"

def merge():
    # Load sources
    with open(SOURCES_V3_PATH) as f:
        sources = json.load(f)
    
    # Load Bright Data results
    with open(BRIGHTDATA_RESULTS_PATH) as f:
        bd_data = json.load(f)
    
    bd_results = bd_data.get("results", {})
    
    # Track updates
    updated = 0
    
    # Update sources that succeeded with Bright Data
    for jur, entries in sources.items():
        for source in entries:
            sid = source.get("id", source.get("domain"))
            if sid in bd_results:
                bd_result = bd_results[sid]
                if bd_result.get("status") == "success":
                    source["scrape_method"] = "brightdata"
                    source["brightdata_validated"] = True
                    if bd_result.get("output_schema"):
                        source["output_schema"] = bd_result["output_schema"]
                    updated += 1
                elif bd_result.get("status") == "still_blocked":
                    source["scrape_method"] = "blocked"  # Mark as permanently blocked
    
    # Save updated sources
    with open(SOURCES_V3_PATH, "w") as f:
        json.dump(sources, f, indent=2)
    
    print(f"Updated {updated} sources with scrape_method='brightdata'")
    print(f"Saved to {SOURCES_V3_PATH}")

if __name__ == "__main__":
    merge()
