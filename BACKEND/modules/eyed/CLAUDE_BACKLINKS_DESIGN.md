# Backlinks Feature Design - Phase 2

## Design Overview

The backlinks feature is mostly working correctly. We just need to fix the data access issue in the display code.

### Current Architecture (Correct)

1. **Two Menu Options** ✅
   - "Get Domain Backlinks" - Shows all backlinks to the domain
   - "Get Page Backlinks" - Shows backlinks to the specific URL

2. **Backend Processing** ✅
   - Uses Ahrefs API with mode parameter
   - Returns structured data with URL, domain, anchor text, etc.

3. **Node Creation** ✅
   - Creates backlinks_query nodes with all data stored properly

### The Fix Required

**Problem**: Display code is looking for properties in wrong location

- Current: `node.urls` and `node.backlinksData`
- Should be: `node.data.urls` and `node.data.backlinksData`

### Implementation Plan

1. **Update showNodeDetails function**:
   - Change line 2677 condition to check `node.data.urls`
   - Change line 2683 to access `node.data.backlinksData`
   - Change line 2680 to access `node.data.searchTerm`
   - Change line 2679 to access `node.data.backlinksMode`

2. **Verify data storage**:
   - Ensure fetchAndDisplayBacklinks stores data correctly
   - Test both domain and page modes

3. **Display Format** (Already Correct):
   - Rich display with domain, URL, anchor text
   - DoFollow/NoFollow indicators
   - Ahrefs rank and first seen date
   - Fallback to simple URL list

### No Major Refactoring Needed!

The architecture is sound. We just need to fix the property access path in the display code.
