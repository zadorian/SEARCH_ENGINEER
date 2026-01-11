# corporella

Global company intelligence - multi-source corporate registry search with AI-powered entity merging and deduplication.

## Architecture

```
                            corporella
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌──────────────┐                                               │
│  │Company Query │                                               │
│  └──────┬───────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Finder Layer                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │    Name     │  │   Officer   │  │     LEI     │       │   │
│  │  │   Search    │  │   Search    │  │   Search    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Fetcher Layer                         │   │
│  │  ┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐ │   │
│  │  │  Open   ││  OCCRP  ││   SEC   ││  Open   ││LinkedIn │ │   │
│  │  │ Corps   ││  Aleph  ││  EDGAR  ││Ownership││         │ │   │
│  │  │  [OC]   ││  [AL]   ││  [ED]   ││  [OO]   ││  [LI]   │ │   │
│  │  └────┬────┘└────┬────┘└────┬────┘└────┬────┘└────┬────┘ │   │
│  │       └─────┬────┴─────┬────┴─────┬────┴─────┬────┘      │   │
│  │             ▼          ▼          ▼          ▼           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Populator Layer                         │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │              Claude Haiku AI                        │ │   │
│  │  │  • Entity deduplication                             │ │   │
│  │  │  • Contradiction resolution                         │ │   │
│  │  │  • Field merging                                    │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                       │
│                         ▼                                       │
│               ┌─────────────────┐                               │
│               │ Company Profile │                               │
│               │  [OC][AL][ED]   │                               │
│               └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **4-Component Architecture**: Finder, Fetcher, Analyzer, Frontend
- **Hybrid Processing**: Deterministic pattern matching (instant) + Claude Haiku AI (smart deduplication)
- **Global Sources**: OpenCorporates, OCCRP Aleph, SEC EDGAR, OpenOwnership, LinkedIn
- **Real-time Streaming**: WebSocket-based progressive results display
- **Source Attribution**: Every data point tagged with source badges [OC], [AL], [ED], [OO], [LI]

## Quick Start

### 1. Install Dependencies

```bash
cd corporella_claude
pip install -r requirements.txt
```

### 2. Environment Variables (Auto-Loaded!)

✅ **Already configured!** The module automatically loads API keys from the project root `.env` file.

Available keys:
- ✅ `ANTHROPIC_API_KEY` - Claude Haiku 4.5
- ✅ `OPENCORPORATES_API_KEY` - OpenCorporates
- ✅ `ALEPH_API_KEY` - OCCRP Aleph

No manual setup required!

### 3. Run Example Search

```python
from fetcher import GlobalCompanyFetcher
import asyncio

async def main():
    fetcher = GlobalCompanyFetcher()
    results = await fetcher.parallel_search("Apple Inc", country_code="us")
    print(results)

asyncio.run(main())
```

### 4. Start WebSocket Server (Full UI)

```bash
python websocket_server.py
```

Then open `company_profile.html` in your browser and search for companies.

You'll get a structured company profile with **editable fields** that auto-populate from search results.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed component documentation.

## Components

1. **Finder** (`finder.py`) - Search companies by criteria
2. **Fetcher** (`fetcher.py`) - Parallel multi-source data retrieval
3. **Populator** (`populator.py`) - Claude Haiku AI-powered entity merging
4. **Frontend** (`websocket_server.py` + `company_profile.html`) - Real-time structured profile UI
   - Alternative: `client.html` for terminal-style JSON view

## What's NOT Included

- National registry modules (placeholder for future)
- Pre-indexed local search (requires bulk data downloads)
- Risk scoring functionality

## Standalone Design

This module is completely self-contained and does not depend on the main Search Engineer structure. It can be used independently or integrated later.
