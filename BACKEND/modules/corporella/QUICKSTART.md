# Corporella Claude - Quick Start Guide

## What You Have

A **standalone, compact** global company search module with:
- ✅ 4 components (Finder, Fetcher, Populator, Frontend)
- ✅ Hybrid processing (deterministic + Claude Haiku 4.5 AI)
- ✅ Real-time WebSocket streaming
- ✅ Global sources only (no national modules)
- ✅ Complete documentation

## 🚀 Get Started in 3 Steps

### Step 1: Install Dependencies

```bash
cd corporella_claude
pip install -r requirements.txt
```

### Step 2: ✅ API Keys (Already Configured!)

**Good news**: The module automatically loads API keys from the project root `.env` file!

Keys already available:
- ✅ `ANTHROPIC_API_KEY` - For Claude Haiku 4.5
- ✅ `OPENCORPORATES_API_KEY` - For OpenCorporates search
- ✅ `ALEPH_API_KEY` - For OCCRP Aleph (when implemented)

No setup needed - just run it!

### Step 3: Try It Out!

#### Option A: Run Examples (Command Line)

```bash
python example_usage.py
```

This will run 4 examples showing:
1. Simple search with Finder
2. Parallel multi-source search with Fetcher
3. AI-powered merging with Claude Haiku 4.5
4. Complete workflow (all components together)

#### Option B: Start Web UI (Real-time)

```bash
# Terminal 1: Start WebSocket server
python websocket_server.py

# Terminal 2: Open browser
open company_profile.html
# Or manually open company_profile.html in your browser
```

Then:
1. Enter a company name (e.g., "Apple Inc")
2. Select sources to search
3. Click "Search"
4. Watch the structured profile populate in real-time!

**Left panel**: Search box + raw results stream
**Right panel**: Structured company profile with **editable fields**
- Basic Information (company number, LEI, jurisdiction, status, founded)
- Contact Information (address, website, phone, email)
- Officers & Directors (with "Add Officer" button)
- Ownership Structure (shareholders, beneficial owners)
- Notes (user editable)
- Source badges next to each field showing data origin

## 📁 What's Inside

```
corporella_claude/
├── README.md                # Overview & setup
├── ARCHITECTURE.md          # Detailed system documentation
├── IMPLEMENTATION_GUIDE.md  # Code extraction guide
├── QUICKSTART.md           # This file
├── STATUS.md               # Current status & next steps
├── requirements.txt        # Dependencies
├── entity_template.json    # Company data structure
│
├── finder.py               # Component 1: Criteria-based search
├── fetcher.py              # Component 2: Parallel multi-source
├── populator.py            # Component 2.5: Claude Haiku 4.5 AI merger
├── websocket_server.py     # Component 4: Real-time server
├── company_profile.html    # Component 4: Structured editable profile UI
├── client.html             # Alternative: Terminal-style JSON viewer
├── example_usage.py        # Usage examples
│
└── utils/
    ├── __init__.py
    └── deduplicator.py     # Advanced deduplication
```

## 🎯 Key Features

### Hybrid Processing Model

```
Raw Result Arrives
│
├─ FAST PATH (Deterministic)
│  └─ Instant field mapping → User sees immediately
│
└─ SMART PATH (Claude Haiku 4.5 - runs in parallel)
   └─ Deduplication, contradictions, unexpected data → Profile gets smarter
```

### Global Data Sources

- **OpenCorporates** - Official registries from 130+ jurisdictions
- **OCCRP Aleph** - Investigative data, leaks (TODO: implement)
- **SEC EDGAR** - US public company filings (TODO: implement)
- **OpenOwnership** - Beneficial ownership (TODO: implement)
- **LinkedIn** - Company profiles via HuggingFace (TODO: implement)

Currently, only **OpenCorporates** is fully implemented. Others have TODO placeholders in `fetcher.py`.

## 📚 Read the Docs

- **ARCHITECTURE.md** - Understand the 4-component system
- **IMPLEMENTATION_GUIDE.md** - Implement the TODOs in `fetcher.py`
- **STATUS.md** - See what's done and what's next

## 🔧 Next Steps

### Phase 1: Complete Data Sources

Open `fetcher.py` and implement the TODOs:

1. `_search_aleph()` - OCCRP Aleph integration
2. `_search_edgar()` - SEC EDGAR integration
3. `_search_openownership()` - OpenOwnership integration
4. `_search_linkedin()` - LinkedIn dataset integration

See **IMPLEMENTATION_GUIDE.md** for detailed instructions.

### Phase 2: Test Everything

Run the test checklist:

```bash
# Test each component
python finder.py
python fetcher.py
python populator.py

# Test full workflow
python example_usage.py

# Test WebSocket
python websocket_server.py
# Then open company_profile.html
```

### Phase 3: Customize

- Add more data sources
- Enhance entity template
- Improve deduplication logic
- Add export functionality

## ⚡ Quick Examples

### Example 1: Simple Search

```python
from finder import CompanyFinder

finder = CompanyFinder()
results = finder.search_by_name("Apple Inc", jurisdiction="us_ca")

for company in results['companies']:
    print(f"{company['name']} - {company['company_number']}")
```

### Example 2: Parallel Search

```python
from fetcher import GlobalCompanyFetcher
import asyncio

async def search():
    fetcher = GlobalCompanyFetcher()
    results = await fetcher.parallel_search("Apple Inc")
    print(f"Found data from {len(results['sources_used'])} sources")

asyncio.run(search())
```

### Example 3: AI Merging

```python
from populator import CorporateEntityPopulator
import asyncio

async def merge():
    populator = CorporateEntityPopulator()

    # Sample OpenCorporates result
    result = {
        "source": "opencorporates",
        "companies": [{
            "name": "Apple Inc",
            "company_number": "C0806592",
            "jurisdiction_code": "us_ca"
        }]
    }

    entity = await populator.process_streaming_result(result)
    print(entity)

asyncio.run(merge())
```

## 🐛 Troubleshooting

### "Module not found" errors

```bash
# Make sure you're in the corporella_claude directory
cd corporella_claude

# Install dependencies
pip install -r requirements.txt
```

### "ANTHROPIC_API_KEY not set"

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Or add to .env file
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

### WebSocket won't connect

1. Make sure server is running: `python websocket_server.py`
2. Check server is on port 8765 (you should see: `ws://localhost:8765`)
3. Open company_profile.html (not via file://, use a local server if needed)

### "No results" from OpenCorporates

1. Check your API key is set correctly
2. Try without API key (free tier has rate limits)
3. Test with a well-known company like "Apple Inc"

## 💡 Tips

1. **Start with examples**: Run `example_usage.py` first
2. **Test incrementally**: Test each component before wiring together
3. **Read the docs**: ARCHITECTURE.md explains how it all works
4. **Watch the WebSocket log**: It shows what's happening in real-time
5. **Use source badges**: [OC], [AL], [ED] show where data came from

## 📝 What's NOT Included

- ❌ National registry modules (UK, Germany, etc.) - placeholder for future
- ❌ `fast_registry_search.py` - requires pre-downloaded data
- ❌ Risk scoring functionality
- ❌ Company network analyzer (will be added in Phase 3)

## 🎉 You're Ready!

Pick one:

- **Quick test**: `python example_usage.py`
- **Full experience**: `python websocket_server.py` + open `company_profile.html`
- **Build your own**: See IMPLEMENTATION_GUIDE.md

**Two UI Options:**
- `company_profile.html` - Structured profile with editable fields (recommended)
- `client.html` - Terminal-style JSON viewer (for debugging)

Questions? Check:
- ARCHITECTURE.md - How it works
- IMPLEMENTATION_GUIDE.md - How to extend it
- STATUS.md - What's done and what's next
