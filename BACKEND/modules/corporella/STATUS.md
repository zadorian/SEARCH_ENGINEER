# Corporella Claude - Status Report

## What Has Been Created

✅ **Folder Structure**: `corporella_claude/` at project root
✅ **Documentation**:
  - `README.md` - Quick start guide
  - `ARCHITECTURE.md` - Detailed 4-component system documentation
  - `IMPLEMENTATION_GUIDE.md` - Step-by-step code extraction and wiring guide
  - `STATUS.md` - This file

✅ **Configuration**:
  - `requirements.txt` - All dependencies
  - `entity_template.json` - Standard company data structure

✅ **Folder Structure**:
  - `utils/` directory for shared utilities

## What Needs to Be Done

### Phase 1: Extract Code from `_TEMP_STANDALONE_CORPORELLA`

Follow the mapping table in `IMPLEMENTATION_GUIDE.md`:

1. **Create `finder.py`**
   - Extract from `corporella.py` lines 69-187
   - OpenCorporates search functions
   - Code template provided in IMPLEMENTATION_GUIDE.md

2. **Create `fetcher.py`**
   - Extract from `corporella.py` lines 703-1354
   - Parallel search orchestration
   - Code template provided in IMPLEMENTATION_GUIDE.md

3. **Create `populator.py`**
   - Copy `corporate_entity_populator.py` (full file)
   - **UPGRADE**: Change model to `"claude-3-5-haiku-20241022"` (Haiku 4.5)
   - Keep all deduplication and contradiction detection logic

4. **Create `analyzer.py`**
   - Extract network analysis from `company_network_analyzer.py`
   - Extract parallel person search from `corporella.py` lines 1361-1576
   - **SKIP**: UK-specific code (lines 1-200 of company_network_analyzer.py)

5. **Create `websocket_server.py`**
   - Copy `corporate_websocket_server.py` (full file)
   - Wire together fetcher + populator for real-time streaming

6. **Create `client.html`**
   - Copy `corporate_client.html` (full file)
   - Frontend UI for split-view display

7. **Create `utils/deduplicator.py`**
   - Copy from `from_canonical_ENTITY_folder/utils/deduplicator.py`

8. **Create `utils/parallel_executor.py`**
   - Extract threading utilities from `corporella.py`

### Phase 2: Complete TODOs in `fetcher.py`

The implementation guide provides starter code with TODOs for:

- [ ] `_search_aleph()` - Integrate OCCRP Aleph using `01aleph.py`
- [ ] `_search_edgar()` - Integrate SEC EDGAR using `edgar_integration.py`
- [ ] `_search_openownership()` - Implement OpenOwnership API
- [ ] `_search_linkedin()` - Implement LinkedIn dataset search (HuggingFace)

### Phase 3: Testing

Test checklist from IMPLEMENTATION_GUIDE.md:

- [ ] `finder.py` - Can search OpenCorporates by name and officer
- [ ] `fetcher.py` - Parallel execution works, handles timeouts gracefully
- [ ] `populator.py` - Claude Haiku merges correctly, detects duplicates
- [ ] `websocket_server.py` - Streams results in real-time
- [ ] `client.html` - Displays raw + merged results side-by-side
- [ ] Full workflow - All 4 components work together seamlessly

### Phase 4: Optional Enhancements

Future additions (not required for initial version):

- National registry modules (UK, Germany, etc.) - placeholder ready
- Pre-indexed local search (requires bulk data downloads)
- Additional data sources (Companies House UK, etc.)
- Export functionality (PDF, Excel, JSON)
- Custom visualization for network graphs

## Architecture Summary

### 4 Components

1. **Finder** (`finder.py`) - Criteria-based search
2. **Fetcher** (`fetcher.py`) - Parallel multi-source retrieval
3. **Populator** (`populator.py`) - Claude Haiku AI merging
4. **Frontend** (`websocket_server.py` + `client.html`) - Real-time UI

### Hybrid Processing Model

```
Raw Result Arrives
│
├─ FAST PATH (Deterministic)
│  └─ Instant field mapping → User sees immediately
│
└─ SMART PATH (Claude Haiku running in parallel)
   └─ Deduplication, contradictions, unexpected data → Profile gets smarter
```

### Data Sources (Global Only)

- ✅ OpenCorporates (130+ jurisdictions)
- ✅ OCCRP Aleph (investigative data, leaks)
- ✅ SEC EDGAR (US public company filings)
- ✅ OpenOwnership (beneficial ownership)
- ✅ LinkedIn (company profiles via HuggingFace)

### What's Excluded

- ❌ `fast_registry_search.py` (requires pre-downloaded data)
- ❌ National registry modules (placeholder for future)
- ❌ Risk scoring functionality
- ❌ Companies House UK API (can be added later)

## Quick Start (After Phase 1 Complete)

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
export ANTHROPIC_API_KEY="your-key"
export OPENCORPORATES_API_KEY="your-key"  # Optional

# Test finder
python finder.py

# Test fetcher
python fetcher.py

# Start WebSocket server (full UI)
python websocket_server.py

# Open client.html in browser
```

## Key Design Decisions

1. **Standalone Module**: Completely independent from main Search Engineer
2. **Compact**: Single-purpose, minimal code
3. **Global Sources Only**: No national registries yet (placeholder ready)
4. **Hybrid Processing**: Fast deterministic + smart AI in parallel
5. **Source Attribution**: Every data point tagged with [OC], [AL], [ED], etc.
6. **Progressive Enhancement**: Users see results immediately, profile gets smarter
7. **Claude Haiku 4.5**: Upgraded from 3.0 for better performance

## Files in `_TEMP_STANDALONE_CORPORELLA` NOT Used

These files are excluded from the clean architecture:

- `fast_registry_search.py` - Requires pre-downloaded German registry data
- `company_network_analyzer.py` (lines 1-200) - UK-specific Companies House code
- Any files in `uk/` folder - National modules excluded
- Risk scoring functions - Not required

## Next Action

**Start with Phase 1, Step 1**: Create `finder.py` using the code template in `IMPLEMENTATION_GUIDE.md`.

The implementation guide provides complete, working code examples that you can copy and adapt. Start there!
